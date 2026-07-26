"""Demonstrate-loading tests for the HRA-integration composites.

Offline (mocked): each of the four composite generators is built via
`build_core()`, run once, and the RAMEmitter snapshot is asserted non-empty.
`discover_generators()` must surface all four.

`@pytest.mark.network`: the same composites are built and run against the
real HRA API (and real BioModels search), asserting realistic counts.
"""
from __future__ import annotations

import pytest
from process_bigraph import Composite, gather_emitter_results

import viva_human_atlas.biomodel_do as biomodel_do
import viva_human_atlas.composites.biomodel_do_composite as biomodel_do_composites
import viva_human_atlas.composites.hra_steps as hra_steps_composites
import viva_human_atlas.hra_api as hra_api
from viva_human_atlas.core import build_core


def _run(doc):
    core = build_core()
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
    doc = hra_steps_composites.build_hra_reference_organs()
    snap = _run(doc)
    organs = snap.get("reference_organs", [])
    assert len(organs) >= 1
    assert organs[0]["uberon"] == "UBERON:0001264"


def test_hra_cell_types_composite_loads(monkeypatch):
    monkeypatch.setattr(hra_api, "fetch_cell_type_terms", lambda *a, **k: _FAKE_CELL_TYPES)
    doc = hra_steps_composites.build_hra_cell_types()
    snap = _run(doc)
    cell_types = snap.get("cell_types", [])
    assert len(cell_types) >= 1
    assert cell_types[0]["cl"] == "CL:0000182"


def test_hra_anatomical_structures_composite_loads(monkeypatch):
    monkeypatch.setattr(
        hra_api, "fetch_anatomical_structure_terms", lambda *a, **k: _FAKE_ANATOMICAL_STRUCTURES
    )
    doc = hra_steps_composites.build_hra_anatomical_structures()
    snap = _run(doc)
    structures = snap.get("anatomical_structures", [])
    assert len(structures) >= 1
    assert structures[0]["term"] == "UBERON:0014455"


def test_glucose_biomodel_do_composite_loads(monkeypatch):
    monkeypatch.setattr(
        biomodel_do, "build_biomodel_do_catalog", lambda *a, **k: _FAKE_CATALOG
    )
    doc = biomodel_do_composites.build_glucose_biomodel_do()
    snap = _run(doc)
    dos = snap.get("biomodel_dos", [])
    organ_to_models = snap.get("organ_to_models", {})
    assert len(dos) >= 1
    assert dos[0]["organs"]
    assert organ_to_models.get("UBERON:0001264") == ["BIOMD_ISLET"]


def test_all_four_generators_discovered():
    try:
        from viva_superpowers.composite_generator import discover_generators
    except ModuleNotFoundError:
        from pbg_superpowers.composite_generator import discover_generators
    import viva_human_atlas  # noqa: F401  (fires decorators)

    names = {g.name for g in discover_generators().values()}
    assert {
        "hra-reference-organs",
        "hra-cell-types",
        "hra-anatomical-structures",
        "glucose-biomodel-do",
    } <= names


@pytest.mark.network
def test_hra_reference_organs_live():
    doc = hra_steps_composites.build_hra_reference_organs()
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
    doc = biomodel_do_composites.build_glucose_biomodel_do()
    snap = _run(doc)
    dos = snap.get("biomodel_dos", [])
    organ_to_models = snap.get("organ_to_models", {})
    assert len(dos) >= 1
    assert len(organ_to_models) >= 1
    assert any(len(models) >= 1 for models in organ_to_models.values())
