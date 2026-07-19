# Appkit Pro playbook for fable

For “marketing for my app at this repo,” run this exact personal workflow from the `appkit-demo` checkout:

```sh
mkdir -p /root/appkit-pro-data
printf '%s\n' /absolute/path/to/the/app-repo > /root/appkit-pro-data/target
python3 tools/pro_make_pipeline.py
gitmoot pipeline add appkit-pro.yaml --force
gitmoot pipeline run appkit-pro
```

The kit persists at `/root/appkit-pro-data/kit/launch-kit.zip`. A successful run freshly replaces that `kit/` tree, so copy out anything you want to retain before running another order.

`/root/appkit-pro-data` is the default personal side channel. To isolate another run, export `APPKIT_PRO_DATA_DIR=/absolute/private/data-dir` before writing `target`, generating the pipeline, starting the worker, and running it. The generator binds that same directory into the produce-stage write grant and derive prompt, and the deliverable moves with it to `$APPKIT_PRO_DATA_DIR/kit/launch-kit.zip`.

This is intentionally a personal, unexposable pipeline. The generated produce stage needs a static read grant for the target repository and a write grant for the selected data directory (default `/root/appkit-pro-data`), so the live home may surface sandbox-approval friction for those paths. Capture prefers exported screenshots, then a real browser rendering of a Flutter or built web surface, then deterministic synthesis. Vendored nested repositories with their own `.git` entry are never searched for exports. Browser capture is not simulator capture, so native-only screens need exported images for full fidelity.

Compatibility note: the current development Gitmoot CLI upserts on plain `pipeline add` and may reject the documented `--force` flag. If so, rerun the add command without `--force`; do not change the generated spec.
