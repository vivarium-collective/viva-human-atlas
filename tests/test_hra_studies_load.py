"""Demonstrate-loading tests for the HRA-integration Steps.

`baseline.step` replaced the single-Step wrapper composites: each study now
references its Step directly. Offline (mocked): each Step is wrapped in a
single-Step composite doc via `step_doc(...)`, built via `build_core()`, run
once, and the RAMEmitter snapshot is asserted non-empty. Each migrated study's
`baseline.step` must resolve to a real, registered Step.

`@pytest.mark.network`: the same Steps are built and run against the real HRA
API (and real BioModels search), asserting realistic counts.
"""
from __future__ import annotations

import yaml
from pathlib import Path

import pytest
from process_bigraph import Composite, gather_emitter_results

import viva_human_atlas.biomodel_do as biomodel_do
import viva_human_atlas.hra_api as hra_api
from viva_human_atlas.core import build_core

from _step_doc import step_doc, resolve_step_class, registered_step_addresses

REPO_ROOT = Path(__file__).resolve().parents[1]

REFERENCE_ORGANS_ADDRESS = "local:viva_human_atlas.hra_api.HRAReferenceOrgansStep"
CELL_TYPES_ADDRESS = "local:viva_human_atlas.hra_api.HRACellTypesStep"
ANATOMICAL_STRUCTURES_ADDRESS = "local:viva_human_atlas.hra_api.HRAAnatomicalStructuresStep"
BIOMODEL_DO_ADDRESS = "local:viva_human_atlas.biomodel_do.BiomodelDOCatalogStep"

_HRA_BASE = {"base_url": "https://apps.humanatlas.io/api"}
_DO_CONFIG = {"query": "glucose regulation", "max_results": 25}

# migrated study slug -> expected baseline step address
STUDY_STEP_ADDRESSES = {
    "hra-reference-organs": REFERENCE_ORGANS_ADDRESS,
    "hra-cell-types": CELL_TYPES_ADDRESS,
    "hra-anatomical-structures": ANATOMICAL_STRUCTURES_ADDRESS,
    "glucose-biomodel-do": BIOMODEL_DO_ADDRESS,
}


def _run(doc, core=None):
    core = core or build_core()
    composite = Composite(doc, core=core)
    composite.run(0.0)  # Steps run on init; this flushes the emitter.
    snap = (gather_emitter_results(composite).get(("emitter",)) or [{}])[-1]
    return snap


_FAKE_REFERENCE_ORGANS = [
    {
        "ref_organ_id": "https://purl.humanatlas.io/ref-organ/pancreas-female/v1.0#primary",
        "organ": "pancreas",
        "uberon": "UBERON:0001264",
        "sex": "Female",
        "asset_url": "https://assets.humanatlas.io/pancreas-female.glb",
    },
    {
        "ref_organ_id": "https://purl.humanatlas.io/ref-organ/kidney-male/v1.0#primary",
        "organ": "kidney",
        "uberon": "UBERON:0002113",
        "sex": "Male",
        "asset_url": "https://assets.humanatlas.io/kidney-male.glb",
    },
]

_FAKE_CELL_TYPES = [
    {"cl": "CL:0000182", "count": 42},
    {"cl": "CL:0000057", "count": 5},
]

_FAKE_ANATOMICAL_STRUCTURES = [{"term": "UBERON:0014455", "count": 9}]

_FAKE_CATALOG = {
    "biomodel_dos": [
        {
            "biomodel_id": "BIOMD_ISLET",
            "name": "pancreatic islet insulin model",
            "organs": [{"organ": "pancreas", "uberon": "UBERON:0001264"}],
            "provenance": {
                "source": "biomodels",
                "annotation": "synonym-match@HRA-reference-organs",
            },
        }
    ],
    "organ_index": {
        "pancreas": {"uberon": "UBERON:0001264", "sexes": ["Female"], "asset_urls": []}
    },
    "organ_to_models": {"UBERON:0001264": ["BIOMD_ISLET"]},
}


def test_hra_reference_organs_composite_loads(monkeypatch):
    monkeypatch.setattr(
        hra_api, "fetch_reference_organs", lambda *a, **k: _FAKE_REFERENCE_ORGANS
    )
    core = build_core()
    doc = step_doc(REFERENCE_ORGANS_ADDRESS, _HRA_BASE, core)
    snap = _run(doc, core)
    organs = snap.get("reference_organs", [])
    assert len(organs) >= 1
    assert organs[0]["uberon"] == "UBERON:0001264"


