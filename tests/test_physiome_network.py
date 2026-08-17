import pytest
from viva_human_atlas import physiome
from viva_human_atlas.biomodel_do import build_organ_index


@pytest.mark.network
def test_pmr3_live_enumerate_and_build():
    ids = physiome.list_exposure_ids()
    assert len(ids) >= 900
    cites = physiome.load_citations()
    exps = physiome.resolve_exposures(_ids=ids[:20])
    assert all(e["identifier"].startswith("https://models.physiomeproject.org/") for e in exps)
    assert any(e["keywords"] for e in exps)
    oi = build_organ_index()
    entries = [physiome.build_entry(e, oi, citations=cites, no_llm=True) for e in exps]
    assert any(m["organs"] for m in entries)
    assert any(m["paper_pmid"] for m in entries)
