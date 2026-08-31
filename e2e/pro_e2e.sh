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

stat_live_target() {
  python3 - "$LIVE_DATA_ROOT" <<'PY'
from pathlib import Path
import json, stat, sys

target = Path(sys.argv[1]) / "target"
try:
    info = target.lstat()
except FileNotFoundError:
    record = {"exists": False}
else:
    record = {
        "exists": True,
        "inode": info.st_ino,
        "mode": stat.S_IFMT(info.st_mode) | stat.S_IMODE(info.st_mode),
        "mtime_ns": info.st_mtime_ns,
        "size": info.st_size,
    }
print(json.dumps(record, separators=(",", ":"), sort_keys=True))
PY
}

assert_e2e_isolation() {
  python3 - "$DATA_ROOT" "$LIVE_DATA_ROOT" "$FIXTURE_ROOT" "$HOME_ROOT" "$REPO" <<'PY'
from pathlib import Path
import sys

data_root, live_root, fixture_root, home_root, repo = (
    Path(value).resolve(strict=False) for value in sys.argv[1:]
)
if data_root == live_root:
    raise SystemExit("E2E data root aliases the live personal data root")
touch_points = [
    data_root,
    *(data_root / name for name in (
        "target", "order.yaml", "rationale.md", "spec-stamp",
        "capture-report.json", "screens", "framed", "content",
        "content-agent", "kit",
    )),
    fixture_root,
    home_root,
    repo / "appkit-pro.yaml",
    repo / "out",
    repo / "templates" / "appkit-pro.yaml.tmpl",
]
for path in touch_points:
    resolved = path.resolve(strict=False)
    if resolved == live_root or live_root in resolved.parents:
        raise SystemExit(f"E2E write path resolves under live data root: {path}")
PY
}

assert_e2e_isolation
live_target_before=$(stat_live_target)
export APPKIT_PRO_DATA_DIR=$DATA_ROOT
[ "$APPKIT_PRO_DATA_DIR" = "$DATA_ROOT" ] || fail "E2E data-root environment mismatch"

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
cat > "$BARE/pubspec.yaml" <<'EOF'
name: bare_switch_app
description: A second fixture for target-switch verification.
EOF
cat > "$BARE/README.md" <<'EOF'
# Bare Switch App

Tagline: Keep the next step beautifully simple.

- Focus on what matters
- Organize each day
- Follow progress clearly
EOF
cat > "$BARE/docs/store/app-name.txt" <<'EOF'
Bare Switch App
EOF
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
gitmoot repo add themartianapp/appkit-demo --path "$REPO" --home "$HOME_ROOT" >/dev/null
gitmoot agent start appkit-deriver \
  --home "$HOME_ROOT" \
  --runtime codex \
  --repo themartianapp/appkit-demo \
  --path "$REPO" \
  --role implementer \
  --capability produce \
  --model gpt-5.6-sol \
  --effort low \
  --policy workspace-write >/dev/null
PARALLEL_SUPPORTED=0
if gitmoot daemon start --help 2>&1 | grep -q -- '-workers'; then
  gitmoot daemon start --home "$HOME_ROOT" --poll 1s --parallel 2 >/dev/null
  PARALLEL_SUPPORTED=1
else
  gitmoot daemon start --home "$HOME_ROOT" --poll 1s >/dev/null
fi
TEMPLATE_BACKUP=''
cleanup() {
  if [ -n "$TEMPLATE_BACKUP" ] && [ -f "$TEMPLATE_BACKUP" ]; then
    cp -p "$TEMPLATE_BACKUP" "$REPO/templates/appkit-pro.yaml.tmpl"
  fi
  gitmoot daemon stop --home "$HOME_ROOT" >/dev/null 2>&1 || true
}
trap cleanup EXIT HUP INT TERM

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

