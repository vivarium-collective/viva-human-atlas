import json
from viva_human_atlas.annotation_match import write_catalog_envelope


def test_envelope_counts(tmp_path):
    catalog = {"biomodel_dos": [
        {"biomodel_id": "A", "organs": [{"organ": "pancreas", "uberon": "UBERON:0001264"}]},
        {"biomodel_id": "B", "organs": []}],
        "organ_index": {}, "organ_to_models": {"UBERON:0001264": ["A"]}}
    env = write_catalog_envelope(tmp_path / "cat.json", catalog)
    assert env["n_ids"] == 2 and env["n_named"] == 2 and env["n_tagged"] == 1
    on_disk = json.loads((tmp_path / "cat.json").read_text(encoding="utf-8"))
    assert on_disk["catalog"]["organ_to_models"] == {"UBERON:0001264": ["A"]}
