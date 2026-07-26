# HRA API integration Implementation Plan

> **For agentic workers:** implement task-by-task, TDD, commit per task.

**Goal:** Add Vivarium (process-bigraph) Steps that pull datasets/knowledge from the live HRA API, plus the concrete biomodel↔HRA integration (per-model **biomodel DO** annotated with an Uberon organ + an organ→models index), plus studies that demonstrate everything loads.

**Architecture:** A thin HRA CCF-API client + Steps; the biomodel-DO layer reuses the Task-2 BioModels search and the HRA reference-organ set (Uberon) to annotate glucose models and build the inverse organ index; composite generators wrap each Step so studies can run them. This realizes the DynXR proposal's Aim 2 T2.1/T1.1 (see `references/sources/dynxr-proposal.md`).

**Tech Stack:** Python 3.12, process-bigraph, `requests`, pytest. Reuses `viva_human_atlas.biomodels_search`.

## Global Constraints

- HRA API base: `HRA_API = "https://apps.humanatlas.io/api"`. Verified JSON endpoints:
  - `/v1/reference-organs` → **list** of objects; each has `representation_of` (Uberon IRI e.g. `http://purl.obolibrary.org/obo/UBERON_0014455`), `@id` (slug e.g. `.../ref-organ/adipose-female/v1.0#primary`), `sex`, `object.file` (GLB asset URL).
  - `/v1/cell-type-term-occurences` → **dict** `{CL_iri: count}`.
  - `/v1/ontology-term-occurences` → **dict** `{term_iri: count}` (anatomical structures).
