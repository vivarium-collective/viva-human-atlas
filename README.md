# viva-human-atlas

A [process-bigraph](https://github.com/vivarium-collective/process-bigraph) /
Vivarium research workspace for **Human Reference Atlas (HRA) / Whole Person
Physiome (WPP)** modeling — the open seed of **Aim 2** of the *DynXR: Integrating
Biomedical Datasets with Mechanistic Biosimulations through the Human Reference
Atlas* proposal. It links curated mechanistic **BioModels** to HRA anatomy and
ontologies, runs them on interoperable simulation engines, and emits
ontology-linked outputs that can connect to the HRA's 3D reference organs.

📊 **Read-only workbench (showcase):**
https://vivarium-collective.github.io/viva-human-atlas/dashboard/

## Investigations

- **`glucose-regulation`** — query BioModels for "glucose regulation", run each
  model on **COPASI** and **Tellurium**, and compare trajectories (all-pairs
  nRMSE). Reuses the multi-simulator comparison from
  [pbg-biomodels](https://github.com/vivarium-collective/pbg-biomodels).
- **`hra-integration`** — pull HRA datasets/knowledge via the live **HRA CCF
  API** (reference organs keyed by **Uberon** + 3D assets, cell types,
  anatomical structures), and produce per-model **biomodel Digital Objects**:
  each glucose model annotated with an HRA Uberon organ term, plus the inverse
  **organ → models** index. This is the ontology bridge toward the 3D spatial
  model.

## Layout

```
viva_human_atlas/
  hra_api.py            # HRA CCF-API client + process-bigraph Steps
  biomodels_search.py   # BioModels REST text search
  biomodel_do.py        # biomodel Digital Objects (Uberon organ annotation + organ->models index)
  composites/           # @composite_generator entries (glucose-regulation, hra-*, glucose-biomodel-do)
investigations/         # glucose-regulation, hra-integration
studies/                # one study per composite; demonstrate loading
references/sources/     # DynXR proposal extraction + HRA/WPP context + curated references
```

## Develop

```bash
uv venv && uv pip install -e .          # needs sibling repos ../pbg-biomodels, ../pbg-copasi, ../pbg-tellurium
.venv/bin/python -m pytest -m "not network"   # offline suite
.venv/bin/python -m pytest -m network         # live BioModels + HRA API
```

Run the comparison directly:

```bash
.venv/bin/python -c "from viva_human_atlas.composites.glucose_regulation import run_glucose_regulation; print(run_glucose_regulation(max_results=5))"
```

## License

Open source (see `LICENSE`). Part of the [Vivarium Collective](https://github.com/vivarium-collective).
