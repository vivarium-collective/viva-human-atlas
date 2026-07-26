"""FTU-model coverage (HRA-3D "Katy Boerner FTU" follow-up).

Answers Katy Boerner's question -- "do any existing models try to model
[functional tissue units]?" -- and stubs the CTpop -> FTU-model
parameterization seam she described (HRA Cell Type Populations, per-
anatomical-structure cell-type counts/proportions, that would set an FTU
model's cell-population parameters; the RUI -> CTpop -> model
parameterization Peter Hunter / SPARC-heart describe).

`HRA_FTUS` is a curated list of Human Reference Atlas functional tissue
units, each `{ftu, organ, cell_types: [{cl, label}], synonyms: [...]}`.
`build_ftu_model_coverage` matches the committed BioModels corpus catalog's
`biomodel_do.name` against each FTU's `synonyms` (case-insensitive substring
match) to answer, at name-matching granularity, which FTUs any curated model
already claims to model. `ctpop_parameter_stub` looks up an FTU's cell types
as candidate CTpop-parameterizable model inputs -- a v1 stub: it only
identifies *which* cell types a real CTpop binding would set, it does not
yet bind real per-structure cell-type counts to any model parameter.
"""
from __future__ import annotations

from typing import Optional

from process_bigraph import Step

from viva_human_atlas.coverage import load_corpus_catalog

_DEFAULT_CATALOG_PATH = "datasets/biomodel_corpus_catalog.json"

# Curated HRA functional tissue units. `cell_types` are the FTU's
# characteristic Cell-Ontology-keyed cell types (candidate CTpop
# parameterization targets, see `ctpop_parameter_stub`); `synonyms` are the
# lowercase substrings `build_ftu_model_coverage` matches against each
# catalog biomodel's `name`.
HRA_FTUS = [
    {
        "ftu": "pancreatic islet of Langerhans",
        "organ": "pancreas",
        "cell_types": [
            {"cl": "CL:0000169", "label": "type B pancreatic cell (beta cell)"},
            {"cl": "CL:0000171", "label": "pancreatic A cell (alpha cell)"},
            {"cl": "CL:0000173", "label": "pancreatic D cell (delta cell)"},
        ],
        "synonyms": [
            "islet", "beta cell", "langerhans", "insulin-secreting", "gsis",
        ],
    },
    {
        "ftu": "kidney renal corpuscle / glomerulus",
        "organ": "kidney",
        "cell_types": [
            {"cl": "CL:0000653", "label": "podocyte"},
        ],
        "synonyms": ["glomerul", "podocyte", "renal corpuscle"],
    },
    {
        "ftu": "kidney nephron",
        "organ": "kidney",
        "cell_types": [],
        "synonyms": ["nephron", "tubule"],
    },
    {
        "ftu": "liver lobule",
        "organ": "liver",
        "cell_types": [
            {"cl": "CL:0000182", "label": "hepatocyte"},
        ],
        "synonyms": ["lobule", "hepatocyte", "sinusoid"],
    },
    {
        "ftu": "lung alveolus",
        "organ": "lung",
        "cell_types": [
            {"cl": "CL:0002062", "label": "type I pneumocyte (AT1)"},
            {"cl": "CL:0002063", "label": "type II pneumocyte (AT2)"},
        ],
        "synonyms": ["alveol", "pneumocyte"],
    },
    {
        "ftu": "large-intestine crypt of Lieberkuhn",
        "organ": "large intestine",
        "cell_types": [],
        "synonyms": ["crypt", "colon crypt"],
    },
    {
        "ftu": "small-intestine crypt-villus axis",
        "organ": "small intestine",
        "cell_types": [],
        "synonyms": ["villus", "enterocyte"],
    },
    # SPARC-heart-relevant unit: this is the FTU the SPARC-heart / Peter
    # Hunter RUI->CTpop->model vision targets for cardiac digital twins.
    {
        "ftu": "cardiac muscle / myocardium unit",
        "organ": "heart",
        "cell_types": [
            {"cl": "CL:0000746", "label": "cardiac muscle cell (cardiomyocyte)"},
        ],
        "synonyms": ["cardiomyocyte", "myocyte", "sarcomere", "myocardial"],
    },
    {
        "ftu": "ovarian follicle",
        "organ": "ovary",
        "cell_types": [],
        "synonyms": ["follicle", "oocyte"],
    },
    {
        "ftu": "skin epidermis unit",
        "organ": "skin",
        "cell_types": [],
        "synonyms": ["epidermis", "keratinocyte"],
    },
    {
        "ftu": "lymph node follicle",
        "organ": "lymph node",
        "cell_types": [],
        "synonyms": ["lymphoid follicle", "germinal center", "germinal centre"],
    },
]


