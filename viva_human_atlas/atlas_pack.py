"""Build the HRA Atlas Browser manifest (atlas.json) from the committed
corpus catalog: one entry per GLB-backed HRA organ, its model count, and the
BioModels list, for the organ-selector + model-count-gradient viewer."""
from __future__ import annotations

import json
from pathlib import Path

BIOMODELS_BASE = "https://www.ebi.ac.uk/biomodels/"

# Anatomical-system grouping for the atlas browser's collapsible menu. Curated
# organ-key -> system map over the 50 GLB-backed HRA reference organs (kept
# transparent/inspectable rather than derived from a live ontology query).
# `SYSTEM_ORDER` fixes the display order; anything unmapped falls to "Other".
SYSTEM_ORDER = [
    "Digestive",
    "Cardiovascular",
    "Respiratory",
    "Nervous",
    "Urinary",
    "Reproductive",
    "Musculoskeletal",
    "Lymphatic / immune",
    "Integumentary",
    "Connective",
    "Other",
]
ORGAN_SYSTEMS = {
    # Digestive
    "pancreas": "Digestive", "liver": "Digestive", "intestine": "Digestive",
    "mouth": "Digestive", "omentum": "Digestive",
    "epiploic-appendage-of-transverse-colon": "Digestive",
    # Cardiovascular
    "heart": "Cardiovascular", "blood": "Cardiovascular",
    # Respiratory
    "lung": "Respiratory", "trachea": "Respiratory", "larynx": "Respiratory",
    "main-bronchus": "Respiratory",
    # Nervous
    "brain": "Nervous", "spinal-cord": "Nervous",
    "eye-female-left": "Nervous", "eye-female-right": "Nervous",
    "eye-male-left": "Nervous", "eye-male-right": "Nervous",
    # Urinary
    "kidney": "Urinary", "urinary-bladder": "Urinary",
    "ureter-female-left": "Urinary", "ureter-female-right": "Urinary",
    "ureter-male-left": "Urinary", "ureter-male-right": "Urinary",
    # Reproductive
    "uterus": "Reproductive", "prostate": "Reproductive",
    "placenta-full-term": "Reproductive",
    "fallopian-tube-female-left": "Reproductive",
    "fallopian-tube-female-right": "Reproductive",
    "ovary-female-left": "Reproductive", "ovary-female-right": "Reproductive",
    "mammary-gland-female-left": "Reproductive",
    "mammary-gland-female-right": "Reproductive",
    # Musculoskeletal
    "intervertebral-disk": "Musculoskeletal", "manubrium": "Musculoskeletal",
    "sternum": "Musculoskeletal", "pelvis": "Musculoskeletal",
    "knee-female-left": "Musculoskeletal", "knee-female-right": "Musculoskeletal",
    "knee-male-left": "Musculoskeletal", "knee-male-right": "Musculoskeletal",
    # Lymphatic / immune
    "lymph-node": "Lymphatic / immune", "spleen": "Lymphatic / immune",
    "thymus": "Lymphatic / immune",
    "palatine-tonsil-female-left": "Lymphatic / immune",
    "palatine-tonsil-female-right": "Lymphatic / immune",
    "palatine-tonsil-male-left": "Lymphatic / immune",
    "palatine-tonsil-male-right": "Lymphatic / immune",
    # Integumentary
    "skin": "Integumentary",
    # Connective
    "adipose": "Connective",
}


def biomodels_url(biomodel_id: str) -> str:
    return f"{BIOMODELS_BASE}{biomodel_id}"


def organ_system(key: str) -> str:
    """The anatomical system an organ key belongs to (``"Other"`` if unmapped)."""
    return ORGAN_SYSTEMS.get(key, "Other")


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
            "system": organ_system(key),
            "glb": _glb_by_sex(entry.get("asset_urls") or []),
            "n_models": len(models),
            "models": models,
        })

    organs.sort(key=lambda o: (-o["n_models"], o["key"]))
    max_models = max((o["n_models"] for o in organs), default=0)
    present = {o["system"] for o in organs}
    systems = [s for s in SYSTEM_ORDER if s in present]
    return {
        "organs": organs,
        "systems": systems,
        "max_models": max_models,
        "summary": {
            "n_organs": len(organs),
            "n_modeled": sum(1 for o in organs if o["n_models"] > 0),
            "n_models_total": sum(o["n_models"] for o in organs),
            "n_systems": len(systems),
        },
    }


def write_atlas_pack(out_dir, *, manifest: dict, coverage: dict, overview_glb_url=None):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "atlas.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (out / "coverage.json").write_text(json.dumps(coverage, indent=2), encoding="utf-8")
    (out / "config.json").write_text(json.dumps({
        "atlas": "atlas.json",
        "coverage": "coverage.json",
        "overview_glb": overview_glb_url,
        "node_field": "node_name",
    }, indent=2), encoding="utf-8")
    return out
