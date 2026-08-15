# HRA Atlas Build Pipeline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the loose atlas-build scripts into stage-level process-bigraph Steps, wire them into one connected composite runnable end-to-end, and prove it reproducibly regenerates the committed `atlas.json` offline.

**Architecture:** Add three `Step` subclasses (`GeneEnrichStep`, `HRApopEnrichStep`, `BtoCrosswalkStep`) that wrap the existing real enrichment/crosswalk functions — auto-discovered into the modules tab by `core.build_core`'s package walk. Add an `atlas_pipeline` `@composite_generator` that wires `ModelHarvestStep → GeneEnrichStep → HRApopEnrichStep → ComputationalModelAtlas` (with `AsctbTablesStep` feeding gene enrichment), passing the DB path through per-stage stores. Every pipeline Step gets a uniform `live` param (default `false`) that replays the committed datasets deterministically.

**Tech Stack:** Python, `process_bigraph.Step`, `viva_superpowers.composite_generator`, pytest.

**Spec:** `docs/superpowers/specs/2026-08-15-atlas-pipeline-composite-design.md`

## Global Constraints

- Steps live under `viva_human_atlas/` so `core.build_core` (`core.py:42`) auto-registers them by dotted path + short name — no manifest edit.
- Wrap the **real** functions (no mocks, no reimplementation). Follow the existing Step convention: `config_schema`, `inputs()`, `outputs()`, `update()`, a module-level `<Class>.contract = {...}`, and emit a summary + counts (never the raw DB).
- Composite-generator import, copied verbatim from `composites/annotation_composite.py`:
  ```python
  try:
      from viva_superpowers.composite_generator import composite_generator
  except ModuleNotFoundError:
      from pbg_superpowers.composite_generator import composite_generator
  ```
- Step addresses in composites use the `local:viva_human_atlas.<module>.<Class>` form.
- `live` param default is `false` everywhere: off = load committed dataset + emit counts (idempotent, no rewrite); on = re-harvest/re-enrich from APIs and rewrite the dataset.
- Tests run offline (`live=false`). Run tests with the worktree on `PYTHONPATH` (editable install points at the canonical checkout): `PYTHONPATH=/Users/eranagmon/code/viva-human-atlas--atlas-pipeline pytest ...`. Verify with `python -c "import viva_human_atlas, sys; print(viva_human_atlas.__file__)"` → must be under the worktree.
- Reproducibility tests write the atlas pack to a **temp** `out_dir` — never clobber the committed `studies/hra-atlas-browser/viz/atlas/`.

---

### Task 1: Lift `enrich_hrapop` into an importable module function

**Files:**
- Create: `viva_human_atlas/enrich_hrapop.py`
- Modify: `scripts/enrich_hrapop.py` (become a thin CLI over the module fn)
- Test: `tests/test_enrich_hrapop_module.py`

**Interfaces:**
- Produces: `enrich_hrapop_map(db_path: str, hrapop_csv: str | None = None, top: int | None = None) -> tuple[int, int]` returning `(n_total, n_linked)`; rewrites `db_path` in place, adding/removing each entry's `hra_pop` field. Same behavior as today's `scripts/enrich_hrapop.py::enrich`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_enrich_hrapop_module.py
import json
from pathlib import Path
from viva_human_atlas.enrich_hrapop import enrich_hrapop_map

