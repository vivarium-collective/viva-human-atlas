import json, importlib.util, pathlib
spec = importlib.util.spec_from_file_location(
    "bhm", pathlib.Path("scripts/build_biomodel_hra_map.py"))
bhm = importlib.util.module_from_spec(spec); spec.loader.exec_module(bhm)

ORGAN_INDEX = {"pancreas": {"uberon": "UBERON:0001264", "asset_urls": []}}


def test_build_entry_shape():
    entry = bhm.build_entry(
        "BIOMD0000000341", ORGAN_INDEX, no_llm=True,
        _sbml=lambda i: "<sbml/>",
        _ids=lambda s: {"chebi": ["CHEBI:17234"], "uniprot": [], "kegg": [], "go": [],
                        "cl": [], "uberon": ["UBERON:0001264"], "fma": [], "bto": [], "n_species": 1},
        _meta=lambda i: {"name": "Topp2000", "pmid": "11073807", "doi": "10.1006/x", "journal": "JTB", "year": 2000, "title": "T"},
        _lit=lambda pmid, doi, **k: {"abstract": None, "fulltext": None, "text_source": "none", "has_fulltext": False},
    )
    assert entry["identifier"] == "https://identifiers.org/biomodels.db:BIOMD0000000341"
    assert entry["repository"] == "biomodels"
    assert entry["paper_doi"] == "10.1006/x"
    assert {"label": "pancreas", "uberon": "UBERON:0001264"} in entry["organs"]
    assert entry["molecular_ids"]["chebi"] == ["CHEBI:17234"]
    assert entry["ontology_ids"]["uberon"] == ["UBERON:0001264"]
    assert "literature" not in entry  # no_llm
    assert entry["provenance"]["pmid"] == "11073807"


def test_db_upsert_and_atomic_write(tmp_path):
    db = {}
    bhm.upsert_db(db, {"identifier": "x", "biomodel_id": "BIOMD1"})
    path = tmp_path / "db.json"
    bhm.write_db(db, str(path))
    loaded = bhm.load_db(str(path))
    assert "BIOMD1" in loaded


def test_sbml_stage_isolated_on_error():
    def boom(i):
        raise RuntimeError("boom-sbml")

    entry = bhm.build_entry(
        "BIOMD0000000341", ORGAN_INDEX, no_llm=True,
        _sbml=boom,
        _meta=lambda i: {"name": "Topp2000", "pmid": "11073807", "doi": "10.1006/x",
                          "journal": "JTB", "year": 2000, "title": "T"},
        _lit=lambda pmid, doi, **k: {"abstract": None, "fulltext": None,
                                      "text_source": "none", "has_fulltext": False},
    )
    assert entry["molecular_ids"]["chebi"] == []
    assert entry["ontology_ids"]["uberon"] == []
    assert entry["provenance"]["n_species"] == 0
    assert any(e.startswith("sbml:") for e in entry["provenance"]["errors"])


