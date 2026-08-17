import json
import pytest
from viva_human_atlas import physiome


class _R:
    def __init__(self, payload): self._p = payload
    def raise_for_status(self): pass
    def json(self): return self._p

# Two files under one exposure id -> one aggregated record (keywords/citations unioned).
_EXP_583 = {
    "kind": {"id": 1, "description": "exposure_id"}, "term": "583",
    "resource_paths": [
        {"resource_path": "/exposure/583/cloutier_2009_a.cellml", "data": {
            "_title": ["Energy metabolism (Version A)"],
            "_brief": ["Model Status ... version A ..."],
            "cellml_keyword": ["metabolism", "brain"],
            "citation_id": ["urn:miriam:pubmed:19828503"],
            "citation_author_family_name": ["Cloutier"],
            "aliased_uri": ["/exposure/e5cfb42225d4534a1e08979e57cf8bdd/cloutier_2009_a.cellml"],
            "exposure_alias": ["e5cfb42225d4534a1e08979e57cf8bdd"],
            "created_ts": ["1274964447"]}},
        {"resource_path": "/exposure/583/cloutier_2009_b.cellml", "data": {
            "_title": ["Energy metabolism (Version B)"],
            "cellml_keyword": ["brain", "metabolic regulation"],
            "citation_id": ["urn:miriam:pubmed:19828503"],
            "citation_author_family_name": ["Wellstead"],
            "exposure_alias": ["e5cfb42225d4534a1e08979e57cf8bdd"],
            "created_ts": ["1274964447"]}},
    ]}


def test_list_exposure_ids():
    got = physiome.list_exposure_ids(_get=lambda url, timeout=0: _R({"terms": ["1", "583", "1000"]}))
    assert got == ["1", "583", "1000"]


def test_fetch_exposure_aggregates_files(tmp_path):
    exp = physiome.fetch_exposure("583", cache_dir=tmp_path, _get=lambda url, timeout=0: _R(_EXP_583))
    assert exp["slug"] == "e5cfb42225d4534a1e08979e57cf8bdd"
    assert exp["identifier"] == "https://models.physiomeproject.org/exposure/e5cfb42225d4534a1e08979e57cf8bdd"
    assert exp["name"] == "Energy metabolism (Version A)"
    assert set(exp["keywords"]) == {"metabolism", "brain", "metabolic regulation"}
    assert exp["citation_ids"] == ["urn:miriam:pubmed:19828503"]
    assert set(exp["authors"]) == {"Cloutier", "Wellstead"}
    assert exp["filename"] == "cloutier_2009_a.cellml"
    assert (tmp_path / "583.json").exists()  # cached


def test_fetch_exposure_uses_cache(tmp_path):
    (tmp_path / "77.json").write_text(json.dumps(_EXP_583), encoding="utf-8")
    calls = {"n": 0}
    def boom(url, timeout=0):
        calls["n"] += 1; raise AssertionError("should not fetch")
    exp = physiome.fetch_exposure("77", cache_dir=tmp_path, _get=boom)
    assert exp["slug"] == "e5cfb42225d4534a1e08979e57cf8bdd" and calls["n"] == 0


def test_resolve_exposures_query_and_limit(tmp_path):
    payloads = {"1": _EXP_583, "2": _EXP_583}
    def get(url, timeout=0): return _R(payloads[url.rsplit("/", 1)[-1]])
    exps = physiome.resolve_exposures(cache_dir=tmp_path, _ids=["1", "2"], _get=get)
    assert len(exps) == 2
    assert physiome.resolve_exposures(cache_dir=tmp_path, _ids=["1", "2"], limit=1, _get=get).__len__() == 1
    assert physiome.resolve_exposures(cache_dir=tmp_path, _ids=["1"], query="nomatch", _get=get) == []


def test_resolve_exposures_skips_a_failed_fetch_without_aborting(tmp_path):
    payloads = {"1": _EXP_583, "3": _EXP_583}

    def get(url, timeout=0):
        eid = url.rsplit("/", 1)[-1]
        if eid == "2":
            raise AssertionError("simulated network failure for id 2")
        return _R(payloads[eid])

    exps = physiome.resolve_exposures(cache_dir=tmp_path, _ids=["1", "2", "3"], _get=get)
    assert len(exps) == 2
    assert all(e["slug"] == "e5cfb42225d4534a1e08979e57cf8bdd" for e in exps)


