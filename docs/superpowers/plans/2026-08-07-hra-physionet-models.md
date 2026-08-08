# PhysioNet Models in a Unified HRA Model DB — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add PhysioNet as a second, organ-mapped model source in a single source-agnostic HRA model DB, harvestable reproducibly via a viva Step/study and a CLI, and shown (badged + filterable) in the atlas viewer.

**Architecture:** Generalize the existing BioModels→HRA DB from `biomodel_id`-keyed to `identifier`-keyed so two sources share one file with non-destructive per-source upsert. A new PhysioNet module (DataCite `prefix:10.13026`) + a hybrid keyword/LLM organ mapper produce same-shaped entries. A source registry + `harvest()` orchestrate incremental multi-source harvesting, exposed as `ModelHarvestStep` (viva study baseline) and `scripts/harvest_models.py`. `atlas_pack` and the viewer become source-aware.

**Tech Stack:** Python 3, `requests`, `pytest` (markers `network` / `not network`), process-bigraph `Step`, existing `viva_human_atlas` modules (`hra_mapping`, `biomodel_do`, `llm_extract`), vanilla JS three.js viewer.

## Global Constraints

- Single DB file: `datasets/model_hra_map.json` (renamed from `biomodel_hra_map.json`). Entries keyed by `identifier`.
- Every entry carries `repository` (source label) and `source_id` (generic id). BioModels keeps `biomodel_id`; PhysioNet uses the content slug.
- Non-destructive invariant: harvesting one source never mutates or drops another source's rows.
- Offline-first: workspace reproduce is network-free (`build_if_missing=false`); live harvest is opt-in (`--force` / DataCite / LLM). `--no-llm` must fully work offline.
- Tests split by marker: pure-logic tests are `-m "not network"`; DataCite/LLM tests are `-m network`.
- PhysioNet DOI prefix is `10.13026`. PhysioNet content URL: `https://physionet.org/content/<slug>/`.
- Reuse, don't rebuild: organ binding goes through `hra_mapping.map_to_hra`; the organ index through `biomodel_do.build_organ_index`; LLM through `llm_extract.extract`.
- Run tests with the workspace venv: `.venv/bin/python -m pytest`.

---

### Task 1: Generalize the DB key from `biomodel_id` to `identifier`

Make the DB layer source-agnostic without changing BioModels behavior. This is the enabling change for one shared file.

**Files:**
- Modify: `viva_human_atlas/biomodel_hra.py` (`load_db`, `upsert_db`, `write_db`, `should_process`, `build_map` loop, `load_map` sort; add `source_id` to the biomodels entry dict in `build_entry`)
- Test: `tests/test_db_key_generalization.py`

**Interfaces:**
- Consumes: existing `build_entry`, `build_map`.
- Produces:
  - `load_db(path) -> dict[str, dict]` keyed by `entry["identifier"]` (accepts legacy `biomodel_id`-keyed lists/objects by re-keying on `identifier`).
  - `upsert_db(db, entry) -> None` keys on `entry["identifier"]`.
  - `write_db(db, path) -> None` sorts by `identifier`.
  - `should_process(db, key, force) -> bool` where `key` is an `identifier`.
  - `build_map(...)` internally iterates `identifier`s (see Step 3).
  - `build_entry(...)` output now also has `"source_id": biomodel_id`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_db_key_generalization.py
import json
from viva_human_atlas import biomodel_hra as bh


def _entry(identifier, source_id, errored=False):
    return {"identifier": identifier, "repository": "biomodels", "source_id": source_id,
            "biomodel_id": source_id, "name": source_id,
            "provenance": {"errors": (["x"] if errored else [])}}


def test_upsert_and_write_are_identifier_keyed(tmp_path):
    db = {}
    e = _entry("https://identifiers.org/biomodels.db:BIOMD0000000001", "BIOMD0000000001")
    bh.upsert_db(db, e)
    assert set(db) == {"https://identifiers.org/biomodels.db:BIOMD0000000001"}
    out = tmp_path / "model_hra_map.json"
    bh.write_db(db, out)
    data = json.loads(out.read_text())
    assert data[0]["identifier"] == "https://identifiers.org/biomodels.db:BIOMD0000000001"


def test_load_db_rekeys_legacy_list(tmp_path):
    p = tmp_path / "legacy.json"
    p.write_text(json.dumps([_entry("iri://A", "BIOMD_A"), _entry("iri://B", "BIOMD_B")]))
    db = bh.load_db(p)
    assert set(db) == {"iri://A", "iri://B"}


def test_should_process_by_identifier(tmp_path):
    db = {"iri://A": _entry("iri://A", "BIOMD_A"),
          "iri://B": _entry("iri://B", "BIOMD_B", errored=True)}
    assert bh.should_process(db, "iri://A", force=False) is False   # present, clean -> skip
    assert bh.should_process(db, "iri://B", force=False) is True    # present, errored -> redo
    assert bh.should_process(db, "iri://C", force=False) is True    # absent -> do
    assert bh.should_process(db, "iri://A", force=True) is True     # force -> do
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_db_key_generalization.py -v`
Expected: FAIL (upsert/load still keyed by `biomodel_id`; `should_process` still expects `bid`).

- [ ] **Step 3: Implement the generalization**

In `viva_human_atlas/biomodel_hra.py` replace the four DB functions:

```python
def upsert_db(db: dict, entry: dict) -> None:
    db[entry["identifier"]] = entry


def load_db(path) -> dict:
    """Internal representation is always `{identifier: entry}`; the on-disk file
    is a JSON array (see `write_db`). Legacy `biomodel_id`-keyed lists/objects are
    re-keyed on `identifier` so old-format DBs keep resuming."""
    p = Path(path)
    if not p.exists():
        return {}
    data = json.loads(p.read_text(encoding="utf-8"))
    entries = data if isinstance(data, list) else list(data.values())
    return {e["identifier"]: e for e in entries}


