#!/usr/bin/env python3
"""
App Store screenshot composer — "floating device" style.

Composites an app screenshot into a photorealistic iPhone frame PNG, places the
framed phone on a dark violet-glow background, and adds a sentence-case headline
on top. Matches the reference the user supplied (Game Night / In your pocket).

Output: 1290x2796 (App Store Connect 6.7").
"""
import argparse, os
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(__file__)
FRAME_PATH = os.path.join(HERE, "assets", "iphone15-black.png")
FONT_PATH = os.environ.get("ASO_FONT") or os.path.join(
    HERE, "assets", "fonts", "PlusJakartaSans-ExtraBold.ttf")

# App Store 6.7" canvas
CANVAS_W, CANVAS_H = 1290, 2796

# Frame screen cutout (measured from the supplied frame, 1419x2796)
FRAME_W, FRAME_H = 1419, 2796
SCREEN = (120, 120, 1298, 2675)   # x0, y0, x1, y1

# Layout
BG_BASE = (14, 14, 18)            # #0E0E12
GLOW = (150, 92, 255)             # violet bloom
PHONE_W_FRAC = 0.82               # phone width as fraction of canvas
PHONE_TOP_FRAC = 0.205            # phone top as fraction of canvas height
HEAD_TOP_FRAC = 0.066
HEAD_SIZE = 132
HEAD_LINE_GAP = 18
HEAD_COLOR = (245, 245, 250)


def build_background():
    yy, xx = np.mgrid[0:CANVAS_H, 0:CANVAS_W].astype(np.float32)
    cx, cy = CANVAS_W * 0.5, CANVAS_H * -0.02
    d = np.sqrt(((xx - cx) / (CANVAS_W * 0.72)) ** 2 +
                ((yy - cy) / (CANVAS_H * 0.40)) ** 2)
    inten = np.clip(1.0 - d, 0.0, 1.0) ** 1.7
    base = np.array(BG_BASE, np.float32)
    glow = np.array(GLOW, np.float32)
    img = base[None, None, :] + inten[:, :, None] * (glow - base)[None, None, :]
    img = np.clip(img, 0, 255).astype(np.uint8)
    return Image.fromarray(img, "RGB").convert("RGBA")


def frame_screenshot(shot_path):
    """Composite the screenshot into the iPhone frame; return RGBA phone.

    The FULL screenshot is shown with no vertical crop: it is contain-fit into
    the screen below a status-bar gap that clears the Dynamic Island. Any small
    leftover (thin side margins) is backfilled with the screen's own top colour.
    """
    frame = Image.open(FRAME_PATH).convert("RGBA")
    alpha = np.asarray(frame)[:, :, 3]
    x0, y0, x1, y1 = SCREEN
    sw, sh = x1 - x0, y1 - y0

    # Measure the Dynamic Island (opaque cluster inside the top of the screen)
    # so the status-bar gap clears it exactly.
    cx = (x0 + x1) // 2
    di = alpha[y0:y0 + 320, cx - 260:cx + 260] > 200
    rows = np.where(di.any(axis=1))[0]
    di_bottom = (y0 + int(rows.max())) if len(rows) else (y0 + 180)
    gap = (di_bottom - y0) + 26

    shot = Image.open(shot_path).convert("RGBA")
    # contain-fit the whole screenshot into the area below the status bar
    avail_w, avail_h = sw, sh - gap
    scale = min(avail_w / shot.width, avail_h / shot.height)
    nw, nh = round(shot.width * scale), round(shot.height * scale)
    rs = shot.resize((nw, nh), Image.LANCZOS)

    top_row = np.asarray(rs)[0:6].reshape(-1, 4)
    fill = tuple(int(c) for c in np.median(top_row, axis=0))
    screen_layer = Image.new("RGBA", (sw, sh), fill)
    ox = (sw - nw) // 2
    oy = gap + (avail_h - nh) // 2
    screen_layer.paste(rs, (ox, oy))

    phone = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    phone.paste(screen_layer, (x0, y0))
    phone = Image.alpha_composite(phone, frame)
    return phone


def word_wrap(draw, text, font, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = f"{cur} {w}".strip()
        if draw.textlength(t, font=font) <= max_w:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def compose(shot_path, lines, output):
    canvas = build_background()
    draw = ImageDraw.Draw(canvas)

    # ── Phone ───────────────────────────────────────────────
    phone = frame_screenshot(shot_path)
    pw = int(CANVAS_W * PHONE_W_FRAC)
    ph = round(phone.height * pw / phone.width)
    phone = phone.resize((pw, ph), Image.LANCZOS)
    px = (CANVAS_W - pw) // 2
    py = int(CANVAS_H * PHONE_TOP_FRAC)
    canvas.alpha_composite(phone, (px, py))

    # ── Headline ────────────────────────────────────────────
    # Keep each supplied line on one line: shrink the font until the widest fits.
    max_w = int(CANVAS_W * 0.86)
    size = HEAD_SIZE
    while size > 74:
        font = ImageFont.truetype(FONT_PATH, size)
        if all(draw.textlength(ln, font=font) <= max_w for ln in lines):
            break
        size -= 4
    font = ImageFont.truetype(FONT_PATH, size)
    all_lines = lines
    y = int(CANVAS_H * HEAD_TOP_FRAC)
    for ln in all_lines:
        bbox = draw.textbbox((0, 0), ln, font=font)
        h = bbox[3] - bbox[1]
        draw.text((CANVAS_W // 2, y - bbox[1]), ln, fill=HEAD_COLOR, font=font, anchor="mt")
        y += h + HEAD_LINE_GAP

    canvas.convert("RGB").save(output, "PNG")
    print(f"✓ {output} ({CANVAS_W}x{CANVAS_H})")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--screenshot", required=True)
    p.add_argument("--line1", required=True)
    p.add_argument("--line2", default="")
    p.add_argument("--output", required=True)
    a = p.parse_args()
    lines = [a.line1] + ([a.line2] if a.line2 else [])
    compose(a.screenshot, lines, a.output)


if __name__ == "__main__":
    main()
