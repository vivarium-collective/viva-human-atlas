"""ModelHarvestStep: the viva reproducibility hook over `harvest`/`load_map`.

Offline (no network): the Step is built via `build_core()` (Step requires a
`core`, same pattern as `BiomodelHraMapStep`'s tests) and run against a tmp DB
with `build_if_missing=False`, so no harvest runs -- just load + count.
"""
import json

from viva_human_atlas.core import build_core
from viva_human_atlas.model_harvest import ModelHarvestStep


def test_step_loads_committed_db_network_free(tmp_path):
    out = tmp_path / "model_hra_map.json"
    out.write_text(json.dumps([
        {"identifier": "iri://A", "repository": "biomodels", "source_id": "A",
         "organs": [], "provenance": {"errors": []}},
        {"identifier": "https://physionet.org/content/mitdb/", "repository": "physionet",
         "source_id": "mitdb", "organs": [{"uberon": "UBERON:0000948"}], "provenance": {"errors": []}},
    ]))
    core = build_core()
    step = ModelHarvestStep(config={"db_path": str(out), "build_if_missing": False}, core=core)
    res = step.update({})
    assert res["n_models"] == 2
    assert res["per_source"] == {"biomodels": 1, "physionet": 1}
