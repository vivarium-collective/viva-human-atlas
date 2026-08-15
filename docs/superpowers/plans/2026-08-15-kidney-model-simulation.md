# Kidney Model Simulation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A study that takes an organ (kidney), pulls every atlas-mapped model, runs each in its compatible simulator (SBML→COPASI, CellML→OpenCOR), and renders all timeseries in one interactive dashboard — runners and failures shown honestly.

**Architecture:** A new `viva_human_atlas/organ_simulation.py` with a pure selection function + two connectable Steps, reusing `viva_biomodels`'s turnkey SBML runner and `viva_opencor`'s OpenCOR Step (both spike-validated). A Physiome→CellML URL resolver (spike-validated) fills the one gap. A normalization layer unifies the two result shapes; a Plotly dashboard renders the grid.

**Tech Stack:** Python, process-bigraph, `viva_biomodels.composites.compare_simulators.run_comparison`, `viva_opencor.processes.OpenCORUTCStep`, Plotly, pytest.

**Spec:** `docs/superpowers/specs/2026-08-15-kidney-model-simulation-design.md`

## Global Constraints

- **Test invocation** (bare pytest/system python fail — missing deps), from the worktree root:
  `PYTHONPATH=$PWD /Users/eranagmon/code/viva-human-atlas/.venv/bin/python -m pytest <args> -v`
  (worktree wins over the editable canonical install; verify `viva_human_atlas.__file__` is under the worktree.)
- **Workspace Steps** live under `viva_human_atlas/` (auto-registered by `core.build_core`). In tests, construct them with `core=build_core()` (from `viva_human_atlas.core`) — `process_bigraph.Step.__init__` raises `must provide a core` otherwise. Check registration with `core.link_registry.get("<dotted>") is <Class>` (NOT `core.access`, which returns non-None for any name).
- **Study `baseline` is a LIST**: `baseline:\n  - name: baseline\n    step: <addr>\n    params: {...}`. Test it as `s["baseline"][0]["step"]`.
- **Reuse, don't rebuild**: SBML runs go through `run_comparison`; CellML through `OpenCORUTCStep`. No reimplementation of simulators.
- **Network/native isolation**: unit tests are OFFLINE (monkeypatch the network/engine calls); any test that hits PMR/BioModels or runs a native engine is marked `@pytest.mark.network` and is NOT required for the suite to pass.
- Commit footer on every commit:
  ```

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  ```
  Use `git -c commit.gpgsign=false commit` if signing errors.

**Reference shapes (verified in the spike):**
- `run_comparison(ids, simulators=["copasi"]) -> {bid: {"engines": {"copasi": {"time":[...],"columns":[...],"values":[[...]]}}, "comparison": {...}, "error": str|None}}`.
- `OpenCORUTCStep(config={"model_source": url, "end_time": e, "number_of_steps": n}, core=allocate_core()+register_link).update({})["result"] = {"time":[...], "state": {"comp/var":[...]}, "rates":{}, "variables":{}, "constants":{}}`.
- DB entry fields: `repository` (biomodels/physiome/physionet), `biomodel_id`, `source_id`, `identifier`, `organs:[{label}]`.

---

### Task 1: `select_organ_models` + `OrganModelSelectStep`

**Files:**
- Create: `viva_human_atlas/organ_simulation.py`
- Test: `tests/test_organ_select.py`

