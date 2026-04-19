"""Helpers for serving the bundled TokenMind web UI."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse


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
