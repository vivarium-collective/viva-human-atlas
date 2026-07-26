"""Thin client + process-bigraph Steps over the live Human Reference Atlas
(HRA) CCF API (https://apps.humanatlas.io/api).

Lets investigations pull HRA datasets/knowledge: reference organs (keyed by
Uberon), cell-type term occurrences (Cell Ontology), and anatomical-structure
term occurrences.
"""
from __future__ import annotations

import csv
import io
from typing import Callable, List, Optional

from process_bigraph import Step

HRA_API = "https://apps.humanatlas.io/api"

CROSSWALK_URL = (
    "https://cdn.humanatlas.io/digital-objects/ref-organ/"
    "asct-b-3d-models-crosswalk/latest/assets/asct-b-3d-models-crosswalk.csv"
)
_FTU_BASE = "https://cdn.humanatlas.io/digital-objects/3d-ftu"


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


def fetch_crosswalk(
    url: str = CROSSWALK_URL,
    *,
    _get: Optional[Callable] = None,
) -> List[dict]:
    """Fetch the ASCT+B-3D models crosswalk CSV and parse it into
    `{"node_name", "label", "uberon", "representation_of", "node_type",
    "organ_glb", "parent"}` rows.

    The CSV has a couple of title/blank lines before the real header (which
    starts with `anatomical_structure_of`); rows before that header are
    skipped, and only rows with a non-empty `node_name` are kept (this still
    includes `organizational` rows, which have no `uberon`).

    `_get` is an injectable requests.get-compatible callable (for tests);
    defaults to the real requests.get.
    """
    if _get is None:
        _get = _default_get()
    resp = _get(url, timeout=60)
    resp.raise_for_status()
    lines = resp.text.splitlines()
    start = next(
        (i for i, ln in enumerate(lines) if ln.startswith("anatomical_structure_of")),
        None,
    )
    if start is None:
        return []
    reader = csv.DictReader(io.StringIO("\n".join(lines[start:])))
    rows = []
    for row in reader:
        node = (row.get("node_name") or "").strip()
        if not node:
            continue
        uid = (row.get("OntologyID") or "").strip()
        rows.append(
            {
                "node_name": node,
                "label": (row.get("label") or "").strip().lstrip("-").strip(),
                "uberon": "" if uid in ("", "-") else uid,
                "representation_of": (row.get("representation_of") or "").strip().lstrip("-").strip(),
                "node_type": (row.get("node_type") or "").strip(),
                "organ_glb": (row.get("glb file of single organs") or "").strip(),
                "parent": (row.get("anatomical_structure_of") or "").strip().lstrip("-").strip(),
            }
        )
    return rows


def fetch_ftu(
    slug: str = "glomerulus",
    *,
    _get: Optional[Callable] = None,
) -> dict:
    """Fetch a 3D functional-tissue-unit (FTU) digital object and parse it
    into `{"slug", "title", "description", "glb", "glb_url"}`.

    `_get` is an injectable requests.get-compatible callable (for tests);
    defaults to the real requests.get.
    """
    if _get is None:
        _get = _default_get()
    # The purl resolver content-negotiates: a bare `Accept: */*` (requests'
    # default) 404s, but an explicit `Accept: application/json` 200s with
    # the digital-object JSON this function expects.
    resp = _get(
        f"https://purl.humanatlas.io/3d-ftu/{slug}/latest",
        timeout=30,
        headers={"Accept": "application/json"},
    )
    resp.raise_for_status()
    do = resp.json() or {}
    glb = (do.get("data") or [""])[0]
    metadata = do.get("metadata") or {}
    return {
        "slug": slug,
        "title": metadata.get("title", slug),
        "description": metadata.get("description", ""),
        "glb": glb,
        "glb_url": f"{_FTU_BASE}/{slug}/latest/assets/{glb}" if glb else "",
    }


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


class HRACrosswalkStep(Step):
    """Step: fetch the ASCT+B-3D models crosswalk (1,400+ anatomical
    structures).

    Pulls the HRA CDN's `asct-b-3d-models-crosswalk.csv` digital object and
    parses each data row into an `as_3d` record — the anatomical-structure
    node's name/label, Uberon CURIE (when representable), node type
    (`mesh`/`organizational`), source-organ GLB name, and parent node —
    giving the full ASCT+B-3D anatomical-structure tree, not just the
    per-organ 3D assets `HRAReferenceOrgansStep` covers.
    """

    description = (
        "Fetch the ASCT+B-3D models crosswalk (1,400+ anatomical structures) "
        "from the HRA CDN's `asct-b-3d-models-crosswalk.csv` digital object."
    )

    config_schema = {"url": "string"}

    def inputs(self):
        return {}

    def outputs(self):
        return {"anatomical_structures_3d": "list[as_3d]"}

    def update(self, inputs):
        return {
            "anatomical_structures_3d": fetch_crosswalk(
                self.config.get("url", CROSSWALK_URL)
            )
        }


HRACrosswalkStep.contract = {
    "summary": HRACrosswalkStep.description,
    "outputs": {
        "anatomical_structures_3d": (
            "One `as_3d` record per crosswalk row: `node_name`, `label`, "
            "`uberon` (CURIE, empty for `organizational` nodes with none), "
            "`representation_of` (ontology IRI), `node_type` "
            "(`mesh`/`organizational`), `organ_glb` (source-organ GLB name), "
            "`parent` (`anatomical_structure_of` node name)."
        ),
    },
}


class HRAFtuStep(Step):
    """Step: fetch a 3D functional-tissue-unit (FTU) digital object.

    Pulls the HRA CDN's `3d-ftu/<slug>` digital object and resolves it into
    an `ftu` record — title, description, GLB asset name, and the full GLB
    asset URL — for FTU 3D models (e.g. `glomerulus`) that sit below the
    per-organ 3D assets `HRAReferenceOrgansStep` covers.
    """

    description = (
        "Fetch a 3D functional-tissue-unit (FTU) digital object from the HRA "
        "CDN's `3d-ftu/<slug>` endpoint, resolving its GLB asset URL."
    )

    config_schema = {"slug": "string"}

    def inputs(self):
        return {}

    def outputs(self):
        return {"ftu": "ftu"}

    def update(self, inputs):
        return {"ftu": fetch_ftu(self.config.get("slug", "glomerulus"))}


HRAFtuStep.contract = {
    "summary": HRAFtuStep.description,
    "outputs": {
        "ftu": (
            "The requested FTU's `ftu` record: `slug`, `title`, "
            "`description`, `glb` (asset file name), `glb_url` (full CDN "
            "asset URL)."
        ),
    },
}
