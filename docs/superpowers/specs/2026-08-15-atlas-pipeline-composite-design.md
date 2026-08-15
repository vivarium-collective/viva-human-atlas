# HRA Computational Model Atlas — connected, reproducible build pipeline

**Date:** 2026-08-15
**Investigation:** hra-3d
**Status:** approved design

## Problem

The HRA Computational Model Atlas (`studies/hra-atlas-browser`) is produced by a
4-stage build pipeline, but only the endpoints are modeled as connectable
process-bigraph Steps. The two enrichment stages and the crosswalk builder run
as loose CLI scripts that pass a JSON file on disk between independent
invocations. Consequences:

1. The enrichment operations do **not** appear in the modules tab (only `Step`
   subclasses under `viva_human_atlas/` are auto-discovered by
   `core.build_core`'s package walk).
2. There is **no single orchestrator** — nothing you can open in the Composite
   Explorer and run end-to-end.
3. Reproducibility is implicit (re-run each script in the right order by hand),
   not a runnable, tested guarantee.

## Goal

- Represent every pipeline operation as a stage-level `Step` in the modules tab.
- Wire them into one **connected composite** runnable end-to-end in the Composite
  Explorer.
- Make the pipeline **reproducibly regenerate the same artifacts** offline from
  the committed datasets, with an explicit `live` path to re-harvest from APIs.
- Present the whole build in a new showcase **study** that highlights each
  component and the exact APIs it calls.

Non-goals: rewriting the existing three studies (only a one-line cross-link);
changing the atlas science, the viewer, or the harvested data; wrapping
individual inner-loop HTTP calls as Steps (stage-level granularity was chosen).

## Current pipeline (from the inventory)

| Stage | Operation | Today | Output |
|---|---|---|---|
| A | Harvest models → HRA map (BioModels/Physiome/PhysioNet + SBML/BioPAX/PubMed/MeSH/BTO/LLM) | `ModelHarvestStep` / `BiomodelHraMapStep` (Steps) | `datasets/model_hra_map.json` |
| — | ASCT+B tables + gene→Uberon index | `AsctbTablesStep` (Step) | `datasets/asctb_tables.json` |
| — | BTO→Uberon crosswalk | `bto_crosswalk.build_bto_uberon_crosswalk` (**loose script**) | `datasets/bto_uberon_crosswalk.json` |
| B | Enrich: organism + gene ids + gene→Uberon anatomy | `enrich.enrich_map` (**loose script**) | rewrites `model_hra_map.json` |
| C | Enrich: HRApop cell populations | `enrich_hrapop.enrich` (**loose script fn**) | rewrites `model_hra_map.json` |
| D | Build atlas pack + viewer JSON | `ComputationalModelAtlas` (Step) | `studies/hra-atlas-browser/viz/atlas/atlas.json` + `config.json` + `coverage.json` |

## Design

### 1. New stage-level Steps

All added under `viva_human_atlas/` so `core.build_core` auto-registers them into
the modules tab. Each wraps the **existing real function** (no reimplementation,
no mocks) and follows the workspace Step convention (`inputs()`/`outputs()`,
emit a summary + counts, not the raw DB).

- **`GeneEnrichStep`** (new, in `viva_human_atlas/enrich.py` alongside `enrich_map`)
  - Wraps `enrich.enrich_map`.
  - Params: `db_path` (default `datasets/model_hra_map.json`), `asctb_path`
    (default `datasets/asctb_tables.json`), `live` (default `false`).
  - `live=false`: no-op replay — the committed DB already carries the enrichment;
    load it and emit the counts it contains (idempotent).
  - `live=true`: build the gene→Uberon index from `asctb_path`, run `enrich_map`,
    rewrite the DB.
  - Outputs: `db_path`, `n_models_enriched`, `n_gene_uberons_added`, `summary`.

- **`HRApopEnrichStep`** (new). Requires a refactor: lift the body of
  `scripts/enrich_hrapop.py::enrich` into an importable module function
  `viva_human_atlas/enrich_hrapop.py::enrich_hrapop_map(db_path, hrapop_csv)`
  (the script becomes a thin CLI over it, matching the `BiomodelHraMapStep` /
  `scripts/build_biomodel_hra_map.py` "shared core, cannot diverge" pattern).
  - Params: `db_path`, `hrapop_csv` (default `datasets/hrapop_as_cell_populations.csv`),
    `live` (default `false`).
  - Outputs: `db_path`, `n_models_linked`, `summary`.

- **`BtoCrosswalkStep`** (new, in `viva_human_atlas/bto_crosswalk.py`)
  - Wraps `bto_crosswalk.build_bto_uberon_crosswalk`.
  - Params: `bto_terms_path` (default `datasets/bto_terms.json`), `out_path`
    (default `datasets/bto_uberon_crosswalk.json`), `live` (default `false`).
  - `live=false`: load and summarize the committed crosswalk.
  - Outputs: `out_path`, `n_terms`, `n_mapped`, `summary`.

### 2. The connected composite

A composite generator `atlas_pipeline` in `viva_human_atlas/composites/`,
registered via the existing `@composite_generator` mechanism
(`composites/__init__.py`). It wires the stage Steps into a build DAG, using the
dataset paths as the stores that connect them:

```
ModelHarvestStep ─┐                                    [model_hra_map store]
                  ├─→ GeneEnrichStep ─→ HRApopEnrichStep ─→ ComputationalModelAtlas ─→ atlas.json + viewer
AsctbTablesStep ──┘   (reads asctb)     (reads hrapop csv)    (reads crosswalk csv)
BtoCrosswalkStep ─→ (feeds ModelHarvest's crosswalk sub-stage)
```

- All nodes are `Step`s (a run-once build graph, not a time-stepped `Process`
  composite), consistent with the existing single-Step studies.
- The shared `model_hra_map.json` store is the wire the two enrich stages flow
  through; enrich Steps read and rewrite the same store in DAG order.
- Spec id follows workspace convention:
  `viva_human_atlas.composites.atlas_pipeline.<slug>`.

### 3. Reproducibility

- The committed datasets (`model_hra_map.json`, `asctb_tables.json`,
  `hrapop_as_cell_populations.csv`, `hra_asctb_crosswalk.csv`,
  `bto_uberon_crosswalk.json`, `biomodel_corpus_catalog.json`) **are the frozen
  snapshot**.
- Uniform **`live` param, default `false`**, on every pipeline Step. Off →
  load/replay the committed datasets deterministically and regenerate `atlas.json`
  identically. On → re-harvest/re-enrich from live APIs (may drift, rewrites
  datasets).
- Stage D (`ComputationalModelAtlas`) is already fully deterministic offline;
  the offline composite therefore reproduces the exact committed `atlas.json`.

### 4. Showcase study + cross-linking

- New `studies/atlas-pipeline/study.yaml` (schema_version 4, investigation
  `hra-3d`), `baseline.step` → the composite spec id (a runnable multi-Step
  composite, not a single Step).
- Narrative presents: the end-to-end DAG; each component and the exact external
  APIs it calls (BioModels REST/SBML/BioPAX, PubMed EFetch, Europe PMC, UniProt,
  ENA taxonomy, PhysioNet/DataCite, Physiome PMR, HRA ASCT+B API, HRA CCF API,
  HRA CDN, Anthropic LLM extraction); and the offline-replay reproducibility
  guarantee. Embeds the atlas viewer (reuse the existing
  `/studies/hra-atlas-browser/viz/atlas/index.html` embed).
- One-line cross-link added to `hra-atlas-browser`, `biomodel-hra-map`,
  `model-harvest` pointing at the new pipeline study.

### 5. Testing

- One offline unit test per new Step (`GeneEnrichStep`, `HRApopEnrichStep`,
  `BtoCrosswalkStep`): `live=false` loads the committed dataset and emits the
  expected counts; each Step is registered/importable.
- One end-to-end **offline composite test**: run `atlas_pipeline` with
  `live=false`, assert it regenerates `atlas.json` with the committed readouts
  (n_models_distinct=256, n_subregions=52, n_organs_with_subregions=9, etc.).
- One **determinism test**: two offline runs produce byte-identical `atlas.json`
  (compare after canonical JSON dump; if float/ordering churn appears, assert on
  parsed readout stats instead and note it).

## Files touched

- New: `viva_human_atlas/enrich_hrapop.py` (lifted module fn + `HRApopEnrichStep`),
  `viva_human_atlas/composites/atlas_pipeline.py`, `studies/atlas-pipeline/study.yaml`,
  tests under `tests/`.
- Edited: `viva_human_atlas/enrich.py` (+`GeneEnrichStep`),
  `viva_human_atlas/bto_crosswalk.py` (+`BtoCrosswalkStep`),
  `scripts/enrich_hrapop.py` (thin CLI over the new module fn),
  the three existing `study.yaml` cross-links.

## Risks

- **HRApop refactor**: moving `enrich_hrapop.py`'s logic into the package must
  preserve exact behavior — covered by asserting the committed DB's HRApop link
  count is reproduced.
- **atlas.json determinism**: dict/float ordering could cause byte churn; the
  determinism test falls back to readout-stat comparison if so.
- **Composite store wiring**: the enrich stages mutate a shared store in order;
  the composite must serialize them (DAG edge), not run them concurrently.
