#!/bin/sh
set -eu

REPO=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

PYTHONPATH="$REPO/tools" python3 - "$TMP" <<'PY'
from pathlib import Path
import os
import sys

import inputs
import pro_agent_content
import render

root = Path(sys.argv[1]) / "render"
root.mkdir()
os.chdir(root)
Path("out").mkdir()
values = inputs.validate_inputs({"app_name": "Example App"})
if set(pro_agent_content.DESCRIPTION_HEADINGS) != set(inputs._LOCALE_ORDER):
    raise SystemExit("description heading locales differ from admitted locales")
render.render_copy(values)
descriptions = {
    locale: Path(f"out/copy/{locale}/description.txt").read_text(encoding="utf-8")
    for locale in values["locales"]
}
checks = {
    "valid_en": pro_agent_content._validate_copy(
        "copy/en/description.txt", descriptions["en"], values
    ),
    "valid_it": pro_agent_content._validate_copy(
        "copy/it/description.txt", descriptions["it"], values
    ),
    "italian_as_en": pro_agent_content._validate_copy(
        "copy/en/description.txt", descriptions["it"], values
    ),
    "english_as_it": pro_agent_content._validate_copy(
        "copy/it/description.txt", descriptions["en"], values
    ),
    "italian_as_unsupported": pro_agent_content._validate_copy(
        "copy/de/description.txt", descriptions["it"], values
    ),
}
expected = {
    "valid_en": None,
    "valid_it": None,
    "italian_as_en": "description_structure",
    "english_as_it": "description_structure",
    "italian_as_unsupported": "description_locale",
}
if checks != expected:
    raise SystemExit(f"description validation mismatch: {checks!r}")

# MARKER COVERAGE. Everything above is built from the shipped templates, which
# use U+2022 exclusively, so none of it can detect a regression in any other
# marker: deleting "-" from _AMBIGUOUS_BULLETS left this suite green. These
# cases drive _validate_copy directly, one per accepted marker, so removing
# any single marker fails here.
heading_en = pro_agent_content.DESCRIPTION_HEADINGS["en"]


def _swap_markers(text, marker):
    lines = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("\u2022"):
            lines.append(marker + stripped[1:])
        else:
            lines.append(line)
    return "\n".join(lines) + "\n"


def _numbered(text):
    lines = []
    index = 0
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("\u2022"):
            index += 1
            lines.append(f"{index}." + stripped[1:])
        else:
            lines.append(line)
    return "\n".join(lines) + "\n"


accepted_markers = {
    "u2022_bullet": "\u2022",
    "u2023_triangular_bullet": "\u2023",
    "u2043_hyphen_bullet": "\u2043",
    "u25aa_small_black_square": "\u25aa",
    "u25a0_black_square": "\u25a0",
    "u25cf_black_circle": "\u25cf",
    "u25e6_white_bullet": "\u25e6",
    "u2713_check": "\u2713",
    "u2714_heavy_check": "\u2714",
    "u2705_emoji_check": "\u2705",
    "hyphen": "-",
    "u2013_en_dash": "\u2013",
    "asterisk": "*",
    "plus": "+",
    "u00b7_middot": "\u00b7",
}
for _name, _marker in accepted_markers.items():
    _reason = pro_agent_content._validate_copy(
        "copy/en/description.txt", _swap_markers(descriptions["en"], _marker), values
    )
    if _reason is not None:
        raise SystemExit(f"accepted marker {_name} rejected: {_reason}")

if (
    pro_agent_content._validate_copy(
        "copy/en/description.txt", _numbered(descriptions["en"]), values
    )
    is not None
):
    raise SystemExit("ordered feature list rejected")

# A glyph needs no following space; that was true before the widening and has
# to stay true.
if (
    pro_agent_content._validate_copy(
        "copy/en/description.txt",
        _swap_markers(descriptions["en"], "\u2022").replace("\u2022 ", "\u2022"),
        values,
    )
    is not None
):
    raise SystemExit("glyph without a following space rejected")

