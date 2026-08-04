#!/usr/bin/env python
"""Build the BioModels -> HRA mapping JSON DB (keyed by model id).

Reusable, resumable: each per-model stage (SBML / metadata / HRA / literature /
LLM) is error-isolated (a stage failure is recorded into `provenance.errors`
and never aborts the entry); the literature and LLM stages are additionally
disk-cached via `cache_dir`. The DB is upserted and atomically written.
See docs/superpowers/specs/2026-08-04-biomodel-hra-map-design.md.
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

from viva_human_atlas.sbml_identifiers import extract_identifiers
from viva_human_atlas.hra_mapping import map_to_hra
from viva_human_atlas.literature import get_literature_text
from viva_human_atlas import llm_extract
from viva_human_atlas.biomodel_do import build_organ_index
from viva_human_atlas.annotation_match import fetch_sbml

_IRI = "https://identifiers.org/biomodels.db:{}"


def _default_meta(biomodel_id: str) -> dict:
    import biomodels
    m = biomodels.get_metadata(biomodel_id) or {}
    pub = (m.get("publication") or {})
    return {"name": m.get("name") or biomodel_id, "pmid": pub.get("pmid") or pub.get("id"),
            "doi": pub.get("doi"), "journal": pub.get("journal"), "year": pub.get("year"),
            "title": pub.get("title")}


def build_entry(biomodel_id, organ_index, *, cache_dir=None, no_llm=False,
                llm_model="claude-haiku-4-5-20251001",
                _sbml=fetch_sbml, _ids=extract_identifiers, _meta=_default_meta,
                _lit=get_literature_text, _llm=None) -> dict:
    errors = []
    ids = {"chebi": [], "uniprot": [], "kegg": [], "go": [], "cl": [], "uberon": [], "fma": [], "bto": [], "n_species": 0}
    try:
        ids = _ids(_sbml(biomodel_id))
    except Exception as e:  # noqa: BLE001
        errors.append(f"sbml:{e}")
    try:
        meta = _meta(biomodel_id)
    except Exception as e:  # noqa: BLE001
        meta = {"name": biomodel_id}; errors.append(f"metadata:{e}")

    try:
        hra = map_to_hra(ids["uberon"], meta.get("name", ""), organ_index)
        # merge SBML-annotated CL directly into cell_types
        cl_seen = {c["cl"] for c in hra["cell_types"]}
        for cl in ids["cl"]:
            if cl not in cl_seen:
                hra["cell_types"].append({"label": None, "cl": cl})
    except Exception as e:  # noqa: BLE001
        errors.append(f"hra:{e}")
        hra = {"organs": [], "functional_tissue_units": [], "cell_types": [],
               "uberon_organ_ids": [], "uberon_subregion_ids": []}

    entry = {
        "identifier": _IRI.format(biomodel_id),
        "repository": "biomodels",
        "biomodel_id": biomodel_id,
        "name": meta.get("name"),
        "paper_doi": meta.get("doi"),
        "organs": hra["organs"],
        "functional_tissue_units": hra["functional_tissue_units"],
        "cell_types": hra["cell_types"],
        "molecular_ids": {k: ids[k] for k in ("chebi", "uniprot", "kegg", "go")},
        "ontology_ids": {k: ids[k] for k in ("cl", "uberon", "fma", "bto")},
        "provenance": {
            "pmid": meta.get("pmid"), "title": meta.get("title"),
            "journal": meta.get("journal"), "year": meta.get("year"),
            "n_species": ids["n_species"],
            "uberon_organ_ids": hra["uberon_organ_ids"],
            "uberon_subregion_ids": hra["uberon_subregion_ids"],
            "text_source": "none", "has_fulltext": False, "errors": errors,
        },
    }

    if not no_llm:
        lit = None
        try:
            lit = _lit(meta.get("pmid"), meta.get("doi"), cache_dir=cache_dir)
            entry["provenance"]["text_source"] = lit["text_source"]
            entry["provenance"]["has_fulltext"] = lit["has_fulltext"]
        except Exception as e:  # noqa: BLE001
            errors.append(f"lit:{e}")
        if lit is not None:
            try:
                extractor = _llm or llm_extract.extract
                entry["literature"] = extractor(meta.get("name"), lit["abstract"], lit["fulltext"],
                                                model=llm_model, cache_dir=cache_dir)
            except Exception as e:  # noqa: BLE001
                errors.append(f"llm:{e}")
    return entry


def upsert_db(db: dict, entry: dict) -> None:
    db[entry["biomodel_id"]] = entry


def load_db(path: str) -> dict:
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def write_db(db: dict, path: str) -> None:
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(db, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build the BioModels -> HRA mapping JSON DB.")
    ap.add_argument("--out", default=str(REPO / "datasets" / "biomodel_hra_map.json"))
    ap.add_argument("--ids-file"); ap.add_argument("--query"); ap.add_argument("--limit", type=int)
    ap.add_argument("--cache-dir", default=str(REPO / ".cache" / "biomodel_hra_map"))
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--llm-model", default="claude-haiku-4-5-20251001")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)

    if a.ids_file:
        ids = [x.strip() for x in Path(a.ids_file).read_text().split() if x.strip()]
    elif a.query:
        from viva_human_atlas.biomodels_search import search_biomodels
        ids = search_biomodels(a.query, a.limit or 25)
    else:
        from viva_human_atlas.biomodels_search import fetch_all_biomodel_ids
        ids = fetch_all_biomodel_ids()
    if a.limit:
        ids = ids[: a.limit]

    db = load_db(a.out)
    organ_index = build_organ_index()
    Path(a.cache_dir).mkdir(parents=True, exist_ok=True)
    for i, bid in enumerate(ids, 1):
        if bid in db and not a.force:
            continue
        try:
            upsert_db(db, build_entry(bid, organ_index, cache_dir=a.cache_dir,
                                      no_llm=a.no_llm, llm_model=a.llm_model))
        except Exception as e:  # noqa: BLE001 — never abort the whole run
            print(f"  ERROR {bid}: {e}")
        if i % 10 == 0:
            write_db(db, a.out); print(f"  {i}/{len(ids)} (db={len(db)})")
    write_db(db, a.out)
    print(f"Wrote {a.out}: {len(db)} models")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
