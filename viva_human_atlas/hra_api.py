"""Thin client + process-bigraph Steps over the live Human Reference Atlas
(HRA) CCF API (https://apps.humanatlas.io/api).

Lets investigations pull HRA datasets/knowledge: reference organs (keyed by
Uberon), cell-type term occurrences (Cell Ontology), and anatomical-structure
term occurrences.
"""
from __future__ import annotations

from typing import Callable, List, Optional

from process_bigraph import Step

HRA_API = "https://apps.humanatlas.io/api"


def iri_to_curie(iri: str) -> str:
    """`http://purl.obolibrary.org/obo/UBERON_0014455` -> `UBERON:0014455`."""
    segment = iri.rstrip("/").split("/")[-1]
    return segment.replace("_", ":", 1)


def _default_get():
    import requests
    return requests.get


def _organ_from_id(ref_organ_id: str) -> str:
    # ".../ref-organ/adipose-female/v1.0#primary" -> "adipose-female" -> "adipose"
    segment = ref_organ_id.split("ref-organ/", 1)[-1].split("/")[0]
    for suffix in ("-male", "-female"):
        if segment.endswith(suffix):
            return segment[: -len(suffix)]
    return segment


def fetch_reference_organs(
    base_url: str = HRA_API,
    *,
    _get: Optional[Callable] = None,
) -> List[dict]:
    """Fetch HRA reference organs, parsed into
    `{"ref_organ_id", "organ", "uberon", "sex", "asset_url"}` dicts.

    `_get` is an injectable requests.get-compatible callable (for tests);
    defaults to the real requests.get.
    """
    if _get is None:
        _get = _default_get()
    resp = _get(f"{base_url}/v1/reference-organs", timeout=30)
    resp.raise_for_status()
    items = resp.json() or []
    organs = []
    for item in items:
        ref_organ_id = item.get("@id", "")
        organs.append(
            {
                "ref_organ_id": ref_organ_id,
                "organ": _organ_from_id(ref_organ_id),
                "uberon": iri_to_curie(item.get("representation_of", "")),
                "sex": item.get("sex"),
                "asset_url": (item.get("object") or {}).get("file"),
            }
        )
    return organs


def fetch_cell_type_terms(
    base_url: str = HRA_API,
    *,
    _get: Optional[Callable] = None,
) -> List[dict]:
    """Fetch `{CL_iri: count}` and return `[{"cl": CURIE, "count": int}]`,
    sorted by count descending."""
    if _get is None:
        _get = _default_get()
    resp = _get(f"{base_url}/v1/cell-type-term-occurences", timeout=30)
    resp.raise_for_status()
    payload = resp.json() or {}
    terms = [{"cl": iri_to_curie(iri), "count": int(count)} for iri, count in payload.items()]
    terms.sort(key=lambda t: t["count"], reverse=True)
    return terms


def fetch_anatomical_structure_terms(
    base_url: str = HRA_API,
    *,
    _get: Optional[Callable] = None,
) -> List[dict]:
    """Fetch `{term_iri: count}` and return `[{"term": CURIE, "count": int}]`,
    sorted by count descending."""
    if _get is None:
        _get = _default_get()
    resp = _get(f"{base_url}/v1/ontology-term-occurences", timeout=30)
    resp.raise_for_status()
    payload = resp.json() or {}
    terms = [{"term": iri_to_curie(iri), "count": int(count)} for iri, count in payload.items()]
    terms.sort(key=lambda t: t["count"], reverse=True)
    return terms


class HRAReferenceOrgansStep(Step):
    """Step: fetch HRA reference organs (Uberon-keyed)."""

    config_schema = {"base_url": "string"}

    def inputs(self):
        return {}

    def outputs(self):
        return {"reference_organs": "list[tree]"}

    def update(self, inputs):
        return {"reference_organs": fetch_reference_organs(self.config.get("base_url", HRA_API))}


class HRACellTypesStep(Step):
    """Step: fetch HRA cell-type term occurrences (Cell Ontology)."""

    config_schema = {"base_url": "string"}

    def inputs(self):
        return {}

    def outputs(self):
        return {"cell_types": "list[tree]"}

    def update(self, inputs):
        return {"cell_types": fetch_cell_type_terms(self.config.get("base_url", HRA_API))}


class HRAAnatomicalStructuresStep(Step):
    """Step: fetch HRA anatomical-structure term occurrences."""

    config_schema = {"base_url": "string"}

    def inputs(self):
        return {}

    def outputs(self):
        return {"anatomical_structures": "list[tree]"}

    def update(self, inputs):
        return {
            "anatomical_structures": fetch_anatomical_structure_terms(
                self.config.get("base_url", HRA_API)
            )
        }