# Markers deliberately left out of the set. Asserted so that widening the set
# again is a decision somebody makes on purpose rather than a side effect.
for _name, _marker in {
    "u2014_em_dash": "\u2014",
    "u2192_arrow": "\u2192",
    "u00bb_guillemet": "\u00bb",
}.items():
    if (
        pro_agent_content._validate_copy(
            "copy/en/description.txt", _swap_markers(descriptions["en"], _marker), values
        )
        != "description_structure"
    ):
        raise SystemExit(f"marker {_name} is outside the set but was accepted")

# STRUCTURE, NOT JUST MARKERS. A marker says "this line is an item", which is
# not the claim "this description has a feature list". Stray prose and an
# unrelated section must not supply a list nobody wrote.
_lines_en = descriptions["en"].splitlines()
_without_list = [
    line for line in _lines_en if pro_agent_content._bullet_payload(line) is None
]


def _with_list(items):
    out = []
    for line in _without_list:
        out.append(line)
        if line.strip() == heading_en:
            out.extend(items)
    return "\n".join(out) + "\n"


def _appended(items):
    return "\n".join(_without_list + [""] + items) + "\n"


structure_rejections = {
    "hyphen_prose_outside_the_list": _appended(
        [
            "- and it keeps working quietly in the background while you are online",
            "- because the details matter more than another settings screen does",
            "- so that the next step in front of you is always the obvious one",
        ]
    ),
    "unrelated_numbered_section": _appended(
        ["1. Privacy Policy", "2. Terms of Service", "3. Contact Support"]
    ),
    "bare_markers": _with_list(["- ", "- ", "- "]),
    "duplicate_items": _with_list(
        ["- One good thing", "- One good thing", "- One good thing"]
    ),
    "items_below_letter_floor": _with_list(["- 4K", "- HD", "- 5G"]),
    "too_few_items": _with_list(["- One good thing", "- Another good thing"]),
}
_phrase_only_admin_before_cta = []
for line in _without_list:
    if line.strip() == heading_en:
        _phrase_only_admin_before_cta.extend(
            [
                f"This sentence mentions {heading_en}, but it is not a heading.",
                "1. Privacy Policy",
                "2. Terms of Service",
                "3. Contact Support",
            ]
        )
    else:
        _phrase_only_admin_before_cta.append(line)
_phrase_only_admin_before_cta = (
    "\n".join(_phrase_only_admin_before_cta) + "\n"
)
_interleaved_prose = _with_list(
    [
        "- One good thing",
        "- Another good thing",
        "This explanatory sentence interrupts the list.",
        "- A third good thing",
    ]
)
structure_rejections.update(
    {
        "phrase_only_admin_before_closing_cta": _phrase_only_admin_before_cta,
        "prose_interleaved_after_list_starts": _interleaved_prose,
    }
)
for _name, _text in structure_rejections.items():
    _reason = pro_agent_content._validate_copy(
        "copy/en/description.txt", _text, values
    )
    if _reason != "description_structure":
        raise SystemExit(
            f"{_name}: expected description_structure, got {_reason!r}"
        )

# Positive control for the block above: the same builder with three real items
# has to validate, or those rejections prove nothing about structure.
if (
    pro_agent_content._validate_copy(
        "copy/en/description.txt",
        _with_list(
            ["- One good thing", "- Another good thing", "- A third good thing"]
        ),
        values,
    )
    is not None
):
    raise SystemExit("rebuilt feature list rejected: structure cases prove nothing")

# HEADING IDENTITY AND DISTANCE. The phrase inside a sentence is not a
# heading, and the prompt requires the heading and bullets but does not demand
# immediate adjacency. These direct cases reproduce the exact-head review's
# false positive and two false rejections.

