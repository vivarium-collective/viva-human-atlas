from viva_human_atlas import anatomy_resolver as ar
from viva_human_atlas.biomodel_do import build_organ_index

ORGAN_INDEX = build_organ_index()
# organ-level reference UBERONs (from the index) for the exact-match tier:
KIDNEY_UB = ORGAN_INDEX["kidney"]["uberon"]      # UBERON:0004538
BRAIN_UB = ORGAN_INDEX["brain"]["uberon"]        # UBERON:0000955

ROLLUP = {                     # non-organ / synonym UBERON -> organ_index key(s)
    "UBERON:0000956": ["brain"],      # cerebral cortex
    "UBERON:0001285": ["kidney"],     # nephron
    "UBERON:0002113": ["kidney"],     # kidney (synonym id != reference id)
    "UBERON:0001155": ["intestine"],  # colon
}
CL_MAP = {"CL:0000499": ["kidney"]}   # stromal cell (kidney AS)
BTO_MAP = {"BTO:0000759": "UBERON:0002113"}   # -> rolls up to kidney
FMA_MAP = {"FMA:7203": "UBERON:0002113"}


def test_organ_level_uberon_exact():
    keys, method = ar.resolve_organ_keys(ORGAN_INDEX, uberon=[KIDNEY_UB], rollup={})
    assert keys == ["kidney"] and method == "annotation"


def test_uberon_rollup_nonorgan_and_synonym():
    keys, m = ar.resolve_organ_keys(ORGAN_INDEX, uberon=["UBERON:0000956"], rollup=ROLLUP)
    assert keys == ["brain"] and m == "annotation_rollup"
    # synonym id resolves to the same organ as the reference id
    keys2, _ = ar.resolve_organ_keys(ORGAN_INDEX, uberon=["UBERON:0002113"], rollup=ROLLUP)
    assert keys2 == ["kidney"]


def test_bto_and_fma_crosswalk_then_rollup():
    keys, m = ar.resolve_organ_keys(ORGAN_INDEX, bto=["BTO:0000759"], rollup=ROLLUP, bto_map=BTO_MAP)
    assert keys == ["kidney"] and m == "crosswalk"
    keys2, m2 = ar.resolve_organ_keys(ORGAN_INDEX, fma=["FMA:7203"], rollup=ROLLUP, fma_map=FMA_MAP)
    assert keys2 == ["kidney"] and m2 == "crosswalk"


def test_cl_celltype_maps_to_organ():
    keys, m = ar.resolve_organ_keys(ORGAN_INDEX, cl=["CL:0000499"], rollup={}, cl_map=CL_MAP)
    assert keys == ["kidney"] and m == "cell_type"


def test_precedence_annotation_beats_rollup_beats_crosswalk_beats_cl():
    # organ-level uberon wins over everything
    keys, m = ar.resolve_organ_keys(ORGAN_INDEX, uberon=[BRAIN_UB, "UBERON:0001285"],
                                    cl=["CL:0000499"], rollup=ROLLUP, cl_map=CL_MAP)
    assert m == "annotation" and "brain" in keys


def test_unmapped_returns_empty():
    keys, m = ar.resolve_organ_keys(ORGAN_INDEX, uberon=["UBERON:9999999"], rollup=ROLLUP)
    assert keys == [] and m == ""
