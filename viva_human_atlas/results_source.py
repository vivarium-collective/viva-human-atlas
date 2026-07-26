"""Robust reader for the committed viva-biomodels corpus time-course
dataset (viva-biomodels Task Z0, `pbg_biomodels.corpus_results`).

viva-human-atlas depends on `pbg-biomodels` (editable install), but that
checkout can be stale or held by a concurrent worktree/session mid-flight,
so `import pbg_biomodels.corpus_results` may not resolve to a checkout that
actually has the dataset committed yet. This module never raises on that:
every loader falls back to `None`/`{}` when the dataset can't be found.

Resolution order for the dataset file (`_dataset_path`):
  (a) env `VIVA_BIOMODELS_DATASET`, if set and it exists;
  (b) `import pbg_biomodels.corpus_results` and use its default dataset
      path, if that file exists;
  (c) glob `~/code/pbg-biomodels*/datasets/corpus_comparison/corpus_timecourse.parquet`
      (covers sibling checkouts/worktrees), first hit that exists;
  else `None`.

    from viva_human_atlas.results_source import (
        load_corpus_timecourse,
        model_timecourse,
        load_corpus_metrics,
    )

    df = load_corpus_timecourse()          # None if unavailable
    sub = model_timecourse("BIOMD0000000001", engine="copasi")
    metrics = load_corpus_metrics()        # {} if unavailable
"""
from __future__ import annotations

import glob
import json
import os
from pathlib import Path
from typing import Optional

import pandas as pd

_METRICS_FILENAME = "corpus_metrics.json"
_SIBLING_GLOB = "~/code/pbg-biomodels*/datasets/corpus_comparison/corpus_timecourse.parquet"


def _dataset_path() -> Optional[Path]:
    """Resolve the `corpus_timecourse.parquet` path, or `None` if it can't
    be found anywhere. See module docstring for the resolution order."""
    env_path = os.environ.get("VIVA_BIOMODELS_DATASET")
    if env_path:
        candidate = Path(env_path).expanduser()
        if candidate.exists():
            return candidate

    try:
        import pbg_biomodels.corpus_results as _corpus_results  # type: ignore

        candidate = Path(_corpus_results.DEFAULT_TIMECOURSE_PATH)
        if candidate.exists():
            return candidate
    except Exception:
        pass

    for match in sorted(glob.glob(str(Path(_SIBLING_GLOB).expanduser()))):
        candidate = Path(match)
        if candidate.exists():
            return candidate

    return None


def load_corpus_timecourse(path=None) -> Optional[pd.DataFrame]:
    """Load the corpus time-course dataset (`[biomodel_id, job, engine,
    variable, time, value]`). Returns `None` (never raises) if `path` is
    given but missing, or if no dataset can be resolved / read."""
    resolved = Path(path) if path is not None else _dataset_path()
    if resolved is None or not resolved.exists():
        return None
    try:
        return pd.read_parquet(resolved)
    except Exception:
        return None


def model_timecourse(
    biomodel_id, engine: str | None = None, job: str | None = None
) -> Optional[pd.DataFrame]:
    """Filter the default corpus time-course dataset down to one biomodel
    (and optionally one engine/job). Returns `None` if the dataset is
    unavailable."""
    df = load_corpus_timecourse()
    if df is None:
        return None
    mask = df["biomodel_id"].astype(str) == str(biomodel_id)
    if engine is not None:
        mask &= df["engine"].astype(str) == str(engine)
    if job is not None:
        mask &= df["job"].astype(str) == str(job)
    return df[mask]


def load_corpus_metrics(path=None) -> dict:
    """Load the sibling `corpus_metrics.json` (copasi<->tellurium pairwise
    agreement summary). Returns `{}` (never raises) if unavailable."""
    if path is not None:
        resolved = Path(path)
    else:
        dataset = _dataset_path()
        if dataset is None:
            return {}
        resolved = dataset.parent / _METRICS_FILENAME

    if not resolved.exists():
        return {}
    try:
        return json.loads(resolved.read_text(encoding="utf-8"))
    except Exception:
        return {}