def test_resolve_exposures_skipped_fetch_reported_via_progress(tmp_path):
    payloads = {"1": _EXP_583, "3": _EXP_583}

    def get(url, timeout=0):
        eid = url.rsplit("/", 1)[-1]
        if eid == "2":
            raise AssertionError("simulated network failure for id 2")
        return _R(payloads[eid])

    messages = []
    exps = physiome.resolve_exposures(cache_dir=tmp_path, _ids=["1", "2", "3"], _get=get,
                                      progress=messages.append)
    assert len(exps) == 2
    assert len(messages) == 1
    assert "skipped 2" in messages[0]
    assert "simulated network failure for id 2" in messages[0]


from viva_human_atlas.biomodel_do import build_organ_index
ORGAN_INDEX = build_organ_index()

_CITATIONS = {
    "urn:miriam:pubmed:19828503": {
        "id": "urn:miriam:pubmed:19828503", "title": "Energy metabolism control",
        "journal": "PLoS ONE", "issued": "2009-10-01",
        "authors": [{"family": "Cloutier", "given": "M", "other": ""}]},
}


def test_load_and_resolve_citation(tmp_path):
    cites = physiome.load_citations(cache_dir=tmp_path, _get=lambda url, timeout=0: _R(_CITATIONS))
    pmid, meta = physiome.resolve_citation(["urn:miriam:pubmed:19828503"], cites)
    assert pmid == "19828503"
    assert meta["title"] == "Energy metabolism control" and meta["year"] == "2009"
    assert meta["authors"] == ["Cloutier"]
    # empty / unknown -> (None, {})
    assert physiome.resolve_citation(["urn:miriam:pubmed:"], cites) == (None, {})
    assert physiome.resolve_citation([], cites) == (None, {})


def test_load_citations_does_not_cache_on_failure(tmp_path):
    def boom(url, timeout=0):
        raise AssertionError("simulated network failure")
    cites = physiome.load_citations(cache_dir=tmp_path, _get=boom)
    assert cites == {}
    assert not (tmp_path / "citations.json").exists()


def test_load_citations_caches_on_success_and_reuses_cache(tmp_path):
    calls = {"n": 0}
    def get(url, timeout=0):
        calls["n"] += 1
        return _R(_CITATIONS)
    cites = physiome.load_citations(cache_dir=tmp_path, _get=get)
    assert cites == _CITATIONS
    assert (tmp_path / "citations.json").exists()
    assert calls["n"] == 1
    # second call must hit the cache, not _get
    def unreachable(url, timeout=0):
        raise AssertionError("should not fetch — cache hit expected")
    cites2 = physiome.load_citations(cache_dir=tmp_path, _get=unreachable)
    assert cites2 == _CITATIONS


def test_build_entry_pmr3_shape_with_citation():
    exp = {"slug": "abc", "identifier": "https://models.physiomeproject.org/exposure/abc",
           "name": "hepatic bile acid model", "abstract": "A liver model.",
           "keywords": ["hepatocyte", "bile acid"], "categories": [],
           "citation_ids": ["urn:miriam:pubmed:19828503"], "authors": ["Cloutier"]}
    e = physiome.build_entry(exp, ORGAN_INDEX, citations=_CITATIONS, no_llm=True)
    assert e["repository"] == "physiome" and e["source_id"] == "abc"
    assert e["paper_pmid"] == "19828503"
    assert e["paper_url"] == "https://pubmed.ncbi.nlm.nih.gov/19828503/"
    assert e["provenance"]["citation"]["journal"] == "PLoS ONE"
    assert e["provenance"]["abstract"] == "A liver model."
    assert e["provenance"]["keywords"] == ["hepatocyte", "bile acid"]
    assert e["provenance"]["model_format"] == "CellML"


def test_build_entry_no_citation_falls_back_to_identifier():
    exp = {"slug": "abc", "identifier": "https://models.physiomeproject.org/exposure/abc",
           "name": "x", "abstract": None, "keywords": [], "categories": [],
           "citation_ids": [], "authors": []}
    e = physiome.build_entry(exp, ORGAN_INDEX, citations={}, no_llm=True)
    assert e["paper_pmid"] is None
    assert e["paper_url"] == "https://models.physiomeproject.org/exposure/abc"