verify_generated_dag() {
  python3 - "$REPO/appkit-pro.yaml" "$DATA_ROOT/spec-stamp" "$REPO/templates/appkit-pro.yaml.tmpl" <<'PY'
import hashlib, json, re, sys
from pathlib import Path

spec_path, stamp_path, template_path = map(Path, sys.argv[1:])
spec = spec_path.read_text(encoding="utf-8")
needs = {}
current = None
for line in spec.splitlines():
    match = re.fullmatch(r"  - id: ([a-z][a-z0-9-]*)", line)
    if match:
        current = match.group(1)
        needs[current] = []
        continue
    match = re.fullmatch(r"    needs: \[([^]]*)\]", line)
    if match and current:
        needs[current] = [item.strip() for item in match.group(1).split(",") if item.strip()]
expected = {
    "derive": [],
    "capture": ["derive"],
    "compose-real": ["capture", "derive"],
    "content": ["derive"],
    "landing": ["content", "compose-real"],
    "kit": ["landing"],
}
if needs != expected:
    raise SystemExit(f"generated DAG mismatch: {needs}")
content_block = spec.split("  - id: content\n", 1)[1].split(
    "  - id: landing\n", 1
)[0]
data_root = str(stamp_path.parent)
required_content_lines = (
    "    agent: appkit-deriver\n",
    "    action: produce\n",
    "    write: true\n",
    f'    writes: ["{data_root}"]\n',
    "    reads: []\n",
)
if "    cmd:" in content_block or any(
    line not in content_block for line in required_content_lines
):
    raise SystemExit("generated content stage is not the isolated produce arm")
if "content-agent/" not in content_block or "__CONTENT_PROMPT__" in spec:
    raise SystemExit("generated content prompt is missing or unresolved")
template_sha = hashlib.sha256(template_path.read_bytes()).hexdigest()
stamp = json.loads(stamp_path.read_text(encoding="utf-8"))
target = str((stamp_path.parent / "target").read_text(encoding="utf-8").strip())
target = str(Path(target).resolve(strict=True))
if (
    stamp != {"target": target, "template_sha256": template_sha}
    or f"# template_sha256: {template_sha}" not in spec
):
    raise SystemExit("generated spec stamp mismatch")
PY
}

record_concurrency() {
  run_json=$1
  python3 - "$run_json" "$HOME_ROOT" "$HOME_ROOT/concurrency-evidence" "$PARALLEL_SUPPORTED" <<'PY'
import datetime as dt
import json, sqlite3, sys
from pathlib import Path

run = json.load(open(sys.argv[1], encoding="utf-8"))
home = Path(sys.argv[2])
output = sys.argv[3]
parallel_supported = sys.argv[4] == "1"
by_id = {stage["id"]: stage for stage in run["stages"]}
database = home / ".gitmoot" / "gitmoot.db"
if not database.is_file():
    database = home / "gitmoot.db"
if not database.is_file():
    raise SystemExit("Gitmoot job-event store is missing")

def parse_time(value):
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.replace(tzinfo=parsed.tzinfo or dt.timezone.utc)

connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)

def event_window(stage_id):
    job_id = by_id[stage_id].get("job_id")
    if not isinstance(job_id, str) or not job_id:
        raise SystemExit(f"{stage_id} stage omitted its job id")
    rows = connection.execute(
        "SELECT kind,created_at FROM job_events "
        "WHERE job_id=? AND kind IN ('running','succeeded') ORDER BY id",
        (job_id,),
    ).fetchall()
    starts = [value for kind, value in rows if kind == "running"]
    finishes = [value for kind, value in rows if kind == "succeeded"]
    if len(starts) != 1 or len(finishes) != 1:
        raise SystemExit(f"{stage_id} job-event window is incomplete: {rows}")
    return job_id, starts[0], finishes[0], parse_time(starts[0]), parse_time(finishes[0])

capture_job, capture_start_raw, capture_end_raw, capture_start, capture_end = event_window("capture")
content_job, content_start_raw, content_end_raw, content_start, content_end = event_window("content")
job_row = connection.execute(
    "SELECT agent,type,state,model FROM jobs WHERE id=?", (content_job,)
).fetchone()
if job_row != ("appkit-deriver", "produce", "succeeded", "gpt-5.6-sol"):
    raise SystemExit(f"content was not a real successful Codex produce job: {job_row}")
