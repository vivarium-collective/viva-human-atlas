"""Place BioModels at HRA organ SUBREGIONS (anatomical structures) for the
Atlas Browser, driven up from each model's cell types + FTUs.

The Atlas Browser used to color every mesh of an organ GLB with one
organ-level count (models distributed uniformly within an organ). This module
resolves, per model, the specific anatomical structure(s) it belongs to, so
subregions can be colored/hovered individually — falling back to the whole
organ where the data can't resolve a subregion.

Signal + join:
- HRApop (`hra_pop.load_hrapop_as`) gives, per organ, each anatomical
  structure's (AS) cell-type composition (AS Uberon <-> cell type).
- The committed ASCT+B-3D crosswalk (`datasets/hra_asctb_crosswalk.csv`,
  `hra_api.fetch_crosswalk` cached) bridges an AS Uberon to the GLB scene-node
  name(s) the viewer colors.

Placement is many-to-many and specificity-gated (a cell-type model can map to
several subregions across several organs — cell types aren't organ-specific;
FTUs usually are but that isn't assumed since the join is by Uberon):
1. FTU / model-subregion Uberon == AS Uberon  -> place there (`via="ftu"`),
   strongest, may cross organs.
2. Cell-type ENRICHMENT: place at an AS where a model cell type is
   over-represented relative to the organ average (E >= threshold), not merely
   present — this avoids the "largest-sampled AS wins" bias. Top-k AS per
   organ; a stricter threshold gates placement into organs the model isn't
   even tagged to.
3. Whole-organ fallback for any tagged organ that resolves no subregion.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Optional

_REPO = Path(__file__).resolve().parents[1]
DEFAULT_CROSSWALK = _REPO / "datasets" / "hra_asctb_crosswalk.csv"

# Enrichment gate for cell-type -> subregion placement. E(cl, AS) = fraction of
# the AS that is `cl`, divided by the fraction of the whole organ that is `cl`;
# > 1 means `cl` is over-represented in that AS relative to the organ average.
DEFAULT_ENRICHMENT = 1.25      # AS must be >1.25x the organ-average for the cell type
DEFAULT_TOP_K = 1              # the single most-enriched AS per (model, organ)
DEFAULT_CROSS_ENRICHMENT = 3.0  # stricter bar to enter an UNtagged organ
# Cross-organ cell-type placement (a model landing in an organ it isn't tagged
# to) is OFF by default: the generic cell types most models carry (from the
# MeSH crosswalk) are not specific enough to place cross-organ without smearing
# many models onto whichever organ has the most anatomical structures (colon,
# lung). Within-organ subregion resolution is the clean, defensible signal.
# Raise this (with a high cross_enrichment) to opt into multi-organ placement.
DEFAULT_CROSS_ORGAN_MAX = 0     # extra (untagged) organs a model may enter


def _words(s: str) -> set:
    return set((s or "").lower().replace("-", " ").split())


def load_crosswalk(path=None) -> list:
    """Load the committed ASCT+B-3D crosswalk rows (AS Uberon -> GLB node)."""
    p = Path(path) if path else DEFAULT_CROSSWALK
    if not p.exists():
        return []
    with open(p, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _mirror_name(node: str):
    """The left/right twin of a bilateral GLB mesh name, or None. The ASCT+B-3D
    crosswalk names bilateral meshes `<base>_L` / `<base>_R` (e.g.
    `Allen_olfactory_bulb_L`); return the opposite side's name."""
    m = re.search(r"^(.*)_([LR])$", node or "")
    if not m:
        return None
    return f"{m.group(1)}_{'R' if m.group(2) == 'L' else 'L'}"


def _nodes_by_uberon(crosswalk: list) -> dict:
    """AS Uberon CURIE -> list of {node_name, label, organ_glb}.

    Bilateral robustness: some bilateral structures annotate the Uberon on only
    ONE side's mesh (e.g. `Allen_olfactory_bulb_L` has UBERON:0002264 but
    `Allen_olfactory_bulb_R`'s row leaves it blank). So after indexing the
    annotated nodes, each node's `_L`/`_R` mesh twin (if it exists in the
    crosswalk) is added under the same Uberon — so both sides color."""
    all_nodes = {}
    for r in crosswalk:
        n = (r.get("node_name") or "").strip()
        if n:
            all_nodes[n] = r
    idx: dict[str, list] = {}
    for r in crosswalk:
        ub = (r.get("uberon") or "").strip()
        node = (r.get("node_name") or "").strip()
        if not ub or not node:
            continue
        entries = idx.setdefault(ub, [])
        seen = {e["node_name"] for e in entries}
        for nm in (node, _mirror_name(node)):
            if not nm or nm in seen or nm not in all_nodes:
                continue
            seen.add(nm)
            twin = all_nodes[nm]
            entries.append({
                "node_name": nm,
                "label": (r.get("label") or twin.get("label") or "").strip(),
                # the twin declares its own organ_glb; fall back to this row's
                "organ_glb": (twin.get("organ_glb") or r.get("organ_glb") or "").strip(),
            })
    return idx


