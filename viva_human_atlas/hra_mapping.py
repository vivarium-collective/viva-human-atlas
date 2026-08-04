"""Map a model's Uberon ids + name to HRA organs, FTUs (with Uberon), and the
FTUs' cell types (with CL) -- the curated HRA view for the biomodel-HRA DB."""
from __future__ import annotations

from typing import Optional

from viva_human_atlas.biomodel_do import _match_organ_key
from viva_human_atlas.ftu_coverage import HRA_FTUS


def _organ_words(s: str) -> set:
    """Normalize an organ label/slug to its lowercase word set."""
    return set((s or "").lower().replace("-", " ").split())


def _ftu_organ_matches(ftu_organ: str, organ_keys) -> bool:
    """True if an FTU's organ label refers to the same organ as any matched
    organ key.

    The two key spaces differ: `HRA_FTUS` uses prose labels ("small
    intestine", "lymph node", "ovary") while `organ_index` keys are HRA
    reference-organ slugs ("lymph-node", "ovary-female-left") or
    `ORGAN_SYNONYMS` keys ("intestine"). Exact string equality therefore
    misses real matches, so compare normalized word sets and accept either
    containment: `{intestine} <= {large, intestine}`,
    `{lymph, node} == {lymph, node}`, `{ovary} <= {ovary, female, left}`.
    Both small- and large-intestine FTUs attach to a generic `intestine`
    organ; that is intended.
    """
    ftu_words = _organ_words(ftu_organ)
    if not ftu_words:
        return False
    for key in organ_keys:
        key_words = _organ_words(key)
        if key_words and (ftu_words <= key_words or key_words <= ftu_words):
            return True
    return False


def map_to_hra(uberon_ids, name: str, organ_index: dict, *, ftus: Optional[list] = None) -> dict:
    """Map a model's Uberon ids and name onto the HRA's organs / FTUs / cell
    types.

    `uberon_ids` are the Uberon CURIEs extracted from the model (e.g. by the
    SBML annotation extractor); `organ_index` is a
    `{organ_key: {"uberon", ...}}` index as built by
    `biomodel_do.build_organ_index`. `ftus` defaults to
    `ftu_coverage.HRA_FTUS`.

    An id that matches an organ-level Uberon in `organ_index` is reported as
    an organ; every other id is reported as a subregion. Organ matches also
    come from the model `name` via `biomodel_do._match_organ_key`, which
    returns the `ORGAN_SYNONYMS` key whose name or synonym occurs in the
    text. FTUs are the curated FTUs whose organ matches one of those organs
    (word-set match, see `_ftu_organ_matches`), and `cell_types` are those
    FTUs' cell types (deduped by CL, first-seen order).

    Returns `{"organs": [{"label", "uberon"}], "functional_tissue_units":
    [{"label", "uberon"}], "cell_types": [{"label", "cl"}],
    "uberon_organ_ids": [...], "uberon_subregion_ids": [...]}`.
    """
    ftu_defs = ftus if ftus is not None else HRA_FTUS
    uberon_ids = list(uberon_ids or [])
    organ_uberons = {e["uberon"] for e in organ_index.values() if e.get("uberon")}

    # sorted + deduped, so repeated annotations in one model collapse.
    uberon_organ_ids = sorted({u for u in uberon_ids if u in organ_uberons})
    uberon_subregion_ids = sorted({u for u in uberon_ids if u not in organ_uberons})

    # organs: organ-level Uberon hits + name-synonym organ matches.
    ub_to_organ = {e["uberon"]: k for k, e in organ_index.items() if e.get("uberon")}
    organ_keys = {ub_to_organ[u] for u in uberon_organ_ids}
    name_key = _match_organ_key((name or "").lower())
    if name_key:
        organ_keys.add(name_key)
    organs = sorted(
        ({"label": k, "uberon": organ_index.get(k, {}).get("uberon")} for k in organ_keys),
        key=lambda o: o["label"],
    )

    # FTUs whose organ is among the model's organs (`organ_keys` already
    # includes `name_key`), carrying their Uberon + CL. Declaration order is
    # preserved: deterministic, and cell-type order is semantically meaningful.
    ftu_out, cell_types, seen_cl = [], [], set()
    for f in ftu_defs:
        if _ftu_organ_matches(f["organ"], organ_keys):
            ftu_out.append({"label": f["ftu"], "uberon": f.get("uberon")})
            for ct in f.get("cell_types", []):
                if ct["cl"] not in seen_cl:
                    seen_cl.add(ct["cl"])
                    cell_types.append({"label": ct["label"], "cl": ct["cl"]})

    return {
        "organs": organs,
        "functional_tissue_units": ftu_out,
        "cell_types": cell_types,
        "uberon_organ_ids": uberon_organ_ids,
        "uberon_subregion_ids": uberon_subregion_ids,
    }
