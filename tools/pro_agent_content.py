"""Validate observed agent content and select deterministic per-file fallbacks."""

from __future__ import annotations

import re
import stat
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import pro_inputs
import render


AGENT_DIR = "content-agent"
AGENT_SOURCE = "agent"
FALLBACK_SOURCE = "deterministic-fallback"
MAX_FILE_BYTES = 64 * 1024

DESCRIPTION_HEADINGS = {
    "en": "WHY YOU'LL LOVE IT",
    "it": "PERCHÉ TI PIACERÀ",
}

# Bullet markers as shipped store copy actually writes them. The content
# prompt asks for `• `, but hyphen and en dash are the dominant App Store
# convention and `* `, middot, and `1. ` all appear in real listings.
# Accepting U+2022 alone repeated the original defect from the other side: a
# correct translated description was rejected for using the marker its own
# market writes. Which locale the text belongs to is still decided by the
# exact localized heading, never by the marker; the marker only has to say
# "this line is an item".
#
# Unambiguous glyphs stand alone (`•Text` was already accepted and stays
# accepted), and the checkmark family is here because a ✓-led feature list is
# a real App Store convention that this validator was rejecting. Characters
# that also occur as prose punctuation, and ordered numbers, require the
# following space that makes them a list marker rather than a hyphenated word
# ("-based") or a decimal ("1.5 million").
_BULLET_GLYPHS = "\u2022\u2023\u2043\u25aa\u25a0\u25cf\u25e6\u2713\u2714\u2705"
_AMBIGUOUS_BULLETS = "-\u2013*+\u00b7"
_BULLET_SPACES = (" ", "\t", "\u00a0")
_ORDERED_BULLET_RE = re.compile(r"^\d{1,2}[.)](?=[ \t\u00a0])")
MIN_BULLETS = 3
MIN_BULLET_LETTERS = 3


@dataclass(frozen=True)
class AgentContent:
    payloads: dict[str, bytes]
    provenance: dict[str, str]
    reasons: dict[str, str]


def expected_relpaths(values: dict[str, object]) -> list[str]:
    paths = ["legal/privacy.md", "legal/terms.md"]
    for locale in list(values["locales"]):
        for filename in render.COPY_FILES:
            paths.append(f"copy/{locale}/{filename}.txt")
    return sorted(paths)


def observed_output_keys(provenance: dict[str, str]) -> list[str]:
    return sorted(
        f"out/{relative}"
        for relative, source in provenance.items()
        if source == AGENT_SOURCE
    )


def observed_derived_keys(provenance: dict[str, str]) -> list[str]:
    keys: list[str] = []
    for name in ("privacy", "terms"):
        if provenance.get(f"legal/{name}.md") == AGENT_SOURCE:
            keys.append(f"out/landing/legal/{name}.html")
    return sorted(keys)


def verified_output_keys(
    all_output_keys: list[str], provenance: dict[str, str]
) -> list[str]:
    excluded = set(observed_output_keys(provenance))
    excluded.update(observed_derived_keys(provenance))
    return sorted(key for key in all_output_keys if key not in excluded)


def _safe_text(root: Path, relative: str) -> tuple[str | None, str]:
    path = root / relative
    current = root
    for part in Path(relative).parts[:-1]:
        current = current / part
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            return None, "missing"
        except OSError:
            return None, "unreadable"
        if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
            return None, "unsafe_parent"
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return None, "missing"
    except OSError:
        return None, "unreadable"
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        return None, "unsafe_type"
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return None, "oversized"
        data = path.read_bytes()
        text = data.decode("utf-8")
    except (OSError, UnicodeError):
        return None, "invalid_utf8"
    if not text.strip():
        return None, "empty"
    if unicodedata.normalize("NFC", text) != text:
        return None, "non_nfc"
    for char in text:
        if char != "\n" and unicodedata.category(char).startswith("C"):
            return None, "control_character"
    if "\r" in text or "\u2014" in text:
        return None, "forbidden_character"
    return text, ""


def _single_line(text: str) -> str | None:
    body = text[:-1] if text.endswith("\n") else text
    if "\n" in body or not body or body != body.strip():
        return None
    return body


def _valid_keywords(body: str) -> bool:
    if len(body) > 100:
        return False
    tokens = body.split(",")
    if not tokens or any(
        not token
        or token != token.strip()
        or any(char.isspace() for char in token)
        for token in tokens
    ):
        return False
    folded = [token.casefold() for token in tokens]
    return len(folded) == len(set(folded))


def _bullet_payload(line: str) -> str | None:
    """The text after a list marker, or None when the line is not an item."""

    stripped = line.lstrip()
    if not stripped:
        return None
    if stripped[0] in _BULLET_GLYPHS:
        return stripped[1:].strip()
    if stripped[0] in _AMBIGUOUS_BULLETS and stripped[1:2] in _BULLET_SPACES:
        return stripped[2:].strip()
    ordered = _ORDERED_BULLET_RE.match(stripped)
    if ordered is not None:
        return stripped[ordered.end() :].strip()
    return None


