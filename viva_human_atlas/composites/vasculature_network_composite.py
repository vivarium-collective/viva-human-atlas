"""Composite generator wrapping ``VasculatureNetworkStep``.

Pulls the HRA/VCCF vasculature data and builds the whole-body blood-transport
graph, emitting its summary + per-FTU routes via a RAMEmitter. Same state/emitter
shape as ``spatial_link_composite.py`` / ``hra_steps.py``. This is the runnable
data-pull backing the ``blood-vasculature-network`` study; the flow dynamics
(a ``BloodTransportProcess`` advecting solutes along this graph, coupling organ
models) are designed in ``docs/blood-circulation-simulation-plan.md``.
"""
from __future__ import annotations

from typing import Any, Dict  # noqa: F401

try:
    from viva_superpowers.composite_generator import composite_generator
except ModuleNotFoundError:
    from pbg_superpowers.composite_generator import composite_generator

VASCULATURE_STEP_ADDRESS = "local:viva_human_atlas.vasculature_step.VasculatureNetworkStep"
FTU_PATH_TABLE_STEP_ADDRESS = "local:viva_human_atlas.vasculature_step.FTUPathTableStep"

DEFAULT_FTU_TABLE_PATH = "datasets/vasculature/FTU_Table_S1_260611.csv"


def build_vasculature_network_document(
    include_routes: bool = True,
    ftu_table_path: str = DEFAULT_FTU_TABLE_PATH,
) -> Dict[str, Any]:
    emit_schema = {"vascular_network_summary": "node", "ftu_routes": "node"}
    state: Dict[str, Any] = {
        "vascular_network_summary": {},
        "ftu_routes": {},
        # In-graph FTU path table: `ftu_path_table_step` reads the CSV (from a
        # config path, not a hardcoded one), `vasculature_network_step`
        # consumes the parsed table — the file dependency is now a declared,
        # visible input rather than a read buried inside the graph builder.
        "ftu_table_json": "",
        "ftu_path_table_step": {
            "_type": "step",
            "address": FTU_PATH_TABLE_STEP_ADDRESS,
            "config": {"path": ftu_table_path},
            "inputs": {},
            "outputs": {"ftu_table_json": ["ftu_table_json"]},
        },
        "vasculature_network_step": {
            "_type": "step",
            "address": VASCULATURE_STEP_ADDRESS,
            "config": {"include_routes": include_routes},
            "inputs": {"ftu_table_json": ["ftu_table_json"]},
            "outputs": {
                "vascular_network_summary": ["vascular_network_summary"],
                "ftu_routes": ["ftu_routes"],
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
    name="blood-vasculature-network",
    description=(
        "Pull the HRA/VCCF vasculature data (28 FTU heart->FTU->heart paths + "
        "VCCF vessel classes) and build a directed whole-body blood-transport "
        "graph, validating every FTU closes a circuit through the heart. The "
        "topology substrate for the planned blood-circulation simulation that "
        "couples organ models through a shared blood compartment."
    ),
    parameters={
        "include_routes": {
            "type": "boolean",
            "default": True,
            "description": "Also emit the per-FTU ordered vessel routes, not just the summary.",
        },
    },
    default_n_steps=1,
)
def build_vasculature_network(core: Any = None, *, include_routes: bool = True) -> Dict[str, Any]:
    return build_vasculature_network_document(include_routes=include_routes)
