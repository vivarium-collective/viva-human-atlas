# viva-human-atlas — instructions

A [process-bigraph](https://github.com/vivarium-collective/process-bigraph) /
Vivarium workspace for **Human Reference Atlas (HRA) / Whole Person Physiome**
modeling — the open seed of **Aim 2** of the *DynXR* proposal (see
`references/sources/dynxr-proposal.md`). It links curated **BioModels** to HRA
anatomy/ontologies and runs them on interoperable engines.

## What's here

**Investigations**
- **`glucose-regulation`** — search BioModels for "glucose regulation", run each
  model on **COPASI** and **Tellurium**, compare trajectories (all-pairs nRMSE).
- **`hra-integration`** — pull HRA datasets/knowledge via the live **HRA CCF
  API** (reference organs keyed by **Uberon** + 3D assets, cell types,
  anatomical structures), and build **biomodel Digital Objects**: each glucose
  model annotated with an HRA Uberon organ term, plus the inverse
  **organ → models** index.

**Studies** (one per composite — each demonstrates its Step/composite loads)
- `glucose-regulation`, `glucose-biomodel-do`, `hra-reference-organs`,
  `hra-cell-types`, `hra-anatomical-structures`.

## Run it locally

Needs the sibling repos `../pbg-biomodels`, `../pbg-copasi`, `../pbg-tellurium`.

```bash
uv venv && uv pip install -e .
.venv/bin/python -m pytest -m "not network"   # offline suite
.venv/bin/python -m pytest -m network         # live BioModels + HRA API
```

Direct calls:

```bash
# COPASI vs Tellurium on glucose-regulation models
.venv/bin/python -c "from viva_human_atlas.composites.glucose_regulation import run_glucose_regulation; print(run_glucose_regulation(max_results=5))"

# biomodel Digital Objects + organ->models index
.venv/bin/python -c "from viva_human_atlas.biomodel_do import build_biomodel_do_catalog; import json; print(json.dumps(build_biomodel_do_catalog(max_results=10)['organ_to_models'], indent=2))"
```

## Serve / publish the workbench

```bash
vivarium-workbench serve --workspace .        # live authoring UI
./scripts/publish_dashboard.sh --push         # static read-only bundle -> gh-pages
```

Read-only showcase: https://vivarium-collective.github.io/viva-human-atlas/dashboard/

## Key modules

- `viva_human_atlas/hra_api.py` — HRA CCF-API client + Steps.
- `viva_human_atlas/biomodels_search.py` — BioModels REST text search.
- `viva_human_atlas/biomodel_do.py` — biomodel Digital Objects (Uberon organ annotation + organ→models index).
- `viva_human_atlas/composites/` — `@composite_generator` entries wired into studies.

## Conventions

- A study's `baseline.composite` must be the **registered generator id**
  (`viva_human_atlas.composites.<module>.<generator-name>`), not the Python
  function name — otherwise the workbench reports "composite not found".
- Unit tests never hit the network (inject fakes / monkeypatch); live paths are
  marked `@pytest.mark.network`.
