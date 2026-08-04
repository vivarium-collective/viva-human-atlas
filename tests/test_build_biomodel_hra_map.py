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
