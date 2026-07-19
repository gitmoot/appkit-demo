"""Verified, symlink-safe content handoff for the personal pipeline."""

from __future__ import annotations

import json
import os
import shutil
import stat
from pathlib import Path

import pro_inputs
import render
from inputs import input_sha256
from stage_support import artifact_identity, canonical_json, inspect_output_tree, sha256_file


HANDOFF_DIR = "content"
MANIFEST_FILE = "manifest.json"


class ContentHandoffError(RuntimeError):
    pass


def _reject_symlink_chain(path: Path) -> None:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            continue
        except OSError as error:
            raise ContentHandoffError("content handoff path unavailable") from error
        if stat.S_ISLNK(mode):
            raise ContentHandoffError("content handoff path contains a symlink")


def _remove_directory(path: Path) -> None:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return
    except OSError as error:
        raise ContentHandoffError("content handoff path unavailable") from error
    if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
        raise ContentHandoffError("content handoff destination is unsafe")
    try:
        shutil.rmtree(path, ignore_errors=False)
    except OSError as error:
        raise ContentHandoffError("content handoff cleanup failed") from error


def _artifact_names(values: dict[str, object]) -> list[str]:
    return sorted(
        Path(path).relative_to("out").as_posix()
        for path in render.expected_content_handoff_relpaths(values)
    )


def expected_digest_keys(values: dict[str, object]) -> list[str]:
    return sorted(
        [f"{HANDOFF_DIR}/{name}" for name in _artifact_names(values)]
        + [f"{HANDOFF_DIR}/{MANIFEST_FILE}"]
    )


def _validate_source(root: Path, expected: list[str]) -> None:
    files, directories, has_symlink = inspect_output_tree(root)
    allowed_directories: set[str] = set()
    for name in expected:
        parent = Path(name).parent
        while parent != Path("."):
            allowed_directories.add(parent.as_posix())
            parent = parent.parent
    if has_symlink or files != set(expected) or not directories.issubset(allowed_directories):
        raise ContentHandoffError("content handoff source tree mismatch")
    for name in expected:
        try:
            mode = (root / name).lstat().st_mode
        except OSError as error:
            raise ContentHandoffError("content handoff source is unreadable") from error
        if not stat.S_ISREG(mode):
            raise ContentHandoffError("content handoff source is not regular")


def persist_assets(
    values: dict[str, object], source_root: Path
) -> tuple[dict[str, str], dict[str, object]]:
    expected = _artifact_names(values)
    _validate_source(source_root, expected)
    try:
        configured_root = pro_inputs.data_root()
    except pro_inputs.ProDataError as error:
        raise ContentHandoffError("content handoff parent is unsafe") from error
    _reject_symlink_chain(configured_root)
    try:
        root = pro_inputs.require_data_root()
    except pro_inputs.ProDataError as error:
        raise ContentHandoffError("content handoff parent is unsafe") from error
    destination = root / HANDOFF_DIR
    staging = root / f".{HANDOFF_DIR}.tmp"
    _reject_symlink_chain(root)
    try:
        destination_mode = destination.lstat().st_mode
    except FileNotFoundError:
        pass
    else:
        if stat.S_ISLNK(destination_mode) or not stat.S_ISDIR(destination_mode):
            raise ContentHandoffError("content handoff destination is unsafe")
    _remove_directory(staging)

    identities: dict[str, str] = {}
    try:
        staging.mkdir(mode=0o700)
        records: list[dict[str, object]] = []
        for name in expected:
            source = source_root / name
            target = staging / name
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            shutil.copyfile(source, target, follow_symlinks=False)
            identity = artifact_identity(target)
            identities[f"{HANDOFF_DIR}/{name}"] = identity
            records.append(
                {
                    "bytes": target.stat().st_size,
                    "identity": identity,
                    "path": name,
                    "sha256": sha256_file(target),
                }
            )
        manifest = {
            "artifacts": records,
            "input_sha256": input_sha256(values),
            "schema_version": 1,
        }
        manifest_path = staging / MANIFEST_FILE
        manifest_path.write_text(
            canonical_json(manifest) + "\n", encoding="utf-8", newline="\n"
        )
        identities[f"{HANDOFF_DIR}/{MANIFEST_FILE}"] = sha256_file(manifest_path)
        _remove_directory(destination)
        os.replace(staging, destination)
    except ContentHandoffError:
        if staging.exists() and not staging.is_symlink():
            shutil.rmtree(staging, ignore_errors=True)
        raise
    except (OSError, UnicodeError) as error:
        if staging.exists() and not staging.is_symlink():
            shutil.rmtree(staging, ignore_errors=True)
        raise ContentHandoffError("content handoff write failed") from error

    loaded, loaded_identities = load_assets(values)
    if sorted(loaded) != expected or loaded_identities != identities:
        raise ContentHandoffError("content handoff verification mismatch")
    return identities, {"count": len(expected), "path": str(destination)}


