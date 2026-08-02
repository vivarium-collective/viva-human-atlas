from pathlib import Path
from viva_human_atlas.atlas_pack import (
    build_atlas_manifest,
    biomodels_url,
    organ_system,
    SYSTEM_ORDER,
)
from viva_human_atlas.coverage import load_corpus_catalog

CATALOG = Path(__file__).resolve().parents[1] / "datasets" / "biomodel_corpus_catalog.json"


def _manifest():
    return build_atlas_manifest(load_corpus_catalog(str(CATALOG)))


def test_biomodels_url():
    assert biomodels_url("BIOMD0000000137") == "https://www.ebi.ac.uk/biomodels/BIOMD0000000137"


def test_manifest_has_all_glb_organs():
    m = _manifest()
    cat = load_corpus_catalog(str(CATALOG))
    assert m["summary"]["n_organs"] == len(cat["organ_index"]) == 50
    assert len(m["organs"]) == 50


def test_every_organ_has_a_known_system():
    m = _manifest()
    # Every organ is assigned to a real (non-"Other") anatomical system, and
    # the manifest lists systems in SYSTEM_ORDER.
    for o in m["organs"]:
        assert o["system"] == organ_system(o["key"])
        assert o["system"] in SYSTEM_ORDER
        assert o["system"] != "Other"
    assert m["systems"] == [s for s in SYSTEM_ORDER if s in {o["system"] for o in m["organs"]}]
    assert m["summary"]["n_systems"] == len(m["systems"]) == 10


def test_pancreas_is_top_and_counts_match_organ_to_models():
    m = _manifest()
    cat = load_corpus_catalog(str(CATALOG))
    top = m["organs"][0]
    assert top["key"] == "pancreas"
    assert top["n_models"] == 36 == m["max_models"]
    assert top["n_models"] == len(cat["organ_to_models"][top["uberon"]])
    assert len(top["models"]) == top["n_models"]


def test_every_model_row_is_well_formed_and_sorted():
    m = _manifest()
    top = m["organs"][0]
    ids = [row["biomodel_id"] for row in top["models"]]
    assert ids == sorted(ids)
    for row in top["models"]:
        assert row["url"] == f"https://www.ebi.ac.uk/biomodels/{row['biomodel_id']}"
        assert row["name"] and not row["name"].startswith("BIOMD")  # real name resolved


def test_zero_model_organs_present_with_empty_models():
    m = _manifest()
    zero = [o for o in m["organs"] if o["n_models"] == 0]
    assert len(zero) == 40
    assert all(o["models"] == [] for o in zero)
    assert m["summary"]["n_modeled"] == 10


def test_glb_urls_split_by_sex():
    m = _manifest()
    pancreas = m["organs"][0]
    assert pancreas["glb"]["female"].endswith("3d-vh-f-pancreas.glb")
    assert pancreas["glb"]["male"].endswith("3d-vh-m-pancreas.glb")