agent_row = connection.execute(
    "SELECT runtime,model,effort FROM agents WHERE name='appkit-deriver'"
).fetchone()
if agent_row != ("codex", "gpt-5.6-sol", "low"):
    raise SystemExit(f"content agent model/effort pin is invalid: {agent_row}")
overlap = capture_start <= content_end and content_start <= capture_end
capture_event_inside_content = (
    content_start <= capture_start <= content_end
    or content_start <= capture_end <= content_end
)
if parallel_supported and (not overlap or not capture_event_inside_content):
    raise SystemExit(
        "content produce and capture shell job-event windows did not overlap: "
        f"capture={capture_start_raw}..{capture_end_raw} "
        f"content={content_start_raw}..{content_end_raw}"
    )
line = (
    f"overlap={'true' if overlap else 'false'} "
    f"capture_job={capture_job} capture={capture_start_raw}..{capture_end_raw} "
    f"content_job={content_job} content={content_start_raw}..{content_end_raw}\n"
)
with open(output, "a", encoding="utf-8") as handle:
    handle.write(line)
PY
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

wait_failed_run() {
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
      failed)
        sleep 1
        gitmoot pipeline show "$run_id" --json --home "$HOME_ROOT" > "$run_json"
        settled=$(python3 - "$run_json" <<'PY'
import json, sys
print(json.load(open(sys.argv[1], encoding="utf-8"))["state"])
PY
)
        [ "$settled" = failed ] || fail "pipeline run $run_id did not remain failed"
        return
        ;;
      succeeded|blocked|cancelled)
        cat "$run_json" >&2
        fail "pipeline run $run_id ended $state instead of failed"
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
landing_summary = json.loads(by_id["landing"]["summary"])
content_stage = by_id["content"]
if (
    content_stage.get("state") != "succeeded"
    or not content_stage.get("job_id")
    or not isinstance(content_stage.get("summary"), str)
):
    raise SystemExit("content produce stage did not complete as a real job")
handoff_keys = {f"framed/{name}" for name in expected_framed}
for key in handoff_keys:
    if compose_summary["digests"].get(key) != landing_summary["digests"].get(key):
        raise SystemExit(f"compose/landing handoff digest mismatch: {key}")
if set(compose_summary["digests"]) != handoff_keys:
    raise SystemExit("compose-real summary contains cwd output artifacts")
for key in expected_shots:
    summary_key = "out/" + key
    frame_key = f"framed/frame_{Path(key).stem.split('_')[-1]}.png"
    if compose_summary["digests"].get(frame_key) != landing_summary["digests"].get(summary_key):
        raise SystemExit(f"framed/landing screenshot identity mismatch: {summary_key}")
if compose_summary.get("counts") != expected_counts or landing_summary.get("counts") != expected_counts:
    raise SystemExit("stage summary counts mismatch")
content_provenance = manifest.get("content_provenance")
if (
    not isinstance(content_provenance, dict)
    or content_provenance != landing_summary.get("content_provenance")
    or content_provenance != summary.get("content_provenance")
):
    raise SystemExit("content provenance differs across landing, kit, and manifest")
expected_content = {
    f"copy/{locale}/{name}.txt"
    for locale in ("en", "it")
    for name in (
        "description", "keywords", "name", "promotional_text", "release_notes", "subtitle"
    )
} | {"legal/privacy.md", "legal/terms.md"}
if set(content_provenance) != expected_content or any(
    source not in ("agent", "deterministic-fallback")
    for source in content_provenance.values()
):
    raise SystemExit("content provenance has an invalid shape")
if "agent" not in content_provenance.values():
    raise SystemExit("content produce job supplied no valid observed files")
