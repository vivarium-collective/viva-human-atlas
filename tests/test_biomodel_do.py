from viva_human_atlas.biomodel_do import (
    ORGAN_SYNONYMS,
    build_organ_index,
    annotate_biomodel,
    build_biomodel_do_catalog,
)


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


_FAKE_REFERENCE_ORGANS = [
    {
        "ref_organ_id": "https://purl.humanatlas.io/ref-organ/pancreas-female/v1.0#primary",
        "organ": "pancreas",
        "uberon": "UBERON:0001264",
        "sex": "Female",
        "asset_url": "https://assets.humanatlas.io/pancreas-female.glb",
    },
    {
        "ref_organ_id": "https://purl.humanatlas.io/ref-organ/pancreas-male/v1.0#primary",
        "organ": "pancreas",
        "uberon": "UBERON:0001264",
        "sex": "Male",
        "asset_url": "https://assets.humanatlas.io/pancreas-male.glb",
    },
    {
        "ref_organ_id": "https://purl.humanatlas.io/ref-organ/liver-female/v1.0#primary",
        "organ": "liver",
        "uberon": "UBERON:0002107",
        "sex": "Female",
        "asset_url": "https://assets.humanatlas.io/liver-female.glb",
    },
]


def test_build_organ_index_from_reference_organs():
    idx = build_organ_index(reference_organs=_FAKE_REFERENCE_ORGANS)

    assert idx["pancreas"]["uberon"] == "UBERON:0001264"
    assert sorted(idx["pancreas"]["sexes"]) == ["Female", "Male"]
    assert len(idx["pancreas"]["asset_urls"]) == 2

    assert idx["liver"]["uberon"] == "UBERON:0002107"
    assert idx["liver"]["sexes"] == ["Female"]
    assert idx["liver"]["asset_urls"] == ["https://assets.humanatlas.io/liver-female.glb"]


def test_annotate_biomodel_hits_pancreas():
    idx = build_organ_index(reference_organs=_FAKE_REFERENCE_ORGANS)

    do = annotate_biomodel(
        "BIOMD0000000372", "Topp2000 beta-cell insulin glucose", idx
    )

    assert do["biomodel_id"] == "BIOMD0000000372"
    assert do["name"] == "Topp2000 beta-cell insulin glucose"
    organs = {o["organ"]: o["uberon"] for o in do["organs"]}
    assert organs["pancreas"] == "UBERON:0001264"
    assert do["provenance"]["source"] == "biomodels"
    assert "synonym-match" in do["provenance"]["annotation"]


def test_build_biomodel_do_catalog_maps_organ_to_models():
    search_payload = {
        "models": [
            {"id": "BIOMD_HEPATIC", "name": "hepatic glucose model"},
            {"id": "BIOMD_ISLET", "name": "pancreatic islet insulin model"},
        ]
    }

    def fake_get_search(url, params=None, timeout=None):
        return _FakeResp(search_payload)

    def fake_get_hra(url, params=None, timeout=None):
        return _FakeResp(
            [
                {
                    "representation_of": "http://purl.obolibrary.org/obo/UBERON_0002107",
                    "@id": "https://purl.humanatlas.io/ref-organ/liver-female/v1.0#primary",
                    "sex": "Female",
                    "object": {"file": "https://assets.humanatlas.io/liver-female.glb"},
                },
                {
                    "representation_of": "http://purl.obolibrary.org/obo/UBERON_0001264",
                    "@id": "https://purl.humanatlas.io/ref-organ/pancreas-male/v1.0#primary",
                    "sex": "Male",
                    "object": {"file": "https://assets.humanatlas.io/pancreas-male.glb"},
                },
            ]
        )

    catalog = build_biomodel_do_catalog(
        "glucose regulation",
        max_results=25,
        _get_search=fake_get_search,
        _get_hra=fake_get_hra,
    )

    assert len(catalog["biomodel_dos"]) == 2
    assert "liver" in catalog["organ_index"]
    assert "pancreas" in catalog["organ_index"]

    liver_uberon = catalog["organ_index"]["liver"]["uberon"]
    pancreas_uberon = catalog["organ_index"]["pancreas"]["uberon"]

    assert catalog["organ_to_models"][liver_uberon] == ["BIOMD_HEPATIC"]
    assert catalog["organ_to_models"][pancreas_uberon] == ["BIOMD_ISLET"]


def test_organ_synonyms_cover_required_organs():
    for organ in ("pancreas", "liver", "kidney", "adipose", "muscle", "intestine", "blood"):
        assert organ in ORGAN_SYNONYMS
        assert len(ORGAN_SYNONYMS[organ]) >= 1
