"""Composite generator wrapping `CtpopIsletParameterizationStep` (the
`fp-ctpop-parameterize-islet` follow-up: bind HRA CTpop islet cell-type
composition to the Topp2000 beta-cell-mass model, BIOMD0000000341, and show
the glucose-regulation consequence).

Same state/emitter shape as `ftu_coverage_composite.py` /
`spatial_link_composite.py`: a single Step feeding a RAMEmitter, computed at
update-time (network: fetches the Topp SBML from BioModels).
"""
from __future__ import annotations

from typing import Any, Dict

try:
    from viva_superpowers.composite_generator import composite_generator
except ModuleNotFoundError:
    from pbg_superpowers.composite_generator import composite_generator

# Fully-dotted address (see `hra_steps.py` for why: lets vivarium-workbench
# resolve this Step's description/contract without a live-built core).
CTPOP_ISLET_STEP_ADDRESS = "local:viva_human_atlas.ctpop_islet.CtpopIsletParameterizationStep"

DEFAULT_MODEL_ID = "BIOMD0000000341"
DEFAULT_T_END = 4000.0
DEFAULT_N_POINTS = 200


def build_ctpop_islet_document(
    model_id: str = DEFAULT_MODEL_ID,
    t_end: float = DEFAULT_T_END,
    n_points: int = DEFAULT_N_POINTS,
) -> Dict[str, Any]:
    emit_schema = {
        "runs": "node",
        "islet_composition": "node",
        "reference_beta_fraction": "node",
    }
    state: Dict[str, Any] = {
        "runs": {},
        "islet_composition": {},
        "reference_beta_fraction": 0.0,
        "ctpop_islet_step": {
            "_type": "step",
            "address": CTPOP_ISLET_STEP_ADDRESS,
            "config": {"model_id": model_id, "t_end": t_end, "n_points": n_points},
            "inputs": {},
            "outputs": {
                "runs": ["runs"],
                "islet_composition": ["islet_composition"],
                "reference_beta_fraction": ["reference_beta_fraction"],
            },
        },
        "emitter": {
            "_type": "step",
            "address": "local:RAMEmitter",
            "config": {"emit": emit_schema},
            "inputs": {k: [k] for k in emit_schema},
        },
    }
    return {"state": state, "run_steps_on_init": True}


@composite_generator(
    name="ctpop-islet-parameterization",
    description=(
        "Bind documented HRA-aligned islet beta-cell-composition fractions "
        "to the Topp2000 beta-cell-mass model's (BIOMD0000000341) initial "
        "beta-cell mass, and run healthy vs beta-depleted composition "
        "scenarios to show the resulting glucose-regulation consequence."
    ),
    parameters={
        "model_id": {
            "type": "string",
            "default": DEFAULT_MODEL_ID,
            "description": "BioModels identifier of the Topp2000 beta-cell-mass model.",
        },
        "t_end": {
            "type": "float",
            "default": DEFAULT_T_END,
            "description": (
                "Simulated horizon in the model's own time units. The Topp "
                "model operates on a DAYS timescale (beta-cell-mass "
                "turnover); a multi-thousand-unit horizon is needed for B "
                "and G to visibly move."
            ),
        },
        "n_points": {
            "type": "integer",
            "default": DEFAULT_N_POINTS,
            "description": "Number of output time points per scenario.",
        },
    },
    default_n_steps=1,
)
def build_ctpop_islet_composite(
    core: Any = None,
    *,
    model_id: str = DEFAULT_MODEL_ID,
    t_end: float = DEFAULT_T_END,
    n_points: int = DEFAULT_N_POINTS,
) -> Dict[str, Any]:
    return build_ctpop_islet_document(model_id=model_id, t_end=t_end, n_points=n_points)
