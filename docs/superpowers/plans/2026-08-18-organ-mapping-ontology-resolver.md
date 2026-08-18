# Ontology-Grounded Organ-Mapping Resolver — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Place far more of the 1,833 unplaced models by resolving anatomy annotations (UBERON/CL/BTO/FMA/MeSH + ASCT+B genes) to HRA organs through the ontology (hierarchy roll-up + crosswalks), instead of exact organ-UBERON-id matching.

**Architecture:** A single `anatomy_resolver.resolve_organs()` maps any annotation to a reference organ via tiers (organ-level UBERON → UBERON roll-up → BTO/FMA/MeSH crosswalk → CL → keyword/name → ASCT+B gene). Roll-up/crosswalk data is generated once from ASCT+B + Ubergraph/OLS and committed as JSON (offline/deterministic build). Every source's `build_entry` calls the resolver; the committed DB is re-mapped (no re-harvest) and the atlas regenerated.

**Tech Stack:** Python 3.12, `requests` (generation only), `process_bigraph`, pytest.

**Spec:** `docs/superpowers/specs/2026-08-18-organ-mapping-ontology-resolver-design.md`

## Global Constraints

- Run tests with `.venv/bin/python -m pytest ...` from the worktree cwd (bare `python` lacks deps).
- The atlas BUILD stays offline/deterministic: the resolver and remap do **no network**; only `scripts/build_anatomy_crosswalks.py` hits the network, and its output is committed. Offline tests inject datasets via keyword args; live calls are `@pytest.mark.network`.
- Never hardcode UBERON ids in logic — map ontology ids to `organ_index` **keys** (resolved to UBERON via the index). A key absent from the reference set contributes nothing.
- Preserve existing behavior: FTU/subregion/cell-type derivation via `hra_mapping`/`hra_pop` is unchanged; per-source keyword/category tables stay as the fallback tier.
- The 3 known pre-existing offline failures (`test_atlas_pack::test_every_organ_has_a_known_system`, `test_atlas_viewer_assets::test_viewer_has_multiselect_menu`, `test_workbench_atlas_viewer::test_atlas_viewer_requires_observables`) are unrelated — do not touch them; "green" means only those remain.
- Commit after each task with `git -c commit.gpgsign=false commit` ending in `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`. Worktree: `~/code/viva-human-atlas--organ-mapping`, branch `feat/organ-mapping-ontology-resolver`.
- ASCT+B organ keys differ from `organ_index` keys — normalize via `ASCTB_ORGAN_ALIAS` (below): `large-intestine`/`small-intestine`→`intestine`, `eye`→`eye-female-left`, `ovary`→`ovary-female-left`; keys with no `organ_index` match (bone-marrow, skeleton, knee, muscular-system, …) contribute nothing.

---

### Task 1: `anatomy_resolver` — annotation tiers (no genes yet)

**Files:**
- Create: `viva_human_atlas/anatomy_resolver.py`
- Test: `tests/test_anatomy_resolver.py`

**Interfaces:**
- Produces:
  - `resolve_organ_keys(organ_index, *, uberon=(), cl=(), fma=(), bto=(), mesh=(), rollup=None, cl_map=None, bto_map=None, mesh_map=None, fma_map=None) -> tuple[list[str], str]` — returns `(organ_keys, method)` where `method` ∈ `{"annotation","annotation_rollup","crosswalk","cell_type",""}`. Datasets default to module-level loaders; injectable for tests.
  - `_CONFIDENCE = {"annotation":"high","annotation_rollup":"high","crosswalk":"medium","cell_type":"medium","keyword":"medium","gene_asctb":"low"}`.
  - module-level cached loaders `load_rollup()`, `load_cl_map()`, `load_fma_map()` reading `datasets/uberon_organ_rollup.json`, `datasets/cl_organ_map.json`, `datasets/fma_uberon_crosswalk.json` (return `{}` if absent).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_anatomy_resolver.py
from viva_human_atlas import anatomy_resolver as ar
from viva_human_atlas.biomodel_do import build_organ_index

ORGAN_INDEX = build_organ_index()
# organ-level reference UBERONs (from the index) for the exact-match tier:
KIDNEY_UB = ORGAN_INDEX["kidney"]["uberon"]      # UBERON:0004538
BRAIN_UB = ORGAN_INDEX["brain"]["uberon"]        # UBERON:0000955