def build_ftu_model_coverage(
    catalog: Optional[dict] = None,
    *,
    catalog_path: str = _DEFAULT_CATALOG_PATH,
    ftus: Optional[list] = None,
) -> dict:
    """Match the corpus catalog's biomodels against `HRA_FTUS` by name/
    synonym substring.

    `catalog` is a `{biomodel_dos, organ_index, organ_to_models}` dict as
    returned by `coverage.load_corpus_catalog`; when `None` (the default)
    it is loaded from `catalog_path` (the committed full-corpus catalog,
    no network). `ftus` defaults to `HRA_FTUS`.

    A catalog biomodel matches an FTU when any of the FTU's `synonyms`
    (lowercased) appears as a substring of the biomodel's `name`
    (lowercased). Deterministic: catalog order determines `model_ids`
    order, FTU order (as given) determines `ftu_coverage` order.

    Returns `{"ftu_coverage": [{"ftu", "organ", "n_models", "model_ids",
    "covered"}, ...], "summary": {"n_ftus", "n_ftus_covered",
    "n_models_matched"}}`.
    """
    cat = catalog if catalog is not None else load_corpus_catalog(catalog_path)
    ftu_defs = ftus if ftus is not None else HRA_FTUS
    biomodel_dos = cat.get("biomodel_dos") or []

    ftu_coverage = []
    all_matched_ids: set[str] = set()
    for ftu in ftu_defs:
        synonyms = [s.lower() for s in ftu.get("synonyms") or []]
        model_ids = []
        for bmdo in biomodel_dos:
            name = (bmdo.get("name") or "").lower()
            if any(syn in name for syn in synonyms):
                model_ids.append(bmdo["biomodel_id"])
        all_matched_ids.update(model_ids)
        ftu_coverage.append(
            {
                "ftu": ftu["ftu"],
                "organ": ftu["organ"],
                "n_models": len(model_ids),
                "model_ids": model_ids,
                "covered": bool(model_ids),
            }
        )

    n_ftus = len(ftu_coverage)
    n_ftus_covered = sum(1 for row in ftu_coverage if row["covered"])

    return {
        "ftu_coverage": ftu_coverage,
        "summary": {
            "n_ftus": n_ftus,
            "n_ftus_covered": n_ftus_covered,
            "n_models_matched": len(all_matched_ids),
        },
    }


def ctpop_parameter_stub(ftu_name: str, *, ftus: Optional[list] = None) -> dict:
    """For a named FTU (from `HRA_FTUS`), return its cell types as
    CANDIDATE CTpop-parameterizable model inputs.

    HRA CTpop (Cell Type Populations, Bueckle 2026) gives per-anatomical-
    structure cell-type counts/proportions for a given RUI-registered
    tissue block -- e.g. an islet's measured beta/alpha/delta-cell counts.
    Those per-structure counts are exactly what would set an FTU model's
    cell-population parameters (e.g. the islet's beta/alpha/delta-cell
    counts binding the Topp2000/Jiang islet models' beta-cell-mass
    parameters) -- the RUI -> CTpop -> model parameterization Peter
    Hunter/SPARC describe for SPARC-heart and beyond.

    This is a v1 STUB: it only identifies which of the FTU's cell types are
    the candidate parameterizable inputs. Binding a *real* CTpop cell count
    to a *specific* model parameter is future work, not done here.

    Raises `KeyError` if `ftu_name` is not in `HRA_FTUS` (or `ftus`).
    """
    ftu_defs = ftus if ftus is not None else HRA_FTUS
    by_name = {entry["ftu"]: entry for entry in ftu_defs}
    if ftu_name not in by_name:
        raise KeyError(f"unknown FTU: {ftu_name!r}")
    entry = by_name[ftu_name]

    note = (
        "v1 STUB: identifies the FTU's cell types as CANDIDATE CTpop-"
        "parameterizable inputs; does not yet bind a real CTpop cell-type "
        "count to any model parameter. HRA CTpop (Cell Type Populations, "
        "Bueckle 2026) gives per-anatomical-structure cell-type "
        "counts/proportions for a RUI-registered tissue block -- e.g. "
        "measured beta/alpha/delta-cell counts for a specific islet -- "
        "which would set an FTU model's cell-population parameters (e.g. "
        "islet beta/alpha/delta-cell counts -> the Topp2000/Jiang islet "
        "models' beta-cell-mass parameters). This is the "
        "RUI -> CTpop -> model parameterization seam Peter Hunter/SPARC "
        "describe (SPARC-heart and beyond)."
    )
    return {
        "ftu": entry["ftu"],
        "cell_types": list(entry["cell_types"]),
        "note": note,
    }


class FtuModelCoverageStep(Step):
    """Step: cross the committed full-corpus BioModels catalog against the
    curated `HRA_FTUS` list by name/synonym substring match, answering
    which HRA functional tissue units any curated model already claims to
    model (`build_ftu_model_coverage`)."""

    description = (
        "Match the committed full-corpus BioModels catalog's model names "
        "against a curated list of HRA functional tissue units (FTUs) by "
        "synonym substring, marking which FTUs have at least one matching "
        "model."
    )

    config_schema = {"catalog_path": "string"}

    def inputs(self):
        return {}

    def outputs(self):
        return {
            "ftu_coverage": "list[ftu_coverage_row]",
            "ftu_coverage_summary": "ftu_coverage_summary",
        }

    def update(self, inputs):
        catalog_path = self.config.get("catalog_path") or _DEFAULT_CATALOG_PATH
        out = build_ftu_model_coverage(catalog_path=catalog_path)
        return {"ftu_coverage": out["ftu_coverage"], "ftu_coverage_summary": out["summary"]}


FtuModelCoverageStep.contract = {
    "summary": FtuModelCoverageStep.description,
    "outputs": {
        "ftu_coverage": (
            "One `ftu_coverage_row` per curated HRA FTU (`HRA_FTUS`): "
            "`ftu`, `organ`, `n_models`/`model_ids` (catalog biomodels "
            "whose name matched one of the FTU's synonyms), `covered` "
            "(True if n_models > 0)."
        ),
        "ftu_coverage_summary": (
            "Aggregate counts: `n_ftus`/`n_ftus_covered`, "
            "`n_models_matched` (distinct catalog biomodel ids matched to "
            "at least one FTU)."
        ),
    },
    "assumptions": [
        "v1 coverage is name/synonym substring matching against the "
        "biomodel-DO catalog's `name` field, not curated per-model FTU "
        "annotation -- a real mechanistic match may be missed (false "
        "negative) or an incidental name hit may overstate coverage "
        "(false positive).",
    ],
}
