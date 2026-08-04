"""Composite generator wrapping `FtuModelCoverageStep` (Katy Boerner's "do
any existing models try to model FTUs?" follow-up).

Matches the committed full-corpus catalog's biomodel names against the
curated `HRA_FTUS` list (`ftu_coverage.build_ftu_model_coverage`,
`datasets/biomodel_corpus_catalog.json` from Task A) by synonym substring,
emitting both the per-FTU `ftu_coverage` list and its `ftu_coverage_summary`
via a RAMEmitter. Same state/emitter shape as `corpus_coverage_composite.py`.
"""
from __future__ import annotations

from typing import Any, Dict

try:
    from viva_superpowers.composite_generator import composite_generator
except ModuleNotFoundError:
    from pbg_superpowers.composite_generator import composite_generator

# Fully-dotted addresses (see `hra_steps.py` for why: lets vivarium-workbench
# resolve these Steps' description/contract without a live-built core).
FTU_COVERAGE_STEP_ADDRESS = "local:viva_human_atlas.ftu_coverage.FtuModelCoverageStep"
CORPUS_CATALOG_STEP_ADDRESS = "local:viva_human_atlas.biomodel_do.CorpusCatalogStep"

DEFAULT_CATALOG_PATH = "datasets/biomodel_corpus_catalog.json"


def build_ftu_model_coverage_document(
    catalog_path: str = DEFAULT_CATALOG_PATH,
) -> Dict[str, Any]:
    emit_schema = {"ftu_coverage": "node", "ftu_coverage_summary": "node"}
    state: Dict[str, Any] = {
        "ftu_coverage": [],
        "ftu_coverage_summary": {},
        # In-graph catalog store: produced by `corpus_catalog_step` (committed
        # cache if present, else live), consumed by `ftu_coverage_step` —
        # replaces the old hidden `config.catalog_path` file read.
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
        "ftu_coverage_step": {
            "_type": "step",
            "address": FTU_COVERAGE_STEP_ADDRESS,
            "config": {},
            "inputs": {"catalog": ["corpus_catalog"]},
            "outputs": {
                "ftu_coverage": ["ftu_coverage"],
                "ftu_coverage_summary": ["ftu_coverage_summary"],
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
    name="ftu-model-coverage",
    description=(
        "Match the committed full-corpus catalog's biomodel names against "
        "a curated list of HRA functional tissue units (FTUs) by synonym "
        "substring, answering which FTUs any curated model already claims "
        "to model."
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
def build_ftu_model_coverage_composite(
    core: Any = None, *, catalog_path: str = DEFAULT_CATALOG_PATH
) -> Dict[str, Any]:
    return build_ftu_model_coverage_document(catalog_path=catalog_path)
