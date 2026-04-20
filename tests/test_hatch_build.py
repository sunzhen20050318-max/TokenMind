from __future__ import annotations

from pathlib import Path
import zipfile

from hatch_build import stage_frontend_bundle


def test_stage_frontend_bundle_replaces_previous_bundle(tmp_path: Path) -> None:
    dist = tmp_path / "frontend-dist"
    dist_assets = dist / "assets"
    dist_assets.mkdir(parents=True)
    (dist / "index.html").write_text("new-index", encoding="utf-8")
    (dist_assets / "app.js").write_text("new-asset", encoding="utf-8")

    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "stale.txt").write_text("old", encoding="utf-8")

    stage_frontend_bundle(dist, bundle)

    assert (bundle / "index.html").read_text(encoding="utf-8") == "new-index"
    assert (bundle / "assets" / "app.js").read_text(encoding="utf-8") == "new-asset"
    assert not (bundle / "stale.txt").exists()


def test_built_wheel_contains_bundled_frontend_assets() -> None:
    wheel = max(Path("dist").glob("tokenmind_ai-*.whl"), key=lambda path: path.stat().st_mtime)

    with zipfile.ZipFile(wheel) as archive:
      names = set(archive.namelist())

    assert "tokenmind/webui/index.html" in names
