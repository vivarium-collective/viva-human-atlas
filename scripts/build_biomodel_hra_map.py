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

from viva_human_atlas.model_harvest import harvest  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Harvest BioModels into the unified HRA model DB.")
    ap.add_argument("--out"); ap.add_argument("--query"); ap.add_argument("--limit", type=int)
    ap.add_argument("--no-llm", action="store_true"); ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    kw = {"out": a.out} if a.out else {}
    harvest(["biomodels"], query=a.query, limit=a.limit, no_llm=a.no_llm,
            force=a.force, progress=print, **kw)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
