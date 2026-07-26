from viva_human_atlas.biomodels_search import search_biomodels


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload
    def raise_for_status(self):
        pass
    def json(self):
        return self._payload


def test_search_biomodels_parses_ids_and_respects_max_results():
    payload = {"models": [
        {"id": "BIOMD0000000372", "name": "Topp2000 - beta-cell glucose"},
        {"id": "BIOMD0000000340", "name": "some glucose model"},
        {"id": "BIOMD0000000205", "name": "another"},
    ]}
    calls = {}
    def fake_get(url, params=None, timeout=None):
        calls["url"] = url
        calls["params"] = params
        return _FakeResp(payload)

    ids = search_biomodels("glucose regulation", max_results=2, _get=fake_get)

    assert ids == ["BIOMD0000000372", "BIOMD0000000340"]
    assert "biomodels/search" in calls["url"]
    assert calls["params"]["query"] == "glucose regulation"
    assert calls["params"]["format"] == "json"


def test_search_biomodels_empty_models_key():
    ids = search_biomodels("nope", _get=lambda *a, **k: _FakeResp({}))
    assert ids == []
