# HRA 3D coverage + spatial linkage + viewer — Implementation Plan

> **For agentic workers:** implement task-by-task, TDD, commit per task. Uses the conventions already on `main` (typed workspace types in `viva_human_atlas/types.py`, `@composite_generator`, study `baseline.composite` = the **registered generator id** `viva_human_atlas.composites.<module>.<name>`, offline tests inject fakes / monkeypatch, live tests `@pytest.mark.network`).

**Goal:** Spatially ground Aim-2 models on HRA 3D anatomy: ingest the 1,400+ AS crosswalk + FTUs, compute model coverage over AS/organs, link model outputs to AS→GLB nodes, and ship a workbench **analysis-tool** 3D viewer that colors an organ's AS by coverage.

**Architecture:** New typed HRA Steps (crosswalk, FTU) + `coverage.py` + `spatial_link.py` reusing the `biomodel_do` `organ_to_models` index; composite generators + studies for each; a `workbench_viewers.py` launcher tool whose three.js viewer + `config.json`/`coverage.json` are materialized under `studies/<slug>/viz/hra/` (served live + copied into the published bundle).

**Tech Stack:** Python 3.12, `requests`, `csv`, process-bigraph, pytest; three.js (importmap-pinned) for the viewer.

## Global Constraints
- HRA endpoints (verified): crosswalk CSV `https://cdn.humanatlas.io/digital-objects/ref-organ/asct-b-3d-models-crosswalk/latest/assets/asct-b-3d-models-crosswalk.csv` (header row begins `anatomical_structure_of,source_spatial_entity,node_name,label,OntologyID,representation_of,node_type,glb file of single organs,...`); reference organs `https://apps.humanatlas.io/api/v1/reference-organs`; FTU DO `https://purl.humanatlas.io/3d-ftu/<slug>/latest` (`{data:[<glb name>], metadata:{...}}`). CDN sends `access-control-allow-origin: *`.
- All fetchers take injectable `_get` (requests.get-compatible), default `requests.get`; unit tests inject fakes (NO network). Live tests `@pytest.mark.network`.
- Register new named types in `viva_human_atlas/types.py` (`TYPES_DICT`) — it's already wired into `register_types` + `core.build_core`.
- Composite generators use the superpowers shim `try: from viva_superpowers.composite_generator import composite_generator except ModuleNotFoundError: from pbg_superpowers...`. Wire Steps by **fully-dotted address** (`local:viva_human_atlas.<mod>.<StepClass>`), not bare name.
- Study `baseline.composite` MUST be the registered generator id.
- Git: `git -c user.name="Eran Agmon" -c user.email="agmon.eran@gmail.com" ...` + trailer `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`. Tests via `.venv/bin/python -m pytest`; offline = `-m "not network"`. Use `PYTHONUTF8=1` for any script reading YAML/CSV with non-ASCII.

---

### Task A — Data ingestion: crosswalk + FTU Steps

**Files:** modify `viva_human_atlas/hra_api.py`, `viva_human_atlas/types.py`; test `tests/test_hra_crosswalk_ftu.py`.

**Produces:**
- `CROSSWALK_URL` constant; `fetch_crosswalk(url=CROSSWALK_URL, *, _get=None) -> list[dict]` → rows `{node_name, label, uberon, representation_of, node_type, organ_glb, parent}` (skip rows before the header line that starts with `anatomical_structure_of`; keep only rows with a non-empty `node_name`).
- `fetch_ftu(slug="glomerulus", *, _get=None) -> dict` → `{slug, title, description, glb, glb_url}` (glb name from DO `data[0]`; `glb_url` = `https://cdn.humanatlas.io/digital-objects/3d-ftu/<slug>/latest/assets/<glb>`).
- `HRACrosswalkStep(Step)`: `config_schema={"url":"string"}`, `inputs()->{}`, `outputs()->{"anatomical_structures_3d":"list[as_3d]"}`, `update` returns `{"anatomical_structures_3d": fetch_crosswalk(self.config.get("url", CROSSWALK_URL))}`, with `description` + `_contract`-style port doc like the existing Steps.
- `HRAFtuStep(Step)`: `config_schema={"slug":"string"}`, `outputs()->{"ftu":"ftu"}`.
- Types in `types.py`: `as_3d = {node_name:string, label:string, uberon:string, representation_of:string, node_type:string, organ_glb:string, parent:string}`; `ftu = {slug:string, title:string, description:string, glb:string, glb_url:string}` (match the bigraph-schema map/field syntax already used in `types.py`).

