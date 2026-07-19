#!/bin/sh
set -eu

REPO=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
FIXTURE_ROOT=/root/appkit-pro-fixture
DATA_ROOT=/root/appkit-pro-e2e-data
LIVE_DATA_ROOT=/root/appkit-pro-data
HOME_ROOT=/root/appkit-pro-e2e-home
FULL="$FIXTURE_ROOT/fixture-full"
BARE="$FIXTURE_ROOT/fixture-bare"
DECOY="$FIXTURE_ROOT/fixture-decoy"

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
mkdir -p \
  "$FULL/docs/store/screenshots/en" "$FULL/lib/theme" \
  "$BARE/docs/store/screenshots/en" "$BARE/lib/theme" \
  "$DECOY/docs/store/screenshots/en" "$DECOY/lib/theme" \
  "$DATA_ROOT"

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
make_fixture_files "$DECOY"
: > "$BARE/docs/store/screenshots/en/.gitkeep"
: > "$DECOY/docs/store/screenshots/en/.gitkeep"

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

for fixture in "$FULL" "$BARE" "$DECOY"; do
  git -C "$fixture" init -q
  git -C "$fixture" config user.name appkit-pro-e2e
  git -C "$fixture" config user.email appkit-pro-e2e@example.invalid
  git -C "$fixture" add .
  git -C "$fixture" commit -qm fixture
done

DECOY_REPO="$DECOY/repos/decoy-app"
DECOY_SCREEN="$DECOY_REPO/fastlane/metadata/en-US/screenshots/decoy_1.png"
mkdir -p "$(dirname "$DECOY_SCREEN")"
git -C "$DECOY_REPO" init -q
python3 - "$DECOY_SCREEN" "$FIXTURE_ROOT/decoy-digests.json" "$REPO/tools" <<'PY'
from pathlib import Path
import hashlib, json, sys, tempfile
from PIL import Image, ImageDraw

screen = Path(sys.argv[1])
digest_path = Path(sys.argv[2])
sys.path.insert(0, sys.argv[3])
import pro_capture

image = Image.new("RGB", (800, 1600), (52, 31, 84))
draw = ImageDraw.Draw(image)
for y in range(1600):
    draw.line(
        (0, y, 799, y),
        fill=((y * 37) % 256, (y * 71 + 19) % 256, (y * 109 + 7) % 256),
    )
for x in range(0, 800, 7):
    draw.line(
        (x, 0, x, 1599),
        fill=((x * 13) % 256, (x * 29 + 5) % 256, (x * 47 + 11) % 256),
        width=2,
    )
for row in range(12):
    top = 60 + row * 125
    color = (245 - row * 4, 225 - row * 3, 255 - row * 2)
    draw.rounded_rectangle((54, top, 746, top + 82), radius=24, fill=color)
image.save(screen, format="PNG", optimize=True)
if screen.stat().st_size <= pro_capture.MIN_EXPORT_BYTES:
    raise SystemExit("decoy fixture did not satisfy the export size threshold")
with tempfile.TemporaryDirectory(prefix="appkit-pro-decoy-") as temporary:
    normalized = Path(temporary) / "normalized.png"
    pro_capture._save_normalized(screen, normalized)
    digests = {
        "normalized_sha256": hashlib.sha256(normalized.read_bytes()).hexdigest(),
        "raw_sha256": hashlib.sha256(screen.read_bytes()).hexdigest(),
    }
digest_path.write_text(
    json.dumps(digests, separators=(",", ":"), sort_keys=True) + "\n",
    encoding="utf-8",
)
PY

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
  decoy_digests=${4-}
  python3 - "$run_json" "$DATA_ROOT" "$expected" "$digest_file" "$decoy_digests" <<'PY'
import base64, hashlib, json, os, re, stat, sys, zipfile
from pathlib import Path

run = json.load(open(sys.argv[1], encoding="utf-8"))
data_root = Path(sys.argv[2])
expected = sys.argv[3]
digest_file = Path(sys.argv[4])
decoy_digest_path = Path(sys.argv[5]) if sys.argv[5] else None
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
if expected == "not-exported":
    if report["ladder"] == "exported":
        raise SystemExit("nested-repository decoy was incorrectly exported")
