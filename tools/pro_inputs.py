"""Fixed-side-channel inputs for the personal appkit-pro pipeline."""

from __future__ import annotations

import json
import os
import re
import unicodedata
from pathlib import Path

from inputs import FIELD_LIMITS, InputError, validate_inputs


DATA_ROOT = Path("/root/appkit-pro-data")
TARGET_FILE = "target"
ORDER_FILE = "order.yaml"
REPORT_FILE = "capture-report.json"
RATIONALE_FILE = "rationale.md"
PRO_APP_NAME_DEFAULT = "My App"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ProDataError(RuntimeError):
    pass


def _safe_regular(path: Path, maximum: int) -> str:
    if not path.is_file() or path.is_symlink():
        raise ProDataError("required side-channel file missing or unsafe")
    try:
        if path.stat().st_size > maximum:
            raise ProDataError("side-channel file exceeds size limit")
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise ProDataError("side-channel file unreadable") from error


def require_data_root() -> Path:
    try:
        DATA_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    except OSError as error:
        raise ProDataError("personal data directory unavailable") from error
    if not DATA_ROOT.is_dir() or DATA_ROOT.is_symlink():
        raise ProDataError("personal data directory unsafe")
    return DATA_ROOT


def load_target() -> Path:
    text = _safe_regular(DATA_ROOT / TARGET_FILE, 4096)
    lines = text.splitlines()
    if len(lines) != 1 or not lines[0].strip():
        raise ProDataError("target must contain exactly one path line")
    candidate = Path(lines[0].strip())
    if not candidate.is_absolute():
        raise ProDataError("target path must be absolute")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as error:
        raise ProDataError("target repository is unavailable") from error
    if resolved == Path("/") or not resolved.is_dir() or resolved.is_symlink():
        raise ProDataError("target repository path is unsafe")
    try:
        resolved.relative_to(DATA_ROOT.resolve(strict=False))
    except ValueError:
        pass
    else:
        raise ProDataError("target repository overlaps personal output data")
    return resolved


def _parse_scalar(raw: str) -> str:
    value = raw.strip()
    if not value:
        return ""
    if value.startswith('"'):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as error:
            raise ProDataError("order contains invalid quoted scalar") from error
        if not isinstance(parsed, str):
            raise ProDataError("order values must be strings")
        return parsed
    if value.startswith("'"):
        if len(value) < 2 or not value.endswith("'"):
            raise ProDataError("order contains invalid quoted scalar")
        return value[1:-1].replace("''", "'")
    if value[0] in "[{&*!>|%@`":
        raise ProDataError("order contains unsupported YAML syntax")
    return value


def parse_order(text: str) -> dict[str, object]:
    source: dict[str, object] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if raw_line[:1].isspace() or ":" not in line:
            raise ProDataError("order must be a flat string mapping")
        key, raw_value = line.split(":", 1)
        key = key.strip()
        if key not in FIELD_LIMITS:
            raise ProDataError("order contains an unknown key")
        if key in source:
            raise ProDataError("order contains a duplicate key")
        source[key] = _parse_scalar(raw_value)
    try:
        return validate_inputs(source, app_name_default=PRO_APP_NAME_DEFAULT)
    except InputError as error:
        raise ProDataError(f"order validation failed:{error.field}:{error.code}") from error


def load_order() -> dict[str, object]:
    return parse_order(_safe_regular(DATA_ROOT / ORDER_FILE, 16 * 1024))


def require_rationale() -> None:
    _safe_regular(DATA_ROOT / RATIONALE_FILE, 64 * 1024)


def load_capture_report() -> dict[str, object]:
    text = _safe_regular(DATA_ROOT / REPORT_FILE, 64 * 1024)
    try:
        report = json.loads(text)
    except json.JSONDecodeError as error:
        raise ProDataError("capture report is malformed") from error
    if not isinstance(report, dict):
        raise ProDataError("capture report is malformed")
    ladder = report.get("ladder")
    source = report.get("source")
    warnings = report.get("warnings")
    shots = report.get("shots")
    if (
        ladder not in ("exported", "web-capture", "synthetic")
        or not isinstance(source, str)
        or len(source) > 4096
        or not isinstance(warnings, list)
        or len(warnings) > 32
        or any(not isinstance(item, str) for item in warnings)
        or any(len(item) > 512 for item in warnings)
        or not isinstance(shots, list)
        or not 1 <= len(shots) <= 3
    ):
        raise ProDataError("capture report is malformed")
    for item in shots:
        if (
            not isinstance(item, dict)
            or sorted(item) != ["file", "height", "sha256", "width"]
            or not isinstance(item["file"], str)
            or Path(item["file"]).name != item["file"]
            or not isinstance(item["sha256"], str)
            or not _SHA256_RE.fullmatch(item["sha256"])
            or not isinstance(item["width"], int)
            or not isinstance(item["height"], int)
            or item["width"] <= 0
            or item["height"] <= 0
        ):
            raise ProDataError("capture report shot is malformed")
    for text_value in [source, *warnings]:
        if unicodedata.normalize("NFC", text_value) != text_value:
            raise ProDataError("capture report contains unsafe text")
        if any(unicodedata.category(char).startswith("C") for char in text_value):
            raise ProDataError("capture report contains unsafe text")
    return report


def atomic_write_text(path: Path, content: str) -> None:
    require_data_root()
    temporary = path.with_name(path.name + ".tmp")
    try:
        if temporary.exists() or temporary.is_symlink():
            temporary.unlink()
        temporary.write_text(content, encoding="utf-8", newline="\n")
        os.chmod(temporary, 0o600)
        temporary.replace(path)
    except OSError as error:
        raise ProDataError("side-channel write failed") from error