# CLOSING-CTA ORDER. A support email before the standalone heading is a closing
# CTA before the description's feature section. It cannot be the required
# closing CTA, and the later list cannot supply valid structure.
_cta_before_heading = (
    "\n".join(
        line for line in _without_list if line.strip() != heading_en
    )
    + "\n"
    + heading_en
    + "\n"
    + "\n".join(
        line for line in _lines_en if pro_agent_content._bullet_payload(line)
    )
    + "\n"
)
_reason = pro_agent_content._validate_copy(
    "copy/en/description.txt", _cta_before_heading, values
)
if _reason != "description_structure":
    raise SystemExit(
        f"cta_before_heading: expected description_structure, got {_reason!r}"
    )
_phrase_only_admin = "\n".join(
    (
        f"This sentence mentions {heading_en}, but it is not a heading."
        if line.strip() == heading_en
        else line
    )
    for line in _without_list
) + "\n\n1. Privacy Policy\n2. Terms of Service\n3. Contact Support\n"
_intro_before_list = descriptions["en"].replace(
    heading_en + "\n",
    heading_en + "\nHere are three grounded highlights from Example App:\n",
    1,
)
_earlier_phrase = (
    f"This opening mentions {heading_en} before the feature heading.\n"
    + descriptions["en"]
)
for _name, _text, _expected in (
    ("phrase_only_admin", _phrase_only_admin, "description_structure"),
    ("intro_before_list", _intro_before_list, None),
    ("earlier_phrase_before_heading", _earlier_phrase, None),
):
    _reason = pro_agent_content._validate_copy(
        "copy/en/description.txt", _text, values
    )
    if _reason != _expected:
        raise SystemExit(
            f"{_name}: expected {_expected!r}, got {_reason!r}"
        )
PY

# ENTRY PATH. Every case above calls _validate_copy directly, one level below
# its only production caller. A mutant that stopped inspect() acting on a
# validation reason would leave all of them green, so these cases drive
# inspect() and assert the observable it actually produces: an accepted file
# carries AGENT_SOURCE and keeps its payload, a rejected one carries
# FALLBACK_SOURCE, the reason code, and no payload.
mkdir -p "$TMP/prodata/content-agent/copy/en" "$TMP/entry"
APPKIT_PRO_DATA_DIR="$TMP/prodata" PYTHONPATH="$REPO/tools" python3 - "$TMP" <<'PY'
import os
import sys
from pathlib import Path

import inputs
import pro_agent_content
import render

tmp = Path(sys.argv[1])
values = inputs.validate_inputs({"app_name": "Example App"})
os.chdir(tmp / "entry")
Path("out").mkdir(exist_ok=True)
render.render_copy(values)
valid_en = Path("out/copy/en/description.txt").read_text(encoding="utf-8")

key = "copy/en/description.txt"
target = Path(os.environ["APPKIT_PRO_DATA_DIR"]) / "content-agent" / key
lines = valid_en.splitlines()
without_list = [
    line for line in lines if pro_agent_content._bullet_payload(line) is None
]


def _swap(marker):
    out = []
    for line in lines:
        stripped = line.lstrip()
        out.append(marker + stripped[1:] if stripped.startswith("\u2022") else line)
    return "\n".join(out) + "\n"


def _check(label, text, want_source, want_reason):
    target.write_text(text, encoding="utf-8")
    content = pro_agent_content.inspect(values)
    source = content.provenance.get(key)
    reason = content.reasons.get(key, "")
    if source != want_source or reason != want_reason:
        raise SystemExit(
            f"entry path {label}: provenance={source!r} reason={reason!r}, "
            f"wanted {want_source!r} / {want_reason!r}"
        )
    if want_source == pro_agent_content.AGENT_SOURCE and key not in content.payloads:
        raise SystemExit(f"entry path {label}: accepted but the payload was dropped")
    if want_source == pro_agent_content.FALLBACK_SOURCE and key in content.payloads:
        raise SystemExit(f"entry path {label}: rejected but the payload was retained")


