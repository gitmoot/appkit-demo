"""Result, digest, and output-tree helpers shared by the shell stages."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

from PIL import Image, __version__ as PILLOW_VERSION

from inputs import input_sha256


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def emit_result(decision: str, summary: dict[str, object]) -> None:
    payload = {
        "gitmoot_result": {
            "decision": decision,
            "summary": canonical_json(summary),
        }
    }
    # Deliberately the only stdout write in every stage process.
    sys.stdout.write(canonical_json(payload) + "\n")


def log(message: str) -> None:
    sys.stderr.write(message + "\n")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def artifact_identity(path: Path) -> str:
    if path.suffix.lower() == ".png":
        with Image.open(path) as image:
            pixels = image.convert("RGBA").tobytes()
        return hashlib.sha256(pixels).hexdigest()
    return sha256_file(path)


def identity_digests(paths: list[Path], cwd: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in sorted(paths, key=lambda item: item.as_posix()):
        key = path.relative_to(cwd).as_posix()
        result[key] = artifact_identity(path)
    return result


def success_summary(
    values: dict[str, object],
    digests: dict[str, str],
    **extras: object,
) -> dict[str, object]:
    summary: dict[str, object] = {
        "digests": {key: digests[key] for key in sorted(digests)},
        "input_sha256": input_sha256(values),
        "pillow": PILLOW_VERSION,
        "v": 1,
    }
    for key in sorted(extras):
        summary[key] = extras[key]
    return summary


def failure_summary(reason: str) -> dict[str, object]:
    return {"reason": reason, "v": 1}


def safe_output_path(relative: str) -> Path:
    cwd = Path.cwd()
    out = cwd / "out"
    if out.exists() and out.is_symlink():
        raise RuntimeError("unsafe output root")
    out.mkdir(exist_ok=True)
    target = cwd / relative
    if target != out and out not in target.parents:
        raise RuntimeError("output path escaped root")
    current = out
    for part in target.relative_to(out).parts[:-1]:
        current = current / part
        if current.exists() and current.is_symlink():
            raise RuntimeError("unsafe output parent")
        current.mkdir(exist_ok=True)
    if target.exists() and target.is_symlink():
        raise RuntimeError("unsafe output target")
    return target


def inspect_output_tree(out: Path) -> tuple[set[str], set[str], bool]:
    files: set[str] = set()
    directories: set[str] = set()
    has_symlink = False
    if not out.exists():
        return files, directories, has_symlink
    if out.is_symlink():
        return files, directories, True
    for root, dir_names, file_names in os.walk(out, followlinks=False):
        root_path = Path(root)
        dir_names.sort()
        file_names.sort()
        for name in list(dir_names):
            path = root_path / name
            rel = path.relative_to(out).as_posix()
            if path.is_symlink():
                has_symlink = True
                dir_names.remove(name)
            else:
                directories.add(rel)
        for name in file_names:
            path = root_path / name
            rel = path.relative_to(out).as_posix()
            if path.is_symlink():
                has_symlink = True
            else:
                files.add(rel)
    return files, directories, has_symlink
