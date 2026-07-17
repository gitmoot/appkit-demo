#!/usr/bin/env python3
"""Verifier and authoritative reproducible launch-kit assembler."""

from __future__ import annotations

import json
import os
import zipfile
from pathlib import Path

import frame_compose
import render
import screens
from inputs import InputError, input_sha256, load_inputs
from stage_support import (
    PILLOW_VERSION,
    ZLIB_VERSION,
    canonical_json,
    emit_result,
    failure_summary,
    identity_digests,
    inspect_output_tree,
    log,
    prepare_output_tree,
    safe_output_path,
    sha256_file,
    success_summary,
)


class VerificationError(RuntimeError):
    pass


def _expected_relpaths(values: dict[str, object]) -> list[str]:
    return sorted(
        screens.expected_screenshot_relpaths(values)
        + render.expected_content_relpaths(values)
    )


def _allowed_directories(expected_files: list[str]) -> set[str]:
    directories: set[str] = set()
    for relative in expected_files:
        path = Path(relative).relative_to("out")
        parent = path.parent
        while parent != Path("."):
            directories.add(parent.as_posix())
            parent = parent.parent
    return directories


def _load_context() -> dict[str, object]:
    raw_path = os.environ.get("GITMOOT_PIPELINE_UPSTREAM_CONTEXT_FILE")
    if not raw_path:
        raise VerificationError("context_missing")
    path = Path(raw_path)
    if not path.is_file() or path.is_symlink():
        raise VerificationError("context_invalid")
    try:
        if path.stat().st_size > 64 * 1024:
            raise VerificationError("context_invalid")
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise VerificationError("context_invalid") from error
    if not isinstance(data, dict):
        raise VerificationError("context_invalid")
    return data


def _upstream_summaries(
    context: dict[str, object], values: dict[str, object]
) -> dict[str, dict[str, object]]:
    if context.get("schema_version") != 1 or context.get("complete") is not True:
        raise VerificationError("context_incomplete")
    stages = context.get("stages")
    if not isinstance(stages, dict) or sorted(stages) != ["compose", "content"]:
        raise VerificationError("context_stages")

    expected_input = input_sha256(values)
    parsed: dict[str, dict[str, object]] = {}
    for stage_id in ("compose", "content"):
        stage = stages.get(stage_id)
        if not isinstance(stage, dict):
            raise VerificationError("context_stage_invalid")
        if (
            stage.get("id") != stage_id
            or stage.get("state") != "succeeded"
            or stage.get("summary_truncated") is not False
            or not isinstance(stage.get("summary"), str)
        ):
            raise VerificationError("context_stage_invalid")
        try:
            summary = json.loads(str(stage["summary"]))
        except json.JSONDecodeError as error:
            raise VerificationError("summary_invalid") from error
        if not isinstance(summary, dict) or sorted(summary) != [
            "digests",
            "input_sha256",
            "pillow",
            "v",
            "zlib",
        ]:
            raise VerificationError("summary_invalid")
        digests = summary.get("digests")
        if (
            summary.get("v") != 1
            or summary.get("input_sha256") != expected_input
            or summary.get("pillow") != PILLOW_VERSION
            or summary.get("zlib") != ZLIB_VERSION
            or not isinstance(digests, dict)
            or any(not isinstance(key, str) or not isinstance(value, str) for key, value in digests.items())
        ):
            raise VerificationError("summary_mismatch")
        parsed[stage_id] = summary
    return parsed


def _verify_upstream(
    values: dict[str, object],
    own_digests: dict[str, str],
    summaries: dict[str, dict[str, object]],
) -> None:
    expected_groups = {
        "compose": screens.expected_screenshot_relpaths(values),
        "content": render.expected_content_relpaths(values),
    }
    for stage_id in ("compose", "content"):
        expected = {
            path: own_digests[path] for path in sorted(expected_groups[stage_id])
        }
        if summaries[stage_id]["digests"] != expected:
            raise VerificationError("digest_mismatch")


def _write_manifest(paths: list[Path], values: dict[str, object]) -> tuple[Path, int]:
    out = Path.cwd() / "out"
    records: list[dict[str, object]] = []
    for path in sorted(paths, key=lambda item: item.relative_to(out).as_posix()):
        records.append(
            {
                "bytes": path.stat().st_size,
                "path": path.relative_to(out).as_posix(),
                "sha256": sha256_file(path),
            }
        )
    manifest = {
        "artifacts": records,
        "input_sha256": input_sha256(values),
        "pillow": PILLOW_VERSION,
        "schema_version": 1,
        "zlib": ZLIB_VERSION,
    }
    manifest_path = safe_output_path("out/manifest.json")
    manifest_path.write_text(canonical_json(manifest) + "\n", encoding="utf-8", newline="\n")
    return manifest_path, len(records)


def _write_zip(paths: list[Path], manifest_path: Path) -> Path:
    out = Path.cwd() / "out"
    zip_path = safe_output_path("out/launch-kit.zip")
    members = sorted(paths + [manifest_path], key=lambda item: item.relative_to(out).as_posix())
    with zipfile.ZipFile(zip_path, mode="w", compression=zipfile.ZIP_STORED) as archive:
        for path in members:
            name = path.relative_to(out).as_posix()
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())
    return zip_path


def _require_exact_tree(expected: set[str]) -> None:
    out = Path.cwd() / "out"
    files, directories, has_symlink = inspect_output_tree(out)
    allowed_dirs = _allowed_directories(["out/" + path for path in expected])
    if has_symlink or files != expected or not directories.issubset(allowed_dirs):
        raise VerificationError("unexpected_output")


def main() -> None:
    try:
        values = load_inputs()
        frame_compose.verify_assets()
        prepare_output_tree()
        summaries = _upstream_summaries(_load_context(), values)

        screenshot_paths = screens.render_screenshots(values)
        content_paths = render.render_all(values)
        artifact_paths = sorted(
            screenshot_paths + content_paths, key=lambda path: path.as_posix()
        )
        digests = identity_digests(artifact_paths, Path.cwd())
        _verify_upstream(values, digests, summaries)

        base_relpaths = {
            path.relative_to(Path.cwd() / "out").as_posix() for path in artifact_paths
        }
        _require_exact_tree(base_relpaths)
        manifest_path, artifact_count = _write_manifest(artifact_paths, values)
        _require_exact_tree(base_relpaths | {"manifest.json"})
        zip_path = _write_zip(artifact_paths, manifest_path)
        _require_exact_tree(base_relpaths | {"manifest.json", "launch-kit.zip"})

        final_digests = dict(digests)
        final_digests["out/manifest.json"] = sha256_file(manifest_path)
        final_digests["out/launch-kit.zip"] = sha256_file(zip_path)
        manifest_sha = final_digests["out/manifest.json"]
        emit_result(
            "implemented",
            success_summary(
                values,
                final_digests,
                artifact_count=artifact_count,
                manifest_sha256=manifest_sha,
            ),
        )
    except InputError as error:
        log(f"validation failed: {error.field}/{error.code}")
        emit_result("failed", failure_summary(f"validation:{error.field}:{error.code}"))
    except VerificationError as error:
        log(f"kit verification failed: {error}")
        emit_result("failed", failure_summary(f"verification:{error}"))
    except render.TemplateError:
        log("kit failed: template error")
        emit_result("failed", failure_summary("template_error"))
    except Exception as error:
        log(f"kit failed: {type(error).__name__}")
        emit_result("failed", failure_summary("kit_error"))


if __name__ == "__main__":
    main()
