"""Deterministic synthetic app screens and framed marketing renders."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import frame_compose
from stage_support import safe_output_path


SCREEN_W = frame_compose.SCREEN_W
SCREEN_H = frame_compose.SCREEN_H


def _rgb(hex_color: str) -> tuple[int, int, int]:
    return tuple(int(hex_color[index : index + 2], 16) for index in (1, 3, 5))


def _mix(
    start: tuple[int, int, int], end: tuple[int, int, int], amount: float
) -> tuple[int, int, int]:
    return tuple(round(a + (b - a) * amount) for a, b in zip(start, end))


def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(
        frame_compose.BOLD_FONT_PATH,
        size,
        layout_engine=ImageFont.Layout.BASIC,
    )


def _fit_font(draw: ImageDraw.ImageDraw, text: str, maximum: int, start: int) -> ImageFont.FreeTypeFont:
    size = start
    while size > 24:
        font = _font(size)
        box = draw.textbbox((0, 0), text, font=font)
        if box[2] - box[0] <= maximum:
            return font
        size -= 2
    return _font(size)


def make_screen(values: dict[str, object], index: int) -> Image.Image:
    brand = _rgb(str(values["brand_color"]))
    dark = _mix(brand, (10, 12, 22), 0.82)
    light = _mix(brand, (255, 255, 255), 0.20)
    image = Image.new("RGB", (SCREEN_W, SCREEN_H), dark)
    draw = ImageDraw.Draw(image)
    for y in range(SCREEN_H):
        amount = y / (SCREEN_H - 1)
        draw.line((0, y, SCREEN_W, y), fill=_mix(light, dark, amount))

    app_name = str(values["app_name"])
    title_font = _fit_font(draw, app_name, SCREEN_W - 150, 82)
    draw.text((76, 116), app_name, fill=(255, 255, 255), font=title_font)
    draw.text(
        (76, 230),
        str(values["tagline"]),
        fill=(235, 238, 248),
        font=_fit_font(draw, str(values["tagline"]), SCREEN_W - 150, 38),
    )

    panel = (255, 255, 255)
    ink = (27, 31, 42)
    muted = (118, 125, 145)
    accent = _mix(brand, (255, 255, 255), 0.10)
    draw.rounded_rectangle((58, 360, 1120, 2350), radius=54, fill=panel)

    if index == 1:
        draw.text((112, 430), "Today", fill=ink, font=_font(56))
        for row, width in enumerate((620, 520, 670, 580)):
            top = 580 + row * 330
            draw.rounded_rectangle((112, top, 1066, top + 245), radius=34, fill=(245, 246, 250))
            draw.ellipse((156, top + 62, 268, top + 174), fill=accent)
            draw.rounded_rectangle((312, top + 62, 312 + width, top + 92), radius=15, fill=ink)
            draw.rounded_rectangle((312, top + 126, 800, top + 150), radius=12, fill=muted)
    elif index == 2:
        draw.text((112, 430), "Your space", fill=ink, font=_font(56))
        for row in range(3):
            top = 590 + row * 480
            draw.rounded_rectangle((112, top, 1066, top + 380), radius=40, fill=(245, 246, 250))
            draw.rounded_rectangle((158, top + 52, 366, top + 260), radius=30, fill=accent)
            draw.rounded_rectangle((418, top + 74, 950, top + 112), radius=19, fill=ink)
            draw.rounded_rectangle((418, top + 148, 860, top + 176), radius=14, fill=muted)
            draw.rounded_rectangle((418, top + 214, 720, top + 282), radius=26, fill=brand)
    else:
        draw.text((112, 430), "Progress", fill=ink, font=_font(56))
        draw.arc((224, 570, 954, 1300), 205, 515, fill=(225, 228, 237), width=70)
        draw.arc((224, 570, 954, 1300), 205, 425, fill=brand, width=70)
        draw.text((468, 820), "74%", fill=ink, font=_font(84))
        for row, width in enumerate((760, 680, 800)):
            top = 1450 + row * 250
            draw.rounded_rectangle((140, top, 1040, top + 150), radius=30, fill=(245, 246, 250))
            draw.rounded_rectangle((180, top + 55, 180 + width, top + 92), radius=18, fill=accent)

    draw.rounded_rectangle((402, 2422, 776, 2438), radius=8, fill=(225, 228, 237))
    return image


def expected_screenshot_relpaths(values: dict[str, object]) -> list[str]:
    paths: list[str] = []
    for locale in list(values["locales"]):
        for index in (1, 2, 3):
            paths.append(f"out/screenshots/{locale}/shot_{index}.png")
    return sorted(paths)


def render_screenshots(values: dict[str, object]) -> list[Path]:
    frame_compose.verify_assets()
    base_screens = {index: make_screen(values, index) for index in (1, 2, 3)}
    headlines = {
        1: str(values["headline_1"]),
        2: str(values["headline_2"]),
        3: str(values["headline_3"]),
    }
    outputs: list[Path] = []
    for locale in list(values["locales"]):
        for index in (1, 2, 3):
            output = safe_output_path(f"out/screenshots/{locale}/shot_{index}.png")
            composed = frame_compose.compose(
                base_screens[index], headlines[index], str(values["brand_color"])
            )
            frame_compose.save_png(composed, output)
            outputs.append(output)
    return sorted(outputs, key=lambda path: path.as_posix())
