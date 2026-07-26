"""Materialize the HRA GLB viewer + its data under a study's `viz/hra/`
(HRA-3D Task D.1).

Writes the study-specific ``coverage.json`` / ``spatial-links.json`` /
``config.json`` data files and copies the packaged, self-contained three.js
viewer (``viva_human_atlas.assets.hra_glb_viewer``: ``index.html`` +
``viewer.js``) in alongside them — via ``importlib.resources`` so this works
whether the package is installed editable (source tree) or as a built wheel.
The viewer reads everything from that sibling ``config.json`` (no query
params), so this directory is fully self-contained and can be served as
static files by the workbench (see ``workbench_viewers.get_viewers``).
"""
from __future__ import annotations

import json
from importlib import resources
from pathlib import Path

_VIEWER_ASSET_PACKAGE = "viva_human_atlas.assets.hra_glb_viewer"
_VIEWER_ASSET_FILES = ("index.html", "viewer.js")


def materialize_viewer(
    study_dir,
    *,
    organ_glb_url: str,
    organ_label: str,
    coverage: dict,
    links: dict,
    node_field: str = "node_name",
) -> Path:
    """Write the HRA GLB viewer + its data files to `study_dir/viz/hra/`.

    - `coverage.json` / `spatial-links.json`: the *coverage* (Task B) and
      *spatial-links* (Task C) result dicts, verbatim.
    - `config.json`: `{"glb": organ_glb_url, "organ": organ_label,
      "coverage": "coverage.json", "links": "spatial-links.json",
      "node_field": node_field}` — the viewer's only data contract.
    - `index.html` + `viewer.js`: copied from the packaged asset directory.

    Returns the `viz/hra/` directory.
    """
    out_dir = Path(study_dir) / "viz" / "hra"
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "coverage.json").write_text(
        json.dumps(coverage, indent=2), encoding="utf-8"
    )
    (out_dir / "spatial-links.json").write_text(
        json.dumps(links, indent=2), encoding="utf-8"
    )

    config = {
        "glb": organ_glb_url,
        "organ": organ_label,
        "coverage": "coverage.json",
        "links": "spatial-links.json",
        "node_field": node_field,
    }
    (out_dir / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")

    asset_dir = resources.files(_VIEWER_ASSET_PACKAGE)
    for name in _VIEWER_ASSET_FILES:
        (out_dir / name).write_bytes((asset_dir / name).read_bytes())

    return out_dir
