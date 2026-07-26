"""Composite generator wrapping `CoverageStep`.

Builds model coverage over the ASCT+B-3D crosswalk's anatomical structures,
crossed with the biomodel-DO organ->models index, emitting both the
per-anatomical-structure `coverage` list and its `coverage_summary` via a
RAMEmitter. Same state/emitter shape as `hra_steps.py` /
`biomodel_do_composite.py`.
"""
from __future__ import annotations

from typing import Any, Dict

try:
    from viva_superpowers.composite_generator import composite_generator
except ModuleNotFoundError:
    from pbg_superpowers.composite_generator import composite_generator

# Fully-dotted address (see `hra_steps.py` for why: lets vivarium-workbench
# resolve this Step's description/contract without a live-built core).
COVERAGE_STEP_ADDRESS = "local:viva_human_atlas.coverage.CoverageStep"


def build_model_coverage_3d_document(
    query: str = "glucose regulation", max_results: int = 25
) -> Dict[str, Any]:
    emit_schema = {"coverage": "node", "coverage_summary": "node"}
    state: Dict[str, Any] = {
        "coverage": [],
        "coverage_summary": {},
        "coverage_step": {
            "_type": "step",
            "address": COVERAGE_STEP_ADDRESS,
            "config": {"query": query, "max_results": max_results},
            "inputs": {},
            "outputs": {
                "coverage": ["coverage"],
                "coverage_summary": ["coverage_summary"],
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
    name="model-coverage-3d",
    description=(
        "Cross the ASCT+B-3D crosswalk's anatomical structures with the "
        "biomodel-DO organ->models index to mark model coverage, at organ "
        "granularity."
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
def build_model_coverage_3d(
    core: Any = None, *, query: str = "glucose regulation", max_results: int = 25
) -> Dict[str, Any]:
    return build_model_coverage_3d_document(query=query, max_results=max_results)
