import json
from pathlib import Path
from process_bigraph import Composite
from viva_human_atlas.core import build_core
from viva_human_atlas.composites.atlas_pipeline import build_atlas_pipeline_document


def _readouts(atlas_json_path):
    m = json.loads(Path(atlas_json_path).read_text(encoding="utf-8"))
    s = m.get("summary", m)
    return {k: s.get(k) for k in ("n_organs", "n_modeled", "n_models_distinct",
                                  "n_subregions", "n_organs_with_subregions")}


def test_pipeline_regenerates_committed_atlas_offline(tmp_path):
    committed = _readouts("studies/hra-atlas-browser/viz/atlas/atlas.json")
    doc = build_atlas_pipeline_document(out_dir=str(tmp_path), live=False)
    Composite(doc, core=build_core())
    regen = _readouts(str(tmp_path / "atlas.json"))
    assert regen == committed          # same artifacts, no hardcoded numbers


def test_pipeline_registered_as_composite_generator():
    import viva_human_atlas.composites  # noqa: F401 — fires @composite_generator registration
    from process_bigraph.composite_generator import _REGISTRY
    assert "viva_human_atlas.composites.atlas_pipeline.hra-atlas-pipeline" in _REGISTRY
