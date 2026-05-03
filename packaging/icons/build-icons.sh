#!/usr/bin/env bash
# Build the Windows .ico and macOS .icns app icons from the brand SVG.
#
# Output:
#   packaging/windows/tokenmind.ico   (multi-resolution Windows icon)
#   packaging/macos/tokenmind.icns    (multi-resolution macOS icon)
#
# The renderer composes the white-stroke logo onto a dark rounded square so
# the icon stays legible on any system theme — matching the convention used
# by VS Code, Telegram, Slack and similar apps.
#
# Requirements: rsvg-convert (brew install librsvg), python3 with Pillow.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SVG_SOURCE="${PROJECT_ROOT}/frontend/public/tokenmind-mark.svg"
ICONS_DIR="${PROJECT_ROOT}/packaging/icons"
WINDOWS_ICO="${PROJECT_ROOT}/packaging/windows/tokenmind.ico"
MACOS_ICNS="${PROJECT_ROOT}/packaging/macos/tokenmind.icns"

MASTER_PNG="${ICONS_DIR}/tokenmind-master-1024.png"
WORK_DIR="${ICONS_DIR}/.build"

# Background composition: dark rounded square (#1a1c24) with the logo centered.
BG_COLOR="#1a1c24"
CORNER_RADIUS=180   # 1024 * 0.176 — matches Apple's macOS icon corner ratio
LOGO_SCALE=0.78     # logo occupies ~78% of the canvas

if ! command -v rsvg-convert >/dev/null 2>&1; then
    echo "rsvg-convert not found. Install it first: brew install librsvg" >&2
    exit 1
fi
if [[ ! -f "${SVG_SOURCE}" ]]; then
    echo "Source SVG not found: ${SVG_SOURCE}" >&2
    exit 1
fi

mkdir -p "${ICONS_DIR}" "${WORK_DIR}"
mkdir -p "$(dirname "${WINDOWS_ICO}")" "$(dirname "${MACOS_ICNS}")"

echo "==> Rendering SVG at high resolution"
LOGO_PX=$(python3 -c "print(int(1024 * ${LOGO_SCALE}))")
rsvg-convert -h "${LOGO_PX}" "${SVG_SOURCE}" -o "${WORK_DIR}/logo-fg.png"

echo "==> Composing master 1024x1024 icon onto dark rounded square"
python3 - <<PY
from PIL import Image, ImageDraw

CANVAS = 1024
RADIUS = ${CORNER_RADIUS}
BG = "${BG_COLOR}"

base = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
mask = Image.new("L", (CANVAS, CANVAS), 0)
ImageDraw.Draw(mask).rounded_rectangle(
    [(0, 0), (CANVAS - 1, CANVAS - 1)], RADIUS, fill=255
)

bg = Image.new("RGBA", (CANVAS, CANVAS), BG)
base.paste(bg, mask=mask)

logo = Image.open("${WORK_DIR}/logo-fg.png").convert("RGBA")
lx = (CANVAS - logo.width) // 2
ly = (CANVAS - logo.height) // 2
base.alpha_composite(logo, (lx, ly))

base.save("${MASTER_PNG}", format="PNG")
PY
echo "    master: ${MASTER_PNG}"

echo "==> Generating Windows .ico (16/24/32/48/64/128/256)"
python3 - <<PY
from PIL import Image

master = Image.open("${MASTER_PNG}")
sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
master.save("${WINDOWS_ICO}", format="ICO", sizes=sizes)
PY
echo "    windows: ${WINDOWS_ICO}"

echo "==> Generating macOS .icns (16/32/64/128/256/512/1024 with @2x)"
ICONSET="${WORK_DIR}/tokenmind.iconset"
rm -rf "${ICONSET}" && mkdir -p "${ICONSET}"

declare -a SIZES=(
    "16  icon_16x16.png"
    "32  icon_16x16@2x.png"
    "32  icon_32x32.png"
    "64  icon_32x32@2x.png"
    "128 icon_128x128.png"
    "256 icon_128x128@2x.png"
    "256 icon_256x256.png"
    "512 icon_256x256@2x.png"
    "512 icon_512x512.png"
    "1024 icon_512x512@2x.png"
)
for spec in "${SIZES[@]}"; do
    px="${spec%% *}"
    name="${spec##* }"
    sips -z "${px}" "${px}" "${MASTER_PNG}" --out "${ICONSET}/${name}" >/dev/null
done

iconutil -c icns "${ICONSET}" -o "${MACOS_ICNS}"
echo "    macos:   ${MACOS_ICNS}"

echo "==> Cleaning intermediate files"
rm -rf "${WORK_DIR}"

echo
echo "Done. Source: ${SVG_SOURCE}"
echo "  → ${WINDOWS_ICO}"
echo "  → ${MACOS_ICNS}"
echo "  → ${MASTER_PNG}  (kept as a 1024x1024 reference)"
