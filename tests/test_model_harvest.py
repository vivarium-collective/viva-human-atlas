import json
from viva_human_atlas import model_harvest as mh


def _seed_db(tmp_path):
    p = tmp_path / "model_hra_map.json"
    p.write_text(json.dumps([
        {"identifier": "iri://BIOMD1", "repository": "biomodels", "source_id": "BIOMD1",
         "provenance": {"errors": []}},
    ]))
    return p


def test_harvest_physionet_preserves_biomodels_rows(tmp_path, monkeypatch):
    out = _seed_db(tmp_path)
    fake_project = {"slug": "mitdb", "identifier": "https://physionet.org/content/mitdb/",
                    "name": "MIT-BIH", "keywords": ["ecg"], "abstract": "", "doi": "10.13026/x",
                    "year": 2005, "access": "open"}
    monkeypatch.setitem(mh.SOURCES, "physionet", {
        **mh.SOURCES["physionet"],
        "list_fn": lambda **k: [fake_project],
        "entry_fn": lambda proj, oi, **k: {"identifier": proj["identifier"], "repository": "physionet",
                                           "source_id": proj["slug"], "provenance": {"errors": []}},
    })
    res = mh.harvest(sources=["physionet"], out=out, no_llm=True)
    db = json.loads(out.read_text())
    ids = {e["identifier"]: e["repository"] for e in db}
    assert ids["iri://BIOMD1"] == "biomodels"          # untouched
    assert ids["https://physionet.org/content/mitdb/"] == "physionet"  # added
    assert res["per_source"]["physionet"]["new"] == 1


def test_harvest_is_incremental(tmp_path, monkeypatch):
    out = _seed_db(tmp_path)
    proj = {"slug": "mitdb", "identifier": "https://physionet.org/content/mitdb/",
            "name": "MIT-BIH", "keywords": ["ecg"], "abstract": "", "doi": None, "year": 2005, "access": "open"}
    monkeypatch.setitem(mh.SOURCES, "physionet", {
        **mh.SOURCES["physionet"], "list_fn": lambda **k: [proj],
        "entry_fn": lambda p, oi, **k: {"identifier": p["identifier"], "repository": "physionet",
                                        "source_id": p["slug"], "provenance": {"errors": []}}})
    mh.harvest(sources=["physionet"], out=out, no_llm=True)
    res2 = mh.harvest(sources=["physionet"], out=out, no_llm=True)   # nothing new
    assert res2["per_source"]["physionet"]["new"] == 0
    assert res2["per_source"]["physionet"]["skipped"] == 1