elif report["ladder"] != expected:
    raise SystemExit(f"ladder={report['ladder']}, expected={expected}")
expected_count = len(report.get("shots", []))
if report["ladder"] == "exported" and expected_count != 2:
    raise SystemExit(f"fixture-full exported {expected_count} screens instead of 2")
if report["ladder"] == "synthetic" and expected_count != 3:
    raise SystemExit(f"synthetic capture emitted {expected_count} screens instead of 3")
expected_counts = (
    {"padded": 3, "real": 0}
    if report["ladder"] == "synthetic"
    else {"padded": 0, "real": expected_count}
)
if report.get("counts") != expected_counts or len(report.get("shots", [])) != expected_count:
    raise SystemExit(f"capture counts mismatch: {report.get('counts')}")
expected_source = "synthetic" if report["ladder"] == "synthetic" else "real"
if any(item.get("source") != expected_source for item in report["shots"]):
    raise SystemExit("capture shot provenance mismatch")

framed_root = data_root / "framed"
expected_framed = {"manifest.json"} | {
    f"{kind}_{index}.png"
    for kind in ("device", "frame")
    for index in range(1, expected_count + 1)
}
actual_framed = {path.name for path in framed_root.iterdir()}
if actual_framed != expected_framed or any(path.is_symlink() for path in framed_root.iterdir()):
    raise SystemExit(f"framed handoff mismatch: {sorted(actual_framed ^ expected_framed)}")
handoff_manifest = json.load((framed_root / "manifest.json").open(encoding="utf-8"))
handoff_by_path = {item["path"]: item for item in handoff_manifest["artifacts"]}
if handoff_manifest.get("counts") != expected_counts:
    raise SystemExit("framed handoff counts mismatch")

manifest_paths = {item["path"] for item in artifact_records}
expected_devices = {f"landing/assets/device_{index}.png" for index in range(1, expected_count + 1)}
actual_devices = {path for path in manifest_paths if path.startswith("landing/assets/device_")}
if actual_devices != expected_devices:
    raise SystemExit(f"landing devices mismatch: {sorted(actual_devices ^ expected_devices)}")
expected_shots = {
    f"screenshots/{locale}/shot_{index}.png"
    for locale in ("en", "it")
    for index in range(1, expected_count + 1)
}
actual_shots = {path for path in manifest_paths if path.startswith("screenshots/")}
if actual_shots != expected_shots:
    raise SystemExit(f"marketing screenshots mismatch: {sorted(actual_shots ^ expected_shots)}")
for index in range(1, expected_count + 1):
    device_bytes = (framed_root / f"device_{index}.png").read_bytes()
    if device_bytes != (kit / f"landing/assets/device_{index}.png").read_bytes():
        raise SystemExit(f"landing device {index} differs from framed handoff")
    frame_bytes = (framed_root / f"frame_{index}.png").read_bytes()
    if frame_bytes != (kit / f"screenshots/en/shot_{index}.png").read_bytes():
        raise SystemExit(f"marketing frame {index} differs from framed handoff")

landing = (kit / "landing/index.html").read_text(encoding="utf-8")
if "./assets/device_" in landing:
    raise SystemExit("Pro landing retained a relative device reference")
embedded_hashes = [
    hashlib.sha256(base64.b64decode(value, validate=True)).hexdigest()
    for value in re.findall(r'src="data:image/png;base64,([A-Za-z0-9+/=]+)"', landing)
]
for index in range(1, expected_count + 1):
    device_sha = hashlib.sha256((framed_root / f"device_{index}.png").read_bytes()).hexdigest()
    expected_occurrences = 2 if index <= 2 else 1
    if embedded_hashes.count(device_sha) != expected_occurrences:
        raise SystemExit(f"landing did not embed device {index} from framed handoff")

compose_summary = json.loads(by_id["compose-real"]["summary"])
content_summary = json.loads(by_id["content"]["summary"])
handoff_keys = {f"framed/{name}" for name in expected_framed}
for key in handoff_keys:
    if compose_summary["digests"].get(key) != content_summary["digests"].get(key):
        raise SystemExit(f"compose/content handoff digest mismatch: {key}")
if compose_summary.get("counts") != expected_counts or content_summary.get("counts") != expected_counts:
    raise SystemExit("stage summary counts mismatch")
