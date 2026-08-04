"""Extract cross-reference identifiers from a BioModel's auto-generated BioPAX
OWL/RDF (Level 3 or Level 2) — a clean complementary source to the SBML MIRIAM
annotations. BioPAX Xrefs carry db/id pairs with human-readable db names;
harvest CHEBI/UniProt/KEGG/GO/Reactome ids + organism NCBI Taxon, via stdlib
ElementTree (no rdflib/pybiopax dependency).

Namespace- and case-agnostic by design: BioPAX Level 3 uses the
`biopax-level3.owl#` namespace with `UnificationXref`/`RelationshipXref` tags
and `bp:db`/`bp:id` children, while Level 2 (the BioModels download fallback)
uses a different namespace with lowercase-initial `unificationXref`/
`relationshipXref` tags and upper-case `bp:DB`/`bp:ID` children. Rather than
hardcode either, xref elements and their db/id children are matched by
lowercased local name so both levels work identically.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Callable, Optional
from xml.etree import ElementTree as ET

import requests

_DOWNLOAD = "https://www.ebi.ac.uk/biomodels/model/download/{}"
_TIMEOUT = 60

# db-name substring (lowercased) -> output collection key.
_DB_MAP = (
    ("chebi", "chebi"), ("uniprot", "uniprot"), ("kegg", "kegg"),
    ("gene ontology", "go"), ("reactome", "reactome"), ("taxonomy", "taxonomy"),
)
_KEYS = ["chebi", "uniprot", "kegg", "go", "reactome", "taxonomy"]

# collection -> CURIE prefix to rebuild unconditionally (drops any existing
# prefix/case, e.g. "chebi:17234" -> "CHEBI:17234").
_PREFIX = {"chebi": "CHEBI", "go": "GO", "taxonomy": "NCBITaxon"}


def _normalize(collection: str, ident: str) -> str:
    ident = (ident or "").strip()
    if collection in _PREFIX:
        return f"{_PREFIX[collection]}:{ident.split(':')[-1]}"
    return ident


def extract_biopax_identifiers(owl_text: str) -> dict:
    buckets = {k: set() for k in _KEYS}
    try:
        root = ET.fromstring(owl_text)
    except ET.ParseError:
        return {k: [] for k in _KEYS}
    for el in root.iter():
        local = el.tag.split("}")[-1].lower()
        if not local.endswith("xref") or local == "publicationxref":
            continue
        db = ident = None
        for child in el:
            cl = child.tag.split("}")[-1].lower()
            if cl == "db":
                db = child.text
            elif cl == "id":
                ident = child.text
        db = (db or "").lower()
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
