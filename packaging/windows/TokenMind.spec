# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules, copy_metadata


project_root = Path(SPECPATH).parents[1]
frontend_dist = project_root / "frontend" / "dist"
app_icon = project_root / "packaging" / "windows" / "tokenmind.ico"

if not (frontend_dist / "index.html").is_file():
    raise SystemExit(
        "frontend/dist is missing. Run: cd frontend && npm install && npm run build"
    )
if not app_icon.is_file():
    raise SystemExit("packaging/windows/tokenmind.ico is missing.")

datas = copy_metadata("tokenmind-ai")
datas += [
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
    [str(project_root / "packaging" / "windows" / "tokenmind_desktop.py")],
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
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(app_icon),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="TokenMind",
)
