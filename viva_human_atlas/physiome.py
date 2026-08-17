"""Physiome Model Repository (PMR) as an HRA model source, via the pmr3 API.

The new PMR backend (OpenAPI at /api-docs/openapi.json) indexes every exposure
with author `cellml_keyword`s, title, abstract, and PubMed citations. We
enumerate all exposures (`/api/index/exposure_id`), fetch each
(`/api/index/exposure_id/{id}`), and aggregate its CellML files into one model
record. Author keywords are the primary organ signal (see physiome_organ_map);
citations enrich the record with the source publication. Plugs into the shared
`model_harvest` framework like `physionet` / `biomodel_hra`.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

import requests

from viva_human_atlas.physiome_organ_map import DEFAULT_LLM_MODEL, map_exposure_to_organs

_REPO = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_DIR = _REPO / ".cache" / "physiome_pmr3"
_DEFAULT_API_BASE = "https://pmr3.demo.physiomeproject.org"
PMR_SITE = "https://models.physiomeproject.org"


def api_base() -> str:
    return os.environ.get("PMR3_API_BASE", _DEFAULT_API_BASE)


def list_exposure_ids(*, _get=requests.get) -> list[str]:
    r = _get(f"{api_base()}/api/index/exposure_id", timeout=60)
    r.raise_for_status()
    return list(r.json().get("terms", []))


def _first(data: dict, key: str) -> Optional[str]:
    vals = data.get(key) or []
    return vals[0] if vals else None


def fetch_exposure(exposure_id: str, *, cache_dir=None, _get=requests.get) -> Optional[dict]:
    cache = Path(cache_dir) if cache_dir else DEFAULT_CACHE_DIR
    cache.mkdir(parents=True, exist_ok=True)
    cached = cache / f"{exposure_id}.json"
    if cached.exists():
        payload = json.loads(cached.read_text(encoding="utf-8"))
    else:
        r = _get(f"{api_base()}/api/index/exposure_id/{exposure_id}", timeout=60)
        r.raise_for_status()
        payload = r.json()
        cached.write_text(json.dumps(payload), encoding="utf-8")
    records = payload.get("resource_paths") or []
    if not records:
        return None
    first = records[0]["data"]
    alias = _first(first, "exposure_alias")
    if not alias:
        uri = _first(first, "aliased_uri") or ""     # /exposure/<alias>/<file>
        parts = uri.strip("/").split("/")
        alias = parts[1] if len(parts) > 1 else exposure_id
    keywords, citation_ids, authors = [], [], []
    for rec in records:
        d = rec["data"]
        for k in d.get("cellml_keyword") or []:
            k = (k or "").strip().lower()
            if k and k not in keywords:
                keywords.append(k)
        for c in d.get("citation_id") or []:
            if c and c not in citation_ids:
                citation_ids.append(c)
        for a in d.get("citation_author_family_name") or []:
            if a and a not in authors:
                authors.append(a)
    filename = records[0]["resource_path"].rsplit("/", 1)[-1]
    return {
        "slug": alias,
        "identifier": f"{PMR_SITE}/exposure/{alias}",
        "name": _first(first, "_title"),
        "abstract": _first(first, "_brief"),
        "keywords": keywords,
        "categories": [],
        "citation_ids": citation_ids,
        "authors": authors,
        "created_ts": _first(first, "created_ts"),
        "filename": filename,
    }


def resolve_exposures(*, query: Optional[str] = None, limit: Optional[int] = None,
                      cache_dir=None, _get=requests.get, _ids=None) -> list[dict]:
    ids = _ids if _ids is not None else list_exposure_ids(_get=_get)
    q = (query or "").lower().strip()
    out: list[dict] = []
    for eid in ids:
        exp = fetch_exposure(eid, cache_dir=cache_dir, _get=_get)
        if exp is None:
            continue
        if q and q not in (exp.get("name") or "").lower():
            continue
        out.append(exp)
        if limit is not None and len(out) >= limit:
            break
    return out


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
