"""Assemble the complete Pro artifact tree from verified data-dir handoffs."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image

import frame_compose
import pro_compose
import pro_content_handoff
import pro_handoff
import render
from stage_support import artifact_identity, canonical_json, safe_output_path


class AssemblyError(RuntimeError):
    pass


def expected_output_relpaths(
    values: dict[str, object], count: int
) -> list[str]:
    return sorted(
        render.expected_content_handoff_relpaths(values)
        + pro_compose.expected_screenshot_relpaths(values, count)
        + render.expected_landing_relpaths(count)
        + ["out/README.md", "out/capture-report.json"]
    )


def expected_digest_keys(
    values: dict[str, object], count: int
) -> list[str]:
    return sorted(
        expected_output_relpaths(values, count)
        + pro_handoff.expected_digest_keys(count)
        + pro_content_handoff.expected_digest_keys(values)
    )


def _header_icon(master: bytes) -> bytes:
    try:
        with Image.open(BytesIO(master)) as image:
            prepared = image.convert("RGBA")
            if prepared.size != (1024, 1024):
                raise AssemblyError("content icon geometry mismatch")
            resized = prepared.resize((64, 64), Image.Resampling.LANCZOS)
    except (OSError, ValueError) as error:
        raise AssemblyError("content icon is invalid") from error
    return frame_compose.png_bytes(resized)


def assemble(
    values: dict[str, object],
    report: dict[str, object],
    framed: dict[int, Image.Image],
    device_pngs: dict[int, bytes],
    content_payloads: dict[str, bytes],
    framed_digests: dict[str, str],
    content_digests: dict[str, str],
) -> list[Path]:
    count = len(framed)
    expected_content = {
        Path(path).relative_to("out").as_posix()
        for path in render.expected_content_handoff_relpaths(values)
    }
    if set(content_payloads) != expected_content:
        raise AssemblyError("content handoff artifact set mismatch")

    outputs: list[Path] = []
    for relative in sorted(content_payloads):
        output = safe_output_path(f"out/{relative}")
        output.write_bytes(content_payloads[relative])
        if artifact_identity(output) != content_digests[f"content/{relative}"]:
            raise AssemblyError("content handoff copy mismatch")
        outputs.append(output)

    framed_pngs = {
        index: frame_compose.png_bytes(framed[index]) for index in sorted(framed)
    }
    screenshot_paths = pro_compose.render_screenshots(values, framed_pngs)
    for locale in list(values["locales"]):
        for index in sorted(framed):
            path = Path.cwd() / f"out/screenshots/{locale}/shot_{index}.png"
            if artifact_identity(path) != framed_digests[f"framed/frame_{index}.png"]:
                raise AssemblyError("framed handoff screenshot mismatch")
    outputs.extend(screenshot_paths)

    icon_pngs = {
        32: content_payloads["icons/favicon-32.png"],
        64: _header_icon(content_payloads["icons/icon-1024.png"]),
    }
    landing_paths = render.render_landing(
        values,
        framed,
        icon_pngs,
        device_pngs,
        embed_devices=True,
    )
    for index in sorted(device_pngs):
        path = Path.cwd() / f"out/landing/assets/device_{index}.png"
        if artifact_identity(path) != framed_digests[f"framed/device_{index}.png"]:
            raise AssemblyError("framed handoff device mismatch")
    outputs.extend(landing_paths)

    outputs.append(
        render.render_readme(
            values,
            pro_compose.provenance(report),
            screenshot_count=count,
        )
    )
    report_path = safe_output_path("out/capture-report.json")
    report_path.write_text(
        canonical_json(report) + "\n", encoding="utf-8", newline="\n"
    )
    outputs.append(report_path)

    expected_outputs = set(expected_output_relpaths(values, count))
    actual_outputs = {
        path.relative_to(Path.cwd()).as_posix() for path in outputs
    }
    if actual_outputs != expected_outputs:
        raise AssemblyError("assembled output set mismatch")
    return sorted(outputs, key=lambda path: path.as_posix())
