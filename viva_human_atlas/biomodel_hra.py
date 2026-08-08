"""BioModels -> HRA mapping: shared core + a reusable Vivarium Step.

This is the single source of truth for the BioModels->HRA extraction that
`scripts/build_biomodel_hra_map.py` (the CLI) and `BiomodelHraMapStep` (the
workbench Step) both call, so neither duplicates the pipeline.

Per model, each stage (SBML / metadata / BioPAX / MeSH / HRA crosswalk /
literature / LLM) is error-isolated -- a stage failure is recorded into
`provenance.errors` and never aborts the entry. The literature/LLM stages are
disk-cached via `cache_dir`. The DB is stored on disk as a JSON **array** of
entries (sorted by identifier); a legacy id-keyed object is still accepted on
read so an old-format file keeps resuming.

`BiomodelHraMapStep` is cache-or-load: it loads the committed
`datasets/model_hra_map.json` if present (the normal, network-free path) and
only runs the live extraction when the cache is missing and building is
enabled. It emits the DB path + model count + coverage summary (not the whole
2.7 MB DB), the summary matching the committed figure
(`scripts/make_biomodel_hra_figure.py`). See
docs/superpowers/specs/2026-08-04-biomodel-hra-map-design.md.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

import requests
from process_bigraph import Step

from viva_human_atlas.sbml_identifiers import extract_identifiers
from viva_human_atlas.hra_mapping import map_to_hra
from viva_human_atlas.literature import get_literature_text, fetch_pubmed_mesh
from viva_human_atlas import llm_extract
from viva_human_atlas.biomodel_do import build_organ_index
from viva_human_atlas.annotation_match import fetch_sbml
from viva_human_atlas.biopax_identifiers import extract_biopax_identifiers, fetch_biopax
from viva_human_atlas.anatomy_crosswalk import crosswalk_anatomy, crosswalk_mesh_labels

_REPO = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = _REPO / "datasets" / "model_hra_map.json"
DEFAULT_CACHE_DIR = _REPO / ".cache" / "biomodel_hra_map"
DEFAULT_LLM_MODEL = "claude-haiku-4-5-20251001"

_IRI = "https://identifiers.org/biomodels.db:{}"
_MODEL_URL = "https://www.ebi.ac.uk/biomodels/{}"


# --------------------------------------------------------------------------- #
# Extraction pipeline (moved verbatim from scripts/build_biomodel_hra_map.py)  #
# --------------------------------------------------------------------------- #
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
                llm_model=DEFAULT_LLM_MODEL,
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
        "source_id": biomodel_id,
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
    db[entry["identifier"]] = entry


def load_db(path) -> dict:
    """Internal representation is always `{identifier: entry}`; the on-disk
    file is a JSON array (see `write_db`). Legacy `biomodel_id`-keyed
    lists/objects are re-keyed on `identifier` so old-format DBs keep
    resuming."""
    p = Path(path)
    if not p.exists():
        return {}
    data = json.loads(p.read_text(encoding="utf-8"))
    entries = data if isinstance(data, list) else list(data.values())
    return {e["identifier"]: e for e in entries}


def write_db(db: dict, path) -> None:
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    ordered = sorted(db.values(), key=lambda e: e.get("identifier", ""))
    tmp.write_text(json.dumps(ordered, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def should_process(db: dict, key: str, force: bool) -> bool:
    if force:
        return True
    entry = db.get(key)
    if entry is None:
        return True
    return bool(entry.get("provenance", {}).get("errors"))  # reprocess if it errored


def resolve_ids(*, ids_file: Optional[str] = None, query: Optional[str] = None,
                limit: Optional[int] = None) -> List[str]:
    """Resolve the list of BioModels ids to process: from an explicit ids
    file, a BioModels search query, or (default) the full curated corpus,
    optionally truncated to `limit`."""
    if ids_file:
        ids = [x.strip() for x in Path(ids_file).read_text().split() if x.strip()]
    elif query:
        from viva_human_atlas.biomodels_search import search_biomodels
        ids = search_biomodels(query, limit or 25)
    else:
        from viva_human_atlas.biomodels_search import fetch_all_biomodel_ids
        ids = fetch_all_biomodel_ids()
    if limit:
        ids = ids[:limit]
    return ids


def build_map(*, ids: Optional[Sequence[str]] = None, out=DEFAULT_DB_PATH,
              cache_dir=DEFAULT_CACHE_DIR, no_llm: bool = False,
              llm_model: str = DEFAULT_LLM_MODEL, force: bool = False,
              limit: Optional[int] = None, ids_file: Optional[str] = None,
              query: Optional[str] = None,
              progress: Optional[Callable[[str], None]] = None) -> dict:
    """Run (or resume) the extraction over `ids` and write the DB to `out`.

    Resumable: entries already present without errors are skipped unless
    `force`. Returns the in-memory `{identifier: entry}` dict.
    """
    if ids is None:
        ids = resolve_ids(ids_file=ids_file, query=query, limit=limit)
    db = load_db(out)
    organ_index = build_organ_index()
    Path(cache_dir).mkdir(parents=True, exist_ok=True)
    for i, bid in enumerate(ids, 1):
        identifier = _IRI.format(bid)
        if not should_process(db, identifier, force):
            continue
        try:
            upsert_db(db, build_entry(bid, organ_index, cache_dir=str(cache_dir),
                                      no_llm=no_llm, llm_model=llm_model))
        except Exception as e:  # noqa: BLE001 — never abort the whole run
            if progress:
                progress(f"  ERROR {bid}: {e}")
        if i % 10 == 0:
            write_db(db, out)
            if progress:
                progress(f"  {i}/{len(ids)} (db={len(db)})")
    write_db(db, out)
    if progress:
        progress(f"Wrote {out}: {len(db)} models")
    return db


# --------------------------------------------------------------------------- #
# Reusable load / summarize / cache-or-load layer (Step + downstream consumers) #
# --------------------------------------------------------------------------- #
def load_map(path=DEFAULT_DB_PATH) -> List[dict]:
    """Return the DB as its on-disk JSON **array** of entries (sorted by
    identifier), or `[]` if the file does not exist. A legacy id-keyed
    object on disk is normalized to the array form."""
    p = Path(path)
    if not p.exists():
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    entries = list(data.values()) if isinstance(data, dict) else data
    return sorted(entries, key=lambda e: e.get("identifier", ""))


# Coverage categories, matching scripts/make_biomodel_hra_figure.py. Each maps
# a model entry to a per-model term count.
_SUMMARY_CATS: Dict[str, Callable[[dict], int]] = {
    "organs": lambda e: len(e.get("organs") or []),
    "functional_tissue_units": lambda e: len(e.get("functional_tissue_units") or []),
    "cell_types": lambda e: len(e.get("cell_types") or []),
    "uberon": lambda e: len((e.get("ontology_ids") or {}).get("uberon") or []),
    "hra_pop_cell_types": lambda e: sum(len(h.get("cell_types") or []) for h in (e.get("hra_pop") or [])),
    "mesh": lambda e: len((e.get("ontology_ids") or {}).get("mesh") or []),
    "chebi": lambda e: len((e.get("molecular_ids") or {}).get("chebi") or []),
    "uniprot": lambda e: len((e.get("molecular_ids") or {}).get("uniprot") or []),
    "kegg": lambda e: len((e.get("molecular_ids") or {}).get("kegg") or []),
    "go": lambda e: len((e.get("molecular_ids") or {}).get("go") or []),
}


def _has_molecular(e: dict) -> bool:
    return any((e.get("molecular_ids") or {}).get(k) for k in ("chebi", "uniprot", "kegg", "go", "reactome"))


def summarize_map(entries: Sequence[dict]) -> dict:
    """Coverage summary of a DB (the numbers the summary figure shows).

    Returns `{"n_models", "n_with_molecular", "n_with_uberon", "n_with_hrapop",
    "coverage": {cat: {"count", "mean", "max"}}}` where `count` is the number
    of models carrying >=1 term of that category, `mean` is the mean over
    models that carry >=1, and `max` is the per-model maximum.
    """
    n = len(entries)
    coverage: Dict[str, dict] = {}
    for cat, fn in _SUMMARY_CATS.items():
        counts = [fn(e) for e in entries]
        nz = [c for c in counts if c > 0]
        coverage[cat] = {
            "count": len(nz),
            "mean": round(sum(nz) / len(nz), 3) if nz else 0.0,
            "max": max(counts) if counts else 0,
        }
    return {
        "n_models": n,
        "n_with_molecular": sum(1 for e in entries if _has_molecular(e)),
        "n_with_uberon": coverage["uberon"]["count"],
        "n_with_hrapop": coverage["hra_pop_cell_types"]["count"],
        "coverage": coverage,
    }


def build_or_load(*, out=DEFAULT_DB_PATH, force: bool = False,
                  build_if_missing: bool = True, **build_kw) -> List[dict]:
    """Cache-or-load: return the DB as a JSON array. If `out` exists and not
    `force`, load and return it (no network). Otherwise, if `build_if_missing`
    (or `force`), run `build_map(out=out, force=force, **build_kw)` and return
    the result; if building is disabled and the cache is missing, return `[]`.
    """
    p = Path(out)
    if p.exists() and not force:
        return load_map(p)
    if build_if_missing or force:
        build_map(out=out, force=force, **build_kw)
        return load_map(p)
    return []


# --------------------------------------------------------------------------- #
# Vivarium Step                                                               #
# --------------------------------------------------------------------------- #
class BiomodelHraMapStep(Step):
    """Step: make the BioModels->HRA map DB available (cache-or-load).

    Normal path is network-free: it loads the committed
    `datasets/model_hra_map.json` and emits the DB path, model count, and a
    coverage summary (not the whole DB). If the cache is missing and
    `build_if_missing` is set, it runs the live extraction first (slow,
    network) -- otherwise it emits an empty summary.
    """

    description = (
        "Load (cache-or-build) the BioModels->HRA map DB and emit its path, "
        "model count, and coverage summary. The DB itself (a JSON array of "
        "per-model molecular ids, publication links, organism, and HRA "
        "organ/FTU/cell-type mapping) is downloadable from the workspace "
        "Resources; this Step surfaces the count + coverage without emitting "
        "the whole 2.7 MB file."
    )

    config_schema = {
        "db_path": "string",
        "force": "boolean",
        "no_llm": "boolean",
        "build_if_missing": "boolean",
        "limit": "integer",
        # Injected by the workbench for a `baseline.step` run
        # (`<study>/analyses/<run_id>/`): when set, the DB is written there so it
        # is downloadable from the Runs/Analysis tab under this run.
        "analysis_out_dir": "string",
    }

    def inputs(self):
        return {}

    def outputs(self):
        return {
            "db_path": "string",
            "n_models": "integer",
            "summary": "tree",
        }

    def update(self, inputs):
        db_path = self.config.get("db_path") or str(DEFAULT_DB_PATH)
        limit = self.config.get("limit") or None
        entries = build_or_load(
            out=db_path,
            force=bool(self.config.get("force", False)),
            build_if_missing=bool(self.config.get("build_if_missing", True)),
            no_llm=bool(self.config.get("no_llm", True)),
            limit=int(limit) if limit else None,
        )
        summary = summarize_map(entries)
        self._write_analysis_copy(entries)
        return {
            "db_path": str(db_path),
            "n_models": summary["n_models"],
            "summary": summary,
        }

    def _write_analysis_copy(self, entries) -> None:
        """When the workbench injects `analysis_out_dir` (a `baseline.step` run's
        `<study>/analyses/<run_id>/`), write the DB there as a downloadable
        per-run analysis artifact. Best-effort — never fails the run."""
        out_dir = self.config.get("analysis_out_dir")
        if not out_dir:
            return
        try:
            out = Path(out_dir)
            out.mkdir(parents=True, exist_ok=True)
            (out / "model_hra_map.json").write_text(
                json.dumps(list(entries), indent=2), encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass


BiomodelHraMapStep.contract = {
    "summary": BiomodelHraMapStep.description,
    "outputs": {
        "db_path": "Repo-relative path to the JSON-array DB on disk (the "
                   "workspace-registered downloadable dataset).",
        "n_models": "Number of models in the DB.",
        "summary": "Coverage summary (summarize_map): n_models, "
                   "n_with_molecular / n_with_uberon / n_with_hrapop, and a "
                   "per-category coverage {count, mean, max} matching the "
                   "committed summary figure.",
    },
    "assumptions": [
        "Normal operation is cache-or-load: the committed "
        "datasets/model_hra_map.json is loaded network-free. A live "
        "rebuild only happens if the cache is absent and build_if_missing is "
        "set, and is slow (fetches every curated BioModel).",
    ],
}