def write_db(db: dict, path) -> None:
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    ordered = sorted(db.values(), key=lambda e: e.get("identifier", ""))
    tmp.write_text(json.dumps(ordered, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def should_process(db: dict, key: str, force: bool) -> bool:
    if force:
        return True
    entry = db.get(key)
    if entry is None:
        return True
    return bool(entry.get("provenance", {}).get("errors"))
```

In the same file, update `load_map`'s sort key from `e.get("biomodel_id", "")` to `e.get("identifier", "")`.

In `build_entry`, add `"source_id": biomodel_id,` to the returned `entry` dict (right after the `"biomodel_id": biomodel_id,` line).

In `build_map`, the loop must key `should_process` by identifier while still fetching by `biomodel_id`. Change the loop body:

```python
    for i, bid in enumerate(ids, 1):
        identifier = _IRI.format(bid)
        if not should_process(db, identifier, force):
            continue
        try:
            upsert_db(db, build_entry(bid, organ_index, cache_dir=str(cache_dir),
                                      no_llm=no_llm, llm_model=llm_model))
        except Exception as e:  # noqa: BLE001 — never abort the whole run
            if progress:
                progress(f"  ERROR {bid}: {e}")
        if i % 10 == 0:
            write_db(db, out)
            if progress:
                progress(f"  {i}/{len(ids)} (db={len(db)})")
```

(`_IRI` is the existing module constant used for `entry["identifier"]`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_db_key_generalization.py -v`
Expected: PASS. Also run `.venv/bin/python -m pytest -m "not network" -q` to confirm no regression in existing biomodel_hra tests.

- [ ] **Step 5: Commit**

```bash
git add viva_human_atlas/biomodel_hra.py tests/test_db_key_generalization.py
git commit -m "refactor(db): key the model DB by identifier (source-agnostic), add source_id"
```

---

### Task 2: Rename the DB file to `model_hra_map.json` and update references

Mechanical, but its own reviewable unit because it touches several files and the committed dataset.

**Files:**
- Rename: `datasets/biomodel_hra_map.json` → `datasets/model_hra_map.json` (git mv)
- Modify: `viva_human_atlas/biomodel_hra.py` (`DEFAULT_DB_PATH`)
- Modify: `scripts/build_biomodel_hra_map.py`, `scripts/build_atlas_pack.py` (`DB_PATH`)
- Modify: `viva_human_atlas/atlas_pack.py` (any `biomodel_hra_map.json` literal)
- Modify: `studies/biomodel-hra-map/study.yaml`, `studies/hra-atlas-browser/study.yaml` (`db_path` params)
- Modify: `scripts/publish_dashboard.sh` (if it references the filename)

**Interfaces:**
- Produces: `DEFAULT_DB_PATH = _REPO / "datasets" / "model_hra_map.json"`.

- [ ] **Step 1: Find every reference**

Run: `git grep -n "biomodel_hra_map.json"`
Record the full list; each hit must be updated in Step 3.

- [ ] **Step 2: Rename the dataset (preserve history)**

```bash
git mv datasets/biomodel_hra_map.json datasets/model_hra_map.json
```

- [ ] **Step 3: Update every reference**

Change `DEFAULT_DB_PATH` in `viva_human_atlas/biomodel_hra.py` to `_REPO / "datasets" / "model_hra_map.json"`. Update each remaining `biomodel_hra_map.json` occurrence from Step 1 to `model_hra_map.json` (scripts' `DB_PATH`, the two studies' `db_path:` params, `publish_dashboard.sh`).

- [ ] **Step 4: Verify no stale references and the DB still loads**

Run: `git grep -n "biomodel_hra_map.json"` → Expected: **no output**.
Run: `.venv/bin/python -c "from viva_human_atlas.biomodel_hra import load_map; print(len(load_map()))"` → Expected: prints `1096` (the committed rows load under the new path/key).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: rename biomodel_hra_map.json -> model_hra_map.json (mixed-source DB)"
```

---

### Task 3: PhysioNet organ mapper (hybrid keyword table + LLM fallback)

**Files:**
- Create: `viva_human_atlas/physionet_organ_map.py`
- Test: `tests/test_physionet_organ_map.py`

**Interfaces:**
- Consumes: `hra_mapping.map_to_hra(uberon_ids, name, organ_index)`, `llm_extract.extract(name, abstract, fulltext, *, model, cache_dir)`.
- Produces:
  - `KEYWORD_TO_ORGAN: dict[str, list[str]]` — lowercase keyword → UBERON organ CURIEs.
  - `keyword_uberons(keywords, title) -> list[str]` — deterministic UBERON ids from keywords+title.
  - `map_project_to_organs(project, organ_index, *, no_llm=True, llm_model="claude-haiku-4-5-20251001", cache_dir=None, _llm=None) -> dict` — returns the `map_to_hra` dict (`organs`, `functional_tissue_units`, `cell_types`, ...) plus `"mapping_method": "keyword" | "llm" | "unmapped"`. `project` is `{"name", "keywords": [...], "abstract"}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_physionet_organ_map.py
from viva_human_atlas import physionet_organ_map as pom
from viva_human_atlas.biomodel_do import build_organ_index

ORGAN_INDEX = build_organ_index()


def test_keyword_table_maps_ecg_to_heart():
    ub = pom.keyword_uberons(["ecg", "arrhythmia"], "MIT-BIH Arrhythmia Database")
    assert "UBERON:0000948" in ub  # heart


def test_map_project_deterministic_no_llm():
    proj = {"name": "MIT-BIH Arrhythmia Database", "keywords": ["ecg", "arrhythmia"], "abstract": ""}
    out = pom.map_project_to_organs(proj, ORGAN_INDEX, no_llm=True)
    assert out["mapping_method"] == "keyword"
    assert any("heart" in (o.get("label", "") or "").lower() or o.get("uberon") == "UBERON:0000948"
               for o in out["organs"])


def test_unmapped_without_llm_is_marked():
    proj = {"name": "Totally Unknown Signal Set", "keywords": ["xyzzy"], "abstract": ""}
    out = pom.map_project_to_organs(proj, ORGAN_INDEX, no_llm=True)
    assert out["mapping_method"] == "unmapped"
    assert out["organs"] == []


def test_llm_fallback_used_when_keywords_miss():
    proj = {"name": "Cerebral Recording Set", "keywords": ["xyzzy"], "abstract": "intracranial brain signals"}
    calls = {}
    def fake_llm(name, abstract, fulltext, *, model, cache_dir=None):
        calls["hit"] = True
        return {"candidate_uberon": ["UBERON:0000955"]}  # brain
    out = pom.map_project_to_organs(proj, ORGAN_INDEX, no_llm=False, _llm=fake_llm)
    assert calls.get("hit") is True
    assert out["mapping_method"] == "llm"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_physionet_organ_map.py -v`
Expected: FAIL with `ModuleNotFoundError: viva_human_atlas.physionet_organ_map`.

- [ ] **Step 3: Implement the mapper**

```python
# viva_human_atlas/physionet_organ_map.py
"""Map a PhysioNet project to HRA organs: a curated physiology-keyword -> UBERON
organ table first (deterministic, offline), then the shared LLM organ-mapper as a
fallback for the unmapped tail. UBERON ids are bound to HRA organs via the same
`hra_mapping.map_to_hra` the BioModels path uses."""
from __future__ import annotations

from typing import Optional

from viva_human_atlas.hra_mapping import map_to_hra

DEFAULT_LLM_MODEL = "claude-haiku-4-5-20251001"

# lowercase keyword/substring -> UBERON organ CURIE(s), curated against the
# ~50 GLB-backed HRA reference organs the atlas viewer knows.
KEYWORD_TO_ORGAN: dict[str, list[str]] = {
    "ecg": ["UBERON:0000948"], "electrocardiogram": ["UBERON:0000948"],
    "arrhythmia": ["UBERON:0000948"], "cardiac": ["UBERON:0000948"],
    "heart": ["UBERON:0000948"], "ppg": ["UBERON:0000948"],
    "eeg": ["UBERON:0000955"], "electroencephalogram": ["UBERON:0000955"],
    "brain": ["UBERON:0000955"], "seizure": ["UBERON:0000955"], "sleep": ["UBERON:0000955"],
    "emg": ["UBERON:0001134"], "electromyogram": ["UBERON:0001134"], "muscle": ["UBERON:0001134"],
    "gait": ["UBERON:0002103"],
    "respiratory": ["UBERON:0002048"], "lung": ["UBERON:0002048"], "pulmonary": ["UBERON:0002048"],
    "eog": ["UBERON:0000970"], "retina": ["UBERON:0000966"], "eye": ["UBERON:0000970"],
    "renal": ["UBERON:0002113"], "kidney": ["UBERON:0002113"],
    "liver": ["UBERON:0002107"], "hepatic": ["UBERON:0002107"],
    "glucose": ["UBERON:0001264"], "pancreas": ["UBERON:0001264"], "diabetes": ["UBERON:0001264"],
    "skin": ["UBERON:0002097"], "eda": ["UBERON:0002097"],
}


def keyword_uberons(keywords, title: str) -> list[str]:
    hay = " ".join([*(keywords or []), title or ""]).lower()
    out: list[str] = []
    for kw, ubs in KEYWORD_TO_ORGAN.items():
        if kw in hay:
            out.extend(ubs)
    # stable de-dup
    return list(dict.fromkeys(out))


def map_project_to_organs(project: dict, organ_index: dict, *, no_llm: bool = True,
                          llm_model: str = DEFAULT_LLM_MODEL, cache_dir=None,
                          _llm=None) -> dict:
    title = project.get("name") or ""
    ubs = keyword_uberons(project.get("keywords") or [], title)
    method = "keyword" if ubs else None

    if not ubs and not no_llm:
        extract = _llm
        if extract is None:
            from viva_human_atlas import llm_extract
            extract = llm_extract.extract
        try:
            facts = extract(title, project.get("abstract") or "", None,
                            model=llm_model, cache_dir=cache_dir) or {}
            ubs = list(dict.fromkeys(facts.get("candidate_uberon") or []))
            if ubs:
                method = "llm"
        except Exception:  # noqa: BLE001 — fallback never aborts a harvest
            ubs = []

    if not ubs:
        return {"organs": [], "functional_tissue_units": [], "cell_types": [],
                "uberon_organ_ids": [], "uberon_subregion_ids": [], "mapping_method": "unmapped"}

    hra = map_to_hra(ubs, title, organ_index)
    hra["mapping_method"] = method or "keyword"
    return hra
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_physionet_organ_map.py -v`
Expected: PASS. (If a UBERON id in the table doesn't resolve to a GLB organ in `map_to_hra`, adjust that row to a covered organ id — the atlas viewer's organ set is the ground truth.)

- [ ] **Step 5: Commit**

```bash
git add viva_human_atlas/physionet_organ_map.py tests/test_physionet_organ_map.py
git commit -m "feat(physionet): hybrid keyword+LLM organ mapper over map_to_hra"
```

---

### Task 4: PhysioNet source module (DataCite enumeration + entry build)

**Files:**
- Create: `viva_human_atlas/physionet.py`
- Test: `tests/test_physionet.py`

**Interfaces:**
- Consumes: `physionet_organ_map.map_project_to_organs`, `biomodel_do.build_organ_index`.
- Produces:
  - `DATACITE_PREFIX = "10.13026"`, `DEFAULT_CACHE_DIR`.
  - `resolve_projects(*, query=None, limit=None, _get=requests.get) -> list[dict]` — each `{"slug", "identifier", "name", "keywords", "abstract", "doi", "year", "access"}` from DataCite `prefix:10.13026` (paged). `query` filters DataCite full-text; `limit` truncates.
  - `build_entry(project, organ_index, *, no_llm=True, llm_model=..., cache_dir=None, _map=None) -> dict` — the source-agnostic record (see code).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_physionet.py
from viva_human_atlas import physionet
from viva_human_atlas.biomodel_do import build_organ_index

ORGAN_INDEX = build_organ_index()

DATACITE_PAGE = {
    "data": [{
        "attributes": {
            "doi": "10.13026/c2f305",
            "titles": [{"title": "MIT-BIH Arrhythmia Database"}],
            "subjects": [{"subject": "ecg"}, {"subject": "arrhythmia"}],
            "descriptions": [{"description": "Two-channel ambulatory ECG recordings."}],
            "publicationYear": 2005,
            "rightsList": [{"rights": "Open Data Commons Attribution License v1.0"}],
            "url": "https://physionet.org/content/mitdb/1.0.0/",
        }
    }],
    "links": {},  # no "next" -> single page
}


def test_resolve_projects_parses_datacite(monkeypatch):
    class R:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return DATACITE_PAGE
    projects = physionet.resolve_projects(_get=lambda *a, **k: R())
    assert len(projects) == 1
    p = projects[0]
    assert p["slug"] == "mitdb"
    assert p["identifier"] == "https://physionet.org/content/mitdb/"
    assert p["keywords"] == ["ecg", "arrhythmia"]
    assert p["doi"] == "10.13026/c2f305"


def test_build_entry_shape_and_organ_mapping():
    proj = {"slug": "mitdb", "identifier": "https://physionet.org/content/mitdb/",
            "name": "MIT-BIH Arrhythmia Database", "keywords": ["ecg", "arrhythmia"],
            "abstract": "", "doi": "10.13026/c2f305", "year": 2005, "access": "open"}
    e = physionet.build_entry(proj, ORGAN_INDEX, no_llm=True)
    assert e["repository"] == "physionet"
    assert e["identifier"] == "https://physionet.org/content/mitdb/"
    assert e["source_id"] == "mitdb"
    assert e["paper_doi"] == "10.13026/c2f305"
    assert e["molecular_ids"] == {"chebi": [], "uniprot": [], "kegg": [], "go": [], "reactome": []}
    assert e["provenance"]["access"] == "open"
    assert e["organs"]  # ecg -> heart
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_physionet.py -v`
Expected: FAIL with `ModuleNotFoundError: viva_human_atlas.physionet`.

- [ ] **Step 3: Implement the module**

```python
# viva_human_atlas/physionet.py
"""PhysioNet as an HRA model source. Enumerate published projects + metadata from
DataCite (all PhysioNet DOIs share prefix 10.13026), then build source-agnostic
model records organ-mapped via `physionet_organ_map`. Mirrors `biomodel_hra`."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import requests

from viva_human_atlas.physionet_organ_map import DEFAULT_LLM_MODEL, map_project_to_organs

_REPO = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_DIR = _REPO / ".cache" / "physionet_hra_map"
DATACITE_PREFIX = "10.13026"
_DATACITE_URL = "https://api.datacite.org/dois"
_CONTENT = "https://physionet.org/content/{slug}/"

_ACCESS_FROM_RIGHTS = (  # crude open/restricted signal from the license string
    ("open", "open"), ("public domain", "open"),
    ("credential", "credentialed"), ("restricted", "restricted"),
)


def _slug_from_url(url: str) -> Optional[str]:
    m = re.search(r"/content/([^/]+)/", url or "")
    return m.group(1) if m else None


def _access(rights_list) -> str:
    text = " ".join((r.get("rights") or "") for r in (rights_list or [])).lower()
    for needle, label in _ACCESS_FROM_RIGHTS:
        if needle in text:
            return label
    return "open" if text else "unknown"


def _project_from_datacite(attrs: dict) -> Optional[dict]:
    url = attrs.get("url") or ""
    slug = _slug_from_url(url)
    if not slug:
        return None
    titles = attrs.get("titles") or [{}]
    descs = attrs.get("descriptions") or [{}]
    return {
        "slug": slug,
        "identifier": _CONTENT.format(slug=slug),
        "name": (titles[0].get("title") or slug).strip(),
        "keywords": [s.get("subject", "").strip().lower()
                     for s in (attrs.get("subjects") or []) if s.get("subject")],
        "abstract": (descs[0].get("description") or "").strip(),
        "doi": (attrs.get("doi") or "").lower() or None,
        "year": attrs.get("publicationYear"),
        "access": _access(attrs.get("rightsList")),
    }


def resolve_projects(*, query: Optional[str] = None, limit: Optional[int] = None,
                     _get=requests.get) -> list[dict]:
    """Enumerate PhysioNet projects (+ metadata) from DataCite prefix 10.13026,
    following pagination. `query` is passed to DataCite full-text; `limit` caps."""
    params = {"query": (f"prefix:{DATACITE_PREFIX}" + (f" AND {query}" if query else "")),
              "page[size]": 250}
    projects: list[dict] = []
    url = _DATACITE_URL
    while url:
        r = _get(url, params=params if url == _DATACITE_URL else None, timeout=60)
        r.raise_for_status()
        payload = r.json()
        for rec in payload.get("data", []):
            proj = _project_from_datacite(rec.get("attributes") or {})
            if proj:
                projects.append(proj)
                if limit and len(projects) >= limit:
                    return projects[:limit]
        url = (payload.get("links") or {}).get("next")
    return projects


def build_entry(project: dict, organ_index: dict, *, no_llm: bool = True,
                llm_model: str = DEFAULT_LLM_MODEL, cache_dir=None, _map=None) -> dict:
    mapper = _map or map_project_to_organs
    hra = mapper(project, organ_index, no_llm=no_llm, llm_model=llm_model, cache_dir=cache_dir)
    doi = project.get("doi")
    return {
        "identifier": project["identifier"],
        "repository": "physionet",
        "source_id": project["slug"],
        "name": project.get("name"),
        "paper_url": (f"https://doi.org/{doi}" if doi else project["identifier"]),
        "paper_pmid": None,
        "paper_doi": doi,
        "taxonomy": [],
        "organs": hra["organs"],
        "functional_tissue_units": hra["functional_tissue_units"],
        "cell_types": hra["cell_types"],
        "molecular_ids": {"chebi": [], "uniprot": [], "kegg": [], "go": [], "reactome": []},
        "ontology_ids": {"uberon": hra.get("uberon_organ_ids", []), "cl": [], "mesh": [],
                         "fma": [], "bto": []},
        "gene_symbols": [],
        "provenance": {
            "abstract": project.get("abstract"), "year": project.get("year"),
            "access": project.get("access"), "keywords": project.get("keywords") or [],
            "mapping_method": hra.get("mapping_method", "unmapped"), "errors": [],
        },
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_physionet.py -v`
Expected: PASS.

- [ ] **Step 5: Add a network smoke test + commit**

```python
# append to tests/test_physionet.py
import pytest

@pytest.mark.network
def test_datacite_live_enumerates_and_finds_mitdb():
    projects = physionet.resolve_projects(limit=300)
    assert len(projects) >= 100
    slugs = {p["slug"] for p in projects}
    assert "mitdb" in slugs
```

```bash
git add viva_human_atlas/physionet.py tests/test_physionet.py
git commit -m "feat(physionet): DataCite enumeration + source-agnostic entry build"
```

---

### Task 5: Source registry + multi-source `harvest()` (non-destructive)

**Files:**
- Create: `viva_human_atlas/model_harvest.py`
- Test: `tests/test_model_harvest.py`

**Interfaces:**
- Consumes: `biomodel_hra` (`resolve_ids`, `build_entry`, `load_db`, `upsert_db`, `write_db`, `should_process`, `build_organ_index`, `DEFAULT_DB_PATH`), `physionet` (`resolve_projects`, `build_entry`).
- Produces:
  - `SOURCES: dict[str, dict]` — `{name: {"repository", "list_fn", "entry_fn", "id_of"}}`.
  - `harvest(sources=None, *, out=DEFAULT_DB_PATH, query=None, limit=None, no_llm=True, force=False, cache_dir=None, progress=None) -> dict` — returns `{"per_source": {name: {resolved,new,updated,skipped,errors}}, "total": int}`. Loads the shared DB once, upserts only each source's rows, writes atomically.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_model_harvest.py
import json
from viva_human_atlas import model_harvest as mh


def _seed_db(tmp_path):
    p = tmp_path / "model_hra_map.json"
    p.write_text(json.dumps([
        {"identifier": "iri://BIOMD1", "repository": "biomodels", "source_id": "BIOMD1",
         "provenance": {"errors": []}},
    ]))
    return p


def test_harvest_physionet_preserves_biomodels_rows(tmp_path, monkeypatch):
    out = _seed_db(tmp_path)
    fake_project = {"slug": "mitdb", "identifier": "https://physionet.org/content/mitdb/",
                    "name": "MIT-BIH", "keywords": ["ecg"], "abstract": "", "doi": "10.13026/x",
                    "year": 2005, "access": "open"}
    monkeypatch.setitem(mh.SOURCES, "physionet", {
        **mh.SOURCES["physionet"],
        "list_fn": lambda **k: [fake_project],
        "entry_fn": lambda proj, oi, **k: {"identifier": proj["identifier"], "repository": "physionet",
                                           "source_id": proj["slug"], "provenance": {"errors": []}},
    })
    res = mh.harvest(sources=["physionet"], out=out, no_llm=True)
    db = json.loads(out.read_text())
    ids = {e["identifier"]: e["repository"] for e in db}
    assert ids["iri://BIOMD1"] == "biomodels"          # untouched
    assert ids["https://physionet.org/content/mitdb/"] == "physionet"  # added
    assert res["per_source"]["physionet"]["new"] == 1


def test_harvest_is_incremental(tmp_path, monkeypatch):
    out = _seed_db(tmp_path)
    proj = {"slug": "mitdb", "identifier": "https://physionet.org/content/mitdb/",
            "name": "MIT-BIH", "keywords": ["ecg"], "abstract": "", "doi": None, "year": 2005, "access": "open"}
    monkeypatch.setitem(mh.SOURCES, "physionet", {
        **mh.SOURCES["physionet"], "list_fn": lambda **k: [proj],
        "entry_fn": lambda p, oi, **k: {"identifier": p["identifier"], "repository": "physionet",
                                        "source_id": p["slug"], "provenance": {"errors": []}}})
    mh.harvest(sources=["physionet"], out=out, no_llm=True)
    res2 = mh.harvest(sources=["physionet"], out=out, no_llm=True)   # nothing new
    assert res2["per_source"]["physionet"]["new"] == 0
    assert res2["per_source"]["physionet"]["skipped"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_model_harvest.py -v`
Expected: FAIL with `ModuleNotFoundError: viva_human_atlas.model_harvest`.

- [ ] **Step 3: Implement the harvester**

```python
# viva_human_atlas/model_harvest.py
"""Orchestrate incremental, non-destructive harvesting of every registered model
source into the single `datasets/model_hra_map.json`. A plain rerun harvests only
newly-posted models; a source rebuild never touches another source's rows."""
from __future__ import annotations

from typing import Callable, Optional, Sequence

from viva_human_atlas import biomodel_hra as bh
from viva_human_atlas import physionet
from viva_human_atlas.biomodel_do import build_organ_index

DEFAULT_DB_PATH = bh.DEFAULT_DB_PATH

SOURCES: dict[str, dict] = {
    "biomodels": {
        "repository": "biomodels",
        "list_fn": lambda **k: bh.resolve_ids(query=k.get("query"), limit=k.get("limit")),
        "entry_fn": lambda bid, oi, **k: bh.build_entry(bid, oi, cache_dir=k.get("cache_dir"),
                                                        no_llm=k.get("no_llm", True)),
        "id_of": lambda bid: bh._IRI.format(bid),   # item -> identifier
    },
    "physionet": {
        "repository": "physionet",
        "list_fn": lambda **k: physionet.resolve_projects(query=k.get("query"), limit=k.get("limit")),
        "entry_fn": lambda proj, oi, **k: physionet.build_entry(proj, oi, cache_dir=k.get("cache_dir"),
                                                                no_llm=k.get("no_llm", True)),
        "id_of": lambda proj: proj["identifier"],
    },
}


def harvest(sources: Optional[Sequence[str]] = None, *, out=DEFAULT_DB_PATH,
            query: Optional[str] = None, limit: Optional[int] = None, no_llm: bool = True,
            force: bool = False, cache_dir=None,
            progress: Optional[Callable[[str], None]] = None) -> dict:
    names = list(sources) if sources else list(SOURCES)
    db = bh.load_db(out)
    organ_index = build_organ_index()
    per_source: dict[str, dict] = {}

    for name in names:
        src = SOURCES[name]
        counts = {"resolved": 0, "new": 0, "updated": 0, "skipped": 0, "errors": 0}
        items = src["list_fn"](query=query, limit=limit)
        counts["resolved"] = len(items)
        for i, item in enumerate(items, 1):
            ident = src["id_of"](item)
            if not bh.should_process(db, ident, force):
                counts["skipped"] += 1
                continue
            existed = ident in db
            try:
                bh.upsert_db(db, src["entry_fn"](item, organ_index, cache_dir=cache_dir, no_llm=no_llm))
                counts["updated" if existed else "new"] += 1
            except Exception as e:  # noqa: BLE001 — never abort the harvest
                counts["errors"] += 1
                if progress:
                    progress(f"  ERROR [{name}] {ident}: {e}")
            if i % 10 == 0:
                bh.write_db(db, out)
                if progress:
                    progress(f"  [{name}] {i}/{len(items)} (db={len(db)})")
        per_source[name] = counts
        if progress:
            progress(f"[{name}] {counts}")

    bh.write_db(db, out)
    return {"per_source": per_source, "total": len(db)}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_model_harvest.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add viva_human_atlas/model_harvest.py tests/test_model_harvest.py
git commit -m "feat(harvest): source registry + non-destructive incremental multi-source harvest"
```

---

### Task 6: `ModelHarvestStep` (viva reproducibility hook)

**Files:**
- Modify: `viva_human_atlas/model_harvest.py` (append the Step)
- Test: `tests/test_model_harvest_step.py`

**Interfaces:**
- Consumes: `harvest`, `bh.load_map`, `bh.summarize_map`, process-bigraph `Step`.
- Produces: `ModelHarvestStep(Step)` with `config_schema` `{db_path, sources, query, limit, no_llm, force, build_if_missing, analysis_out_dir}` and `outputs` `{db_path: string, n_models: integer, per_source: tree, summary: tree}`. When `build_if_missing=false` it loads the committed DB (network-free) and reports counts by `repository`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_model_harvest_step.py
import json
from viva_human_atlas.model_harvest import ModelHarvestStep


def test_step_loads_committed_db_network_free(tmp_path):
    out = tmp_path / "model_hra_map.json"
    out.write_text(json.dumps([
        {"identifier": "iri://A", "repository": "biomodels", "source_id": "A",
         "organs": [], "provenance": {"errors": []}},
        {"identifier": "https://physionet.org/content/mitdb/", "repository": "physionet",
         "source_id": "mitdb", "organs": [{"uberon": "UBERON:0000948"}], "provenance": {"errors": []}},
    ]))
    step = ModelHarvestStep(config={"db_path": str(out), "build_if_missing": False})
    res = step.update({})
    assert res["n_models"] == 2
    assert res["per_source"] == {"biomodels": 1, "physionet": 1}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_model_harvest_step.py -v`
Expected: FAIL with `ImportError: cannot import name 'ModelHarvestStep'`.

- [ ] **Step 3: Implement the Step**

Append to `viva_human_atlas/model_harvest.py` (import `Step` the same way `biomodel_hra` does — copy its `from ... import Step` line):

```python
from collections import Counter
from viva_human_atlas import biomodel_hra as _bh  # for load_map / summarize_map
# NOTE: copy the exact `Step` import used at the top of biomodel_hra.py

class ModelHarvestStep(Step):
    """Cache-or-harvest the unified model DB across all sources and emit path,
    model count, per-source counts, and a coverage summary."""

    description = ("Load (cache-or-harvest) the unified BioModels+PhysioNet -> HRA "
                   "model DB and emit its path, total count, per-source counts, and "
                   "coverage summary. Reproducible: run this study to refresh the DB.")

    config_schema = {
        "db_path": "string", "sources": "list", "query": "string", "limit": "integer",
        "no_llm": "boolean", "force": "boolean", "build_if_missing": "boolean",
        "analysis_out_dir": "string",
    }

    def inputs(self):
        return {}

    def outputs(self):
        return {"db_path": "string", "n_models": "integer", "per_source": "tree", "summary": "tree"}

    def update(self, inputs):
        db_path = self.config.get("db_path") or str(DEFAULT_DB_PATH)
        if self.config.get("build_if_missing", False) or self.config.get("force", False):
            harvest(self.config.get("sources") or None, out=db_path,
                    query=self.config.get("query"), limit=self.config.get("limit"),
                    no_llm=bool(self.config.get("no_llm", True)),
                    force=bool(self.config.get("force", False)))
        entries = _bh.load_map(db_path)
        per_source = dict(Counter(e.get("repository", "unknown") for e in entries))
        return {"db_path": str(db_path), "n_models": len(entries),
                "per_source": per_source, "summary": _bh.summarize_map(entries)}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_model_harvest_step.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add viva_human_atlas/model_harvest.py tests/test_model_harvest_step.py
git commit -m "feat(harvest): ModelHarvestStep as the viva reproducibility hook"
```

---

### Task 7: `scripts/harvest_models.py` CLI + alias the old script

**Files:**
- Create: `scripts/harvest_models.py`
- Modify: `scripts/build_biomodel_hra_map.py` (delegate to `--source biomodels`)
- Test: `tests/test_harvest_cli.py`

**Interfaces:**
- Consumes: `model_harvest.harvest`.
- Produces: `main(argv=None) -> int` with flags `--out --source (repeatable) --query --limit --no-llm --force`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_harvest_cli.py
import json
import scripts.harvest_models as cli  # scripts/__init__.py may be needed; add if missing


def test_cli_runs_selected_source(tmp_path, monkeypatch):
    calls = {}
    def fake_harvest(sources, *, out, query, limit, no_llm, force, progress=None):
        calls.update(sources=sources, out=out, no_llm=no_llm, limit=limit)
        json.loads  # noop
        return {"per_source": {"physionet": {"new": 0}}, "total": 0}
    monkeypatch.setattr(cli, "harvest", fake_harvest)
    rc = cli.main(["--source", "physionet", "--no-llm", "--limit", "5", "--out", str(tmp_path/"db.json")])
    assert rc == 0
    assert calls["sources"] == ["physionet"]
    assert calls["no_llm"] is True and calls["limit"] == 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_harvest_cli.py -v`
Expected: FAIL (`ModuleNotFoundError: scripts.harvest_models`). If `scripts/` is not a package, create empty `scripts/__init__.py` first (and note it in the commit).

- [ ] **Step 3: Implement the CLI + alias**

```python
# scripts/harvest_models.py
#!/usr/bin/env python
"""Reproducible multi-source harvest into datasets/model_hra_map.json.

  python scripts/harvest_models.py                    # harvest new from every source
  python scripts/harvest_models.py --source physionet  # one source
  python scripts/harvest_models.py --force            # re-fetch all
  python scripts/harvest_models.py --no-llm --limit 50 # cheap/offline dev run
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from viva_human_atlas.model_harvest import DEFAULT_DB_PATH, SOURCES, harvest  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Harvest all model sources into the unified HRA model DB.")
    ap.add_argument("--out", default=str(DEFAULT_DB_PATH))
    ap.add_argument("--source", action="append", choices=list(SOURCES), dest="sources")
    ap.add_argument("--query"); ap.add_argument("--limit", type=int)
    ap.add_argument("--no-llm", action="store_true"); ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    res = harvest(a.sources, out=a.out, query=a.query, limit=a.limit,
                  no_llm=a.no_llm, force=a.force, progress=print)
    for name, c in res["per_source"].items():
        print(f"[{name}] {c}")
    print(f"total models: {res['total']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Replace the body of `scripts/build_biomodel_hra_map.py`'s `main` to delegate (keep its shebang/docstring):

```python
from viva_human_atlas.model_harvest import harvest  # noqa: E402

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Harvest BioModels into the unified HRA model DB.")
    ap.add_argument("--out"); ap.add_argument("--query"); ap.add_argument("--limit", type=int)
    ap.add_argument("--no-llm", action="store_true"); ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    kw = {"out": a.out} if a.out else {}
    harvest(["biomodels"], query=a.query, limit=a.limit, no_llm=a.no_llm,
            force=a.force, progress=print, **kw)
    return 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_harvest_cli.py -v`
Expected: PASS. Smoke: `.venv/bin/python scripts/harvest_models.py --help` prints usage.

- [ ] **Step 5: Commit**

```bash
git add scripts/harvest_models.py scripts/build_biomodel_hra_map.py tests/test_harvest_cli.py scripts/__init__.py
git commit -m "feat(cli): harvest_models.py multi-source harvester; biomodels script delegates"
```

---

### Task 8: `model-harvest` study (baseline.step wiring)

**Files:**
- Create: `studies/model-harvest/study.yaml`
- Test: `tests/test_model_harvest_study.py`

**Interfaces:**
- Consumes: `ModelHarvestStep` at `local:viva_human_atlas.model_harvest.ModelHarvestStep`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_model_harvest_study.py
import yaml
from pathlib import Path

STUDY = Path("studies/model-harvest/study.yaml")


def test_study_baseline_points_at_model_harvest_step():
    d = yaml.safe_load(STUDY.read_text())
    baseline = d["baseline"][0]
    assert baseline["step"] == "local:viva_human_atlas.model_harvest.ModelHarvestStep"
    assert baseline["params"]["db_path"] == "datasets/model_hra_map.json"
    assert set(baseline["params"]["sources"]) == {"biomodels", "physionet"}
    assert baseline["params"]["build_if_missing"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_model_harvest_study.py -v`
Expected: FAIL (`FileNotFoundError`).

- [ ] **Step 3: Author the study**

Copy the metadata shape from `studies/biomodel-hra-map/study.yaml` (title/phase/summary/goal/mechanism/expected_result fields) and adapt for the unified harvest. The baseline block:

```yaml
title: "Unified Model Harvest — BioModels + PhysioNet into the HRA Model DB"
phase: Evaluate
baseline:
  - name: baseline
    step: "local:viva_human_atlas.model_harvest.ModelHarvestStep"
    params:
      db_path: datasets/model_hra_map.json
      sources: [biomodels, physionet]
      build_if_missing: false
```

Fill `summary`/`goal`/`mechanism`/`expected_result` with real prose: the study loads the committed `model_hra_map.json` and reports total + per-source counts + HRA coverage; the mechanism is `ModelHarvestStep.update -> model_harvest.harvest` (incremental, non-destructive per-source upsert; PhysioNet via DataCite prefix 10.13026 + hybrid keyword/LLM organ mapping); expected_result names the actual post-harvest counts once Task 9's build has run (update this number after the first real harvest).

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_model_harvest_study.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add studies/model-harvest/study.yaml tests/test_model_harvest_study.py
git commit -m "feat(study): model-harvest study runs the unified harvest as its baseline"
```

---

### Task 9: Real harvest run + `atlas_pack` source-aware manifest

Produce actual PhysioNet rows in the committed DB and make the atlas builder read a mixed-source DB with correct per-source links.

**Files:**
- Modify: `viva_human_atlas/atlas_pack.py` (model-entry construction: use each entry's `repository`/`url`/`name`/`source_id`; union across sources)
- Modify: `datasets/model_hra_map.json` (regenerated with PhysioNet rows)
- Test: `tests/test_atlas_pack_multisource.py`

**Interfaces:**
- Produces: atlas manifest model entries shaped `{"source_id", "repository", "url", "name", "via"}` (replacing the biomodels-only `{"biomodel_id", "url", "via"}`), keyed/counted across both sources.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_atlas_pack_multisource.py
from viva_human_atlas import atlas_pack


def test_model_link_is_source_aware():
    bio = {"repository": "biomodels", "source_id": "BIOMD0000000633", "biomodel_id": "BIOMD0000000633",
           "name": "Bulik2016"}
    phys = {"repository": "physionet", "source_id": "mitdb", "name": "MIT-BIH",
            "identifier": "https://physionet.org/content/mitdb/"}
    assert atlas_pack.model_url(bio).endswith("BIOMD0000000633")
    assert atlas_pack.model_url(phys) == "https://physionet.org/content/mitdb/"
    assert atlas_pack.model_ref(phys)["repository"] == "physionet"
    assert atlas_pack.model_ref(phys)["source_id"] == "mitdb"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_atlas_pack_multisource.py -v`
Expected: FAIL (`AttributeError: module has no attribute 'model_url'`).

- [ ] **Step 3: Make `atlas_pack` source-aware**

Add helpers near the existing `biomodels_url`:

```python
def model_url(entry: dict) -> str:
    """Link to a model's landing page, per source."""
    if entry.get("repository") == "biomodels":
        return biomodels_url(entry.get("source_id") or entry.get("biomodel_id"))
    return entry.get("identifier") or ""


def model_ref(entry: dict) -> dict:
    return {"source_id": entry.get("source_id") or entry.get("biomodel_id"),
            "repository": entry.get("repository", "biomodels"),
            "url": model_url(entry), "name": entry.get("name") or entry.get("source_id")}
```

Then update `build_atlas_manifest` where it builds `models` lists (currently `{"biomodel_id": m["biomodel_id"], "url": biomodels_url(...), "via": ...}`) to spread `model_ref(entry)` and keep `via`. Ensure the model index is built from the whole `model_hra_map.json` (both repositories) and `organ_to_models` unions sources. Where code keys by `biomodel_id`, switch to `source_id` (unique within source; the entries also carry `repository`, so `(repository, source_id)` is globally unique — use that tuple if a global key is needed).

- [ ] **Step 4: Run test + regenerate the DB + atlas pack**

```bash
.venv/bin/python -m pytest tests/test_atlas_pack_multisource.py -v          # PASS
PYTHONUTF8=1 .venv/bin/python scripts/harvest_models.py --source physionet --no-llm   # real PhysioNet rows (offline mapper)
PYTHONUTF8=1 .venv/bin/python scripts/build_atlas_pack.py                    # rebuild atlas.json from mixed DB
.venv/bin/python -m pytest -m "not network" -q                              # full offline suite green
```

Expected: `model_hra_map.json` now contains `repository: "physionet"` rows; `atlas.json` lists PhysioNet models on their organs (e.g. `mitdb` under heart).

- [ ] **Step 5: Commit**

```bash
git add viva_human_atlas/atlas_pack.py datasets/model_hra_map.json \
        studies/hra-atlas-browser/viz/atlas/atlas.json tests/test_atlas_pack_multisource.py
git commit -m "feat(atlas): source-aware model links + PhysioNet rows in the unified DB"
```

---

### Task 10: Viewer source badge + source filter

**Files:**
- Modify: `viva_human_atlas/assets/hra_glb_viewer/viewer.js` (+ `index.html` if a filter control is added there)
- Modify: the atlas-browser viewer JS if it is a separate file (check `studies/hra-atlas-browser/viz/atlas/`)
- Test: `tests/test_viewer_assets.py` (asset-content assertions; the JS itself is exercised manually)

**Interfaces:**
- Consumes: `atlas.json` model entries `{source_id, repository, url, name}` from Task 9.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_viewer_assets.py
from pathlib import Path

VIEWER = Path("viva_human_atlas/assets/hra_glb_viewer/viewer.js")


def test_viewer_renders_source_badge_and_filter():
    js = VIEWER.read_text()
    assert "repository" in js          # per-model source used in the click list
    assert "data-source-filter" in js  # a source filter control exists
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_viewer_assets.py -v`
Expected: FAIL (strings absent).

- [ ] **Step 3: Add the badge + filter to `viewer.js`**

In the function that renders an organ's model list, render each model with a source badge and use its `url`:

```javascript
// where each model item is built (m has {source_id, repository, url, name}):
const badge = `<span class="src-badge src-${m.repository}">${m.repository}</span>`;
item.innerHTML = `${badge} <a href="${m.url}" target="_blank" rel="noopener">${m.name}</a>`;
```

Add a filter control (in `index.html` or built in JS) and honor it when rendering:

```html
<!-- index.html, near the legend -->
<select data-source-filter>
  <option value="all">All sources</option>
  <option value="biomodels">BioModels</option>
  <option value="physionet">PhysioNet</option>
</select>
```

```javascript
// filter applied before rendering a model list:
const filter = document.querySelector('[data-source-filter]').value;
const shown = models.filter(m => filter === 'all' || m.repository === filter);
```

Add minimal CSS for `.src-badge`/`.src-biomodels`/`.src-physionet` (two distinct colors) in the viewer's `<style>`. If the atlas-browser ships a separate copied viewer under `studies/hra-atlas-browser/viz/atlas/`, apply the same edits there (or re-copy from the canonical asset via `scripts/build_atlas_pack.py` / `publish_dashboard.sh`).

- [ ] **Step 4: Run test + eyeball the viewer**

Run: `.venv/bin/python -m pytest tests/test_viewer_assets.py -v` → PASS.
Manual: `bash scripts/serve_dashboard.sh` (or open the atlas viewer), click an organ with both sources (e.g. heart), confirm badges render and the filter toggles BioModels/PhysioNet.

- [ ] **Step 5: Commit**

```bash
git add viva_human_atlas/assets/hra_glb_viewer/ studies/hra-atlas-browser/viz/atlas/ tests/test_viewer_assets.py
git commit -m "feat(viewer): per-model source badge + BioModels/PhysioNet filter"
```

---

## Self-Review

**Spec coverage:**
- Single source-agnostic DB + identifier key → Task 1. ✓
- File rename `model_hra_map.json` → Task 2. ✓
- PhysioNet via DataCite prefix 10.13026 → Task 4. ✓
- Hybrid keyword-table + LLM-fallback organ mapping → Task 3. ✓
- Non-destructive per-source upsert (invariant + test) → Task 5. ✓
- Source registry / extensibility → Task 5. ✓
- Reproducible via composite/study (`ModelHarvestStep` + `model-harvest` study) → Tasks 6, 8. ✓
- Reproducible CLI, incremental "harvest new" → Task 7 (+ incremental test in Task 5). ✓
- Atlas viewer source-aware + badge/filter → Tasks 9, 10. ✓
- Access badging / all projects cataloged → Task 4 (`access` in provenance) + Task 10 (badge). ✓
- Offline-first / `--no-llm` → Global Constraints; enforced in Tasks 3–7 tests. ✓
- Tests split by marker; network tests for DataCite → Task 4 network test. ✓

**Placeholder scan:** No TBD/TODO; every code step carries real code. Task 8's `expected_result` prose intentionally gets its final count filled after Task 9's first harvest — this is a data-dependent number, not a placeholder for logic.

**Type consistency:** `identifier`-keyed DB used consistently (Tasks 1, 5, 6). `source_id` added in Task 1, consumed in Tasks 4/5/9. `repository` set in Tasks 1(biomodels)/4(physionet), consumed in 6/9/10. `harvest()` return shape `{per_source, total}` produced in Task 5, consumed in Tasks 6/7. `model_ref`/`model_url` produced in Task 9, consumed in Task 10. Consistent.

**Open risk flagged for execution:** the exact `Step` import line in Task 6 must be copied verbatim from `biomodel_hra.py` (framework import path varies); the test in Task 6 will fail loudly if it's wrong.
