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

import requests

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from viva_human_atlas.sbml_identifiers import extract_identifiers
from viva_human_atlas.hra_mapping import map_to_hra
from viva_human_atlas.literature import get_literature_text, fetch_pubmed_mesh
from viva_human_atlas import llm_extract
from viva_human_atlas.biomodel_do import build_organ_index
from viva_human_atlas.annotation_match import fetch_sbml
from viva_human_atlas.biopax_identifiers import extract_biopax_identifiers, fetch_biopax
from viva_human_atlas.anatomy_crosswalk import crosswalk_anatomy, crosswalk_mesh_labels

_IRI = "https://identifiers.org/biomodels.db:{}"
_MODEL_URL = "https://www.ebi.ac.uk/biomodels/{}"


def _default_meta(biomodel_id: str, *, _get=None) -> dict:
    # The `biomodels` python client's get_metadata() returns a pydantic
    # Metadata object exposing only model_id + files -- no publication/name --
    # so the BioModels REST model endpoint is used directly instead.
    get = _get or requests.get
    r = get(_MODEL_URL.format(biomodel_id), params={"format": "json"}, timeout=30)
    r.raise_for_status()
    d = r.json()
    pub = d.get("publication") or {}
    ptype = (pub.get("type") or "").lower()
    acc = pub.get("accession")
    pmid = acc if "pubmed" in ptype else None
    doi = acc if "doi" in ptype else (pub.get("doi") or None)
    return {"name": d.get("name") or biomodel_id, "pmid": pmid, "doi": doi,
            "journal": pub.get("journal"), "year": pub.get("year"), "title": pub.get("title")}


def build_entry(biomodel_id, organ_index, *, cache_dir=None, no_llm=False,
                llm_model="claude-haiku-4-5-20251001",
                _sbml=fetch_sbml, _ids=extract_identifiers, _meta=_default_meta,
                _lit=get_literature_text, _llm=None,
                _biopax=fetch_biopax, _biopax_ids=extract_biopax_identifiers,
                _bto_map=None, _mesh_label_map=None, _pubmed_mesh=fetch_pubmed_mesh) -> dict:
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

    biopax = {"chebi": [], "uniprot": [], "kegg": [], "go": [], "reactome": [], "taxonomy": []}
    try:
        owl = _biopax(biomodel_id, cache_dir=cache_dir)
        if owl:
            biopax = _biopax_ids(owl)
    except Exception as e:  # noqa: BLE001
        errors.append(f"biopax:{e}")

    # union SBML + BioPAX per molecular collection
    molecular = {k: sorted(set(ids[k]) | set(biopax[k])) for k in ("chebi", "uniprot", "kegg", "go")}
    molecular["reactome"] = sorted(biopax["reactome"])

    # BioModels' SBML/BioPAX essentially never carry MeSH ids, but PubMed
    # assigns MeSH headings per paper -- an anatomy-relevant stage that runs
    # regardless of --no-llm (it isn't part of the LLM extraction stage).
    mesh_terms = []
    try:
        mesh_terms = _pubmed_mesh(meta.get("pmid"), cache_dir=cache_dir) if meta.get("pmid") else []
    except Exception as e:  # noqa: BLE001
        errors.append(f"mesh:{e}")
    mesh = sorted({f"MESH:{t['id']}" for t in mesh_terms})

    # Enrich Uberon/CL from BTO (SBML/BioPAX anatomy) and MeSH (PubMed
    # headings) crosswalks, then feed the enriched Uberon into HRA mapping.
    # The crosswalk sub-stage is nested inside the HRA stage's try/except: a
    # crosswalk failure is isolated (`crosswalk:{e}`) and falls back to the
    # raw SBML/BioPAX uberon/cl without aborting the HRA mapping itself.
    ont_uberon, ont_cl = sorted(set(ids["uberon"])), sorted(set(ids["cl"]))
    try:
        try:
            raw_ont = {"uberon": ids["uberon"], "cl": ids["cl"], "mesh": mesh,
                       "fma": ids["fma"], "bto": ids["bto"]}
            derived_bto = crosswalk_anatomy(raw_ont, bto_map=_bto_map)
            derived_mesh = crosswalk_mesh_labels(mesh_terms, _mesh_label_map)
            ont_uberon = sorted(set(ids["uberon"]) | set(derived_bto["uberon"]) | set(derived_mesh["uberon"]))
            ont_cl = sorted(set(ids["cl"]) | set(derived_mesh["cl"]))
        except Exception as e:  # noqa: BLE001
            errors.append(f"crosswalk:{e}")

        hra = map_to_hra(ont_uberon, meta.get("name", ""), organ_index)
        # merge SBML-annotated + MeSH-derived CL directly into cell_types
        cl_seen = {c["cl"] for c in hra["cell_types"]}
        for cl in ont_cl:
            if cl not in cl_seen:
                cl_seen.add(cl)
                hra["cell_types"].append({"label": None, "cl": cl})
    except Exception as e:  # noqa: BLE001
        errors.append(f"hra:{e}")
        hra = {"organs": [], "functional_tissue_units": [], "cell_types": [],
               "uberon_organ_ids": [], "uberon_subregion_ids": []}

    # Preferred paper link is PubMed (most BioModels record a PubMed ID, not a
    # DOI); fall back to a DOI link, then None.
    pmid, doi = meta.get("pmid"), meta.get("doi")
    paper_url = (
        f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid
        else f"https://doi.org/{doi}" if doi else None
    )

    entry = {
        "identifier": _IRI.format(biomodel_id),
        "repository": "biomodels",
        "biomodel_id": biomodel_id,
        "name": meta.get("name"),
        "paper_url": paper_url,
        "paper_pmid": pmid,
        "paper_doi": doi,
        "taxonomy": biopax["taxonomy"],
        "organs": hra["organs"],
        "functional_tissue_units": hra["functional_tissue_units"],
        "cell_types": hra["cell_types"],
        "molecular_ids": molecular,
        "ontology_ids": {"uberon": ont_uberon, "cl": ont_cl, "mesh": mesh,
                         "fma": ids["fma"], "bto": ids["bto"]},
        "provenance": {
            "journal": meta.get("journal"), "year": meta.get("year"), "title": meta.get("title"),
            "n_species": ids["n_species"],
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
    """Internal representation is always a `{biomodel_id: entry}` dict, but
    the on-disk file is a JSON array (see `write_db`); a legacy id-keyed
    object is still accepted so resuming an old-format DB keeps working."""
    p = Path(path)
    if not p.exists():
        return {}
    data = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return {e["biomodel_id"]: e for e in data}
    return data


def write_db(db: dict, path: str) -> None:
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    ordered = sorted(db.values(), key=lambda e: e.get("biomodel_id", ""))
    tmp.write_text(json.dumps(ordered, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def should_process(db: dict, bid: str, force: bool) -> bool:
    if force:
        return True
    entry = db.get(bid)
    if entry is None:
        return True
    return bool(entry.get("provenance", {}).get("errors"))  # reprocess if it errored


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
        if not should_process(db, bid, a.force):
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
