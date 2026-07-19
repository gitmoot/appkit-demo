#!/usr/bin/env python3
"""Appkit-pro stage: frame captured or derived synthetic screenshots."""

from __future__ import annotations

from pathlib import Path

import pro_compose
import pro_inputs
import screens
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
    framed = pro_compose.build_framed(values, report)
    outputs = screens.render_screenshots(
        values, screens.encode_framed_screens(framed)
    )
    return success_summary(values, identity_digests(outputs, Path.cwd()))


def main() -> None:
    try:
        values = pro_inputs.load_order()
        emit_result("implemented", run_compose_real(values))
    except Exception as error:
        log(f"compose-real failed: {type(error).__name__}")
        emit_result("failed", failure_summary("compose_real_error"))


if __name__ == "__main__":
    main()
