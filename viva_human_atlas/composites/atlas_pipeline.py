"""Composite generator: the end-to-end HRA Computational Model Atlas build
pipeline, wired as a connectable Step DAG.

  ModelHarvestStep ─┐                                    (per-stage db_path stores)
                    ├→ GeneEnrichStep → HRApopEnrichStep → ComputationalModelAtlas → atlas.json
  AsctbTablesStep ──┘

live=false (default) replays the committed datasets and regenerates atlas.json
identically; live=true re-harvests/re-enriches from external APIs.
"""
from __future__ import annotations
from typing import Any, Dict

try:
    from viva_superpowers.composite_generator import composite_generator
except ModuleNotFoundError:
    from pbg_superpowers.composite_generator import composite_generator

HARVEST = "local:viva_human_atlas.model_harvest.ModelHarvestStep"
ASCTB = "local:viva_human_atlas.asctb_tables.AsctbTablesStep"
GENE = "local:viva_human_atlas.enrich.GeneEnrichStep"
HRAPOP = "local:viva_human_atlas.enrich_hrapop.HRApopEnrichStep"
ATLAS = "local:viva_human_atlas.atlas_browser.ComputationalModelAtlas"

DEFAULT_OUT_DIR = "studies/hra-atlas-browser/viz/atlas"


def build_atlas_pipeline_document(out_dir: str = DEFAULT_OUT_DIR,
                                  live: bool = False) -> Dict[str, Any]:
    emit_schema = {"atlas_summary": "tree", "placement_stats": "tree",
                   "gene_enrich_summary": "tree", "hrapop_summary": "tree"}
    state: Dict[str, Any] = {
        # stores wiring the DAG
        "db_harvested": "", "asctb_path": "", "db_gene": "", "db_hrapop": "",
        "atlas_summary": {}, "placement_stats": {},
        "gene_enrich_summary": {}, "hrapop_summary": {},
        "harvest_step": {
            "_type": "step", "address": HARVEST,
            "config": {"build_if_missing": bool(live)},
            "inputs": {},
            "outputs": {"db_path": ["db_harvested"]},
        },
        "asctb_step": {
            "_type": "step", "address": ASCTB,
            "config": {"force": bool(live)},
            "inputs": {},
            "outputs": {"out_path": ["asctb_path"]},
        },
        "gene_enrich_step": {
            "_type": "step", "address": GENE,
            "config": {"live": bool(live)},
            "inputs": {"db_path": ["db_harvested"], "asctb_path": ["asctb_path"]},
            "outputs": {"db_path": ["db_gene"], "summary": ["gene_enrich_summary"]},
        },
        "hrapop_step": {
            "_type": "step", "address": HRAPOP,
            "config": {"live": bool(live)},
            "inputs": {"db_path": ["db_gene"]},
            "outputs": {"db_path": ["db_hrapop"], "summary": ["hrapop_summary"]},
        },
        "atlas_step": {
            "_type": "step", "address": ATLAS,
            "config": {"out_dir": out_dir},
            "inputs": {"db_path": ["db_hrapop"]},
            "outputs": {"summary": ["atlas_summary"], "placement_stats": ["placement_stats"]},
        },
        "emitter": {
            "_type": "step", "address": "local:RAMEmitter",
            "config": {"emit": emit_schema},
            "inputs": {k: [k] for k in emit_schema},
        },
    }
    return {"state": state, "run_steps_on_init": True}


@composite_generator(
    name="hra-atlas-pipeline",
    description=(
        "End-to-end HRA Computational Model Atlas build: harvest models -> gene/"
        "organism enrichment -> HRApop linkage -> atlas pack, wired as a "
        "connectable Step DAG. Offline (live=false) it replays the committed "
        "datasets and regenerates atlas.json identically."
    ),
    parameters={
        "out_dir": {"type": "string", "default": DEFAULT_OUT_DIR,
                    "description": "Directory the atlas pack is written to."},
        "live": {"type": "boolean", "default": False,
                 "description": "Re-harvest/re-enrich from external APIs (may drift)."},
    },
    default_n_steps=1,
)
def build_atlas_pipeline(core: Any = None, *, out_dir: str = DEFAULT_OUT_DIR,
                         live: bool = False) -> Dict[str, Any]:
    return build_atlas_pipeline_document(out_dir=out_dir, live=live)
