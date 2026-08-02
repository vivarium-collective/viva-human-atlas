# HRA Atlas Browser — design

**Date:** 2026-08-01
**Status:** approved (brainstorming)
**Branch:** `feat/hra-atlas-browser`

## Problem

The repo's 3D visualization (`studies/model-coverage-3d/viz/hra/`) shows a
single organ GLB (default pancreas), colors each mesh **binary** green/grey
(covered vs not), and on hover shows a region label + Uberon + a model *count*.
It has three gaps the user wants closed:

1. **No organ selection** — you must navigate to hidden per-organ URLs
   (`viz/hra/{kidney,liver,pancreas}/`); there is no in-UI picker, and only 3
   of the 50 GLB-backed organs are exposed.
2. **Regions not demarcated** — sub-regions of an organ are one undifferentiated
   colored blob; the region name only appears on hover.
3. **No model-count gradient, no BioModels access** — coloring is binary, not
   scaled to how many models touch a region; the models themselves are not
   listed or linked out to BioModels.

## Goal

A self-contained **HRA Atlas Browser**: pick any of the 50 HRA organs with a
3D asset, see its regions demarcated and colored by the number of mechanistic
models associated with it, and browse/click through to the actual BioModels
pages. Feed it from a refreshed data pipeline and give it a coherent home in
the investigation structure.

## Data reality (constrains the design)

The committed corpus catalog (`datasets/biomodel_corpus_catalog.json`) yields:

- **50 HRA organs with GLB assets** in `organ_index` (key, `uberon`, `sexes`,
  `asset_urls`).
- **10 organs have ≥1 model** (`organ_to_models`): pancreas 36, blood 19,
  liver 9, lung 6, brain 5, heart 4, adipose 2, intestine 2, skin 1, kidney 1.
- Coverage is **organ-granularity**: every sub-region cut from an organ's GLB
  inherits that organ's model list, so **within a single organ all sub-regions
  currently share the same model count**. Per-node rows already carry
  `model_ids` (BioModels IDs).

Decision (confirmed): color at **organ granularity now**; true per-sub-structure
counts are a **follow-up study** (`fp-as-level-coverage`, needs SBML
MIRIAM/Uberon parsing). This design does **not** implement AS-level counts.

## Scope decisions (confirmed)

- **Region granularity:** organ-level now; AS-level follow-up (out of scope).
- **Organ selector scope:** all **50** GLB organs; the 40 with zero models
  render greyed to make the modeling white-space visible.
- **Landing view:** whole-body overview (all organs colored by count) as the
  default, with the dropdown to drill into a single organ. Falls back to
  dropdown → single-organ if the united whole-body GLB fails to load.
- **Restructure depth:** conservative — keep the existing study grouping, add
  an explicit `investigation:` back-reference to each `study.yaml`, and update
  the `hra-3d` investigation's lead/verdict to include the browser. No
  re-homing of existing studies.
- **Deps:** refresh `vivarium-workbench` and `pbg-superpowers` (dist
  `viva-superpowers`) to `origin/main` and install editable, using their
  `--main` worktrees so the canonical siblings' feature branches are untouched.

## Architecture

Four units, each independently testable:

### A. Atlas manifest builder (Python)
`scripts/build_atlas_pack.py` + a library function in
`viva_human_atlas/atlas_pack.py`.

- Reuses `load_corpus_catalog`, `build_corpus_coverage`, `organ_index`,
  `organ_to_models` — **no new network dependency** (committed catalog).
- Emits `viz/atlas/atlas.json`:
  ```json
  {
    "organs": [
      {"key": "pancreas", "label": "Pancreas", "uberon": "UBERON:0001264",
       "glb": {"female": "…3d-vh-f-pancreas.glb", "male": "…"},
       "n_models": 36,
       "models": [{"biomodel_id": "BIOMD0000000137",
                   "name": "Sedaghat2002_InsulinSignalling_noFeedback",
                   "url": "https://www.ebi.ac.uk/biomodels/BIOMD0000000137"}, …]},
      …50 organs…
    ],
    "max_models": 36,
    "summary": {"n_organs": 50, "n_modeled": 10, "n_models_total": …}
  }
  ```
