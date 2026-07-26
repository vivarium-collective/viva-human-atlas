"""Materialize the HRA GLB viewer pack(s) for the `model-coverage-3d` study
(HRA-3D Task E, full-corpus Task B).

Builds model coverage against the committed **full-corpus** catalog
(`coverage.build_corpus_coverage`, Task A's `datasets/biomodel_corpus_catalog.json`
— 1,096 curated BioModels, 82 organ-tagged) rather than a single live
"glucose regulation" search, so the viewer reflects the whole corpus's organ
reach instead of one query's hits.

Writes:
  - the default top-level pack (``coverage.json``, ``spatial-links.json``,
    ``config.json``, ``index.html``, ``viewer.js``) under
    ``studies/model-coverage-3d/viz/hra/`` for the **most-covered organ**
    (the organ with the most corpus-tagged models — see
    `most_tagged_organ`), via ``viewer_pack.materialize_viewer``;
  - per-organ packs under ``studies/model-coverage-3d/viz/hra/<organ>/`` for
    kidney, liver, and pancreas (each via a temp-dir + move, since
    `materialize_viewer` always writes to `<study_dir>/viz/hra/`).

Spatial links (Task C, `spatial_link.build_spatial_links`) are also built
from the committed full-corpus catalog (`catalog=` fast-path, mirroring
coverage's corpus mode) rather than a single live "glucose regulation"
query, so every pack's ``spatial-links.json`` reflects corpus-wide
model->AS links, not just liver/pancreas glucose-query hits.

The committed pack under ``studies/model-coverage-3d/viz/hra/`` is what the
workbench Analysis Tools viewer + published bundle serve.

Run with: ``PYTHONUTF8=1 .venv/bin/python scripts/build_hra_viewer_pack.py``
(network required — hits the live HRA CCF API, HRA CDN, and the ASCT+B-3D
crosswalk).
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from viva_human_atlas.coverage import build_corpus_coverage, load_corpus_catalog
from viva_human_atlas.spatial_link import build_spatial_links
from viva_human_atlas.viewer_pack import materialize_viewer

STUDY_DIR = REPO_ROOT / "studies" / "model-coverage-3d"
CATALOG_PATH = REPO_ROOT / "datasets" / "biomodel_corpus_catalog.json"

PER_ORGAN_PACKS = ("kidney", "liver", "pancreas")


def most_tagged_organ(catalog: dict) -> str:
    """The `organ_index` key with the most corpus-tagged models
    (`organ_to_models`), e.g. "pancreas" (36 models in the committed
    corpus catalog) — used to pick the default top-level pack's organ."""
    uberon_to_organ = {
        entry["uberon"]: key for key, entry in catalog["organ_index"].items() if entry.get("uberon")
    }
    counts = {
        uberon_to_organ[uberon]: len(ids)
        for uberon, ids in catalog["organ_to_models"].items()
        if uberon in uberon_to_organ
    }
    return max(counts, key=counts.get)


def resolve_organ_glb_url(catalog: dict, organ_key: str, sex: str = "Female") -> str:
    """Pick one `asset_urls` entry for `organ_key` from the corpus catalog's
    `organ_index`, preferring the given `sex` (matched against the asset
    stem's naming convention, e.g. "3d-vh-f-pancreas.glb"), else the first
    available asset."""
    urls = catalog["organ_index"][organ_key].get("asset_urls") or []
    if not urls:
        raise RuntimeError(f"No asset_urls for organ {organ_key!r} in catalog organ_index")
    sex_tag = "-f-" if sex.lower().startswith("f") else "-m-"
    for url in urls:
        stem = url.rsplit("/", 1)[-1].lower()
        if sex_tag in stem or sex_tag.replace("-", "_") in stem:
            return url
    return urls[0]


def is_organ_covered(coverage: dict, organ_key: str) -> bool:
    """True if any crosswalk row whose normalized `organ_glb` matches
    `organ_key` (e.g. "VH_F_Kidney_L" -> "kidneyl" contains "kidney") is
    covered."""
    key = organ_key.lower()
    return any(
        key in (row.get("organ_glb") or "").lower() and row["covered"]
        for row in coverage["coverage"]
    )


def materialize_organ_pack(organ_key: str, *, glb_url: str, coverage: dict, links: dict) -> Path:
    """Write a per-organ viewer pack to `studies/model-coverage-3d/viz/hra/<organ_key>/`.

    `materialize_viewer` always writes to `<study_dir>/viz/hra/`, so this
    materializes into a scratch dir and moves the result into the desired
    per-organ subdirectory.
    """
    target = STUDY_DIR / "viz" / "hra" / organ_key
    with tempfile.TemporaryDirectory() as tmp:
        materialize_viewer(
            Path(tmp) / "scratch",
            organ_glb_url=glb_url,
            organ_label=organ_key,
            coverage=coverage,
            links=links,
        )
        src = Path(tmp) / "scratch" / "viz" / "hra"
        if target.exists():
            shutil.rmtree(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(target))
    return target


def main() -> None:
    print(f"Loading committed corpus catalog from {CATALOG_PATH}...")
    catalog = load_corpus_catalog(str(CATALOG_PATH))
    print(f"  {len(catalog['biomodel_dos'])} biomodel_dos, {len(catalog['organ_to_models'])} organs with models")

    print("Building corpus coverage (full-corpus catalog x live ASCT+B-3D crosswalk)...")
    coverage = build_corpus_coverage(str(CATALOG_PATH))
    print(f"  -> {coverage['summary']}")

    for organ in PER_ORGAN_PACKS:
        covered = is_organ_covered(coverage, organ)
        print(f"  kidney covered? {covered}" if organ == "kidney" else f"  {organ} covered? {covered}")

    print("Building spatial links (corpus catalog, all organ-tagged models)...")
    links = build_spatial_links(catalog=catalog)
    print(f"  -> {links['summary']}")

    default_organ = most_tagged_organ(catalog)
    default_glb_url = resolve_organ_glb_url(catalog, default_organ)
    print(f"Most-tagged organ in corpus catalog: {default_organ!r} -> {default_glb_url}")

    out_dir = materialize_viewer(
        STUDY_DIR,
        organ_glb_url=default_glb_url,
        organ_label=default_organ,
        coverage=coverage,
        links=links,
    )
    print(f"Wrote default top-level viewer pack to {out_dir}")

    for organ in PER_ORGAN_PACKS:
        glb_url = resolve_organ_glb_url(catalog, organ)
        out_dir = materialize_organ_pack(organ, glb_url=glb_url, coverage=coverage, links=links)
        print(f"Wrote per-organ viewer pack for {organ!r} to {out_dir}")


if __name__ == "__main__":
    main()
