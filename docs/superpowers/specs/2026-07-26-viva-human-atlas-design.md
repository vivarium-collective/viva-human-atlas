# viva-human-atlas — workspace + first investigation design

**Date:** 2026-07-26
**Status:** approved (design), pending implementation plan

## Purpose & long arc

A viva workspace for **Human Reference Atlas / Whole Person Physiome (HRA/WPP)**
modeling. The long arc: ontology-linked BioModels that connect to the **3D
spatial model**, and eventually to FTUs, drugs, and transcriptome signatures
(see `references/sources/hra-wpp-context.md`, from Katy Börner's email).

This first pass is deliberately narrow: a working **fetch-and-compare spine**.
Query BioModels for glucose regulation, run each model on COPASI and Tellurium,
and compare. The HRA/ontology bridge and 3D-spatial connection are explicitly
**deferred** to later investigations.

Builds on the prior [hra-hackathon](https://github.com/vivarium-collective/hra-hackathon)
work (fetch-from-BioModels + `CopasiUTCStep` pattern), generalizing it to a
proper viva workspace with a second engine (Tellurium) and a comparison step.

## Scope decision

First investigation delivers **fetch + dual-sim compare only**. Species
annotation (UniProt/KEGG) and a formal UBERON/CL ontology bridge are out of
scope for this investigation; they are later work that the sources file
prepares for.

## Workspace layout

```
viva-human-atlas/
  workspace.yaml            # schema_version 2; imports pbg-biomodels, pbg-copasi, pbg-tellurium
  viva_human_atlas/
    __init__.py             # register_types + import composites (fires @composite_generator)
    core.py                 # build_core(): registers copasi + tellurium + biomodels types
    biomodels_search.py     # NEW: BioModelsSearchStep — REST search → model IDs
    composites/
      dual_sim_biomodel.py       # one model: SBML → CopasiUTCStep + TelluriumUTCStep → compare
      glucose_regulation_batch.py# search → fan out dual_sim over IDs → aggregate agreement
  investigations/
    glucose-regulation/     # first investigation
  studies/
  references/
    sources/hra-wpp-context.md   # curated from Katy's email
    papers.bib
  docs/superpowers/specs/2026-07-26-viva-human-atlas-design.md
```

## Imports (reference mode)

Following the pattern in `pbg-biomodels/workspace.yaml`:

- **pbg-biomodels** — BioModels by-ID fetch + SED-ML UniformTimeCourse parse +
  `SimulatorComparisonStep`.
- **pbg-copasi** — `CopasiUTCStep`.
- **pbg-tellurium** — `TelluriumUTCStep`.

## Components

### `BioModelsSearchStep` (new)

The `biomodels` Python package is **by-ID only** (`get_all_identifiers`,
`get_file`, `get_metadata`, `get_omex`) — no text search. This Step hits the
BioModels REST search endpoint
(`https://www.ebi.ac.uk/biomodels/search?query=<q>&format=json`), returns the
matching model IDs + light metadata (name, submitter). Parameterized by `query`
(default `"glucose regulation"`) and `max_results`. Downstream steps feed those
IDs to the existing by-ID fetcher in `pbg-biomodels`.

- **Inputs:** `query: string`, `max_results: int`
- **Outputs:** `model_ids: list[string]`, `model_index: map[...]` (id → metadata)
- **Dependency:** `requests` (or urllib); mockable in tests.

### `dual_sim_biomodel` composite

Parameterized by `model_id`. Fetches the SBML once (pbg-biomodels loader), reads
the model's SED-ML UniformTimeCourse, runs the same time course through
`CopasiUTCStep` and `TelluriumUTCStep`, then `SimulatorComparisonStep` compares
the trajectories and emits a per-species agreement metric. Records load/run
failure per engine rather than aborting.

### `glucose_regulation_batch` composite

Runs `BioModelsSearchStep(query="glucose regulation")` → gets IDs → fans out
`dual_sim_biomodel` over them → aggregates a cross-model COPASI-vs-Tellurium
agreement table (and a per-model overlay). Reuses the batch-comparison muscle
already proven in pbg-biomodels (892 models × 5 engines).

## First investigation: `glucose-regulation`

- **Question:** For BioModels matching "glucose regulation," do COPASI and
  Tellurium agree on the time-course dynamics — and which models diverge or fail
  to load in one engine?
- **Baseline composite:** `glucose_regulation_batch`.
- **Study:** runs the batch; produces the cross-model agreement table + per-model
  COPASI/Tellurium overlay.

## Testing

- `BioModelsSearchStep` — unit test with a mocked REST response (no network).
- Composites — smoke test on 1–2 known glucose-regulation models (e.g. a
  Topp β-cell / Bergman minimal-model glucose entry), asserting both engines run
  and the comparison step produces a metric.

## Notes / non-goals

- **New workspace** → created fresh at `~/code/viva-human-atlas` with `git init`;
  no worktree needed (worktree discipline applies to the shared *existing* repos).
  GitHub repo creation under `vivarium-collective` is a later step.
- Out of scope for this investigation: species annotation, UBERON/CL ontology
  bridge, 3D-spatial connection, FTU/CTpop parameterization, drug/transcriptome
  links. These are captured in `references/sources/hra-wpp-context.md` for later.
