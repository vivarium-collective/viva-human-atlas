"""Task BV: Plotly viz helpers + corpus-results source.

Offline: `timecourse_overlay_html`/`coverage_bar_html`/`write_study_figure`
are exercised against tiny synthetic data (no network, no real dataset
required). `results_source.load_corpus_timecourse` must never raise, even
when the dataset can't be found. The one dataset-dependent assertion is
guarded behind `_dataset_path() is not None` so this suite stays green in
environments where the real viva-biomodels dataset isn't present.
"""
from __future__ import annotations

import re

import pandas as pd

from viva_human_atlas import viz
from viva_human_atlas.results_source import (
    _dataset_path,
    load_corpus_timecourse,
)

_EXPLICIT_HEIGHT_RE = re.compile(r'"height":\s*4\d\d|height\s*=\s*4\d\d')


def _synthetic_timecourse_df() -> pd.DataFrame:
    rows = []
    for engine in ("copasi", "tellurium"):
        for t in range(5):
            rows.append(
                {
                    "biomodel_id": "BIOMD0000000001",
                    "job": "auto_ten_seconds",
                    "engine": engine,
                    "variable": "S",
                    "time": float(t),
                    "value": float(t) * (1.0 if engine == "copasi" else 1.1),
                }
            )
    return pd.DataFrame(rows)


def test_timecourse_overlay_html_contains_plotly_engines_and_species():
    df = _synthetic_timecourse_df()

    html = viz.timecourse_overlay_html("BIOMD0000000001", df, name="toy model")

    lower = html.lower()
    assert "plotly" in lower
    assert "copasi" in lower
    assert "tellurium" in lower
    assert "S" in html
    assert "BIOMD0000000001" in html
    assert _EXPLICIT_HEIGHT_RE.search(html), "expected an explicit height >= 400 in the figure layout"


def test_coverage_bar_html_contains_organ_labels():
    coverage_summary = {"n_as": 4, "n_as_covered": 2}
    per_organ = [
        {"organ": "liver", "n_models": 12},
        {"organ": "kidney", "n_models": 0},
    ]

    html = viz.coverage_bar_html(coverage_summary, per_organ)

    assert "plotly" in html.lower()
    assert "liver" in html
    assert "kidney" in html
    assert _EXPLICIT_HEIGHT_RE.search(html), "expected an explicit height >= 400 in the figure layout"


def test_coverage_bar_html_derives_per_organ_from_raw_coverage_rows():
    coverage_summary = {"n_as": 2, "n_as_covered": 1}
    coverage_rows = [
        {"organ_glb": "VH_F_Liver", "n_models": 3, "covered": True},
        {"organ_glb": "VH_F_Kidney", "n_models": 0, "covered": False},
    ]

    html = viz.coverage_bar_html(coverage_summary, coverage_rows)

    assert "VH_F_Liver" in html
    assert "VH_F_Kidney" in html


def test_write_study_figure_writes_file_and_returns_relative_path(tmp_path):
    rel_path = viz.write_study_figure(
        "corpus-coverage", "coverage-bar", "<div>hi</div>", ws_root=str(tmp_path)
    )

    written = tmp_path / rel_path
    assert written.exists()
    assert written.read_text(encoding="utf-8") == "<div>hi</div>"
    assert rel_path == "reports/figures/corpus-coverage/coverage-bar.html"


def test_load_corpus_timecourse_missing_path_returns_none():
    assert load_corpus_timecourse("/nonexistent.parquet") is None


def test_load_corpus_timecourse_finds_real_dataset_when_available():
    if _dataset_path() is None:
        return  # real viva-biomodels dataset not present in this environment

    df = load_corpus_timecourse()

    assert df is not None
    assert len(df) > 0
    assert set(df["engine"].unique()) >= {"copasi", "tellurium"}
