import yaml
from pathlib import Path


def test_study_references_the_pipeline_composite():
    s = yaml.safe_load(Path("studies/atlas-pipeline/study.yaml").read_text(encoding="utf-8"))
    assert s["schema_version"] == 4
    assert s["investigation"] == "hra-3d"
    assert "atlas_pipeline" in s["baseline"][0]["composite"]
