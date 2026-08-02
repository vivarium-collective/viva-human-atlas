from viva_human_atlas.workbench_viewers import get_viewers, _studies_with_atlas


def _mk(ws, slug):
    d = ws / "studies" / slug / "viz" / "atlas"
    d.mkdir(parents=True)
    (d / "atlas.json").write_text("{}")


def test_atlas_viewer_absent_when_no_pack(tmp_path):
    (tmp_path / "studies").mkdir()
    ids = [v["id"] for v in get_viewers(tmp_path) if v["applies"](tmp_path)]
    assert "hra-atlas-browser" not in ids


def test_atlas_viewer_present_and_targets_index(tmp_path):
    _mk(tmp_path, "hra-atlas-browser")
    assert _studies_with_atlas(tmp_path) == ["hra-atlas-browser"]
    viewer = next(v for v in get_viewers(tmp_path) if v["id"] == "hra-atlas-browser")
    assert viewer["applies"](tmp_path) is True
    targets = viewer["targets"](tmp_path)
    assert targets[0]["href"] == "/studies/hra-atlas-browser/viz/atlas/index.html"
    assert viewer["launch"](tmp_path, study="hra-atlas-browser")["url"] == \
        "/studies/hra-atlas-browser/viz/atlas/index.html"


def test_atlas_viewer_requires_observables(tmp_path):
    _mk(tmp_path, "hra-atlas-browser")
    viewer = next(v for v in get_viewers(tmp_path) if v["id"] == "hra-atlas-browser")
    assert viewer.get("requires") == ["observables"]


def test_atlas_launch_ignores_a_run_study_without_a_pack(tmp_path):
    # Launched from a per-run chip, `study` is the RUN's study (which has no
    # atlas pack). It must still resolve to the atlas-pack study, not build a
    # 404 URL under the run's study (that was the blank-tab bug).
    _mk(tmp_path, "hra-atlas-browser")
    viewer = next(v for v in get_viewers(tmp_path) if v["id"] == "hra-atlas-browser")
    result = viewer["launch"](tmp_path, study="annotation-recall-gain",
                              run="annotation-recall-gain__123__abc")
    assert result["url"] == "/studies/hra-atlas-browser/viz/atlas/index.html"
