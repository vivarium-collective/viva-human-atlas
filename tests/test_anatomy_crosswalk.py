from viva_human_atlas.anatomy_crosswalk import (
    crosswalk_anatomy,
    crosswalk_mesh_labels,
    load_bto_uberon,
    load_mesh_label_crosswalk,
    norm_label,
)


def test_load_bto_uberon_missing_file_returns_empty(tmp_path):
    assert load_bto_uberon(tmp_path / "nope.json") == {}


def test_load_mesh_label_crosswalk_missing_file_returns_empty(tmp_path):
    assert load_mesh_label_crosswalk(tmp_path / "nope.csv") == {}


def test_load_bto_uberon_loads_real_dataset():
    m = load_bto_uberon()
    assert m  # non-empty, real curated file
    assert all(k.startswith("BTO:") for k in m)
    assert all(v.startswith("UBERON:") for v in m.values())


def test_load_mesh_label_crosswalk_loads_real_dataset():
    m = load_mesh_label_crosswalk()
    assert m  # non-empty, real SSSOM CSV
    assert m[norm_label("Liver")]["uberon"] == ["UBERON:0002107"]


def test_crosswalk_anatomy_bto_id_maps_to_uberon():
    ontology_ids = {"bto": ["BTO:0000759"]}
    derived = crosswalk_anatomy(ontology_ids, bto_map={"BTO:0000759": "UBERON:0002107"})
    assert derived["uberon"] == ["UBERON:0002107"]
    assert derived["cl"] == []


def test_crosswalk_anatomy_unmapped_bto_id_yields_empty():
    ontology_ids = {"bto": ["BTO:9999999"]}
    derived = crosswalk_anatomy(ontology_ids, bto_map={"BTO:0000759": "UBERON:0002107"})
    assert derived == {"uberon": [], "cl": []}


def test_crosswalk_anatomy_no_bto_ids_yields_empty():
    derived = crosswalk_anatomy({"bto": []}, bto_map={"BTO:0000759": "UBERON:0002107"})
    assert derived == {"uberon": [], "cl": []}


def test_crosswalk_anatomy_normalizes_bto_id_and_map_key():
    # map key has no colon/leading zeros-preserved, lowercase; input is the
    # canonical CURIE -- normalization (strip non-alphanumerics + uppercase)
    # must make them compare equal.
    ontology_ids = {"bto": ["BTO:0000759"]}
    derived = crosswalk_anatomy(ontology_ids, bto_map={"bto0000759": "UBERON:0002107"})
    assert derived["uberon"] == ["UBERON:0002107"]


def test_crosswalk_mesh_labels_maps_to_uberon_and_cl():
    label_map = {norm_label("Liver"): {"uberon": ["UBERON:0002107"], "cl": ["CL:0000182"]}}
    mesh_terms = [{"id": "D008099", "label": "Liver"}]
    derived = crosswalk_mesh_labels(mesh_terms, label_map)
    assert derived == {"uberon": ["UBERON:0002107"], "cl": ["CL:0000182"]}


def test_crosswalk_mesh_labels_unmapped_label_yields_empty():
    label_map = {norm_label("Liver"): {"uberon": ["UBERON:0002107"], "cl": []}}
    mesh_terms = [{"id": "D999999", "label": "Something Unmapped"}]
    assert crosswalk_mesh_labels(mesh_terms, label_map) == {"uberon": [], "cl": []}


def test_crosswalk_mesh_labels_no_terms_yields_empty():
    assert crosswalk_mesh_labels([], {}) == {"uberon": [], "cl": []}
