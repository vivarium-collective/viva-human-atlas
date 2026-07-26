# HRA 3D coverage + spatial linkage + viewer — design

**Date:** 2026-07-26
**Status:** approved (design), pending implementation plan

## North Star

Spatially ground viva-human-atlas's Aim-2 models on the HRA 3D anatomy: show
**model coverage** across the 1,400+ anatomical structures (AS) in the 81 HRA 3D
reference organs, and **spatially link** model outputs to specific AS. Supports
the DynXR proposal and the collaborator's browser 3D-viewer goal (a viewer that
renders the HRA GLBs and colors AS by model coverage / results). See
`references/sources/dynxr-proposal.md`.

## Data model (verified from the live HRA)

- **ASCT-B-3D crosswalk** (the 1,400+ AS): CSV at
  `https://cdn.humanatlas.io/digital-objects/ref-organ/asct-b-3d-models-crosswalk/latest/assets/asct-b-3d-models-crosswalk.csv`
  (v1.10, 2306 rows; ~11 metadata header rows then a data table). Columns:
  `anatomical_structure_of, source_spatial_entity, node_name, label, OntologyID,
  representation_of, node_type, glb file of single organs, Ref/1, Ref/1/ID`.
  Each row = an AS as a **named node in a GLB scene**, with its Uberon id
  (`OntologyID`, e.g. `UBERON:0014455`), human `label`, `node_type` (`mesh` vs
  `organizational`), and the organ GLB it lives in.
- **Reference organs** (81, per-organ GLB): existing `HRAReferenceOrgansStep` /
  `GET /v1/reference-organs` (`representation_of` = Uberon, `object.file` = GLB URL).
- **3D FTU**: DO container, e.g. `https://purl.humanatlas.io/3d-ftu/glomerulus/latest`
  → `{data: ["glomerulus.glb"], metadata: {...}}`; GLB at the DO's `assets/`.

**GLB binaries are streamed from the HRA CDN at view time — never vendored** (large).

## Components (one spec, built in order)

### C1 — Data ingestion (`viva_human_atlas/hra_api.py`, typed like the others)
- **`HRACrosswalkStep`** → `fetch_crosswalk(*, _get=None) -> list[dict]` parses the
  CSV (skip metadata rows; header row starts with `anatomical_structure_of`) into
  typed `as_3d` records `{node_name, label, uberon(CURIE), representation_of,
  node_type, organ_glb, parent}`. Registered type `as_3d`. `outputs()` →
  `{"anatomical_structures_3d": "list[as_3d]"}`. Description + `_contract`.
- **`HRAFtuStep`** → `fetch_ftu(slug="glomerulus", *, _get=None) -> dict` returns FTU
  DO metadata + GLB asset URL. Typed `ftu` record. Config `{slug}`.
- Reuse `HRAReferenceOrgansStep`.

### C2 — Model coverage (`viva_human_atlas/coverage.py`)
- **`build_coverage(query="glucose regulation", max_results=25, *, _get_search=None,
  _get_hra=None) -> dict`**: build the biomodel-DO `organ_to_models` (existing) and
  the crosswalk AS; for each AS, mark coverage by whether its **organ** has ≥1
  model (v1 = **organ-granularity**: an AS inherits its organ's coverage — finer
  AS-level annotation is future). Returns `{coverage: [{uberon, label, organ,
  organ_glb, n_models, model_ids, covered}], summary: {n_as, n_as_covered,
  n_organs, n_organs_covered}}`.
- **`CoverageStep`** + **`model-coverage-3d`** `@composite_generator`.

### C3 — Spatial linkage (`viva_human_atlas/spatial_link.py`)
- **`build_spatial_links(query=..., max_results=..., *, _get_search=None,
  _get_hra=None) -> dict`**: for each biomodel DO, emit linkage records
  `{biomodel_id, name, uberon, organ, organ_glb, node_name, readout}` joining
  biomodel-DO organs → crosswalk AS nodes (match on Uberon), so a viewer can color
  the exact GLB node by a model result. `readout` is a placeholder label in v1
  (real time-series wiring is future). `SpatialLinkStep` + composite.