content_root = data_root / "content-agent"
for relative, source in sorted(content_provenance.items()):
    output = kit / relative
    if source == "agent":
        observed_path = content_root / relative
        if (
            not observed_path.is_file()
            or observed_path.is_symlink()
            or observed_path.read_bytes() != output.read_bytes()
        ):
            raise SystemExit(f"agent content was not preserved: {relative}")

for locale in ("en", "it"):
    for name, limit in (
        ("name", 30),
        ("subtitle", 30),
        ("promotional_text", 170),
        ("release_notes", 4000),
    ):
        text = (kit / f"copy/{locale}/{name}.txt").read_text(encoding="utf-8").rstrip("\n")
        if "\n" in text or not text or len(text) > limit:
            raise SystemExit(f"final store field is invalid: {locale}/{name}")
    keywords = (kit / f"copy/{locale}/keywords.txt").read_text(encoding="utf-8").rstrip("\n")
    tokens = keywords.split(",")
    if (
        len(keywords) > 100
        or any(not token or token != token.strip() or any(c.isspace() for c in token) for token in tokens)
        or len({token.casefold() for token in tokens}) != len(tokens)
    ):
        raise SystemExit(f"final keywords are invalid: {locale}")
    description = (kit / f"copy/{locale}/description.txt").read_text(encoding="utf-8").rstrip("\n")
    if not description or len(description) > 4000:
        raise SystemExit(f"final description is invalid: {locale}")
for name in ("privacy", "terms"):
    legal = (kit / f"legal/{name}.md").read_text(encoding="utf-8")
    if "1 January 2026" not in legal or "—" in legal:
        raise SystemExit(f"final legal source is invalid: {name}")

observed = landing_summary.get("observed")
if not isinstance(observed, dict) or any(
    not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None
    for value in observed.values()
):
    raise SystemExit("landing observed digest map is invalid")
expected_observed = {
    "out/" + relative
    for relative, source in content_provenance.items()
    if source == "agent"
}
for name in ("privacy", "terms"):
    if content_provenance[f"legal/{name}.md"] == "agent":
        expected_observed.add(f"out/landing/legal/{name}.html")
if set(observed) != expected_observed:
    raise SystemExit("landing observed file set is invalid")
landing_output_digests = {
    key for key in landing_summary["digests"] if key.startswith("out/")
}
required_landing_outputs = {"out/" + path for path in artifact_paths}
if (
    landing_output_digests.intersection(observed)
    or landing_output_digests | set(observed) != required_landing_outputs
):
    raise SystemExit("landing verified/observed partition is incomplete")
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
for relative, source in sorted(content_provenance.items()):
    if f"| `{relative}` | {source} |" not in readme:
        raise SystemExit(f"kit README omits content provenance: {relative}")
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
  expected_app_name=${5-}
  printf '%s\n' "$target" > "$DATA_ROOT/target"
  make_stderr=$HOME_ROOT/$expected-pro-make.stderr
  python3 "$REPO/tools/pro_make_pipeline.py" >/dev/null 2>"$make_stderr"
  verify_generated_dag
  add_pipeline
  run_id=$(gitmoot pipeline run appkit-pro --home "$HOME_ROOT")
  run_json="$HOME_ROOT/$expected-run.json"
  wait_run "$run_id" "$run_json"
  record_concurrency "$run_json"
  verify_persisted_kit "$run_json" "$expected" "$digest_file" "$decoy_digests"
  if [ -n "$expected_app_name" ]; then
    python3 - "$REPO/tools" "$DATA_ROOT" "$target" "$expected_app_name" <<'PY'
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])
import pro_inputs

data_root = Path(sys.argv[2])
expected_target = str(Path(sys.argv[3]).resolve(strict=True))
expected_app_name = sys.argv[4]
values = pro_inputs.load_order()
order_target = pro_inputs.parse_persisted_order_target(
    (data_root / "order.yaml").read_text(encoding="utf-8")
)
if order_target != expected_target:
    raise SystemExit(f"order target mismatch: {order_target} != {expected_target}")
