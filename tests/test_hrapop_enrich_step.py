from viva_human_atlas.enrich_hrapop import HRApopEnrichStep
from viva_human_atlas.core import build_core


def test_hrapop_enrich_step_offline_counts_committed_db():
    step = HRApopEnrichStep({"db_path": "datasets/model_hra_map.json", "live": False}, core=build_core())
    out = step.update({})
    assert out["db_path"] == "datasets/model_hra_map.json"
    assert out["n_models_linked"] >= 0
    assert "summary" in out
