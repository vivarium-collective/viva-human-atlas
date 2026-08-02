"""Regenerate every study's embedded figure(s) from live/committed data,
using the fixed `viz.py` builders (explicit height >= 450px so the report
iframe's auto-sizing doesn't collapse the figure).

Writes to `reports/figures/<slug>/<name>.html`, matching the exact paths each
study's `study.yaml` `embed_visualizations[].url` already references — this
script does not invent new filenames.

Run: `PYTHONUTF8=1 .venv/bin/python scripts/build_study_figures.py`
(needs network for the live HRA/BioModels fetches; the two COPASI-vs-Tellurium
overlays additionally need the committed viva-biomodels corpus dataset, see
`results_source._dataset_path`).
"""
from __future__ import annotations

from collections import Counter

from viva_human_atlas import annotation_gain, coverage, results_source, viz
from viva_human_atlas.ftu_coverage import build_ftu_model_coverage
from viva_human_atlas.hra_api import (
    fetch_anatomical_structure_terms,
    fetch_cell_type_terms,
    fetch_crosswalk,
    fetch_ftu,
    fetch_reference_organs,
)
from viva_human_atlas.spatial_link import build_spatial_links

GLUCOSE_QUERY = "glucose regulation"
GLUCOSE_MAX_RESULTS = 25
BULIK_MODEL = "BIOMD0000000633"


def _write(slug: str, name: str, html: str) -> None:
    rel_path = viz.write_study_figure(slug, name, html)
    print(f"wrote {rel_path} ({len(html)} bytes)")


def build_corpus_coverage_figure() -> None:
    out = coverage.build_corpus_coverage()
    html = viz.coverage_bar_html(out["summary"], out["coverage"])
    _write("corpus-coverage", "coverage-per-organ", html)


def build_model_coverage_3d_figure() -> None:
    out = coverage.build_coverage(GLUCOSE_QUERY, GLUCOSE_MAX_RESULTS)
    html = viz.coverage_bar_html(out["summary"], out["coverage"])
    _write("model-coverage-3d", "coverage-per-organ", html)


def _bulik_overlay_html() -> str:
    df = results_source.model_timecourse(BULIK_MODEL)
    if df is None or df.empty:
        raise RuntimeError(
            f"committed corpus timecourse dataset unavailable/empty for {BULIK_MODEL} "
            "(see results_source._dataset_path); cannot regenerate the "
            "COPASI-vs-Tellurium overlay figures without it."
        )
    return viz.timecourse_overlay_html(
        BULIK_MODEL, df, name="Bulik2016 hepatic glucose metabolism"
    )


def build_glucose_regulation_figure() -> None:
    _write("glucose-regulation", "copasi-vs-tellurium-BIOMD0000000633", _bulik_overlay_html())


def build_glucose_biomodel_do_figure() -> None:
    _write("glucose-biomodel-do", "copasi-vs-tellurium-BIOMD0000000633", _bulik_overlay_html())


def build_hra_reference_organs_figure() -> None:
    organs = fetch_reference_organs()
    n_uberon = sum(1 for o in organs if (o.get("uberon") or "").startswith("UBERON:"))
    counts = Counter(o.get("sex") or "unspecified" for o in organs)
    sexes = sorted(counts)
    html = viz.bar_html(
        sexes,
        [counts[s] for s in sexes],
        title=(
            f"HRA reference organs by sex ({len(organs)} entries, "
            f"{n_uberon}/{len(organs)} Uberon-keyed)"
        ),
        xaxis_title="sex",
        yaxis_title="reference-organ entries",
    )
    _write("hra-reference-organs", "organs-by-sex", html)


def build_hra_cell_types_figure(top_n: int = 15) -> None:
    terms = fetch_cell_type_terms()
    top = terms[:top_n]
    html = viz.bar_html(
        [t["cl"] for t in top],
        [t["count"] for t in top],
        title=f"Top {len(top)} of {len(terms)} HRA cell-type (CL) terms by occurrence count",
        xaxis_title="CL term",
        yaxis_title="occurrences",
    )
    _write("hra-cell-types", "top-cell-types", html)


