"""Custom Hatch build hook for bundling the TokenMind frontend."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

try:
    from hatchling.builders.hooks.plugin.interface import BuildHookInterface
except ImportError:  # pragma: no cover - allows unit tests without hatchling installed globally
    class BuildHookInterface:  # type: ignore[override]
        def __init__(self, *args, **kwargs):
            self.root = kwargs.get("root", "")


def stage_frontend_bundle(dist_dir: Path, bundle_dir: Path) -> None:
    """Copy a built frontend bundle into the Python package tree."""
    if not (dist_dir / "index.html").is_file():
        raise FileNotFoundError(f"Frontend bundle is missing index.html: {dist_dir}")
    if bundle_dir.exists():
        shutil.rmtree(bundle_dir)
    shutil.copytree(dist_dir, bundle_dir)


def ensure_frontend_bundle(project_root: Path) -> tuple[Path, bool]:
    """Ensure the package-local frontend bundle exists for packaging."""
    bundle_dir = project_root / "tokenmind" / "webui"
    if (bundle_dir / "index.html").is_file():
        return bundle_dir, False

    frontend_dir = project_root / "frontend"
    dist_dir = frontend_dir / "dist"
    generated = not bundle_dir.exists()

    if not (dist_dir / "index.html").is_file():
        npm = shutil.which("npm")
        if not npm:
            raise RuntimeError(
                "npm is required to build the TokenMind web UI before packaging. "
                "Install Node.js or provide a prebuilt frontend/dist bundle."
            )

        if not (frontend_dir / "node_modules").exists():
            install_command = [npm, "ci"] if (frontend_dir / "package-lock.json").exists() else [npm, "install"]
            subprocess.run(install_command, cwd=frontend_dir, check=True)

        subprocess.run([npm, "run", "build"], cwd=frontend_dir, check=True)

    stage_frontend_bundle(dist_dir, bundle_dir)
    return bundle_dir, generated


class CustomBuildHook(BuildHookInterface):
    """Build and stage the React frontend so wheels can serve it directly."""

    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict[str, object]) -> None:
        bundle_dir, generated = ensure_frontend_bundle(Path(self.root))
        self._bundle_dir = bundle_dir
        self._generated_bundle = generated
        force_include = build_data.setdefault("force_include", {})
        force_include[str(bundle_dir)] = "tokenmind/webui"

    def finalize(self, version: str, build_data: dict[str, object], artifact_path: str) -> None:
        if getattr(self, "_generated_bundle", False):
            shutil.rmtree(getattr(self, "_bundle_dir"), ignore_errors=True)
