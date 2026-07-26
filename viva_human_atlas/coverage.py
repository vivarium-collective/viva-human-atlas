"""Model coverage over anatomical structures / organs (HRA-3D Task B).

Crosses the ASCT+B-3D models crosswalk (`hra_api.fetch_crosswalk` — every 3D
anatomical-structure node, Uberon-keyed where representable) with the
biomodel-DO organ annotations (`biomodel_do.build_biomodel_do_catalog` —
which Uberon organs have an annotated BioModels hit) to answer: which
anatomical structures / organs does the current model set actually touch?

v1 is **organ-granularity**: an anatomical-structure (AS) row is `covered` if
its own Uberon has annotated models, *or* its source-organ GLB
(`organ_glb`) belongs to an organ that has models (i.e. coverage propagates
from the organ's reference-organ Uberon down to every AS node cut from that
organ's GLB) — not per-AS-node model matching, which nothing in the current
BioModels/HRA data supports yet.

The crosswalk's `organ_glb` (e.g. `"VH_F_Liver"`) and the reference-organ
asset stems used to compute which GLBs are covered (e.g.
`"3d-vh-f-liver"`) come from two different naming conventions, so the
propagation compares a **normalized organ key** on both sides
(`_normalize_organ_key`: lowercase, strip a leading naming-convention
prefix, drop all non-alphanumerics) rather than the raw strings.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Callable, Optional

from process_bigraph import Step

from viva_human_atlas.biomodel_do import build_biomodel_do_catalog
from viva_human_atlas.hra_api import fetch_crosswalk

_DEFAULT_CORPUS_CATALOG_PATH = "datasets/biomodel_corpus_catalog.json"

# Naming-convention prefixes seen on reference-organ asset stems / crosswalk
# `organ_glb` values, longest/most-specific first so e.g. "3d-vh-f-" is
# stripped before the more general "3d-vh-" would otherwise match.
_ORGAN_KEY_PREFIXES = (
    "3d-vh-f-", "3d-vh-m-", "3d-vh-", "vh-f-", "vh-m-", "vh_f_", "vh_m_", "vh-", "vh_",
)


def _glb_stem(asset_url: str) -> str:
    """`".../assets/VH_F_Liver.glb"` -> `"VH_F_Liver"`."""
    name = asset_url.rsplit("/", 1)[-1]
    if name.endswith(".glb"):
        name = name[: -len(".glb")]
    return name


def _normalize_organ_key(name: str) -> str:
    """Canonicalize a crosswalk `organ_glb` or a reference-organ asset stem
    to a bare organ key so the two naming conventions compare equal, e.g.
    both `"3d-vh-f-liver"` and `"VH_F_Liver"` normalize to `"liver"`."""
    key = (name or "").lower()
    for prefix in _ORGAN_KEY_PREFIXES:
        if key.startswith(prefix):
            key = key[len(prefix):]
            break
    return re.sub(r"[^a-z0-9]", "", key)


def build_coverage(
    query: str = "glucose regulation",
    max_results: int = 25,
    *,
    catalog: Optional[dict] = None,
    _get_search: Optional[Callable] = None,
    _get_hra: Optional[Callable] = None,
    _get_xwalk: Optional[Callable] = None,
) -> dict:
    """Build model coverage over the ASCT+B-3D crosswalk's anatomical
    structures, crossed with the biomodel-DO organ->models index.

    When `catalog` (a `{biomodel_dos, organ_index, organ_to_models}` dict —
    e.g. from `load_corpus_catalog`) is given, it is used directly and the
    live BioModels search/annotate (`build_biomodel_do_catalog`, `query`/
    `max_results`/`_get_search`/`_get_hra`) is skipped entirely. When
    `catalog is None` (the default), behavior is unchanged: `query`/
    `max_results` drive a live `build_biomodel_do_catalog` call.

    Returns `{"coverage": [coverage_row, ...], "summary": {...}}` — see
    module docstring for the organ-granularity coverage rule.
    """
    cat = catalog if catalog is not None else build_biomodel_do_catalog(
        query, max_results, _get_search=_get_search, _get_hra=_get_hra
    )
    rows = fetch_crosswalk(_get=_get_xwalk)

    uberon_models = cat["organ_to_models"]
    organ_index = cat["organ_index"]

    # organ_by_uberon: Uberon CURIE -> organ_index entry, for organs that have
    # a resolvable Uberon (used to find which organs have models).
    organ_by_uberon = {
        entry["uberon"]: entry for entry in organ_index.values() if entry.get("uberon")
    }

    # covered_glbs: normalized organ keys (e.g. "liver", from GLB stems like
    # "3d-vh-f-liver") belonging to an organ whose Uberon has annotated
    # models — this is what lets coverage propagate from a reference organ's
    # Uberon down to every AS node cut from that organ's GLB, even when the
    # AS node's own Uberon differs. Normalizing both sides is what makes the
    # propagation actually fire: crosswalk `organ_glb` values (e.g.
    # "VH_F_Liver") and reference-organ asset stems (e.g. "3d-vh-f-liver")
    # use different naming conventions and never match as raw strings.
    covered_glbs = set()
    for uberon, entry in organ_by_uberon.items():
        if uberon not in uberon_models:
            continue
        for asset_url in entry.get("asset_urls") or []:
            covered_glbs.add(_normalize_organ_key(_glb_stem(asset_url)))

    coverage = []
    organs_glb_seen = set()
    organs_glb_covered = set()
    for row in rows:
        uberon = row.get("uberon") or ""
        if not uberon:
            continue
        organ_glb = row.get("organ_glb", "")
        model_ids = uberon_models.get(uberon, [])
        covered = bool(model_ids) or (_normalize_organ_key(organ_glb) in covered_glbs)

        if organ_glb:
            organs_glb_seen.add(organ_glb)
            if covered:
                organs_glb_covered.add(organ_glb)

        coverage.append(
            {
                "uberon": uberon,
                "label": row.get("label", ""),
                "organ_glb": organ_glb,
                "node_name": row.get("node_name", ""),
                "node_type": row.get("node_type", ""),
                "n_models": len(model_ids),
                "model_ids": model_ids,
                "covered": covered,
            }
        )

    n_as = len(coverage)
    n_as_covered = sum(1 for r in coverage if r["covered"])

    return {
        "coverage": coverage,
        "summary": {
            "n_as": n_as,
            "n_as_covered": n_as_covered,
            "n_organs_glb": len(organs_glb_seen),
            "n_organs_glb_covered": len(organs_glb_covered),
            "query": query,
        },
    }


def load_corpus_catalog(path: str = _DEFAULT_CORPUS_CATALOG_PATH) -> dict:
    """Load the committed full-corpus catalog (Task A,
    `datasets/biomodel_corpus_catalog.json` = `{n_ids, n_named, n_tagged,
    catalog}`) and return just the inner `catalog`
    (`{biomodel_dos, organ_index, organ_to_models}`)."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return payload["catalog"]


