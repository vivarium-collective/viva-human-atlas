#!/usr/bin/env python
"""Build the BioModels -> HRA mapping JSON DB (CLI).

Thin wrapper over `viva_human_atlas.biomodel_hra` (the shared core the
`BiomodelHraMapStep` also uses -- no duplicated pipeline). Reusable and
resumable: each per-model stage is error-isolated and the DB is upserted and
atomically written. See docs/superpowers/specs/2026-08-04-biomodel-hra-map-design.md.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from viva_human_atlas.biomodel_hra import (  # noqa: E402
    DEFAULT_CACHE_DIR,
    DEFAULT_DB_PATH,
    DEFAULT_LLM_MODEL,
    build_map,
    resolve_ids,
)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build the BioModels -> HRA mapping JSON DB.")
    ap.add_argument("--out", default=str(DEFAULT_DB_PATH))
    ap.add_argument("--ids-file"); ap.add_argument("--query"); ap.add_argument("--limit", type=int)
    ap.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--llm-model", default=DEFAULT_LLM_MODEL)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)

    ids = resolve_ids(ids_file=a.ids_file, query=a.query, limit=a.limit)
    build_map(ids=ids, out=a.out, cache_dir=a.cache_dir, no_llm=a.no_llm,
              llm_model=a.llm_model, force=a.force, progress=print)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
