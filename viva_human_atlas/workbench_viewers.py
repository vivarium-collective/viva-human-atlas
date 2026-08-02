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


def _studies_with_atlas(ws_root) -> list:
    root = Path(ws_root) / "studies"
    return (
        sorted(p.parent.parent.parent.name for p in root.glob("*/viz/atlas/atlas.json"))
        if root.exists() else []
    )


def _atlas_targets(ws_root) -> list:
    return [
        {"study": s, "label": f"HRA Atlas Browser — {s}",
         "detail": "3D organ browser colored by model count",
         "href": f"/studies/{s}/viz/atlas/index.html"}
        for s in _studies_with_atlas(ws_root)
    ]


def _atlas_launch(ws_root, study=None, run=None, ctx=None) -> dict:
    """Live-path launcher callback → the materialized `viz/atlas/index.html`.

    The Atlas Browser is a single global page (all organs in one manifest), so
    it opens the same place regardless of `study`/`run`. When launched from a
    per-run chip (Runs DB tab) no `study` is passed, so default to the
    workspace's atlas study rather than erroring; `run`/`ctx` are accepted for
    contract compatibility but unused (no server-side rendering)."""
    if not study:
        atlas_studies = _studies_with_atlas(ws_root)
        if not atlas_studies:
            return {"error": "no atlas pack found", "status": 404}
        study = atlas_studies[0]
    # Absolute (root-relative) URL: the frontend opens this via window.open in a
    # new tab, which resolves a bare "studies/..." against the current SPA page
    # path (→ wrong URL → blank tab). A leading slash pins it to the workbench
    # origin so it always loads the materialized page.
    return {"url": f"/studies/{study}/viz/atlas/index.html"}


def get_viewers(ws_root) -> list:
    """Contribute the HRA Organ Viewer launcher (one target per study with a
    materialized `viz/hra/` pack)."""
    return [
        {
            "id": "hra-atlas-browser",
            "title": "HRA Atlas Browser",
            "description": "3D HRA organ browser: pick an organ, see regions colored by model count, click through to BioModels.",
            "kind": "launcher",
            "requires": ["observables"],
            "applies": lambda ws: bool(_studies_with_atlas(ws)),
            "targets": _atlas_targets,
            "launch": _atlas_launch,
        },
    ]
