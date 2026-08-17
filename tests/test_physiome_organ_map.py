from viva_human_atlas.physiome_organ_map import (
    extract_cellml_curies, map_exposure_to_organs, category_organ_keys, keyword_organ_keys)
from viva_human_atlas.biomodel_do import build_organ_index

ORGAN_INDEX = build_organ_index()

CELLML_WITH_RDF = """<?xml version="1.0"?>
<model xmlns="http://www.cellml.org/cellml/1.0#" name="demo">
  <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
    <rdf:li rdf:resource="http://identifiers.org/fma/FMA:7088"/>
    <rdf:li rdf:resource="http://identifiers.org/chebi/CHEBI:29108"/>
  </rdf:RDF>
</model>"""


def test_extract_cellml_curies_anatomy_and_molecular():
    c = extract_cellml_curies(CELLML_WITH_RDF)
    assert c["fma"] == ["FMA:7088"] and c["chebi"] == ["CHEBI:29108"]


def test_category_organ_keys_and_ep_title_refinement():
    assert category_organ_keys(["hepatology"], "") == ["liver"]
    assert category_organ_keys(["cardiovascular_circulation"], "") == ["heart", "blood"]
    # Electrophysiology defaults to heart, but a neuron title refines to brain,
    # and a smooth-muscle/gut title to intestine.
    assert category_organ_keys(["electrophysiology"], "Beeler Reuter cardiac") == ["heart"]
    assert category_organ_keys(["electrophysiology"], "substantia nigra neurons") == ["brain"]
    assert category_organ_keys(["electrophysiology"], "jejunal smooth muscle") == ["intestine"]
    # organ-agnostic category contributes nothing
    assert category_organ_keys(["cell_cycle"], "") == []
    # the two removed-as-too-coarse categories no longer map on the shelf alone
    assert category_organ_keys(["metabolism"], "") == []
    assert category_organ_keys(["endocrine"], "") == []


def test_map_exposure_category_first():
    hra = map_exposure_to_organs({"name": "X", "categories": ["ion_transport"]}, ORGAN_INDEX)
    assert hra["mapping_method"] == "category" and hra["confidence"] == "medium"
    assert [o["label"] for o in hra["organs"]] == ["kidney"]


def test_metabolism_falls_through_to_title_keyword():
    # "metabolism" no longer blanket-maps, but a title naming the organ still does
    # (via the keyword path) -- per-model evidence, not the shelf.
    on_shelf = map_exposure_to_organs({"name": "generic ATP model", "categories": ["metabolism"]},
                                      ORGAN_INDEX)
    assert on_shelf["mapping_method"] == "unmapped"
    named = map_exposure_to_organs({"name": "hepatic bile acid model", "categories": ["metabolism"]},
                                   ORGAN_INDEX)
    assert named["mapping_method"] == "keyword"
    assert [o["label"] for o in named["organs"]] == ["liver"]


def test_map_exposure_ep_neuron_goes_to_brain_not_heart():
    hra = map_exposure_to_organs(
        {"name": "pacemaking in substantia nigra neurons", "categories": ["electrophysiology"]},
        ORGAN_INDEX)
    labels = {o["label"] for o in hra["organs"]}
    assert "brain" in labels and "heart" not in labels


def test_map_exposure_annotation_beats_category():
    # neurobiology would map to brain, but a real FMA:7088 annotation wins -> heart
    hra = map_exposure_to_organs(
        {"name": "x", "categories": ["neurobiology"]}, ORGAN_INDEX, cellml_text=CELLML_WITH_RDF)
    assert hra["mapping_method"] == "annotation" and hra["confidence"] == "high"
    assert {o["label"] for o in hra["organs"]} == {"heart"}  # FMA:7088


def test_map_exposure_unmapped_agnostic_category():
    hra = map_exposure_to_organs({"name": "an oscillator", "categories": ["cell_cycle"]}, ORGAN_INDEX)
    assert hra["mapping_method"] == "unmapped" and hra["organs"] == []


def test_keyword_organ_keys_exact_and_pattern():
    assert "heart" in keyword_organ_keys(["atrial myocyte"])
    assert "brain" in keyword_organ_keys(["substantia nigra"])
    assert "pancreas" in keyword_organ_keys(["beta cell"])
    assert "kidney" in keyword_organ_keys(["collecting duct"])
    assert keyword_organ_keys(["cardiac action potential"]) == ["heart"]   # pattern cardiac.*
    assert keyword_organ_keys(["systems biology"]) == []                    # no anatomy signal


def test_map_exposure_keyword_path_beats_category():
    # keywords give brain; category electrophysiology would give heart -> keyword wins
    exp = {"name": "x", "keywords": ["hippocampal neuron"], "categories": ["electrophysiology"]}
    hra = map_exposure_to_organs(exp, ORGAN_INDEX)
    assert hra["mapping_method"] == "keyword_annotation" and hra["confidence"] == "medium"
    assert {o["label"] for o in hra["organs"]} == {"brain"}


def test_map_exposure_keyword_yields_celltypes_via_ftu():
    # beta cell -> pancreas -> pancreatic islet FTU -> beta cell CL flows through map_to_hra
    exp = {"name": "insulin secretion model", "keywords": ["beta cell"], "categories": []}
    hra = map_exposure_to_organs(exp, ORGAN_INDEX)
    assert {o["label"] for o in hra["organs"]} == {"pancreas"}
    assert any("beta" in (ct["label"] or "").lower() for ct in hra["cell_types"])


def test_map_exposure_keyword_absent_falls_to_category():
    exp = {"name": "x", "keywords": ["oscillation"], "categories": ["ion_transport"]}
    hra = map_exposure_to_organs(exp, ORGAN_INDEX)
    assert hra["mapping_method"] == "category"
    assert {o["label"] for o in hra["organs"]} == {"kidney"}