- [ ] **Step 1 — failing test** `tests/test_hra_crosswalk_ftu.py`:
```python
from viva_human_atlas.hra_api import fetch_crosswalk, fetch_ftu

class _R:
    def __init__(self, text=None, payload=None): self._t=text; self._p=payload
    def raise_for_status(self): pass
    @property
    def text(self): return self._t
    def json(self): return self._p

CSV = (
 '"ASCT+B ... Mapping",,,,,,,,\n'
 ',,,,,,,,\n'
 'anatomical_structure_of,source_spatial_entity,node_name,label,OntologyID,representation_of,node_type,glb file of single organs,Ref/1\n'
 '-,#VHFemaleOrgans,VH_F_kidney,kidney,UBERON:0002113,http://purl.obolibrary.org/obo/UBERON_0002113,mesh,VH_F_Kidney\n'
 '-,-,VH_F,-,-,-,organizational,3d-vh-f-united\n'
)

def test_fetch_crosswalk_parses_as_rows():
    rows = fetch_crosswalk(_get=lambda u, **k: _R(text=CSV))
    kidney = [r for r in rows if r["node_name"] == "VH_F_kidney"][0]
    assert kidney["uberon"] == "UBERON:0002113"
    assert kidney["label"] == "kidney"
    assert kidney["node_type"] == "mesh"
    assert kidney["organ_glb"] == "VH_F_Kidney"
    # organizational rows are still parsed (node present) but VH_F has no uberon
    assert any(r["node_name"] == "VH_F" and not r["uberon"] for r in rows)

def test_fetch_ftu_resolves_glb_url():
    payload = {"data": ["glomerulus.glb"], "metadata": {"title": "glomerulus (v1.0)"}}
    ftu = fetch_ftu("glomerulus", _get=lambda u, **k: _R(payload=payload))
    assert ftu["glb"] == "glomerulus.glb"
    assert ftu["glb_url"].endswith("/3d-ftu/glomerulus/latest/assets/glomerulus.glb")
```
- [ ] **Step 2** run → FAIL. `.venv/bin/python -m pytest tests/test_hra_crosswalk_ftu.py -v`
- [ ] **Step 3** implement in `hra_api.py`:
```python
import csv, io
CROSSWALK_URL = ("https://cdn.humanatlas.io/digital-objects/ref-organ/"
                 "asct-b-3d-models-crosswalk/latest/assets/asct-b-3d-models-crosswalk.csv")
_FTU_BASE = "https://cdn.humanatlas.io/digital-objects/3d-ftu"

def fetch_crosswalk(url=CROSSWALK_URL, *, _get=None):
    if _get is None:
        import requests; _get = requests.get
    resp = _get(url, timeout=60); resp.raise_for_status()
    lines = resp.text.splitlines()
    start = next((i for i, ln in enumerate(lines)
                  if ln.startswith("anatomical_structure_of")), None)
    if start is None:
        return []
    reader = csv.DictReader(io.StringIO("\n".join(lines[start:])))
    out = []
    for row in reader:
        node = (row.get("node_name") or "").strip()
        if not node:
            continue
        uid = (row.get("OntologyID") or "").strip()
        out.append({
            "node_name": node,
            "label": (row.get("label") or "").strip().lstrip("-").strip(),
            "uberon": "" if uid in ("", "-") else uid,
            "representation_of": (row.get("representation_of") or "").strip().lstrip("-").strip(),
            "node_type": (row.get("node_type") or "").strip(),
            "organ_glb": (row.get("glb file of single organs") or "").strip(),
            "parent": (row.get("anatomical_structure_of") or "").strip().lstrip("-").strip(),
        })
    return out

def fetch_ftu(slug="glomerulus", *, _get=None):
    if _get is None:
        import requests; _get = requests.get
    resp = _get(f"https://purl.humanatlas.io/3d-ftu/{slug}/latest", timeout=30)
    resp.raise_for_status()
    do = resp.json() or {}
    glb = (do.get("data") or [""])[0]
    return {
        "slug": slug,
        "title": (do.get("metadata") or {}).get("title", slug),
        "description": (do.get("metadata") or {}).get("description", ""),
        "glb": glb,
        "glb_url": f"{_FTU_BASE}/{slug}/latest/assets/{glb}" if glb else "",
    }
```
Add `HRACrosswalkStep` / `HRAFtuStep` mirroring the existing Steps' description/`describe()`/`_contract` convention, and the two types to `types.py::TYPES_DICT`.
- [ ] **Step 4** run → PASS (offline). Also confirm `build_core()` still discovers all generators and registers the new types.
- [ ] **Step 5 — live sanity (network)** add:
```python
import pytest
@pytest.mark.network
def test_crosswalk_live_has_many_as():
    rows = fetch_crosswalk()
    withu = [r for r in rows if r["uberon"].startswith("UBERON:")]
    assert len(withu) >= 1000
```
Run `-m network` once; record the count in the commit.
- [ ] **Step 6** commit: `feat: HRA crosswalk + FTU Steps (as_3d / ftu types)`

