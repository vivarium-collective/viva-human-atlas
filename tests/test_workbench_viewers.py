"""Tests for the workbench analysis-viewer contribution (HRA-3D Task D.2).

``viva_human_atlas.workbench_viewers.get_viewers`` is discovered by
vivarium-workbench (via the workspace package / a `pbg-*`/`viva-*`-style
scan) and contributes the HRA GLB Viewer launcher whenever a study has
materialized a `viz/hra/coverage.json`.
"""
from __future__ import annotations

from viva_human_atlas.workbench_viewers import get_viewers


def _make_ws_with_hra_study(tmp_path, slug: str = "model-coverage-3d"):
    hra_dir = tmp_path / "studies" / slug / "viz" / "hra"
    hra_dir.mkdir(parents=True)
    (hra_dir / "coverage.json").write_text("{}", encoding="utf-8")
    return tmp_path


def test_get_viewers_reports_hra_glb_viewer_shape(tmp_path):
    ws_root = _make_ws_with_hra_study(tmp_path)
    viewers = get_viewers(ws_root)

    assert len(viewers) == 1
    viewer = viewers[0]
    assert viewer["id"] == "hra-glb-viewer"
    assert viewer["kind"] == "launcher"
    assert callable(viewer["applies"])
    assert viewer["applies"](ws_root) is True
    assert callable(viewer["targets"])


def test_get_viewers_targets_one_study_with_hra(tmp_path):
    ws_root = _make_ws_with_hra_study(tmp_path, slug="model-coverage-3d")
    viewer = get_viewers(ws_root)[0]

    targets = viewer["targets"](ws_root)
    assert len(targets) == 1
    target = targets[0]
    assert target["study"] == "model-coverage-3d"
    assert target["href"].endswith("studies/model-coverage-3d/viz/hra/index.html")


def test_get_viewers_empty_targets_and_not_applies_without_coverage(tmp_path):
    (tmp_path / "studies").mkdir()
    viewer = get_viewers(tmp_path)[0]

    assert viewer["applies"](tmp_path) is False
    assert viewer["targets"](tmp_path) == []


def test_get_viewers_no_studies_dir_at_all(tmp_path):
    viewer = get_viewers(tmp_path)[0]
    assert viewer["applies"](tmp_path) is False
    assert viewer["targets"](tmp_path) == []
