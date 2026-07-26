"""Model coverage over AS/organs: crosswalk (Task A) x biomodel-DO organ
annotations (Task A's `biomodel_do`), at organ granularity (v1).

Offline (mocked): `build_biomodel_do_catalog` and `fetch_crosswalk` are both
monkeypatched on the `coverage` module (imported at its top), so
`build_coverage` never touches the network.
"""
from __future__ import annotations

import viva_human_atlas.coverage as cov


def test_build_coverage_organ_granularity(monkeypatch):
    # organ_index's asset stem ("3d-vh-f-liver", the reference-organ naming
    # convention) and the crosswalk's `organ_glb` ("VH_F_Liver") are
    # deliberately different strings/casing/prefixes — this is what exercises
    # the normalized-organ-key comparison the propagation rule depends on.
    monkeypatch.setattr(cov, "build_biomodel_do_catalog", lambda q, n, **k: {
        "biomodel_dos": [{"biomodel_id": "BIOMD1", "name": "hepatic glucose",
                          "organs": [{"organ": "liver", "uberon": "UBERON:0002107"}]}],
        "organ_index": {"liver": {"uberon": "UBERON:0002107", "asset_urls": ["x/3d-vh-f-liver.glb"]}},
        "organ_to_models": {"UBERON:0002107": ["BIOMD1"]},
    })
    monkeypatch.setattr(cov, "fetch_crosswalk", lambda **k: [
        {"node_name": "VH_F_liver", "label": "liver", "uberon": "UBERON:0002107",
         "representation_of": "", "node_type": "mesh", "organ_glb": "VH_F_Liver", "parent": ""},
        {"node_name": "VH_F_kidney", "label": "kidney", "uberon": "UBERON:0002113",
         "representation_of": "", "node_type": "mesh", "organ_glb": "VH_F_Kidney", "parent": ""},
        # A liver sub-AS whose OWN uberon has no direct model annotation (and
        # differs from the liver organ's uberon), but whose `organ_glb`
        # belongs to the (now-normalized-matching) covered liver organ — this
        # is the propagation path: covered via its organ, not direct match.
        {"node_name": "VH_F_liver_lobule", "label": "hepatic lobule", "uberon": "UBERON:0004647",
         "representation_of": "", "node_type": "mesh", "organ_glb": "VH_F_Liver",
         "parent": "VH_F_liver"},
    ])
    out = cov.build_coverage(max_results=1)
    by = {r["uberon"]: r for r in out["coverage"]}
    assert by["UBERON:0002107"]["covered"] is True and by["UBERON:0002107"]["n_models"] == 1
    assert by["UBERON:0002113"]["covered"] is False
    # Propagation: no direct model on this uberon, but covered via its organ.
    assert by["UBERON:0004647"]["covered"] is True and by["UBERON:0004647"]["n_models"] == 0
    assert by["UBERON:0004647"]["node_name"] == "VH_F_liver_lobule"
    assert out["summary"]["n_as"] == 3 and out["summary"]["n_as_covered"] == 2
