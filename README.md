# Appkit Demo

Appkit Demo is a deterministic, shell-only Gitmoot pipeline that turns a small typed input object into a ready-to-use app launch kit. It produces device-framed 1290×2796 marketing images, transparent device renders, English and Italian App Store copy, a responsive static landing page, hosted and editable legal documents, app icons, an Open Graph image, a handoff guide, a byte manifest, and a reproducible ZIP.

## Pipeline

`compose` and `content` are independent roots and can run concurrently. `compose` creates three polished app archetypes and device-framed images for each selected locale. `content` renders copy, a dark product landing page with relative transparent-phone assets, hosted legal HTML derived from the Markdown sources, editable legal Markdown, icons, social art, and the handoff README. `kit` depends on both roots, regenerates every artifact from the same inputs, verifies upstream canonical pixel/text digests, then writes `out/manifest.json` and `out/launch-kit.zip`.

Every stage command is fixed (`python3 tools/stage_<id>.py`). Inputs are read only from the bounded `GITMOOT_INPUT_*` variables. There is no network access, input interpolation into shell, shared stage filesystem, clock, randomness, or host/run metadata in artifacts. Each stage writes only beneath its own `out/` and emits exactly one final `gitmoot_result` JSON line on stdout; diagnostics go to stderr.

Image identity uses SHA-256 over canonical RGBA pixels. Text identity uses raw file bytes. Each stage summary includes the canonical input digest plus exact Pillow and zlib runtime fingerprints. The kit fails closed unless the v1 upstream context is complete, untruncated, successful, and exactly matches its regeneration. The manifest uses file-byte SHA-256, while the ZIP uses sorted stored entries, fixed 1980 metadata, and fixed Unix file attributes. Manifest SHA-256 values are per-host because PNG encoder bytes may vary with zlib; cross-stage image verification uses canonical RGBA identities. Unique kit artifacts fail closed above 15 MiB, and the reproducible ZIP has a separate 20 MiB ceiling.

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

The service is the proof-receipt demonstration: it attests typed-input admission and successful execution. Current Gitmoot bundles collect every stage's `out/` tree beneath `artifacts/<stage>/`; artifact digests are bound into the proof. The authoritative assembled kit is `artifacts/kit/launch-kit.zip`, while compose and content artifacts remain useful previews.

## Service delivery & privacy

Served bundles include the generated stage artifacts, with their digests bound into the proof by engine #1015. Public receipts strip caller inputs and stage summaries. On this demo deployment, a separate unexposable `appkit-notify` operator-notification pipeline also sends the service operator a Telegram message for each served order with the kit attached. Callers should therefore treat served kits as visible to the service operator.

## Launch-kit layout

The assembled ZIP contains `copy/<locale>/` metadata including release notes, `screenshots/<locale>/`, the `icons/` set, `landing/index.html`, transparent phones in `landing/assets/`, `landing/og.png`, hosted pages in `landing/legal/`, editable Markdown in `legal/`, and a generated `README.md` mapping every file to its launch destination. The landing ships in English in v1, and synthesized screens are used because the flat typed schema cannot accept real screenshot files. The manifest covers every generated artifact except itself and the ZIP; the ZIP includes the manifest.

## Defaults and validation

Only `app_name` is required. Locales default to `en,it`; color, tagline, three headlines, support email, and developer entity have deterministic defaults, including when an optional input is present but blank. Stages trim every value, reject overlong or non-NFC strings, all Unicode `C*` categories (including controls, zero-width/bidirectional characters, and surrogates), invalid colors, non-enumerated locale lists, and non-conservative ASCII email addresses.

Rendered App Store copy is deterministically capped to the platform fields: name 30 characters, subtitle 30, promotional text 170, and keywords 100. Truncation uses no ellipsis and strips trailing whitespace; the full validated values still flow to landing and legal outputs.