def test_enrich_hrapop_map_adds_hra_pop(tmp_path):
    # An entry whose organ HRApop covers should gain an hra_pop field.
    db = tmp_path / "db.json"
    db.write_text(json.dumps([
        {"biomodel_id": "M1", "organs": [{"label": "kidney", "uberon": "UBERON:0002113"}]},
    ]), encoding="utf-8")
    total, linked = enrich_hrapop_map(str(db))
    assert total == 1
    out = json.loads(db.read_text(encoding="utf-8"))
    assert linked >= 0                      # linked is 0 or 1 depending on HRApop coverage
    assert ("hra_pop" in out[0]) == (linked == 1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=$PWD pytest tests/test_enrich_hrapop_module.py -v`
Expected: FAIL with `ModuleNotFoundError: viva_human_atlas.enrich_hrapop`

- [ ] **Step 3: Write minimal implementation**

Create `viva_human_atlas/enrich_hrapop.py` by moving the body of `scripts/enrich_hrapop.py::enrich` into it (rename to `enrich_hrapop_map`), keeping the atomic tmp-write:

```python
"""HRApop cell-population enrichment of the BioModels->HRA DB (Stage C).

Adds an `hra_pop` field to each model whose organ(s) HRApop covers — the
measured cell-type composition of that organ from HRApop. Importable core so
the CLI (scripts/enrich_hrapop.py) and the HRApopEnrichStep share one path and
cannot diverge (same pattern as biomodel_hra / scripts/build_biomodel_hra_map).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from viva_human_atlas.hra_pop import load_hrapop, hrapop_for_organs


def enrich_hrapop_map(db_path: str, hrapop_csv: str | None = None,
                      top: int | None = None) -> tuple[int, int]:
    entries = json.loads(Path(db_path).read_text(encoding="utf-8"))
    hrapop = load_hrapop(hrapop_csv)
    n = 0
    for e in entries:
        organs = [o["label"] for o in e.get("organs", []) if o.get("label")]
        hp = hrapop_for_organs(organs, hrapop, top=top)
        if hp:
            e["hra_pop"] = hp
            n += 1
        elif "hra_pop" in e:
            del e["hra_pop"]
    tmp = Path(db_path).with_suffix(".json.tmp")
    tmp.write_text(json.dumps(entries, indent=2), encoding="utf-8")
    os.replace(tmp, db_path)
    return len(entries), n
```

Then rewrite `scripts/enrich_hrapop.py` so `enrich` delegates (keep the CLI + `main` intact for back-compat):

```python
from viva_human_atlas.enrich_hrapop import enrich_hrapop_map

def enrich(db_path: str, hrapop_csv=None, top=None) -> tuple[int, int]:
    return enrich_hrapop_map(db_path, hrapop_csv, top)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=$PWD pytest tests/test_enrich_hrapop_module.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add viva_human_atlas/enrich_hrapop.py scripts/enrich_hrapop.py tests/test_enrich_hrapop_module.py
git commit -m "refactor: lift HRApop enrichment into importable enrich_hrapop_map"
```

---

### Task 2: `GeneEnrichStep` (Stage B) in `enrich.py`

**Files:**
- Modify: `viva_human_atlas/enrich.py` (append the Step + contract)
- Test: `tests/test_gene_enrich_step.py`

**Interfaces:**
- Consumes: `enrich.enrich_map` (existing), `asctb_tables.build_gene_uberon_index` (`asctb_tables.py:146`), `biomodel_hra.load_map`/`summarize_map` (`biomodel_hra.py:278,310`), `biomodel_do.build_organ_index` (`biomodel_do.py:45`).
- Produces: `GeneEnrichStep` (subclass of `process_bigraph.Step`). Ports: `inputs() -> {"db_path": "string", "asctb_path": "string"}`, `outputs() -> {"db_path": "string", "n_models_enriched": "integer", "n_gene_uberons_added": "integer", "summary": "tree"}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_gene_enrich_step.py
from viva_human_atlas.enrich import GeneEnrichStep

def test_gene_enrich_step_offline_counts_committed_db():
    step = GeneEnrichStep({"db_path": "datasets/model_hra_map.json",
                           "asctb_path": "datasets/asctb_tables.json",
                           "live": False})
    out = step.update({})
    assert out["db_path"] == "datasets/model_hra_map.json"     # passthrough
    assert out["n_models_enriched"] > 0                         # committed DB is enriched
    assert "summary" in out

def test_gene_enrich_step_registered_in_modules():
    from viva_human_atlas.core import build_core
    core = build_core()
    assert core.access("viva_human_atlas.enrich.GeneEnrichStep") is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=$PWD pytest tests/test_gene_enrich_step.py -v`
Expected: FAIL with `ImportError: cannot import name 'GeneEnrichStep'`

- [ ] **Step 3: Write minimal implementation**

Append to `viva_human_atlas/enrich.py`:

```python
import json
from pathlib import Path
from process_bigraph import Step

from viva_human_atlas.biomodel_hra import load_map, summarize_map
from viva_human_atlas.asctb_tables import build_gene_uberon_index

_REPO = Path(__file__).resolve().parents[1]
_DEFAULT_DB = str(_REPO / "datasets" / "model_hra_map.json")
_DEFAULT_ASCTB = str(_REPO / "datasets" / "asctb_tables.json")


class GeneEnrichStep(Step):
    """Step: enrich the BioModels->HRA DB with organism + gene ids + gene->Uberon
    anatomy (Stage B). live=false replays the committed (already-enriched) DB and
    emits its counts; live=true re-runs enrich_map and rewrites the DB."""

    description = (
        "Enrich each model with its organism (from NCBITaxon), HGNC/Ensembl "
        "genes (from UniProt), and gene-derived Uberon anatomy (via the ASCT+B "
        "gene->Uberon index), re-mapped to HRA organs/FTUs/cell types. Emits "
        "how many models carry gene ids and gene-derived anatomy."
    )

    config_schema = {
        "db_path": "string", "asctb_path": "string",
        "live": "boolean", "cache_dir": "string",
    }

    def inputs(self):
        return {"db_path": "string", "asctb_path": "string"}

    def outputs(self):
        return {"db_path": "string", "n_models_enriched": "integer",
                "n_gene_uberons_added": "integer", "summary": "tree"}

    def update(self, inputs):
        db_path = inputs.get("db_path") or self.config.get("db_path") or _DEFAULT_DB
        asctb_path = inputs.get("asctb_path") or self.config.get("asctb_path") or _DEFAULT_ASCTB
        if self.config.get("live"):
            from viva_human_atlas.enrich import enrich_map
            from viva_human_atlas.biomodel_do import build_organ_index
            tables = json.loads(Path(asctb_path).read_text(encoding="utf-8"))
            gene_index = build_gene_uberon_index(tables)
            entries = load_map(db_path)
            enrich_map(entries, gene_index=gene_index, organ_index=build_organ_index(),
                       cache_dir=self.config.get("cache_dir") or None)
            Path(db_path).write_text(json.dumps(list(entries), indent=2), encoding="utf-8")
        else:
            entries = load_map(db_path)
        n_enriched = sum(1 for e in entries if (e.get("molecular_ids") or {}).get("hgnc"))
        n_gene_uberon = sum(1 for e in entries if (e.get("ontology_ids") or {}).get("uberon"))
        return {
            "db_path": str(db_path),
            "n_models_enriched": n_enriched,
            "n_gene_uberons_added": n_gene_uberon,
            "summary": summarize_map(entries),
        }


GeneEnrichStep.contract = {
    "summary": GeneEnrichStep.description,
    "outputs": {
        "db_path": "Passthrough path to the (rewritten if live) DB.",
        "n_models_enriched": "Models carrying HGNC gene ids.",
        "n_gene_uberons_added": "Models carrying (gene-derived) Uberon anatomy.",
        "summary": "summarize_map coverage summary of the DB.",
    },
    "assumptions": [
        "live=false is the reproducible default: the committed DB is already "
        "enriched, so this loads and counts it without network. live=true "
        "makes UniProt + NCBITaxon calls (disk-cached) and rewrites the DB.",
    ],
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=$PWD pytest tests/test_gene_enrich_step.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add viva_human_atlas/enrich.py tests/test_gene_enrich_step.py
git commit -m "feat: GeneEnrichStep wraps Stage B gene/organism enrichment"
```

---

### Task 3: `HRApopEnrichStep` (Stage C) in `enrich_hrapop.py`

**Files:**
- Modify: `viva_human_atlas/enrich_hrapop.py` (append the Step + contract)
- Test: `tests/test_hrapop_enrich_step.py`

**Interfaces:**
- Consumes: `enrich_hrapop.enrich_hrapop_map` (Task 1), `biomodel_hra.load_map`.
- Produces: `HRApopEnrichStep`. Ports: `inputs() -> {"db_path": "string"}`, `outputs() -> {"db_path": "string", "n_models_linked": "integer", "summary": "tree"}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_hrapop_enrich_step.py
from viva_human_atlas.enrich_hrapop import HRApopEnrichStep

def test_hrapop_enrich_step_offline_counts_committed_db():
    step = HRApopEnrichStep({"db_path": "datasets/model_hra_map.json", "live": False})
    out = step.update({})
    assert out["db_path"] == "datasets/model_hra_map.json"
    assert out["n_models_linked"] >= 0
    assert "summary" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=$PWD pytest tests/test_hrapop_enrich_step.py -v`
Expected: FAIL with `ImportError: cannot import name 'HRApopEnrichStep'`

- [ ] **Step 3: Write minimal implementation**

Append to `viva_human_atlas/enrich_hrapop.py`:

```python
from process_bigraph import Step
from viva_human_atlas.biomodel_hra import load_map, summarize_map

_REPO = Path(__file__).resolve().parents[1]
_DEFAULT_DB = str(_REPO / "datasets" / "model_hra_map.json")
_DEFAULT_HRAPOP = str(_REPO / "datasets" / "hrapop_as_cell_populations.csv")


class HRApopEnrichStep(Step):
    """Step: link each model to its organ's HRApop cell-type population (Stage C).
    live=false counts the committed DB's existing hra_pop links; live=true re-runs
    enrich_hrapop_map and rewrites the DB."""

    description = (
        "Attach HRApop measured cell-type populations to each model whose "
        "organ(s) HRApop covers. Emits how many models were linked."
    )

    config_schema = {"db_path": "string", "hrapop_csv": "string", "live": "boolean"}

    def inputs(self):
        return {"db_path": "string"}

    def outputs(self):
        return {"db_path": "string", "n_models_linked": "integer", "summary": "tree"}

    def update(self, inputs):
        db_path = inputs.get("db_path") or self.config.get("db_path") or _DEFAULT_DB
        hrapop_csv = self.config.get("hrapop_csv") or None
        if self.config.get("live"):
            _total, n_linked = enrich_hrapop_map(db_path, hrapop_csv)
        else:
            n_linked = sum(1 for e in load_map(db_path) if e.get("hra_pop"))
        entries = load_map(db_path)
        return {
            "db_path": str(db_path),
            "n_models_linked": n_linked,
            "summary": summarize_map(entries),
        }


HRApopEnrichStep.contract = {
    "summary": HRApopEnrichStep.description,
    "outputs": {
        "db_path": "Passthrough path to the (rewritten if live) DB.",
        "n_models_linked": "Models linked to an HRApop cell-type population.",
        "summary": "summarize_map coverage summary of the DB.",
    },
    "assumptions": [
        "live=false counts the committed DB's existing hra_pop links (offline, "
        "reproducible). live=true re-runs the HRApop join and rewrites the DB.",
    ],
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=$PWD pytest tests/test_hrapop_enrich_step.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add viva_human_atlas/enrich_hrapop.py tests/test_hrapop_enrich_step.py
git commit -m "feat: HRApopEnrichStep wraps Stage C HRApop linkage"
```

---

### Task 4: `BtoCrosswalkStep` in `bto_crosswalk.py`

**Files:**
- Modify: `viva_human_atlas/bto_crosswalk.py` (append the Step + contract)
- Test: `tests/test_bto_crosswalk_step.py`

**Interfaces:**
- Consumes: `bto_crosswalk.build_bto_uberon_crosswalk(bto_terms: dict, organ_index: dict) -> dict` (`bto_crosswalk.py:66`), `biomodel_do.build_organ_index`.
- Produces: `BtoCrosswalkStep`. Ports: `inputs() -> {}`, `outputs() -> {"out_path": "string", "n_terms": "integer", "n_mapped": "integer", "summary": "tree"}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_bto_crosswalk_step.py
from viva_human_atlas.bto_crosswalk import BtoCrosswalkStep

def test_bto_crosswalk_step_offline_loads_committed():
    step = BtoCrosswalkStep({"out_path": "datasets/bto_uberon_crosswalk.json", "live": False})
    out = step.update({})
    assert out["out_path"] == "datasets/bto_uberon_crosswalk.json"
    assert out["n_terms"] > 0
    assert out["n_mapped"] >= 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=$PWD pytest tests/test_bto_crosswalk_step.py -v`
Expected: FAIL with `ImportError: cannot import name 'BtoCrosswalkStep'`

- [ ] **Step 3: Write minimal implementation**

Append to `viva_human_atlas/bto_crosswalk.py` (adjust the mapped-count key to whatever `build_bto_uberon_crosswalk` returns — inspect its return dict; the crosswalk maps BTO id → {uberon:[...]}):

```python
import json
from pathlib import Path
from process_bigraph import Step
from viva_human_atlas.biomodel_do import build_organ_index

_REPO = Path(__file__).resolve().parents[1]
_DEFAULT_BTO = str(_REPO / "datasets" / "bto_terms.json")
_DEFAULT_OUT = str(_REPO / "datasets" / "bto_uberon_crosswalk.json")


class BtoCrosswalkStep(Step):
    """Step: build (or load) the BTO->Uberon crosswalk that feeds the harvest
    crosswalk sub-stage. live=false loads the committed crosswalk; live=true
    rebuilds it from datasets/bto_terms.json + the organ index."""

    description = (
        "Build the BTO->Uberon anatomy crosswalk (Brenda Tissue Ontology terms "
        "mapped to Uberon via the organ index) used when harvesting each "
        "model's annotation-derived anatomy. Emits term/mapping counts."
    )

    config_schema = {"bto_terms_path": "string", "out_path": "string", "live": "boolean"}

    def inputs(self):
        return {}

    def outputs(self):
        return {"out_path": "string", "n_terms": "integer",
                "n_mapped": "integer", "summary": "tree"}

    def update(self, inputs):
        out_path = self.config.get("out_path") or _DEFAULT_OUT
        if self.config.get("live"):
            bto_terms = json.loads(Path(self.config.get("bto_terms_path") or _DEFAULT_BTO).read_text(encoding="utf-8"))
            crosswalk = build_bto_uberon_crosswalk(bto_terms, build_organ_index())
            Path(out_path).write_text(json.dumps(crosswalk, indent=2, sort_keys=True), encoding="utf-8")
        else:
            crosswalk = json.loads(Path(out_path).read_text(encoding="utf-8"))
        n_mapped = sum(1 for v in crosswalk.values() if (v.get("uberon") if isinstance(v, dict) else v))
        return {
            "out_path": str(out_path),
            "n_terms": len(crosswalk),
            "n_mapped": n_mapped,
            "summary": {"n_terms": len(crosswalk), "n_mapped": n_mapped},
        }


BtoCrosswalkStep.contract = {
    "summary": BtoCrosswalkStep.description,
    "outputs": {
        "out_path": "Path to the BTO->Uberon crosswalk JSON.",
        "n_terms": "Number of BTO terms in the crosswalk.",
        "n_mapped": "BTO terms that resolved to >=1 Uberon.",
        "summary": "term/mapping counts.",
    },
    "assumptions": [
        "This Step is an upstream feeder to the harvest crosswalk sub-stage; it "
        "appears in the modules tab for reuse but is not wired into the main "
        "atlas_pipeline composite (harvest reads the committed crosswalk from "
        "disk). live=false loads the committed crosswalk offline.",
    ],
}
```

**Before Step 4, verify** the mapped-count expression against the real return shape of `build_bto_uberon_crosswalk` (read `bto_crosswalk.py:66` and the committed `datasets/bto_uberon_crosswalk.json`); fix `n_mapped` to match its actual value type.

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=$PWD pytest tests/test_bto_crosswalk_step.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add viva_human_atlas/bto_crosswalk.py tests/test_bto_crosswalk_step.py
git commit -m "feat: BtoCrosswalkStep wraps the BTO->Uberon crosswalk builder"
```

---

### Task 5: Add a `db_path` input port to `ComputationalModelAtlas`

**Files:**
- Modify: `viva_human_atlas/atlas_browser.py:52-77` (the `inputs()` + `update()` of `ComputationalModelAtlas`)
- Test: `tests/test_atlas_db_path_port.py`

**Interfaces:**
- Produces: `ComputationalModelAtlas.inputs() -> {"db_path": "string"}` (was `{}`); `update()` prefers `inputs["db_path"]` over `config["db_path"]`. Default behavior (no wired input) unchanged.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_atlas_db_path_port.py
from viva_human_atlas.atlas_browser import ComputationalModelAtlas

def test_atlas_declares_db_path_input_port():
    step = ComputationalModelAtlas({})
    assert step.inputs() == {"db_path": "string"}

def test_atlas_input_db_path_overrides_config(tmp_path):
    # Wired input path takes precedence over config; assert it reaches build.
    step = ComputationalModelAtlas({"db_path": "config_path.json",
                                    "out_dir": str(tmp_path)})
    seen = {}
    import viva_human_atlas.atlas_browser as ab
    orig = ab.build_and_write_atlas
    ab.build_and_write_atlas = lambda **kw: (seen.update(kw) or
        {"summary": {}, "placement_stats": {}})
    try:
        step.update({"db_path": "wired_path.json"})
    finally:
        ab.build_and_write_atlas = orig
    assert seen["db_path"] == "wired_path.json"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=$PWD pytest tests/test_atlas_db_path_port.py -v`
Expected: FAIL — `inputs()` returns `{}`, and the override assertion fails.

- [ ] **Step 3: Write minimal implementation**

In `viva_human_atlas/atlas_browser.py`, change `inputs()` and the `db_path` resolution in `update()`:

```python
    def inputs(self):
        return {"db_path": "string"}

    def update(self, inputs):
        out_dir = self.config.get("out_dir") or str(DEFAULT_OUT_DIR)
        db_path = inputs.get("db_path") or self.config.get("db_path") or None
        # ... unchanged place_kw block ...
        result = build_and_write_atlas(
            db_path=db_path,
            catalog_path=self.config.get("catalog_path") or str(DEFAULT_CATALOG),
            out_dir=out_dir,
            **place_kw,
        )
        # ... unchanged return ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=$PWD pytest tests/test_atlas_db_path_port.py tests/test_atlas_pack.py -v`
Expected: PASS (existing `test_atlas_pack.py` still green — default path unchanged when no input wired).

- [ ] **Step 5: Commit**

```bash
git add viva_human_atlas/atlas_browser.py tests/test_atlas_db_path_port.py
git commit -m "feat: ComputationalModelAtlas accepts db_path input port for composite wiring"
```

---

### Task 6: `atlas_pipeline` composite generator (the connected DAG)

**Files:**
- Create: `viva_human_atlas/composites/atlas_pipeline.py`
- Modify: `viva_human_atlas/composites/__init__.py` (add the import)
- Test: `tests/test_atlas_pipeline_composite.py`

**Interfaces:**
- Consumes Step addresses: `local:viva_human_atlas.model_harvest.ModelHarvestStep`, `local:viva_human_atlas.asctb_tables.AsctbTablesStep`, `local:viva_human_atlas.enrich.GeneEnrichStep`, `local:viva_human_atlas.enrich_hrapop.HRApopEnrichStep`, `local:viva_human_atlas.atlas_browser.ComputationalModelAtlas`.
- Produces: a `@composite_generator(name="hra-atlas-pipeline", ...)` → spec id `viva_human_atlas.composites.atlas_pipeline.hra-atlas-pipeline`. Document builder `build_atlas_pipeline_document(out_dir: str, live: bool = False) -> dict`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_atlas_pipeline_composite.py
import json
from pathlib import Path
from process_bigraph import Composite
from viva_human_atlas.core import build_core
from viva_human_atlas.composites.atlas_pipeline import build_atlas_pipeline_document

def _readouts(atlas_json_path):
    m = json.loads(Path(atlas_json_path).read_text(encoding="utf-8"))
    s = m.get("summary", m)
    return {k: s.get(k) for k in ("n_organs", "n_modeled", "n_models_distinct",
                                  "n_subregions", "n_organs_with_subregions")}

def test_pipeline_regenerates_committed_atlas_offline(tmp_path):
    committed = _readouts("studies/hra-atlas-browser/viz/atlas/atlas.json")
    doc = build_atlas_pipeline_document(out_dir=str(tmp_path), live=False)
    Composite(doc, core=build_core())
    regen = _readouts(str(tmp_path / "atlas.json"))
    assert regen == committed          # same artifacts, no hardcoded numbers

def test_pipeline_registered_as_composite_generator():
    core = build_core()
    assert any("hra-atlas-pipeline" in a for a in core.registry.list())  # generator present
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=$PWD pytest tests/test_atlas_pipeline_composite.py -v`
Expected: FAIL with `ModuleNotFoundError: ...composites.atlas_pipeline`

- [ ] **Step 3: Write minimal implementation**

Create `viva_human_atlas/composites/atlas_pipeline.py`. Wire per-stage stores so ordering is a DAG (distinct keys avoid a read-write-same-store cycle). Follow `annotation_composite.py`'s state/emitter shape exactly.

```python
"""Composite generator: the end-to-end HRA Computational Model Atlas build
pipeline, wired as a connectable Step DAG.

  ModelHarvestStep ─┐                                    (per-stage db_path stores)
                    ├→ GeneEnrichStep → HRApopEnrichStep → ComputationalModelAtlas → atlas.json
  AsctbTablesStep ──┘

live=false (default) replays the committed datasets and regenerates atlas.json
identically; live=true re-harvests/re-enriches from external APIs.
"""
from __future__ import annotations
from typing import Any, Dict

try:
    from viva_superpowers.composite_generator import composite_generator
except ModuleNotFoundError:
    from pbg_superpowers.composite_generator import composite_generator

HARVEST = "local:viva_human_atlas.model_harvest.ModelHarvestStep"
ASCTB = "local:viva_human_atlas.asctb_tables.AsctbTablesStep"
GENE = "local:viva_human_atlas.enrich.GeneEnrichStep"
HRAPOP = "local:viva_human_atlas.enrich_hrapop.HRApopEnrichStep"
ATLAS = "local:viva_human_atlas.atlas_browser.ComputationalModelAtlas"

DEFAULT_OUT_DIR = "studies/hra-atlas-browser/viz/atlas"


def build_atlas_pipeline_document(out_dir: str = DEFAULT_OUT_DIR,
                                  live: bool = False) -> Dict[str, Any]:
    emit_schema = {"atlas_summary": "tree", "placement_stats": "tree",
                   "gene_enrich_summary": "tree", "hrapop_summary": "tree"}
    state: Dict[str, Any] = {
        # stores wiring the DAG
        "db_harvested": "", "asctb_path": "", "db_gene": "", "db_hrapop": "",
        "atlas_summary": {}, "placement_stats": {},
        "gene_enrich_summary": {}, "hrapop_summary": {},
        "harvest_step": {
            "_type": "step", "address": HARVEST,
            "config": {"build_if_missing": bool(live)},
            "inputs": {},
            "outputs": {"db_path": ["db_harvested"]},
        },
        "asctb_step": {
            "_type": "step", "address": ASCTB,
            "config": {"force": bool(live)},
            "inputs": {},
            "outputs": {"out_path": ["asctb_path"]},
        },
        "gene_enrich_step": {
            "_type": "step", "address": GENE,
            "config": {"live": bool(live)},
            "inputs": {"db_path": ["db_harvested"], "asctb_path": ["asctb_path"]},
            "outputs": {"db_path": ["db_gene"], "summary": ["gene_enrich_summary"]},
        },
        "hrapop_step": {
            "_type": "step", "address": HRAPOP,
            "config": {"live": bool(live)},
            "inputs": {"db_path": ["db_gene"]},
            "outputs": {"db_path": ["db_hrapop"], "summary": ["hrapop_summary"]},
        },
        "atlas_step": {
            "_type": "step", "address": ATLAS,
            "config": {"out_dir": out_dir},
            "inputs": {"db_path": ["db_hrapop"]},
            "outputs": {"summary": ["atlas_summary"], "placement_stats": ["placement_stats"]},
        },
        "emitter": {
            "_type": "step", "address": "local:RAMEmitter",
            "config": {"emit": emit_schema},
            "inputs": {k: [k] for k in emit_schema},
        },
    }
    return {"state": state, "run_steps_on_init": True}


@composite_generator(
    name="hra-atlas-pipeline",
    description=(
        "End-to-end HRA Computational Model Atlas build: harvest models -> gene/"
        "organism enrichment -> HRApop linkage -> atlas pack, wired as a "
        "connectable Step DAG. Offline (live=false) it replays the committed "
        "datasets and regenerates atlas.json identically."
    ),
    parameters={
        "out_dir": {"type": "string", "default": DEFAULT_OUT_DIR,
                    "description": "Directory the atlas pack is written to."},
        "live": {"type": "boolean", "default": False,
                 "description": "Re-harvest/re-enrich from external APIs (may drift)."},
    },
    default_n_steps=1,
)
def build_atlas_pipeline(core: Any = None, *, out_dir: str = DEFAULT_OUT_DIR,
                         live: bool = False) -> Dict[str, Any]:
    return build_atlas_pipeline_document(out_dir=out_dir, live=live)
```

Add to `viva_human_atlas/composites/__init__.py`:

```python
from viva_human_atlas.composites import atlas_pipeline  # noqa: F401
```

**Note for implementer:** the `test_pipeline_registered_as_composite_generator` assertion (`core.registry.list()`) is a guess at the registry API — if `build_core()` exposes generators differently, adjust the assertion to the real accessor (grep `core.py` / `composites/__init__.py` for how `@composite_generator` entries land in the core). The offline-regeneration test is the load-bearing one.

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=$PWD pytest tests/test_atlas_pipeline_composite.py -v`
Expected: PASS — the offline pipeline writes `atlas.json` into tmp with readouts equal to the committed atlas.

- [ ] **Step 5: Commit**

```bash
git add viva_human_atlas/composites/atlas_pipeline.py viva_human_atlas/composites/__init__.py tests/test_atlas_pipeline_composite.py
git commit -m "feat: atlas_pipeline composite wires the full build DAG end-to-end"
```

---

### Task 7: Reproducibility (determinism) test

**Files:**
- Test: `tests/test_atlas_pipeline_reproducible.py`

**Interfaces:**
- Consumes: `build_atlas_pipeline_document` (Task 6).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_atlas_pipeline_reproducible.py
import json
from pathlib import Path
from process_bigraph import Composite
from viva_human_atlas.core import build_core
from viva_human_atlas.composites.atlas_pipeline import build_atlas_pipeline_document

def _atlas(out):
    return json.loads((Path(out) / "atlas.json").read_text(encoding="utf-8"))

def test_two_offline_runs_are_identical(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(); b.mkdir()
    Composite(build_atlas_pipeline_document(out_dir=str(a), live=False), core=build_core())
    Composite(build_atlas_pipeline_document(out_dir=str(b), live=False), core=build_core())
    # Prefer byte-identity; fall back to readout stats if float/key ordering churns.
    da = json.dumps(_atlas(a), sort_keys=True)
    db = json.dumps(_atlas(b), sort_keys=True)
    assert da == db
```

- [ ] **Step 2: Run test to verify it fails, then passes**

Run: `PYTHONPATH=$PWD pytest tests/test_atlas_pipeline_reproducible.py -v`
Expected: PASS immediately (no new production code — this validates Task 6's determinism). If it FAILS on ordering/floats, change the assertion to compare the five readout stats from Task 6's `_readouts` and add a code comment explaining the non-determinism source. Re-run until green.

- [ ] **Step 3: Commit**

```bash
git add tests/test_atlas_pipeline_reproducible.py
git commit -m "test: atlas pipeline regenerates atlas.json deterministically offline"
```

---

### Task 8: Showcase study + cross-links

**Files:**
- Create: `studies/atlas-pipeline/study.yaml`
- Modify: `studies/hra-atlas-browser/study.yaml`, `studies/biomodel-hra-map/study.yaml`, `studies/model-harvest/study.yaml` (one cross-link line each)
- Test: `tests/test_atlas_pipeline_study.py`

**Interfaces:**
- Consumes: the composite spec id from Task 6.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_atlas_pipeline_study.py
import yaml
from pathlib import Path

def test_study_references_the_pipeline_composite():
    s = yaml.safe_load(Path("studies/atlas-pipeline/study.yaml").read_text(encoding="utf-8"))
    assert s["schema_version"] == 4
    assert s["investigation"] == "hra-3d"
    assert "atlas_pipeline" in s["baseline"]["composite"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=$PWD pytest tests/test_atlas_pipeline_study.py -v`
Expected: FAIL — `studies/atlas-pipeline/study.yaml` does not exist.

- [ ] **Step 3: Author the study**

Prefer authoring via `/viva-study` (canonicalizes + adds provenance). If authoring the file directly, write `studies/atlas-pipeline/study.yaml` (schema_version 4, investigation `hra-3d`) with: `question`, `study_card` (goal/mechanism/expected_result presenting the DAG + each component's APIs from the spec's component list), `baseline.composite: viva_human_atlas.composites.atlas_pipeline.hra-atlas-pipeline`, a `report` block explaining the offline-replay reproducibility guarantee, and `embed_visualizations` reusing `/studies/hra-atlas-browser/viz/atlas/index.html`. Then add one line under each of the three existing studies' narrative pointing at `atlas-pipeline` as the end-to-end build.

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=$PWD pytest tests/test_atlas_pipeline_study.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add studies/atlas-pipeline/study.yaml studies/hra-atlas-browser/study.yaml studies/biomodel-hra-map/study.yaml studies/model-harvest/study.yaml tests/test_atlas_pipeline_study.py
git commit -m "docs: atlas-pipeline showcase study + cross-links to the build pipeline"
```

---

### Task 9: Full offline suite + report regen

- [ ] **Step 1: Run the whole suite offline**

Run: `PYTHONPATH=$PWD pytest tests/ -q`
Expected: PASS (no network). Investigate any failure before proceeding.

- [ ] **Step 2: Regenerate the dashboard/report**

Run `/viva-report` to render the new study + refresh the investigation report (Pass A reviewer audit, then render). Address any lint it raises.

- [ ] **Step 3: Commit any report/state changes**

```bash
git add -A && git commit -m "chore: regenerate report with atlas-pipeline study"
```

---

## Self-Review

**Spec coverage:**
- New stage-level Steps (spec §1) → Tasks 2, 3, 4 (+ Task 1 refactor enabling Task 3).
- Connected composite (spec §2) → Task 6 (+ Task 5 enabling the atlas port wiring).
- Reproducibility, offline-replay + live flag (spec §3) → `live` param in every Step (Tasks 2–4, 6) + Tasks 6/7 tests.
- Showcase study + cross-links (spec §4) → Task 8.
- Testing (spec §5) → per-Step tests (Tasks 1–5), end-to-end (Task 6), determinism (Task 7), full suite (Task 9).

**Placeholder scan:** Two tasks carry an explicit "verify against real return shape" note (Task 4 `n_mapped`, Task 6 registry-list assertion) rather than a guessed value — these are verification instructions, not placeholders; the load-bearing assertions (offline counts, atlas regeneration) are concrete.

**Type consistency:** `db_path` (string) is the store value threaded harvest→gene→hrapop→atlas; each new Step's `outputs()["db_path"]` matches the next's `inputs()["db_path"]`. `enrich_hrapop_map` signature is identical in Task 1 (definition) and Task 3 (call). `build_atlas_pipeline_document(out_dir, live)` signature matches across Tasks 6 and 7.

**Known soft spots the executor must confirm at runtime (not assumptions to trust blindly):** (a) the exact `atlas.json` top-level shape for `_readouts` (summary nested vs top-level) — inspect the committed file; (b) the composite registry accessor in Task 6's second test; (c) `build_bto_uberon_crosswalk`'s return value shape for `n_mapped`. Each is flagged inline at its task.