**Interfaces:**
- Produces: `select_organ_models(organ: str, db_path: str = "datasets/model_hra_map.json") -> list[dict]` — each `{"key","name","repository","simulator","runnable","ref"}`. `simulator`: biomodels→"copasi", physiome→"opencor", physionet→None. `ref`: `biomodel_id` (biomodels) else `identifier`. `runnable`: `simulator is not None`.
- Produces: `OrganModelSelectStep(process_bigraph.Step)` — config `{organ, db_path}`; `inputs()={}`; `outputs()={"manifest":"list[tree]","n_models":"integer","per_simulator":"tree","summary":"tree"}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_organ_select.py
from viva_human_atlas.organ_simulation import select_organ_models, OrganModelSelectStep
from viva_human_atlas.core import build_core

def test_select_kidney_models_split_by_simulator():
    models = select_organ_models("kidney")
    sims = {}
    for m in models:
        sims[m["simulator"]] = sims.get(m["simulator"], 0) + 1
    assert sims.get("copasi", 0) == 5          # 5 SBML biomodels
    assert sims.get("opencor", 0) == 19         # 19 Physiome CellML
    assert all(m["runnable"] for m in models)   # physionet excluded from the list
    assert {m["ref"] for m in models if m["simulator"] == "copasi"} >= {"BIOMD0000000259"}

def test_select_step_registered_and_runs():
    core = build_core()
    assert core.link_registry.get("viva_human_atlas.organ_simulation.OrganModelSelectStep") is OrganModelSelectStep
    out = OrganModelSelectStep({"organ": "kidney"}, core=core).update({})
    assert out["n_models"] == 24
    assert out["per_simulator"]["copasi"] == 5 and out["per_simulator"]["opencor"] == 19
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=$PWD /Users/eranagmon/code/viva-human-atlas/.venv/bin/python -m pytest tests/test_organ_select.py -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Write minimal implementation**

```python
# viva_human_atlas/organ_simulation.py
"""Take an organ, pull its atlas-mapped models, route each to its compatible
simulator, run to a timeseries, normalize, and render an interactive dashboard.

SBML (BioModels) -> COPASI via viva_biomodels.run_comparison; CellML (Physiome)
-> OpenCOR via viva_opencor.OpenCORUTCStep. PhysioNet entries are dataset
references, not runnable ODE models, and are excluded. Non-runnable / failing
models are marked, never dropped silently.
"""
from __future__ import annotations

import json
from pathlib import Path

from process_bigraph import Step

_REPO = Path(__file__).resolve().parents[1]
_DEFAULT_DB = str(_REPO / "datasets" / "model_hra_map.json")
_SIM_BY_REPO = {"biomodels": "copasi", "physiome": "opencor", "physionet": None}


def select_organ_models(organ: str, db_path: str = _DEFAULT_DB) -> list:
    organ = organ.lower()
    db = json.loads(Path(db_path).read_text(encoding="utf-8"))
    out = []
    for e in db:
        if not any(organ in (o.get("label") or "").lower() for o in (e.get("organs") or [])):
            continue
        sim = _SIM_BY_REPO.get(e.get("repository"))
        if sim is None:
            continue  # physionet / unknown: not runnable, exclude
        ref = e.get("biomodel_id") if e.get("repository") == "biomodels" else e.get("identifier")
        out.append({
            "key": e.get("source_id") or e.get("biomodel_id") or e.get("identifier"),
            "name": e.get("name") or "",
            "repository": e.get("repository"),
            "simulator": sim,
            "runnable": True,
            "ref": ref,
        })
    return out


class OrganModelSelectStep(Step):
    """Step: select an organ's runnable models from the atlas DB and route each
    to its compatible simulator."""

    description = ("Select every model tagged to an organ from the BioModels/"
                   "Physiome->HRA map and route it to a simulator (SBML->COPASI, "
                   "CellML->OpenCOR); PhysioNet dataset entries are excluded.")

    config_schema = {"organ": "string", "db_path": "string"}

    def inputs(self):
        return {}

    def outputs(self):
        return {"manifest": "list[tree]", "n_models": "integer",
                "per_simulator": "tree", "summary": "tree"}

    def update(self, inputs):
        organ = self.config.get("organ") or "kidney"
        models = select_organ_models(organ, self.config.get("db_path") or _DEFAULT_DB)
        per_sim = {}
        for m in models:
            per_sim[m["simulator"]] = per_sim.get(m["simulator"], 0) + 1
        return {
            "manifest": models,
            "n_models": len(models),
            "per_simulator": per_sim,
            "summary": {"organ": organ, "n_models": len(models), "by_simulator": per_sim},
        }


