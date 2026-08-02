"""Materialize datasets/biomodel_annotation_catalog.json — the annotation
(SBML MIRIAM -> Uberon) organ catalog over the full curated corpus.

Network: fetches/caches each model's SBML (biomodels API). Run once:
  PYTHONUTF8=1 .venv/bin/python scripts/build_annotation_catalog.py
Resumable/robust: models whose SBML can't be fetched/parsed are skipped and
counted, never aborting the run.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from viva_human_atlas.annotation_match import (
    build_annotation_catalog, fetch_sbml, write_catalog_envelope,
)
from viva_human_atlas.coverage import load_corpus_catalog

CORPUS = REPO / "datasets" / "biomodel_corpus_catalog.json"
OUT = REPO / "datasets" / "biomodel_annotation_catalog.json"
BTO = REPO / "datasets" / "bto_uberon_crosswalk.json"


def main() -> None:
    corpus = load_corpus_catalog(str(CORPUS))
    organ_index = corpus["organ_index"]
    model_dos = corpus["biomodel_dos"]
    bto = None
    if BTO.exists():
        import json
        bto = json.loads(BTO.read_text(encoding="utf-8"))
    n = len(model_dos)
    done = {"i": 0, "ok": 0, "err": 0}

    def fetch(bid: str) -> str:
        done["i"] += 1
        if done["i"] % 25 == 0:
            print(f"  {done['i']}/{n} (tagged-so-far via ok fetches {done['ok']}, errors {done['err']})")
        try:
            s = fetch_sbml(bid)
            done["ok"] += 1
            return s
        except Exception as e:  # noqa: BLE001
            done["err"] += 1
            # skip: build_annotation_catalog treats None as sbml-unavailable and continues
            return None

    catalog = build_annotation_catalog(model_dos, organ_index, fetch=fetch, bto_crosswalk=bto)
    env = write_catalog_envelope(OUT, catalog)
    print(f"Wrote {OUT}: n_ids={env['n_ids']} n_tagged={env['n_tagged']} "
          f"(fetch ok={done['ok']} err={done['err']}); organs={len(catalog['organ_to_models'])}")


if __name__ == "__main__":
    main()
