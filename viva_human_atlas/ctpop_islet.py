"""CTpop -> Topp2000 beta-cell-mass model parameterization (realizes the
`fp-ctpop-parameterize-islet` follow-up from `ftu-model-coverage`, Katy
Boerner's CTpop -> FTU-model vision).

`ftu_coverage.ctpop_parameter_stub` identified the pancreatic islet's
beta/alpha/delta cell types (CL:0000169/0171/0173) as candidate CTpop-
parameterizable inputs for the islet's beta-cell-mass models, but bound no
real cell-type count to any model parameter. This module takes that next
step for the Topp2000 beta-cell-mass model (BIOMD0000000341, Topp et al.
2000 J Theor Biol): it maps a documented HRA-aligned islet beta-cell
FRACTION onto the model's initial beta-cell mass (`B`), then runs the model
to show the glucose-regulation consequence of a real (if not yet
live-CTpop-sourced) composition shift.

A live HRA CTpop API pull is not (as of this writing) publicly exposed as
JSON, so `ISLET_COMPOSITION` uses documented literature/HRA-ASCT+B
composition values instead -- each entry cites its source. Binding is
initial-mass only: `beta_fraction_to_beta_mass` rescales the Topp model's own
default initial `B` (read out of the SBML, never hardcoded) by the ratio of
the queried beta fraction to the reference (healthy) fraction. Per-cell-type
parameter binding (alpha/delta influencing separate model parameters) is
future work -- see `discovery_implications` in the
ctpop-islet-parameterization study.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

from process_bigraph import Step

DEFAULT_MODEL_ID = "BIOMD0000000341"
DEFAULT_T_END = 4000.0
DEFAULT_N_POINTS = 200

# Reference (healthy) beta-cell fraction the binding is calibrated against.
REFERENCE_BETA_FRACTION = 0.54

# Documented HRA-aligned human pancreatic islet cell-type composition.
# A live CTpop (Cell Type Populations, Bueckle 2026) API pull is NOT
# publicly exposed as JSON as of this writing -- these are documented
# literature/HRA-ASCT+B composition values instead, cited per cell type.
ISLET_COMPOSITION = {
    "beta": {
        "cl": "CL:0000169",
        "label": "type B pancreatic cell (beta cell)",
        "fraction": 0.54,
        "citation": "Cabrera et al. 2006 PNAS 103(7):2334-2339 (human islet architecture)",
    },
    "alpha": {
        "cl": "CL:0000171",
        "label": "pancreatic A cell (alpha cell)",
        "fraction": 0.34,
        "citation": "Cabrera et al. 2006 PNAS; Brissova et al. 2005 J Histochem Cytochem 53(9):1087-97",
    },
    "delta": {
        "cl": "CL:0000173",
        "label": "pancreatic D cell (delta cell)",
        "fraction": 0.10,
        "citation": "Cabrera et al. 2006 PNAS; Brissova et al. 2005; HRA ASCT+B pancreas",
    },
    "pp_epsilon": {
        "cl": None,
        "label": "PP/epsilon cells (pancreatic-polypeptide + ghrelin cells)",
        "fraction": 0.02,
        "citation": "Cabrera et al. 2006 PNAS; Brissova et al. 2005; HRA ASCT+B pancreas",
    },
}


def beta_fraction_to_beta_mass(
    beta_fraction: float, b_ref: float, ref_fraction: float = REFERENCE_BETA_FRACTION
) -> float:
    """Map a CTpop beta-cell fraction to a Topp2000 initial beta-cell mass.

    `B_init = b_ref * (beta_fraction / ref_fraction)`: proportional scaling
    of the Topp model's own default initial `B` (`b_ref`, read out of its
    SBML) by the ratio of the queried islet's beta fraction to the reference
    (healthy, `ref_fraction=0.54`) fraction -- so a healthy islet (54% beta)
    reproduces `b_ref` exactly, and a beta-depleted islet (e.g. 30% beta, the
    T2D-relevant beta-cell loss) uses a proportionally lower initial mass.
    """
    return b_ref * (beta_fraction / ref_fraction)


def _default_b_ref_from_sbml(sbml_path: str) -> Optional[float]:
    """Read the Topp model's own default initial beta-cell mass (species
    `B`'s `initialConcentration`) straight out of the SBML, so the binding
    never hardcodes it. Returns None if the SBML can't be parsed or lacks
    species `B`."""
    try:
        import libsbml

        doc = libsbml.SBMLReader().readSBMLFromFile(str(sbml_path))
        model = doc.getModel() if doc is not None else None
        if model is None:
            return None
        species = model.getSpecies("B")
        if species is None:
            return None
        return float(species.getInitialConcentration())
    except Exception:
        return None


def _fetch_topp_sbml(model_id: str = DEFAULT_MODEL_ID) -> Optional[str]:
    """Fetch the Topp2000 SBML from BioModels, returning a local file path
    (or None on any failure).

    Reuses the `biomodels` package `viva_biomodels.run_biomodels.load_biomodel`
    already wraps for this workspace's other composites, but sidesteps its
    SED-ML requirement -- `load_biomodel` raises if no `.sedml` file is
    present in the BioModels entry, which this binding doesn't need (only the
    SBML's species initial values and parameters matter here).
    """
    try:
        import biomodels

        meta = biomodels.get_metadata(model_id)
        candidates = [
            f
            for f in meta.files
            if f.name.lower().endswith(".xml") and "manifest" not in f.name.lower()
        ]
        # Prefer the curated "<id>_url.xml" SBML export BioModels ships.
        sbml_file = next((f for f in candidates if f.name.endswith("_url.xml")), None)
        if sbml_file is None:
            sbml_file = candidates[0] if candidates else None
        if sbml_file is None:
            return None
        path = biomodels.get_file(sbml_file, model_id=model_id)
        return str(path)
    except Exception:
        return None


def run_topp_with_composition(
    beta_fraction: float,
    *,
    model_id: str = DEFAULT_MODEL_ID,
    t_end: float = DEFAULT_T_END,
    n_points: int = DEFAULT_N_POINTS,
    ref_fraction: float = REFERENCE_BETA_FRACTION,
) -> Dict[str, Any]:
    """Fetch the Topp2000 SBML, bind `beta_fraction` to its initial
    beta-cell mass (`beta_fraction_to_beta_mass`), run it via
    `viva_tellurium.TelluriumProcess`, and return the glucose/insulin/
    beta-cell-mass trajectory.

    The Topp model operates on a DAYS timescale (beta-cell-mass turnover is
    slow relative to glucose/insulin kinetics) -- `t_end`/`n_points` default
    to a multi-thousand-day horizon (~11 years) long enough for `B` and `G`
    to visibly move off their initial values.

    Returns `{"time": [...], "B": [...], "G": [...], "I": [...],
    "beta_fraction": ..., "b_init": ..., "b_ref": ..., "model_id": ...}`.
    Tolerant: returns `{}` on any failure (network, missing deps, SBML
    parse, solver failure) -- never raises.
    """
    try:
        sbml_path = _fetch_topp_sbml(model_id)
        if not sbml_path:
            return {}

        b_ref = _default_b_ref_from_sbml(sbml_path)
        if b_ref is None:
            return {}

        b_init = beta_fraction_to_beta_mass(beta_fraction, b_ref, ref_fraction)

        from process_bigraph import allocate_core
        from viva_tellurium.processes import TelluriumProcess

        core = allocate_core()
        proc = TelluriumProcess(
            config={
                "model_file": sbml_path,
                "model_format": "sbml",
                "species_overrides": {"B": b_init},
            },
            core=core,
        )
        # `initial_state()` triggers TelluriumProcess's model load + config
        # overrides (`_build()`). The Topp SBML represents G/I/B as boundary
        # species driven by rate rules, not floating species, so
        # TelluriumProcess's generic `species` output port (which only
        # tracks `getFloatingSpeciesIds()`) can't see them. Read the
        # trajectory directly off the underlying roadrunner instance instead,
        # via one continuous `simulate()` call over the full horizon: a
        # chunked tick-by-tick `update()` loop was tried first and fails
        # numerically (CVODE convergence failure) right at this model's
        # beta-cell-mass bifurcation, whereas one continuous simulate() call
        # is stable.
        proc.initial_state()
        result = proc._rr.simulate(0, float(t_end), int(n_points))

        return {
            "time": [float(v) for v in result["time"]],
            "B": [float(v) for v in result["B"]],
            "G": [float(v) for v in result["G"]],
            "I": [float(v) for v in result["I"]],
            "beta_fraction": float(beta_fraction),
            "b_init": float(b_init),
            "b_ref": float(b_ref),
            "model_id": model_id,
        }
    except Exception:
        return {}


def compare_islet_compositions(
    fractions: Sequence[float] = (0.54, 0.30),
    *,
    model_id: str = DEFAULT_MODEL_ID,
    t_end: float = DEFAULT_T_END,
    n_points: int = DEFAULT_N_POINTS,
    labels: Sequence[str] = ("healthy", "beta_depleted"),
) -> Dict[str, Any]:
    """Run the Topp model once per beta-cell fraction in `fractions`
    (default: healthy islet at 54% beta vs a beta-depleted islet at 30% beta
    -- the T2D-relevant beta-cell loss), binding each via
    `run_topp_with_composition`.

    Returns `{"runs": {label: run_topp_with_composition(...) result, ...},
    "scenarios": [label, ...], "islet_composition": ISLET_COMPOSITION,
    "reference_beta_fraction": REFERENCE_BETA_FRACTION}`.
    """
    runs: Dict[str, Any] = {}
    scenarios = []
    for label, frac in zip(labels, fractions):
        runs[label] = run_topp_with_composition(
            frac, model_id=model_id, t_end=t_end, n_points=n_points
        )
        scenarios.append(label)

    return {
        "runs": runs,
        "scenarios": scenarios,
        "islet_composition": ISLET_COMPOSITION,
        "reference_beta_fraction": REFERENCE_BETA_FRACTION,
    }


class CtpopIsletParameterizationStep(Step):
    """Step: bind HRA CTpop islet cell-type composition to the Topp2000
    beta-cell-mass model and run healthy-vs-beta-depleted scenarios
    (`compare_islet_compositions`) at update-time."""

    description = (
        "Bind documented HRA-aligned islet beta-cell fractions to the "
        "Topp2000 beta-cell-mass model's (BIOMD0000000341) initial "
        "beta-cell mass, and run healthy vs beta-depleted composition "
        "scenarios to show the glucose-regulation consequence."
    )

    config_schema = {
        "model_id": "string",
        "t_end": "float",
        "n_points": "integer",
    }

    def inputs(self):
        return {}

    def outputs(self):
        return {
            "runs": "tree",
            "islet_composition": "tree",
            "reference_beta_fraction": "float",
        }

    def update(self, inputs):
        out = compare_islet_compositions(
            model_id=self.config.get("model_id") or DEFAULT_MODEL_ID,
            t_end=float(self.config.get("t_end") or DEFAULT_T_END),
            n_points=int(self.config.get("n_points") or DEFAULT_N_POINTS),
        )
        return {
            "runs": out["runs"],
            "islet_composition": out["islet_composition"],
            "reference_beta_fraction": out["reference_beta_fraction"],
        }


CtpopIsletParameterizationStep.contract = {
    "summary": CtpopIsletParameterizationStep.description,
    "outputs": {
        "runs": (
            "Per-scenario Topp2000 trajectory (`healthy`/`beta_depleted` by "
            "default): `time`/`B`/`G`/`I` arrays plus `beta_fraction`/"
            "`b_init`/`b_ref`/`model_id`. Empty dict per scenario on any "
            "fetch/solve failure (network, missing deps, SBML parse, "
            "solver)."
        ),
        "islet_composition": (
            "Echo of `ISLET_COMPOSITION`: documented HRA-aligned islet "
            "beta/alpha/delta/PP-epsilon fractions, each with its "
            "Cell-Ontology id and literature citation."
        ),
        "reference_beta_fraction": (
            "The healthy reference beta-cell fraction (0.54) the binding "
            "scales against."
        ),
    },
    "assumptions": [
        "ISLET_COMPOSITION is documented literature/HRA-ASCT+B composition, "
        "not a live HRA CTpop API pull -- a live CTpop query for a specific "
        "RUI-registered tissue block would give a different, "
        "block-specific composition.",
        "Binding is initial-mass only: the beta fraction rescales the "
        "Topp model's initial beta-cell mass B; alpha/delta fractions are "
        "not (yet) bound to any Topp model parameter.",
    ],
}
