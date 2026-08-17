# Reproducing the HRA Computational Model Atlas

This document records **how the atlas is built from the workspace's own
process-bigraph modules and composites**, and how to press "play" to regenerate
it. The whole pipeline is wired as one connectable **Step DAG** — a single
composite (`hra-atlas-pipeline`) — so you don't re-run a pile of ad-hoc scripts;
you run the composite (or its study) and it reproduces `atlas.json` and the
viewer.

> **Two modes, one pipeline.** Every stage takes a `live` flag.
> - `live=false` (default) — **replay**: deterministically rebuild `atlas.json`
>   from the **committed datasets**. No network, no LLM, byte-identical every run
>   (there's a test that asserts two runs are identical). This is the normal
>   "hit play → recreate the atlas."
> - `live=true` — **rebuild**: re-harvest from the external source APIs
>   (BioModels, PhysioNet DataCite, the Physiome pmr3 API) and re-enrich. Slow,
>   network- and LLM-dependent, and not bit-reproducible run-to-run. Use only to
>   refresh the committed datasets.

## The pipeline (Step DAG)

```
                     ┌───────────────────┐
  external sources → │ ModelHarvestStep  │ ─┐   datasets/model_hra_map.json
  (BioModels /       └───────────────────┘  │   (the unified multi-source model DB)
   PhysioNet /       ┌───────────────────┐  │
   Physiome pmr3)  → │ AsctbTablesStep   │ ─┤
                     └───────────────────┘  │
                                            ▼
                            ┌───────────────────────────┐
                            │ GeneEnrichStep            │  organism / HGNC / gene→Uberon
                            └───────────────────────────┘
                                            ▼
                            ┌───────────────────────────┐
                            │ HRApopEnrichStep          │  HRApop per-AS cell populations
                            └───────────────────────────┘
                                            ▼
                            ┌───────────────────────────┐
                            │ ComputationalModelAtlas   │ → studies/hra-atlas-browser/
                            └───────────────────────────┘     viz/atlas/atlas.json
                                            ▼
                                   static viewer.js + index.html
                                   (organ selector, model-count gradient,
                                    subregion placement, model links)
```

All of this is defined in `viva_human_atlas/composites/atlas_pipeline.py` as the
`@composite_generator` **`hra-atlas-pipeline`**, and surfaced as the
**`atlas-pipeline` study**.

## The modules (process-bigraph Steps)

Each stage is a real registered `Step` in `viva_human_atlas/` (registered by
`core.build_core()` under both a dotted path and short name):

| Step | File | What it does |
|---|---|---|
| `ModelHarvestStep` | `model_harvest.py` | Load (replay) or harvest (live) the unified model DB across the `SOURCES` registry — **BioModels + PhysioNet + Physiome** — into `datasets/model_hra_map.json`. Emits total + per-source counts + coverage summary. |
| `AsctbTablesStep` | `asctb_tables.py` | Load/refresh the ASCT+B anatomical-structure/cell-type tables (`datasets/asctb_tables.json`). |
| `GeneEnrichStep` | `enrich.py` | Attach organism / HGNC / Ensembl gene info and gene→Uberon anatomy to model rows. |
| `HRApopEnrichStep` | `enrich_hrapop.py` | Attach HRApop measured per-anatomical-structure cell populations. |
| `ComputationalModelAtlas` | `atlas_browser.py` | Build the atlas pack (`atlas.json` + `config.json` + `coverage.json`), placing each model on its organ and, where cell-type/FTU evidence supports it, on organ **subregions**. |

Supporting cores (called by the Steps / scripts, not themselves the play button):
`biomodel_hra.py` (BioModels extraction + `summarize_map`), `physionet.py` /
`physionet_organ_map.py`, `physiome.py` / `physiome_organ_map.py` (the pmr3-API
source), `atlas_pack.py` (`build_and_write_atlas`, the offline orchestrator that
`scripts/build_atlas_pack.py` wraps), `atlas_subregions.py`, `hra_pop.py`.

The **sources** behind `ModelHarvestStep` (`model_harvest.SOURCES`):

| Source | Module | Enumerate → build |
|---|---|---|
| `biomodels` | `biomodel_hra.py` | BioModels search → SBML/BioPAX/PubMed extraction |
| `physionet` | `physionet.py` | PhysioNet DataCite DOI enumeration (`10.13026` prefix) |
| `physiome` | `physiome.py` | Physiome **pmr3 API** (`/api/index/exposure_id`) → author-keyword organ mapping + PubMed citations |

Adding a fourth source = one more `SOURCES` entry (`list_fn`/`entry_fn`/`id_of`).

## How to run it

All commands run in the workspace virtualenv (`.venv`). See
[Environment](#environment) below for setup.

### 1. Run the pipeline composite (replay — the usual "hit play")

```bash
.venv/bin/python -c "
from process_bigraph import Composite
from viva_human_atlas.core import build_core
from viva_human_atlas.composites.atlas_pipeline import build_atlas_pipeline_document
Composite(build_atlas_pipeline_document(live=False), core=build_core())
"
```

This runs the full Step DAG offline and regenerates
`studies/hra-atlas-browser/viz/atlas/atlas.json` from the committed datasets.

### 2. Run it from the interactive workbench

```bash
vivarium-workbench serve          # then open the workspace in the browser
```

Open the **`atlas-pipeline`** study and press **Run / Rerun** — its baseline is
the `hra-atlas-pipeline` composite with `live: false`.

### 3. Rebuild just the atlas pack (stage 3 only)

If the model DB is already current and you only want to regenerate `atlas.json`:

```bash
.venv/bin/python scripts/build_atlas_pack.py
```

### 4. View the atlas

```bash
bash scripts/serve_dashboard.sh   # serves the read-only dashboard locally
```

or open the published viewer:
`https://vivarium-collective.github.io/viva-human-atlas/dashboard/studies/hra-atlas-browser/viz/atlas/index.html`.
(The viewer streams each organ's 3D GLB mesh from the HRA CDN at view time, so
viewing — unlike the offline `atlas.json` build — needs internet.)

### 5. Full rebuild from the source APIs (optional, slow)

To refresh the committed datasets from scratch, pass `live=True`
(`build_atlas_pipeline_document(live=True)`), or refresh a single source:

```bash
.venv/bin/python scripts/harvest_models.py                      # all sources, incremental
.venv/bin/python scripts/harvest_models.py --rebuild physiome --source physiome
```

`scripts/harvest_models.py` calls the same `model_harvest.harvest()` the Step
does, so the CLI and the Step cannot diverge. Live runs hit external APIs (and,
for the unmapped tail, an LLM), and are not bit-reproducible.

## The studies

Which study is which (atlas-relevant ones):

| Study | Baseline | Role |
|---|---|---|
| **`atlas-pipeline`** | composite `hra-atlas-pipeline` (`live: false`) | **The "hit play" study** — full harvest→enrich→atlas DAG, offline replay by default. |
| `model-harvest` | `ModelHarvestStep` (`build_if_missing: false`) | Stage 1 only: load/refresh the unified model DB across all three sources. |
| `hra-atlas-browser` | `ComputationalModelAtlas` | Stage 3 only: regenerate the atlas pack from an already-built DB. |
| `biomodel-hra-map` | `BiomodelHraMapStep` | Older BioModels-only extraction (predates the multi-source harvest). |

The other studies (`corpus-coverage`, `annotation-organ-matching`,
`annotation-recall-gain`, `ftu-model-coverage`, `model-coverage-3d`,
`spatial-linkage`, `ctpop-islet-parameterization`, `kidney-model-simulation`,
`glucose-regulation`, the vasculature studies, …) are analyses/viewers built
**on top of** the atlas DB, not part of the atlas build itself.

## What's committed vs. live

- **Committed (so replay works offline):** `datasets/model_hra_map.json` (the
  unified model DB), `datasets/asctb_tables.json`, the corpus catalog + HRApop
  CSV + ASCT+B-3D crosswalk, and the built `studies/hra-atlas-browser/viz/atlas/`
  pack (`atlas.json`, `config.json`, `coverage.json`) + the static viewer.
- **Not committed:** `.cache/` (per-source harvest caches) and `models/` (raw
  SBML/CellML for the simulation studies) — only needed for live rebuilds /
  actual simulation, not for replaying the atlas.

## Verify

```bash
.venv/bin/python -m pytest -m "not network"
```

Relevant guards: `tests/test_atlas_pipeline_composite.py` (the composite
regenerates the committed `atlas.json`) and
`tests/test_atlas_pipeline_reproducible.py` (two offline runs are byte-identical).

## Environment

The workspace depends on sibling process packages `viva-biomodels`,
`viva-copasi`, `viva-tellurium` (renamed from `pbg-*` in the 2026 rebrand), which
are not on PyPI. `pyproject.toml`'s `[tool.uv.sources]` declares them as **git
sources (`@main`)**, so a fresh clone installs with no local sibling checkouts:

```bash
uv venv && uv pip install -e .            # clone → install (pulls siblings from git)
.venv/bin/python -m pytest -m "not network"
```

For LOCAL editable dev of a sibling, override per-checkout:

```bash
uv pip install -e ../viva-biomodels -e ../viva-copasi -e ../viva-tellurium
```

`core.build_core()` guards the sibling-simulator import, so the registry still
builds (Steps register, the atlas pipeline runs) even in a degraded environment;
only the COPASI/Tellurium **simulation** studies need the engine packages.

> **Note (transitional):** a clean from-scratch `uv pip install` also requires two
> upstream fixes to be merged so the sibling dependency graph resolves —
> viva-biomodels#25 (corrects the copasi/tellurium git-source dist names) and
> vivarium-workbench#860 (unifies `viva-superpowers@main` across the graph). Until
> those land, use the local-editable override above (the workspace `.venv` already
> has everything installed).
