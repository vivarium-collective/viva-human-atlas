# HRA Atlas Browser Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a self-contained 3D "HRA Atlas Browser" that lets you pick any of the 50 HRA organs with a GLB asset, see its regions demarcated and colored by the number of mechanistic models associated with it, and click through to the BioModels pages — fed by a refreshed atlas-manifest pipeline and homed in a new study under the `hra-3d` investigation.

**Architecture:** A Python builder crosses the committed corpus catalog (`organ_index` + `organ_to_models`) into an `atlas.json` manifest and reuses `build_corpus_coverage` for per-node `coverage.json`. A no-build three.js page (`viz/atlas/`) reads those sibling JSONs to render an organ selector, outlined regions, a model-count color gradient, and a clickable BioModels panel. A workbench viewer plugin exposes it on the Analyses page. A new `hra-atlas-browser` study documents the deliverable.

**Tech Stack:** Python 3.12 (stdlib `json`, `pathlib`), pytest, three.js 0.160 (importmap/unpkg, no bundler), vivarium-workbench + viva-superpowers (editable from `origin/main`).

## Global Constraints

- Python `>=3.12`; `process-bigraph==1.5.0`.
- Package imports are `viva_biomodels` (NOT `pbg_biomodels`) — the repo migrated on `origin/main` (commit 5b48db7). Follow existing module imports.
- No new network dependency in the builder or its tests — use the committed `datasets/biomodel_corpus_catalog.json`.
- Offline tests must pass under `-m "not network"`.
- Viewer is self-contained: three.js pinned via importmap (`https://unpkg.com/three@0.160.0/…`), all data from sibling JSON files, no query params, no build step. Mirror the existing `studies/model-coverage-3d/viz/hra/` pattern.
- BioModels URL format: `https://www.ebi.ac.uk/biomodels/<BIOMD_ID>`.
- Work happens in the `feat/hra-atlas-browser` worktree at `~/code/viva-human-atlas--atlas-browser`. Run Python via that worktree's own venv (see Task 0); verify `viva_human_atlas.__file__` resolves inside the worktree before running tests.
- Commit after every task. End commit messages with the `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>` trailer.

---

### Task 0: Refresh deps + worktree venv

**Files:**
- Modify: none (environment only)

**Interfaces:**
- Produces: a worktree venv at `~/code/viva-human-atlas--atlas-browser/.venv` with `viva_human_atlas`, `vivarium_workbench`, and `viva_superpowers`/`superpowers` importable; `vivarium-workbench` + `pbg-superpowers` installed editable from their `origin/main` `--main` worktrees.

- [ ] **Step 1: Refresh the sibling `--main` worktrees to origin/main**

Do NOT touch the canonical siblings' checked-out feature branches. Use their `--main` worktrees:
```bash
git -C ~/code/vivarium-workbench fetch origin main
git -C ~/code/vivarium-workbench--main checkout main && git -C ~/code/vivarium-workbench--main pull --ff-only origin main
git -C ~/code/pbg-superpowers fetch origin main
# create a --main worktree for pbg-superpowers if absent:
test -d ~/code/pbg-superpowers--main || git -C ~/code/pbg-superpowers worktree add ~/code/pbg-superpowers--main main
git -C ~/code/pbg-superpowers--main checkout main && git -C ~/code/pbg-superpowers--main pull --ff-only origin main
```
Expected: both `--main` worktrees report `HEAD` at `origin/main` with no foreign commits (`git log --oneline -1`).

- [ ] **Step 2: Create the worktree venv and install**

```bash
cd ~/code/viva-human-atlas--atlas-browser
uv venv
uv pip install -e .
uv pip install -e ~/code/vivarium-workbench--main
uv pip install -e ~/code/pbg-superpowers--main
```

- [ ] **Step 3: Verify the right trees are imported**

Run:
```bash
cd ~/code/viva-human-atlas--atlas-browser
.venv/bin/python -c "import viva_human_atlas, vivarium_workbench; print(viva_human_atlas.__file__); print(vivarium_workbench.__file__)"
```
Expected: `viva_human_atlas.__file__` is under `~/code/viva-human-atlas--atlas-browser/`; `vivarium_workbench.__file__` is under `~/code/vivarium-workbench--main/`. If `viva_human_atlas` resolves elsewhere, stop and fix before continuing.

- [ ] **Step 4: Baseline the offline suite**

Run: `cd ~/code/viva-human-atlas--atlas-browser && .venv/bin/python -m pytest -m "not network" -q`
Expected: PASS (green baseline before any changes). Record the count.

- [ ] **Step 5: Commit** (no code changed; skip commit if `git status` is clean)

---

### Task 1: Atlas manifest builder library

**Files:**
- Create: `viva_human_atlas/atlas_pack.py`
- Test: `tests/test_atlas_pack.py`

**Interfaces:**
- Consumes: `viva_human_atlas.coverage.load_corpus_catalog(path) -> {biomodel_dos, organ_index, organ_to_models}`. Shapes:
  - `organ_index[key] = {"uberon": "UBERON:…"|None, "sexes": ["Female","Male"], "asset_urls": ["…3d-vh-f-….glb", …]}` (50 keys; some are sex/side variants like `eye-female-left`).
  - `organ_to_models[uberon] = ["BIOMD0000000137", …]`.
  - `biomodel_dos = [{"biomodel_id": "BIOMD…", "name": "…", "organs": [...], ...}, …]` (1096 entries).
- Produces:
  - `biomodels_url(biomodel_id: str) -> str` → `"https://www.ebi.ac.uk/biomodels/<id>"`.
  - `build_atlas_manifest(catalog: dict) -> dict` → the `atlas.json` payload:
    ```python
    {"organs": [{"key": str, "label": str, "uberon": str|None,
                 "glb": {"female": str|None, "male": str|None},
                 "n_models": int,
                 "models": [{"biomodel_id": str, "name": str, "url": str}, ...]}, ...],
     "max_models": int,
     "summary": {"n_organs": int, "n_modeled": int, "n_models_total": int}}
    ```
    Rules: one entry per `organ_index` key (all 50). `n_models`/`models` come from `organ_to_models[entry["uberon"]]` (empty when the organ has no uberon or no models). `models[].name` resolved from a `biomodel_dos` id→name map (fall back to the id if unknown). `models` sorted by `biomodel_id`. `organs` sorted by `n_models` descending, then `key` ascending. `glb.female`/`glb.male` picked from `asset_urls` by the `-f-`/`-m-` stem convention (None if absent). `label` = key with hyphens→spaces, title-cased. `max_models` = max `n_models` (0 if none). `summary.n_modeled` = count of organs with `n_models > 0`; `summary.n_models_total` = sum of `n_models`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_atlas_pack.py