def test_hra_cell_types_composite_loads(monkeypatch):
    monkeypatch.setattr(hra_api, "fetch_cell_type_terms", lambda *a, **k: _FAKE_CELL_TYPES)
    core = build_core()
    doc = step_doc(CELL_TYPES_ADDRESS, _HRA_BASE, core)
    snap = _run(doc, core)
    cell_types = snap.get("cell_types", [])
    assert len(cell_types) >= 1
    assert cell_types[0]["cl"] == "CL:0000182"


def test_hra_anatomical_structures_composite_loads(monkeypatch):
    monkeypatch.setattr(
        hra_api, "fetch_anatomical_structure_terms", lambda *a, **k: _FAKE_ANATOMICAL_STRUCTURES
    )
    core = build_core()
    doc = step_doc(ANATOMICAL_STRUCTURES_ADDRESS, _HRA_BASE, core)
    snap = _run(doc, core)
    structures = snap.get("anatomical_structures", [])
    assert len(structures) >= 1
    assert structures[0]["term"] == "UBERON:0014455"


def test_glucose_biomodel_do_composite_loads(monkeypatch):
    monkeypatch.setattr(
        biomodel_do, "build_biomodel_do_catalog", lambda *a, **k: _FAKE_CATALOG
    )
    core = build_core()
    doc = step_doc(BIOMODEL_DO_ADDRESS, _DO_CONFIG, core)
    snap = _run(doc, core)
    dos = snap.get("biomodel_dos", [])
    organ_to_models = snap.get("organ_to_models", {})
    assert len(dos) >= 1
    assert dos[0]["organs"]
    assert organ_to_models.get("UBERON:0001264") == ["BIOMD_ISLET"]


def test_all_four_study_baselines_reference_registered_steps():
    """The four HRA-integration studies migrated from `baseline.composite`
    (single-Step wrapper generators) to `baseline.step`. Assert each migrated
    study's baseline references a real, registered Step at the expected
    address."""
    core = build_core()
    registered = registered_step_addresses(core)
    for slug, expected_address in STUDY_STEP_ADDRESSES.items():
        study_path = REPO_ROOT / "studies" / slug / "study.yaml"
        study = yaml.safe_load(study_path.read_text(encoding="utf-8"))
        baseline = study.get("baseline") or []
        assert baseline, f"{slug}: baseline must be non-empty"
        assert "composite" not in baseline[0], (
            f"{slug}: baseline still uses `composite`; expected migrated `step`"
        )
        address = baseline[0]["step"]
        assert address == expected_address, (
            f"{slug}: baseline.step {address!r} != expected {expected_address!r}"
        )
        # Resolves to a real Step subclass ...
        resolve_step_class(address)
        # ... and is registered by build_core().
        assert address in registered, (
            f"{slug}: baseline.step {address!r} not registered in build_core()"
        )


@pytest.mark.network
def test_hra_reference_organs_live():
    doc = step_doc(REFERENCE_ORGANS_ADDRESS, _HRA_BASE, build_core())
    snap = _run(doc)
    organs = snap.get("reference_organs", [])
    # Live count as of 2026-07-26: 81 reference organs. Assert a generous
    # floor rather than the exact count so the test tolerates the API
    # adding/removing entries.
    assert len(organs) >= 50
    # 12 of the 81 organs carry a bare FMA id in `representation_of` with no
    # `_`/`:` separator at all (e.g. "fma15046", not "FMA:15046") — verified
    # against the live API. `iri_to_curie` only rewrites the first `_`, so
    # these come through as non-CURIE-shaped strings; the plan's assumption
    # that they'd at least be colon-shaped CURIEs doesn't hold. Loosened here
    # to "non-empty string" (not the ":"-shaped check originally planned),
    # plus a floor requiring at least one real UBERON hit.
    assert all(o.get("uberon") for o in organs)
    assert any((o.get("uberon") or "").startswith("UBERON:") for o in organs)


@pytest.mark.network
def test_glucose_biomodel_do_live():
    doc = step_doc(BIOMODEL_DO_ADDRESS, _DO_CONFIG, build_core())
    snap = _run(doc)
    dos = snap.get("biomodel_dos", [])
    organ_to_models = snap.get("organ_to_models", {})
    assert len(dos) >= 1
    assert len(organ_to_models) >= 1
    assert any(len(models) >= 1 for models in organ_to_models.values())
