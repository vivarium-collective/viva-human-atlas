import pytest

from viva_human_atlas import physiome
from viva_human_atlas.physiome_organ_map import (
    extract_cellml_curies, map_exposure_to_organs, category_organ_keys)
from viva_human_atlas.biomodel_do import build_organ_index

ORGAN_INDEX = build_organ_index()

CELLML_WITH_RDF = """<?xml version="1.0"?>
<model xmlns="http://www.cellml.org/cellml/1.0#" name="demo">
  <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
    <rdf:li rdf:resource="http://identifiers.org/fma/FMA:7088"/>
    <rdf:li rdf:resource="http://identifiers.org/chebi/CHEBI:29108"/>
  </rdf:RDF>
</model>"""

# A category listing page fragment: two exposures, one short /e/ id and one hash id.
CATEGORY_HTML = '''
<a href="https://models.physiomeproject.org/e/103/beeler_reuter_1977.cellml/view"
   class="url">Beeler, Reuter, 1977</a>
<a href="https://models.physiomeproject.org/exposure/d86b21/adrian_1970.cellml/view"
   class="url">A model of pacemaking in substantia nigra neurons</a>
'''


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


def test_scrape_and_resolve_from_category_html():
    class R:
        def __init__(self, t): self._t = t
        def raise_for_status(self): pass
        @property
        def text(self): return self._t
    # first call returns entries, subsequent (paginated) calls are empty -> stop
    calls = {"n": 0}
    def get(url, timeout=0):
        calls["n"] += 1
        return R(CATEGORY_HTML if calls["n"] == 1 else "")
    index = physiome.build_category_index(categories=["electrophysiology"], _get=get)
    assert set(index) == {"103", "d86b21"}
    assert index["103"]["categories"] == ["electrophysiology"]
    exps = physiome.resolve_exposures(_index=index)
    assert {e["slug"] for e in exps} == {"103", "d86b21"}
    assert exps[0]["identifier"].startswith("https://models.physiomeproject.org/")


def test_build_entry_shape_category_mapped():
    exp = {"slug": "d86b21", "identifier": "https://models.physiomeproject.org/exposure/d86b21",
           "name": "substantia nigra neurons", "categories": ["electrophysiology"]}
    e = physiome.build_entry(exp, ORGAN_INDEX, no_llm=True,
                             _doi=lambda ex, cache_dir=None: "10.1234/demo")
    assert e["repository"] == "physiome" and e["source_id"] == "d86b21"
    assert e["provenance"]["model_format"] == "CellML"
    assert e["provenance"]["mapping_method"] == "category"
    assert e["provenance"]["categories"] == ["electrophysiology"]
    assert {o["label"] for o in e["organs"]} == {"brain"}
    assert e["paper_doi"] == "10.1234/demo"
    assert e["paper_url"] == "https://doi.org/10.1234/demo"


@pytest.mark.network
def test_pmr_live_category_scrape_maps_bulk():
    exps = physiome.resolve_exposures()
    assert len(exps) >= 200
    mapped = [physiome.build_entry(e, ORGAN_INDEX, no_llm=True) for e in exps]
    assert sum(1 for m in mapped if m["organs"]) >= 150