from pathlib import Path
from viva_human_atlas.atlas_pack import build_atlas_manifest, biomodels_url
from viva_human_atlas.coverage import load_corpus_catalog

CATALOG = Path(__file__).resolve().parents[1] / "datasets" / "biomodel_corpus_catalog.json"


def _manifest():
    return build_atlas_manifest(load_corpus_catalog(str(CATALOG)))


def test_biomodels_url():
    assert biomodels_url("BIOMD0000000137") == "https://www.ebi.ac.uk/biomodels/BIOMD0000000137"


def test_manifest_has_all_glb_organs():
    m = _manifest()
    cat = load_corpus_catalog(str(CATALOG))
    assert m["summary"]["n_organs"] == len(cat["organ_index"]) == 50
    assert len(m["organs"]) == 50


def test_pancreas_is_top_and_counts_match_organ_to_models():
    m = _manifest()
    cat = load_corpus_catalog(str(CATALOG))
    top = m["organs"][0]
    assert top["key"] == "pancreas"
    assert top["n_models"] == 36 == m["max_models"]
    assert top["n_models"] == len(cat["organ_to_models"][top["uberon"]])
    assert len(top["models"]) == top["n_models"]


def test_every_model_row_is_well_formed_and_sorted():
    m = _manifest()
    top = m["organs"][0]
    ids = [row["biomodel_id"] for row in top["models"]]
    assert ids == sorted(ids)
    for row in top["models"]:
        assert row["url"] == f"https://www.ebi.ac.uk/biomodels/{row['biomodel_id']}"
        assert row["name"] and not row["name"].startswith("BIOMD")  # real name resolved


def test_zero_model_organs_present_with_empty_models():
    m = _manifest()
    zero = [o for o in m["organs"] if o["n_models"] == 0]
    assert len(zero) == 40
    assert all(o["models"] == [] for o in zero)
    assert m["summary"]["n_modeled"] == 10


def test_glb_urls_split_by_sex():
    m = _manifest()
    pancreas = m["organs"][0]
    assert pancreas["glb"]["female"].endswith("3d-vh-f-pancreas.glb")
    assert pancreas["glb"]["male"].endswith("3d-vh-m-pancreas.glb")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_atlas_pack.py -q`
Expected: FAIL with `ModuleNotFoundError: viva_human_atlas.atlas_pack`.

- [ ] **Step 3: Write minimal implementation**

```python
# viva_human_atlas/atlas_pack.py
"""Build the HRA Atlas Browser manifest (atlas.json) from the committed
corpus catalog: one entry per GLB-backed HRA organ, its model count, and the
BioModels list, for the organ-selector + model-count-gradient viewer."""
from __future__ import annotations

BIOMODELS_BASE = "https://www.ebi.ac.uk/biomodels/"


def biomodels_url(biomodel_id: str) -> str:
    return f"{BIOMODELS_BASE}{biomodel_id}"


def _label(key: str) -> str:
    return key.replace("-", " ").title()


def _glb_by_sex(asset_urls: list[str]) -> dict:
    out = {"female": None, "male": None}
    for url in asset_urls or []:
        stem = url.rsplit("/", 1)[-1].lower()
        if "-f-" in stem and out["female"] is None:
            out["female"] = url
        elif "-m-" in stem and out["male"] is None:
            out["male"] = url
    # organs whose stems don't follow the -f-/-m- convention: fall back to first
    if out["female"] is None and out["male"] is None and asset_urls:
        out["female"] = asset_urls[0]
    return out


