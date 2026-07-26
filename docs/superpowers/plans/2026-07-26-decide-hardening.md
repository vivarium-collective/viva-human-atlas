# Decide-tab hardening + follow-up studies + investigation structure — Plan

**Goal:** Make the Decide tab usable across every study (real computed three-track verdicts + authored basis), harden the investigation structure (open questions/decisions), author seedable follow-up study proposals, and SEED all 5 follow-ups as planned study scaffolds. Plus two fast-follows. All authored directly in yaml (the Decide/seed/narrative POST paths don't exist in the static bundle; computed verdicts + authored fields ARE baked into the published JSON, so this renders live AND in the showcase).

## Decide-tab field contract (verified from vivarium-workbench)
The three verdict badges are COMPUTED (author only the `basis`):
- `regression_compatibility` ← `runs[].status`: all runs status in {completed,complete,success,ok,done} → **PASS**; any errored → FAIL; none → PENDING; mixed → PARTIAL.
- `biological_validation` ← `pipeline_gate.gate_evaluator.result`: passed/ok → **PASS**; partial/needs_calibration → PARTIAL; fail → FAIL; unset → PENDING.
- `explanatory_gain` ← `findings[]`: any `tier: interpretation` (or truthy `mechanism_origin`) → **PASS**; findings present but none interpretation → PARTIAL; no findings → GAP.

**Author per study (schema_version 4; KEEP existing `baseline`):**
```yaml
runs:
  - {name: baseline, status: completed}      # reflects the real successful composite run
pipeline_gate:
  gate_evaluator: {result: passed}           # or needs_calibration/partial where honest
findings:
  - id: F-01
    tier: interpretation                     # at least one interpretation-tier finding
    mechanism_origin: emergent               # or engineered
    statement: "<a real, specific claim grounded in this study's enriched report numbers>"
    claim_scope: mechanism
    evidence: {summary: "<the real number/result>"}
conclusion_verdicts:
  regression_compatibility: {basis: "<why the runs are clean>"}
  biological_validation:    {basis: "<the real metric vs expectation>"}
  explanatory_gain:         {basis: "<what we learned — cite the finding>"}
limitations:
  - "<a real limitation>"
discovery_implications:
  resolved_uncertainties: ["<what this study settled>"]
  remaining_uncertainties: ["<what's still open>"]
  followup_study_proposals:
    - {id: fp-..., title: "...", motivation: "...", study_type: "...", proposed_experiment: "...", expected_information_gain: high, source_trigger: "<this study>"}
```
Derive each study's findings/bases from its EXISTING enriched `report`/`conclusion` (real numbers already there) — do NOT fabricate. Set `gate_evaluator.result` honestly (a study that only demonstrates loading, with no calibrated biology, is `needs_calibration` → PARTIAL, not passed).

## Per-study honest gate guidance
- Data-load studies (hra-reference-organs, hra-cell-types, hra-anatomical-structures, hra-3d-crosswalk, ftu-glomerulus): runs completed → regression PASS; `gate_evaluator.result: passed` if the endpoint returns the expected data shape/counts (it does — real counts); explanatory finding = "the endpoint drives a Step-based fetch and returns N records."
- glucose-regulation / glucose-biomodel-do: regression PASS; biological `passed` (COPASI≈Tellurium nRMSE ~2e-7 for loadable models) but note load-coverage caveat; explanatory finding = engine-agreement + load-coverage bottleneck.
- corpus-coverage / model-coverage-3d: regression PASS; biological `needs_calibration` → PARTIAL (coverage is name-based, recall-limited); explanatory finding = 635/1730 AS, 31 organs, kidney covered; organ-granularity overstates fine coverage.
- spatial-linkage: regression PASS; biological `needs_calibration` (placeholder readouts); explanatory finding = model→AS→GLB-node linkage works but carries no results yet.

## Investigation structure (author into each investigation.yaml)
Add `executive.decisions_needed[]` (the OPEN QUESTIONS), plus `scientific_argument`, `at_a_glance`, `hypotheses[]`, `acceptance_criteria[]` where thin.
- **glucose-regulation:** decisions_needed = [{question: "Why do most curated glucose models fail to load in both engines (missing SED-ML)? Recover them?", context: "Only 1/5 loaded; engines agree when they do."}, {question: "Which models genuinely disagree vs. merely fail to load?"}].
- **hra-integration:** decisions_needed = [{question: "What is the organ-tag recall ceiling with names alone (currently ~7.5%)? Move to SBML MIRIAM annotations?"}, {question: "Which organs are systematically under-tagged?"}].
- **hra-3d:** decisions_needed = [{question: "Which HRA organs/FTUs have ZERO mechanistic models (the modeling white-space)?"}, {question: "Does organ-granularity coverage overstate AS-level coverage — can we get finer?"}, {question: "Can we spatially link model RESULTS (steady-state values) to AS, not just presence?"}].

## Seed all 5 follow-up studies (planned scaffolds + also list as followup_study_proposals on the trigger study)
Each new `studies/<slug>/study.yaml`: schema_version 4, `status: planned`, `phase: Design`, `pipeline_gate.prerequisites: [{study: <parent>, relation: leads-to}]`, a rich `purpose`/`question`/`study_card`, PENDING `conclusion_verdicts` blocks, `limitations: ["TBD — planned study."]`, and a **resolvable placeholder `baseline`** (closest existing generator — a planned study still needs a non-empty resolvable baseline or study-detail 500s; note in study_card that the real composite is future work). Splice the slug into the parent investigation's `studies:` list.

| slug | parent study / investigation | placeholder baseline (registered id) |
|---|---|---|
| `sbml-annotation-tagging` | glucose-biomodel-do / hra-integration | `viva_human_atlas.composites.biomodel_do_composite.glucose-biomodel-do` |
| `coverage-gap-analysis` | corpus-coverage / hra-3d | `viva_human_atlas.composites.corpus_coverage_composite.corpus-coverage` |
| `result-driven-spatial-link` | spatial-linkage / hra-3d | `viva_human_atlas.composites.spatial_link_composite.spatial-linkage` |
| `multiorgan-glucose-m4` | glucose-regulation / glucose-regulation | `viva_human_atlas.composites.glucose_regulation.glucose-regulation` |
| `load-failure-recovery` | glucose-regulation / glucose-regulation | `viva_human_atlas.composites.glucose_regulation.glucose-regulation` |

Follow-up motivations (real):
1. **sbml-annotation-tagging** — parse curated SBML MIRIAM (Uberon/taxon/GO) annotations for organ tags → lift recall past name-only ~7.5%.
2. **coverage-gap-analysis** — enumerate HRA organs/FTUs with zero mechanistic models → prioritize modeling.
3. **result-driven-spatial-link** — color AS by a model readout (steady-state concentration from the corpus dataset) so the 3D viewer shows results, not just coverage.
4. **multiorgan-glucose-m4** — import the M4/Herrgårdh multi-organ glucose homeostasis model → a coupled multi-organ Aim-2 demo.
5. **load-failure-recovery** — auto-generate default UTC/SED-ML for models missing it → recover un-loadable BioModels.

## Fast-follows
- **#2:** `coverage.build_corpus_coverage` / `build_coverage(catalog=...)` — set `summary.query` to `"corpus (1096 curated)"` (or None) when a `catalog` is supplied, so committed corpus coverage.json isn't mislabeled `"glucose regulation"`. (Code fix; regenerate the committed corpus coverage.json/packs if straightforward.)
- **#3:** `scripts/build_hra_viewer_pack.py` — use CORPUS-scoped spatial links (`build_spatial_links` over the corpus catalog / the corpus-covered organs) instead of the glucose query, so per-organ packs carry organ-appropriate links. Regenerate packs.

## Verify + finish
- Offline suite green; every study (incl. the 5 new) `baseline.composite` resolves; yaml parses; the three Decide verdicts compute non-PENDING where authored (spot-check `derived.conclusion_verdicts` via `report_views`/`study_derivations`).
- Republish; verify a study-detail JSON has `derived.conclusion_verdicts` with real results + `conclusion_verdicts.*.basis` + `executive.decisions_needed` on investigations.
