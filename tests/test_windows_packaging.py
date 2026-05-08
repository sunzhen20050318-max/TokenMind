from __future__ import annotations

import socket
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_desktop_launcher_finds_next_free_port() -> None:
    from tokenmind.desktop.launcher import find_available_port

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        occupied_port = sock.getsockname()[1]

        assert find_available_port(occupied_port, attempts=2) == occupied_port + 1


def test_pyinstaller_spec_bundles_frontend_and_runtime_assets() -> None:
    spec = (ROOT / "packaging" / "windows" / "TokenMind.spec").read_text(encoding="utf-8")

    assert (ROOT / "packaging" / "windows" / "tokenmind.ico").is_file()
    assert "icon=str(app_icon)" in spec
    assert "frontend_dist" in spec
    assert "frontend_dist / \"index.html\"" in spec
    assert "\"tokenmind/webui\"" in spec
    assert "\"tokenmind/templates\"" in spec
    assert "\"tokenmind/skills\"" in spec
    assert "copy_metadata(\"tokenmind-ai\")" in spec
    assert "collect_submodules(\"tokenmind.channels\")" in spec
    assert "name=\"TokenMind\"" in spec


def test_windows_installer_script_wraps_onedir_build() -> None:
    iss = (ROOT / "packaging" / "windows" / "TokenMind.iss").read_text(encoding="utf-8")

    assert "#define AppIcon" in iss
    assert "SetupIconFile={#AppIcon}" in iss
    # Shortcut IconFilename must reference the runtime install dir, not the
    # build-machine absolute path baked in via {#AppIcon}. The .ico itself
    # is staged into {app} via [Files] for that to resolve at runtime.
    assert 'IconFilename: "{app}\\tokenmind.ico"' in iss
    assert 'DestDir: "{app}"; DestName: "tokenmind.ico"' in iss
    assert "OutputBaseFilename=TokenMindSetup-{#MyAppVersion}" in iss
    assert 'Source: "{#AppDist}\\*"' in iss
    assert "recursesubdirs" in iss
    assert 'Filename: "{app}\\TokenMind.exe"' in iss
    assert "DefaultDirName={localappdata}\\Programs\\TokenMind" in iss


def test_windows_build_script_builds_frontend_before_pyinstaller() -> None:
    script = (ROOT / "packaging" / "windows" / "build-installer.ps1").read_text(encoding="utf-8")

    assert "npm run build" in script
    assert "python -m PyInstaller" in script
    assert 'python -m pip install ".[windows]"' in script
    assert "TokenMind.spec" in script
    assert "TokenMind.iss" in script
    assert "dist-installer" in script
