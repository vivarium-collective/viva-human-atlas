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

from viva_human_atlas.hra_pop import load_hrapop, hrapop_for_organs


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
