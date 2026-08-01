"""Compare the name-synonym organ catalog with the annotation (MIRIAM)
catalog: how many more organs and models the annotation matcher reaches."""
from __future__ import annotations


def _uberon_to_organ(organ_index):
    return {e["uberon"]: k for k, e in organ_index.items() if e.get("uberon")}


def _stats(catalog, u2o):
    o2m = catalog["organ_to_models"]
    organs = sorted({u2o.get(u, u) for u in o2m})
    models = {m for ids in o2m.values() for m in ids}
    return {"organs": organs, "n_models_total": len(models),
            "n_models_tagged": len(models), "_by_organ": o2m}


def compare_catalogs(name_catalog: dict, annotation_catalog: dict) -> dict:
    u2o = _uberon_to_organ(name_catalog["organ_index"])
    name, anno = _stats(name_catalog, u2o), _stats(annotation_catalog, u2o)
    all_ub = set(name["_by_organ"]) | set(anno["_by_organ"])
    per_organ, union_models = [], set()
    for ub in sorted(all_ub, key=lambda u: u2o.get(u, u)):
        nm, am = set(name["_by_organ"].get(ub, [])), set(anno["_by_organ"].get(ub, []))
        um = nm | am
        union_models |= um
        per_organ.append({"organ": u2o.get(ub, ub), "uberon": ub,
                          "name_models": len(nm), "annotation_models": len(am),
                          "union_models": len(um), "added": bool(am - nm)})
    union_organs = sorted({u2o.get(u, u) for u in all_ub})
    organs_added = sorted(set(anno["organs"]) - set(name["organs"]))
    n_corpus = len(name_catalog["biomodel_dos"]) or 1
    def strip(s): return {k: v for k, v in s.items() if not k.startswith("_")}
    return {
        "name": strip(name), "annotation": strip(anno),
        "union": {"organs": union_organs, "n_models_total": len(union_models),
                  "n_models_tagged": len(union_models)},
        "delta": {"organs_added": organs_added,
                  "n_models_added": len(union_models) - name["n_models_total"],
                  "per_organ": per_organ},
        "summary": {"pct_corpus_tagged_name": round(100 * name["n_models_total"] / n_corpus, 1),
                    "pct_corpus_tagged_annotation": round(100 * anno["n_models_total"] / n_corpus, 1)},
    }