---

### Task B — Model coverage (`viva_human_atlas/coverage.py`)

**Files:** create `viva_human_atlas/coverage.py`, `viva_human_atlas/composites/coverage_composite.py`; modify `composites/__init__.py`, `types.py`; test `tests/test_coverage.py`.

**Consumes:** `hra_api.fetch_crosswalk`; `biomodel_do.build_biomodel_do_catalog` (returns `{biomodel_dos, organ_index, organ_to_models}`) — import both at module top (monkeypatchable).

**Produces:**
- `build_coverage(query="glucose regulation", max_results=25, *, _get_search=None, _get_hra=None, _get_xwalk=None) -> dict`:
  1. `cat = build_biomodel_do_catalog(query, max_results, _get_search=_get_search, _get_hra=_get_hra)`.
  2. `rows = fetch_crosswalk(_get=_get_xwalk)`.
  3. Build `uberon_models = cat["organ_to_models"]` (uberon→[ids]) and, from `cat["organ_index"]`, `organ_by_uberon`. For each crosswalk row with a `uberon`, mark `covered` if that uberon is in `uberon_models` **OR** the row's organ (matched via `organ_index` uberon or `organ_glb` heuristic) has models — v1 **organ-granularity**: also propagate coverage to every AS whose `organ_glb` matches a covered organ's assets. Keep it simple + documented: covered = `uberon in uberon_models` OR `organ_glb in covered_glbs` where `covered_glbs` = set of `organ_index[*]` asset stems for organs that have models.
  4. Return `{"coverage": [{uberon, label, organ_glb, node_type, n_models, model_ids, covered}], "summary": {"n_as": int, "n_as_covered": int, "n_organs_glb": int, "n_organs_glb_covered": int, "query": query}}`.
- `CoverageStep(Step)`: config `{query, max_results}`, `outputs()->{"coverage":"list[coverage_row]", "coverage_summary":"coverage_summary"}`.
- `@composite_generator(name="model-coverage-3d", parameters={query,max_results})` `build_model_coverage_3d` → composite wiring `CoverageStep` → stores + RAMEmitter.
- Types `coverage_row`, `coverage_summary` in `types.py`.

