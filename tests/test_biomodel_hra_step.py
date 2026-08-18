"""BiomodelHraMapStep + the load/summarize/cache-or-load layer.

Offline (no network): `load_map` / `summarize_map` are pure over a small
in-memory DB written to tmp; `build_or_load`'s cache path loads a pre-written
file without building; the Step is built via `build_core()` and run against a
tmp DB (build_if_missing off, so no extraction). One test asserts the Step's
summary numbers agree with the committed corpus DB.
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

import viva_human_atlas.biomodel_hra as bhm
from viva_human_atlas.core import build_core

REPO_ROOT = Path(__file__).resolve().parents[1]
COMMITTED_DB = REPO_ROOT / "datasets" / "model_hra_map.json"


def _entry(bid, *, chebi=(), uberon=(), cell_types=(), mesh=(), organs=(), ftus=(), hra_pop=None):
    return {
        "biomodel_id": bid,
        "identifier": f"https://identifiers.org/biomodels.db:{bid}",
        "organs": [{"label": o, "uberon": "UBERON:x"} for o in organs],
        "functional_tissue_units": [{"label": f, "uberon": "UBERON:y"} for f in ftus],
        "cell_types": [{"label": None, "cl": c} for c in cell_types],
        "molecular_ids": {"chebi": list(chebi), "uniprot": [], "kegg": [], "go": [], "reactome": []},
        "ontology_ids": {"uberon": list(uberon), "cl": [], "mesh": list(mesh), "fma": [], "bto": []},
        "hra_pop": hra_pop or [],
    }


def _sample_db():
    return {
        "BIOMD2": _entry("BIOMD2", chebi=["CHEBI:1"], uberon=["UBERON:1"],
                         cell_types=["CL:1", "CL:2"], mesh=["MESH:D1"], organs=["liver"],
                         hra_pop=[{"cell_types": [{"cl": "CL:1"}, {"cl": "CL:2"}, {"cl": "CL:3"}]}]),
        "BIOMD1": _entry("BIOMD1", chebi=[], uberon=[], cell_types=[], mesh=["MESH:D1", "MESH:D2"]),
    }


def test_load_map_returns_sorted_array(tmp_path):
    path = tmp_path / "db.json"
    bhm.write_db(_sample_db(), str(path))
    entries = bhm.load_map(path)
    assert isinstance(entries, list)
    assert [e["biomodel_id"] for e in entries] == ["BIOMD1", "BIOMD2"]  # sorted


def test_load_map_missing_file_is_empty(tmp_path):
    assert bhm.load_map(tmp_path / "nope.json") == []


def test_summarize_map_counts_coverage_mean_and_max(tmp_path):
    entries = list(_sample_db().values())
    s = bhm.summarize_map(entries)
    assert s["n_models"] == 2
    # only BIOMD2 has a molecular id / uberon / hra_pop
    assert s["n_with_molecular"] == 1
    assert s["n_with_uberon"] == 1
    assert s["n_with_hrapop"] == 1
    # mesh: both models carry >=1 -> count 2; means over non-zero only
    assert s["coverage"]["mesh"]["count"] == 2
    assert s["coverage"]["mesh"]["max"] == 2  # BIOMD1 has 2 mesh terms
    assert s["coverage"]["cell_types"]["count"] == 1  # only BIOMD2
    assert s["coverage"]["cell_types"]["mean"] == 2.0  # BIOMD2 has 2 cell types
    assert s["coverage"]["hra_pop_cell_types"]["count"] == 1
    assert s["coverage"]["hra_pop_cell_types"]["max"] == 3


def test_build_or_load_cache_path_does_not_build(tmp_path, monkeypatch):
    path = tmp_path / "db.json"
    bhm.write_db(_sample_db(), str(path))

    def boom(*a, **k):  # build_map must NOT be called when the cache exists
        raise AssertionError("build_map should not run on the cache path")

    monkeypatch.setattr(bhm, "build_map", boom)
    entries = bhm.build_or_load(out=str(path))
    assert [e["biomodel_id"] for e in entries] == ["BIOMD1", "BIOMD2"]


def test_build_or_load_missing_without_build_returns_empty(tmp_path):
    entries = bhm.build_or_load(out=str(tmp_path / "nope.json"), build_if_missing=False)
    assert entries == []


def test_step_update_emits_path_count_and_summary(tmp_path):
    path = tmp_path / "db.json"
    bhm.write_db(_sample_db(), str(path))
    core = build_core()
    step = bhm.BiomodelHraMapStep(
        config={"db_path": str(path), "build_if_missing": False}, core=core)
    out = step.update({})
    assert out["db_path"] == str(path)
    assert out["n_models"] == 2
    assert out["summary"]["n_with_molecular"] == 1
    assert set(out["summary"]["coverage"]) == {
        "organs", "functional_tissue_units", "cell_types", "uberon",
        "hra_pop_cell_types", "mesh", "chebi", "uniprot", "kegg", "go",
    }


def test_step_writes_per_run_analysis_copy_when_dir_injected(tmp_path):
    db = tmp_path / "db.json"
    bhm.write_db(_sample_db(), str(db))
    out = tmp_path / "analyses" / "run1"
    core = build_core()
    step = bhm.BiomodelHraMapStep(config={
        "db_path": str(db), "build_if_missing": False,
        "analysis_out_dir": str(out)}, core=core)
    step.update({})
    artifact = out / "model_hra_map.json"
    assert artifact.exists()
    assert json.loads(artifact.read_text())  # non-empty DB array


def test_step_no_analysis_copy_without_dir(tmp_path):
    db = tmp_path / "db.json"
    bhm.write_db(_sample_db(), str(db))
    core = build_core()
    step = bhm.BiomodelHraMapStep(config={"db_path": str(db), "build_if_missing": False}, core=core)
    out = step.update({})  # no analysis_out_dir -> no write, no error
    assert out["n_models"] == 2
    assert not (tmp_path / "analyses").exists()


def test_step_summary_matches_committed_corpus_db():
    """The Step over the committed DB reports the headline coverage the study
    report + summary figure quote. Across three sources the DB is 1,096 BioModels
    + 480 PhysioNet + 978 Physiome = 2,554 models (Physiome rebuilt onto the pmr3
    API); PhysioNet and Physiome rows carry no molecular/HRApop data (offline /
    category-based organ mappers only). Counts reflect the ontology-resolver remap
    (Task 5: scripts/remap_organs.py re-mapped every row from its existing
    annotations -- BioModels via anatomy_resolver directly, Physiome/PhysioNet via
    their own keyword/category mappers (their ontology_ids.uberon is an echo of a
    prior keyword match, not a raw annotation) -- n_with_uberon rose 788->901,
    then gated back down to 868 by the CL_MAX_ORGANS specificity gate on the
    cell_type tier, Task 5 fix round 2 (final review))."""
    if not COMMITTED_DB.exists():
        return  # DB not present in this checkout; nothing to assert
    core = build_core()
    step = bhm.BiomodelHraMapStep(
        config={"db_path": str(COMMITTED_DB), "build_if_missing": False}, core=core)
    out = step.update({})
    assert out["n_models"] == 2554
    assert out["summary"]["n_with_molecular"] == 978
    assert out["summary"]["n_with_uberon"] == 868
    assert out["summary"]["n_with_hrapop"] == 112


def test_study_yaml_wires_step_and_figure():
    study = yaml.safe_load(
        (REPO_ROOT / "studies" / "biomodel-hra-map" / "study.yaml").read_text(encoding="utf-8"))
    assert study["name"] == "biomodel-hra-map"
    assert study["investigation"] == "hra-integration"
    # Migrated from `baseline.composite` (single-Step wrapper) to `baseline.step`
    # referencing the Step directly.
    assert "composite" not in study["baseline"][0]
    assert study["baseline"][0]["step"] == (
        "local:viva_human_atlas.biomodel_hra.BiomodelHraMapStep")
    assert study["embed_visualizations"][0]["url"] == (
        "/reports/figures/biomodel-hra-map/summary.html")


def test_workspace_registers_downloadable_dataset():
    ws = yaml.safe_load((REPO_ROOT / "workspace.yaml").read_text(encoding="utf-8"))
    ds = [d for d in (ws.get("datasets") or []) if d.get("name") == "biomodel-hra-map"]
    assert ds, "biomodel-hra-map dataset not registered in workspace.yaml"
    assert ds[0]["path"] == "datasets/model_hra_map.json"


def test_cli_delegates_to_shared_core():
    """The slimmed CLI imports the shared multi-source harvest it delegates to
    (scripts/harvest_models.py is the general CLI; this one pins --source
    biomodels)."""
    import importlib.util

    from viva_human_atlas import model_harvest
    spec = importlib.util.spec_from_file_location(
        "bhm_cli", REPO_ROOT / "scripts" / "build_biomodel_hra_map.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    assert cli.harvest is model_harvest.harvest