def build_corpus_coverage(
    catalog_path: str = _DEFAULT_CORPUS_CATALOG_PATH,
    *,
    _get_xwalk: Optional[Callable] = None,
) -> dict:
    """`build_coverage` over the full committed corpus catalog (Task A) —
    loads `catalog_path` (default the committed
    `datasets/biomodel_corpus_catalog.json`) via `load_corpus_catalog` and
    crosses it with the live ASCT+B-3D crosswalk."""
    return build_coverage(catalog=load_corpus_catalog(catalog_path), _get_xwalk=_get_xwalk)


class CoverageStep(Step):
    """Step: build model coverage over the ASCT+B-3D crosswalk's anatomical
    structures, crossed with the biomodel-DO organ->models index.

    Realizes HRA-3D Task B: crosses Task A's crosswalk (every 3D
    anatomical-structure node) with the biomodel-DO catalog's organ
    annotations (Task A) to mark which anatomical structures/organs the
    current BioModels-derived model set actually covers, at organ
    granularity (`build_coverage`).
    """

    description = (
        "Cross the ASCT+B-3D crosswalk's anatomical structures with the "
        "biomodel-DO organ->models index to mark model coverage, at organ "
        "granularity."
    )

    config_schema = {
        "query": "string",
        "max_results": "integer",
        "catalog_path": "string",
    }

    def inputs(self):
        return {}

    def outputs(self):
        return {"coverage": "list[coverage_row]", "coverage_summary": "coverage_summary"}

    def update(self, inputs):
        catalog_path = self.config.get("catalog_path")
        if catalog_path:
            # Corpus mode (Task B, `corpus-coverage` composite): use the
            # committed full-corpus catalog instead of a live BioModels
            # search/annotate.
            out = build_corpus_coverage(catalog_path)
        else:
            out = build_coverage(
                self.config.get("query", "glucose regulation"),
                int(self.config.get("max_results", 25)),
            )
        return {"coverage": out["coverage"], "coverage_summary": out["summary"]}


CoverageStep.contract = {
    "summary": CoverageStep.description,
    "outputs": {
        "coverage": (
            "One `coverage_row` per crosswalk anatomical-structure node with "
            "a resolvable Uberon: `uberon`, `label`, `organ_glb` (source-organ "
            "GLB name), `node_name` (the crosswalk row's own GLB scene-node "
            "name, for coloring the 3D viewer), `node_type`, "
            "`n_models`/`model_ids` (annotated biomodel-DO hits), `covered` "
            "(True if its own Uberon has models, or its `organ_glb` "
            "normalizes to the same organ key as a covered organ's "
            "reference-organ GLB — this propagation actually fires now that "
            "both sides are normalized through `_normalize_organ_key`)."
        ),
        "coverage_summary": (
            "Aggregate counts: `n_as`/`n_as_covered` (anatomical-structure "
            "nodes), `n_organs_glb`/`n_organs_glb_covered` (distinct "
            "source-organ GLBs), `query` (the BioModels search term used)."
        ),
    },
    "assumptions": [
        "v1 coverage is organ-granularity: a covered organ's Uberon marks "
        "every AS node cut from that organ's GLB as covered, not just the "
        "organ's own Uberon row — no per-AS-node model matching yet.",
    ],
}
