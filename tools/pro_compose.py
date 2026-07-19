"""Shared real-capture compositor for appkit-pro compose and kit stages."""

from __future__ import annotations

import hashlib
from pathlib import Path

from PIL import Image

import frame_compose
import pro_inputs
import screens


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


def build_framed(
    values: dict[str, object], report: dict[str, object]
) -> dict[int, Image.Image]:
    frame_compose.verify_assets()
    if report["ladder"] == "synthetic":
        return screens.build_framed_screens(values)
    captures = _captured_images(report)
    headlines = {
        1: str(values["headline_1"]),
        2: str(values["headline_2"]),
        3: str(values["headline_3"]),
    }
    return {
        index: frame_compose.compose(
            captures[min(index - 1, len(captures) - 1)],
            headlines[index],
            str(values["brand_color"]),
        )
        for index in (1, 2, 3)
    }


def provenance(report: dict[str, object]) -> str:
    if report["ladder"] == "synthetic":
        return "Synthesized deterministically from derived brand inputs."
    source = str(report["source"])
    for token in ("\\", "`", "*", "_", "{", "}", "[", "]", "<", ">", "|", "#"):
        source = source.replace(token, "\\" + token)
    return f"Captured from {source} via {report['ladder']}."
