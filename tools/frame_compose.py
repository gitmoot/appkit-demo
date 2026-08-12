"""Deterministic, repo-asset-only App Store screenshot compositor."""

from __future__ import annotations

import hashlib
import io
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont
from PIL.PngImagePlugin import PngInfo


HERE = Path(__file__).resolve().parent
FRAME_PATH = HERE / "assets" / "iphone15-black.png"
FONT_PATH = HERE / "assets" / "fonts" / "PlusJakartaSans-ExtraBold.ttf"
BOLD_FONT_PATH = HERE / "assets" / "fonts" / "PlusJakartaSans-Bold.ttf"

ASSET_SHA256 = {
    FRAME_PATH: "4a3572fab045a896e9685b059d4936fa0504edb26f39e14d15c0188d14fa42cf",
    FONT_PATH: "7d60d21b5dec501c77437e80aabd539f1d7a7b0ac7d4ada361d4d42abc7c55ea",
    BOLD_FONT_PATH: "5f5342ef76862b5b5365d1dff1a667629dfa484e388dd602552f647219c3870f",
}

CANVAS_W, CANVAS_H = 1290, 2796
FRAME_SCREEN = (120, 120, 1298, 2675)
SCREEN_W = FRAME_SCREEN[2] - FRAME_SCREEN[0]
SCREEN_H = FRAME_SCREEN[3] - FRAME_SCREEN[1]
# Measured from assets/iphone15-black.png, relative to FRAME_SCREEN.
ISLAND_RECT = (402, 34, 776, 143)
ISLAND_CLEARANCE = 26
CONTENT_TOP = ISLAND_RECT[3] + ISLAND_CLEARANCE
BG_BASE = (14, 14, 18, 255)
PHONE_W_FRAC = 0.82
PHONE_TOP_FRAC = 0.205
HEAD_TOP_FRAC = 0.12
HEAD_COLOR = (245, 245, 250, 255)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


@lru_cache(maxsize=1)
def verify_assets() -> None:
    for path in sorted(ASSET_SHA256, key=lambda item: item.as_posix()):
        if not path.is_file() or path.is_symlink():
            raise RuntimeError("required asset missing or unsafe")
        if _sha256(path) != ASSET_SHA256[path]:
            raise RuntimeError("required asset digest mismatch")


def _brand_rgb(brand_color: str) -> tuple[int, int, int]:
    return tuple(int(brand_color[index : index + 2], 16) for index in (1, 3, 5))


def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(
        FONT_PATH, size, layout_engine=ImageFont.Layout.BASIC
    )


def build_background(brand_color: str) -> Image.Image:
    brand = _brand_rgb(brand_color)
    canvas = Image.new("RGBA", (CANVAS_W, CANVAS_H), BG_BASE)
    glow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(glow)
    draw.ellipse(
        (-190, -690, CANVAS_W + 190, 960),
        fill=(brand[0], brand[1], brand[2], 225),
    )
    glow = glow.filter(ImageFilter.GaussianBlur(220))
    return Image.alpha_composite(canvas, glow)


def frame_screenshot(screen: Image.Image) -> Image.Image:
    verify_assets()
    frame = Image.open(FRAME_PATH).convert("RGBA")
    prepared = screen.convert("RGBA")
    available_height = SCREEN_H - CONTENT_TOP
    scale = min(SCREEN_W / prepared.width, available_height / prepared.height)
    prepared_width = round(prepared.width * scale)
    prepared_height = round(prepared.height * scale)
    prepared = prepared.resize(
        (prepared_width, prepared_height), Image.Resampling.LANCZOS
    )
    fill = prepared.getpixel((0, 0))
    screen_layer = Image.new("RGBA", (SCREEN_W, SCREEN_H), fill)
    offset_x = (SCREEN_W - prepared_width) // 2
    offset_y = CONTENT_TOP + (available_height - prepared_height) // 2
    screen_layer.paste(prepared, (offset_x, offset_y))
    phone = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    phone.paste(screen_layer, FRAME_SCREEN[:2])
    return Image.alpha_composite(phone, frame)


def compose_device(screen: Image.Image) -> Image.Image:
    """Composite only the device and trim transparent asset padding."""

    verify_assets()
    with Image.open(FRAME_PATH) as source:
        frame_bounds = source.convert("RGBA").getbbox()
    if frame_bounds is None:
        raise RuntimeError("frame asset has no visible bounds")
    return frame_screenshot(screen).crop(frame_bounds).convert("RGBA")