- [ ] **Step 1 — failing test** `tests/test_coverage.py` (fully offline; mock both `build_biomodel_do_catalog` and `fetch_crosswalk` on the `coverage` module):
```python
import viva_human_atlas.coverage as cov

def test_build_coverage_organ_granularity(monkeypatch):
    monkeypatch.setattr(cov, "build_biomodel_do_catalog", lambda q, n, **k: {
        "biomodel_dos": [{"biomodel_id": "BIOMD1", "name": "hepatic glucose",
                          "organs": [{"organ": "liver", "uberon": "UBERON:0002107"}]}],
        "organ_index": {"liver": {"uberon": "UBERON:0002107", "asset_urls": ["x/VH_F_Liver.glb"]}},
        "organ_to_models": {"UBERON:0002107": ["BIOMD1"]},
    })
    monkeypatch.setattr(cov, "fetch_crosswalk", lambda **k: [
        {"node_name": "VH_F_liver", "label": "liver", "uberon": "UBERON:0002107",
         "representation_of": "", "node_type": "mesh", "organ_glb": "VH_F_Liver", "parent": ""},
        {"node_name": "VH_F_kidney", "label": "kidney", "uberon": "UBERON:0002113",
         "representation_of": "", "node_type": "mesh", "organ_glb": "VH_F_Kidney", "parent": ""},
    ])
    out = cov.build_coverage(max_results=1)
    by = {r["uberon"]: r for r in out["coverage"]}
    assert by["UBERON:0002107"]["covered"] is True and by["UBERON:0002107"]["n_models"] == 1
    assert by["UBERON:0002113"]["covered"] is False
    assert out["summary"]["n_as"] == 2 and out["summary"]["n_as_covered"] == 1
```
- [ ] **Step 2** run → FAIL.
- [ ] **Step 3** implement `coverage.py` (per the contract above) + `CoverageStep`; add the generator in `composites/coverage_composite.py`; register it in `composites/__init__.py`; add the two types.
- [ ] **Step 4** run → PASS + full offline suite (`-m "not network"`) green; confirm `discover_generators()` includes `model-coverage-3d`.
- [ ] **Step 5** commit: `feat: model-coverage-3d — AS/organ coverage from biomodel-DO annotations`

---

### Task C — Spatial linkage (`viva_human_atlas/spatial_link.py`)

**Files:** create `viva_human_atlas/spatial_link.py`, `viva_human_atlas/composites/spatial_link_composite.py`; modify `composites/__init__.py`, `types.py`; test `tests/test_spatial_link.py`.

**Produces:**
- `build_spatial_links(query="glucose regulation", max_results=25, *, _get_search=None, _get_hra=None, _get_xwalk=None) -> dict` → for each biomodel DO organ, join to crosswalk AS on `uberon`, emit `{"links": [{biomodel_id, name, uberon, label, organ_glb, node_name, readout}], "summary": {n_links, n_models}}`. `readout` is the placeholder string `"pending time-series"` in v1.
- `SpatialLinkStep` + `@composite_generator(name="spatial-linkage")` `build_spatial_linkage`. Type `spatial_link_row`.

- [ ] **Step 1 — failing test** (offline, mock `build_biomodel_do_catalog` + `fetch_crosswalk` on the module): a liver model links to the `VH_F_liver` node via `UBERON:0002107`; assert one link with `node_name=="VH_F_liver"`, `readout=="pending time-series"`.
- [ ] **Step 2** run → FAIL.
- [ ] **Step 3** implement.
- [ ] **Step 4** run → PASS + offline suite green + generator discovered.
- [ ] **Step 5** commit: `feat: spatial-linkage — model -> AS -> GLB node links`

---

### Task D — Viewer analysis tool + materialize

**Files:** create `viva_human_atlas/assets/hra_glb_viewer/index.html`, `viva_human_atlas/assets/hra_glb_viewer/viewer.js`, `viva_human_atlas/workbench_viewers.py`, `viva_human_atlas/viewer_pack.py`; test `tests/test_viewer_tool.py`, `tests/test_workbench_viewers.py`.

