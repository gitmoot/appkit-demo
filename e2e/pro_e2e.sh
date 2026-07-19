#!/bin/sh
set -eu

REPO=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
FIXTURE_ROOT=/root/appkit-pro-fixture
DATA_ROOT=/root/appkit-pro-e2e-data
LIVE_DATA_ROOT=/root/appkit-pro-data
HOME_ROOT=/root/appkit-pro-e2e-home
FULL="$FIXTURE_ROOT/fixture-full"
BARE="$FIXTURE_ROOT/fixture-bare"

fail() {
  printf '%s\n' "pro_e2e: $*" >&2
  exit 1
}

case "$FIXTURE_ROOT:$DATA_ROOT:$LIVE_DATA_ROOT:$HOME_ROOT" in
  /root/appkit-pro-fixture:/root/appkit-pro-e2e-data:/root/appkit-pro-data:/root/appkit-pro-e2e-home) ;;
  *) fail "unsafe fixed roots" ;;
esac

snapshot_live_root() {
  python3 - "$LIVE_DATA_ROOT" <<'PY'
from pathlib import Path
import hashlib, json, os, stat, sys

root = Path(sys.argv[1])
records = []
if not root.exists() and not root.is_symlink():
    records.append({"missing": True})
else:
    for path in [root, *sorted(root.rglob("*"), key=lambda item: item.as_posix())]:
        info = path.lstat()
        record = {
            "mode": stat.S_IFMT(info.st_mode) | stat.S_IMODE(info.st_mode),
            "mtime_ns": info.st_mtime_ns,
            "path": "." if path == root else path.relative_to(root).as_posix(),
            "size": info.st_size,
        }
        if stat.S_ISREG(info.st_mode):
            record["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        elif stat.S_ISLNK(info.st_mode):
            record["target"] = os.readlink(path)
        records.append(record)
payload = json.dumps(records, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
print(hashlib.sha256(payload.encode("utf-8")).hexdigest())
PY
}

live_before=$(snapshot_live_root)
export APPKIT_PRO_DATA_DIR=$DATA_ROOT

require_writable_e2e_root() {
  root=$1
  [ ! -L "$root" ] || fail "$root is a symlink"
  mkdir -p "$root" || fail "cannot create $root"
  probe=$root/.appkit-pro-e2e-write-probe.$$
  touch "$probe" || fail "$root is not writable"
  rm -f "$probe"
}

require_writable_e2e_root "$FIXTURE_ROOT"
require_writable_e2e_root "$HOME_ROOT"
require_writable_e2e_root "$DATA_ROOT"
rm -rf "$FIXTURE_ROOT" "$HOME_ROOT" "$DATA_ROOT"
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
      succeeded)
        # Re-read after success so persistence is checked only after the daemon
        # has settled the terminal run state.
        sleep 1
        gitmoot pipeline show "$run_id" --json --home "$HOME_ROOT" > "$run_json"
        settled=$(python3 - "$run_json" <<'PY'
import json, sys
print(json.load(open(sys.argv[1], encoding="utf-8"))["state"])
PY
)
        [ "$settled" = succeeded ] || fail "pipeline run $run_id did not remain settled"
        return
        ;;
      failed|blocked|cancelled)
        cat "$run_json" >&2
        fail "pipeline run $run_id ended $state"
        ;;
    esac
    [ "$(date +%s)" -lt "$deadline" ] || fail "pipeline run $run_id timed out"
    sleep 2
  done
}

