# HRA / WPP context sources

Curated reference material for the viva-human-atlas project. These inform the
**later** investigations (ontology bridge, 3D-spatial connection, WPP timescale
tables) — not the first fetch-and-compare investigation. Kept here so they're at
hand when we need them.

Primary source: email thread "Preparing for the hackathon", Katy Börner
(katy@iu.edu) → Eran Agmon, Andreas Bueckle, 2026-07-25 (Griffin Weber added for
vasculature; Jacob Scherba, Bruce on thread).

## 1. HRA-WPP graph → drugs & transcriptome signatures
The HRA-WPP graph should ultimately connect to **drugs and transcriptome
signatures**.
- Barabási post (primary pointer): <https://www.facebook.com/barabasi/posts/pfbid0VZm6FTKEkKeKaPedDiY8bbXJuWp24hjt7b7fQg3HnMwE4LKNgnLNGUAXnroMpayVl>
- Likely associated paper (Barabási Lab): *Discovery of Disease Relationships via
  Transcriptomic Signature Analysis Powered by Agentic AI* —
  <https://arxiv.org/pdf/2508.04742>

## 2. Functional Tissue Units (FTUs) as modeling targets
Katy's question: *do any existing models try to model FTUs?* — a candidate target
class for the biomodels we pull.
- HRA 2D FTU illustrations (v2.5):
  <https://humanatlas.io/2d-ftu-illustrations?releaseVersion=2.5>
- **CTpop** (cell-type populations, including B-cell expressions) could
  *parameterize* these FTU models. This is the intended bridge between HRA
  cell-type data and mechanistic models.

## 3. SPARC heart — 3D FE organ models + tissue registration
Peter Hunter's long-standing vision: use HRA **RUI** (Registration User
Interface) to register tissue, then use CTpop (incl. B-cell expressions) to
parameterize his 3D finite-element organ models.
- Reference DOI given: <https://doi.org/10.3389/fphys.2021.693735>
  (SPARC infrastructure: 3D FE organ scaffolds incl. heart, RUI-style tissue
  registration, o2S2PARC reproducible modeling, FAIR data).
- Relevance: this is the anatomical/3D-spatial side that viva-human-atlas's
  ontology-linked biomodels are meant to connect to.

## 4. WPP timescale tables — process durations & fast→slow triggering
Katy wants the WPP tables to record **how long certain processes take** and
**which fast processes trigger slower ones**.
- Canonical multi-timescale example (from the thread): cardiac myocyte
  **depolarization (~1 ms)** triggers **mechanical contraction (~100–300 ms)**
  via **excitation–contraction coupling** — linking electrical, molecular, and
  mechanical processes across timescales.
- Relevance: motivates capturing per-process timescale metadata on the models we
  pull, and multi-timescale composite coupling downstream.

## People / roles on the thread
- **Katy Börner** (katy@iu.edu) — HRA lead
- **Andreas Bueckle** (abueckle@iu.edu) — slide deck / HRA
- **Griffin Weber** (griffin_weber@hms.harvard.edu) — vasculature
- **Jacob Scherba** (jscherba@engineering.upenn.edu)
- **Bruce**, **Eran Agmon** (agmon@uchc.edu)
