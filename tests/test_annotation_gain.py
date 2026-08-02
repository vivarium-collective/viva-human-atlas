from viva_human_atlas.annotation_gain import compare_catalogs

OI = {"pancreas": {"uberon": "UBERON:0001264"}, "liver": {"uberon": "UBERON:0002107"},
      "kidney": {"uberon": "UBERON:0004538"}}


def _cat(o2m):
    dos = []
    for uber, ids in o2m.items():
        for i in ids:
            dos.append({"biomodel_id": i, "organs": [{"organ": "x", "uberon": uber}]})
    return {"biomodel_dos": dos, "organ_index": OI, "organ_to_models": o2m}


def test_gain_adds_organ_and_models():
    name = _cat({"UBERON:0001264": ["A", "B"]})                       # pancreas: A,B
    anno = _cat({"UBERON:0001264": ["A", "C"], "UBERON:0002107": ["D"]})  # +C pancreas, +liver D
    r = compare_catalogs(name, anno)
    assert set(r["delta"]["organs_added"]) == {"liver"}
    assert r["union"]["n_models_total"] >= r["name"]["n_models_total"]
    assert r["union"]["n_models_total"] >= r["annotation"]["n_models_total"]
    assert r["delta"]["n_models_added"] == r["union"]["n_models_total"] - r["name"]["n_models_total"]
    per = {row["organ"]: row for row in r["delta"]["per_organ"]}
    assert per["pancreas"]["union_models"] == 3  # A,B,C
    assert per["liver"]["added"] is True
