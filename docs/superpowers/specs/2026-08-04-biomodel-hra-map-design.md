# BioModels → HRA mapping extractor — design

**Status:** approved design (2026-08-04)
**Scope of this spec:** a reusable script that builds a **JSON DB object**
mapping each curated BioModel to HRA anatomy/cell-type entities, molecular
identifiers, and LLM-extracted literature details. **Connecting the resulting DB
to the HRA knowledge graph is a separate, later step and is NOT part of this
spec.**

## Goal

For all ~1096 curated (`BIOMD`-prefixed) BioModels, build a single **JSON
database object keyed by model id**:

```json
{
  "BIOMD0000000341": { ...per-model object... },
  "BIOMD0000000633": { ... },
  ...
}
```

Each per-model object carries the requested headline fields first-class, with
the richer SBML/literature data nested:

```json
"BIOMD0000000341": {
  "identifier": "https://identifiers.org/biomodels.db:BIOMD0000000341",
  "repository": "biomodels",
  "name": "Topp2000 - Beta-cell mass, insulin, and glucose kinetics",
  "paper_doi": "10.1006/jtbi.2000.2150",

  "organs":                  [{"label": "pancreas", "uberon": "UBERON:0001264"}],
  "functional_tissue_units": [{"label": "islet of Langerhans", "uberon": "UBERON:0000006"}],
  "cell_types":              [{"label": "beta cell", "cl": "CL:0000169"}],

  "molecular_ids": {
    "chebi":   ["CHEBI:17234", "..."],
    "uniprot": ["P01308", "..."],
    "kegg":    ["C00031", "..."],
    "go":      ["GO:0006006", "..."]
  },
  "ontology_ids": {          // raw ontology CURIEs parsed from the SBML
    "cl":     ["CL:0000169"],
    "uberon": ["UBERON:0001264", "UBERON:0000006"],
    "fma":    ["FMA:16016"],
    "bto":    ["BTO:0000991"]
  },
  "literature": {            // Claude-extracted from abstract + OA full text
    "anatomical_structures": ["islet of Langerhans"],
    "tissues": ["..."], "cell_types": ["beta cell", "..."],
    "disease": "type 2 diabetes", "species": "human",
    "model_type": "ODE", "scale": "tissue",
    "key_process": "beta-cell mass adaptation to glucose",
    "candidate_uberon": ["UBERON:0000006"], "candidate_cl": ["CL:0000169"],
    "summary": "..."
  },
  "provenance": {
    "pmid": "11073807", "title": "...", "journal": "J Theor Biol", "year": 2000,
    "text_source": "abstract+fulltext", "has_fulltext": true,
    "n_species": 3, "errors": []
  }
}
```

**Field derivation:**
- `identifier` — resolvable IRI `https://identifiers.org/biomodels.db:<id>`.
- `repository` — `"biomodels"` (see Physiome note below).
- `organs` / `functional_tissue_units` / `cell_types` — the HRA-mapped curated
  view: each an object with a human `label` and its ontology id (`uberon` for
  organs/FTUs, `cl` for cell types), merged from SBML ontology ids, the curated
  organ→FTU→CL mapping, and (as candidates) the LLM fields.
- `molecular_ids` / `ontology_ids` — raw ids parsed from the SBML.
- `literature` — Claude structured extraction.
- `paper_doi` / `provenance.pmid` — from BioModels metadata.

## Non-goals (YAGNI)

- No knowledge-graph ingestion / RDF / triples — that is the separate downstream
  step.
- No paywalled full-text scraping — open-access (Europe PMC / PMC OA) only,
  abstract-only fallback otherwise.
- No new process-bigraph Steps/composites — standalone extraction script.

## Repositories (BioModels now, Physiome-ready)

Only the ~1096 curated BioModels are processed; every object's `repository` is
`"biomodels"`. The DB shape (top-level id keys, a `repository` field, and a
resolvable `identifier` IRI) is designed so **Physiome Model Repository (CellML)
models can be added later** as a second source — a future `physiome` loader
would parse CellML instead of SBML and emit the same per-model object shape,
merged into the same DB under its own ids. No Physiome work in this spec.

## Architecture

Thin CLI orchestrator + focused reusable library modules (repo convention:
`scripts/build_*.py` thin; logic in `viva_human_atlas/*.py`, unit-testable).

| Module | Responsibility |
|---|---|
| `scripts/build_biomodel_hra_map.py` | CLI; iterate ids; resume; assemble per-model objects; atomic-write the JSON DB |
| `viva_human_atlas/sbml_identifiers.py` | Generalize `annotation_match`'s CVTerm parser to extract CHEBI/UniProt/KEGG/GO/CL/Uberon/FMA/BTO per species/compartment/model |
| `viva_human_atlas/literature.py` | PubMed abstract (NCBI E-utilities via PMID) + Europe PMC OA full text; disk-cached; abstract-only fallback |
| `viva_human_atlas/llm_extract.py` | Claude structured extraction (Messages API, forced tool-use schema); cached by `(id, text-hash)` |
| `viva_human_atlas/hra_mapping.py` | Uberon organ-vs-subregion classification; organ→FTU→CL mapping; attaches Uberon ids to organs/FTUs and CL ids to cell types |

**Reuse:** `biomodels_search` (id list), `annotation_match` (`fetch_sbml`,
`_curie_from_uri`, CVTerm walking), `biomodel_do` (`build_organ_index`),
`ftu_coverage` (`HRA_FTUS`), `bto_crosswalk`, `hra_api`.

**Data enrichment:** the curated `HRA_FTUS` list gains a `uberon` id per FTU
(e.g. islet `UBERON:0000006`, renal corpuscle `UBERON:0001229`) so
`functional_tissue_units` can carry the requested Uberon id.

