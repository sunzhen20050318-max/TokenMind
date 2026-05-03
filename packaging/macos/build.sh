#!/usr/bin/env bash
# Build the TokenMind macOS .app and DMG installer.
#
# Outputs:
#   dist-macos/TokenMind.app                       (raw application bundle)
#   dist-installer/TokenMind-<version>-<arch>.dmg  (drag-to-install DMG)
#
# Flags:
#   --skip-frontend     Reuse existing frontend/dist (don't run npm build)
#   --skip-dmg          Stop after building the .app
#   --sign IDENTITY     Apple Developer ID for codesigning (e.g. "Developer ID Application: Your Name (TEAMID)")
#   --no-clean          Reuse existing build/ directory
#
# Requirements:
#   - Python 3.11+ with PyInstaller (pip install -e ".[macos]")
#   - Node.js 20+ (for the frontend build, unless --skip-frontend)
#   - create-dmg (brew install create-dmg) for nicer DMG layout — falls back
#     to hdiutil if create-dmg is not installed.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SPEC_PATH="${PROJECT_ROOT}/packaging/macos/TokenMind.spec"
FRONTEND_DIR="${PROJECT_ROOT}/frontend"
DIST_DIR="${PROJECT_ROOT}/dist-macos"
WORK_DIR="${PROJECT_ROOT}/build-macos"
INSTALLER_DIR="${PROJECT_ROOT}/dist-installer"

SKIP_FRONTEND=0
SKIP_DMG=0
NO_CLEAN=0
SIGN_IDENTITY=""

while (( $# > 0 )); do
    case "$1" in
        --skip-frontend) SKIP_FRONTEND=1 ;;
        --skip-dmg) SKIP_DMG=1 ;;
        --no-clean) NO_CLEAN=1 ;;
        --sign) SIGN_IDENTITY="$2"; shift ;;
        -h|--help)
            sed -n '2,17p' "$0"
            exit 0
            ;;
        *) echo "Unknown option: $1" >&2; exit 2 ;;
    esac
    shift
done

step() {
    echo
    echo "==> $1"
}

extract_version() {
    python3 -c "import re,sys; m=re.search(r'(?m)^version\\s*=\\s*\"([^\"]+)\"', open(sys.argv[1]).read()); print(m.group(1) if m else '0.0.0')" \
        "${PROJECT_ROOT}/pyproject.toml"
}

VERSION="$(extract_version)"
ARCH="$(uname -m)"
case "${ARCH}" in
    arm64) ARCH_LABEL="arm64" ;;
    x86_64) ARCH_LABEL="x64" ;;
    *) ARCH_LABEL="${ARCH}" ;;
esac

step "Verifying PyInstaller"
python3 -m PyInstaller --version >/dev/null || {
    echo "PyInstaller not installed. Run: pip install -e \".[macos]\"" >&2
    exit 1
}

if [[ ${SKIP_FRONTEND} -eq 0 ]]; then
    step "Building frontend"
    pushd "${FRONTEND_DIR}" >/dev/null
    if [[ ! -d node_modules ]]; then
        if [[ -f package-lock.json ]]; then
            npm ci
        else
            npm install
        fi
    fi
    npm run build
    popd >/dev/null
fi

if [[ ! -f "${FRONTEND_DIR}/dist/index.html" ]]; then
    echo "frontend/dist/index.html missing. Build the frontend first." >&2
    exit 1
fi

if [[ ! -f "${PROJECT_ROOT}/packaging/macos/tokenmind.icns" ]]; then
    echo "tokenmind.icns missing. Run: bash packaging/icons/build-icons.sh" >&2
    exit 1
fi

step "Building .app via PyInstaller (${ARCH_LABEL})"
if [[ ${NO_CLEAN} -eq 0 ]]; then
    rm -rf "${DIST_DIR}" "${WORK_DIR}"
fi
python3 -m PyInstaller --noconfirm --clean \
    --distpath "${DIST_DIR}" \
    --workpath "${WORK_DIR}" \
    "${SPEC_PATH}"

APP_BUNDLE="${DIST_DIR}/TokenMind.app"
if [[ ! -d "${APP_BUNDLE}" ]]; then
    echo "Build failed: ${APP_BUNDLE} not produced" >&2
    exit 1
fi
echo "    .app: ${APP_BUNDLE}"

if [[ -n "${SIGN_IDENTITY}" ]]; then
    step "Code signing with: ${SIGN_IDENTITY}"
    codesign --force --deep --options runtime \
        --sign "${SIGN_IDENTITY}" "${APP_BUNDLE}"
    codesign --verify --deep --strict --verbose=2 "${APP_BUNDLE}"
    echo "    Signed. To notarize:"
    echo "    xcrun notarytool submit \"${APP_BUNDLE}.zip\" --apple-id ... --team-id ... --password ... --wait"
    echo "    xcrun stapler staple \"${APP_BUNDLE}\""
fi

if [[ ${SKIP_DMG} -eq 1 ]]; then
    echo
    echo "Done (skipped DMG). App: ${APP_BUNDLE}"
    exit 0
fi

step "Building DMG"
mkdir -p "${INSTALLER_DIR}"
DMG_NAME="TokenMind-${VERSION}-${ARCH_LABEL}.dmg"
DMG_PATH="${INSTALLER_DIR}/${DMG_NAME}"
rm -f "${DMG_PATH}"

if command -v create-dmg >/dev/null 2>&1; then
    create-dmg \
        --volname "TokenMind ${VERSION}" \
        --window-pos 200 120 \
        --window-size 600 380 \
        --icon-size 110 \
        --icon "TokenMind.app" 165 180 \
        --hide-extension "TokenMind.app" \
        --app-drop-link 435 180 \
        --no-internet-enable \
        "${DMG_PATH}" \
        "${APP_BUNDLE}"
else
    echo "    create-dmg not installed (brew install create-dmg). Falling back to hdiutil."
    STAGE_DIR="$(mktemp -d)"
    cp -R "${APP_BUNDLE}" "${STAGE_DIR}/"
    ln -s /Applications "${STAGE_DIR}/Applications"
    hdiutil create -volname "TokenMind ${VERSION}" \
        -srcfolder "${STAGE_DIR}" \
        -ov -format UDZO "${DMG_PATH}"
    rm -rf "${STAGE_DIR}"
fi

echo
echo "Done."
echo "  App: ${APP_BUNDLE}"
echo "  DMG: ${DMG_PATH}"