def build_hra_anatomical_structures_figure(top_n: int = 15) -> None:
    terms = fetch_anatomical_structure_terms()
    top = terms[:top_n]
    html = viz.bar_html(
        [t["term"] for t in top],
        [t["count"] for t in top],
        title=f"Top {len(top)} of {len(terms)} HRA anatomical-structure terms by occurrence count",
        xaxis_title="anatomical-structure term",
        yaxis_title="occurrences",
    )
    _write("hra-anatomical-structures", "top-anatomical-structures", html)


def build_hra_3d_crosswalk_figure(top_n: int = 20) -> None:
    rows = fetch_crosswalk()
    n_uberon = sum(1 for r in rows if r.get("uberon"))
    counts = Counter(r["organ_glb"] for r in rows if r.get("organ_glb"))
    top = counts.most_common(top_n)
    html = viz.bar_html(
        [organ for organ, _ in top],
        [n for _, n in top],
        title=(
            f"AS nodes per source-organ GLB (top {len(top)} of {len(counts)} organs) — "
            f"{len(rows)} rows total, {n_uberon} Uberon-keyed"
        ),
        xaxis_title="source-organ GLB",
        yaxis_title="AS node count",
    )
    _write("hra-3d-crosswalk", "as-per-organ", html)


def build_ftu_glomerulus_figure() -> None:
    ftu = fetch_ftu("glomerulus")
    fields = ["slug", "title", "description", "glb", "glb_url"]
    rows = [(field, str(ftu.get(field, ""))) for field in fields]
    html = viz.table_html(["field", "value"], rows, title="Glomerulus FTU digital-object metadata")
    _write("ftu-glomerulus", "ftu-metadata", html)


def build_ftu_model_coverage_figure() -> None:
    out = build_ftu_model_coverage()
    rows = out["ftu_coverage"]
    summary = out["summary"]
    html = viz.bar_html(
        [row["ftu"] for row in rows],
        [row["n_models"] for row in rows],
        title=(
            f"Models per HRA FTU ({summary['n_ftus_covered']}/{summary['n_ftus']} "
            f"FTUs covered, {summary['n_models_matched']} distinct models)"
        ),
        xaxis_title="functional tissue unit",
        yaxis_title="models",
    )
    _write("ftu-model-coverage", "models-per-ftu", html)


def build_annotation_recall_gain_figure() -> None:
    name_catalog = coverage.load_corpus_catalog("datasets/biomodel_corpus_catalog.json")
    annotation_catalog = coverage.load_corpus_catalog("datasets/biomodel_annotation_catalog.json")
    gain = annotation_gain.compare_catalogs(name_catalog, annotation_catalog)
    per_organ = sorted(gain["delta"]["per_organ"], key=lambda row: row["union_models"], reverse=True)
    organs = [row["organ"] for row in per_organ]
    html = viz.grouped_bar_html(
        organs,
        [
            {"name": "name-only", "y": [row["name_models"] for row in per_organ]},
            {"name": "annotation", "y": [row["annotation_models"] for row in per_organ]},
            {"name": "union", "y": [row["union_models"] for row in per_organ]},
        ],
        title=(
            "Recall gain: name-only vs annotation-based organ matching "
            f"({gain['name']['n_models_total']} vs {gain['annotation']['n_models_total']} models, "
            f"union {gain['union']['n_models_total']})"
        ),
        yaxis_title="models",
    )
    _write("annotation-recall-gain", "recall-gain", html)


def build_spatial_linkage_figure() -> None:
    out = build_spatial_links(GLUCOSE_QUERY, GLUCOSE_MAX_RESULTS)
    counts = Counter(link["label"] for link in out["links"])
    organs = sorted(counts)
    html = viz.bar_html(
        organs,
        [counts[o] for o in organs],
        title=(
            f"Model->AS links per organ ({out['summary']['n_links']} links / "
            f"{out['summary']['n_models']} models)"
        ),
        xaxis_title="organ",
        yaxis_title="links",
    )
    _write("spatial-linkage", "links-per-organ", html)


def main() -> None:
    build_corpus_coverage_figure()
    build_model_coverage_3d_figure()
    build_glucose_regulation_figure()
    build_glucose_biomodel_do_figure()
    build_hra_reference_organs_figure()
    build_hra_cell_types_figure()
    build_hra_anatomical_structures_figure()
    build_hra_3d_crosswalk_figure()
    build_ftu_glomerulus_figure()
    build_ftu_model_coverage_figure()
    build_spatial_linkage_figure()
    build_annotation_recall_gain_figure()


if __name__ == "__main__":
    main()
