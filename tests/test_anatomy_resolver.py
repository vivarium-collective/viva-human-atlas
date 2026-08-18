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


PROMISCUOUS_CL_MAP = {
    "CL:0000499": ["kidney"],   # stromal cell (specific: 1 organ)
    "CL:0000084": ["kidney", "lung"],   # a moderately specific example (2 organs, still allowed)
    "CL:0000542": ["kidney", "lung", "heart", "brain"],   # e.g. "T cell" (>=4 organs: promiscuous)
}

def test_cl_promiscuous_does_not_place():
    keys, m = ar.resolve_organ_keys(ORGAN_INDEX, cl=["CL:0000542"], rollup={}, cl_map=PROMISCUOUS_CL_MAP)
    assert keys == [] and m == ""

def test_cl_specific_still_places():
    keys, m = ar.resolve_organ_keys(ORGAN_INDEX, cl=["CL:0000499"], rollup={}, cl_map=PROMISCUOUS_CL_MAP)
    assert keys == ["kidney"] and m == "cell_type"
    keys2, m2 = ar.resolve_organ_keys(ORGAN_INDEX, cl=["CL:0000084"], rollup={}, cl_map=PROMISCUOUS_CL_MAP)
    assert set(keys2) == {"kidney", "lung"} and m2 == "cell_type"

def test_cl_mix_promiscuous_and_specific_keeps_only_specific():
    keys, m = ar.resolve_organ_keys(ORGAN_INDEX, cl=["CL:0000542", "CL:0000499"],
                                    rollup={}, cl_map=PROMISCUOUS_CL_MAP)
    assert keys == ["kidney"] and m == "cell_type"


def test_precedence_annotation_beats_rollup_beats_crosswalk_beats_cl():
    # organ-level uberon wins over everything
    keys, m = ar.resolve_organ_keys(ORGAN_INDEX, uberon=[BRAIN_UB, "UBERON:0001285"],
                                    cl=["CL:0000499"], rollup=ROLLUP, cl_map=CL_MAP)
    assert m == "annotation" and "brain" in keys


def test_unmapped_returns_empty():
    keys, m = ar.resolve_organ_keys(ORGAN_INDEX, uberon=["UBERON:9999999"], rollup=ROLLUP)
    assert keys == [] and m == ""


GENE_MAP = {
    "FOXD1": {"kidney": 2}, "PECAM1": {"kidney": 1, "heart": 1, "lung": 1, "blood": 1},
    "NPHS1": {"kidney": 3},
}

def test_gene_specific_places():
    keys, m = ar.resolve_organ_keys(ORGAN_INDEX, gene_symbols=["foxd1", "nphs1-a"],
                                    rollup={}, gene_map=GENE_MAP)
    assert keys == ["kidney"] and m == "gene_asctb"

def test_gene_panorgan_does_not_place():
    keys, m = ar.resolve_organ_keys(ORGAN_INDEX, gene_symbols=["PECAM1"],
                                    rollup={}, gene_map=GENE_MAP)
    assert keys == [] and m == ""

def test_annotation_beats_gene():
    keys, m = ar.resolve_organ_keys(ORGAN_INDEX, uberon=[BRAIN_UB], gene_symbols=["NPHS1"],
                                    rollup={}, gene_map=GENE_MAP)
    assert m == "annotation" and keys == ["brain"]

def test_normalize_gene():
    assert ar.normalize_gene("cdk1-a") == "CDK1" and ar.normalize_gene("FoxD1") == "FOXD1"
