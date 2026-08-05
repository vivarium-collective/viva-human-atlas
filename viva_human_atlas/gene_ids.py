"""Crosswalk a UniProt accession to gene ids (HGNC, Ensembl gene, symbol).

Reads the UniProtKB entry JSON and parses its cross-references: HGNC ids, the
Ensembl `GeneId` (ENSG..., version suffix stripped), and the gene symbol.
Disk-cached; injectable `_get` for offline tests.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable, Dict, List, Optional

_UNIPROT = "https://rest.uniprot.org/uniprotkb/{acc}.json"
_TIMEOUT = 30


def _default_get():
    import requests
    return requests.get


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


def _prop(properties, key) -> Optional[str]:
    for prop in properties or []:
        if prop.get("key") == key:
            return prop.get("value")
    return None


def _strip_version(ensg: str) -> str:
    """`ENSG00000254647.7` -> `ENSG00000254647`."""
    return (ensg or "").split(".", 1)[0]


def _parse_uniprot(payload: dict) -> dict:
    hgnc: set = set()
    ensembl: set = set()
    symbol: Optional[str] = None

    # symbol: prefer genes[0].geneName.value
    genes = payload.get("genes") or []
    if genes:
        gn = (genes[0] or {}).get("geneName") or {}
        symbol = (gn.get("value") or "").strip() or None

    for xref in payload.get("uniProtKBCrossReferences") or []:
        db = xref.get("database")
        if db == "HGNC":
            xid = xref.get("id")
            if xid:
                hgnc.add(xid)
            if symbol is None:
                gname = _prop(xref.get("properties"), "GeneName")
                if gname:
                    symbol = gname.strip() or None
        elif db == "Ensembl":
            ensg = _prop(xref.get("properties"), "GeneId")
            if ensg:
                stripped = _strip_version(ensg)
                if stripped:
                    ensembl.add(stripped)

    return {"hgnc": sorted(hgnc), "ensembl": sorted(ensembl), "symbol": symbol}


def uniprot_gene_ids(
    acc,
    *,
    _get: Optional[Callable] = None,
    cache_dir: Optional[str] = None,
) -> dict:
    """Resolve a UniProt accession to `{"hgnc": [...], "ensembl": [...],
    "symbol": Optional[str]}`. Disk-cached by accession. Tolerant — returns
    empty lists / None on any failure.
    """
    if not acc:
        return {"hgnc": [], "ensembl": [], "symbol": None}
    get = _get or _default_get()

    def produce():
        try:
            resp = get(_UNIPROT.format(acc=acc), timeout=_TIMEOUT)
            resp.raise_for_status()
            payload = resp.json() or {}
        except Exception:  # noqa: BLE001
            return None
        return _parse_uniprot(payload)

    result = _cached(cache_dir, f"uniprot_{acc}", produce)
    if result is None:
        return {"hgnc": [], "ensembl": [], "symbol": None}
    return result


def genes_for_uniprot(accs, **kw) -> dict:
    """Union HGNC/Ensembl ids and collect symbols over a list of accessions.
    Returns `{"hgnc": [...], "ensembl": [...], "symbols": [...]}`.
    """
    hgnc: set = set()
    ensembl: set = set()
    symbols: set = set()
    for acc in accs or []:
        rec = uniprot_gene_ids(acc, **kw)
        hgnc.update(rec.get("hgnc") or [])
        ensembl.update(rec.get("ensembl") or [])
        if rec.get("symbol"):
            symbols.add(rec["symbol"])
    return {
        "hgnc": sorted(hgnc),
        "ensembl": sorted(ensembl),
        "symbols": sorted(symbols),
    }
