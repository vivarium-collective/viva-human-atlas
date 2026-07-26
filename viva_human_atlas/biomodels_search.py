"""Query the BioModels REST search endpoint for model IDs.

The `biomodels` PyPI client only fetches by ID; this module adds text search
(https://www.ebi.ac.uk/biomodels/search?query=...&format=json) so an
investigation can ask for e.g. all "glucose regulation" models.
"""
from __future__ import annotations

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


class BioModelsSearchStep(Step):
    """Step: text query -> list of BioModels IDs."""

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
