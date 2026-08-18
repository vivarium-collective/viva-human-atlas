#!/usr/bin/env python
"""Build the committed anatomy crosswalk/rollup datasets consumed by
`viva_human_atlas.anatomy_resolver`:

- `datasets/uberon_organ_rollup.json`   `{UBERON curie: [organ_key, ...]}`
- `datasets/cl_organ_map.json`          `{CL curie: [organ_key, ...]}`
- `datasets/gene_organ_map.json`        `{GENE_SYMBOL: {organ_key: n_rows}}`
- `datasets/fma_uberon_crosswalk.json`  `{FMA curie: UBERON curie}`

Two stages:

1. **ASCT+B (offline, deterministic).** Parse the committed
   `datasets/asctb_tables.json` (per-organ lists of cell-type rows, each with
   `anatomical_structures` (UBERON chain), `cell_types` (CL), and
   `biomarkers_gene` (`{"id": HGNC, "label": SYMBOL}`)). ASCT+B organ keys
   don't line up with `organ_index` keys 1:1 -- normalize via
   `ASCTB_ORGAN_ALIAS` then a direct membership check against `organ_index`.
   Organs with no `organ_index` match (bone-marrow, skeleton, knee,
   muscular-system, palatine-tonsil, blood-vasculature, lymph-vasculature,
   anatomical-systems, peripheral-nervous-system) contribute nothing.

2. **Ubergraph hierarchy roll-up (network, additive).** For the corpus
   UBERON/FMA CURIEs referenced in `datasets/model_hra_map.json` that the
   ASCT+B rollup doesn't already cover, query Ubergraph's public SPARQL
   endpoint for `rdfs:subClassOf|part_of` ancestors and roll them up to the
   nearest organ-level reference UBERON (`uberon_ancestors_rollup`); FMA ids
   are crossed to UBERON via `oboInOwl:hasDbXref` (`fma_to_uberon`).
   Best-effort: if Ubergraph is unreachable, `main()` still writes the
   ASCT+B-only datasets and reports the failure -- the atlas build itself
   stays fully offline/deterministic (only this script touches the network).

Run with: ``.venv/bin/python scripts/build_anatomy_crosswalks.py``.
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from viva_human_atlas.coverage import load_corpus_catalog

DATASETS = REPO_ROOT / "datasets"
ASCTB_PATH = DATASETS / "asctb_tables.json"
MODEL_HRA_MAP_PATH = DATASETS / "model_hra_map.json"

ROLLUP_OUT = DATASETS / "uberon_organ_rollup.json"
CL_OUT = DATASETS / "cl_organ_map.json"
GENE_OUT = DATASETS / "gene_organ_map.json"
FMA_OUT = DATASETS / "fma_uberon_crosswalk.json"

UBERGRAPH_URL = "https://ubergraph.apps.renci.org/sparql"
_ACCEPT = {"Accept": "application/sparql-results+json"}

ASCTB_ORGAN_ALIAS = {
    "large-intestine": "intestine",
    "small-intestine": "intestine",
    "eye": "eye-female-left",
    "ovary": "ovary-female-left",
}

# organ_index["blood"]'s reference term is UBERON:0004537 "blood vasculature" --
# the whole-body circulatory tree, not a placeable organ compartment. It's a
# part_of/subClassOf ancestor of nearly every named artery/vein in the corpus
# (radial artery, buccal artery, uterine artery, ...), so letting the hierarchy
# step match against it turns vessel containment into a near-universal false
# "blood" hit. Exclude it from the reference-organ set the hierarchy step
# matches against; "blood" stays reachable via direct annotation (resolver
# tier 1), just not via vessel-containment rollup.
_HIERARCHY_EXCLUDED_ORGAN_KEYS = {"blood"}

# Strip a leading/trailing sex/side qualifier from an ontology label so
# "left kidney" and "kidney" (or "right ovary" / "ovary") compare equal --
# HRA reference organs are frequently a *sided* Uberon term (e.g. "left
# kidney") while the corpus/hierarchy uses the generic term ("kidney").
_SIDE_RE = re.compile(r"^(?:left|right|male|female)\s+|\s+(?:left|right|male|female)$")


def _base_label(label: Optional[str]) -> str:
    return _SIDE_RE.sub("", (label or "").strip().lower()).strip()


def _organ_key_for_asctb(asctb_key: str, organ_index: dict) -> Optional[str]:
    """Normalize an ASCT+B organ key to an `organ_index` key, or None if no
    reference organ matches (the ASCT+B organ contributes nothing).

    Alias first (`ASCTB_ORGAN_ALIAS`), then require the normalized name to be
    a direct `organ_index` member. `biomodel_do._match_organ_key`'s substring
    synonym match is deliberately NOT used as a further fallback here: it
    would (correctly, by its own rules) match "blood-vasculature" -> "blood",
    which conflicts with the verified ground truth that blood-vasculature
    (the vasculature graph, not the blood organ) contributes nothing. Direct
    membership after aliasing reproduces every verified case (17 organs
    match, 9 contribute nothing) without that false positive.
    """
    norm = ASCTB_ORGAN_ALIAS.get(asctb_key, asctb_key)
    if norm in organ_index:
        return norm
    return None


def rollup_from_asctb(asctb: dict, organ_index: dict) -> dict:
    """`{UBERON curie: [organ_key, ...]}` from every ASCT+B
    `anatomical_structures` UBERON id, for organs that normalize to an
    `organ_index` key."""
    out: dict = {}
    for asctb_key, rows in asctb.items():
        organ_key = _organ_key_for_asctb(asctb_key, organ_index)
        if organ_key is None:
            continue
        for row in rows:
            for struct in row.get("anatomical_structures") or []:
                uberon = struct.get("id")
                if not uberon or not uberon.startswith("UBERON:"):
                    continue
                organs = out.setdefault(uberon, [])
                if organ_key not in organs:
                    organs.append(organ_key)
    return out


def cl_map_from_asctb(asctb: dict, organ_index: dict) -> dict:
    """`{CL curie: [organ_key, ...]}` from every ASCT+B `cell_types` id."""
    out: dict = {}
    for asctb_key, rows in asctb.items():
        organ_key = _organ_key_for_asctb(asctb_key, organ_index)
        if organ_key is None:
            continue
        for row in rows:
            for ct in row.get("cell_types") or []:
                cl_id = ct.get("id")
                if not cl_id or not cl_id.startswith("CL:"):
                    continue
                organs = out.setdefault(cl_id, [])
                if organ_key not in organs:
                    organs.append(organ_key)
    return out


def gene_map_from_asctb(asctb: dict, organ_index: dict) -> dict:
    """`{GENE_SYMBOL: {organ_key: n_rows}}` -- `n_rows` counts ASCT+B
    cell-type rows (not gene mentions) that list the gene for that organ; a
    gene repeated within one row's `biomarkers_gene` counts once."""
    out: dict = {}
    for asctb_key, rows in asctb.items():
        organ_key = _organ_key_for_asctb(asctb_key, organ_index)
        if organ_key is None:
            continue
        for row in rows:
            genes = row.get("biomarkers_gene") or []
            if not genes:
                continue
            seen = set()
            for g in genes:
                label = (g.get("label") or "").strip().upper()
                if not label or label in seen:
                    continue
                seen.add(label)
                counts = out.setdefault(label, {})
                counts[organ_key] = counts.get(organ_key, 0) + 1
    return out


