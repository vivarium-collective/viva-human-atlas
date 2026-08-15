# Organ → run all models → unified timeseries dashboard (kidney first)

**Date:** 2026-08-15
**Investigation:** hra-3d
**Study:** kidney-model-simulation
**Status:** approved design (libOpenCOR spike passed)

## Problem

The atlas maps mechanistic models to organs but never *runs* them. We want to
take an organ (kidney), pull every model tagged to it from the atlas DB, load
each into its compatible simulator, run it to a timeseries, and present all of
them in one interactive dashboard — showing both the models that run (with real
trajectories) and the ones that don't (with the reason), no silent drops.

## Spike outcome (already validated, informs this design)

libOpenCOR runs CellML end-to-end. Measured on kidney's 19 Physiome models:
- Resolver (GET `/e/<id>`, take the `.cellml` href, strip `/view`, hand the URL
  to OpenCOR) resolved **17/19**; **9/19 run cleanly** (7 state vars each).
- The rest fail on `libOpenCOR could not load model` (almost certainly
  multi-file CellML with imports) or a 500 on the exposure page. These are
  marked failures, not crashes.
- v1 uses the single-URL resolver (9/19); "download the exposure's full
  workspace fileset for import-heavy models" is a named follow-up to lift yield.

## Decisions (locked)

1. **Full heterogeneous**: SBML→COPASI, CellML→OpenCOR; run all runnable models.
2. **One canonical simulator per format** (SBML→COPASI, CellML→OpenCOR).
3. **Unified dashboard**: one interactive page, a grid of per-model cards
   (name · simulator · run-status badge) expanding to Plotly species/state
   timeseries.
4. **Placement**: a study in the existing **hra-3d** investigation.

Model routing by `repository` (+ `provenance`): `biomodels`→SBML→COPASI;
`physiome`→CellML→OpenCOR; `physionet`→skip (dataset references, not runnable).

## Reuse (do NOT rebuild)

- **SBML path is turnkey**: `viva_biomodels.composites.compare_simulators.run_comparison(biomodel_ids, simulators=["copasi"])` runs each model in its own isolated Composite (`LoadBiomodelStep` reads the model's SED-ML for duration/points → `BiomodelsCopasiStep`) and returns `{bid: {"engines": {"copasi": numeric_result}, "error": str|None}}` where `numeric_result = {time, columns, values}`. Models lacking SED-ML surface as `error` — shown as failure cards.
- **OpenCOR**: `viva_opencor.processes.OpenCORUTCStep` (construct with `core = allocate_core(); core.register_link('OpenCORUTCStep', OpenCORUTCStep)`), config `{model_source: <cellml url>, end_time, number_of_steps}`, output `result = {time, state:{comp/var:[...]}, rates, variables, constants}`.
- **Viz idiom**: self-contained Plotly HTML (`viva_human_atlas/viz.py` pattern, `fig.to_html(include_plotlyjs="cdn")`), written under the study's `viz/`.

## Design

### 1. Model selection (new, connectable)
`viva_human_atlas/organ_simulation.py::select_organ_models(organ, db_path) -> list[dict]`
returns, per organ-tagged model: `{key, name, repository, simulator, runnable, ref}` where `ref` is the `biomodel_id` (SBML) or `identifier`/`source_id` (Physiome), and `simulator ∈ {copasi, opencor, None}`. Wrapped as **`OrganModelSelectStep`** (config `organ`, `db_path`; outputs `manifest`, `n_models`, `per_simulator`, `summary`) so it appears in the modules tab.

### 2. Physiome CellML resolver (new; spike-validated)
`viva_human_atlas/physiome.py::resolve_cellml_url(identifier_or_exposure) -> str | None`:
GET the exposure page, regex `href="([^"]+\.cellml)(?:/view)?"`, `urljoin` to absolute, strip a trailing `/view`. Returns `None` on no-link/HTTP-error (caller marks the model failed). Parsing is unit-tested against a saved HTML fixture (offline); a network-marked test hits `/e/22e` live.

### 3. Run + normalize (new runner, reuses the engines)
`run_organ_simulation(organ, *, end_time, number_of_steps, db_path, out_dir) -> dict`:
- select models; split biomodels / physiome.
- SBML: `run_comparison(biomodel_ids, simulators=["copasi"])`.
- CellML: per model, `resolve_cellml_url` → `OpenCORUTCStep(...).update({})` in try/except (isolated; one failure never sinks the batch).
- **normalize** every result to a common tidy record via
  `normalize_result(kind, raw) -> {status, time:[...], series:{name:[...]}, error?}`:
  - SBML `{time, columns, values}` → `series = {col: column-vector}`.
  - OpenCOR `{time, state, variables, ...}` → `series = state (+ non-constant variables)`.
- returns `{organ, models:[{key,name,simulator,status,time,series,error}], summary:{n_models,n_ran,n_failed,by_simulator}}`.

### 4. Dashboard (new viz)
`viva_human_atlas/viz.py::organ_dashboard_html(result) -> str`: a self-contained
page — a responsive grid of per-model cards (name, simulator badge, green/red
run-status badge; failure cards show the error), each expanding to an
interactive Plotly figure of that model's series (small-multiples / overlay with
a species toggle). Written to `studies/kidney-model-simulation/viz/index.html`
(+ the tidy `result` JSON alongside), embedded in the study via a relative URL.

