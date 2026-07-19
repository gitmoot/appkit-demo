# Appkit Pro playbook for fable

For “marketing for my app at this repo,” run this exact personal workflow from the `appkit-demo` checkout:

```sh
mkdir -p /root/appkit-pro-data
printf '%s\n' /absolute/path/to/the/app-repo > /root/appkit-pro-data/target
python3 tools/pro_make_pipeline.py
gitmoot pipeline add appkit-pro.yaml --force
gitmoot pipeline add notify-pro.yaml --enable
gitmoot pipeline run appkit-pro
```

The kit persists at `/root/appkit-pro-data/kit/launch-kit.zip`. A successful run freshly replaces that `kit/` tree, so copy out anything you want to retain before running another order. When `target` changes, `pro_make_pipeline.py` clears the prior target's derived state and handoffs before rendering the spec; when the target is unchanged, it preserves them.

`/root/appkit-pro-data` is the default personal side channel. To isolate another run, export `APPKIT_PRO_DATA_DIR=/absolute/private/data-dir` before writing `target`, generating the pipeline, starting the worker, and running it. The generator binds that same directory into the produce-stage write grant and derive prompt, stamps the current pipeline-template digest plus resolved target there, and the deliverable plus Pro notification source move with it to `$APPKIT_PRO_DATA_DIR/kit/launch-kit.zip`. Regenerate and re-add the spec whenever the checked-in template or `target` changes; capture fails loudly with `stale_spec` or `switch_target_requires_regen` otherwise.

This is intentionally a personal, unexposable pipeline. Derive needs a static read grant for the target repository and both produce stages need a write grant for the selected data directory (default `/root/appkit-pro-data`), so the live home may surface sandbox-approval friction for those paths. Register `appkit-deriver` with model `gpt-5.6-sol` and effort `low`; the installed pipeline schema inherits those seat settings rather than accepting model or effort per stage. After derive, the isolated content produce job runs visibly in parallel with the shell capture-to-compose branch; landing joins both, produces the complete artifact tree, and kit depends only on landing. Capture prefers exported screenshots, then a stable browser rendering of a Flutter or built web surface, then deterministic synthesis. Compose persists the exact marketing frames and transparent devices under `framed/`; the content agent freshly writes grounded copy and legal sources under `content-agent/`. Landing validates every content file, substitutes a deterministic fallback for each malformed or missing file, generates icons itself, and records the per-file source in the README and manifest. Vendored nested repositories with their own `.git` entry are never searched for exports. Browser capture is not simulator capture, so native-only screens need exported images for full fidelity. The internal `appkit-notify-pro` chain sends the persistent ZIP using the existing Telegram env file and is also intentionally unexposable.

Compatibility note: the current development Gitmoot CLI upserts on plain `pipeline add` and may reject the documented `--force` flag. If so, rerun the add command without `--force`; do not change the generated spec.
