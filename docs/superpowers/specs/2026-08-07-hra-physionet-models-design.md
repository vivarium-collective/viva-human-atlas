# Design — PhysioNet as a second model source in the unified HRA model DB

**Date:** 2026-08-07
**Status:** approved (brainstorming), pending implementation plan
**Branch/worktree:** `feat/physionet-harvest` @ `~/code/viva-human-atlas--physionet-models`

## Goal

The atlas viewer today colors HRA organs by how many **BioModels** map to each,
and lists those models (with paper links) when an organ is clicked. Add
**PhysioNet** (<https://physionet.org>) as a second source of "models" mapped to
HRA organs, so the same viewer shows BioModels *and* PhysioNet projects, and the
underlying DB becomes a single, source-agnostic, **reproducibly-harvestable**
model catalog.

Two hard requirements from the requester:

1. **One JSON with all models** — BioModels and PhysioNet live in a single DB
   file, not two.
2. **Reproducible via a composite/study run in the viva workspace** — the
   harvest is a process-bigraph Step exposed as a study baseline, so *running the
   study* reproduces/refreshes the DB. A standalone CLI wraps the same core.

## Scope decisions (locked)

- **What counts as a PhysioNet "model":** *all* published PhysioNet projects,
  organ-mapped by subject matter (ECG→heart, EEG→brain, …). PhysioNet is mostly
  physiological *signal/data* databases plus some software/models; we catalog the
  project **metadata + organ mapping**, not the signal data.
- **Organ mapping:** hybrid — a curated deterministic keyword→organ table first,
  the existing BioModels LLM organ-mapper (`claude-haiku-4-5`) as fallback for the
  unmapped tail. `--no-llm` leaves the tail in an `unmapped` bucket.
- **Access policy:** catalog every project (open / restricted / credentialed) —
  metadata is public — and carry an `access` field so the viewer can badge it. We
  never download credentialed signal data.

**Explicitly out of scope (YAGNI):** downloading or simulating PhysioNet signal
records; per-record/waveform parsing; any credentialed-data retrieval.

## Data source: PhysioNet via DataCite

Every PhysioNet published project carries a DataCite DOI under the prefix
**`10.13026`** (e.g. MIT-BIH Arrhythmia DB = `10.13026/C2F305`). So:

- **Enumeration + metadata in one API:**
  `https://api.datacite.org/dois?query=prefix:10.13026&page[size]=…` (paged)
  returns every project with structured JSON: title, `subjects` (keywords),
  dates, `rightsList` (access/license), creators, description, and the resolvable
  `url` (the `physionet.org/content/<slug>/` landing page).
- **Fallback / keyword enrichment:** DataCite `subjects` can be sparse for older
  records; when a project's keywords are missing, fetch its
  `/content/<slug>/` page and read the topics list (e.g. `arrhythmia, ecg`) and
  abstract. The `/about/database/` page is the human-readable cross-check.

Both enumeration and metadata are therefore machine-readable and offline-cacheable
per project (same pattern BioModels already uses).

## Unified DB — one source-agnostic file

### File

Rename `datasets/biomodel_hra_map.json` → **`datasets/model_hra_map.json`** (honest
once it is mixed-source). Update the ~handful of references: `atlas_pack.py`
(`build_atlas_pack.py` `DB_PATH`), `BiomodelHraMapStep.config_schema` default,
the build scripts, and `scripts/publish_dashboard.sh`. Keep the existing entry
schema; every entry already has a `repository` discriminator and an `identifier`.

### Key generalization

Today `biomodel_hra.load_db/upsert_db/should_process/write_db` key entries by
`biomodel_id`. Generalize them to key by **`identifier`** (the unique landing URL
every entry has — BioModels and PhysioNet alike). `repository` stays as the source
label. This is the single change that lets two sources coexist in one file.

### Non-destructive per-source upsert (critical invariant)

`build_map(source=…)` **loads the whole DB, upserts only rows whose `repository`
matches the source it is harvesting, and preserves all other rows.** Consequence:
rebuilding PhysioNet never drops BioModels rows and vice-versa. This is what makes
the single file safe under independent per-source reruns.

### Entry shape (PhysioNet)

Same schema as BioModels, source-appropriate fields populated, BioModels-only
fields empty:

```
identifier:  "https://physionet.org/content/<slug>/"
repository:  "physionet"
source_id:   "<slug>"                # generic id; mirrors biomodel_id's role
name:        "<title>"
paper_doi:   "10.13026/<...>"
paper_url / paper_pmid: null (unless present)
keywords:    ["ecg", "arrhythmia", ...]
provenance:  {abstract, creators, year, access, license}
organs / functional_tissue_units / cell_types:  from the hybrid mapper
molecular_ids / ontology_ids / taxonomy / gene_symbols / organism: empty
```

(BioModels keeps its existing richer fields; a `source_id` alias equal to
`biomodel_id` is added so downstream code can key generically.)

## Components

### 1. `viva_human_atlas/physionet.py` (mirrors `biomodel_hra.py`)

- `resolve_projects(*, query=None, limit=None) -> list[dict]` — DataCite
  `prefix:10.13026` paged enumeration; returns raw project metadata dicts.
- `fetch_project(slug) -> dict` — cache-first keyword/abstract enrichment from the
  content page when DataCite is sparse.
- `build_entry(project, organ_index, *, no_llm, llm_model, cache_dir) -> dict` —
  produce the source-agnostic record above; per-project error-isolated + cached
  under `.cache/physionet_hra_map/`.

### 2. `viva_human_atlas/physionet_organ_map.py`

- Curated `KEYWORD_TO_ORGAN` table: physiology/clinical keyword → UBERON organ id
  (ecg/arrhythmia→heart, eeg→brain, emg→skeletal muscle, ppg→blood vasculature,
  ehr/mimic/eicu/sepsis→whole-body/multi, gait→lower limb, …). Curated against the
  ~50 GLB-backed HRA organs the viewer knows.
- `map_project_to_organs(project, organ_index, *, no_llm, llm_model) -> dict` —
  deterministic table over keywords+title first; unmapped → reuse
  `biomodel_hra`'s LLM organ-mapper; results cached so reruns are stable.

### 3. Source registry + `viva_human_atlas/model_harvest.py`

A small registry maps source name → `{list_fn, build_entry_fn, repository}`:

```
SOURCES = {
  "biomodels": {list: biomodel_hra.resolve_ids,     build: biomodel_hra.build_entry, repo: "biomodels"},
  "physionet": {list: physionet.resolve_projects,   build: physionet.build_entry,    repo: "physionet"},
}
```

`harvest(sources, *, out, query, limit, no_llm, force, progress) -> summary` loops
the requested sources; each does an incremental, non-destructive upsert into the
shared DB; returns a per-source `{resolved, new, updated, skipped, errors}` plus a
final total. Adding a 3rd DB later = one module + one registry line.

### 4. `ModelHarvestStep(Step)` — the viva-native reproducibility hook

A source-agnostic Step generalizing `BiomodelHraMapStep`. `config_schema`:
`{db_path, sources (list), query, limit, no_llm, force, build_if_missing,
analysis_out_dir}`. `update()` calls `model_harvest.harvest(...)` (or cache-or-load
when `build_if_missing=false`), writes the analysis copy, and emits
`{db_path, n_models, per_source_counts, summary}` as observables. `BiomodelHraMapStep`
is retained as a thin `sources=["biomodels"]` alias for the existing study, or
that study is repointed at `ModelHarvestStep`.

### 5. Study `model-harvest` — running it *is* the harvest

A study whose baseline is:

```yaml
baseline:
  - name: baseline
    step: "local:viva_human_atlas.model_harvest.ModelHarvestStep"
    params:
      db_path: datasets/model_hra_map.json
      sources: [biomodels, physionet]
      build_if_missing: false      # network-free reproduce from committed DB
```

Running the study in the workbench loads/refreshes the unified DB and reports
coverage per source — the reproducible, provenanced viva path. (Existing
`biomodel-hra-map` study stays valid; a sibling `physionet` study or a widened
`model-harvest` study surfaces the second source.)

### 6. `scripts/harvest_models.py` — thin CLI over the same core

```
python scripts/harvest_models.py                    # harvest new from every source
python scripts/harvest_models.py --source physionet  # one source
python scripts/harvest_models.py --force            # re-fetch all
python scripts/harvest_models.py --no-llm --limit 50 # cheap/offline dev run
```

Incremental by construction: `resolve_*` lists what is *currently posted*
upstream; `should_process` skips identifiers already in the DB; per-model
upsert + atomic write; per-model errors isolated. A plain rerun harvests only
newly-posted models — the "harvest new models as they get posted" requirement.
`scripts/build_biomodel_hra_map.py` becomes a thin alias (or `--source biomodels`).

### 7. Atlas viewer — source-aware (`atlas_pack.py` + viewer assets)

The one place existing code needs a small refactor: `atlas_pack` currently
hardcodes `biomodels_url(biomodel_id)` and keys models on `biomodel_id`. Change:

- Read the single `model_hra_map.json`; build model entries that carry their own
  `repository`, `url`, `name`, and generic `source_id` (no per-source URL
  assumption).
- Union `organ_to_models` across sources; organ color = **total** model count.
- Viewer (`assets/hra_glb_viewer/` + atlas browser): per-model **source badge**
  (BioModels / PhysioNet) with the correct link, and a **source filter** toggle
  (All / BioModels / PhysioNet). Optional per-organ count breakdown by source.

## Data flow

```
{BioModels ids, DataCite prefix:10.13026}
   → per-source build_entry (organ mapping: table → LLM fallback)
   → model_harvest.harvest  (incremental, non-destructive upsert by identifier)
   → datasets/model_hra_map.json          (ONE file, all sources)
   → atlas_pack.build_and_write_atlas     (source-aware union)
   → studies/<atlas>/viz/atlas/atlas.json → 3D viewer (badged + filterable)
```

Reproducible three ways over the *same* core: the `model-harvest` **study**
(viva-native, provenanced), the `harvest_models.py` **CLI**, and the
`ModelHarvestStep` **Step** embedded in any composite.

## Testing

- Offline (`-m "not network"`): keyword→organ table mapping; `physionet.build_entry`
  schema shape; **non-destructive upsert invariant** (harvest PhysioNet, assert
  BioModels rows untouched, and vice-versa); atlas-manifest union across two
  sources; DB key generalization (load/upsert/should_process by `identifier`).
- Network (`-m network`): DataCite `prefix:10.13026` returns projects; a known DOI
  (e.g. `10.13026/C2F305`, MIT-BIH) resolves to expected title/keywords and
  organ-maps to heart.

## Migration / compatibility notes

- Rename is a git `mv` + reference updates; the committed BioModels rows are
  carried into `model_hra_map.json` unchanged (identifier-keyed), so the existing
  atlas/coverage studies keep working.
- `build_if_missing: false` everywhere by default → the workspace stays
  network-free on reproduce; live harvesting is opt-in (`--force` / study param).
- Publish (`scripts/publish_dashboard.sh`) copies the viewer pack as today; the
  new badge/filter is client-side JS in the committed viewer assets, so it works
  in the static gh-pages bundle.
