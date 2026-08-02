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

🧊 **3D coverage viewer (HRA liver, colored by model coverage):**
https://vivarium-collective.github.io/viva-human-atlas/dashboard/studies/model-coverage-3d/viz/hra/index.html
(Also registered as an "HRA Organ Viewer" analysis tool — launchable from the
Analyses tab in a live `vivarium-workbench serve`.)

🧭 **HRA Atlas Browser (organ selector, model-count gradient, BioModels links):**
https://vivarium-collective.github.io/viva-human-atlas/dashboard/studies/hra-atlas-browser/viz/atlas/index.html
— pick any of the 50 GLB-backed HRA organs (or compose them with "All modeled"),
see regions colored by associated model count (viridis), and click through to
BioModels. The manifest is the union of name-synonym and SBML-annotation
matching (167 models across 14 organs). Built by `scripts/build_atlas_pack.py`;
also launchable from the Analyses tab as "HRA Atlas Browser".

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
  - **Annotation-based organ matching:** Extract SBML **MIRIAM annotations**
    from BioModels and cross-reference anatomy via a **BTO → Uberon organ
    crosswalk**. Two studies compare annotation-based vs. name-synonym matching:
    annotation matching tags 114 models across 14 organs; name-synonym tags 82
    across 10 organs. Combined, they cover 167 models, adding 85 models and 4
    organs (lymph node, ovary, spleen, urinary bladder). Name-synonym still wins
    some organs (e.g., pancreas). Most BioModels annotate anatomy via BTO terms
    rather than direct Uberon links. (See `studies/annotation-organ-matching`
    and `studies/annotation-recall-gain`.)

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
