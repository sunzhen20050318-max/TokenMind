"""Fetch a WeChat (mp.weixin.qq.com) article and return a clean markdown
document plus parsed metadata.

This is a vendored, slimmed-down port of the standalone
fetch_wechat_article tool living at /Users/ent/fetch_wechat_article. The
original is async, ships with a VLM-based image transcription path,
Tencent COS upload, an in-memory cache, and a LangGraph tool wrapper. None
of those are useful inside TokenMind's Wiki KB pipeline — we just need the
HTML → markdown conversion so the WikiCompileRunner can do its job on the
resulting source page. So this module keeps:

  - WeChat URL detection
  - HTTP fetch with retry + anti-crawl signature detection
  - HTML parse: title, account, author, publish_time, digest, body
  - DOM cleanup: drop script/style/mp-*/iframe/audio/video, strip tracker
    attributes, convert <img> to standard ![](url) instead of placeholders
  - markdownify-based body conversion
  - header composition (title + byline + digest + body)

and drops everything image-related beyond the inline ![](url). The Wiki
editor LLM downstream is free to mention images by position; we do not
need to caption them ourselves.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup, NavigableString, Tag
from loguru import logger
from markdownify import markdownify


_DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_VALID_HOSTS = frozenset({"mp.weixin.qq.com"})
_BJT = timezone(timedelta(hours=8))

_DROP_TAGS = ("script", "style")
_MEDIA_TAGS = ("mpvoice", "iframe", "qqmusic", "audio", "video")
_NOISE_ATTR_PREFIXES = ("data-report-", "data-track-", "data-mpa-", "_ke_saved_")
_NOISE_ATTR_EXACT = frozenset({"data-mpchecktext"})


class WechatFetchError(Exception):
    """Raised when a WeChat article can't be fetched or parsed."""


@dataclass
class WechatArticle:
    url: str
    title: str
    account: str | None = None
    author: str | None = None
    publish_time: str | None = None
    digest: str | None = None
    markdown: str = ""
    warnings: list[str] = field(default_factory=list)


def is_wechat_url(url: str) -> bool:
    """True iff `url` parses as an http(s) mp.weixin.qq.com link."""
    try:
        p = urlparse(url)
    except ValueError:
        return False
    return p.scheme in ("http", "https") and p.netloc in _VALID_HOSTS


def fetch_wechat_article(url: str, *, timeout: float = 30.0) -> WechatArticle:
    """Synchronous fetch + parse. Returns a WechatArticle.

    Sync on purpose: the wiki ingest pipeline runs in a worker thread via
    asyncio.to_thread, and adding another event loop layer here would just
    complicate the dispatch. httpx has a perfectly good sync client.
    """
    if not is_wechat_url(url):
        raise WechatFetchError(f"not a WeChat URL: {url}")

    html, final_url, status = _fetch_with_retry(url, timeout=timeout)
    block = _detect_block(html, status, final_url)
    if block:
        raise WechatFetchError(f"anti-crawl: {block} @ {final_url}")

    soup = BeautifulSoup(html, "html.parser")
    meta = _extract_metadata(soup, html)
    if not meta["title"]:
        raise WechatFetchError(f"missing #activity-name: {final_url}")

    body = soup.find(id="js_content")
    if not isinstance(body, Tag):
        raise WechatFetchError(f"missing #js_content: {final_url}")

    warnings: list[str] = []
    _rewrite_images(body)
    _clean_body(body)
    body_md = _to_markdown(body)

    return WechatArticle(
        url=final_url,
        title=meta["title"] or "",
        account=meta["account"],
        author=meta["author"],
        publish_time=meta["publish_time"],
        digest=meta["digest"],
        markdown=_compose(meta, body_md),
        warnings=warnings,
    )


# ---- HTTP -----------------------------------------------------------------

def _fetch_with_retry(
    url: str,
    *,
    timeout: float,
    max_retries: int = 2,
) -> tuple[str, str, int]:
    last_exc: Exception | None = None
    with httpx.Client(
        timeout=timeout,
        follow_redirects=True,
        headers={"User-Agent": _DEFAULT_UA},
    ) as client:
        for attempt in range(max_retries + 1):
            try:
                r = client.get(url)
            except (httpx.NetworkError, httpx.TimeoutException) as exc:
                last_exc = exc
                if attempt < max_retries:
                    time.sleep(2**attempt)
                    continue
                raise WechatFetchError(f"network error: {exc}") from exc

            if 500 <= r.status_code < 600 and attempt < max_retries:
                time.sleep(2**attempt)
                continue
            if r.status_code in (403, 429):
                raise WechatFetchError(f"rate limited (HTTP {r.status_code})")
            if r.status_code >= 400:
                raise WechatFetchError(f"HTTP {r.status_code}")
            return r.text, str(r.url), r.status_code
    raise WechatFetchError("retry loop exited without response") from last_exc