def _fit_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    maximum: int,
    start: int,
    minimum: int,
) -> tuple[str, ImageFont.FreeTypeFont]:
    size = start
    while True:
        font = _font(size)
        box = draw.textbbox((0, 0), text, font=font)
        if box[2] - box[0] <= maximum:
            return text, font
        if size == minimum:
            break
        size = max(minimum, size - 2)

    rendered = text
    while rendered:
        box = draw.textbbox((0, 0), rendered, font=font)
        if box[2] - box[0] <= maximum:
            break
        rendered = rendered[:-1]
    return rendered, font


def _line_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> int:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0]


def _best_two_line_split(
    draw: ImageDraw.ImageDraw,
    words: list[str],
    font: ImageFont.FreeTypeFont,
    maximum: int,
) -> list[str] | None:
    """Split words into two balanced lines that both fit `maximum`, or None."""
    best: tuple[int, list[str]] | None = None
    for cut in range(1, len(words)):
        first = " ".join(words[:cut])
        second = " ".join(words[cut:])
        w1 = _line_width(draw, first, font)
        w2 = _line_width(draw, second, font)
        if w1 <= maximum and w2 <= maximum:
            imbalance = abs(w1 - w2)
            if best is None or imbalance < best[0]:
                best = (imbalance, [first, second])
    return best[1] if best else None


def _fit_headline(
    draw: ImageDraw.ImageDraw,
    text: str,
    maximum: int,
    start: int,
    minimum: int,
) -> tuple[list[str], ImageFont.FreeTypeFont]:
    """Fit a headline as one line if it fits, else wrap to a balanced two lines,
    shrinking the font until it fits. Keeps captions inside the margin at a
    comfortable size instead of stretching one line edge-to-edge."""
    words = text.split()
    size = start
    while size >= minimum:
        font = _font(size)
        if _line_width(draw, text, font) <= maximum:
            return [text], font
        if len(words) > 1:
            wrapped = _best_two_line_split(draw, words, font, maximum)
            if wrapped is not None:
                return wrapped, font
        size = max(minimum, size - 2)
        if size == minimum and _line_width(draw, text, _font(size)) > maximum:
            break
    # Last resort: single line at the minimum, truncated by the existing fitter.
    rendered, font = _fit_text(draw, text, maximum, minimum, minimum)
    return [rendered], font


def compose(screen: Image.Image, headline: str, brand_color: str) -> Image.Image:
    verify_assets()
    canvas = build_background(brand_color)
    phone = frame_screenshot(screen)
    phone_width = int(CANVAS_W * PHONE_W_FRAC)
    phone_height = round(phone.height * phone_width / phone.width)
    phone = phone.resize(
        (phone_width, phone_height), Image.Resampling.LANCZOS
    )
    phone_x = (CANVAS_W - phone_width) // 2
    phone_y = int(CANVAS_H * PHONE_TOP_FRAC)
    canvas.alpha_composite(phone, (phone_x, phone_y))

    draw = ImageDraw.Draw(canvas)
    # Tighter margin (0.80) and a lower start size (108) than the old single-line
    # fitter, so a long caption wraps to two balanced lines rather than stretching
    # cramped across the full width.
    max_width = int(CANVAS_W * 0.80)
    lines, font = _fit_headline(draw, headline, max_width, 108, 40)
    ascent, descent = font.getmetrics()
    line_height = ascent + descent + 10
    total_height = line_height * len(lines)
    top = int(CANVAS_H * HEAD_TOP_FRAC)
    # Keep the block roughly centered on the old single-line baseline.
    y = top - (total_height - line_height) // 2
    for line in lines:
        box = draw.textbbox((0, 0), line, font=font)
        width = box[2] - box[0]
        x = (CANVAS_W - width) // 2 - box[0]
        draw.text((x, y - box[1]), line, fill=HEAD_COLOR, font=font)
        y += line_height
    return canvas.convert("RGB")


def save_png(image: Image.Image, output: Path) -> None:
    output.write_bytes(png_bytes(image))


def png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(
        buffer,
        format="PNG",
        optimize=True,
        compress_level=9,
        pnginfo=PngInfo(),
    )
    return buffer.getvalue()