def test_hra_stage_isolated_on_error(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("boom-hra")

    monkeypatch.setattr(bhm, "map_to_hra", boom)
    entry = bhm.build_entry(
        "BIOMD0000000341", ORGAN_INDEX, no_llm=True,
        _sbml=lambda i: "<sbml/>",
        _ids=lambda s: {"chebi": [], "uniprot": [], "kegg": [], "go": [],
                        "cl": ["CL:0000169"], "uberon": ["UBERON:0001264"], "fma": [], "bto": [],
                        "n_species": 1},
        _meta=lambda i: {"name": "Topp2000", "pmid": "11073807", "doi": "10.1006/x",
                          "journal": "JTB", "year": 2000, "title": "T"},
        _lit=lambda pmid, doi, **k: {"abstract": None, "fulltext": None,
                                      "text_source": "none", "has_fulltext": False},
    )
    assert entry["organs"] == []
    assert entry["functional_tissue_units"] == []
    assert entry["cell_types"] == []
    assert entry["provenance"]["uberon_organ_ids"] == []
    assert entry["provenance"]["uberon_subregion_ids"] == []
    assert any(e.startswith("hra:") for e in entry["provenance"]["errors"])


def test_literature_failure_recorded_as_lit_and_skips_llm(monkeypatch):
    def boom_lit(pmid, doi, **k):
        raise RuntimeError("boom-lit")

    llm_calls = []

    def spy_llm(name, abstract, fulltext, **k):
        llm_calls.append((name, abstract, fulltext))
        return {}

    entry = bhm.build_entry(
        "BIOMD0000000341", ORGAN_INDEX, no_llm=False,
        _sbml=lambda i: "<sbml/>",
        _ids=lambda s: {"chebi": [], "uniprot": [], "kegg": [], "go": [], "cl": [],
                        "uberon": ["UBERON:0001264"], "fma": [], "bto": [], "n_species": 1},
        _meta=lambda i: {"name": "Topp2000", "pmid": "11073807", "doi": "10.1006/x",
                          "journal": "JTB", "year": 2000, "title": "T"},
        _lit=boom_lit,
        _llm=spy_llm,
    )
    assert "literature" not in entry
    assert llm_calls == []
    assert any(e.startswith("lit:") for e in entry["provenance"]["errors"])
    assert not any(e.startswith("llm:") for e in entry["provenance"]["errors"])


def test_llm_failure_recorded_as_llm_not_lit():
    def boom_llm(name, abstract, fulltext, **k):
        raise RuntimeError("boom-llm")

    entry = bhm.build_entry(
        "BIOMD0000000341", ORGAN_INDEX, no_llm=False,
        _sbml=lambda i: "<sbml/>",
        _ids=lambda s: {"chebi": [], "uniprot": [], "kegg": [], "go": [], "cl": [],
                        "uberon": ["UBERON:0001264"], "fma": [], "bto": [], "n_species": 1},
        _meta=lambda i: {"name": "Topp2000", "pmid": "11073807", "doi": "10.1006/x",
                          "journal": "JTB", "year": 2000, "title": "T"},
        _lit=lambda pmid, doi, **k: {"abstract": "abc", "fulltext": None,
                                      "text_source": "abstract", "has_fulltext": False},
        _llm=boom_llm,
    )
    assert "literature" not in entry
    assert any(e.startswith("llm:") for e in entry["provenance"]["errors"])
    assert not any(e.startswith("lit:") for e in entry["provenance"]["errors"])


def test_should_process_absent_id_is_true():
    assert bhm.should_process({}, "BIOMD1", False) is True


def test_should_process_present_no_errors_not_forced_is_false():
    db = {"BIOMD1": {"provenance": {"errors": []}}}
    assert bhm.should_process(db, "BIOMD1", False) is False


def test_should_process_present_with_errors_is_true():
    db = {"BIOMD1": {"provenance": {"errors": ["lit:boom"]}}}
    assert bhm.should_process(db, "BIOMD1", False) is True


def test_should_process_forced_is_true_regardless():
    db_clean = {"BIOMD1": {"provenance": {"errors": []}}}
    db_errored = {"BIOMD1": {"provenance": {"errors": ["lit:boom"]}}}
    assert bhm.should_process(db_clean, "BIOMD1", True) is True
    assert bhm.should_process(db_errored, "BIOMD1", True) is True
    assert bhm.should_process({}, "BIOMD1", True) is True


def test_main_skips_existing_id_unless_forced(tmp_path, monkeypatch):
    out = tmp_path / "db.json"
    ids_file = tmp_path / "ids.txt"
    ids_file.write_text("BIOMD1\n")

    calls = []

    def fake_build_entry(bid, organ_index, **kw):
        calls.append(bid)
        return {"identifier": f"x:{bid}", "biomodel_id": bid}

    monkeypatch.setattr(bhm, "build_entry", fake_build_entry)
    monkeypatch.setattr(bhm, "build_organ_index", lambda *a, **k: {})
    # pre-seed the db with BIOMD1 already present.
    bhm.write_db({"BIOMD1": {"identifier": "x:BIOMD1", "biomodel_id": "BIOMD1"}}, str(out))

    rc = bhm.main(["--ids-file", str(ids_file), "--out", str(out), "--no-llm"])
    assert rc == 0
    assert calls == []  # skipped: already in db, no --force

    rc = bhm.main(["--ids-file", str(ids_file), "--out", str(out), "--no-llm", "--force"])
    assert rc == 0
    assert calls == ["BIOMD1"]  # reprocessed with --force


def test_main_resumes_errored_entry_without_force(tmp_path, monkeypatch):
    out = tmp_path / "db.json"
    ids_file = tmp_path / "ids.txt"
    ids_file.write_text("BIOMD1\n")

    calls = []

    def fake_build_entry(bid, organ_index, **kw):
        calls.append(bid)
        return {"identifier": f"x:{bid}", "biomodel_id": bid,
                "provenance": {"errors": []}}

    monkeypatch.setattr(bhm, "build_entry", fake_build_entry)
    monkeypatch.setattr(bhm, "build_organ_index", lambda *a, **k: {})
    # pre-seed the db with BIOMD1 present but transiently errored (empty entry).
    bhm.write_db({"BIOMD1": {"identifier": "x:BIOMD1", "biomodel_id": "BIOMD1",
                             "provenance": {"errors": ["lit:boom"]}}}, str(out))

    rc = bhm.main(["--ids-file", str(ids_file), "--out", str(out), "--no-llm"])
    assert rc == 0
    assert calls == ["BIOMD1"]  # retried on resume even without --force


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        pass


def test_default_meta_parses_pubmed_publication():
    payload = {
        "name": "Bulik2016 - Regulation of hepatic glucose metabolism",
        "publication": {"type": "PubMed ID", "accession": "26935066",
                        "journal": "BMC biology",
                        "title": "The relative importance of kinetic mechanisms ..."},
    }
    meta = bhm._default_meta("BIOMD0000000001", _get=lambda url, **k: _Resp(payload))
    assert meta["name"] == "Bulik2016 - Regulation of hepatic glucose metabolism"
    assert meta["pmid"] == "26935066"
    assert meta["doi"] is None
    assert meta["journal"] == "BMC biology"
    assert meta["title"] == "The relative importance of kinetic mechanisms ..."


def test_default_meta_parses_doi_publication():
    payload = {
        "name": "SomeModel",
        "publication": {"type": "DOI", "accession": "10.1006/x", "journal": "JTB"},
    }
    meta = bhm._default_meta("BIOMD0000000002", _get=lambda url, **k: _Resp(payload))
    assert meta["doi"] == "10.1006/x"
    assert meta["pmid"] is None


def test_default_meta_handles_missing_publication():
    payload = {"name": "NoPubModel"}
    meta = bhm._default_meta("BIOMD0000000003", _get=lambda url, **k: _Resp(payload))
    assert meta["name"] == "NoPubModel"
    assert meta["pmid"] is None
    assert meta["doi"] is None


def test_default_meta_falls_back_to_id_when_no_name():
    payload = {}
    meta = bhm._default_meta("BIOMD0000000004", _get=lambda url, **k: _Resp(payload))
    assert meta["name"] == "BIOMD0000000004"
    assert meta["pmid"] is None
    assert meta["doi"] is None
