"""Plotly visualization helpers for viva-human-atlas study reports (Task
BV). Self-contained HTML fragments/pages (`include_plotlyjs="cdn"`) meant
to be embedded via a study's `embed_visualizations` (see
`write_study_figure`, which writes them under `reports/figures/<slug>/`).
"""
from __future__ import annotations

from pathlib import Path

import plotly.graph_objects as go

# Per-engine line style for the COPASI-vs-Tellurium overlay: COPASI solid,
# Tellurium dashed, anything else dotted (so a future 3rd engine doesn't
# collide visually with either).
_ENGINE_DASH = {"copasi": "solid", "tellurium": "dash"}
_PREFERRED_JOB = "auto_ten_seconds"


def timecourse_overlay_html(bid, df, *, name: str = "", max_species: int = 6) -> str:
    """Self-contained Plotly HTML overlaying COPASI (solid) vs Tellurium
    (dashed) per-species trajectories for one biomodel.

    `df` is a tidy dataframe with columns `engine, variable, time, value`
    for (at least) one biomodel; optional `biomodel_id`/`job` columns
    narrow it down to `bid` and, when multiple jobs are present, prefer
    the `auto_ten_seconds` job (else the first job encountered).
    """
    sub = df
    if "biomodel_id" in sub.columns:
        sub = sub[sub["biomodel_id"].astype(str) == str(bid)]
    if "job" in sub.columns:
        jobs = list(sub["job"].unique())
        job = _PREFERRED_JOB if _PREFERRED_JOB in jobs else (jobs[0] if jobs else None)
        if job is not None:
            sub = sub[sub["job"] == job]

    species = sorted(str(v) for v in sub["variable"].unique())[:max_species]
    engines = sorted(str(e) for e in sub["engine"].unique())

    fig = go.Figure()
    for engine in engines:
        dash = _ENGINE_DASH.get(engine.lower(), "dot")
        eng_df = sub[sub["engine"].astype(str) == engine]
        for species_name in species:
            trace_df = eng_df[eng_df["variable"].astype(str) == species_name].sort_values("time")
            if trace_df.empty:
                continue
            fig.add_trace(
                go.Scatter(
                    x=trace_df["time"],
                    y=trace_df["value"],
                    mode="lines",
                    line=dict(dash=dash),
                    name=f"{engine}: {species_name}",
                )
            )

    title = f"{bid} — {name}" if name else str(bid)
    fig.update_layout(
        title=title,
        xaxis_title="time",
        yaxis_title="value",
        height=480,
        margin=dict(l=70, r=30, t=70, b=70),
        font=dict(size=13),
        title_font_size=15,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        hovermode="x unified",
    )
    return fig.to_html(include_plotlyjs="cdn", full_html=True)


def _per_organ_rows(per_organ) -> list[dict]:
    """Normalize `per_organ` to `[{"organ": ..., "n_models": ...}, ...]`.

    Accepts either already-aggregated rows (`{"organ": ..., "n_models":
    ...}`) or raw coverage rows as returned by `coverage.build_coverage`
    (`{"organ_glb": ..., "n_models": ..., "covered": ..., ...}`), which are
    aggregated here by summing `n_models` per `organ_glb`.
    """
    rows = list(per_organ or [])
    if rows and "organ" in rows[0]:
        return rows

    totals: dict[str, int] = {}
    for row in rows:
        organ = row.get("organ_glb") or row.get("label") or "unknown"
        totals[organ] = totals.get(organ, 0) + int(row.get("n_models") or 0)
    return [{"organ": organ, "n_models": n} for organ, n in sorted(totals.items())]


def coverage_bar_html(coverage_summary: dict, per_organ) -> str:
    """Self-contained Plotly HTML: a bar chart of models (or AS-covered
    count) per organ, derived from a `coverage.build_coverage`-shaped
    result. `coverage_summary` supplies the title's overall AS-covered
    tally when present (`n_as`/`n_as_covered`)."""
    rows = _per_organ_rows(per_organ)
    organs = [row["organ"] for row in rows]
    n_models = [row["n_models"] for row in rows]

    fig = go.Figure(go.Bar(x=organs, y=n_models, name="models per organ"))

    title = "BioModels coverage per organ"
    coverage_summary = coverage_summary or {}
    n_as = coverage_summary.get("n_as")
    n_as_covered = coverage_summary.get("n_as_covered")
    if n_as is not None and n_as_covered is not None:
        title += f" ({n_as_covered}/{n_as} anatomical structures covered)"

    fig.update_layout(
        title=title,
        xaxis_title="organ",
        yaxis_title="models",
        height=470,
        margin=dict(l=80, r=30, t=70, b=170),
        font=dict(size=13),
        title_font_size=15,
        xaxis_tickangle=-45,
        bargap=0.25,
    )
    return fig.to_html(include_plotlyjs="cdn", full_html=True)


def bar_html(x, y, *, title: str = "", xaxis_title: str = "", yaxis_title: str = "") -> str:
    """Self-contained Plotly HTML: a generic labeled count-bar chart, for
    figures whose title/axis semantics don't fit `coverage_bar_html`'s
    BioModels-coverage-specific title (e.g. reference organs by sex, top
    HRA cell-type/anatomical-structure terms, AS nodes per organ-GLB,
    model->AS links per organ). Same tall/readable layout treatment as the
    other builders — explicit height, generous margins for rotated tick
    labels, readable font."""
    fig = go.Figure(go.Bar(x=list(x), y=list(y)))
    fig.update_layout(
        title=title,
        xaxis_title=xaxis_title,
        yaxis_title=yaxis_title,
        height=470,
        margin=dict(l=80, r=30, t=70, b=170),
        font=dict(size=13),
        title_font_size=15,
        xaxis_tickangle=-45,
        bargap=0.25,
    )
    return fig.to_html(include_plotlyjs="cdn", full_html=True)


def table_html(headers, rows, *, title: str = "") -> str:
    """Self-contained Plotly HTML: a left-aligned info table (e.g. a single
    digital object's field/value pairs). `rows` is a list of tuples/lists,
    one per table row, each with `len(headers)` cells."""
    rows = list(rows)
    columns = list(zip(*rows)) if rows else [[] for _ in headers]
    fig = go.Figure(
        go.Table(
            header=dict(values=list(headers), align="left"),
            cells=dict(values=[list(col) for col in columns], align="left"),
        )
    )
    fig.update_layout(
        title=title,
        height=470,
        margin=dict(l=30, r=30, t=70, b=30),
        font=dict(size=13),
        title_font_size=15,
    )
    return fig.to_html(include_plotlyjs="cdn", full_html=True)


def write_study_figure(study_slug: str, name: str, html: str, ws_root: str = ".") -> str:
    """Write `html` to `<ws_root>/reports/figures/<study_slug>/<name>.html`
    (creating parent dirs as needed) and return the path relative to
    `ws_root` (e.g. `reports/figures/<study_slug>/<name>.html`), suitable
    for a study's `embed_visualizations`.

    Note `reports/*` is gitignored (`reports/published/`) — callers must
    `git add -f` the written figure to commit it.
    """
    rel_path = Path("reports") / "figures" / study_slug / f"{name}.html"
    full_path = Path(ws_root) / rel_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(html, encoding="utf-8")
    return str(rel_path)
