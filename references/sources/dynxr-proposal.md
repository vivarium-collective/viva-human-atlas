# DynXR / DynKG proposal — relevance to viva-human-atlas

Source: R01 Research Strategy **"DynXR: Integrating Biomedical Datasets with
Mechanistic Biosimulations through the Human Reference Atlas"** (26-R01-VR,
Research-Strategy-4). PI **Bueckle**; Letters of Support / key personnel:
**Börner** (HRA), **Sego** (BioModels), **Sauro** (BioSimulators), **Robinson**
(MAxO / ontologies). **Agmon is Co-I and co-leads Aim 2** (the Vivarium-based
simulation layer). Not a clinical trial — human-subjects work is usability
studies only.

**This repo is the seed of Aim 2.** Our glucose-regulation investigation already
does the "run curated BioModels on BioSimulators-compatible engines" part; the
proposal tells us exactly what to build next to make it HRA-aligned.

## The two deliverables

- **DynKG (Dynamics Knowledge Graph)** — extends the HRA Knowledge Graph so
  mechanistic simulations and their outputs are first-class, ontology-linked
  entities: anatomy ↔ cell types ↔ biomarkers ↔ physiological processes ↔
  biomodels ↔ simulation metadata ↔ time-resolved outputs. Implemented as
  5-star Linked Open Data (RDF/SPARQL, OWL, LinkML).
- **DynXR** — web + XR app over DynKG for non-expert exploration (Aim 3; not our
  layer, but it consumes our outputs).

Goal: turn the HRA from a **static** anatomical atlas into a **simulation-enabled,
physiology-aware** framework. Primary use case: **diabetes / glucose-insulin
dynamics** across pancreas, liver, adipose, vasculature, kidney, intestine.

## Aim 2 (ours): HRA-aligned compositional simulations of organ-resolved dynamics

Pipeline: **curated BioModels → mapped to HRA anatomy/ontology → wrapped as
Vivarium modules → executed with COPASI / BioSimulators-compatible tools →
exported as ontology-linked time-series**, cached + queryable for DynXR.

Tasks:
- **T2.1** Identify, prioritize, semantically curate executable models for
  HRA-aligned simulation. Start with glucose-insulin regulation, pancreatic
  insulin secretion, hepatic glucose production, skeletal-muscle glucose uptake,
  adipose metabolism, intestinal nutrient absorption, renal glucose handling.
  Annotate each model with **Uberon** (organ), **CL/PCL** (cell type),
  **HGNC/Ensembl** (genes/biomarkers), **SBO** (model entities), **MAxO**
  (interventions). Evaluate executability under COPASI/other engines.
- **T2.2** Parameterized perturbation interfaces (diet / meal carbohydrate load,
  glucose load, medication e.g. metformin, physical activity, body weight,
  baseline glucose, insulin sensitivity, renal handling, hepatic production,
  intestinal absorption). High-level user inputs → model params via
  MAxO/SBO/HPO/LOINC + NIH CDEs, stored as *simulation-settings* DOs.
- **T2.3** Execution + caching + query + streaming of ontology-linked time-series
  (Vivarium orchestrates coupling; outputs carry model id, simulator version,
  settings, perturbation, anatomical context, variables, units, timestamps,
  provenance).
- **T2.4** Minimal, transparent, swappable **gap-filling** modules (transport,
  compartment-coupling, unit/scale conversion, reduced-order, stub processes) to
  bridge curated models into coherent multi-organ workflows. Cites Agmon's
  Vivarium whole-cell composition success.

### Preliminary model survey (from the proposal, directly reusable)
- **68** BioModels related to diabetes; **39** related to **glucose regulation**;
  ~**11** pancreas, ~**28** kidney. The hra-hackathon pipeline (Agmon, ref below)
  already fetches biomodels via HRA ontologies and runs them with Vivarium.
- Named concrete multi-organ model: **M4_SBML.xml** — an updated organ-based
  multi-level model of **glucose homeostasis** (Herrgårdh et al. 2021), spanning
  organ distributions, timing, and blood-flow effects. A strong candidate for a
  multi-organ demo in this repo.

## The three new HRA Digital Object (DO) types (Aim 1, T1.1) — our target schema

