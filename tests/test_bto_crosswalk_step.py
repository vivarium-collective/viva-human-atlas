from viva_human_atlas.core import build_core
from viva_human_atlas.bto_crosswalk import BtoCrosswalkStep

def test_bto_crosswalk_step_offline_loads_committed():
    # process_bigraph.Step requires a `core` (raises "must provide a core"
    # otherwise) -- same pattern as every other Step test in this repo
    # (e.g. tests/test_model_harvest_step.py, tests/test_gene_enrich_step.py).
    step = BtoCrosswalkStep({"out_path": "datasets/bto_uberon_crosswalk.json",
                              "live": False}, core=build_core())
    out = step.update({})
    assert out["out_path"] == "datasets/bto_uberon_crosswalk.json"
    assert out["n_terms"] > 0
    assert out["n_mapped"] >= 0
