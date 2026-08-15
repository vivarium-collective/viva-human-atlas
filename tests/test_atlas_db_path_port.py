from viva_human_atlas.atlas_browser import ComputationalModelAtlas
from viva_human_atlas.core import build_core


def test_atlas_declares_db_path_input_port():
    step = ComputationalModelAtlas({}, core=build_core())
    assert step.inputs() == {"db_path": "string"}


def test_atlas_input_db_path_overrides_config(tmp_path):
    # Wired input path takes precedence over config; assert it reaches build.
    step = ComputationalModelAtlas(
        {"db_path": "config_path.json", "out_dir": str(tmp_path)},
        core=build_core(),
    )
    seen = {}
    import viva_human_atlas.atlas_browser as ab
    orig = ab.build_and_write_atlas
    ab.build_and_write_atlas = lambda **kw: (seen.update(kw) or
        {"summary": {}, "placement_stats": {}})
    try:
        step.update({"db_path": "wired_path.json"})
    finally:
        ab.build_and_write_atlas = orig
    assert seen["db_path"] == "wired_path.json"
