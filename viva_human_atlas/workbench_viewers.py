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
``config.json``/``coverage.json``/``spatial-links.json`` siblings, so no
server-side rendering is needed either way.

Both a ``targets`` (``href``-carrying) list *and* a ``launch`` callback are
provided, belt-and-suspenders, because the two paths through the workbench
differ: the published (gh-pages) snapshot may serve ``targets`` with ``href``
verbatim, but the installed vivarium-workbench's live env-worker path
(``_av_resolve_targets`` in ``env_worker.py``) strips each target down to
``{study, label, detail}`` before it reaches the browser, and clicking the
card instead calls ``/api/analysis-viewer/<id>/launch`` -> ``_av_resolve_launch``,
which 400s without a ``launch`` callable. So ``launch`` must independently
reconstruct the same ``href``.
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


def _launch(ws_root, study=None, run=None, ctx=None) -> dict:
    """Live-path launcher callback: resolve `study` straight to its
    materialized `viz/hra/index.html` href (`run`/`ctx` accepted for contract
    compatibility but unused — this viewer needs no server-side rendering)."""
    if not study:
        return {"error": "no study selected", "status": 400}
    return {"url": f"studies/{study}/viz/hra/index.html"}


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
            "launch": _launch,
        }
    ]
