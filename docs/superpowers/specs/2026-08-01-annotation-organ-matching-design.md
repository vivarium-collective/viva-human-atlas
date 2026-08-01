# Annotation-based organ matching + compelling HRA-integration — design

**Date:** 2026-08-01
**Status:** approved (brainstorming)
**Branch:** `feat/hra-atlas-browser` (Phase 1 grows PR #6)

## Problem

The atlas's model→organ links come only from **name-synonym matching** over
BioModels *titles* (`viva_human_atlas/biomodel_do.py`): 85 organ-links from 82
of 1,096 curated models (~7.5%). Models whose titles don't mention an organ
word are missed even when their SBML clearly annotates the anatomy. We want to
(a) add an **annotation-based matcher** (SBML MIRIAM → Uberon), (b) quantify
**how much more** it covers (organs and models), (c) track **how** models get
organs from annotations, and (d) make the `hra-integration` investigation
compelling and explicitly linked to the Atlas Browser. A later phase surfaces
the viewer as a per-run workbench tool.

## Scope decisions (confirmed)

- **Matcher scope:** full curated corpus (1,096 models), run once over the
  network, commit the annotation-derived catalog — studies then run offline and
  deterministically, and the recall-gain headline is exact.
- **Two studies:** `annotation-organ-matching` (pipeline + provenance) and
  `annotation-recall-gain` (name-synonym vs annotation Δ).
- **Home:** `hra-integration`, reframed around integrating models into the HRA
  atlas; both studies added there.
- **Workbench per-run link:** **no workbench changes.** Analysis tools stay
  workspace-isolated and importable — implemented entirely through the existing
  `workbench_viewers.get_viewers(ws_root)` hook this repo already owns. The
  viewer declares `requires: ["observables"]`, and the stock workbench surfaces
  an "Atlas Browser" link on each run that advertises that (built-in) capability
  (any run with a readable emitted store). Minting a strict HRA-only capability
  tag is the only thing that would need a workbench change, so it is dropped.

## Phase 1 architecture (this repo)

### A. Annotation matcher — `viva_human_atlas/annotation_match.py`
- `fetch_sbml(biomodel_id) -> str`: resolve/cache a model's SBML via
  `biomodels.get_metadata` + `viva_biomodels.run_biomodels.load_biomodel`
  (returns `result.sbml_path`); read the file text.
- `extract_anatomy_curies(sbml_text) -> list[dict]`: parse with **libsbml**
  (`readSBMLFromString`); walk the model element, its `compartments`, and
  `species`; for each `CVTerm` whose qualifier is a biological qualifier in
  `{BQB_IS, BQB_IS_PART_OF, BQB_OCCURS_IN, BQB_HAS_PART, BQB_IS_VERSION_OF}`,
  read each resource URI; keep `urn:miriam:uberon`, `:fma`, `:bto` (and the
  `identifiers.org/obo` equivalents); return
  `[{"curie": "UBERON:0001264", "qualifier": "BQB_OCCURS_IN",
     "element": "compartment:cytosol"}, ...]` (deduped).
- `map_curie_to_organ(curie, organ_index, bto_crosswalk) -> str|None`:
  UBERON/FMA CURIEs match the HRA `organ_index` directly (its keys carry
  UBERON + FMA ids); BTO CURIEs map via a small committed BTO→UBERON crosswalk
  (`datasets/bto_uberon_crosswalk.json`; may be empty initially — BTO support
  is best-effort and flagged in the study).
- `annotate_model(biomodel_id, organ_index, *, sbml_text=None, bto_crosswalk=None)
  -> dict`: returns
  `{"biomodel_id", "organs": [{"organ", "uberon", "via": {curie,qualifier,element}}],
    "provenance": {"annotation": "miriam-match@SBML", "source": "biomodels"}}`.
  `sbml_text` injectable for offline tests.
- `build_annotation_catalog(model_ids, organ_index, *, fetch=fetch_sbml,
  bto_crosswalk=None) -> dict`: returns the SAME shape as the name catalog —
  `{biomodel_dos, organ_index, organ_to_models}` — so it drops straight into the
  existing `coverage`/`atlas_pack` pipeline. Each `biomodel_do` also keeps its
  per-organ `via` provenance. `fetch` injectable for tests.

### B. Build script — `scripts/build_annotation_catalog.py`
Reads the committed corpus catalog's model ids
(`datasets/biomodel_corpus_catalog.json` → `biomodel_dos`), the HRA
`organ_index`, and (optional) BTO crosswalk; runs `build_annotation_catalog`
over all 1,096 models (network — fetches SBML, cached); writes
`datasets/biomodel_annotation_catalog.json` in the committed-catalog envelope
`{n_ids, n_named, n_tagged, catalog}`. Logs a progress counter and a summary
(models parsed, models with ≥1 anatomy CURIE, organs reached). Idempotent;
skips models whose SBML can't be fetched/parsed and records the skip count.

### C. Comparison — `viva_human_atlas/annotation_gain.py`
`compare_catalogs(name_catalog, annotation_catalog) -> dict`:
```python
{"name": {"n_models_tagged": int, "organs": [key...], "n_models_total": int},
 "annotation": {...same...},
 "union": {...same...},
 "delta": {"organs_added": [key...], "n_models_added": int,
           "per_organ": [{"organ", "name_models", "annotation_models",
                          "union_models", "added"}...]},
 "summary": {"pct_corpus_tagged_name": float, "pct_corpus_tagged_annotation": float}}
```
Pure/offline over the two committed catalogs.

### D. Two studies (under `hra-integration`)
- `studies/annotation-organ-matching/study.yaml` + composite generator
  `viva_human_atlas/composites/annotation_composite.py`: an
  `AnnotationMatchStep` loads the committed annotation catalog and emits a
  coverage summary + a sample of per-model provenance traces (qualifier /
  ontology distribution). Study card frames the **mechanism**: how a model gets
  an organ from its SBML annotations, transparently.
- `studies/annotation-recall-gain/study.yaml` + composite generator: a
  `RecallGainStep` runs `compare_catalogs` and emits the deltas. Study card
  frames the **compelling comparison**; `embed_visualizations` points at a
  Plotly figure (per-organ name-vs-annotation-vs-union bars) built by the
  repo's `scripts/build_study_figures.py` / `viva_human_atlas/viz.py`.
- Both studies carry `investigation: hra-integration` and appear in that
  investigation's `studies:` list.

### E. Investigation reframe — `investigations/hra-integration/investigation.yaml`
Rewrite `lead`, `executive.what_is_this`/`verdict`, and `scientific_argument`
around the arc *name-match → annotation-match → shown in the Atlas Browser*;
add the two studies and matching `acceptance_criteria`; add a
`decisions_needed`/verdict update reflecting the measured recall gain; reference
the Atlas Browser viewer (`studies/hra-atlas-browser/viz/atlas/`).

## Data flow
```
corpus catalog (1,096 ids) ─┐
HRA organ_index ────────────┼─ build_annotation_catalog (SBML+libsbml MIRIAM)
BTO→UBERON crosswalk ───────┘        └─► datasets/biomodel_annotation_catalog.json
name catalog + annotation catalog ─► compare_catalogs ─► recall-gain study + figure
annotation catalog ─► AnnotationMatchStep ─► annotation-organ-matching study
                                             (both under hra-integration)
```

## Error handling
- SBML fetch/parse failure for a model: skip, count, continue (never abort the
  whole build); the study reports the skip count as a coverage caveat.
- A CURIE that maps to no organ: dropped, not an error.
- Missing/empty BTO crosswalk: BTO CURIEs simply don't map; flagged in the study.

## Testing (offline)
- `annotation_match`: `extract_anatomy_curies` + `annotate_model` against 2–3
  committed SBML fixtures (a pancreas model e.g. BIOMD0000000137, a heart model
  e.g. BIOMD0000000126, and one with only a non-anatomy annotation → yields no
  organ). `build_annotation_catalog` with an injected `fetch` (fixture map) —
  no network.
- `annotation_gain.compare_catalogs`: hand-built name/annotation catalogs →
  known deltas (organs added, models added, per-organ rows). Invariants that
  always hold (asserted over the committed catalogs): `union ≥ name` and
  `union ≥ annotation` on organ count and model count, and
  `delta.n_models_added == union − name ≥ 0`. (Annotation is NOT assumed to beat
  name-matching per organ — name may catch a title an annotation misses; the
  union is the honest combined coverage.)
- Studies: composites load and emit non-empty summaries; study/investigation
  YAML validates and carries the `investigation:` backref (extends the existing
  `test_investigation_structure.py`).

## Phase 2 (separate plan) — per-run link, workspace-only (no workbench changes)
Entirely in this repo, through the existing workspace hook — importable into any
other workspace by copying the module + viz pack:
- `viva_human_atlas/workbench_viewers.py`: the `hra-atlas-browser` viewer
  declares `requires: ["observables"]` (a built-in workbench capability every
  store-emitting run advertises) so the workbench shows an "Atlas Browser" link
  on each compatible run in the Runs table, and keeps the viewer on the Analysis
  tab. Its `launch(ws_root, study, run, ctx)` resolves to the study's
  `viz/atlas/index.html`.
- The study composites (Phase 1 D) emit to a RAMEmitter, so their runs carry the
  `observables` capability and thus the per-run link.
- Optional, additive: also expose the pack via `ui.viz_viewer_urls` so it
  advertises the workspace-sourced `3d_pack` capability and shows as a
  study-level Analysis card too.
- Verified against the installed workbench (`feat/sim-db-compatible-tools`),
  which already matches tools to runs via `requires ⊆ run.capabilities`.

## Out of scope
- Per-anatomical-structure (sub-organ) counts (still organ-granularity).
- Re-running simulations; this is metadata/annotation work only.
- Modifying the name-synonym matcher (kept as the baseline to compare against).