OrganModelSelectStep.contract = {
    "summary": OrganModelSelectStep.description,
    "outputs": {
        "manifest": "Per-model {key,name,repository,simulator,runnable,ref}.",
        "n_models": "Runnable models tagged to the organ.",
        "per_simulator": "Count of models per simulator.",
        "summary": "organ + counts.",
    },
    "assumptions": ["PhysioNet entries are dataset references, not runnable ODE "
                    "models, so they are excluded from the manifest."],
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=$PWD /Users/eranagmon/code/viva-human-atlas/.venv/bin/python -m pytest tests/test_organ_select.py -v`
Expected: PASS. If the kidney counts differ from 5/19 (the DB may have shifted), update the asserted numbers to the actual `select_organ_models("kidney")` split and note it — the split-by-simulator structure is the invariant, not the exact counts.

- [ ] **Step 5: Commit**

```bash
git add viva_human_atlas/organ_simulation.py tests/test_organ_select.py
git commit -m "feat: select_organ_models + OrganModelSelectStep (organ -> simulator routing)"
```

---

### Task 2: `resolve_cellml_url` (Physiome → CellML)

**Files:**
- Modify: `viva_human_atlas/physiome.py` (append the resolver)
- Test: `tests/test_resolve_cellml.py`, `tests/fixtures/pmr_exposure_22e.html`

**Interfaces:**
- Produces: `resolve_cellml_url(identifier: str, *, _get=requests.get) -> str | None` — GET the exposure page, find the first `.cellml` href, absolutize, strip a trailing `/view`. `None` on HTTP error or no link. The `_get` seam lets tests inject a fake response (offline).

- [ ] **Step 1: Save an offline HTML fixture**

Create `tests/fixtures/pmr_exposure_22e.html` containing (minimal, the real page's relevant markup):
```html
<html><body>
<a href="https://models.physiomeproject.org/e/22e/Eskandari_et_al_2005.cellml/view">Eskandari_et_al_2005.cellml</a>
</body></html>
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_resolve_cellml.py
from pathlib import Path
from viva_human_atlas.physiome import resolve_cellml_url

class _Resp:
    def __init__(self, text, url, status=200):
        self.text = text; self.url = url; self.status_code = status
    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"{self.status_code} error")

def test_resolve_cellml_url_from_fixture():
    html = Path("tests/fixtures/pmr_exposure_22e.html").read_text()
    url = resolve_cellml_url("https://models.physiomeproject.org/e/22e",
                             _get=lambda u, **k: _Resp(html, "https://models.physiomeproject.org/e/22e"))
    assert url == "https://models.physiomeproject.org/e/22e/Eskandari_et_al_2005.cellml"  # /view stripped

def test_resolve_cellml_url_no_link_returns_none():
    url = resolve_cellml_url("https://models.physiomeproject.org/e/zzz",
                             _get=lambda u, **k: _Resp("<html>no models here</html>", "x"))
    assert url is None
```

- [ ] **Step 3: Run test to verify it fails**

Run: `PYTHONPATH=$PWD /Users/eranagmon/code/viva-human-atlas/.venv/bin/python -m pytest tests/test_resolve_cellml.py -v`
Expected: FAIL (`resolve_cellml_url` missing).

- [ ] **Step 4: Write minimal implementation**

Append to `viva_human_atlas/physiome.py` (it already imports `re`, `requests`; add `from urllib.parse import urljoin` at top):

```python
def resolve_cellml_url(identifier: str, *, _get=requests.get) -> "str | None":
    """Resolve a PMR exposure (identifier URL like .../e/<id>) to its primary
    runnable .cellml URL. Returns None on HTTP error or no .cellml link.

    Spike-validated: the exposure page links `<file>.cellml/view`; strip /view
    and OpenCOR fetches it directly. (Multi-file/import CellML that fails to
    load is the caller's marked failure — a workspace-archive fetch is a
    follow-up.)"""
    try:
        r = _get(identifier, timeout=25)
        r.raise_for_status()
    except Exception:
        return None
    m = re.findall(r'href="([^"]+\.cellml)(?:/view)?"', r.text)
    if not m:
        return None
    url = urljoin(getattr(r, "url", identifier), m[0])
    return url[:-5] if url.endswith("/view") else url
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `PYTHONPATH=$PWD /Users/eranagmon/code/viva-human-atlas/.venv/bin/python -m pytest tests/test_resolve_cellml.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add viva_human_atlas/physiome.py tests/test_resolve_cellml.py tests/fixtures/pmr_exposure_22e.html
git commit -m "feat: resolve_cellml_url — PMR exposure -> runnable CellML URL"
```

---

### Task 3: `normalize_result`

**Files:**
- Modify: `viva_human_atlas/organ_simulation.py` (add `normalize_result`)
- Test: `tests/test_normalize_result.py`

