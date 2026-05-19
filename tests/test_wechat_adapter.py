"""Offline tests for the WeChat article adapter.

These cover URL detection, anti-crawl heuristics, metadata extraction, and
the body → markdown conversion path. The live HTTP fetch is not covered
here on purpose — mp.weixin.qq.com requires real network and changes its
HTML over time. End-to-end is verified manually by pasting a public
article URL into the frontend.
"""
from __future__ import annotations

from tokenmind.knowledge.adapters.wechat import (
    _clean_body,
    _detect_block,
    _extract_metadata,
    _rewrite_images,
    _to_markdown,
    fetch_wechat_article,
    is_wechat_url,
)


def test_is_wechat_url_recognizes_canonical_path():
    assert is_wechat_url("https://mp.weixin.qq.com/s/abc")
    assert is_wechat_url("http://mp.weixin.qq.com/s?__biz=xx&mid=yy")


def test_is_wechat_url_rejects_others():
    assert not is_wechat_url("https://example.com")
    assert not is_wechat_url("https://mp.weixin.com/s/abc")
    assert not is_wechat_url("not a url")
    assert not is_wechat_url("ftp://mp.weixin.qq.com/s/abc")


def test_detect_block_recognizes_deletion_marker():
    html = "<html><body>该内容已被发布者删除<div class='weui-msg__title'>不存在</div></body></html>"
    assert _detect_block(html, 200, "https://mp.weixin.qq.com/s/abc") == "article_deleted"


def test_detect_block_recognizes_env_check():
    html = "<html><body>环境异常,请验证身份</body></html>"
    assert _detect_block(html, 200, "https://mp.weixin.qq.com/s/abc") == "env_check"


def test_detect_block_recognizes_rate_limit_via_missing_content():
    # 200 OK but no #js_content / #img-content means we got a soft block page
    html = "<html><body>hi</body></html>"
    assert _detect_block(html, 200, "https://mp.weixin.qq.com/s/abc") == "rate_limited"


def test_detect_block_passes_through_valid_article():
    html = '<html><body><div id="js_content">real article</div></body></html>'
    assert _detect_block(html, 200, "https://mp.weixin.qq.com/s/abc") is None


def test_extract_metadata_pulls_title_account_author_publish_time():
    from bs4 import BeautifulSoup
    html = """
    <html>
    <head>
      <meta name="author" content="张三">
      <meta name="description" content="一段摘要">
    </head>
    <body>
      <h1 id="activity-name"> 我的文章标题 </h1>
      <div id="js_name">某公众号</div>
      <script>var ct = "1700000000";</script>
    </body>
    </html>
    """
    soup = BeautifulSoup(html, "html.parser")
    meta = _extract_metadata(soup, html)
    assert meta["title"] == "我的文章标题"
    assert meta["account"] == "某公众号"
    assert meta["author"] == "张三"
    assert meta["digest"] == "一段摘要"
    # publish_time should parse the unix ts and format as Beijing time
    # ts=1700000000 → 2023-11-15 06:13 BJT (UTC+8)
    assert meta["publish_time"] == "2023-11-15 06:13"


def test_rewrite_images_uses_data_src_then_src_then_drops_empty():
    from bs4 import BeautifulSoup
    html = """
    <div id="body">
      <img data-src="https://x.com/1.png" src="placeholder">
      <img src="https://x.com/2.png">
      <img src="">
    </div>
    """
    soup = BeautifulSoup(html, "html.parser")
    body = soup.find(id="body")
    _rewrite_images(body)
    text = str(body)
    assert "![](https://x.com/1.png)" in text
    assert "![](https://x.com/2.png)" in text
    # the empty <img> got replaced with empty string
    assert text.count("![]") == 2


def test_clean_body_drops_scripts_and_media_and_mp_tags():
    from bs4 import BeautifulSoup
    html = """
    <div id="body">
      <p>kept</p>
      <script>var x = 1;</script>
      <iframe src="video"></iframe>
      <mp-common-profile data-id="xx"></mp-common-profile>
      <span data-report-foo="bar" data-mpchecktext="z">keep this</span>
    </div>
    """
    soup = BeautifulSoup(html, "html.parser")
    body = soup.find(id="body")
    _clean_body(body)
    text = str(body)
    assert "<script>" not in text
    assert "<iframe>" not in text
    assert "mp-common-profile" not in text
    # noise attrs gone, but content preserved
    assert "data-report-foo" not in text
    assert "data-mpchecktext" not in text
    assert "keep this" in text
    assert "kept" in text


def test_to_markdown_converts_basic_structure():
    from bs4 import BeautifulSoup
    html = """
    <div id="body">
      <h2>section</h2>
      <p>paragraph with <strong>bold</strong></p>
      <ul><li>item 1</li><li>item 2</li></ul>
    </div>
    """
    soup = BeautifulSoup(html, "html.parser")
    md = _to_markdown(soup.find(id="body"))
    assert "## section" in md
    assert "**bold**" in md
    assert "- item 1" in md
    assert "- item 2" in md


def test_fetch_wechat_article_rejects_non_wechat_url():
    import pytest
    with pytest.raises(Exception) as exc:
        fetch_wechat_article("https://example.com/page")
    assert "WeChat" in str(exc.value)
