#!/usr/bin/env python3
"""Verifier and authoritative reproducible launch-kit assembler."""

from __future__ import annotations

import json
import os
import zipfile
from collections.abc import Callable
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


MAX_OUTPUT_BYTES = 48 * 1024 * 1024
MAX_ZIP_BYTES = 56 * 1024 * 1024


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
    context: dict[str, object],
    values: dict[str, object],
    stage_ids: tuple[str, ...] = ("compose", "content"),
    summary_extras: dict[str, set[str]] | None = None,
) -> dict[str, dict[str, object]]:
    if context.get("schema_version") != 1 or context.get("complete") is not True:
        raise VerificationError("context_incomplete")
    stages = context.get("stages")
    if not isinstance(stages, dict) or sorted(stages) != sorted(stage_ids):
        raise VerificationError("context_stages")

    expected_input = input_sha256(values)
    parsed: dict[str, dict[str, object]] = {}
    for stage_id in stage_ids:
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
        expected_summary_keys = {
            "digests",
            "input_sha256",
            "pillow",
            "v",
            "zlib",
        }
        if summary_extras is not None:
            expected_summary_keys.update(summary_extras.get(stage_id, set()))
        if not isinstance(summary, dict) or set(summary) != expected_summary_keys:
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
    required_stage_ids: tuple[str, ...] = ("compose", "content"),
    expected_groups: dict[str, list[str]] | None = None,
) -> None:
    if expected_groups is None:
        expected_groups = {
            "compose": screens.expected_screenshot_relpaths(values),
            "content": render.expected_content_relpaths(values),
        }
    if (
        sorted(summaries) != sorted(required_stage_ids)
        or sorted(expected_groups) != sorted(required_stage_ids)
    ):
        raise VerificationError("summary_stages")
    for stage_id in required_stage_ids:
        expected = {
            path: own_digests[path] for path in sorted(expected_groups[stage_id])
        }
        if summaries[stage_id]["digests"] != expected:
            raise VerificationError("digest_mismatch")


def _write_manifest(
    paths: list[Path],
    values: dict[str, object],
    warnings: list[str] | None = None,
    metadata: dict[str, object] | None = None,
) -> tuple[Path, int]:
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
    if warnings is not None:
        manifest["warnings"] = warnings
    if metadata is not None:
        if set(metadata).intersection(manifest):
            raise VerificationError("manifest_metadata")
        for key in sorted(metadata):
            manifest[key] = metadata[key]
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


def _paths_size(paths: list[Path]) -> int:
    return sum(
        path.stat().st_size
        for path in sorted(paths, key=lambda item: item.as_posix())
    )


def run_kit(
    values: dict[str, object],
    context: dict[str, object],
    *,
    stage_ids: tuple[str, ...] = ("compose", "content"),
    screenshot_builder: Callable[[dict[str, object]], list[Path]] | None = None,
    expected_groups: dict[str, list[str]] | None = None,
    enrich: Callable[[list[Path]], list[Path]] | None = None,
    manifest_warnings: list[str] | None = None,
    summary_extras: dict[str, object] | None = None,
    render_assets: tuple[dict[int, object], dict[int, bytes]] | None = None,
    render_options: dict[str, object] | None = None,
    content_builder: Callable[
        [dict[str, object], dict[int, object], dict[int, bytes]], list[Path]
    ]
    | None = None,
    extra_identity_digests: dict[str, str] | None = None,
    upstream_summary_extras: dict[str, set[str]] | None = None,
    artifact_builder: Callable[[dict[str, object]], list[Path]] | None = None,
    manifest_metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    """Regenerate, cross-check, and package a public or personal kit."""

    frame_compose.verify_assets()
    prepare_output_tree()
    summaries = _upstream_summaries(
        context, values, stage_ids, upstream_summary_extras
    )

    if artifact_builder is not None:
        if any(
            option is not None
            for option in (
                screenshot_builder,
                render_assets,
                render_options,
                content_builder,
            )
        ):
            raise VerificationError("artifact_builder_options")
        upstream_paths = sorted(
            artifact_builder(values), key=lambda path: path.as_posix()
        )
    else:
        if screenshot_builder is None:
            framed, devices = screens.build_render_assets(values)
            screenshot_paths = screens.render_screenshots(
                values, screens.encode_framed_screens(framed)
            )
        else:
            screenshot_paths = screenshot_builder(values)
            if render_assets is None:
                framed, devices = screens.build_render_assets(values)
                device_pngs = screens.encode_device_screens(devices)
            else:
                framed, device_pngs = render_assets
        if screenshot_builder is None:
            device_pngs = screens.encode_device_screens(devices)
        if content_builder is None:
            content_paths = render.render_all(
                values,
                framed,
                device_pngs,
                **({} if render_options is None else render_options),
            )
        else:
            if render_options is not None:
                raise VerificationError("content_builder_options")
            content_paths = content_builder(values, framed, device_pngs)
        upstream_paths = sorted(
            screenshot_paths + content_paths,
            key=lambda path: path.as_posix(),
        )
    upstream_digests = identity_digests(upstream_paths, Path.cwd())
    if extra_identity_digests is not None:
        overlap = set(upstream_digests).intersection(extra_identity_digests)
        if overlap:
            raise VerificationError("extra_digest_overlap")
        upstream_digests.update(extra_identity_digests)
    _verify_upstream(
        values,
        upstream_digests,
        summaries,
        stage_ids,
        expected_groups,
    )

    upstream_relpaths = {
        path.relative_to(Path.cwd() / "out").as_posix()
        for path in upstream_paths
    }
    _require_exact_tree(upstream_relpaths)

    artifact_paths = upstream_paths if enrich is None else sorted(
        enrich(upstream_paths), key=lambda path: path.as_posix()
    )
    base_relpaths = {
        path.relative_to(Path.cwd() / "out").as_posix()
        for path in artifact_paths
    }
    _require_exact_tree(base_relpaths)
    manifest_path, artifact_count = _write_manifest(
        artifact_paths,
        values,
        warnings=manifest_warnings,
        metadata=manifest_metadata,
    )
    _require_exact_tree(base_relpaths | {"manifest.json"})
    zip_path = _write_zip(artifact_paths, manifest_path)
    _require_exact_tree(base_relpaths | {"manifest.json", "launch-kit.zip"})

    artifact_bytes = _paths_size(artifact_paths)
    if artifact_bytes > MAX_OUTPUT_BYTES:
        raise VerificationError("artifact_budget")
    zip_bytes = zip_path.stat().st_size
    if zip_bytes > MAX_ZIP_BYTES:
        raise VerificationError("zip_budget")

    final_digests = identity_digests(artifact_paths, Path.cwd())
    final_digests["out/manifest.json"] = sha256_file(manifest_path)
    final_digests["out/launch-kit.zip"] = sha256_file(zip_path)
    extras: dict[str, object] = {
        "artifact_count": artifact_count,
        "artifact_bytes": artifact_bytes,
        "manifest_sha256": final_digests["out/manifest.json"],
        "zip_bytes": zip_bytes,
    }
    if summary_extras is not None:
        extras.update(summary_extras)
    return success_summary(values, final_digests, **extras)


def main() -> None:
    try:
        values = load_inputs()
        prepare_output_tree()
        context = _load_context()
        emit_result("implemented", run_kit(values, context))
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