**Interfaces:**
- Produces: `normalize_result(simulator: str, raw: dict) -> dict` → `{"time": list, "series": {name: list}}`. SBML (`raw={time,columns,values}`): `series[col_j] = [row[j] for row in values]`. OpenCOR (`raw={time,state,...}`): `series = dict(state)` (component/var → list), plus any non-empty `variables`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_normalize_result.py
from viva_human_atlas.organ_simulation import normalize_result

def test_normalize_sbml():
    raw = {"time": [0.0, 1.0], "columns": ["A", "B"], "values": [[1.0, 2.0], [3.0, 4.0]]}
    n = normalize_result("copasi", raw)
    assert n["time"] == [0.0, 1.0]
    assert n["series"] == {"A": [1.0, 3.0], "B": [2.0, 4.0]}

def test_normalize_opencor():
    raw = {"time": [0.0, 1.0], "state": {"m/x": [1.0, 0.5]}, "variables": {}, "rates": {}, "constants": {}}
    n = normalize_result("opencor", raw)
    assert n["time"] == [0.0, 1.0]
    assert n["series"] == {"m/x": [1.0, 0.5]}
```

- [ ] **Step 2: Run to verify fail** — `pytest tests/test_normalize_result.py -v` → FAIL.

- [ ] **Step 3: Implement** (append to `organ_simulation.py`):

```python
def normalize_result(simulator: str, raw: dict) -> dict:
    """Collapse a simulator result into {"time": [...], "series": {name: [...]}}."""
    time = list(raw.get("time") or [])
    if simulator == "opencor":
        series = {k: list(v) for k, v in (raw.get("state") or {}).items()}
        for k, v in (raw.get("variables") or {}).items():
            if v:
                series[k] = list(v)
        return {"time": time, "series": series}
    # SBML engines: {time, columns, values} (row-per-timepoint)
    cols = list(raw.get("columns") or [])
    vals = raw.get("values") or []
    series = {c: [row[j] for row in vals] for j, c in enumerate(cols)}
    return {"time": time, "series": series}
```

- [ ] **Step 4: Run to verify pass.** **Step 5: Commit** (`tests/test_normalize_result.py`, `organ_simulation.py`): `feat: normalize_result unifies SBML + OpenCOR timeseries shapes`.

---

### Task 4: `run_organ_simulation` runner

**Files:**
- Modify: `viva_human_atlas/organ_simulation.py`
- Test: `tests/test_run_organ_simulation.py`

**Interfaces:**
- Consumes: `select_organ_models`, `normalize_result`, `resolve_cellml_url`, `run_comparison` (viva_biomodels), `OpenCORUTCStep` (viva_opencor).
- Produces: `run_organ_simulation(organ, *, end_time=10.0, number_of_steps=100, db_path=_DEFAULT_DB) -> dict` → `{"organ", "models": [{"key","name","simulator","status","time","series","error"}], "summary": {"n_models","n_ran","n_failed","by_simulator"}}`. `status ∈ {"ran","failed"}`. Split into module-level `_run_sbml(models, ...)` and `_run_cellml(models, end_time, number_of_steps)` so tests can monkeypatch them.

- [ ] **Step 1: Write the failing test** (offline — monkeypatch both engine calls):

```python
# tests/test_run_organ_simulation.py
import viva_human_atlas.organ_simulation as osim

def test_run_organ_simulation_assembles_ran_and_failed(monkeypatch):
    fake_models = [
        {"key": "B1", "name": "sbml one", "repository": "biomodels", "simulator": "copasi", "runnable": True, "ref": "BIOMD1"},
        {"key": "P1", "name": "cellml one", "repository": "physiome", "simulator": "opencor", "runnable": True, "ref": "https://x/e/1"},
        {"key": "P2", "name": "cellml bad", "repository": "physiome", "simulator": "opencor", "runnable": True, "ref": "https://x/e/2"},
    ]
    monkeypatch.setattr(osim, "select_organ_models", lambda organ, db_path=None: fake_models)
    # SBML: one ran
    monkeypatch.setattr(osim, "_run_sbml", lambda models, **k: {
        "B1": {"status": "ran", "raw": {"time": [0, 1], "columns": ["A"], "values": [[1.0], [2.0]]}, "error": None}})
    # CellML: P1 ran, P2 failed
    def fake_cellml(models, **k):
        return {"P1": {"status": "ran", "raw": {"time": [0, 1], "state": {"m/x": [1.0, 0.5]}}, "error": None},
                "P2": {"status": "failed", "raw": None, "error": "libOpenCOR could not load model"}}
    monkeypatch.setattr(osim, "_run_cellml", fake_cellml)

    res = osim.run_organ_simulation("kidney")
    assert res["summary"] == {"n_models": 3, "n_ran": 2, "n_failed": 1, "by_simulator": {"copasi": 1, "opencor": 2}}
    by_key = {m["key"]: m for m in res["models"]}
    assert by_key["B1"]["status"] == "ran" and by_key["B1"]["series"] == {"A": [1.0, 2.0]}
    assert by_key["P1"]["series"] == {"m/x": [1.0, 0.5]}
    assert by_key["P2"]["status"] == "failed" and "libOpenCOR" in by_key["P2"]["error"]
