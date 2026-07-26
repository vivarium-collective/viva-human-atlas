"""HRA GLB Viewer — a vivarium-workbench analysis-viewer plugin (HRA-3D Task D).

The workbench discovers a ``<pkg>.workbench_viewers`` module on the workspace
package and calls its ``get_viewers(ws_root)`` to render extra cards on the
Analyses page (see ``vivarium_workbench.lib.analysis_viewers`` for the
contract this mirrors, and ``pbg_ptools.workbench_viewers`` for a sibling
launcher-kind viewer).

This viewer is a plain static launcher: any study that has materialized a
``viz/hra/`` viewer pack (via ``viva_human_atlas.viewer_pack.materialize_viewer``)
gets a target whose ``href`` points straight at that study's
``viz/hra/index.html`` — a self-contained three.js page that reads its own
``config.json``/``coverage.json``/``spatial-links.json`` siblings, so there is
no ``launch`` callback to resolve server-side.
"""
from __future__ import annotations

from pathlib import Path


def _studies_with_hra(ws_root) -> list:
    """Slugs of studies (sorted) that have a materialized `viz/hra/coverage.json`.

    For a match `<study>/viz/hra/coverage.json`, the study slug is three
    parents up from the file: `hra` (p.parent) -> `viz` (.parent) ->
    `<study>` (.parent).
    """
    root = Path(ws_root) / "studies"
    return (
        sorted(p.parent.parent.parent.name for p in root.glob("*/viz/hra/coverage.json"))
        if root.exists()
        else []
    )


def _targets(ws_root) -> list:
    return [
        {
            "study": s,
            "label": f"HRA Organ Viewer — {s}",
            "detail": "3D organ colored by model coverage",
            "href": f"studies/{s}/viz/hra/index.html",
        }
        for s in _studies_with_hra(ws_root)
    ]


def get_viewers(ws_root) -> list:
    """Contribute the HRA Organ Viewer launcher (one target per study with a
    materialized `viz/hra/` pack)."""
    return [
        {
            "id": "hra-glb-viewer",
            "title": "HRA Organ Viewer",
            "description": "3D HRA organ (GLB) colored by mechanistic-model coverage.",
            "kind": "launcher",
            "applies": lambda ws: bool(_studies_with_hra(ws)),
            "targets": _targets,
        }
    ]
