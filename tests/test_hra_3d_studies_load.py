"""Demonstrate-loading tests for the HRA-3D studies (Task E).

Offline (mocked): each of the four HRA-3D composite generators
(`hra-3d-crosswalk`, `model-coverage-3d`, `spatial-linkage`, `ftu-glomerulus`)
is built via `build_core()`, run once, and the RAMEmitter snapshot is
asserted non-empty. `discover_generators()` must surface all four, and each
of the four studies' `baseline.composite` must resolve to a registered
generator id.

`@pytest.mark.network`: `build_coverage` is run against real data (crosswalk
CSV + BioModels search + HRA reference organs) and asserted to cover at
least 1,000 anatomical structures with at least one covered organ.
"""
from __future__ import annotations

import yaml
from pathlib import Path

import pytest
from process_bigraph import Composite, gather_emitter_results

import viva_human_atlas.biomodel_do as biomodel_do
import viva_human_atlas.composites.coverage_composite as coverage_composites
import viva_human_atlas.composites.hra_steps as hra_steps_composites
import viva_human_atlas.composites.spatial_link_composite as spatial_link_composites
import viva_human_atlas.coverage as coverage_mod
import viva_human_atlas.hra_api as hra_api
import viva_human_atlas.spatial_link as spatial_link_mod
from viva_human_atlas.core import build_core

REPO_ROOT = Path(__file__).resolve().parents[1]

STUDY_SLUGS = ["hra-3d-crosswalk", "model-coverage-3d", "spatial-linkage", "ftu-glomerulus"]


def _run(doc):
    core = build_core()
    composite = Composite(doc, core=core)
    composite.run(0.0)  # Steps run on init; this flushes the emitter.
    snap = (gather_emitter_results(composite).get(("emitter",)) or [{}])[-1]
    return snap


_FAKE_CROSSWALK_ROWS = [
    {
        "node_name": "VH_F_kidney",
        "label": "kidney",
        "uberon": "UBERON:0002113",
        "representation_of": "http://purl.obolibrary.org/obo/UBERON_0002113",
        "node_type": "mesh",
        "organ_glb": "VH_F_Kidney",
        "parent": "VH_F",
    },
    {
        "node_name": "VH_F",
        "label": "",
        "uberon": "",
        "representation_of": "",
        "node_type": "organizational",
        "organ_glb": "",
        "parent": "",
    },
]

_FAKE_FTU = {
    "slug": "glomerulus",
    "title": "glomerulus (v1.0)",
    "description": "Renal corpuscle FTU",
    "glb": "glomerulus.glb",
    "glb_url": (
        "https://cdn.humanatlas.io/digital-objects/3d-ftu/glomerulus/latest/"
        "assets/glomerulus.glb"
    ),
}

_FAKE_CATALOG = {
    "biomodel_dos": [
        {
            "biomodel_id": "BIOMD_KIDNEY",
            "name": "renal glucose model",
            "organs": [{"organ": "kidney", "uberon": "UBERON:0002113"}],
            "provenance": {"source": "biomodels", "annotation": "synonym-match@HRA-reference-organs"},
        }
    ],
    "organ_index": {
        "kidney": {"uberon": "UBERON:0002113", "sexes": ["Female"], "asset_urls": ["x/VH_F_Kidney.glb"]}
    },
    "organ_to_models": {"UBERON:0002113": ["BIOMD_KIDNEY"]},
}


def test_hra_3d_crosswalk_composite_loads(monkeypatch):
    monkeypatch.setattr(hra_api, "fetch_crosswalk", lambda *a, **k: _FAKE_CROSSWALK_ROWS)
    doc = hra_steps_composites.build_hra_3d_crosswalk()
    snap = _run(doc)
    rows = snap.get("anatomical_structures_3d", [])
    assert len(rows) >= 1
    assert rows[0]["uberon"] == "UBERON:0002113"


def test_ftu_glomerulus_composite_loads(monkeypatch):
    monkeypatch.setattr(hra_api, "fetch_ftu", lambda *a, **k: _FAKE_FTU)
    doc = hra_steps_composites.build_ftu_glomerulus()
    snap = _run(doc)
    ftu = snap.get("ftu", {})
    assert ftu.get("slug") == "glomerulus"
    assert ftu.get("glb_url", "").endswith("glomerulus.glb")


def test_model_coverage_3d_composite_loads(monkeypatch):
    monkeypatch.setattr(coverage_mod, "build_biomodel_do_catalog", lambda *a, **k: _FAKE_CATALOG)
    monkeypatch.setattr(coverage_mod, "fetch_crosswalk", lambda **k: _FAKE_CROSSWALK_ROWS)
    doc = coverage_composites.build_model_coverage_3d()
    snap = _run(doc)
    rows = snap.get("coverage", [])
    summary = snap.get("coverage_summary", {})
    assert len(rows) >= 1
    assert summary.get("n_as", 0) >= 1
    assert any(r["covered"] for r in rows)


def test_spatial_linkage_composite_loads(monkeypatch):
    monkeypatch.setattr(spatial_link_mod, "build_biomodel_do_catalog", lambda *a, **k: _FAKE_CATALOG)
    monkeypatch.setattr(spatial_link_mod, "fetch_crosswalk", lambda **k: _FAKE_CROSSWALK_ROWS)
    doc = spatial_link_composites.build_spatial_linkage()
    snap = _run(doc)
    links = snap.get("links", [])
    summary = snap.get("spatial_link_summary", {})
    assert len(links) >= 1
    assert links[0]["node_name"] == "VH_F_kidney"
    assert summary.get("n_links", 0) >= 1


def test_all_four_hra_3d_generators_discovered():
    try:
        from viva_superpowers.composite_generator import discover_generators
    except ModuleNotFoundError:
        from pbg_superpowers.composite_generator import discover_generators
    import viva_human_atlas  # noqa: F401  (fires decorators)

    names = {g.name for g in discover_generators().values()}
    assert {
        "hra-3d-crosswalk",
        "model-coverage-3d",
        "spatial-linkage",
        "ftu-glomerulus",
    } <= names


def test_hra_3d_study_baselines_resolve_to_registered_generators():
    try:
        from viva_superpowers.composite_generator import discover_generators
    except ModuleNotFoundError:
        from pbg_superpowers.composite_generator import discover_generators
    import viva_human_atlas  # noqa: F401  (fires decorators)

    generator_ids = set(discover_generators().keys())
    assert generator_ids, "discover_generators() returned nothing"

    for slug in STUDY_SLUGS:
        study_path = REPO_ROOT / "studies" / slug / "study.yaml"
        study = yaml.safe_load(study_path.read_text(encoding="utf-8"))
        baseline = study.get("baseline") or []
        assert baseline, f"{slug}: baseline must be non-empty"
        composite_id = baseline[0]["composite"]
        assert composite_id in generator_ids, (
            f"{slug}: baseline.composite {composite_id!r} not in "
            f"discover_generators() keys"
        )


@pytest.mark.network
def test_coverage_live_summary():
    out = coverage_mod.build_coverage()
    summary = out["summary"]
    assert summary["n_as"] >= 1000
    assert any(row["covered"] for row in out["coverage"])
