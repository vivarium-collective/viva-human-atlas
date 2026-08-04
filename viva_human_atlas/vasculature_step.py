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

import json

from process_bigraph import Step

from viva_human_atlas.vasculature import (
    build_vascular_graph,
    load_ftu_table,
    vascular_network_summary,
)


class FTUPathTableStep(Step):
    """Step: load the HRA/VCCF FTU heart->FTU->heart path table
    (``FTU_Table_S1``) from disk and emit the parsed table in-graph.

    This lifts the (previously hardcoded, buried) dataset read out of
    ``VasculatureNetworkStep`` into a visible upstream source Step, so the
    vasculature composite declares its data dependency explicitly. The CSV
    location is a `config.path` (defaulting to the committed
    ``datasets/vasculature/FTU_Table_S1_260611.csv``), not a hardcoded path.
    The parsed ``{ftu_paths, ftu_ids}`` is handed over as a JSON string (the
    per-FTU path lists are a loose shape better passed verbatim than typed).
    """

    description = (
        "Load the FTU heart->FTU->heart path table (FTU_Table_S1) from disk "
        "and emit the parsed paths + FTU ontology ids in-graph."
    )

    config_schema = {"path": "string"}

    def inputs(self):
        return {}

    def outputs(self):
        return {"ftu_table_json": "string"}

    def update(self, inputs):
        ftu_paths, ftu_ids = load_ftu_table(path=self.config.get("path") or None)
        return {"ftu_table_json": json.dumps({"ftu_paths": ftu_paths, "ftu_ids": ftu_ids})}


FTUPathTableStep.contract = {
    "summary": FTUPathTableStep.description,
    "outputs": {
        "ftu_table_json": (
            "The parsed FTU path table `{ftu_paths, ftu_ids}` as a JSON string: "
            "`ftu_paths` maps each FTU to its ordered heart->FTU->heart path "
            "steps, `ftu_ids` maps each FTU to its ontology id."
        ),
    },
    "assumptions": [
        "`config.path` is the FTU_Table_S1 CSV location (default the committed "
        "`datasets/vasculature/` copy — a vendored HRA VCCF supplement with no "
        "regeneration script). Making it a config input, rather than a "
        "hardcoded read two modules down, is what surfaces the dependency.",
    ],
}


class VasculatureNetworkStep(Step):
    """Build + validate the VCCF blood-transport graph, emit its summary."""

    description = (
        "Build a directed whole-body blood-transport graph from the FTU "
        "heart->FTU->heart paths (handed over in-graph by an upstream "
        "FTUPathTableStep), validating that every FTU closes a circuit "
        "through the heart."
    )

    config_schema = {
        # Emit the per-FTU routes (heart->FTU->heart vessel lists) alongside the
        # summary. Off by default to keep the emit compact.
        "include_routes": {"_type": "boolean", "_default": True},
    }

    def inputs(self):
        # Wired to the upstream `FTUPathTableStep`'s `ftu_table_json` store;
        # falls back to reading the committed CSV directly when standalone.
        return {"ftu_table_json": "string"}

    def outputs(self):
        return {
            "vascular_network_summary": "tree",
            "ftu_routes": "tree",
        }

    def update(self, inputs):
        table_json = (inputs or {}).get("ftu_table_json") or ""
        if table_json:
            data = json.loads(table_json)
            ftu_paths, ftu_ids = data["ftu_paths"], data.get("ftu_ids")
        else:
            ftu_paths, ftu_ids = load_ftu_table()
        summary = vascular_network_summary(ftu_paths=ftu_paths, ftu_ids=ftu_ids)
        routes = {}
        if self.config.get("include_routes", True):
            routes = build_vascular_graph(ftu_paths=ftu_paths, ftu_ids=ftu_ids).ftu_routes
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