```

- [ ] **Step 2: Run to verify fail.**

- [ ] **Step 3: Implement** (append to `organ_simulation.py`):

```python
def _run_sbml(models, *, references=None):
    """{key: {status, raw(numeric_result)|None, error}} via viva_biomodels."""
    from viva_biomodels.composites.compare_simulators import run_comparison
    ids = [m["ref"] for m in models]
    rep = run_comparison(ids, simulators=["copasi"], references=references) if ids else {}
    out = {}
    for m in models:
        r = rep.get(m["ref"]) or {}
        raw = (r.get("engines") or {}).get("copasi") or {}
        if r.get("error") or not raw.get("time"):
            out[m["key"]] = {"status": "failed", "raw": None, "error": r.get("error") or "no timeseries produced"}
        else:
            out[m["key"]] = {"status": "ran", "raw": raw, "error": None}
    return out


def _run_cellml(models, *, end_time=10.0, number_of_steps=100):
    """{key: {status, raw(opencor result)|None, error}} via OpenCOR."""
    out = {}
    try:
        from process_bigraph import allocate_core
        from viva_opencor.processes import OpenCORUTCStep
    except Exception as exc:  # noqa: BLE001 — engine not installed
        return {m["key"]: {"status": "failed", "raw": None,
                           "error": f"OpenCOR unavailable: {exc}"} for m in models}
    core = allocate_core(); core.register_link("OpenCORUTCStep", OpenCORUTCStep)
    for m in models:
        try:
            url = resolve_cellml_url(m["ref"])
            if not url:
                out[m["key"]] = {"status": "failed", "raw": None, "error": "no .cellml resolved for exposure"}
                continue
            step = OpenCORUTCStep(config={"model_source": url, "end_time": end_time,
                                          "number_of_steps": number_of_steps}, core=core)
            out[m["key"]] = {"status": "ran", "raw": step.update({})["result"], "error": None}
        except Exception as exc:  # noqa: BLE001 — one model never sinks the batch
            out[m["key"]] = {"status": "failed", "raw": None, "error": str(exc)}
    return out


def run_organ_simulation(organ, *, end_time=10.0, number_of_steps=100, db_path=_DEFAULT_DB) -> dict:
    models = select_organ_models(organ, db_path)
    sbml = [m for m in models if m["simulator"] == "copasi"]
    cellml = [m for m in models if m["simulator"] == "opencor"]
    ran_sbml = _run_sbml(sbml)
    ran_cellml = _run_cellml(cellml, end_time=end_time, number_of_steps=number_of_steps)
    raw_by_key = {**ran_sbml, **ran_cellml}
    out_models, n_ran, n_failed, by_sim = [], 0, 0, {}
    for m in models:
        by_sim[m["simulator"]] = by_sim.get(m["simulator"], 0) + 1
        r = raw_by_key.get(m["key"]) or {"status": "failed", "raw": None, "error": "not run"}
        rec = {"key": m["key"], "name": m["name"], "simulator": m["simulator"],
               "status": r["status"], "error": r.get("error")}
        if r["status"] == "ran":
            norm = normalize_result(m["simulator"], r["raw"])
            rec["time"] = norm["time"]; rec["series"] = norm["series"]; n_ran += 1
        else:
            rec["time"] = []; rec["series"] = {}; n_failed += 1
        out_models.append(rec)
    return {"organ": organ, "models": out_models,
            "summary": {"n_models": len(models), "n_ran": n_ran,
                        "n_failed": n_failed, "by_simulator": by_sim}}
