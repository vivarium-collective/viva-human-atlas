# tests/test_viewer_assets.py
#
# CONTROLLER CORRECTION: the task-10 brief pointed at
# viva_human_atlas/assets/hra_glb_viewer/viewer.js, which is a SEPARATE
# coverage viewer, not the one that renders the atlas' per-organ model lists.
# The viewer under test here is the atlas browser at
# studies/hra-atlas-browser/viz/atlas/, which Task 9 updated atlas.json's
# model-row shape for ({source_id, repository, url, name, ...} replacing the
# old biomodel_id-only shape).
from pathlib import Path

VIZ = Path(__file__).resolve().parent.parent / "studies" / "hra-atlas-browser" / "viz" / "atlas"
VIEWER = VIZ / "viewer.js"
INDEX = VIZ / "index.html"


def test_viewer_renders_source_badge_and_filter():
    js = VIEWER.read_text(encoding="utf-8")
    html = INDEX.read_text(encoding="utf-8")
    assert "repository" in js          # per-model source used in the list/badge
    assert "src-badge" in js           # the source badge itself
    assert "data-source-filter" in html  # the source filter control exists


def test_viewer_no_longer_references_stale_biomodel_id_field():
    # Task 9 renamed atlas.json's per-model id field from biomodel_id to
    # source_id; m.biomodel_id is now undefined everywhere it's read. This
    # proves the break is fixed.
    js = VIEWER.read_text(encoding="utf-8")
    assert "biomodel_id" not in js
    assert "source_id" in js
