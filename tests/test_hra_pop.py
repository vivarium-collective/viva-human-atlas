from viva_human_atlas.hra_pop import load_hrapop, hrapop_for_organs


def _csv(tmp_path):
    p = tmp_path / "hrapop.csv"
    p.write_text(
        "organ,as,as_label,sex,tool,modality,cell_id,cell_label,cell_count,cell_percentage,dataset_count\n"
        "pancreas,http://purl.obolibrary.org/obo/UBERON_0000006,islet,Male,azimuth,sc,http://purl.obolibrary.org/obo/CL_0000169,beta cell,100,0.5,3\n"
        "pancreas,http://purl.obolibrary.org/obo/UBERON_0001264,pancreas,Female,azimuth,sc,http://purl.obolibrary.org/obo/CL_0000169,beta cell,80,0.6,2\n"
        "pancreas,http://purl.obolibrary.org/obo/UBERON_0000006,islet,Male,azimuth,sc,http://purl.obolibrary.org/obo/CL_0000171,alpha cell,40,0.2,3\n"
        "large intestine,http://purl.obolibrary.org/obo/UBERON_0000059,colon,Male,azimuth,sc,http://purl.obolibrary.org/obo/CL_0000160,goblet cell,10,0.1,1\n",
        encoding="utf-8",
    )
    return str(p)


def test_load_aggregates_organ_cell_populations(tmp_path):
    hp = load_hrapop(_csv(tmp_path))
    assert set(hp) == {"pancreas", "large intestine"}
    beta = next(c for c in hp["pancreas"]["cell_types"] if c["cl"] == "CL:0000169")
    # count-based organ composition: beta 180 / (beta 180 + alpha 40) = 0.8182
    assert beta["percentage"] == round(180 / 220, 4)
    assert beta["cell_count"] == 180   # summed
    assert beta["n_as"] == 2           # islet + pancreas
    # composition sums to ~1 across the organ's cell types
    assert round(sum(c["percentage"] for c in hp["pancreas"]["cell_types"]), 2) == 1.0
    # ranked by percentage desc: beta before alpha
    assert hp["pancreas"]["cell_types"][0]["cl"] == "CL:0000169"


def test_join_matches_organs_incl_label_normalization(tmp_path):
    hp = load_hrapop(_csv(tmp_path))
    out = hrapop_for_organs(["pancreas", "intestine"], hp)  # 'intestine' -> 'large intestine'
    assert {o["organ"] for o in out} == {"pancreas", "large intestine"}
    panc = next(o for o in out if o["organ"] == "pancreas")
    assert panc["cell_types"][0]["cl"] == "CL:0000169"


def test_join_no_match_and_empty(tmp_path):
    hp = load_hrapop(_csv(tmp_path))
    assert hrapop_for_organs(["blood"], hp) == []   # HRApop doesn't cover blood
    assert hrapop_for_organs([], hp) == []
