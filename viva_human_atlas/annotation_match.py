"""Annotation-based organ matching: parse a BioModel's SBML MIRIAM
annotations (Uberon/FMA/BTO CVTerms) and map them to HRA reference organs —
the recall-oriented complement to biomodel_do.py's name-synonym matcher.
Same catalog shape, so it drops into the coverage/atlas pipeline."""
from __future__ import annotations

import re
from typing import Callable, Optional

import libsbml

ANATOMY_PREFIXES = ("uberon", "fma", "bto")
# biological qualifiers we treat as an anatomical assertion about the model part
_QUALIFIERS = {
    libsbml.BQB_IS: "BQB_IS",
    libsbml.BQB_IS_PART_OF: "BQB_IS_PART_OF",
    libsbml.BQB_OCCURS_IN: "BQB_OCCURS_IN",
    libsbml.BQB_HAS_PART: "BQB_HAS_PART",
    libsbml.BQB_IS_VERSION_OF: "BQB_IS_VERSION_OF",
}


def _curie_from_uri(uri: str) -> Optional[str]:
    # e.g. http://identifiers.org/uberon/UBERON:0001264
    #      urn:miriam:uberon:UBERON%3A0001264
    #      http://purl.obolibrary.org/obo/UBERON_0001264  (OBO PURL, underscore form)
    u = uri.replace("%3A", ":").replace("%3a", ":")
    low = u.lower()
    token = u.rsplit("/", 1)[-1]
    for pref in ANATOMY_PREFIXES:
        if f"/{pref}/" in low or f":{pref}:" in low:
            tail = token.rsplit(":", 1)[-1]
            if ":" in token and token.upper().startswith(pref.upper() + ":"):
                return token.upper()
            return f"{pref.upper()}:{tail}"
        if token.upper().startswith(pref.upper() + "_"):
            return f"{pref.upper()}:{token.upper().split('_', 1)[1]}"
    return None


def _element_curies(sbo_obj, element_label: str) -> list[dict]:
    out = []
    for i in range(sbo_obj.getNumCVTerms()):
        cv = sbo_obj.getCVTerm(i)
        if cv.getQualifierType() != libsbml.BIOLOGICAL_QUALIFIER:
            continue
        qual = _QUALIFIERS.get(cv.getBiologicalQualifierType())
        if not qual:
            continue
        for j in range(cv.getNumResources()):
            curie = _curie_from_uri(cv.getResourceURI(j))
            if curie:
                out.append({"curie": curie, "qualifier": qual, "element": element_label})
    return out


def extract_anatomy_curies(sbml_text: str) -> list[dict]:
    doc = libsbml.readSBMLFromString(sbml_text)
    model = doc.getModel()
    if model is None:
        return []
    found: list[dict] = []
    found += _element_curies(model, "model")
    for i in range(model.getNumCompartments()):
        c = model.getCompartment(i)
        found += _element_curies(c, f"compartment:{c.getId() or i}")
    for i in range(model.getNumSpecies()):
        s = model.getSpecies(i)
        found += _element_curies(s, f"species:{s.getId() or i}")
    # dedupe on (curie, qualifier, element)
    seen, out = set(), []
    for f in found:
        k = (f["curie"], f["qualifier"], f["element"])
        if k not in seen:
            seen.add(k)
            out.append(f)
    return out


def _normalize_curie(value: str) -> str:
    # Uppercase and strip separators so differing CURIE formats compare equal:
    # "FMA:24978" (SBML-extracted) vs. "fma24978" (bare, no colon, as stored by
    # several organ_index entries) both normalize to "FMA24978".
    return re.sub(r"[^A-Za-z0-9]", "", value).upper()


def map_curie_to_organ(curie: str, organ_index: dict, bto_crosswalk: Optional[dict] = None) -> Optional[str]:
    cu = curie.upper()
    norm = _normalize_curie(curie)
    # organ_index[*]["uberon"] holds either a full UBERON CURIE ("UBERON:0001264")
    # or, for ~11 entries, a bare FMA id ("fma15046", lowercase, no colon).
    # Normalize both sides so either format matches regardless of separators/case.
    for key, entry in organ_index.items():
        ub = entry.get("uberon") or ""
        if ub and _normalize_curie(ub) == norm:
            return key
    if cu.startswith("BTO:") and bto_crosswalk:
        uber = bto_crosswalk.get(curie) or bto_crosswalk.get(cu)
        if uber:
            return map_curie_to_organ(uber, organ_index)
    return None


def annotate_model(biomodel_id: str, organ_index: dict, *, sbml_text: str,
                    bto_crosswalk: Optional[dict] = None, name: Optional[str] = None) -> dict:
    organs, seen = [], set()
    for hit in extract_anatomy_curies(sbml_text):
        key = map_curie_to_organ(hit["curie"], organ_index, bto_crosswalk)
        if key and key not in seen:
            seen.add(key)
            organs.append({"organ": key, "uberon": organ_index[key].get("uberon"), "via": hit})
    do = {"biomodel_id": biomodel_id, "organs": organs,
          "provenance": {"annotation": "miriam-match@SBML", "source": "biomodels"}}
    if name is not None:
        do["name"] = name
    return do


def build_annotation_catalog(model_dos: list[dict], organ_index: dict, *,
                              fetch: Callable[[str], str], bto_crosswalk: Optional[dict] = None) -> dict:
    biomodel_dos, organ_to_models = [], {}
    for m in model_dos:
        bid = m["biomodel_id"]
        try:
            sbml = fetch(bid)
        except Exception:  # noqa: BLE001 — unfetchable model contributes nothing
            sbml = None
        do = (annotate_model(bid, organ_index, sbml_text=sbml, bto_crosswalk=bto_crosswalk,
                              name=m.get("name")) if sbml is not None
              else {"biomodel_id": bid, "name": m.get("name"), "organs": [],
                    "provenance": {"annotation": "miriam-match@SBML", "source": "biomodels",
                                   "error": "sbml_unavailable"}})
        biomodel_dos.append(do)
        for o in do["organs"]:
            organ_to_models.setdefault(o["uberon"], []).append(bid)
    return {"biomodel_dos": biomodel_dos, "organ_index": organ_index,
            "organ_to_models": organ_to_models}