The DynKG introduces three DO types. Aim 2 produces the 1st and 3rd:

1. **biomodel DO** — ontology-linked representation of a mechanistic model
   encoding its **biological scope, organ, cell types, input parameters, and
   provenance**, pointing to a BioModels ID; cross-linked to Uberon / CL / PCL /
   HGNC / Ensembl / SBO terms. Makes a BioModels entry a first-class DynKG node.
2. **simulation-settings DO** — the algorithm/engine, input parameters, and
   number/duration of runs used for a simulation.
3. **time-series DO** — the structured, ontology-linked output of a biomodel run
   under given simulation-settings (variables, units, ontology ids, provenance).

Schema tooling: **LinkML** per DO type; ingest/enrich via the HRA DO Processor
pattern; publish as versioned, persistent-URL LOD.

## Ontologies & standards to align to
Uberon (anatomy) · Cell Ontology (CL) + Provisional Cell Ontology (PCL) ·
HGNC + Ensembl (genes/biomarkers) · Human Phenotype Ontology (HPO) · Medical
Action Ontology (MAxO, interventions) · Systems Biology Ontology (SBO, model
entities) · CCF (Common Coordinate Framework) · LinkML · OWL · RDF / SPARQL ·
NIH CDEs · FAIR + 5-star LOD.

## Organs / anatomy (diabetes use case) → Uberon anchors for 3D linkage
77 HRA 3D reference organs (from NLM Visible Human) are keyed by Uberon IDs — this
is the hook to the 3D spatial model. Diabetes-relevant set: pancreas, liver,
adipose tissue, vasculature, kidney, small/large intestine, skeletal muscle,
blood. (FTUs = functional tissue units; CTpop / cell-type populations can
parameterize FTU-scale models — see [[hra-wpp-context]].)

## Where viva-human-atlas stands vs the proposal (the gap = the next step)
- ✅ Have: BioModels text search + fetch, dual-engine run (COPASI + Tellurium),
  all-pairs comparison. This covers T2.1's "which models are executable" and part
  of T2.3's execution.
- ❌ Missing: **HRA ontology annotation** of each model (no Uberon/CL/SBO;
  hra-hackathon only resolved species names via UniProt/KEGG). No **biomodel DO**,
  no **simulation-settings / time-series DO** export, no organ→Uberon mapping,
  no perturbation interface, no gap-filling/coupling.
- **Concrete next step** = emit a minimal **biomodel DO** per glucose-regulation
  model, annotated with an Uberon organ term — the ontology bridge that connects
  our runs to HRA anatomy (and thence the 3D organs).

## Relevant references (Aim 2 / simulation / ontology / HRA — curated subset)

**Simulation stack (directly used here)**
- BioModels — Malik-Sheriff RS, et al. *BioModels—15 years of sharing
  computational models in life science.* Nucleic Acids Res. 2020;48(D1):D407–15.
  doi:10.1093/nar/gkz1055
- SBML — Hucka M, et al. *The Systems Biology Markup Language (SBML) L3V1 Core.*
  Nat Preced. 2010. doi:10.1038/npre.2010.4959.1
- COPASI — Hoops S, et al. *COPASI—a COmplex PAthway SImulator.* Bioinformatics.
  2006;22(24):3067–74. doi:10.1093/bioinformatics/btl485
- Vivarium — **Agmon E**, et al. *Vivarium: an interface and engine for
  integrative multiscale modeling in computational biology.* Bioinformatics.
  2022;38(7):1972–9. doi:10.1093/bioinformatics/btac049
- BioSimulators — Shaikh B, …, **Agmon E**, et al. *BioSimulators: a central
  registry of simulation engines and services.* Nucleic Acids Res.
  2022;50(W1):W108–14. doi:10.1093/nar/gkac331
- BioSimulations — https://biosimulations.org/
- hra-hackathon (our starting point) — **Agmon E.**
  https://github.com/vivarium-collective/hra-hackathon
- BioModels Exploration UI (WPP EUI) —
  https://wholepersonproject.github.io/wpp-eui-experiment/

**Concrete glucose models**
- Herrgårdh T, et al. *An Updated Organ-Based Multi-Level Model for Glucose
  Homeostasis: Organ Distributions, Timing, and Impact of Blood Flow.* Front
  Physiol. 2021;12:619254. doi:10.3389/fphys.2021.619254
