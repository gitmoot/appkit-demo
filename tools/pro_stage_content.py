#!/usr/bin/env python3
"""Appkit-pro stage: render derived content through the public generator."""

from __future__ import annotations

import pro_inputs
import render
import stage_content
from stage_support import emit_result, failure_summary, log


def main() -> None:
    try:
        values = pro_inputs.load_order()
        emit_result("implemented", stage_content.run_content(values))
    except render.TemplateError:
        log("pro content failed: template error")
        emit_result("failed", failure_summary("template_error"))
    except Exception as error:
        log(f"pro content failed: {type(error).__name__}")
        emit_result("failed", failure_summary("pro_content_error"))


if __name__ == "__main__":
    main()
