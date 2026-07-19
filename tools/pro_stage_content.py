#!/usr/bin/env python3
"""Appkit-pro stage: render derived content through the public generator."""

from __future__ import annotations

from pathlib import Path

import frame_compose
import pro_compose
import pro_handoff
import pro_inputs
import render
from stage_support import (
    artifact_identity,
    emit_result,
    failure_summary,
    identity_digests,
    log,
    prepare_output_tree,
    success_summary,
)


def run_content(values: dict[str, object]) -> dict[str, object]:
    frame_compose.verify_assets()
    report = pro_inputs.load_capture_report()
    prepare_output_tree()
    framed, device_pngs, handoff_digests = pro_handoff.load_assets(values, report)
    outputs = render.render_all(
        values,
        framed,
        device_pngs,
        provenance=pro_compose.provenance(report),
        embed_devices=True,
    )
    for index in sorted(device_pngs):
        output = Path.cwd() / f"out/landing/assets/device_{index}.png"
        if artifact_identity(output) != handoff_digests[f"framed/device_{index}.png"]:
            raise pro_handoff.HandoffError("landing device differs from handoff")
    digests = identity_digests(outputs, Path.cwd())
    digests.update(handoff_digests)
    return success_summary(values, digests, counts=report["counts"])


def main() -> None:
    try:
        values = pro_inputs.load_order()
        emit_result("implemented", run_content(values))
    except render.TemplateError:
        log("pro content failed: template error")
        emit_result("failed", failure_summary("template_error"))
    except Exception as error:
        log(f"pro content failed: {type(error).__name__}")
        emit_result("failed", failure_summary("pro_content_error"))


if __name__ == "__main__":
    main()
