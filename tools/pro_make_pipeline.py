#!/usr/bin/env python3
"""Render the personal pipeline with its static target-repository read grant."""

from __future__ import annotations

import json
import os
from pathlib import Path

from pro_inputs import load_target


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
TEMPLATE = ROOT / "templates" / "appkit-pro.yaml.tmpl"
PROMPT = ROOT / "templates" / "derive-prompt.md"
OUTPUT = ROOT / "appkit-pro.yaml"


def _read(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        raise RuntimeError("pipeline template missing or unsafe")
    return path.read_text(encoding="utf-8")


def main() -> None:
    target = load_target()
    template = _read(TEMPLATE)
    prompt = _read(PROMPT).rstrip("\n")
    if template.count("__TARGET_REPO__") != 1 or template.count("__DERIVE_PROMPT__") != 1:
        raise RuntimeError("pipeline template markers are invalid")
    prompt_block = "\n".join("      " + line for line in prompt.splitlines())
    rendered = template.replace("__TARGET_REPO__", json.dumps(str(target)))
    rendered = rendered.replace("__DERIVE_PROMPT__", prompt_block)
    temporary = OUTPUT.with_name(OUTPUT.name + ".tmp")
    if OUTPUT.is_symlink() or temporary.is_symlink():
        raise RuntimeError("pipeline output path is unsafe")
    temporary.write_text(rendered, encoding="utf-8", newline="\n")
    os.chmod(temporary, 0o600)
    temporary.replace(OUTPUT)
    print(str(OUTPUT))


if __name__ == "__main__":
    main()
