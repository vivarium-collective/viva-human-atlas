"""Step: pull the HRA/VCCF vasculature data and build the whole-body blood
transport network.

Wraps :func:`viva_human_atlas.vasculature.vascular_network_summary` — loads the
28 FTU heart -> FTU -> heart paths (+ VCCF vessel classes), builds a directed
vessel graph, and validates that every FTU forms a closed circuit through the
heart. This is the concrete "pull the vasculature data" mechanism of the
``blood-vasculature-network`` study, and the topology the planned blood-
circulation simulation (docs/blood-circulation-simulation-plan.md) will advect
solutes along.
"""
from __future__ import annotations

from process_bigraph import Step

from viva_human_atlas.vasculature import build_vascular_graph, vascular_network_summary


class VasculatureNetworkStep(Step):
    """Build + validate the VCCF blood-transport graph, emit its summary."""

    description = (
        "Load the HRA/VCCF vasculature data (28 FTU heart->FTU->heart paths + "
        "VCCF vessel classes) and build a directed whole-body blood-transport "
        "graph, validating that every FTU closes a circuit through the heart."
    )

    config_schema = {
        # Emit the per-FTU routes (heart->FTU->heart vessel lists) alongside the
        # summary. Off by default to keep the emit compact.
        "include_routes": {"_type": "boolean", "_default": True},
    }

    def inputs(self):
        return {}

    def outputs(self):
        return {
            "vascular_network_summary": "tree",
            "ftu_routes": "tree",
        }

    def update(self, inputs):
        summary = vascular_network_summary()
        routes = {}
        if self.config.get("include_routes", True):
            routes = build_vascular_graph().ftu_routes
        return {"vascular_network_summary": summary, "ftu_routes": routes}


VasculatureNetworkStep.contract = {
    "summary": VasculatureNetworkStep.description,
    "outputs": {
        "vascular_network_summary": (
            "Graph stats + validation: n_ftus, n_vessels, n_edges, "
            "vessel_classes (artery/vein/capillary/chamber counts), "
            "heart_chambers, n_closed_circuits / n_open_routes (a closed FTU "
            "route starts AND ends at a heart chamber), and an example route."
        ),
        "ftu_routes": (
            "FTU name -> ordered vessel list (heart -> FTU capillary -> heart) "
            "— the per-organ path a blood-borne solute travels."
        ),
    },
}