ROLLUP = {                     # non-organ / synonym UBERON -> organ_index key(s)
    "UBERON:0000956": ["brain"],      # cerebral cortex
    "UBERON:0001285": ["kidney"],     # nephron
    "UBERON:0002113": ["kidney"],     # kidney (synonym id != reference id)
    "UBERON:0001155": ["intestine"],  # colon
}
CL_MAP = {"CL:0000499": ["kidney"]}   # stromal cell (kidney AS)
BTO_MAP = {"BTO:0000759": "UBERON:0002113"}   # -> rolls up to kidney
FMA_MAP = {"FMA:7203": "UBERON:0002113"}


def test_organ_level_uberon_exact():
    keys, method = ar.resolve_organ_keys(ORGAN_INDEX, uberon=[KIDNEY_UB], rollup={})
    assert keys == ["kidney"] and method == "annotation"


def test_uberon_rollup_nonorgan_and_synonym():
    keys, m = ar.resolve_organ_keys(ORGAN_INDEX, uberon=["UBERON:0000956"], rollup=ROLLUP)
    assert keys == ["brain"] and m == "annotation_rollup"
    # synonym id resolves to the same organ as the reference id
    keys2, _ = ar.resolve_organ_keys(ORGAN_INDEX, uberon=["UBERON:0002113"], rollup=ROLLUP)
    assert keys2 == ["kidney"]


def test_bto_and_fma_crosswalk_then_rollup():
    keys, m = ar.resolve_organ_keys(ORGAN_INDEX, bto=["BTO:0000759"], rollup=ROLLUP, bto_map=BTO_MAP)
    assert keys == ["kidney"] and m == "crosswalk"
    keys2, m2 = ar.resolve_organ_keys(ORGAN_INDEX, fma=["FMA:7203"], rollup=ROLLUP, fma_map=FMA_MAP)
    assert keys2 == ["kidney"] and m2 == "crosswalk"


def test_cl_celltype_maps_to_organ():
    keys, m = ar.resolve_organ_keys(ORGAN_INDEX, cl=["CL:0000499"], rollup={}, cl_map=CL_MAP)
    assert keys == ["kidney"] and m == "cell_type"


def test_precedence_annotation_beats_rollup_beats_crosswalk_beats_cl():
    # organ-level uberon wins over everything
    keys, m = ar.resolve_organ_keys(ORGAN_INDEX, uberon=[BRAIN_UB, "UBERON:0001285"],
                                    cl=["CL:0000499"], rollup=ROLLUP, cl_map=CL_MAP)
    assert m == "annotation" and "brain" in keys


def test_unmapped_returns_empty():
    keys, m = ar.resolve_organ_keys(ORGAN_INDEX, uberon=["UBERON:9999999"], rollup=ROLLUP)
    assert keys == [] and m == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_anatomy_resolver.py -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Write minimal implementation**

```python
# viva_human_atlas/anatomy_resolver.py
"""Resolve a model's anatomy annotations to HRA reference organ_index keys via
the ontology: organ-level UBERON, UBERON hierarchy roll-up, BTO/FMA/MeSH
crosswalks, and CL cell-types. Deterministic; datasets are generated once by
scripts/build_anatomy_crosswalks.py and committed. See the design spec."""
from __future__ import annotations

import json
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
                       rollup=None, cl_map=None, bto_map=None, mesh_map=None,
                       fma_map=None) -> tuple[list[str], str]:
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

    return [], ""
```

Note: `crosswalk_mesh_labels` takes MeSH *labels*; if callers hold MeSH ids, mesh handling is a no-op here (BioModels passes labels via its existing pipeline — see Task 4). Keep the `mesh` param but the id-vs-label detail is resolved at integration.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_anatomy_resolver.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add viva_human_atlas/anatomy_resolver.py tests/test_anatomy_resolver.py
git -c commit.gpgsign=false commit -m "feat(mapping): anatomy_resolver annotation tiers (uberon/rollup/crosswalk/cl)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: gene tier (ASCT+B biomarkers, specificity-gated)

**Files:**
- Modify: `viva_human_atlas/anatomy_resolver.py`
- Test: `tests/test_anatomy_resolver.py` (append)

**Interfaces:**
- Consumes: `datasets/gene_organ_map.json` = `{GENE_SYMBOL_UPPER: {organ_key: n_celltypes}}`.
- Produces:
  - `load_gene_map()` (cached loader).
  - `normalize_gene(sym) -> str` — uppercase, strip a trailing `-<alnum>` suffix (SBML names like `cdk1-a` → `CDK1`).
  - `resolve_organ_keys(...)` gains `gene_symbols=()`, `gene_map=None`; adds tier 5 (gene) AFTER the annotation tiers, returning method `"gene_asctb"`. Specificity gate: collect organ→count across all genes' matched organs; place only the organ(s) with the max count, and only if a single organ dominates (max count strictly greater than the runner-up, i.e. no pan-organ tie). Return `[]` if genes map to ≥3 organs with no dominant one.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_anatomy_resolver.py
