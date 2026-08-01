"""Build the HRA Atlas Browser manifest (atlas.json) from the committed
corpus catalog: one entry per GLB-backed HRA organ, its model count, and the
BioModels list, for the organ-selector + model-count-gradient viewer."""
from __future__ import annotations

BIOMODELS_BASE = "https://www.ebi.ac.uk/biomodels/"


def biomodels_url(biomodel_id: str) -> str:
    return f"{BIOMODELS_BASE}{biomodel_id}"


def _label(key: str) -> str:
    return key.replace("-", " ").title()


def _glb_by_sex(asset_urls: list[str]) -> dict:
    out = {"female": None, "male": None}
    for url in asset_urls or []:
        stem = url.rsplit("/", 1)[-1].lower()
        if "-f-" in stem and out["female"] is None:
            out["female"] = url
        elif "-m-" in stem and out["male"] is None:
            out["male"] = url
    # organs whose stems don't follow the -f-/-m- convention: fall back to first
    if out["female"] is None and out["male"] is None and asset_urls:
        out["female"] = asset_urls[0]
    return out


def build_atlas_manifest(catalog: dict) -> dict:
    organ_index = catalog["organ_index"]
    organ_to_models = catalog["organ_to_models"]
    id_to_name = {d["biomodel_id"]: d.get("name") or d["biomodel_id"]
                  for d in catalog["biomodel_dos"]}

    organs = []
    for key, entry in organ_index.items():
        uberon = entry.get("uberon")
        model_ids = sorted(organ_to_models.get(uberon, [])) if uberon else []
        models = [{"biomodel_id": mid,
                   "name": id_to_name.get(mid, mid),
                   "url": biomodels_url(mid)}
                  for mid in model_ids]
        organs.append({
            "key": key,
            "label": _label(key),
            "uberon": uberon,
            "glb": _glb_by_sex(entry.get("asset_urls") or []),
            "n_models": len(models),
            "models": models,
        })

    organs.sort(key=lambda o: (-o["n_models"], o["key"]))
    max_models = max((o["n_models"] for o in organs), default=0)
    return {
        "organs": organs,
        "max_models": max_models,
        "summary": {
            "n_organs": len(organs),
            "n_modeled": sum(1 for o in organs if o["n_models"] > 0),
            "n_models_total": sum(o["n_models"] for o in organs),
        },
    }
