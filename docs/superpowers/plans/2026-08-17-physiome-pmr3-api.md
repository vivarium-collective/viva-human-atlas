# Physiome pmr3 API Source Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Physiome (PMR) Plone-HTML scraper with a client for the new structured pmr3 API, harvesting the complete ~978-exposure corpus with author-keyword organ mapping and PubMed citation enrichment.

**Architecture:** `physiome.py` becomes a pmr3 REST client (enumerate exposure ids → fetch per-id records → aggregate files into one model record). `physiome_organ_map.py` gains a curated author-keyword→organ-key table as the primary organ signal above the existing category/title fallbacks. `model_harvest.py` gains per-source rebuild so the physiome source is replaced cleanly (its rows key on a new identifier URL). Then rebuild the DB and regenerate the atlas.

**Tech Stack:** Python 3.11, `requests`, `process_bigraph.Step`, pytest (offline + `-m network`).

**Spec:** `docs/superpowers/specs/2026-08-17-physiome-pmr3-api-design.md`

## Global Constraints

- Run tests with the project venv: `.venv/bin/python -m pytest ...` (bare `python` lacks deps). Run from the worktree cwd so it shadows the installed package.
- Offline tests MUST NOT hit the network — inject responses via the `_get`/`_ids`/`_citations` seams. Only `@pytest.mark.network` tests may call live.
- API base URL is `PMR3_API_BASE` env-overridable, default `https://pmr3.demo.physiomeproject.org`. Human-facing model URLs use `PMR_SITE = https://models.physiomeproject.org` (independent of the API host).
- Never hardcode UBERON ids in mapping tables — map to `organ_index` keys, resolved live (a key absent from the HRA reference set contributes nothing, by design).
- Record record schema is the existing source-agnostic shape (see `physionet.build_entry` / current `physiome.build_entry`): keys `identifier, repository, source_id, name, paper_url, paper_pmid, paper_doi, taxonomy, organs, functional_tissue_units, cell_types, molecular_ids, ontology_ids, gene_symbols, provenance`.
- Preserve the `model_harvest` registry contract: each source provides `list_fn`, `entry_fn`, `id_of`.
- Commit after each task. This runs in worktree `~/code/viva-human-atlas--physiome-pmr3` on branch `feat/physiome-pmr3-api`; git commits use `-c commit.gpgsign=false` and end with the `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>` trailer.

---

### Task 1: pmr3 API client — enumerate + fetch + aggregate

Replace the Plone scraper core in `physiome.py` with pmr3 API calls. This task delivers exposure enumeration and per-exposure aggregation; citations + `build_entry` come in Task 2.

