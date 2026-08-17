# Re-home the Physiome model source onto the pmr3 API

**Date:** 2026-08-17
**Status:** Approved design (pending spec review)
**Branch:** `feat/physiome-pmr3-api`

## Problem

The Physiome Model Repository (PMR) source currently harvests models by
scraping PMR's legacy Plone category-listing HTML (`physiome.py`). This has
three limits:

1. **Incomplete corpus.** Only models filed under 21 hand-listed categories are
   reached (570 rows). PMR's master `/exposure` listing has ~1108 exposures;
   ~538 are outside our category list and unreachable (the Plone listing pages
   carry no titles, and exposure pages carry no category back-link).
2. **Coarse organ signal.** The 21 categories are a blunt anatomical signal
   (`metabolism`, `endocrine` too coarse to place). Author-supplied keywords are
   far richer but invisible to the scrape.
3. **Fragile + expensive enrichment.** DOIs are recovered by fetching and
   regex-scraping each exposure's HTML page.

A new PMR backend (preview frontend `https://preview.models.physiomeproject.org/`,
API `https://pmr3.demo.physiomeproject.org/`, OpenAPI at `/api-docs/openapi.json`)
exposes all of this as structured JSON.

## What the pmr3 API gives us (verified live)

- `GET /api/index` → available index kinds, incl. `exposure_id`,
  `exposure_alias`, `cellml_keyword`, `citation_id`, `model_author`.
- `GET /api/index/exposure_id` → **978** exposure-id terms = the complete
  exposure set.
- `GET /api/index/exposure_id/{id}` → that exposure's records (one per CellML
  file). Each record's `data` carries: `_title`, `_brief` (abstract),
  `cellml_keyword` (author keywords), `citation_id` (e.g.
  `urn:miriam:pubmed:19828503`), `citation_author_family_name`, `aliased_uri`
  (`/exposure/<alias>/<file>.cellml`), `exposure_alias`, `created_ts`,
  `commit_authored_ts`, `model_author`.
- `GET /api/citations` → **413** citations keyed by `urn:miriam:pubmed:<id>`,
  each with `title`, `journal`, `authors`, `issued` (year), pages, volume.
- `GET /api/index/cellml_keyword` → the full author-keyword vocabulary
  (hundreds of terms, many anatomy/cell-type bearing: `brain`, `bone`,
  `beta cell`, `adrenal cortex`, `collecting duct`, `atrial myocyte`,
  `cerebral arteries`, `chromaffin cell`, ...).

**ID compatibility:** 568/570 existing physiome `source_id`s already equal the
new API's `exposure_alias` hashes. So the alias is our stable canonical id; a
rebuild enriches the same models rather than inventing new ones (≈2 stale
exposures absent from the new backend are dropped).

## Design

### Decisions (approved 2026-08-17)

- **D1 — Full replace.** pmr3 API is the sole physiome source; the Plone
  scraper is removed. No dual path.
- **D2 — Curated keyword→anatomy/cell-type table.** Hand-built mapping over the
  PMR keyword vocab is the primary organ signal (the whole point of using
  author keywords). Existing category/keyword/EP-refine layers stay as
  fallbacks; LLM stays last-resort/off-by-default.
- **D3 — Configurable base URL** (`PMR3_API_BASE` env override, default the demo
  host) so we swap to production when it ships. Offline tests run against
  recorded JSON fixtures, never the live host.

### Component 1 — `physiome.py` rewrite (pmr3 API client)

Replace the Plone scraper. New public surface (keeps the `model_harvest`
registry contract: `resolve_exposures`, `build_entry`):

- `_BASE` / `api_base()` — default `https://pmr3.demo.physiomeproject.org`,
  overridable via `PMR3_API_BASE`.
- `list_exposure_ids(*, _get) -> list[str]` — `GET /api/index/exposure_id`.
- `fetch_exposure(id, *, cache_dir, _get) -> dict | None` — `GET
  /api/index/exposure_id/{id}`; aggregate the exposure's file records into one
  dict: `slug` (= `exposure_alias`), `identifier`
  (`{PMR_SITE}/exposure/<alias>`), `name` (first `_title`), `abstract` (first
  `_brief`), `keywords` (union of `cellml_keyword` across files, lowercased,
  deduped), `citation_ids` (union), `authors` (union of
  `citation_author_family_name`), `created_ts`, `filename` (primary
  `.cellml`). Cache the raw JSON per id under
  `.cache/physiome_pmr3/<id>.json`.
- `resolve_exposures(*, query=None, limit=None, _get, _ids=None) -> list[dict]`
  — enumerate ids, fetch each (cached), return exposure dicts. `query` = title
  substring filter; `limit` caps.
- `load_citations(*, cache_dir, _get) -> dict` — `GET /api/citations`, cached
  once per harvest to `.cache/physiome_pmr3/citations.json`.
- `resolve_cellml_url(identifier, *, _get)` — kept (rewire to the
  `aliased_uri`→rawfile path or the public site's `<file>.cellml`; runnable
  URL for OpenCOR). Non-critical to the count; keep behavior.

`PMR_SITE = https://models.physiomeproject.org` remains the human-facing model
URL base (identifier + paper fallback), independent of the API host.

### Component 2 — Citation enrichment (replaces `fetch_doi`)

`build_entry(exposure, organ_index, *, citations, no_llm, ...)` resolves the
exposure's `citation_ids` against the `load_citations()` map:

