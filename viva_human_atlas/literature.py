"""Fetch a model's paper text: PubMed abstract (NCBI E-utilities) + Europe PMC
open-access full text. Disk-cached; injectable `_get` for offline tests."""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Callable, Optional
from xml.etree import ElementTree as ET

import requests

_EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
_EPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest"
_TIMEOUT = 30
# NCBI/Europe PMC politeness: identify ourselves and stay under ~3 req/s.
_TOOL = "viva-human-atlas"
_EMAIL = "agmon.eran@gmail.com"
_MIN_INTERVAL = 0.34  # seconds, ~3 req/s


def _polite_pause():
    time.sleep(_MIN_INTERVAL)


def _cached(cache_dir, key, produce):
    if not cache_dir:
        return produce()
    p = Path(cache_dir) / (hashlib.sha1(key.encode()).hexdigest() + ".txt")
    if p.exists():
        t = p.read_text(encoding="utf-8")
        return t or None
    val = produce()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(val or "", encoding="utf-8")
    os.replace(tmp, p)
    return val


def fetch_abstract(pmid, *, _get: Optional[Callable] = None, cache_dir=None):
    if not pmid:
        return None
    real = _get is None
    get = _get or requests.get

    def produce():
        params = {"db": "pubmed", "id": str(pmid), "rettype": "abstract", "retmode": "xml"}
        if real:
            params["tool"] = _TOOL
            params["email"] = _EMAIL
            _polite_pause()
        r = get(_EFETCH, params=params, timeout=_TIMEOUT)
        r.raise_for_status()
        root = ET.fromstring(r.text)
        parts = [(e.text or "") for e in root.iter("AbstractText")]
        text = " ".join(p.strip() for p in parts if p).strip()
        return text or None

    return _cached(cache_dir, f"abstract:{pmid}", produce)


def fetch_oa_fulltext(pmid, *, _get: Optional[Callable] = None, cache_dir=None):
    if not pmid:
        return None
    real = _get is None
    get = _get or requests.get

    def produce():
        params = {"query": f"EXT_ID:{pmid} AND SRC:MED", "format": "json", "resultType": "core"}
        if real:
            params["tool"] = _TOOL
            params["email"] = _EMAIL
            _polite_pause()
        s = get(f"{_EPMC}/search", params=params, timeout=_TIMEOUT)
        s.raise_for_status()
        if '"isOpenAccess":"Y"' not in s.text and '"inEPMC":"Y"' not in s.text:
            return None
        if real:
            _polite_pause()
        f = get(f"{_EPMC}/MED/{pmid}/fullTextXML", timeout=_TIMEOUT)
        if getattr(f, "status_code", 200) != 200:
            return None
        txt = re.sub(r"<[^>]+>", " ", f.text)
        txt = re.sub(r"\s+", " ", txt).strip()
        return txt or None

    return _cached(cache_dir, f"fulltext:{pmid}", produce)


_MESH_HEADING_RE = re.compile(r'<DescriptorName UI="(D\d+)"[^>]*>([^<]+)</DescriptorName>')


def fetch_pubmed_mesh(pmid, *, _get: Optional[Callable] = None, cache_dir=None) -> list:
    """`[{"id": "D008099", "label": "Liver"}, ...]` -- the MeSH headings NLM
    assigned to a paper, parsed from the PubMed efetch abstract XML (the same
    record `fetch_abstract` reads, but MeSH headings live in `MeshHeadingList`
    rather than `AbstractText`). `[]` if there's no pmid, or on any error."""
    if not pmid:
        return []
    real = _get is None
    get = _get or requests.get

    def produce():
        params = {"db": "pubmed", "id": str(pmid), "rettype": "abstract", "retmode": "xml"}
        if real:
            params["tool"] = _TOOL
            params["email"] = _EMAIL
            _polite_pause()
        r = get(_EFETCH, params=params, timeout=_TIMEOUT)
        r.raise_for_status()
        terms = [{"id": uid, "label": label.strip()}
                 for uid, label in _MESH_HEADING_RE.findall(r.text)]
        return json.dumps(terms)

    try:
        cached = _cached(cache_dir, f"mesh:{pmid}", produce)
    except Exception:  # noqa: BLE001
        return []
    return json.loads(cached) if cached else []


def get_literature_text(pmid, doi=None, *, _get: Optional[Callable] = None, cache_dir=None) -> dict:
    abstract = fetch_abstract(pmid, _get=_get, cache_dir=cache_dir)
    fulltext = fetch_oa_fulltext(pmid, _get=_get, cache_dir=cache_dir) if abstract or pmid else None
    if fulltext:
        source = "abstract+fulltext"
    elif abstract:
        source = "abstract"
    else:
        source = "none"
    return {"abstract": abstract, "fulltext": fulltext, "text_source": source, "has_fulltext": bool(fulltext)}
