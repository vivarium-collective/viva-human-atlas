# BioModels → HRA mapping extractor — design

**Status:** approved design (2026-08-04)
**Scope of this spec:** a reusable script that extracts a comprehensive
per-BioModel CSV mapping each curated model to HRA anatomy/cell-type entities,
molecular identifiers, and LLM-extracted literature details. **Connecting the
resulting CSV to the HRA knowledge graph is a separate, later step and is NOT
part of this spec.**

## Goal

For all ~1096 curated (`BIOMD`-prefixed) BioModels, produce **one comprehensive
CSV row per model** capturing:

- molecular identifiers parsed from the model's SBML (**CHEBI, UniProt, KEGG,
  GO**),
- ontology identifiers parsed from the SBML (**CL** cell types, **Uberon**
  organs/subregions, **FMA**, **BTO**),
- HRA mapping: organs, organ-level Uberon, functional tissue units (FTUs), and
  the cell types of those FTUs,
- key details extracted by Claude from the model's **abstract + open-access
  full text**: organs, **anatomical structures**, tissues, cell types, FTUs,
  disease/condition, species, model type & scale, key biological process, and
  candidate ontology terms.

## Non-goals (YAGNI)

- No knowledge-graph ingestion / RDF / triple emission — that is the separate
  downstream step.
- No paywalled full-text scraping — open-access (Europe PMC / PMC OA) only,
  abstract-only fallback otherwise.
- No new process-bigraph Steps/composites — this is a standalone extraction
  script, not a workspace composite.

## Architecture

Thin CLI orchestrator + focused reusable library modules, matching the repo
convention (`scripts/build_*.py` stays thin; logic lives in
`viva_human_atlas/*.py` and is unit-testable).

| Module | Responsibility |
|---|---|
| `scripts/build_biomodel_hra_map.py` | CLI; iterate ids; checkpoint/resume; assemble + append CSV rows |
| `viva_human_atlas/sbml_identifiers.py` | Generalize `annotation_match`'s CVTerm parser to extract CHEBI/UniProt/KEGG/GO/CL/Uberon/FMA/BTO per species/compartment/model, each with element + qualifier context |
| `viva_human_atlas/literature.py` | PubMed abstract (NCBI E-utilities via PMID) + Europe PMC open-access full text; disk-cached; abstract-only fallback |
| `viva_human_atlas/llm_extract.py` | Claude structured extraction (Messages API, forced tool-use schema); cached by `(biomodel_id, text-hash)` |
| `viva_human_atlas/hra_mapping.py` | Uberon organ-vs-subregion classification; organ→FTU→CL mapping. Reuses `biomodel_do` organ_index, `ftu_coverage.HRA_FTUS`, `datasets/bto_uberon_crosswalk.json` |

**Reuse of existing code:** `biomodels_search` (id list), `annotation_match`
(`fetch_sbml`, `_curie_from_uri`, CVTerm walking), `biomodel_do`
(`build_organ_index`), `ftu_coverage` (`HRA_FTUS`), `bto_crosswalk`, `hra_api`.

## Per-model data flow

Each stage writes to a per-stage disk cache and is independently error-isolated
(a failure degrades that field and is recorded in `errors`; it never aborts the
run):

1. **SBML** — `biomodels.get_file` → `sbml_identifiers.extract_identifiers` →
   molecular + ontology id sets (with element/qualifier provenance).
2. **Metadata** — `biomodels.get_metadata` → name, PMID, DOI, title, journal,
   year.
3. **HRA mapping** — classify each Uberon as organ vs subregion (via the HRA
   reference-organ index); map to HRA organ; look up curated FTUs and their CL
   cell types for those organs.
4. **Literature** — `literature.fetch_abstract(pmid)` + `fetch_oa_fulltext`
   (Europe PMC); fall back to abstract-only; record `text_source`.
5. **LLM** — `llm_extract.extract(name, abstract, fulltext)` → structured fields
   (Claude, forced tool schema).

## CSV schema (one row per model; list-valued fields are `;`-joined, deduped)

- **Identity:** `biomodel_id`, `name`
- **Publication:** `pmid`, `doi`, `title`, `journal`, `year`
- **Molecular (SBML):** `chebi_ids`, `uniprot_ids`, `kegg_ids`, `go_ids`
- **Anatomy/cell (SBML):** `cl_ids`, `uberon_ids`, `uberon_organ_ids`,
  `uberon_subregion_ids`, `fma_ids`, `bto_ids`