def _iri_to_uberon_curie(uri: str) -> Optional[str]:
    tail = uri.rsplit("/", 1)[-1]
    if tail.startswith("UBERON_"):
        return "UBERON:" + tail.split("_", 1)[1]
    return None


def uberon_ancestors_rollup(uberon_ids, organ_index: dict, *, _post=requests.post) -> dict:
    """Roll up `uberon_ids` (corpus UBERON CURIEs, typically ones the ASCT+B
    rollup doesn't already cover) to `organ_index` keys via Ubergraph's
    public SPARQL endpoint.

    For each term, fetch its full `rdfs:subClassOf|part_of` ancestor closure
    (batched in one POST alongside every `organ_index` reference UBERON, so
    the reference organs' own closures/labels come back in the same
    response). A term resolves via:

    1. **Exact hit** -- an ancestor CURIE literally equals a reference
       organ's `uberon`.
    2. **Label fallback** -- an ancestor's `rdfs:label`, with a leading/
       trailing side/sex qualifier stripped, equals a reference organ's own
       (similarly stripped) label. This is what lets e.g. nephron
       (UBERON:0001285), whose ancestors include the *generic* "kidney"
       (UBERON:0002113), resolve to the `kidney` organ_index key even though
       the HRA reference organ for kidney is the *sided* "left kidney"
       (UBERON:0004538).

    Returns `{uberon_curie: [organ_key, ...]}` for every id that resolved
    (ids with no ontology hit are simply absent). Raises on network/HTTP
    failure -- callers wanting graceful degradation should catch.
    """
    uberon_ids = sorted(set(uberon_ids))
    if not uberon_ids:
        return {}

    organ_ubs = sorted(
        {
            v["uberon"]
            for k, v in organ_index.items()
            if k not in _HIERARCHY_EXCLUDED_ORGAN_KEYS and (v.get("uberon") or "").startswith("UBERON:")
        }
    )
    all_terms = sorted(set(uberon_ids) | set(organ_ubs))
    values = " ".join("obo:" + t.replace("UBERON:", "UBERON_") for t in all_terms)
    query = f"""
PREFIX obo: <http://purl.obolibrary.org/obo/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?term ?ancestor ?label WHERE {{
  VALUES ?term {{ {values} }}
  ?term (rdfs:subClassOf|<http://purl.obolibrary.org/obo/BFO_0000050>)* ?ancestor .
  FILTER(isIRI(?ancestor))
  OPTIONAL {{ ?ancestor rdfs:label ?label }}
}}
"""
    resp = _post(UBERGRAPH_URL, data={"query": query}, headers=_ACCEPT, timeout=120)
    resp.raise_for_status()
    bindings = resp.json()["results"]["bindings"]

    closures: dict = defaultdict(dict)  # term_curie -> {ancestor_curie_or_iri: label}
    for b in bindings:
        term = _iri_to_uberon_curie(b["term"]["value"])
        if term is None:
            continue
        anc_uri = b["ancestor"]["value"]
        anc = _iri_to_uberon_curie(anc_uri) or anc_uri
        label = (b.get("label") or {}).get("value")
        if label or anc not in closures[term]:
            closures[term][anc] = label

    # exact reference-uberon -> organ_key(s) (blood excluded -- see
    # _HIERARCHY_EXCLUDED_ORGAN_KEYS above)
    exact_index: dict = defaultdict(list)
    for k, v in organ_index.items():
        if k in _HIERARCHY_EXCLUDED_ORGAN_KEYS:
            continue
        u = v.get("uberon")
        if u and u.startswith("UBERON:"):
            exact_index[u].append(k)

    # base-label (side-stripped) -> organ_key(s), from each reference
    # uberon's own label (its self-loop row in the same closure).
    label_index: dict = defaultdict(list)
    for organ_ub, organ_keys in exact_index.items():
        own_label = closures.get(organ_ub, {}).get(organ_ub)
        if own_label:
            for k in organ_keys:
                if k not in label_index[_base_label(own_label)]:
                    label_index[_base_label(own_label)].append(k)

    out: dict = {}
    for term in uberon_ids:
        closure = closures.get(term)
        if not closure:
            continue

        exact_hits: list = []
        for anc in closure:
            for k in exact_index.get(anc, []):
                if k not in exact_hits:
                    exact_hits.append(k)
        if exact_hits:
            out[term] = sorted(exact_hits)  # SPARQL binding order isn't stable
            continue

        label_hits: list = []
        for anc, label in closure.items():
            if not label:
                continue
            for k in label_index.get(_base_label(label), []):
                if k not in label_hits:
                    label_hits.append(k)
        if label_hits:
            out[term] = sorted(label_hits)  # SPARQL binding order isn't stable

    return out


