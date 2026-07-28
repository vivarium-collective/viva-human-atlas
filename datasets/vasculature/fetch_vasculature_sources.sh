#!/usr/bin/env bash
# Re-pull the (re-fetchable) vasculature sources into datasets/vasculature/.
# See README.md for provenance + licenses. The provided FTU_Table_S1_*.csv is
# supplied directly (not re-fetchable) and is left untouched.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"

# 1) VCCF source CSVs (hubmapconsortium/hra-vccf, MIT).
VCCF="$HERE/vccf"
mkdir -p "$VCCF"
BASE="https://raw.githubusercontent.com/hubmapconsortium/hra-vccf/main"
for f in Vessel.csv VesselOrganCrosswalk.csv VesselCTB.csv CellTypeBiomarker.csv \
         Geometry.csv schema.yaml LICENSE README.md; do
  echo "  vccf/$f"
  curl -fsSL "$BASE/$f" -o "$VCCF/$f"
done

# 2) "Blood Vasculature Extended Database" Google Sheet (all tabs -> xlsx).
SHEET_ID="1OXUloOgIJ9AZSw80WSg0Qv40_uWy2WfGav33MT_4YSM"
echo "  blood_vasculature_extended_database.xlsx"
curl -fsSL "https://docs.google.com/spreadsheets/d/${SHEET_ID}/export?format=xlsx" \
  -o "$HERE/blood_vasculature_extended_database.xlsx"

# 3) Font-Clos et al. 2020 flow-model code/dataset — REFERENCED, not vendored.
#    Uncomment to clone it locally (kept out of the repo; see references/papers.bib):
# git clone --depth 1 https://github.com/ComplexityBiosystems/CTC-model "$HERE/_ctc-model-ref"

echo "done. FTU_Table_S1_*.csv (provided) left as-is."
