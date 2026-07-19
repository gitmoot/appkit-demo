#!/usr/bin/env python3
"""Appkit-pro parallel branch: persist copy, legal sources, and icons."""

from __future__ import annotations

from pathlib import Path

import frame_compose
import pro_content_handoff
import pro_inputs
import render
from stage_support import (
    emit_result,
    failure_summary,
    log,
    prepare_output_tree,
    success_summary,
)


def run_content(values: dict[str, object]) -> dict[str, object]:
    frame_compose.verify_assets()
    prepare_output_tree()
    render.render_content_handoff(values)
    digests, persisted = pro_content_handoff.persist_assets(
        values, Path.cwd() / "out"
    )
    return success_summary(values, digests, persisted=persisted)


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
