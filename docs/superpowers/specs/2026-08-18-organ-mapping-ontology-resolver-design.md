# Ontology-grounded organ-mapping resolver

**Date:** 2026-08-18
**Status:** Approved design (pending spec review)
**Branch:** `feat/organ-mapping-ontology-resolver`

## Problem

The atlas places **721 / 2,554** models on an organ; **1,833 are unplaced**. The
cause is that organ resolution matches anatomy annotations by **exact organ-level
UBERON id** only. Investigation of the unplaced pool:

- **85 unplaced BioModels already carry a UBERON** — but every one is a
  *non-organ-level* id (subregion/tissue) or an organ **synonym id** that isn't
  our reference id. E.g. `UBERON:0000956` (cerebral cortex)→brain,
  `UBERON:0001285` (nephron)→kidney, `UBERON:0001155` (colon)→intestine, and
  `UBERON:0002113` (kidney) which is the **same organ** as our reference
  `UBERON:0004538` under a different id. Exact-match drops all of them.
- Unplaced BioModels also carry rich, unused ontology signal: **MeSH 687, CL
  (cell type) 193, BTO 147, FMA 24, gene symbols 345**. BTO/MeSH are already
  crosswalked to UBERON in `build_entry`, but the resulting non-organ UBERONs
  then fail the same exact-match.
- **Physiome:** 233 unplaced carry author `cellml_keyword`s (rest have none).
- **PhysioNet:** 356 unplaced carry only a name.

The current mapping logic is also **scattered** across `hra_mapping.map_to_hra`
(exact UBERON + name-synonym), `biomodel_do` (organ synonyms), `anatomy_crosswalk`
(BTO/MeSH→UBERON), and the per-source keyword tables (`physiome_organ_map`,
`physionet_organ_map`).

## Decisions (approved 2026-08-18)

- **D1 — Ontology-grounded resolver.** One resolver maps any anatomy annotation
  (UBERON / CL / BTO / FMA / MeSH) to an HRA reference organ via ontology
  relationships (hierarchy roll-up + crosswalks), not exact-id matching.
- **D2 — Generate-once, commit crosswalk datasets.** A script queries the
  ontologies (OLS / Ubergraph) + HRA ASCT+B once and commits the resulting
  crosswalk/roll-up JSONs, so the atlas build stays **offline + deterministic**.
- **D3 — Placement bar = annotation + ontology.** Place a model only from
  anatomy annotations resolved through the ontology (high/medium confidence).
  **Genes are resolved through the HRA ASCT+B biomarker tables** (gene → cell
  type → organ), specificity-gated — an ontology-grounded path, not fuzzy
  expression inference. Non-ASCT+B gene inference and LLM tail-mapping are out of
  scope here.

## Existing assets to reuse (do NOT rebuild)

- `datasets/asctb_tables.json` — per-organ ASCT+B: each row has
  `anatomical_structures` (a UBERON chain system→organ→AS), `cell_types` (CL),
  and `biomarkers_gene` (gene symbols). This already encodes **AS-UBERON→organ**,
  **CL→organ**, and **gene→organ**.
- `datasets/bto_uberon_crosswalk.json` — BTO→UBERON (`anatomy_crosswalk.load_bto_uberon`).
- `datasets/mesh-uberon-cl-human-mapping.sssom.csv` — MeSH→UBERON/CL SSSOM
  (`anatomy_crosswalk.load_mesh_label_crosswalk` / `crosswalk_mesh_labels`).
- `viva_human_atlas/anatomy_crosswalk.py`, `annotation_match.py`, `bto_crosswalk.py`,
  `asctb_tables.py`, `hra_pop.py`, `biomodel_do.build_organ_index`.

The gap is **roll-up to organ** (the ontology hierarchy step) + a **single
resolver** that composes all of the above; not new crosswalk plumbing.

## Design

### Component 1 — Generated crosswalk/roll-up datasets

New script `scripts/build_anatomy_crosswalks.py` (network, run occasionally;
output committed) produces:

1. `datasets/uberon_organ_rollup.json` — `{uberon_id: [organ_key, ...]}` mapping
   every UBERON that should resolve to a reference organ but isn't the reference
   organ-level id. Two contributions, unioned:
   - **ASCT+B-derived:** for each organ in `asctb_tables.json`, every UBERON in
     its `anatomical_structures` chains → that organ key (covers subregions +
     organ synonym ids for HRA-covered organs).
   - **UBERON-hierarchy-derived:** for the UBERON CURIEs that appear in our
     corpus (from `model_hra_map.json`) but aren't yet resolved, query
     Ubergraph/OLS for their `part_of`/`is_a` ancestors and map to a reference
     organ if an ancestor is (or is a synonym of) one. Bounded to corpus CURIEs
     → small, deterministic output.
   - Records provenance (`source: asctb|uberon-hierarchy`) alongside each entry
     in a sibling `*.provenance.json` (not required at runtime).
2. `datasets/cl_organ_map.json` — `{cl_id: [organ_key, ...]}` from
   `asctb_tables.json` `cell_types` (+ Ubergraph `part_of` for CLs not in ASCT+B).
3. `datasets/gene_organ_map.json` — `{gene_symbol: {organ_key: n_celltypes}}`
   from `asctb_tables.json` `biomarkers_gene`, so specificity is known at
   resolve time (a gene marking cell types across many organs is ambiguous).
4. Extend the existing FMA→UBERON coverage: `datasets/fma_uberon_crosswalk.json`
   from Ubergraph/OLS `database_cross_reference` for corpus FMA ids (replaces the
   7-entry hardcoded `FMA_TO_UBERON` in `physiome_organ_map`).

