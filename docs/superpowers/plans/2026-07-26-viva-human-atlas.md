# viva-human-atlas Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the `viva-human-atlas` workspace with a first investigation that queries BioModels for "glucose regulation" and compares each model on COPASI vs Tellurium.

**Architecture:** A viva workspace that *reuses* pbg-biomodels' existing fetch→multi-engine→all-pairs-comparison machinery (`build_compare_document` / `run_comparison`, which already support `simulators="copasi,tellurium"`). The only genuinely new code is a BioModels **search** (query → model IDs) plus one `@composite_generator` that chains search → compare, and the workspace/investigation/study scaffolding.

**Tech Stack:** Python 3.12, process-bigraph 1.5.0, pbg-biomodels / pbg-copasi / pbg-tellurium (editable path deps), pbg(viva)-superpowers `composite_generator`, `uv` for env, `pytest` for tests, `requests` for the BioModels REST search.

## Global Constraints

- **Python:** `requires-python = ">=3.12"`; pin `process-bigraph==1.5.0` (matches pbg-biomodels).
- **Not a distributable package:** `[tool.hatch.build.targets.wheel] bypass-selection = true` (research workspace, like pbg-biomodels).
- **Reuse, don't reimplement:** the COPASI-vs-Tellurium comparison comes from `pbg_biomodels.composites.compare_simulators` (`build_compare_document`, `run_comparison`) and `pbg_biomodels.simulators.resolve_simulators`. Do **not** write a new comparison step or a per-model dual-sim composite.
- **Superpowers import shim:** the installed package may be named `viva_superpowers` or `pbg_superpowers`. Always import via:
  ```python
  try:
      from viva_superpowers.composite_generator import composite_generator
  except ModuleNotFoundError:
      from pbg_superpowers.composite_generator import composite_generator
  ```
- **Package name:** dist-name `viva-human-atlas`, import package `viva_human_atlas`, workspace display name `human-atlas`.
- **No network in unit tests:** mock `requests.get` / the search function. Live end-to-end tests are marked `@pytest.mark.network` and skipped by default.
- **Commit** after each task with the shown message.

---

### Task 1: Workspace scaffold + env + `build_core`

Stand up the installable workspace so `import viva_human_atlas` and `build_core()` work and pbg-biomodels' functions are reachable.

**Files:**
- Create: `pyproject.toml`
- Create: `workspace.yaml`
- Create: `viva_human_atlas/__init__.py`
- Create: `viva_human_atlas/core.py`
- Create: `viva_human_atlas/composites/__init__.py`
- Test: `tests/test_scaffold.py`

