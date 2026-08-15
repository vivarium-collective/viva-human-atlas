from viva_human_atlas.organ_simulation import select_organ_models, OrganModelSelectStep
from viva_human_atlas.core import build_core

def test_select_kidney_models_split_by_simulator():
    models = select_organ_models("kidney")
    sims = {}
    for m in models:
        sims[m["simulator"]] = sims.get(m["simulator"], 0) + 1
    assert sims.get("copasi", 0) == 5          # 5 SBML biomodels
    assert sims.get("opencor", 0) == 19         # 19 Physiome CellML
    assert all(m["runnable"] for m in models)   # physionet excluded from the list
    assert {m["ref"] for m in models if m["simulator"] == "copasi"} >= {"BIOMD0000000259"}

def test_select_step_registered_and_runs():
    core = build_core()
    assert core.link_registry.get("viva_human_atlas.organ_simulation.OrganModelSelectStep") is OrganModelSelectStep
    out = OrganModelSelectStep({"organ": "kidney"}, core=core).update({})
    assert out["n_models"] == 24
    assert out["per_simulator"]["copasi"] == 5 and out["per_simulator"]["opencor"] == 19
