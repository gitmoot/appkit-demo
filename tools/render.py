"""Shared deterministic store, web, legal, and brand-asset renderers."""

from __future__ import annotations

import base64
import re
from pathlib import Path
from urllib.parse import quote

from PIL import Image, ImageDraw, ImageFont

import frame_compose
import screens
from inputs import escape_html
from stage_support import safe_output_path


REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = REPO_ROOT / "templates"
COPY_FILES = (
    "description",
    "keywords",
    "name",
    "promotional_text",
    "release_notes",
    "subtitle",
)
COPY_LIMITS = {
    "name": 30,
    "promotional_text": 170,
    "subtitle": 30,
}
ICON_SIZES = (1024, 180, 167, 152, 120, 32)
_TOKEN_RE = re.compile(r"\{([a-z][a-z0-9_]*)\}")


class TemplateError(RuntimeError):
    pass


def _rgb(hex_color: str) -> tuple[int, int, int]:
    return tuple(int(hex_color[index : index + 2], 16) for index in (1, 3, 5))


def _mix(
    start: tuple[int, int, int], end: tuple[int, int, int], amount: float
) -> tuple[int, int, int]:
    return tuple(round(a + (b - a) * amount) for a, b in zip(start, end))


def _font(size: int, extra: bool = False) -> ImageFont.FreeTypeFont:
    path = frame_compose.FONT_PATH if extra else frame_compose.BOLD_FONT_PATH
    return ImageFont.truetype(path, size, layout_engine=ImageFont.Layout.BASIC)


def _fit_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    maximum: int,
    start: int,
    minimum: int,
    extra: bool = True,
) -> tuple[str, ImageFont.FreeTypeFont]:
    size = start
    while True:
        font = _font(size, extra=extra)
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


def _gradient_square(
    size: tuple[int, int],
    start: tuple[int, int, int],
    end: tuple[int, int, int],
) -> Image.Image:
    width, height = size
    image = Image.new("RGB", size, start)
    draw = ImageDraw.Draw(image)
    maximum = width + height - 2
    for step in range(maximum + 1):
        amount = step / maximum if maximum else 0.0
        color = _mix(start, end, amount)
        first_x = max(0, step - (height - 1))
        first_y = step - first_x
        last_x = min(width - 1, step)
        last_y = step - last_x
        draw.line((first_x, first_y, last_x, last_y), fill=color, width=2)
    return image


