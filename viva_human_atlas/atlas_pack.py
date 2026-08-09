"""Build the HRA Computational Model Atlas manifest (atlas.json) from the committed
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


def model_url(entry: dict) -> str:
    """Link to a model's landing page, per source. Entries missing a
    `repository` field (legacy BioModels-only catalogs, from before the
    multi-source DB) default to "biomodels" so old callers keep working."""
    if entry.get("repository", "biomodels") == "biomodels":
        return biomodels_url(entry.get("source_id") or entry.get("biomodel_id"))
    return entry.get("identifier") or ""


def model_ref(entry: dict) -> dict:
    """Source-aware model reference `{source_id, repository, url, name}` for
    an atlas manifest row -- unions BioModels + PhysioNet (and any future
    source) into one shape."""
    return {"source_id": entry.get("source_id") or entry.get("biomodel_id"),
            "repository": entry.get("repository", "biomodels"),
            "url": model_url(entry), "name": entry.get("name") or entry.get("source_id")}


def organ_system(key: str) -> str:
    """The anatomical system an organ key belongs to (``"Other"`` if unmapped).
    Legacy curated fallback for organs the HRA anatomical-systems partonomy
    doesn't cover (see ``load_anatomical_systems``)."""
    return ORGAN_SYSTEMS.get(key, "Other")


DEFAULT_ASCTB_TABLES = Path(__file__).resolve().parents[1] / "datasets" / "asctb_tables.json"


def _norm_label(s) -> str:
    return " ".join((s or "").lower().replace("-", " ").split())


_SEX_SIDE = {"female", "male", "left", "right"}


def _system_for(key: str, uberon, systems_map: dict | None) -> str:
    """The HRA anatomical system for a GLB organ: match by AS Uberon, then by
    organ label, then by the label with sex/side words stripped (so
    `eye-female-left` -> `eye`). Genuinely unmatched organs fall to "Other" so
    grouping stays purely HRA (no mixed curated/HRA names)."""
    sm = systems_map or {}
    if not sm:
        # No HRA systems data supplied (e.g. unit tests / degraded build): keep
        # the legacy curated organ->system fallback.
        return organ_system(key)
    if uberon and sm.get(uberon):
        return sm[uberon]
    label = _norm_label(_label(key))
    if sm.get("label:" + label):
        return sm["label:" + label]
    base = " ".join(w for w in label.split() if w not in _SEX_SIDE)
    if base and sm.get("label:" + base):
        return sm["label:" + base]
    return "Other"


def load_anatomical_systems(path=None) -> tuple[dict, list]:
    """Group organs by the HRA **anatomical systems** partonomy (rather than a
    hand-curated organ->system map). Reads the harvested ASCT+B
    `anatomical-systems` table: each row's `anatomical_structures` chain is
    [anatomical system, SYSTEM, ...organ]; element [1] is the system and every
    deeper node belongs to it. Returns `(uberon_to_system, system_order)` where
    system labels are title-cased HRA names (e.g. "Cardiovascular System")."""
    p = Path(path) if path else DEFAULT_ASCTB_TABLES
    if not p.exists():
        return {}, []
    try:
        tables = json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}, []
    # keyed by both the AS Uberon and a normalized `label:<name>` (the GLB organs
    # often use a different-granularity Uberon than the partonomy, so a name
    # fallback recovers pancreas/kidney/lung/etc.).
    systems_map: dict[str, str] = {}
    order: list[str] = []
    for row in tables.get("anatomical-systems") or []:
        chain = row.get("anatomical_structures") or []
        if len(chain) < 2:
            continue
        system = (chain[1].get("label") or "").strip().title()
        if not system:
            continue
        if system not in order:
            order.append(system)
        for node in chain[2:]:
            u = node.get("id")
            if u:
                systems_map.setdefault(u, system)
            lab = _norm_label(node.get("label"))
            if lab:
                systems_map.setdefault("label:" + lab, system)
    return systems_map, order


def _label(key: str) -> str:
    return key.replace("-", " ").title()


# Biologically sex-specific organs whose key does NOT carry a `-female-`/`-male-`
# suffix (those are handled by the suffix check in `organ_sex`). GLB availability
# alone is NOT a reliable signal — unisex bones like manubrium/sternum ship only
# a female asset — so these are curated explicitly.
FEMALE_ONLY_ORGANS = {"placenta-full-term", "uterus"}
MALE_ONLY_ORGANS = {"prostate"}