def fma_to_uberon(fma_ids, *, _post=requests.post) -> dict:
    """`{FMA curie: UBERON curie}` for corpus FMA ids that Ubergraph carries
    an `oboInOwl:hasDbXref` from some UBERON class to (deterministic:
    lexicographically-smallest UBERON wins on multi-hit). Raises on network/
    HTTP failure -- callers wanting graceful degradation should catch."""
    fma_ids = sorted(set(fma_ids))
    if not fma_ids:
        return {}

    values = " ".join(f'"{f}"^^xsd:string' for f in fma_ids)
    query = f"""
PREFIX oboInOwl: <http://www.geneontology.org/formats/oboInOwl#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
SELECT ?uberon ?xref WHERE {{
  VALUES ?xref {{ {values} }}
  ?uberon oboInOwl:hasDbXref ?xref .
  FILTER(isIRI(?uberon))
}}
"""
    resp = _post(UBERGRAPH_URL, data={"query": query}, headers=_ACCEPT, timeout=90)
    resp.raise_for_status()
    bindings = resp.json()["results"]["bindings"]

    candidates: dict = defaultdict(list)
    for b in bindings:
        uberon = _iri_to_uberon_curie(b["uberon"]["value"])
        if uberon is None:
            continue
        candidates[b["xref"]["value"]].append(uberon)

    return {fma: sorted(ubs)[0] for fma, ubs in candidates.items()}


