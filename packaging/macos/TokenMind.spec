# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for TokenMind macOS .app bundle.

Mirrors packaging/windows/TokenMind.spec; the main difference is the
BUNDLE node that wraps the COLLECT into a Mac-native .app with proper
Info.plist metadata and the .icns app icon.
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules


project_root = Path(SPECPATH).parents[1]
frontend_dist = project_root / "frontend" / "dist"
app_icon = project_root / "packaging" / "macos" / "tokenmind.icns"
version = "0.1.7"

if not (frontend_dist / "index.html").is_file():
    raise SystemExit(
        "frontend/dist is missing. Run: cd frontend && npm install && npm run build"
    )
if not app_icon.is_file():
    raise SystemExit(
        "packaging/macos/tokenmind.icns is missing. "
        "Run: bash packaging/icons/build-icons.sh"
    )

datas = [
    (str(frontend_dist), "tokenmind/webui"),
    (str(project_root / "tokenmind" / "templates"), "tokenmind/templates"),
    (str(project_root / "tokenmind" / "skills"), "tokenmind/skills"),
]

bridge_dir = project_root / "bridge"
if bridge_dir.is_dir():
    datas.append((str(bridge_dir), "tokenmind/bridge"))

hiddenimports = []
hiddenimports += collect_submodules("tokenmind.channels")
hiddenimports += collect_submodules("tokenmind.creative")
hiddenimports += collect_submodules("tokenmind.providers")
hiddenimports += collect_submodules("tokenmind.server.routes")

a = Analysis(
    [str(project_root / "packaging" / "macos" / "tokenmind_desktop.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="TokenMind",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX is unreliable on macOS; the Mach-O loader can refuse compressed binaries
    console=False,  # GUI mode — no terminal window when launched from Finder
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,  # Builds for the host arch (arm64 on Apple Silicon, x86_64 on Intel)
    codesign_identity=None,  # Set externally via build.sh when signing
    entitlements_file=None,
    icon=str(app_icon),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="TokenMind",
)

app = BUNDLE(
    coll,
    name="TokenMind.app",
    icon=str(app_icon),
    bundle_identifier="com.tokenmind.desktop",
    version=version,
    info_plist={
        "CFBundleName": "TokenMind",
        "CFBundleDisplayName": "TokenMind",
        "CFBundleVersion": version,
        "CFBundleShortVersionString": version,
        "CFBundleIdentifier": "com.tokenmind.desktop",
        "CFBundleExecutable": "TokenMind",
        "LSMinimumSystemVersion": "11.0",
        "NSHighResolutionCapable": True,
        "NSRequiresAquaSystemAppearance": False,  # Allow dark mode
        "LSApplicationCategoryType": "public.app-category.productivity",
        "NSHumanReadableCopyright": "Copyright © 2026 TokenMind. All rights reserved.",
        # Networking permissions — TokenMind runs a local FastAPI server and
        # talks to LLM providers over HTTPS. The default sandbox-free build
        # only needs these as documentation, but they make notarization
        # smoother if you later add an entitlements file.
        "NSAppTransportSecurity": {
            "NSAllowsLocalNetworking": True,
        },
    },
)
