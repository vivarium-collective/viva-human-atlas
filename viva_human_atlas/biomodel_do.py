"""Biomodel Digital Objects: annotate glucose-regulation BioModels with HRA
Uberon organ terms, and build the inverse organ->models index.

This realizes the DynXR proposal's Aim 2 T2.1/T1.1: a minimal "biomodel DO"
links a BioModels entry to the HRA reference-organ set via transparent
keyword/synonym matching over the model name (T2.4 gap-filling), so a study
can ask "which glucose models touch the liver / pancreas / kidney?".
"""
from __future__ import annotations

from typing import Callable, Dict, List, Optional

from process_bigraph import Step

from viva_human_atlas.biomodels_search import search_biomodels_detailed
from viva_human_atlas.hra_api import fetch_reference_organs

# organ key -> keyword synonyms used to scan biomodel names/descriptions.
# Deliberately simple substring matching, kept transparent/inspectable
# rather than a black-box classifier (proposal T2.4: transparent gap-filling).
ORGAN_SYNONYMS: Dict[str, List[str]] = {
    "pancreas": ["pancrea", "islet", "beta cell", "beta-cell", "β-cell", "insulin", "glucagon"],
    "liver": ["liver", "hepatic", "hepatocyte"],
    "kidney": ["kidney", "renal", "nephron"],
    "adipose": ["adipose", "adipocyte", "fat tissue"],
    "muscle": ["skeletal muscle", "myocyte", "myotube"],
    "intestine": ["intestine", "intestinal", "gut", "enteric"],
    "blood": ["blood", "plasma", "circulation"],
}


def _match_organ_key(text: str) -> Optional[str]:
    """Return the ORGAN_SYNONYMS key whose name or a synonym occurs in `text`
    (lowercased), or None."""
    for organ_key, synonyms in ORGAN_SYNONYMS.items():
        candidates = [organ_key] + synonyms
        if any(candidate.lower() in text for candidate in candidates):
            return organ_key
    return None


def build_organ_index(
    reference_organs: Optional[List[dict]] = None,
    *,
    _get: Optional[Callable] = None,
) -> Dict[str, dict]:
    """Build `{organ_key: {"uberon", "sexes", "asset_urls"}}` from HRA
    reference organs, deduped across sex.

    Fetches via `hra_api.fetch_reference_organs` if `reference_organs` is
    None. Each reference organ's `organ` slug is matched to an
    `ORGAN_SYNONYMS` key when possible, else the slug itself is used as the
    key.
    """
    if reference_organs is None:
        reference_organs = fetch_reference_organs(_get=_get)

    index: Dict[str, dict] = {}
    for ro in reference_organs:
        slug = ro.get("organ", "")
        key = _match_organ_key(slug.replace("-", " ").lower()) or slug

        entry = index.setdefault(key, {"uberon": None, "sexes": [], "asset_urls": []})
        if not entry["uberon"] and ro.get("uberon"):
            entry["uberon"] = ro["uberon"]

        sex = ro.get("sex")
        if sex and sex not in entry["sexes"]:
            entry["sexes"].append(sex)

        asset_url = ro.get("asset_url")
        if asset_url and asset_url not in entry["asset_urls"]:
            entry["asset_urls"].append(asset_url)

    return index


def annotate_biomodel(
    biomodel_id: str,
    name: str,
    organ_index: Dict[str, dict],
    *,
    extra_text: str = "",
) -> dict:
    """Scan `name`/`extra_text` for each organ's synonyms and return a
    minimal biomodel Digital Object annotated with matching HRA organs."""
    haystack = f"{name} {extra_text}".lower()

    organs = []
    for organ_key, entry in organ_index.items():
        candidates = [organ_key] + ORGAN_SYNONYMS.get(organ_key, [])
        if any(candidate.lower() in haystack for candidate in candidates):
            organs.append({"organ": organ_key, "uberon": entry.get("uberon")})

    return {
        "biomodel_id": biomodel_id,
        "name": name,
        "organs": organs,
        "provenance": {
            "source": "biomodels",
            "annotation": "synonym-match@HRA-reference-organs",
        },
    }


