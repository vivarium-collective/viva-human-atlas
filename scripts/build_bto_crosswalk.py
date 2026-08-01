"""Build the committed BTO -> HRA-organ crosswalk (Task 4b).

OFFLINE: loads the committed `datasets/bto_terms.json` (144 corpus BTO
terms with OLS labels + corpus mention counts) and the committed
`datasets/biomodel_corpus_catalog.json`'s `organ_index`
(`viva_human_atlas.coverage.load_corpus_catalog`), crosses them via
`viva_human_atlas.bto_crosswalk.build_bto_uberon_crosswalk`, and writes
`datasets/bto_uberon_crosswalk.json` — a plain `{BTO curie: uberon}` dict
that `annotation_match.map_curie_to_organ` consumes as its `bto_crosswalk`
argument.

Run with: ``.venv/bin/python scripts/build_bto_crosswalk.py`` (no network).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from viva_human_atlas.bto_crosswalk import build_bto_uberon_crosswalk
from viva_human_atlas.coverage import load_corpus_catalog

BTO_TERMS_PATH = REPO_ROOT / "datasets" / "bto_terms.json"
OUT_PATH = REPO_ROOT / "datasets" / "bto_uberon_crosswalk.json"


def main() -> None:
    bto_terms = json.loads(BTO_TERMS_PATH.read_text(encoding="utf-8"))
    print(f"Loaded {len(bto_terms)} corpus BTO terms from {BTO_TERMS_PATH}")

    organ_index = load_corpus_catalog()["organ_index"]
    print(f"Loaded organ_index with {len(organ_index)} organs")

    crosswalk = build_bto_uberon_crosswalk(bto_terms, organ_index)
    covered_mentions = sum(
        bto_terms[curie].get("count", 0) for curie in crosswalk if curie in bto_terms
    )
    print(f"Mapped {len(crosswalk)}/{len(bto_terms)} BTO terms to an organ uberon")
    print(f"Covered BTO mention total: {covered_mentions}")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(crosswalk, indent=2), encoding="utf-8")
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
