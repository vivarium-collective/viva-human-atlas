"""FTU-model coverage (Katy Boerner's "do any existing models try to model
FTUs?" question) + the CTpop -> FTU-model parameterization stub.

Offline (no network): `build_ftu_model_coverage` takes an in-memory
`catalog` fixture directly (same `{biomodel_dos, organ_index,
organ_to_models}` shape `coverage.load_corpus_catalog` returns) and never
touches the committed corpus file or the network.
"""
from __future__ import annotations

import viva_human_atlas.ftu_coverage as ftu_cov

_FIXTURE_CATALOG = {
    "biomodel_dos": [
        {
            "biomodel_id": "BIOMD_ISLET",
            "name": "Topp2000 - islet beta-cell mass model",
            "organs": [{"organ": "pancreas", "uberon": "UBERON:0001264"}],
        },
        {
            "biomodel_id": "BIOMD_CRYPT",
            "name": "Smallbone2011 - colon crypt stem cell dynamics",
            "organs": [{"organ": "large intestine", "uberon": "UBERON:0000059"}],
        },
        {
            "biomodel_id": "BIOMD_UNRELATED",
            "name": "Edelstein1996 - EPSP ACh event",
            "organs": [],
        },
    ],
    "organ_index": {},
    "organ_to_models": {},
}


def test_build_ftu_model_coverage_matches_islet_and_crypt():
    out = ftu_cov.build_ftu_model_coverage(catalog=_FIXTURE_CATALOG)
    by_ftu = {row["ftu"]: row for row in out["ftu_coverage"]}

    islet = by_ftu["pancreatic islet of Langerhans"]
    assert islet["covered"] is True
    assert islet["model_ids"] == ["BIOMD_ISLET"]
    assert islet["n_models"] == 1

    crypt_rows = [row for name, row in by_ftu.items() if name.startswith("large-intestine crypt")]
    assert len(crypt_rows) == 1
    crypt = crypt_rows[0]
    assert crypt["covered"] is True
    assert crypt["model_ids"] == ["BIOMD_CRYPT"]

    # The unrelated model matches no FTU at all.
    matched_ids = {mid for row in out["ftu_coverage"] for mid in row["model_ids"]}
    assert "BIOMD_UNRELATED" not in matched_ids

    # Other FTUs (no matching model in this tiny fixture) are uncovered.
    uncovered = [row for row in out["ftu_coverage"] if not row["covered"]]
    assert len(uncovered) >= 1
    assert all(row["n_models"] == 0 and row["model_ids"] == [] for row in uncovered)

    summary = out["summary"]
    assert summary["n_ftus"] == len(ftu_cov.HRA_FTUS)
    assert summary["n_ftus_covered"] == 2
    assert summary["n_models_matched"] == 2


def test_build_ftu_model_coverage_is_deterministic():
    out1 = ftu_cov.build_ftu_model_coverage(catalog=_FIXTURE_CATALOG)
    out2 = ftu_cov.build_ftu_model_coverage(catalog=_FIXTURE_CATALOG)
    assert out1 == out2


def test_ctpop_parameter_stub_islet_cell_types():
    stub = ftu_cov.ctpop_parameter_stub("pancreatic islet of Langerhans")
    assert stub["ftu"] == "pancreatic islet of Langerhans"
    cls = {ct["cl"] for ct in stub["cell_types"]}
    assert cls == {"CL:0000169", "CL:0000171", "CL:0000173"}
    assert "ctpop" in stub["note"].lower()
    assert "note" in stub and stub["note"]


def test_hra_ftus_has_at_least_ten_entries_with_required_ftus():
    names = {entry["ftu"] for entry in ftu_cov.HRA_FTUS}
    assert len(ftu_cov.HRA_FTUS) >= 10
    assert "pancreatic islet of Langerhans" in names
    # Every FTU has the required shape.
    for entry in ftu_cov.HRA_FTUS:
        assert entry["ftu"] and entry["organ"]
        assert isinstance(entry["cell_types"], list)
        assert isinstance(entry["synonyms"], list) and entry["synonyms"]


def test_discover_generators_includes_ftu_model_coverage():
    try:
        from viva_superpowers.composite_generator import discover_generators
    except ModuleNotFoundError:
        from pbg_superpowers.composite_generator import discover_generators

    import viva_human_atlas.composites  # noqa: F401 registers generators

    names = {g.name for g in discover_generators().values()}
    assert "ftu-model-coverage" in names


def test_ftu_model_coverage_study_baseline_resolves():
    import yaml
    from pathlib import Path

    try:
        from viva_superpowers.composite_generator import discover_generators
    except ModuleNotFoundError:
        from pbg_superpowers.composite_generator import discover_generators

    import viva_human_atlas.composites  # noqa: F401 registers generators

    generator_ids = set(discover_generators().keys())
    repo_root = Path(__file__).resolve().parents[1]
    study_path = repo_root / "studies" / "ftu-model-coverage" / "study.yaml"
    study = yaml.safe_load(study_path.read_text(encoding="utf-8"))
    baseline = study.get("baseline") or []
    assert baseline, "baseline must be non-empty"
    composite_id = baseline[0]["composite"]
    assert composite_id in generator_ids, (
        f"baseline.composite {composite_id!r} not in discover_generators() keys"
    )