def _read_template(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        raise RuntimeError("template missing or unsafe")
    return path.read_text(encoding="utf-8")


def _replace(
    template: str,
    replacements: dict[str, object],
    html_target: bool,
    safe_html_tokens: frozenset[str] = frozenset(),
) -> str:
    def substitute(match: re.Match[str]) -> str:
        key = match.group(1)
        try:
            value = replacements[key]
        except KeyError as error:
            raise TemplateError("unknown template token") from error
        if html_target and key not in safe_html_tokens:
            return escape_html(value)
        return str(value)

    return _TOKEN_RE.sub(substitute, template)


def _write_text(relative: str, content: str) -> Path:
    output = safe_output_path(relative)
    output.write_text(content, encoding="utf-8", newline="\n")
    return output


def _write_png(relative: str, image: Image.Image) -> tuple[Path, bytes]:
    output = safe_output_path(relative)
    data = frame_compose.png_bytes(image)
    output.write_bytes(data)
    return output, data


def _data_uri(data: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(data).decode("ascii")


def _base_replacements(values: dict[str, object]) -> dict[str, object]:
    return {
        "app_name": values["app_name"],
        "brand_color": values["brand_color"],
        "developer_entity": values["developer_entity"],
        "headline_1": values["headline_1"],
        "headline_2": values["headline_2"],
        "headline_3": values["headline_3"],
        "support_email": values["support_email"],
        "support_email_href": quote(str(values["support_email"]), safe="@."),
        "tagline": values["tagline"],
    }


def _icon_relpath(size: int) -> str:
    return "out/icons/icon-1024.png" if size == 1024 else f"out/icons/icon-{size}.png" if size != 32 else "out/icons/favicon-32.png"


def expected_content_relpaths(
    values: dict[str, object], device_count: int = 3
) -> list[str]:
    paths = [
        "out/README.md",
        "out/landing/index.html",
        "out/landing/legal/privacy.html",
        "out/landing/legal/terms.html",
        "out/landing/og.png",
        "out/legal/privacy.md",
        "out/legal/terms.md",
    ]
    paths.extend(
        f"out/landing/assets/device_{index}.png"
        for index in range(1, device_count + 1)
    )
    paths.extend(_icon_relpath(size) for size in ICON_SIZES)
    for locale in list(values["locales"]):
        for filename in COPY_FILES:
            paths.append(f"out/copy/{locale}/{filename}.txt")
    return sorted(paths)


def _normalize_keywords(rendered: str) -> str:
    unique: list[str] = []
    seen: set[str] = set()
    for raw in rendered.split(","):
        keyword = raw.strip()
        folded = keyword.casefold()
        if not keyword or folded in seen:
            continue
        candidate = ",".join(unique + [keyword])
        if len(candidate) > 100:
            continue
        unique.append(keyword)
        seen.add(folded)
    return ",".join(unique)


def render_copy(values: dict[str, object]) -> list[Path]:
    replacements = _base_replacements(values)
    outputs: list[Path] = []
    for locale in list(values["locales"]):
        for filename in COPY_FILES:
            template = _read_template(TEMPLATES / "copy" / locale / f"{filename}.tmpl")
            content = _replace(template, replacements, html_target=False)
            if filename == "keywords":
                content = _normalize_keywords(content)
            elif filename in COPY_LIMITS:
                content = content[: COPY_LIMITS[filename]].rstrip()
            if filename == "description" and len(content) > 4000:
                raise TemplateError("description exceeds App Store limit")
            outputs.append(_write_text(f"out/copy/{locale}/{filename}.txt", content))
    return outputs


def _master_icon(values: dict[str, object]) -> Image.Image:
    brand = _rgb(str(values["brand_color"]))
    start = _mix(brand, (255, 255, 255), 0.18)
    end = _mix(brand, (0, 0, 0), 0.18)
    image = _gradient_square((1024, 1024), start, end)
    draw = ImageDraw.Draw(image)
    first = str(values["app_name"])[0]
    if first.isascii() and first.isalnum():
        rendered, font = _fit_text(draw, first.upper(), 650, 560, 200)
        _centered_text(draw, (512, 500), rendered, font, (255, 255, 255))
    else:
        # Fixed vector fallback guarantees coverage without font probing.
        screens.draw_spark(draw, (512, 512), 260, (255, 255, 255))
    return image


def render_icons(values: dict[str, object]) -> tuple[list[Path], dict[int, bytes]]:
    master = _master_icon(values)
    outputs: list[Path] = []
    encoded: dict[int, bytes] = {}
    for size in ICON_SIZES:
        image = master if size == 1024 else master.resize((size, size), Image.Resampling.LANCZOS)
        output, data = _write_png(_icon_relpath(size), image)
        outputs.append(output)
        encoded[size] = data
    header = master.resize((64, 64), Image.Resampling.LANCZOS)
    encoded[64] = frame_compose.png_bytes(header)
    return outputs, encoded


def _og_image(
    values: dict[str, object], framed: dict[int, Image.Image]
) -> Image.Image:
    brand = _rgb(str(values["brand_color"]))
    image = _gradient_square(
        (1200, 630),
        _mix(brand, (255, 255, 255), 0.10),
        _mix(brand, (0, 0, 0), 0.32),
    )
    draw = ImageDraw.Draw(image)
    dot = _mix(brand, (255, 255, 255), 0.42)
    for y in range(26, 630, 34):
        for x in range(26, 1200, 34):
            draw.ellipse((x, y, x + 3, y + 3), fill=dot)

    app_name, app_font = _fit_text(
        draw, str(values["app_name"]), 720, 82, 34
    )
    draw.text((66, 126), app_name, font=app_font, fill=(255, 255, 255))
    tagline, tagline_font = _fit_text(
        draw, str(values["tagline"]), 690, 34, 20, extra=False
    )
    draw.text((70, 250), tagline, font=tagline_font, fill=(248, 250, 252))
    draw.rounded_rectangle((68, 516, 384, 574), radius=29, fill=_mix(brand, (0, 0, 0), 0.40))
    _centered_text(
        draw,
        (226, 545),
        "Launch kit by appkit-demo",
        _font(20),
        (255, 255, 255),
    )

    shot = framed[1].resize((267, 580), Image.Resampling.LANCZOS)
    shadow = Image.new("RGB", (287, 600), _mix(brand, (0, 0, 0), 0.42))
    image.paste(shadow, (857, 30))
    image.paste(shot, (867, 20))
    return image


def render_landing(
    values: dict[str, object],
    framed: dict[int, Image.Image],
    icon_pngs: dict[int, bytes],
    device_pngs: dict[int, bytes],
    embed_devices: bool = False,
) -> list[Path]:
    indices = sorted(device_pngs)
    if indices != list(range(1, len(indices) + 1)) or sorted(framed) != indices:
        raise TemplateError("landing device indices are invalid")
    labels = ("home", "detail", "progress")
    descriptions = (
        "Find the right next move without digging through clutter.",
        "Focused details keep every choice clear and approachable.",
        "Progress stays visible, useful, and easy to act on.",
    )
    escaped_name = escape_html(values["app_name"])
    escaped_headlines = [
        escape_html(values[f"headline_{index}"]) for index in indices
    ]
    hero_lines = []
    sources = {
        index: (
            _data_uri(device_pngs[index])
            if embed_devices
            else f"./assets/device_{index}.png"
        )
        for index in indices
    }
    if len(indices) >= 2:
        hero_lines.append(
            f'<img class="hero-device back" src="{sources[2]}" alt="{escaped_name} detail screen">'
        )
    hero_lines.append(
        f'<img class="hero-device front" src="{sources[1]}" alt="{escaped_name} home screen">'
    )
    shot_lines = []
    for position, index in enumerate(indices):
        shot_lines.append(
            f'<figure class="shot-card"><img src="{sources[index]}" alt="{escaped_name} {labels[position]} screen"><figcaption><h3>{escaped_headlines[position]}</h3><p>{descriptions[position]}</p></figcaption></figure>'
        )
    shot_rail_attributes = ""
    if len(indices) == 1:
        shot_rail_attributes = (
            ' data-count="1" style="grid-template-columns:minmax(0,360px);justify-content:center"'
        )
    elif len(indices) == 2:
        shot_rail_attributes = (
            ' data-count="2" style="grid-template-columns:repeat(2,minmax(0,1fr));max-width:740px;margin:0 auto"'
        )
    replacements = _base_replacements(values)
    replacements.update(
        {
            "favicon_data_uri": _data_uri(icon_pngs[32]),
            "hero_devices": "\n          ".join(hero_lines),
            "icon_data_uri": _data_uri(icon_pngs[64]),
            "shot_cards": "\n          ".join(shot_lines),
            "shot_rail_attributes": shot_rail_attributes,
        }
    )
    outputs: list[Path] = []
    for index in indices:
        output = safe_output_path(f"out/landing/assets/device_{index}.png")
        output.write_bytes(device_pngs[index])
        outputs.append(output)
    outputs.append(
        _write_text(
            "out/landing/index.html",
            _replace(
                _read_template(TEMPLATES / "landing" / "index.html.tmpl"),
                replacements,
                html_target=True,
                safe_html_tokens=frozenset(
                    ("hero_devices", "shot_cards", "shot_rail_attributes")
                ),
            ),
        )
    )
    og_path, _ = _write_png("out/landing/og.png", _og_image(values, framed))
    outputs.append(og_path)
    for name in ("privacy", "terms"):
        markdown_template = _read_template(
            TEMPLATES / "legal" / f"{name}.md.tmpl"
        )
        legal_replacements = dict(replacements)
        legal_replacements.update(
            {
                "icon_data_uri": _data_uri(icon_pngs[64]),
                "legal_content": _markdown_to_html(
                    markdown_template, replacements
                ),
                "page_title": "Privacy Policy" if name == "privacy" else "Terms of Service",
            }
        )
        outputs.append(
            _write_text(
                f"out/landing/legal/{name}.html",
                _replace(
                    _read_template(TEMPLATES / "legal" / f"{name}.html.tmpl"),
                    legal_replacements,
                    html_target=True,
                    safe_html_tokens=frozenset(("legal_content",)),
                ),
            )
        )
    return outputs


def _markdown_to_html(
    template: str, replacements: dict[str, object]
) -> str:
    """Classify trusted template lines, then insert escaped inline values."""

    rendered: list[str] = []
    for raw_line in template.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("## "):
            tag, content = "h2", line[3:]
        elif line.startswith("# "):
            tag, content = "h1", line[2:]
        elif line.startswith("**") and line.endswith("**") and len(line) > 4:
            tag, content = 'p class="effective"', line[2:-2]
        else:
            tag, content = "p", line
        inline = _replace(content, replacements, html_target=True)
        rendered.append(f"<{tag}>{inline}</{tag.split()[0]}>")
    return "".join(rendered)


def render_legal(values: dict[str, object]) -> list[Path]:
    replacements = _base_replacements(values)
    outputs: list[Path] = []
    for name in ("privacy", "terms"):
        outputs.append(
            _write_text(
                f"out/legal/{name}.md",
                _replace(
                    _read_template(TEMPLATES / "legal" / f"{name}.md.tmpl"),
                    replacements,
                    html_target=False,
                ),
            )
        )
    return outputs


def _kit_readme(
    values: dict[str, object],
    provenance: str | None = None,
    screenshot_count: int = 3,
) -> str:
    app_name = str(values["app_name"]).replace("\\", "\\\\").replace("|", "\\|")
    rows: list[tuple[str, str, str]] = []
    copy_destinations = {
        "description": ("Store description", "App Store Connect > App Information > Description"),
        "keywords": ("Search keywords", "App Store Connect > App Information > Keywords"),
        "name": ("Store name", "App Store Connect > App Information > Name"),
        "promotional_text": ("Promotional copy", "App Store Connect > App Information > Promotional Text"),
        "release_notes": ("Launch release notes", "App Store Connect > What's New"),
        "subtitle": ("Store subtitle", "App Store Connect > App Information > Subtitle"),
    }
    for locale in list(values["locales"]):
        for filename in COPY_FILES:
            what, where = copy_destinations[filename]
            rows.append((f"copy/{locale}/{filename}.txt", what, where))
        for index in range(1, screenshot_count + 1):
            rows.append(
                (
                    f"screenshots/{locale}/shot_{index}.png",
                    f"Framed marketing screenshot {index}",
                    "App Store Connect > iPhone 6.7-inch screenshot slots",
                )
            )
    for size in (1024, 180, 167, 152, 120):
        rows.append((f"icons/icon-{size}.png", f"{size}px app icon", "Your app project and store listing"))
    device_descriptions = (
        "Transparent home device render",
        "Transparent detail device render",
        "Transparent progress device render",
    )
    rows.extend(
        (
            f"landing/assets/device_{index}.png",
            device_descriptions[index - 1],
            "Displayed by landing/index.html",
        )
        for index in range(1, screenshot_count + 1)
    )
    rows.extend(
        (
            ("icons/favicon-32.png", "Browser favicon", "Your website favicon"),
            ("landing/index.html", "Single-file product page", "Host at your marketing URL"),
            ("landing/og.png", "Social sharing image", "Host beside landing/index.html"),
            ("landing/legal/privacy.html", "Hosted privacy page", "Host and paste its URL into Privacy Policy URL"),
            ("landing/legal/terms.html", "Hosted terms page", "Host beside the privacy page"),
            ("legal/privacy.md", "Editable privacy source", "Keep as legal source and review before launch"),
            ("legal/terms.md", "Editable terms source", "Keep as legal source and review before launch"),
            ("README.md", "This handoff guide", "Start here"),
            ("manifest.json", "Byte-level artifact inventory", "Use for local integrity checks"),
            ("launch-kit.zip", "Complete launch kit archive", "Share with your launch team"),
        )
    )
    if provenance is not None:
        rows.append(
            (
                "capture-report.json",
                "Screenshot provenance and observed source digests",
                "Keep with the launch handoff",
            )
        )
    lines = [
        f"# {app_name} Launch Kit",
        "",
        f"Everything needed to prepare {app_name} for its first real launch, organized by destination.",
        "",
    ]
    if provenance is not None:
        lines.extend((f"**Provenance:** {provenance}", ""))
    lines.extend(
        (
            "| File | What it is | Where it goes |",
            "| --- | --- | --- |",
        )
    )
    for path, what, where in sorted(rows, key=lambda row: row[0]):
        lines.append(f"| `{path}` | {what} | {where} |")
    lines.extend(
        (
            "",
            "## Known limits (v1)",
            "",
            (
                "Real-screenshot ingestion is out of scope because the flat typed schema cannot carry files. Screens are synthesized deterministically from brand inputs. The landing page ships in English; localization is a follow-up."
                if provenance is None
                else "Direct simulator ingestion is out of scope. Pro capture uses qualifying exports, a capturable web surface, or an explicit synthetic fallback. The landing page ships in English; localization is a follow-up."
            ),
            "",
            "If this kit was generated by a hosted pipeline service, treat its contents as visible to the service operator (service deployments may notify the operator with a copy of each served kit).",
            "",
            "## Hosting",
            "",
            "Before hosting, replace `./og.png` in both the `og:image` and `twitter:image` metadata in `landing/index.html` with the image's absolute public URL. This is one global find-and-replace; the relative default is retained for local preview.",
            "",
            "Review legal text and store metadata before publishing.",
            "",
        )
    )
    return "\n".join(lines)


def render_readme(
    values: dict[str, object],
    provenance: str | None = None,
    screenshot_count: int = 3,
) -> Path:
    return _write_text(
        "out/README.md", _kit_readme(values, provenance, screenshot_count)
    )


def render_all(
    values: dict[str, object],
    framed: dict[int, Image.Image],
    device_pngs: dict[int, bytes],
    provenance: str | None = None,
    embed_devices: bool = False,
) -> list[Path]:
    outputs = render_copy(values)
    icon_paths, icon_pngs = render_icons(values)
    outputs.extend(icon_paths)
    outputs.extend(
        render_landing(
            values,
            framed,
            icon_pngs,
            device_pngs,
            embed_devices=embed_devices,
        )
    )
    outputs.extend(render_legal(values))
    outputs.append(
        render_readme(values, provenance, screenshot_count=len(framed))
    )
    return sorted(outputs, key=lambda path: path.as_posix())
