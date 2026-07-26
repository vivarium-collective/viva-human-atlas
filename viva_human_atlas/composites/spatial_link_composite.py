"""Composite generator wrapping `SpatialLinkStep`.

Joins biomodel-DO organs to ASCT+B-3D crosswalk anatomical-structure nodes on
shared Uberon CURIE, emitting both the per-link `links` list and its
`spatial_link_summary` via a RAMEmitter. Same state/emitter shape as
`hra_steps.py` / `biomodel_do_composite.py` / `coverage_composite.py`.
"""
from __future__ import annotations

from typing import Any, Dict

try:
    from viva_superpowers.composite_generator import composite_generator
except ModuleNotFoundError:
    from pbg_superpowers.composite_generator import composite_generator

# Fully-dotted address (see `hra_steps.py` for why: lets vivarium-workbench
# resolve this Step's description/contract without a live-built core).
SPATIAL_LINK_STEP_ADDRESS = "local:viva_human_atlas.spatial_link.SpatialLinkStep"


def build_spatial_linkage_document(
    query: str = "glucose regulation", max_results: int = 25
) -> Dict[str, Any]:
    emit_schema = {"links": "node", "spatial_link_summary": "node"}
    state: Dict[str, Any] = {
        "links": [],
        "spatial_link_summary": {},
        "spatial_link_step": {
            "_type": "step",
            "address": SPATIAL_LINK_STEP_ADDRESS,
            "config": {"query": query, "max_results": max_results},
            "inputs": {},
            "outputs": {
                "links": ["links"],
                "spatial_link_summary": ["spatial_link_summary"],
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
    name="spatial-linkage",
    description=(
        "Join biomodel-DO organ annotations to ASCT+B-3D crosswalk "
        "anatomical-structure nodes on shared Uberon CURIE, so each linked "
        "GLB scene node can be colored/labeled by its model."
    ),
    parameters={
        "query": {
            "type": "string",
            "default": "glucose regulation",
            "description": "BioModels search term feeding the biomodel-DO catalog.",
        },
        "max_results": {
            "type": "integer",
            "default": 25,
            "description": "Max number of matching models to annotate.",
        },
    },
    default_n_steps=1,
)
def build_spatial_linkage(
    core: Any = None, *, query: str = "glucose regulation", max_results: int = 25
) -> Dict[str, Any]:
    return build_spatial_linkage_document(query=query, max_results=max_results)