GENE_MAP = {
    "FOXD1": {"kidney": 2}, "PECAM1": {"kidney": 1, "heart": 1, "lung": 1, "blood": 1},
    "NPHS1": {"kidney": 3},
}

def test_gene_specific_places():
    keys, m = ar.resolve_organ_keys(ORGAN_INDEX, gene_symbols=["foxd1", "nphs1-a"],
                                    rollup={}, gene_map=GENE_MAP)
    assert keys == ["kidney"] and m == "gene_asctb"

def test_gene_panorgan_does_not_place():
    keys, m = ar.resolve_organ_keys(ORGAN_INDEX, gene_symbols=["PECAM1"],
                                    rollup={}, gene_map=GENE_MAP)
    assert keys == [] and m == ""

def test_annotation_beats_gene():
    keys, m = ar.resolve_organ_keys(ORGAN_INDEX, uberon=[BRAIN_UB], gene_symbols=["NPHS1"],
                                    rollup={}, gene_map=GENE_MAP)
    assert m == "annotation" and keys == ["brain"]

def test_normalize_gene():
    assert ar.normalize_gene("cdk1-a") == "CDK1" and ar.normalize_gene("FoxD1") == "FOXD1"
```

- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_anatomy_resolver.py -k gene -v` → FAIL.

- [ ] **Step 3: Implement** — add to `anatomy_resolver.py`:

```python
import re
_GENE = None
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
```

Then in `resolve_organ_keys`, add the `gene_symbols=()`/`gene_map=None` params and, after the CL tier returns nothing:

```python
    gene_map = load_gene_map() if gene_map is None else gene_map
    g_organs = _gene_organs(gene_symbols, gene_map)
    if g_organs:
        return g_organs, "gene_asctb"
    return [], ""
```

- [ ] **Step 4: Run** `.venv/bin/python -m pytest tests/test_anatomy_resolver.py -v` → PASS (all).

- [ ] **Step 5: Commit** (`feat(mapping): ASCT+B gene tier with specificity gate`).

---

### Task 3: `scripts/build_anatomy_crosswalks.py` — generate + commit datasets

**Files:**
- Create: `scripts/build_anatomy_crosswalks.py`
- Create (committed output): `datasets/uberon_organ_rollup.json`, `datasets/cl_organ_map.json`, `datasets/gene_organ_map.json`, `datasets/fma_uberon_crosswalk.json`
- Test: `tests/test_build_anatomy_crosswalks.py`

**Interfaces:**
- Produces functions (all pure/injectable so they test offline):
  - `rollup_from_asctb(asctb: dict, organ_index: dict) -> dict[str, list[str]]` — for each ASCT+B organ, map every UBERON in its `anatomical_structures` chains to the normalized `organ_index` key (via `ASCTB_ORGAN_ALIAS` + `biomodel_do._match_organ_key`); skip organs with no `organ_index` match.
  - `cl_map_from_asctb(asctb, organ_index) -> dict[str, list[str]]` — CL id → organ key(s) from `cell_types`.
  - `gene_map_from_asctb(asctb, organ_index) -> dict[str, dict[str,int]]` — `biomarkers_gene` label → `{organ_key: n_celltypes}` (count rows).
  - `ASCTB_ORGAN_ALIAS = {"large-intestine":"intestine","small-intestine":"intestine","eye":"eye-female-left","ovary":"ovary-female-left"}`.
  - `uberon_ancestors_rollup(uberon_ids, organ_index, *, _get=requests.get) -> dict` — for corpus UBERONs not covered by ASCT+B, query Ubergraph for `rdfs:subClassOf*`/`part_of*` ancestors and map to an organ key if an ancestor is an organ-level reference UBERON (network; `@pytest.mark.network`).
  - `main()` — load `asctb_tables.json` + corpus CURIEs from `model_hra_map.json`, build all four datasets (ASCT+B first, hierarchy for the uncovered UBERON/FMA tail), write them, print a diff summary.

Ubergraph query (in `uberon_ancestors_rollup`), POST to `https://ubergraph.apps.renci.org/sparql` with `Accept: application/sparql-results+json`:
```sparql
SELECT ?term ?ancestor WHERE {
  VALUES ?term { obo:UBERON_0000956 obo:UBERON_0001285 ... }
  ?term (rdfs:subClassOf|<http://purl.obolibrary.org/obo/BFO_0000050>)* ?ancestor .
}
```
Map `?ancestor` (as `UBERON:xxxx`) to an organ key when it equals a reference organ-level UBERON; take the most specific (nearest) organ ancestor per term. FMA→UBERON via Ubergraph `oboInOwl:hasDbXref` / equivalent-class over corpus FMA ids.