def _corpus_ontology_ids(model_hra_map: list) -> tuple:
    uberon, fma = set(), set()
    for entry in model_hra_map:
        oids = entry.get("ontology_ids") or {}
        uberon.update(oids.get("uberon") or [])
        fma.update(oids.get("fma") or [])
    return sorted(uberon), sorted(fma)


def main() -> None:
    organ_index = load_corpus_catalog()["organ_index"]
    print(f"Loaded organ_index: {len(organ_index)} organs")

    asctb = json.loads(ASCTB_PATH.read_text(encoding="utf-8"))
    n_rows = sum(len(v) for v in asctb.values())
    print(f"Loaded ASCT+B tables: {len(asctb)} organs, {n_rows} rows ({ASCTB_PATH})")

    asctb_rollup = rollup_from_asctb(asctb, organ_index)
    cl_map = cl_map_from_asctb(asctb, organ_index)
    gene_map = gene_map_from_asctb(asctb, organ_index)
    matched_organs = sorted({k for organs in asctb_rollup.values() for k in organs})
    print(f"ASCT+B rollup: {len(asctb_rollup)} UBERON -> organ ({len(matched_organs)} organs matched)")
    print(f"ASCT+B CL map: {len(cl_map)} CL -> organ")
    print(f"ASCT+B gene map: {len(gene_map)} gene symbols")

    model_hra_map = json.loads(MODEL_HRA_MAP_PATH.read_text(encoding="utf-8"))
    corpus_uberon, corpus_fma = _corpus_ontology_ids(model_hra_map)
    print(
        f"Corpus ({MODEL_HRA_MAP_PATH.name}): {len(model_hra_map)} models, "
        f"{len(corpus_uberon)} distinct UBERON ids, {len(corpus_fma)} distinct FMA ids"
    )

    uncovered_uberon = sorted(set(corpus_uberon) - set(asctb_rollup))

    # Each network step is isolated so a failure in one doesn't misreport the
    # other as skipped (degrade gracefully per-step, not all-or-nothing).
    hierarchy_rollup: dict = {}
    fma_crosswalk: dict = {}
    uberon_ok = True
    fma_ok = True
    try:
        hierarchy_rollup = uberon_ancestors_rollup(uncovered_uberon, organ_index)
    except Exception as exc:  # network unreachable / SPARQL failure: degrade gracefully
        uberon_ok = False
        print(f"WARNING: Ubergraph hierarchy roll-up failed ({exc!r}); "
              f"uberon_organ_rollup.json will be ASCT+B-only.")
    try:
        fma_crosswalk = fma_to_uberon(corpus_fma)
    except Exception as exc:  # network unreachable / SPARQL failure: degrade gracefully
        fma_ok = False
        print(f"WARNING: Ubergraph FMA crosswalk failed ({exc!r}); "
              f"fma_uberon_crosswalk.json will be empty.")

    ubergraph_ok = uberon_ok and fma_ok
    print(f"Ubergraph reachable: {ubergraph_ok}"
          + ("" if ubergraph_ok else f" (uberon_ok={uberon_ok}, fma_ok={fma_ok})"))
    print(f"Ubergraph hierarchy roll-up: resolved {len(hierarchy_rollup)}/{len(uncovered_uberon)} "
          f"uncovered corpus UBERON ids")
    print(f"Ubergraph FMA crosswalk: resolved {len(fma_crosswalk)}/{len(corpus_fma)} corpus FMA ids")

    final_rollup = {**hierarchy_rollup, **asctb_rollup}  # ASCT+B wins on overlap (shouldn't overlap)

    DATASETS.mkdir(parents=True, exist_ok=True)
    ROLLUP_OUT.write_text(json.dumps(final_rollup, indent=2, sort_keys=True), encoding="utf-8")
    CL_OUT.write_text(json.dumps(cl_map, indent=2, sort_keys=True), encoding="utf-8")
    GENE_OUT.write_text(json.dumps(gene_map, indent=2, sort_keys=True), encoding="utf-8")
    FMA_OUT.write_text(json.dumps(fma_crosswalk, indent=2, sort_keys=True), encoding="utf-8")

    print(f"Wrote {ROLLUP_OUT} ({len(final_rollup)} entries; {len(asctb_rollup)} ASCT+B + "
          f"{len(hierarchy_rollup)} hierarchy)")
    print(f"Wrote {CL_OUT} ({len(cl_map)} entries)")
    print(f"Wrote {GENE_OUT} ({len(gene_map)} entries)")
    print(f"Wrote {FMA_OUT} ({len(fma_crosswalk)} entries)")


if __name__ == "__main__":
    main()
