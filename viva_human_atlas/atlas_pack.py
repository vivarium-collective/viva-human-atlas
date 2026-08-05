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


def _glbs_by_sex(asset_urls: list[str]) -> dict:
    """ALL same-sex GLB assets per organ, not just the first — bilateral organs
    (kidney L/R, ureters) and multi-part organs ship several GLBs per sex, so
    the viewer must load them all or half the organ is missing."""
    out = {"female": [], "male": []}
    for url in asset_urls or []:
        stem = url.rsplit("/", 1)[-1].lower()
        if "-f-" in stem:
            out["female"].append(url)
        elif "-m-" in stem:
            out["male"].append(url)
    # stems without the -f-/-m- convention -> treat all as the (female) default
    if not out["female"] and not out["male"] and asset_urls:
        out["female"] = list(asset_urls)
    return out


def build_atlas_manifest(catalog: dict, *, provenance: dict | None = None,
                         subregions: dict | None = None) -> dict:
    """Build the atlas manifest from a catalog `{biomodel_dos, organ_index,
    organ_to_models}`.

    If `provenance` is given as `{"name": {uberon: iterable[id]},
    "annotation": {uberon: iterable[id]}}`, each model row gets a `matched_by`
    list (subset of `["name", "annotation"]`) recording which matcher(s) linked
    that model to that organ — so the viewer can show where a link came from.

    If `subregions` is given as `{organ_uberon: {as_uberon: {"label",
    "uberon", "node_names", "models": [{biomodel_id, url, via}]}}}` (from
    `atlas_subregions.place_models`), each organ gets a `subregions` list of
    `{node_names, uberon, label, n_models, models}` so the viewer can color and
    hover anatomical structures individually. Organs always get a `subregions`
    key (empty list when none resolve) — the whole-organ `models`/`n_models`
    stay the fallback.
    """
    organ_index = catalog["organ_index"]
    organ_to_models = catalog["organ_to_models"]
    id_to_name = {d["biomodel_id"]: d.get("name") or d["biomodel_id"]
                  for d in catalog["biomodel_dos"]}
    prov = provenance or {}
    subs = subregions or {}
    name_sets = {u: set(ids) for u, ids in (prov.get("name") or {}).items()}
    anno_sets = {u: set(ids) for u, ids in (prov.get("annotation") or {}).items()}

    def _matched_by(uberon, mid):
        tags = []
        if mid in name_sets.get(uberon, ()):
            tags.append("name")
        if mid in anno_sets.get(uberon, ()):
            tags.append("annotation")
        return tags

    def _subregions_for(uberon):
        out = []
        for as_ub, sub in (subs.get(uberon) or {}).items():
            smodels = [{"biomodel_id": m["biomodel_id"],
                        "name": id_to_name.get(m["biomodel_id"], m["biomodel_id"]),
                        "url": m["url"], "via": m.get("via")}
                       for m in sub["models"]]
            out.append({"node_names": sub["node_names"], "uberon": sub["uberon"],
                        "label": sub["label"], "n_models": len(smodels),
                        "models": smodels})
        out.sort(key=lambda s: (-s["n_models"], s["label"] or ""))
        return out

    organs = []
    all_model_ids = set()
    n_subregions = 0
    n_organs_with_subregions = 0
    for key, entry in organ_index.items():
        uberon = entry.get("uberon")
        model_ids = sorted(organ_to_models.get(uberon, [])) if uberon else []
        all_model_ids.update(model_ids)
        models = []
        for mid in model_ids:
            row = {"biomodel_id": mid, "name": id_to_name.get(mid, mid),
                   "url": biomodels_url(mid)}
            if provenance is not None:
                row["matched_by"] = _matched_by(uberon, mid)
            models.append(row)
        sub_list = _subregions_for(uberon) if uberon else []
        n_subregions += len(sub_list)
        if sub_list:
            n_organs_with_subregions += 1
        organs.append({
            "key": key,
            "label": _label(key),
            "uberon": uberon,
            "system": organ_system(key),
            "glb": _glb_by_sex(entry.get("asset_urls") or []),
            "glbs": _glbs_by_sex(entry.get("asset_urls") or []),
            "n_models": len(models),
            "models": models,
            "subregions": sub_list,
        })

    organs.sort(key=lambda o: (-o["n_models"], o["key"]))
    max_models = max((o["n_models"] for o in organs), default=0)
    max_subregion_models = max(
        (s["n_models"] for o in organs for s in o["subregions"]), default=0)
    present = {o["system"] for o in organs}
    systems = [s for s in SYSTEM_ORDER if s in present]
    return {
        "organs": organs,
        "systems": systems,
        "max_models": max_models,
        "max_subregion_models": max_subregion_models,
        "summary": {
            "n_organs": len(organs),
            "n_modeled": sum(1 for o in organs if o["n_models"] > 0),
            "n_models_total": sum(o["n_models"] for o in organs),
            "n_models_distinct": len(all_model_ids),
            "n_systems": len(systems),
            "n_subregions": n_subregions,
            "n_organs_with_subregions": n_organs_with_subregions,
        },
    }


