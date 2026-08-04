"""Composite generator wrapping `CoverageStep` in corpus mode (Task B).

Builds model coverage over the ASCT+B-3D crosswalk's anatomical structures,
crossed with the committed full-corpus catalog's organ->models index
(`coverage.build_corpus_coverage`, `datasets/biomodel_corpus_catalog.json`
from Task A — 1,096 curated BioModels, 82 organ-tagged), emitting both the
per-anatomical-structure `coverage` list and its `coverage_summary` via a
RAMEmitter. Reuses `CoverageStep` (same as `coverage_composite.py`'s
`model-coverage-3d`), just configured with `catalog_path` instead of
`query`/`max_results` — see `CoverageStep.update` for the branch.
"""
from __future__ import annotations

from typing import Any, Dict

try:
    from viva_superpowers.composite_generator import composite_generator
except ModuleNotFoundError:
    from pbg_superpowers.composite_generator import composite_generator

# Fully-dotted addresses (see `hra_steps.py` for why: lets vivarium-workbench
# resolve these Steps' description/contract without a live-built core).
COVERAGE_STEP_ADDRESS = "local:viva_human_atlas.coverage.CoverageStep"
CORPUS_CATALOG_STEP_ADDRESS = "local:viva_human_atlas.biomodel_do.CorpusCatalogStep"

DEFAULT_CATALOG_PATH = "datasets/biomodel_corpus_catalog.json"


def build_corpus_coverage_document(
    catalog_path: str = DEFAULT_CATALOG_PATH,
) -> Dict[str, Any]:
    emit_schema = {"coverage": "node", "coverage_summary": "node"}
    state: Dict[str, Any] = {
        "coverage": [],
        "coverage_summary": {},
        # In-graph catalog store: `corpus_catalog_step` produces it (from the
        # committed cache if present, else live), `coverage_step` consumes it.
        # This replaces the old hidden `config.catalog_path` file read.
        "corpus_catalog": {
            "biomodel_dos": [],
            "organ_index": {},
            "organ_to_models": {},
        },
        "corpus_catalog_step": {
            "_type": "step",
            "address": CORPUS_CATALOG_STEP_ADDRESS,
            "config": {"catalog_path": catalog_path},
            "inputs": {},
            "outputs": {"corpus_catalog": ["corpus_catalog"]},
        },
        "coverage_step": {
            "_type": "step",
            "address": COVERAGE_STEP_ADDRESS,
            "config": {},
            "inputs": {"catalog": ["corpus_catalog"]},
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
    name="corpus-coverage",
    description=(
        "Cross the ASCT+B-3D crosswalk's anatomical structures with the "
        "committed full-corpus catalog's organ->models index (1,096 "
        "curated BioModels, Task A) to mark model coverage, at organ "
        "granularity."
    ),
    parameters={
        "catalog_path": {
            "type": "string",
            "default": DEFAULT_CATALOG_PATH,
            "description": "Path to the committed full-corpus catalog JSON.",
        },
    },
    default_n_steps=1,
)
def build_corpus_coverage_composite(
    core: Any = None, *, catalog_path: str = DEFAULT_CATALOG_PATH
) -> Dict[str, Any]:
    return build_corpus_coverage_document(catalog_path=catalog_path)
