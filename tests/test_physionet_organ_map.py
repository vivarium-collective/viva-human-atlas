from viva_human_atlas import physionet_organ_map as pom
from viva_human_atlas.biomodel_do import build_organ_index

ORGAN_INDEX = build_organ_index()


def test_keyword_table_maps_ecg_to_heart():
    ub = pom.keyword_uberons(["ecg", "arrhythmia"], "MIT-BIH Arrhythmia Database")
    assert "UBERON:0000948" in ub  # heart


def test_map_project_deterministic_no_llm():
    proj = {"name": "MIT-BIH Arrhythmia Database", "keywords": ["ecg", "arrhythmia"], "abstract": ""}
    out = pom.map_project_to_organs(proj, ORGAN_INDEX, no_llm=True)
    assert out["mapping_method"] == "keyword"
    assert any("heart" in (o.get("label", "") or "").lower() or o.get("uberon") == "UBERON:0000948"
               for o in out["organs"])


def test_unmapped_without_llm_is_marked():
    proj = {"name": "Totally Unknown Signal Set", "keywords": ["xyzzy"], "abstract": ""}
    out = pom.map_project_to_organs(proj, ORGAN_INDEX, no_llm=True)
    assert out["mapping_method"] == "unmapped"
    assert out["organs"] == []


def test_llm_fallback_used_when_keywords_miss():
    proj = {"name": "Cerebral Recording Set", "keywords": ["xyzzy"], "abstract": "intracranial brain signals"}
    calls = {}
    def fake_llm(name, abstract, fulltext, *, model, cache_dir=None):
        calls["hit"] = True
        return {"candidate_uberon": ["UBERON:0000955"]}  # brain
    out = pom.map_project_to_organs(proj, ORGAN_INDEX, no_llm=False, _llm=fake_llm)
    assert calls.get("hit") is True
    assert out["mapping_method"] == "llm"
