"""Extract every identifier class MIRIAM-annotated in a BioModel's SBML.

Generalizes annotation_match.py's anatomy-only CVTerm walk to also collect the
molecular (CHEBI/UniProt/KEGG/GO) and cell-type (CL) identifiers, keyed by the
identifiers.org collection each resource URI belongs to."""
from __future__ import annotations

import libsbml

# identifiers.org collection substring (lowercased URI) -> output key.
# Order matters: check "kegg.compound"/"kegg.reaction" etc. via the "kegg" stem.
_COLLECTIONS = (
    ("chebi", "chebi"),
    ("uniprot", "uniprot"),
    ("kegg", "kegg"),
    ("/go/", "go"), ("obo/go", "go"), (":go:", "go"), ("_go_", "go"),
    ("/cl/", "cl"), ("obo/cl", "cl"), (":cl:", "cl"),
    ("uberon", "uberon"),
    ("fma", "fma"),
    ("bto", "bto"),
)
# Prefixed CURIE classes (id keeps a PREFIX:number form, upper-cased).
_CURIE_KEYS = {"chebi", "go", "cl", "uberon", "fma", "bto"}


def collection_of_uri(uri: str):
    """`(collection, curie_or_accession)` for a MIRIAM resource URI, or None."""
    u = uri.replace("%3A", ":").replace("%3a", ":")
    low = u.lower()
    token = u.rstrip("/").rsplit("/", 1)[-1]
    for needle, key in _COLLECTIONS:
        if needle in low:
            tail = token.rsplit(":", 1)[-1].rsplit("_", 1)[-1]
            if key in _CURIE_KEYS:
                return key, f"{key.upper()}:{tail}"
            return key, tail  # uniprot / kegg accession, native case
    return None


def _element_ids(sbo_obj, bucket: dict) -> None:
    for i in range(sbo_obj.getNumCVTerms()):
        cv = sbo_obj.getCVTerm(i)
        if cv.getQualifierType() != libsbml.BIOLOGICAL_QUALIFIER:
            continue
        for j in range(cv.getNumResources()):
            hit = collection_of_uri(cv.getResourceURI(j))
            if hit:
                key, ident = hit
                bucket[key].add(ident)


def extract_identifiers(sbml_text: str) -> dict:
    keys = ["chebi", "uniprot", "kegg", "go", "cl", "uberon", "fma", "bto"]
    bucket = {k: set() for k in keys}
    doc = libsbml.readSBMLFromString(sbml_text)
    model = doc.getModel()
    if model is None:
        return {**{k: [] for k in keys}, "n_species": 0}
    _element_ids(model, bucket)
    for i in range(model.getNumCompartments()):
        _element_ids(model.getCompartment(i), bucket)
    for i in range(model.getNumSpecies()):
        _element_ids(model.getSpecies(i), bucket)
    out = {k: sorted(v) for k, v in bucket.items()}
    out["n_species"] = model.getNumSpecies()
    return out
