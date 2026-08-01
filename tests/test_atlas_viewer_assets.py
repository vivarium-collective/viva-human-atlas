# tests/test_atlas_viewer_assets.py
from pathlib import Path

VIZ = Path(__file__).resolve().parents[1] / "studies" / "hra-atlas-browser" / "viz" / "atlas"


def test_viewer_assets_exist_and_are_wired():
    # encoding="utf-8" pinned explicitly: importing viva_human_atlas (via
    # pbg_simbio/viva_superpowers) flips the process's ambient locale
    # encoding to ASCII in some environments, which breaks the default
    # `Path.read_text()` on these UTF-8 files (em-dash, ellipsis). Same
    # class of issue already worked around in composite_generator.py.
    html = (VIZ / "index.html").read_text(encoding="utf-8")
    js = (VIZ / "viewer.js").read_text(encoding="utf-8")
    assert 'src="./viewer.js"' in html
    assert "config.json" in js and "atlas.json" in js.lower() or "cfg.atlas" in js
    assert "organ-select" in html          # the selector element
    assert "biomodels-panel" in html       # the model list panel
    assert "three@0.160.0" in html         # pinned importmap


def test_viewer_has_overview_mode():
    js = (VIZ / "viewer.js").read_text(encoding="utf-8")
    html = (VIZ / "index.html").read_text(encoding="utf-8")
    assert "overview_glb" in js or "cfg.overview_glb" in js
    assert "loadOverview" in js
    assert "__overview__" in html or "__overview__" in js  # the overview select value