### C4 — 3D viewer as a workbench **Analysis Tool**
Registered the workbench way (not a standalone page), so it's surfaced in the
Analysis Tools tab and matched to the coverage studies.
- **Registration:** `viva_human_atlas/workbench_viewers.py::get_viewers(ws_root)`
  returns one **`launcher`**-kind viewer `hra-glb-viewer` ("HRA Organ Viewer").
  Its `targets(ws_root)` globs `studies/*/viz/hra/coverage.json` and returns one
  target per such study, each carrying a plain external **`href`** to the viewer
  page (targets with an `href` stay clickable in the **published snapshot**; the
  `/api/analysis-viewer/{uid}/launch` resolve endpoint has NO static form, so we
  do not rely on it). Uses the `targets` escape-hatch — no capability-vocabulary
  edit to `vivarium-workbench` needed.
- **Viewer asset:** a self-contained **three.js + GLTFLoader** page (importmap-
  pinned, like `pbg_parsimony/viewer/`) shipped in the package and **written into
  `studies/<slug>/viz/hra/`** by the coverage step (workspace-tree files are
  served statically live AND copied wholesale into the published bundle — same
  place parsimony packs live). It takes data purely via URL query params:
  `?glb=<cdn.humanatlas.io organ GLB>&coverage=<coverage.json>&links=<spatial-links.json>`.
- **Behavior:** loads **one organ** (default **kidney** — diabetes/glucose + the
  glomerulus FTU), streams its GLB (HRA CDN sends `access-control-allow-origin: *`
  — cross-origin verified OK), traverses named nodes (`node_name` from the
  crosswalk), and **colors each AS by coverage** (covered = highlighted; hover →
  `label` + Uberon + model count). Organ + data paths are query-params so other
  organs work later.
- **Data placement:** C2/C3 write `studies/<slug>/viz/hra/{coverage.json,
  spatial-links.json}` alongside the copied viewer `index.html`/`viewer.js`, so
  the tool's target + data resolve in both live and published-bundle modes.
- Publish already snapshots `get_viewers()` into `api/analysis-viewers.json`.

### Studies
`hra-3d-crosswalk` (loads 1,400+ AS), `model-coverage-3d` (coverage map + summary),
`spatial-linkage` (glucose models → AS nodes), `ftu-glomerulus` (the FTU). Each
`schema_version 4` with a non-empty `baseline` → the registered generator id, and a
load/verify test (offline mocked + `@pytest.mark.network` live).

## Testing
- Unit tests: `fetch_crosswalk` / `fetch_ftu` with injected fakes (no network);
  `build_coverage` / `build_spatial_links` fully mocked (crosswalk + biomodel-DO
  fixtures) asserting coverage/linkage shape + the organ-inheritance rule.
- Network tests (`@pytest.mark.network`): real crosswalk loads ≥1000 AS with Uberon
  ids; real coverage summary is non-trivial; real FTU resolves a GLB URL.
- Viewer/tool: `get_viewers(ws_root)` returns the `hra-glb-viewer` with valid
  fields; `targets` picks up a study once `studies/<slug>/viz/hra/coverage.json`
  exists; the viewer `index.html` references three.js + reads `glb`/`coverage`
  query params; the coverage step writes `coverage.json`/`spatial-links.json` +
  the viewer assets under `viz/hra/`.

## Non-goals (v1)
- No AS-level model annotation (coverage is organ-granularity).
- No real time-series wired into spatial links (placeholder readouts).
- No GLB binaries vendored; no full multi-organ viewer UI (single organ, configurable).
- The viewer is a prototype, not the production CNS-IU viewer.

## Notes
- Reuses the typed-contracts + biomodel-DO foundation already on `main`.
- Build order: C1 → C2 → C3 → C4 (C4 consumes C2/C3 outputs).
