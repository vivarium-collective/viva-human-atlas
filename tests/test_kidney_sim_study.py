import yaml
from pathlib import Path

def test_kidney_sim_study():
    s = yaml.safe_load(Path("studies/kidney-model-simulation/study.yaml").read_text())
    assert s["schema_version"] == 4
    assert s["investigation"] == "hra-3d"
    assert s["baseline"][0]["step"] == "local:viva_human_atlas.organ_simulation.OrganSimulationStep"
    assert s["baseline"][0]["params"]["organ"] == "kidney"
