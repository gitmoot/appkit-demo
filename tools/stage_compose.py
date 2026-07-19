#!/usr/bin/env python3
"""Root stage: render deterministic, device-framed marketing screenshots."""

from __future__ import annotations

from pathlib import Path

import frame_compose
import screens
from inputs import InputError, load_inputs
from stage_support import (
    emit_result,
    failure_summary,
    identity_digests,
    log,
    prepare_output_tree,
    success_summary,
)


def run_compose(values: dict[str, object]) -> dict[str, object]:
    frame_compose.verify_assets()
    prepare_output_tree()
    framed = screens.build_framed_screens(values)
    framed_pngs = screens.encode_framed_screens(framed)
    outputs = screens.render_screenshots(values, framed_pngs)
    return success_summary(values, identity_digests(outputs, Path.cwd()))


def main() -> None:
    try:
        values = load_inputs()
        summary = run_compose(values)
        emit_result("implemented", summary)
    except InputError as error:
        log(f"validation failed: {error.field}/{error.code}")
        emit_result("failed", failure_summary(f"validation:{error.field}:{error.code}"))
    except Exception as error:
        log(f"compose failed: {type(error).__name__}")
        emit_result("failed", failure_summary("compose_error"))


if __name__ == "__main__":
    main()