- M4_SBML.xml (ISBgroup) —
  https://gitlab.liu.se/ISBgroup/projects/updated-multi-level/-/blob/master/scripts/Models/M4_SBML.xml

**HRA / Whole Person Physiome**
- Börner K, et al. *HuBMAP: 3D Human Reference Atlas construction and usage.* Nat
  Methods. 2025. doi:10.1038/s41592-024-02563-5
- Börner K, et al. *Anatomical structures, cell types and biomarkers of the HRA.*
  Nat Cell Biol. 2021;23(11):1117–28. doi:10.1038/s41556-021-00788-6
- Bueckle A, et al. *Construction, Deployment, and Usage of the HRA Knowledge
  Graph.* Sci Data. 2025;12(1):1100. doi:10.1038/s41597-025-05183-6
- Bueckle A, et al. *Tissue registration and exploration user interfaces (RUI/EUI)
  in support of a HRA.* Commun Biol. 2022;5(1):1369. doi:10.1038/s42003-022-03644-x
- Bueckle A, et al. *Cell Type Populations for 3D Anatomical Structures of the
  HRA (CTpop).* Sci Data. 2026. doi:10.1038/s41597-026-06642-4
- Herr BW, et al. *Specimen, biological structure, and spatial ontologies for a
  HRA.* Sci Data. 2023;10(1):171. doi:10.1038/s41597-023-01993-8
- Bidanta S, et al. *Functional tissue units in the HRA.* Nat Commun.
  2025;16(1):1526. doi:10.1038/s41467-024-54591-6
- Whole Person Physiome (WPP) — NIH RePORTER project 11224772;
  KG Explorer https://kg.wholepersonphysiome.org/ ;
  Data Products https://cdn.wholepersonphysiome.org/data-products/ ;
  WPP LinkML schema (draft) https://kg.wholepersonphysiome.org/schema/wpp/draft
- HRA KG Explorer https://apps.humanatlas.io/kg-explorer/ ;
  HRA API (grlc) https://apps.humanatlas.io/api/grlc ;
  HRA DO Processor https://github.com/hubmapconsortium/hra-do-processor

**Ontologies & standards**
- Uberon — Mungall CJ, et al. Genome Biol. 2012;13(1):R5. doi:10.1186/gb-2012-13-1-r5
- Cell Ontology (CL) — Diehl AD, et al. J Biomed Semant. 2016;7(1):44.
  doi:10.1186/s13326-016-0088-7 ; Tan SZK, et al. Sci Data 2026,
  doi:10.1038/s41597-026-07173-8
- Provisional Cell Ontology (PCL) — Tan SZK, et al. *Brain Data Standards.* Sci
  Data. 2023;10(1):50. doi:10.1038/s41597-022-01886-2
- HGNC — Seal RL, et al. Nucleic Acids Res. 2023;51(D1):D1003–9. doi:10.1093/nar/gkac888
- Ensembl — Martin FJ, et al. Nucleic Acids Res. 2023;51(D1):D933–41. doi:10.1093/nar/gkac958
- Human Phenotype Ontology (HPO) — Gargano MA, et al. Nucleic Acids Res.
  2024;52(D1):D1333–46. doi:10.1093/nar/gkad1005
- Medical Action Ontology (MAxO) — Carmody LC, et al. Med. 2023;4(12):913-927.e3.
  doi:10.1016/j.medj.2023.10.003
- Systems Biology Ontology (SBO) — Juty N, le Novère N. In: Encyclopedia of
  Systems Biology, Springer 2013. doi:10.1007/978-1-4419-9863-7_1287
- LinkML — Moxon SAT, et al. GigaScience. 2025. doi:10.1093/gigascience/giaf152
- Visible Human — Ackerman MJ. Proc IEEE. 1998;86(3):504–11. doi:10.1109/5.662875
- FAIR — Wilkinson MD, et al. Sci Data. 2016;3:160018. doi:10.1038/sdata.2016.18
- 5-star LOD — https://5stardata.info/ ; RDF https://www.w3.org/RDF/ ;
  SPARQL https://www.w3.org/TR/sparql11-query/ ; OWL https://www.w3.org/OWL/
