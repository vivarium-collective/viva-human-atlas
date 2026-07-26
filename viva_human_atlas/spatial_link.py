"""Spatial linkage: join biomodel-DO organs to crosswalk AS nodes (HRA-3D
Task C).

Crosses the biomodel-DO organ annotations (`biomodel_do.build_biomodel_do_catalog`
— which Uberon organs have an annotated BioModels hit) with the ASCT+B-3D
models crosswalk (`hra_api.fetch_crosswalk` — every 3D anatomical-structure
node, Uberon-keyed where representable) to answer, per model: exactly which
GLB scene node(s) does this model's organ correspond to?

v1 emits a `readout` placeholder (`"pending time-series"`) per link — wiring
an actual model-simulation readout onto the linked node is future work; this
step only establishes the model -> AS -> GLB-node join.
"""
from __future__ import annotations

from typing import Callable, Optional

from process_bigraph import Step

from viva_human_atlas.biomodel_do import build_biomodel_do_catalog
from viva_human_atlas.hra_api import fetch_crosswalk

READOUT_PLACEHOLDER = "pending time-series"


def build_spatial_links(
    query: str = "glucose regulation",
    max_results: int = 25,
    *,
    catalog: Optional[dict] = None,
    _get_search: Optional[Callable] = None,
    _get_hra: Optional[Callable] = None,
    _get_xwalk: Optional[Callable] = None,
) -> dict:
    """Join each biomodel-DO organ to crosswalk anatomical-structure (AS)
    rows sharing the same Uberon CURIE.

    When `catalog` (a `{biomodel_dos, organ_index, organ_to_models}` dict —
    e.g. from `coverage.load_corpus_catalog`) is given, it is used directly
    and the live BioModels search/annotate (`build_biomodel_do_catalog`,
    `query`/`max_results`/`_get_search`/`_get_hra`) is skipped entirely —
    mirrors `coverage.build_coverage`'s `catalog=` fast-path. When `catalog
    is None` (the default), behavior is unchanged: `query`/`max_results`
    drive a live `build_biomodel_do_catalog` call.

    Returns `{"links": [spatial_link_row, ...], "summary": {"n_links",
    "n_models"}}` — one `spatial_link_row` per (biomodel, matching crosswalk
    row) pair, so a viewer can color the exact GLB node
    (`spatial_link_row["node_name"]`) that a model's organ maps to.
    """
    cat = catalog if catalog is not None else build_biomodel_do_catalog(
        query, max_results, _get_search=_get_search, _get_hra=_get_hra
    )
    rows = fetch_crosswalk(_get=_get_xwalk)

    # rows_by_uberon: Uberon CURIE -> every crosswalk row sharing it (a
    # reference organ's Uberon can cover multiple AS nodes cut from its GLB).
    rows_by_uberon: dict = {}
    for row in rows:
        uberon = row.get("uberon") or ""
        if not uberon:
            continue
        rows_by_uberon.setdefault(uberon, []).append(row)

    links = []
    models_linked = set()
    for do in cat["biomodel_dos"]:
        for organ in do.get("organs", []):
            uberon = organ.get("uberon")
            if not uberon:
                continue
            for row in rows_by_uberon.get(uberon, []):
                links.append(
                    {
                        "biomodel_id": do["biomodel_id"],
                        "name": do["name"],
                        "uberon": uberon,
                        "label": row.get("label", ""),
                        "organ_glb": row.get("organ_glb", ""),
                        "node_name": row.get("node_name", ""),
                        "readout": READOUT_PLACEHOLDER,
                    }
                )
                models_linked.add(do["biomodel_id"])

    return {
        "links": links,
        "summary": {
            "n_links": len(links),
            "n_models": len(models_linked),
        },
    }


class SpatialLinkStep(Step):
    """Step: join biomodel-DO organs to ASCT+B-3D crosswalk AS nodes.

    Realizes HRA-3D Task C: crosses the biomodel-DO catalog's organ
    annotations (Task A) with the crosswalk's anatomical-structure nodes
    (Task A) on shared Uberon CURIE, so a viewer can color the exact GLB
    scene node a model's organ maps to (`build_spatial_links`). `readout` is
    a placeholder string in v1 — no model-simulation output is wired yet.
    """

    description = (
        "Join biomodel-DO organ annotations to ASCT+B-3D crosswalk "
        "anatomical-structure nodes on shared Uberon CURIE, so each linked "
        "GLB scene node can be colored/labeled by its model."
    )

    config_schema = {
        "query": "string",
        "max_results": "integer",
    }

    def inputs(self):
        return {}

    def outputs(self):
        return {"links": "list[spatial_link_row]", "spatial_link_summary": "tree"}

    def update(self, inputs):
        out = build_spatial_links(
            self.config.get("query", "glucose regulation"),
            int(self.config.get("max_results", 25)),
        )
        return {"links": out["links"], "spatial_link_summary": out["summary"]}


SpatialLinkStep.contract = {
    "summary": SpatialLinkStep.description,
    "outputs": {
        "links": (
            "One `spatial_link_row` per (biomodel, matching crosswalk AS "
            "node) pair sharing a Uberon CURIE: `biomodel_id`, `name`, "
            "`uberon`, `label`, `organ_glb`, `node_name` (the exact GLB "
            "scene node to color), `readout` (placeholder "
            f"`{READOUT_PLACEHOLDER!r}` in v1 — no simulation output wired "
            "yet)."
        ),
        "spatial_link_summary": (
            "Aggregate counts: `n_links` (total AS-node links) and "
            "`n_models` (distinct biomodels with at least one link)."
        ),
    },
    "assumptions": [
        "Join key is Uberon CURIE only: a model's organ links to every "
        "crosswalk AS node sharing that Uberon, which may be more than one "
        "GLB node per organ (v1 does not resolve to a single 'best' node).",
        "`readout` is a placeholder string, not a real model-simulation "
        "output — wiring an actual per-node readout is future work.",
    ],
}
