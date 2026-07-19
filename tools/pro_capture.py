#!/usr/bin/env python3
"""Personal screenshot capture ladder: exports, web surface, then synthesis."""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import re
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import time
import unicodedata
from pathlib import Path

from PIL import Image, ImageOps

import frame_compose
import pro_inputs
import screens
from stage_support import canonical_json, emit_result, failure_summary, log


MAX_CAPTURE_SECONDS = 13 * 60
MAX_FLUTTER_SECONDS = 12 * 60
MIN_EXPORT_BYTES = 10 * 1024
MAX_EXPORT_PIXELS = 100_000_000
NODE = Path("/usr/bin/node")
CHROME = Path("/usr/bin/google-chrome")
PLAYWRIGHT = Path("/root/vetrina/node_modules/playwright-core")
EXPORT_JUNK_DIRECTORIES = frozenset(
    ("build", "coverage", "deriveddata", "dist", "out", "target")
)


NODE_CAPTURE_SCRIPT = r"""
const { chromium } = require(process.argv[1]);
const fs = require('fs');
const base = process.argv[2];
const output = process.argv[3];
let serial = 0;

function byteClose(first, second) {
  if (!first || !second) return false;
  const longest = Math.max(first.length, second.length);
  if (Math.abs(first.length - second.length) > longest * 0.02) return false;
  const length = Math.min(first.length, second.length);
  const step = Math.max(1, Math.floor(length / 4096));
  let compared = 0;
  let different = 0;
  for (let index = 0; index < length; index += step) {
    compared++;
    if (first[index] !== second[index]) different++;
  }
  return different / compared <= 0.01;
}

(async () => {
  const browser = await chromium.launch({headless: true, executablePath: process.argv[4]});
  try {
    const context = await browser.newContext({
      viewport: {width: 390, height: 844},
      deviceScaleFactor: 3,
      hasTouch: true,
      isMobile: true
    });
    const page = await context.newPage();
    await page.goto(base, {waitUntil: 'domcontentloaded', timeout: 30000});
    const result = [];

    async function collectStable(label, windowMs) {
      const end = Date.now() + windowMs;
      let previous = null;
      let lastStable = null;
      while (Date.now() < end) {
        const current = await page.screenshot({fullPage: false, type: 'png'});
        if (byteClose(previous, current) && !byteClose(lastStable, current)) {
          serial++;
          const file = `${output}/raw_${serial}.png`;
          fs.writeFileSync(file, current);
          result.push({file, phase: label, url: page.url()});
          lastStable = current;
          process.stderr.write(`capture interaction: stable ${label}\n`);
        }
        previous = current;
        await page.waitForTimeout(500);
      }
    }

    process.stderr.write('capture interaction: splash-settle begin\n');
    await collectStable('settle', 20000);

    const discovered = await page.evaluate(() => {
      const current = new URL(location.href);
      const values = [];
      for (const node of document.querySelectorAll('a[href]')) {
        const url = new URL(node.getAttribute('href'), current);
        if (url.origin === current.origin) values.push(url.pathname + url.search);
      }
      return Array.from(new Set(values)).sort();
    });

    const tabs = page.locator('[role="tab"]');
    const tabCount = Math.min(await tabs.count(), 2);
    for (let index = 0; index < tabCount; index++) {
      process.stderr.write(`capture interaction: dom-tab ${index + 1}\n`);
      try {
        await tabs.nth(index).click({timeout: 3000});
        await collectStable(`tab-${index + 1}`, 5000);
      } catch (_) {
        process.stderr.write(`capture interaction: dom-tab ${index + 1} failed\n`);
      }
      await page.keyboard.press('Escape');
      await page.goto(base, {waitUntil: 'domcontentloaded', timeout: 30000});
    }

    const routes = discovered.filter(route => route !== '/').slice(0, 2);
    for (let index = 0; index < routes.length; index++) {
      process.stderr.write(`capture interaction: dom-link ${index + 1}\n`);
      const route = routes[index];
      try {
        await page.evaluate((wanted) => {
          const current = new URL(location.href);
          const nodes = Array.from(document.querySelectorAll('a[href]'));
          nodes.sort((a, b) => new URL(a.getAttribute('href'), current).href.localeCompare(new URL(b.getAttribute('href'), current).href));
          const match = nodes.find(node => {
            const url = new URL(node.getAttribute('href'), current);
            return url.origin === current.origin && url.pathname + url.search === wanted;
          });
          if (!match) throw new Error('internal link disappeared');
          match.click();
        }, route);
        await page.waitForTimeout(500);
        await collectStable(`link-${index + 1}`, 5000);
      } catch (_) {
        process.stderr.write(`capture interaction: dom-link ${index + 1} failed\n`);
      }
      await page.keyboard.press('Escape');
      await page.goto(base, {waitUntil: 'domcontentloaded', timeout: 30000});
    }

    if (discovered.length === 0 && tabCount === 0) {
      const taps = [[195,295],[78,802],[195,802],[312,802]];
      for (let index = 0; index < taps.length; index++) {
        process.stderr.write(`capture interaction: canvas-tap ${index + 1}\n`);
        await page.mouse.click(taps[index][0], taps[index][1]);
        await collectStable(`canvas-${index + 1}`, 5000);
        process.stderr.write(`capture interaction: canvas-back ${index + 1}\n`);
        await page.keyboard.press('Escape');
        if (page.url() !== base) {
          await page.goBack({waitUntil: 'domcontentloaded', timeout: 3000}).catch(() => null);
        }
      }
    }
    process.stdout.write(JSON.stringify(result));
  } finally {
    await browser.close();
  }
})().catch(error => { process.stderr.write(error.name + '\n'); process.exit(1); });
"""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _reset_screens_dir() -> Path:
    root = pro_inputs.require_data_root()
    destination = root / "screens"
    try:
        mode = destination.lstat().st_mode
    except FileNotFoundError:
        pass
    else:
        if stat.S_ISLNK(mode):
            raise pro_inputs.ProDataError("screens directory is a symlink")
        if stat.S_ISDIR(mode):
            shutil.rmtree(destination, ignore_errors=False)
        else:
            destination.unlink()
    destination.mkdir(mode=0o700)
    return destination


