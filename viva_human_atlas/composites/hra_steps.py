"""Composite generators wrapping the HRA CCF-API Steps.

Each generator wires one HRA Step's output into a single store plus a
RAMEmitter, so a study's baseline run demonstrates that the dataset actually
loads (offline against a mocked `fetch_*`, or live against the real HRA API).
Follows the state/emitter shape used by
`pbg_biomodels.composites.compare_simulators` (`_type: step`, `address`,
one-segment `inputs`/`outputs` stores, an `emitter` step with an `emit`
schema, `run_steps_on_init: True`).
"""
from __future__ import annotations

from typing import Any, Dict

try:
    from viva_superpowers.composite_generator import composite_generator
except ModuleNotFoundError:
    from pbg_superpowers.composite_generator import composite_generator

from viva_human_atlas.hra_api import HRA_API

# Fully-dotted (not bare-registry-name) addresses: this is what lets
# vivarium-workbench's process_docs.py resolve each Step's `description`/
# `describe()`/`contract` for the Composite Explorer without needing a
# live-built core (see `pbg_biomodels.composites.compare_simulators`, which
# uses the same `local:<module>.<Class>` convention).
REFERENCE_ORGANS_STEP_ADDRESS = "local:viva_human_atlas.hra_api.HRAReferenceOrgansStep"
CELL_TYPES_STEP_ADDRESS = "local:viva_human_atlas.hra_api.HRACellTypesStep"
ANATOMICAL_STRUCTURES_STEP_ADDRESS = "local:viva_human_atlas.hra_api.HRAAnatomicalStructuresStep"


def _single_store_document(store: str, step_address: str, *, base_url: str) -> Dict[str, Any]:
    """Build a one-Step, one-store, one-RAMEmitter composite document."""
    state: Dict[str, Any] = {
        store: [],
        "load_step": {
            "_type": "step",
            "address": step_address,
            "config": {"base_url": base_url},
            "inputs": {},
            "outputs": {store: [store]},
        },
        "emitter": {
            "_type": "step",
            "address": "local:RAMEmitter",
            "config": {"emit": {store: "node"}},
            "inputs": {store: [store]},
        },
    }
    return {"state": state, "run_steps_on_init": True}


@composite_generator(
    name="hra-reference-organs",
    description="Fetch HRA reference organs (Uberon-keyed, per-sex GLB assets) from the CCF API.",
    parameters={
        "base_url": {
            "type": "string",
            "default": HRA_API,
            "description": "HRA CCF API base URL.",
        },
    },
    default_n_steps=1,
)
def build_hra_reference_organs(core: Any = None, *, base_url: str = HRA_API) -> Dict[str, Any]:
    return _single_store_document("reference_organs", REFERENCE_ORGANS_STEP_ADDRESS, base_url=base_url)


@composite_generator(
    name="hra-cell-types",
    description="Fetch HRA cell-type term occurrences (Cell Ontology) from the CCF API.",
    parameters={
        "base_url": {
            "type": "string",
            "default": HRA_API,
            "description": "HRA CCF API base URL.",
        },
    },
    default_n_steps=1,
)
def build_hra_cell_types(core: Any = None, *, base_url: str = HRA_API) -> Dict[str, Any]:
    return _single_store_document("cell_types", CELL_TYPES_STEP_ADDRESS, base_url=base_url)


@composite_generator(
    name="hra-anatomical-structures",
    description="Fetch HRA anatomical-structure term occurrences from the CCF API.",
    parameters={
        "base_url": {
            "type": "string",
            "default": HRA_API,
            "description": "HRA CCF API base URL.",
        },
    },
    default_n_steps=1,
)
def build_hra_anatomical_structures(core: Any = None, *, base_url: str = HRA_API) -> Dict[str, Any]:
    return _single_store_document(
        "anatomical_structures", ANATOMICAL_STRUCTURES_STEP_ADDRESS, base_url=base_url
    )
