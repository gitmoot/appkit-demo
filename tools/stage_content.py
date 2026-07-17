#!/usr/bin/env python3
"""Root stage: render store copy, landing page, and legal documents."""

from __future__ import annotations

from pathlib import Path

import frame_compose
import render
from inputs import InputError, load_inputs
from stage_support import (
    emit_result,
    failure_summary,
    identity_digests,
    log,
    success_summary,
)


def main() -> None:
    try:
        values = load_inputs()
        frame_compose.verify_assets()
        outputs = render.render_all(values)
        digests = identity_digests(outputs, Path.cwd())
        emit_result("implemented", success_summary(values, digests))
    except InputError as error:
        log(f"validation failed: {error.field}/{error.code}")
        emit_result("failed", failure_summary(f"validation:{error.field}:{error.code}"))
    except Exception as error:
        log(f"content failed: {type(error).__name__}")
        emit_result("failed", failure_summary("content_error"))


if __name__ == "__main__":
    main()
