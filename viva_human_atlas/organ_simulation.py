"""Take an organ, pull its atlas-mapped models, route each to its compatible
simulator, run to a timeseries, normalize, and render an interactive dashboard.

SBML (BioModels) -> COPASI via viva_biomodels.run_comparison; CellML (Physiome)
-> OpenCOR via viva_opencor.OpenCORUTCStep. PhysioNet entries are dataset
references, not runnable ODE models, and are excluded. Non-runnable / failing
models are marked, never dropped silently.
"""
from __future__ import annotations

import json
from pathlib import Path

from process_bigraph import Step

from viva_human_atlas.physiome import resolve_cellml_url

_REPO = Path(__file__).resolve().parents[1]
_DEFAULT_DB = str(_REPO / "datasets" / "model_hra_map.json")
_SIM_BY_REPO = {"biomodels": "copasi", "physiome": "opencor", "physionet": None}


def select_organ_models(organ: str, db_path: str = _DEFAULT_DB) -> list:
    organ = organ.lower()
    db = json.loads(Path(db_path).read_text(encoding="utf-8"))
    out = []
    for e in db:
        if not any(organ in (o.get("label") or "").lower() for o in (e.get("organs") or [])):
            continue
        sim = _SIM_BY_REPO.get(e.get("repository"))
        if sim is None:
            continue  # physionet / unknown: not runnable, exclude
        ref = e.get("biomodel_id") if e.get("repository") == "biomodels" else e.get("identifier")
        out.append({
            "key": e.get("source_id") or e.get("biomodel_id") or e.get("identifier"),
            "name": e.get("name") or "",
            "repository": e.get("repository"),
            "simulator": sim,
            "runnable": True,
            "ref": ref,
        })
    return out


class OrganModelSelectStep(Step):
    """Step: select an organ's runnable models from the atlas DB and route each
    to its compatible simulator."""

    description = ("Select every model tagged to an organ from the BioModels/"
                   "Physiome->HRA map and route it to a simulator (SBML->COPASI, "
                   "CellML->OpenCOR); PhysioNet dataset entries are excluded.")

    config_schema = {"organ": "string", "db_path": "string"}

    def inputs(self):
        return {}

    def outputs(self):
        return {"manifest": "list[tree]", "n_models": "integer",
                "per_simulator": "tree", "summary": "tree"}

    def update(self, inputs):
        organ = self.config.get("organ") or "kidney"
        models = select_organ_models(organ, self.config.get("db_path") or _DEFAULT_DB)
        per_sim = {}
        for m in models:
            per_sim[m["simulator"]] = per_sim.get(m["simulator"], 0) + 1
        return {
            "manifest": models,
            "n_models": len(models),
            "per_simulator": per_sim,
            "summary": {"organ": organ, "n_models": len(models), "by_simulator": per_sim},
        }


OrganModelSelectStep.contract = {
    "summary": OrganModelSelectStep.description,
    "outputs": {
        "manifest": "Per-model {key,name,repository,simulator,runnable,ref}.",
        "n_models": "Runnable models tagged to the organ.",
        "per_simulator": "Count of models per simulator.",
        "summary": "organ + counts.",
    },
    "assumptions": ["PhysioNet entries are dataset references, not runnable ODE "
                    "models, so they are excluded from the manifest."],
}


def normalize_result(simulator: str, raw: dict) -> dict:
    """Collapse a simulator result into {"time": [...], "series": {name: [...]}}."""
    time = list(raw.get("time") or [])
    if simulator == "opencor":
        # State variables are the model's ODE dynamics — keep ONLY these. The
        # `variables` map is algebraic intermediates + parameters/constants;
        # many are constant (e.g. parameters/k0_65 == 4500) or numerically
        # divergent (King-Altman C_sum -> 1e43), and merged in they bury the
        # real state trajectories on a shared axis.
        series = {k: list(v) for k, v in (raw.get("state") or {}).items()}
        return {"time": time, "series": series}
    # SBML engines: {time, columns, values} (row-per-timepoint)
    cols = list(raw.get("columns") or [])
    vals = raw.get("values") or []
    series = {c: [row[j] for row in vals] for j, c in enumerate(cols)}
    return {"time": time, "series": series}


def _run_sbml(models, *, references=None):
    """{key: {status, raw(numeric_result)|None, error}} via viva_biomodels."""
    from viva_biomodels.composites.compare_simulators import run_comparison
    ids = [m["ref"] for m in models]
    rep = run_comparison(ids, simulators=["copasi"], references=references) if ids else {}
    out = {}
    for m in models:
        r = rep.get(m["ref"]) or {}
        raw = (r.get("engines") or {}).get("copasi") or {}
        if r.get("error") or not raw.get("time"):
            out[m["key"]] = {"status": "failed", "raw": None, "error": r.get("error") or "no timeseries produced"}
        else:
            out[m["key"]] = {"status": "ran", "raw": raw, "error": None}
    return out


