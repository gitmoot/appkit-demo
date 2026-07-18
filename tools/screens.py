"""Deterministic launch-ready app screens and framed marketing renders."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import frame_compose
from stage_support import safe_output_path


SCREEN_W = frame_compose.SCREEN_W
SCREEN_H = frame_compose.SCREEN_H
PAGE = (247, 248, 250)
CARD = (255, 255, 255)
INK = (17, 24, 39)
SECONDARY = (107, 114, 128)
BORDER = (229, 231, 235)
SHADOW = (209, 213, 219)


def _rgb(hex_color: str) -> tuple[int, int, int]:
    return tuple(int(hex_color[index : index + 2], 16) for index in (1, 3, 5))


def _mix(
    start: tuple[int, int, int], end: tuple[int, int, int], amount: float
) -> tuple[int, int, int]:
    return tuple(round(a + (b - a) * amount) for a, b in zip(start, end))


def _font(size: int, extra: bool = False) -> ImageFont.FreeTypeFont:
    path = frame_compose.FONT_PATH if extra else frame_compose.BOLD_FONT_PATH
    return ImageFont.truetype(
        path,
        size,
        layout_engine=ImageFont.Layout.BASIC,
    )


def _fit_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    maximum: int,
    start: int,
    minimum: int = 24,
) -> tuple[str, ImageFont.FreeTypeFont]:
    size = start
    while True:
        font = _font(size, extra=True)
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


def _centered_text(
    draw: ImageDraw.ImageDraw,
    center: tuple[int, int],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int],
) -> None:
    box = draw.textbbox((0, 0), text, font=font)
    x = center[0] - (box[2] - box[0]) // 2 - box[0]
    y = center[1] - (box[3] - box[1]) // 2 - box[1]
    draw.text((x, y), text, font=font, fill=fill)


def _rounded_card(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    radius: int = 24,
    fill: tuple[int, int, int] = CARD,
) -> None:
    x0, y0, x1, y1 = box
    draw.rounded_rectangle((x0, y0 + 5, x1, y1 + 5), radius=radius, fill=SHADOW)
    draw.rounded_rectangle(
        box, radius=radius, fill=fill, outline=BORDER, width=2
    )


def _line_block(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    width: int,
    height: int,
    fill: tuple[int, int, int],
) -> None:
    draw.rounded_rectangle(
        (x, y, x + width, y + height), radius=height // 2, fill=fill
    )


def _diagonal_gradient(
    image: Image.Image,
    box: tuple[int, int, int, int],
    start: tuple[int, int, int],
    end: tuple[int, int, int],
    radius: int,
) -> None:
    x0, y0, x1, y1 = box
    width, height = x1 - x0, y1 - y0
    layer = Image.new("RGB", (width, height), start)
    painter = ImageDraw.Draw(layer)
    maximum = width + height - 2
    for step in range(maximum + 1):
        amount = step / maximum if maximum else 0.0
        color = _mix(start, end, amount)
        first_x = max(0, step - (height - 1))
        first_y = step - first_x
        last_x = min(width - 1, step)
        last_y = step - last_x
        painter.line((first_x, first_y, last_x, last_y), fill=color, width=2)
    mask = Image.new("L", (width, height), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, width - 1, height - 1), radius=radius, fill=255
    )
    image.paste(layer, (x0, y0), mask)


def _status_bar(draw: ImageDraw.ImageDraw) -> None:
    draw.text((72, 40), "9:41", font=_font(28), fill=INK)
    base_x = 930
    for index, height in enumerate((12, 18, 25, 32)):
        x = base_x + index * 18
        draw.rounded_rectangle(
            (x, 68 - height, x + 10, 68), radius=3, fill=INK
        )
    draw.arc((1015, 35, 1071, 83), 210, 330, fill=INK, width=7)
    draw.arc((1027, 48, 1059, 76), 210, 330, fill=INK, width=7)
    draw.ellipse((1040, 65, 1047, 72), fill=INK)
    draw.rounded_rectangle((1090, 40, 1150, 70), radius=8, outline=INK, width=4)
    draw.rounded_rectangle((1096, 46, 1138, 64), radius=4, fill=INK)
    draw.rounded_rectangle((1152, 49, 1158, 61), radius=2, fill=INK)


def _draw_magnifier(
    draw: ImageDraw.ImageDraw, center: tuple[int, int], color: tuple[int, int, int]
) -> None:
    x, y = center
    draw.ellipse((x - 17, y - 17, x + 17, y + 17), outline=color, width=6)
    draw.line((x + 13, y + 13, x + 29, y + 29), fill=color, width=6)


def draw_spark(
    draw: ImageDraw.ImageDraw,
    center: tuple[int, int],
    radius: int,
    color: tuple[int, int, int],
) -> None:
    x, y = center
    points = (
        (x, y - radius),
        (x + radius // 4, y - radius // 4),
        (x + radius, y),
        (x + radius // 4, y + radius // 4),
        (x, y + radius),
        (x - radius // 4, y + radius // 4),
        (x - radius, y),
        (x - radius // 4, y - radius // 4),
    )
    draw.polygon(points, fill=color)


def _draw_feature_glyph(
    draw: ImageDraw.ImageDraw,
    kind: int,
    center: tuple[int, int],
) -> None:
    x, y = center
    if kind == 1:
        draw.ellipse((x - 65, y - 65, x + 65, y + 65), outline=(255, 255, 255), width=18)
        draw.ellipse((x - 18, y - 18, x + 18, y + 18), fill=(255, 255, 255))
    elif kind == 2:
        draw.polygon(
            ((x, y - 78), (x + 78, y + 66), (x - 78, y + 66)),
            outline=(255, 255, 255),
        )
        draw.line((x, y - 78, x + 78, y + 66, x - 78, y + 66, x, y - 78), fill=(255, 255, 255), width=16)
    else:
        draw_spark(draw, center, 82, (255, 255, 255))


def _draw_tab_icon(
    draw: ImageDraw.ImageDraw,
    kind: str,
    center: tuple[int, int],
    color: tuple[int, int, int],
    brand: tuple[int, int, int],
) -> None:
    x, y = center
    if kind == "home":
        draw.line((x - 24, y, x, y - 22, x + 24, y), fill=color, width=8)
        draw.rounded_rectangle((x - 17, y - 2, x + 17, y + 26), radius=5, outline=color, width=7)
    elif kind == "search":
        _draw_magnifier(draw, (x - 3, y - 3), color)
    elif kind == "plus":
        draw.ellipse((x - 38, y - 38, x + 38, y + 38), fill=brand)
        draw.line((x - 17, y, x + 17, y), fill=(255, 255, 255), width=8)
        draw.line((x, y - 17, x, y + 17), fill=(255, 255, 255), width=8)
    elif kind == "bell":
        draw.arc((x - 25, y - 28, x + 25, y + 26), 190, 350, fill=color, width=8)
        draw.line((x - 27, y + 12, x + 27, y + 12), fill=color, width=8)
        draw.ellipse((x - 6, y + 20, x + 6, y + 32), fill=color)
    else:
        draw.ellipse((x - 15, y - 29, x + 15, y + 1), outline=color, width=7)
        draw.arc((x - 31, y - 1, x + 31, y + 49), 190, 350, fill=color, width=8)


def _bottom_tabs(
    draw: ImageDraw.ImageDraw,
    brand: tuple[int, int, int],
    active: str,
) -> None:
    top = 2290
    draw.rectangle((0, top, SCREEN_W, SCREEN_H), fill=CARD)
    draw.line((0, top, SCREEN_W, top), fill=BORDER, width=2)
    kinds = ("home", "search", "plus", "bell", "person")
    centers = (118, 354, 589, 824, 1060)
    for kind, x in zip(kinds, centers):
        is_active = kind == active
        color = brand if is_active else SECONDARY
        _draw_tab_icon(draw, kind, (x, 2370), color, brand)
        if is_active:
            label = "Home" if kind == "home" else "Profile"
            _centered_text(draw, (x, 2452), label, _font(24), brand)
    draw.rounded_rectangle((440, 2523, 738, 2537), radius=7, fill=INK)


def _base_screen() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (SCREEN_W, SCREEN_H), PAGE)
    draw = ImageDraw.Draw(image)
    _status_bar(draw)
    return image, draw


def _home_screen(values: dict[str, object], brand: tuple[int, int, int]) -> Image.Image:
    image, draw = _base_screen()
    rendered_name, nav_font = _fit_text(draw, str(values["app_name"]), 1034, 64)
    draw.text((72, 128), rendered_name, font=nav_font, fill=INK)

    draw.rounded_rectangle((64, 238, 1114, 326), radius=44, fill=CARD, outline=BORDER, width=2)
    _draw_magnifier(draw, (116, 280), SECONDARY)
    draw.text((168, 259), "Search", font=_font(30), fill=SECONDARY)

    chips = (("For you", 64, 272, True), ("Recent", 288, 500, False), ("Saved", 516, 720, False))
    for label, left, right, selected in chips:
        fill = brand if selected else CARD
        color = (255, 255, 255) if selected else SECONDARY
        outline = brand if selected else BORDER
        draw.rounded_rectangle((left, 358, right, 426), radius=34, fill=fill, outline=outline, width=2)
        _centered_text(draw, ((left + right) // 2, 392), label, _font(26), color)

    title_widths = (510, 440, 560)
    body_widths = ((560, 470), (510, 590), (600, 425))
    meta_widths = (178, 142, 194)
    for index, top in enumerate((466, 1006, 1546), start=1):
        _rounded_card(draw, (64, top, 1114, top + 500))
        gradient_box = (90, top + 34, 390, top + 356)
        _diagonal_gradient(
            image,
            gradient_box,
            _mix(brand, CARD, 0.62),
            brand,
            28,
        )
        _draw_feature_glyph(draw, index, (240, top + 195))
        _line_block(draw, 432, top + 68, title_widths[index - 1], 34, INK)
        _line_block(draw, 432, top + 148, body_widths[index - 1][0], 24, SECONDARY)
        _line_block(draw, 432, top + 197, body_widths[index - 1][1], 24, SECONDARY)
        draw.ellipse((432, top + 390, 448, top + 406), fill=brand)
        _line_block(draw, 468, top + 388, meta_widths[index - 1], 20, _mix(SECONDARY, CARD, 0.25))
        _line_block(draw, 432, top + 438, 118, 18, _mix(brand, CARD, 0.45))

    _bottom_tabs(draw, brand, "home")
    return image


def _detail_screen(brand: tuple[int, int, int]) -> Image.Image:
    image, draw = _base_screen()
    draw.line((95, 158, 70, 183, 95, 208), fill=INK, width=10)
    draw.ellipse((1042, 146, 1110, 214), outline=BORDER, fill=CARD, width=2)
    draw.line((1076, 183, 1076, 151), fill=INK, width=7)
    draw.line((1061, 165, 1076, 150, 1091, 165), fill=INK, width=7)
    draw.line((1058, 181, 1058, 199, 1094, 199, 1094, 181), fill=INK, width=6)

    hero = (64, 250, 1114, 906)
    _diagonal_gradient(image, hero, _mix(brand, CARD, 0.58), brand, 34)
    draw_spark(draw, (589, 578), 116, (255, 255, 255))
    draw.ellipse((515, 504, 663, 652), outline=(255, 255, 255), width=10)

    draw.text((64, 984), "Getting started", font=_font(56, extra=True), fill=INK)
    chips = (("Quick guide", 64, 280), ("6 min", 296, 444))
    tint = _mix(brand, CARD, 0.90)
    for label, left, right in chips:
        draw.rounded_rectangle((left, 1073, right, 1135), radius=31, fill=tint)
        _centered_text(draw, ((left + right) // 2, 1104), label, _font(24), brand)

    paragraphs = (
        (990, 930, 770, 440),
        (1010, 860, 940, 520),
        (940, 1000, 720, 360),
    )
    for group, top in zip(paragraphs, (1238, 1530, 1822)):
        for line, width in enumerate(group):
            _line_block(draw, 64, top + line * 52, width, 22, _mix(SECONDARY, CARD, 0.18))

    draw.rounded_rectangle((64, 2160, 1114, 2298), radius=32, fill=brand)
    _centered_text(draw, (589, 2229), "Get started", _font(36, extra=True), (255, 255, 255))
    draw.rounded_rectangle((440, 2523, 738, 2537), radius=7, fill=INK)
    return image


def _stats_screen(brand: tuple[int, int, int]) -> Image.Image:
    image, draw = _base_screen()
    draw.text((64, 128), "Progress", font=_font(64, extra=True), fill=INK)

    ring_box = (100, 340, 610, 850)
    draw.arc(ring_box, 0, 359, fill=BORDER, width=54)
    draw.arc(ring_box, -90, -90 + round(360 * 0.76), fill=brand, width=54)
    _centered_text(draw, (355, 580), "76%", _font(82, extra=True), INK)
    _centered_text(draw, (355, 664), "this week", _font(28), SECONDARY)

    _rounded_card(draw, (642, 330, 1114, 888))
    draw.text((682, 378), "Weekly activity", font=_font(34), fill=INK)
    values = (32, 48, 40, 64, 56, 72, 60)
    labels = ("M", "T", "W", "T", "F", "S", "S")
    chart_bottom = 800
    tint = _mix(brand, CARD, 0.75)
    for index, value in enumerate(values):
        left = 682 + index * 58
        height = value * 4
        fill = brand if index == 6 else tint
        draw.rounded_rectangle((left, chart_bottom - height, left + 34, chart_bottom), radius=17, fill=fill)
        _centered_text(draw, (left + 17, 835), labels[index], _font(20), SECONDARY)

    stats = (
        ("12", "day streak"),
        ("4.8", "avg"),
        ("36", "done"),
        ("8", "saved"),
    )
    boxes = (
        (64, 1014, 568, 1424),
        (610, 1014, 1114, 1424),
        (64, 1474, 568, 1884),
        (610, 1474, 1114, 1884),
    )
    for index, (value, label) in enumerate(stats):
        box = boxes[index]
        _rounded_card(draw, box)
        glyph_x = box[0] + 58
        glyph_y = box[1] + 58
        draw.rounded_rectangle((glyph_x, glyph_y, glyph_x + 74, glyph_y + 74), radius=22, fill=_mix(brand, CARD, 0.90))
        if index % 2:
            draw.ellipse((glyph_x + 22, glyph_y + 22, glyph_x + 52, glyph_y + 52), fill=brand)
        else:
            draw_spark(draw, (glyph_x + 37, glyph_y + 37), 23, brand)
        draw.text((box[0] + 54, box[1] + 164), value, font=_font(72, extra=True), fill=INK)
        draw.text((box[0] + 54, box[1] + 270), label, font=_font(30), fill=SECONDARY)

    _bottom_tabs(draw, brand, "person")
    return image


def make_screen(values: dict[str, object], index: int) -> Image.Image:
    brand = _rgb(str(values["brand_color"]))
    if index == 1:
        return _home_screen(values, brand)
    if index == 2:
        return _detail_screen(brand)
    if index == 3:
        return _stats_screen(brand)
    raise ValueError("screen index must be 1, 2, or 3")


def build_screen_images(values: dict[str, object]) -> dict[int, Image.Image]:
    return {index: make_screen(values, index) for index in (1, 2, 3)}


def build_framed_screens(
    values: dict[str, object],
    screen_images: dict[int, Image.Image] | None = None,
) -> dict[int, Image.Image]:
    frame_compose.verify_assets()
    if screen_images is None:
        screen_images = build_screen_images(values)
    headlines = {
        1: str(values["headline_1"]),
        2: str(values["headline_2"]),
        3: str(values["headline_3"]),
    }
    return {
        index: frame_compose.compose(
            screen_images[index],
            headlines[index],
            str(values["brand_color"]),
        )
        for index in (1, 2, 3)
    }


def build_device_screens(
    values: dict[str, object],
    screen_images: dict[int, Image.Image] | None = None,
) -> dict[int, Image.Image]:
    frame_compose.verify_assets()
    if screen_images is None:
        screen_images = build_screen_images(values)
    return {
        index: frame_compose.compose_device(screen_images[index])
        for index in (1, 2, 3)
    }


def build_render_assets(
    values: dict[str, object],
) -> tuple[dict[int, Image.Image], dict[int, Image.Image]]:
    screen_images = build_screen_images(values)
    return (
        build_framed_screens(values, screen_images),
        build_device_screens(values, screen_images),
    )


def encode_framed_screens(framed: dict[int, Image.Image]) -> dict[int, bytes]:
    return {index: frame_compose.png_bytes(framed[index]) for index in (1, 2, 3)}


def encode_device_screens(devices: dict[int, Image.Image]) -> dict[int, bytes]:
    return {index: frame_compose.png_bytes(devices[index]) for index in (1, 2, 3)}


def expected_screenshot_relpaths(values: dict[str, object]) -> list[str]:
    paths: list[str] = []
    for locale in list(values["locales"]):
        for index in (1, 2, 3):
            paths.append(f"out/screenshots/{locale}/shot_{index}.png")
    return sorted(paths)


def render_screenshots(
    values: dict[str, object], framed_pngs: dict[int, bytes] | None = None
) -> list[Path]:
    if framed_pngs is None:
        framed_pngs = encode_framed_screens(build_framed_screens(values))
    outputs: list[Path] = []
    for locale in list(values["locales"]):
        for index in (1, 2, 3):
            output = safe_output_path(f"out/screenshots/{locale}/shot_{index}.png")
            output.write_bytes(framed_pngs[index])
            outputs.append(output)
    return sorted(outputs, key=lambda path: path.as_posix())
