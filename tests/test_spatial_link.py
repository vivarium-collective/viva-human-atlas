"""Spatial linkage: biomodel-DO organ x crosswalk AS node join (HRA-3D Task C).

Offline (mocked): `build_biomodel_do_catalog` and `fetch_crosswalk` are both
monkeypatched on the `spatial_link` module (imported at its top), so
`build_spatial_links` never touches the network.
"""
from __future__ import annotations

import viva_human_atlas.spatial_link as sl


def test_build_spatial_links_liver_model_links_to_glb_node(monkeypatch):
    monkeypatch.setattr(sl, "build_biomodel_do_catalog", lambda q, n, **k: {
        "biomodel_dos": [{"biomodel_id": "BIOMD1", "name": "hepatic glucose",
                          "organs": [{"organ": "liver", "uberon": "UBERON:0002107"}]}],
        "organ_index": {"liver": {"uberon": "UBERON:0002107", "asset_urls": ["x/VH_F_Liver.glb"]}},
        "organ_to_models": {"UBERON:0002107": ["BIOMD1"]},
    })
    monkeypatch.setattr(sl, "fetch_crosswalk", lambda **k: [
        {"node_name": "VH_F_liver", "label": "liver", "uberon": "UBERON:0002107",
         "representation_of": "", "node_type": "mesh", "organ_glb": "VH_F_Liver", "parent": ""},
        {"node_name": "VH_F_kidney", "label": "kidney", "uberon": "UBERON:0002113",
         "representation_of": "", "node_type": "mesh", "organ_glb": "VH_F_Kidney", "parent": ""},
    ])

    out = sl.build_spatial_links(max_results=1)

    assert len(out["links"]) == 1
    link = out["links"][0]
    assert link["node_name"] == "VH_F_liver"
    assert link["biomodel_id"] == "BIOMD1"
    assert link["uberon"] == "UBERON:0002107"
    assert link["readout"] == "pending time-series"
    assert out["summary"]["n_links"] == 1
    assert out["summary"]["n_models"] == 1