def _bullet_texts(lines: list[str]) -> list[str]:
    """Distinct bullet payloads that actually say something.

    Widening the marker set without this would loosen the guard rather than
    correct it: three bare `- ` lines, or `* X` repeated, satisfy a plain
    marker count while saying nothing. Requiring distinct payloads with real
    letters keeps the widening from trading one silent-acceptance defect for
    another.
    """

    seen: dict[str, None] = {}
    for line in lines:
        payload = _bullet_payload(line)
        if payload is None:
            continue
        if sum(character.isalpha() for character in payload) < MIN_BULLET_LETTERS:
            continue
        seen.setdefault(payload.casefold(), None)
    return list(seen)


def _feature_bullets(
    lines: list[str], heading: str, support_email: str
) -> list[str]:
    """Distinct items in the list a standalone localized heading introduces.

    A heading phrase inside prose is not a heading: accepting it let an
    unrelated numbered section supply a feature list nobody wrote. Match the
    normalized line exactly, then allow the hook's introductory prose before
    the list begins; content-prompt.md requires the heading and bullets but
    does not require immediate adjacency. The required support email marks
    the closing CTA, so a list found after it cannot supply the feature list.
    Once the list starts, the first non-item ends it.

    Structure still cannot distinguish an administrative list written under a
    real standalone heading from feature bullets. That needs the text's
    meaning, not its shape.
    """

    start = None
    for index, line in enumerate(lines):
        if line.strip() == heading:
            start = index + 1
            break
    if start is None:
        return []
    run: list[str] = []
    started = False
    for line in lines[start:]:
        if support_email in line:
            break
        if not line.strip():
            continue
        if _bullet_payload(line) is None:
            if started:
                break
            continue
        started = True
        run.append(line)
    return _bullet_texts(run)


def _validate_copy(
    relative: str, text: str, values: dict[str, object]
) -> str | None:
    filename = Path(relative).stem
    if filename in {
        "name",
        "subtitle",
        "keywords",
        "promotional_text",
        "release_notes",
    }:
        body = _single_line(text)
        if body is None:
            return "not_single_line"
        limits = {
            "name": 30,
            "subtitle": 30,
            "keywords": 100,
            "promotional_text": 170,
            "release_notes": 4000,
        }
        if len(body) > limits[filename]:
            return "field_limit"
        if filename == "name":
            expected = str(values["app_name"])[:30].rstrip()
            if body != expected:
                return "name_mismatch"
        if filename == "keywords" and not _valid_keywords(body):
            return "keywords_invalid"
        return None
    if filename != "description":
        return "unexpected_file"
    body = text[:-1] if text.endswith("\n") else text
    if not body.strip() or len(body) > 4000:
        return "field_limit"
    required = [
        str(values["app_name"]),
        str(values["tagline"]),
        str(values["support_email"]),
    ]
    if any(value not in body for value in required):
        return "grounding_missing"
    locale = Path(relative).parts[1]
    heading = DESCRIPTION_HEADINGS.get(locale)
    if heading is None:
        return "description_locale"
    if len(
        _feature_bullets(
            body.splitlines(), heading, str(values["support_email"])
        )
    ) < MIN_BULLETS:
        return "description_structure"
    return None


def _validate_legal(text: str, values: dict[str, object]) -> str | None:
    body = text[:-1] if text.endswith("\n") else text
    if len(body) > 32 * 1024 or not body.strip():
        return "field_limit"
    required = (
        "1 January 2026",
        str(values["app_name"]),
        str(values["developer_entity"]),
        str(values["support_email"]),
    )
    if any(value not in body for value in required):
        return "grounding_missing"
    return None


def inspect(values: dict[str, object]) -> AgentContent:
    root = pro_inputs.data_root() / AGENT_DIR
    expected = expected_relpaths(values)
    payloads: dict[str, bytes] = {}
    provenance: dict[str, str] = {}
    reasons: dict[str, str] = {}
    try:
        root_mode = root.lstat().st_mode
    except FileNotFoundError:
        root_reason = "root_missing"
    except OSError:
        root_reason = "root_unreadable"
    else:
        root_reason = (
            "root_unsafe"
            if stat.S_ISLNK(root_mode) or not stat.S_ISDIR(root_mode)
            else ""
        )

    for relative in expected:
        if root_reason:
            provenance[relative] = FALLBACK_SOURCE
            reasons[relative] = root_reason
            continue
        text, reason = _safe_text(root, relative)
        if text is not None:
            reason = (
                _validate_legal(text, values)
                if relative.startswith("legal/")
                else _validate_copy(relative, text, values)
            ) or ""
        if text is None or reason:
            provenance[relative] = FALLBACK_SOURCE
            reasons[relative] = reason or "invalid"
            continue
        payloads[relative] = text.encode("utf-8")
        provenance[relative] = AGENT_SOURCE

    return AgentContent(
        payloads={key: payloads[key] for key in sorted(payloads)},
        provenance={key: provenance[key] for key in sorted(provenance)},
        reasons={key: reasons[key] for key in sorted(reasons)},
    )
