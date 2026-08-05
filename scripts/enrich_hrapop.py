#!/usr/bin/env python
"""Enrich the biomodel-HRA DB with HRApop cell-type populations (organ-level).

Post-hoc pass over `datasets/biomodel_hra_map.json`: adds an `hra_pop` field to
each model whose organ(s) HRApop covers — the measured cell-type composition of
that organ (CL cell types + percentage/count) from HRApop. No re-run of the
extractor needed. See viva_human_atlas/hra_pop.py.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from viva_human_atlas.hra_pop import load_hrapop, hrapop_for_organs


def enrich(db_path: str, hrapop_csv=None, top=None) -> tuple[int, int]:
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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Enrich the biomodel-HRA DB with HRApop cell populations.")
    ap.add_argument("--db", default=str(REPO / "datasets" / "biomodel_hra_map.json"))
    ap.add_argument("--hrapop-csv", default=None)
    ap.add_argument("--top", type=int, default=None, help="cap cell types per organ (default: all)")
    a = ap.parse_args(argv)
    total, enriched = enrich(a.db, a.hrapop_csv, a.top)
    print(f"enriched {enriched}/{total} models with hra_pop")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