def load_assets(
    values: dict[str, object],
) -> tuple[dict[str, bytes], dict[str, str]]:
    expected = _artifact_names(values)
    root = pro_inputs.data_root() / HANDOFF_DIR
    _reject_symlink_chain(root)
    if not root.is_dir() or root.is_symlink():
        raise ContentHandoffError("content handoff is missing or unsafe")
    files, directories, has_symlink = inspect_output_tree(root)
    expected_files = set(expected) | {MANIFEST_FILE}
    allowed_directories = {
        parent.as_posix()
        for name in expected
        for parent in Path(name).parents
        if parent != Path(".")
    }
    if has_symlink or files != expected_files or not directories.issubset(allowed_directories):
        raise ContentHandoffError("content handoff tree mismatch")

    manifest_path = root / MANIFEST_FILE
    try:
        if manifest_path.stat().st_size > 256 * 1024:
            raise ContentHandoffError("content handoff manifest is too large")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ContentHandoffError("content handoff manifest is invalid") from error
    if (
        not isinstance(manifest, dict)
        or sorted(manifest) != ["artifacts", "input_sha256", "schema_version"]
        or manifest.get("schema_version") != 1
        or manifest.get("input_sha256") != input_sha256(values)
        or not isinstance(manifest.get("artifacts"), list)
    ):
        raise ContentHandoffError("content handoff manifest mismatch")

    records = manifest["artifacts"]
    if len(records) != len(expected):
        raise ContentHandoffError("content handoff manifest artifacts mismatch")
    identities = {f"{HANDOFF_DIR}/{MANIFEST_FILE}": sha256_file(manifest_path)}
    payloads: dict[str, bytes] = {}
    seen: list[str] = []
    for record in records:
        if (
            not isinstance(record, dict)
            or sorted(record) != ["bytes", "identity", "path", "sha256"]
            or not isinstance(record.get("path"), str)
            or str(record["path"]) not in expected
            or not isinstance(record.get("bytes"), int)
            or not isinstance(record.get("identity"), str)
            or not isinstance(record.get("sha256"), str)
        ):
            raise ContentHandoffError("content handoff artifact record is invalid")
        name = str(record["path"])
        path = root / name
        try:
            mode = path.lstat().st_mode
        except OSError as error:
            raise ContentHandoffError("content handoff artifact is unreadable") from error
        if (
            not stat.S_ISREG(mode)
            or path.stat().st_size != record["bytes"]
            or sha256_file(path) != record["sha256"]
            or artifact_identity(path) != record["identity"]
        ):
            raise ContentHandoffError("content handoff artifact digest mismatch")
        payloads[name] = path.read_bytes()
        identities[f"{HANDOFF_DIR}/{name}"] = str(record["identity"])
        seen.append(name)
    if sorted(seen) != expected:
        raise ContentHandoffError("content handoff artifact set mismatch")
    return payloads, {key: identities[key] for key in sorted(identities)}