**D.1 — `viewer_pack.py`: materialize the viewer + data under a study's `viz/hra/`.**
- `materialize_viewer(study_dir, *, organ_glb_url, organ_label, coverage, links, node_field="node_name") -> Path`:
  writes `study_dir/viz/hra/coverage.json`, `spatial-links.json`, and `config.json` = `{"glb": organ_glb_url, "organ": organ_label, "coverage": "coverage.json", "links": "spatial-links.json", "node_field": node_field}`, and copies the packaged `index.html`+`viewer.js` (via `importlib.resources`) into `viz/hra/`. Returns the dir.
- [ ] test (offline): call `materialize_viewer` into a tmp dir with tiny coverage/links dicts + a fake glb url; assert `viz/hra/{config.json,coverage.json,spatial-links.json,index.html,viewer.js}` all exist and `config.json["glb"]` matches.

**D.2 — `workbench_viewers.py::get_viewers(ws_root)`** (mirrors `pbg_ptools/workbench_viewers.py`):
```python
from pathlib import Path
def _studies_with_hra(ws_root):
    root = Path(ws_root) / "studies"
    return sorted(p.parent.parent.name for p in root.glob("*/viz/hra/coverage.json")) if root.exists() else []
def _targets(ws_root):
    return [{"study": s, "label": f"HRA Organ Viewer — {s}",
             "detail": "3D organ colored by model coverage",
             "href": f"studies/{s}/viz/hra/index.html"} for s in _studies_with_hra(ws_root)]
def get_viewers(ws_root):
    return [{
        "id": "hra-glb-viewer",
        "title": "HRA Organ Viewer",
        "description": "3D HRA organ (GLB) colored by mechanistic-model coverage.",
        "kind": "launcher",
        "applies": lambda ws: bool(_studies_with_hra(ws)),
        "targets": _targets,
    }]
```
- [ ] test `tests/test_workbench_viewers.py`: with a tmp ws_root containing `studies/model-coverage-3d/viz/hra/coverage.json`, `get_viewers(ws_root)[0]["id"]=="hra-glb-viewer"` and its `targets(ws_root)` yields one item with `href` ending `studies/model-coverage-3d/viz/hra/index.html`; empty when no coverage.json.

**D.3 — the viewer** `assets/hra_glb_viewer/{index.html,viewer.js}`: three.js (importmap-pinned to a CDN like `https://unpkg.com/three@0.160.0/`), `GLTFLoader`. On load: `fetch('config.json')` → then `fetch(cfg.coverage)`; `GLTFLoader().load(cfg.glb, ...)`; build a `uberon→covered/n_models` map from coverage keyed also by `node_name` (coverage rows carry `organ_glb`+`uberon`; match scene nodes by `node.name`); traverse `gltf.scene`, for each mesh set material color green (covered) / grey (uncovered); `OrbitControls`; a hover raycaster showing `label + uberon + n_models`; a small legend + summary line. Keep it one self-contained file pair, no build step. index.html mounts a full-window canvas + reads no query params (all via config.json).
- [ ] test `tests/test_viewer_tool.py`: assert `index.html` references `viewer.js` + an importmap/three; assert `viewer.js` reads `config.json`, `coverage`, and colors by a covered flag (grep for `config.json`, `coverage`, `covered`, `GLTFLoader`, `raycast`).

- [ ] commit: `feat: HRA GLB viewer analysis tool (workbench_viewers + three.js + materialize)`

---

### Task E — Studies + investigation + materialize + republish

**Files:** `investigations/hra-3d/investigation.yaml`; studies `hra-3d-crosswalk`, `model-coverage-3d`, `spatial-linkage`, `ftu-glomerulus` (`studies/<slug>/study.yaml`); `scripts/build_hra_viewer_pack.py`; test `tests/test_hra_3d_studies_load.py`.

