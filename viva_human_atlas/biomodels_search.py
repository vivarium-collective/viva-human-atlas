"""Query the BioModels REST search endpoint for model IDs.

The `biomodels` PyPI client only fetches by ID; this module adds text search
(https://www.ebi.ac.uk/biomodels/search?query=...&format=json) so an
investigation can ask for e.g. all "glucose regulation" models.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Callable, List, Optional

from process_bigraph import Step

_SEARCH_URL = "https://www.ebi.ac.uk/biomodels/search"


def search_biomodels(
    query: str,
    max_results: int = 25,
    *,
    _get: Optional[Callable] = None,
) -> List[str]:
    """Return up to `max_results` BioModels IDs matching `query`.

    `_get` is an injectable requests.get-compatible callable (for tests);
    defaults to the real requests.get.
    """
    if _get is None:
        import requests
        _get = requests.get
    resp = _get(
        _SEARCH_URL,
        params={"query": query, "format": "json", "numResults": int(max_results)},
        timeout=30,
    )
    resp.raise_for_status()
    models = resp.json().get("models") or []
    ids = [m["id"] for m in models if m.get("id")]
    return ids[:max_results]


def search_biomodels_detailed(
    query: str,
    max_results: int = 25,
    *,
    _get: Optional[Callable] = None,
) -> List[dict]:
    """Return up to `max_results` `{"id", "name"}` dicts matching `query`.

    Same endpoint/params as `search_biomodels`, but keeps the model name
    alongside the id (needed to annotate biomodel DOs with an organ).
    `_get` is an injectable requests.get-compatible callable (for tests);
    defaults to the real requests.get.
    """
    if _get is None:
        import requests
        _get = requests.get
    resp = _get(
        _SEARCH_URL,
        params={"query": query, "format": "json", "numResults": int(max_results)},
        timeout=30,
    )
    resp.raise_for_status()
    models = resp.json().get("models") or []
    results = [{"id": m["id"], "name": m.get("name", "")} for m in models if m.get("id")]
    return results[:max_results]


def fetch_all_biomodel_ids(
    *,
    curated_only: bool = True,
    _all: Optional[List[str]] = None,
) -> List[str]:
    """Return every BioModels identifier, optionally filtered to curated
    ("BIOMD"-prefixed) entries.

    Wraps `biomodels.get_all_identifiers()` (the whole registry: curated
    BIOMD entries + non-curated MODEL entries). `_all` is injectable (for
    tests) as a stand-in for that call's return value.
    """
    if _all is None:
        import biomodels
        _all = list(biomodels.get_all_identifiers())

    if curated_only:
        return [id_ for id_ in _all if id_.startswith("BIOMD")]
    return list(_all)


def fetch_biomodels_named(
    ids: List[str],
    *,
    max_workers: int = 8,
    _get: Optional[Callable] = None,
) -> List[dict]:
    """Resolve `{"id", "name"}` for each id in `ids`, in parallel, preserving
    input order.

    Each id is looked up via `search_biomodels_detailed(id)` (BioModels
    search-by-accession returns that model as its sole/first hit). Any
    per-id failure (exception or no hit) yields `name=""` rather than
    raising, so one bad id never aborts the whole corpus fetch. `_get` is
    threaded through to `search_biomodels_detailed` (injectable for tests).
    """

    def _resolve_one(id_: str) -> dict:
        try:
            hits = search_biomodels_detailed(id_, max_results=1, _get=_get)
        except Exception:
            return {"id": id_, "name": ""}
        if not hits:
            return {"id": id_, "name": ""}
        return {"id": id_, "name": hits[0].get("name", "") or ""}

    if not ids:
        return []

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        results = list(pool.map(_resolve_one, ids))
    return results


class BioModelsSearchStep(Step):
    """Step: text query -> list of BioModels IDs.

    Thin wrapper over `search_biomodels`: queries the BioModels REST search
    endpoint and returns up to `max_results` matching BioModels accession IDs
    (e.g. `BIOMD0000000372`), ordered as returned by the API (typically
    relevance).
    """

    description = (
        "Query the BioModels REST search endpoint for a text term and "
        "return up to `max_results` matching BioModels accession IDs."
    )

    config_schema = {
        "query": "string",
        "max_results": "integer",
    }

    def inputs(self):
        return {}

    def outputs(self):
        return {"model_ids": "list[string]"}

    def update(self, inputs):
        ids = search_biomodels(
            self.config.get("query", "glucose regulation"),
            int(self.config.get("max_results", 25)),
        )
        return {"model_ids": ids}


BioModelsSearchStep.contract = {
    "summary": BioModelsSearchStep.description,
    "config": {
        "query": "Free-text search term passed to the BioModels search API.",
        "max_results": "Cap on the number of returned IDs.",
    },
    "outputs": {
        "model_ids": "BioModels accession IDs matching `query`, in API result order.",
    },
}
