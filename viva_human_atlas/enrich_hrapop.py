"""HRApop cell-population enrichment of the BioModels->HRA DB (Stage C).

Adds an `hra_pop` field to each model whose organ(s) HRApop covers — the
measured cell-type composition of that organ from HRApop. Importable core so
the CLI (scripts/enrich_hrapop.py) and the HRApopEnrichStep share one path and
cannot diverge (same pattern as biomodel_hra / scripts/build_biomodel_hra_map).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from process_bigraph import Step

from viva_human_atlas.hra_pop import load_hrapop, hrapop_for_organs
from viva_human_atlas.biomodel_hra import load_map, summarize_map


def enrich_hrapop_map(db_path: str, hrapop_csv: str | None = None,
                      top: int | None = None) -> tuple[int, int]:
    entries = json.loads(Path(db_path).read_text(encoding="utf-8"))
    hrapop = load_hrapop(hrapop_csv)
    n = 0
    for e in entries:
        organs = [o["label"] for o in e.get("organs", []) if o.get("label")]
        hp = hrapop_for_organs(organs, hrapop, top=top)
        if hp:
            e["hra_pop"] = hp
            n += 1
        elif "hra_pop" in e:
            del e["hra_pop"]
    tmp = Path(db_path).with_suffix(".json.tmp")
    tmp.write_text(json.dumps(entries, indent=2), encoding="utf-8")
    os.replace(tmp, db_path)
    return len(entries), n


_REPO = Path(__file__).resolve().parents[1]
_DEFAULT_DB = str(_REPO / "datasets" / "model_hra_map.json")
_DEFAULT_HRAPOP = str(_REPO / "datasets" / "hrapop_as_cell_populations.csv")


class HRApopEnrichStep(Step):
    """Step: link each model to its organ's HRApop cell-type population (Stage C).
    live=false counts the committed DB's existing hra_pop links; live=true re-runs
    enrich_hrapop_map and rewrites the DB."""

    description = (
        "Attach HRApop measured cell-type populations to each model whose "
        "organ(s) HRApop covers. Emits how many models were linked."
    )

    config_schema = {"db_path": "string", "hrapop_csv": "string", "live": "boolean"}

    def inputs(self):
        return {"db_path": "string"}

    def outputs(self):
        return {"db_path": "string", "n_models_linked": "integer", "summary": "tree"}

    def update(self, inputs):
        db_path = inputs.get("db_path") or self.config.get("db_path") or _DEFAULT_DB
        hrapop_csv = self.config.get("hrapop_csv") or None
        if self.config.get("live"):
            _total, n_linked = enrich_hrapop_map(db_path, hrapop_csv)
        else:
            n_linked = sum(1 for e in load_map(db_path) if e.get("hra_pop"))
        entries = load_map(db_path)
        return {
            "db_path": str(db_path),
            "n_models_linked": n_linked,
            "summary": summarize_map(entries),
        }


HRApopEnrichStep.contract = {
    "summary": HRApopEnrichStep.description,
    "outputs": {
        "db_path": "Passthrough path to the (rewritten if live) DB.",
        "n_models_linked": "Models linked to an HRApop cell-type population.",
        "summary": "summarize_map coverage summary of the DB.",
    },
    "assumptions": [
        "live=false counts the committed DB's existing hra_pop links (offline, "
        "reproducible). live=true re-runs the HRApop join and rewrites the DB.",
    ],
}
