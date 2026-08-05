"""UniProt -> gene-id crosswalk (offline, mocked `_get`).

A fake UniProtKB JSON for P01308 (insulin) exercises HGNC / Ensembl / symbol
parsing, version stripping, and dedupe; empty/malformed payloads resolve to
empty results.
"""
from __future__ import annotations

import viva_human_atlas.gene_ids as gi


class _FakeResp:
    def __init__(self, payload, ok=True):
        self._payload = payload
        self._ok = ok

    def raise_for_status(self):
        if not self._ok:
            raise RuntimeError("500")

    def json(self):
        return self._payload


_P01308 = {
    "genes": [{"geneName": {"value": "INS"}}],
    "uniProtKBCrossReferences": [
        {"database": "HGNC", "id": "HGNC:6081", "properties": [{"key": "GeneName", "value": "INS"}]},
        {"database": "Ensembl", "id": "ENST00000381330",
         "properties": [{"key": "GeneId", "value": "ENSG00000254647.7"}]},
        {"database": "Ensembl", "id": "ENST00000397262",
         "properties": [{"key": "GeneId", "value": "ENSG00000254647.7"}]},  # dupe ENSG
        {"database": "PDB", "id": "1ZNI", "properties": []},  # unrelated xref
    ],
}


def test_uniprot_gene_ids_parses_p01308():
    def fake_get(url, timeout=None):
        assert "P01308.json" in url
        return _FakeResp(_P01308)

    rec = gi.uniprot_gene_ids("P01308", _get=fake_get)
    assert rec["hgnc"] == ["HGNC:6081"]
    assert rec["ensembl"] == ["ENSG00000254647"]  # version stripped + deduped
    assert rec["symbol"] == "INS"


def test_symbol_falls_back_to_hgnc_property():
    payload = {
        "uniProtKBCrossReferences": [
            {"database": "HGNC", "id": "HGNC:6081", "properties": [{"key": "GeneName", "value": "INS"}]},
        ],
    }

    def fake_get(url, timeout=None):
        return _FakeResp(payload)

    rec = gi.uniprot_gene_ids("P01308", _get=fake_get)
    assert rec["symbol"] == "INS"
    assert rec["hgnc"] == ["HGNC:6081"]


def test_empty_acc_returns_empty():
    rec = gi.uniprot_gene_ids("", _get=lambda *a, **k: None)
    assert rec == {"hgnc": [], "ensembl": [], "symbol": None}


def test_malformed_payload_tolerant():
    def fake_get(url, timeout=None):
        return _FakeResp({})  # no genes, no xrefs

    rec = gi.uniprot_gene_ids("Q99999", _get=fake_get)
    assert rec == {"hgnc": [], "ensembl": [], "symbol": None}


def test_network_failure_tolerant():
    def boom(url, timeout=None):
        raise RuntimeError("down")

    rec = gi.uniprot_gene_ids("P01308", _get=boom)
    assert rec == {"hgnc": [], "ensembl": [], "symbol": None}


def test_cache_avoids_second_call(tmp_path):
    calls = {"n": 0}

    def fake_get(url, timeout=None):
        calls["n"] += 1
        return _FakeResp(_P01308)

    a = gi.uniprot_gene_ids("P01308", _get=fake_get, cache_dir=str(tmp_path))
    b = gi.uniprot_gene_ids("P01308", _get=lambda *x, **k: (_ for _ in ()).throw(AssertionError("cached")),
                            cache_dir=str(tmp_path))
    assert a == b
    assert calls["n"] == 1


def test_genes_for_uniprot_unions():
    payloads = {
        "P01308": _P01308,
        "P02769": {
            "genes": [{"geneName": {"value": "ALB"}}],
            "uniProtKBCrossReferences": [
                {"database": "Ensembl", "id": "ENST1",
                 "properties": [{"key": "GeneId", "value": "ENSG00000000001.2"}]},
            ],
        },
    }

    def fake_get(url, timeout=None):
        acc = url.rsplit("/", 1)[-1].replace(".json", "")
        return _FakeResp(payloads[acc])

    out = gi.genes_for_uniprot(["P01308", "P02769"], _get=fake_get)
    assert out["hgnc"] == ["HGNC:6081"]
    assert out["ensembl"] == ["ENSG00000000001", "ENSG00000254647"]
    assert out["symbols"] == ["ALB", "INS"]
