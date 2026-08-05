"""Composite generator wrapping `AtlasBrowserStep` — the "full redo" of the HRA
Atlas Browser generation: consume the BioModels->HRA map DB (Phase 1) and place
models at organ SUBREGIONS driven by their cell types + FTUs (whole-organ
fallback), writing the atlas pack the browser renders.

Same state/emitter shape as `ctpop_islet_composite.py`: a single Step feeding a
RAMEmitter, computed at update-time. Offline (reads committed datasets).
"""
from __future__ import annotations

from typing import Any, Dict

try:
    from viva_superpowers.composite_generator import composite_generator
except ModuleNotFoundError:
    from pbg_superpowers.composite_generator import composite_generator

ATLAS_BROWSER_STEP_ADDRESS = "local:viva_human_atlas.atlas_browser.AtlasBrowserStep"


def build_atlas_browser_document(
    db_path: str = "datasets/biomodel_hra_map.json",
    enrichment: float = 1.25,
    cross_organ_max: int = 0,
) -> Dict[str, Any]:
    emit_schema = {"summary": "node", "placement_stats": "node", "out_dir": "node"}
    state: Dict[str, Any] = {
        "summary": {},
        "placement_stats": {},
        "out_dir": "",
        "atlas_browser_step": {
            "_type": "step",
            "address": ATLAS_BROWSER_STEP_ADDRESS,
            "config": {"db_path": db_path, "enrichment": enrichment,
                       "cross_organ_max": cross_organ_max},
            "inputs": {},
            "outputs": {
                "summary": ["summary"],
                "placement_stats": ["placement_stats"],
                "out_dir": ["out_dir"],
            },
        },
        "emitter": {
            "_type": "step",
            "address": "local:RAMEmitter",
            "config": {"emit": emit_schema},
            "inputs": {k: [k] for k in emit_schema},
        },
    }
    return {"state": state, "run_steps_on_init": True}


@composite_generator(
    name="hra-atlas-browser",
    description=(
        "Regenerate the HRA Atlas Browser pack from the BioModels->HRA map DB "
        "(Phase 1), placing each model at the organ subregion(s) its cell "
        "types / FTUs resolve to — via HRApop per-AS cell populations + the "
        "ASCT+B-3D crosswalk — and falling back to the whole organ where no "
        "subregion resolves. Writes atlas.json/config.json for the browser."
    ),
    parameters={
        "db_path": {
            "type": "string",
            "default": "datasets/biomodel_hra_map.json",
            "description": "Repo-relative path to the biomodel-hra-map DB (loaded network-free).",
        },
        "enrichment": {
            "type": "float",
            "default": 1.25,
            "description": (
                "Cell-type enrichment gate: an anatomical structure gets a "
                "model only where the model's cell type is over-represented by "
                "this factor vs the organ average (higher = more specific, "
                "fewer subregion placements)."
            ),
        },
        "cross_organ_max": {
            "type": "integer",
            "default": 0,
            "description": (
                "Max extra (untagged) organs a model's cell types may place it "
                "into. 0 (default) keeps placement within the model's tagged "
                "organs, avoiding generic-cell-type smear."
            ),
        },
    },
    default_n_steps=1,
)
def build_atlas_browser_composite(
    core: Any = None,
    *,
    db_path: str = "datasets/biomodel_hra_map.json",
    enrichment: float = 1.25,
    cross_organ_max: int = 0,
) -> Dict[str, Any]:
    return build_atlas_browser_document(
        db_path=db_path, enrichment=enrichment, cross_organ_max=cross_organ_max)