- [ ] **Step 1: Write the failing test** (offline, fixture ASCT+B):

```python
# tests/test_build_anatomy_crosswalks.py
from viva_human_atlas import build_anatomy_crosswalks as b  # scripts/ on path via conftest or importlib
from viva_human_atlas.biomodel_do import build_organ_index
OI = build_organ_index()
ASCTB = {
  "large-intestine": [{"anatomical_structures": [{"id":"UBERON:0000059"},{"id":"UBERON:0001155"}],
                       "cell_types":[{"id":"CL:0011108"}], "biomarkers_gene":[{"id":"HGNC:1","label":"CDX2"}]}],
  "kidney": [{"anatomical_structures":[{"id":"UBERON:0002113"},{"id":"UBERON:0001285"}],
              "cell_types":[{"id":"CL:0000499"}], "biomarkers_gene":[{"id":"HGNC:2","label":"NPHS1"}]}],
  "bone-marrow": [{"anatomical_structures":[{"id":"UBERON:0002371"}], "cell_types":[], "biomarkers_gene":[]}],
}

def test_rollup_from_asctb_normalizes_organ_keys():
    r = b.rollup_from_asctb(ASCTB, OI)
    assert r["UBERON:0001155"] == ["intestine"]   # large-intestine -> intestine
    assert r["UBERON:0002113"] == ["kidney"]        # kidney synonym id
    assert "UBERON:0002371" not in r                # bone-marrow: no organ_index key

def test_cl_and_gene_maps():
    assert b.cl_map_from_asctb(ASCTB, OI)["CL:0000499"] == ["kidney"]
    g = b.gene_map_from_asctb(ASCTB, OI)
    assert g["NPHS1"] == {"kidney": 1} and "CDX2" in g
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** the pure functions + `main()` + the network `uberon_ancestors_rollup`. **Step 4: Run** the offline tests → PASS.

- [ ] **Step 5: Generate the real datasets (network)**

```bash
.venv/bin/python scripts/build_anatomy_crosswalks.py
```
Inspect the printed summary (counts per dataset; how many corpus UBERON/FMA the hierarchy step resolved). Sanity-check a few entries by hand (cerebral cortex→brain, nephron→kidney, colon→intestine).

- [ ] **Step 6: Commit** the script + tests + generated datasets (`feat(mapping): generate committed anatomy crosswalk/rollup datasets`).

---

### Task 4: Integration — route every source through the resolver

**Files:**
- Modify: `viva_human_atlas/hra_mapping.py`, `viva_human_atlas/biomodel_hra.py`, `viva_human_atlas/physiome_organ_map.py`, `viva_human_atlas/physionet_organ_map.py`
- Test: `tests/` (extend existing per-source tests)

**Interfaces:**
- Consumes Tasks 1–3.
- `hra_mapping.map_to_hra(uberon_ids, name, organ_index, *, ftus=None)` unchanged signature: internally, organ resolution = union of (a) `anatomy_resolver.resolve_organ_keys(organ_index, uberon=uberon_ids)` and (b) the existing name-synonym `_match_organ_key(name)`; FTU/cell-type derivation from the resulting organ keys is unchanged.
- `biomodel_hra.build_entry`: after crosswalking, call `resolve_organ_keys(organ_index, uberon=ont_uberon, cl=ids["cl"], fma=ids["fma"], bto=ids["bto"], mesh=mesh_labels, gene_symbols=ids.get("genes") or entry gene_symbols)`; union with name-synonym; set `provenance.mapping_method`/`confidence` from the resolver's method (falling back to existing name/keyword method when the resolver is empty).
- `physiome_organ_map.map_exposure_to_organs` / `physionet_organ_map`: prepend `resolve_organ_keys` on any annotation ids the exposure carries (usually none), THEN fall through to the existing category/keyword tiers (unchanged); replace `physiome_organ_map.FMA_TO_UBERON` usage with `anatomy_resolver.load_fma_map()`.

- [ ] **Step 1: Write failing integration tests** — (a) `map_to_hra` now maps a non-organ UBERON (e.g. `UBERON:0000956`→brain) given an injected rollup or the committed dataset; (b) a `biomodel_hra.build_entry` fixture with only a non-organ UBERON now returns non-empty `organs` with `mapping_method == "annotation_rollup"`; (c) existing physiome/physionet keyword tests still pass unchanged. Provide concrete fixtures mirroring `tests/test_physiome_organ_map.py` style.

- [ ] **Step 2–4:** Run (fail) → implement the delegations (keep each function's public signature; add resolver calls; preserve keyword/category fallbacks and FTU logic) → run.

- [ ] **Step 5: Full offline suite**

Run: `.venv/bin/python -m pytest -m "not network" -q`
Expected: green except the 3 known pre-existing failures. Fix any fallout by updating callers to the new internal behavior — do not weaken assertions.

- [ ] **Step 6: Commit** (`feat(mapping): route all sources through anatomy_resolver`).

---

### Task 5: Re-map the corpus, regenerate the atlas, measure lift

**Files:**
- Create: `scripts/remap_organs.py`
- Modify (data artifacts): `datasets/model_hra_map.json`, `studies/hra-atlas-browser/viz/atlas/atlas.json`
- Test: `tests/test_remap_organs.py`

**Interfaces:**
- `remap_row(row, organ_index) -> row` — recompute `organs`/`functional_tissue_units`/`cell_types`/`ontology_ids.uberon`(organ ids)/`provenance.mapping_method`/`provenance.confidence` from the row's existing `ontology_ids.{uberon,cl,fma,bto,mesh}` + `gene_symbols` + `name` + `provenance.keywords` via `resolve_organ_keys` + `map_to_hra` (for FTU/cell types). No network.
- `main()` — load DB, remap every row, write DB, print per-source placed before/after + per-method histogram.

- [ ] **Step 1: Write the failing test** — `remap_row` places a row that has only a non-organ UBERON (using the committed rollup), and leaves an unmappable row empty. Assert deterministic (two calls identical).

- [ ] **Step 2–4:** fail → implement → pass.

- [ ] **Step 5: Run the remap + regenerate atlas**

```bash
.venv/bin/python scripts/remap_organs.py            # rewrites datasets/model_hra_map.json
.venv/bin/python -c "
import json
from collections import Counter
rows=json.load(open('datasets/model_hra_map.json'))
for s in ['biomodels','physiome','physionet']:
    S=[r for r in rows if r['repository']==s]
    print(s,'placed', sum(1 for r in S if r['organs']),'/',len(S))
