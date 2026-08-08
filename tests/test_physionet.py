from viva_human_atlas import physionet
from viva_human_atlas.biomodel_do import build_organ_index

ORGAN_INDEX = build_organ_index()

DATACITE_PAGE = {
    "data": [{
        "attributes": {
            "doi": "10.13026/c2f305",
            "titles": [{"title": "MIT-BIH Arrhythmia Database"}],
            "subjects": [{"subject": "ecg"}, {"subject": "arrhythmia"}],
            "descriptions": [{"description": "Two-channel ambulatory ECG recordings."}],
            "publicationYear": 2005,
            "rightsList": [{"rights": "Open Data Commons Attribution License v1.0"}],
            "url": "https://physionet.org/content/mitdb/1.0.0/",
        }
    }],
    "links": {},  # no "next" -> single page
}


def test_resolve_projects_parses_datacite(monkeypatch):
    class R:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return DATACITE_PAGE
    projects = physionet.resolve_projects(_get=lambda *a, **k: R())
    assert len(projects) == 1
    p = projects[0]
    assert p["slug"] == "mitdb"
    assert p["identifier"] == "https://physionet.org/content/mitdb/"
    assert p["keywords"] == ["ecg", "arrhythmia"]
    assert p["doi"] == "10.13026/c2f305"


def test_build_entry_shape_and_organ_mapping():
    proj = {"slug": "mitdb", "identifier": "https://physionet.org/content/mitdb/",
            "name": "MIT-BIH Arrhythmia Database", "keywords": ["ecg", "arrhythmia"],
            "abstract": "", "doi": "10.13026/c2f305", "year": 2005, "access": "open"}
    e = physionet.build_entry(proj, ORGAN_INDEX, no_llm=True)
    assert e["repository"] == "physionet"
    assert e["identifier"] == "https://physionet.org/content/mitdb/"
    assert e["source_id"] == "mitdb"
    assert e["paper_doi"] == "10.13026/c2f305"
    assert e["molecular_ids"] == {"chebi": [], "uniprot": [], "kegg": [], "go": [], "reactome": []}
    assert e["provenance"]["access"] == "open"
    assert e["organs"]  # ecg -> heart


import pytest

@pytest.mark.network
def test_datacite_live_enumerates_and_finds_mitdb():
    projects = physionet.resolve_projects(limit=300)
    assert len(projects) >= 100
    slugs = {p["slug"] for p in projects}
    assert "mitdb" in slugs