_check("shipped U+2022 list", valid_en, pro_agent_content.AGENT_SOURCE, "")
_check("hyphen list", _swap("-"), pro_agent_content.AGENT_SOURCE, "")
_check("checkmark list", _swap("\u2713"), pro_agent_content.AGENT_SOURCE, "")
_check(
    "hyphen prose outside the list",
    "\n".join(
        without_list
        + [
            "",
            "- and it keeps working quietly in the background while you are online",
            "- because the details matter more than another settings screen does",
            "- so that the next step in front of you is always the obvious one",
        ]
    )
    + "\n",
    pro_agent_content.FALLBACK_SOURCE,
    "description_structure",
)
# An excluded marker reaches the validator and comes back as structure. Arrow,
# not em dash: _safe_text:122 rejects U+2014 anywhere in agent content, so an
# em-dash description is refused a layer above and the marker set never sees
# it. Both layers are asserted so neither can quietly stop working.
_check(
    "arrow outside the marker set",
    _swap("\u2192"),
    pro_agent_content.FALLBACK_SOURCE,
    "description_structure",
)
_check(
    "em dash refused upstream of the validator",
    _swap("\u2014"),
    pro_agent_content.FALLBACK_SOURCE,
    "forbidden_character",
)

# Same heading cases through inspect(), the production entry path.
heading = pro_agent_content.DESCRIPTION_HEADINGS["en"]
phrase_only_admin = "\n".join(
    (
        f"This sentence mentions {heading}, but it is not a heading."
        if line.strip() == heading
        else line
    )
    for line in without_list
) + "\n\n1. Privacy Policy\n2. Terms of Service\n3. Contact Support\n"
intro_before_list = valid_en.replace(
    heading + "\n",
    heading + "\nHere are three grounded highlights from Example App:\n",
    1,
)
earlier_phrase = (
    f"This opening mentions {heading} before the feature heading.\n" + valid_en
)
_check(
    "heading phrase in prose plus administrative list",
    phrase_only_admin,
    pro_agent_content.FALLBACK_SOURCE,
    "description_structure",
)
_check(
    "intro between standalone heading and list",
    intro_before_list,
    pro_agent_content.AGENT_SOURCE,
    "",
)
_check(
    "earlier phrase before standalone heading",
    earlier_phrase,
    pro_agent_content.AGENT_SOURCE,
    "",
)

# These two cases kill the identity and list-end mutations independently of
# the closing-CTA boundary: the faux heading and the interrupted list both
# occur before the support email.
phrase_only_admin_before_cta = []
for line in without_list:
    if line.strip() == heading:
        phrase_only_admin_before_cta.extend(
            [
                f"This sentence mentions {heading}, but it is not a heading.",
                "1. Privacy Policy",
                "2. Terms of Service",
                "3. Contact Support",
            ]
        )
    else:
        phrase_only_admin_before_cta.append(line)
phrase_only_admin_before_cta = "\n".join(phrase_only_admin_before_cta) + "\n"
interleaved_prose = []
for line in without_list:
    interleaved_prose.append(line)
    if line.strip() == heading:
        interleaved_prose.extend(
            [
                "- One good thing",
                "- Another good thing",
                "This explanatory sentence interrupts the list.",
                "- A third good thing",
            ]
        )
interleaved_prose = "\n".join(interleaved_prose) + "\n"
_check(
    "heading phrase plus admin list before closing CTA",
    phrase_only_admin_before_cta,
    pro_agent_content.FALLBACK_SOURCE,
    "description_structure",
)
_check(
    "prose interrupts the feature list",
    interleaved_prose,
    pro_agent_content.FALLBACK_SOURCE,
    "description_structure",
)

