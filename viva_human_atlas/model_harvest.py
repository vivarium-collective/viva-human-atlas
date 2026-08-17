"""Orchestrate incremental, non-destructive harvesting of every registered model
source into the single `datasets/model_hra_map.json`. A plain rerun harvests only
newly-posted models; a source rebuild never touches another source's rows."""
from __future__ import annotations

from collections import Counter
from typing import Callable, Optional, Sequence

from process_bigraph import Step

from viva_human_atlas import biomodel_hra as bh
from viva_human_atlas import physionet
from viva_human_atlas import physiome
from viva_human_atlas.biomodel_do import build_organ_index

DEFAULT_DB_PATH = bh.DEFAULT_DB_PATH

SOURCES: dict[str, dict] = {
    "biomodels": {
        "repository": "biomodels",
        "list_fn": lambda **k: bh.resolve_ids(query=k.get("query"), limit=k.get("limit")),
        "entry_fn": lambda bid, oi, **k: bh.build_entry(bid, oi, cache_dir=k.get("cache_dir"),
                                                        no_llm=k.get("no_llm", True)),
        "id_of": lambda bid: bh._IRI.format(bid),   # item -> identifier
    },
    "physionet": {
        "repository": "physionet",
        "list_fn": lambda **k: physionet.resolve_projects(query=k.get("query"), limit=k.get("limit")),
        "entry_fn": lambda proj, oi, **k: physionet.build_entry(proj, oi, cache_dir=k.get("cache_dir"),
                                                                no_llm=k.get("no_llm", True)),
        "id_of": lambda proj: proj["identifier"],
    },
    "physiome": {
        "repository": "physiome",
        "list_fn": lambda **k: physiome.resolve_exposures(query=k.get("query"), limit=k.get("limit"),
                                                          cache_dir=k.get("cache_dir")),
        "entry_fn": lambda exp, oi, **k: physiome.build_entry(exp, oi, citations=k.get("citations"),
                                                             cache_dir=k.get("cache_dir"),
                                                             no_llm=k.get("no_llm", True)),
        "id_of": lambda exp: exp["identifier"],
    },
}


def harvest(sources: Optional[Sequence[str]] = None, *, out=DEFAULT_DB_PATH,
            query: Optional[str] = None, limit: Optional[int] = None, no_llm: bool = True,
            force: bool = False, cache_dir=None, rebuild: "bool | Sequence[str]" = False,
            progress: Optional[Callable[[str], None]] = None) -> dict:
    names = list(sources) if sources else list(SOURCES)
    rebuild_set = set(names) if rebuild is True else set(rebuild or [])
    db = bh.load_db(out)
    organ_index = build_organ_index()
    per_source: dict[str, dict] = {}
    citations = physiome.load_citations(cache_dir=cache_dir) if "physiome" in names else {}

    for name in names:
        src = SOURCES[name]
        if name in rebuild_set:
            for k in [k for k, v in db.items() if v.get("repository") == src["repository"]]:
                del db[k]
        counts = {"resolved": 0, "new": 0, "updated": 0, "skipped": 0, "errors": 0}
        items = src["list_fn"](query=query, limit=limit, cache_dir=cache_dir)
        counts["resolved"] = len(items)
        for i, item in enumerate(items, 1):
            ident = src["id_of"](item)
            if not bh.should_process(db, ident, force):
                counts["skipped"] += 1
                continue
            existed = ident in db
            try:
                bh.upsert_db(db, src["entry_fn"](item, organ_index, cache_dir=cache_dir,
                                                 no_llm=no_llm, citations=citations))
                counts["updated" if existed else "new"] += 1
            except Exception as e:  # noqa: BLE001 — never abort the harvest
                counts["errors"] += 1
                if progress:
                    progress(f"  ERROR [{name}] {ident}: {e}")
            if i % 10 == 0:
                bh.write_db(db, out)
                if progress:
                    progress(f"  [{name}] {i}/{len(items)} (db={len(db)})")
        per_source[name] = counts
        if progress:
            progress(f"[{name}] {counts}")

    bh.write_db(db, out)
    return {"per_source": per_source, "total": len(db)}


# --------------------------------------------------------------------------- #
# Vivarium Step                                                               #
# --------------------------------------------------------------------------- #
class ModelHarvestStep(Step):
    """Cache-or-harvest the unified model DB across all sources and emit path,
    model count, per-source counts, and a coverage summary."""

    description = ("Load (cache-or-harvest) the unified BioModels+PhysioNet -> HRA "
                   "model DB and emit its path, total count, per-source counts, and "
                   "coverage summary. Reproducible: run this study to refresh the DB.")

    config_schema = {
        "db_path": "string", "sources": "list", "query": "string", "limit": "integer",
        "no_llm": "boolean", "force": "boolean", "build_if_missing": "boolean",
        "analysis_out_dir": "string", "rebuild": "list",
    }

    def inputs(self):
        return {}

    def outputs(self):
        return {"db_path": "string", "n_models": "integer", "per_source": "tree", "summary": "tree"}

    def update(self, inputs):
        db_path = self.config.get("db_path") or str(DEFAULT_DB_PATH)
        if self.config.get("build_if_missing", False) or self.config.get("force", False):
            harvest(self.config.get("sources") or None, out=db_path,
                    query=self.config.get("query"), limit=self.config.get("limit"),
                    no_llm=bool(self.config.get("no_llm", True)),
                    force=bool(self.config.get("force", False)),
                    rebuild=self.config.get("rebuild") or False)
        entries = bh.load_map(db_path)
        per_source = dict(Counter(e.get("repository", "unknown") for e in entries))
        return {"db_path": str(db_path), "n_models": len(entries),
                "per_source": per_source, "summary": bh.summarize_map(entries)}