**Files:**
- Modify: `viva_human_atlas/physiome.py` (rewrite scraper internals; keep module docstring updated)
- Test: `tests/test_physiome_pmr3.py` (new)

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - `api_base() -> str` — `os.environ.get("PMR3_API_BASE", _DEFAULT_API_BASE)`.
  - `PMR_SITE = "https://models.physiomeproject.org"`.
  - `list_exposure_ids(*, _get=requests.get) -> list[str]` — GET `{api_base}/api/index/exposure_id`, return `json()["terms"]`.
  - `fetch_exposure(exposure_id: str, *, cache_dir=None, _get=requests.get) -> dict | None` — GET `{api_base}/api/index/exposure_id/{id}`, aggregate `resource_paths` into one dict `{slug, identifier, name, abstract, keywords, citation_ids, authors, created_ts, filename, categories}`. Cache raw JSON at `<cache_dir or DEFAULT_CACHE_DIR>/<id>.json`. Returns `None` if no resource_paths. `categories` is `[]` (kept for back-compat with the organ mapper's category path).
  - `resolve_exposures(*, query=None, limit=None, cache_dir=None, _get=requests.get, _ids=None) -> list[dict]` — enumerate ids (`_ids` override for tests), fetch each, drop `None`, apply title-substring `query` filter and `limit`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_physiome_pmr3.py
import json
import pytest
from viva_human_atlas import physiome


class _R:
    def __init__(self, payload): self._p = payload
    def raise_for_status(self): pass
    def json(self): return self._p

# Two files under one exposure id -> one aggregated record (keywords/citations unioned).
_EXP_583 = {
    "kind": {"id": 1, "description": "exposure_id"}, "term": "583",
    "resource_paths": [
        {"resource_path": "/exposure/583/cloutier_2009_a.cellml", "data": {
            "_title": ["Energy metabolism (Version A)"],
            "_brief": ["Model Status ... version A ..."],
            "cellml_keyword": ["metabolism", "brain"],
            "citation_id": ["urn:miriam:pubmed:19828503"],
            "citation_author_family_name": ["Cloutier"],
            "aliased_uri": ["/exposure/e5cfb42225d4534a1e08979e57cf8bdd/cloutier_2009_a.cellml"],
            "exposure_alias": ["e5cfb42225d4534a1e08979e57cf8bdd"],
            "created_ts": ["1274964447"]}},
        {"resource_path": "/exposure/583/cloutier_2009_b.cellml", "data": {
            "_title": ["Energy metabolism (Version B)"],
            "cellml_keyword": ["brain", "metabolic regulation"],
            "citation_id": ["urn:miriam:pubmed:19828503"],
            "citation_author_family_name": ["Wellstead"],
            "exposure_alias": ["e5cfb42225d4534a1e08979e57cf8bdd"],
            "created_ts": ["1274964447"]}},
    ]}


def test_list_exposure_ids():
    got = physiome.list_exposure_ids(_get=lambda url, timeout=0: _R({"terms": ["1", "583", "1000"]}))
    assert got == ["1", "583", "1000"]


def test_fetch_exposure_aggregates_files(tmp_path):
    exp = physiome.fetch_exposure("583", cache_dir=tmp_path, _get=lambda url, timeout=0: _R(_EXP_583))
    assert exp["slug"] == "e5cfb42225d4534a1e08979e57cf8bdd"
    assert exp["identifier"] == "https://models.physiomeproject.org/exposure/e5cfb42225d4534a1e08979e57cf8bdd"
    assert exp["name"] == "Energy metabolism (Version A)"
    assert set(exp["keywords"]) == {"metabolism", "brain", "metabolic regulation"}
    assert exp["citation_ids"] == ["urn:miriam:pubmed:19828503"]
    assert set(exp["authors"]) == {"Cloutier", "Wellstead"}
    assert exp["filename"] == "cloutier_2009_a.cellml"
    assert (tmp_path / "583.json").exists()  # cached


def test_fetch_exposure_uses_cache(tmp_path):
    (tmp_path / "77.json").write_text(json.dumps(_EXP_583), encoding="utf-8")
    calls = {"n": 0}
    def boom(url, timeout=0):
        calls["n"] += 1; raise AssertionError("should not fetch")
    exp = physiome.fetch_exposure("77", cache_dir=tmp_path, _get=boom)
    assert exp["slug"] == "e5cfb42225d4534a1e08979e57cf8bdd" and calls["n"] == 0


def test_resolve_exposures_query_and_limit(tmp_path):
    payloads = {"1": _EXP_583, "2": _EXP_583}
    def get(url, timeout=0): return _R(payloads[url.rsplit("/", 1)[-1]])
    exps = physiome.resolve_exposures(cache_dir=tmp_path, _ids=["1", "2"], _get=get)
    assert len(exps) == 2
    assert physiome.resolve_exposures(cache_dir=tmp_path, _ids=["1", "2"], limit=1, _get=get).__len__() == 1
    assert physiome.resolve_exposures(cache_dir=tmp_path, _ids=["1"], query="nomatch", _get=get) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_physiome_pmr3.py -v`
Expected: FAIL (`AttributeError: module 'viva_human_atlas.physiome' has no attribute 'list_exposure_ids'`).

- [ ] **Step 3: Write minimal implementation**

Rewrite the top of `viva_human_atlas/physiome.py`. Replace the Plone scraper constants/functions (`_BASE`, `_ENTRY_RE`, `_PAGE_STEP`, `_DOI_RE`, `fetch_doi`, `_scrape_category`, `build_category_index`, old `resolve_exposures`) with:

```python
"""Physiome Model Repository (PMR) as an HRA model source, via the pmr3 API.

The new PMR backend (OpenAPI at /api-docs/openapi.json) indexes every exposure
with author `cellml_keyword`s, title, abstract, and PubMed citations. We
enumerate all exposures (`/api/index/exposure_id`), fetch each
(`/api/index/exposure_id/{id}`), and aggregate its CellML files into one model
record. Author keywords are the primary organ signal (see physiome_organ_map);
citations enrich the record with the source publication. Plugs into the shared
`model_harvest` framework like `physionet` / `biomodel_hra`.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

import requests

from viva_human_atlas.physiome_organ_map import DEFAULT_LLM_MODEL, map_exposure_to_organs

_REPO = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_DIR = _REPO / ".cache" / "physiome_pmr3"
_DEFAULT_API_BASE = "https://pmr3.demo.physiomeproject.org"
PMR_SITE = "https://models.physiomeproject.org"


def api_base() -> str:
    return os.environ.get("PMR3_API_BASE", _DEFAULT_API_BASE)


def list_exposure_ids(*, _get=requests.get) -> list[str]:
    r = _get(f"{api_base()}/api/index/exposure_id", timeout=60)
    r.raise_for_status()
    return list(r.json().get("terms", []))


def _first(data: dict, key: str) -> Optional[str]:
    vals = data.get(key) or []
    return vals[0] if vals else None


def fetch_exposure(exposure_id: str, *, cache_dir=None, _get=requests.get) -> Optional[dict]:
    cache = Path(cache_dir) if cache_dir else DEFAULT_CACHE_DIR
    cache.mkdir(parents=True, exist_ok=True)
    cached = cache / f"{exposure_id}.json"
    if cached.exists():
        payload = json.loads(cached.read_text(encoding="utf-8"))
    else:
        r = _get(f"{api_base()}/api/index/exposure_id/{exposure_id}", timeout=60)
        r.raise_for_status()
        payload = r.json()
        cached.write_text(json.dumps(payload), encoding="utf-8")
    records = payload.get("resource_paths") or []
    if not records:
        return None
    first = records[0]["data"]
    alias = _first(first, "exposure_alias")
    if not alias:
        uri = _first(first, "aliased_uri") or ""     # /exposure/<alias>/<file>
        parts = uri.strip("/").split("/")
        alias = parts[1] if len(parts) > 1 else exposure_id
    keywords, citation_ids, authors = [], [], []
    for rec in records:
        d = rec["data"]
        for k in d.get("cellml_keyword") or []:
            k = (k or "").strip().lower()
            if k and k not in keywords:
                keywords.append(k)
        for c in d.get("citation_id") or []:
            if c and c not in citation_ids:
                citation_ids.append(c)
        for a in d.get("citation_author_family_name") or []:
            if a and a not in authors:
                authors.append(a)
    filename = records[0]["resource_path"].rsplit("/", 1)[-1]
    return {
        "slug": alias,
        "identifier": f"{PMR_SITE}/exposure/{alias}",
        "name": _first(first, "_title"),
        "abstract": _first(first, "_brief"),
        "keywords": keywords,
        "categories": [],
        "citation_ids": citation_ids,
        "authors": authors,
        "created_ts": _first(first, "created_ts"),
        "filename": filename,
    }


def resolve_exposures(*, query: Optional[str] = None, limit: Optional[int] = None,
                      cache_dir=None, _get=requests.get, _ids=None) -> list[dict]:
    ids = _ids if _ids is not None else list_exposure_ids(_get=_get)
    q = (query or "").lower().strip()
    out: list[dict] = []
    for eid in ids:
        exp = fetch_exposure(eid, cache_dir=cache_dir, _get=_get)
        if exp is None:
            continue
        if q and q not in (exp.get("name") or "").lower():
            continue
        out.append(exp)
        if limit is not None and len(out) >= limit:
            break
    return out
```

Keep `resolve_cellml_url` for now (it references the public site; leave as-is at the bottom of the module — it still works against `PMR_SITE` exposure pages). `build_entry` is rewritten in Task 2 — leave the OLD `build_entry` temporarily so imports don't break between tasks; it will be replaced in Task 2.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_physiome_pmr3.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Delete the obsolete Plone scraper test**

The old `tests/test_physiome.py` tests the removed scraper (`build_category_index`, category-HTML). Delete the scraper-specific tests but KEEP the organ-mapping tests. Split: move the still-valid organ-map tests (`test_extract_cellml_curies_*`, `test_category_organ_keys_*`, `test_map_exposure_*`, `test_metabolism_falls_through_*`) into `tests/test_physiome_organ_map.py` (they import from `physiome_organ_map` + `biomodel_do`, not the scraper), and delete `test_physiome.py`'s scraper tests (`test_scrape_and_resolve_from_category_html`, `test_build_entry_shape_category_mapped` [rewritten in Task 2], the network `test_pmr_live_category_scrape_maps_bulk` [rewritten in Task 5]).

Run: `.venv/bin/python -m pytest tests/test_physiome_organ_map.py -v`
Expected: PASS (the moved organ-map tests).

- [ ] **Step 6: Commit**

```bash
git add viva_human_atlas/physiome.py tests/test_physiome_pmr3.py tests/test_physiome_organ_map.py
git rm tests/test_physiome.py
git -c commit.gpgsign=false commit -m "feat(physiome): pmr3 API client — enumerate + fetch + aggregate exposures

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Citation enrichment + `build_entry` rewrite

**Files:**
- Modify: `viva_human_atlas/physiome.py` (add `load_citations`, `resolve_citation`; rewrite `build_entry`)
- Test: `tests/test_physiome_pmr3.py` (append)

**Interfaces:**
- Consumes: `fetch_exposure` record shape from Task 1; `map_exposure_to_organs` (Task 3 extends it, but its current signature already accepts the exposure dict).
- Produces:
  - `load_citations(*, cache_dir=None, _get=requests.get) -> dict` — GET `{api_base}/api/citations`, cache once to `<cache_dir>/citations.json`, return the `{urn: Citation}` map.
  - `resolve_citation(citation_ids, citations) -> tuple[Optional[str], dict]` — return `(pmid, citation_meta)` for the first `urn:miriam:pubmed:<id>` with a non-empty id resolvable in `citations`; `citation_meta` is `{title, journal, year, authors}` (year from `issued[:4]`).
  - `build_entry(exposure, organ_index, *, citations=None, no_llm=True, llm_model=DEFAULT_LLM_MODEL, cache_dir=None, _map=None) -> dict` — record with citation-derived `paper_pmid`/`paper_url`, `provenance.citation`, `provenance.abstract`, `provenance.keywords` = exposure keywords.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_physiome_pmr3.py
from viva_human_atlas.biomodel_do import build_organ_index
ORGAN_INDEX = build_organ_index()

_CITATIONS = {
    "urn:miriam:pubmed:19828503": {
        "id": "urn:miriam:pubmed:19828503", "title": "Energy metabolism control",
        "journal": "PLoS ONE", "issued": "2009-10-01",
        "authors": [{"family": "Cloutier", "given": "M", "other": ""}]},
}


def test_load_and_resolve_citation(tmp_path):
    cites = physiome.load_citations(cache_dir=tmp_path, _get=lambda url, timeout=0: _R(_CITATIONS))
    pmid, meta = physiome.resolve_citation(["urn:miriam:pubmed:19828503"], cites)
    assert pmid == "19828503"
    assert meta["title"] == "Energy metabolism control" and meta["year"] == "2009"
    assert meta["authors"] == ["Cloutier"]
    # empty / unknown -> (None, {})
    assert physiome.resolve_citation(["urn:miriam:pubmed:"], cites) == (None, {})
    assert physiome.resolve_citation([], cites) == (None, {})


def test_build_entry_pmr3_shape_with_citation():
    exp = {"slug": "abc", "identifier": "https://models.physiomeproject.org/exposure/abc",
           "name": "hepatic bile acid model", "abstract": "A liver model.",
           "keywords": ["hepatocyte", "bile acid"], "categories": [],
           "citation_ids": ["urn:miriam:pubmed:19828503"], "authors": ["Cloutier"]}
    e = physiome.build_entry(exp, ORGAN_INDEX, citations=_CITATIONS, no_llm=True)
    assert e["repository"] == "physiome" and e["source_id"] == "abc"
    assert e["paper_pmid"] == "19828503"
    assert e["paper_url"] == "https://pubmed.ncbi.nlm.nih.gov/19828503/"
    assert e["provenance"]["citation"]["journal"] == "PLoS ONE"
    assert e["provenance"]["abstract"] == "A liver model."
    assert e["provenance"]["keywords"] == ["hepatocyte", "bile acid"]
    assert e["provenance"]["model_format"] == "CellML"


def test_build_entry_no_citation_falls_back_to_identifier():
    exp = {"slug": "abc", "identifier": "https://models.physiomeproject.org/exposure/abc",
           "name": "x", "abstract": None, "keywords": [], "categories": [],
           "citation_ids": [], "authors": []}
    e = physiome.build_entry(exp, ORGAN_INDEX, citations={}, no_llm=True)
    assert e["paper_pmid"] is None
    assert e["paper_url"] == "https://models.physiomeproject.org/exposure/abc"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_physiome_pmr3.py -k "citation or pmr3_shape or no_citation" -v`
Expected: FAIL (`load_citations` missing / `build_entry` signature).

- [ ] **Step 3: Write minimal implementation**

Add to `physiome.py` (and remove the OLD `build_entry` left from Task 1):

```python
def load_citations(*, cache_dir=None, _get=requests.get) -> dict:
    cache = Path(cache_dir) if cache_dir else DEFAULT_CACHE_DIR
    cache.mkdir(parents=True, exist_ok=True)
    cached = cache / "citations.json"
    if cached.exists():
        return json.loads(cached.read_text(encoding="utf-8"))
    try:
        r = _get(f"{api_base()}/api/citations", timeout=90)
        r.raise_for_status()
        cites = r.json()
    except Exception:  # noqa: BLE001 — citation enrichment must never abort a harvest
        cites = {}
    cached.write_text(json.dumps(cites), encoding="utf-8")
    return cites


def resolve_citation(citation_ids, citations) -> tuple[Optional[str], dict]:
    for cid in citation_ids or []:
        if not cid.startswith("urn:miriam:pubmed:"):
            continue
        pmid = cid.rsplit(":", 1)[-1].strip()
        if not pmid:
            continue
        c = (citations or {}).get(cid) or {}
        meta = {
            "title": c.get("title"), "journal": c.get("journal"),
            "year": (c.get("issued") or "")[:4] or None,
            "authors": [a.get("family") for a in c.get("authors") or [] if a.get("family")],
        }
        return pmid, meta
    return None, {}


def build_entry(exposure: dict, organ_index: dict, *, citations=None, no_llm: bool = True,
                llm_model: str = DEFAULT_LLM_MODEL, cache_dir=None, _map=None) -> dict:
    mapper = _map or map_exposure_to_organs
    hra = mapper(exposure, organ_index, no_llm=no_llm, llm_model=llm_model, cache_dir=cache_dir)
    anat = hra.get("anatomy_ids") or {}
    mol = hra.get("molecular") or {}
    pmid, cite = resolve_citation(exposure.get("citation_ids") or [], citations or {})
    return {
        "identifier": exposure["identifier"],
        "repository": "physiome",
        "source_id": exposure["slug"],
        "name": exposure.get("name"),
        "paper_url": (f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else exposure["identifier"]),
        "paper_pmid": pmid,
        "paper_doi": None,
        "taxonomy": [],
        "organs": hra["organs"],
        "functional_tissue_units": hra["functional_tissue_units"],
        "cell_types": hra["cell_types"],
        "molecular_ids": {"chebi": mol.get("chebi") or [], "uniprot": [], "kegg": [],
                          "go": mol.get("go") or [], "reactome": []},
        "ontology_ids": {"uberon": hra.get("uberon_organ_ids", []), "cl": [], "mesh": [],
                         "fma": anat.get("fma") or [], "bto": []},
        "gene_symbols": [],
        "provenance": {
            "abstract": exposure.get("abstract"), "year": cite.get("year"), "access": "open",
            "keywords": exposure.get("keywords") or [],
            "authors": exposure.get("authors") or [],
            "model_format": "CellML", "executable": "OpenCOR",
            "citation": cite,
            "mapping_method": hra.get("mapping_method", "unmapped"),
            "confidence": hra.get("confidence", "none"), "errors": [],
        },
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_physiome_pmr3.py -v`
Expected: PASS (all Task 1 + Task 2 tests).

- [ ] **Step 5: Commit**

```bash
git add viva_human_atlas/physiome.py tests/test_physiome_pmr3.py
git -c commit.gpgsign=false commit -m "feat(physiome): PubMed citation enrichment + pmr3 build_entry

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Curated author-keyword → organ mapping

**Files:**
- Modify: `viva_human_atlas/physiome_organ_map.py`
- Test: `tests/test_physiome_organ_map.py` (append)

**Interfaces:**
- Consumes: exposure dict now carries `keywords: list[str]` (Task 1).
- Produces:
  - `KEYWORD_TO_ORGAN_KEYS: dict[str, list[str]]` — exact lowercase keyword → organ keys.
  - `KEYWORD_PATTERNS: list[tuple[re.Pattern, list[str]]]` — regex families.
  - `keyword_organ_keys(keywords: list[str]) -> list[str]` — union of organ keys implied by an exposure's author keywords.
  - `map_exposure_to_organs(...)` gains a keyword-annotation path (precedence: annotation > keyword > category > title-keyword > llm) with `mapping_method="keyword_annotation"`, confidence `"medium"`.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_physiome_organ_map.py
from viva_human_atlas.physiome_organ_map import keyword_organ_keys, map_exposure_to_organs
from viva_human_atlas.biomodel_do import build_organ_index
ORGAN_INDEX = build_organ_index()


def test_keyword_organ_keys_exact_and_pattern():
    assert "heart" in keyword_organ_keys(["atrial myocyte"])
    assert "brain" in keyword_organ_keys(["substantia nigra"])
    assert "pancreas" in keyword_organ_keys(["beta cell"])
    assert "kidney" in keyword_organ_keys(["collecting duct"])
    assert keyword_organ_keys(["cardiac action potential"]) == ["heart"]   # pattern cardiac.*
    assert keyword_organ_keys(["systems biology"]) == []                    # no anatomy signal


def test_map_exposure_keyword_path_beats_category():
    # keywords give brain; category electrophysiology would give heart -> keyword wins
    exp = {"name": "x", "keywords": ["hippocampal neuron"], "categories": ["electrophysiology"]}
    hra = map_exposure_to_organs(exp, ORGAN_INDEX)
    assert hra["mapping_method"] == "keyword_annotation" and hra["confidence"] == "medium"
    assert {o["label"] for o in hra["organs"]} == {"brain"}


def test_map_exposure_keyword_yields_celltypes_via_ftu():
    # beta cell -> pancreas -> pancreatic islet FTU -> beta cell CL flows through map_to_hra
    exp = {"name": "insulin secretion model", "keywords": ["beta cell"], "categories": []}
    hra = map_exposure_to_organs(exp, ORGAN_INDEX)
    assert {o["label"] for o in hra["organs"]} == {"pancreas"}
    assert any("beta" in (ct["label"] or "").lower() for ct in hra["cell_types"])


def test_map_exposure_keyword_absent_falls_to_category():
    exp = {"name": "x", "keywords": ["oscillation"], "categories": ["ion_transport"]}
    hra = map_exposure_to_organs(exp, ORGAN_INDEX)
    assert hra["mapping_method"] == "category"
    assert {o["label"] for o in hra["organs"]} == {"kidney"}
```

Note: `test_map_exposure_keyword_yields_celltypes_via_ftu` depends on `HRA_FTUS` having a pancreatic-islet FTU with a beta-cell type. If it does not, replace the cell-type assertion with an organ-only assertion and record a follow-up — do not fake the data.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_physiome_organ_map.py -k keyword -v`
Expected: FAIL (`keyword_organ_keys` missing).

- [ ] **Step 3: Write minimal implementation**

Add to `physiome_organ_map.py` (after `CATEGORY_TO_ORGAN_KEYS`):

```python
# Author `cellml_keyword` -> HRA organ key(s). Only keys present in the HRA
# reference organ set resolve to an UBERON id; the rest (e.g. bone, adrenal,
# thyroid — absent from the reference set) contribute nothing, by design.
KEYWORD_TO_ORGAN_KEYS: dict[str, list[str]] = {
    "atrial myocyte": ["heart"], "ventricular myocyte": ["heart"],
    "cardiac myocyte": ["heart"], "sinoatrial node": ["heart"], "atrial cell": ["heart"],
    "cardiovascular circulation": ["heart", "blood"], "circulation": ["blood"],
    "beta cell": ["pancreas"], "beta-cell": ["pancreas"], "islet": ["pancreas"],
    "insulin secretion": ["pancreas"], "pancreatic acinar cell": ["pancreas"],
    "collecting duct": ["kidney"], "nephron": ["kidney"], "proximal tubule": ["kidney"],
    "glomerulus": ["kidney"], "renal": ["kidney"],
    "hepatocyte": ["liver"], "bile acid": ["liver"],
    "substantia nigra": ["brain"], "hippocampus": ["brain"], "cortical neuron": ["brain"],
    "astrocyte": ["brain"], "dopaminergic neuron": ["brain"], "purkinje cell": ["brain"],
    "airway myocyte": ["lung"], "alveolar": ["lung"],
    "smooth muscle": ["intestine"], "enteric": ["intestine"], "jejunum": ["intestine"],
    "adipocyte": ["adipose"],
}

# Keyword families (regex, first-match-wins per keyword).
KEYWORD_PATTERNS: list[tuple[re.Pattern, list[str]]] = [
    (re.compile(r"^cardiac|cardiac (action potential|muscle|mechanics|myocyte)|arrhythmia", re.I), ["heart"]),
    (re.compile(r"neuron|neural|cortex|cortical|hippocamp|cerebell|dopaminerg|axon", re.I), ["brain"]),
    (re.compile(r"hepat", re.I), ["liver"]),
    (re.compile(r"\bislet\b|insulin", re.I), ["pancreas"]),
    (re.compile(r"nephron|renal|collecting duct|glomerul|tubule", re.I), ["kidney"]),
]


def keyword_organ_keys(keywords) -> list[str]:
    """Organ keys implied by an exposure's author `cellml_keyword`s."""
    keys: list[str] = []
    for kw in keywords or []:
        k = (kw or "").strip().lower()
        if not k:
            continue
        hit = KEYWORD_TO_ORGAN_KEYS.get(k)
        if hit is None:
            for pat, pk in KEYWORD_PATTERNS:
                if pat.search(k):
                    hit = pk
                    break
        for key in hit or []:
            if key not in keys:
                keys.append(key)
    return keys
```

Then insert the keyword path into `map_exposure_to_organs`, between the annotation step (1) and the category step (2):

```python
    # 1b) NEW primary signal: curated author-keyword -> organ table
    if not ubs:
        kw_keys = keyword_organ_keys(exposure.get("keywords"))
        if kw_keys:
            ubs = _keys_to_uberon(kw_keys, organ_index)
            method = "keyword_annotation" if ubs else None
```

Add `"keyword_annotation": "medium"` to `_CONFIDENCE`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_physiome_organ_map.py -v`
Expected: PASS. (If the FTU cell-type assertion fails because `HRA_FTUS` lacks a pancreatic-islet/beta-cell entry, weaken that one assertion to organ-only and note the follow-up — see Step 1 note.)

- [ ] **Step 5: Commit**

```bash
git add viva_human_atlas/physiome_organ_map.py tests/test_physiome_organ_map.py
git -c commit.gpgsign=false commit -m "feat(physiome): curated author-keyword -> organ mapping

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Harvest rebuild + physiome registry rewire

**Files:**
- Modify: `viva_human_atlas/model_harvest.py`
- Modify: `scripts/harvest_models.py` (add `--rebuild`)
- Test: `tests/test_model_harvest.py` (append)

**Interfaces:**
- Consumes: Task 1 `resolve_exposures`, Task 2 `build_entry`/`load_citations`.
- Produces: `harvest(..., rebuild=False)` where `rebuild` is `bool | Sequence[str]`; when a source is rebuilt its existing DB rows are dropped before its loop. Physiome registry: `list_fn=resolve_exposures`, `entry_fn=build_entry`, `id_of=exp["identifier"]`; citations loaded once and passed as `citations=` kwarg to every `entry_fn`.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_model_harvest.py
from viva_human_atlas import model_harvest


def test_rebuild_drops_only_named_source(tmp_path, monkeypatch):
    db_path = tmp_path / "db.json"
    from viva_human_atlas import biomodel_hra as bh
    seed = {
        "https://models.physiomeproject.org/e/OLD": {
            "identifier": "https://models.physiomeproject.org/e/OLD",
            "repository": "physiome", "source_id": "OLD", "provenance": {}},
        "https://identifiers.org/biomodels.db:BIOMD1": {
            "identifier": "https://identifiers.org/biomodels.db:BIOMD1",
            "repository": "biomodels", "source_id": "BIOMD1", "provenance": {}},
    }
    bh.write_db(seed, db_path)

    def fake_resolve(**k):
        return [{"slug": "NEW", "identifier": "https://models.physiomeproject.org/exposure/NEW",
                 "name": "n", "abstract": None, "keywords": [], "categories": [],
                 "citation_ids": [], "authors": []}]
    monkeypatch.setattr(model_harvest.physiome, "resolve_exposures", fake_resolve)
    monkeypatch.setattr(model_harvest.physiome, "load_citations", lambda **k: {})
    monkeypatch.setattr(model_harvest.physiome, "build_entry",
                        lambda exp, oi, **k: {"identifier": exp["identifier"], "repository": "physiome",
                                              "source_id": exp["slug"], "provenance": {}})

    res = model_harvest.harvest(["physiome"], out=db_path, rebuild=["physiome"])
    db = bh.load_db(db_path)
    ids = set(db)
    assert "https://models.physiomeproject.org/e/OLD" not in ids   # old physiome row dropped
    assert "https://models.physiomeproject.org/exposure/NEW" in ids  # rebuilt
    assert "https://identifiers.org/biomodels.db:BIOMD1" in ids      # other source preserved
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_model_harvest.py -k rebuild -v`
Expected: FAIL (`harvest() got an unexpected keyword argument 'rebuild'`).

- [ ] **Step 3: Write minimal implementation**

In `model_harvest.py`: update the physiome registry entry and add rebuild handling + citation threading.

```python
# registry: physiome entry
    "physiome": {
        "repository": "physiome",
        "list_fn": lambda **k: physiome.resolve_exposures(query=k.get("query"), limit=k.get("limit"),
                                                          cache_dir=k.get("cache_dir")),
        "entry_fn": lambda exp, oi, **k: physiome.build_entry(exp, oi, citations=k.get("citations"),
                                                             cache_dir=k.get("cache_dir"),
                                                             no_llm=k.get("no_llm", True)),
        "id_of": lambda exp: exp["identifier"],
    },
```

In `harvest(...)` add the `rebuild` parameter and logic:

```python
def harvest(sources=None, *, out=DEFAULT_DB_PATH, query=None, limit=None, no_llm=True,
            force=False, cache_dir=None, rebuild=False, progress=None) -> dict:
    names = list(sources) if sources else list(SOURCES)
    rebuild_set = set(names) if rebuild is True else set(rebuild or [])
    db = bh.load_db(out)
    organ_index = build_organ_index()
    per_source: dict[str, dict] = {}
    citations = physiome.load_citations(cache_dir=cache_dir) if "physiome" in names else {}

    for name in names:
        src = SOURCES[name]
        if name in rebuild_set:
            for k in [k for k, v in db.items() if v.get("repository") == src["repository"]]:
                del db[k]
        counts = {"resolved": 0, "new": 0, "updated": 0, "skipped": 0, "errors": 0}
        items = src["list_fn"](query=query, limit=limit, cache_dir=cache_dir)
        counts["resolved"] = len(items)
        for i, item in enumerate(items, 1):
            ident = src["id_of"](item)
            if not bh.should_process(db, ident, force):
                counts["skipped"] += 1
                continue
            existed = ident in db
            try:
                bh.upsert_db(db, src["entry_fn"](item, organ_index, cache_dir=cache_dir,
                                                 no_llm=no_llm, citations=citations))
                counts["updated" if existed else "new"] += 1
            except Exception as e:  # noqa: BLE001
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

Note: the biomodels/physionet `entry_fn` lambdas already take `**k`, so the extra `citations=` kwarg is harmless to them. Add a `rebuild` config field to `ModelHarvestStep.config_schema` (`"rebuild": "list"`) and pass `rebuild=self.config.get("rebuild") or False` into the `harvest(...)` call in `update()`.

In `scripts/harvest_models.py`: add an argparse `--rebuild` (append, source name, repeatable) and pass it to `harvest(rebuild=args.rebuild)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_model_harvest.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full offline suite**

Run: `.venv/bin/python -m pytest -m "not network" -q`
Expected: PASS (green). Fix any fallout from the physiome/harvest changes (e.g. `test_harvest_cli`, `test_model_harvest_step`, `test_model_harvest_study` may reference removed physiome symbols — update them to the new signatures; do not weaken assertions to pass).

- [ ] **Step 6: Commit**

```bash
git add viva_human_atlas/model_harvest.py scripts/harvest_models.py tests/test_model_harvest.py
git -c commit.gpgsign=false commit -m "feat(harvest): per-source rebuild + physiome pmr3 rewire

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Record fixtures, network smoke test, and rebuild the DB

**Files:**
- Create: `tests/test_physiome_network.py` (network smoke)
- Modify: `datasets/model_hra_map.json` (the rebuilt DB — data artifact)

**Interfaces:**
- Consumes: Tasks 1–4.
- Produces: an updated `model_hra_map.json` with ~978 physiome rows; a `@pytest.mark.network` smoke test.

- [ ] **Step 1: Write the network smoke test**

```python
# tests/test_physiome_network.py
import pytest
from viva_human_atlas import physiome
from viva_human_atlas.biomodel_do import build_organ_index


@pytest.mark.network
def test_pmr3_live_enumerate_and_build():
    ids = physiome.list_exposure_ids()
    assert len(ids) >= 900
    cites = physiome.load_citations()
    exps = physiome.resolve_exposures(_ids=ids[:20])
    assert all(e["identifier"].startswith("https://models.physiomeproject.org/") for e in exps)
    assert any(e["keywords"] for e in exps)
    oi = build_organ_index()
    entries = [physiome.build_entry(e, oi, citations=cites, no_llm=True) for e in exps]
    assert any(m["organs"] for m in entries)
    assert any(m["paper_pmid"] for m in entries)
```

- [ ] **Step 2: Run the smoke test (live)**

Run: `.venv/bin/python -m pytest tests/test_physiome_network.py -m network -v`
Expected: PASS (confirms the live API contract).

- [ ] **Step 3: Run the real rebuild harvest**

Run (populates the per-id + citations cache, then rebuilds physiome rows):
```bash
.venv/bin/python scripts/harvest_models.py --rebuild physiome --source physiome
```
(If `harvest_models.py`'s flags differ, call `harvest` directly:
`.venv/bin/python -c "from viva_human_atlas.model_harvest import harvest; print(harvest(['physiome'], rebuild=['physiome'], progress=print)['per_source'])"`.)
Expected: physiome `new` ≈ 978, `errors` low.

- [ ] **Step 4: Verify the rebuilt DB**

Run:
```bash
.venv/bin/python -c "
import json
from collections import Counter
rows=json.load(open('datasets/model_hra_map.json'))
print('by repo:', Counter(r['repository'] for r in rows))
phys=[r for r in rows if r['repository']=='physiome']
print('physiome:', len(phys), 'mapped:', sum(1 for r in phys if r['organs']),
      'with pmid:', sum(1 for r in phys if r.get('paper_pmid')))
print('methods:', Counter(r['provenance'].get('mapping_method') for r in phys))
"
```
Expected: physiome ≈ 978, mapped materially > 309 (old), many with pmid. Sanity-check a few rows by hand.

- [ ] **Step 5: Commit**

```bash
git add tests/test_physiome_network.py datasets/model_hra_map.json
git -c commit.gpgsign=false commit -m "feat(physiome): rebuild model DB from pmr3 API (~978 exposures)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Regenerate the atlas + publish (user-gated)

**Files:**
- Modify: `datasets/` atlas artifacts (regenerated), gh-pages bundle.

**Interfaces:**
- Consumes: rebuilt `model_hra_map.json`.

- [ ] **Step 1: Regenerate atlas.json**

Run: `.venv/bin/python scripts/build_atlas_pack.py` (deterministic, no network).
Verify the physiome count rose and the atlas viewer JSON is valid; commit the regenerated atlas artifacts.

```bash
git add -A datasets studies
git -c commit.gpgsign=false commit -m "chore(atlas): regenerate atlas pack from rebuilt physiome corpus

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 2: Push branch + open PR**

```bash
git push -u origin feat/physiome-pmr3-api
gh pr create --title "Physiome: harvest full corpus via pmr3 API" --body "<summary + spec link>"
```

- [ ] **Step 3: Publish the read-only dashboard (after merge, on request)**

Per memory: `scripts/publish_dashboard.sh` (build-only) then manual gh-pages push. Do NOT auto-merge; the user approves the merge. Publish only when asked.

---

## Self-Review

- **Spec coverage:** C1 client → Task 1; C2 citations → Task 2; C3 keyword table → Task 3; C4 rebuild wiring → Task 4; C5 atlas/publish → Task 6; testing → embedded per task + Task 5. All covered.
- **Placeholder scan:** PR body `<summary>` in Task 6 is intentional (written at PR time). No code placeholders.
- **Type consistency:** `resolve_exposures`/`fetch_exposure`/`build_entry`/`load_citations`/`resolve_citation`/`keyword_organ_keys` signatures consistent across tasks; exposure record keys (`slug, identifier, name, abstract, keywords, categories, citation_ids, authors`) consistent between Task 1 producer and Task 2/3 consumers.
- **Known risk:** the FTU cell-type assertion (Task 3 Step 1) depends on `HRA_FTUS` content — handled with an explicit fallback instruction, not a fake.
