"""Orchestrate incremental, non-destructive harvesting of every registered model
source into the single `datasets/model_hra_map.json`. A plain rerun harvests only
newly-posted models; a source rebuild never touches another source's rows."""
from __future__ import annotations

from typing import Callable, Optional, Sequence

from viva_human_atlas import biomodel_hra as bh
from viva_human_atlas import physionet
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
}


def harvest(sources: Optional[Sequence[str]] = None, *, out=DEFAULT_DB_PATH,
            query: Optional[str] = None, limit: Optional[int] = None, no_llm: bool = True,
            force: bool = False, cache_dir=None,
            progress: Optional[Callable[[str], None]] = None) -> dict:
    names = list(sources) if sources else list(SOURCES)
    db = bh.load_db(out)
    organ_index = build_organ_index()
    per_source: dict[str, dict] = {}

    for name in names:
        src = SOURCES[name]
        counts = {"resolved": 0, "new": 0, "updated": 0, "skipped": 0, "errors": 0}
        items = src["list_fn"](query=query, limit=limit)
        counts["resolved"] = len(items)
        for i, item in enumerate(items, 1):
            ident = src["id_of"](item)
            if not bh.should_process(db, ident, force):
                counts["skipped"] += 1
                continue
            existed = ident in db
            try:
                bh.upsert_db(db, src["entry_fn"](item, organ_index, cache_dir=cache_dir, no_llm=no_llm))
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
