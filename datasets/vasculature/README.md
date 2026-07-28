# Vasculature datasets — HRA / VCCF blood-vessel network

Source data for the **`blood-vasculature-network`** study and the blood-circulation
simulation planned in [`docs/blood-circulation-simulation-plan.md`](../../docs/blood-circulation-simulation-plan.md).
Loaded and turned into a directed transport graph by
[`viva_human_atlas/vasculature.py`](../../viva_human_atlas/vasculature.py).

## Files

| File | Source | What it is |
|------|--------|-----------|
| `FTU_Table_S1_260611.csv` | provided (HRA VCCF supplement) | For each of **28 FTUs**, an *ordered* heart → FTU → heart vessel path. `PathStep` < 0 = arterial (toward the FTU), `0` = the FTU exchange capillary, > 0 = venous (back to the heart). The cleanest topology source — a complete transport route per organ. (Header note: the vessel-id column is misspelled `PahtVesselID` in the source.) |
| `vccf/Vessel.csv` | [hubmapconsortium/hra-vccf](https://github.com/hubmapconsortium/hra-vccf) | VCCF master vessel table — type/subtype, body part, artery↔vein pairing, `BranchesFrom` parent links (1082 vessels). |
| `vccf/VesselOrganCrosswalk.csv` | same | Vessel → BodyPart → FTU → Angiosome crosswalk (576 rows). |
| `vccf/VesselCTB.csv` | same | Vessel → cell-type → biomarker links. |
| `vccf/CellTypeBiomarker.csv`, `vccf/Geometry.csv`, `vccf/schema.yaml` | same | Cell-type biomarkers, per-vessel geometry, table schema. |
| `vccf/LICENSE`, `vccf/README.md` | same | Upstream MIT license + readme (kept for attribution). |
| `blood_vasculature_extended_database.xlsx` | [Google Sheet](https://docs.google.com/spreadsheets/d/1OXUloOgIJ9AZSw80WSg0Qv40_uWy2WfGav33MT_4YSM/edit) | "Blood Vasculature Extended Database" (v1.10) — the same vasculature organized differently (multi-tab). Snapshot; refresh with the fetch script. |

## External references (not vendored)

- **VCCF portal / preferred source files:** <https://humanatlas.io/vccf> (the interactive
  HRA portal; `hubmapconsortium/hra-vccf` above holds its published CSVs).
- **Blood-flow modeling precedent — Font-Clos et al. 2020**, *Blood Flow Contributions
  to Cancer Metastasis*, iScience 23(5):101073. doi:10.1016/j.isci.2020.101073
  (PMID 32361595, PMCID PMC7200936). A whole-body hemodynamic **flow network over
  organs** — the closest published analog to what we want to build. Code + dataset:
  <https://github.com/ComplexityBiosystems/CTC-model/tree/master/code> (key files:
  `solve_flows_network.py` = the flow solver, `launch_tracers_fullsystem.py` = tracer
  transport, `optimize_organ_coefficients.py` = per-organ flow fractions). Cited in
  [`references/papers.bib`](../../references/papers.bib).

## Refreshing

```bash
bash datasets/vasculature/fetch_vasculature_sources.sh   # re-pulls VCCF + the Google Sheet
```

The provided `FTU_Table_S1_260611.csv` is not re-fetchable (it was supplied directly)
and is left untouched by the script.

## Licenses / attribution

- `vccf/*` — MIT, © 2022 HuBMAP Consortium (see `vccf/LICENSE`).
- `FTU_Table_S1_*` and the extended-database sheet — HRA VCCF materials; cite the VCCF
  portal and the HRA vasculature work when used.
- CTC-model code/data is **referenced, not redistributed** — pull it from its repo under
  that project's own license.
