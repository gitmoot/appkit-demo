#!/bin/sh
# Local tangible-kit build for demos: runs the three stage scripts the same way
# the pipeline engine would (isolated dirs, upstream-context handoff) and leaves
# launch-kit.zip in <workdir>/kit/out/. Inputs: pre-set GITMOOT_INPUT_* env wins;
# otherwise a fixed demo preset is used. No network, no clock, repo-relative.
set -eu

WORKDIR="${1:?usage: scripts/demo-kit.sh <workdir>}"
TOOLS="$(cd "$(dirname "$0")/../tools" && pwd)"

: "${GITMOOT_INPUT_APP_NAME:=Waybread}"
: "${GITMOOT_INPUT_BRAND_COLOR:=#e0af68}"
: "${GITMOOT_INPUT_TAGLINE:=Your launch kit in one pipeline run.}"
: "${GITMOOT_INPUT_HEADLINE_1:=Ship the store page}"
: "${GITMOOT_INPUT_HEADLINE_2:=Frames and copy included}"
: "${GITMOOT_INPUT_HEADLINE_3:=Proof receipts built in}"
: "${GITMOOT_INPUT_LOCALES:=en,it}"
: "${GITMOOT_INPUT_SUPPORT_EMAIL:=support@waybread.dev}"
: "${GITMOOT_INPUT_DEVELOPER_ENTITY:=Gitmoot Demo Lab}"
export GITMOOT_INPUT_APP_NAME GITMOOT_INPUT_BRAND_COLOR GITMOOT_INPUT_TAGLINE \
  GITMOOT_INPUT_HEADLINE_1 GITMOOT_INPUT_HEADLINE_2 GITMOOT_INPUT_HEADLINE_3 \
  GITMOOT_INPUT_LOCALES GITMOOT_INPUT_SUPPORT_EMAIL GITMOOT_INPUT_DEVELOPER_ENTITY

mkdir -p "$WORKDIR/compose" "$WORKDIR/content" "$WORKDIR/kit"

run_stage() {
  # $1 = stage id; runs in its own dir, keeps only the last stdout line (the result)
  ( cd "$WORKDIR/$1" && python3 "$TOOLS/stage_$1.py" ) > "$WORKDIR/$1.result.json"
}

run_stage compose
run_stage content

python3 - "$WORKDIR" <<'PY'
import json, sys
workdir = sys.argv[1]
stages = {}
for stage in ("compose", "content"):
    with open(f"{workdir}/{stage}.result.json", encoding="utf-8") as fh:
        result = json.load(fh)["gitmoot_result"]
    if result["decision"] != "implemented":
        raise SystemExit(f"{stage} failed: {result['summary']}")
    stages[stage] = {"id": stage, "state": "succeeded",
                     "summary": result["summary"], "summary_truncated": False}
doc = {"schema_version": 1, "complete": True, "stages": stages}
with open(f"{workdir}/context.json", "w", encoding="utf-8") as fh:
    json.dump(doc, fh, separators=(",", ":"), sort_keys=True)
PY

( cd "$WORKDIR/kit" && GITMOOT_PIPELINE_UPSTREAM_CONTEXT_FILE="$WORKDIR/context.json" \
    python3 "$TOOLS/stage_kit.py" ) > "$WORKDIR/kit.result.json"

python3 - "$WORKDIR" <<'PY'
import json, sys
workdir = sys.argv[1]
with open(f"{workdir}/kit.result.json", encoding="utf-8") as fh:
    result = json.load(fh)["gitmoot_result"]
print("kit decision:", result["decision"])
print("kit summary:", result["summary"][:200])
if result["decision"] != "implemented":
    raise SystemExit(1)
PY
echo "launch kit: $WORKDIR/kit/out/launch-kit.zip"
