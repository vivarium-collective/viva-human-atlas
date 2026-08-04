"""Extract cross-reference identifiers from a BioModel's auto-generated BioPAX
Level-3 OWL/RDF — a clean complementary source to the SBML MIRIAM annotations.
BioPAX Xrefs carry <bp:db>/<bp:id> pairs with human-readable db names; harvest
CHEBI/UniProt/KEGG/GO/Reactome ids + organism NCBI Taxon, via stdlib
ElementTree (no rdflib/pybiopax dependency)."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Callable, Optional
from xml.etree import ElementTree as ET

import requests

_BP = "{http://www.biopax.org/release/biopax-level3.owl#}"
_DOWNLOAD = "https://www.ebi.ac.uk/biomodels/model/download/{}"
_TIMEOUT = 60

# db-name substring (lowercased) -> output collection key.
_DB_MAP = (
    ("chebi", "chebi"), ("uniprot", "uniprot"), ("kegg", "kegg"),
    ("gene ontology", "go"), ("reactome", "reactome"), ("taxonomy", "taxonomy"),
)
_KEYS = ["chebi", "uniprot", "kegg", "go", "reactome", "taxonomy"]


def _normalize(collection: str, ident: str) -> str:
    ident = (ident or "").strip()
    if collection == "chebi" and not ident.upper().startswith("CHEBI:"):
        ident = "CHEBI:" + ident.split(":")[-1]
    elif collection == "go" and not ident.upper().startswith("GO:"):
        ident = "GO:" + ident.split(":")[-1]
    elif collection == "taxonomy" and not ident.upper().startswith("NCBITAXON:"):
        ident = "NCBITaxon:" + ident.split(":")[-1]
    return ident


def extract_biopax_identifiers(owl_text: str) -> dict:
    buckets = {k: set() for k in _KEYS}
    try:
        root = ET.fromstring(owl_text)
    except ET.ParseError:
        return {k: [] for k in _KEYS}
    for el in root.iter():
        if el.tag.split("}")[-1] not in ("UnificationXref", "RelationshipXref"):
            continue
        db = (el.findtext(_BP + "db") or "").lower()
        ident = el.findtext(_BP + "id")
        if not ident:
            continue
        for needle, key in _DB_MAP:
            if needle in db:
                buckets[key].add(_normalize(key, ident))
                break
    return {k: sorted(v) for k, v in buckets.items()}


def fetch_biopax(biomodel_id: str, *, _get: Optional[Callable] = None, cache_dir=None) -> Optional[str]:
    get = _get or requests.get

    def produce():
        for fn in (f"{biomodel_id}-biopax3.owl", f"{biomodel_id}-biopax2.owl"):
            r = get(_DOWNLOAD.format(biomodel_id), params={"filename": fn}, timeout=_TIMEOUT)
            if getattr(r, "status_code", 200) == 200 and (r.text or "").strip():
                return r.text
        return None

    if not cache_dir:
        return produce()
    p = Path(cache_dir) / (hashlib.sha1(f"biopax:{biomodel_id}".encode()).hexdigest() + ".owl")
    if p.exists():
        return p.read_text(encoding="utf-8") or None
    val = produce()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(val or "", encoding="utf-8")
    os.replace(tmp, p)
    return val
