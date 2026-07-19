"""Bounded, deterministic service-input handling for every pipeline stage."""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import unicodedata
from collections.abc import Mapping


FIELD_LIMITS = {
    "app_name": 60,
    "brand_color": 7,
    "developer_entity": 80,
    "headline_1": 60,
    "headline_2": 60,
    "headline_3": 60,
    "locales": 16,
    "support_email": 80,
    "tagline": 80,
}

DEFAULTS = {
    "brand_color": "#6c5ce7",
    "developer_entity": "Independent Developer",
    "headline_1": "Made for every day",
    "headline_2": "Simple. Fast. Focused.",
    "headline_3": "Ready when you are",
    "locales": "en,it",
    "support_email": "support@example.com",
    "tagline": "A better way to get things done.",
}

_BRAND_RE = re.compile(r"^#[0-9a-f]{6}$")
_EMAIL_RE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._%+\-]{0,63}@"
    r"[A-Za-z0-9](?:[A-Za-z0-9\-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9\-]{0,61}[A-Za-z0-9])?)+$"
)
_LOCALE_ORDER = ("en", "it")
_MISSING = object()


class InputError(ValueError):
    """A value-free input error safe to report in a stage result."""

    def __init__(self, field: str, code: str):
        super().__init__(f"{field}: {code}")
        self.field = field
        self.code = code


def _reject_unsafe_unicode(field: str, value: str) -> None:
    if unicodedata.normalize("NFC", value) != value:
        raise InputError(field, "non_nfc")
    for char in value:
        if unicodedata.category(char).startswith("C"):
            raise InputError(field, "unsafe_unicode")


def _read_string(
    field: str,
    raw: object = _MISSING,
    app_name_default: str | None = None,
) -> str:
    if raw is _MISSING:
        if field == "app_name":
            if app_name_default is None:
                raise InputError(field, "required")
            raw = app_name_default
        else:
            raw = DEFAULTS[field]
    if not isinstance(raw, str):
        raise InputError(field, "type")
    value = raw.strip()
    if not value:
        if field == "app_name":
            if app_name_default is None:
                raise InputError(field, "required")
            value = app_name_default
        else:
            value = DEFAULTS[field]
    if len(value) > FIELD_LIMITS[field]:
        raise InputError(field, "too_long")
    _reject_unsafe_unicode(field, value)
    return value


def validate_inputs(
    source: Mapping[str, object],
    *,
    app_name_default: str | None = None,
) -> dict[str, object]:
    """Validate a plain mapping with the same rules used by service inputs."""

    if any(key not in FIELD_LIMITS for key in source):
        raise InputError("inputs", "unknown_field")
    values = {
        field: _read_string(
            field,
            source[field] if field in source else _MISSING,
            app_name_default,
        )
        for field in sorted(FIELD_LIMITS)
    }

    brand_color = str(values["brand_color"]).lower()
    if not _BRAND_RE.fullmatch(brand_color):
        raise InputError("brand_color", "invalid")
    values["brand_color"] = brand_color

    locale_text = str(values["locales"])
    requested = locale_text.split(",")
    if (
        not requested
        or any(locale not in _LOCALE_ORDER for locale in requested)
        or len(requested) != len(set(requested))
    ):
        raise InputError("locales", "invalid")
    values["locales"] = [
        locale for locale in _LOCALE_ORDER if locale in requested
    ]

    email = str(values["support_email"])
    if not email.isascii() or not _EMAIL_RE.fullmatch(email):
        raise InputError("support_email", "invalid")

    return values


def load_inputs() -> dict[str, object]:
    """Read the fixed GITMOOT_INPUT_* surface, preserving public behavior."""

    source: dict[str, object] = {}
    for field in sorted(FIELD_LIMITS):
        raw = os.environ.get("GITMOOT_INPUT_" + field.upper())
        if raw is not None:
            source[field] = raw
    return validate_inputs(source)


def canonical_inputs_json(values: dict[str, object]) -> str:
    return json.dumps(
        values, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )


def input_sha256(values: dict[str, object]) -> str:
    return hashlib.sha256(canonical_inputs_json(values).encode("utf-8")).hexdigest()


def escape_html(value: object) -> str:
    return html.escape(str(value), quote=True)