- All client fns take an injectable `_get` (a `requests.get`-compatible callable) defaulting to `requests.get`; unit tests inject fakes and MUST NOT hit the network. Live tests are marked `@pytest.mark.network`.
- IRI→CURIE: `http://purl.obolibrary.org/obo/UBERON_0014455` → `UBERON:0014455`; `.../CL_0000057` → `CL:0000057`. Write one helper `iri_to_curie(iri) -> str` (last path segment, first `_`→`:`).
- Git: commit with `git -c user.name="Eran Agmon" -c user.email="agmon.eran@gmail.com" ...`, trailer `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- Run tests via `.venv/bin/python -m pytest`. Offline suite = `-m "not network"`.

---

### Task A: HRA API client + Steps (`viva_human_atlas/hra_api.py`)

**Produces (later tasks + studies depend on these exact names):**
- `iri_to_curie(iri: str) -> str`
- `fetch_reference_organs(base_url=HRA_API, *, _get=None) -> list[dict]` — each `{"ref_organ_id": str(@id), "organ": <slug w/o -male/-female>, "uberon": <CURIE>, "sex": str, "asset_url": str|None}`.
- `fetch_cell_type_terms(base_url=HRA_API, *, _get=None) -> list[dict]` — `[{"cl": <CURIE>, "count": int}]`, sorted by count desc.
- `fetch_anatomical_structure_terms(base_url=HRA_API, *, _get=None) -> list[dict]` — `[{"term": <CURIE or iri>, "count": int}]`, sorted desc.
- Steps (all `Step`, `inputs()->{}`, config `{"base_url":"string"}`):
  - `HRAReferenceOrgansStep` → `outputs()={"reference_organs":"list[tree]"}`, `update` returns `{"reference_organs": fetch_reference_organs(self.config.get("base_url", HRA_API))}`.
  - `HRACellTypesStep` → `outputs()={"cell_types":"list[tree]"}`.
  - `HRAAnatomicalStructuresStep` → `outputs()={"anatomical_structures":"list[tree]"}`.

**Slug parsing for `organ`:** from `@id` take the path segment after `ref-organ/` (before the next `/`), strip a trailing `-male`/`-female`. e.g. `adipose-female` → `adipose`; `blood-vasculature-male` → `blood-vasculature`.

- [ ] Write `tests/test_hra_api.py`: (1) `iri_to_curie` on UBERON + CL iris; (2) `fetch_reference_organs` with a fake `_get` returning a 2-item list (one female adipose w/ Uberon, one male kidney) → asserts parsed `organ`/`uberon`/`sex`/`asset_url`; (3) `fetch_cell_type_terms` with fake dict `{CL_iri: n}` → sorted CURIE list. Run (fail).
- [ ] Implement `hra_api.py`. Run (pass).
- [ ] Commit `feat: HRA CCF-API client + Steps (reference organs, cell types, anatomical structures)`.

---

### Task B: BioModels detailed search + biomodel DO (`viva_human_atlas/biomodel_do.py`)

**Modify** `viva_human_atlas/biomodels_search.py`: add
`search_biomodels_detailed(query, max_results=25, *, _get=None) -> list[dict]` returning `[{"id": m["id"], "name": m.get("name","")}]` (same endpoint/params as `search_biomodels`; keep `search_biomodels` unchanged).

**Produces (`biomodel_do.py`):**
- `ORGAN_SYNONYMS: dict[str, list[str]]` — maps organ key → keyword synonyms, at least: pancreas→[pancrea, islet, beta cell, β-cell, insulin, glucagon]; liver→[liver, hepatic, hepatocyte]; kidney→[kidney, renal, nephron]; adipose→[adipose, adipocyte, fat tissue]; muscle→[skeletal muscle, myocyte, myotube]; intestine→[intestine, intestinal, gut, enteric]; blood→[blood, plasma, circulation]. (Transparent gap-filling per proposal T2.4.)
- `build_organ_index(reference_organs=None, *, _get=None) -> dict` — `{organ_key: {"uberon": CURIE, "sexes":[...], "asset_urls":[...]}}` deduped across sex; fetches via `hra_api.fetch_reference_organs` if `reference_organs` is None. Match each reference organ's `organ` slug to an `ORGAN_SYNONYMS` key when possible (else key = slug).
- `annotate_biomodel(biomodel_id, name, organ_index, *, extra_text="") -> dict` — scan `f"{name} {extra_text}".lower()` for each organ's synonyms (and the organ key); return biomodel DO `{"biomodel_id":..., "name":..., "organs":[{"organ":key,"uberon":curie} ...], "provenance":{"source":"biomodels","annotation":"synonym-match@HRA-reference-organs"}}`.
- `build_biomodel_do_catalog(query="glucose regulation", max_results=25, *, _get_search=None, _get_hra=None) -> dict` — `search_biomodels_detailed` for `[{id,name}]`; `build_organ_index`; annotate each → returns `{"biomodel_dos":[...], "organ_index":{...}, "organ_to_models": {uberon: [biomodel_id,...]}}` (organ_to_models built by inverting the DOs).
- `BiomodelDOCatalogStep(Step)` — config `{"query":"string","max_results":"integer"}`, `inputs()->{}`, `outputs()->{"biomodel_dos":"list[tree]","organ_to_models":"tree"}`, `update` calls `build_biomodel_do_catalog`.

- [ ] Write `tests/test_biomodel_do.py` (offline, all mocked): (1) `build_organ_index` from a fake reference-organ list → pancreas/liver keys w/ Uberon; (2) `annotate_biomodel("BIOMD...","Topp2000 beta-cell insulin glucose", idx)` → organs include pancreas; (3) `build_biomodel_do_catalog` with fake `_get_search` (2 models: one "hepatic glucose", one "pancreatic islet") and fake `_get_hra` → asserts 2 DOs and `organ_to_models` maps liver-uberon→[hepatic id], pancreas-uberon→[islet id]. Run (fail).
- [ ] Implement `search_biomodels_detailed` + `biomodel_do.py`. Run (pass).
- [ ] Commit `feat: biomodel Digital Objects — Uberon organ annotation + organ->models index`.

---

### Task C: Composite generators + investigation + studies + demonstrate-loading

**Create `viva_human_atlas/composites/hra_steps.py`** — three `@composite_generator`s (`hra-reference-organs`, `hra-cell-types`, `hra-anatomical-structures`) each returning a `{"state": {...}, "run_steps_on_init": True}` doc wiring the corresponding Step's output into a store + a `RAMEmitter`. Use the superpowers import shim for `composite_generator`. Follow the state/emitter shape used in `pbg_biomodels/composites/compare_simulators.py` (`_type: step`, `address: local:<StepName>`, `inputs`/`outputs` to one-segment stores, emitter with `emit` schema). Address form: `local:HRAReferenceOrgansStep` (build_core registers local Steps by short name).

**Create `viva_human_atlas/composites/biomodel_do_composite.py`** — `@composite_generator(name="glucose-biomodel-do", parameters={query, max_results})` wiring `BiomodelDOCatalogStep` → stores `biomodel_dos`, `organ_to_models` → emitter.

**Update** `viva_human_atlas/composites/__init__.py` to import the two new modules (keep the existing `glucose_regulation` import).

**Create** `investigations/hra-integration/investigation.yaml` (schema_version 2; question: "Can we pull HRA datasets/knowledge via the API and link glucose BioModels to HRA anatomy?"; studies list below).

**Create studies** (schema_version 4; each `baseline: [{name: baseline, composite: <dotted generator fn>}]`, non-empty; `simulation_status: ran` after the load test confirms):
- `studies/hra-reference-organs/study.yaml` → composite `viva_human_atlas.composites.hra_steps.build_hra_reference_organs`
- `studies/hra-cell-types/study.yaml` → `...hra_steps.build_hra_cell_types`
- `studies/hra-anatomical-structures/study.yaml` → `...hra_steps.build_hra_anatomical_structures`
- `studies/glucose-biomodel-do/study.yaml` → `...biomodel_do_composite.build_glucose_biomodel_do`

**Create `tests/test_hra_studies_load.py`** — demonstrate-loading:
- Offline (mocked): for each generator, monkeypatch the underlying `fetch_*` / catalog functions on their module to return small fixtures, build the composite via `build_core()`, run it, `gather_emitter_results`, and assert the store is non-empty (e.g. ≥1 reference organ; ≥1 cell type; catalog has ≥1 biomodel DO with an organ). Assert all four generators are discovered by `discover_generators()`.
- `@pytest.mark.network`: build+run `hra-reference-organs` against the real API and assert ≥50 organs loaded (the HRA has 77) and each has a `uberon` CURIE; build+run `glucose-biomodel-do` live and assert ≥1 DO maps to an organ.

- [ ] Write `tests/test_hra_studies_load.py` (offline parts). Run (fail).
- [ ] Implement the generators, `__init__` update, investigation + studies. Run offline (pass).
- [ ] Run the network tests once (`-m network`) to confirm real HRA loads; record counts in the commit message.
- [ ] Commit `feat: HRA-integration investigation + studies demonstrating dataset/DO loading`.

---

## Self-Review checklist
- Coverage: HRA API Steps (A), biomodel DO + organ index [Both] (B), studies demonstrating load (C). ✔
- No network in unit tests (injected `_get`/monkeypatch); live paths behind `network` marker. ✔
- Reuses Task-2 search + Task-A reference organs; no duplicated comparison logic. ✔
- Type consistency: `iri_to_curie`, `fetch_reference_organs` dict keys, `build_organ_index`/`annotate_biomodel`/`build_biomodel_do_catalog` signatures used consistently across B and C. ✔
