#!/usr/bin/env python3
"""Appkit-pro verifier and authoritative personal launch-kit assembler."""

from __future__ import annotations

import os
import shutil
import stat
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
    inspect_output_tree,
    prepare_output_tree,
    safe_output_path,
    sha256_file,
)


class PersistenceError(RuntimeError):
    pass


def _reject_symlink_chain(path: Path) -> None:
    """Reject an existing symlink in an absolute destination's parent chain."""

    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            continue
        except OSError as error:
            raise PersistenceError("persistent destination unavailable") from error
        if stat.S_ISLNK(mode):
            raise PersistenceError("persistent destination symlink")


def _checked_directory(path: Path, *, removable: bool) -> None:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return
    except OSError as error:
        raise PersistenceError("persistent destination unavailable") from error
    if stat.S_ISLNK(mode):
        raise PersistenceError("persistent destination symlink")
    if not stat.S_ISDIR(mode):
        raise PersistenceError("persistent destination is not a directory")
    if removable:
        try:
            shutil.rmtree(path, ignore_errors=False)
        except OSError as error:
            raise PersistenceError("persistent destination cleanup failed") from error


def _regular_tree(root: Path) -> tuple[list[str], list[str]]:
    files, directories, has_symlink = inspect_output_tree(root)
    if has_symlink:
        raise PersistenceError("persistent tree contains a symlink")
    for relative in sorted(directories):
        try:
            mode = (root / relative).lstat().st_mode
        except OSError as error:
            raise PersistenceError("persistent tree is unreadable") from error
        if not stat.S_ISDIR(mode):
            raise PersistenceError("persistent tree contains a non-directory")
    for relative in sorted(files):
        try:
            mode = (root / relative).lstat().st_mode
        except OSError as error:
            raise PersistenceError("persistent tree is unreadable") from error
        if not stat.S_ISREG(mode):
            raise PersistenceError("persistent tree contains a non-regular file")
    return sorted(files), sorted(directories)


def persist_verified_kit(expected_zip_sha256: str) -> dict[str, str]:
    """Freshly mirror the verified worktree kit into the personal data root."""

    source = Path.cwd() / "out"
    if not source.is_dir() or source.is_symlink():
        raise PersistenceError("verified kit source is unavailable")
    source_files, source_directories = _regular_tree(source)
    if "launch-kit.zip" not in source_files:
        raise PersistenceError("verified kit zip is missing")
    if sha256_file(source / "launch-kit.zip") != expected_zip_sha256:
        raise PersistenceError("verified kit zip digest mismatch")

    try:
        configured_parent = pro_inputs.data_root()
    except pro_inputs.ProDataError as error:
        raise PersistenceError("persistent destination parent is unsafe") from error
    _reject_symlink_chain(configured_parent)
    try:
        parent = pro_inputs.require_data_root()
    except pro_inputs.ProDataError as error:
        raise PersistenceError("persistent destination parent is unsafe") from error
    destination = parent / "kit"
    staging = parent / ".kit.tmp"
    _reject_symlink_chain(parent)
    _checked_directory(destination, removable=False)
    _checked_directory(staging, removable=True)

    try:
        staging.mkdir(mode=0o700)
        for relative in source_directories:
            (staging / relative).mkdir(mode=0o700, parents=True, exist_ok=True)
        for relative in source_files:
            target = staging / relative
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            shutil.copyfile(source / relative, target, follow_symlinks=False)

        copied_files, copied_directories = _regular_tree(staging)
        if copied_files != source_files or copied_directories != source_directories:
            raise PersistenceError("persistent tree shape mismatch")
        for relative in source_files:
            source_path = source / relative
            copied_path = staging / relative
            if (
                source_path.stat().st_size != copied_path.stat().st_size
                or sha256_file(source_path) != sha256_file(copied_path)
            ):
                raise PersistenceError("persistent file digest mismatch")

        _checked_directory(destination, removable=True)
        os.replace(staging, destination)
    except PersistenceError:
        if staging.exists() and not staging.is_symlink():
            shutil.rmtree(staging, ignore_errors=True)
        raise
    except OSError as error:
        if staging.exists() and not staging.is_symlink():
            shutil.rmtree(staging, ignore_errors=True)
        raise PersistenceError("persistent kit write failed") from error

    persisted_zip_sha256 = sha256_file(destination / "launch-kit.zip")
    if persisted_zip_sha256 != expected_zip_sha256:
        raise PersistenceError("persisted zip digest mismatch")
    log(f"persisted pro kit to {destination}")
    return {"path": str(destination), "zip_sha256": persisted_zip_sha256}


def main() -> None:
    try:
        values = pro_inputs.load_order()
        report = pro_inputs.load_capture_report()
        prepare_output_tree()
        context = stage_kit._load_context()

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

        summary = stage_kit.run_kit(
            values,
            context,
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
        )
        zip_digest = summary["digests"]["out/launch-kit.zip"]
        if not isinstance(zip_digest, str):
            raise PersistenceError("verified kit zip digest is invalid")
        summary["persisted"] = persist_verified_kit(zip_digest)
        emit_result("implemented", summary)
    except stage_kit.VerificationError as error:
        log(f"pro kit verification failed: {error}")
        emit_result("failed", failure_summary(f"verification:{error}"))
    except render.TemplateError:
        log("pro kit failed: template error")
        emit_result("failed", failure_summary("template_error"))
    except PersistenceError as error:
        log(f"pro kit persistence failed: {error}")
        emit_result("failed", failure_summary("persistence_error"))
    except Exception as error:
        log(f"pro kit failed: {type(error).__name__}")
        emit_result("failed", failure_summary("pro_kit_error"))


if __name__ == "__main__":
    main()