print('methods', Counter((r['provenance'] or {}).get('mapping_method') for r in rows if r['repository']=='biomodels'))
"
.venv/bin/python scripts/build_atlas_pack.py         # regenerate atlas.json
```
Report the placement lift (before: 264 biomodels / 341 physiome / 124 physionet placed) and the new atlas `summary.n_models_distinct`.

- [ ] **Step 6: Reconcile count-hardcoded tests** — the corpus placement counts change, so `test_organ_select`, `test_biomodel_hra_step::test_step_summary_matches_committed_corpus_db`, `test_atlas_subregions` (n_models_distinct), `test_atlas_pipeline_composite` will drift. Regenerate/update their literals to the new computed values (exact `==`, not weakened), as in the physiome-harvest PR. Re-run `pytest -m "not network"` → only the 3 pre-existing failures remain.

- [ ] **Step 7: Commit** the scripts + tests + regenerated `model_hra_map.json` + `atlas.json` + test updates (`feat(atlas): re-map corpus via ontology resolver + regenerate atlas`).

---

### Task 6: PR + publish (user-gated)

- [ ] Push branch, open PR summarizing the placement lift per source + per method.
- [ ] Do NOT merge (user approves). Publish the dashboard to gh-pages only on request (local build + manual gh-pages push, per repo flow).

---

## Self-Review

- **Spec coverage:** resolver tiers → T1/T2; generated datasets → T3; integration → T4; remap+atlas+measure → T5; publish → T6. Genes-via-ASCT+B (D3) → T2. Offline/deterministic (D2) → resolver/remap no-network, generation committed. All covered.
- **Placeholder scan:** Task 3's Ubergraph SPARQL and Task 4's integration fixtures are described with concrete endpoints/behavior; the exact SPARQL string + fixture bodies are written during implementation from the given shapes — acceptable for a network-generation script and mirror-existing-test tasks. No logic placeholders.
- **Type consistency:** `resolve_organ_keys` signature + return `(list[str], str)` consistent across T1/T2/T4/T5; dataset filenames consistent (`uberon_organ_rollup.json`, `cl_organ_map.json`, `gene_organ_map.json`, `fma_uberon_crosswalk.json`); ASCT+B alias handling consistent T3↔global-constraints.
- **Known risk:** physiome/physionet gain little (no annotations) — the lift is BioModels-dominated, as the spec states; not a defect.
