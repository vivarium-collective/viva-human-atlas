"""Map a Physiome Model Repository (PMR) CellML exposure to HRA organs.

PMR CellML models almost never carry machine-readable *organ* annotations (their
RDF is variable-level physiology + citations), so — unlike BioModels — the
reliable anatomical signal is the **PMR category** each model is filed under
(Cardiovascular Circulation, Electrophysiology, Endocrine, Ion Transport,
Metabolism, Neurobiology, ...). We map category -> organ deterministically, refine
the broad Electrophysiology bucket by title so neuron/gut models don't land on the
heart, and fall back to the shared physiology-keyword table. A model whose only
categories are organ-agnostic (Calcium Dynamics, Signal Transduction, Cell Cycle,
...) stays unmapped rather than being forced onto an organ. Every placement records
`mapping_method` (annotation > category > keyword > llm) and a coarse `confidence`.
"""
from __future__ import annotations

import re

from viva_human_atlas.annotation_match import _curie_from_uri
from viva_human_atlas.hra_mapping import map_to_hra
from viva_human_atlas.physionet_organ_map import DEFAULT_LLM_MODEL, keyword_uberons

# PMR category slug -> HRA organ key(s). Keys are resolved to UBERON ids through
# the live organ_index, so we never hardcode (and drift) an id; a category that
# maps to an organ absent from the reference set simply contributes nothing.
# Organ-agnostic categories are deliberately omitted -> their models stay unmapped.
CATEGORY_TO_ORGAN_KEYS: dict[str, list[str]] = {
    "electrophysiology": ["heart"],                    # default; refined by title below
    "cardiovascular_circulation": ["heart", "blood"],
    "excitation-contraction_coupling": ["heart"],
    "myofilament_mechanics": ["heart"],
    "hepatology": ["liver"],
    "ion_transport": ["kidney"],
    "ph_regulation": ["kidney"],
    "neurobiology": ["brain"],
    # NOTE: "metabolism" -> liver and "endocrine" -> pancreas are intentionally
    # NOT here. Both categories are too coarse for a confident blanket organ
    # mapping (metabolism spans generic/cellular/microbial models, not just
    # liver; endocrine spans thyroid/adrenal/pituitary, not just pancreas). Their
    # models are still harvested and fall through to the title-keyword path, so a
    # model whose title actually names the organ (e.g. "hepatic", "insulin")
    # still maps -- just on per-model evidence, not on the shelf it sits on.
}

# Electrophysiology spans cardiac / neuronal / smooth-muscle EP. Refine by title
# (first match wins) so non-cardiac EP models aren't blanket-placed on the heart;
# anything unmatched defaults to heart (the category's dominant anatomy).
_EP_REFINE: list[tuple[re.Pattern, list[str]]] = [
    (re.compile(r"neuron|neural|cortex|cortical|hippocamp|substantia nigra|"
                r"purkinje cell|thalam|interneuron|pyramidal|dopaminerg|\baxon\b|"
                r"cerebell|retina|photoreceptor", re.I), ["brain"]),
    (re.compile(r"smooth muscle|jejunal|jejunum|intestin|colon|\bgut\b|ileum|"
                r"duoden|gastrointestinal|enteric", re.I), ["intestine"]),
]

# Minimal whole-organ FMA -> UBERON crosswalk for the rare PMR model that DOES
# carry an anatomy annotation (CellML anatomy, when present, leans FMA; the HRA
# organ_index is keyed by UBERON). The long tail falls through to category/keyword.
FMA_TO_UBERON: dict[str, str] = {
    "FMA:7088": "UBERON:0000948",   # heart
    "FMA:50801": "UBERON:0000955",  # brain
    "FMA:7195": "UBERON:0001004",   # lung
    "FMA:7203": "UBERON:0004538",   # kidney
    "FMA:7197": "UBERON:0002107",   # liver
    "FMA:7198": "UBERON:0001264",   # pancreas
    "FMA:7163": "UBERON:0002097",   # skin
}