def _detect_block(html: str, status: int, final_url: str) -> str | None:
    host = urlparse(final_url).netloc
    if host not in _VALID_HOSTS:
        return "invalid_url"
    if (
        "该内容已被发布者删除" in html
        or "该内容已被发布者发布" in html
        or "weui-msg__title" in html
    ) and 'id="js_content"' not in html:
        return "article_deleted"
    if "环境异常" in html or "请验证身份" in html:
        return "env_check"
    if (
        status == 200
        and 'id="js_content"' not in html
        and 'id="img-content"' not in html
    ):
        return "rate_limited"
    return None


# ---- DOM ------------------------------------------------------------------

def _rewrite_images(body: Tag) -> None:
    """Convert <img> to a synthetic <md-img> element carrying just the URL,
    so markdownify outputs `![](url)`. WeChat lazy-loads images via
    data-src; fall back to src. Empty URLs get stripped entirely."""
    for img in list(body.find_all("img")):
        url = (img.get("data-src") or img.get("src") or "").strip()
        if not url:
            img.replace_with(NavigableString(""))
            continue
        # Build a plain markdown image marker. markdownify preserves
        # NavigableString text as-is.
        img.replace_with(NavigableString(f"![]({url})"))


def _clean_body(body: Tag) -> None:
    for tag in body.find_all(_DROP_TAGS):
        tag.decompose()
    for tag in body.find_all(_MEDIA_TAGS):
        tag.replace_with(NavigableString("\n*[此处为视频/音频]*\n"))
    for tag in body.find_all(lambda t: t.name and t.name.startswith("mp-")):
        tag.decompose()
    _strip_noise_attrs(body)


def _strip_noise_attrs(node: Tag) -> None:
    for tag in node.find_all(True):
        attrs_to_remove = [
            k
            for k in tag.attrs
            if any(k.startswith(p) for p in _NOISE_ATTR_PREFIXES) or k in _NOISE_ATTR_EXACT
        ]
        for k in attrs_to_remove:
            del tag.attrs[k]


def _to_markdown(body: Tag) -> str:
    md: str = markdownify(
        str(body),
        heading_style="ATX",
        bullets="-",
        strip=list(_DROP_TAGS),
    )
    md = re.sub(r"\n{3,}", "\n\n", md)
    md = "\n".join(line.rstrip() for line in md.splitlines())
    return md.strip()


# ---- metadata -------------------------------------------------------------

def _extract_metadata(soup: BeautifulSoup, html: str) -> dict[str, str | None]:
    title_tag = soup.find(id="activity-name")
    title = title_tag.get_text(strip=True) if title_tag else ""
    return {
        "title": title,
        "account": _safe_text(soup.find(id="js_name")),
        "author": _extract_author(soup),
        "digest": (
            _safe_meta_content(soup, "description")
            or _safe_meta_content(soup, "og:description", attr="property")
        ),
        "publish_time": _extract_publish_time(html),
    }


def _extract_author(soup: BeautifulSoup) -> str | None:
    for cand in (
        _safe_meta_content(soup, "author"),
        _safe_meta_content(soup, "og:article:author", attr="property"),
        _safe_text(soup.find(id="js_author_name")),
    ):
        if cand:
            return cand
    return None


def _extract_publish_time(html: str) -> str | None:
    m = re.search(r'var\s+ct\s*=\s*"(\d+)"', html)
    if not m:
        m = re.search(r"var\s+oriCreateTime\s*=\s*['\"](\d+)['\"]", html)
    if not m:
        return None
    try:
        ts = int(m.group(1))
    except ValueError:
        return None
    if ts <= 0 or ts > 4_000_000_000:
        return None
    return datetime.fromtimestamp(ts, tz=_BJT).strftime("%Y-%m-%d %H:%M")


def _safe_text(tag: Tag | None) -> str | None:
    if tag is None:
        return None
    text = tag.get_text(strip=True)
    return text or None


def _safe_meta_content(
    soup: BeautifulSoup,
    name: str,
    *,
    attr: str = "name",
) -> str | None:
    tag = soup.find("meta", attrs={attr: name})
    if not tag:
        return None
    content = tag.get("content")
    if not content:
        return None
    return content.strip() or None


# ---- composition ----------------------------------------------------------

def _compose(meta: dict[str, str | None], body_md: str) -> str:
    lines: list[str] = [f"# {meta['title']}", ""]
    sub = [p for p in (meta.get("account"), meta.get("author"), meta.get("publish_time")) if p]
    if sub:
        lines.append(f"*{' · '.join(sub)}*")
        lines.append("")
    if meta.get("digest"):
        lines.append(f"> {meta['digest']}")
        lines.append("")
    lines.append("---")
    lines.append("")
    return "\n".join(lines) + body_md
