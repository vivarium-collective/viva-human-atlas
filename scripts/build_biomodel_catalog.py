"""Build the full curated-corpus biomodel-DO catalog (Task A).

Retrieves every curated ("BIOMD"-prefixed) BioModels identifier
(`biomodels_search.fetch_all_biomodel_ids`), resolves each id's name in
parallel (`biomodels_search.fetch_biomodels_named`), organ-tags the whole
set against the live HRA reference organs
(`biomodel_do.build_catalog_from_models`), and writes the committed dataset
`datasets/biomodel_corpus_catalog.json`:

    {"n_ids": <total curated ids>,
     "n_named": <# resolved to a non-empty name>,
     "n_tagged": <# biomodel_dos with >=1 matched organ>,
     "catalog": {"biomodel_dos": [...], "organ_index": {...},
                 "organ_to_models": {...}}}

Run with: ``PYTHONUTF8=1 .venv/bin/python scripts/build_biomodel_catalog.py``
(network required — hits the live BioModels registry/search + HRA CCF API;
~1,096 curated models, fetched in parallel, ~2-3 min).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from viva_human_atlas.biomodel_do import build_catalog_from_models
from viva_human_atlas.biomodels_search import (
    fetch_all_biomodel_ids,
    fetch_biomodels_named,
)

OUT_PATH = REPO_ROOT / "datasets" / "biomodel_corpus_catalog.json"


def main() -> None:
    print("Fetching all curated BioModels identifiers...")
    ids = fetch_all_biomodel_ids()
    print(f"  {len(ids)} curated (BIOMD-prefixed) ids")

    print("Resolving model names in parallel...")
    models = fetch_biomodels_named(ids)
    n_named = sum(1 for m in models if m.get("name"))
    print(f"  {n_named}/{len(models)} resolved to a non-empty name")

    print("Building organ-tagged catalog against live HRA reference organs...")
    catalog = build_catalog_from_models(models)
    n_tagged = sum(1 for do in catalog["biomodel_dos"] if do.get("organs"))
    print(f"  {n_tagged}/{len(catalog['biomodel_dos'])} biomodel_dos tagged with >=1 organ")

    payload = {
        "n_ids": len(ids),
        "n_named": n_named,
        "n_tagged": n_tagged,
        "catalog": catalog,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, indent=2))
    size_kb = OUT_PATH.stat().st_size / 1024
    print(f"Wrote {OUT_PATH} ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