if values["app_name"] != expected_app_name:
    raise SystemExit(
        f"derived app name mismatch: {values['app_name']} != {expected_app_name}"
    )
readme = (data_root / "kit" / "README.md").read_text(encoding="utf-8")
if f"# {expected_app_name} Launch Kit" not in readme:
    raise SystemExit("persisted kit does not reflect the newly derived app name")
PY
  fi
}

first_digest_file=$HOME_ROOT/exported-persisted.sha256
second_digest_file=$HOME_ROOT/synthetic-persisted.sha256
decoy_digest_file=$HOME_ROOT/decoy-persisted.sha256
run_case exported "$FULL" "$first_digest_file" "" "Fixture App"
outside_switch_sentinel=$HOME_ROOT/target-switch-outside-data-root
printf '%s\n' keep > "$outside_switch_sentinel"
printf '%s\n' "$BARE" > "$DATA_ROOT/target"
no_regen_run_id=$(gitmoot pipeline run appkit-pro --home "$HOME_ROOT")
no_regen_run_json=$HOME_ROOT/no-regen-switch-run.json
wait_failed_run "$no_regen_run_id" "$no_regen_run_json"
python3 - "$no_regen_run_json" <<'PY'
import json, sys

run = json.load(open(sys.argv[1], encoding="utf-8"))
capture = {stage["id"]: stage for stage in run["stages"]}.get("capture")
expected = (
    "switch_target_requires_regen: target changed since the spec was generated - "
    "run tools/pro_make_pipeline.py, then re-add the pipeline"
)
if not capture or capture.get("state") != "failed":
    raise SystemExit(f"no-regen capture did not fail: {capture}")
summary = json.loads(capture.get("summary", "null"))
if summary != {"reason": expected, "v": 1}:
    raise SystemExit(f"no-regen target guard returned {summary}")
PY
run_case synthetic "$BARE" "$second_digest_file" "" "Bare Switch App"
[ "$(cat "$outside_switch_sentinel")" = keep ] || fail "target switch changed a path outside the data root"
switch_log=$HOME_ROOT/synthetic-pro-make.stderr
grep -F 'pro_make_pipeline: target changed ' "$switch_log" >/dev/null || fail "target switch did not log the changed target"
for stale_path in order.yaml rationale.md capture-report.json screens framed content-agent kit; do
  grep -F "pro_make_pipeline: cleared stale $stale_path" "$switch_log" >/dev/null || {
    cat "$switch_log" >&2
    fail "target switch did not clear stale $stale_path"
  }
done
same_target_before=$(python3 - "$DATA_ROOT/order.yaml" <<'PY'
import hashlib, sys
from pathlib import Path

path = Path(sys.argv[1])
print(f"{path.stat().st_mtime_ns}:{hashlib.sha256(path.read_bytes()).hexdigest()}")
PY
)
same_target_stderr=$HOME_ROOT/same-target-pro-make.stderr
python3 "$REPO/tools/pro_make_pipeline.py" >/dev/null 2>"$same_target_stderr"
same_target_after=$(python3 - "$DATA_ROOT/order.yaml" <<'PY'
import hashlib, sys
from pathlib import Path

path = Path(sys.argv[1])
print(f"{path.stat().st_mtime_ns}:{hashlib.sha256(path.read_bytes()).hexdigest()}")
PY
)
[ "$same_target_before" = "$same_target_after" ] || fail "same-target generator run changed order.yaml"
if grep -F 'pro_make_pipeline: cleared stale ' "$same_target_stderr" >/dev/null; then
  cat "$same_target_stderr" >&2
  fail "same-target generator run cleared derived state"
fi
old_stamp_backup=$(mktemp "$HOME_ROOT/spec-stamp-json.XXXXXX")
cp "$DATA_ROOT/spec-stamp" "$old_stamp_backup"
python3 - "$DATA_ROOT/spec-stamp" "$old_stamp_backup" <<'PY'
import json, sys
from pathlib import Path

