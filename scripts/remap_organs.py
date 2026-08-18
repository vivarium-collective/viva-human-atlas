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
from viva_human_atlas.physiome_organ_map import (  # noqa: E402
    map_exposure_to_organs, _CONFIDENCE as _PHYSIOME_CONFIDENCE,
)
from viva_human_atlas.physionet_organ_map import map_project_to_organs  # noqa: E402

DEFAULT_CATALOG_PATH = REPO_ROOT / "datasets" / "biomodel_corpus_catalog.json"

# Shared method->confidence table for sources whose own mapper doesn't return
# a confidence (physionet_organ_map.map_project_to_organs never sets one --
# see _remap_physionet_row). Same values physiome_organ_map._CONFIDENCE uses.
_METHOD_CONFIDENCE = {**_PHYSIOME_CONFIDENCE, "unmapped": "none"}


def _remap_annotation_row(row: dict, organ_index: dict) -> dict:
    """`remap_row` for sources whose `ontology_ids`/`gene_symbols` are
    GENUINE raw annotations (BioModels: SBML/BioPAX + BTO/MeSH-crosswalk
    ids) -- recompute via `anatomy_resolver.resolve_organ_keys` +
    `hra_mapping.map_to_hra`. See `remap_row`'s docstring for why this path
    is repository-specific."""
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


def _remap_physiome_row(row: dict, organ_index: dict) -> dict:
    """`remap_row` for physiome. `ontology_ids.uberon` on these rows is NOT a
    raw annotation -- `physiome.build_entry` writes back `hra["uberon_organ_ids"]`,
    the organ id its OWN keyword/category mapper already resolved. Feeding that
    echo into `resolve_organ_keys` would trivially exact-match tier 1 and
    mislabel a keyword-based placement as `mapping_method="annotation"`,
    `confidence="high"` (Task 5 fix-round-1 bug). Instead this calls
    `physiome_organ_map.map_exposure_to_organs` -- the single source of truth
    for physiome organ mapping (its own resolver-annotation / keyword_annotation
    / category / keyword tiers) -- on a reconstructed exposure dict from the
    row's `name` + `provenance.keywords`/`categories`. No CellML text is
    available offline, so the rare real-CellML-RDF-annotation tier is a no-op
    here (as it already is for the vast majority of physiome rows)."""
    prov = row.get("provenance") or {}
    exposure = {
        "name": row.get("name"),
        "keywords": prov.get("keywords") or [],
        "categories": prov.get("categories") or [],
    }
    hra = map_exposure_to_organs(exposure, organ_index, no_llm=True)

    out = dict(row)
    out["organs"] = hra["organs"]
    out["functional_tissue_units"] = hra["functional_tissue_units"]
    out["cell_types"] = hra["cell_types"]
    out["ontology_ids"] = dict(row.get("ontology_ids") or {})
    out["ontology_ids"]["uberon"] = hra.get("uberon_organ_ids", [])
    out["provenance"] = dict(prov)
    out["provenance"]["mapping_method"] = hra.get("mapping_method", "unmapped")
    out["provenance"]["confidence"] = hra.get("confidence", "none")
    return out


def _remap_physionet_row(row: dict, organ_index: dict) -> dict:
    """`remap_row` for physionet -- same rationale as `_remap_physiome_row`:
    `ontology_ids.uberon` is an echoed, already-resolved organ id (`physionet.py`
    `build_entry` writes back `hra.get("uberon_organ_ids", [])`), not a raw
    annotation, so it must not be fed into `resolve_organ_keys` again. Calls
    `physionet_organ_map.map_project_to_organs` -- the source of truth for
    physionet (its own resolver-annotation-then-keyword-title tiers) -- on a
    reconstructed project dict from the row's `name` + `provenance.keywords`.
    That function never returns a `confidence` (neither does the original
    `physionet.py` `build_entry`), so confidence is derived here from
    `mapping_method` via the same table `physiome_organ_map._CONFIDENCE` uses."""
    prov = row.get("provenance") or {}
    project = {"name": row.get("name"), "keywords": prov.get("keywords") or []}
    hra = map_project_to_organs(project, organ_index, no_llm=True)

    out = dict(row)
    out["organs"] = hra["organs"]
    out["functional_tissue_units"] = hra["functional_tissue_units"]
    out["cell_types"] = hra["cell_types"]
    out["ontology_ids"] = dict(row.get("ontology_ids") or {})
    out["ontology_ids"]["uberon"] = hra.get("uberon_organ_ids", [])
    method = hra.get("mapping_method", "unmapped")
    out["provenance"] = dict(prov)
    out["provenance"]["mapping_method"] = method
    out["provenance"]["confidence"] = _METHOD_CONFIDENCE.get(method, "none")
    return out


_REMAPPERS = {"physiome": _remap_physiome_row, "physionet": _remap_physionet_row}


def remap_row(row: dict, organ_index: dict) -> dict:
    """Recompute `organs`/`functional_tissue_units`/`cell_types`/
    `ontology_ids.uberon`/`provenance.mapping_method`/`provenance.confidence`
    for one model_hra_map row. No network. Deterministic: same input -> same
    output. Returns a new row dict (the input `row` is not mutated); every
    other field is carried over unchanged.

    Source-aware (Task 5 fix-round-1): only BioModels rows carry genuine raw
    ontology annotation in `ontology_ids`/`gene_symbols`, so only those go
    through `anatomy_resolver.resolve_organ_keys` directly
    (`_remap_annotation_row`). Physiome/PhysioNet rows' `ontology_ids.uberon`
    is an ECHO of their own keyword/category mapper's prior result, not a raw
    annotation -- feeding it back into the resolver would trivially exact-match
    and mislabel a keyword-based placement as high-confidence "annotation".
    Those two sources are instead re-mapped by calling their own single
    source of truth (`physiome_organ_map.map_exposure_to_organs` /
    `physionet_organ_map.map_project_to_organs`, `_remap_physiome_row` /
    `_remap_physionet_row`), which already contain a
    resolver-annotation-first-then-keyword path (Task 4)."""
    fn = _REMAPPERS.get(row.get("repository"), _remap_annotation_row)
    return fn(row, organ_index)


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
