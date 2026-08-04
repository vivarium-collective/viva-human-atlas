"""Fetch a model's paper text: PubMed abstract (NCBI E-utilities) + Europe PMC
open-access full text. Disk-cached; injectable `_get` for offline tests."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Callable, Optional
from xml.etree import ElementTree as ET

import requests

_EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
_EPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest"
_TIMEOUT = 30


def _cached(cache_dir, key, produce):
    if not cache_dir:
        return produce()
    p = Path(cache_dir) / (hashlib.sha1(key.encode()).hexdigest() + ".txt")
    if p.exists():
        t = p.read_text(encoding="utf-8")
        return t or None
    val = produce()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(val or "", encoding="utf-8")
    return val


def fetch_abstract(pmid, *, _get: Optional[Callable] = None, cache_dir=None):
    if not pmid:
        return None
    get = _get or requests.get

    def produce():
        r = get(_EFETCH, params={"db": "pubmed", "id": str(pmid), "rettype": "abstract", "retmode": "xml"}, timeout=_TIMEOUT)
        r.raise_for_status()
        root = ET.fromstring(r.text)
        parts = [(e.text or "") for e in root.iter("AbstractText")]
        text = " ".join(p.strip() for p in parts if p).strip()
        return text or None

    return _cached(cache_dir, f"abstract:{pmid}", produce)


def fetch_oa_fulltext(pmid, *, _get: Optional[Callable] = None, cache_dir=None):
    if not pmid:
        return None
    get = _get or requests.get

    def produce():
        s = get(f"{_EPMC}/search", params={"query": f"EXT_ID:{pmid} AND SRC:MED", "format": "json", "resultType": "core"}, timeout=_TIMEOUT)
        s.raise_for_status()
        if '"isOpenAccess":"Y"' not in s.text and '"inEPMC":"Y"' not in s.text:
            return None
        f = get(f"{_EPMC}/MED/{pmid}/fullTextXML", timeout=_TIMEOUT)
        if getattr(f, "status_code", 200) != 200:
            return None
        txt = re.sub(r"<[^>]+>", " ", f.text)
        txt = re.sub(r"\s+", " ", txt).strip()
        return txt or None

    return _cached(cache_dir, f"fulltext:{pmid}", produce)


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
