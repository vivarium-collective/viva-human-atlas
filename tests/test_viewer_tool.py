"""Tests for the HRA GLB viewer analysis tool (HRA-3D Task D).

Two things are checked, both offline: the packaged static viewer
(``assets/hra_glb_viewer/{index.html,viewer.js}``) has the right shape via
grep-style content asserts (no headless browser needed — no build step means
the source *is* the artifact), and ``materialize_viewer`` writes the full
``viz/hra/`` file set for a study.
"""
from __future__ import annotations

import json
from pathlib import Path

from viva_human_atlas.viewer_pack import materialize_viewer

ASSETS = (
    Path(__file__).resolve().parent.parent
    / "viva_human_atlas"
    / "assets"
    / "hra_glb_viewer"
)


def test_index_html_references_viewer_js_and_importmap():
    html = (ASSETS / "index.html").read_text(encoding="utf-8")
    assert "viewer.js" in html
    assert "importmap" in html
    assert "three" in html


def test_viewer_js_reads_config_and_colors_by_coverage():
    js = (ASSETS / "viewer.js").read_text(encoding="utf-8")
    for token in ("config.json", "coverage", "covered", "GLTFLoader", "raycast"):
        assert token in js, f"expected {token!r} to appear in viewer.js"


def test_materialize_viewer_writes_all_files(tmp_path):
    study_dir = tmp_path / "studies" / "model-coverage-3d"
    coverage = {
        "coverage": [
            {
                "uberon": "UBERON:0002107",
                "label": "Liver",
                "organ_glb": "VH_F_Liver",
                "n_models": 1,
                "model_ids": ["BIOMD0000000001"],
                "covered": True,
            }
        ],
        "summary": {"n_as": 1, "n_as_covered": 1, "n_organs_glb": 1, "n_organs_glb_covered": 1},
    }
    links = {
        "links": [
            {
                "biomodel_id": "BIOMD0000000001",
                "name": "Glucose model",
                "uberon": "UBERON:0002107",
                "label": "Liver",
                "organ_glb": "VH_F_Liver",
                "node_name": "Liver_node",
                "readout": "pending time-series",
            }
        ],
        "summary": {"n_links": 1, "n_models": 1},
    }

    out_dir = materialize_viewer(
        study_dir,
        organ_glb_url="https://cdn.example.org/assets/VH_F_Liver.glb",
        organ_label="Liver",
        coverage=coverage,
        links=links,
    )

    assert out_dir == study_dir / "viz" / "hra"
    for name in ("config.json", "coverage.json", "spatial-links.json", "index.html", "viewer.js"):
        assert (out_dir / name).is_file(), f"missing {name}"

    config = json.loads((out_dir / "config.json").read_text(encoding="utf-8"))
    assert config["glb"] == "https://cdn.example.org/assets/VH_F_Liver.glb"
    assert config["organ"] == "Liver"
    assert config["coverage"] == "coverage.json"
    assert config["links"] == "spatial-links.json"
    assert config["node_field"] == "node_name"

    assert json.loads((out_dir / "coverage.json").read_text(encoding="utf-8")) == coverage
    assert json.loads((out_dir / "spatial-links.json").read_text(encoding="utf-8")) == links

    # Copied assets match the packaged source exactly (same viewer, no drift).
    assert (out_dir / "index.html").read_text(encoding="utf-8") == (
        ASSETS / "index.html"
    ).read_text(encoding="utf-8")
    assert (out_dir / "viewer.js").read_text(encoding="utf-8") == (
        ASSETS / "viewer.js"
    ).read_text(encoding="utf-8")


def test_materialize_viewer_custom_node_field(tmp_path):
    study_dir = tmp_path / "studies" / "other-study"
    out_dir = materialize_viewer(
        study_dir,
        organ_glb_url="https://cdn.example.org/assets/VH_M_Kidney.glb",
        organ_label="Kidney",
        coverage={"coverage": [], "summary": {}},
        links={"links": [], "summary": {}},
        node_field="organ_glb",
    )
    config = json.loads((out_dir / "config.json").read_text(encoding="utf-8"))
    assert config["node_field"] == "organ_glb"
