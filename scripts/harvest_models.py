#!/usr/bin/env python
"""Reproducible multi-source harvest into datasets/model_hra_map.json.

  python scripts/harvest_models.py                    # harvest new from every source
  python scripts/harvest_models.py --source physionet  # one source
  python scripts/harvest_models.py --force            # re-fetch all
  python scripts/harvest_models.py --no-llm --limit 50 # cheap/offline dev run
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from viva_human_atlas.model_harvest import DEFAULT_DB_PATH, SOURCES, harvest  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Harvest all model sources into the unified HRA model DB.")
    ap.add_argument("--out", default=str(DEFAULT_DB_PATH))
    ap.add_argument("--source", action="append", choices=list(SOURCES), dest="sources")
    ap.add_argument("--query"); ap.add_argument("--limit", type=int)
    ap.add_argument("--no-llm", action="store_true"); ap.add_argument("--force", action="store_true")
    ap.add_argument("--rebuild", action="append", choices=list(SOURCES), dest="rebuild",
                    help="Drop this source's existing rows before re-harvesting it (repeatable).")
    a = ap.parse_args(argv)
    res = harvest(a.sources, out=a.out, query=a.query, limit=a.limit,
                  no_llm=a.no_llm, force=a.force, rebuild=a.rebuild or False, progress=print)
    for name, c in res["per_source"].items():
        print(f"[{name}] {c}")
    print(f"total models: {res['total']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
