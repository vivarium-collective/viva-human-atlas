from viva_human_atlas.hra_api import (
    iri_to_curie,
    fetch_reference_organs,
    fetch_cell_type_terms,
    fetch_anatomical_structure_terms,
)


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_iri_to_curie_uberon_and_cl():
    assert iri_to_curie("http://purl.obolibrary.org/obo/UBERON_0014455") == "UBERON:0014455"
    assert iri_to_curie("http://purl.obolibrary.org/obo/CL_0000057") == "CL:0000057"


def test_fetch_reference_organs_parses_slug_uberon_sex_asset():
    payload = [
        {
            "representation_of": "http://purl.obolibrary.org/obo/UBERON_0014455",
            "@id": "https://purl.humanatlas.io/ref-organ/adipose-female/v1.0#primary",
            "sex": "Female",
            "object": {"file": "https://assets.humanatlas.io/adipose-female.glb"},
        },
        {
            "representation_of": "http://purl.obolibrary.org/obo/UBERON_0002113",
            "@id": "https://purl.humanatlas.io/ref-organ/kidney-male/v1.0#primary",
            "sex": "Male",
            "object": {"file": "https://assets.humanatlas.io/kidney-male.glb"},
        },
    ]

    def fake_get(url, params=None, timeout=None):
        return _FakeResp(payload)

    organs = fetch_reference_organs(_get=fake_get)

    assert organs == [
        {
            "ref_organ_id": "https://purl.humanatlas.io/ref-organ/adipose-female/v1.0#primary",
            "organ": "adipose",
            "uberon": "UBERON:0014455",
            "sex": "Female",
            "asset_url": "https://assets.humanatlas.io/adipose-female.glb",
        },
        {
            "ref_organ_id": "https://purl.humanatlas.io/ref-organ/kidney-male/v1.0#primary",
            "organ": "kidney",
            "uberon": "UBERON:0002113",
            "sex": "Male",
            "asset_url": "https://assets.humanatlas.io/kidney-male.glb",
        },
    ]


def test_fetch_cell_type_terms_sorted_desc_by_count():
    payload = {
        "http://purl.obolibrary.org/obo/CL_0000057": 5,
        "http://purl.obolibrary.org/obo/CL_0000182": 42,
    }

    def fake_get(url, params=None, timeout=None):
        return _FakeResp(payload)

    terms = fetch_cell_type_terms(_get=fake_get)

    assert terms == [
        {"cl": "CL:0000182", "count": 42},
        {"cl": "CL:0000057", "count": 5},
    ]


def test_fetch_anatomical_structure_terms_sorted_desc_by_count():
    payload = {
        "http://purl.obolibrary.org/obo/UBERON_0002113": 3,
        "http://purl.obolibrary.org/obo/UBERON_0014455": 9,
    }

    def fake_get(url, params=None, timeout=None):
        return _FakeResp(payload)

    terms = fetch_anatomical_structure_terms(_get=fake_get)

    assert terms == [
        {"term": "UBERON:0014455", "count": 9},
        {"term": "UBERON:0002113", "count": 3},
    ]
