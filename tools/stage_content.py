#!/usr/bin/env python3
"""Root stage: render store copy, landing page, and legal documents."""

from __future__ import annotations

from pathlib import Path

import frame_compose
import render
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


def run_content(values: dict[str, object]) -> dict[str, object]:
    frame_compose.verify_assets()
    prepare_output_tree()
    framed, devices = screens.build_render_assets(values)
    device_pngs = screens.encode_device_screens(devices)
    outputs = render.render_all(values, framed, device_pngs)
    return success_summary(values, identity_digests(outputs, Path.cwd()))


def main() -> None:
    try:
        values = load_inputs()
        emit_result("implemented", run_content(values))
    except InputError as error:
        log(f"validation failed: {error.field}/{error.code}")
        emit_result("failed", failure_summary(f"validation:{error.field}:{error.code}"))
    except render.TemplateError:
        log("content failed: template error")
        emit_result("failed", failure_summary("template_error"))
    except Exception as error:
        log(f"content failed: {type(error).__name__}")
        emit_result("failed", failure_summary("content_error"))


if __name__ == "__main__":
    main()
