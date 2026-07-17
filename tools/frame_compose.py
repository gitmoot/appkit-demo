"""Deterministic, repo-asset-only App Store screenshot compositor."""

from __future__ import annotations

import hashlib
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
BG_BASE = (14, 14, 18, 255)
PHONE_W_FRAC = 0.82
PHONE_TOP_FRAC = 0.205
HEAD_TOP_FRAC = 0.066
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
    if prepared.size != (SCREEN_W, SCREEN_H):
        prepared = prepared.resize(
            (SCREEN_W, SCREEN_H), Image.Resampling.LANCZOS
        )
    phone = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    phone.paste(prepared, FRAME_SCREEN[:2])
    return Image.alpha_composite(phone, frame)


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
    max_width = int(CANVAS_W * 0.86)
    size = 132
    while size > 18:
        font = _font(size)
        box = draw.textbbox((0, 0), headline, font=font)
        if box[2] - box[0] <= max_width:
            break
        size -= 2
    font = _font(size)
    box = draw.textbbox((0, 0), headline, font=font)
    width = box[2] - box[0]
    x = (CANVAS_W - width) // 2 - box[0]
    y = int(CANVAS_H * HEAD_TOP_FRAC) - box[1]
    draw.text((x, y), headline, fill=HEAD_COLOR, font=font)
    return canvas.convert("RGB")


def save_png(image: Image.Image, output: Path) -> None:
    image.save(
        output,
        format="PNG",
        optimize=False,
        compress_level=9,
        pnginfo=PngInfo(),
    )
