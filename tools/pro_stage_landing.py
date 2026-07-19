#!/usr/bin/env python3
"""Appkit-pro join: assemble the full tree from isolated persisted branches."""

from __future__ import annotations

from pathlib import Path

import frame_compose
import pro_assemble
import pro_content_handoff
import pro_handoff
import pro_inputs
import render
import stage_kit
from stage_support import (
    emit_result,
    failure_summary,
    identity_digests,
    log,
    prepare_output_tree,
    success_summary,
)


def run_landing(values: dict[str, object]) -> dict[str, object]:
    frame_compose.verify_assets()
    prepare_output_tree()
    context = stage_kit._load_context()
    report = pro_inputs.load_capture_report()
    framed, device_pngs, framed_digests = pro_handoff.load_assets(values, report)
    content_payloads, content_digests = pro_content_handoff.load_assets(values)
    count = len(framed)

    handoff_digests = dict(framed_digests)
    if set(handoff_digests).intersection(content_digests):
        raise stage_kit.VerificationError("landing_digest_overlap")
    handoff_digests.update(content_digests)
    summaries = stage_kit._upstream_summaries(
        context,
        values,
        ("compose-real", "content"),
        {
            "compose-real": {"counts", "persisted"},
            "content": {"persisted"},
        },
    )
    stage_kit._verify_upstream(
        values,
        handoff_digests,
        summaries,
        ("compose-real", "content"),
        {
            "compose-real": pro_handoff.expected_digest_keys(count),
            "content": pro_content_handoff.expected_digest_keys(values),
        },
    )

    outputs = pro_assemble.assemble(
        values,
        report,
        framed,
        device_pngs,
        content_payloads,
        framed_digests,
        content_digests,
    )
    digests = identity_digests(outputs, Path.cwd())
    if set(digests).intersection(handoff_digests):
        raise stage_kit.VerificationError("landing_digest_overlap")
    digests.update(handoff_digests)
    return success_summary(values, digests, counts=report["counts"])


def main() -> None:
    try:
        values = pro_inputs.load_order()
        emit_result("implemented", run_landing(values))
    except stage_kit.VerificationError as error:
        log(f"pro landing verification failed: {error}")
        emit_result("failed", failure_summary(f"verification:{error}"))
    except render.TemplateError:
        log("pro landing failed: template error")
        emit_result("failed", failure_summary("template_error"))
    except Exception as error:
        log(f"pro landing failed: {type(error).__name__}")
        emit_result("failed", failure_summary("pro_landing_error"))


if __name__ == "__main__":
    main()
