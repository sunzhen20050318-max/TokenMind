"""Helpers for serving the bundled TokenMind web UI."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse


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
        return FileResponse(index_path)

    @app.get("/{full_path:path}", include_in_schema=False)
    async def frontend_entry(full_path: str) -> FileResponse:
        normalized = full_path.strip("/")
        if normalized in reserved_exact or any(
            normalized == prefix or normalized.startswith(f"{prefix}/") for prefix in reserved_prefixes
        ):
            raise HTTPException(status_code=404, detail="Not Found")

        asset = _asset_for_path(normalized)
        if asset is not None:
            return FileResponse(asset)

        if Path(normalized).suffix:
            raise HTTPException(status_code=404, detail="Not Found")

        return FileResponse(index_path)


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
    <h1>TokenMind Web UI has not been built yet</h1>
    <p>
      The backend is running, but this source checkout does not contain a built React frontend.
      Choose one of the following source-development workflows.
    </p>
    <p><strong>Production-style source run on this same port:</strong></p>
    <pre>cd frontend
npm install
npm run build
cd ..
tokenmind web --port 8080</pre>
    <p><strong>Frontend development mode with hot reload:</strong></p>
    <pre>tokenmind web --port 8080
cd frontend
npm install
npm run dev</pre>
    <p>Then open <code>http://localhost:5173</code> for development mode.</p>
    <p class="muted">
      Installed pip and desktop builds bundle the production Web UI, so they can serve
      <code>http://localhost:8080</code> directly.
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
