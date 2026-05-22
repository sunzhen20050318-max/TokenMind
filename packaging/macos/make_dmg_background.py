"""Generate the macOS DMG installer background image.

Produces a soft-gradient backdrop with a centred "Drag → Applications"
hint, so users opening the DMG immediately understand how to install.
The two icons themselves are positioned by ``create-dmg`` at coordinates
that line up with the empty slots in this background.

Outputs ``dmg_background.png`` (and the @2x retina variant) next to this
script. Re-run after edits with::

    python3 packaging/macos/make_dmg_background.py

Requires Pillow (``pip install pillow``). Pillow is not a runtime
dependency of TokenMind itself — only needed when rebuilding the DMG.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# Window geometry must match the values in ``packaging/macos/build.sh``.
WINDOW_WIDTH = 660
WINDOW_HEIGHT = 420

# Icon centres (must match the ``--icon`` / ``--app-drop-link`` positions
# passed to create-dmg). Y is the icon centre; create-dmg places the
# label below.
ICON_Y = 200
ICON_LEFT_X = 175
ICON_RIGHT_X = 485

OUTPUT_DIR = Path(__file__).resolve().parent
OUTPUT_FILE = OUTPUT_DIR / "dmg_background.png"
OUTPUT_FILE_2X = OUTPUT_DIR / "dmg_background@2x.png"


def _load_font(size: int) -> ImageFont.ImageFont:
    """Pick the first available macOS-bundled CJK-capable font."""
    candidates = [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
        "/System/Library/Fonts/HelveticaNeue.ttc",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _draw_gradient(canvas: Image.Image) -> None:
    """Vertical soft gradient — light at top, slightly cooler at bottom."""
    width, height = canvas.size
    top = (250, 251, 254)
    bottom = (236, 240, 247)
    pixels = canvas.load()
    for y in range(height):
        t = y / max(1, height - 1)
        r = int(top[0] * (1 - t) + bottom[0] * t)
        g = int(top[1] * (1 - t) + bottom[1] * t)
        b = int(top[2] * (1 - t) + bottom[2] * t)
        for x in range(width):
            pixels[x, y] = (r, g, b, 255)


def _draw_arrow(draw: ImageDraw.ImageDraw, scale: int) -> None:
    """Soft arrow pointing from the app slot to the Applications slot."""
    start_x = (ICON_LEFT_X + 75) * scale
    end_x = (ICON_RIGHT_X - 75) * scale
    y = ICON_Y * scale
    shaft_thickness = max(2, 3 * scale)
    arrow_color = (90, 110, 150, 230)
    # Shaft.
    draw.line(
        [(start_x, y), (end_x, y)],
        fill=arrow_color,
        width=shaft_thickness,
    )
    # Arrowhead.
    head_size = 16 * scale
    draw.polygon(
        [
            (end_x, y),
            (end_x - head_size, y - head_size // 2),
            (end_x - head_size, y + head_size // 2),
        ],
        fill=arrow_color,
    )


def _draw_text(draw: ImageDraw.ImageDraw, scale: int) -> None:
    """Title + hint text positioned above and below the icon row."""
    title = "把 TokenMind 拖到 Applications 文件夹即可安装"
    sub = "Drag TokenMind into your Applications folder to install."
    title_font = _load_font(18 * scale)
    sub_font = _load_font(12 * scale)

    width = WINDOW_WIDTH * scale
    title_y = 50 * scale
    sub_y = title_y + 26 * scale

    for text, font, y, color in (
        (title, title_font, title_y, (40, 45, 70)),
        (sub, sub_font, sub_y, (110, 120, 140)),
    ):
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        draw.text(((width - text_w) // 2, y), text, fill=color, font=font)

    footer = "© TokenMind · 一个本地优先的 AI 智能体框架"
    footer_font = _load_font(10 * scale)
    bbox = draw.textbbox((0, 0), footer, font=footer_font)
    footer_w = bbox[2] - bbox[0]
    draw.text(
        ((width - footer_w) // 2, (WINDOW_HEIGHT - 30) * scale),
        footer,
        fill=(150, 158, 175),
        font=footer_font,
    )


def render(scale: int = 1) -> Image.Image:
    canvas = Image.new(
        "RGBA", (WINDOW_WIDTH * scale, WINDOW_HEIGHT * scale), (255, 255, 255, 255)
    )
    _draw_gradient(canvas)
    draw = ImageDraw.Draw(canvas)
    _draw_arrow(draw, scale)
    _draw_text(draw, scale)
    return canvas


def main() -> None:
    render(scale=1).save(OUTPUT_FILE, "PNG")
    render(scale=2).save(OUTPUT_FILE_2X, "PNG")
    print(f"Wrote {OUTPUT_FILE.relative_to(OUTPUT_DIR.parent.parent)}")
    print(f"Wrote {OUTPUT_FILE_2X.relative_to(OUTPUT_DIR.parent.parent)}")


if __name__ == "__main__":
    main()
