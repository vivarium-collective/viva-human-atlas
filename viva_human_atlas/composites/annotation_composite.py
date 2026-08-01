"""Composite generators wrapping `annotation_coverage.py`'s Steps
(Task 5): `annotation-organ-matching` (mechanism/provenance summary of the
committed annotation catalog) and `annotation-recall-gain` (the
annotation-vs-name-only comparison, `annotation_gain.compare_catalogs`).
Same shape/pattern as `coverage_composite.py`/`corpus_coverage_composite.py`.
"""
from __future__ import annotations

from typing import Any, Dict

try:
    from viva_superpowers.composite_generator import composite_generator
except ModuleNotFoundError:
    from pbg_superpowers.composite_generator import composite_generator

# Fully-dotted addresses (see `hra_steps.py` for why: lets
# vivarium-workbench resolve these Steps' description/contract without a
# live-built core).
ANNOTATION_MATCH_STEP_ADDRESS = "local:viva_human_atlas.annotation_coverage.AnnotationMatchStep"
RECALL_GAIN_STEP_ADDRESS = "local:viva_human_atlas.annotation_coverage.RecallGainStep"

DEFAULT_ANNOTATION_CATALOG_PATH = "datasets/biomodel_annotation_catalog.json"
DEFAULT_NAME_CATALOG_PATH = "datasets/biomodel_corpus_catalog.json"


def build_annotation_organ_matching_document(
    catalog_path: str = DEFAULT_ANNOTATION_CATALOG_PATH,
) -> Dict[str, Any]:
    emit_schema = {"annotation_summary": "node", "sample_provenance": "node"}
    state: Dict[str, Any] = {
        "annotation_summary": {},
        "sample_provenance": [],
        "annotation_match_step": {
            "_type": "step",
            "address": ANNOTATION_MATCH_STEP_ADDRESS,
            "config": {"catalog_path": catalog_path},
            "inputs": {},
            "outputs": {
                "annotation_summary": ["annotation_summary"],
                "sample_provenance": ["sample_provenance"],
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
    name="annotation-organ-matching",
    description=(
        "Summarize the committed annotation-based (SBML MIRIAM + BTO "
        "crosswalk) organ-matching catalog: model/organ counts and the "
        "biological-qualifier/ontology distribution behind each organ tag."
    ),
    parameters={
        "catalog_path": {
            "type": "string",
            "default": DEFAULT_ANNOTATION_CATALOG_PATH,
            "description": "Path to the committed annotation catalog JSON.",
        },
    },
    default_n_steps=1,
)
def build_annotation_organ_matching(
    core: Any = None, *, catalog_path: str = DEFAULT_ANNOTATION_CATALOG_PATH
) -> Dict[str, Any]:
    return build_annotation_organ_matching_document(catalog_path=catalog_path)


def build_annotation_recall_gain_document(
    name_catalog_path: str = DEFAULT_NAME_CATALOG_PATH,
    annotation_catalog_path: str = DEFAULT_ANNOTATION_CATALOG_PATH,
) -> Dict[str, Any]:
    emit_schema = {"gain": "node"}
    state: Dict[str, Any] = {
        "gain": {},
        "recall_gain_step": {
            "_type": "step",
            "address": RECALL_GAIN_STEP_ADDRESS,
            "config": {
                "name_catalog_path": name_catalog_path,
                "annotation_catalog_path": annotation_catalog_path,
            },
            "inputs": {},
            "outputs": {"gain": ["gain"]},
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
    name="annotation-recall-gain",
    description=(
        "Compare the annotation-based organ-matching catalog against the "
        "name-synonym catalog to quantify the recall gain (organs/models "
        "added) from parsing SBML MIRIAM/BTO annotations."
    ),
    parameters={
        "name_catalog_path": {
            "type": "string",
            "default": DEFAULT_NAME_CATALOG_PATH,
            "description": "Path to the committed name-synonym catalog JSON.",
        },
        "annotation_catalog_path": {
            "type": "string",
            "default": DEFAULT_ANNOTATION_CATALOG_PATH,
            "description": "Path to the committed annotation catalog JSON.",
        },
    },
    default_n_steps=1,
)
def build_annotation_recall_gain(
    core: Any = None,
    *,
    name_catalog_path: str = DEFAULT_NAME_CATALOG_PATH,
    annotation_catalog_path: str = DEFAULT_ANNOTATION_CATALOG_PATH,
) -> Dict[str, Any]:
    return build_annotation_recall_gain_document(
        name_catalog_path=name_catalog_path,
        annotation_catalog_path=annotation_catalog_path,
    )
