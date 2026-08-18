#!/usr/bin/env python
"""Re-map the committed model_hra_map.json corpus onto HRA organs via the
ontology resolver (Task 5) -- from each row's EXISTING annotations only, no
re-harvest, no network.

Tasks 1-4 built `anatomy_resolver.resolve_organ_keys` (UBERON exact ->
hierarchy roll-up -> BTO/FMA/MeSH crosswalk -> CL cell-type -> ASCT+B gene)
and wired every source's live `build_entry` through it, but the committed DB
predates that wiring: its rows still carry whatever `organs`/mapping_method
the OLD extraction produced. `remap_row` recomputes organs/FTUs/cell-types
from the annotation ids each row already has on disk
(`ontology_ids.{uberon,cl,fma,bto,mesh}` + `gene_symbols` + `name`), so the
new resolver tiers get a chance to place rows that were previously stuck on
organ-level-exact-match alone -- without touching the network.

MeSH note: rows store `ontology_ids.mesh` as plain "MESH:Dxxxxx" id strings
(from `literature.fetch_pubmed_mesh`'s ids, e.g. `biomodel_hra.build_entry`'s
`mesh = sorted({f"MESH:{t['id']}" for t in mesh_terms})`), not the
`{"id", "label"}` dicts `anatomy_crosswalk.crosswalk_mesh_labels` needs (its
crosswalk is keyed by MeSH *label*, since PubMed's D-ids and the SSSOM's
M-ids don't line up). Without labels on disk, the mesh tier legitimately
no-ops here -- it is not run.

Run: `.venv/bin/python scripts/remap_organs.py` (rewrites
datasets/model_hra_map.json in place; prints per-source placed before/after
+ a mapping_method histogram).
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from viva_human_atlas import anatomy_resolver  # noqa: E402
from viva_human_atlas.anatomy_resolver import resolve_organ_keys  # noqa: E402
from viva_human_atlas.hra_mapping import map_to_hra  # noqa: E402
from viva_human_atlas.biomodel_hra import load_map, write_db, DEFAULT_DB_PATH  # noqa: E402
from viva_human_atlas.coverage import load_corpus_catalog  # noqa: E402

DEFAULT_CATALOG_PATH = REPO_ROOT / "datasets" / "biomodel_corpus_catalog.json"


def remap_row(row: dict, organ_index: dict) -> dict:
    """Recompute `organs`/`functional_tissue_units`/`cell_types`/
    `ontology_ids.uberon`/`provenance.mapping_method`/`provenance.confidence`
    for one model_hra_map row, from the row's EXISTING
    `ontology_ids.{uberon,cl,fma,bto,mesh}` + `gene_symbols` + `name`, via
    `anatomy_resolver.resolve_organ_keys` + `hra_mapping.map_to_hra`. No
    network. Deterministic: same input -> same output.

    Returns a new row dict (the input `row` is not mutated); every other
    field is carried over unchanged. `ontology_ids.mesh` is read but NOT fed
    into the resolver's mesh tier -- see the module docstring's MeSH note.
    """
    ont = row.get("ontology_ids") or {}
    uberon = ont.get("uberon") or []
    cl = ont.get("cl") or []
    fma = ont.get("fma") or []
    bto = ont.get("bto") or []
    gene_symbols = row.get("gene_symbols") or []
    name = row.get("name") or ""

    resolver_keys, resolver_method = resolve_organ_keys(
        organ_index, uberon=uberon, cl=cl, fma=fma, bto=bto,
        # mesh intentionally omitted: rows carry MeSH id-strings, not the
        # {"id","label"} dicts the mesh crosswalk tier requires (see module
        # docstring) -- passing them would either no-op or raise.
        gene_symbols=gene_symbols,
    )
    resolver_uberon = {
        organ_index[k]["uberon"] for k in resolver_keys
        if organ_index.get(k, {}).get("uberon")
    }
    new_uberon = sorted(set(uberon) | resolver_uberon)

    hra = map_to_hra(new_uberon, name, organ_index)

    if resolver_keys:
        mapping_method = resolver_method
        confidence = anatomy_resolver._CONFIDENCE.get(resolver_method, "low")
    elif hra["organs"]:
        # organs came from map_to_hra's model-name synonym match alone -- no
        # ontology annotation resolved anything (mirrors biomodel_hra.build_entry).
        mapping_method, confidence = "name_match", "medium"
    else:
        mapping_method, confidence = "", "none"

    out = dict(row)
    out["organs"] = hra["organs"]
    out["functional_tissue_units"] = hra["functional_tissue_units"]
    out["cell_types"] = hra["cell_types"]
    out["ontology_ids"] = dict(ont)
    out["ontology_ids"]["uberon"] = new_uberon
    out["provenance"] = dict(row.get("provenance") or {})
    out["provenance"]["mapping_method"] = mapping_method
    out["provenance"]["confidence"] = confidence
    return out


def main(db_path=None, catalog_path=None) -> None:
    db_path = Path(db_path or DEFAULT_DB_PATH)
    catalog_path = Path(catalog_path or DEFAULT_CATALOG_PATH)

    organ_index = load_corpus_catalog(str(catalog_path))["organ_index"]
    rows = load_map(db_path)

    before_placed = {
        s: sum(1 for r in rows if r["repository"] == s and r.get("organs"))
        for s in sorted({r["repository"] for r in rows})
    }

    remapped = [remap_row(r, organ_index) for r in rows]

    after_placed = {
        s: sum(1 for r in remapped if r["repository"] == s and r.get("organs"))
        for s in sorted({r["repository"] for r in remapped})
    }

    db = {r["identifier"]: r for r in remapped}
    write_db(db, db_path)

    print(f"Re-mapped {len(remapped)} rows -> {db_path}")
    for s in sorted(before_placed):
        n = sum(1 for r in rows if r["repository"] == s)
        print(f"  {s}: placed {before_placed[s]} -> {after_placed[s]} / {n}")

    methods = Counter((r.get("provenance") or {}).get("mapping_method") for r in remapped)
    print(f"  mapping_method histogram (all sources): {dict(methods)}")
    for s in sorted(before_placed):
        s_methods = Counter(
            (r.get("provenance") or {}).get("mapping_method")
            for r in remapped if r["repository"] == s
        )
        print(f"  {s} mapping_method histogram: {dict(s_methods)}")


if __name__ == "__main__":
    main()
