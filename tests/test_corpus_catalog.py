"""Task A: full BioModels corpus retrieval + organ-tagged catalog build.

Offline tests only (network calls are injected via fakes / `_all` / `_get`).
"""
from __future__ import annotations

from viva_human_atlas.biomodels_search import (
    fetch_all_biomodel_ids,
    fetch_biomodels_named,
)
from viva_human_atlas.biomodel_do import (
    build_catalog_from_models,
    build_biomodel_do_catalog,
)


def test_fetch_all_biomodel_ids_filters_to_curated():
    ids = fetch_all_biomodel_ids(
        _all=["BIOMD0000000001", "MODEL123"], curated_only=True
    )
    assert ids == ["BIOMD0000000001"]


def test_fetch_all_biomodel_ids_uncurated_keeps_all():
    ids = fetch_all_biomodel_ids(
        _all=["BIOMD0000000001", "MODEL123"], curated_only=False
    )
    assert ids == ["BIOMD0000000001", "MODEL123"]


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_fetch_biomodels_named_parallel_preserves_order():
    names = {
        "B1": "hepatic glucose metabolism",
        "B2": "cardiac action potential",
    }

    def fake_get(url, params=None, timeout=None):
        query = params["query"]
        return _FakeResp({"models": [{"id": query, "name": names[query]}]})

    models = fetch_biomodels_named(["B1", "B2"], max_workers=4, _get=fake_get)

    assert models == [
        {"id": "B1", "name": "hepatic glucose metabolism"},
        {"id": "B2", "name": "cardiac action potential"},
    ]


def test_fetch_biomodels_named_tolerates_failures():
    def fake_get(url, params=None, timeout=None):
        query = params["query"]
        if query == "BAD":
            raise RuntimeError("boom")
        if query == "NOHIT":
            return _FakeResp({"models": []})
        return _FakeResp({"models": [{"id": query, "name": "ok model"}]})

    models = fetch_biomodels_named(
        ["BAD", "NOHIT", "GOOD"], max_workers=2, _get=fake_get
    )

    assert models == [
        {"id": "BAD", "name": ""},
        {"id": "NOHIT", "name": ""},
        {"id": "GOOD", "name": "ok model"},
    ]


_FAKE_REFERENCE_ORGANS = [
    {
        "ref_organ_id": "https://purl.humanatlas.io/ref-organ/liver-female/v1.0#primary",
        "organ": "liver",
        "uberon": "UBERON:0002107",
        "sex": "Female",
        "asset_url": "https://assets.humanatlas.io/liver-female.glb",
    },
    {
        "ref_organ_id": "https://purl.humanatlas.io/ref-organ/heart-male/v1.0#primary",
        "organ": "heart",
        "uberon": "UBERON:0000948",
        "sex": "Male",
        "asset_url": "https://assets.humanatlas.io/heart-male.glb",
    },
]


def _fake_get_hra(url, params=None, timeout=None):
    class _FakeResp:
        def json(self_inner):
            return [
                {
                    "@id": ro["ref_organ_id"],
                    "representation_of": (
                        "http://purl.obolibrary.org/obo/"
                        + ro["uberon"].replace(":", "_")
                    ),
                    "sex": ro["sex"],
                    "object": {"file": ro["asset_url"]},
                }
                for ro in _FAKE_REFERENCE_ORGANS
            ]

        def raise_for_status(self_inner):
            pass

    return _FakeResp()


def test_build_catalog_from_models_maps_organs():
    models = [
        {"id": "B1", "name": "hepatic glucose metabolism"},
        {"id": "B2", "name": "cardiac action potential"},
    ]

    catalog = build_catalog_from_models(models, _get_hra=_fake_get_hra)

    assert len(catalog["biomodel_dos"]) == 2
    assert "liver" in catalog["organ_index"]
    assert "heart" in catalog["organ_index"]

    liver_uberon = catalog["organ_index"]["liver"]["uberon"]
    heart_uberon = catalog["organ_index"]["heart"]["uberon"]

    assert catalog["organ_to_models"][liver_uberon] == ["B1"]
    assert catalog["organ_to_models"][heart_uberon] == ["B2"]


def test_build_biomodel_do_catalog_still_delegates_through_core():
    search_payload_models = [
        {"id": "BIOMD_HEPATIC", "name": "hepatic glucose model"},
        {"id": "BIOMD_ISLET", "name": "pancreatic islet insulin model"},
    ]

    class _FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"models": search_payload_models}

    def fake_get_search(url, params=None, timeout=None):
        return _FakeResp()

    catalog = build_biomodel_do_catalog(
        "glucose regulation",
        max_results=25,
        _get_search=fake_get_search,
        _get_hra=_fake_get_hra,
    )

    assert len(catalog["biomodel_dos"]) == 2
    assert "liver" in catalog["organ_index"]
    liver_uberon = catalog["organ_index"]["liver"]["uberon"]
    assert catalog["organ_to_models"][liver_uberon] == ["BIOMD_HEPATIC"]