if decoy_digest_path is not None:
    decoy_digests = set(json.load(decoy_digest_path.open(encoding="utf-8")).values())
    observed_shots = {item["sha256"] for item in report["shots"]}
    persisted_screenshots = {
        item["sha256"]
        for item in artifact_records
        if item["path"].startswith("screenshots/")
    }
    if observed_shots.intersection(decoy_digests):
        raise SystemExit("capture report contains the nested-repository decoy digest")
    if persisted_screenshots.intersection(decoy_digests):
        raise SystemExit("persisted screenshots contain the nested-repository decoy digest")
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
count_line = f"Real screens: {expected_counts['real']}; synthetic padding: {expected_counts['padded']}."
if count_line not in readme:
    raise SystemExit("kit README omits honest real/padded counts")
if report["ladder"] == "exported":
    if manifest.get("warnings") != [] or "Captured from " not in readme:
        raise SystemExit("exported provenance missing")
elif report["ladder"] == "synthetic":
    warning = "synthetic screens: no exported screenshots found and web capture unavailable/failed"
    if warning not in manifest.get("warnings", []) or "Synthesized deterministically" not in readme:
        raise SystemExit("synthetic warning/provenance missing")
elif "Captured from " not in readme:
    raise SystemExit("web-capture provenance missing")
digest_file.write_text(actual_zip_sha + "\n", encoding="ascii")
PY
}

run_case() {
  expected=$1
  target=$2
  digest_file=$3
  decoy_digests=${4-}
  printf '%s\n' "$target" > "$DATA_ROOT/target"
  rm -f "$DATA_ROOT/order.yaml" "$DATA_ROOT/rationale.md" "$DATA_ROOT/capture-report.json"
  rm -rf "$DATA_ROOT/screens"
  python3 "$REPO/tools/pro_make_pipeline.py" >/dev/null
  add_pipeline
  run_id=$(gitmoot pipeline run appkit-pro --home "$HOME_ROOT")
  run_json="$HOME_ROOT/$expected-run.json"
  wait_run "$run_id" "$run_json"
  verify_persisted_kit "$run_json" "$expected" "$digest_file" "$decoy_digests"
}

first_digest_file=$HOME_ROOT/exported-persisted.sha256
second_digest_file=$HOME_ROOT/synthetic-persisted.sha256
decoy_digest_file=$HOME_ROOT/decoy-persisted.sha256
run_case exported "$FULL" "$first_digest_file"
run_case synthetic "$BARE" "$second_digest_file"
run_case not-exported "$DECOY" "$decoy_digest_file" "$FIXTURE_ROOT/decoy-digests.json"
first_digest=$(cat "$first_digest_file")
second_digest=$(cat "$second_digest_file")
decoy_digest=$(cat "$decoy_digest_file")
[ "$first_digest" != "$second_digest" ] || fail "second run did not overwrite the first persisted kit"

decoy_capture_stdout=$HOME_ROOT/decoy-capture.stdout
decoy_capture_stderr=$HOME_ROOT/decoy-capture.stderr
python3 "$REPO/tools/pro_capture.py" >"$decoy_capture_stdout" 2>"$decoy_capture_stderr"
python3 - "$decoy_capture_stdout" <<'PY'
import json, sys

lines = open(sys.argv[1], encoding="utf-8").read().splitlines()
if len(lines) != 1:
    raise SystemExit("decoy capture stdout did not contain exactly one result line")
result = json.loads(lines[0])["gitmoot_result"]
summary = json.loads(result["summary"])
if result["decision"] != "implemented" or summary.get("ladder") == "exported":
    raise SystemExit("standalone decoy capture selected the nested-repository export")
PY
grep -F 'capture scan boundary excluded: repos/decoy-app (nested-repository)' "$decoy_capture_stderr" >/dev/null || {
  cat "$decoy_capture_stderr" >&2
  fail "decoy capture log did not record the nested-repository boundary"
}

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
printf '%s\n' "pro_e2e: decoy non-exported=$decoy_digest; nested decoy digests absent; boundary log present"
printf '%s\n' 'pro_e2e: fixture-full exported, fixture-bare synthetic, fixture-decoy non-exported, persistence verified, expose rejected, public determinism matched'
