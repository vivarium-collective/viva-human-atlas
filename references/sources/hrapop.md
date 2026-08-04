# HRApop — Cell Type Populations for 3D Anatomical Structures of the HRA

**Citation.** Bueckle A, Herr BW II, Chen L, Bolin D, Qaurooni D, Ginda M, Jain Y,
Puig-Barbe A, Ardlie K, Wang F, Börner K. *Cell Type Populations for 3D Anatomical
Structures of the Human Reference Atlas.* **Scientific Data** 13:716 (2026).
DOI: [10.1038/s41597-026-06642-4](https://doi.org/10.1038/s41597-026-06642-4).
Data Descriptor (OPEN). Companion site: https://cns-iu.github.io/hra-cell-type-populations-supporting-information/

**Live knowledge graph.** HRApop is browsable in the HRA KG Explorer:
https://apps.humanatlas.io/kg-explorer/graph/hra-pop/latest
(also queryable via SPARQL and the HRA API — https://apps.humanatlas.io/api).

## What HRApop is

HRApop (HRA Cell Type Population) is the Human Reference Atlas effort that
**quantifies cell-type (CT) populations per 3D anatomical structure (AS)** — i.e.
for a given AS (e.g. "15 AS within the male lung"), how many cells of each cell
type it contains, plus per-CT mean biomarker expression. It answers the question
the HRA's 3D reference organs (HRA v2.3: 1,283 3D ASs across 73 reference organs)
otherwise leave open: *what cells, and how many, populate each structure.*

**HRApop v1.0 scale:**
- Reference CT populations for **73 ASs** (112 when sex-specific) across **17 organs**
  (31 when sex-specific), spatially registered to **230 locations**.
- Built from **662 high-quality datasets**; **27,619,613 cells** total.
- sc-transcriptomics: 558 datasets (11,042,750 cells), CTs + biomarker expression
  computed with **Azimuth, CellTypist, and popV** (CTann tools).
- sc-proteomics: 104 datasets (16,576,863 cells) integrated for generalization.
- CT labels aligned to **Cell Ontology (CL)**; AS are Uberon-typed via `part_of`.
- Published as **5-Star Linked Open Data** with resolvable URIs, FAIR, full provenance.

## Key concepts (relevant to this workspace)

- **ASpop** — Anatomical-Structure Cell-Type Populations: the number of cells per CT
  for an AS (the aggregate, donor-independent reference).
- **DESpop** — Dataset & Extraction-Site Cell-Type Populations: per-dataset / per-RUI-
  extraction-site cell counts per CT.
- **RUI2CTpop workflow** — takes CT populations + donor metadata + 3D extraction sites
  recorded via the **RUI (Registration User Interface)** and computes CT populations for
  ASs. This is the concrete **RUI → CTpop → model parameterization** pipeline the DynXR
  proposal and the `ctpop-islet-parameterization` study describe.
- Access: HRA API (`apps.humanatlas.io/api`), SPARQL (AS–CT combinations with sex/tool/
  cell-percentage as CSV), and the HRA Knowledge Graph (KG) linked above.

## Why it matters here

`studies/ctpop-islet-parameterization` bound a **documented literature** islet
beta/alpha/delta composition to the Topp2000 model because, at the time, "a live HRA
CTpop endpoint is not (as of this writing) publicly exposed as JSON." **HRApop is that
endpoint** — it exposes per-AS CT populations (with CL cell types + Uberon AS) via the
HRA API / SPARQL / KG. This reference is the bridge to replace the study's
literature-average composition with a **real, queryable CTpop pull** (the
`fp-ctpop-live-islet-binding` follow-up), and more broadly to parameterize any
FTU/AS-scoped model from measured cell-type populations.

Also connects to `hra-integration` / `hra-3d` (Uberon-keyed reference organs + ASs) and
the `ftu-model-coverage` CTpop parameterization stub (beta/alpha/delta CL ids).

## Stated limitations (v1.0)

- Dataset duplication across portals (HuBMAP/CELLxGENE) is hard to fully de-duplicate.
- CTann tools (Azimuth/CellTypist/popV) were trained on data that can lack donor
  demographics / RUI extraction sites.
- Missing assay-type ontology terms for systematic batch-correction queries.
- The 1,283 3D ASs are meant to be non-overlapping but some intersect (17 organs),
  complicating strictly AS-specific CT populations.
