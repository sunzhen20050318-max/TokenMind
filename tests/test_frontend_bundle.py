from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from tokenmind.server.frontend import register_frontend_routes, register_missing_frontend_routes


def _make_dist(root: Path) -> Path:
    dist = root / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><html><body>tokenmind-ui</body></html>", encoding="utf-8")
    (assets / "app.js").write_text("console.log('tokenmind-ui');", encoding="utf-8")
    return dist


def test_register_frontend_routes_serves_index_and_assets(tmp_path: Path) -> None:
    dist = _make_dist(tmp_path)
    app = FastAPI()
    register_frontend_routes(app, dist)
    client = TestClient(app)

    index_response = client.get("/")
    asset_response = client.get("/assets/app.js")

    assert index_response.status_code == 200
    assert "tokenmind-ui" in index_response.text
    assert asset_response.status_code == 200
    assert "console.log('tokenmind-ui');" in asset_response.text


def test_register_frontend_routes_falls_back_for_spa_paths(tmp_path: Path) -> None:
    dist = _make_dist(tmp_path)
    app = FastAPI()
    register_frontend_routes(app, dist)
    client = TestClient(app)

    response = client.get("/projects/demo")

    assert response.status_code == 200
    assert "tokenmind-ui" in response.text


def test_register_frontend_routes_preserves_api_404s_and_missing_assets(tmp_path: Path) -> None:
    dist = _make_dist(tmp_path)
    app = FastAPI()
    register_frontend_routes(app, dist)
    client = TestClient(app)

    api_response = client.get("/api/unknown")
    asset_response = client.get("/assets/missing.js")

    assert api_response.status_code == 404
    assert asset_response.status_code == 404


def test_register_missing_frontend_routes_explains_source_setup() -> None:
    app = FastAPI()
    register_missing_frontend_routes(app)
    client = TestClient(app)

    index_response = client.get("/")
    api_response = client.get("/api/unknown")

    assert index_response.status_code == 503
    assert "TokenMind Web UI has not been built yet" in index_response.text
    assert "TokenMind Web UI 还没有构建" in index_response.text
    assert "npm run build" in index_response.text
    assert "http://localhost:18888" in index_response.text
    assert "http://localhost:5173" in index_response.text
    assert api_response.status_code == 404