def build_biomodel_do_catalog(
    query: str = "glucose regulation",
    max_results: int = 25,
    *,
    _get_search: Optional[Callable] = None,
    _get_hra: Optional[Callable] = None,
) -> dict:
    """Search BioModels, annotate each hit with HRA organs, and invert into
    an organ(Uberon CURIE)->model-ids index.

    Returns `{"biomodel_dos": [...], "organ_index": {...},
    "organ_to_models": {uberon: [biomodel_id, ...]}}`.
    """
    models = search_biomodels_detailed(query, max_results, _get=_get_search)
    organ_index = build_organ_index(_get=_get_hra)

    biomodel_dos = [
        annotate_biomodel(m["id"], m.get("name", ""), organ_index) for m in models
    ]

    organ_to_models: Dict[str, List[str]] = {}
    for do in biomodel_dos:
        for organ in do["organs"]:
            uberon = organ["uberon"]
            if uberon is None:
                continue
            organ_to_models.setdefault(uberon, []).append(do["biomodel_id"])

    return {
        "biomodel_dos": biomodel_dos,
        "organ_index": organ_index,
        "organ_to_models": organ_to_models,
    }


class BiomodelDOCatalogStep(Step):
    """Step: build the glucose-regulation biomodel-DO catalog (organs +
    inverse organ->models index).

    Searches BioModels for `query`, annotates each hit with HRA reference
    organs via transparent keyword/synonym matching over the model name
    (`annotate_biomodel`), and inverts the result into a Uberon-CURIE ->
    biomodel-id index (`build_organ_index` / `build_biomodel_do_catalog`).
    Realizes the DynXR proposal's Aim 2 T2.1/T1.1 minimal "biomodel DO".
    """

    description = (
        "Search BioModels for a text query, annotate each hit with HRA "
        "Uberon organ terms via transparent synonym-matching over the model "
        "name, and build the inverse organ->models index."
    )

    config_schema = {
        "query": "string",
        "max_results": "integer",
    }

    def inputs(self):
        return {}

    def outputs(self):
        return {"biomodel_dos": "list[biomodel_do]", "organ_to_models": "organ_to_models"}

    def update(self, inputs):
        catalog = build_biomodel_do_catalog(
            self.config.get("query", "glucose regulation"),
            int(self.config.get("max_results", 25)),
        )
        return {
            "biomodel_dos": catalog["biomodel_dos"],
            # `organ_to_models` is a `map[list[string]]`: unlike `tree`, Map's
            # apply only updates keys that already exist in state (see
            # bigraph_schema.methods.apply's Map handler) — brand-new keys
            # need the `_add` sentinel, same convention used by e.g.
            # viva_munk's GrowDivide for adding new agents.
            "organ_to_models": {"_add": catalog["organ_to_models"]},
        }


BiomodelDOCatalogStep.contract = {
    "summary": BiomodelDOCatalogStep.description,
    "outputs": {
        "biomodel_dos": (
            "One `biomodel_do` record per BioModels hit: `biomodel_id`, "
            "`name`, `organs` (list of `matched_organ` — organ slug + Uberon "
            "CURIE, one per HRA organ whose name/synonym matched), and "
            "`provenance` (annotation source/method)."
        ),
        "organ_to_models": (
            "Inverse index: Uberon CURIE -> list of `biomodel_id`s annotated "
            "with that organ."
        ),
    },
    "assumptions": [
        "Organ matching is transparent substring synonym-matching over the "
        "model name (`ORGAN_SYNONYMS`), not a learned classifier — a model "
        "with no matching synonym contributes no `matched_organ` and is "
        "absent from `organ_to_models`.",
    ],
}
