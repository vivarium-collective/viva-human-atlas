from viva_human_atlas.organ_simulation import select_organ_models, OrganModelSelectStep
from viva_human_atlas.core import build_core

def test_select_kidney_models_split_by_simulator():
    models = select_organ_models("kidney")
    sims = {}
    for m in models:
        sims[m["simulator"]] = sims.get(m["simulator"], 0) + 1
    assert sims.get("copasi", 0) == 60         # 60 SBML biomodels (ontology-resolver remap)
    assert sims.get("opencor", 0) == 22         # 22 Physiome CellML (ontology-resolver remap)
    assert all(m["runnable"] for m in models)   # physionet excluded from the list
    assert {m["ref"] for m in models if m["simulator"] == "copasi"} >= {"BIOMD0000000259"}

def test_select_step_registered_and_runs():
    core = build_core()
    assert core.link_registry.get("viva_human_atlas.organ_simulation.OrganModelSelectStep") is OrganModelSelectStep
    out = OrganModelSelectStep({"organ": "kidney"}, core=core).update({})
    # counts reflect the ontology-resolver remap (Task 5): kidney copasi 5->60, opencor 21->22
    assert out["n_models"] == 82
    assert out["per_simulator"]["copasi"] == 60 and out["per_simulator"]["opencor"] == 22
