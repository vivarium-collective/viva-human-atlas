"""NCBITaxon -> organism-name resolution (offline).

Static-map hits need no network; the ENA fallback is driven by a mocked
`_get`; unknown ids resolve to None.
"""
from __future__ import annotations

import viva_human_atlas.organism as org


class _FakeResp:
    def __init__(self, payload, ok=True):
        self._payload = payload
        self._ok = ok

    def raise_for_status(self):
        if not self._ok:
            raise RuntimeError("404")

    def json(self):
        return self._payload


def _boom(*a, **k):
    raise AssertionError("network should not be hit for a static id")


def test_static_hit_human_no_network():
    rec = org.organism_name("NCBITaxon:9606", _get=_boom)
    assert rec == {"taxon": "NCBITaxon:9606", "name": "Homo sapiens", "common": "human"}


def test_static_hit_accepts_bare_id():
    rec = org.organism_name("10090", _get=_boom)
    assert rec["name"] == "Mus musculus"
    assert rec["taxon"] == "NCBITaxon:10090"


def test_ena_fallback_via_mock():
    def fake_get(url, timeout=None):
        assert url.endswith("/7777")
        return _FakeResp({"scientificName": "Danio rerio", "commonName": "zebrafish"})

    # 7777 is not in the static map -> hits the ENA fallback
    rec = org.organism_name("NCBITaxon:7777", _get=fake_get)
    assert rec == {"taxon": "NCBITaxon:7777", "name": "Danio rerio", "common": "zebrafish"}


def test_ena_fallback_no_common_name():
    def fake_get(url, timeout=None):
        return _FakeResp({"scientificName": "Some species"})

    rec = org.organism_name("424242", _get=fake_get)
    assert rec["name"] == "Some species"
    assert rec["common"] is None


def test_unknown_returns_none_on_failure():
    def fake_get(url, timeout=None):
        return _FakeResp(None, ok=False)

    assert org.organism_name("NCBITaxon:999999", _get=fake_get) is None


def test_empty_taxon_returns_none():
    assert org.organism_name("", _get=_boom) is None


def test_cache_avoids_second_network_call(tmp_path):
    calls = {"n": 0}

    def fake_get(url, timeout=None):
        calls["n"] += 1
        return _FakeResp({"scientificName": "Cached org", "commonName": "c"})

    a = org.organism_name("55555", _get=fake_get, cache_dir=str(tmp_path))
    b = org.organism_name("55555", _get=_boom, cache_dir=str(tmp_path))
    assert a == b
    assert calls["n"] == 1


def test_organisms_for_taxonomy_dedupes_and_drops_none():
    def fake_get(url, timeout=None):
        return _FakeResp(None, ok=False)  # 7777-style unknowns fail

    recs = org.organisms_for_taxonomy(
        ["NCBITaxon:9606", "9606", "10090", "NCBITaxon:999999"], _get=fake_get
    )
    names = [r["name"] for r in recs]
    assert names == ["Homo sapiens", "Mus musculus"]  # deduped, None dropped