- [ ] **studies** (schema_version 4; `baseline` → the **registered generator ids**: `viva_human_atlas.composites.hra_steps.hra-...` won't exist for crosswalk/ftu unless you add generators — so ALSO add tiny generators `hra-3d-crosswalk` and `ftu-glomerulus` in `composites/hra_steps.py` wrapping `HRACrosswalkStep`/`HRAFtuStep`, and point those studies at them; `model-coverage-3d`→`viva_human_atlas.composites.coverage_composite.model-coverage-3d`; `spatial-linkage`→`...spatial_link_composite.spatial-linkage`). Each has a non-empty baseline.
- [ ] **investigation** `investigations/hra-3d/investigation.yaml` (schema_version 2): question "Which of the 1,400+ HRA AS / 81 organs are covered by mechanistic models, and can we view model coverage on the 3D anatomy?"; `studies:` the four above; `inputs.references` → `Boerner2021HRA`, `Bidanta2025FTU`, `Bueckle2025HRAKG`, `Mungall2012Uberon`; `inputs.expert_docs` → the instructions + dynxr-proposal docs.
- [ ] **materialize script** `scripts/build_hra_viewer_pack.py`: resolves the kidney-female reference-organ GLB URL (from `fetch_reference_organs`), runs `build_coverage` + `build_spatial_links` (network), and calls `materialize_viewer(studies/model-coverage-3d, organ_glb_url=<kidney glb>, organ_label="kidney", coverage=..., links=...)`. Run it once (network) and **commit** the produced `studies/model-coverage-3d/viz/hra/` (coverage.json, spatial-links.json, config.json, index.html, viewer.js) — the committed pack is what the tool + published bundle serve.
- [ ] **tests** `tests/test_hra_3d_studies_load.py`: offline (mock fetchers) build+run each generator's composite via `build_core()` and assert non-empty stores; assert all four generators discovered; assert the four studies' `baseline.composite` resolve to registered ids. `@pytest.mark.network`: run `scripts/build_hra_viewer_pack.py` logic against real data and assert coverage summary `n_as>=1000` and at least one covered organ.
- [ ] Run offline suite green; run the materialize script (network) and commit the viz pack.
- [ ] commit: `feat: hra-3d investigation + studies + committed kidney viewer pack`
- [ ] **republish showcase**: `bash scripts/publish_dashboard.sh --push`; verify live that `api/analysis-viewers.json` contains `hra-glb-viewer` and `studies/model-coverage-3d/viz/hra/index.html` + `coverage.json` are reachable under the published base path. (If the target `href` needs the base-path prefix to resolve in the bundle, adjust `_targets` to prepend it / verify against the live URL.)

---

## Self-Review
- **Coverage:** C1 ingestion (Task A) ✓; C2 coverage (Task B) ✓; C3 linkage (Task C) ✓; C4 viewer analysis tool (Task D) ✓; studies + showcase (Task E) ✓. Spec's "organ-granularity v1" + "placeholder readouts" honored (Task B step 3 rule; Task C `readout="pending time-series"`).
- **Placeholder scan:** viewer.js body is described concretely (fetch config.json→coverage→GLTFLoader→color by covered→raycast hover) — implementer writes the ~150-line three.js against that contract + the grep test; not a TODO.
- **Type consistency:** `fetch_crosswalk` row keys (node_name/label/uberon/representation_of/node_type/organ_glb/parent) are identical across A/B/C/D; `build_biomodel_do_catalog` shape (`organ_to_models`,`organ_index`,`biomodel_dos`) matches its real signature; study refs use registered gids per the workbench resolver; `materialize_viewer` writes exactly what `get_viewers` targets + the viewer reads (`config.json`).
- **Risk flagged for Task E:** published-bundle href resolution (base-path) + that `studies/*/viz/` is copied into the bundle — verify against the live URL and adjust `_targets` if needed.