def build_atlas_from_hra_map(db_entries, organ_index, hrapop_as, crosswalk,
                             **place_kw) -> tuple[dict, dict, dict]:
    """Assemble the atlas inputs from the BioModels->HRA map DB (Phase 1),
    replacing the old name/annotation catalogs.

    Builds `organ_to_models` (organ Uberon -> [biomodel_id]) and the id->name
    table straight from `db_entries`, then resolves subregion placement via
    `atlas_subregions.place_models`. Returns `(catalog, subregions,
    placement_stats)` ready for `build_atlas_manifest(catalog,
    subregions=subregions)`.
    """
    from viva_human_atlas.atlas_subregions import place_models

    id_to_name = {e["biomodel_id"]: e.get("name") or e["biomodel_id"] for e in db_entries}
    organ_to_models: dict[str, set] = {}
    for e in db_entries:
        for o in e.get("organs") or []:
            u = o.get("uberon")
            if u:
                organ_to_models.setdefault(u, set()).add(e["biomodel_id"])
    catalog = {
        "biomodel_dos": [{"biomodel_id": mid, "name": nm} for mid, nm in sorted(id_to_name.items())],
        "organ_index": organ_index,
        "organ_to_models": {u: sorted(ids) for u, ids in organ_to_models.items()},
    }
    placement = place_models(db_entries, hrapop_as, crosswalk, organ_index, **place_kw)
    return catalog, placement["subregions"], placement["stats"]


def merge_catalogs(name_catalog: dict, annotation_catalog: dict) -> tuple[dict, dict]:
    """Union two organ catalogs (name-synonym + annotation) into one catalog
    of the same shape, plus a `provenance` dict for `build_atlas_manifest`.

    organ_to_models is unioned per organ (deduped, sorted); biomodel_dos merges
    id->name from both. Returns `(merged_catalog, provenance)`.
    """
    organ_index = name_catalog["organ_index"]
    n_o2m = name_catalog["organ_to_models"]
    a_o2m = annotation_catalog["organ_to_models"]
    merged = {}
    for uberon in set(n_o2m) | set(a_o2m):
        merged[uberon] = sorted(set(n_o2m.get(uberon, [])) | set(a_o2m.get(uberon, [])))
    id_to_name = {}
    for cat in (annotation_catalog, name_catalog):  # name wins on label conflicts
        for d in cat["biomodel_dos"]:
            id_to_name.setdefault(d["biomodel_id"], d.get("name") or d["biomodel_id"])
    id_to_name.update({d["biomodel_id"]: d.get("name") or d["biomodel_id"]
                       for d in name_catalog["biomodel_dos"] if d.get("name")})
    biomodel_dos = [{"biomodel_id": mid, "name": nm} for mid, nm in sorted(id_to_name.items())]
    merged_catalog = {"biomodel_dos": biomodel_dos, "organ_index": organ_index,
                      "organ_to_models": merged}
    provenance = {"name": n_o2m, "annotation": a_o2m}
    return merged_catalog, provenance


# HRA "united" whole-body reference GLB (single-sex) for the viewer's optional
# overview backdrop.
DEFAULT_OVERVIEW_GLB = ("https://cdn.humanatlas.io/digital-objects/ref-organ/"
                        "united-female/v1.4/assets/3d-vh-f-united.glb")


def build_and_write_atlas(*, db_path=None, catalog_path, out_dir,
                          hrapop_csv=None, crosswalk_path=None,
                          overview_glb_url=DEFAULT_OVERVIEW_GLB, **place_kw) -> dict:
    """Offline end-to-end: build the Atlas Browser pack from the BioModels->HRA
    map DB (Phase 1) with organ-subregion placement, and write it to `out_dir`.

    `db_path` -> the biomodel_hra_map.json (organ->models + cell types/FTUs);
    `catalog_path` -> the committed corpus catalog (the 50 GLB `organ_index`);
    `hrapop_csv`/`crosswalk_path` default to the committed datasets. `place_kw`
    tunes `atlas_subregions.place_models` (enrichment, top_k, cross_organ_max).
    Returns `{"summary": manifest summary, "placement_stats": ...}`.
    """
    from viva_human_atlas.biomodel_hra import load_map, DEFAULT_DB_PATH
    from viva_human_atlas.hra_pop import load_hrapop_as
    from viva_human_atlas.atlas_subregions import load_crosswalk
    from viva_human_atlas.coverage import load_corpus_catalog

    db = load_map(db_path or DEFAULT_DB_PATH)
    organ_index = load_corpus_catalog(str(catalog_path))["organ_index"]
    hrapop_as = load_hrapop_as(hrapop_csv)
    crosswalk = load_crosswalk(crosswalk_path)
    catalog, subs, stats = build_atlas_from_hra_map(
        db, organ_index, hrapop_as, crosswalk, **place_kw)
    manifest = build_atlas_manifest(catalog, subregions=subs)
    write_atlas_pack(out_dir, manifest=manifest,
                     coverage={"coverage": [], "summary": {}},
                     overview_glb_url=overview_glb_url)
    return {"summary": manifest["summary"], "placement_stats": stats}


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
