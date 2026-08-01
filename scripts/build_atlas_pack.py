"""Materialize the HRA Atlas Browser pack for the `hra-atlas-browser` study.

Builds the atlas manifest (all 50 GLB organs + model counts + BioModels
links) from the committed corpus catalog, plus full-corpus coverage, and
writes atlas.json/coverage.json/config.json alongside the committed
index.html/viewer.js under studies/hra-atlas-browser/viz/atlas/.

Run: PYTHONUTF8=1 .venv/bin/python scripts/build_atlas_pack.py
(network required — build_corpus_coverage hits the live ASCT+B-3D crosswalk).
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from viva_human_atlas.atlas_pack import build_atlas_manifest, write_atlas_pack
from viva_human_atlas.coverage import build_corpus_coverage, load_corpus_catalog

CATALOG_PATH = REPO_ROOT / "datasets" / "biomodel_corpus_catalog.json"
OUT_DIR = REPO_ROOT / "studies" / "hra-atlas-browser" / "viz" / "atlas"
# HRA "united" whole-body reference GLB for the overview landing view:
OVERVIEW_GLB = ("https://cdn.humanatlas.io/digital-objects/ref-organ/"
                "united-female/v1.4/assets/3d-vh-f-united.glb")


def main() -> None:
    catalog = load_corpus_catalog(str(CATALOG_PATH))
    manifest = build_atlas_manifest(catalog)
    print(f"  manifest: {manifest['summary']}")
    coverage = build_corpus_coverage(str(CATALOG_PATH))
    print(f"  coverage: {coverage['summary']}")
    out = write_atlas_pack(OUT_DIR, manifest=manifest, coverage=coverage,
                           overview_glb_url=OVERVIEW_GLB)
    print(f"Wrote atlas pack JSON to {out}")


if __name__ == "__main__":
    main()
