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


def test_reason_from_issues_classifies_opencor_failures():
    from viva_human_atlas.organ_simulation import _reason_from_issues
    assert "not a runnable CellML" in _reason_from_issues(
        ["The file is not a CellML file, a SED-ML file, or a COMBINE archive."])
    r = _reason_from_issues([
        "Analyser: the type of variable 'K_int' in component 'NaK' is unknown.",
        "Analyser: the type of variable 'Na_ext' in component 'NaK' is unknown."])
    assert "component/flux model" in r and "2 input variable" in r
    assert "MathML" in _reason_from_issues(
        ["w3C MathML DTD error: Syntax of value for attribute id of math is not valid."])
    assert "unit inconsistency" in _reason_from_issues(
        ["Analyser: the units in 'Ha = H*exp(...)' in component 'x' are not equivalent."])
    assert _reason_from_issues([]) == ""


def test_is_component_fragment_text():
    from viva_human_atlas.organ_simulation import _is_component_fragment_text
    # interface="in" inputs + NO <diff> → a component fragment
    assert _is_component_fragment_text(
        '<variable name="K_int" public_interface="in" units="mM"/>'
        '<variable name="J" public_interface="out"/>') is True
    # has an ODE (<diff>) → a real standalone model, not a fragment
    assert _is_component_fragment_text(
        '<variable name="V" public_interface="in"/><math><apply><diff/></apply></math>') is False
    # no interface-in inputs at all → not a fragment
    assert _is_component_fragment_text('<variable name="V" initial_value="0"/>') is False
    assert _is_component_fragment_text("") is False


def test_classify_cellml_failure_never_crashes():
    # A bogus source must not raise — it returns some string reason (the full
    # fragment-sharpening integration is covered by the live regeneration).
    from viva_human_atlas.organ_simulation import _classify_cellml_failure
    assert isinstance(_classify_cellml_failure("nonexistent://model"), str)
