#!/usr/bin/env python3
"""Render the personal pipeline with its static target-repository read grant."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import sys
from pathlib import Path

import pro_inputs


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
TEMPLATE = ROOT / "templates" / "appkit-pro.yaml.tmpl"
PROMPT = ROOT / "templates" / "derive-prompt.md"
CONTENT_PROMPT = ROOT / "templates" / "content-prompt.md"
OUTPUT = ROOT / "appkit-pro.yaml"
STALE_FILES = (
    f"{pro_inputs.ORDER_FILE}.tmp",
    pro_inputs.ORDER_FILE,
    f"{pro_inputs.RATIONALE_FILE}.tmp",
    pro_inputs.RATIONALE_FILE,
    f"{pro_inputs.REPORT_FILE}.tmp",
    pro_inputs.REPORT_FILE,
)
STALE_DIRECTORIES = (
    ".content.tmp",
    ".framed.tmp",
    ".kit.tmp",
    "content",
    "content-agent",
    "framed",
    "kit",
    "screens",
)


def _read(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        raise RuntimeError("pipeline template missing or unsafe")
    return path.read_text(encoding="utf-8")


def _reject_symlink_chain(path: Path) -> None:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            continue
        except OSError as error:
            raise RuntimeError("personal data path is unavailable") from error
        if stat.S_ISLNK(mode):
            raise RuntimeError("personal data path contains a symlink")


def _assert_regular_tree(path: Path) -> None:
    for directory, dir_names, file_names in os.walk(path, followlinks=False):
        dir_names.sort()
        file_names.sort()
        parent = Path(directory)
        for name in dir_names:
            mode = (parent / name).lstat().st_mode
            if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
                raise RuntimeError("stale derived directory is unsafe")
        for name in file_names:
            mode = (parent / name).lstat().st_mode
            if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
                raise RuntimeError("stale derived file is unsafe")


def _clear_stale_path(root: Path, name: str, *, directory: bool) -> bool:
    path = root / name
    if path.parent != root:
        raise RuntimeError("stale derived path escaped the data root")
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return False
    except OSError as error:
        raise RuntimeError("stale derived path is unavailable") from error
    if stat.S_ISLNK(mode):
        raise RuntimeError("stale derived path is a symlink")
    try:
        if directory:
            if not stat.S_ISDIR(mode):
                raise RuntimeError("stale derived directory is unsafe")
            _assert_regular_tree(path)
            shutil.rmtree(path, ignore_errors=False)
        else:
            if not stat.S_ISREG(mode):
                raise RuntimeError("stale derived file is unsafe")
            path.unlink()
    except OSError as error:
        raise RuntimeError("stale derived cleanup failed") from error
    return True


def _read_stored_order_target(path: Path) -> str:
    try:
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
            raise RuntimeError("stored order is unsafe")
        if path.stat().st_size > 16 * 1024:
            raise RuntimeError("stored order is too large")
        text = path.read_text(encoding="utf-8")
        return pro_inputs.parse_persisted_order_target(text)
    except (OSError, UnicodeError, pro_inputs.ProDataError) as error:
        raise RuntimeError("stored order is malformed") from error


def _reconcile_derived_state(target: Path, configured_root: Path) -> None:
    _reject_symlink_chain(configured_root)
    root = pro_inputs.require_data_root()
    _reject_symlink_chain(root)
    order = root / pro_inputs.ORDER_FILE
    derived_names = (*STALE_FILES, *STALE_DIRECTORIES)
    other_state_exists = any(
        (root / name).exists() or (root / name).is_symlink()
        for name in derived_names
        if name != pro_inputs.ORDER_FILE
    )
    try:
        order.lstat()
    except FileNotFoundError:
        if not other_state_exists:
            return
        old_target = "<missing>"
    except OSError as error:
        raise RuntimeError("stored order is unavailable") from error
    else:
        try:
            old_target = _read_stored_order_target(order)
        except RuntimeError:
            old_target = "<malformed>"
        else:
            if old_target == str(target):
                return

    sys.stderr.write(
        "pro_make_pipeline: target changed "
        f"{json.dumps(old_target, ensure_ascii=True)} -> "
        f"{json.dumps(str(target), ensure_ascii=True)}\n"
    )
    for name in STALE_FILES:
        if _clear_stale_path(root, name, directory=False):
            sys.stderr.write(f"pro_make_pipeline: cleared stale {name}\n")
    for name in STALE_DIRECTORIES:
        if _clear_stale_path(root, name, directory=True):
            sys.stderr.write(f"pro_make_pipeline: cleared stale {name}\n")


def main() -> None:
    target = pro_inputs.load_target()
    data_root = pro_inputs.data_root()
    _reconcile_derived_state(target, data_root)
    template = _read(TEMPLATE)
    template_sha256 = hashlib.sha256(TEMPLATE.read_bytes()).hexdigest()
    prompt = _read(PROMPT).rstrip("\n")
    content_prompt = _read(CONTENT_PROMPT).rstrip("\n")
    if (
        template.count("__DATA_ROOT__") != 2
        or template.count("__TARGET_REPO__") != 1
        or template.count("__DERIVE_PROMPT__") != 1
        or template.count("__CONTENT_PROMPT__") != 1
        or template.count("__SPEC_SHA256__") != 1
        or prompt.count("__DATA_ROOT__") != 2
        or prompt.count("__TARGET_REPO__") != 1
        or content_prompt.count("__DATA_ROOT__") != 1
    ):
        raise RuntimeError("pipeline template markers are invalid")
    prompt = prompt.replace("__DATA_ROOT__", str(data_root))
    prompt = prompt.replace("__TARGET_REPO__", json.dumps(str(target)))
    prompt_block = "\n".join("      " + line for line in prompt.splitlines())
    content_prompt = content_prompt.replace("__DATA_ROOT__", str(data_root))
    content_prompt_block = "\n".join(
        "      " + line for line in content_prompt.splitlines()
    )
    rendered = template.replace("__TARGET_REPO__", json.dumps(str(target)))
    rendered = rendered.replace("__DATA_ROOT__", json.dumps(str(data_root)))
    rendered = rendered.replace("__DERIVE_PROMPT__", prompt_block)
    rendered = rendered.replace("__CONTENT_PROMPT__", content_prompt_block)
    rendered = rendered.replace("__SPEC_SHA256__", template_sha256)
    temporary = OUTPUT.with_name(OUTPUT.name + ".tmp")
    if OUTPUT.is_symlink() or temporary.is_symlink():
        raise RuntimeError("pipeline output path is unsafe")
    temporary.write_text(rendered, encoding="utf-8", newline="\n")
    os.chmod(temporary, 0o600)
    temporary.replace(OUTPUT)
    pro_inputs.atomic_write_text(
        data_root / pro_inputs.SPEC_STAMP_FILE,
        json.dumps(
            {
                "target": str(target),
                "template_sha256": template_sha256,
            },
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n",
    )
    print(str(OUTPUT))


if __name__ == "__main__":
    main()