stamp = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
Path(sys.argv[1]).write_text(stamp["template_sha256"] + "\n", encoding="ascii")
PY
old_stamp_result=$(PYTHONPATH="$REPO/tools" python3 -c 'import pro_inputs; print(pro_inputs.require_spec_stamp())')
expected_old_stamp=$(python3 - "$old_stamp_backup" <<'PY'
import json, sys
print(json.load(open(sys.argv[1], encoding="utf-8"))["template_sha256"])
PY
)
[ "$old_stamp_result" = "$expected_old_stamp" ] || fail "legacy one-line spec stamp was rejected"
cp "$old_stamp_backup" "$DATA_ROOT/spec-stamp"
run_case not-exported "$DECOY" "$decoy_digest_file" "$FIXTURE_ROOT/decoy-digests.json" "Fixture App"

fallback_context=$HOME_ROOT/fallback-landing-context.json
fallback_relative_file=$HOME_ROOT/fallback-relative
python3 - "$HOME_ROOT/not-exported-run.json" "$DATA_ROOT/kit/manifest.json" "$fallback_context" "$fallback_relative_file" <<'PY'
import json, sys
from pathlib import Path

run = json.load(open(sys.argv[1], encoding="utf-8"))
manifest = json.load(open(sys.argv[2], encoding="utf-8"))
by_id = {stage["id"]: stage for stage in run["stages"]}
stages = {}
for stage_id in ("compose-real", "content"):
    stage = by_id[stage_id]
    stages[stage_id] = {
        "id": stage_id,
        "state": "succeeded",
        "summary": stage["summary"],
        "summary_truncated": False,
    }
context = {"complete": True, "schema_version": 1, "stages": stages}
Path(sys.argv[3]).write_text(json.dumps(context), encoding="utf-8")
provenance = manifest["content_provenance"]
candidates = sorted(path for path, source in provenance.items() if source == "agent")
if not candidates:
    raise SystemExit("no agent-sourced file is available for fallback simulation")
Path(sys.argv[4]).write_text(candidates[0] + "\n", encoding="utf-8")
PY
fallback_relative=$(cat "$fallback_relative_file")
fallback_source=$DATA_ROOT/content-agent/$fallback_relative
fallback_backup=$(mktemp "$HOME_ROOT/fallback-content.XXXXXX")
cp "$fallback_source" "$fallback_backup"
truncate -s 0 "$fallback_source"
fallback_stdout_one=$HOME_ROOT/fallback-landing-one.stdout
fallback_stdout_two=$HOME_ROOT/fallback-landing-two.stdout
fallback_stderr=$HOME_ROOT/fallback-landing.stderr
(cd "$REPO" && GITMOOT_PIPELINE_UPSTREAM_CONTEXT_FILE="$fallback_context" \
  python3 tools/pro_stage_landing.py) >"$fallback_stdout_one" 2>"$fallback_stderr"
fallback_digest_one=$(sha256sum "$REPO/out/$fallback_relative" | awk '{print $1}')
(cd "$REPO" && GITMOOT_PIPELINE_UPSTREAM_CONTEXT_FILE="$fallback_context" \
  python3 tools/pro_stage_landing.py) >"$fallback_stdout_two" 2>>"$fallback_stderr"
fallback_digest_two=$(sha256sum "$REPO/out/$fallback_relative" | awk '{print $1}')
cp "$fallback_backup" "$fallback_source"
python3 - "$fallback_stdout_one" "$fallback_stdout_two" "$fallback_relative" "$DATA_ROOT/kit/manifest.json" <<'PY'
import json, sys