cta_before_heading = (
    "\n".join(line for line in without_list if line.strip() != heading)
    + "\n"
    + heading
    + "\n"
    + "\n".join(line for line in lines if pro_agent_content._bullet_payload(line))
    + "\n"
)
_check(
    "closing CTA before standalone heading",
    cta_before_heading,
    pro_agent_content.FALLBACK_SOURCE,
    "description_structure",
)
PY

mkdir -p "$TMP/bin" "$TMP/data/kit"
cat > "$TMP/bin/curl" <<'SH'
#!/bin/sh
printf '%s\n' "$@" > "$MOCK_CURL_ARGS"
cat > "$MOCK_CURL_STDIN"
printf '%s' 200
SH
chmod +x "$TMP/bin/curl"
printf 'x' > "$TMP/data/kit/launch-kit.zip"
export MOCK_CURL_ARGS="$TMP/curl.args"
export MOCK_CURL_STDIN="$TMP/curl.stdin"

run_notify() {
  PATH="$TMP/bin:$PATH" \
    APPKIT_PRO_DATA_DIR="$TMP/data" \
    TELEGRAM_BOT_TOKEN='123456:test_token' \
    TELEGRAM_CHAT_ID='-1001234567890' \
    GITMOOT_TRIGGER_UPSTREAM_RUN_ID='run-test-123' \
    sh "$REPO/tools/notify_pro.sh" > "$TMP/notify.stdout" 2> "$TMP/notify.stderr"
  grep -F '"decision":"approved"' "$TMP/notify.stdout" >/dev/null
}

assert_unavailable() {
  grep -F 'content provenance unavailable' "$MOCK_CURL_ARGS" >/dev/null || {
    printf '%s\n' 'unknown provenance was reported as a clean notification' >&2
    exit 1
  }
}

cat > "$TMP/data/kit/manifest.json" <<'JSON'
{"content_provenance":{"copy/en/description.txt":"agent","copy/it/description.txt":"agent"}}
JSON
run_notify
if grep -F 'content fallbacks:' "$MOCK_CURL_ARGS" >/dev/null; then
  printf '%s\n' 'clean notification was incorrectly marked as fallback' >&2
  exit 1
fi
if grep -F 'content provenance unavailable' "$MOCK_CURL_ARGS" >/dev/null; then
  printf '%s\n' 'clean notification was incorrectly marked as unknown provenance' >&2
  exit 1
fi

cat > "$TMP/data/kit/manifest.json" <<'JSON'
{"content_provenance":{"copy/en/description.txt":"agent","copy/it/description.txt":"deterministic-fallback"}}
JSON
run_notify
if grep -F 'content provenance unavailable' "$MOCK_CURL_ARGS" >/dev/null; then
  printf '%s\n' 'fallback notification was incorrectly marked as unknown provenance' >&2
  exit 1
fi
grep -F 'content fallbacks: 1' "$MOCK_CURL_ARGS" >/dev/null || {
  printf '%s\n' 'fallback notification omitted its visible count' >&2
  exit 1
}

printf '%s\n' '{}' > "$TMP/data/kit/manifest.json"
run_notify
assert_unavailable

rm "$TMP/data/kit/manifest.json"
run_notify
assert_unavailable

printf '%s\n' '{"content_provenance":{"copy/en/description.txt":"agent"}}' > "$TMP/data/kit/manifest-target.json"
ln -s manifest-target.json "$TMP/data/kit/manifest.json"
run_notify
assert_unavailable

rm "$TMP/data/kit/manifest.json"
printf '%s\n' 'not-json' > "$TMP/data/kit/manifest.json"
run_notify
assert_unavailable
if grep -F 'Traceback' "$TMP/notify.stderr" >/dev/null; then
  printf '%s\n' 'malformed provenance printed a Python traceback' >&2
  exit 1
fi

printf '%s\n' 'content_validation: valid descriptions accepted, every accepted marker asserted, excluded markers held out, stray prose and unrelated sections rejected as structure, inspect() entry path asserted for provenance/reason/payload, malformed locales rejected, fallbacks surfaced'
