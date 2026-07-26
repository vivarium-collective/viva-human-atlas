"""Bigraph-schema types for the workspace-local HRA / BioModels-DO Steps.

These name the shapes the workspace's own Steps (`hra_api.py`,
`biomodel_do.py`, `biomodels_search.py`) already build by hand, so composite
ports carry a resolvable named type instead of an opaque `tree`/`list[tree]`
— that's what lets bigraph-loom's semantic zoom drill into the structure
(`reference_organ`'s `uberon`/`organ`/`sex`/`asset_url` fields, etc.) instead
of rendering a closed blob.

`reference_organ` is the per-item shape `hra_api.fetch_reference_organs`
returns (Uberon-keyed, per-sex GLB asset). `cell_type_term` /
`anatomical_term` are the per-item shapes of `fetch_cell_type_terms` /
`fetch_anatomical_structure_terms` (Cell-Ontology / anatomy term counts).
`matched_organ` is the per-organ-hit shape inside a `biomodel_do`'s `organs`
list (`biomodel_do.annotate_biomodel`); `biomodel_do` is the annotated
BioModels hit `build_biomodel_do_catalog` emits, and `organ_to_models` is its
inverted Uberon-CURIE -> biomodel-id index.
"""
from __future__ import annotations


WORKSPACE_TYPES = {
    "reference_organ": {
        "ref_organ_id": "string",
        "organ": "string",
        "uberon": "string",
        "sex": "maybe[string]",
        "asset_url": "maybe[string]",
    },
    "cell_type_term": {
        "cl": "string",
        "count": "integer",
    },
    "anatomical_term": {
        "term": "string",
        "count": "integer",
    },
    "matched_organ": {
        "organ": "string",
        "uberon": "maybe[string]",
    },
    "biomodel_do": {
        "biomodel_id": "string",
        "name": "string",
        "organs": "list[matched_organ]",
        "provenance": "tree",
    },
    "organ_to_models": "map[list[string]]",
}


def register_workspace_types(core):
    """Register viva-human-atlas's own bigraph-schema types into a core."""
    core.register_types(WORKSPACE_TYPES)
    return core