```

- [ ] **Step 4: Run to verify pass.** **Step 5: Commit**: `feat: run_organ_simulation orchestrates SBML+CellML runs with honest failures`.

---

### Task 5: `organ_dashboard_html`

**Files:**
- Modify: `viva_human_atlas/viz.py`
- Test: `tests/test_organ_dashboard.py`

**Interfaces:**
- Produces: `organ_dashboard_html(result: dict, *, max_series: int = 8) -> str` — a self-contained HTML page: Plotly CDN loaded once in `<head>`; a header line with the organ + `n_ran`/`n_failed`/by-simulator; a grid of `<details>` cards, one per model (name, simulator badge, ✓/✗ status badge). A `ran` card embeds `go.Figure(...).to_html(include_plotlyjs=False, full_html=False)` with one trace per series (capped at `max_series`), x=time. A `failed` card shows the error text.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_organ_dashboard.py
from viva_human_atlas.viz import organ_dashboard_html

def test_dashboard_renders_ran_and_failed():
    result = {"organ": "kidney",
        "models": [
            {"key": "B1", "name": "ran model", "simulator": "copasi", "status": "ran",
             "time": [0, 1, 2], "series": {"A": [1, 2, 3]}, "error": None},
            {"key": "P2", "name": "failed model", "simulator": "opencor", "status": "failed",
             "time": [], "series": {}, "error": "libOpenCOR could not load model"}],
        "summary": {"n_models": 2, "n_ran": 1, "n_failed": 1, "by_simulator": {"copasi": 1, "opencor": 1}}}
    html = organ_dashboard_html(result)
    assert "<html" in html.lower() and "plotly" in html.lower()
    assert "ran model" in html and "failed model" in html
    assert "libOpenCOR could not load model" in html      # failure reason shown
    assert "Plotly.newPlot" in html or "plotly-graph-div" in html  # a real plot embedded
```

- [ ] **Step 2: Run to verify fail.**

- [ ] **Step 3: Implement** (append to `viz.py`; `go` is already imported). Load Plotly once via `go.Figure().to_html(include_plotlyjs="cdn", full_html=False)` is wrong for a shared page — instead put `<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>` in `<head>` and render each figure with `include_plotlyjs=False`. Build the page as an HTML string:

```python
def organ_dashboard_html(result: dict, *, max_series: int = 8) -> str:
    s = result.get("summary", {})
    cards = []
    for m in result.get("models", []):
        badge = "✓ ran" if m["status"] == "ran" else "✗ failed"
        color = "#1a7f37" if m["status"] == "ran" else "#b42318"
        head = (f'<summary><b>{m["name"] or m["key"]}</b> '
                f'<span style="opacity:.7">[{m["simulator"]}]</span> '
                f'<span style="color:{color}">{badge}</span></summary>')
        if m["status"] == "ran" and m.get("series"):
            fig = go.Figure()
            for name, ys in list(m["series"].items())[:max_series]:
                fig.add_trace(go.Scatter(x=m["time"], y=ys, mode="lines", name=name))
            fig.update_layout(margin=dict(l=40, r=10, t=10, b=30), height=320,
                              xaxis_title="time", template="plotly_white")
            body = fig.to_html(include_plotlyjs=False, full_html=False)
        else:
            body = f'<p style="color:{color}">{m.get("error") or "did not run"}</p>'
        cards.append(f'<details style="border:1px solid #ddd;border-radius:8px;'
                     f'margin:8px 0;padding:8px">{head}{body}</details>')
    header = (f'<h1>{result.get("organ","organ").title()} — model simulations</h1>'
              f'<p>{s.get("n_ran",0)}/{s.get("n_models",0)} ran, '
              f'{s.get("n_failed",0)} failed · by simulator: {s.get("by_simulator",{})}</p>')
    return (f'<!doctype html><html><head><meta charset="utf-8">'
            f'<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>'
            f'<style>body{{font-family:system-ui;margin:24px;max-width:900px}}</style>'
            f'</head><body>{header}{"".join(cards)}</body></html>')
```

- [ ] **Step 4: Run to verify pass** (the test accepts either `Plotly.newPlot` or a `plotly-graph-div`; `include_plotlyjs=False` fragments contain a `plotly-graph-div`). **Step 5: Commit**: `feat: organ_dashboard_html — interactive grid of per-model timeseries`.

---

### Task 6: `OrganSimulationStep`

**Files:**
- Modify: `viva_human_atlas/organ_simulation.py`
- Test: `tests/test_organ_simulation_step.py`

