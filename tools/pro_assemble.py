"""Assemble the complete Pro tree from verified frames and observed content."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

import frame_compose
import pro_agent_content
import pro_compose
import pro_handoff
import render
from stage_support import artifact_identity, canonical_json, safe_output_path


class AssemblyError(RuntimeError):
    pass


@dataclass(frozen=True)
class AssemblyResult:
    paths: list[Path]
    observed: dict[str, str]


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
    values: dict[str, object],
    count: int,
    content_provenance: dict[str, str],
) -> list[str]:
    verified = pro_agent_content.verified_output_keys(
        expected_output_relpaths(values, count), content_provenance
    )
    return sorted(verified + pro_handoff.expected_digest_keys(count))


def expected_observed_keys(content_provenance: dict[str, str]) -> list[str]:
    return sorted(
        pro_agent_content.observed_output_keys(content_provenance)
        + pro_agent_content.observed_derived_keys(content_provenance)
    )


def assemble(
    values: dict[str, object],
    report: dict[str, object],
    framed: dict[int, Image.Image],
    device_pngs: dict[int, bytes],
    framed_digests: dict[str, str],
    content: pro_agent_content.AgentContent,
) -> AssemblyResult:
    count = len(framed)
    expected_content = set(pro_agent_content.expected_relpaths(values))
    if set(content.provenance) != expected_content or not set(
        content.payloads
    ).issubset(expected_content):
        raise AssemblyError("agent content selection mismatch")

    outputs = render.render_copy(values)
    outputs.extend(render.render_legal(values))
    icon_paths, icon_pngs = render.render_icons(values)
    outputs.extend(icon_paths)
    for relative in sorted(content.payloads):
        output = safe_output_path(f"out/{relative}")
        output.write_bytes(content.payloads[relative])

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

    legal_markdown = {
        name: (Path.cwd() / f"out/legal/{name}.md").read_text(encoding="utf-8")
        for name in ("privacy", "terms")
    }
    landing_paths = render.render_landing(
        values,
        framed,
        icon_pngs,
        device_pngs,
        embed_devices=True,
        legal_markdown=legal_markdown,
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
            content_provenance=content.provenance,
        )
    )
    report_path = safe_output_path("out/capture-report.json")
    report_path.write_text(
        canonical_json(report) + "\n", encoding="utf-8", newline="\n"
    )
    outputs.append(report_path)

    expected_outputs = set(expected_output_relpaths(values, count))
    actual_outputs = {path.relative_to(Path.cwd()).as_posix() for path in outputs}
    if actual_outputs != expected_outputs:
        raise AssemblyError("assembled output set mismatch")
    observed: dict[str, str] = {}
    for key in expected_observed_keys(content.provenance):
        data = (Path.cwd() / key).read_bytes()
        observed[key] = hashlib.sha256(data).hexdigest()
    return AssemblyResult(
        paths=sorted(outputs, key=lambda path: path.as_posix()),
        observed={key: observed[key] for key in sorted(observed)},
    )
