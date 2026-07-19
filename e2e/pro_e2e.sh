#!/bin/sh
set -eu

REPO=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
FIXTURE_ROOT=/root/appkit-pro-fixture
DATA_ROOT=/root/appkit-pro-data
HOME_ROOT=/root/appkit-pro-e2e-home
FULL="$FIXTURE_ROOT/fixture-full"
BARE="$FIXTURE_ROOT/fixture-bare"

fail() {
  printf '%s\n' "pro_e2e: $*" >&2
  exit 1
}

case "$FIXTURE_ROOT:$DATA_ROOT:$HOME_ROOT" in
  /root/appkit-pro-fixture:/root/appkit-pro-data:/root/appkit-pro-e2e-home) ;;
  *) fail "unsafe fixed roots" ;;
esac

rm -rf "$FIXTURE_ROOT" "$HOME_ROOT"
mkdir -p "$FIXTURE_ROOT" || fail "cannot create $FIXTURE_ROOT (the coordinator needs a writable /root fixture grant)"
mkdir -p "$FULL/docs/store/screenshots/en" "$FULL/lib/theme" "$BARE/docs/store/screenshots/en" "$BARE/lib/theme" "$DATA_ROOT"

make_fixture_files() {
  fixture=$1
  cat > "$fixture/pubspec.yaml" <<'EOF'
name: fixture_app
description: A fixture for the personal launch-kit pipeline.
EOF
  cat > "$fixture/README.md" <<'EOF'
# Fixture App

Tagline: Make every day feel organized.

- Plan with clarity
- Stay in the moment
- See progress at a glance
EOF
  cat > "$fixture/lib/theme/colors.dart" <<'EOF'
const primaryBrandColor = Color(0xFF1FA2FF); // #1FA2FF
EOF
}

make_fixture_files "$FULL"
make_fixture_files "$BARE"
: > "$BARE/docs/store/screenshots/en/.gitkeep"

python3 - "$FULL/docs/store/screenshots/en" <<'PY'
from pathlib import Path
import sys
from PIL import Image, ImageDraw