## Per-model data flow

Each stage writes to a per-stage disk cache and is independently error-isolated
(a failure degrades that field, is recorded in `provenance.errors`, and never
aborts the run):

1. **SBML** — `biomodels.get_file` → `sbml_identifiers.extract_identifiers` →
   molecular + ontology id sets.
2. **Metadata** — `biomodels.get_metadata` → name, PMID, DOI, title, journal,
   year.
3. **HRA mapping** — Uberon organ vs subregion; organ → curated FTU (+ uberon) →
   CL cell types.
4. **Literature** — abstract (PMID) + Europe PMC OA full text; abstract-only
   fallback; record `text_source`.
5. **LLM** — `llm_extract.extract(name, abstract, fulltext)` → `literature{}`.

Then assemble the per-model object and upsert it into the DB under its id.

## LLM extraction

- **Provider:** Claude Messages API via the `anthropic` SDK; a forced tool-use
  call returns the fixed `literature` schema (structured, validated).
- **Model:** default **Haiku 4.5** (`claude-haiku-4-5-20251001`) for cost/speed
  over ~1096 calls; `--llm-model` overrides (e.g. Sonnet).
- **Caching:** keyed by `(id, sha256(name+abstract+fulltext))`.
- **Inputs:** model name + abstract + OA full text (truncated to a token
  budget). Schema asks for HRA-style entities (organs, **anatomical
  structures**, tissues, cell types, FTUs) and, where confident, candidate
  Uberon/CL CURIEs (flagged candidate, not authoritative).
- SDK/model-id specifics confirmed against the `claude-api` skill at build time.
- **Prerequisite:** `ANTHROPIC_API_KEY` in the env. `--no-llm` builds the DB
  without the `literature` block and with no API use.

## Robustness

- **Resumable:** on start, load the existing `--out` JSON DB; skip ids already
  present; `--force` reprocesses.
- **Atomic writes:** the DB is written to a temp file and renamed, periodically
  (every N models) and at the end, so a crash never corrupts the DB and loses at
  most the last N in-flight models.
- **Staged caches:** SBML / abstract / fulltext / LLM cached separately under
  `--cache-dir`, so any single stage re-runs without redoing the others.
- **Per-model isolation:** each model is a try/except; each stage guarded;
  failures recorded in `provenance.errors`; the run continues.
- **Politeness:** modest concurrency (`--workers`) + rate limiting for NCBI /
  Europe PMC / BioModels.

## CLI

```
build_biomodel_hra_map.py
  --out PATH            # output JSON DB (default datasets/biomodel_hra_map.json)
  --ids-file PATH       # explicit id list (default: all curated ids)
  --query STR           # restrict to a BioModels search query
  --limit N             # cap number of models (for testing)
  --cache-dir PATH      # stage caches (default .cache/biomodel_hra_map)
  --no-llm              # skip LLM extraction (no `literature` block)
  --llm-model ID        # override extraction model (default Haiku 4.5)
  --workers N           # concurrency (default small)
  --resume / --force    # skip vs reprocess ids already in --out
```

Importable entry point `build_biomodel_hra_entry(biomodel_id, ...) -> dict`
(returns one per-model object) for reuse/testing.

## Testing

- **`sbml_identifiers`** — unit tests over inline SBML asserting
  CHEBI/UniProt/KEGG/GO/CL/Uberon/FMA/BTO extraction per element (offline).
- **`hra_mapping`** — organ-vs-subregion classification; organ→FTU→CL mapping;
  FTU/organ Uberon attachment over fixtures (offline).
- **`literature`** — parse fixture PubMed / Europe PMC XML via the injectable
  `_get` seam (offline).
- **`llm_extract`** — schema/prompt assembly + cache behavior with a stubbed
  client (offline; no real API calls).
- **orchestrator** — end-to-end over 2–3 stubbed models producing a JSON DB with
  the expected object shape and id keys; network/LLM stages mocked. DB
  resume/upsert covered. Live stages marked `network`.

## Validation & rollout

1. Build with unit tests (offline).
2. Validate on a **~20-model subset** (`--limit 20` over a metabolism/glucose
   query) — inspect the JSON DB, confirm every block populates and errors are
   sane.
3. Run the **full ~1096** pass with explicit go-ahead (slow; costs API for LLM).

## Open items / assumptions

- Uberon "organ vs subregion" is decided by membership in the HRA
  reference-organ set (organ-level) vs everything else (subregion).
- `functional_tissue_units[].uberon` comes from the enriched `HRA_FTUS` table;
  FTUs a model matches by organ inherit that organ's FTUs.
- Full-text token budget / truncation tuned during subset validation.

## Increment: BioPAX identifiers (added 2026-08-04)

Each BioModel ships an auto-generated BioPAX Level-3 OWL/RDF. `biopax_identifiers.py`
fetches it (`.../model/download/{id}?filename={id}-biopax3.owl`, biopax2 fallback,
cached) and harvests `<bp:db>/<bp:id>` Xref pairs — a clean complementary source to
the SBML MIRIAM pass — parsed with stdlib ElementTree (no rdflib/pybiopax dep).
Collections: CHEBI, UniProt, KEGG, GO (unioned into `molecular_ids` with the SBML
ids), plus **Reactome** (new `molecular_ids.reactome`) and organism **NCBI Taxon**
(`provenance.taxonomy`) that the SBML pass doesn't collect. Per-collection source
provenance is recorded in `provenance.id_sources` = `{collection: {sbml, biopax,
biopax_only}}`. Error-isolated like the other stages.