_RESOURCE_RE = re.compile(r'resource\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)
_MOLECULAR = ("chebi", "go")
_CONFIDENCE = {"annotation": "high", "category": "medium", "keyword": "medium", "llm": "low"}


def _molecular_curie(uri: str, prefix: str) -> str | None:
    u = uri.replace("%3A", ":").replace("%3a", ":")
    if f"/{prefix}/" not in u.lower() and f":{prefix}:" not in u.lower():
        return None
    tail = u.rsplit("/", 1)[-1].rsplit(":", 1)[-1].rsplit("_", 1)[-1]
    return f"{prefix.upper()}:{tail}" if tail else None


def extract_cellml_curies(cellml_text: str) -> dict:
    """Pull anatomy (UBERON/FMA) + molecular (CHEBI/GO) CURIEs from a CellML
    model's RDF `rdf:resource` URIs. Anatomy is near-empty in practice for PMR
    (kept because a handful of models do carry it, at high confidence)."""
    out = {"uberon": [], "fma": [], "chebi": [], "go": []}
    for uri in _RESOURCE_RE.findall(cellml_text or ""):
        cur = _curie_from_uri(uri)
        if cur:
            pref = cur.split(":", 1)[0].lower()
            if pref in ("uberon", "fma"):
                out[pref].append(cur)
            continue
        for p in _MOLECULAR:
            m = _molecular_curie(uri, p)
            if m:
                out[p].append(m)
                break
    return {k: list(dict.fromkeys(v)) for k, v in out.items()}


def _ep_refine(title: str) -> list[str]:
    for pat, keys in _EP_REFINE:
        if pat.search(title or ""):
            return keys
    return ["heart"]


def category_organ_keys(categories, title: str) -> list[str]:
    """Organ keys implied by an exposure's PMR categories (EP refined by title)."""
    keys: list[str] = []
    for c in categories or []:
        if c == "electrophysiology":
            keys += _ep_refine(title)
        else:
            keys += CATEGORY_TO_ORGAN_KEYS.get(c, [])
    return list(dict.fromkeys(keys))


def _keys_to_uberon(keys, organ_index) -> list[str]:
    out = []
    for k in keys:
        ub = (organ_index.get(k) or {}).get("uberon")
        if ub:
            out.append(ub)
    return list(dict.fromkeys(out))


def map_exposure_to_organs(exposure: dict, organ_index: dict, *, cellml_text: str = "",
                           no_llm: bool = True, llm_model: str = DEFAULT_LLM_MODEL,
                           cache_dir=None, _llm=None) -> dict:
    """Resolve one PMR exposure to HRA organs. Returns the `map_to_hra` dict plus
    `mapping_method`, `confidence`, and any extracted `molecular` CURIEs."""
    title = exposure.get("name") or ""
    categories = exposure.get("categories") or []
    curies = extract_cellml_curies(cellml_text)

    # 1) rare high-confidence path: an actual anatomy annotation in the model RDF
    ubs = list(curies["uberon"])
    for fma in curies["fma"]:
        ub = FMA_TO_UBERON.get(fma)
        if ub:
            ubs.append(ub)
    ubs = list(dict.fromkeys(ubs))
    method = "annotation" if ubs else None

    # 2) primary signal: the PMR category taxonomy (EP refined by title)
    if not ubs and categories:
        ubs = _keys_to_uberon(category_organ_keys(categories, title), organ_index)
        method = "category" if ubs else None

    # 3) fallback: physiology keyword in the title
    if not ubs:
        ubs = keyword_uberons([], title)
        method = "keyword" if ubs else None

    # 4) last resort: LLM over the title (off by default)
    if not ubs and not no_llm:
        extract = _llm
        if extract is None:
            from viva_human_atlas import llm_extract
            extract = llm_extract.extract
        try:
            facts = extract(title, exposure.get("abstract") or "", None,
                            model=llm_model, cache_dir=cache_dir) or {}
            ubs = list(dict.fromkeys(facts.get("candidate_uberon") or []))
            if ubs:
                method = "llm"
        except Exception:  # noqa: BLE001 — fallback never aborts a harvest
            ubs = []

    molecular = {"chebi": curies["chebi"], "go": curies["go"]}
    anatomy_ids = {"uberon": curies["uberon"], "fma": curies["fma"]}
    if not ubs:
        return {"organs": [], "functional_tissue_units": [], "cell_types": [],
                "uberon_organ_ids": [], "uberon_subregion_ids": [],
                "mapping_method": "unmapped", "confidence": "none",
                "molecular": molecular, "anatomy_ids": anatomy_ids}

    hra = map_to_hra(ubs, title, organ_index)
    hra["mapping_method"] = method
    hra["confidence"] = _CONFIDENCE.get(method, "low")
    hra["molecular"] = molecular
    hra["anatomy_ids"] = anatomy_ids
    return hra
