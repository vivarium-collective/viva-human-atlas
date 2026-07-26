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

`as_3d` is the per-row shape `hra_api.fetch_crosswalk` returns (one ASCT+B-3D
anatomical-structure node from the crosswalk); `ftu` is the shape
`hra_api.fetch_ftu` returns (a 3D functional-tissue-unit digital object).

`coverage_row` is the per-anatomical-structure shape `coverage.build_coverage`
returns (crosswalk AS node x biomodel-DO organ annotations, organ-granularity
`covered` flag, plus the crosswalk row's own `node_name` so viewers can key
scene-node coloring directly off it); `coverage_summary` is its
aggregate-counts shape.

`spatial_link_row` is the per-link shape `spatial_link.build_spatial_links`
returns (one biomodel-DO organ joined to a crosswalk AS node sharing its
Uberon CURIE — the exact GLB scene node a model's organ maps to; `readout` is
a placeholder string in v1).

`ftu_cell_type` is the per-cell-type shape inside an `HRA_FTUS` entry's
`cell_types` (and `ftu_coverage.ctpop_parameter_stub`'s output) — a
Cell-Ontology-keyed candidate CTpop-parameterizable input. `ftu_coverage_row`
is the per-FTU shape `ftu_coverage.build_ftu_model_coverage` returns (which
curated HRA functional tissue units have a name/synonym-matching BioModels
model); `ftu_coverage_summary` is its aggregate-counts shape.
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
    "as_3d": {
        "node_name": "string",
        "label": "string",
        "uberon": "string",
        "representation_of": "string",
        "node_type": "string",
        "organ_glb": "string",
        "parent": "string",
    },
    "ftu": {
        "slug": "string",
        "title": "string",
        "description": "string",
        "glb": "string",
        "glb_url": "string",
    },
    "coverage_row": {
        "uberon": "string",
        "label": "string",
        "organ_glb": "string",
        "node_name": "string",
        "node_type": "string",
        "n_models": "integer",
        "model_ids": "list[string]",
        "covered": "boolean",
    },
    "coverage_summary": {
        "n_as": "integer",
        "n_as_covered": "integer",
        "n_organs_glb": "integer",
        "n_organs_glb_covered": "integer",
        "query": "string",
    },
    "spatial_link_row": {
        "biomodel_id": "string",
        "name": "string",
        "uberon": "string",
        "label": "string",
        "organ_glb": "string",
        "node_name": "string",
        "readout": "string",
    },
    "ftu_cell_type": {
        "cl": "string",
        "label": "string",
    },
    "ftu_coverage_row": {
        "ftu": "string",
        "organ": "string",
        "n_models": "integer",
        "model_ids": "list[string]",
        "covered": "boolean",
    },
    "ftu_coverage_summary": {
        "n_ftus": "integer",
        "n_ftus_covered": "integer",
        "n_models_matched": "integer",
    },
}


def register_workspace_types(core):
    """Register viva-human-atlas's own bigraph-schema types into a core."""
    core.register_types(WORKSPACE_TYPES)
    return core
