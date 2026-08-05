"""organ-vasculature-scaffold composite: store hierarchy only (no processes).

A structural scaffold for the Whole-Person-Physiome model: two top-level store
trees — ``Vasculature`` (the vessels feeding each modeled organ, plus the shared
``blood`` compartment) and ``Organs`` (the organ compartments themselves). No
processes yet; this is the state topology that later processes (blood transport,
per-organ dynamics) will read and write. Empty ``{}`` leaves are bare stores,
matching the store-node convention in ``vasculature_network_composite.py``.
"""
from __future__ import annotations

from typing import Any, Dict

try:
    from viva_superpowers.composite_generator import composite_generator
except ModuleNotFoundError:
    from pbg_superpowers.composite_generator import composite_generator

# Registered draft-process classes (ports + contract live on the class, so they
# show up in the dashboard's Modules -> Processes tab). See draft_processes.py.
PTH_SECRETION_ADDRESS = "local:viva_human_atlas.draft_processes.PTHSecretion"
CA2_ABSORPTION_ADDRESS = "local:viva_human_atlas.draft_processes.Ca2Absorption"


def _blood_solutes() -> Dict[str, Any]:
    """The regulated solutes of the PTH / calcium / vitamin-D endocrine axis,
    each a float concentration. Carried by every blood-filled compartment."""
    return {
        "PTH": {"_type": "float"},
        "Ca2+": {"_type": "float"},
        "VitD": {"_type": "float"},
        "25-OH-VitD": {"_type": "float"},
    }


def build_organ_vasculature_document() -> Dict[str, Any]:
    state: Dict[str, Any] = {
        # Every vessel (and the shared blood pool) carries the four regulated
        # solutes as float concentrations — spatially-resolved blood chemistry.
        "Vasculature": {
            "parathyroid vessel": _blood_solutes(),
            "renal artery": _blood_solutes(),
            "superior mesenteric artery": _blood_solutes(),
            "blood": _blood_solutes(),
        },
        "Organs": {
            "parathyroid": {
                "parathyroid parenchyma": {
                    # Glandular PTH pool secreted by the chief cells.
                    "PTH": {"_type": "float"},
                },
            },
            "kidney": {
                "nephron": {
                    # Filtered calcium available for tubular reabsorption.
                    "Ca2+": {"_type": "float"},
                },
            },
            "small intestines": {
                "intestinal villus": {},
            },
            "bone": {
                "osteon": {},
            },
        },
        # ── Draft processes (registered classes; contract only, no dynamics) ──
        # Ports + contract live on the DraftProcess subclasses in
        # draft_processes.py; here we supply only the store wiring.
        "PTH secretion": {
            "_type": "process",
            "address": PTH_SECRETION_ADDRESS,
            "inputs": {
                "ca_sense": ["Vasculature", "parathyroid vessel", "Ca2+"],
            },
            "outputs": {
                "pth_out": ["Vasculature", "parathyroid vessel", "PTH"],
            },
        },
        "Ca2+ absorption": {
            "_type": "process",
            "address": CA2_ABSORPTION_ADDRESS,
            "inputs": {
                "ca_source": ["Organs", "kidney", "nephron", "Ca2+"],
                "pth_sense": ["Vasculature", "renal artery", "PTH"],
            },
            "outputs": {
                "ca_absorbed": ["Vasculature", "renal artery", "Ca2+"],
            },
        },
    }
    return {"state": state}


@composite_generator(
    name="organ-vasculature-scaffold",
    description=(
        "Store-hierarchy scaffold for the Whole-Person-Physiome model: a "
        "Vasculature tree (parathyroid vessel, renal artery, superior "
        "mesenteric artery, blood) and an Organs tree (parathyroid, kidney, "
        "small intestines, bone). No processes yet — just the state topology."
    ),
    parameters={},
    default_n_steps=1,
)
def build_organ_vasculature_scaffold(core: Any = None) -> Dict[str, Any]:
    return build_organ_vasculature_document()
