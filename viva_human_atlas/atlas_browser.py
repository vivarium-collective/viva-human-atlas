"""`AtlasBrowserStep` — regenerate the HRA Atlas Browser pack from the
BioModels->HRA map DB (Phase 1), with organ-subregion placement.

This is the "full redo" of the Atlas Browser generation as a process-bigraph
Step: it consumes the biomodel-hra-map DB (the cached JSON the
`BiomodelHraMapStep` produces / loads) instead of the old name+annotation
catalogs, and drives model placement UP from each model's cell types + FTUs to
the specific organ SUBREGIONS (anatomical structures) they belong to — falling
back to the whole organ where no subregion resolves. It writes the atlas pack
(atlas.json / config.json / coverage.json) alongside the committed
index.html/viewer.js under a study's `viz/atlas/`.

Offline: reads the committed model_hra_map.json, the corpus catalog (for the
50 GLB `organ_index`), HRApop's per-AS cell populations, and the cached ASCT+B-3D
crosswalk. Emits the manifest summary + placement stats (not the pack itself).
"""
from __future__ import annotations

from pathlib import Path

from process_bigraph import Step

from viva_human_atlas.atlas_pack import build_and_write_atlas

_REPO = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = _REPO / "datasets" / "biomodel_corpus_catalog.json"
DEFAULT_OUT_DIR = _REPO / "studies" / "hra-atlas-browser" / "viz" / "atlas"


class AtlasBrowserStep(Step):
    """Step: build the HRA Atlas Browser pack from the biomodel-hra-map DB with
    cell-type/FTU-driven organ-subregion placement (whole-organ fallback)."""

    description = (
        "Regenerate the HRA Atlas Browser pack from the BioModels->HRA map DB: "
        "place each model at the organ subregion(s) its cell types / FTUs "
        "resolve to (via HRApop per-AS cell populations + the ASCT+B-3D "
        "crosswalk), falling back to the whole organ. Writes atlas.json/"
        "config.json to the study's viz/atlas/; emits the manifest summary + "
        "placement stats."
    )

    config_schema = {
        "db_path": "string",
        "catalog_path": "string",
        "out_dir": "string",
        "enrichment": "float",
        "top_k": "integer",
        "cross_organ_max": "integer",
    }

    def inputs(self):
        return {}

    def outputs(self):
        return {"summary": "tree", "placement_stats": "tree", "out_dir": "string"}

    def update(self, inputs):
        out_dir = self.config.get("out_dir") or str(DEFAULT_OUT_DIR)
        place_kw = {}
        if self.config.get("enrichment"):
            place_kw["enrichment"] = float(self.config["enrichment"])
        if self.config.get("top_k"):
            place_kw["top_k"] = int(self.config["top_k"])
        if self.config.get("cross_organ_max") is not None and self.config.get("cross_organ_max") != "":
            place_kw["cross_organ_max"] = int(self.config["cross_organ_max"])
        result = build_and_write_atlas(
            db_path=self.config.get("db_path") or None,
            catalog_path=self.config.get("catalog_path") or str(DEFAULT_CATALOG),
            out_dir=out_dir,
            **place_kw,
        )
        return {
            "summary": result["summary"],
            "placement_stats": result["placement_stats"],
            "out_dir": str(out_dir),
        }


AtlasBrowserStep.contract = {
    "summary": AtlasBrowserStep.description,
    "outputs": {
        "summary": "Atlas manifest summary: n_organs, n_modeled, "
                   "n_models_distinct, n_subregions, n_organs_with_subregions.",
        "placement_stats": "Subregion placement stats: n_subregion_models, "
                           "n_ftu_models, n_cell_type_models, n_placements.",
        "out_dir": "Directory the atlas pack (atlas.json/config.json) was written to.",
    },
    "assumptions": [
        "Subregion placement is specificity-gated and mostly within-organ: a "
        "cell type places a model at a subregion only where it is enriched "
        "above the organ average, and FTUs place only when the FTU has a GLB "
        "mesh in the ASCT+B-3D crosswalk (most FTUs do not). Cross-organ "
        "placement is off by default. So most models fall back to the whole "
        "organ — subregion resolution is real but modest, bounded by HRApop's "
        "coarse anatomical-structure granularity and the 3D crosswalk.",
    ],
}