def _edge_color(image: Image.Image) -> tuple[int, int, int]:
    width = min(image.width, 512)
    height = min(image.height, 512)
    sample = image.resize((width, height), Image.Resampling.LANCZOS).convert("RGB")
    pixels = sample.load()
    total = [0, 0, 0]
    count = 0
    for x in range(width):
        for y in (0, height - 1):
            pixel = pixels[x, y]
            for channel in range(3):
                total[channel] += pixel[channel]
            count += 1
    for y in range(1, max(1, height - 1)):
        for x in (0, width - 1):
            pixel = pixels[x, y]
            for channel in range(3):
                total[channel] += pixel[channel]
            count += 1
    return tuple(value // count for value in total)


def _normalize(image: Image.Image) -> Image.Image:
    prepared = ImageOps.exif_transpose(image).convert("RGB")
    scale = min(screens.SCREEN_W / prepared.width, screens.SCREEN_H / prepared.height)
    size = (max(1, round(prepared.width * scale)), max(1, round(prepared.height * scale)))
    resized = prepared.resize(size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (screens.SCREEN_W, screens.SCREEN_H), _edge_color(prepared))
    offset = ((screens.SCREEN_W - size[0]) // 2, (screens.SCREEN_H - size[1]) // 2)
    canvas.paste(resized, offset)
    return canvas


def _save_normalized(source: Path, destination: Path) -> None:
    with Image.open(source) as image:
        if image.width * image.height > MAX_EXPORT_PIXELS:
            raise ValueError("image too large")
        normalized = _normalize(image)
    destination.write_bytes(frame_compose.png_bytes(normalized))


def _visual_signature(path: Path) -> bytes | None:
    with Image.open(path) as image:
        prepared = ImageOps.exif_transpose(image).convert("RGBA")
        if prepared.width * prepared.height > MAX_EXPORT_PIXELS:
            raise ValueError("image too large")
        sample = prepared.resize((16, 16), Image.Resampling.LANCZOS)
    extrema = sample.getextrema()
    if extrema[3][1] == 0:
        return None
    color_spread = max(high for low, high in extrema[:3]) - min(
        low for low, high in extrema[:3]
    )
    if color_spread < 12:
        return None
    return sample.tobytes()


def _signature_distance(first: bytes, second: bytes) -> float:
    if len(first) != len(second) or not first:
        return 1.0
    return sum(abs(left - right) for left, right in zip(first, second)) / (
        len(first) * 255
    )


def _select_web_records(records: list[dict[str, object]], temporary: Path) -> list[Path]:
    prepared: list[tuple[Path, str, bytes]] = []
    for record in records:
        if (
            not isinstance(record, dict)
            or sorted(record) != ["file", "phase", "url"]
            or not isinstance(record.get("file"), str)
            or not isinstance(record.get("phase"), str)
            or not isinstance(record.get("url"), str)
            or not re.fullmatch(r"(?:settle|(?:tab|link|canvas)-[1-4])", str(record["phase"]))
        ):
            raise RuntimeError("browser capture output malformed")
        raw = Path(str(record["file"]))
        if raw.parent != temporary or not raw.is_file() or raw.is_symlink():
            raise RuntimeError("browser capture file unsafe")
        signature = _visual_signature(raw)
        if signature is None:
            log("capture interaction: rejected blank or uniform frame")
            continue
        prepared.append((raw, str(record["phase"]), signature))

    settled = [item for item in prepared if item[1] == "settle"]
    ordered = ([settled[-1]] if settled else []) + [
        item for item in prepared if item[1] != "settle"
    ]
    selected: list[tuple[Path, bytes]] = []
    for raw, phase, signature in ordered:
        if any(
            _signature_distance(signature, existing) < 0.025
            for _, existing in selected
        ):
            log(f"capture interaction: rejected duplicate {phase}")
            continue
        selected.append((raw, signature))
        log(f"capture interaction: accepted distinct {phase}")
        if len(selected) == 3:
            break
    return [path for path, _ in selected]


def _export_location_rank(relative: Path) -> int | None:
    """Prefer standard app-owned export layouts over legacy fastlane layouts."""

    directories = tuple(part.casefold() for part in relative.parts[:-1])
    if len(directories) >= 3 and directories[:3] == (
        "docs",
        "store",
        "screenshots",
    ):
        return 0
    if directories and directories[0] in ("screenshots", "store", "marketing"):
        return 0
    for index, part in enumerate(directories):
        if part != "fastlane":
            continue
        remainder = directories[index + 1 :]
        if (
            remainder
            and remainder[0] == "metadata"
            and any(item.startswith("screenshot") for item in remainder[1:])
        ):
            return 0
        if "screenshots" in remainder:
            return 1
    return None


def _contains_git_entry(directory: Path) -> bool:
    try:
        (directory / ".git").lstat()
    except FileNotFoundError:
        return False
    except OSError:
        # An unreadable repository marker is still a boundary; fail closed.
        return True
    return True


def _directory_boundary(
    directory: Path,
    name: str,
    *,
    exclude_build_outputs: bool,
) -> str | None:
    child = directory / name
    folded = name.casefold()
    if child.is_symlink():
        return "symlink"
    if name.startswith("."):
        return "hidden"
    if folded == "node_modules":
        return "node_modules"
    if _contains_git_entry(child):
        return "nested-repository"
    if exclude_build_outputs and folded in EXPORT_JUNK_DIRECTORIES:
        return "export-junk"
    return None


def _walk_files(
    root: Path,
    deadline: float | None = None,
    *,
    exclude_build_outputs: bool = False,
    log_boundaries: bool = False,
) -> list[Path]:
    result: list[Path] = []
    for directory, dir_names, file_names in os.walk(root, followlinks=False):
        if deadline is not None and time.monotonic() >= deadline:
            log("capture scan deadline reached")
            break
        kept: list[str] = []
        directory_path = Path(directory)
        for name in sorted(dir_names):
            reason = _directory_boundary(
                directory_path,
                name,
                exclude_build_outputs=exclude_build_outputs,
            )
            if reason is None:
                kept.append(name)
                continue
            if log_boundaries:
                relative = (directory_path / name).relative_to(root).as_posix()
                log(f"capture scan boundary excluded: {relative} ({reason})")
        dir_names[:] = kept
        for name in sorted(file_names):
            if deadline is not None and time.monotonic() >= deadline:
                log("capture scan deadline reached")
                return result
            path = Path(directory) / name
            if not path.is_symlink():
                result.append(path)
    return result


def _export_candidates(target: Path, deadline: float) -> list[Path]:
    candidates: list[Path] = []
    for path in _walk_files(
        target,
        deadline,
        exclude_build_outputs=True,
        log_boundaries=True,
    ):
        if time.monotonic() >= deadline:
            break
        relative = path.relative_to(target)
        location_rank = _export_location_rank(relative)
        if location_rank is None or path.suffix.casefold() not in (".png", ".jpg", ".jpeg"):
            continue
        try:
            if path.stat().st_size <= MIN_EXPORT_BYTES:
                continue
            with Image.open(path) as image:
                if image.format not in ("PNG", "JPEG") or image.width < 400:
                    continue
                image.verify()
        except (
            OSError,
            ValueError,
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
        ):
            continue
        candidates.append(path)

    def key(path: Path) -> tuple[int, int, int, str]:
        relative = path.relative_to(target)
        locale_parts = {part.casefold().replace("_", "-") for part in relative.parts[:-1]}
        preferred = bool(locale_parts.intersection(("en", "en-us", "en-gb")))
        location_rank = _export_location_rank(relative)
        if location_rank is None:
            raise RuntimeError("unranked export candidate")
        return (
            location_rank,
            len(relative.parts) - 1,
            0 if preferred else 1,
            relative.as_posix(),
        )

    return sorted(candidates, key=key)[:3]


def _capture_exports(
    target: Path, destination: Path, deadline: float
) -> tuple[str, list[Path]] | None:
    log("capture ladder attempt: exported screenshots")
    candidates = _export_candidates(target, deadline)
    if not candidates:
        log("capture ladder exported: no qualifying raster exports")
        return None
    outputs: list[Path] = []
    selected: list[Path] = []
    for source in candidates:
        if time.monotonic() >= deadline:
            log("capture ladder exported: deadline reserved for fallback")
            break
        output = destination / f"shot_{len(outputs) + 1}.png"
        try:
            _save_normalized(source, output)
        except (
            OSError,
            ValueError,
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
        ):
            log("capture ladder exported: skipped unreadable candidate")
            if output.exists() and not output.is_symlink():
                output.unlink()
            continue
        outputs.append(output)
        selected.append(source)
    if not outputs:
        log("capture ladder exported: qualifying files could not be decoded")
        return None
    log(f"capture ladder exported: selected {len(outputs)} screenshot(s)")
    return str(selected[0]), outputs


def _find_flutter_dirs(target: Path, deadline: float) -> list[Path]:
    directories: set[Path] = set()
    for path in _walk_files(target, deadline, log_boundaries=False):
        if path.name == "pubspec.yaml" and (path.parent / "web").is_dir():
            directories.add(path.parent)
    return sorted(directories, key=lambda path: path.relative_to(target).as_posix())


def _find_built_web(target: Path, deadline: float) -> list[Path]:
    roots: set[Path] = set()
    for path in _walk_files(target, deadline, log_boundaries=False):
        if path.name != "index.html":
            continue
        relative_parent = path.parent.relative_to(target)
        parts = tuple(part.casefold() for part in relative_parent.parts)
        if (parts and parts[-1] == "dist") or (len(parts) >= 2 and parts[-2:] == ("build", "web")):
            roots.add(path.parent)
    return sorted(roots, key=lambda path: path.relative_to(target).as_posix())


def _remaining(deadline: float, maximum: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("capture deadline exceeded")
    return min(remaining, maximum)


def _wait_server(server: subprocess.Popen[bytes], port: int, deadline: float) -> None:
    while time.monotonic() < deadline:
        if server.poll() is not None:
            raise RuntimeError("local web server exited before readiness")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.05)
    raise TimeoutError("local web server did not start")


def _require_http_ok(server: subprocess.Popen[bytes], port: int, deadline: float) -> None:
    if server.poll() is not None:
        raise RuntimeError("local web server exited before HTTP probe")
    connection = http.client.HTTPConnection(
        "127.0.0.1",
        port,
        timeout=_remaining(deadline, 5),
    )
    try:
        connection.request("GET", "/")
        response = connection.getresponse()
        response.read(1)
        if response.status != 200:
            raise RuntimeError("local web server root did not return HTTP 200")
    finally:
        connection.close()
    if server.poll() is not None:
        raise RuntimeError("local web server exited after HTTP probe")


def _stop_server(server: subprocess.Popen[bytes]) -> None:
    if server.poll() is None:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)


def _start_server(web_root: Path, deadline: float) -> tuple[subprocess.Popen[bytes], int]:
    last_error: Exception | None = None
    for attempt in range(1, 4):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = int(probe.getsockname()[1])
        server = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "http.server",
                str(port),
                "--bind",
                "127.0.0.1",
                "--directory",
                str(web_root),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            _wait_server(
                server,
                port,
                time.monotonic() + _remaining(deadline, 10),
            )
            _require_http_ok(server, port, deadline)
            return server, port
        except (
            OSError,
            RuntimeError,
            TimeoutError,
            http.client.HTTPException,
        ) as error:
            last_error = error
            log(f"capture web server attempt {attempt} failed")
            _stop_server(server)
    raise RuntimeError("local web server failed after 3 attempts") from last_error


def _capture_web_root(
    web_root: Path, destination: Path, deadline: float
) -> tuple[str, list[Path]]:
    if not NODE.is_file() or not CHROME.is_file() or not PLAYWRIGHT.is_dir():
        raise RuntimeError("browser capture toolchain unavailable")
    server, port = _start_server(web_root, deadline)
    try:
        with tempfile.TemporaryDirectory(prefix="appkit-pro-web-") as temporary:
            result = subprocess.run(
                [str(NODE), "-e", NODE_CAPTURE_SCRIPT, str(PLAYWRIGHT), f"http://127.0.0.1:{port}/", temporary, str(CHROME)],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=_remaining(deadline, 180),
            )
            for line in result.stderr.splitlines()[:128]:
                if line.startswith("capture interaction:"):
                    log(line[:512])
            if len(result.stdout) > 64 * 1024:
                raise RuntimeError("browser capture output too large")
            records = json.loads(result.stdout)
            if not isinstance(records, list) or not 1 <= len(records) <= 32:
                raise RuntimeError("browser capture returned no shots")
            selected = _select_web_records(records, Path(temporary))
            if not selected:
                raise RuntimeError("browser capture returned no useful stable shots")
            outputs: list[Path] = []
            for index, raw in enumerate(selected, start=1):
                output = destination / f"shot_{index}.png"
                _save_normalized(raw, output)
                outputs.append(output)
            return str(web_root), outputs
    finally:
        _stop_server(server)


def _capture_web(
    target: Path, destination: Path, warnings: list[str], deadline: float
) -> tuple[str, list[Path]] | None:
    log("capture ladder attempt: web capture")
    flutter = Path("/usr/local/bin/flutter")
    for app in _find_flutter_dirs(target, deadline)[:8]:
        log("capture web attempt: Flutter release build")
        if not flutter.is_file():
            warnings.append("Flutter app found but /usr/local/bin/flutter is unavailable")
            break
        try:
            subprocess.run(
                [str(flutter), "build", "web", "--release"],
                cwd=app,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=_remaining(deadline, MAX_FLUTTER_SECONDS),
            )
            built = app / "build" / "web"
            if not (built / "index.html").is_file():
                raise RuntimeError("Flutter build produced no index")
            return _capture_web_root(built, destination, deadline)
        except (OSError, RuntimeError, subprocess.SubprocessError, TimeoutError, json.JSONDecodeError):
            warnings.append("Flutter web build or capture failed")
            log("capture web Flutter attempt failed")
    for web_root in _find_built_web(target, deadline)[:8]:
        log("capture web attempt: existing built web surface")
        try:
            return _capture_web_root(web_root, destination, deadline)
        except (OSError, RuntimeError, subprocess.SubprocessError, TimeoutError, json.JSONDecodeError):
            warnings.append("built web surface capture failed")
            log("capture existing web attempt failed")
    log("capture ladder web: no capturable surface succeeded")
    return None


def _capture_synthetic(
    target: Path, destination: Path, values: dict[str, object], warnings: list[str]
) -> tuple[str, list[Path]]:
    log("capture ladder attempt: deterministic synthetic screens")
    warning = "synthetic screens: no exported screenshots found and web capture unavailable/failed"
    warnings.append(warning)
    outputs: list[Path] = []
    for index in (1, 2, 3):
        output = destination / f"shot_{index}.png"
        output.write_bytes(frame_compose.png_bytes(screens.make_screen(values, index)))
        outputs.append(output)
    return str(target), outputs


def _sanitize_source(source: str, target: Path) -> str:
    rendered = "".join(
        char for char in source if not unicodedata.category(char).startswith("C")
    )
    rendered = unicodedata.normalize("NFC", rendered)
    if "://" not in rendered:
        try:
            path = Path(rendered).resolve(strict=False)
            rendered = path.relative_to(target).as_posix()
        except (OSError, ValueError):
            pass
    return unicodedata.normalize("NFC", rendered[:4096]) or "."


def _report(
    ladder: str,
    source: str,
    warnings: list[str],
    shots: list[Path],
    target: Path,
) -> dict[str, object]:
    synthetic = ladder == "synthetic"
    records: list[dict[str, object]] = []
    for shot in shots:
        with Image.open(shot) as image:
            width, height = image.size
        records.append(
            {
                "file": shot.name,
                "height": height,
                "sha256": _sha256(shot),
                "source": "synthetic" if synthetic else "real",
                "width": width,
            }
        )
    report = {
        "counts": {
            "padded": len(records) if synthetic else 0,
            "real": 0 if synthetic else len(records),
        },
        "ladder": ladder,
        "shots": records,
        "source": _sanitize_source(source, target),
        "warnings": warnings,
    }
    pro_inputs.atomic_write_text(
        pro_inputs.data_root() / pro_inputs.REPORT_FILE,
        canonical_json(report) + "\n",
    )
    return report


def main() -> None:
    try:
        deadline = time.monotonic() + MAX_CAPTURE_SECONDS
        target = pro_inputs.load_target()
        values = pro_inputs.load_order()
        pro_inputs.require_rationale()
        destination = _reset_screens_dir()
        warnings: list[str] = []
        exported = _capture_exports(target, destination, deadline)
        if exported is not None:
            ladder = "exported"
            source, shots = exported
        else:
            web = _capture_web(target, destination, warnings, deadline)
            if web is not None:
                ladder = "web-capture"
                source, shots = web
            else:
                ladder = "synthetic"
                source, shots = _capture_synthetic(target, destination, values, warnings)
        report = _report(ladder, source, warnings, shots, target)
        digests = {
            str(item["file"]): str(item["sha256"])
            for item in report["shots"]
        }
        emit_result(
            "implemented",
            {
                "counts": report["counts"],
                "digests": digests,
                "ladder": ladder,
                "v": 1,
            },
        )
    except Exception as error:
        log(f"capture failed: {type(error).__name__}")
        emit_result("failed", failure_summary("capture_error"))


if __name__ == "__main__":
    main()
