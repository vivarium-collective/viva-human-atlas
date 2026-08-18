"""Resolve a model's anatomy annotations to HRA reference organ_index keys via
the ontology: organ-level UBERON, UBERON hierarchy roll-up, BTO/FMA/MeSH
crosswalks, and CL cell-types. Deterministic; datasets are generated once by
scripts/build_anatomy_crosswalks.py and committed. See the design spec."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

_DATASETS = Path(__file__).resolve().parents[1] / "datasets"

_CONFIDENCE = {"annotation": "high", "annotation_rollup": "high",
               "crosswalk": "medium", "cell_type": "medium",
               "keyword": "medium", "gene_asctb": "low"}


def _load(name) -> dict:
    p = _DATASETS / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


_ROLLUP = _CL = _FMA = None  # lazy module caches
_GENE = None


def load_rollup():
    global _ROLLUP
    if _ROLLUP is None: _ROLLUP = _load("uberon_organ_rollup.json")
    return _ROLLUP

def load_cl_map():
    global _CL
    if _CL is None: _CL = _load("cl_organ_map.json")
    return _CL

def load_fma_map():
    global _FMA
    if _FMA is None: _FMA = _load("fma_uberon_crosswalk.json")
    return _FMA

def load_gene_map():
    global _GENE
    if _GENE is None: _GENE = _load("gene_organ_map.json")
    return _GENE


def normalize_gene(sym: str) -> str:
    s = (sym or "").strip().upper()
    return re.sub(r"-[A-Z0-9]+$", "", s)


def _gene_organs(gene_symbols, gene_map) -> list[str]:
    counts = {}
    for g in gene_symbols:
        for organ, n in (gene_map.get(normalize_gene(g)) or {}).items():
            counts[organ] = counts.get(organ, 0) + n
    if not counts:
        return []
    top = max(counts.values())
    winners = [o for o, n in counts.items() if n == top]
    # dominant single organ only (no pan-organ tie)
    return winners if len(winners) == 1 else []


def _organ_uberon_keys(organ_index) -> dict:
    """{organ_level_uberon_id: organ_key} from the reference index."""
    return {e["uberon"]: k for k, e in organ_index.items() if e.get("uberon")}


def _dedup(seq):
    out = []
    for x in seq:
        if x and x not in out:
            out.append(x)
    return out


def resolve_organ_keys(organ_index, *, uberon=(), cl=(), fma=(), bto=(), mesh=(),
                       gene_symbols=(), rollup=None, cl_map=None, bto_map=None,
                       mesh_map=None, fma_map=None, gene_map=None) -> tuple[list[str], str]:
    rollup = load_rollup() if rollup is None else rollup
    cl_map = load_cl_map() if cl_map is None else cl_map
    fma_map = load_fma_map() if fma_map is None else fma_map
    if bto_map is None:
        from viva_human_atlas.anatomy_crosswalk import load_bto_uberon
        bto_map = load_bto_uberon()
    ub_to_organ = _organ_uberon_keys(organ_index)

    def organs_from_uberon(uberons):
        exact, rolled = [], []
        for u in uberons:
            if u in ub_to_organ:
                exact.append(ub_to_organ[u])
            else:
                rolled += rollup.get(u, [])
        return _dedup(exact), _dedup(rolled)

    # tier 1 + 2: UBERON exact, then roll-up
    exact, rolled = organs_from_uberon(uberon)
    if exact:
        return exact, "annotation"
    if rolled:
        return rolled, "annotation_rollup"

    # tier 3: BTO / FMA / MeSH -> UBERON -> exact|rollup
    xwalk_ub = _dedup([bto_map.get(b) for b in bto if bto_map.get(b)]
                      + [fma_map.get(f) for f in fma if fma_map.get(f)])
    if mesh:
        from viva_human_atlas.anatomy_crosswalk import crosswalk_mesh_labels
        xwalk_ub += crosswalk_mesh_labels(mesh).get("uberon", []) if mesh_map is None \
            else crosswalk_mesh_labels(mesh, mesh_map).get("uberon", [])
    xwalk_ub = _dedup(xwalk_ub)
    if xwalk_ub:
        e2, r2 = organs_from_uberon(xwalk_ub)
        if e2 or r2:
            return _dedup(e2 + r2), "crosswalk"

    # tier 4: CL cell-type -> organ
    cl_organs = _dedup([k for c in cl for k in cl_map.get(c, [])])
    if cl_organs:
        return cl_organs, "cell_type"

    # tier 5: ASCT+B gene -> organ, specificity-gated
    gene_map = load_gene_map() if gene_map is None else gene_map
    g_organs = _gene_organs(gene_symbols, gene_map)
    if g_organs:
        return g_organs, "gene_asctb"

    return [], ""
