#!/usr/bin/env python
"""Enrich datasets/model_hra_map.json in place: organism + gene ids
(HGNC/Ensembl) + gene->Uberon anatomy (via the harvested ASCT+B tables).

Reuses the existing DB (SBML/BioPAX/MeSH already extracted); only makes the new
cached network calls (UniProt per accession, NCBITaxon names). Resumable via the
disk cache. Run:
    PYTHONPATH=. .venv/bin/python scripts/enrich_biomodel_hra_map.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from viva_human_atlas.asctb_tables import build_gene_uberon_index  # noqa: E402
from viva_human_atlas.biomodel_do import build_organ_index  # noqa: E402
from viva_human_atlas.enrich import enrich_map  # noqa: E402

DB = REPO / "datasets" / "model_hra_map.json"
ASCTB = REPO / "datasets" / "asctb_tables.json"
CACHE = REPO / ".cache" / "enrich"


def main() -> int:
    entries = json.loads(DB.read_text(encoding="utf-8"))
    tables = json.loads(ASCTB.read_text(encoding="utf-8"))
    gene_index = build_gene_uberon_index(tables)
    print(f"loaded {len(entries)} models, gene->uberon index {len(gene_index)} genes", flush=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    organ_index = build_organ_index()
    enrich_map(entries, gene_index=gene_index, organ_index=organ_index,
               cache_dir=str(CACHE), progress=lambda m: print(m, flush=True))
    entries.sort(key=lambda e: e.get("biomodel_id", ""))
    tmp = DB.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(entries, indent=2), encoding="utf-8")
    tmp.replace(DB)
    n_org = sum(1 for e in entries if e.get("organism"))
    n_gene = sum(1 for e in entries if (e.get("molecular_ids") or {}).get("hgnc"))
    n_ub = sum(1 for e in entries if (e.get("ontology_ids") or {}).get("uberon"))
    print(f"DONE: organism {n_org}, hgnc genes {n_gene}, uberon {n_ub} of {len(entries)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
