#!/usr/bin/env python3
"""Appkit-pro stage: frame captured or derived synthetic screenshots."""

from __future__ import annotations

import pro_compose
import pro_handoff
import pro_inputs
from stage_support import (
    emit_result,
    failure_summary,
    log,
    success_summary,
)


def run_compose_real(values: dict[str, object]) -> dict[str, object]:
    report = pro_inputs.load_capture_report()
    framed, devices = pro_compose.build_render_assets(values, report)
    handoff_digests, persisted = pro_handoff.persist_assets(
        values, report, framed, devices
    )
    return success_summary(
        values,
        handoff_digests,
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