- `paper_pmid` ← numeric id parsed from `urn:miriam:pubmed:<id>` (first
  non-empty).
- `paper_url` ← `https://pubmed.ncbi.nlm.nih.gov/<pmid>/` when a pmid exists,
  else the exposure identifier.
- `provenance.citation` ← `{title, journal, year, authors}` from the resolved
  Citation (year from `issued`).
- `provenance.abstract` ← exposure `_brief`.

The old per-page DOI scrape (`fetch_doi`, `_DOI_RE`) is removed.

### Component 3 — `physiome_organ_map.py` extension (curated keyword table)

Add `KEYWORD_TO_ORGAN_KEYS` and `KEYWORD_TO_CELLTYPE` tables mapping PMR author
keywords → HRA organ keys / cell-type terms. Resolution order in
`map_exposure_to_organs` becomes:

1. CellML RDF anatomy annotation (existing, high confidence) — unchanged.
2. **NEW: author-keyword table** (medium-high). Union organ keys from
   `KEYWORD_TO_ORGAN_KEYS` over the exposure's keywords; collect cell types
   from `KEYWORD_TO_CELLTYPE`.
3. Category taxonomy (existing) — now a fallback, still EP-title-refined.
4. Title physiology-keyword table (existing).
5. LLM over title (existing, off by default).

Keyword tables are keys into `organ_index` (resolved to UBERON live, never
hardcoded ids), mirroring `CATEGORY_TO_ORGAN_KEYS`. `mapping_method` gains
`"keyword_annotation"` for the new path. Cell types flow into the record's
`cell_types` field.

Initial curated coverage (extend iteratively): heart (`cardiac*`,
`atrial/ventricular myocyte`, `sinoatrial`, `purkinje fibre`), brain
(`neuron*`, `substantia nigra`, `hippocamp*`, `cortical`, `astro*`), pancreas
(`beta cell`, `islet`, `insulin secretion`), kidney (`collecting duct`,
`nephron`, `proximal tubule`, `glomerul*`), liver (`hepato*`, `hepatic`),
bone (`bone`, `osteo*`), adrenal (`adrenal*`, `chromaffin`), thyroid, lung
(`airway`, `alveol*`), intestine (`enteric`, `smooth muscle`, `jejun*`),
skeletal muscle, vasculature (`arter*`, `capillary`). Cell types: `beta cell`,
`chromaffin cell`, `cardiac myocyte`, `neuron`, etc.

### Component 4 — Rebuild wiring in `model_harvest.py`

`upsert_db` keys on `identifier` (a URL); the new identifier scheme differs
from the old Plone URLs, so a plain rerun would duplicate. Add a per-source
**rebuild**: before harvesting a source flagged for rebuild, drop that source's
existing rows from the in-memory DB, then insert fresh.

- `harvest(..., rebuild: Sequence[str] | bool = False)` — for each named source
  in `rebuild` (or all if `True`), remove `{k:v for ... v['repository']==name}`
  before its loop; `should_process` then treats every row as new.
- Registry entry for `physiome` updated: `list_fn` → `resolve_exposures`;
  `entry_fn` → `build_entry`; `id_of` → `exp["identifier"]`. Citations are
  loaded once per harvest (only when `physiome` is in the source set) and passed
  through the existing `**k` kwargs of every `entry_fn` call as `citations=...`;
  the biomodels/physionet `entry_fn` lambdas already accept and ignore extra
  kwargs, so no other source is affected.
- `ModelHarvestStep` gains a `rebuild` config field; the `model-harvest` study
  and `scripts/harvest_models.py` gain a `--rebuild <source>` flag.

BioModels and PhysioNet paths are untouched.

### Component 5 — Regenerate atlas + republish

After the harvest updates `datasets/model_hra_map.json`:

- `scripts/build_atlas_pack.py` regenerates `atlas.json` deterministically
  (no network) from the merged datasets.
- Publish: local build (`scripts/publish_dashboard.sh`) + manual gh-pages push
  (the workflow is `workflow_dispatch`-only; CI can't build sibling deps).

## Testing

- **Offline unit tests** (`pytest -m "not network"`), all with recorded JSON
  fixtures injected via the existing `_get`/`_ids` seams:
  - `physiome`: id enumeration, per-exposure aggregation across multiple files,
    keyword/citation union, `build_entry` field shape, citation resolution
    (pmid + url + provenance), missing-citation graceful path.
  - `physiome_organ_map`: keyword-table → organ + cell-type mapping, precedence
    (annotation > keyword > category > title-keyword), unmapped fallback.
  - `model_harvest`: rebuild drops only the named source's rows; other sources
    preserved; re-insert count.
- **Network smoke test** (`-m network`): live enumerate + fetch one exposure +
  citations; assert non-empty title/keywords.
- Fixtures recorded from live responses into `tests/fixtures/physiome_pmr3/`.

## Non-goals (this change)

- Deep publication-metadata mining for anatomy/cell-types/genes beyond the
  citation title/journal (the API exposes citations; parsing paper bodies for
  anatomy is a follow-up).
- CellML RDF download for every model (annotation path stays opportunistic).
- Changing BioModels / PhysioNet sources.

## Rollout / count expectation

Physiome rows 570 → ~978 (complete corpus), with materially higher
organ + cell-type mapping coverage from author keywords, and PubMed-linked
citations. Total atlas rows ≈ 1096 biomodels + 480 physionet + ~978 physiome.
