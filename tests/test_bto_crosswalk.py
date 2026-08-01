from viva_human_atlas.bto_crosswalk import (
    LABEL2ORGAN, organ_base_uberon, build_bto_uberon_crosswalk,
)

# organ_index like the corpus catalog's: key -> {uberon, sexes, asset_urls}
ORGAN_INDEX = {
    "liver": {"uberon": "UBERON:0002107", "sexes": ["Female", "Male"], "asset_urls": ["x"]},
    "ovary-female-left": {"uberon": "UBERON:0002119", "sexes": ["Female"], "asset_urls": ["y"]},
    "ovary-female-right": {"uberon": "UBERON:0002118", "sexes": ["Female"], "asset_urls": ["z"]},
}

BTO_TERMS = {
    "BTO:0000759": {"label": "liver", "count": 16},
    "BTO:0004383": {"label": "follicular fluid", "count": 66},
    "BTO:0000152": {"label": "infected cell", "count": 31},
}


def test_organ_base_uberon_strips_sex_and_side():
    base = organ_base_uberon(ORGAN_INDEX)
    assert base["liver"] == "UBERON:0002107"
    # first-wins: ovary-female-left comes before ovary-female-right
    assert base["ovary"] == "UBERON:0002119"
    # slug entries are present too
    assert base["ovary-female-left"] == "UBERON:0002119"


def test_build_crosswalk_maps_liver_and_follicular_fluid():
    crosswalk = build_bto_uberon_crosswalk(BTO_TERMS, ORGAN_INDEX)
    assert crosswalk["BTO:0000759"] == "UBERON:0002107"
    assert crosswalk["BTO:0004383"] == "UBERON:0002119"


def test_build_crosswalk_excludes_ambiguous_terms():
    crosswalk = build_bto_uberon_crosswalk(BTO_TERMS, ORGAN_INDEX)
    assert "BTO:0000152" not in crosswalk


def test_build_crosswalk_values_are_valid_uberon_curies_in_organ_index():
    crosswalk = build_bto_uberon_crosswalk(BTO_TERMS, ORGAN_INDEX)
    valid_uberons = {e["uberon"] for e in ORGAN_INDEX.values() if e.get("uberon")}
    for curie, uberon in crosswalk.items():
        assert uberon.startswith("UBERON:") or uberon.startswith("FMA:") or uberon.startswith("fma")
        assert uberon in valid_uberons
