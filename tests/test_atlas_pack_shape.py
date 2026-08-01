import json
from pathlib import Path
from viva_human_atlas.atlas_pack import build_atlas_manifest, write_atlas_pack
from viva_human_atlas.coverage import load_corpus_catalog

CATALOG = Path(__file__).resolve().parents[1] / "datasets" / "biomodel_corpus_catalog.json"


def test_write_atlas_pack_emits_three_jsons(tmp_path):
    cat = load_corpus_catalog(str(CATALOG))
    manifest = build_atlas_manifest(cat)
    coverage = {"coverage": [], "summary": {"n_as": 0}}
    out = write_atlas_pack(tmp_path, manifest=manifest, coverage=coverage,
                           overview_glb_url="https://example/united.glb")
    atlas = json.loads((out / "atlas.json").read_text())
    cfg = json.loads((out / "config.json").read_text())
    assert atlas["organs"][0]["key"] == "pancreas"
    assert (out / "coverage.json").exists()
    assert cfg == {"atlas": "atlas.json", "coverage": "coverage.json",
                   "overview_glb": "https://example/united.glb", "node_field": "node_name"}
