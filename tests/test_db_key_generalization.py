import json
from viva_human_atlas import biomodel_hra as bh


def _entry(identifier, source_id, errored=False):
    return {"identifier": identifier, "repository": "biomodels", "source_id": source_id,
            "biomodel_id": source_id, "name": source_id,
            "provenance": {"errors": (["x"] if errored else [])}}


def test_upsert_and_write_are_identifier_keyed(tmp_path):
    db = {}
    e = _entry("https://identifiers.org/biomodels.db:BIOMD0000000001", "BIOMD0000000001")
    bh.upsert_db(db, e)
    assert set(db) == {"https://identifiers.org/biomodels.db:BIOMD0000000001"}
    out = tmp_path / "model_hra_map.json"
    bh.write_db(db, out)
    data = json.loads(out.read_text())
    assert data[0]["identifier"] == "https://identifiers.org/biomodels.db:BIOMD0000000001"


def test_load_db_rekeys_legacy_list(tmp_path):
    p = tmp_path / "legacy.json"
    p.write_text(json.dumps([_entry("iri://A", "BIOMD_A"), _entry("iri://B", "BIOMD_B")]))
    db = bh.load_db(p)
    assert set(db) == {"iri://A", "iri://B"}


def test_should_process_by_identifier(tmp_path):
    db = {"iri://A": _entry("iri://A", "BIOMD_A"),
          "iri://B": _entry("iri://B", "BIOMD_B", errored=True)}
    assert bh.should_process(db, "iri://A", force=False) is False   # present, clean -> skip
    assert bh.should_process(db, "iri://B", force=False) is True    # present, errored -> redo
    assert bh.should_process(db, "iri://C", force=False) is True    # absent -> do
    assert bh.should_process(db, "iri://A", force=True) is True     # force -> do
