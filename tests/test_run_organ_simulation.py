import viva_human_atlas.organ_simulation as osim


def test_run_organ_simulation_assembles_ran_and_failed(monkeypatch):
    fake_models = [
        {"key": "B1", "name": "sbml one", "repository": "biomodels", "simulator": "copasi", "runnable": True, "ref": "BIOMD1"},
        {"key": "P1", "name": "cellml one", "repository": "physiome", "simulator": "opencor", "runnable": True, "ref": "https://x/e/1"},
        {"key": "P2", "name": "cellml bad", "repository": "physiome", "simulator": "opencor", "runnable": True, "ref": "https://x/e/2"},
    ]
    monkeypatch.setattr(osim, "select_organ_models", lambda organ, db_path=None: fake_models)
    # SBML: one ran
    monkeypatch.setattr(osim, "_run_sbml", lambda models, **k: {
        "B1": {"status": "ran", "raw": {"time": [0, 1], "columns": ["A"], "values": [[1.0], [2.0]]}, "error": None}})
    # CellML: P1 ran, P2 failed
    def fake_cellml(models, **k):
        return {"P1": {"status": "ran", "raw": {"time": [0, 1], "state": {"m/x": [1.0, 0.5]}}, "error": None},
                "P2": {"status": "failed", "raw": None, "error": "libOpenCOR could not load model"}}
    monkeypatch.setattr(osim, "_run_cellml", fake_cellml)

    res = osim.run_organ_simulation("kidney")
    assert res["summary"] == {"n_models": 3, "n_ran": 2, "n_failed": 1, "by_simulator": {"copasi": 1, "opencor": 2}}
    by_key = {m["key"]: m for m in res["models"]}
    assert by_key["B1"]["status"] == "ran" and by_key["B1"]["series"] == {"A": [1.0, 2.0]}
    assert by_key["P1"]["series"] == {"m/x": [1.0, 0.5]}
    assert by_key["P2"]["status"] == "failed" and "libOpenCOR" in by_key["P2"]["error"]
