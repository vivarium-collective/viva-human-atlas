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

# viva_biomodels (the sibling process-package) provides the compare machinery,
# but it is only needed to actually RUN a comparison — not to import this module
# or register the composite's spec. The read-only dashboard/report publish
# installs only vivarium-workbench + this workspace (`uv pip install -e .
# --no-deps`) and best-effort git-installs the sibling process-packages; if that
# install flakes (e.g. the pbg->viva rebrand naming mismatch surfacing anywhere
# in the live @main dependency graph), viva_biomodels is absent. A hard
# top-level `from viva_biomodels...` would then make `import viva_human_atlas`
# itself raise, which crashes build_core() BEFORE its own ImportError guard can
# degrade to spec-only rendering — collapsing the whole registry to 0 processes
# and tripping the publish guard (red CI, "could not import viva_human_atlas.core:
# No module named 'viva_biomodels'"). So guard the import: keep the names bound
# (to the real functions when present, else None) so the module still imports and
# the composite spec stays discoverable, and resolve lazily at call time.
try:
    from viva_biomodels.composites.compare_simulators import (
        build_compare_document,
        run_comparison,
    )
except ModuleNotFoundError:  # sibling process-package unavailable (e.g. --no-deps publish)
    build_compare_document = None  # type: ignore[assignment]
    run_comparison = None  # type: ignore[assignment]

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
    build = build_compare_document
    if build is None:  # sibling absent at import; try now for a clear error
        from viva_biomodels.composites.compare_simulators import build_compare_document as build
    ids = search_biomodels(query, max_results)
    return build(ids, simulators=simulators)


def run_glucose_regulation(
    query: str = "glucose regulation",
    max_results: int = 25,
    simulators: str = "copasi,tellurium",
    *,
    on_progress=None,
) -> Dict[str, Any]:
    """Search then run the isolated per-model comparison; returns the report dict."""
    run = run_comparison
    if run is None:  # sibling absent at import; try now for a clear error
        from viva_biomodels.composites.compare_simulators import run_comparison as run
    ids = search_biomodels(query, max_results)
    return run(ids, simulators=simulators, on_progress=on_progress)
