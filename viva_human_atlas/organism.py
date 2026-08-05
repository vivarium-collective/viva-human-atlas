"""Resolve NCBITaxon ids to organism names.

A small static map covers the common BioModels organisms (human, mouse, yeast,
E. coli, ...) with no network; anything else falls back to the EBI ENA taxonomy
REST service. Disk-cached; injectable `_get` for offline tests.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable, Dict, List, Optional

_ENA_TAX = "https://www.ebi.ac.uk/ena/taxonomy/rest/tax-id/{id}"
_TIMEOUT = 30

# Common BioModels organisms, keyed by bare NCBITaxon id -> (scientific, common).
_STATIC: Dict[str, tuple] = {
    "9606": ("Homo sapiens", "human"),
    "10090": ("Mus musculus", "house mouse"),
    "10116": ("Rattus norvegicus", "Norway rat"),
    "559292": ("Saccharomyces cerevisiae", "baker's yeast"),
    "4932": ("Saccharomyces cerevisiae", "baker's yeast"),
    "511145": ("Escherichia coli", "E. coli K-12 MG1655"),
    "562": ("Escherichia coli", "E. coli"),
    "9913": ("Bos taurus", "cattle"),
    "9615": ("Canis lupus familiaris", "dog"),
    "8355": ("Xenopus laevis", "African clawed frog"),
    "8364": ("Xenopus tropicalis", "tropical clawed frog"),
    "7227": ("Drosophila melanogaster", "fruit fly"),
    "6239": ("Caenorhabditis elegans", "roundworm"),
    "7955": ("Danio rerio", "zebrafish"),
    "3702": ("Arabidopsis thaliana", "thale cress"),
}


def _default_get():
    import requests
    return requests.get


def _bare_id(taxon: str) -> str:
    """`"NCBITaxon:9606"` or `"9606"` -> `"9606"`."""
    s = str(taxon).strip()
    if ":" in s:
        s = s.split(":", 1)[1]
    return s.strip()


def _cached(cache_dir, key, produce):
    if not cache_dir:
        return produce()
    p = Path(cache_dir) / (key + ".json")
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return None
    val = produce()
    if val is not None:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(val), encoding="utf-8")
        os.replace(tmp, p)
    return val


def organism_name(
    taxon,
    *,
    _get: Optional[Callable] = None,
    cache_dir: Optional[str] = None,
) -> Optional[dict]:
    """Resolve `"NCBITaxon:9606"` or `"9606"` to
    `{"taxon": "NCBITaxon:9606", "name": "Homo sapiens", "common": "human"}`.

    Uses the static map first; else GETs the EBI ENA taxonomy REST service
    (disk-cached by id). Tolerant — returns `None` on failure / unknown id.
    """
    bare = _bare_id(taxon)
    if not bare:
        return None
    if bare in _STATIC:
        name, common = _STATIC[bare]
        return {"taxon": f"NCBITaxon:{bare}", "name": name, "common": common}

    get = _get or _default_get()

    def produce():
        try:
            resp = get(_ENA_TAX.format(id=bare), timeout=_TIMEOUT)
            resp.raise_for_status()
            payload = resp.json() or {}
        except Exception:  # noqa: BLE001
            return None
        name = (payload.get("scientificName") or "").strip()
        if not name:
            return None
        common = (payload.get("commonName") or "").strip() or None
        return {"taxon": f"NCBITaxon:{bare}", "name": name, "common": common}

    return _cached(cache_dir, f"taxon_{bare}", produce)


def organisms_for_taxonomy(taxonomy_ids, **kw) -> List[dict]:
    """Resolve each id in `taxonomy_ids`, drop Nones, and dedupe by taxon."""
    seen = set()
    out: List[dict] = []
    for tid in taxonomy_ids or []:
        rec = organism_name(tid, **kw)
        if rec is None:
            continue
        if rec["taxon"] in seen:
            continue
        seen.add(rec["taxon"])
        out.append(rec)
    return out