- **HRA mapping:** `hra_organs`, `hra_organ_uberon`, `hra_ftus`,
  `hra_ftu_cell_types`
- **LLM (from abstract + OA full text):** `llm_organs`,
  `llm_anatomical_structures`, `llm_tissues`, `llm_cell_types`, `llm_ftus`,
  `llm_disease`, `llm_species`, `llm_model_type`, `llm_scale`,
  `llm_key_process`, `llm_candidate_uberon`, `llm_candidate_cl`, `llm_summary`
- **Provenance:** `n_species`, `text_source` (`none|abstract|abstract+fulltext`),
  `has_fulltext`, `errors`

## LLM extraction

- **Provider:** Claude Messages API via the `anthropic` SDK. A forced tool-use
  call returns a fixed JSON schema (the `llm_*` fields above), so output is
  structured and validated, not free-text parsed.
- **Model:** default **Haiku 4.5** (`claude-haiku-4-5-20251001`) for cost/speed
  across ~1096 calls; `--llm-model` overrides (e.g. Sonnet for higher quality).
- **Caching:** keyed by `(biomodel_id, sha256(name+abstract+fulltext))` so
  re-running assembly or changing non-LLM code never re-pays for extraction.
- **Prompt inputs:** model name + abstract + OA full text (truncated to a token
  budget). The schema instructs Claude to return HRA-style entities (organs,
  anatomical structures, cell types, FTUs) and, where confident, candidate
  Uberon/CL CURIEs — flagged as candidates, not authoritative.
- SDK/model-id specifics confirmed against the `claude-api` skill at build time.
- **Prerequisite:** `ANTHROPIC_API_KEY` in the environment. `--no-llm` produces
  the structural CSV (everything except the `llm_*` columns) with no API use.

## Robustness

- **Resumable:** on start, read existing `--out` CSV and skip ids already
  present; `--force` reprocesses.
- **Staged caches:** SBML / abstract / fulltext / LLM cached separately under
  `--cache-dir`, so any single stage can be re-run without redoing the others.
- **Per-model isolation:** each model is a try/except; each stage within it is
  guarded; failures are recorded in the row's `errors` field and the run
  continues. Incremental append + flush so a crash loses at most the in-flight
  model.
- **Politeness:** modest concurrency (`--workers`, small default) and rate
  limiting for NCBI / Europe PMC / BioModels.

## CLI

```
build_biomodel_hra_map.py
  --out PATH            # output CSV (default datasets/biomodel_hra_map.csv)
  --ids-file PATH       # explicit id list (default: all curated ids)
  --query STR           # restrict to a BioModels search query
  --limit N             # cap number of models (for testing)
  --cache-dir PATH      # stage caches (default .cache/biomodel_hra_map)
  --no-llm              # skip LLM extraction (structural CSV only)
  --llm-model ID        # override extraction model (default Haiku 4.5)
  --workers N           # concurrency (default small)
  --resume / --force    # skip vs reprocess ids already in --out
```

Importable entry point `build_biomodel_hra_row(biomodel_id, ...) -> dict` for
reuse/testing.

## Testing

- **`sbml_identifiers`** — unit tests over small inline SBML strings asserting
  CHEBI/UniProt/KEGG/GO/CL/Uberon/FMA/BTO are extracted per element (offline).
- **`hra_mapping`** — organ-vs-subregion classification and organ→FTU→CL
  mapping over fixture organ indexes/FTUs (offline).
- **`literature`** — parsing of fixture PubMed/Europe PMC XML payloads via the
  injectable `_get` seam (offline; no live HTTP in tests).
- **`llm_extract`** — schema/prompt assembly + cache behavior with a stubbed
  client (offline); no real API calls in tests.
- **orchestrator** — end-to-end over 2–3 stubbed models producing a CSV with the
  expected columns; network/LLM stages mocked. Live stages marked `network`.

## Validation & rollout

1. Build with unit tests (offline).
2. Validate on a **~20-model subset** (`--limit 20` over a metabolism/glucose
   query) — inspect the CSV, confirm all stages populate and errors are sane.
3. Hand off / run the **full ~1096** pass with explicit go-ahead (slow; costs
   API for the LLM stage).

## Open items / assumptions

- Uberon "organ vs subregion" is decided by membership in the HRA
  reference-organ set (organ-level) vs everything else (subregion); FMA/BTO are
  reported but not organ/subregion-classified.
- Full-text token budget and truncation strategy tuned during subset validation.
