"""Draft processes for the organ-vasculature scaffold.

Each is a registered :class:`~viva_superpowers.draft_process.DraftProcess`
subclass — ports + contract on the class, no update dynamics yet. Being
``Process`` subclasses in this package, ``build_core()`` auto-registers them, so
they appear in the dashboard's Modules -> Processes tab (by name, with ports +
contract, marked DRAFT). The ``organ_vasculature_scaffold`` composite references
them by address and supplies only the store wiring.
"""
from __future__ import annotations

from process_bigraph import DraftProcess, draft_process


@draft_process(
    name="PTH secretion",
    inputs={"ca_sense": "float"},
    outputs={"pth_out": "float"},
    contract={
        "summary": (
            "Parathyroid chief cells synthesize PTH de novo and secrete it into "
            "the parathyroid vessel, in response to low blood calcium."
        ),
        "makes": "PTH (de novo) -> parathyroid vessel",
        "senses": "parathyroid vessel Ca2+",
        "regulation": (
            "Inversely calcium-dependent: at normal Ca2+, secretion is low-level "
            "short pulses; at low Ca2+, secretion is elevated and sustained."
        ),
    },
)
class PTHSecretion(DraftProcess):
    pass


@draft_process(
    name="Ca2+ absorption",
    inputs={"ca_source": "float", "pth_sense": "float"},
    outputs={"ca_absorbed": "float"},
    contract={
        "summary": (
            "Renal tubular calcium reabsorption: moves calcium from the nephron "
            "into the renal artery blood, up-regulated by PTH."
        ),
        "moves": "Ca2+: nephron -> renal artery",
        "senses": "renal artery PTH",
        "holds": "some amount of calcium (internal pool; amount TBD)",
        "regulation": "PTH-dependent: more PTH in the renal artery increases Ca2+ absorption.",
    },
)
class Ca2Absorption(DraftProcess):
    pass
