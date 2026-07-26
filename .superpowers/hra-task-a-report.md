# Task A report — HRA API client + Steps

**Branch:** `feat/hra-api-integration` (no worktree used, per instructions — repo is not a git worktree
setup here; worked directly on the checked-out branch).

## What was built

`viva_human_atlas/hra_api.py`:

- `HRA_API = "https://apps.humanatlas.io/api"`
- `iri_to_curie(iri: str) -> str` — takes the last `/`-segment of the IRI and replaces the first
  `_` with `:`. E.g. `http://purl.obolibrary.org/obo/UBERON_0014455` → `UBERON:0014455`.
- `fetch_reference_organs(base_url=HRA_API, *, _get=None) -> list[dict]` — GETs
  `{base_url}/v1/reference-organs` (a JSON list), returns
  `[{"ref_organ_id", "organ", "uberon", "sex", "asset_url"}]`. `organ` is derived from the `@id`
  path segment after `ref-organ/` (before the next `/`), with a trailing `-male`/`-female` suffix
  stripped (helper `_organ_from_id`). `asset_url` comes from `item["object"]["file"]`.
- `fetch_cell_type_terms(base_url=HRA_API, *, _get=None) -> list[dict]` — GETs
  `{base_url}/v1/cell-type-term-occurences` (a JSON dict `{CL_iri: count}`), returns
  `[{"cl": CURIE, "count": int}]` sorted by count descending.
- `fetch_anatomical_structure_terms(base_url=HRA_API, *, _get=None) -> list[dict]` — GETs
  `{base_url}/v1/ontology-term-occurences` (a JSON dict `{term_iri: count}`), returns
  `[{"term": CURIE, "count": int}]` sorted by count descending.
- `HRAReferenceOrgansStep`, `HRACellTypesStep`, `HRAAnatomicalStructuresStep` — `Step` subclasses,
  `config_schema = {"base_url": "string"}`, empty `inputs()`, each `outputs()` returns
  `{"<field>": "list[tree]"}`, `update` calls the matching fetch function with
  `self.config.get("base_url", HRA_API)`. Follows the existing `BioModelsSearchStep` pattern in
  `viva_human_atlas/biomodels_search.py` exactly (config_schema, empty inputs, `update` shape).

All four `_get`-injectable functions default to the real `requests.get` (imported lazily inside a
`_default_get()` helper, mirroring `biomodels_search.py`'s lazy `import requests`) so no network
call happens at import time and unit tests never touch the network.

## TDD sequence

1. Wrote `tests/test_hra_api.py` with the plan's 3 cases (plus a 4th mirroring case for
   anatomical-structure terms, since the plan's Global Constraints call for all three fetch fns and
   the third — anatomical structures — has the same dict-sorting shape as cell types, so I covered
   it too for symmetry / regression safety):
   - `test_iri_to_curie_uberon_and_cl`
   - `test_fetch_reference_organs_parses_slug_uberon_sex_asset` (2-item fake list: female adipose
     w/ Uberon + asset, male kidney w/ Uberon + asset)
   - `test_fetch_cell_type_terms_sorted_desc_by_count`
   - `test_fetch_anatomical_structure_terms_sorted_desc_by_count`
2. Ran — confirmed collection failure (`ModuleNotFoundError: No module named 'viva_human_atlas.hra_api'`).
3. Implemented `hra_api.py`.
4. Ran — all 4 passed.
5. Ran full offline suite (`-m "not network"`) — **10 passed, 2 deselected** (the 2 deselected are
   pre-existing network tests in the repo, unrelated to this task).

## Live sanity check (not committed to the test suite)

Ran `fetch_reference_organs()`, `fetch_cell_type_terms()`, `fetch_anatomical_structure_terms()`
directly against the real HRA API (network available on this machine):

- **`fetch_reference_organs()`: 81 organs** loaded (plan mentions "the HRA has 77" as a rough
  figure for a later live-test threshold of ≥50 — 81 comfortably clears that).
  Both `sex` values (`Male`, `Female`) present. First item (adipose-female) and last item
  (uterus-female) parsed correctly, e.g.
  `{'ref_organ_id': '...ref-organ/adipose-female/v1.0#primary', 'organ': 'adipose',
  'uberon': 'UBERON:0014455', 'sex': 'Female', 'asset_url': '...3d-vh-f-adipose.glb'}`.
- **Data quirk found (not a code bug):** 12/81 reference organs use **FMA** ontology IDs instead of
  Uberon in `representation_of` (e.g. `epiploic-appendage-of-transverse-colon`, `knee-*-left/right`,
  `mammary-gland-female-left/right`, `palatine-tonsil-*-left/right`). `iri_to_curie` is spec'd
  generically ("last path segment, first `_`→`:`"), so for an IRI like
  `.../fma/fma15046` (no underscore) it correctly passes through as `fma15046` rather than
  `UBERON:...` — this is correct behavior per the Task A spec, just a heads-up that the `uberon`
  field is not *always* a `UBERON:` CURIE in the live data. **Flag for Task C:** its live test
  asserts "each has a uberon CURIE" — that assertion will need to tolerate/filter these 12 FMA-keyed
  organs, or the assertion should be scoped to organs with `uberon.startswith("UBERON:")`.
- **`fetch_cell_type_terms()`: 149 terms**, correctly sorted descending, e.g. top entry
  `{'cl': 'CL:0000000', 'count': 2762}`.
- **`fetch_anatomical_structure_terms()`: 288 terms**, correctly sorted descending, e.g. top entry
  `{'term': 'UBERON:0013702', 'count': 2762}`.

This live check was run ad hoc via `.venv/bin/python -c "..."` and was **not** added to the
committed test file (per instructions — unit tests stay mocked/offline; a `@pytest.mark.network`
live test for this module is left for Task C's `test_hra_studies_load.py`, which the plan already
scopes to include a live `hra-reference-organs` composite run).

## Files touched

- `viva_human_atlas/hra_api.py` (new)
- `tests/test_hra_api.py` (new)

## Commit

See commit hash in the final response.
