# BioGears as the flow source for the blood-circulation network

**Date:** 2026-11-24
**Status:** Proposed design for review (no code)
**Branch:** `docs/biogears-flow-link`
**Companion:** viva-biogears design `docs/design-organ-flow-export.md` (the export side)
**Extends:** [`docs/blood-circulation-simulation-plan.md`](../../blood-circulation-simulation-plan.md), sections 2 and 3

## Problem

The circulation plan has a validated transport graph (v1) but nothing that drives
it. Its v2 needs a heart and a flow `Q` on every edge; the plan's first answer for
`Q` is a tabulated cardiac-output partition (section 3, route 1). That partition
is fixed: it cannot respond to hemorrhage, fluids, drugs or a different patient.

[viva-biogears](https://github.com/vivarium-collective/viva-biogears) already runs
the real BioGears 8.2.0 engine as a process-bigraph `Process`, with a heart,
per-organ vascular compartments and circuit paths, and these respond to
interventions. This design makes BioGears the source of the heart and the
per-organ flows, and keeps the atlas as the owner of topology, ontology and organ
models.

## Decided shape

One-way, typed, Uberon-keyed (Alex, 2026-11-24). BioGears writes flows; the atlas
reads them. Nothing flows back to BioGears in this design.

## Division of ownership

| Concern | Owner | Why |
|---|---|---|
| Heart, cardiac output, per-region flow and pressure | viva-biogears (BioGears) | The engine computes them. |
| BioGears region names (`LiverVasculature`, ...) | viva-biogears | They are BioGears' own names; viva-biogears knows no Uberon. |
| Uberon organ -> BioGears region(s) mapping | atlas (`datasets/vasculature/`) | The atlas owns ontology ids and the organ-mapping resolver. |
| Graph topology, per-edge `Q` assembly, transport | atlas | Plan sections 2 to 4. |

## Interface

BioGears side (full detail in the viva-biogears design): a cycle-averaged
per-region export, typed by BioGears region name:

```
flows: map[region] -> { inflow_mL_per_min: float, mean_pressure_mmHg: float, volume_mL: float }
cardiac_output_mL_per_min: float
```

Atlas side, a new Step (name provisional, `OrganFlowAdapterStep`) that consumes
that and the mapping table and emits what `BloodTransportProcess` (plan section 2)
already expects:

```
organ_flow: map[uberon_id] -> Q_mL_per_min      # per mapped organ
edge_flow:  map[edge_id]   -> Q_mL_per_min      # per directed edge of the graph
cardiac_output_mL_per_min: float                # drives the heart node
```

The mapping table is a committed data file, `datasets/vasculature/biogears_region_map.csv`
(columns: `uberon_id`, `organ_label`, `biogears_regions` (`;`-separated), `role`
(`parallel_organ`, `pump`, `whole_circuit`), `notes`). Organ ids are resolved with the
existing organ-mapping resolver, not compared as raw strings, because the atlas records
reference ids that differ from the common Uberon id (its own resolver spec notes
`UBERON:0002113` kidney is the reference organ `UBERON:0004538`).

## What replaces the cardiac-output partition

Plan section 3, route 1 becomes **route 1b: engine-sourced partition**:

1. Each tick, the adapter reads the cycle-averaged inflow of every mapped BioGears
   region. This is the organ's share of cardiac output, time-varying and
   patient-specific, instead of a tabulated fraction.
2. An organ with several FTU routes splits its `Q` among them. **Open:** equal split,
   or weighted (tissue volume, FTU count). Default proposed: equal, flagged as a
   placeholder.
3. Each FTU route is a series path heart -> FTU capillary -> heart, so every edge on
   it carries that FTU's `Q`. An edge shared by several routes (a trunk) carries the sum.
   This is the same push-down as the plan's partition; only the source of the shares
   changes.
4. The heart node's output is BioGears' cardiac output, not a constant.

Route 2 (resistance network) is unchanged and still planned as v3.

## Which organs and FTUs have a BioGears region

BioGears 8.2.0 vascular compartments are read in
`viva_biogears/modules/cardiovascular.py`. Counted from the current atlas data:

**FTU routes (28, from `FTU_Table_S1_260611.csv`): 17 have a BioGears region, 11 do not.**

| BioGears region | FTU routes |
|---|---|
| `LeftKidneyVasculature` + `RightKidneyVasculature` (kidney as a whole) | cortical collecting duct, descending limb of loop of Henle, inner medullary collecting duct, loop of Henle ascending limb thin segment, nephron, outer medullary collecting duct, renal corpuscle, thick ascending limb (8) |
| `SkinVasculature` | dermal papilla, epidermal ridge of digit, hair follicle (3) |
| `SpleenVasculature` | red pulp of spleen, white pulp of spleen (2) |
| `LiverVasculature` | liver lobule (1) |
| `SmallIntestineVasculature` | intestinal villus (1) |
| `LargeIntestineVasculature` | crypt of Lieberkuhn (1) |
| pulmonary circulation (`PulmonaryCapillaries`) | alveolus of lung (1) |
| **none** | bronchus submucosal gland, chorionic terminal villus, gingival attachment, intercalated duct (pancreas), pancreatic acinus, islet of Langerhans, parotid, sublingual and submandibular ducto-acinar units, prostate glandular acinus, thymus lobule (11) |

**Modeled organs (23 distinct labels in `datasets/model_hra_map.json`; the plan and
README say 24, which should be reconciled): 10 map to a BioGears region, 2 map partly,
11 do not.**

- Region: heart (`MyocardiumVasculature` for coronary flow; the chambers are the pump),
  brain (`BrainVasculature`; cerebral branch also read), liver, lung (pulmonary),
  spleen, intestine, kidney, muscle (`MuscleVasculature`), skin, adipose (`FatVasculature`).
- Partial: blood (the whole circuit, not an organ: carries cardiac output and
  total volume), lymph-node (BioGears has a lymph module, not a node-level vessel).
- None: pancreas, thymus, placenta, eye (left and right), spinal cord, ovary, trachea,
  main bronchus, prostate, urinary bladder.

Consequence: the glucose-regulation payload (plan section 5) needs the pancreas, which
BioGears does not represent as a vascular region. Its flow has to come from a
documented rule (for example a fraction of splanchnic flow) or stay tabulated. **Open
decision for the reviewers.** The design does not hide this: unmapped organs keep the
tabulated partition (route 1) and are marked as such in the output.

## Units and time

- Flow: mL/min (BioGears' unit; the plan is unit-agnostic). Pressure mmHg, volume mL.
- BioGears steps at 0.02 s and reports compartment flows **instantaneously within the
  heartbeat**; 1 s sampling aliases the cycle (stated in `cardiovascular.py`). The export
  therefore averages over a window of at least one cardiac cycle inside the engine
  process, and the atlas reads the average, never a raw sample.
- Atlas transport runs at its own tick (a full loop is about 1 min; organ models step in
  minutes). The adapter holds `Q` constant across a tick and updates it at each export.
  **Open:** tick length (suggested: the export interval, default 1 s, with a fast transport
  sub-step as in plan section 7).

## Validation (real engine, nothing mocked)

1. **Conservation at the heart:** the sum of mapped parallel-organ inflows plus unmapped
   remainder equals BioGears' cardiac output within a stated tolerance, on the
   StandardMale state. **Unverified:** whether BioGears' regional inflows sum to cardiac
   output; this is the first probe, and the tolerance is set from it.
2. **Kirchhoff on the graph:** at every internal node, inflow equals outflow within
   numerical tolerance for the assembled `edge_flow` (a property of the adapter, tested on
   the real vasculature graph).
3. **Response:** after a BioGears hemorrhage, the mapped organ flows and the heart output
   change in the engine's direction and the edge flows follow, run through the real engine.
4. **Independent oracle:** regional cycle-means from a separate engine driven directly
   through pybiogears, as the viva-biogears tests already do for their readings.
5. **Patient cohort:** flows differ across BioGears' shipped patients in the expected order.

## Out of scope

- Solute transport and delays (plan section 4), perfusion adapters and the organ models
  (plan section 5, v4): this design only supplies flow.
- Atlas -> BioGears coupling (two-way).
- The resistance network (v3) and per-vessel geometry.
- BioGears' lymph, tissue-fluid and thermal modules.
- Any new BioGears capability: the engine is used as built (8.2.0).

## Open questions for review

1. Equal or weighted split of an organ's `Q` among its FTU routes.
2. How the pancreas (and thymus, prostate, salivary glands) get a flow: tabulated or a rule.
3. Averaging window (one cardiac cycle versus a fixed number of seconds).
4. Mapping table location: this repo (proposed) or viva-biogears.
5. Reconcile 23 versus 24 modeled organs and confirm the reference-id mapping for each
   BioGears-mapped organ with the organ-mapping resolver.
