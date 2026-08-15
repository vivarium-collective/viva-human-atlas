"""Physiome Model Repository (PMR) as an HRA model source.

PMR CellML models don't carry machine-readable organ annotations, but PMR files
every model under a scientific **category** (`.../electrophysiology`,
`.../metabolism`, ...), and that category IS the anatomical signal. So we harvest
the corpus straight from the category listing pages: each page yields its
exposures (canonical `/e/<slug>` or `/exposure/<hash>` id + title), and the page
it came from IS the model's category. That sidesteps PMR's split `/e/` vs
`/exposure/` id namespaces (no cross-matching) and needs no per-model CellML
download. `physiome_organ_map` turns categories into HRA organs. Plugs into the
shared `model_harvest` framework like `physionet` / `biomodel_hra`.
"""
from __future__ import annotations

import re
from html import unescape
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

import requests

from viva_human_atlas.physiome_organ_map import DEFAULT_LLM_MODEL, map_exposure_to_organs

_REPO = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_DIR = _REPO / ".cache" / "physiome_hra_map"
CATEGORY_SNAPSHOT = _REPO / "datasets" / "physiome_categories.json"
_BASE = "https://models.physiomeproject.org"

# PMR category slugs to harvest. The mappable ones carry a confident organ signal
# (see CATEGORY_TO_ORGAN_KEYS); the rest are still harvested so their models exist
# in the DB, but they carry no blanket organ mapping and rely on the title-keyword
# / annotation path instead (they stay unmapped otherwise). "metabolism" and
# "endocrine" live here deliberately: as categories they're too coarse to place
# confidently (metabolism != liver-only; endocrine != pancreas-only).
MAPPABLE_CATEGORIES = [
    "electrophysiology", "cardiovascular_circulation", "excitation-contraction_coupling",
    "myofilament_mechanics", "hepatology", "ion_transport", "ph_regulation", "neurobiology",
]
NON_MAPPING_CATEGORIES = [
    "metabolism", "endocrine",
    "calcium_dynamics", "signal_transduction", "cell_cycle", "immunology",
    "mechanical_constitutive_laws", "circadian_rhythms", "gene_regulation",
    "synthetic_biology", "PKPD", "cell_migration", "protein_modules",
]

# One exposure entry on a category listing page: the canonical id (short /e/<slug>
# OR full /exposure/<hash>), the primary CellML filename, and the anchor title.
_ENTRY_RE = re.compile(
    r'href="' + re.escape(_BASE) + r'/(e/[0-9a-fA-F]+|exposure/[0-9a-fA-F]+)/'
    r'([^"/]+\.cellml)/view"[^>]*>([^<]*)</a>')
_PAGE_STEP = 100  # PMR (Plone) batches category listings; walk b_start until dry.
# A PMR exposure page cites its source publication as a doi.org link (often with
# a redundant "doi:" prefix); many exposures have one, some don't.
_DOI_RE = re.compile(r'doi\.org/(?:doi:)?(10\.\d{4,}/[^\s"\'<>]+)', re.IGNORECASE)


def fetch_doi(exposure: dict, *, cache_dir=None, _get=requests.get) -> Optional[str]:
    """Return the publication DOI cited on an exposure's PMR page (or None),
    caching the result per exposure so reruns don't re-fetch. Never raises."""
    cache = Path(cache_dir) if cache_dir else DEFAULT_CACHE_DIR
    cache.mkdir(parents=True, exist_ok=True)
    cached = cache / f"{exposure['slug']}.doi"
    if cached.exists():
        return cached.read_text(encoding="utf-8").strip() or None
    doi = ""
    try:
        r = _get(exposure["identifier"], timeout=60)
        r.raise_for_status()
        m = _DOI_RE.search(r.text)
        if m:
            doi = m.group(1).rstrip(".,);>").lower()
    except Exception:  # noqa: BLE001 — a missing page must not abort the harvest
        doi = ""
    cached.write_text(doi, encoding="utf-8")
    return doi or None


def _scrape_category(slug: str, *, _get=requests.get) -> dict:
    """Return `{canonical_id: {"id","url","name","filename"}}` for one category,
    walking pagination until a page yields no new exposures."""
    found: dict[str, dict] = {}
    b = 0
    while b < 3000:
        url = f"{_BASE}/{slug}" + (f"?b_start:int={b}" if b else "")
        r = _get(url, timeout=60)
        r.raise_for_status()
        new = 0
        for idpart, filename, title in _ENTRY_RE.findall(r.text):
            cid = idpart.rsplit("/", 1)[-1]
            if cid not in found:
                found[cid] = {"id": cid, "url": f"{_BASE}/{idpart}",
                              "name": unescape(title).strip(), "filename": filename}
                new += 1
        if new == 0:
            break
        b += _PAGE_STEP
    return found