**Interfaces:**
- Consumes: `run_organ_simulation`, `viva_human_atlas.viz.organ_dashboard_html`.
- Produces: `OrganSimulationStep(Step)` — config `{organ, end_time, number_of_steps, db_path, out_dir}`; `inputs()={}`; `outputs()={"summary":"tree","dashboard_path":"string","results_path":"string"}`. `update()` runs the pipeline, writes `<out_dir>/index.html` (dashboard) and `<out_dir>/results.json` (the tidy result), emits the summary + paths. Default `out_dir = studies/kidney-model-simulation/viz`.

- [ ] **Step 1: Write the failing test** (offline — monkeypatch `run_organ_simulation`):

```python
# tests/test_organ_simulation_step.py
import json
import viva_human_atlas.organ_simulation as osim
from viva_human_atlas.organ_simulation import OrganSimulationStep
from viva_human_atlas.core import build_core

_FAKE = {"organ": "kidney",
    "models": [{"key": "B1", "name": "m", "simulator": "copasi", "status": "ran",
                "time": [0, 1], "series": {"A": [1, 2]}, "error": None}],
    "summary": {"n_models": 1, "n_ran": 1, "n_failed": 0, "by_simulator": {"copasi": 1}}}

def test_step_registered():
    core = build_core()
    assert core.link_registry.get("viva_human_atlas.organ_simulation.OrganSimulationStep") is OrganSimulationStep

def test_step_writes_dashboard_and_results(monkeypatch, tmp_path):
    monkeypatch.setattr(osim, "run_organ_simulation", lambda organ, **k: _FAKE)
    step = OrganSimulationStep({"organ": "kidney", "out_dir": str(tmp_path)}, core=build_core())
    out = step.update({})
    assert out["summary"]["n_ran"] == 1
    assert (tmp_path / "index.html").exists() and (tmp_path / "results.json").exists()
    assert json.loads((tmp_path / "results.json").read_text())["summary"]["n_ran"] == 1
    assert "<html" in (tmp_path / "index.html").read_text().lower()
```

- [ ] **Step 2: Run to verify fail.**

- [ ] **Step 3: Implement** (append to `organ_simulation.py`):

```python
_DEFAULT_OUT = str(_REPO / "studies" / "kidney-model-simulation" / "viz")


class OrganSimulationStep(Step):
    """Step: run every runnable model for an organ in its compatible simulator
    and write an interactive dashboard + tidy results JSON."""

    description = ("Run all of an organ's atlas-mapped models (SBML->COPASI, "
                   "CellML->OpenCOR), collect timeseries, and write an "
                   "interactive dashboard. Live run: native simulators + "
                   "network fetches. Failing models are shown, not dropped.")

    config_schema = {"organ": "string", "end_time": "float",
                     "number_of_steps": "integer", "db_path": "string", "out_dir": "string"}

    def inputs(self):
        return {}

    def outputs(self):
        return {"summary": "tree", "dashboard_path": "string", "results_path": "string"}

    def update(self, inputs):
        from viva_human_atlas.viz import organ_dashboard_html
        organ = self.config.get("organ") or "kidney"
        result = run_organ_simulation(
            organ,
            end_time=float(self.config.get("end_time") or 10.0),
            number_of_steps=int(self.config.get("number_of_steps") or 100),
            db_path=self.config.get("db_path") or _DEFAULT_DB,
        )
        out_dir = Path(self.config.get("out_dir") or _DEFAULT_OUT)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        (out_dir / "index.html").write_text(organ_dashboard_html(result), encoding="utf-8")
        return {"summary": result["summary"],
                "dashboard_path": str(out_dir / "index.html"),
                "results_path": str(out_dir / "results.json")}


OrganSimulationStep.contract = {
    "summary": OrganSimulationStep.description,
    "outputs": {"summary": "n_models/n_ran/n_failed/by_simulator.",
                "dashboard_path": "Path to the written interactive dashboard HTML.",
                "results_path": "Path to the tidy results JSON."},
    "assumptions": ["A live run study: COPASI + libOpenCOR native engines and "
                    "PMR/BioModels network fetches. Re-runs may differ with "
                    "upstream changes; failing models are marked, not dropped."],
}
```

