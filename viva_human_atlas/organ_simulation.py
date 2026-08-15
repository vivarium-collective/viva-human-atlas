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
