import json
from viva_human_atlas import model_harvest
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


def test_rebuild_drops_only_named_source(tmp_path, monkeypatch):
    db_path = tmp_path / "db.json"
    from viva_human_atlas import biomodel_hra as bh
    seed = {
        "https://models.physiomeproject.org/e/OLD": {
            "identifier": "https://models.physiomeproject.org/e/OLD",
            "repository": "physiome", "source_id": "OLD", "provenance": {}},
        "https://identifiers.org/biomodels.db:BIOMD1": {
            "identifier": "https://identifiers.org/biomodels.db:BIOMD1",
            "repository": "biomodels", "source_id": "BIOMD1", "provenance": {}},
    }
    bh.write_db(seed, db_path)

    def fake_resolve(**k):
        return [{"slug": "NEW", "identifier": "https://models.physiomeproject.org/exposure/NEW",
                 "name": "n", "abstract": None, "keywords": [], "categories": [],
                 "citation_ids": [], "authors": []}]
    monkeypatch.setattr(model_harvest.physiome, "resolve_exposures", fake_resolve)
    monkeypatch.setattr(model_harvest.physiome, "load_citations", lambda **k: {})
    monkeypatch.setattr(model_harvest.physiome, "build_entry",
                        lambda exp, oi, **k: {"identifier": exp["identifier"], "repository": "physiome",
                                              "source_id": exp["slug"], "provenance": {}})

    res = model_harvest.harvest(["physiome"], out=db_path, rebuild=["physiome"])
    db = bh.load_db(db_path)
    ids = set(db)
    assert "https://models.physiomeproject.org/e/OLD" not in ids   # old physiome row dropped
    assert "https://models.physiomeproject.org/exposure/NEW" in ids  # rebuilt
    assert "https://identifiers.org/biomodels.db:BIOMD1" in ids      # other source preserved
