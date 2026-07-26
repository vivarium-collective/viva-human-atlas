# Full-corpus coverage + shared results + viz + study enrichment — Plan

> **For agentic workers:** implement task-by-task, TDD, commit per task. Reuse `main` conventions (typed `WORKSPACE_TYPES`; `@composite_generator`; study `baseline.composite` = registered generator id; offline tests inject fakes / live tests `@pytest.mark.network`; superpowers shim; fully-dotted `local:` Step addresses).

**Goal:** (1) In **viva-biomodels** (dir `~/code/pbg-biomodels`, GitHub `viva-biomodels`), commit a compact **corpus COPASI+Tellurium time-course dataset** (trimmed to those 2 engines, downsampled) + a `biomodels-corpus-comparison` study. (2) In **viva-human-atlas**: federate that study (provenance card) AND read the committed dataset directly for **Plotly visualizations**; retrieve+tag all 1,096 curated BioModels, evaluate corpus coverage, regenerate viewer packs; and fill EVERY study card with rich content + REAL findings + embedded Plotly figures.

## Key architecture facts (verified)
- **Workbench federation (PR #600) = metadata only** — surfaces study/composite cards with `origin_repo` badges from `external/<repo>/` checkouts; does NOT transfer run results/figures (SP-C unbuilt). So results MUST come via a committed **data file** read directly (pbg_biomodels is already a viva-human-atlas dep).
- Source results (uncommitted scratch in the canonical `~/code/pbg-biomodels/out/compare_all_1054/`): `series/<BID>.parquet` (tidy `job,engine,variable,time,value`; engines incl. copasi,tellurium; 892 models) + `index.json` (pairwise NRMSE metrics).
- **Worktree discipline:** `pbg-biomodels` is a SHARED repo — do viva-biomodels commits in a dedicated worktree off `origin/main`; READ the uncommitted `out/` scratch from the canonical `~/code/pbg-biomodels/out/` (absolute path), WRITE the trimmed dataset into the worktree.
- Git commits: `-c user.name="Eran Agmon" -c user.email="agmon.eran@gmail.com"` + trailer `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

---

## PART 1 — viva-biomodels (data + study), in a worktree

### Task Z0 — Trimmed corpus results dataset (committed)
**Where:** a worktree `~/code/pbg-biomodels--corpus-dataset` off `origin/main` (create via `git -C ~/code/pbg-biomodels worktree add`).
**Files:** `scripts/build_corpus_dataset.py`; committed output `datasets/corpus_comparison/corpus_timecourse.parquet` + `datasets/corpus_comparison/corpus_metrics.json` + `datasets/corpus_comparison/README.md`; test `tests/test_corpus_dataset.py`.

- `scripts/build_corpus_dataset.py --source <dir> --out datasets/corpus_comparison`: reads `<source>/series/*.parquet` (default source = `/Users/eranagmon/code/pbg-biomodels/out/compare_all_1054`), for each model: filter `engine in {copasi, tellurium}`, **downsample** each (model,job,engine,variable) series to ≤100 time points (even stride), concat into ONE tidy parquet `corpus_timecourse.parquet` columns `[biomodel_id, job, engine, variable, time, value]` (float32). Also read `<source>/index.json` → write `corpus_metrics.json` = `{biomodel_id: {job: {pairs: {copasi__tellurium: {mean_nrmse, bucket, n_shared}}}}}` (copasi/tellurium only). Log models processed + final parquet size (target < ~15 MB).
- A tiny `pbg_biomodels/corpus_results.py` reader: `load_corpus_timecourse(path=None) -> "pandas.DataFrame"` (default path = packaged/dataset location) and `model_timecourse(biomodel_id, engine=None) -> DataFrame`; `load_corpus_metrics(path=None) -> dict`. So downstream repos import `pbg_biomodels.corpus_results`.
- [ ] test (offline): build a 2-model synthetic `series/` parquet in tmp, run the dataset builder, assert `corpus_timecourse.parquet` exists with the right columns + ≤100 pts/series + only copasi/tellurium; `load_corpus_timecourse`/`model_timecourse` read it back.
- [ ] implement; run the builder against the real canonical `out/compare_all_1054` (READ from `~/code/pbg-biomodels/out/...`); verify size < ~15 MB, N models. Commit the dataset + reader + script to the worktree branch; push; open PR to viva-biomodels. Record model count + size.
- [ ] commit: `feat: committed trimmed corpus COPASI+Tellurium time-course dataset + reader`

### Task Z1 — viva-biomodels corpus-comparison study (metadata layer)
Same worktree.
**Files:** `workspace.yaml` (ensure study support), `studies/biomodels-corpus-comparison/study.yaml`, `investigations/biomodels-comparison/investigation.yaml` (if the repo has none, create minimal).
- Create `studies/biomodels-corpus-comparison/study.yaml` (schema_version 4): question ("Do COPASI and Tellurium agree across the curated BioModels corpus?"), study_card, biological_summary, readouts, report block with REAL numbers from `corpus_metrics.json` (n models, agreement bucket distribution copasi-vs-tellurium), `baseline` → the existing `compare-simulators` generator (registered id `pbg_biomodels.composites.compare_simulators.compare-simulators`), and `embed_visualizations` pointing at a committed Plotly summary figure (agreement-bucket histogram) generated from `corpus_metrics.json`.
- [ ] verify the study's baseline resolves; commit to the same PR.
- [ ] commit: `feat: biomodels-corpus-comparison study (corpus COPASI-vs-Tellurium)`

---

## PART 2 — viva-human-atlas (consume + coverage + viz + enrich)

*(All Part-2 tasks on branch `feat/full-corpus-coverage` in `~/code/viva-human-atlas`.)*

### Task A — Corpus retrieval + catalog build (1,096 curated)
**Files:** modify `viva_human_atlas/biomodels_search.py`, `biomodel_do.py`; `scripts/build_biomodel_catalog.py`; test `tests/test_corpus_catalog.py`.
- `biomodels_search.fetch_all_biomodel_ids(*, curated_only=True, _all=None) -> list[str]` (filter `get_all_identifiers()` to `BIOMD`).
- `biomodels_search.fetch_biomodels_named(ids, *, max_workers=8, _get=None) -> list[{id,name}]` (parallel per-id `search_biomodels_detailed`; tolerate failures → name ""; deterministic order).
- `biomodel_do.build_catalog_from_models(models, *, _get_hra=None) -> {biomodel_dos, organ_index, organ_to_models}` (refactor the annotate-core out of `build_biomodel_do_catalog`, which now = search → this).
- `scripts/build_biomodel_catalog.py` → writes committed `datasets/biomodel_corpus_catalog.json` `{n_ids, n_named, n_tagged, catalog}`.
- [ ] test offline (mock ids + names + ref-organs); implement; run script (network); commit dataset + record n_named/n_tagged.
- [ ] commit: `feat: full BioModels corpus catalog (organ-tagged, committed)`

### Task B — Corpus coverage + regenerated viewer packs
**Files:** modify `coverage.py`, `scripts/build_hra_viewer_pack.py`; `composites/corpus_coverage_composite.py`; `composites/__init__.py`; test `tests/test_corpus_coverage.py`.
- `coverage.build_coverage(..., catalog=None)`; `coverage.load_corpus_catalog(path)`; `coverage.build_corpus_coverage(catalog_path=..., *, _get_xwalk=None)`; `@composite_generator("corpus-coverage")`.
- Update viewer-pack script to use **corpus** coverage; regenerate packs for covered organs (kidney/liver/pancreas at least); commit; record whether kidney now covered.
- [ ] test offline; implement; run (network); commit; `discover_generators()` includes `corpus-coverage`.
- [ ] commit: `feat: corpus-coverage + regenerated viewer packs`

### Task BV — Plotly viz + corpus-results source
**Files:** `viva_human_atlas/viz.py`, `viva_human_atlas/results_source.py`; test `tests/test_viz.py`.
- `results_source.load_corpus_timecourse()` / `model_timecourse(bid, engine)` / `load_corpus_metrics()` — thin wrappers delegating to `pbg_biomodels.corpus_results` (Task Z0), tolerant if unavailable (`None`/empty).
- `viz.timecourse_overlay_html(bid, df_or_engines, *, max_species=6) -> str` — self-contained Plotly HTML overlaying COPASI (solid) vs Tellurium (dashed) species trajectories (from the corpus DataFrame OR a live `run_comparison` numeric_result). `include_plotlyjs="cdn"` (verify iframe embed OK; else inline).
- `viz.coverage_bar_html(coverage_summary, per_organ) -> str`; `viz.write_study_figure(slug, name, html, ws_root=".") -> Path` (writes `reports/figures/<slug>/<name>.html`; `git add -f`, since `reports/*` is gitignored).
- [ ] test offline (synthetic df + coverage); implement.
- [ ] commit: `feat: Plotly viz + corpus-results source (reads viva-biomodels dataset)`

### Task C+D — Enrich ALL studies with rich cards + real findings + embedded Plotly
For every study across `glucose-regulation`, `hra-integration`, `hra-3d` (+ new `corpus-coverage`): populate `question`, `study_card{goal,mechanism,expected_result,main_expert_question}`, `biological_summary`, `readouts`, and a `report{title,verdict,confidence,evidence_quality,objective,conclusion(REAL numbers),caveat}` (model on `~/code/viva-munk/studies/glucose-growth/study.yaml`); keep `baseline` (registered id). Add `embed_visualizations` with a REAL Plotly figure where results exist:
- `glucose-regulation` / `glucose-biomodel-do`: COPASI-vs-Tellurium overlay for a representative model (from the corpus dataset or live run) + agreement numbers.
- `corpus-coverage` / `model-coverage-3d`: coverage bar chart + real coverage counts.
- `hra-reference-organs`/`cell-types`/`anatomical-structures`/`hra-3d-crosswalk`/`ftu-glomerulus`: real counts (81/149/288/2295/FTU) in the report; a Plotly bar where meaningful.
These can be split across parallel subagents by investigation. Each verifies: offline suite green; baselines resolve; figures written (`git add -f`).
- [ ] commit(s): `feat: enrich <investigation> study cards + Plotly viz with real findings`

### Task E — Federate + republish + verify
- [ ] Federate viva-biomodels into viva-human-atlas: create `external/viva-biomodels` pointing at the viva-biomodels checkout (symlink to `~/code/pbg-biomodels` or a submodule) so `federation.linked_workspaces` surfaces the `biomodels-corpus-comparison` study card. Verify it appears (badge, read-only).
- [ ] `bash scripts/publish_dashboard.sh --push`; verify live: enriched cards render (study-detail JSON has report + embed_visualizations), Plotly figures load, corpus-coverage study present, viewer packs reachable.
- [ ] commit showcase fixes.

## Self-Review
- Locked decisions honored: trimmed copasi+tellurium downsampled dataset (Z0); viva-biomodels data file + study + federation (Z0/Z1/E); 1,096 curated corpus (A); rich cards + real findings + Plotly viz (BV/C/D).
- Federation reality baked in: results travel via committed dataset read directly (BV/results_source), NOT via federation (metadata card only, Task E).
- No-placeholder: C/D require REAL numbers from the committed dataset / live runs / coverage — no fabricated results; a study without runnable results gets an honest "pending" verdict.
- Cross-repo: viva-biomodels commits via worktree off origin/main, reading canonical `out/` scratch by absolute path; PR to viva-biomodels. viva-human-atlas depends on the new `pbg_biomodels.corpus_results` reader (bump the dep after Z0 merges, or read via the sibling path meanwhile).
- Risk: viva-human-atlas reading the dataset requires the viva-biomodels change installed — during dev, read from the sibling `~/code/pbg-biomodels` checkout; note the dep bump needed post-merge.
