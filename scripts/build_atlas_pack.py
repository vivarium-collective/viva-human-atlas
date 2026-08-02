"""Materialize the HRA Atlas Browser pack for the `hra-atlas-browser` study.

Builds the atlas manifest (all 50 GLB organs + model counts + BioModels
links) from the UNION of the name-synonym catalog and the annotation
(SBML MIRIAM + BTO) catalog, so the viewer reflects the full model coverage
(167 models / 14 organs) with per-model provenance (name / annotation /
both). Writes atlas.json/config.json alongside the committed
index.html/viewer.js under studies/hra-atlas-browser/viz/atlas/.

Offline: reads the two committed catalogs; no network.
Run: PYTHONUTF8=1 .venv/bin/python scripts/build_atlas_pack.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from viva_human_atlas.atlas_pack import build_atlas_manifest, merge_catalogs, write_atlas_pack
from viva_human_atlas.coverage import load_corpus_catalog

CATALOG_PATH = REPO_ROOT / "datasets" / "biomodel_corpus_catalog.json"
ANNOTATION_CATALOG_PATH = REPO_ROOT / "datasets" / "biomodel_annotation_catalog.json"
OUT_DIR = REPO_ROOT / "studies" / "hra-atlas-browser" / "viz" / "atlas"
# HRA "united" whole-body reference GLB (single-sex) for an optional overview:
OVERVIEW_GLB = ("https://cdn.humanatlas.io/digital-objects/ref-organ/"
                "united-female/v1.4/assets/3d-vh-f-united.glb")


def main() -> None:
    name_catalog = load_corpus_catalog(str(CATALOG_PATH))
    annotation_catalog = json.loads(
        ANNOTATION_CATALOG_PATH.read_text(encoding="utf-8"))["catalog"]
    merged, provenance = merge_catalogs(name_catalog, annotation_catalog)
    manifest = build_atlas_manifest(merged, provenance=provenance)
    print(f"  union manifest: {manifest['summary']}")
    # coverage.json is retained (empty) for pack-shape compatibility; the
    # current viewer reads only atlas.json.
    out = write_atlas_pack(OUT_DIR, manifest=manifest,
                           coverage={"coverage": [], "summary": {}},
                           overview_glb_url=OVERVIEW_GLB)
    print(f"Wrote atlas pack JSON to {out}")


if __name__ == "__main__":
    main()