def _run_cellml(models, *, end_time=10.0, number_of_steps=100):
    """{key: {status, raw(opencor result)|None, error}} via OpenCOR."""
    out = {}
    try:
        from process_bigraph import allocate_core
        from viva_opencor.processes import OpenCORUTCStep
    except Exception as exc:  # noqa: BLE001 — engine not installed
        return {m["key"]: {"status": "failed", "raw": None,
                           "error": f"OpenCOR unavailable: {exc}"} for m in models}
    core = allocate_core(); core.register_link("OpenCORUTCStep", OpenCORUTCStep)
    for m in models:
        try:
            url = resolve_cellml_url(m["ref"])
            if not url:
                out[m["key"]] = {"status": "failed", "raw": None, "error": "no .cellml resolved for exposure"}
                continue
            step = OpenCORUTCStep(config={"model_source": url, "end_time": end_time,
                                          "number_of_steps": number_of_steps}, core=core)
            out[m["key"]] = {"status": "ran", "raw": step.update({})["result"], "error": None}
        except Exception as exc:  # noqa: BLE001 — one model never sinks the batch
            out[m["key"]] = {"status": "failed", "raw": None, "error": str(exc)}
    return out


def run_organ_simulation(organ, *, end_time=10.0, number_of_steps=100, db_path=_DEFAULT_DB) -> dict:
    models = select_organ_models(organ, db_path)
    sbml = [m for m in models if m["simulator"] == "copasi"]
    cellml = [m for m in models if m["simulator"] == "opencor"]
    ran_sbml = _run_sbml(sbml)
    ran_cellml = _run_cellml(cellml, end_time=end_time, number_of_steps=number_of_steps)
    raw_by_key = {**ran_sbml, **ran_cellml}
    out_models, n_ran, n_failed, by_sim = [], 0, 0, {}
    for m in models:
        by_sim[m["simulator"]] = by_sim.get(m["simulator"], 0) + 1
        r = raw_by_key.get(m["key"]) or {"status": "failed", "raw": None, "error": "not run"}
        rec = {"key": m["key"], "name": m["name"], "simulator": m["simulator"],
               "status": r["status"], "error": r.get("error")}
        if r["status"] == "ran":
            norm = normalize_result(m["simulator"], r["raw"])
            rec["time"] = norm["time"]; rec["series"] = norm["series"]; n_ran += 1
        else:
            rec["time"] = []; rec["series"] = {}; n_failed += 1
        out_models.append(rec)
    return {"organ": organ, "models": out_models,
            "summary": {"n_models": len(models), "n_ran": n_ran,
                        "n_failed": n_failed, "by_simulator": by_sim}}


_DEFAULT_OUT = str(_REPO / "studies" / "kidney-model-simulation" / "viz")


class OrganSimulationStep(Step):
    """Step: run every runnable model for an organ in its compatible simulator
    and write an interactive dashboard + tidy results JSON."""

    description = ("Run all of an organ's atlas-mapped models (SBML->COPASI, "
                   "CellML->OpenCOR), collect timeseries, and write an "
                   "interactive dashboard. Live run: native simulators + "
                   "network fetches. Failing models are shown, not dropped.")

    config_schema = {"organ": "string", "end_time": "float",
                     "number_of_steps": "integer", "db_path": "string", "out_dir": "string"}

    def inputs(self):
        return {}

    def outputs(self):
        return {"summary": "tree", "dashboard_path": "string", "results_path": "string"}

    def update(self, inputs):
        from viva_human_atlas.viz import organ_dashboard_html
        organ = self.config.get("organ") or "kidney"
        result = run_organ_simulation(
            organ,
            end_time=float(self.config.get("end_time") or 10.0),
            number_of_steps=int(self.config.get("number_of_steps") or 100),
            db_path=self.config.get("db_path") or _DEFAULT_DB,
        )
        out_dir = Path(self.config.get("out_dir") or _DEFAULT_OUT)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        (out_dir / "index.html").write_text(organ_dashboard_html(result), encoding="utf-8")
        return {"summary": result["summary"],
                "dashboard_path": str(out_dir / "index.html"),
                "results_path": str(out_dir / "results.json")}


OrganSimulationStep.contract = {
    "summary": OrganSimulationStep.description,
    "outputs": {"summary": "n_models/n_ran/n_failed/by_simulator.",
                "dashboard_path": "Path to the written interactive dashboard HTML.",
                "results_path": "Path to the tidy results JSON."},
    "assumptions": ["A live run study: COPASI + libOpenCOR native engines and "
                    "PMR/BioModels network fetches. Re-runs may differ with "
                    "upstream changes; failing models are marked, not dropped."],
}
