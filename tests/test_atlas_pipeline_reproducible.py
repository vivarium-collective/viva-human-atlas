import json
from pathlib import Path
from process_bigraph import Composite
from viva_human_atlas.core import build_core
from viva_human_atlas.composites.atlas_pipeline import build_atlas_pipeline_document

def _atlas(out):
    return json.loads((Path(out) / "atlas.json").read_text(encoding="utf-8"))

def test_two_offline_runs_are_identical(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(); b.mkdir()
    Composite(build_atlas_pipeline_document(out_dir=str(a), live=False), core=build_core())
    Composite(build_atlas_pipeline_document(out_dir=str(b), live=False), core=build_core())
    # Prefer byte-identity; fall back to readout stats if float/key ordering churns.
    da = json.dumps(_atlas(a), sort_keys=True)
    db = json.dumps(_atlas(b), sort_keys=True)
    assert da == db
