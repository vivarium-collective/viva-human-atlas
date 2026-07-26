"""Composite generator wrapping `BiomodelDOCatalogStep`.

Builds the glucose-regulation biomodel-DO catalog (BioModels hits annotated
with HRA Uberon organ terms) and its inverse organ->models index, emitting
both via a RAMEmitter. Same state/emitter shape as `hra_steps.py` /
`pbg_biomodels.composites.compare_simulators`.
"""
from __future__ import annotations

from typing import Any, Dict

try:
    from viva_superpowers.composite_generator import composite_generator
except ModuleNotFoundError:
    from pbg_superpowers.composite_generator import composite_generator

CATALOG_STEP_ADDRESS = "local:BiomodelDOCatalogStep"


def build_glucose_biomodel_do_document(
    query: str = "glucose regulation", max_results: int = 25
) -> Dict[str, Any]:
    emit_schema = {"biomodel_dos": "node", "organ_to_models": "node"}
    state: Dict[str, Any] = {
        "biomodel_dos": [],
        "organ_to_models": {},
        "catalog_step": {
            "_type": "step",
            "address": CATALOG_STEP_ADDRESS,
            "config": {"query": query, "max_results": max_results},
            "inputs": {},
            "outputs": {
                "biomodel_dos": ["biomodel_dos"],
                "organ_to_models": ["organ_to_models"],
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
    name="glucose-biomodel-do",
    description=(
        "Search BioModels for a text query, annotate hits with HRA Uberon "
        "organ terms (synonym-match), and build the inverse organ->models "
        "index."
    ),
    parameters={
        "query": {
            "type": "string",
            "default": "glucose regulation",
            "description": "BioModels search term.",
        },
        "max_results": {
            "type": "integer",
            "default": 25,
            "description": "Max number of matching models to annotate.",
        },
    },
    default_n_steps=1,
)
def build_glucose_biomodel_do(
    core: Any = None, *, query: str = "glucose regulation", max_results: int = 25
) -> Dict[str, Any]:
    return build_glucose_biomodel_do_document(query=query, max_results=max_results)
