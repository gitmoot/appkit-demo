"""Verified, symlink-safe framed-asset handoff for personal pipeline stages."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
from pathlib import Path

from PIL import Image

import frame_compose
import pro_inputs
from inputs import input_sha256
from stage_support import artifact_identity, canonical_json, sha256_file


HANDOFF_DIR = "framed"
MANIFEST_FILE = "manifest.json"


class HandoffError(RuntimeError):
    pass


def _report_sha256(report: dict[str, object]) -> str:
    return hashlib.sha256(canonical_json(report).encode("utf-8")).hexdigest()


def _reject_symlink_chain(path: Path) -> None:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            continue
        except OSError as error:
            raise HandoffError("framed handoff path unavailable") from error
        if stat.S_ISLNK(mode):
            raise HandoffError("framed handoff path contains a symlink")


def _remove_directory(path: Path) -> None:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return
    except OSError as error:
        raise HandoffError("framed handoff path unavailable") from error
    if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
        raise HandoffError("framed handoff destination is unsafe")
    try:
        shutil.rmtree(path, ignore_errors=False)
    except OSError as error:
        raise HandoffError("framed handoff cleanup failed") from error


def _expected_names(count: int) -> list[str]:
    names = [MANIFEST_FILE]
    for index in range(1, count + 1):
        names.extend((f"device_{index}.png", f"frame_{index}.png"))
    return sorted(names)


def expected_digest_keys(count: int) -> list[str]:
    return [f"{HANDOFF_DIR}/{name}" for name in _expected_names(count)]


def persist_assets(
    values: dict[str, object],
    report: dict[str, object],
    framed: dict[int, Image.Image],
    devices: dict[int, Image.Image],
) -> tuple[dict[str, str], dict[str, object]]:
    indices = sorted(framed)
    if indices != list(range(1, len(indices) + 1)) or sorted(devices) != indices:
        raise HandoffError("framed handoff indices are invalid")
    if len(indices) != len(report["shots"]):
        raise HandoffError("framed handoff count mismatch")

    try:
        configured_root = pro_inputs.data_root()
    except pro_inputs.ProDataError as error:
        raise HandoffError("framed handoff parent is unsafe") from error
    _reject_symlink_chain(configured_root)
    try:
        root = pro_inputs.require_data_root()
    except pro_inputs.ProDataError as error:
        raise HandoffError("framed handoff parent is unsafe") from error
    destination = root / HANDOFF_DIR
    staging = root / f".{HANDOFF_DIR}.tmp"
    _reject_symlink_chain(root)
    try:
        destination_mode = destination.lstat().st_mode
    except FileNotFoundError:
        pass
    else:
        if stat.S_ISLNK(destination_mode) or not stat.S_ISDIR(destination_mode):
            raise HandoffError("framed handoff destination is unsafe")
    _remove_directory(staging)

    try:
        staging.mkdir(mode=0o700)
        records: list[dict[str, object]] = []
        identities: dict[str, str] = {}
        for index in indices:
            for kind, image in (("device", devices[index]), ("frame", framed[index])):
                name = f"{kind}_{index}.png"
                path = staging / name
                path.write_bytes(frame_compose.png_bytes(image))
                identity = artifact_identity(path)
                identities[f"{HANDOFF_DIR}/{name}"] = identity
                records.append(
                    {
                        "bytes": path.stat().st_size,
                        "identity": identity,
                        "path": name,
                        "sha256": sha256_file(path),
                    }
                )
        manifest = {
            "artifacts": sorted(records, key=lambda item: str(item["path"])),
            "capture_report_sha256": _report_sha256(report),
            "counts": report["counts"],
            "input_sha256": input_sha256(values),
            "schema_version": 1,
        }
        manifest_path = staging / MANIFEST_FILE
        manifest_path.write_text(
            canonical_json(manifest) + "\n", encoding="utf-8", newline="\n"
        )
        identities[f"{HANDOFF_DIR}/{MANIFEST_FILE}"] = sha256_file(manifest_path)

        actual = sorted(path.name for path in staging.iterdir())
        if actual != _expected_names(len(indices)) or any(
            path.is_symlink() or not path.is_file() for path in staging.iterdir()
        ):
            raise HandoffError("framed handoff staging tree mismatch")
        _remove_directory(destination)
        os.replace(staging, destination)
    except HandoffError:
        if staging.exists() and not staging.is_symlink():
            shutil.rmtree(staging, ignore_errors=True)
        raise
    except (OSError, UnicodeError) as error:
        if staging.exists() and not staging.is_symlink():
            shutil.rmtree(staging, ignore_errors=True)
        raise HandoffError("framed handoff write failed") from error

    loaded_framed, loaded_devices, loaded_identities = load_assets(values, report)
    for image in loaded_framed.values():
        image.close()
    if sorted(loaded_devices) != indices or loaded_identities != identities:
        raise HandoffError("framed handoff verification mismatch")
    return identities, {"count": len(indices), "path": str(destination)}


def load_assets(
    values: dict[str, object], report: dict[str, object]
) -> tuple[dict[int, Image.Image], dict[int, bytes], dict[str, str]]:
    count = len(report["shots"])
    root = pro_inputs.data_root() / HANDOFF_DIR
    _reject_symlink_chain(root)
    if not root.is_dir() or root.is_symlink():
        raise HandoffError("framed handoff is missing or unsafe")
    try:
        children = sorted(root.iterdir(), key=lambda path: path.name)
    except OSError as error:
        raise HandoffError("framed handoff is unreadable") from error
    if [path.name for path in children] != _expected_names(count) or any(
        path.is_symlink() or not path.is_file() for path in children
    ):
        raise HandoffError("framed handoff tree mismatch")

    manifest_path = root / MANIFEST_FILE
    try:
        if manifest_path.stat().st_size > 64 * 1024:
            raise HandoffError("framed handoff manifest is too large")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise HandoffError("framed handoff manifest is invalid") from error
    if (
        not isinstance(manifest, dict)
        or sorted(manifest)
        != [
            "artifacts",
            "capture_report_sha256",
            "counts",
            "input_sha256",
            "schema_version",
        ]
        or manifest.get("schema_version") != 1
        or manifest.get("input_sha256") != input_sha256(values)
        or manifest.get("capture_report_sha256") != _report_sha256(report)
        or manifest.get("counts") != report["counts"]
        or not isinstance(manifest.get("artifacts"), list)
    ):
        raise HandoffError("framed handoff manifest mismatch")

    expected_artifact_names = sorted(
        name for name in _expected_names(count) if name != MANIFEST_FILE
    )
    records = manifest["artifacts"]
    if len(records) != len(expected_artifact_names):
        raise HandoffError("framed handoff manifest artifacts mismatch")
    identities: dict[str, str] = {
        f"{HANDOFF_DIR}/{MANIFEST_FILE}": sha256_file(manifest_path)
    }
    framed: dict[int, Image.Image] = {}
    devices: dict[int, bytes] = {}
    seen: list[str] = []
    for record in records:
        if (
            not isinstance(record, dict)
            or sorted(record) != ["bytes", "identity", "path", "sha256"]
            or not isinstance(record.get("path"), str)
            or Path(str(record["path"])).name != record["path"]
            or not isinstance(record.get("bytes"), int)
            or not isinstance(record.get("identity"), str)
            or not isinstance(record.get("sha256"), str)
        ):
            raise HandoffError("framed handoff artifact record is invalid")
        name = str(record["path"])
        path = root / name
        if (
            path.stat().st_size != record["bytes"]
            or sha256_file(path) != record["sha256"]
            or artifact_identity(path) != record["identity"]
        ):
            raise HandoffError("framed handoff artifact digest mismatch")
        identities[f"{HANDOFF_DIR}/{name}"] = str(record["identity"])
        seen.append(name)
        kind, raw_index = name.removesuffix(".png").rsplit("_", 1)
        index = int(raw_index)
        if kind == "frame":
            with Image.open(path) as image:
                if image.size != (frame_compose.CANVAS_W, frame_compose.CANVAS_H):
                    raise HandoffError("framed marketing image geometry mismatch")
                framed[index] = image.convert("RGB")
        elif kind == "device":
            with Image.open(path) as image:
                prepared = image.convert("RGBA")
                if prepared.getpixel((0, 0))[3] != 0:
                    raise HandoffError("framed device alpha corner is opaque")
            devices[index] = path.read_bytes()
        else:
            raise HandoffError("framed handoff artifact name is invalid")
    if sorted(seen) != expected_artifact_names or sorted(framed) != list(
        range(1, count + 1)
    ) or sorted(devices) != list(range(1, count + 1)):
        raise HandoffError("framed handoff artifact set mismatch")
    return framed, devices, {key: identities[key] for key in sorted(identities)}