verify_persisted_kit() {
  run_json=$1
  expected=$2
  digest_file=$3
  python3 - "$run_json" "$DATA_ROOT" "$expected" "$digest_file" <<'PY'
import hashlib, json, os, stat, sys, zipfile
from pathlib import Path

run = json.load(open(sys.argv[1], encoding="utf-8"))
data_root = Path(sys.argv[2])
expected = sys.argv[3]
digest_file = Path(sys.argv[4])
kit = data_root / "kit"
by_id = {stage["id"]: stage for stage in run["stages"]}
stage = by_id.get("kit")
if not stage or stage.get("state") != "succeeded" or not isinstance(stage.get("summary"), str):
    raise SystemExit("missing successful kit summary")
summary = json.loads(stage["summary"])
persisted = summary.get("persisted")
if not isinstance(persisted, dict) or sorted(persisted) != ["path", "zip_sha256"] or persisted.get("path") != str(kit):
    raise SystemExit("kit summary has an invalid persisted destination")
expected_zip_sha = persisted["zip_sha256"]
if not isinstance(expected_zip_sha, str) or len(expected_zip_sha) != 64:
    raise SystemExit("kit summary has an invalid persisted zip digest")
if summary.get("digests", {}).get("out/launch-kit.zip") != expected_zip_sha:
    raise SystemExit("persisted digest differs from the in-worktree zip digest")

zip_path = kit / "launch-kit.zip"
if not zip_path.is_file() or zip_path.is_symlink():
    raise SystemExit("persisted launch-kit.zip is missing or unsafe")
actual_zip_sha = hashlib.sha256(zip_path.read_bytes()).hexdigest()
if actual_zip_sha != expected_zip_sha:
    raise SystemExit("persisted zip does not match the run result digest")

manifest_path = kit / "manifest.json"
if not manifest_path.is_file() or manifest_path.is_symlink():
    raise SystemExit("persisted manifest is missing or unsafe")
manifest = json.load(manifest_path.open(encoding="utf-8"))
artifact_records = manifest.get("artifacts")
if not isinstance(artifact_records, list):
    raise SystemExit("persisted manifest artifacts are invalid")
artifact_paths = {record["path"] for record in artifact_records}
expected_files = artifact_paths | {"manifest.json", "launch-kit.zip"}
actual_files = set()
for root, directories, files in os.walk(kit, followlinks=False):
    directories.sort()
    files.sort()
    root_path = Path(root)
    for name in directories:
        path = root_path / name
        if stat.S_ISLNK(path.lstat().st_mode):
            raise SystemExit("persisted tree contains a directory symlink")
    for name in files:
        path = root_path / name
        mode = path.lstat().st_mode
        if not stat.S_ISREG(mode):
            raise SystemExit("persisted tree contains a non-regular file")
        actual_files.add(path.relative_to(kit).as_posix())
if actual_files != expected_files:
    raise SystemExit(f"persisted tree mismatch: {sorted(actual_files ^ expected_files)}")
for record in artifact_records:
    path = kit / record["path"]
    data = path.read_bytes()
    if len(data) != record["bytes"] or hashlib.sha256(data).hexdigest() != record["sha256"]:
        raise SystemExit(f"persisted artifact mismatch: {record['path']}")

report = json.load((data_root / "capture-report.json").open(encoding="utf-8"))
if report["ladder"] != expected:
    raise SystemExit(f"ladder={report['ladder']}, expected={expected}")
with zipfile.ZipFile(zip_path) as archive:
    names = set(archive.namelist())
    if names != artifact_paths | {"manifest.json"}:
        raise SystemExit(f"zip member mismatch: {sorted(names ^ (artifact_paths | {'manifest.json'}))}")
    required = {"capture-report.json", "screenshots/en/shot_1.png", "README.md", "manifest.json"}
    if not required.issubset(names):
        raise SystemExit(f"kit zip missing {sorted(required - names)}")
    kit_report = json.loads(archive.read("capture-report.json"))
    readme = archive.read("README.md").decode("utf-8")
    for name in sorted(names):
        if archive.read(name) != (kit / name).read_bytes():
            raise SystemExit(f"zip member differs from persisted file: {name}")
if kit_report != report:
    raise SystemExit("kit capture report differs from observed report")
if expected == "exported":
    if manifest.get("warnings") != [] or "Captured from " not in readme:
        raise SystemExit("exported provenance missing")
else:
    warning = "synthetic screens: no exported screenshots found and web capture unavailable/failed"
    if warning not in manifest.get("warnings", []) or "Synthesized deterministically" not in readme:
        raise SystemExit("synthetic warning/provenance missing")
digest_file.write_text(actual_zip_sha + "\n", encoding="ascii")
PY
}

run_case() {
  expected=$1
  target=$2
  digest_file=$3
  printf '%s\n' "$target" > "$DATA_ROOT/target"
  rm -f "$DATA_ROOT/order.yaml" "$DATA_ROOT/rationale.md" "$DATA_ROOT/capture-report.json"
  rm -rf "$DATA_ROOT/screens"
  python3 "$REPO/tools/pro_make_pipeline.py" >/dev/null
  add_pipeline
  run_id=$(gitmoot pipeline run appkit-pro --home "$HOME_ROOT")
  run_json="$HOME_ROOT/$expected-run.json"
  wait_run "$run_id" "$run_json"
  verify_persisted_kit "$run_json" "$expected" "$digest_file"
}

first_digest_file=$HOME_ROOT/exported-persisted.sha256
second_digest_file=$HOME_ROOT/synthetic-persisted.sha256
run_case exported "$FULL" "$first_digest_file"
run_case synthetic "$BARE" "$second_digest_file"
first_digest=$(cat "$first_digest_file")
second_digest=$(cat "$second_digest_file")
[ "$first_digest" != "$second_digest" ] || fail "second run did not overwrite the first persisted kit"

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

live_after=$(snapshot_live_root)
[ "$live_before" = "$live_after" ] || fail "live $LIVE_DATA_ROOT changed during E2E"
printf '%s\n' "pro_e2e: live root unchanged $live_after"
printf '%s\n' "pro_e2e: persisted exported=$first_digest synthetic=$second_digest (overwrite confirmed)"
printf '%s\n' 'pro_e2e: fixture-full exported, fixture-bare synthetic, persistence verified, expose rejected, public determinism matched'