baseline = json.load(open(sys.argv[4], encoding="utf-8"))["content_provenance"]
relative = sys.argv[3]
for output in sys.argv[1:3]:
    lines = open(output, encoding="utf-8").read().splitlines()
    if len(lines) != 1:
        raise SystemExit("fallback landing stdout did not contain exactly one result line")
    result = json.loads(lines[0])["gitmoot_result"]
    summary = json.loads(result["summary"])
    if result["decision"] != "implemented":
        raise SystemExit(f"fallback landing failed: {result}")
    if summary["content_provenance"].get(relative) != "deterministic-fallback":
        raise SystemExit("truncated agent file did not select deterministic fallback")
    if f"out/{relative}" not in summary["digests"]:
        raise SystemExit("fallback file was not included in verified digests")
    for path, source in baseline.items():
        if path != relative and summary["content_provenance"].get(path) != source:
            raise SystemExit(f"unrelated provenance changed during fallback: {path}")
PY
[ "$fallback_digest_one" = "$fallback_digest_two" ] || fail "truncated agent fallback was not deterministic"
grep -F "content fallback: $fallback_relative/empty" "$fallback_stderr" >/dev/null || fail "fallback reason missing from landing stderr"

first_digest=$(cat "$first_digest_file")
second_digest=$(cat "$second_digest_file")
decoy_digest=$(cat "$decoy_digest_file")
[ "$first_digest" != "$second_digest" ] || fail "second run did not overwrite the first persisted kit"
if [ "$PARALLEL_SUPPORTED" = 1 ]; then
  grep -q '^overlap=true ' "$HOME_ROOT/concurrency-evidence" || {
    cat "$HOME_ROOT/concurrency-evidence" >&2
    fail "content and capture never overlapped with parallel workers enabled"
  }
fi

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

TEMPLATE_BACKUP=$(mktemp "$HOME_ROOT/appkit-pro-template.XXXXXX")
cp -p "$REPO/templates/appkit-pro.yaml.tmpl" "$TEMPLATE_BACKUP"
printf '%s\n' '# e2e stale-spec mutation' >> "$REPO/templates/appkit-pro.yaml.tmpl"
stale_stdout=$HOME_ROOT/stale-spec.stdout
stale_stderr=$HOME_ROOT/stale-spec.stderr
python3 "$REPO/tools/pro_capture.py" >"$stale_stdout" 2>"$stale_stderr"
python3 - "$stale_stdout" <<'PY'
import json, sys

lines = open(sys.argv[1], encoding="utf-8").read().splitlines()
if len(lines) != 1:
    raise SystemExit("stale-spec capture stdout did not contain exactly one result line")
result = json.loads(lines[0])["gitmoot_result"]
summary = json.loads(result["summary"])
expected = "stale_spec: regenerate with pro_make_pipeline.py (template changed since this spec was generated)"
if result["decision"] != "failed" or summary != {"reason": expected, "v": 1}:
    raise SystemExit(f"stale-spec guard returned {result}")
PY
grep -F 'stale_spec: regenerate with pro_make_pipeline.py' "$stale_stderr" >/dev/null || fail "stale-spec reason missing from stderr"
cp -p "$TEMPLATE_BACKUP" "$REPO/templates/appkit-pro.yaml.tmpl"
TEMPLATE_BACKUP=''

NOTIFY_TMP=$(mktemp -d "$HOME_ROOT/notify-pro.XXXXXX")
mkdir -p "$NOTIFY_TMP/bin" "$NOTIFY_TMP/data"
cat > "$NOTIFY_TMP/bin/curl" <<'EOF'
#!/bin/sh
printf '%s\n' "$@" > "$MOCK_CURL_ARGS"
cat > "$MOCK_CURL_STDIN"
printf '%s' 200
EOF
chmod +x "$NOTIFY_TMP/bin/curl"
export MOCK_CURL_ARGS=$NOTIFY_TMP/curl.args
export MOCK_CURL_STDIN=$NOTIFY_TMP/curl.stdin
notify_stdout=$NOTIFY_TMP/stdout
notify_stderr=$NOTIFY_TMP/stderr
PATH="$NOTIFY_TMP/bin:$PATH" \
  APPKIT_PRO_DATA_DIR="$NOTIFY_TMP/data" \
  TELEGRAM_BOT_TOKEN='123456:unit_test_token_never_in_argv' \
  TELEGRAM_CHAT_ID='-1001234567890' \
  GITMOOT_TRIGGER_UPSTREAM_RUN_ID='run-unit-123' \
  sh "$REPO/tools/notify_pro.sh" >"$notify_stdout" 2>"$notify_stderr"
