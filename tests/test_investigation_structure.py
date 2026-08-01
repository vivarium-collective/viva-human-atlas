# tests/test_investigation_structure.py
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]


def _load(p):
    return yaml.safe_load(Path(p).read_text(encoding="utf-8"))


def test_atlas_study_exists_and_is_registered():
    study = _load(ROOT / "studies" / "hra-atlas-browser" / "study.yaml")
    assert study["name"] == "hra-atlas-browser"
    assert study["investigation"] == "hra-3d"
    inv = _load(ROOT / "investigations" / "hra-3d" / "investigation.yaml")
    assert "hra-atlas-browser" in inv["studies"]


def test_every_study_has_investigation_backref():
    inv_lists = {}  # study slug -> set of investigations that list it
    for inv_yaml in (ROOT / "investigations").glob("*/investigation.yaml"):
        inv = _load(inv_yaml)
        for s in inv.get("studies", []):
            inv_lists.setdefault(s, set()).add(inv["name"])
    for study_yaml in (ROOT / "studies").glob("*/study.yaml"):
        study = _load(study_yaml)
        assert "investigation" in study, f"{study['name']} missing investigation backref"
        if study["name"] in inv_lists:
            assert study["investigation"] in inv_lists[study["name"]], \
                f"{study['name']} backref {study['investigation']} not among {inv_lists[study['name']]}"
