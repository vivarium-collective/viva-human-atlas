import json

import pytest

import scripts.build_anatomy_crosswalks as b
from viva_human_atlas.biomodel_do import build_organ_index

OI = build_organ_index()

ASCTB = {
    "large-intestine": [{
        "anatomical_structures": [{"id": "UBERON:0000059"}, {"id": "UBERON:0001155"}],
        "cell_types": [{"id": "CL:0011108"}],
        "biomarkers_gene": [{"id": "HGNC:1", "label": "CDX2"}],
    }],
    "kidney": [{
        "anatomical_structures": [{"id": "UBERON:0002113"}, {"id": "UBERON:0001285"}],
        "cell_types": [{"id": "CL:0000499"}],
        "biomarkers_gene": [{"id": "HGNC:2", "label": "NPHS1"}],
    }],
    "bone-marrow": [{
        "anatomical_structures": [{"id": "UBERON:0002371"}],
        "cell_types": [],
        "biomarkers_gene": [],
    }],
}


def test_rollup_from_asctb_normalizes_organ_keys():
    r = b.rollup_from_asctb(ASCTB, OI)
    assert r["UBERON:0001155"] == ["intestine"]  # large-intestine -> intestine
    assert r["UBERON:0002113"] == ["kidney"]  # kidney synonym id
    assert "UBERON:0002371" not in r  # bone-marrow: no organ_index key


def test_cl_and_gene_maps():
    assert b.cl_map_from_asctb(ASCTB, OI)["CL:0000499"] == ["kidney"]
    g = b.gene_map_from_asctb(ASCTB, OI)
    assert g["NPHS1"] == {"kidney": 1} and "CDX2" in g


def test_small_intestine_alias_also_normalizes_to_intestine():
    asctb = {"small-intestine": [{
        "anatomical_structures": [{"id": "UBERON:0002108"}],
        "cell_types": [], "biomarkers_gene": [],
    }]}
    r = b.rollup_from_asctb(asctb, OI)
    assert r["UBERON:0002108"] == ["intestine"]


def test_eye_and_ovary_alias_to_sided_organ_index_keys():
    asctb = {
        "eye": [{"anatomical_structures": [{"id": "UBERON:0004548"}],
                 "cell_types": [], "biomarkers_gene": []}],
        "ovary": [{"anatomical_structures": [{"id": "UBERON:0002119"}],
                   "cell_types": [], "biomarkers_gene": []}],
    }
    r = b.rollup_from_asctb(asctb, OI)
    assert r["UBERON:0004548"] == ["eye-female-left"]
    assert r["UBERON:0002119"] == ["ovary-female-left"]


def test_organs_with_no_organ_index_match_contribute_nothing():
    # per the plan's verified ground truth: none of these normalize to an
    # organ_index key, including blood-vasculature -- which a naive
    # _match_organ_key substring fallback would (wrongly) fold into "blood".
    no_match_asctb_keys = [
        "bone-marrow", "skeleton", "knee", "muscular-system", "palatine-tonsil",
        "blood-vasculature", "lymph-vasculature", "anatomical-systems",
        "peripheral-nervous-system",
    ]
    asctb = {
        key: [{
            "anatomical_structures": [{"id": f"UBERON:999900{i}"}],
            "cell_types": [{"id": f"CL:99990{i}"}],
            "biomarkers_gene": [{"id": f"HGNC:999{i}", "label": f"FAKEGENE{i}"}],
        }]
        for i, key in enumerate(no_match_asctb_keys)
    }
    assert b.rollup_from_asctb(asctb, OI) == {}
    assert b.cl_map_from_asctb(asctb, OI) == {}
    assert b.gene_map_from_asctb(asctb, OI) == {}


def test_gene_map_counts_rows_not_gene_mentions():
    asctb = {"kidney": [
        {"anatomical_structures": [], "cell_types": [],
         "biomarkers_gene": [{"id": "HGNC:2", "label": "NPHS1"}]},
        {"anatomical_structures": [], "cell_types": [],
         "biomarkers_gene": [{"id": "HGNC:2", "label": "nphs1"}, {"id": "HGNC:2", "label": "NPHS1"}]},
    ]}
    g = b.gene_map_from_asctb(asctb, OI)
    # second row repeats NPHS1 twice within the SAME row -> still counts once
    assert g["NPHS1"] == {"kidney": 2}


def test_non_uberon_and_non_cl_structure_ids_are_ignored():
    asctb = {"kidney": [{
        "anatomical_structures": [{"id": "FMA:7203"}],
        "cell_types": [{"id": "PCL:0000001"}],
        "biomarkers_gene": [],
    }]}
    assert b.rollup_from_asctb(asctb, OI) == {}
    assert b.cl_map_from_asctb(asctb, OI) == {}


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _binding(term, ancestor, label=None):
    row = {
        "term": {"value": f"http://purl.obolibrary.org/obo/{term}"},
        "ancestor": {"value": f"http://purl.obolibrary.org/obo/{ancestor}"},
    }
    if label is not None:
        row["label"] = {"value": label}
    return row


