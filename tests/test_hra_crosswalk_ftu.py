import pytest

from viva_human_atlas.hra_api import fetch_crosswalk, fetch_ftu


class _R:
    def __init__(self, text=None, payload=None): self._t=text; self._p=payload
    def raise_for_status(self): pass
    @property
    def text(self): return self._t
    def json(self): return self._p

CSV = (
 '"ASCT+B ... Mapping",,,,,,,,\n'
 ',,,,,,,,\n'
 'anatomical_structure_of,source_spatial_entity,node_name,label,OntologyID,representation_of,node_type,glb file of single organs,Ref/1\n'
 '-,#VHFemaleOrgans,VH_F_kidney,kidney,UBERON:0002113,http://purl.obolibrary.org/obo/UBERON_0002113,mesh,VH_F_Kidney\n'
 '-,-,VH_F,-,-,-,organizational,3d-vh-f-united\n'
)

def test_fetch_crosswalk_parses_as_rows():
    rows = fetch_crosswalk(_get=lambda u, **k: _R(text=CSV))
    kidney = [r for r in rows if r["node_name"] == "VH_F_kidney"][0]
    assert kidney["uberon"] == "UBERON:0002113"
    assert kidney["label"] == "kidney"
    assert kidney["node_type"] == "mesh"
    assert kidney["organ_glb"] == "VH_F_Kidney"
    # organizational rows are still parsed (node present) but VH_F has no uberon
    assert any(r["node_name"] == "VH_F" and not r["uberon"] for r in rows)

def test_fetch_ftu_resolves_glb_url():
    payload = {"data": ["glomerulus.glb"], "metadata": {"title": "glomerulus (v1.0)"}}
    ftu = fetch_ftu("glomerulus", _get=lambda u, **k: _R(payload=payload))
    assert ftu["glb"] == "glomerulus.glb"
    assert ftu["glb_url"].endswith("/3d-ftu/glomerulus/latest/assets/glomerulus.glb")


@pytest.mark.network
def test_crosswalk_live_has_many_as():
    rows = fetch_crosswalk()
    withu = [r for r in rows if r["uberon"].startswith("UBERON:")]
    assert len(withu) >= 1000
