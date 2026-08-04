from viva_human_atlas.hra_mapping import map_to_hra
from viva_human_atlas.ftu_coverage import HRA_FTUS


def test_hra_ftus_have_uberon_ids():
    for f in HRA_FTUS:
        assert f.get("uberon", "").startswith("UBERON:"), f["ftu"]


ORGAN_INDEX = {
    "pancreas": {"uberon": "UBERON:0001264", "asset_urls": []},
    "liver": {"uberon": "UBERON:0002107", "asset_urls": []},
}


def test_map_to_hra_organ_ftu_celltype():
    out = map_to_hra(["UBERON:0001264", "UBERON:0000006"], "beta-cell insulin model", ORGAN_INDEX)
    assert {"label": "pancreas", "uberon": "UBERON:0001264"} in out["organs"]
    ftu_labels = {f["label"] for f in out["functional_tissue_units"]}
    assert any("islet" in l for l in ftu_labels)
    assert all(f["uberon"].startswith("UBERON:") for f in out["functional_tissue_units"])
    cl_ids = {c["cl"] for c in out["cell_types"]}
    assert "CL:0000169" in cl_ids  # beta cell, from the islet FTU
    assert "UBERON:0001264" in out["uberon_organ_ids"]
    assert "UBERON:0000006" in out["uberon_subregion_ids"]


def test_map_to_hra_id_lists_sorted_and_deduped():
    out = map_to_hra(
        ["UBERON:0002107", "UBERON:0001264", "UBERON:0001264", "UBERON:0000006", "UBERON:0000006"],
        "",
        ORGAN_INDEX,
    )
    assert out["uberon_organ_ids"] == ["UBERON:0001264", "UBERON:0002107"]
    assert out["uberon_subregion_ids"] == ["UBERON:0000006"]


def test_map_to_hra_empty_inputs():
    out = map_to_hra([], "", ORGAN_INDEX)
    assert out == {
        "organs": [],
        "functional_tissue_units": [],
        "cell_types": [],
        "uberon_organ_ids": [],
        "uberon_subregion_ids": [],
    }
