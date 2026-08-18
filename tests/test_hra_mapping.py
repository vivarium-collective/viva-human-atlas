from viva_human_atlas.hra_mapping import map_to_hra
from viva_human_atlas.ftu_coverage import HRA_FTUS
from viva_human_atlas.biomodel_do import build_organ_index


def test_hra_ftus_have_uberon_ids():
    for f in HRA_FTUS:
        assert f.get("uberon", "").startswith("UBERON:"), f["ftu"]


ORGAN_INDEX = {
    "pancreas": {"uberon": "UBERON:0001264", "asset_urls": []},
    "liver": {"uberon": "UBERON:0002107", "asset_urls": []},
}


def test_map_to_hra_organ_ftu_celltype():
    out = map_to_hra(["UBERON:0001264", "UBERON:0000006"], "beta-cell insulin model", ORGAN_INDEX)
    assert {"label": "pancreas", "uberon": "UBERON:0001264"} in out["organs"]
    ftu_labels = {f["label"] for f in out["functional_tissue_units"]}
    assert any("islet" in l for l in ftu_labels)
    assert all(f["uberon"].startswith("UBERON:") for f in out["functional_tissue_units"])
    cl_ids = {c["cl"] for c in out["cell_types"]}
    assert "CL:0000169" in cl_ids  # beta cell, from the islet FTU
    assert "UBERON:0001264" in out["uberon_organ_ids"]
    assert "UBERON:0000006" in out["uberon_subregion_ids"]


def test_map_to_hra_id_lists_sorted_and_deduped():
    out = map_to_hra(
        ["UBERON:0002107", "UBERON:0001264", "UBERON:0001264", "UBERON:0000006", "UBERON:0000006"],
        "",
        ORGAN_INDEX,
    )
    assert out["uberon_organ_ids"] == ["UBERON:0001264", "UBERON:0002107"]
    assert out["uberon_subregion_ids"] == ["UBERON:0000006"]


# Production-shaped organ keys: `build_organ_index` keys off HRA reference-
# organ slugs (`lymph-node`, `ovary-female-left`) or an `ORGAN_SYNONYMS` key
# (`_match_organ_key("small intestine") -> "intestine"`). None of these equal
# the `HRA_FTUS` organ labels, so an exact-string join drops these FTUs.
PROD_ORGAN_INDEX = {
    "intestine": {"uberon": "UBERON:0000160", "asset_urls": []},
    "lymph-node": {"uberon": "UBERON:0000029", "asset_urls": []},
    "ovary-female-left": {"uberon": "UBERON:0002119", "asset_urls": []},
}


def test_map_to_hra_matches_ftus_across_organ_key_spellings():
    out = map_to_hra(
        ["UBERON:0000160", "UBERON:0000029", "UBERON:0002119"],
        "",
        PROD_ORGAN_INDEX,
    )
    labels = {f["label"] for f in out["functional_tissue_units"]}
    # "intestine" organ key vs "large intestine"/"small intestine" FTU organs
    assert "large-intestine crypt of Lieberkuhn" in labels
    assert "small-intestine crypt-villus axis" in labels
    # "lymph-node" slug vs "lymph node" FTU organ
    assert "lymph node follicle" in labels
    # "ovary-female-left" slug vs "ovary" FTU organ
    assert "ovarian follicle" in labels
    # and it must not over-match unrelated organs
    assert "liver lobule" not in labels
    assert "pancreatic islet of Langerhans" not in labels


def test_map_to_hra_organ_word_match_is_not_substring_match():
    # "ovary" must not match a key merely containing the letters, and an
    # unrelated organ key must not drag in every FTU.
    out = map_to_hra(["UBERON:0002107"], "", {"liver": {"uberon": "UBERON:0002107"}})
    labels = {f["label"] for f in out["functional_tissue_units"]}
    assert labels == {"liver lobule"}


# Task 4: map_to_hra now routes uberon_ids through anatomy_resolver.resolve_
# organ_keys, so a non-organ UBERON that only rolls up to an organ (not an
# organ-level exact id in organ_index) still resolves an organ, via the
# committed uberon_organ_rollup.json dataset (real production organ_index).
REAL_ORGAN_INDEX = build_organ_index()


def test_map_to_hra_rolls_up_nonorgan_uberon_via_resolver():
    # UBERON:0000956 = cerebral cortex, rolls up to "brain" per the committed
    # dataset (verified in task-3-report.md); it is NOT brain's own reference
    # (organ-level) UBERON id, so only the rollup tier can resolve it.
    out = map_to_hra(["UBERON:0000956"], "", REAL_ORGAN_INDEX)
    assert {"label": "brain", "uberon": REAL_ORGAN_INDEX["brain"]["uberon"]} in out["organs"]


def test_map_to_hra_empty_inputs():
    out = map_to_hra([], "", ORGAN_INDEX)
    assert out == {
        "organs": [],
        "functional_tissue_units": [],
        "cell_types": [],
        "uberon_organ_ids": [],
        "uberon_subregion_ids": [],
    }