python3 - "$notify_stdout" <<'PY'
import json, sys

lines = open(sys.argv[1], encoding="utf-8").read().splitlines()
if len(lines) != 1:
    raise SystemExit("notify-pro stdout did not contain exactly one result line")
result = json.loads(lines[0])["gitmoot_result"]
if result["decision"] != "approved" or "kit attached: 0" not in result["summary"]:
    raise SystemExit(f"notify-pro fallback failed: {result}")
PY
grep -F 'persisted kit is missing; using text fallback' "$notify_stderr" >/dev/null || fail "notify-pro omitted its fallback reason"
if grep -F '123456:unit_test_token_never_in_argv' "$MOCK_CURL_ARGS" >/dev/null; then
  fail "notify-pro leaked the bot token into curl argv"
fi
grep -F '123456:unit_test_token_never_in_argv' "$MOCK_CURL_STDIN" >/dev/null || fail "notify-pro did not feed the bot URL through stdin config"

gitmoot pipeline add "$REPO/notify-pro.yaml" --enable --home "$HOME_ROOT" >/dev/null
for pipeline in appkit-pro appkit-notify-pro; do
  expose_log=$HOME_ROOT/expose-rejection-$pipeline.log
  if gitmoot pipeline expose --schema "$REPO/schema.json" --home "$HOME_ROOT" "$pipeline" >"$expose_log" 2>&1; then
    fail "$pipeline unexpectedly exposed"
  fi
  grep -Eq 'template-free shell stage|not safe to expose|declares (env_keys|reads|writes|network)' "$expose_log" || {
    cat "$expose_log" >&2
    fail "$pipeline expose failed without the expected safety rejection"
  }
done

rm -rf "$HOME_ROOT/public-a" "$HOME_ROOT/public-b"
sh "$REPO/scripts/demo-kit.sh" "$HOME_ROOT/public-a" >/dev/null
sh "$REPO/scripts/demo-kit.sh" "$HOME_ROOT/public-b" >/dev/null
cmp "$HOME_ROOT/public-a/kit/out/manifest.json" "$HOME_ROOT/public-b/kit/out/manifest.json"
cmp "$HOME_ROOT/public-a/kit/out/launch-kit.zip" "$HOME_ROOT/public-b/kit/out/launch-kit.zip"

live_target_after=$(stat_live_target)
printf '%s\n' "pro_e2e: isolation roots verified; live target stat before=$live_target_before after=$live_target_after (observation only)"
printf '%s\n' "pro_e2e: persisted exported=$first_digest synthetic=$second_digest (overwrite confirmed)"
printf '%s\n' 'pro_e2e: no-regen target switch failed at capture with switch_target_requires_regen; legacy one-line stamp accepted'
printf '%s\n' "pro_e2e: target switch self-healed to $BARE; stale state cleared; same-target order stable $same_target_after"
printf '%s\n' "pro_e2e: decoy non-exported=$decoy_digest; nested decoy digests absent; boundary log present"
printf '%s\n' "pro_e2e: truncated agent file $fallback_relative used deterministic fallback=$fallback_digest_one"
if [ "$PARALLEL_SUPPORTED" = 1 ]; then
  printf '%s\n' "pro_e2e: concurrency $(grep '^overlap=true ' "$HOME_ROOT/concurrency-evidence" | head -n 1)"
else
  printf '%s\n' 'pro_e2e: daemon has no parallel-worker flag; fork/join edges verified structurally'
fi
printf '%s\n' 'pro_e2e: fixture-full exported, fixture-bare synthetic, fixture-decoy non-exported, persistence verified, both personal pipelines expose-rejected, notify fallback hardened, stale spec and unregenerated target switch rejected, public determinism matched'
