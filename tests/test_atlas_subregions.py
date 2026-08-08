"""Organ-subregion placement for the Atlas Browser (Phase 2).

Offline: `place_models` is exercised on a small synthetic DB + HRApop-AS dict +
crosswalk; `load_hrapop_as` on a tiny CSV; the manifest wiring + the end-to-end
`build_and_write_atlas` on the committed datasets; and `AtlasBrowserStep` via
`build_core()` writing a pack to tmp. No network.
"""
from __future__ import annotations

import json
from pathlib import Path

import viva_human_atlas.hra_pop as hra_pop
from viva_human_atlas.atlas_subregions import place_models, _mirror_name, _nodes_by_uberon
from viva_human_atlas.atlas_pack import (
    build_atlas_from_hra_map, build_atlas_manifest, build_and_write_atlas,
)
from viva_human_atlas.coverage import load_corpus_catalog
from viva_human_atlas.core import build_core
from viva_human_atlas.atlas_browser import AtlasBrowserStep

REPO = Path(__file__).resolve().parents[1]
CATALOG = REPO / "datasets" / "biomodel_corpus_catalog.json"

ORGAN_INDEX = {
    "kidney": {"uberon": "UBERON:0004538",
               "asset_urls": ["x/3d-vh-f-kidney-l.glb", "x/3d-vh-f-kidney-r.glb"]},
    "liver": {"uberon": "UBERON:0002107", "asset_urls": ["x/3d-vh-f-liver.glb"]},
    "lymph-node": {"uberon": "UBERON:0002509", "asset_urls": ["x/3d-nih-f-lymph-node.glb"]},
}

CROSSWALK = [
    {"node_name": "VH_F_outer_cortex_of_kidney_L", "label": "outer cortex of kidney",
     "uberon": "UBERON:0002189", "organ_glb": "VH_F_Kidney_L"},
    {"node_name": "VH_F_outer_cortex_of_kidney_R", "label": "outer cortex of kidney",
     "uberon": "UBERON:0002189", "organ_glb": "VH_F_Kidney_R"},
    {"node_name": "Yao_follicles", "label": "lymph node follicle",
     "uberon": "UBERON:0010748", "organ_glb": "NIH_F_Lymph_Node"},
]

# HRApop AS dict: podocyte enriched in kidney cortex (1.8x), not medulla.
HRAPOP_AS = {
    "kidney": {
        "raw_names": ["Left kidney"], "organ_total": 100.0,
        "cl_organ_count": {"CL:PODO": 10.0},
        "as": {
            "UBERON:0002189": {"label": "outer cortex of kidney", "total": 50.0, "cts": {"CL:PODO": 9.0}},
            "UBERON:0004200": {"label": "renal pyramid", "total": 50.0, "cts": {"CL:PODO": 1.0}},
        },
    },
}


def _kidney_model():
    return {"biomodel_id": "BIOMD1", "name": "Kidney model",
            "organs": [{"label": "kidney", "uberon": "UBERON:0004538"}],
            "cell_types": [{"cl": "CL:PODO"}], "functional_tissue_units": []}


def test_mirror_name_flips_left_right_suffix():
    assert _mirror_name("Allen_olfactory_bulb_L") == "Allen_olfactory_bulb_R"
    assert _mirror_name("Allen_olfactory_bulb_R") == "Allen_olfactory_bulb_L"
    assert _mirror_name("VH_F_liver") is None


def test_nodes_by_uberon_recovers_unannotated_bilateral_twin():
    # The crosswalk annotates the Uberon on the LEFT twin only; the RIGHT twin's
    # row has a blank uberon. Both meshes must still resolve under the Uberon.
    crosswalk = [
        {"node_name": "Allen_olfactory_bulb_L", "label": "olfactory bulb",
         "uberon": "UBERON:0002264", "organ_glb": "Allen_F_Brain"},
        {"node_name": "Allen_olfactory_bulb_R", "label": "",
         "uberon": "", "organ_glb": "Allen_F_Brain"},
    ]
    nodes = _nodes_by_uberon(crosswalk)["UBERON:0002264"]
    names = sorted(n["node_name"] for n in nodes)
    assert names == ["Allen_olfactory_bulb_L", "Allen_olfactory_bulb_R"]


def test_cell_type_enrichment_places_at_cortex_with_both_side_nodes():
    out = place_models([_kidney_model()], HRAPOP_AS, CROSSWALK, ORGAN_INDEX)
    subs = out["subregions"]["UBERON:0004538"]
    assert "UBERON:0002189" in subs                      # cortex resolved
    assert "UBERON:0004200" not in subs                  # pyramid not enriched
    sub = subs["UBERON:0002189"]
    assert sub["node_names"] == ["VH_F_outer_cortex_of_kidney_L", "VH_F_outer_cortex_of_kidney_R"]
    assert [m["source_id"] for m in sub["models"]] == ["BIOMD1"]
    assert sub["models"][0]["via"] == "cell_type"
    assert out["stats"]["n_cell_type_models"] == 1


def test_ftu_with_crosswalk_mesh_places_under_tagged_organ():
    model = {"biomodel_id": "BIOMD2", "name": "LN model",
             "organs": [{"label": "lymph-node", "uberon": "UBERON:0002509"}],
             "cell_types": [],
             "functional_tissue_units": [{"label": "lymph node follicle", "uberon": "UBERON:0010748"}]}
    out = place_models([model], HRAPOP_AS, CROSSWALK, ORGAN_INDEX)
    sub = out["subregions"]["UBERON:0002509"]["UBERON:0010748"]
    assert sub["models"][0]["via"] == "anatomy"
    assert sub["node_names"] == ["Yao_follicles"]
    assert out["stats"]["n_anatomy_models"] == 1


