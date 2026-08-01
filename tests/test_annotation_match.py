from pathlib import Path
from viva_human_atlas.annotation_match import (
    extract_anatomy_curies, map_curie_to_organ, annotate_model, build_annotation_catalog,
)

FIX = Path(__file__).resolve().parent / "fixtures" / "sbml"
PANCREAS = (FIX / "pancreas_uberon.xml").read_text(encoding="utf-8")
NO_ANAT = (FIX / "no_anatomy.xml").read_text(encoding="utf-8")

# organ_index like the corpus catalog's: key -> {uberon, sexes, asset_urls}
ORGAN_INDEX = {
    "pancreas": {"uberon": "UBERON:0001264", "sexes": ["Female"], "asset_urls": ["x"]},
    "heart": {"uberon": "UBERON:0000948", "sexes": ["Female"], "asset_urls": ["y"]},
}


def test_extract_finds_uberon_curie():
    curies = extract_anatomy_curies(PANCREAS)
    assert any(c["curie"] == "UBERON:0001264" for c in curies)
    c = next(c for c in curies if c["curie"] == "UBERON:0001264")
    assert c["qualifier"] == "BQB_IS_PART_OF"
    assert "compartment" in c["element"]


def test_extract_ignores_non_anatomy():
    assert extract_anatomy_curies(NO_ANAT) == []


def test_map_curie_uberon_direct():
    assert map_curie_to_organ("UBERON:0001264", ORGAN_INDEX) == "pancreas"
    assert map_curie_to_organ("UBERON:9999999", ORGAN_INDEX) is None


def test_annotate_model_pancreas():
    do = annotate_model("BIOMD0000000137", ORGAN_INDEX, sbml_text=PANCREAS)
    assert do["biomodel_id"] == "BIOMD0000000137"
    assert [o["organ"] for o in do["organs"]] == ["pancreas"]
    assert do["organs"][0]["uberon"] == "UBERON:0001264"
    assert do["organs"][0]["via"]["curie"] == "UBERON:0001264"
    assert do["provenance"]["annotation"] == "miriam-match@SBML"


def test_annotate_model_no_anatomy_is_empty():
    do = annotate_model("BIOMD0000000000", ORGAN_INDEX, sbml_text=NO_ANAT)
    assert do["organs"] == []


def test_build_annotation_catalog_shape_and_index():
    model_dos = [{"biomodel_id": "BIOMD0000000137", "name": "Pancreas model"},
                 {"biomodel_id": "BIOMD0000000000", "name": "Abstract model"}]
    fetch = {"BIOMD0000000137": PANCREAS, "BIOMD0000000000": NO_ANAT}.__getitem__
    cat = build_annotation_catalog(model_dos, ORGAN_INDEX, fetch=fetch)
    assert set(cat) == {"biomodel_dos", "organ_index", "organ_to_models"}
    assert cat["organ_to_models"]["UBERON:0001264"] == ["BIOMD0000000137"]
    assert len(cat["biomodel_dos"]) == 2


def test_map_curie_fma_normalized():
    # real organ_index entries store bare FMA ids like "fma24978" (no colon,
    # lowercase) rather than "FMA:24978" -- map_curie_to_organ must normalize
    # both sides so an SBML-extracted "FMA:24978" CURIE still matches.
    organ_index = {"knee": {"uberon": "fma24978", "sexes": ["Female"], "asset_urls": ["x"]}}
    assert map_curie_to_organ("FMA:24978", organ_index) == "knee"


PURL_UBERON = """<?xml version="1.0" encoding="UTF-8"?>
<sbml xmlns="http://www.sbml.org/sbml/level3/version1/core" level="3" version="1">
  <model id="m1" metaid="m1">
    <listOfCompartments>
      <compartment id="c" metaid="c" constant="true">
        <annotation>
          <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
                   xmlns:bqbiol="http://biomodels.net/biology-qualifiers/">
            <rdf:Description rdf:about="#c">
              <bqbiol:isPartOf>
                <rdf:Bag>
                  <rdf:li rdf:resource="http://purl.obolibrary.org/obo/UBERON_0001264"/>
                </rdf:Bag>
              </bqbiol:isPartOf>
            </rdf:Description>
          </rdf:RDF>
        </annotation>
      </compartment>
    </listOfCompartments>
  </model>
</sbml>
"""


def test_extract_handles_obo_purl():
    curies = extract_anatomy_curies(PURL_UBERON)
    assert any(c["curie"] == "UBERON:0001264" for c in curies)
