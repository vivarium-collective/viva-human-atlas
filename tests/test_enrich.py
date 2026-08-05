"""In-place DB enrichment: organism + gene ids + gene->Uberon anatomy.

Offline: the network resolvers (`organisms_for_taxonomy`, `genes_for_uniprot`)
and `map_to_hra` are monkeypatched, so `enrich_entry` is exercised purely.
"""
from __future__ import annotations

import viva_human_atlas.enrich as en


def _patch(monkeypatch):
    monkeypatch.setattr(en, "organisms_for_taxonomy",
                        lambda taxa, **k: ([{"taxon": "NCBITaxon:9606", "name": "Homo sapiens",
                                             "common": "human"}] if taxa else []))
    monkeypatch.setattr(en, "genes_for_uniprot",
                        lambda accs, **k: {"hgnc": ["HGNC:1"], "ensembl": ["ENSG1"], "symbols": ["INS"]})
    monkeypatch.setattr(en, "map_to_hra",
                        lambda ub, name, oi: {"organs": [{"label": "liver", "uberon": "UBERON:0002107"}],
                                              "functional_tissue_units": [],
                                              "cell_types": [{"label": "hepatocyte", "cl": "CL:0000182"}]})


def _entry():
    return {"biomodel_id": "B1", "name": "x", "taxonomy": ["NCBITaxon:9606"],
            "molecular_ids": {"uniprot": ["P01308"]}, "ontology_ids": {"uberon": []},
            "organs": [], "functional_tissue_units": [], "cell_types": []}


def test_enrich_entry_adds_organism_genes_and_gene_derived_anatomy(monkeypatch):
    _patch(monkeypatch)
    e = _entry()
    gene_index = {"HGNC:1": {"uberon": ["UBERON:0002107"], "cl": ["CL:0000182"]}}
    en.enrich_entry(e, gene_index=gene_index, organ_index={}, cache_dir=None)
    assert e["organism"][0]["name"] == "Homo sapiens"
    assert e["molecular_ids"]["hgnc"] == ["HGNC:1"]
    assert e["molecular_ids"]["ensembl"] == ["ENSG1"]
    # gene -> Uberon unioned into the model's anatomy, then re-mapped to HRA
    assert "UBERON:0002107" in e["ontology_ids"]["uberon"]
    assert {"label": "liver", "uberon": "UBERON:0002107"} in e["organs"]
    assert any(c["cl"] == "CL:0000182" for c in e["cell_types"])


def test_enrich_entry_no_genes_leaves_anatomy_unchanged(monkeypatch):
    _patch(monkeypatch)
    e = _entry()
    # gene_index has no entry for HGNC:1 -> no gene-derived Uberon
    en.enrich_entry(e, gene_index={}, organ_index={}, cache_dir=None)
    assert e["ontology_ids"]["uberon"] == []
    assert e["organs"] == []
    assert e["molecular_ids"]["hgnc"] == ["HGNC:1"]  # gene ids still added


def test_enrich_map_is_tolerant_of_entry_errors(monkeypatch):
    _patch(monkeypatch)
    monkeypatch.setattr(en, "genes_for_uniprot", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    entries = [_entry()]
    out = en.enrich_map(entries, gene_index={}, organ_index={})  # must not raise
    assert out[0]["biomodel_id"] == "B1"
