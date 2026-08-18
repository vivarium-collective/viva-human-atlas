import json
# The extraction pipeline lives in the shared core module
# `viva_human_atlas.biomodel_hra` (the CLI `scripts/build_biomodel_hra_map.py`
# and the workbench `BiomodelHraMapStep` both call it), so the pipeline tests
# target the module directly.
import viva_human_atlas.biomodel_hra as bhm
from viva_human_atlas.biomodel_do import build_organ_index

ORGAN_INDEX = {
    "pancreas": {"uberon": "UBERON:0001264", "asset_urls": []},
    "liver": {"uberon": "UBERON:0002107", "asset_urls": []},
}

# Default stub: no PubMed MeSH headings, no network. Individual tests that
# exercise the MeSH stage override this.
_NO_MESH = lambda *a, **k: []  # noqa: E731


def test_build_entry_shape():
    entry = bhm.build_entry(
        "BIOMD0000000341", ORGAN_INDEX, no_llm=True,
        _sbml=lambda i: "<sbml/>",
        _ids=lambda s: {"chebi": ["CHEBI:17234"], "uniprot": [], "kegg": [], "go": [],
                        "cl": [], "uberon": ["UBERON:0001264"], "fma": [], "bto": [], "n_species": 1},
        _meta=lambda i: {"name": "Topp2000", "pmid": "11073807", "doi": "10.1006/x", "journal": "JTB", "year": 2000, "title": "T"},
        _lit=lambda pmid, doi, **k: {"abstract": None, "fulltext": None, "text_source": "none", "has_fulltext": False},
        _biopax=lambda i, **k: None,
        _pubmed_mesh=_NO_MESH,
    )
    assert entry["identifier"] == "https://identifiers.org/biomodels.db:BIOMD0000000341"
    assert entry["repository"] == "biomodels"
    assert entry["paper_doi"] == "10.1006/x"
    # PubMed is the preferred paper link (falls back to DOI, then None)
    assert entry["paper_pmid"] == "11073807"
    assert entry["paper_url"] == "https://pubmed.ncbi.nlm.nih.gov/11073807/"
    assert entry["taxonomy"] == []  # top-level now, promoted from biopax
    assert {"label": "pancreas", "uberon": "UBERON:0001264"} in entry["organs"]
    assert entry["molecular_ids"]["chebi"] == ["CHEBI:17234"]
    assert entry["molecular_ids"]["reactome"] == []
    assert entry["ontology_ids"]["uberon"] == ["UBERON:0001264"]
    assert entry["ontology_ids"]["mesh"] == []
    assert "literature" not in entry  # no_llm
    # provenance is de-bloated: no id_sources / pmid / uberon_*_ids. Task 4:
    # mapping_method/confidence now come from anatomy_resolver.resolve_organ_
    # keys -- an organ-level exact UBERON hit is tier 1 ("annotation"/"high").
    assert entry["provenance"] == {
        "journal": "JTB", "year": 2000, "title": "T", "n_species": 1,
        "mapping_method": "annotation", "confidence": "high",
        "text_source": "none", "has_fulltext": False, "errors": [],
    }
    assert entry["source_id"] == "BIOMD0000000341"
    # key order matches the spec
    assert list(entry.keys()) == [
        "identifier", "repository", "biomodel_id", "source_id", "name", "paper_url",
        "paper_pmid", "paper_doi", "taxonomy", "organs",
        "functional_tissue_units", "cell_types", "molecular_ids",
        "ontology_ids", "provenance",
    ]


