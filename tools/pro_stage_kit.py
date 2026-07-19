#!/usr/bin/env python3
"""Appkit-pro verifier and authoritative personal launch-kit assembler."""

from __future__ import annotations

from pathlib import Path

import pro_compose
import pro_inputs
import render
import screens
import stage_kit
from stage_support import (
    canonical_json,
    emit_result,
    failure_summary,
    log,
    safe_output_path,
)


def main() -> None:
    try:
        values = pro_inputs.load_order()
        report = pro_inputs.load_capture_report()

        def screenshot_builder(current: dict[str, object]) -> list[Path]:
            real_framed = pro_compose.build_framed(current, report)
            return screens.render_screenshots(
                current, screens.encode_framed_screens(real_framed)
            )

        def enrich(upstream_paths: list[Path]) -> list[Path]:
            old_readme = next(
                path for path in upstream_paths if path.as_posix().endswith("/out/README.md")
            )
            readme_path = render.render_readme(
                values, pro_compose.provenance(report)
            )
            report_path = safe_output_path("out/capture-report.json")
            report_path.write_text(
                canonical_json(report) + "\n",
                encoding="utf-8",
                newline="\n",
            )
            return [path for path in upstream_paths if path != old_readme] + [
                readme_path,
                report_path,
            ]

        emit_result(
            "implemented",
            stage_kit.run_kit(
                values,
                stage_kit._load_context(),
                stage_ids=("compose-real", "content"),
                screenshot_builder=screenshot_builder,
                expected_groups={
                    "compose-real": screens.expected_screenshot_relpaths(values),
                    "content": render.expected_content_relpaths(values),
                },
                enrich=enrich,
                manifest_warnings=(
                    list(report["warnings"])
                    if report["ladder"] == "synthetic"
                    else []
                ),
                summary_extras={"ladder": report["ladder"]},
            ),
        )
    except stage_kit.VerificationError as error:
        log(f"pro kit verification failed: {error}")
        emit_result("failed", failure_summary(f"verification:{error}"))
    except render.TemplateError:
        log("pro kit failed: template error")
        emit_result("failed", failure_summary("template_error"))
    except Exception as error:
        log(f"pro kit failed: {type(error).__name__}")
        emit_result("failed", failure_summary("pro_kit_error"))


if __name__ == "__main__":
    main()