### 5. Orchestration Step + study
**`OrganSimulationStep`** (`organ_simulation.py`): config `{organ, end_time, number_of_steps, db_path, out_dir}`; `update()` calls `run_organ_simulation`, writes the dashboard + JSON, emits `summary` (`n_models, n_ran, n_failed, by_simulator`). Study baseline = this Step.
New **`studies/kidney-model-simulation/study.yaml`** (schema_version 4, investigation `hra-3d`), `baseline.step: local:viva_human_atlas.organ_simulation.OrganSimulationStep`, params `{organ: kidney}`. A **run study** (live native simulators + network fetches), like `glucose-regulation`; the committed dashboard is a snapshot of one run.

## Testing

- `select_organ_models("kidney")` offline: returns 24 models = 5 biomodels(copasi) + 19 physiome(opencor); physionet excluded. (reads committed DB)
- `resolve_cellml_url` offline: parses a saved exposure HTML fixture to the right URL (incl. `/view` strip); network-marked live test on `/e/22e`.
- `normalize_result` offline: SBML and OpenCOR synthetic inputs → correct tidy shape.
- `organ_dashboard_html` offline: on a synthetic 2-model result (1 ran, 1 failed) → valid self-contained HTML containing both a plot and a failure card.
- `OrganModelSelectStep` / `OrganSimulationStep` registered (link_registry) and construct with `core`.
- Network-marked end-to-end smoke (not default CI): kidney, `end_time` small — asserts ≥1 SBML and ≥1 CellML model ran.

## Files

- New: `viva_human_atlas/organ_simulation.py` (`select_organ_models`, `normalize_result`, `run_organ_simulation`, `OrganModelSelectStep`, `OrganSimulationStep`), `studies/kidney-model-simulation/study.yaml`, tests, an HTML fixture for the resolver test.
- Edited: `viva_human_atlas/physiome.py` (+`resolve_cellml_url`), `viva_human_atlas/viz.py` (+`organ_dashboard_html`).

## Risks / follow-ups

- **Yield-limited by single-file resolver** (9/19 Physiome for kidney): import-heavy CellML needs the exposure's full fileset — a named follow-up (download the PMR workspace archive, hand OpenCOR the local primary file).
- **Run study, not offline-reproducible**: live PMR/BioModels + native COPASI/libOpenCOR. Re-runs can differ if upstream changes; CI uses offline unit tests only, the live smoke is opt-in.
- **libOpenCOR must be installed** (native, via viva-opencor) — verified present in the workspace venv during the spike.