def test_build_entry_unions_biopax_with_sbml_and_records_provenance():
    entry = bhm.build_entry(
        "BIOMD0000000341", ORGAN_INDEX, no_llm=True,
        _sbml=lambda i: "<sbml/>",
        _ids=lambda s: {"chebi": ["CHEBI:17234"], "uniprot": [], "kegg": ["C00013"], "go": [],
                        "cl": [], "uberon": ["UBERON:0001264"], "fma": [], "bto": [], "n_species": 1},
        _meta=lambda i: {"name": "Topp2000", "pmid": "11073807", "doi": "10.1006/x", "journal": "JTB", "year": 2000, "title": "T"},
        _lit=lambda pmid, doi, **k: {"abstract": None, "fulltext": None, "text_source": "none", "has_fulltext": False},
        _biopax=lambda i, **k: "<owl/>",
        _biopax_ids=lambda owl: {"chebi": ["CHEBI:17234"], "uniprot": ["P01308"], "kegg": ["C99999"],
                                 "go": ["GO:0005783"], "reactome": ["R-HSA-70171"], "taxonomy": ["NCBITaxon:9606"]},
        _pubmed_mesh=_NO_MESH,
    )
    assert entry["molecular_ids"]["chebi"] == ["CHEBI:17234"]  # union, deduped
    assert entry["molecular_ids"]["kegg"] == ["C00013", "C99999"]  # union of sbml + biopax
    assert entry["molecular_ids"]["uniprot"] == ["P01308"]
    assert entry["molecular_ids"]["go"] == ["GO:0005783"]
    assert entry["molecular_ids"]["reactome"] == ["R-HSA-70171"]
    assert entry["taxonomy"] == ["NCBITaxon:9606"]


def test_biopax_stage_isolated_on_error():
    def boom(i, **k):
        raise RuntimeError("boom-biopax")

    entry = bhm.build_entry(
        "BIOMD0000000341", ORGAN_INDEX, no_llm=True,
        _sbml=lambda i: "<sbml/>",
        _ids=lambda s: {"chebi": ["CHEBI:17234"], "uniprot": [], "kegg": [], "go": [],
                        "cl": [], "uberon": ["UBERON:0001264"], "fma": [], "bto": [], "n_species": 1},
        _meta=lambda i: {"name": "Topp2000", "pmid": "11073807", "doi": "10.1006/x", "journal": "JTB", "year": 2000, "title": "T"},
        _lit=lambda pmid, doi, **k: {"abstract": None, "fulltext": None, "text_source": "none", "has_fulltext": False},
        _biopax=boom,
        _pubmed_mesh=_NO_MESH,
    )
    assert entry["molecular_ids"]["chebi"] == ["CHEBI:17234"]  # SBML ids still present
    assert entry["molecular_ids"]["reactome"] == []
    assert entry["taxonomy"] == []
    assert any(e.startswith("biopax:") for e in entry["provenance"]["errors"])


def test_db_upsert_and_atomic_write(tmp_path):
    db = {}
    bhm.upsert_db(db, {"identifier": "x", "biomodel_id": "BIOMD1"})
    path = tmp_path / "db.json"
    bhm.write_db(db, str(path))
    loaded = bhm.load_db(str(path))
    assert "x" in loaded


def test_write_db_serializes_as_sorted_json_array(tmp_path):
    db = {
        "BIOMD2": {"identifier": "x:2", "biomodel_id": "BIOMD2"},
        "BIOMD1": {"identifier": "x:1", "biomodel_id": "BIOMD1"},
    }
    path = tmp_path / "db.json"
    bhm.write_db(db, str(path))
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(on_disk, list)
    assert [e["biomodel_id"] for e in on_disk] == ["BIOMD1", "BIOMD2"]  # sorted


def test_load_db_array_round_trip(tmp_path):
    db = {
        "x:2": {"identifier": "x:2", "biomodel_id": "BIOMD2", "name": "Two"},
        "x:1": {"identifier": "x:1", "biomodel_id": "BIOMD1", "name": "One"},
    }
    path = tmp_path / "db.json"
    bhm.write_db(db, str(path))
    loaded = bhm.load_db(str(path))
    assert loaded == db


def test_load_db_accepts_legacy_id_keyed_object(tmp_path):
    """A legacy `biomodel_id`-keyed on-disk object is re-keyed on `identifier`
    when loaded (the DB is always identifier-keyed internally)."""
    legacy = {"BIOMD1": {"identifier": "x:1", "biomodel_id": "BIOMD1"}}
    path = tmp_path / "db.json"
    path.write_text(json.dumps(legacy), encoding="utf-8")
    assert bhm.load_db(str(path)) == {"x:1": {"identifier": "x:1", "biomodel_id": "BIOMD1"}}


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
        _biopax=lambda i, **k: None,
        _pubmed_mesh=_NO_MESH,
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
        _biopax=lambda i, **k: None,
        _pubmed_mesh=_NO_MESH,
    )
    assert entry["organs"] == []
    assert entry["functional_tissue_units"] == []
    assert entry["cell_types"] == []
    assert any(e.startswith("hra:") for e in entry["provenance"]["errors"])