All keyed by ontology ids resolved to `organ_index` **keys** (never hardcoded
UBERON ids); a key absent from the reference set contributes nothing, by design.
The script is idempotent and prints a diff summary; re-running only matters when
the corpus gains genuinely new CURIEs.

### Component 2 — `anatomy_resolver.py`

New module: the single anatomy→organ resolver every source uses.

```python
def resolve_organs(
    organ_index: dict, *,
    uberon=(), cl=(), fma=(), bto=(), mesh=(),   # annotation CURIEs
    name: str = "", keywords=(),                  # text fallbacks
    gene_symbols=(),                              # ASCT+B biomarker path
    rollup=None, cl_map=None, gene_map=None,      # loaded datasets (injectable)
    bto_map=None, mesh_map=None, fma_map=None,
) -> dict:
    """Resolve to {organs, functional_tissue_units, cell_types,
    uberon_organ_ids, uberon_subregion_ids, mapping_method, confidence,
    method_detail}. Deterministic; no network."""
```

Resolution tiers (first non-empty wins; `method`/`confidence` record the tier):

1. **organ-level UBERON** exact match in `organ_index` → organ. (`annotation`, high)
2. **UBERON roll-up**: any UBERON via `uberon_organ_rollup.json` → organ
   (subregion/tissue/synonym). (`annotation_rollup`, high)
3. **BTO / FMA / MeSH → UBERON** (crosswalks) → re-enter tiers 1–2.
   (`crosswalk`, medium-high)
4. **CL cell-type → organ** via `cl_organ_map.json`. (`cell_type`, medium)
5. **keyword / name** via the existing per-source keyword tables + `map_to_hra`
   name-synonym. (`keyword`, medium/low)
6. **gene → organ** via `gene_organ_map.json`, specificity-gated: place only if
   the gene set resolves to a single organ (or a clear plurality ≥ threshold),
   never if the genes are pan-organ. (`gene_asctb`, low)

FTUs + cell types for the chosen organ(s) come from the existing
`map_to_hra`/`hra_pop` FTU logic (unchanged), so subregion placement still works.

### Component 3 — Integration (wire every source through the resolver)

- `hra_mapping.map_to_hra` keeps its signature but delegates organ resolution to
  `anatomy_resolver.resolve_organs` (roll-up now applied); FTU/cell-type
  derivation unchanged. Callers of `map_to_hra` are unaffected.
- `biomodel_hra.build_entry` passes its already-extracted `uberon/cl/fma/bto/mesh`
  + `gene_symbols` into the resolver (it currently crosswalks then calls
  `map_to_hra` on organ-level uberon only — now the full annotation set flows).
- `physiome_organ_map` / `physionet_organ_map`: keyword tables become tier-5
  inside the resolver; their category/keyword logic is preserved. `physiome`'s
  hardcoded `FMA_TO_UBERON` is replaced by the generated `fma_uberon_crosswalk`.
- The datasets are loaded once (module-level cache, like `anatomy_crosswalk`) and
  injectable for tests.

### Component 4 — Rebuild + measure

- Re-harvest is **not** needed (annotations are already in each committed row).
  Add `scripts/remap_organs.py`: for every row in `model_hra_map.json`, call
  `anatomy_resolver.resolve_organs` on the row's existing annotation fields
  (`ontology_ids.{uberon,cl,fma,bto,mesh}`, `gene_symbols`, `name`,
  `provenance.keywords`) and overwrite `organs` / `functional_tissue_units` /
  `cell_types` / `ontology_ids.uberon` (organ ids) + `provenance.mapping_method`
  / `confidence`. No network, no re-extraction — a pure, deterministic re-map of
  committed annotations, so it is safe to re-run and easy to diff.
- Regenerate `atlas.json` (`scripts/build_atlas_pack.py`) and report the
  placement lift per source + per mapping-method.

## Testing

- `anatomy_resolver`: unit tests per tier with injected datasets —
  organ-level UBERON, roll-up (cerebral cortex→brain, nephron→kidney, colon→
  intestine, UBERON:0002113→kidney synonym), BTO/MeSH/FMA→organ, CL→organ,
  keyword fallback, gene specificity gate (single-organ places; pan-organ does
  not), unmapped fallback. Precedence order asserted.
- `build_anatomy_crosswalks`: run offline against a small recorded ASCT+B +
  ontology fixture; assert the roll-up/cl/gene JSON shapes; network call behind
  `@pytest.mark.network`.
- Integration: `biomodel_hra.build_entry` places a model that has only a
  non-organ UBERON (previously unplaced); other sources unchanged in shape.
- Offline suite stays green; the 3 known pre-existing failures excluded.

## Non-goals

- No LLM tail-mapping (PhysioNet name-only / Physiome no-keyword stay unplaced).
- No non-ASCT+B gene-expression inference.
- No re-harvest from source APIs (re-map from committed annotations only).
- No change to FTU/subregion placement logic beyond feeding it more organs.

## Expected outcome

Place the annotation-bearing unplaced models — the 85 UBERON-only + a large share
of the 147 BTO + 687 MeSH + 193 CL BioModels, plus gene-specific ones — lifting
placed distinct well above 721, with every new placement carrying a recorded
`mapping_method` + `confidence` and grounded in an ontology relationship (no
hand-guessed organ). Exact lift measured at rebuild; the design's success bar is
"materially more placed, each defensible via ontology," not a fixed number.
