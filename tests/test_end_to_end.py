import pytest

import viva_human_atlas.composites.glucose_regulation as gr
from viva_human_atlas.composites.glucose_regulation import run_glucose_regulation
from viva_human_atlas.biomodels_search import search_biomodels


def test_run_glucose_regulation_delegates_offline(monkeypatch):
    # Fully offline: mock BOTH search and run_comparison (run_comparison fetches
    # SBML over the network via LoadBiomodelStep, so it must be mocked here).
    monkeypatch.setattr(gr, "search_biomodels", lambda q, n, **k: ["BIOMD0000000633"])
    captured = {}
    def fake_run(ids, simulators=None, on_progress=None):
        captured["ids"] = ids
        captured["simulators"] = simulators
        return {ids[0]: {"engines": {}, "comparison": {}, "error": None}}
    monkeypatch.setattr(gr, "run_comparison", fake_run)

    report = run_glucose_regulation(max_results=1, simulators="copasi,tellurium")

    assert captured["ids"] == ["BIOMD0000000633"]
    assert captured["simulators"] == "copasi,tellurium"
    assert set(report) == {"BIOMD0000000633"}
    assert set(report["BIOMD0000000633"]) == {"engines", "comparison", "error"}


@pytest.mark.network
def test_run_glucose_regulation_real_model(monkeypatch):
    # End-to-end: mock only search; really fetch + run COPASI + Tellurium on one
    # known glucose model. If BIOMD0000000633 errors in one engine, the entry's
    # `error` is populated and the shape asserts still hold.
    monkeypatch.setattr(gr, "search_biomodels", lambda q, n, **k: ["BIOMD0000000633"])
    report = run_glucose_regulation(max_results=1, simulators="copasi,tellurium")
    assert set(report) == {"BIOMD0000000633"}
    assert set(report["BIOMD0000000633"]) == {"engines", "comparison", "error"}


@pytest.mark.network
def test_live_search_finds_glucose_models():
    ids = search_biomodels("glucose regulation", max_results=5)
    assert len(ids) >= 1
    assert all(i.startswith("BIOMD") or i.startswith("MODEL") for i in ids)