def test_wrong_organ_ftu_mesh_is_filtered_by_organ_glb():
    # A model tagged LIVER carrying the follicle FTU must NOT get a follicle
    # subregion under liver (the follicle mesh's organ_glb is a lymph node GLB).
    model = {"biomodel_id": "BIOMD3", "name": "x",
             "organs": [{"label": "liver", "uberon": "UBERON:0002107"}],
             "cell_types": [],
             "functional_tissue_units": [{"label": "lymph node follicle", "uberon": "UBERON:0010748"}]}
    out = place_models([model], HRAPOP_AS, CROSSWALK, ORGAN_INDEX)
    assert "UBERON:0002107" not in out["subregions"]


def test_cross_organ_off_by_default_keeps_subregion_within_organ():
    # A LIVER model whose cell type is enriched in kidney cortex stays out of
    # kidney by default (cross_organ_max=0).
    model = {"biomodel_id": "BIOMD4", "name": "x",
             "organs": [{"label": "liver", "uberon": "UBERON:0002107"}],
             "cell_types": [{"cl": "CL:PODO"}], "functional_tissue_units": []}
    out = place_models([model], HRAPOP_AS, CROSSWALK, ORGAN_INDEX)
    assert out["subregions"] == {} or "UBERON:0004538" not in out["subregions"]
    # ...but opting in admits it
    out2 = place_models([model], HRAPOP_AS, CROSSWALK, ORGAN_INDEX,
                        cross_organ_max=1, cross_enrichment=1.25)
    assert "UBERON:0004538" in out2["subregions"]


def test_load_hrapop_as_keeps_per_as_and_asctb_temp(tmp_path):
    csv = tmp_path / "hrapop.csv"
    csv.write_text(
        "organ,as,as_label,sex,tool,modality,cell_id,cell_label,cell_count,cell_percentage,dataset_count\n"
        "kidney,http://purl.obolibrary.org/obo/UBERON_0002189,outer cortex,F,x,y,http://purl.obolibrary.org/obo/CL_0000653,podocyte,9,0.9,1\n"
        "kidney,http://purl.obolibrary.org/obo/UBERON_0002189,outer cortex,F,x,y,https://purl.org/ccf/ASCTB-TEMP_abc,colonocyte,1,0.1,1\n",
        encoding="utf-8")
    d = hra_pop.load_hrapop_as(str(csv))
    assert "kidney" in d
    cortex = d["kidney"]["as"]["UBERON:0002189"]
    assert cortex["cts"]["CL:0000653"] == 9.0
    assert cortex["cts"]["ASCTB-TEMP_abc"] == 1.0   # ASCTB-TEMP kept, not dropped
    assert d["kidney"]["organ_total"] == 10.0


def test_manifest_attaches_subregions_and_is_backward_compatible():
    catalog = {"biomodel_dos": [{"biomodel_id": "BIOMD1", "name": "Kidney model"}],
               "organ_index": ORGAN_INDEX,
               "organ_to_models": {"UBERON:0004538": ["BIOMD1"]}}
    subs = place_models([_kidney_model()], HRAPOP_AS, CROSSWALK, ORGAN_INDEX)["subregions"]
    m = build_atlas_manifest(catalog, subregions=subs)
    kidney = next(o for o in m["organs"] if o["key"] == "kidney")
    assert kidney["subregions"][0]["label"] == "outer cortex of kidney"
    assert kidney["subregions"][0]["models"][0]["name"] == "Kidney model"  # name injected
    assert m["summary"]["n_subregions"] == 1 and m["summary"]["n_organs_with_subregions"] == 1
    # backward compatible: no subregions arg -> organs still build, empty lists
    m0 = build_atlas_manifest(catalog)
    assert all(o["subregions"] == [] for o in m0["organs"])


def test_glbs_field_carries_all_same_sex_assets():
    m = build_atlas_manifest({"biomodel_dos": [], "organ_index": ORGAN_INDEX, "organ_to_models": {}})
    kidney = next(o for o in m["organs"] if o["key"] == "kidney")
    assert kidney["glbs"]["female"] == ["x/3d-vh-f-kidney-l.glb", "x/3d-vh-f-kidney-r.glb"]


def test_end_to_end_build_from_committed_datasets(tmp_path):
    result = build_and_write_atlas(
        db_path=str(REPO / "datasets" / "model_hra_map.json"),
        catalog_path=str(CATALOG), out_dir=tmp_path)
    atlas = json.loads((tmp_path / "atlas.json").read_text())
    # post physionet-harvest with the word-boundary keyword-match fix (organ-tagged
    # BioModels + PhysioNet models, distinct across whole-organ + subregion placements)
    assert atlas["summary"]["n_models_distinct"] == 380
    assert atlas["summary"]["n_subregions"] >= 3
    kidney = next(o for o in atlas["organs"] if o["key"] == "kidney")
    assert len(kidney["glbs"]["female"]) == 4                      # both kidneys + pelvises
    assert any(s["label"] == "outer cortex of kidney" for s in kidney["subregions"])
    assert result["placement_stats"]["n_subregion_models"] >= 9


def test_atlas_browser_step_writes_pack_and_emits_summary(tmp_path):
    core = build_core()
    step = AtlasBrowserStep(config={"out_dir": str(tmp_path)}, core=core)
    out = step.update({})
    assert (tmp_path / "atlas.json").exists()
    # post physionet-harvest with the word-boundary keyword-match fix (organ-tagged
    # BioModels + PhysioNet models, distinct across whole-organ + subregion placements)
    assert out["summary"]["n_models_distinct"] == 380
    assert out["placement_stats"]["n_subregion_models"] >= 9
    assert out["out_dir"] == str(tmp_path)
