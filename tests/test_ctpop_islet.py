"""CTpop -> Topp2000 beta-cell-mass parameterization (`fp-ctpop-parameterize-
islet` follow-up).

Offline (no network): `beta_fraction_to_beta_mass` is pure arithmetic;
`ISLET_COMPOSITION` is a static dict; `compare_islet_compositions` is
exercised with `run_topp_with_composition` monkeypatched so no BioModels
fetch / tellurium solve happens. The composite is built via `build_core()`
and run once with the same Step-level monkeypatch, so no network call
happens in this file at all.

`@pytest.mark.network`: `run_topp_with_composition` really fetches the Topp
SBML from BioModels and solves it via tellurium, for a healthy vs
beta-depleted islet.
"""
from __future__ import annotations

import pytest
import yaml
from pathlib import Path

from process_bigraph import Composite, gather_emitter_results

import viva_human_atlas.ctpop_islet as ctpop_islet
from viva_human_atlas.core import build_core

from _step_doc import step_doc, resolve_step_class, registered_step_addresses

REPO_ROOT = Path(__file__).resolve().parents[1]

CTPOP_ADDRESS = "local:viva_human_atlas.ctpop_islet.CtpopIsletParameterizationStep"
CTPOP_CONFIG = {"model_id": "BIOMD0000000341", "t_end": 4000.0, "n_points": 200}


def test_beta_fraction_to_beta_mass_scales_proportionally():
    b_ref = 300.0
    # Healthy reference fraction reproduces b_ref exactly.
    assert ctpop_islet.beta_fraction_to_beta_mass(0.54, b_ref) == b_ref
    # Beta-depleted islet (30% beta, the T2D-relevant loss) scales down
    # proportionally: 300 * 0.30 / 0.54.
    expected = b_ref * 0.30 / 0.54
    assert ctpop_islet.beta_fraction_to_beta_mass(0.30, b_ref) == pytest.approx(expected)


def test_islet_composition_sums_to_one_and_has_expected_cl_ids():
    comp = ctpop_islet.ISLET_COMPOSITION
    total = sum(entry["fraction"] for entry in comp.values())
    assert abs(total - 1.0) < 1e-6

    cl_ids = {entry["cl"] for entry in comp.values() if entry.get("cl")}
    assert cl_ids == {"CL:0000169", "CL:0000171", "CL:0000173"}

    # Each entry (including the one without a CL id) carries a citation.
    for entry in comp.values():
        assert entry.get("citation")


def test_compare_islet_compositions_returns_both_scenarios(monkeypatch):
    def fake_run(beta_fraction, *, model_id="BIOMD0000000341", t_end=4000.0, n_points=200, ref_fraction=0.54):
        return {
            "time": [0.0, t_end],
            "B": [37.0 * beta_fraction / ref_fraction, 100.0],
            "G": [250.0, 100.0 if beta_fraction > 0.4 else 600.0],
            "I": [2.8, 10.0],
            "beta_fraction": beta_fraction,
            "b_init": 37.0 * beta_fraction / ref_fraction,
            "b_ref": 37.0,
            "model_id": model_id,
        }

    monkeypatch.setattr(ctpop_islet, "run_topp_with_composition", fake_run)

    out = ctpop_islet.compare_islet_compositions()

    assert set(out["runs"]) == {"healthy", "beta_depleted"}
    assert out["scenarios"] == ["healthy", "beta_depleted"]
    assert out["runs"]["healthy"]["beta_fraction"] == 0.54
    assert out["runs"]["beta_depleted"]["beta_fraction"] == 0.30
    # The mocked scenario shows the intended qualitative shift: lower beta
    # fraction -> higher terminal glucose.
    assert out["runs"]["beta_depleted"]["G"][-1] > out["runs"]["healthy"]["G"][-1]
    assert out["islet_composition"] == ctpop_islet.ISLET_COMPOSITION
    assert out["reference_beta_fraction"] == 0.54


def test_ctpop_islet_composite_loads(monkeypatch):
    def fake_run(beta_fraction, *, model_id="BIOMD0000000341", t_end=4000.0, n_points=200, ref_fraction=0.54):
        return {
            "time": [0.0, t_end],
            "B": [37.0 * beta_fraction / ref_fraction, 100.0],
            "G": [250.0, 100.0 if beta_fraction > 0.4 else 600.0],
            "I": [2.8, 10.0],
            "beta_fraction": beta_fraction,
            "b_init": 37.0 * beta_fraction / ref_fraction,
            "b_ref": 37.0,
            "model_id": model_id,
        }

    monkeypatch.setattr(ctpop_islet, "run_topp_with_composition", fake_run)

    core = build_core()
    doc = step_doc(CTPOP_ADDRESS, CTPOP_CONFIG, core)
    composite = Composite(doc, core=core)
    composite.run(0.0)  # Steps run on init; this flushes the emitter.
    snap = (gather_emitter_results(composite).get(("emitter",)) or [{}])[-1]

    runs = snap.get("runs", {})
    assert set(runs) == {"healthy", "beta_depleted"}
    assert runs["beta_depleted"]["G"][-1] > runs["healthy"]["G"][-1]
    assert snap.get("reference_beta_fraction") == 0.54


def test_study_baseline_references_registered_step():
    """The study migrated from `baseline.composite` (a single-Step wrapper
    generator) to `baseline.step`. Assert its baseline references a real,
    registered Step at the expected address."""
    core = build_core()
    registered = registered_step_addresses(core)

    study_path = REPO_ROOT / "studies" / "ctpop-islet-parameterization" / "study.yaml"
    study = yaml.safe_load(study_path.read_text(encoding="utf-8"))
    baseline = study.get("baseline") or []
    assert baseline, "baseline must be non-empty"
    assert "composite" not in baseline[0], (
        "baseline still uses `composite`; expected migrated `step`"
    )
    address = baseline[0]["step"]
    assert address == CTPOP_ADDRESS, (
        f"baseline.step {address!r} != expected {CTPOP_ADDRESS!r}"
    )
    resolve_step_class(address)
    assert address in registered, (
        f"baseline.step {address!r} not registered in build_core()"
    )


@pytest.mark.network
def test_run_topp_with_composition_real_model():
    out = ctpop_islet.run_topp_with_composition(0.54, t_end=4000.0, n_points=100)
    assert out, "run_topp_with_composition returned {} (failure) on the real model"
    assert set(out) >= {"time", "B", "G", "I", "beta_fraction", "b_init", "b_ref", "model_id"}
    assert len(out["time"]) > 1
    assert out["G"][0] != out["G"][-1], "glucose did not change over the run -- horizon too short?"


@pytest.mark.network
def test_compare_islet_compositions_real_healthy_vs_depleted():
    out = ctpop_islet.compare_islet_compositions(t_end=4000.0, n_points=100)
    healthy = out["runs"]["healthy"]
    depleted = out["runs"]["beta_depleted"]
    assert healthy and depleted
    # The T2D-relevant beta-cell loss (30% vs 54% beta) drives glucose up.
    assert depleted["G"][-1] > healthy["G"][-1]