- [ ] **Step 4: Run to verify pass.** **Step 5: Commit**: `feat: OrganSimulationStep runs the organ pipeline + writes the dashboard`.

---

### Task 7: `kidney-model-simulation` study

**Files:**
- Create: `studies/kidney-model-simulation/study.yaml`
- Test: `tests/test_kidney_sim_study.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_kidney_sim_study.py
import yaml
from pathlib import Path

def test_kidney_sim_study():
    s = yaml.safe_load(Path("studies/kidney-model-simulation/study.yaml").read_text())
    assert s["schema_version"] == 4
    assert s["investigation"] == "hra-3d"
    assert s["baseline"][0]["step"] == "local:viva_human_atlas.organ_simulation.OrganSimulationStep"
    assert s["baseline"][0]["params"]["organ"] == "kidney"
```

- [ ] **Step 2: Run to verify fail.**

- [ ] **Step 3: Author `studies/kidney-model-simulation/study.yaml`** — schema_version 4, investigation `hra-3d`, a `question`/`study_card` describing the organ→run→dashboard flow and the honest yield (spike: ~9/19 Physiome + up-to-5 BioModels for kidney), `baseline` list with `step: local:viva_human_atlas.organ_simulation.OrganSimulationStep`, `params: {organ: kidney}`, a `report` block flagging it as a live run study, `embed_visualizations` pointing at `/studies/kidney-model-simulation/viz/index.html`, and `limitations` (single-file CellML resolver; run-study non-determinism). Follow the field shape of `studies/hra-atlas-browser/study.yaml`. The controller will provide the drafted YAML.

- [ ] **Step 4: Run to verify pass** + `python -c "import yaml; yaml.safe_load(open('studies/kidney-model-simulation/study.yaml'))"`. **Step 5: Commit**: `docs: kidney-model-simulation study`.

---

### Task 8: Full offline suite + live smoke (opt-in)

- [ ] **Step 1: Run the full suite offline**

Run: `PYTHONPATH=$PWD /Users/eranagmon/code/viva-human-atlas/.venv/bin/python -m pytest tests/ -q -m "not network"`
Expected: all new tests pass; pre-existing failures (`test_atlas_pack.py::test_every_organ_has_a_known_system`, `test_atlas_viewer_assets.py`, `test_workbench_atlas_viewer.py`) are unrelated and out of scope — confirm no NEW failures.

- [ ] **Step 2: (Opt-in) live smoke**

Run the network smoke to confirm the real pipeline end-to-end (not required for merge):
`PYTHONPATH=$PWD /Users/eranagmon/code/viva-human-atlas/.venv/bin/python -c "from viva_human_atlas.organ_simulation import run_organ_simulation; r=run_organ_simulation('kidney', end_time=5.0, number_of_steps=20); print(r['summary'])"`
Expected: `n_ran >= 1` with both simulators represented. Record the summary in the commit message if run.

- [ ] **Step 3: Commit any final adjustments.**

---

## Self-Review

**Spec coverage:** selection (Task 1) · resolver (Task 2) · normalize (Task 3) · runner reusing run_comparison + OpenCOR (Task 4) · dashboard (Task 5) · orchestration Step (Task 6) · study (Task 7) · suite/smoke (Task 8). All spec §Design items map to a task.

**Placeholder scan:** Task 7's YAML body is prose ("controller will provide the drafted YAML") — the controller supplies concrete content at dispatch (same pattern as the atlas-pipeline plan); the load-bearing schema assertions are concrete. Task 1's counts (5/19/24) may shift with the DB — the task says update to the actual split if so, keeping the structure invariant.

**Type consistency:** `select_organ_models` record keys (`key,name,repository,simulator,runnable,ref`) are consumed unchanged in Task 4; `normalize_result` output `{time,series}` (Task 3) is what Task 4 embeds and Task 5 reads; `run_organ_simulation` result shape (Task 4) is exactly what Task 5's `organ_dashboard_html` and Task 6's Step consume. `_run_sbml`/`_run_cellml` are module-level (monkeypatchable) as the Task 4 test requires.

**Runtime soft spots (confirm during implementation):** (a) exact kidney counts (Task 1); (b) `run_comparison` returning `engines["copasi"]` empty vs error for SED-ML-less models — Task 4 treats both as `failed`; (c) OpenCOR `result` key nesting under a possible wrapper — Task 4 reads `step.update({})["result"]`, matching the spike.
