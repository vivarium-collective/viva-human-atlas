"""Connect the biomodel-HRA DB to HRApop (HRA Cell Type Populations, Bueckle
2026) — the measured cell-type populations per HRA anatomical structure.

The BioModels map to organs (organ-granularity), while HRApop's rows are keyed
by specific sub-organ anatomical structures. So this joins at the ORGAN level:
HRApop's per-AS cell populations are aggregated up to the organ, and a model
inherits its organ's cell-type composition. Data product:
`datasets/hrapop_as_cell_populations.csv` (HRApop v1.0, x-atlas-consortia/hra-pop
output-data/v1.0 .../cell-types-in-anatomical-structures...cts-per-as.csv),
columns: organ, as, as_label, sex, tool, modality, cell_id, cell_label,
cell_count, cell_percentage, dataset_count.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Optional

_DEFAULT_CSV = Path(__file__).resolve().parents[1] / "datasets" / "hrapop_as_cell_populations.csv"


def _curie(uri: str) -> str:
    tail = (uri or "").rsplit("/", 1)[-1]
    return tail.replace("UBERON_", "UBERON:").replace("CL_", "CL:")


def _organ_words(s: str) -> set:
    return set((s or "").lower().replace("-", " ").split())


def load_hrapop(path: Optional[str] = None) -> dict:
    """`{organ_label: {"organs": {raw hrapop organ names}, "cell_types": [
    {cl, label, percentage (mean), cell_count (sum), n_as, n_rows}, ...]}}`
    aggregated from the per-AS rows, cell types ranked by mean percentage."""
    p = Path(path) if path else _DEFAULT_CSV
    if not p.exists():
        return {}
    # organ -> cell_id -> accumulator
    agg: dict[str, dict[str, dict]] = {}
    raw_names: dict[str, set] = {}
    with open(p, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            organ = (r.get("organ") or "").strip().lower()
            if not organ:
                continue
            raw_names.setdefault(organ, set()).add((r.get("organ") or "").strip())
            cl = _curie(r.get("cell_id", ""))
            if not cl.startswith("CL:"):
                continue
            try:
                cnt = float(r.get("cell_count") or 0)
            except ValueError:
                cnt = 0.0
            a = agg.setdefault(organ, {}).setdefault(
                cl, {"cl": cl, "label": r.get("cell_label") or None,
                     "cell_count": 0.0, "_as": set(), "n_rows": 0})
            a["cell_count"] += cnt
            a["_as"].add(_curie(r.get("as", "")))
            a["n_rows"] += 1

    out: dict[str, dict] = {}
    for organ, cells in agg.items():
        # Organ-level composition: each cell type's summed count over the
        # organ's total observed cells (sums to ~1 across the organ), which is a
        # cleaner aggregate than averaging the per-context percentages.
        total = sum(c["cell_count"] for c in cells.values()) or 1.0
        ct = []
        for c in cells.values():
            ct.append({"cl": c["cl"], "label": c["label"],
                       "percentage": round(c["cell_count"] / total, 4),
                       "cell_count": round(c["cell_count"]),
                       "n_as": len(c.pop("_as")), "n_rows": c["n_rows"]})
        ct.sort(key=lambda x: x["percentage"], reverse=True)
        out[organ] = {"organs": sorted(raw_names[organ]), "cell_types": ct}
    return out


def _organ_match(model_organ: str, hrapop: dict) -> Optional[str]:
    """Match a model organ label to a HRApop organ key by word-subset (so
    `intestine`->`large/small intestine`, `kidney`->`left/right kidney`,
    `urinary-bladder`->`urinary bladder`). Returns the HRApop key, or None."""
    mw = _organ_words(model_organ)
    if not mw:
        return None
    for key in hrapop:
        kw = _organ_words(key)
        if mw <= kw or kw <= mw:
            return key
    return None


def hrapop_for_organs(organ_labels, hrapop: dict, *, top: Optional[int] = None) -> list:
    """For a model's organ labels, return `[{organ, hrapop_organs, cell_types}]`
    from HRApop (organ-level). Deduped across the model's organs; `top` caps the
    cell-type list per organ (default: all)."""
    seen, out = set(), []
    for lab in organ_labels or []:
        key = _organ_match(lab, hrapop)
        if key is None or key in seen:
            continue
        seen.add(key)
        entry = hrapop[key]
        cts = entry["cell_types"][:top] if top else entry["cell_types"]
        out.append({"organ": key, "hrapop_organs": entry["organs"], "cell_types": cts})
    return out