def test_uberon_ancestors_rollup_exact_hit_offline():
    payload = {"results": {"bindings": [
        _binding("UBERON_0000956", "UBERON_0000956", "cerebral cortex"),
        _binding("UBERON_0000956", "UBERON_0000955", "brain"),
    ]}}
    fake_organ_index = {"brain": {"uberon": "UBERON:0000955"}}
    calls = []

    def fake_post(url, **kw):
        calls.append((url, kw))
        return _FakeResp(payload)

    r = b.uberon_ancestors_rollup(["UBERON:0000956"], fake_organ_index, _post=fake_post)
    assert r == {"UBERON:0000956": ["brain"]}
    assert calls and calls[0][0] == b.UBERGRAPH_URL


def test_uberon_ancestors_rollup_label_fallback_for_sided_reference_offline():
    # nephron's ancestors include the *generic* "kidney" (UBERON:0002113),
    # not the *sided* HRA reference uberon "left kidney" (UBERON:0004538) --
    # the label fallback (side-stripped) must bridge the two.
    payload = {"results": {"bindings": [
        _binding("UBERON_0001285", "UBERON_0001285", "nephron"),
        _binding("UBERON_0001285", "UBERON_0002113", "kidney"),
        _binding("UBERON_0004538", "UBERON_0004538", "left kidney"),
    ]}}
    fake_organ_index = {"kidney": {"uberon": "UBERON:0004538"}}

    def fake_post(url, **kw):
        return _FakeResp(payload)

    r = b.uberon_ancestors_rollup(["UBERON:0001285"], fake_organ_index, _post=fake_post)
    assert r == {"UBERON:0001285": ["kidney"]}


def test_uberon_ancestors_rollup_no_match_is_absent_offline():
    payload = {"results": {"bindings": [
        _binding("UBERON_0000001", "UBERON_0000001", "unrelated structure"),
    ]}}
    fake_organ_index = {"brain": {"uberon": "UBERON:0000955"}}

    def fake_post(url, **kw):
        return _FakeResp(payload)

    r = b.uberon_ancestors_rollup(["UBERON:0000001"], fake_organ_index, _post=fake_post)
    assert r == {}


def test_uberon_ancestors_rollup_excludes_blood_vasculature_container_offline():
    # A named vessel (e.g. uterine artery) is part_of BOTH the whole-body
    # "blood vasculature" container AND (via a different ancestor chain) a
    # real placeable organ. "blood" must never win via containment alone --
    # only the genuine organ hit should survive.
    payload = {"results": {"bindings": [
        _binding("UBERON_0002416", "UBERON_0002416", "uterine artery"),
        _binding("UBERON_0002416", "UBERON_0004537", "blood vasculature"),
        _binding("UBERON_0002416", "UBERON_0000995", "uterus"),
        _binding("UBERON_0004537", "UBERON_0004537", "blood vasculature"),
        _binding("UBERON_0000995", "UBERON_0000995", "uterus"),
    ]}}
    fake_organ_index = {
        "blood": {"uberon": "UBERON:0004537"},
        "uterus": {"uberon": "UBERON:0000995"},
    }

    def fake_post(url, **kw):
        return _FakeResp(payload)

    r = b.uberon_ancestors_rollup(["UBERON:0002416"], fake_organ_index, _post=fake_post)
    assert r == {"UBERON:0002416": ["uterus"]}


def test_uberon_ancestors_rollup_vessel_with_no_organ_ancestor_is_unplaced_offline():
    # A vessel that is ONLY part_of the whole-body vasculature (no other
    # organ ancestor) resolves to nothing, not "blood" -- acceptably unplaced.
    payload = {"results": {"bindings": [
        _binding("UBERON_0002097", "UBERON_0002097", "radial artery"),
        _binding("UBERON_0002097", "UBERON_0004537", "blood vasculature"),
        _binding("UBERON_0004537", "UBERON_0004537", "blood vasculature"),
    ]}}
    fake_organ_index = {"blood": {"uberon": "UBERON:0004537"}}

    def fake_post(url, **kw):
        return _FakeResp(payload)

    r = b.uberon_ancestors_rollup(["UBERON:0002097"], fake_organ_index, _post=fake_post)
    assert r == {}