def test_crosswalk_stage_isolated_on_error_falls_back_to_raw_uberon(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("boom-crosswalk")

    monkeypatch.setattr(bhm, "crosswalk_anatomy", boom)
    entry = bhm.build_entry(
        "BIOMD0000000341", ORGAN_INDEX, no_llm=True,
        _sbml=lambda i: "<sbml/>",
        _ids=lambda s: {"chebi": [], "uniprot": [], "kegg": [], "go": [],
                        "cl": [], "uberon": ["UBERON:0001264"], "fma": [], "bto": ["BTO:0000759"],
                        "n_species": 1},
        _meta=lambda i: {"name": "Topp2000", "pmid": "11073807", "doi": "10.1006/x",
                          "journal": "JTB", "year": 2000, "title": "T"},
        _lit=lambda pmid, doi, **k: {"abstract": None, "fulltext": None,
                                      "text_source": "none", "has_fulltext": False},
        _biopax=lambda i, **k: None,
        _pubmed_mesh=_NO_MESH,
    )
    # falls back to the raw (un-enriched) uberon; HRA mapping still runs
    assert entry["ontology_ids"]["uberon"] == ["UBERON:0001264"]
    assert {"label": "pancreas", "uberon": "UBERON:0001264"} in entry["organs"]
    assert any(e.startswith("crosswalk:") for e in entry["provenance"]["errors"])
    assert not any(e.startswith("hra:") for e in entry["provenance"]["errors"])


def test_bto_crosswalk_enriches_uberon_and_adds_organ():
    """A model annotated only with a BTO liver term (no direct Uberon liver
    annotation) still resolves a liver organ, via the injected BTO->Uberon
    crosswalk feeding the enriched Uberon into HRA mapping."""
    entry = bhm.build_entry(
        "BIOMD0000000341", ORGAN_INDEX, no_llm=True,
        _sbml=lambda i: "<sbml/>",
        _ids=lambda s: {"chebi": [], "uniprot": [], "kegg": [], "go": [],
                        "cl": [], "uberon": [], "fma": [], "bto": ["BTO:0000759"], "n_species": 1},
        _meta=lambda i: {"name": "SomeLiverModel", "pmid": "11073807", "doi": None,
                          "journal": "JTB", "year": 2000, "title": "T"},
        _lit=lambda pmid, doi, **k: {"abstract": None, "fulltext": None,
                                      "text_source": "none", "has_fulltext": False},
        _biopax=lambda i, **k: None,
        _pubmed_mesh=_NO_MESH,
        _bto_map={"BTO:0000759": "UBERON:0002107"},
    )
    assert entry["ontology_ids"]["uberon"] == ["UBERON:0002107"]
    assert {"label": "liver", "uberon": "UBERON:0002107"} in entry["organs"]
    assert entry["provenance"]["errors"] == []


def test_build_entry_annotation_rollup_via_resolver_places_nonorgan_uberon():
    """Task 4: build_entry now feeds ont_uberon through anatomy_resolver.
    resolve_organ_keys, so a model annotated only with a non-organ UBERON
    (no organ-level id, no BTO/MeSH) still resolves an organ via the
    committed hierarchy roll-up -- e.g. UBERON:0000956 (cerebral cortex) ->
    brain -- and provenance.mapping_method records the resolver's tier."""
    real_organ_index = build_organ_index()
    entry = bhm.build_entry(
        "BIOMD0000000341", real_organ_index, no_llm=True,
        _sbml=lambda i: "<sbml/>",
        _ids=lambda s: {"chebi": [], "uniprot": [], "kegg": [], "go": [],
                        "cl": [], "uberon": ["UBERON:0000956"], "fma": [], "bto": [], "n_species": 1},
        _meta=lambda i: {"name": "SomeBrainModel", "pmid": "11073807", "doi": None,
                          "journal": "JTB", "year": 2000, "title": "T"},
        _lit=lambda pmid, doi, **k: {"abstract": None, "fulltext": None,
                                      "text_source": "none", "has_fulltext": False},
        _biopax=lambda i, **k: None,
        _pubmed_mesh=_NO_MESH,
    )
    assert entry["organs"], "expected a non-empty organs list"
    assert {"label": "brain", "uberon": real_organ_index["brain"]["uberon"]} in entry["organs"]
    assert entry["provenance"]["mapping_method"] == "annotation_rollup"
    assert entry["provenance"]["confidence"] == "high"
    assert entry["provenance"]["errors"] == []


def test_pubmed_mesh_stage_populates_ontology_ids_and_enriches_uberon():
    """MeSH headings fetched from PubMed (via the injected `_pubmed_mesh`)
    are recorded in ontology_ids.mesh and, via the label crosswalk, enrich
    Uberon/CL and resolve an organ -- even with no LIVER annotation in the
    SBML/BioPAX at all."""
    entry = bhm.build_entry(
        "BIOMD0000000341", ORGAN_INDEX, no_llm=True,
        _sbml=lambda i: "<sbml/>",
        _ids=lambda s: {"chebi": [], "uniprot": [], "kegg": [], "go": [],
                        "cl": [], "uberon": [], "fma": [], "bto": [], "n_species": 1},
        _meta=lambda i: {"name": "SomeLiverModel", "pmid": "11073807", "doi": None,
                          "journal": "JTB", "year": 2000, "title": "T"},
        _lit=lambda pmid, doi, **k: {"abstract": None, "fulltext": None,
                                      "text_source": "none", "has_fulltext": False},
        _biopax=lambda i, **k: None,
        _pubmed_mesh=lambda pmid, **k: [{"id": "D008099", "label": "Liver"}],
        _mesh_label_map={"liver": {"uberon": ["UBERON:0002107"],
                                   "cl": ["CL:0000182", "CL:9999999"]}},
    )
    assert entry["ontology_ids"]["mesh"] == ["MESH:D008099"]
    assert entry["ontology_ids"]["uberon"] == ["UBERON:0002107"]
    assert entry["ontology_ids"]["cl"] == ["CL:0000182", "CL:9999999"]
    assert {"label": "liver", "uberon": "UBERON:0002107"} in entry["organs"]
    # CL:0000182 (hepatocyte) is already surfaced by the liver FTU itself
    # (with a real label), so the ont_cl merge dedupes rather than
    # appending a second label:None entry for the same CL.
    assert {"cl": "CL:0000182", "label": "hepatocyte"} in entry["cell_types"]
    assert sum(1 for c in entry["cell_types"] if c["cl"] == "CL:0000182") == 1
    # CL:9999999 isn't part of any liver FTU, so it's merged in directly.
    assert {"cl": "CL:9999999", "label": None} in entry["cell_types"]


def test_pubmed_mesh_stage_skipped_without_pmid():
    calls = []

    def spy(pmid, **k):
        calls.append(pmid)
        return [{"id": "D008099", "label": "Liver"}]

    entry = bhm.build_entry(
        "BIOMD0000000341", ORGAN_INDEX, no_llm=True,
        _sbml=lambda i: "<sbml/>",
        _ids=lambda s: {"chebi": [], "uniprot": [], "kegg": [], "go": [],
                        "cl": [], "uberon": [], "fma": [], "bto": [], "n_species": 1},
        _meta=lambda i: {"name": "NoP mid", "pmid": None, "doi": None,
                          "journal": "JTB", "year": 2000, "title": "T"},
        _lit=lambda pmid, doi, **k: {"abstract": None, "fulltext": None,
                                      "text_source": "none", "has_fulltext": False},
        _biopax=lambda i, **k: None,
        _pubmed_mesh=spy,
    )
    assert calls == []  # never called: no pmid
    assert entry["ontology_ids"]["mesh"] == []


def test_pubmed_mesh_stage_isolated_on_error():
    def boom(pmid, **k):
        raise RuntimeError("boom-mesh")

    entry = bhm.build_entry(
        "BIOMD0000000341", ORGAN_INDEX, no_llm=True,
        _sbml=lambda i: "<sbml/>",
        _ids=lambda s: {"chebi": [], "uniprot": [], "kegg": [], "go": [],
                        "cl": [], "uberon": ["UBERON:0001264"], "fma": [], "bto": [], "n_species": 1},
        _meta=lambda i: {"name": "Topp2000", "pmid": "11073807", "doi": None,
                          "journal": "JTB", "year": 2000, "title": "T"},
        _lit=lambda pmid, doi, **k: {"abstract": None, "fulltext": None,
                                      "text_source": "none", "has_fulltext": False},
        _biopax=lambda i, **k: None,
        _pubmed_mesh=boom,
    )
    assert entry["ontology_ids"]["mesh"] == []
    # the rest of the pipeline still runs: pancreas organ still resolves
    assert {"label": "pancreas", "uberon": "UBERON:0001264"} in entry["organs"]
    assert any(e.startswith("mesh:") for e in entry["provenance"]["errors"])


def test_pubmed_mesh_stage_runs_even_with_no_llm_true():
    """The MeSH stage is an anatomy stage, not the LLM extraction stage: it
    must run regardless of --no-llm."""
    calls = []

    def spy(pmid, **k):
        calls.append(pmid)
        return []

    bhm.build_entry(
        "BIOMD0000000341", ORGAN_INDEX, no_llm=True,
        _sbml=lambda i: "<sbml/>",
        _ids=lambda s: {"chebi": [], "uniprot": [], "kegg": [], "go": [],
                        "cl": [], "uberon": [], "fma": [], "bto": [], "n_species": 1},
        _meta=lambda i: {"name": "Topp2000", "pmid": "11073807", "doi": None,
                          "journal": "JTB", "year": 2000, "title": "T"},
        _lit=lambda pmid, doi, **k: {"abstract": None, "fulltext": None,
                                      "text_source": "none", "has_fulltext": False},
        _biopax=lambda i, **k: None,
        _pubmed_mesh=spy,
    )
    assert calls == ["11073807"]


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
        _biopax=lambda i, **k: None,
        _pubmed_mesh=_NO_MESH,
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
        _biopax=lambda i, **k: None,
        _pubmed_mesh=_NO_MESH,
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


def test_build_map_skips_existing_id_unless_forced(tmp_path, monkeypatch):
    out = tmp_path / "db.json"

    calls = []

    def fake_build_entry(bid, organ_index, **kw):
        calls.append(bid)
        return {"identifier": bhm._IRI.format(bid), "biomodel_id": bid}

    monkeypatch.setattr(bhm, "build_entry", fake_build_entry)
    monkeypatch.setattr(bhm, "build_organ_index", lambda *a, **k: {})
    # pre-seed the db with BIOMD1 already present (keyed by its identifier,
    # as build_map's should_process check computes it via _IRI.format).
    identifier = bhm._IRI.format("BIOMD1")
    bhm.write_db({identifier: {"identifier": identifier, "biomodel_id": "BIOMD1"}}, str(out))

    bhm.build_map(ids=["BIOMD1"], out=str(out), cache_dir=str(tmp_path / "cache"), no_llm=True)
    assert calls == []  # skipped: already in db, no force

    bhm.build_map(ids=["BIOMD1"], out=str(out), cache_dir=str(tmp_path / "cache"),
                  no_llm=True, force=True)
    assert calls == ["BIOMD1"]  # reprocessed with force


def test_build_map_resumes_errored_entry_without_force(tmp_path, monkeypatch):
    out = tmp_path / "db.json"

    calls = []

    def fake_build_entry(bid, organ_index, **kw):
        calls.append(bid)
        return {"identifier": bhm._IRI.format(bid), "biomodel_id": bid,
                "provenance": {"errors": []}}

    monkeypatch.setattr(bhm, "build_entry", fake_build_entry)
    monkeypatch.setattr(bhm, "build_organ_index", lambda *a, **k: {})
    # pre-seed the db with BIOMD1 present but transiently errored (empty entry).
    identifier = bhm._IRI.format("BIOMD1")
    bhm.write_db({identifier: {"identifier": identifier, "biomodel_id": "BIOMD1",
                               "provenance": {"errors": ["lit:boom"]}}}, str(out))

    bhm.build_map(ids=["BIOMD1"], out=str(out), cache_dir=str(tmp_path / "cache"), no_llm=True)
    assert calls == ["BIOMD1"]  # retried on resume even without force


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
