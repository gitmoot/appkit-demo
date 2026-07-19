#!/usr/bin/env python3
"""Appkit-pro stage: frame captured or derived synthetic screenshots."""

from __future__ import annotations

from pathlib import Path

import frame_compose
import pro_compose
import pro_handoff
import pro_inputs
from stage_support import (
    emit_result,
    failure_summary,
    identity_digests,
    log,
    prepare_output_tree,
    success_summary,
)


def run_compose_real(values: dict[str, object]) -> dict[str, object]:
    report = pro_inputs.load_capture_report()
    prepare_output_tree()
    framed, devices = pro_compose.build_render_assets(values, report)
    framed_pngs = {
        index: frame_compose.png_bytes(framed[index])
        for index in sorted(framed)
    }
    outputs = pro_compose.render_screenshots(values, framed_pngs)
    handoff_digests, persisted = pro_handoff.persist_assets(
        values, report, framed, devices
    )
    digests = identity_digests(outputs, Path.cwd())
    digests.update(handoff_digests)
    return success_summary(
        values,
        digests,
        counts=report["counts"],
        persisted=persisted,
    )


def main() -> None:
    try:
        values = pro_inputs.load_order()
        emit_result("implemented", run_compose_real(values))
    except Exception as error:
        log(f"compose-real failed: {type(error).__name__}")
        emit_result("failed", failure_summary("compose_real_error"))


if __name__ == "__main__":
    main()