def _hrapop_to_organ_uberon(hrapop_as: dict, organ_index: dict) -> dict:
    """Map each HRApop organ key (prose, e.g. 'large intestine', 'Left kidney')
    to the atlas organ Uberon it belongs to, by word-subset match of the
    HRApop name against the organ_index organ keys (slugs). Returns
    `{hrapop_key: organ_uberon}` (unmatched HRApop organs are omitted)."""
    out = {}
    for hk in hrapop_as:
        hw = _words(hk)
        for okey, entry in organ_index.items():
            ub = entry.get("uberon")
            if not ub:
                continue
            ow = _words(okey)
            if hw <= ow or ow <= hw:
                out[hk] = ub
                break
    return out


def _enrichment(cts: dict, as_total: float, cl_organ: float, organ_total: float) -> float:
    """E = (AS fraction that is cl) / (organ fraction that is cl)."""
    if as_total <= 0 or cl_organ <= 0 or organ_total <= 0:
        return 0.0
    return (cts / as_total) / (cl_organ / organ_total)


def place_models(
    db_entries: list,
    hrapop_as: dict,
    crosswalk: list,
    organ_index: dict,
    *,
    enrichment: float = DEFAULT_ENRICHMENT,
    top_k: int = DEFAULT_TOP_K,
    cross_enrichment: float = DEFAULT_CROSS_ENRICHMENT,
    cross_organ_max: int = DEFAULT_CROSS_ORGAN_MAX,
) -> dict:
    """Resolve each model to organ subregion(s).

    `db_entries` rows are keyed by `source_id` (falling back to `biomodel_id`
    for pre-multi-source rows), so this places BioModels and PhysioNet
    entries alike -- each model's `repository` decides its rendered link.

    Returns `{"subregions": {organ_uberon: {as_uberon: {"label", "uberon",
    "node_names": [...], "models": [{source_id, repository, name, url,
    via}]}}}, "stats": {n_models_placed, n_subregion_models, n_ftu_models,
    n_cell_type_models, n_placements}}`.
    """
    nodes_by_uberon = _nodes_by_uberon(crosswalk)
    hk_to_organ_ub = _hrapop_to_organ_uberon(hrapop_as, organ_index)
    # organ Uberon -> the organ-key words, to check a crosswalk node's
    # `organ_glb` (e.g. "VH_F_Kidney_L") really belongs to that organ's GLB.
    organ_ub_kw = {e["uberon"]: _words(k) for k, e in organ_index.items() if e.get("uberon")}

    def _gtok(s):
        return set((s or "").lower().replace("-", " ").replace("_", " ").split())

    def _node_names_for(organ_ub, as_ub):
        """The GLB node names for this AS that belong to `organ_ub`'s GLB:
        keep a node whose `organ_glb` token-set covers the organ's key words
        (or has no organ_glb declared — treated as a wildcard)."""
        kw = organ_ub_kw.get(organ_ub, set())
        out = set()
        for n in nodes_by_uberon.get(as_ub, []):
            glb = n["organ_glb"]
            if not glb or (kw and kw <= _gtok(glb)):
                out.add(n["node_name"])
        return sorted(out)

    # subregions[organ_uberon][as_uberon] -> {label, uberon, node_names, models{mid: via}}
    subregions: dict = {}
    stats = {"n_models_placed": 0, "n_subregion_models": 0, "n_anatomy_models": 0,
             "n_cell_type_models": 0, "n_placements": 0}

    def _add(organ_ub, as_ub, as_label, mid, name, via):
        if as_ub == organ_ub:
            return False  # the whole organ, not a subregion
        node_names = _node_names_for(organ_ub, as_ub)
        if not node_names:
            return False  # no GLB mesh for this AS in this organ -> can't show
        label = as_label
        if not label:
            nodes = nodes_by_uberon.get(as_ub, [])
            label = nodes[0]["label"] if nodes else as_ub
        # skip a "subregion" that is really the whole organ under a different
        # Uberon id (label matches the organ's own name, e.g. "lung"/"skin")
        if _words(label) == organ_ub_kw.get(organ_ub, set()):
            return False
        org = subregions.setdefault(organ_ub, {})
        sub = org.get(as_ub)
        if sub is None:
            sub = org[as_ub] = {
                "uberon": as_ub,
                "label": label,
                "node_names": node_names,
                "models": {},
            }
        # a model's own anatomy annotation beats cell-type enrichment if it
        # reaches the same structure both ways
        if sub["models"].get(mid) != "anatomy":
            sub["models"][mid] = via
        return True

    id_to_entry: dict = {}
    for e in db_entries:
        mid = e.get("source_id") or e.get("biomodel_id")
        id_to_entry[mid] = e
        name = e.get("name") or mid
        cls = {c["cl"] for c in (e.get("cell_types") or []) if c.get("cl")}
        model_ftu_uberons = {f.get("uberon") for f in (e.get("functional_tissue_units") or []) if f.get("uberon")}
        model_organ_ubs = {o.get("uberon") for o in (e.get("organs") or []) if o.get("uberon")}

        placed_here = False
        placed_anat = False
        placed_ct = False

        # (1) Anatomy the model itself carries — its FTU Uberons + its ontology
        # Uberons — that maps to a specific GLB mesh in the crosswalk -> place
        # the model at that anatomical structure, under whichever organ's GLB
        # contains the mesh. `_add` filters meshes to the organ (via organ_glb)
        # and skips organ-level Uberons (as_ub == organ_ub), so only genuine
        # subregions land. This is the model's own strongest subregion signal.
        anatomy_ubs = set(model_ftu_uberons) | set((e.get("ontology_ids") or {}).get("uberon") or [])
        for u in anatomy_ubs:
            if u not in nodes_by_uberon:
                continue
            for organ_ub in organ_ub_kw:
                if _add(organ_ub, u, None, mid, name, "anatomy"):
                    placed_here = placed_anat = True

        # (2) cell-type enrichment. Score every (organ, AS); tagged organs use
        # the base gate, untagged organs the stricter cross gate.
        if cls:
            tagged_hks = {hk for hk, ub in hk_to_organ_ub.items() if ub in model_organ_ubs}
            cross_hits = []  # (best_E, hk) for untagged organs
            for hk, odata in hrapop_as.items():
                organ_ub = hk_to_organ_ub.get(hk)
                if organ_ub is None:
                    continue
                is_tagged = hk in tagged_hks
                gate = enrichment if is_tagged else cross_enrichment
                scored = []
                for a_ub, a in odata["as"].items():
                    best = 0.0
                    for cl in cls:
                        if cl in a["cts"]:
                            best = max(best, _enrichment(
                                a["cts"][cl], a["total"],
                                odata["cl_organ_count"].get(cl, 0.0), odata["organ_total"]))
                    if best >= gate:
                        scored.append((best, a_ub, a["label"]))
                if not scored:
                    continue
                scored.sort(reverse=True)
                if is_tagged:
                    for _e, a_ub, a_label in scored[:top_k]:
                        if _add(organ_ub, a_ub, a_label, mid, name, "cell_type"):
                            placed_here = placed_ct = True
                else:
                    cross_hits.append((scored[0][0], hk, organ_ub, scored[:top_k]))
            # admit the strongest few untagged organs (off by default)
            cross_hits.sort(reverse=True)
            for _best, hk, organ_ub, scored in cross_hits[:cross_organ_max]:
                for _e, a_ub, a_label in scored:
                    if _add(organ_ub, a_ub, a_label, mid, name, "cell_type"):
                        placed_here = placed_ct = True

        if placed_here:
            stats["n_subregion_models"] += 1
        if placed_anat:
            stats["n_anatomy_models"] += 1
        if placed_ct:
            stats["n_cell_type_models"] += 1

    # finalize: models dict -> sorted list of source-aware rows (BioModels and
    # PhysioNet models can both land in a subregion -- e.g. an ECG project's
    # curated FTU anatomy under heart -- so the link must resolve per source,
    # not assume BioModels).
    from viva_human_atlas.atlas_pack import model_ref

    for org in subregions.values():
        for sub in org.values():
            sub["models"] = [
                {**model_ref(id_to_entry.get(mid, {"biomodel_id": mid, "name": mid})), "via": via}
                for mid, via in sorted(sub["models"].items())
            ]
            stats["n_placements"] += len(sub["models"])
    stats["n_models_placed"] = stats["n_subregion_models"]
    return {"subregions": subregions, "stats": stats}
