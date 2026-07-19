#!/usr/bin/env python3
"""Appkit-pro join: assemble the full tree from isolated persisted branches."""

from __future__ import annotations

from pathlib import Path

import frame_compose
import pro_agent_content
import pro_assemble
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


def _verify_branches(
    context: dict[str, object],
    values: dict[str, object],
    framed_digests: dict[str, str],
    count: int,
) -> None:
    if context.get("schema_version") != 1 or context.get("complete") is not True:
        raise stage_kit.VerificationError("context_incomplete")
    stages = context.get("stages")
    if not isinstance(stages, dict) or sorted(stages) != ["compose-real", "content"]:
        raise stage_kit.VerificationError("context_stages")
    content_stage = stages.get("content")
    if (
        not isinstance(content_stage, dict)
        or content_stage.get("id") != "content"
        or content_stage.get("state") != "succeeded"
        or content_stage.get("summary_truncated") is not False
        or not isinstance(content_stage.get("summary"), str)
    ):
        raise stage_kit.VerificationError("context_stage_invalid")
    compose_context = {
        "complete": True,
        "schema_version": 1,
        "stages": {"compose-real": stages["compose-real"]},
    }
    summaries = stage_kit._upstream_summaries(
        compose_context,
        values,
        ("compose-real",),
        {"compose-real": {"counts", "persisted"}},
    )
    stage_kit._verify_upstream(
        values,
        framed_digests,
        summaries,
        ("compose-real",),
        {"compose-real": pro_handoff.expected_digest_keys(count)},
    )


def run_landing(values: dict[str, object]) -> dict[str, object]:
    frame_compose.verify_assets()
    prepare_output_tree()
    context = stage_kit._load_context()
    report = pro_inputs.load_capture_report()
    framed, device_pngs, framed_digests = pro_handoff.load_assets(values, report)
    count = len(framed)
    _verify_branches(context, values, framed_digests, count)
    content = pro_agent_content.inspect(values)
    for relative in sorted(content.reasons):
        log(f"content fallback: {relative}/{content.reasons[relative]}")

    assembly = pro_assemble.assemble(
        values,
        report,
        framed,
        device_pngs,
        framed_digests,
        content,
    )
    all_digests = identity_digests(assembly.paths, Path.cwd())
    verified_keys = pro_agent_content.verified_output_keys(
        pro_assemble.expected_output_relpaths(values, count),
        content.provenance,
    )
    digests = {key: all_digests[key] for key in verified_keys}
    if set(digests).intersection(framed_digests):
        raise stage_kit.VerificationError("landing_digest_overlap")
    digests.update(framed_digests)
    return success_summary(
        values,
        digests,
        content_provenance=content.provenance,
        counts=report["counts"],
        observed=assembly.observed,
    )


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
