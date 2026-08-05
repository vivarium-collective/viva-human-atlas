"""Composite generator wrapping `BiomodelHraMapStep` -- make the
BioModels->HRA map DB available (cache-or-load) and emit its path + coverage
summary.

Same state/emitter shape as `ctpop_islet_composite.py`: a single Step feeding a
RAMEmitter, computed at update-time. The normal path is network-free (loads the
committed datasets/biomodel_hra_map.json).
"""
from __future__ import annotations

from typing import Any, Dict

try:
    from viva_superpowers.composite_generator import composite_generator
except ModuleNotFoundError:
    from pbg_superpowers.composite_generator import composite_generator

# Fully-dotted address (see `hra_steps.py`: lets vivarium-workbench resolve
# this Step's description/contract without a live-built core).
BIOMODEL_HRA_MAP_STEP_ADDRESS = "local:viva_human_atlas.biomodel_hra.BiomodelHraMapStep"


def build_biomodel_hra_map_document(
    db_path: str = "datasets/biomodel_hra_map.json",
    build_if_missing: bool = False,
) -> Dict[str, Any]:
    emit_schema = {
        "db_path": "node",
        "n_models": "node",
        "summary": "node",
    }
    state: Dict[str, Any] = {
        "db_path": "",
        "n_models": 0,
        "summary": {},
        "biomodel_hra_map_step": {
            "_type": "step",
            "address": BIOMODEL_HRA_MAP_STEP_ADDRESS,
            "config": {"db_path": db_path, "build_if_missing": build_if_missing},
            "inputs": {},
            "outputs": {
                "db_path": ["db_path"],
                "n_models": ["n_models"],
                "summary": ["summary"],
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
    name="biomodel-hra-map",
    description=(
        "Make the BioModels->HRA map DB available (cache-or-load) and emit its "
        "path, model count, and coverage summary. The DB -- a JSON array of "
        "per-model molecular ids, publication links, organism, and HRA "
        "organ/FTU/cell-type mapping (anatomy crosswalked from paper MeSH + "
        "BTO), with HRApop-linked models carrying measured cell-type "
        "populations -- is downloadable from the workspace Resources."
    ),
    parameters={
        "db_path": {
            "type": "string",
            "default": "datasets/biomodel_hra_map.json",
            "description": "Repo-relative path to the JSON-array DB (loaded network-free if present).",
        },
        "build_if_missing": {
            "type": "boolean",
            "default": False,
            "description": (
                "If the DB file is absent, run the live extraction over the "
                "curated BioModels corpus (slow, network). Off by default: the "
                "committed DB is expected to be present."
            ),
        },
    },
    default_n_steps=1,
)
def build_biomodel_hra_map_composite(
    core: Any = None,
    *,
    db_path: str = "datasets/biomodel_hra_map.json",
    build_if_missing: bool = False,
) -> Dict[str, Any]:
    return build_biomodel_hra_map_document(db_path=db_path, build_if_missing=build_if_missing)