root = Path(sys.argv[1])
for index, base in enumerate(((31, 162, 255), (20, 184, 166)), start=1):
    image = Image.new("RGB", (800, 1600), (247, 248, 250))
    draw = ImageDraw.Draw(image)
    for y in range(0, 1600, 8):
        shade = tuple(max(0, min(255, channel + ((y // 8) % 17) * 2 - 16)) for channel in base)
        draw.rectangle((0, y, 799, min(1599, y + 7)), fill=shade)
    for row in range(7):
        top = 180 + row * 170
        draw.rounded_rectangle((72, top, 728, top + 116), radius=28, fill=(255, 255, 255), outline=(229, 231, 235), width=3)
        draw.rounded_rectangle((104, top + 30, 104 + 260 + row * 23, top + 52), radius=11, fill=(17, 24, 39))
        draw.rounded_rectangle((104, top + 72, 104 + 420 - row * 19, top + 88), radius=8, fill=(107, 114, 128))
    image.save(root / f"fixture_{index}.png", format="PNG", optimize=True)
PY

for fixture in "$FULL" "$BARE"; do
  git -C "$fixture" init -q
  git -C "$fixture" config user.name appkit-pro-e2e
  git -C "$fixture" config user.email appkit-pro-e2e@example.invalid
  git -C "$fixture" add .
  git -C "$fixture" commit -qm fixture
done

mkdir -p "$HOME_ROOT"
gitmoot repo add gitmoot/appkit-demo --path "$REPO" --home "$HOME_ROOT" >/dev/null
gitmoot agent start appkit-deriver \
  --home "$HOME_ROOT" \
  --runtime codex \
  --repo gitmoot/appkit-demo \
  --path "$REPO" \
  --role implementer \
  --capability produce \
  --model gpt-5.6-sol \
  --policy workspace-write >/dev/null
gitmoot daemon start --home "$HOME_ROOT" --poll 1s >/dev/null
trap 'gitmoot daemon stop --home "$HOME_ROOT" >/dev/null 2>&1 || true' EXIT HUP INT TERM

add_pipeline() {
  add_log=$HOME_ROOT/pipeline-add.log
  if gitmoot pipeline add "$REPO/appkit-pro.yaml" --force --home "$HOME_ROOT" >"$add_log" 2>&1; then
    return
  fi
  if grep -q 'flag provided but not defined: -force' "$add_log"; then
    printf '%s\n' 'pro_e2e: CLI has no pipeline-add --force; retrying the upsert without it' >&2
    gitmoot pipeline add "$REPO/appkit-pro.yaml" --home "$HOME_ROOT"
    return
  fi
  cat "$add_log" >&2
  fail "pipeline add failed"
}

wait_run() {
  run_id=$1
  run_json=$2
  deadline=$(( $(date +%s) + 1800 ))
  while :; do
    gitmoot pipeline show "$run_id" --json --home "$HOME_ROOT" > "$run_json"
    state=$(python3 - "$run_json" <<'PY'
import json, sys
print(json.load(open(sys.argv[1], encoding="utf-8"))["state"])
PY
)
    case "$state" in
      succeeded) return ;;
      failed|blocked|cancelled)
        cat "$run_json" >&2
        fail "pipeline run $run_id ended $state"
        ;;
    esac
    [ "$(date +%s)" -lt "$deadline" ] || fail "pipeline run $run_id timed out"
    sleep 2
  done
}

materialize_kit() {
  run_json=$1
  context=$2
  python3 - "$run_json" "$context" <<'PY'
import json, sys

run = json.load(open(sys.argv[1], encoding="utf-8"))
by_id = {stage["id"]: stage for stage in run["stages"]}
stages = {}
for stage_id in ("compose-real", "content"):
    stage = by_id.get(stage_id)
    if not stage or stage.get("state") != "succeeded" or not isinstance(stage.get("summary"), str):
        raise SystemExit(f"missing successful {stage_id} summary")
    stages[stage_id] = {
        "id": stage_id,
        "state": "succeeded",
        "summary": stage["summary"],
        "summary_truncated": False,
    }
context = {"complete": True, "schema_version": 1, "stages": stages}
with open(sys.argv[2], "w", encoding="utf-8", newline="\n") as handle:
    json.dump(context, handle, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    handle.write("\n")
PY
  (
    cd "$REPO"
    GITMOOT_PIPELINE_UPSTREAM_CONTEXT_FILE="$context" python3 tools/pro_stage_kit.py > "$HOME_ROOT/materialize-result.json"
  )
  python3 - "$HOME_ROOT/materialize-result.json" <<'PY'
import json, sys
lines = open(sys.argv[1], encoding="utf-8").read().splitlines()
if len(lines) != 1 or json.loads(lines[0])["gitmoot_result"]["decision"] != "implemented":
    raise SystemExit("materialized kit did not implement")
PY
}

run_case() {
  expected=$1
  target=$2
  printf '%s\n' "$target" > "$DATA_ROOT/target"
  rm -f "$DATA_ROOT/order.yaml" "$DATA_ROOT/rationale.md" "$DATA_ROOT/capture-report.json"
  rm -rf "$DATA_ROOT/screens"
  python3 "$REPO/tools/pro_make_pipeline.py" >/dev/null
  add_pipeline
  run_id=$(gitmoot pipeline run appkit-pro --home "$HOME_ROOT")
  run_json="$HOME_ROOT/$expected-run.json"
  context="$HOME_ROOT/$expected-context.json"
  wait_run "$run_id" "$run_json"
  materialize_kit "$run_json" "$context"
  python3 - "$DATA_ROOT/capture-report.json" "$REPO/out/manifest.json" "$REPO/out/launch-kit.zip" "$expected" <<'PY'
import json, sys, zipfile

report = json.load(open(sys.argv[1], encoding="utf-8"))
manifest = json.load(open(sys.argv[2], encoding="utf-8"))
expected = sys.argv[4]
if report["ladder"] != expected:
    raise SystemExit(f"ladder={report['ladder']}, expected={expected}")
with zipfile.ZipFile(sys.argv[3]) as archive:
    names = set(archive.namelist())
    required = {"capture-report.json", "screenshots/en/shot_1.png", "README.md", "manifest.json"}
    if not required.issubset(names):
        raise SystemExit(f"kit zip missing {sorted(required - names)}")
    kit_report = json.loads(archive.read("capture-report.json"))
    readme = archive.read("README.md").decode("utf-8")
if kit_report != report:
    raise SystemExit("kit capture report differs from observed report")
if expected == "exported":
    if manifest.get("warnings") != [] or "Captured from " not in readme:
        raise SystemExit("exported provenance missing")
else:
    warning = "synthetic screens: no exported screenshots found and web capture unavailable/failed"
    if warning not in manifest.get("warnings", []) or "Synthesized deterministically" not in readme:
        raise SystemExit("synthetic warning/provenance missing")
PY
}

run_case exported "$FULL"
run_case synthetic "$BARE"

expose_log=$HOME_ROOT/expose-rejection.log
if gitmoot pipeline expose --schema "$REPO/schema.json" --home "$HOME_ROOT" appkit-pro >"$expose_log" 2>&1; then
  fail "appkit-pro unexpectedly exposed"
fi
grep -Eq 'template-free shell stage|not safe to expose|declares (reads|writes|network)' "$expose_log" || {
  cat "$expose_log" >&2
  fail "expose failed without the expected safety rejection"
}

rm -rf "$HOME_ROOT/public-a" "$HOME_ROOT/public-b"
sh "$REPO/scripts/demo-kit.sh" "$HOME_ROOT/public-a" >/dev/null
sh "$REPO/scripts/demo-kit.sh" "$HOME_ROOT/public-b" >/dev/null
cmp "$HOME_ROOT/public-a/kit/out/manifest.json" "$HOME_ROOT/public-b/kit/out/manifest.json"
cmp "$HOME_ROOT/public-a/kit/out/launch-kit.zip" "$HOME_ROOT/public-b/kit/out/launch-kit.zip"

printf '%s\n' 'pro_e2e: fixture-full exported, fixture-bare synthetic, expose rejected, public determinism matched'