def build_category_index(*, categories=None, _get=requests.get) -> dict:
    """Scrape PMR category pages into `{canonical_id: {..., "categories": [slug]}}`,
    unioning categories for exposures that appear under more than one."""
    cats = categories if categories is not None else (MAPPABLE_CATEGORIES + NON_MAPPING_CATEGORIES)
    index: dict[str, dict] = {}
    for slug in cats:
        for cid, meta in _scrape_category(slug, _get=_get).items():
            row = index.setdefault(cid, {**meta, "categories": []})
            if slug not in row["categories"]:
                row["categories"].append(slug)
    return index


def resolve_exposures(*, query: Optional[str] = None, limit: Optional[int] = None,
                      _get=requests.get, _index=None) -> list[dict]:
    """List PMR exposures (id + title + categories) from the category listings.
    `query` is a client-side title substring filter; `limit` caps."""
    index = _index if _index is not None else build_category_index(_get=_get)
    q = (query or "").lower().strip()
    exposures: list[dict] = []
    for cid, row in index.items():
        if q and q not in (row.get("name") or "").lower():
            continue
        exposures.append({
            "slug": cid, "identifier": row["url"], "name": row.get("name"),
            "categories": row.get("categories") or [], "filename": row.get("filename"),
        })
        if limit is not None and len(exposures) >= limit:
            break
    return exposures


def build_entry(exposure: dict, organ_index: dict, *, no_llm: bool = True,
                llm_model: str = DEFAULT_LLM_MODEL, cache_dir=None, _map=None, _doi=None) -> dict:
    """Build a source-agnostic HRA model record for one PMR exposure, mapped by
    its PMR category (no CellML download — PMR anatomy annotations are absent).
    Also enriches the record with the exposure's cited publication DOI."""
    mapper = _map or map_exposure_to_organs
    hra = mapper(exposure, organ_index, no_llm=no_llm, llm_model=llm_model, cache_dir=cache_dir)
    anat = hra.get("anatomy_ids") or {}
    mol = hra.get("molecular") or {}
    doi_fn = _doi if _doi is not None else fetch_doi
    try:
        doi = doi_fn(exposure, cache_dir=cache_dir)
    except Exception:  # noqa: BLE001 — DOI enrichment must never abort the harvest
        doi = None
    return {
        "identifier": exposure["identifier"],
        "repository": "physiome",
        "source_id": exposure["slug"],
        "name": exposure.get("name"),
        "paper_url": (f"https://doi.org/{doi}" if doi else exposure["identifier"]),
        "paper_pmid": None,
        "paper_doi": doi,
        "taxonomy": [],
        "organs": hra["organs"],
        "functional_tissue_units": hra["functional_tissue_units"],
        "cell_types": hra["cell_types"],
        "molecular_ids": {"chebi": mol.get("chebi") or [], "uniprot": [], "kegg": [],
                          "go": mol.get("go") or [], "reactome": []},
        "ontology_ids": {"uberon": hra.get("uberon_organ_ids", []), "cl": [], "mesh": [],
                         "fma": anat.get("fma") or [], "bto": []},
        "gene_symbols": [],
        "provenance": {
            "abstract": None, "year": None, "access": "open",
            "keywords": exposure.get("categories") or [],
            "model_format": "CellML", "executable": "OpenCOR",
            "categories": exposure.get("categories") or [],
            "mapping_method": hra.get("mapping_method", "unmapped"),
            "confidence": hra.get("confidence", "none"), "errors": [],
        },
    }


def resolve_cellml_url(identifier: str, *, _get=requests.get) -> "str | None":
    """Resolve a PMR exposure (identifier URL like .../e/<id>) to its primary
    runnable .cellml URL. Returns None on HTTP error or no .cellml link.

    Spike-validated: the exposure page links `<file>.cellml/view`; strip /view
    and OpenCOR fetches it directly. (Multi-file/import CellML that fails to
    load is the caller's marked failure — a workspace-archive fetch is a
    follow-up.)"""
    try:
        r = _get(identifier, timeout=25)
        r.raise_for_status()
    except Exception:
        return None
    m = re.findall(r'href="([^"]+\.cellml)(?:/view)?"', r.text)
    if not m:
        return None
    url = urljoin(getattr(r, "url", identifier), m[0])
    return url[:-5] if url.endswith("/view") else url
