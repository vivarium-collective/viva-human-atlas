"""Derive a coarse *physiological process* label for a model, so the atlas can
group an organ's models by process (ion transport, metabolism, ...) instead of
showing one flat list -- the "anatomical structure -> physiological process ->
model" unit.

The signal is uneven across sources (by design, first pass): Physiome carries a
real PMR category, so we use it directly; BioModels/PhysioNet have no process
field, so we key a coarse keyword table off the model name. Anything unmatched
is "Other" rather than force-fit. This is deliberately a rough, shared
vocabulary -- a curated per-organ process taxonomy is a later refinement.
"""
from __future__ import annotations

# PMR category slug -> process label (Physiome's category IS a process signal).
CATEGORY_PROCESS: dict[str, str] = {
    "electrophysiology": "Electrophysiology",
    "excitation-contraction_coupling": "Excitation–contraction coupling",
    "myofilament_mechanics": "Mechanics",
    "mechanical_constitutive_laws": "Mechanics",
    "cardiovascular_circulation": "Circulation",
    "ion_transport": "Ion transport",
    "ph_regulation": "Acid–base / pH",
    "metabolism": "Metabolism",
    "hepatology": "Metabolism",
    "endocrine": "Endocrine / signaling",
    "neurobiology": "Neural",
    "calcium_dynamics": "Calcium dynamics",
    "signal_transduction": "Signaling",
    "cell_cycle": "Cell cycle",
    "immunology": "Immune",
    "gene_regulation": "Gene regulation",
    "circadian_rhythms": "Circadian rhythms",
    "synthetic_biology": "Synthetic biology",
    "cell_migration": "Cell migration",
    "protein_modules": "Protein modules",
    "PKPD": "Pharmacokinetics",
}

# Physiome categories that actually place a model on an organ (so their process
# is the organ-relevant one) -- preferred over co-filed cellular categories.
_PREFERRED = ("electrophysiology", "cardiovascular_circulation",
              "excitation-contraction_coupling", "myofilament_mechanics",
              "hepatology", "ion_transport", "ph_regulation", "neurobiology")

# Coarse keyword-on-name -> process for sources without a category (BioModels,
# PhysioNet). First match wins; ordered most- to least-specific.
PROCESS_KEYWORDS: list[tuple[str, str]] = [
    ("action potential", "Electrophysiology"), ("electrophysiolog", "Electrophysiology"),
    ("cardiac", "Electrophysiology"), ("purkinje", "Electrophysiology"),
    ("ecg", "Electrophysiology"), ("arrhythmi", "Electrophysiology"),
    ("excitation-contraction", "Excitation–contraction coupling"),
    ("calcium", "Calcium dynamics"), ("ca2+", "Calcium dynamics"),
    ("circadian", "Circadian rhythms"), ("cell cycle", "Cell cycle"),
    ("apoptosis", "Cell death"), ("insulin", "Endocrine / signaling"),
    ("hormone", "Endocrine / signaling"), ("glucose", "Metabolism"),
    ("glycolysis", "Metabolism"), ("metabol", "Metabolism"), ("hepatic", "Metabolism"),
    ("transcription", "Gene regulation"), ("gene regulat", "Gene regulation"),
    ("signal", "Signaling"), ("mapk", "Signaling"), ("cascade", "Signaling"),
    ("receptor", "Signaling"), ("immun", "Immune"), ("transport", "Ion transport"),
    ("channel", "Ion transport"), ("circulation", "Circulation"),
    ("hemodynamic", "Circulation"), ("blood flow", "Circulation"),
    ("pharmacokinetic", "Pharmacokinetics"), ("mechanic", "Mechanics"),
]

OTHER = "Other"


def model_process(entry: dict) -> str:
    """Best-effort physiological-process label for a model record/row. Physiome
    uses its PMR category (organ-placing category preferred); other sources fall
    back to a keyword match on the name; unmatched -> "Other"."""
    cats = entry.get("categories") or (entry.get("provenance") or {}).get("categories") or []
    if cats:
        for c in _PREFERRED:
            if c in cats and c in CATEGORY_PROCESS:
                return CATEGORY_PROCESS[c]
        for c in cats:
            if c in CATEGORY_PROCESS:
                return CATEGORY_PROCESS[c]
    name = (entry.get("name") or "").lower()
    for kw, proc in PROCESS_KEYWORDS:
        if kw in name:
            return proc
    return OTHER
