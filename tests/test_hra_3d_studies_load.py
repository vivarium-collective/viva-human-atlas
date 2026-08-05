"""Demonstrate-loading tests for the HRA-3D studies (Task E).

`baseline.step` replaced the single-Step wrapper composites: each study now
references its Step directly. Offline (mocked): each of the four HRA-3D Steps
(`HRACrosswalkStep`, `CoverageStep`, `SpatialLinkStep`, `HRAFtuStep`) is
wrapped in a single-Step composite doc via `step_doc(...)`, built via
`build_core()`, run once, and the RAMEmitter snapshot is asserted non-empty.
Each of the four studies' `baseline.step` must resolve to a real, registered
Step.

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
import viva_human_atlas.coverage as coverage_mod
import viva_human_atlas.hra_api as hra_api
import viva_human_atlas.spatial_link as spatial_link_mod
from viva_human_atlas.core import build_core

from _step_doc import step_doc, resolve_step_class, registered_step_addresses

REPO_ROOT = Path(__file__).resolve().parents[1]

STUDY_SLUGS = ["hra-3d-crosswalk", "model-coverage-3d", "spatial-linkage", "ftu-glomerulus"]

CROSSWALK_ADDRESS = "local:viva_human_atlas.hra_api.HRACrosswalkStep"
FTU_ADDRESS = "local:viva_human_atlas.hra_api.HRAFtuStep"
COVERAGE_ADDRESS = "local:viva_human_atlas.coverage.CoverageStep"
SPATIAL_LINK_ADDRESS = "local:viva_human_atlas.spatial_link.SpatialLinkStep"

_CROSSWALK_CONFIG = {
    "url": (
        "https://cdn.humanatlas.io/digital-objects/ref-organ/"
        "asct-b-3d-models-crosswalk/latest/assets/asct-b-3d-models-crosswalk.csv"
    )
}
_FTU_CONFIG = {"slug": "glomerulus"}
_QUERY_CONFIG = {"query": "glucose regulation", "max_results": 25}

# migrated study slug -> expected baseline step address
STUDY_STEP_ADDRESSES = {
    "hra-3d-crosswalk": CROSSWALK_ADDRESS,
    "model-coverage-3d": COVERAGE_ADDRESS,
    "spatial-linkage": SPATIAL_LINK_ADDRESS,
    "ftu-glomerulus": FTU_ADDRESS,
}


def _run(doc, core=None):
    core = core or build_core()
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
    core = build_core()
    doc = step_doc(CROSSWALK_ADDRESS, _CROSSWALK_CONFIG, core)
    snap = _run(doc, core)
    rows = snap.get("anatomical_structures_3d", [])
    assert len(rows) >= 1
    assert rows[0]["uberon"] == "UBERON:0002113"


def test_ftu_glomerulus_composite_loads(monkeypatch):
    monkeypatch.setattr(hra_api, "fetch_ftu", lambda *a, **k: _FAKE_FTU)
    core = build_core()
    doc = step_doc(FTU_ADDRESS, _FTU_CONFIG, core)
    snap = _run(doc, core)
    ftu = snap.get("ftu", {})
    assert ftu.get("slug") == "glomerulus"
    assert ftu.get("glb_url", "").endswith("glomerulus.glb")


def test_model_coverage_3d_composite_loads(monkeypatch):
    monkeypatch.setattr(coverage_mod, "build_biomodel_do_catalog", lambda *a, **k: _FAKE_CATALOG)
    monkeypatch.setattr(coverage_mod, "fetch_crosswalk", lambda **k: _FAKE_CROSSWALK_ROWS)
    core = build_core()
    doc = step_doc(COVERAGE_ADDRESS, _QUERY_CONFIG, core)
    snap = _run(doc, core)
    rows = snap.get("coverage", [])
    summary = snap.get("coverage_summary", {})
    assert len(rows) >= 1
    assert summary.get("n_as", 0) >= 1
    assert any(r["covered"] for r in rows)


def test_spatial_linkage_composite_loads(monkeypatch):
    monkeypatch.setattr(spatial_link_mod, "build_biomodel_do_catalog", lambda *a, **k: _FAKE_CATALOG)
    monkeypatch.setattr(spatial_link_mod, "fetch_crosswalk", lambda **k: _FAKE_CROSSWALK_ROWS)
    core = build_core()
    doc = step_doc(SPATIAL_LINK_ADDRESS, _QUERY_CONFIG, core)
    snap = _run(doc, core)
    links = snap.get("links", [])
    summary = snap.get("spatial_link_summary", {})
    assert len(links) >= 1
    assert links[0]["node_name"] == "VH_F_kidney"
    assert summary.get("n_links", 0) >= 1


def test_hra_3d_study_baselines_reference_registered_steps():
    """The four HRA-3D studies migrated from `baseline.composite` (single-Step
    wrapper generators) to `baseline.step`. Assert each migrated study's
    baseline references a real, registered Step at the expected address."""
    core = build_core()
    registered = registered_step_addresses(core)
    for slug in STUDY_SLUGS:
        study_path = REPO_ROOT / "studies" / slug / "study.yaml"
        study = yaml.safe_load(study_path.read_text(encoding="utf-8"))
        baseline = study.get("baseline") or []
        assert baseline, f"{slug}: baseline must be non-empty"
        assert "composite" not in baseline[0], (
            f"{slug}: baseline still uses `composite`; expected migrated `step`"
        )
        address = baseline[0]["step"]
        expected = STUDY_STEP_ADDRESSES[slug]
        assert address == expected, (
            f"{slug}: baseline.step {address!r} != expected {expected!r}"
        )
        # Resolves to a real Step subclass ...
        resolve_step_class(address)
        # ... and is registered by build_core().
        assert address in registered, (
            f"{slug}: baseline.step {address!r} not registered in build_core()"
        )


@pytest.mark.network
def test_coverage_live_summary():
    out = coverage_mod.build_coverage()
    summary = out["summary"]
    assert summary["n_as"] >= 1000
    assert any(row["covered"] for row in out["coverage"])
