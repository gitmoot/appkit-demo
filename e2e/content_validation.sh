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

cat > "$TMP/data/kit/manifest.json" <<'JSON'
{"content_provenance":{"copy/en/description.txt":"agent","copy/it/description.txt":"agent"}}
JSON
run_notify
if grep -F 'content fallbacks:' "$MOCK_CURL_ARGS" >/dev/null; then
  printf '%s\n' 'clean notification was incorrectly marked as fallback' >&2
  exit 1
fi

cat > "$TMP/data/kit/manifest.json" <<'JSON'
{"content_provenance":{"copy/en/description.txt":"agent","copy/it/description.txt":"deterministic-fallback"}}
JSON
run_notify
grep -F 'content fallbacks: 1' "$MOCK_CURL_ARGS" >/dev/null || {
  printf '%s\n' 'fallback notification omitted its visible count' >&2
  exit 1
}

printf '%s\n' 'content_validation: valid descriptions accepted, malformed locales rejected, fallbacks surfaced'
