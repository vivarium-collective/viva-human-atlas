"""Map a PhysioNet project to HRA organs: a curated physiology-keyword -> UBERON
organ table first (deterministic, offline), then the shared LLM organ-mapper as a
fallback for the unmapped tail. UBERON ids are bound to HRA organs via the same
`hra_mapping.map_to_hra` the BioModels path uses."""
from __future__ import annotations

from typing import Optional

from viva_human_atlas.hra_mapping import map_to_hra

DEFAULT_LLM_MODEL = "claude-haiku-4-5-20251001"

# lowercase keyword/substring -> UBERON organ CURIE(s), curated against the
# ~50 GLB-backed HRA reference organs the atlas viewer knows (verified against
# a live `biomodel_do.build_organ_index()` -- see task-3-report.md for the
# corrections made to the ids originally drafted in the brief).
#
# Some physiology keywords (EMG/muscle, gait) have no corresponding organ in
# the current HRA reference-organ set (no muscle or musculoskeletal GLB), so
# they are intentionally left out of this table and fall through to the LLM
# fallback / unmapped path instead of pointing at a UBERON id that would never
# resolve to an organ.
KEYWORD_TO_ORGAN: dict[str, list[str]] = {
    "ecg": ["UBERON:0000948"], "electrocardiogram": ["UBERON:0000948"],
    "arrhythmia": ["UBERON:0000948"], "cardiac": ["UBERON:0000948"],
    "heart": ["UBERON:0000948"], "ppg": ["UBERON:0000948"],
    "eeg": ["UBERON:0000955"], "electroencephalogram": ["UBERON:0000955"],
    "brain": ["UBERON:0000955"], "seizure": ["UBERON:0000955"], "sleep": ["UBERON:0000955"],
    "respiratory": ["UBERON:0001004"], "lung": ["UBERON:0001004"], "pulmonary": ["UBERON:0001004"],
    # eye organs are left/right-specific in the HRA index (no single generic
    # "eye" uberon id); include both so either side resolves.
    "eog": ["UBERON:0004548", "UBERON:0004549"], "eye": ["UBERON:0004548", "UBERON:0004549"],
    "retina": ["UBERON:0004548", "UBERON:0004549"],
    "renal": ["UBERON:0004538"], "kidney": ["UBERON:0004538"],
    "liver": ["UBERON:0002107"], "hepatic": ["UBERON:0002107"],
    "glucose": ["UBERON:0001264"], "pancreas": ["UBERON:0001264"], "diabetes": ["UBERON:0001264"],
    "skin": ["UBERON:0002097"], "eda": ["UBERON:0002097"],
}


def keyword_uberons(keywords, title: str) -> list[str]:
    hay = " ".join([*(keywords or []), title or ""]).lower()
    out: list[str] = []
    for kw, ubs in KEYWORD_TO_ORGAN.items():
        if kw in hay:
            out.extend(ubs)
    # stable de-dup
    return list(dict.fromkeys(out))


def map_project_to_organs(project: dict, organ_index: dict, *, no_llm: bool = True,
                          llm_model: str = DEFAULT_LLM_MODEL, cache_dir=None,
                          _llm=None) -> dict:
    title = project.get("name") or ""
    ubs = keyword_uberons(project.get("keywords") or [], title)
    method = "keyword" if ubs else None

    if not ubs and not no_llm:
        extract = _llm
        if extract is None:
            from viva_human_atlas import llm_extract
            extract = llm_extract.extract
        try:
            facts = extract(title, project.get("abstract") or "", None,
                            model=llm_model, cache_dir=cache_dir) or {}
            ubs = list(dict.fromkeys(facts.get("candidate_uberon") or []))
            if ubs:
                method = "llm"
        except Exception:  # noqa: BLE001 — fallback never aborts a harvest
            ubs = []

    if not ubs:
        return {"organs": [], "functional_tissue_units": [], "cell_types": [],
                "uberon_organ_ids": [], "uberon_subregion_ids": [], "mapping_method": "unmapped"}

    hra = map_to_hra(ubs, title, organ_index)
    hra["mapping_method"] = method or "keyword"
    return hra
