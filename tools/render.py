"""Shared deterministic copy, landing-page, and legal renderers."""

from __future__ import annotations

import re
from pathlib import Path

from inputs import escape_html
from stage_support import safe_output_path


REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = REPO_ROOT / "templates"
COPY_FILES = (
    "description",
    "keywords",
    "name",
    "promotional_text",
    "subtitle",
)
COPY_LIMITS = {
    "keywords": 100,
    "name": 30,
    "promotional_text": 170,
    "subtitle": 30,
}
_TOKEN_RE = re.compile(r"\{([a-z][a-z0-9_]*)\}")


class TemplateError(RuntimeError):
    pass


def _read_template(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        raise RuntimeError("template missing or unsafe")
    return path.read_text(encoding="utf-8")


def _replace(template: str, replacements: dict[str, object], html_target: bool) -> str:
    def substitute(match: re.Match[str]) -> str:
        key = match.group(1)
        try:
            value = replacements[key]
        except KeyError as error:
            raise TemplateError("unknown template token") from error
        return escape_html(value) if html_target else str(value)

    # re.sub scans only the template. Braces returned by the callback are inert.
    return _TOKEN_RE.sub(substitute, template)


def _write_text(relative: str, content: str) -> Path:
    output = safe_output_path(relative)
    output.write_text(content, encoding="utf-8", newline="\n")
    return output


def _base_replacements(values: dict[str, object]) -> dict[str, object]:
    return {
        "app_name": values["app_name"],
        "brand_color": values["brand_color"],
        "developer_entity": values["developer_entity"],
        "headline_1": values["headline_1"],
        "headline_2": values["headline_2"],
        "headline_3": values["headline_3"],
        "support_email": values["support_email"],
        "tagline": values["tagline"],
    }


def expected_content_relpaths(values: dict[str, object]) -> list[str]:
    paths = [
        "out/landing/index.html",
        "out/legal/privacy.md",
        "out/legal/terms.md",
    ]
    for locale in list(values["locales"]):
        for filename in COPY_FILES:
            paths.append(f"out/copy/{locale}/{filename}.txt")
    return sorted(paths)


def render_copy(values: dict[str, object]) -> list[Path]:
    replacements = _base_replacements(values)
    outputs: list[Path] = []
    for locale in list(values["locales"]):
        for filename in COPY_FILES:
            template = _read_template(TEMPLATES / "copy" / locale / f"{filename}.tmpl")
            content = _replace(template, replacements, html_target=False)
            if filename in COPY_LIMITS:
                content = content[: COPY_LIMITS[filename]].rstrip()
            outputs.append(_write_text(f"out/copy/{locale}/{filename}.txt", content))
    return outputs


def render_landing(values: dict[str, object]) -> Path:
    replacements = _base_replacements(values)
    replacements["screenshot_locale"] = list(values["locales"])[0]
    template = _read_template(TEMPLATES / "landing" / "index.html.tmpl")
    return _write_text(
        "out/landing/index.html",
        _replace(template, replacements, html_target=True),
    )


def render_legal(values: dict[str, object]) -> list[Path]:
    replacements = _base_replacements(values)
    outputs: list[Path] = []
    for name in ("privacy", "terms"):
        template = _read_template(TEMPLATES / "legal" / f"{name}.md.tmpl")
        outputs.append(
            _write_text(
                f"out/legal/{name}.md",
                _replace(template, replacements, html_target=False),
            )
        )
    return outputs


def render_all(values: dict[str, object]) -> list[Path]:
    outputs = render_copy(values)
    outputs.append(render_landing(values))
    outputs.extend(render_legal(values))
    return sorted(outputs, key=lambda path: path.as_posix())
