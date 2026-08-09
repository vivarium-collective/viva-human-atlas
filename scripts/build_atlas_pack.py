"""Materialize the HRA Computational Model Atlas pack for the `hra-atlas-browser` study.

Builds the atlas manifest (all 50 GLB organs + model counts + BioModels links)
from the BioModels->HRA map DB (Phase 1), and places each model at the organ
SUBREGION(s) its cell types / FTUs resolve to (HRApop per-AS cell populations +
the ASCT+B-3D crosswalk), falling back to the whole organ. Writes
atlas.json/config.json alongside the committed index.html/viewer.js under
studies/hra-atlas-browser/viz/atlas/.

Thin CLI over `atlas_pack.build_and_write_atlas` (the `AtlasBrowserStep` shares
the same orchestrator). Offline: reads committed datasets; no network.
Run: PYTHONUTF8=1 .venv/bin/python scripts/build_atlas_pack.py
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from viva_human_atlas.atlas_pack import build_and_write_atlas  # noqa: E402

CATALOG_PATH = REPO_ROOT / "datasets" / "biomodel_corpus_catalog.json"
DB_PATH = REPO_ROOT / "datasets" / "model_hra_map.json"
OUT_DIR = REPO_ROOT / "studies" / "hra-atlas-browser" / "viz" / "atlas"


def main() -> None:
    result = build_and_write_atlas(
        db_path=str(DB_PATH), catalog_path=str(CATALOG_PATH), out_dir=OUT_DIR)
    print(f"  manifest: {result['summary']}")
    print(f"  subregion placement: {result['placement_stats']}")
    print(f"Wrote atlas pack JSON to {OUT_DIR}")


if __name__ == "__main__":
    main()