- Also (re)emits the existing `coverage.json` shape for per-node data (reused).

### B. Viewer (three.js, no build step)
`viz/atlas/{index.html, viewer.js, config.json}` + the manifest above.
Mirrors the existing `viewer_pack` pattern (importmap-pinned three.js, all data
from sibling JSON, no query params).

- **Organ selector:** dropdown from `atlas.json.organs`; modeled organs sorted
  first and colored, zero-model organs greyed. Selecting loads that organ's GLB
  (prefer female asset, fall back to first).
- **Region demarcation:** per-mesh `EdgesGeometry` outlines so sub-regions read
  as distinct shapes; hover brightens the hovered region, click pins it.
- **Color by model count:** sequential palette scaled to `max_models`
  (saturated = highest, faint = 1, grey = 0). Whole-body overview colors each
  organ by its count; single-organ view colors the organ by its count with
  sub-regions separated by outline. Legend shows the count→color colorbar plus
  a grey "no model" swatch.
- **BioModels panel:** side panel lists the selected organ's `models` as
  `BIOMD… — name` rows; each row links to its `url`
  (`https://www.ebi.ac.uk/biomodels/<id>`), opening in a new tab.

### C. Workbench integration
Extend `viva_human_atlas/workbench_viewers.py` with a new viewer
`hra-atlas-browser` (title "HRA Atlas Browser", `applies` when
`viz/atlas/atlas.json` exists), alongside the existing `hra-glb-viewer` for
back-compat. Both `targets` (href) and `launch` callback, mirroring the
existing belt-and-suspenders pattern.

### D. New study + investigation refinement
- New study `studies/hra-atlas-browser/` with `study.yaml` documenting the
  interface deliverable and its data crossing; `viz/atlas/` holds the pack.
- Add it to the `hra-3d` investigation's `studies:` list; update that
  investigation's `lead`/`executive.verdict` to mention the browser.
- Add `investigation: hra-3d` (and the correct parent for the others) as a
  back-reference key to each `study.yaml` for navigability.

## Data flow

```
biomodel_corpus_catalog.json
  └─ load_corpus_catalog → organ_index (50) + organ_to_models (10)
       └─ build_atlas_manifest → atlas.json  ─┐
  └─ build_corpus_coverage → coverage.json  ─┤
                                              ├─→ viz/atlas/  (index.html + viewer.js read them)
config.json (glb overview url, node_field) ──┘
                                              └─→ workbench_viewers → Analyses card → published bundle
```

## Error handling

- Manifest builder: raise if an organ in `organ_to_models` has no
  `organ_index` entry (data drift); skip organs with empty `asset_urls` but
  log them in `summary`.
- Viewer: united-GLB load failure → fall back to dropdown/single-organ with a
  status message; a per-organ GLB load failure surfaces in the status line and
  leaves the selector usable; missing `atlas.json` → clear error, no silent
  blank canvas.

## Testing

- **Python (offline, committed catalog):** `build_atlas_manifest` yields all 50
  organs; each modeled organ's `n_models` equals `len(organ_to_models[uberon])`;
  every `models[].url` is a well-formed `ebi.ac.uk/biomodels/<id>` link;
  `max_models == 36`; zero-model organs present with empty `models`.
- **Shape validation:** emitted `atlas.json` validates against the documented
  schema (required keys, types).
- **Workbench viewer:** `get_viewers` returns the atlas viewer only when
  `viz/atlas/atlas.json` exists.
- No JS test harness exists in the repo today; viewer behavior is verified
  manually + by the JSON-shape tests. (Not introducing a JS harness here.)

## Out of scope

- AS-level (sub-structure) model counts (`fp-as-level-coverage` follow-up).
- Live model *results* on nodes (spatial-linkage's placeholder readout).
- Deep re-homing of existing studies across investigations.
- Fetching new BioModels metadata over the network (names come from the
  committed catalog).
```
