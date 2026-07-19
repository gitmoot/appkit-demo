Extract launch-kit metadata from the target repository. This is extraction, not invention.

Read the repository made available by the stage's `reads` grant. Write exactly two files and no others:

1. `/root/appkit-pro-data/order.yaml`, a flat YAML mapping containing only grounded values from this exact allowlist. Omit any key you cannot support from a file.
   - `app_name` (maximum 60 characters): prefer a store or marketing display name under `docs/store`, `store`, or site content; then a web app `appName`; then a humanized `pubspec.yaml` or package name.
   - `brand_color` (exact lowercase `#rrggbb`): extract from theme tokens or the design system. Quote this YAML value.
   - `tagline` (maximum 80 characters): use site content, README text explicitly labeled as a tagline, or a store subtitle.
   - `headline_1`, `headline_2`, `headline_3` (maximum 60 characters each): use feature copy, README bullets, or store descriptions. Keep each as a short marketing line, not a sentence. Omit missing positions rather than filling them.
   - `support_email` (maximum 80 characters): include only if a file states it.
   - `developer_entity` (maximum 80 characters): include only if a file states it.
2. `/root/appkit-pro-data/rationale.md`, one line for every emitted key in the form `key: relative/source/file — concise extraction reason`.

Use deterministic repository evidence only. Do not use the network. Do not infer a company, email, color, tagline, or feature that is not written in a file. Do not edit the target repository. Prefer omission because downstream defaults fill gaps. Use one YAML `key: value` per line, with string scalars only and no nested objects, lists, aliases, tags, or block scalars. Return the normal Gitmoot implemented result only after both files have been written.
