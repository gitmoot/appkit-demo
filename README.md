# Appkit Demo

Appkit Demo is a deterministic, shell-only Gitmoot pipeline that turns a small typed input object into an app launch kit. It produces device-framed 1290×2796 marketing images, English and Italian App Store copy, a single-file landing page, Terms and Privacy documents, a byte manifest, and a reproducible ZIP.

## Pipeline

`compose` and `content` are independent roots and can run concurrently. `compose` creates three synthetic app screens and device-framed images for each selected locale. `content` renders copy, landing, and legal files. `kit` depends on both roots, regenerates every artifact from the same inputs, verifies upstream canonical pixel/text digests, then writes `out/manifest.json` and `out/launch-kit.zip`.

Every stage command is fixed (`python3 tools/stage_<id>.py`). Inputs are read only from the bounded `GITMOOT_INPUT_*` variables. There is no network access, input interpolation into shell, shared stage filesystem, clock, randomness, or host/run metadata in artifacts. Each stage writes only beneath its own `out/` and emits exactly one final `gitmoot_result` JSON line on stdout; diagnostics go to stderr.

Image identity uses SHA-256 over canonical RGBA pixels. Text identity uses raw file bytes. Each stage summary includes the canonical input digest and exact Pillow fingerprint. The kit fails closed unless the v1 upstream context is complete, untruncated, successful, and exactly matches its regeneration. The manifest uses file-byte SHA-256, while the ZIP uses sorted stored entries, fixed 1980 metadata, and fixed Unix file attributes.

## Register and run

Register the checked-in DAG:

```sh
gitmoot pipeline add pipeline.yaml
gitmoot pipeline run appkit-demo
```

The bare manual `pipeline run` is a graph/contract smoke and intentionally fails input validation because `app_name` is required. Typed values are admitted through the service seam; Gitmoot's manual-run command does not accept a typed payload. For a tangible local kit, run the three scripts in separate scratch directories, retain the two root summary strings in a v1 upstream-context JSON file, and invoke `stage_kit.py` with that file path. The resulting ZIP is in the kit scratch directory at `out/launch-kit.zip`.

## Serve the typed pipeline

```sh
gitmoot pipeline expose --schema schema.json appkit-demo
gitmoot pipeline serve
```

Use the one-time bearer token printed by `expose`:

```sh
curl -sS -X POST http://127.0.0.1:8792/v1/pipelines/appkit-demo/runs \
  -H 'Authorization: Bearer YOUR_TOKEN' \
  -H 'Content-Type: application/json' \
  --data '{"app_name":"DemoApp","brand_color":"#635bff","locales":"en,it"}'
```

The service is the proof-receipt demonstration: it attests typed-input admission and successful execution. The public receipt strips stage summaries, so it does not cryptographically identify the ZIP. A PaaS v1 frozen bundle contains proof material and the pipeline definition, not generated artifacts. The tangible ZIP is available only from a local stage run where its output directory is retained.

## Defaults and validation

Only `app_name` is required. Locales default to `en,it`; color, tagline, three headlines, support email, and developer entity have deterministic defaults. Stages trim every value, reject overlong or non-NFC strings, control/format characters (including zero-width and bidirectional controls), invalid colors, non-enumerated locale lists, and non-conservative ASCII email addresses.
