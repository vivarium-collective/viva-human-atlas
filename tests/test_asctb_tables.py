"""ASCT+B table harvest + gene->Uberon index (offline, mocked `_get`).

A fake sheet-config and fake table JSON drive `list_asctb_organs`,
`fetch_asctb_table`, and `build_gene_uberon_index`; the Step is exercised by
calling `update()` directly against a tmp out_path (harvest monkeypatched so no
network).
"""
from __future__ import annotations

import json

import viva_human_atlas.asctb_tables as at
from viva_human_atlas.core import build_core


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


_SHEET_CONFIG = [
    {"name": "all", "sheetId": "x", "gid": "0"},
    {"name": "pancreas", "sheetId": "a", "gid": "1"},
    {"name": "liver", "sheetId": "b", "gid": "2"},
]

# Two rows: a pancreas row that ties HGNC:3802 to a UBERON structure + a CL
# cell type, and a row whose only gene lacks the HGNC prefix (ignored).
_TABLE = {
    "data": [
        {
            "anatomical_structures": [
                {"id": "UBERON:0001264", "rdfs_label": "pancreas"},
                {"id": "notuberon:1", "rdfs_label": "junk"},
            ],
            "cell_types": [{"id": "CL:0000171", "rdfs_label": "beta cell"}],
            "biomarkers_gene": [
                {"id": "HGNC:3802", "rdfs_label": "GCK", "name": "glucokinase"},
            ],
        },
        {
            "anatomical_structures": [{"id": "UBERON:0000006", "rdfs_label": "islet"}],
            "cell_types": [{"id": "CL:0000169", "rdfs_label": "beta"}],
            "biomarkers_gene": [{"id": "ENSG:x", "rdfs_label": "nope"}],
        },
    ]
}


def test_list_asctb_organs_excludes_all():
    def fake_get(url, timeout=None):
        return _FakeResp(_SHEET_CONFIG)

    organs = at.list_asctb_organs(_get=fake_get)
    assert "all" not in organs
    assert organs == ["pancreas", "liver"]


def test_fetch_asctb_table_returns_rows():
    def fake_get(url, timeout=None):
        # the CDN csv url is quoted into the API url
        assert "asct-b-vh-pancreas.csv" in url
        assert "output=json" in url
        return _FakeResp(_TABLE)

    rows = at.fetch_asctb_table("pancreas", _get=fake_get)
    assert len(rows) == 2
    assert rows[0]["biomarkers_gene"][0]["id"] == "HGNC:3802"


def test_fetch_asctb_table_tolerates_failure():
    def boom(url, timeout=None):
        raise RuntimeError("network down")

    assert at.fetch_asctb_table("pancreas", _get=boom) == []


def test_build_gene_uberon_index_maps_hgnc():
    tables = {"pancreas": _TABLE["data"]}
    index = at.build_gene_uberon_index(tables)
    assert set(index) == {"HGNC:3802"}  # ENSG gene ignored
    entry = index["HGNC:3802"]
    assert entry["label"] == "GCK"
    assert entry["uberon"] == ["UBERON:0001264"]  # non-UBERON id dropped
    assert entry["cl"] == ["CL:0000171"]
    assert entry["organs"] == ["pancreas"]


def test_build_gene_uberon_index_unions_across_rows_and_organs():
    tables = {
        "pancreas": [
            {
                "anatomical_structures": [{"id": "UBERON:1"}],
                "cell_types": [{"id": "CL:1"}],
                "biomarkers_gene": [{"id": "HGNC:1", "rdfs_label": "G1"}],
            }
        ],
        "liver": [
            {
                "anatomical_structures": [{"id": "UBERON:2"}],
                "cell_types": [{"id": "CL:2"}],
                "biomarkers_gene": [{"id": "HGNC:1", "name": "G1"}],
            }
        ],
    }
    index = at.build_gene_uberon_index(tables)
    e = index["HGNC:1"]
    assert e["uberon"] == ["UBERON:1", "UBERON:2"]
    assert e["cl"] == ["CL:1", "CL:2"]
    assert e["organs"] == ["liver", "pancreas"]


def test_write_asctb_json_roundtrips(tmp_path):
    tables = {"pancreas": _TABLE["data"]}
    path = tmp_path / "sub" / "asctb.json"
    at.write_asctb_json(tables, path)
    assert path.exists()
    assert json.loads(path.read_text()) == tables


def test_harvest_uses_cache(tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "pancreas.json").write_text(json.dumps(_TABLE["data"]))

    def boom(*a, **k):  # fetch must NOT be called when cache exists
        raise AssertionError("should have used cache")

    tables = at.harvest_asctb_tables(organs=["pancreas"], _get=boom, cache_dir=str(cache))
    assert tables == {"pancreas": _TABLE["data"]}


def test_step_update_writes_json_and_emits_counts(tmp_path, monkeypatch):
    out_path = tmp_path / "asctb_tables.json"
    analysis = tmp_path / "analysis"

    def fake_harvest(*, cache_dir=None):
        return {"pancreas": _TABLE["data"]}

    monkeypatch.setattr(at, "harvest_asctb_tables", fake_harvest)

    step = at.AsctbTablesStep(
        config={
            "out_path": str(out_path),
            "cache_dir": str(tmp_path / "cache"),
            "analysis_out_dir": str(analysis),
        },
        core=build_core(),
    )
    out = step.update({})
    assert out["out_path"] == str(out_path)
    assert out["n_organs"] == 1
    assert out["n_genes"] == 1  # only HGNC:3802
    assert out["summary"]["organs"] == ["pancreas"]
    assert out_path.exists()
    # analysis copy written best-effort
    assert (analysis / "asctb_tables.json").exists()


def test_step_update_loads_existing_out_path(tmp_path):
    out_path = tmp_path / "asctb_tables.json"
    at.write_asctb_json({"pancreas": _TABLE["data"]}, out_path)

    step = at.AsctbTablesStep(config={"out_path": str(out_path)}, core=build_core())
    # no force + file exists -> loads it, never harvests (no network configured)
    out = step.update({})
    assert out["n_organs"] == 1
    assert out["n_genes"] == 1
