#!/usr/bin/env bash
# Build the read-only dashboard SPA for this workspace (see the companion
# .github/workflows/publish-dashboard.yml). Scaffolded by
# `vivarium-workbench add-dashboard`; run it locally to preview the bundle.
set -euo pipefail
# Force UTF-8 I/O. Importing viva_human_atlas (via pbg_simbio/viva_superpowers)
# can flip the process's ambient locale encoding to ASCII; the publisher's
# investigation-notebook export then dies on non-ASCII bytes (em-dash 0xe2) and
# SILENTLY drops every notebook from the bundle. PYTHONUTF8=1 makes the export
# deterministic regardless of the caller's locale.
export PYTHONUTF8=1
WS_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$WS_ROOT/reports/published/dashboard}"
BASE_PATH="/viva-human-atlas/dashboard"
INTERACTIVE_URL="https://github.com/vivarium-collective/viva-human-atlas"
rm -rf "$OUT"
PYTHONPATH="$WS_ROOT${PYTHONPATH:+:$PYTHONPATH}" \
  vivarium-workbench-publish \
    --workspace "$WS_ROOT" \
    --out "$OUT" \
    --base-path "$BASE_PATH" \
    --interactive-url "$INTERACTIVE_URL"
find "$OUT" -name '*.map' -delete

# Guard: refuse to ship a broken registry. viva_human_atlas.core.build_core()
# imports pbg_biomodels (a sibling ../pbg-* path dep) plus its copasi/tellurium
# backends; if THIS env lacks them, the publisher bakes an `error` + empty
# registry into the bundle, i.e. a "None registered" snapshot with no
# processes/composites. Publishing that would clobber a good publish — so fail
# loudly instead. Build from an env where `from viva_human_atlas.core import
# build_core` works (the sibling ../pbg-* repos installed).
python - "$OUT" <<'PY'
import sys, json, pathlib
reg = pathlib.Path(sys.argv[1]) / "api" / "registry.json"
try:
    d = json.loads(reg.read_text())
except Exception as e:
    sys.exit(f"REFUSING TO PUBLISH: cannot read {reg}: {e}")
err, nproc = d.get("error"), len(d.get("processes") or [])
if err or nproc == 0:
    sys.exit(
        f"REFUSING TO PUBLISH: registry did not build (error={err!r}, "
        f"processes={nproc}). Install the sibling pbg-* deps so "
        f"`from viva_human_atlas.core import build_core` works."
    )
print(f"registry guard OK: {nproc} processes")
PY

# Copy the self-contained HRA viewer packs (studies/*/viz/hra) into the bundle.
# They are generated locally (scripts/build_hra_viewer_pack.py) and gitignored,
# and the static publisher doesn't copy arbitrary viz/ trees — so a README link
# like .../studies/model-coverage-3d/viz/hra/index.html 404s without this. A
# no-op when no packs are present (they're only built locally).
for pack in "$WS_ROOT"/studies/*/viz/hra; do
  [ -d "$pack" ] || continue
  slug=$(basename "$(dirname "$(dirname "$pack")")")
  dest="$OUT/studies/$slug/viz/hra"
  mkdir -p "$dest"; cp -R "$pack"/. "$dest/"
  echo "copied viewer pack: studies/$slug/viz/hra"
done

# Same for the self-contained HRA Computational Model Atlas packs (studies/*/viz/atlas).
# Unlike viz/hra these ARE committed, but the static publisher still doesn't
# copy arbitrary viz/ trees, so the atlas index.html would 404 without this.
for pack in "$WS_ROOT"/studies/*/viz/atlas; do
  [ -d "$pack" ] || continue
  slug=$(basename "$(dirname "$(dirname "$pack")")")
  dest="$OUT/studies/$slug/viz/atlas"
  mkdir -p "$dest"; cp -R "$pack"/. "$dest/"
  echo "copied viewer pack: studies/$slug/viz/atlas"
done

touch "$OUT/.nojekyll"
echo "built read-only dashboard bundle at $OUT ($(du -sh "$OUT" | cut -f1))"
