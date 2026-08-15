import json
import viva_human_atlas.organ_simulation as osim
from viva_human_atlas.organ_simulation import OrganSimulationStep
from viva_human_atlas.core import build_core

_FAKE = {"organ": "kidney",
    "models": [{"key": "B1", "name": "m", "simulator": "copasi", "status": "ran",
                "time": [0, 1], "series": {"A": [1, 2]}, "error": None}],
    "summary": {"n_models": 1, "n_ran": 1, "n_failed": 0, "by_simulator": {"copasi": 1}}}

def test_step_registered():
    core = build_core()
    assert core.link_registry.get("viva_human_atlas.organ_simulation.OrganSimulationStep") is OrganSimulationStep

def test_step_writes_dashboard_and_results(monkeypatch, tmp_path):
    monkeypatch.setattr(osim, "run_organ_simulation", lambda organ, **k: _FAKE)
    step = OrganSimulationStep({"organ": "kidney", "out_dir": str(tmp_path)}, core=build_core())
    out = step.update({})
    assert out["summary"]["n_ran"] == 1
    assert (tmp_path / "index.html").exists() and (tmp_path / "results.json").exists()
    # encoding="utf-8" pinned explicitly: importing viva_human_atlas (COPASI
    # bindings) flips the process's ambient locale encoding to ASCII in some
    # environments, which breaks the default `Path.read_text()` on the
    # UTF-8 dashboard HTML. Same class of issue documented/worked around in
    # tests/test_atlas_viewer_assets.py and tests/test_model_harvest_study.py.
    assert json.loads((tmp_path / "results.json").read_text(encoding="utf-8"))["summary"]["n_ran"] == 1
    assert "<html" in (tmp_path / "index.html").read_text(encoding="utf-8").lower()
