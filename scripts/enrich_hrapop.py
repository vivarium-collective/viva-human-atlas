#!/usr/bin/env python
"""Enrich the biomodel-HRA DB with HRApop cell-type populations (organ-level).

Post-hoc pass over `datasets/model_hra_map.json`: adds an `hra_pop` field to
each model whose organ(s) HRApop covers — the measured cell-type composition of
that organ (CL cell types + percentage/count) from HRApop. No re-run of the
extractor needed. See viva_human_atlas/hra_pop.py.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from viva_human_atlas.enrich_hrapop import enrich_hrapop_map


def enrich(db_path: str, hrapop_csv=None, top=None) -> tuple[int, int]:
    return enrich_hrapop_map(db_path, hrapop_csv, top)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Enrich the biomodel-HRA DB with HRApop cell populations.")
    ap.add_argument("--db", default=str(REPO / "datasets" / "model_hra_map.json"))
    ap.add_argument("--hrapop-csv", default=None)
    ap.add_argument("--top", type=int, default=None, help="cap cell types per organ (default: all)")
    a = ap.parse_args(argv)
    total, enriched = enrich(a.db, a.hrapop_csv, a.top)
    print(f"enriched {enriched}/{total} models with hra_pop")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
