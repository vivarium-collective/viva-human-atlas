import yaml
from pathlib import Path

def test_kidney_sim_study():
    # encoding="utf-8" pinned explicitly: importing viva_human_atlas (COPASI
    # bindings) flips the process's ambient locale encoding to ASCII in some
    # environments, which breaks the default `Path.read_text()` on files with
    # non-ASCII characters like em-dashes. Same class of issue documented/worked
    # around in tests/test_organ_simulation_step.py.
    s = yaml.safe_load(Path("studies/kidney-model-simulation/study.yaml").read_text(encoding="utf-8"))
    assert s["schema_version"] == 4
    assert s["investigation"] == "hra-3d"
    assert s["baseline"][0]["step"] == "local:viva_human_atlas.organ_simulation.OrganSimulationStep"
    assert s["baseline"][0]["params"]["organ"] == "kidney"
