"""PhysioNet as an HRA model source. Enumerate published projects + metadata from
DataCite (all PhysioNet DOIs share prefix 10.13026), then build source-agnostic
model records organ-mapped via `physionet_organ_map`. Mirrors `biomodel_hra`."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import requests

from viva_human_atlas.physionet_organ_map import DEFAULT_LLM_MODEL, map_project_to_organs

_REPO = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_DIR = _REPO / ".cache" / "physionet_hra_map"
DATACITE_PREFIX = "10.13026"
_DATACITE_URL = "https://api.datacite.org/dois"
_CONTENT = "https://physionet.org/content/{slug}/"

_ACCESS_FROM_RIGHTS = (  # crude open/restricted signal from the license string
    ("open", "open"), ("public domain", "open"),
    ("credential", "credentialed"), ("restricted", "restricted"),
)


def _slug_from_url(url: str) -> Optional[str]:
    m = re.search(r"/content/([^/]+)/", url or "")
    return m.group(1) if m else None


def _access(rights_list) -> str:
    text = " ".join((r.get("rights") or "") for r in (rights_list or [])).lower()
    for needle, label in _ACCESS_FROM_RIGHTS:
        if needle in text:
            return label
    return "open" if text else "unknown"


def _project_from_datacite(attrs: dict) -> Optional[dict]:
    url = attrs.get("url") or ""
    slug = _slug_from_url(url)
    if not slug:
        return None
    titles = attrs.get("titles") or [{}]
    descs = attrs.get("descriptions") or [{}]
    return {
        "slug": slug,
        "identifier": _CONTENT.format(slug=slug),
        "name": (titles[0].get("title") or slug).strip(),
        "keywords": [s.get("subject", "").strip().lower()
                     for s in (attrs.get("subjects") or []) if s.get("subject")],
        "abstract": (descs[0].get("description") or "").strip(),
        "doi": (attrs.get("doi") or "").lower() or None,
        "year": attrs.get("publicationYear"),
        "access": _access(attrs.get("rightsList")),
    }


def resolve_projects(*, query: Optional[str] = None, limit: Optional[int] = None,
                     _get=requests.get) -> list[dict]:
    """Enumerate PhysioNet projects (+ metadata) from DataCite prefix 10.13026,
    following pagination. `query` is passed to DataCite full-text; `limit` caps."""
    params = {"query": (f"prefix:{DATACITE_PREFIX}" + (f" AND {query}" if query else "")),
              "page[size]": 250}
    projects: list[dict] = []
    url = _DATACITE_URL
    while url:
        r = _get(url, params=params if url == _DATACITE_URL else None, timeout=60)
        r.raise_for_status()
        payload = r.json()
        for rec in payload.get("data", []):
            proj = _project_from_datacite(rec.get("attributes") or {})
            if proj:
                projects.append(proj)
                if limit and len(projects) >= limit:
                    return projects[:limit]
        url = (payload.get("links") or {}).get("next")
    return projects


def build_entry(project: dict, organ_index: dict, *, no_llm: bool = True,
                llm_model: str = DEFAULT_LLM_MODEL, cache_dir=None, _map=None) -> dict:
    mapper = _map or map_project_to_organs
    hra = mapper(project, organ_index, no_llm=no_llm, llm_model=llm_model, cache_dir=cache_dir)
    doi = project.get("doi")
    return {
        "identifier": project["identifier"],
        "repository": "physionet",
        "source_id": project["slug"],
        "name": project.get("name"),
        "paper_url": (f"https://doi.org/{doi}" if doi else project["identifier"]),
        "paper_pmid": None,
        "paper_doi": doi,
        "taxonomy": [],
        "organs": hra["organs"],
        "functional_tissue_units": hra["functional_tissue_units"],
        "cell_types": hra["cell_types"],
        "molecular_ids": {"chebi": [], "uniprot": [], "kegg": [], "go": [], "reactome": []},
        "ontology_ids": {"uberon": hra.get("uberon_organ_ids", []), "cl": [], "mesh": [],
                         "fma": [], "bto": []},
        "gene_symbols": [],
        "provenance": {
            "abstract": project.get("abstract"), "year": project.get("year"),
            "access": project.get("access"), "keywords": project.get("keywords") or [],
            "mapping_method": hra.get("mapping_method", "unmapped"), "errors": [],
        },
    }
