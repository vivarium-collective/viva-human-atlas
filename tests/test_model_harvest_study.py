"""Demonstrate-loading test for the `model-harvest` study (Task 8): its
baseline must point at the unified ModelHarvestStep with the exact params
that reproduce/refresh `datasets/model_hra_map.json` across both sources."""
import yaml
from pathlib import Path

STUDY = Path("studies/model-harvest/study.yaml")


def test_study_baseline_points_at_model_harvest_step():
    # encoding="utf-8" pinned explicitly: importing viva_human_atlas flips the
    # process's ambient locale encoding to ASCII in some environments, which
    # breaks the default Path.read_text() on this UTF-8 study.yaml (em-dash
    # in the title). Same class of issue documented in
    # tests/test_atlas_viewer_assets.py.
    d = yaml.safe_load(STUDY.read_text(encoding="utf-8"))
    baseline = d["baseline"][0]
    assert baseline["step"] == "local:viva_human_atlas.model_harvest.ModelHarvestStep"
    assert baseline["params"]["db_path"] == "datasets/model_hra_map.json"
    assert set(baseline["params"]["sources"]) == {"biomodels", "physionet"}
    assert baseline["params"]["build_if_missing"] is False