**Interfaces:**
- Produces: `viva_human_atlas.core.build_core() -> core` (a fully-configured process-bigraph core with copasi/tellurium/biomodels types + the workspace's local Edges registered). `viva_human_atlas.register_types(core) -> core`.

- [ ] **Step 1: Write `pyproject.toml`.** Model it on `../pbg-biomodels/pyproject.toml`. Before writing, read `../pbg-biomodels/pyproject.toml` and `../pbg-superpowers/pyproject.toml` to copy the **exact** dist-names for the editable path sources. Use:

```toml
[project]
name = "viva-human-atlas"
version = "0.0.0"
description = "HRA / Whole Person Physiome modeling workspace (process-bigraph)"
requires-python = ">=3.12"
dependencies = [
    "process-bigraph==1.5.0",
    "bigraph-schema",
    "requests>=2.31",
    "pyyaml>=6.0",
    # Reused comparison machinery + transitively copasi/tellurium/simbio/biomodels/superpowers/workbench:
    "pbg-biomodels",
    # Direct engine deps (also pulled by pbg-biomodels, listed for clarity):
    "pbg-copasi",
    "pbg-tellurium",
]

[project.optional-dependencies]
dev = ["pytest>=7.4"]

[tool.uv.sources]
pbg-biomodels = { path = "../pbg-biomodels", editable = true }
pbg-copasi = { path = "../pbg-copasi", editable = true }
pbg-tellurium = { path = "../pbg-tellurium", editable = true }

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
bypass-selection = true
```

- [ ] **Step 2: Write `workspace.yaml`.** Model on `../pbg-biomodels/workspace.yaml` header + a small imports block:

```yaml
schema_version: 2
name: human-atlas
created: '2026-07-26'
package_path: viva_human_atlas
observables: []
visualizations: []
simulations: []
datasets: []
references_bib: references/papers.bib
imports:
  pbg-biomodels:
    source: https://github.com/vivarium-collective/pbg-biomodels.git
    ref: main
    mode: reference
    path: ../pbg-biomodels
    package: pbg_biomodels
    description: BioModels fetch + SED-ML parse + multi-simulator comparison
  pbg-copasi:
    source: https://github.com/vivarium-collective/pbg-copasi.git
    ref: main
    mode: reference
    path: ../pbg-copasi
    package: pbg_copasi
    description: COPASI-backed UTC Step
  pbg-tellurium:
    source: https://github.com/vivarium-collective/pbg-tellurium.git
    ref: main
    mode: reference
    path: ../pbg-tellurium
    package: pbg_tellurium
    description: Tellurium / libroadrunner UTC Step
server:
  enabled: false
```

- [ ] **Step 3: Write `viva_human_atlas/composites/__init__.py`** — fires generator decorators on import:

```python
"""Importing this package registers viva-human-atlas @composite_generator entries."""
from viva_human_atlas.composites import glucose_regulation  # noqa: F401
```

(The `glucose_regulation` module is created in Task 3. Until then, temporarily leave the import body as `pass` so Task 1 is testable; Task 3 restores the real import.)

- [ ] **Step 4: Write `viva_human_atlas/core.py`.** Mirror `../pbg-biomodels/pbg_biomodels/core.py`'s walk-and-register pattern, then layer biomodels' types/backends on top:

```python
"""build_core() for viva-human-atlas.

Registers the workspace-local Steps (walking the viva_human_atlas package the
same way pbg-biomodels does) plus everything pbg-biomodels' build_core sets up
(simulator Process backends + biomodels types), since we reuse its composites.
"""
from __future__ import annotations

import importlib
import inspect
import pkgutil
from typing import Iterable

from process_bigraph import Process, Step, allocate_core

import viva_human_atlas


def _iter_workspace_edges(package) -> Iterable[tuple[type, str]]:
    pkg_name = package.__name__
    seen: set[type] = set()
    for _, modname, _ in pkgutil.walk_packages(package.__path__, prefix=f"{pkg_name}."):
        try:
            mod = importlib.import_module(modname)
        except Exception as exc:  # pragma: no cover
            import warnings
            warnings.warn(f"build_core: skipping {modname}: {type(exc).__name__}: {exc}")
            continue
        for _, cls in inspect.getmembers(mod, inspect.isclass):
            if cls in (Step, Process):
                continue
            if not issubclass(cls, (Step, Process)):
                continue
            if not (cls.__module__ or "").startswith(pkg_name + "."):
                continue
            if cls in seen:
                continue
            seen.add(cls)
            yield cls, f"{cls.__module__}.{cls.__name__}"


def build_core():
    core = allocate_core()
    # Register pbg-biomodels' simulator backends + types (reused by our composites).
    from pbg_biomodels.simulators import register_simulator_backends
    from pbg_biomodels import register_types as register_biomodels_types
    register_simulator_backends(core)
    register_biomodels_types(core)
    # Register this workspace's local Steps by dotted path and short name.
    for cls, dotted in _iter_workspace_edges(viva_human_atlas):
        core.register_link(dotted, cls)
        core.register_link(cls.__name__, cls)
    return core
```

- [ ] **Step 5: Write `viva_human_atlas/__init__.py`:**

```python
"""viva_human_atlas — HRA / Whole Person Physiome modeling workspace.

Importing the package fires the @composite_generator decorators in composites/
so discover_generators() finds them.
"""
from viva_human_atlas import composites  # noqa: F401


def register_types(core):
    """Register the types this workspace needs (delegates to pbg-biomodels)."""
    from pbg_biomodels import register_types as _reg
    return _reg(core)


__all__ = ["register_types"]
```

- [ ] **Step 6: Create the env and install.** Run:

```bash
cd ~/code/viva-human-atlas
uv venv
uv pip install -e .
```

Expected: resolves and installs, exposing `pbg_biomodels`, `pbg_copasi`, `pbg_tellurium` (editable). If `pbg_biomodels` fails to import after this (bypass-selection edge case), confirm `../pbg-biomodels` is editable-installed (`uv pip install -e ../pbg-biomodels`) — its own `_editable_impl_pbg_biomodels.pth` is what makes it importable.

- [ ] **Step 7: Write the failing test** `tests/test_scaffold.py`:

```python
def test_build_core_and_imports():
    import pbg_biomodels  # reused machinery must be importable
    import pbg_copasi, pbg_tellurium  # noqa: F401
    from viva_human_atlas.core import build_core
    core = build_core()
    assert core is not None
    # copasi + tellurium are known simulators in the reused registry
    from pbg_biomodels.simulators import resolve_simulators
    sims = resolve_simulators("copasi,tellurium")
    assert sims == ["copasi", "tellurium"]
```

- [ ] **Step 8: Run it, expect FAIL** (module/import errors) before the env+files are right:

```bash
cd ~/code/viva-human-atlas && .venv/bin/python -m pytest tests/test_scaffold.py -v
```

- [ ] **Step 9: Fix any wiring until it PASSES.** Re-run the same command; expect PASS.

- [ ] **Step 10: Commit:**

```bash
git add pyproject.toml workspace.yaml viva_human_atlas tests/test_scaffold.py
git commit -m "feat: viva-human-atlas workspace scaffold + build_core reusing pbg-biomodels"
```

---

### Task 2: BioModels search (`search_biomodels` + `BioModelsSearchStep`)

The `biomodels` PyPI package is by-ID only. Add a REST-search helper that turns a text query into model IDs, plus a process-bigraph Step wrapper.

**Files:**
- Create: `viva_human_atlas/biomodels_search.py`
- Test: `tests/test_biomodels_search.py`

**Interfaces:**
- Produces:
  - `search_biomodels(query: str, max_results: int = 25, *, _get=None) -> list[str]` — returns BioModels IDs (e.g. `["BIOMD0000000372", ...]`). `_get` is an injectable `requests.get`-compatible callable for tests.
  - `class BioModelsSearchStep(Step)` with `config_schema = {'query': 'string', 'max_results': 'integer'}`, `inputs() -> {}`, `outputs() -> {'model_ids': 'list[string]'}`, and `update()` returning `{'model_ids': search_biomodels(...)}`.

- [ ] **Step 1: Write the failing test** `tests/test_biomodels_search.py`:

```python
import json
from viva_human_atlas.biomodels_search import search_biomodels


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload
    def raise_for_status(self):
        pass
    def json(self):
        return self._payload


def test_search_biomodels_parses_ids_and_respects_max_results():
    payload = {"models": [
        {"id": "BIOMD0000000372", "name": "Topp2000 - beta-cell glucose"},
        {"id": "BIOMD0000000340", "name": "some glucose model"},
        {"id": "BIOMD0000000205", "name": "another"},
    ]}
    calls = {}
    def fake_get(url, params=None, timeout=None):
        calls["url"] = url
        calls["params"] = params
        return _FakeResp(payload)

    ids = search_biomodels("glucose regulation", max_results=2, _get=fake_get)

    assert ids == ["BIOMD0000000372", "BIOMD0000000340"]
    assert "biomodels/search" in calls["url"]
    assert calls["params"]["query"] == "glucose regulation"
    assert calls["params"]["format"] == "json"


def test_search_biomodels_empty_models_key():
    ids = search_biomodels("nope", _get=lambda *a, **k: _FakeResp({}))
    assert ids == []
```

- [ ] **Step 2: Run it, expect FAIL** ("No module named ... biomodels_search"):

```bash
cd ~/code/viva-human-atlas && .venv/bin/python -m pytest tests/test_biomodels_search.py -v
```

- [ ] **Step 3: Write the implementation** `viva_human_atlas/biomodels_search.py`:

```python
"""Query the BioModels REST search endpoint for model IDs.

The `biomodels` PyPI client only fetches by ID; this module adds text search
(https://www.ebi.ac.uk/biomodels/search?query=...&format=json) so an
investigation can ask for e.g. all "glucose regulation" models.
"""
from __future__ import annotations

from typing import Callable, List, Optional

from process_bigraph import Step

_SEARCH_URL = "https://www.ebi.ac.uk/biomodels/search"


def search_biomodels(
    query: str,
    max_results: int = 25,
    *,
    _get: Optional[Callable] = None,
) -> List[str]:
    """Return up to `max_results` BioModels IDs matching `query`.

    `_get` is an injectable requests.get-compatible callable (for tests);
    defaults to the real requests.get.
    """
    if _get is None:
        import requests
        _get = requests.get
    resp = _get(
        _SEARCH_URL,
        params={"query": query, "format": "json", "numResults": int(max_results)},
        timeout=30,
    )
    resp.raise_for_status()
    models = resp.json().get("models") or []
    ids = [m["id"] for m in models if m.get("id")]
    return ids[:max_results]


class BioModelsSearchStep(Step):
    """Step: text query -> list of BioModels IDs."""

    config_schema = {
        "query": "string",
        "max_results": "integer",
    }

    def inputs(self):
        return {}

    def outputs(self):
        return {"model_ids": "list[string]"}

    def update(self, inputs):
        ids = search_biomodels(
            self.config.get("query", "glucose regulation"),
            int(self.config.get("max_results", 25)),
        )
        return {"model_ids": ids}
```

- [ ] **Step 4: Run it, expect PASS:**

```bash
cd ~/code/viva-human-atlas && .venv/bin/python -m pytest tests/test_biomodels_search.py -v
```

- [ ] **Step 5: Commit:**

```bash
git add viva_human_atlas/biomodels_search.py tests/test_biomodels_search.py
git commit -m "feat: BioModels REST text search (search_biomodels + BioModelsSearchStep)"
```

---

### Task 3: `glucose-regulation` composite generator + runner

One generator that resolves IDs via search then delegates to pbg-biomodels' compare machinery, plus a runner helper for the study.

**Files:**
- Create: `viva_human_atlas/composites/glucose_regulation.py`
- Modify: `viva_human_atlas/composites/__init__.py` (restore the real import from Task 1 Step 3)
- Test: `tests/test_glucose_regulation.py`

**Interfaces:**
- Consumes: `search_biomodels` (Task 2); `pbg_biomodels.composites.compare_simulators.build_compare_document(biomodel_ids, simulators=...)` and `.run_comparison(biomodel_ids, simulators=..., on_progress=None)`.
- Produces:
  - `@composite_generator(name="glucose-regulation", ...)` → `build_glucose_regulation(core=None, *, query, max_results, simulators) -> dict` (a compare-document `{"state", "run_steps_on_init": True}`).
  - `run_glucose_regulation(query="glucose regulation", max_results=25, simulators="copasi,tellurium", *, on_progress=None) -> dict` (the `{biomodel_id: {engines, comparison, error}}` report structure).

- [ ] **Step 1: Write the failing test** `tests/test_glucose_regulation.py` (mock search so no network; assert delegation shape):

```python
import viva_human_atlas.composites.glucose_regulation as gr


def test_build_glucose_regulation_delegates_to_compare(monkeypatch):
    monkeypatch.setattr(gr, "search_biomodels",
                        lambda q, n, **k: ["BIOMD0000000372", "BIOMD0000000340"])
    captured = {}
    def fake_build(ids, simulators=None):
        captured["ids"] = ids
        captured["simulators"] = simulators
        return {"state": {"marker": True}, "run_steps_on_init": True}
    monkeypatch.setattr(gr, "build_compare_document", fake_build)

    doc = gr.build_glucose_regulation(
        query="glucose regulation", max_results=2, simulators="copasi,tellurium")

    assert doc["state"]["marker"] is True
    assert captured["ids"] == ["BIOMD0000000372", "BIOMD0000000340"]
    assert captured["simulators"] == "copasi,tellurium"


def test_generator_is_discovered():
    try:
        from viva_superpowers.composite_generator import discover_generators
    except ModuleNotFoundError:
        from pbg_superpowers.composite_generator import discover_generators
    import viva_human_atlas  # noqa: F401  (fires decorators)
    names = {g.name for g in discover_generators()}
    assert "glucose-regulation" in names
```

- [ ] **Step 2: Run it, expect FAIL** ("No module named ... glucose_regulation"):

```bash
cd ~/code/viva-human-atlas && .venv/bin/python -m pytest tests/test_glucose_regulation.py -v
```

- [ ] **Step 3: Write** `viva_human_atlas/composites/glucose_regulation.py`:

```python
"""glucose-regulation composite: search BioModels, compare COPASI vs Tellurium.

Reuses pbg-biomodels' fetch->multi-engine->all-pairs-comparison machinery; the
only workspace-specific piece is turning a text query into the model-id list.
"""
from __future__ import annotations

from typing import Any, Dict

try:
    from viva_superpowers.composite_generator import composite_generator
except ModuleNotFoundError:
    from pbg_superpowers.composite_generator import composite_generator

from pbg_biomodels.composites.compare_simulators import (
    build_compare_document,
    run_comparison,
)

from viva_human_atlas.biomodels_search import search_biomodels


@composite_generator(
    name="glucose-regulation",
    description=(
        "Query BioModels for a text term (default 'glucose regulation'), then "
        "run every matching model under COPASI and Tellurium and score their "
        "agreement (all-pairs nRMSE)."
    ),
    parameters={
        "query": {
            "type": "string",
            "default": "glucose regulation",
            "description": "BioModels search term.",
        },
        "max_results": {
            "type": "integer",
            "default": 10,
            "description": "Max number of matching models to compare.",
        },
        "simulators": {
            "type": "string",
            "default": "copasi,tellurium",
            "description": "Comma-separated simulator names.",
        },
    },
    default_n_steps=1,
)
def build_glucose_regulation(
    core: Any = None,
    *,
    query: str = "glucose regulation",
    max_results: int = 10,
    simulators: str = "copasi,tellurium",
) -> Dict[str, Any]:
    ids = search_biomodels(query, max_results)
    return build_compare_document(ids, simulators=simulators)


def run_glucose_regulation(
    query: str = "glucose regulation",
    max_results: int = 25,
    simulators: str = "copasi,tellurium",
    *,
    on_progress=None,
) -> Dict[str, Any]:
    """Search then run the isolated per-model comparison; returns the report dict."""
    ids = search_biomodels(query, max_results)
    return run_comparison(ids, simulators=simulators, on_progress=on_progress)
```

- [ ] **Step 4: Restore the real import in** `viva_human_atlas/composites/__init__.py` (replace the temporary `pass` body from Task 1 Step 3 with):

```python
"""Importing this package registers viva-human-atlas @composite_generator entries."""
from viva_human_atlas.composites import glucose_regulation  # noqa: F401
```

- [ ] **Step 5: Run it, expect PASS:**

```bash
cd ~/code/viva-human-atlas && .venv/bin/python -m pytest tests/test_glucose_regulation.py -v
```

- [ ] **Step 6: Commit:**

```bash
git add viva_human_atlas/composites tests/test_glucose_regulation.py
git commit -m "feat: glucose-regulation generator + run_glucose_regulation (reuses compare-simulators)"
```

---

### Task 4: Investigation + study + live end-to-end smoke

Wire the investigation/study metadata and prove the whole path runs against real BioModels for one known glucose model.

**Files:**
- Create: `investigations/glucose-regulation/investigation.yaml`
- Create: `studies/glucose-regulation/study.yaml`
- Create: `references/papers.bib` (empty-but-valid placeholder: a single comment line)
- Test: `tests/test_end_to_end.py`

**Interfaces:**
- Consumes: `run_glucose_regulation` (Task 3); `search_biomodels` (Task 2).

- [ ] **Step 1: Write** `investigations/glucose-regulation/investigation.yaml` (model header on `../viva-munk/investigations/composite-gallery/investigation.yaml`):

```yaml
schema_version: 2
name: glucose-regulation
title: "Glucose Regulation — COPASI vs Tellurium"
created: '2026-07-26'
status: running

question: |
  For BioModels matching "glucose regulation", do COPASI and Tellurium agree on
  the time-course dynamics — and which models diverge or fail to load in one engine?

hypothesis: |
  Most curated glucose-regulation SBML models integrate to near-identical
  trajectories under COPASI and Tellurium; disagreements flag either engine-
  specific loading issues or genuinely stiff/edge-case models worth follow-up.

lead: |
  This is the first investigation in viva-human-atlas (HRA / Whole Person
  Physiome). It reuses pbg-biomodels' multi-simulator comparison, scoped to the
  glucose-regulation query and the COPASI + Tellurium engines, to establish a
  trustworthy fetch-and-compare spine. Ontology linking and the 3D-spatial
  connection are deferred to later investigations (see
  references/sources/hra-wpp-context.md).

studies:
  - glucose-regulation

expert_docs: []
acceptance_criteria: []
```

- [ ] **Step 2: Write** `studies/glucose-regulation/study.yaml` (model header on `../viva-munk/studies/glucose-growth/study.yaml`):

```yaml
schema_version: 4
name: glucose-regulation
title: "Glucose Regulation — COPASI vs Tellurium"
created: '2026-07-26'
status: running
design_status: complete
implementation_status: complete
simulation_status: pending
phase: Evaluate

question: |
  Do COPASI and Tellurium agree on the dynamics of BioModels matching
  "glucose regulation"?

study_card:
  goal: "Fetch glucose-regulation BioModels and score COPASI-vs-Tellurium agreement."
  mechanism: "search_biomodels(query) -> pbg-biomodels compare (LoadBiomodelStep + per-engine UTC + all-pairs nRMSE)."
  expected_result: "Most models agree closely; divergences/load-failures are flagged per model."
  main_expert_question: "Are divergent models real dynamics differences or engine loading artifacts?"

readouts:
  - "per-model COPASI-vs-Tellurium nRMSE"
  - "count of models that fail to load in one engine"

baseline:
  - name: baseline
    composite: viva_human_atlas.composites.glucose_regulation.build_glucose_regulation
    params:
      query: "glucose regulation"
      max_results: 10
      simulators: "copasi,tellurium"
```

- [ ] **Step 3: Write** `references/papers.bib`:

```bibtex
% viva-human-atlas references. Add BibTeX entries as investigations cite them.
```

- [ ] **Step 4: Write the end-to-end test** `tests/test_end_to_end.py` (a fast mocked test + a real network test that's opt-in):

```python
import pytest

import viva_human_atlas.composites.glucose_regulation as gr
from viva_human_atlas.composites.glucose_regulation import run_glucose_regulation
from viva_human_atlas.biomodels_search import search_biomodels


def test_run_glucose_regulation_delegates_offline(monkeypatch):
    # Fully offline: mock BOTH search and run_comparison (run_comparison fetches
    # SBML over the network via LoadBiomodelStep, so it must be mocked here).
    monkeypatch.setattr(gr, "search_biomodels", lambda q, n, **k: ["BIOMD0000000372"])
    captured = {}
    def fake_run(ids, simulators=None, on_progress=None):
        captured["ids"] = ids
        captured["simulators"] = simulators
        return {ids[0]: {"engines": {}, "comparison": {}, "error": None}}
    monkeypatch.setattr(gr, "run_comparison", fake_run)

    report = run_glucose_regulation(max_results=1, simulators="copasi,tellurium")

    assert captured["ids"] == ["BIOMD0000000372"]
    assert captured["simulators"] == "copasi,tellurium"
    assert set(report) == {"BIOMD0000000372"}
    assert set(report["BIOMD0000000372"]) == {"engines", "comparison", "error"}


@pytest.mark.network
def test_run_glucose_regulation_real_model(monkeypatch):
    # End-to-end: mock only search; really fetch + run COPASI + Tellurium on one
    # known glucose model. If BIOMD0000000372 errors in one engine, the entry's
    # `error` is populated and the shape asserts still hold.
    monkeypatch.setattr(gr, "search_biomodels", lambda q, n, **k: ["BIOMD0000000372"])
    report = run_glucose_regulation(max_results=1, simulators="copasi,tellurium")
    assert set(report) == {"BIOMD0000000372"}
    assert set(report["BIOMD0000000372"]) == {"engines", "comparison", "error"}


@pytest.mark.network
def test_live_search_finds_glucose_models():
    ids = search_biomodels("glucose regulation", max_results=5)
    assert len(ids) >= 1
    assert all(i.startswith("BIOMD") or i.startswith("MODEL") for i in ids)
```

- [ ] **Step 5: Register the `network` marker.** Append to `pyproject.toml`:

```toml
[tool.pytest.ini_options]
markers = ["network: hits external services; deselect with -m 'not network'"]
```

- [ ] **Step 6: Run the offline test, expect PASS** (fully mocked delegation, no network):

```bash
cd ~/code/viva-human-atlas && .venv/bin/python -m pytest tests/test_end_to_end.py -m "not network" -v
```

- [ ] **Step 7: Run the live tests once to confirm real search + real dual-engine run works** (network required; not part of default CI):

```bash
cd ~/code/viva-human-atlas && .venv/bin/python -m pytest tests/test_end_to_end.py -m network -v
```

If `BIOMD0000000372` does not appear in the live search or fails to load in both engines, pick a glucose-regulation ID that does (from the live search output) and update the mocked ID in the Step 4 tests accordingly.

- [ ] **Step 8: Run the full offline suite, expect all PASS:**

```bash
cd ~/code/viva-human-atlas && .venv/bin/python -m pytest -m "not network" -v
```

- [ ] **Step 9: Commit:**

```bash
git add investigations studies references/papers.bib tests/test_end_to_end.py pyproject.toml
git commit -m "feat: glucose-regulation investigation + study + end-to-end smoke"
```

---

## Self-Review

**Spec coverage:**
- Workspace `viva-human-atlas` + layout → Task 1. ✔
- Imports pbg-biomodels / pbg-copasi / pbg-tellurium → Task 1 (pyproject + workspace.yaml). ✔
- BioModels API query for "glucose regulation" → Task 2 (`search_biomodels`) + used in Task 3/4. ✔
- Run on COPASI **and** Tellurium + compare → reused via `build_compare_document`/`run_comparison` with `simulators="copasi,tellurium"` in Task 3. ✔
- Starting composite + beginning of an investigation → Task 3 generator + Task 4 investigation/study. ✔
- Sources from Katy's email → already written (`references/sources/hra-wpp-context.md`, committed in the scaffold commit). ✔
- Deferred (ontology bridge, 3D, annotation) → not implemented, by design. ✔

**Placeholder scan:** No TBD/TODO; every code step has full code. `references/papers.bib` is intentionally a single comment line (valid). ✔

**Type consistency:** `search_biomodels(query, max_results, *, _get)` used consistently in Tasks 2/3/4. `build_compare_document(ids, simulators=)` and `run_comparison(ids, simulators=, on_progress=)` match the real pbg-biomodels signatures read from source. `build_glucose_regulation(core=None, *, query, max_results, simulators)` matches the generator param names. ✔