def test_uberon_ancestors_rollup_multi_hit_lists_are_sorted_offline():
    # SPARQL binding order isn't stable -- multi-organ hits must come back
    # sorted for deterministic regeneration, regardless of response order.
    payload = {"results": {"bindings": [
        _binding("UBERON_0000001", "UBERON_0000001", "dual-organ structure"),
        _binding("UBERON_0000001", "UBERON_0000955", "brain"),
        _binding("UBERON_0000001", "UBERON_0004538", "left kidney"),
    ]}}
    fake_organ_index = {
        "brain": {"uberon": "UBERON:0000955"},
        "kidney": {"uberon": "UBERON:0004538"},
    }

    def fake_post(url, **kw):
        return _FakeResp(payload)

    r = b.uberon_ancestors_rollup(["UBERON:0000001"], fake_organ_index, _post=fake_post)
    assert r["UBERON:0000001"] == sorted(r["UBERON:0000001"])
    assert r["UBERON:0000001"] == ["brain", "kidney"]


def test_uberon_ancestors_rollup_empty_input_makes_no_request():
    def fake_post(url, **kw):
        raise AssertionError("should not be called for empty input")

    assert b.uberon_ancestors_rollup([], {"brain": {"uberon": "UBERON:0000955"}}, _post=fake_post) == {}


def test_main_writes_asctb_only_datasets_when_ubergraph_unreachable(tmp_path, monkeypatch):
    """Graceful-degradation path: both network calls fail (network down) --
    main() must still write the ASCT+B-derived datasets (rollup/CL/gene),
    with an empty FMA crosswalk, and must not raise."""

    def raising_uberon(*a, **k):
        raise ConnectionError("network down")

    def raising_fma(*a, **k):
        raise ConnectionError("network down")

    monkeypatch.setattr(b, "uberon_ancestors_rollup", raising_uberon)
    monkeypatch.setattr(b, "fma_to_uberon", raising_fma)

    rollup_out = tmp_path / "uberon_organ_rollup.json"
    cl_out = tmp_path / "cl_organ_map.json"
    gene_out = tmp_path / "gene_organ_map.json"
    fma_out = tmp_path / "fma_uberon_crosswalk.json"
    monkeypatch.setattr(b, "DATASETS", tmp_path)
    monkeypatch.setattr(b, "ROLLUP_OUT", rollup_out)
    monkeypatch.setattr(b, "CL_OUT", cl_out)
    monkeypatch.setattr(b, "GENE_OUT", gene_out)
    monkeypatch.setattr(b, "FMA_OUT", fma_out)

    b.main()  # must not raise

    rollup = json.loads(rollup_out.read_text())
    cl_map = json.loads(cl_out.read_text())
    gene_map = json.loads(gene_out.read_text())
    fma_crosswalk = json.loads(fma_out.read_text())

    # ASCT+B-derived slice still written in full (579 UBERON entries from
    # the real committed datasets/asctb_tables.json -- unaffected by the
    # network outage since ASCT+B parsing is entirely offline).
    asctb = json.loads(b.ASCTB_PATH.read_text(encoding="utf-8"))
    organ_index = b.load_corpus_catalog()["organ_index"]  # same source main() uses
    expected_asctb_rollup = b.rollup_from_asctb(asctb, organ_index)
    assert rollup == expected_asctb_rollup
    assert len(rollup) == 579
    assert cl_map  # non-empty, ASCT+B CL map unaffected
    assert gene_map  # non-empty, ASCT+B gene map unaffected
    assert fma_crosswalk == {}  # FMA step failed -> empty, not crashed


def test_fma_to_uberon_offline():
    payload = {"results": {"bindings": [
        {"uberon": {"value": "http://purl.obolibrary.org/obo/UBERON_0002113"},
         "xref": {"value": "FMA:7203"}},
    ]}}

    def fake_post(url, **kw):
        return _FakeResp(payload)

    assert b.fma_to_uberon(["FMA:7203"], _post=fake_post) == {"FMA:7203": "UBERON:0002113"}


def test_fma_to_uberon_empty_input_makes_no_request():
    def fake_post(url, **kw):
        raise AssertionError("should not be called for empty input")

    assert b.fma_to_uberon([], _post=fake_post) == {}


@pytest.mark.network
def test_uberon_ancestors_rollup_live_hand_checked_examples():
    organ_index = OI
    r = b.uberon_ancestors_rollup(
        ["UBERON:0000956", "UBERON:0001285", "UBERON:0001155"], organ_index,
    )
    assert "brain" in r["UBERON:0000956"]  # cerebral cortex -> brain
    assert "kidney" in r["UBERON:0001285"]  # nephron -> kidney
    assert "intestine" in r["UBERON:0001155"]  # colon -> intestine


@pytest.mark.network
def test_fma_to_uberon_live():
    r = b.fma_to_uberon(["FMA:7203"])  # "adult mammalian kidney"
    assert r["FMA:7203"].startswith("UBERON:")
    # end-to-end: the crossed UBERON rolls up to the kidney organ_index key
    rollup = b.uberon_ancestors_rollup([r["FMA:7203"]], OI)
    assert "kidney" in rollup[r["FMA:7203"]]