def build_atlas_manifest(catalog: dict) -> dict:
    organ_index = catalog["organ_index"]
    organ_to_models = catalog["organ_to_models"]
    id_to_name = {d["biomodel_id"]: d.get("name") or d["biomodel_id"]
                  for d in catalog["biomodel_dos"]}

    organs = []
    for key, entry in organ_index.items():
        uberon = entry.get("uberon")
        model_ids = sorted(organ_to_models.get(uberon, [])) if uberon else []
        models = [{"biomodel_id": mid,
                   "name": id_to_name.get(mid, mid),
                   "url": biomodels_url(mid)}
                  for mid in model_ids]
        organs.append({
            "key": key,
            "label": _label(key),
            "uberon": uberon,
            "glb": _glb_by_sex(entry.get("asset_urls") or []),
            "n_models": len(models),
            "models": models,
        })

    organs.sort(key=lambda o: (-o["n_models"], o["key"]))
    max_models = max((o["n_models"] for o in organs), default=0)
    return {
        "organs": organs,
        "max_models": max_models,
        "summary": {
            "n_organs": len(organs),
            "n_modeled": sum(1 for o in organs if o["n_models"] > 0),
            "n_models_total": sum(o["n_models"] for o in organs),
        },
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_atlas_pack.py -q`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add viva_human_atlas/atlas_pack.py tests/test_atlas_pack.py
git commit -m "feat: atlas-manifest builder (organ->models + BioModels links)"
```

---

### Task 2: Atlas pack build script + shape validation

**Files:**
- Create: `scripts/build_atlas_pack.py`
- Create: `viva_human_atlas/atlas_pack.py` — add `write_atlas_pack(out_dir, *, manifest, coverage, overview_glb_url)`
- Test: `tests/test_atlas_pack_shape.py`

**Interfaces:**
- Consumes: `build_atlas_manifest` (Task 1); `viva_human_atlas.coverage.build_corpus_coverage(catalog_path) -> {coverage:[...], summary:{...}}` and `load_corpus_catalog`.
- Produces: `write_atlas_pack(out_dir: Path, *, manifest: dict, coverage: dict, overview_glb_url: str|None) -> Path` — writes `atlas.json`, `coverage.json`, `config.json` into `out_dir` and returns it. `config.json` shape: `{"atlas": "atlas.json", "coverage": "coverage.json", "overview_glb": <url|None>, "node_field": "node_name"}`.
- The viewer files `index.html`/`viewer.js` are added in Task 3; this script copies them from `viz/atlas/` template location once they exist — for now it writes only the three JSON files. (Task 3 wires the copy step.)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_atlas_pack_shape.py
import json
from pathlib import Path
from viva_human_atlas.atlas_pack import build_atlas_manifest, write_atlas_pack
from viva_human_atlas.coverage import load_corpus_catalog

CATALOG = Path(__file__).resolve().parents[1] / "datasets" / "biomodel_corpus_catalog.json"


def test_write_atlas_pack_emits_three_jsons(tmp_path):
    cat = load_corpus_catalog(str(CATALOG))
    manifest = build_atlas_manifest(cat)
    coverage = {"coverage": [], "summary": {"n_as": 0}}
    out = write_atlas_pack(tmp_path, manifest=manifest, coverage=coverage,
                           overview_glb_url="https://example/united.glb")
    atlas = json.loads((out / "atlas.json").read_text())
    cfg = json.loads((out / "config.json").read_text())
    assert atlas["organs"][0]["key"] == "pancreas"
    assert (out / "coverage.json").exists()
    assert cfg == {"atlas": "atlas.json", "coverage": "coverage.json",
                   "overview_glb": "https://example/united.glb", "node_field": "node_name"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_atlas_pack_shape.py -q`
Expected: FAIL with `ImportError: cannot import name 'write_atlas_pack'`.

- [ ] **Step 3: Add `write_atlas_pack` to `viva_human_atlas/atlas_pack.py`**

```python
# append to viva_human_atlas/atlas_pack.py
import json
from pathlib import Path


def write_atlas_pack(out_dir, *, manifest: dict, coverage: dict, overview_glb_url=None):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "atlas.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (out / "coverage.json").write_text(json.dumps(coverage, indent=2), encoding="utf-8")
    (out / "config.json").write_text(json.dumps({
        "atlas": "atlas.json",
        "coverage": "coverage.json",
        "overview_glb": overview_glb_url,
        "node_field": "node_name",
    }, indent=2), encoding="utf-8")
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_atlas_pack_shape.py -q`
Expected: PASS.

- [ ] **Step 5: Write the build script**

```python
# scripts/build_atlas_pack.py
"""Materialize the HRA Atlas Browser pack for the `hra-atlas-browser` study.

Builds the atlas manifest (all 50 GLB organs + model counts + BioModels
links) from the committed corpus catalog, plus full-corpus coverage, and
writes atlas.json/coverage.json/config.json alongside the committed
index.html/viewer.js under studies/hra-atlas-browser/viz/atlas/.

Run: PYTHONUTF8=1 .venv/bin/python scripts/build_atlas_pack.py
(network required — build_corpus_coverage hits the live ASCT+B-3D crosswalk).
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from viva_human_atlas.atlas_pack import build_atlas_manifest, write_atlas_pack
from viva_human_atlas.coverage import build_corpus_coverage, load_corpus_catalog

CATALOG_PATH = REPO_ROOT / "datasets" / "biomodel_corpus_catalog.json"
OUT_DIR = REPO_ROOT / "studies" / "hra-atlas-browser" / "viz" / "atlas"
# HRA "united" whole-body reference GLB for the overview landing view:
OVERVIEW_GLB = ("https://cdn.humanatlas.io/digital-objects/ref-organ/"
                "united-female/v1.4/assets/3d-vh-f-united.glb")


def main() -> None:
    catalog = load_corpus_catalog(str(CATALOG_PATH))
    manifest = build_atlas_manifest(catalog)
    print(f"  manifest: {manifest['summary']}")
    coverage = build_corpus_coverage(str(CATALOG_PATH))
    print(f"  coverage: {coverage['summary']}")
    out = write_atlas_pack(OUT_DIR, manifest=manifest, coverage=coverage,
                           overview_glb_url=OVERVIEW_GLB)
    print(f"Wrote atlas pack JSON to {out}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Commit**

```bash
git add viva_human_atlas/atlas_pack.py scripts/build_atlas_pack.py tests/test_atlas_pack_shape.py
git commit -m "feat: atlas pack writer + build script"
```

---

### Task 3: The three.js Atlas Browser viewer

**Files:**
- Create: `studies/hra-atlas-browser/viz/atlas/index.html`
- Create: `studies/hra-atlas-browser/viz/atlas/viewer.js`
- Modify: `scripts/build_atlas_pack.py` — copy `index.html`/`viewer.js` into `OUT_DIR` is NOT needed (they live there already, committed); instead ensure the build script does not overwrite them (it only writes JSON — already true). Add a guard test.
- Test: `tests/test_atlas_viewer_assets.py`

**Interfaces:**
- Consumes: `atlas.json` (Task 1 shape), `coverage.json`, `config.json` (Task 2 shape), all siblings of `index.html`.
- Produces: a browsable page. No JS test harness in-repo; verification is (a) a Python asset/shape test that the committed HTML references `viewer.js` + reads `config.json`, and (b) a manual checklist.

- [ ] **Step 1: Write the failing asset test**

```python
# tests/test_atlas_viewer_assets.py
from pathlib import Path

VIZ = Path(__file__).resolve().parents[1] / "studies" / "hra-atlas-browser" / "viz" / "atlas"


def test_viewer_assets_exist_and_are_wired():
    html = (VIZ / "index.html").read_text()
    js = (VIZ / "viewer.js").read_text()
    assert 'src="./viewer.js"' in html
    assert "config.json" in js and "atlas.json" in js.lower() or "cfg.atlas" in js
    assert "organ-select" in html          # the selector element
    assert "biomodels-panel" in html       # the model list panel
    assert "three@0.160.0" in html         # pinned importmap
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_atlas_viewer_assets.py -q`
Expected: FAIL (files do not exist).

- [ ] **Step 3: Create `index.html`**

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>HRA Atlas Browser — organs by model coverage</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="dark">
  <style>
    :root {
      --bg:#0e1116; --panel:#161b22; --text:#d6dde3; --text-dim:#8a96a3;
      --border:#2a313c; --nomodel:#6b7480;
    }
    *{box-sizing:border-box;}
    html,body{height:100%;margin:0;background:var(--bg);color:var(--text);
      font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;font-size:13px;overflow:hidden;}
    #app{position:relative;width:100vw;height:100vh;}
    canvas{display:block;width:100%;height:100%;}
    header{position:absolute;top:0;left:0;right:0;z-index:20;background:var(--panel);
      border-bottom:1px solid var(--border);padding:8px 14px;display:flex;align-items:center;gap:14px;}
    header h1{font-size:14px;font-weight:600;margin:0;}
    header h1 .sub{color:var(--text-dim);font-weight:400;font-size:12px;margin-left:8px;}
    #organ-select{margin-left:8px;background:var(--bg);color:var(--text);
      border:1px solid var(--border);border-radius:6px;padding:4px 8px;font-size:12px;max-width:280px;}
    #summary-line{color:var(--text-dim);font-size:12px;margin-left:auto;font-variant-numeric:tabular-nums;}
    .card{position:absolute;background:var(--panel);border:1px solid var(--border);
      border-radius:8px;box-shadow:0 8px 30px rgba(0,0,0,.5);}
    #legend{top:56px;left:14px;padding:10px 14px;font-size:12px;}
    #legend .bar{height:10px;width:180px;border-radius:5px;margin:6px 0;
      background:linear-gradient(90deg,#22303a,#2f6f4f,#4caf78,#8fe6b0);}
    #legend .scale{display:flex;justify-content:space-between;color:var(--text-dim);}
    #legend .nomodel-row{display:flex;align-items:center;gap:7px;margin-top:6px;}
    #legend .swatch{width:12px;height:12px;border-radius:50%;background:var(--nomodel);
      border:1px solid rgba(255,255,255,.15);}
    #biomodels-panel{top:56px;right:14px;width:300px;max-height:calc(100% - 84px);
      display:flex;flex-direction:column;overflow:hidden;}
    #biomodels-panel .bp-head{padding:10px 14px;border-bottom:1px solid var(--border);}
    #biomodels-panel .bp-title{font-weight:600;font-size:13px;}
    #biomodels-panel .bp-sub{color:var(--text-dim);font-size:11.5px;margin-top:2px;}
    #biomodels-list{overflow-y:auto;padding:6px 0;}
    #biomodels-list a{display:block;padding:6px 14px;color:var(--text);text-decoration:none;
      border-bottom:1px solid rgba(255,255,255,.04);}
    #biomodels-list a:hover{background:var(--bg);}
    #biomodels-list .mid{color:var(--text-dim);font-size:11px;font-variant-numeric:tabular-nums;}
    #biomodels-list .empty{padding:10px 14px;color:var(--text-dim);}
    #status{position:absolute;bottom:14px;left:14px;z-index:20;color:var(--text-dim);font-size:11.5px;}
  </style>
  <script type="importmap">
  {"imports":{
    "three":"https://unpkg.com/three@0.160.0/build/three.module.js",
    "three/addons/":"https://unpkg.com/three@0.160.0/examples/jsm/"}}
  </script>
</head>
<body>
  <div id="app">
    <header>
      <h1>HRA Atlas Browser<span class="sub">organs by model coverage</span></h1>
      <select id="organ-select" aria-label="Select organ"></select>
      <div id="summary-line">loading…</div>
    </header>
    <div id="legend" class="card">
      <div>models per organ</div>
      <div class="bar"></div>
      <div class="scale"><span>0</span><span id="legend-max">—</span></div>
      <div class="nomodel-row"><span class="swatch"></span><span>no model</span></div>
    </div>
    <div id="biomodels-panel" class="card">
      <div class="bp-head">
        <div class="bp-title" id="bp-title">Select an organ</div>
        <div class="bp-sub" id="bp-sub"></div>
      </div>
      <div id="biomodels-list"></div>
    </div>
    <div id="status">loading…</div>
  </div>
  <script type="module" src="./viewer.js"></script>
</body>
</html>
```

- [ ] **Step 4: Create `viewer.js`**

```javascript
// HRA Atlas Browser — self-contained three.js organ browser.
// Reads config.json -> {atlas, coverage, overview_glb, node_field}, then
// atlas.json (organ selector + model counts + BioModels links) and
// coverage.json (per-node covered flags). No build step; no query params.
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

const NOMODEL = 0x6b7480;

const els = {
  status: document.getElementById("status"),
  summary: document.getElementById("summary-line"),
  select: document.getElementById("organ-select"),
  legendMax: document.getElementById("legend-max"),
  bpTitle: document.getElementById("bp-title"),
  bpSub: document.getElementById("bp-sub"),
  bpList: document.getElementById("biomodels-list"),
};
const setStatus = (t) => { if (els.status) els.status.textContent = t; };

// Sequential model-count color: grey at 0, dark->bright green up to max.
function countColor(n, max) {
  if (!n) return new THREE.Color(NOMODEL);
  const t = max > 1 ? Math.log1p(n) / Math.log1p(max) : 1; // log scale (pancreas dominates)
  const lo = new THREE.Color(0x22303a), hi = new THREE.Color(0x8fe6b0);
  return lo.clone().lerp(hi, 0.15 + 0.85 * t);
}

function populateSelect(organs) {
  els.select.innerHTML = "";
  for (const o of organs) {
    const opt = document.createElement("option");
    opt.value = o.key;
    opt.textContent = o.n_models
      ? `${o.label} — ${o.n_models} model${o.n_models > 1 ? "s" : ""}`
      : `${o.label} — no model`;
    els.select.appendChild(opt);
  }
}

function renderBioModels(organ) {
  els.bpTitle.textContent = organ.label;
  els.bpSub.textContent = organ.n_models
    ? `${organ.n_models} BioModel${organ.n_models > 1 ? "s" : ""} · ${organ.uberon || ""}`
    : `no models · ${organ.uberon || ""}`;
  els.bpList.innerHTML = "";
  if (!organ.models.length) {
    const d = document.createElement("div");
    d.className = "empty";
    d.textContent = "No mechanistic models associated with this organ.";
    els.bpList.appendChild(d);
    return;
  }
  for (const m of organ.models) {
    const a = document.createElement("a");
    a.href = m.url;
    a.target = "_blank";
    a.rel = "noopener";
    a.innerHTML = `<div>${m.name}</div><div class="mid">${m.biomodel_id}</div>`;
    els.bpList.appendChild(a);
  }
}

async function main() {
  setStatus("loading config…");
  const cfg = await fetch("config.json").then((r) => r.json());
  const atlas = await fetch(cfg.atlas).then((r) => r.json());
  const organsByKey = new Map(atlas.organs.map((o) => [o.key, o]));
  els.legendMax.textContent = String(atlas.max_models);
  els.summary.textContent =
    `${atlas.summary.n_modeled}/${atlas.summary.n_organs} organs modeled · ${atlas.summary.n_models_total} model links`;
  populateSelect(atlas.organs);

  // ---- scene ----
  const app = document.getElementById("app");
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0e1116);
  const camera = new THREE.PerspectiveCamera(45, innerWidth / innerHeight, 0.01, 10000);
  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(devicePixelRatio || 1);
  renderer.setSize(innerWidth, innerHeight);
  app.appendChild(renderer.domElement);
  scene.add(new THREE.AmbientLight(0xffffff, 0.65));
  const dir = new THREE.DirectionalLight(0xffffff, 0.8);
  dir.position.set(3, 5, 4);
  scene.add(dir);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  const loader = new GLTFLoader();

  let currentRoot = null;
  const meshes = [];

  function frameObject(root) {
    const box = new THREE.Box3().setFromObject(root);
    const size = box.getSize(new THREE.Vector3()).length() || 1;
    const center = box.getCenter(new THREE.Vector3());
    camera.position.copy(center).add(new THREE.Vector3(size, size * 0.6, size));
    camera.near = size / 100;
    camera.far = size * 100;
    camera.updateProjectionMatrix();
    controls.target.copy(center);
    controls.update();
  }

  // Load one organ's GLB, color it by the organ's model count, and outline
  // each sub-region mesh so regions read as distinct shapes.
  function loadOrgan(key) {
    const organ = organsByKey.get(key);
    if (!organ) return;
    renderBioModels(organ);
    const url = organ.glb.female || organ.glb.male;
    if (!url) { setStatus(`${organ.label}: no GLB asset`); return; }
    setStatus(`loading ${organ.label}…`);
    loader.load(url, (gltf) => {
      if (currentRoot) { scene.remove(currentRoot); }
      meshes.length = 0;
      currentRoot = gltf.scene;
      const color = countColor(organ.n_models, atlas.max_models);
      currentRoot.traverse((node) => {
        if (!node.isMesh) return;
        node.material = new THREE.MeshStandardMaterial({ color: color.clone() });
        const edges = new THREE.LineSegments(
          new THREE.EdgesGeometry(node.geometry, 30),
          new THREE.LineBasicMaterial({ color: 0x0e1116, transparent: true, opacity: 0.55 })
        );
        node.add(edges);
        node.userData.regionName = node.name;
        meshes.push(node);
      });
      scene.add(currentRoot);
      frameObject(currentRoot);
      setStatus(`${organ.label}: ${meshes.length} regions`);
    }, undefined, (err) => setStatus(`failed to load ${organ.label}: ${err?.message || err}`));
  }

  els.select.addEventListener("change", (e) => loadOrgan(e.target.value));

  // Hover: brighten the hovered region and show its name in the status line.
  const ray = new THREE.Raycaster();
  const ndc = new THREE.Vector2();
  let hovered = null;
  renderer.domElement.addEventListener("pointermove", (event) => {
    const rect = renderer.domElement.getBoundingClientRect();
    ndc.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    ndc.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
    ray.setFromCamera(ndc, camera);
    const hit = ray.intersectObjects(meshes, false)[0];
    if (hovered && hovered !== hit?.object) { hovered.material.emissive?.setHex(0x000000); }
    if (hit) {
      hovered = hit.object;
      hovered.material.emissive = new THREE.Color(0x2b3a44);
      const organ = organsByKey.get(els.select.value);
      setStatus(`${hovered.userData.regionName} · ${organ.label} (${organ.n_models} models)`);
    }
  });

  addEventListener("resize", () => {
    camera.aspect = innerWidth / innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(innerWidth, innerHeight);
  });
  (function animate() {
    requestAnimationFrame(animate);
    controls.update();
    renderer.render(scene, camera);
  })();

  // Landing: load the most-modeled organ (first in the sorted list).
  els.select.value = atlas.organs[0].key;
  loadOrgan(atlas.organs[0].key);
}

main().catch((err) => { console.error(err); setStatus(`error: ${err?.message || err}`); });
```

- [ ] **Step 5: Run the asset test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_atlas_viewer_assets.py -q`
Expected: PASS.

- [ ] **Step 6: Build the real pack and manually verify**

Run: `cd ~/code/viva-human-atlas--atlas-browser && PYTHONUTF8=1 .venv/bin/python scripts/build_atlas_pack.py`
Then serve and open:
```bash
cd ~/code/viva-human-atlas--atlas-browser/studies/hra-atlas-browser/viz/atlas && python3 -m http.server 8765
```
Manual checklist (open http://localhost:8765/): dropdown lists 50 organs (modeled first); pancreas loads by default, colored bright green; regions show distinct outlines; hovering a region names it in the status line; the BioModels panel lists 36 rows for pancreas, each opening `ebi.ac.uk/biomodels/BIOMD…` in a new tab; switching to a zero-model organ (e.g. an eye) shows grey + "No mechanistic models". Note any failures.

- [ ] **Step 7: Commit**

```bash
git add studies/hra-atlas-browser/viz/atlas/index.html \
        studies/hra-atlas-browser/viz/atlas/viewer.js \
        studies/hra-atlas-browser/viz/atlas/atlas.json \
        studies/hra-atlas-browser/viz/atlas/coverage.json \
        studies/hra-atlas-browser/viz/atlas/config.json \
        tests/test_atlas_viewer_assets.py
git commit -m "feat: HRA Atlas Browser viewer (organ selector, region outlines, count gradient, BioModels panel)"
```

---

### Task 3b: Whole-body overview mode (default landing)

**Files:**
- Modify: `studies/hra-atlas-browser/viz/atlas/index.html` (add an "Overview (whole body)" option)
- Modify: `studies/hra-atlas-browser/viz/atlas/viewer.js`
- Test: `tests/test_atlas_viewer_assets.py` (extend)

**Interfaces:**
- Consumes: `cfg.overview_glb` (Task 2 config), `atlas.organs` (Task 1). Node→organ mapping is done in JS by normalized-substring match: an organ `key` (hyphens stripped, lowercased) that appears in a mesh's normalized node name (e.g. node `VH_F_Pancreas` → `vhfpancreas` contains `pancreas`) maps that mesh to that organ's `n_models`.
- Produces: an overview view that colors each organ mesh of the united GLB by its model count; it is the **default landing**, falling back to the top organ's single view if `cfg.overview_glb` is missing or fails to load.

- [ ] **Step 1: Extend the failing asset test**

Add to `tests/test_atlas_viewer_assets.py`:

```python
def test_viewer_has_overview_mode():
    js = (VIZ / "viewer.js").read_text()
    html = (VIZ / "index.html").read_text()
    assert "overview_glb" in js or "cfg.overview_glb" in js
    assert "loadOverview" in js
    assert "__overview__" in html or "__overview__" in js  # the overview select value
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_atlas_viewer_assets.py::test_viewer_has_overview_mode -q`
Expected: FAIL.

- [ ] **Step 3: Add the overview option to `index.html`**

Insert as the first option of the `<select id="organ-select">` — since the select is populated in JS, instead prepend it in `populateSelect`. No HTML change needed beyond a marker comment; add `<!-- __overview__ option is prepended in viewer.js -->` right before the `<select>` so the asset test's `__overview__` check passes via HTML, and implement the option in JS.

- [ ] **Step 4: Implement `loadOverview` and default-to-overview in `viewer.js`**

In `populateSelect`, prepend the overview option:

```javascript
  const ov = document.createElement("option");
  ov.value = "__overview__";
  ov.textContent = "Overview (whole body)";
  els.select.appendChild(ov);
```

Add a normalized-key helper and the overview loader:

```javascript
const normKey = (s) => String(s || "").toLowerCase().replace(/[^a-z0-9]/g, "");

function organForNode(nodeName, organs) {
  const nn = normKey(nodeName);
  // longest organ key that appears in the node name wins (avoids "eye" vs "eyelid")
  let best = null;
  for (const o of organs) {
    if (nn.includes(normKey(o.key)) && (!best || o.key.length > best.key.length)) best = o;
  }
  return best;
}

function loadOverview(cfg, atlas) {
  if (!cfg.overview_glb) { loadOrgan(atlas.organs[0].key); return; }
  els.bpTitle.textContent = "Whole body";
  els.bpSub.textContent = `${atlas.summary.n_modeled}/${atlas.summary.n_organs} organs modeled`;
  els.bpList.innerHTML = "";
  setStatus("loading whole-body overview…");
  loader.load(cfg.overview_glb, (gltf) => {
    if (currentRoot) scene.remove(currentRoot);
    meshes.length = 0;
    currentRoot = gltf.scene;
    currentRoot.traverse((node) => {
      if (!node.isMesh) return;
      const organ = organForNode(node.name, atlas.organs);
      const n = organ ? organ.n_models : 0;
      node.material = new THREE.MeshStandardMaterial({ color: countColor(n, atlas.max_models) });
      node.userData.regionName = node.name;
      node.userData.overviewOrgan = organ || null;
      meshes.push(node);
    });
    scene.add(currentRoot);
    frameObject(currentRoot);
    setStatus(`overview: ${meshes.length} nodes`);
  }, undefined, () => { setStatus("overview GLB failed — showing top organ"); loadOrgan(atlas.organs[0].key); });
}
```

Wire the selector and default landing (replace the two landing lines at the end of `main`):

```javascript
  els.select.addEventListener("change", (e) => {
    if (e.target.value === "__overview__") loadOverview(cfg, atlas);
    else loadOrgan(e.target.value);
  });
  // clicking an organ in the overview drills into it
  renderer.domElement.addEventListener("click", () => {
    if (els.select.value !== "__overview__" || !hovered) return;
    const organ = hovered.userData.overviewOrgan;
    if (organ) { els.select.value = organ.key; loadOrgan(organ.key); }
  });
  els.select.value = "__overview__";
  loadOverview(cfg, atlas);
```

Update the hover handler's status/BioModels for overview: when in overview and hovering a mapped node, show that organ's name/count and render its BioModels list, so hover previews the organ before a click drills in.

- [ ] **Step 5: Run the asset tests**

Run: `.venv/bin/python -m pytest tests/test_atlas_viewer_assets.py -q`
Expected: PASS.

- [ ] **Step 6: Rebuild pack + manually verify overview**

Run the build script and serve (as Task 3 Step 6). Verify: page lands on the whole-body overview with organs tinted by model count (pancreas brightest); hovering an organ names it and previews its models; clicking drills into that organ; the dropdown's "Overview (whole body)" returns to it; if the united GLB is slow/unavailable, it falls back to pancreas without a blank canvas.

- [ ] **Step 7: Commit**

```bash
git add studies/hra-atlas-browser/viz/atlas/index.html \
        studies/hra-atlas-browser/viz/atlas/viewer.js \
        tests/test_atlas_viewer_assets.py
git commit -m "feat: whole-body overview mode as the Atlas Browser landing view"
```

---

### Task 4: Workbench viewer registration

**Files:**
- Modify: `viva_human_atlas/workbench_viewers.py`
- Test: `tests/test_workbench_atlas_viewer.py`

**Interfaces:**
- Consumes: existing `get_viewers(ws_root)` contract (returns a list of viewer dicts with `id/title/description/kind/applies/targets/launch`).
- Produces: a second viewer dict `id="hra-atlas-browser"`, `applies` true when any `studies/*/viz/atlas/atlas.json` exists; `targets` point at `studies/<s>/viz/atlas/index.html`; `launch` reconstructs the same href. Add helper `_studies_with_atlas(ws_root) -> list[str]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_workbench_atlas_viewer.py
from pathlib import Path
from viva_human_atlas.workbench_viewers import get_viewers, _studies_with_atlas


def _mk(ws, slug):
    d = ws / "studies" / slug / "viz" / "atlas"
    d.mkdir(parents=True)
    (d / "atlas.json").write_text("{}")


def test_atlas_viewer_absent_when_no_pack(tmp_path):
    (tmp_path / "studies").mkdir()
    ids = [v["id"] for v in get_viewers(tmp_path) if v["applies"](tmp_path)]
    assert "hra-atlas-browser" not in ids


def test_atlas_viewer_present_and_targets_index(tmp_path):
    _mk(tmp_path, "hra-atlas-browser")
    assert _studies_with_atlas(tmp_path) == ["hra-atlas-browser"]
    viewer = next(v for v in get_viewers(tmp_path) if v["id"] == "hra-atlas-browser")
    assert viewer["applies"](tmp_path) is True
    targets = viewer["targets"](tmp_path)
    assert targets[0]["href"] == "studies/hra-atlas-browser/viz/atlas/index.html"
    assert viewer["launch"](tmp_path, study="hra-atlas-browser")["url"] == \
        "studies/hra-atlas-browser/viz/atlas/index.html"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_workbench_atlas_viewer.py -q`
Expected: FAIL with `ImportError: cannot import name '_studies_with_atlas'`.

- [ ] **Step 3: Add the atlas viewer to `workbench_viewers.py`**

Add after the existing `_launch`/before `get_viewers`, then extend `get_viewers`'s returned list:

```python
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
         "href": f"studies/{s}/viz/atlas/index.html"}
        for s in _studies_with_atlas(ws_root)
    ]


def _atlas_launch(ws_root, study=None, run=None, ctx=None) -> dict:
    if not study:
        return {"error": "no study selected", "status": 400}
    return {"url": f"studies/{study}/viz/atlas/index.html"}
```

In `get_viewers`, append a second dict to the returned list:

```python
        {
            "id": "hra-atlas-browser",
            "title": "HRA Atlas Browser",
            "description": "3D HRA organ browser: pick an organ, see regions colored by model count, click through to BioModels.",
            "kind": "launcher",
            "applies": lambda ws: bool(_studies_with_atlas(ws)),
            "targets": _atlas_targets,
            "launch": _atlas_launch,
        },
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_workbench_atlas_viewer.py -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add viva_human_atlas/workbench_viewers.py tests/test_workbench_atlas_viewer.py
git commit -m "feat: register HRA Atlas Browser as a workbench analysis viewer"
```

---

### Task 5: New study + investigation refinement

**Files:**
- Create: `studies/hra-atlas-browser/study.yaml`
- Modify: `investigations/hra-3d/investigation.yaml` (add study to `studies:`, mention browser in `lead`/`executive.verdict`)
- Modify: each `studies/*/study.yaml` — add an `investigation:` back-reference key
- Test: `tests/test_investigation_structure.py`

**Interfaces:**
- Consumes: existing study/investigation YAML schema (see `studies/model-coverage-3d/study.yaml`, `investigations/hra-3d/investigation.yaml`).
- Produces: a validated `hra-atlas-browser` study registered under `hra-3d`; every study carries `investigation: <name>`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_investigation_structure.py
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]


def _load(p):
    return yaml.safe_load(Path(p).read_text())


def test_atlas_study_exists_and_is_registered():
    study = _load(ROOT / "studies" / "hra-atlas-browser" / "study.yaml")
    assert study["name"] == "hra-atlas-browser"
    assert study["investigation"] == "hra-3d"
    inv = _load(ROOT / "investigations" / "hra-3d" / "investigation.yaml")
    assert "hra-atlas-browser" in inv["studies"]


def test_every_study_has_investigation_backref():
    inv_studies = {}
    for inv_yaml in (ROOT / "investigations").glob("*/investigation.yaml"):
        inv = _load(inv_yaml)
        for s in inv.get("studies", []):
            inv_studies[s] = inv["name"]
    for study_yaml in (ROOT / "studies").glob("*/study.yaml"):
        study = _load(study_yaml)
        assert "investigation" in study, f"{study['name']} missing investigation backref"
        # backref must match the investigation that lists it (when one does)
        if study["name"] in inv_studies:
            assert study["investigation"] == inv_studies[study["name"]]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_investigation_structure.py -q`
Expected: FAIL (study dir + backrefs absent).

- [ ] **Step 3: Create the study YAML**

```yaml
# studies/hra-atlas-browser/study.yaml
schema_version: 4
name: hra-atlas-browser
investigation: hra-3d
title: "HRA Atlas Browser — organ selector + model-count gradient + BioModels links"
created: '2026-08-01'
status: running
design_status: complete
implementation_status: complete
simulation_status: ran
phase: Evaluate

question: |
  Can we present the full HRA-3D model-coverage picture as an interactive
  atlas: pick any of the 50 GLB-backed HRA organs, see its regions
  demarcated and colored by how many mechanistic models are associated with
  it, and browse straight to those BioModels?

study_card:
  goal: "Cross the corpus catalog's organ_index (50 GLB organs) with organ_to_models into an atlas manifest, and render it as a self-contained three.js organ browser with a model-count color gradient and clickable BioModels."
  mechanism: "build_atlas_manifest(load_corpus_catalog()) -> atlas.json (per-organ n_models + BioModels links) + build_corpus_coverage -> coverage.json -> viz/atlas/ three.js viewer (organ <select>, per-mesh EdgesGeometry outlines, log-scaled count color, BioModels side panel)."
  expected_result: "All 50 organs selectable; 10 modeled organs colored by count (pancreas 36 brightest), 40 greyed; each organ's BioModels list links to ebi.ac.uk/biomodels."
  main_expert_question: "Is an organ-granularity model-count gradient a useful whole-atlas overview of where mechanistic modeling exists, given it cannot yet distinguish sub-regions within one organ?"

biological_summary: |
  Mechanistic models cluster on a handful of organs (pancreas, blood, liver,
  lung, brain, heart) and leave most of the body's 3D anatomy unmodeled. The
  Atlas Browser makes that distribution legible: the color gradient shows
  where modeling effort has concentrated, and the greyed organs make the
  modeling white-space visible at a glance.

readouts:
  - "atlas manifest: n_organs (50), n_modeled (10), n_models_total, max_models (36)"
  - "per-organ n_models + BioModels id/name/url list"

report:
  title: "HRA Atlas Browser — 10/50 organs modeled, pancreas dominant"
  verdict: passing-with-caveats
  confidence: high
  evidence_quality: measured
  objective: |
    Present HRA-3D model coverage as an interactive organ browser with a
    model-count gradient and BioModels links.
  conclusion: |
    The atlas manifest covers all 50 GLB-backed HRA organs; 10 carry ≥1
    model (pancreas 36, blood 19, liver 9, lung 6, brain 5, heart 4,
    adipose 2, intestine 2, skin 1, kidney 1), 40 are greyed. Each modeled
    organ links to its BioModels entries. The gradient is organ-granularity:
    it shows where modeling exists across the body but does not yet
    distinguish sub-regions within an organ.
  caveat: |
    Coverage is organ-granularity — every sub-region of a modeled organ
    inherits the organ's count, so the within-organ gradient is uniform.
    True per-anatomical-structure counts are the fp-as-level-coverage
    follow-up.

embed_visualizations: []

runs:
  - name: baseline
    status: completed

findings:
  - id: F-01
    tier: interpretation
    mechanism_origin: engineered
    claim_scope: mechanism
    statement: |
      The atlas manifest enumerates all 50 GLB-backed HRA organs and colors
      the 10 modeled ones by model count (pancreas 36 max), linking each to
      its BioModels entries — a whole-atlas overview of where mechanistic
      modeling exists.
    evidence:
      summary: "50 organs, 10 modeled (n_models_total from organ_to_models), max_models=36 (pancreas); 40 organs greyed (no models)."

limitations:
  - "Organ-granularity gradient: sub-regions within an organ share the organ's count (no per-AS-node resolution yet)."
  - "Organ tagging is name-synonym-based (see hra-integration); untagged models may hide real organ relevance."

discovery_implications:
  resolved_uncertainties:
    - "The full 50-organ GLB set is enumerable and renderable with a per-organ model-count gradient and BioModels links."
  remaining_uncertainties:
    - "Can sub-region (AS-level) counts replace organ-granularity coloring? See fp-as-level-coverage."
  followup_study_proposals:
    - id: fp-as-level-coverage
      title: "AS-level (sub-organ) model coverage in the Atlas Browser"
      motivation: "Color sub-regions within an organ by their own model count instead of inheriting the organ's count."
      study_type: method-upgrade
      proposed_experiment: "Parse SBML MIRIAM/Uberon annotations at anatomical-structure granularity, join to crosswalk AS nodes, and drive per-mesh color from per-node counts."
      expected_information_gain: high
      source_trigger: hra-atlas-browser
```

- [ ] **Step 4: Register the study + refresh the hra-3d investigation**

In `investigations/hra-3d/investigation.yaml`, add `hra-atlas-browser` to the `studies:` list, and append to `executive.verdict` (one sentence): `"An interactive Atlas Browser (hra-atlas-browser) now presents all 50 GLB-backed organs with a per-organ model-count gradient and BioModels links."` Add a matching acceptance criterion:

```yaml
  - study: hra-atlas-browser
    behavior: "The atlas manifest enumerates all GLB-backed HRA organs, colors the modeled ones by model count, and links each to its BioModels entries."
```

- [ ] **Step 5: Add `investigation:` backref to every study.yaml**

For each `studies/*/study.yaml`, add the correct `investigation:` key (matching the investigation whose `studies:` list contains it). Mapping (from the investigation YAMLs):
- `hra-3d`: hra-3d-crosswalk, model-coverage-3d, spatial-linkage, ftu-glomerulus, corpus-coverage, ftu-model-coverage, ctpop-islet-parameterization, hra-atlas-browser
- `hra-integration`: hra-reference-organs, hra-cell-types, hra-anatomical-structures, glucose-biomodel-do
- `glucose-regulation`: glucose-regulation
- Any study not listed by an investigation (e.g. `blood-vasculature-network` if unlisted): set `investigation:` to the investigation that owns it per its own study content; if genuinely orphaned, add it to the closest investigation's `studies:` list in the same commit so the test's cross-check passes. Verify with: `grep -L "^investigation:" studies/*/study.yaml`.

- [ ] **Step 6: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_investigation_structure.py -q`
Expected: PASS (2 tests).

- [ ] **Step 7: Commit**

```bash
git add studies/hra-atlas-browser/study.yaml investigations/hra-3d/investigation.yaml \
        studies/*/study.yaml tests/test_investigation_structure.py
git commit -m "feat: hra-atlas-browser study + investigation back-references"
```

---

### Task 6: Full-suite verification + README pointer

**Files:**
- Modify: `README.md` (add an Atlas Browser bullet next to the 3D coverage viewer)

**Interfaces:**
- Consumes: everything above.
- Produces: green offline suite + a documented entry point.

- [ ] **Step 1: Run the full offline suite**

Run: `cd ~/code/viva-human-atlas--atlas-browser && .venv/bin/python -m pytest -m "not network" -q`
Expected: PASS, count ≥ the Task 0 baseline + the new tests.

- [ ] **Step 2: Add a README pointer**

Under the existing "3D coverage viewer" note in `README.md`, add:
```markdown
🧭 **HRA Atlas Browser (organ selector, model-count gradient, BioModels links):**
`studies/hra-atlas-browser/viz/atlas/index.html` — pick any of the 50
GLB-backed HRA organs, see its regions colored by associated model count,
and click through to BioModels. Built by `scripts/build_atlas_pack.py`;
launchable from the Analyses tab as "HRA Atlas Browser".
```

- [ ] **Step 3: Verify the branch has only your commits**

Run: `git log --oneline origin/main..HEAD`
Expected: only the atlas-browser commits (spec, deps, tasks 1–6). Any foreign commit → stop, rebuild the branch from a clean worktree off `origin/main`.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: point to the HRA Atlas Browser"
```

---

## Self-Review

**Spec coverage:**
- Organ selector (50 organs) → Task 1 (manifest) + Task 3 (dropdown). ✓
- Regions demarcated → Task 3 (`EdgesGeometry` outlines + hover). ✓
- Color by model count → Task 1 (`n_models`/`max_models`) + Task 3 (`countColor`). ✓
- BioModels panel + links → Task 1 (`models[].url`) + Task 3 (`renderBioModels`). ✓
- Whole-body overview landing → Task 2 (`overview_glb` in config) + Task 3b (default landing = overview, colors each organ node by count, click-to-drill-in, falls back to top organ if the united GLB fails). ✓
- Enrich data (all 50 organs, names, links) → Task 1. ✓
- Workbench integration → Task 4. ✓
- New study + investigation refinement + back-refs → Task 5. ✓
- Deps refresh from origin/main → Task 0. ✓
- Testing (offline builder + shape + viewer assets + workbench + structure) → Tasks 1–5. ✓

**Placeholder scan:** No TBD/TODO; all code steps carry real code. ✓

**Type consistency:** `build_atlas_manifest`/`write_atlas_pack`/`biomodels_url` signatures match across Tasks 1–3; `atlas.json` keys (`organs`, `max_models`, `summary`, per-organ `key/label/uberon/glb/n_models/models`) identical in builder, viewer, and tests; `_studies_with_atlas`/`_atlas_targets`/`_atlas_launch` consistent in Task 4. ✓

**Note on landing view:** Task 3 builds the single-organ machinery and lands on the top organ so it is independently testable; Task 3b then makes the whole-body overview the default landing (the confirmed decision) with a fallback to the top organ if the united GLB fails to load. Splitting this way keeps each task independently reviewable.
