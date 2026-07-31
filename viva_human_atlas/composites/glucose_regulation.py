"""glucose-regulation composite: search BioModels, compare COPASI vs Tellurium.

Reuses pbg-biomodels' fetch->multi-engine->all-pairs-comparison machinery; the
only workspace-specific piece is turning a text query into the model-id list.
"""
from __future__ import annotations

from typing import Any, Dict

try:
    from viva_superpowers.composite_generator import composite_generator
except ModuleNotFoundError:
    from pbg_superpowers.composite_generator import composite_generator

from viva_biomodels.composites.compare_simulators import (
    build_compare_document,
    run_comparison,
)

from viva_human_atlas.biomodels_search import search_biomodels


@composite_generator(
    name="glucose-regulation",
    description=(
        "Query BioModels for a text term (default 'glucose regulation'), then "
        "run every matching model under COPASI and Tellurium and score their "
        "agreement (all-pairs nRMSE)."
    ),
    parameters={
        "query": {
            "type": "string",
            "default": "glucose regulation",
            "description": "BioModels search term.",
        },
        "max_results": {
            "type": "integer",
            "default": 10,
            "description": "Max number of matching models to compare.",
        },
        "simulators": {
            "type": "string",
            "default": "copasi,tellurium",
            "description": "Comma-separated simulator names.",
        },
    },
    default_n_steps=1,
)
def build_glucose_regulation(
    core: Any = None,
    *,
    query: str = "glucose regulation",
    max_results: int = 10,
    simulators: str = "copasi,tellurium",
) -> Dict[str, Any]:
    ids = search_biomodels(query, max_results)
    return build_compare_document(ids, simulators=simulators)


def run_glucose_regulation(
    query: str = "glucose regulation",
    max_results: int = 25,
    simulators: str = "copasi,tellurium",
    *,
    on_progress=None,
) -> Dict[str, Any]:
    """Search then run the isolated per-model comparison; returns the report dict."""
    ids = search_biomodels(query, max_results)
    return run_comparison(ids, simulators=simulators, on_progress=on_progress)
