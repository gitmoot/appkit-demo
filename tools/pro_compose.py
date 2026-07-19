"""Shared real-capture compositor for appkit-pro compose and kit stages."""

from __future__ import annotations

import hashlib
from pathlib import Path

from PIL import Image

import frame_compose
import pro_inputs
import screens
from stage_support import safe_output_path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _captured_images(report: dict[str, object]) -> list[Image.Image]:
    result: list[Image.Image] = []
    shots = report.get("shots")
    if not isinstance(shots, list):
        raise pro_inputs.ProDataError("capture report has no screenshots")
    for item in shots:
        if not isinstance(item, dict):
            raise pro_inputs.ProDataError("capture report shot is malformed")
        path = pro_inputs.data_root() / "screens" / str(item["file"])
        if not path.is_file() or path.is_symlink() or _sha256(path) != item["sha256"]:
            raise pro_inputs.ProDataError("captured screenshot missing or changed")
        with Image.open(path) as image:
            if image.size != (screens.SCREEN_W, screens.SCREEN_H):
                raise pro_inputs.ProDataError("captured screenshot geometry changed")
            result.append(image.convert("RGB"))
    if not result:
        raise pro_inputs.ProDataError("capture report has no screenshots")
    return result


def build_render_assets(
    values: dict[str, object], report: dict[str, object]
) -> tuple[dict[int, Image.Image], dict[int, Image.Image]]:
    frame_compose.verify_assets()
    if report["ladder"] == "synthetic":
        return screens.build_render_assets(values)
    captures = _captured_images(report)
    framed = {
        index: frame_compose.compose(
            captures[index - 1],
            str(values[f"headline_{index}"]),
            str(values["brand_color"]),
        )
        for index in range(1, len(captures) + 1)
    }
    devices = {
        index: frame_compose.compose_device(captures[index - 1])
        for index in range(1, len(captures) + 1)
    }
    return framed, devices


def build_framed(
    values: dict[str, object], report: dict[str, object]
) -> dict[int, Image.Image]:
    return build_render_assets(values, report)[0]


def expected_screenshot_relpaths(
    values: dict[str, object], count: int
) -> list[str]:
    return sorted(
        f"out/screenshots/{locale}/shot_{index}.png"
        for locale in list(values["locales"])
        for index in range(1, count + 1)
    )


def render_screenshots(
    values: dict[str, object], framed_pngs: dict[int, bytes]
) -> list[Path]:
    outputs: list[Path] = []
    for locale in list(values["locales"]):
        for index in sorted(framed_pngs):
            output = safe_output_path(
                f"out/screenshots/{locale}/shot_{index}.png"
            )
            output.write_bytes(framed_pngs[index])
            outputs.append(output)
    return sorted(outputs, key=lambda path: path.as_posix())


def provenance(report: dict[str, object]) -> str:
    counts = report["counts"]
    if report["ladder"] == "synthetic":
        return (
            "Synthesized deterministically from derived brand inputs. "
            f"Real screens: {counts['real']}; synthetic padding: {counts['padded']}."
        )
    source = str(report["source"])
    for token in ("\\", "`", "*", "_", "{", "}", "[", "]", "<", ">", "|", "#"):
        source = source.replace(token, "\\" + token)
    return (
        f"Captured from {source} via {report['ladder']}. "
        f"Real screens: {counts['real']}; synthetic padding: {counts['padded']}."
    )
