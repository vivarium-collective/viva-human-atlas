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
    """Step: fetch HRA reference organs (Uberon-keyed).

    Pulls the HRA CCF API's `/v1/reference-organs` list and parses each entry
    into a `reference_organ` record (Uberon CURIE, organ slug, sex, 3D asset
    URL) — the per-sex reference-organ 3D models the Human Reference Atlas
    publishes for anatomical grounding.
    """

    description = (
        "Fetch HRA reference organs (Uberon-keyed, per-sex GLB 3D assets) "
        "from the CCF API's `/v1/reference-organs` endpoint."
    )

    config_schema = {"base_url": "string"}

    def inputs(self):
        return {}

    def outputs(self):
        return {"reference_organs": "list[reference_organ]"}

    def update(self, inputs):
        return {"reference_organs": fetch_reference_organs(self.config.get("base_url", HRA_API))}


HRAReferenceOrgansStep.contract = {
    "summary": HRAReferenceOrgansStep.description,
    "outputs": {
        "reference_organs": (
            "One `reference_organ` record per HRA reference organ: "
            "`ref_organ_id` (source IRI), `organ` (slug, e.g. `liver`), "
            "`uberon` (Uberon CURIE), `sex` (`Male`/`Female`, if sex-specific), "
            "`asset_url` (GLB 3D-model URL)."
        ),
    },
}


class HRACellTypesStep(Step):
    """Step: fetch HRA cell-type term occurrences (Cell Ontology).

    Pulls the HRA CCF API's `/v1/cell-type-term-occurences` histogram (Cell
    Ontology IRI -> occurrence count across HRA datasets) and returns it as a
    CURIE-keyed, count-descending list of `cell_type_term` records.
    """

    description = (
        "Fetch HRA cell-type term occurrences (Cell Ontology, CURIE-keyed) "
        "from the CCF API's `/v1/cell-type-term-occurences` endpoint, sorted "
        "by occurrence count descending."
    )

    config_schema = {"base_url": "string"}

    def inputs(self):
        return {}

    def outputs(self):
        return {"cell_types": "list[cell_type_term]"}

    def update(self, inputs):
        return {"cell_types": fetch_cell_type_terms(self.config.get("base_url", HRA_API))}


HRACellTypesStep.contract = {
    "summary": HRACellTypesStep.description,
    "outputs": {
        "cell_types": (
            "One `cell_type_term` record per distinct Cell Ontology term: "
            "`cl` (CL CURIE) and `count` (occurrences across HRA datasets), "
            "sorted by `count` descending."
        ),
    },
}


class HRAAnatomicalStructuresStep(Step):
    """Step: fetch HRA anatomical-structure term occurrences.

    Pulls the HRA CCF API's `/v1/ontology-term-occurences` histogram
    (anatomy-ontology IRI -> occurrence count across HRA datasets) and
    returns it as a CURIE-keyed, count-descending list of `anatomical_term`
    records.
    """

    description = (
        "Fetch HRA anatomical-structure term occurrences (CURIE-keyed) from "
        "the CCF API's `/v1/ontology-term-occurences` endpoint, sorted by "
        "occurrence count descending."
    )

    config_schema = {"base_url": "string"}

    def inputs(self):
        return {}

    def outputs(self):
        return {"anatomical_structures": "list[anatomical_term]"}

    def update(self, inputs):
        return {
            "anatomical_structures": fetch_anatomical_structure_terms(
                self.config.get("base_url", HRA_API)
            )
        }


HRAAnatomicalStructuresStep.contract = {
    "summary": HRAAnatomicalStructuresStep.description,
    "outputs": {
        "anatomical_structures": (
            "One `anatomical_term` record per distinct anatomy-ontology "
            "term: `term` (CURIE) and `count` (occurrences across HRA "
            "datasets), sorted by `count` descending."
        ),
    },
}
