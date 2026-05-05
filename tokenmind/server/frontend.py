"""Helpers for serving the bundled TokenMind web UI."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse


# Index HTML must always revalidate. After an in-place upgrade (0.1.x → 0.1.y)
# the on-disk index.html now references new content-hashed bundles, but the
# browser would happily keep serving the old cached HTML for hours under
# heuristic caching — leading to "I installed the new version but it still
# says 0.1.9". Forcing revalidation lets ETag-based 304s stay efficient
# while guaranteeing the upgrade is picked up on the very next page load.
_NO_CACHE_HEADERS = {
    "Cache-Control": "no-cache, no-store, must-revalidate",
    "Pragma": "no-cache",
    "Expires": "0",
}

# Vite emits content-hashed filenames under /assets/ (e.g.
# `assets/index-DpMZhPXy.js`). A new release means a new hash means a new
# URL — caching them forever is safe and avoids an unnecessary round-trip
# on every page load.
_IMMUTABLE_HEADERS = {
    "Cache-Control": "public, max-age=31536000, immutable",
}


def resolve_frontend_dist_dir() -> Path | None:
    """Return the best available frontend build directory."""
    source_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    packaged_dist = Path(__file__).resolve().parents[1] / "webui"

    for candidate in (source_dist, packaged_dist):
        if (candidate / "index.html").is_file():
            return candidate
    return None


def register_frontend_routes(app: FastAPI, frontend_dir: Path) -> None:
    """Serve static frontend files and SPA fallback routes."""
    base_dir = frontend_dir.resolve()
    index_path = base_dir / "index.html"

    if not index_path.is_file():
        raise FileNotFoundError(f"TokenMind frontend bundle is missing index.html: {index_path}")

    reserved_prefixes = ("api", "ws")
    reserved_exact = {"docs", "redoc", "openapi.json"}

    def _asset_for_path(full_path: str) -> Path | None:
        target = (base_dir / full_path).resolve()
        try:
            target.relative_to(base_dir)
        except ValueError:
            return None
        if target.is_file():
            return target
        return None

    @app.get("/", include_in_schema=False)
    async def frontend_index() -> FileResponse:
        return FileResponse(index_path, headers=_NO_CACHE_HEADERS)

    @app.get("/{full_path:path}", include_in_schema=False)
    async def frontend_entry(full_path: str) -> FileResponse:
        normalized = full_path.strip("/")
        if normalized in reserved_exact or any(
            normalized == prefix or normalized.startswith(f"{prefix}/") for prefix in reserved_prefixes
        ):
            raise HTTPException(status_code=404, detail="Not Found")

        asset = _asset_for_path(normalized)
        if asset is not None:
            # Hashed bundles under /assets/ are safe to cache forever; everything
            # else (favicon, robots.txt, etc.) shares the no-cache policy with
            # index.html so a stale copy can't survive an upgrade.
            headers = (
                _IMMUTABLE_HEADERS
                if normalized.startswith("assets/")
                else _NO_CACHE_HEADERS
            )
            return FileResponse(asset, headers=headers)

        if Path(normalized).suffix:
            raise HTTPException(status_code=404, detail="Not Found")

        return FileResponse(index_path, headers=_NO_CACHE_HEADERS)


def register_missing_frontend_routes(app: FastAPI) -> None:
    """Serve a helpful setup page when source checkouts have no built frontend."""

    reserved_prefixes = ("api", "ws")
    reserved_exact = {"docs", "redoc", "openapi.json"}
    html = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>TokenMind Web UI not built</title>
  <style>
    :root { color-scheme: dark; }
    body {
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      background: #0d0d10;
      color: #f4f4f5;
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    main {
      width: min(760px, calc(100vw - 40px));
      border: 1px solid #2f3037;
      border-radius: 24px;
      padding: 32px;
      background: linear-gradient(145deg, #18181d, #101014);
      box-shadow: 0 30px 90px rgba(0, 0, 0, 0.45);
    }
    h1 { margin: 0 0 12px; font-size: 28px; }
    p { margin: 0 0 18px; color: #b8bac7; line-height: 1.7; }
    .eyebrow {
      margin-bottom: 8px;
      color: #8d91a2;
      font-size: 13px;
      letter-spacing: .08em;
      text-transform: uppercase;
    }
    code, pre {
      font-family: "Cascadia Code", "SFMono-Regular", Consolas, monospace;
    }
    pre {
      margin: 12px 0 22px;
      padding: 16px;
      overflow-x: auto;
      border-radius: 16px;
      background: #060607;
      border: 1px solid #2a2b31;
      color: #ffffff;
    }
    .muted { color: #898c99; font-size: 14px; }
  </style>
</head>
<body>
  <main>
    <p class="eyebrow">TokenMind Web UI has not been built yet</p>
    <h1>TokenMind Web UI 还没有构建</h1>
    <p>
      后端已经启动，但当前源码目录里还没有构建好的 React 前端。
      如果你是通过 <code>git clone</code> 运行源码，请选择下面其中一种方式。
    </p>
    <p><strong>方式 A：源码生产模式，使用默认 18888 端口：</strong></p>
    <pre>cd frontend
npm install
npm run build
cd ..
tokenmind web --port 18888</pre>
    <p>如果你启动后端时使用了自定义端口，请把命令里的 <code>18888</code> 换成你的实际端口。</p>
    <p><strong>方式 B：前端开发模式，使用 Vite 热更新：</strong></p>
    <pre>tokenmind web --port 18888
cd frontend
npm install
npm run dev</pre>
    <p>开发模式下请打开 <code>http://localhost:5173</code>，不要打开当前后端端口。</p>
    <p class="muted">
      如果你是通过 pip 包或桌面安装包安装，生产 Web UI 会随程序一起打包，
      正常可以直接打开 <code>http://localhost:18888</code>。
    </p>
  </main>
</body>
</html>
"""

    @app.get("/", include_in_schema=False)
    async def missing_frontend_index() -> HTMLResponse:
        return HTMLResponse(html, status_code=503)

    @app.get("/{full_path:path}", include_in_schema=False)
    async def missing_frontend_entry(full_path: str) -> HTMLResponse:
        normalized = full_path.strip("/")
        if normalized in reserved_exact or any(
            normalized == prefix or normalized.startswith(f"{prefix}/") for prefix in reserved_prefixes
        ):
            raise HTTPException(status_code=404, detail="Not Found")
        return HTMLResponse(html, status_code=503)