def organ_sex(key: str) -> str:
    """"female" | "male" | "both" — which sex's anatomy an organ belongs to, so
    the viewer never shows female-specific anatomy (placenta, uterus, ovary…) in
    the male view or vice versa. Sex-specific organs are identified by a
    `-female-`/`-male-` key suffix OR the curated sets above; everything else is
    unisex ("both")."""
    if "-female" in key or key in FEMALE_ONLY_ORGANS:
        return "female"
    if "-male" in key or key in MALE_ONLY_ORGANS:
        return "male"
    return "both"


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
                         subregions: dict | None = None,
                         systems_map: dict | None = None,
                         systems_order: list | None = None) -> dict:
    """Build the atlas manifest from a catalog `{biomodel_dos, organ_index,
    organ_to_models}`.

    If `provenance` is given as `{"name": {uberon: iterable[id]},
    "annotation": {uberon: iterable[id]}}`, each model row gets a `matched_by`
    list (subset of `["name", "annotation"]`) recording which matcher(s) linked
    that model to that organ — so the viewer can show where a link came from.

    If `subregions` is given as `{organ_uberon: {as_uberon: {"label",
    "uberon", "node_names", "models": [{source_id, repository, url, name,
    via}]}}}` (from `atlas_subregions.place_models`), each organ gets a
    `subregions` list of `{node_names, uberon, label, n_models, models}` so
    the viewer can color and hover anatomical structures individually. Organs
    always get a `subregions` key (empty list when none resolve) — the
    whole-organ `models`/`n_models` stay the fallback.

    Each model row (whole-organ or subregion) is `model_ref`-shaped:
    `{source_id, repository, url, name}` (plus `via` for subregion rows,
    `matched_by` when `provenance` is given) -- source-aware so BioModels and
    PhysioNet (or any future source) render with correct links side by side.
    """
    organ_index = catalog["organ_index"]
    organ_to_models = catalog["organ_to_models"]
    # keyed by each row's own id (`biomodel_id` doubles as the generic
    # per-source id field -- for a PhysioNet row it holds the `source_id`
    # slug, per `build_atlas_from_hra_map`), so `model_ref` can resolve a
    # source-aware link even though the field name predates multi-source.
    id_to_entry = {d.get("biomodel_id") or d.get("source_id"): d
                   for d in catalog["biomodel_dos"]}
    id_to_name = {mid: e.get("name") or mid for mid, e in id_to_entry.items()}
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
            # `sub["models"]` rows are already `model_ref`-shaped (from
            # `atlas_subregions.place_models`); re-resolve `name` against this
            # manifest's own id_to_name so a catalog-level name correction
            # still wins (matches the pre-multi-source behavior).
            smodels = [{**m, "name": id_to_name.get(m["source_id"], m.get("name"))}
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
            model_entry = id_to_entry.get(mid, {"biomodel_id": mid, "name": mid})
            row = model_ref(model_entry)
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
            "system": _system_for(key, uberon, systems_map),
            "glb": _glb_by_sex(entry.get("asset_urls") or []),
            "glbs": _glbs_by_sex(entry.get("asset_urls") or []),
            "sex": organ_sex(key),
            "n_models": len(models),
            "models": models,
            "subregions": sub_list,
        })

    organs.sort(key=lambda o: (-o["n_models"], o["key"]))
    max_models = max((o["n_models"] for o in organs), default=0)
    max_subregion_models = max(
        (s["n_models"] for o in organs for s in o["subregions"]), default=0)
    present = {o["system"] for o in organs}
    # Group by the HRA anatomical-systems partonomy order when supplied, else the
    # legacy curated SYSTEM_ORDER; "Other" last.
    order = list(systems_order or SYSTEM_ORDER) + ["Other"]
    systems = [s for s in order if s in present]
    systems += [s for s in present if s not in systems]  # any stragglers, stable
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


def _entry_key(e: dict) -> str:
    """The id an entry is keyed/counted by across the atlas, unique within a
    repository: `source_id` when present, falling back to `biomodel_id`
    (committed BioModels rows have no `source_id` field; PhysioNet rows do).
    `source_id`/`biomodel_id` don't collide across repositories in practice
    (BioModels ids are `BIOMD...`, PhysioNet ids are project slugs), so this
    alone is a safe global key; callers needing an unambiguous key can still
    pair it with the entry's `repository`."""
    return e.get("source_id") or e.get("biomodel_id")


def build_atlas_from_hra_map(db_entries, organ_index, hrapop_as, crosswalk,
                             **place_kw) -> tuple[dict, dict, dict]:
    """Assemble the atlas inputs from the unified model->HRA map DB (mixed
    BioModels + PhysioNet, see `_entry_key`), replacing the old
    name/annotation catalogs.

    Builds `organ_to_models` (organ Uberon -> [id]) and the id->entry table
    straight from `db_entries` (unioned across every `repository` present),
    then resolves subregion placement via `atlas_subregions.place_models`.
    Returns `(catalog, subregions, placement_stats)` ready for
    `build_atlas_manifest(catalog, subregions=subregions)`. Each
    `catalog["biomodel_dos"]` row keeps the legacy `biomodel_id`/`name` fields
    (still the id field's name, for BioModels-only readers of this shape) and
    adds `source_id`/`repository`/`identifier` so `model_ref` can resolve a
    source-aware link for both repositories -- a superset of the old
    BioModels-only row, not a replacement.
    """
    from viva_human_atlas.atlas_subregions import place_models

    entries_by_key = {_entry_key(e): e for e in db_entries}
    organ_to_models: dict[str, set] = {}
    for e in db_entries:
        mid = _entry_key(e)
        for o in e.get("organs") or []:
            u = o.get("uberon")
            if u:
                organ_to_models.setdefault(u, set()).add(mid)
    catalog = {
        "biomodel_dos": [
            {"biomodel_id": mid, "name": e.get("name") or mid,
             "source_id": e.get("source_id") or mid,
             "repository": e.get("repository", "biomodels"),
             "identifier": e.get("identifier")}
            for mid, e in sorted(entries_by_key.items())
        ],
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

    `db_path` -> the model_hra_map.json (organ->models + cell types/FTUs);
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
    systems_map, systems_order = load_anatomical_systems()
    manifest = build_atlas_manifest(catalog, subregions=subs,
                                    systems_map=systems_map, systems_order=systems_order)
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
