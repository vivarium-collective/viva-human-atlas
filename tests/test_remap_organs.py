import copy

from viva_human_atlas.coverage import load_corpus_catalog
from scripts.remap_organs import remap_row

ORGAN_INDEX = load_corpus_catalog()["organ_index"]

# UBERON:0000006 (islet of Langerhans) is a non-organ id that the committed
# rollup dataset (datasets/uberon_organ_rollup.json) rolls up to "pancreas".
ROLLUP_UBERON = "UBERON:0000006"


def _row(**over) -> dict:
    row = {
        "identifier": "test:1",
        "repository": "biomodels",
        "name": "an unrelated model title",
        "organs": [],
        "functional_tissue_units": [],
        "cell_types": [],
        "ontology_ids": {"uberon": [], "cl": [], "mesh": [], "fma": [], "bto": []},
        "gene_symbols": [],
        "provenance": {"mapping_method": "", "confidence": "none", "errors": []},
    }
    row.update(over)
    return row


def test_places_row_via_committed_rollup_from_existing_nonorgan_uberon():
    row = _row(ontology_ids={"uberon": [ROLLUP_UBERON], "cl": [], "mesh": [], "fma": [], "bto": []})
    out = remap_row(row, ORGAN_INDEX)
    labels = [o["label"] for o in out["organs"]]
    assert labels == ["pancreas"]
    assert out["provenance"]["mapping_method"] == "annotation_rollup"
    assert out["provenance"]["confidence"] == "high"
    assert ORGAN_INDEX["pancreas"]["uberon"] in out["ontology_ids"]["uberon"]


def test_leaves_unmappable_row_empty():
    row = _row()  # no uberon/cl/fma/bto/mesh/gene_symbols, generic name
    out = remap_row(row, ORGAN_INDEX)
    assert out["organs"] == []
    assert out["functional_tissue_units"] == []
    assert out["cell_types"] == []
    assert out["provenance"]["mapping_method"] == ""
    assert out["provenance"]["confidence"] == "none"


def test_deterministic_two_calls_identical():
    row = _row(ontology_ids={"uberon": [ROLLUP_UBERON], "cl": [], "mesh": [], "fma": [], "bto": []})
    out1 = remap_row(copy.deepcopy(row), ORGAN_INDEX)
    out2 = remap_row(copy.deepcopy(row), ORGAN_INDEX)
    assert out1 == out2


def test_mesh_id_strings_do_not_crash_and_no_op():
    # Committed rows store ontology_ids.mesh as plain "MESH:Dxxxxx" id strings
    # (no labels); the mesh crosswalk tier needs label dicts, so this must be a
    # safe no-op rather than an error.
    row = _row(ontology_ids={"uberon": [], "cl": [], "mesh": ["MESH:D008099"], "fma": [], "bto": []})
    out = remap_row(row, ORGAN_INDEX)
    assert out["organs"] == []
    assert out["provenance"]["mapping_method"] == ""
