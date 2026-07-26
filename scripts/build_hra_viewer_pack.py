"""Materialize the HRA GLB viewer pack for the `model-coverage-3d` study
(HRA-3D Task E).

Resolves a Female liver reference-organ GLB URL from the live HRA CCF API
(`hra_api.fetch_reference_organs`) — liver rather than kidney because the
glucose-regulation biomodel-DO set (`biomodel_do.ORGAN_SYNONYMS`) matches
liver/hepatic models directly, and organ-granularity propagation
(`coverage.build_coverage`) then covers every liver sub-AS node, so the
viewer actually shows meaningful green coverage instead of a handful of
isolated hits — builds model coverage (Task B, `coverage.build_coverage`)
and spatial links (Task C, `spatial_link.build_spatial_links`) against the
live crosswalk + BioModels search, and writes the resulting self-contained
three.js viewer pack (``coverage.json``, ``spatial-links.json``,
``config.json``, ``index.html``, ``viewer.js``) under
``studies/model-coverage-3d/viz/hra/`` via
``viewer_pack.materialize_viewer``. The committed pack under that directory
is what the workbench Analysis Tools viewer + published bundle serve.

Run with: ``PYTHONUTF8=1 .venv/bin/python scripts/build_hra_viewer_pack.py``
(network required — hits the live HRA CCF API, HRA CDN, and BioModels
search).
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from viva_human_atlas.coverage import build_coverage
from viva_human_atlas.hra_api import fetch_reference_organs
from viva_human_atlas.spatial_link import build_spatial_links
from viva_human_atlas.viewer_pack import materialize_viewer

STUDY_DIR = REPO_ROOT / "studies" / "model-coverage-3d"


def resolve_liver_female_glb_url() -> str:
    """Pick a Female liver reference-organ GLB URL from the live HRA API.

    Selects the reference-organ entry whose source `@id` contains "liver"
    and whose sex is "Female", with an `asset_url` (`object.file`) ending in
    `.glb`.
    """
    organs = fetch_reference_organs()
    for entry in organs:
        ref_organ_id = entry.get("ref_organ_id", "")
        asset_url = entry.get("asset_url") or ""
        if (
            "liver" in ref_organ_id.lower()
            and entry.get("sex") == "Female"
            and asset_url.endswith(".glb")
        ):
            return asset_url
    raise RuntimeError(
        "No Female liver reference organ with a .glb asset_url found in "
        "fetch_reference_organs()"
    )


def main() -> None:
    print("Resolving liver (female) reference-organ GLB URL...")
    liver_glb_url = resolve_liver_female_glb_url()
    print(f"  -> {liver_glb_url}")

    print("Building model coverage (query='glucose regulation')...")
    coverage = build_coverage()
    print(f"  -> {coverage['summary']}")

    print("Building spatial links (query='glucose regulation')...")
    links = build_spatial_links()
    print(f"  -> {links['summary']}")

    out_dir = materialize_viewer(
        STUDY_DIR,
        organ_glb_url=liver_glb_url,
        organ_label="liver",
        coverage=coverage,
        links=links,
    )
    print(f"Wrote viewer pack to {out_dir}")


if __name__ == "__main__":
    main()
