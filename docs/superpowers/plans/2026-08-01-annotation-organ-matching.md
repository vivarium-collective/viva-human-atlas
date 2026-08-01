# Annotation-based Organ Matching — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an SBML-MIRIAM→Uberon annotation matcher, quantify how many more organs/models it reaches vs name-synonym matching, ship two compelling studies under a reframed `hra-integration` investigation, and surface the Atlas Browser as a per-run analysis tool — all workspace-only (no workbench changes).

**Architecture:** A pure `annotation_match` library parses each BioModel's SBML with libsbml, extracts anatomy CURIEs from MIRIAM CVTerms, and maps them to HRA organs — producing a catalog in the SAME shape as the existing name-synonym catalog so it drops into the coverage/atlas pipeline. A network build script materializes that catalog once (committed dataset). An `annotation_gain` library compares the two catalogs. Two studies (mechanism + recall-gain) and an investigation reframe present it; the workspace `workbench_viewers.py` viewer declares a built-in capability so it links per-run.

**Tech Stack:** Python 3.12, libsbml 5.21.1, pytest, viva_biomodels (SBML fetch), viva_superpowers (`@composite_generator`), process-bigraph 1.5.0, Plotly-via-`viva_human_atlas.viz`.

## Global Constraints

- Python `>=3.12`; imports are `viva_human_atlas`, `viva_biomodels`, `viva_superpowers` (with a `pbg_superpowers` fallback, mirroring `composites/coverage_composite.py`).
- Catalog shape (name AND annotation) is exactly `{biomodel_dos, organ_index, organ_to_models}`; committed catalog envelope is `{n_ids, n_named, n_tagged, catalog}` (see `datasets/biomodel_corpus_catalog.json`).
- BioModels/MIRIAM: anatomy CURIEs are `UBERON:*`, `FMA:*`, `BTO:*` from `urn:miriam:` / `identifiers.org/obo` resource URIs on biological-qualifier CVTerms.
- BioModels page URL: `https://www.ebi.ac.uk/biomodels/<id>` (reuse `atlas_pack.biomodels_url`).
- No new network dependency in tests; all tests pass under `-m "not network"` using committed fixtures/hand-built data. The one network operation (the full-corpus SBML build) is a controller-run step (Task 4), not a subagent task.
- All new studies carry `investigation: hra-integration` and appear in that investigation's `studies:` list (extends `tests/test_investigation_structure.py`).
- Work in the `feat/hra-atlas-browser` worktree at `~/code/viva-human-atlas--atlas-browser`; run Python via its `.venv`. Verify `viva_human_atlas.__file__` resolves inside the worktree before testing.
- Commit after every task; end commit messages with `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

---

### Task 1: Annotation matcher core (`annotation_match.py`)

**Files:**
- Create: `viva_human_atlas/annotation_match.py`
- Create: `tests/test_annotation_match.py`
- Create fixture: `tests/fixtures/sbml/pancreas_uberon.xml`, `tests/fixtures/sbml/no_anatomy.xml`

**Interfaces:**
- Consumes: `libsbml`; `viva_human_atlas.atlas_pack.biomodels_url`.
- Produces:
  - `ANATOMY_PREFIXES = ("uberon", "fma", "bto")`
  - `extract_anatomy_curies(sbml_text: str) -> list[dict]` → deduped `[{"curie": "UBERON:0001264", "qualifier": "BQB_IS_PART_OF", "element": "compartment:default"}, ...]`
  - `map_curie_to_organ(curie: str, organ_index: dict, bto_crosswalk: dict|None=None) -> str|None`
  - `annotate_model(biomodel_id: str, organ_index: dict, *, sbml_text: str, bto_crosswalk: dict|None=None) -> dict` → `{"biomodel_id","name"?,"organs":[{"organ","uberon","via":{...}}],"provenance":{"annotation":"miriam-match@SBML","source":"biomodels"}}`
  - `build_annotation_catalog(model_dos: list[dict], organ_index: dict, *, fetch, bto_crosswalk=None) -> dict` → `{biomodel_dos, organ_index, organ_to_models}` (fetch: `biomodel_id -> sbml_text`)

- [ ] **Step 1: Write fixtures**

`tests/fixtures/sbml/pancreas_uberon.xml` — a minimal valid SBML L3 model whose compartment carries a MIRIAM `bqbiol:isPartOf` annotation to Uberon pancreas:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<sbml xmlns="http://www.sbml.org/sbml/level3/version1/core" level="3" version="1">
  <model id="m1" metaid="m1">
    <listOfCompartments>
      <compartment id="c" metaid="c" constant="true">
        <annotation>
          <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
                   xmlns:bqbiol="http://biomodels.net/biology-qualifiers/">
            <rdf:Description rdf:about="#c">
              <bqbiol:isPartOf>
                <rdf:Bag>
                  <rdf:li rdf:resource="http://identifiers.org/uberon/UBERON:0001264"/>
                </rdf:Bag>
              </bqbiol:isPartOf>
            </rdf:Description>
          </rdf:RDF>
        </annotation>
      </compartment>
    </listOfCompartments>
  </model>
</sbml>
```
`tests/fixtures/sbml/no_anatomy.xml` — same skeleton but the resource is a non-anatomy term, e.g. `http://identifiers.org/go/GO:0005829` (cytosol GO CC), so it yields NO organ.

- [ ] **Step 2: Write the failing test**

```python
# tests/test_annotation_match.py
from pathlib import Path
from viva_human_atlas.annotation_match import (
    extract_anatomy_curies, map_curie_to_organ, annotate_model, build_annotation_catalog,
)

FIX = Path(__file__).resolve().parent / "fixtures" / "sbml"
PANCREAS = (FIX / "pancreas_uberon.xml").read_text(encoding="utf-8")
NO_ANAT = (FIX / "no_anatomy.xml").read_text(encoding="utf-8")

# organ_index like the corpus catalog's: key -> {uberon, sexes, asset_urls}
ORGAN_INDEX = {
    "pancreas": {"uberon": "UBERON:0001264", "sexes": ["Female"], "asset_urls": ["x"]},
    "heart": {"uberon": "UBERON:0000948", "sexes": ["Female"], "asset_urls": ["y"]},
}


def test_extract_finds_uberon_curie():
    curies = extract_anatomy_curies(PANCREAS)
    assert any(c["curie"] == "UBERON:0001264" for c in curies)
    c = next(c for c in curies if c["curie"] == "UBERON:0001264")
    assert c["qualifier"] == "BQB_IS_PART_OF"
    assert "compartment" in c["element"]


def test_extract_ignores_non_anatomy():
    assert extract_anatomy_curies(NO_ANAT) == []


def test_map_curie_uberon_direct():
    assert map_curie_to_organ("UBERON:0001264", ORGAN_INDEX) == "pancreas"
    assert map_curie_to_organ("UBERON:9999999", ORGAN_INDEX) is None


def test_annotate_model_pancreas():
    do = annotate_model("BIOMD0000000137", ORGAN_INDEX, sbml_text=PANCREAS)
    assert do["biomodel_id"] == "BIOMD0000000137"
    assert [o["organ"] for o in do["organs"]] == ["pancreas"]
    assert do["organs"][0]["uberon"] == "UBERON:0001264"
    assert do["organs"][0]["via"]["curie"] == "UBERON:0001264"
    assert do["provenance"]["annotation"] == "miriam-match@SBML"


def test_annotate_model_no_anatomy_is_empty():
    do = annotate_model("BIOMD0000000000", ORGAN_INDEX, sbml_text=NO_ANAT)
    assert do["organs"] == []


def test_build_annotation_catalog_shape_and_index():
    model_dos = [{"biomodel_id": "BIOMD0000000137", "name": "Pancreas model"},
                 {"biomodel_id": "BIOMD0000000000", "name": "Abstract model"}]
    fetch = {"BIOMD0000000137": PANCREAS, "BIOMD0000000000": NO_ANAT}.__getitem__
    cat = build_annotation_catalog(model_dos, ORGAN_INDEX, fetch=fetch)
    assert set(cat) == {"biomodel_dos", "organ_index", "organ_to_models"}
    assert cat["organ_to_models"]["UBERON:0001264"] == ["BIOMD0000000137"]
    assert len(cat["biomodel_dos"]) == 2
```

- [ ] **Step 3: Run the test — RED**

Run: `.venv/bin/python -m pytest tests/test_annotation_match.py -q`
Expected: FAIL (`ModuleNotFoundError: viva_human_atlas.annotation_match`).

- [ ] **Step 4: Implement `annotation_match.py`**

```python
"""Annotation-based organ matching: parse a BioModel's SBML MIRIAM
annotations (Uberon/FMA/BTO CVTerms) and map them to HRA reference organs —
the recall-oriented complement to biomodel_do.py's name-synonym matcher.
Same catalog shape, so it drops into the coverage/atlas pipeline."""
from __future__ import annotations

from typing import Any, Callable, Optional

import libsbml

from viva_human_atlas.atlas_pack import biomodels_url

ANATOMY_PREFIXES = ("uberon", "fma", "bto")
# biological qualifiers we treat as an anatomical assertion about the model part
_QUALIFIERS = {
    libsbml.BQB_IS: "BQB_IS",
    libsbml.BQB_IS_PART_OF: "BQB_IS_PART_OF",
    libsbml.BQB_OCCURS_IN: "BQB_OCCURS_IN",
    libsbml.BQB_HAS_PART: "BQB_HAS_PART",
    libsbml.BQB_IS_VERSION_OF: "BQB_IS_VERSION_OF",
}


def _curie_from_uri(uri: str) -> Optional[str]:
    # e.g. http://identifiers.org/uberon/UBERON:0001264  or urn:miriam:uberon:UBERON%3A0001264
    u = uri.replace("%3A", ":").replace("%3a", ":")
    low = u.lower()
    for pref in ANATOMY_PREFIXES:
        if f"/{pref}/" in low or f":{pref}:" in low:
            tail = u.rsplit("/", 1)[-1].rsplit(":", 1)[-1]
            # tail like "UBERON:0001264" (kept) or "0001264" (needs prefix)
            if ":" in u.rsplit("/", 1)[-1]:
                token = u.rsplit("/", 1)[-1]
                if token.upper().startswith(pref.upper() + ":"):
                    return token.upper() if pref != "fma" else token.upper()
            return f"{pref.upper()}:{tail}"
    return None


def _element_curies(sbo_obj, element_label: str) -> list[dict]:
    out = []
    for i in range(sbo_obj.getNumCVTerms()):
        cv = sbo_obj.getCVTerm(i)
        if cv.getQualifierType() != libsbml.BIOLOGICAL_QUALIFIER:
            continue
        qual = _QUALIFIERS.get(cv.getBiologicalQualifierType())
        if not qual:
            continue
        for j in range(cv.getNumResources()):
            curie = _curie_from_uri(cv.getResourceURI(j))
            if curie:
                out.append({"curie": curie, "qualifier": qual, "element": element_label})
    return out


def extract_anatomy_curies(sbml_text: str) -> list[dict]:
    doc = libsbml.readSBMLFromString(sbml_text)
    model = doc.getModel()
    if model is None:
        return []
    found: list[dict] = []
    found += _element_curies(model, "model")
    for i in range(model.getNumCompartments()):
        c = model.getCompartment(i)
        found += _element_curies(c, f"compartment:{c.getId() or i}")
    for i in range(model.getNumSpecies()):
        s = model.getSpecies(i)
        found += _element_curies(s, f"species:{s.getId() or i}")
    # dedupe on (curie, qualifier, element)
    seen, out = set(), []
    for f in found:
        k = (f["curie"], f["qualifier"], f["element"])
        if k not in seen:
            seen.add(k); out.append(f)
    return out


def map_curie_to_organ(curie: str, organ_index: dict, bto_crosswalk: Optional[dict] = None) -> Optional[str]:
    cu = curie.upper()
    # UBERON/FMA match organ_index keys directly (they carry UBERON+FMA ids)
    for key, entry in organ_index.items():
        ub = (entry.get("uberon") or "").upper()
        if ub and ub == cu:
            return key
    if cu.startswith("BTO:") and bto_crosswalk:
        uber = bto_crosswalk.get(curie) or bto_crosswalk.get(cu)
        if uber:
            return map_curie_to_organ(uber, organ_index)
    return None


def annotate_model(biomodel_id: str, organ_index: dict, *, sbml_text: str,
                   bto_crosswalk: Optional[dict] = None, name: Optional[str] = None) -> dict:
    organs, seen = [], set()
    for hit in extract_anatomy_curies(sbml_text):
        key = map_curie_to_organ(hit["curie"], organ_index, bto_crosswalk)
        if key and key not in seen:
            seen.add(key)
            organs.append({"organ": key, "uberon": organ_index[key].get("uberon"), "via": hit})
    do = {"biomodel_id": biomodel_id, "organs": organs,
          "provenance": {"annotation": "miriam-match@SBML", "source": "biomodels"}}
    if name is not None:
        do["name"] = name
    return do


def build_annotation_catalog(model_dos: list[dict], organ_index: dict, *,
                             fetch: Callable[[str], str], bto_crosswalk: Optional[dict] = None) -> dict:
    biomodel_dos, organ_to_models = [], {}
    for m in model_dos:
        bid = m["biomodel_id"]
        try:
            sbml = fetch(bid)
        except Exception:  # noqa: BLE001 — unfetchable model contributes nothing
            sbml = None
        do = (annotate_model(bid, organ_index, sbml_text=sbml, bto_crosswalk=bto_crosswalk,
                             name=m.get("name")) if sbml is not None
              else {"biomodel_id": bid, "name": m.get("name"), "organs": [],
                    "provenance": {"annotation": "miriam-match@SBML", "source": "biomodels",
                                   "error": "sbml_unavailable"}})
        biomodel_dos.append(do)
        for o in do["organs"]:
            organ_to_models.setdefault(o["uberon"], []).append(bid)
    return {"biomodel_dos": biomodel_dos, "organ_index": organ_index,
            "organ_to_models": organ_to_models}
```
Note: if a fixture assertion about the exact CURIE-token casing fails, adjust `_curie_from_uri` — the test is the contract. Keep `identifiers.org/uberon/UBERON:0001264` → `UBERON:0001264`.

- [ ] **Step 5: Run — GREEN**

Run: `.venv/bin/python -m pytest tests/test_annotation_match.py -q` → PASS (6 tests).

- [ ] **Step 6: Full offline suite + commit**

Run: `.venv/bin/python -m pytest -m "not network" -q` → PASS.
```bash
git add viva_human_atlas/annotation_match.py tests/test_annotation_match.py tests/fixtures/sbml/
git commit -m "feat: SBML MIRIAM -> Uberon annotation matcher"
```

---

### Task 2: Build script + catalog envelope writer

**Files:**
- Create: `scripts/build_annotation_catalog.py`
- Modify: `viva_human_atlas/annotation_match.py` — add `fetch_sbml`, `write_catalog_envelope`
- Test: `tests/test_annotation_catalog_build.py`

**Interfaces:**
- Consumes: `build_annotation_catalog` (Task 1); `biomodels.get_metadata`, `viva_biomodels.run_biomodels.load_biomodel`.
- Produces:
  - `fetch_sbml(biomodel_id: str) -> str` (network; reads `load_biomodel(...).sbml_path`)
  - `write_catalog_envelope(path, catalog: dict) -> dict` — writes `{n_ids, n_named, n_tagged, catalog}` where `n_ids=len(biomodel_dos)`, `n_named=n_ids`, `n_tagged=#dos with >=1 organ`; returns the envelope.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_annotation_catalog_build.py
import json
from viva_human_atlas.annotation_match import write_catalog_envelope


def test_envelope_counts(tmp_path):
    catalog = {"biomodel_dos": [
        {"biomodel_id": "A", "organs": [{"organ": "pancreas", "uberon": "UBERON:0001264"}]},
        {"biomodel_id": "B", "organs": []}],
        "organ_index": {}, "organ_to_models": {"UBERON:0001264": ["A"]}}
    env = write_catalog_envelope(tmp_path / "cat.json", catalog)
    assert env["n_ids"] == 2 and env["n_named"] == 2 and env["n_tagged"] == 1
    on_disk = json.loads((tmp_path / "cat.json").read_text(encoding="utf-8"))
    assert on_disk["catalog"]["organ_to_models"] == {"UBERON:0001264": ["A"]}
```

- [ ] **Step 2: Run — RED** (`ImportError: write_catalog_envelope`).

- [ ] **Step 3: Add to `annotation_match.py`**

```python
import json
from pathlib import Path


def fetch_sbml(biomodel_id: str) -> str:
    import biomodels
    from viva_biomodels.run_biomodels import load_biomodel
    meta = biomodels.get_metadata(biomodel_id)
    result = load_biomodel(biomodel_id, meta)
    return Path(result.sbml_path).read_text(encoding="utf-8")


def write_catalog_envelope(path, catalog: dict) -> dict:
    dos = catalog["biomodel_dos"]
    env = {"n_ids": len(dos), "n_named": len(dos),
           "n_tagged": sum(1 for d in dos if d.get("organs")),
           "catalog": catalog}
    Path(path).write_text(json.dumps(env, indent=2), encoding="utf-8")
    return env
```

- [ ] **Step 4: Run — GREEN**, then write the build script:

```python
# scripts/build_annotation_catalog.py
"""Materialize datasets/biomodel_annotation_catalog.json — the annotation
(SBML MIRIAM -> Uberon) organ catalog over the full curated corpus.

Network: fetches/caches each model's SBML (biomodels API). Run once:
  PYTHONUTF8=1 .venv/bin/python scripts/build_annotation_catalog.py
Resumable/robust: models whose SBML can't be fetched/parsed are skipped and
counted, never aborting the run.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from viva_human_atlas.annotation_match import (
    build_annotation_catalog, fetch_sbml, write_catalog_envelope,
)
from viva_human_atlas.coverage import load_corpus_catalog

CORPUS = REPO / "datasets" / "biomodel_corpus_catalog.json"
OUT = REPO / "datasets" / "biomodel_annotation_catalog.json"
BTO = REPO / "datasets" / "bto_uberon_crosswalk.json"


def main() -> None:
    corpus = load_corpus_catalog(str(CORPUS))
    organ_index = corpus["organ_index"]
    model_dos = corpus["biomodel_dos"]
    bto = None
    if BTO.exists():
        import json
        bto = json.loads(BTO.read_text(encoding="utf-8"))
    n = len(model_dos)
    done = {"i": 0, "ok": 0, "err": 0}

    def fetch(bid: str) -> str:
        done["i"] += 1
        if done["i"] % 25 == 0:
            print(f"  {done['i']}/{n} (tagged-so-far via ok fetches {done['ok']}, errors {done['err']})")
        try:
            s = fetch_sbml(bid)
            done["ok"] += 1
            return s
        except Exception as e:  # noqa: BLE001
            done["err"] += 1
            raise

    catalog = build_annotation_catalog(model_dos, organ_index, fetch=fetch, bto_crosswalk=bto)
    env = write_catalog_envelope(OUT, catalog)
    print(f"Wrote {OUT}: n_ids={env['n_ids']} n_tagged={env['n_tagged']} "
          f"(fetch ok={done['ok']} err={done['err']}); organs={len(catalog['organ_to_models'])}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Full suite + commit** (do NOT run the network build here — that's Task 4)
```bash
git add scripts/build_annotation_catalog.py viva_human_atlas/annotation_match.py tests/test_annotation_catalog_build.py
git commit -m "feat: annotation catalog build script + envelope writer"
```

---

### Task 3: Recall-gain comparison (`annotation_gain.py`)

**Files:**
- Create: `viva_human_atlas/annotation_gain.py`
- Test: `tests/test_annotation_gain.py`

**Interfaces:**
- Consumes: catalogs of shape `{biomodel_dos, organ_index, organ_to_models}`.
- Produces: `compare_catalogs(name_catalog: dict, annotation_catalog: dict) -> dict` (shape per the design spec's Section C).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_annotation_gain.py
from viva_human_atlas.annotation_gain import compare_catalogs

OI = {"pancreas": {"uberon": "UBERON:0001264"}, "liver": {"uberon": "UBERON:0002107"},
      "kidney": {"uberon": "UBERON:0004538"}}


def _cat(o2m):
    dos = []
    for uber, ids in o2m.items():
        for i in ids:
            dos.append({"biomodel_id": i, "organs": [{"organ": "x", "uberon": uber}]})
    return {"biomodel_dos": dos, "organ_index": OI, "organ_to_models": o2m}


def test_gain_adds_organ_and_models():
    name = _cat({"UBERON:0001264": ["A", "B"]})                       # pancreas: A,B
    anno = _cat({"UBERON:0001264": ["A", "C"], "UBERON:0002107": ["D"]})  # +C pancreas, +liver D
    r = compare_catalogs(name, anno)
    assert set(r["delta"]["organs_added"]) == {"liver"}
    assert r["union"]["n_models_total"] >= r["name"]["n_models_total"]
    assert r["union"]["n_models_total"] >= r["annotation"]["n_models_total"]
    assert r["delta"]["n_models_added"] == r["union"]["n_models_total"] - r["name"]["n_models_total"]
    per = {row["organ"]: row for row in r["delta"]["per_organ"]}
    assert per["pancreas"]["union_models"] == 3  # A,B,C
    assert per["liver"]["added"] is True
```

- [ ] **Step 2: RED**, **Step 3: implement**:

```python
"""Compare the name-synonym organ catalog with the annotation (MIRIAM)
catalog: how many more organs and models the annotation matcher reaches."""
from __future__ import annotations


def _uberon_to_organ(organ_index):
    return {e["uberon"]: k for k, e in organ_index.items() if e.get("uberon")}


def _stats(catalog, u2o):
    o2m = catalog["organ_to_models"]
    organs = sorted({u2o.get(u, u) for u in o2m})
    models = {m for ids in o2m.values() for m in ids}
    return {"organs": organs, "n_models_total": len(models),
            "n_models_tagged": len(models), "_by_organ": o2m}


def compare_catalogs(name_catalog: dict, annotation_catalog: dict) -> dict:
    u2o = _uberon_to_organ(name_catalog["organ_index"])
    name, anno = _stats(name_catalog, u2o), _stats(annotation_catalog, u2o)
    all_ub = set(name["_by_organ"]) | set(anno["_by_organ"])
    per_organ, union_models = [], set()
    for ub in sorted(all_ub, key=lambda u: u2o.get(u, u)):
        nm, am = set(name["_by_organ"].get(ub, [])), set(anno["_by_organ"].get(ub, []))
        um = nm | am
        union_models |= um
        per_organ.append({"organ": u2o.get(ub, ub), "uberon": ub,
                          "name_models": len(nm), "annotation_models": len(am),
                          "union_models": len(um), "added": bool(am - nm)})
    union_organs = sorted({u2o.get(u, u) for u in all_ub})
    organs_added = sorted(set(anno["organs"]) - set(name["organs"]))
    n_corpus = len(name_catalog["biomodel_dos"]) or 1
    def strip(s): return {k: v for k, v in s.items() if not k.startswith("_")}
    return {
        "name": strip(name), "annotation": strip(anno),
        "union": {"organs": union_organs, "n_models_total": len(union_models),
                  "n_models_tagged": len(union_models)},
        "delta": {"organs_added": organs_added,
                  "n_models_added": len(union_models) - name["n_models_total"],
                  "per_organ": per_organ},
        "summary": {"pct_corpus_tagged_name": round(100 * name["n_models_total"] / n_corpus, 1),
                    "pct_corpus_tagged_annotation": round(100 * anno["n_models_total"] / n_corpus, 1)},
    }
```

- [ ] **Step 4: GREEN**, **Step 5: full suite + commit**
```bash
git add viva_human_atlas/annotation_gain.py tests/test_annotation_gain.py
git commit -m "feat: name-vs-annotation recall-gain comparison"
```

---

### Task 4: Build & commit the annotation catalog (CONTROLLER-RUN, network)

**This task is run by the controller, not a subagent** — it fetches ~1,096 SBML files over the network and can take a long time. Run it in the background.

- [ ] **Step 1:** `cd ~/code/viva-human-atlas--atlas-browser && PYTHONUTF8=1 .venv/bin/python scripts/build_annotation_catalog.py` (background). It prints progress every 25 models and a final `n_tagged` / organs summary.
- [ ] **Step 2:** Sanity-check the output: `datasets/biomodel_annotation_catalog.json` exists, valid JSON, `n_ids==1096`, `n_tagged >= 82` (should meet-or-exceed the name-matcher's 82), organ_to_models non-empty.
- [ ] **Step 3:** Quick gain check: load both catalogs, run `compare_catalogs`, print `delta.organs_added` and `delta.n_models_added` — the headline numbers the studies will report.
- [ ] **Step 4:** Commit `datasets/biomodel_annotation_catalog.json` (+ `datasets/bto_uberon_crosswalk.json` if a curated one was added).
```bash
git add datasets/biomodel_annotation_catalog.json datasets/bto_uberon_crosswalk.json 2>/dev/null
git commit -m "data: committed annotation (MIRIAM) organ catalog over the curated corpus"
```

---

### Task 5: Two studies + composites

**Files:**
- Create: `viva_human_atlas/annotation_coverage.py` (thin Steps: `AnnotationMatchStep`, `RecallGainStep`)
- Create: `viva_human_atlas/composites/annotation_composite.py` (two `@composite_generator`s)
- Create: `studies/annotation-organ-matching/study.yaml`, `studies/annotation-recall-gain/study.yaml`
- Test: `tests/test_annotation_studies_load.py`

**Interfaces:**
- Consumes: committed `datasets/biomodel_annotation_catalog.json` (Task 4), `annotation_gain.compare_catalogs`, `coverage.load_corpus_catalog` (name catalog), the `@composite_generator` pattern from `composites/coverage_composite.py`.
- Produces: two composite generators `viva_human_atlas.composites.annotation_composite.annotation-organ-matching` and `…​.annotation-recall-gain`, each emitting a summary node via RAMEmitter (so runs advertise `observables`).

- [ ] **Step 1: Write the failing test** (mirror `tests/test_hra_studies_load.py`):

```python
# tests/test_annotation_studies_load.py
from viva_superpowers.composite_generator import discover_generators, known_composite_ids  # or the repo's discovery util
# If the repo exposes a different discovery helper, mirror test_hra_studies_load.py exactly.

def test_annotation_generators_discovered():
    ids = set(known_composite_ids())
    assert any(i.endswith("annotation-organ-matching") for i in ids)
    assert any(i.endswith("annotation-recall-gain") for i in ids)
```
(If the existing discovery test uses a different import, COPY that test's imports/structure from `tests/test_hra_3d_studies_load.py` verbatim and adapt the two names.)

- [ ] **Step 2: RED.**

- [ ] **Step 3: Implement Steps** in `annotation_coverage.py` — two `process_bigraph.Step`s:
  - `AnnotationMatchStep` (`config: {catalog_path}`; `update` loads the annotation catalog, returns `{"annotation_summary": {n_ids, n_tagged, n_organs, qualifier_counts, ontology_counts}, "sample_provenance": [first N dos with organs+via]}`). Compute `qualifier_counts`/`ontology_counts` by scanning `biomodel_dos[].organs[].via`.
  - `RecallGainStep` (`config: {name_catalog_path, annotation_catalog_path}`; `update` runs `compare_catalogs` and returns `{"gain": <compare result>}`). For the name catalog, load `datasets/biomodel_corpus_catalog.json` via `load_corpus_catalog`.
  Use fully-dotted `address = "local:viva_human_atlas.annotation_coverage.<Step>"` (see `coverage_composite.COVERAGE_STEP_ADDRESS`).

- [ ] **Step 4: Implement composites** in `composites/annotation_composite.py` — mirror `coverage_composite.py` exactly (same imports/fallback, `@composite_generator(name=…)`, RAMEmitter emit-schema with the Step's output keys, `run_steps_on_init: True`). Default `catalog_path` → the committed dataset path.

- [ ] **Step 5: Write the study YAMLs** — mirror `studies/glucose-biomodel-do/study.yaml` structure (schema_version 4, `investigation: hra-integration`, study_card, readouts, report with verdict, baseline.composite pointing at the new generator id, `embed_visualizations` for recall-gain → `/reports/figures/annotation-recall-gain/recall-gain.html`). Study cards:
  - `annotation-organ-matching`: mechanism/provenance framing ("how a model gets an organ from its SBML MIRIAM annotations, transparently"). `main_expert_question`: "Which biological qualifiers / ontologies carry the most organ signal?"
  - `annotation-recall-gain`: comparison framing with the measured Δ organs / Δ models from Task 4 Step 3 (fill in the real numbers). `main_expert_question`: "How much organ/model coverage does annotation-matching add over name-only matching?"

- [ ] **Step 6: GREEN** (`.venv/bin/python -m pytest tests/test_annotation_studies_load.py -q`), then verify both composites actually build+run once:
```bash
.venv/bin/python -c "from viva_human_atlas.composites.annotation_composite import *; print('composites import OK')"
```

- [ ] **Step 7: Full suite + commit**
```bash
git add viva_human_atlas/annotation_coverage.py viva_human_atlas/composites/annotation_composite.py studies/annotation-organ-matching/ studies/annotation-recall-gain/ tests/test_annotation_studies_load.py
git commit -m "feat: annotation-organ-matching + annotation-recall-gain studies"
```

---

### Task 6: Recall-gain figure + investigation reframe

**Files:**
- Modify: `viva_human_atlas/viz.py` — add `grouped_bar_html(categories, series, *, title, yaxis_title)` if not present
- Modify: `scripts/build_study_figures.py` — add `build_annotation_recall_gain_figure()` (+ call in `main`)
- Modify: `investigations/hra-integration/investigation.yaml`
- Test: extend `tests/test_investigation_structure.py`

**Interfaces:**
- Consumes: `annotation_gain.compare_catalogs`, `viz.write_study_figure`, both committed catalogs.
- Produces: `reports/figures/annotation-recall-gain/recall-gain.html`; a reframed investigation listing both new studies.

- [ ] **Step 1: Write/extend the failing test** — add to `tests/test_investigation_structure.py`:
```python
def test_annotation_studies_registered_under_hra_integration():
    import yaml
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    inv = yaml.safe_load((root / "investigations" / "hra-integration" / "investigation.yaml").read_text(encoding="utf-8"))
    assert "annotation-organ-matching" in inv["studies"]
    assert "annotation-recall-gain" in inv["studies"]
```
- [ ] **Step 2: RED.**
- [ ] **Step 3:** Add `grouped_bar_html` to `viz.py` (Plotly grouped bar; mirror `bar_html`'s structure — return a self-contained `<div>` with the Plotly CDN include exactly as `bar_html` does).
- [ ] **Step 4:** Add `build_annotation_recall_gain_figure()` to `build_study_figures.py`: load name catalog (`coverage.load_corpus_catalog`) + annotation catalog, `compare_catalogs`, build a grouped bar over `delta.per_organ` (series: name_models, annotation_models, union_models) → `_write("annotation-recall-gain", "recall-gain", html)`; call it from `main()`.
- [ ] **Step 5:** Reframe `investigations/hra-integration/investigation.yaml`: add both studies to `studies:`; rewrite `lead` + `executive.what_is_this`/`verdict` around *name-match → annotation-match → Atlas Browser*; update `scientific_argument.evidence_for` with the measured gain (real numbers from Task 4); add two `acceptance_criteria` (one per new study); reference `studies/hra-atlas-browser/viz/atlas/`.
- [ ] **Step 6:** Generate the figure: `PYTHONUTF8=1 .venv/bin/python -c "import scripts.build_study_figures as b; b.build_annotation_recall_gain_figure()"` (offline — reads committed catalogs).
- [ ] **Step 7: GREEN + full suite + commit**
```bash
git add viva_human_atlas/viz.py scripts/build_study_figures.py investigations/hra-integration/investigation.yaml reports/figures/annotation-recall-gain/ tests/test_investigation_structure.py
git commit -m "feat: recall-gain figure + reframed hra-integration investigation"
```

---

### Task 7: Per-run Atlas Browser link (workspace-only)

**Files:**
- Modify: `viva_human_atlas/workbench_viewers.py`
- Test: `tests/test_workbench_atlas_viewer.py` (extend)

**Interfaces:**
- Consumes: the existing `get_viewers`/`_atlas_*` contract (from the atlas-browser work already on this branch).
- Produces: the `hra-atlas-browser` viewer dict gains `"requires": ["observables"]` and `"kind": "launcher"` so the stock workbench matches it to any run advertising the built-in `observables` capability, surfacing an "Atlas Browser" launch link per compatible run. `launch(ws_root, study, run, ctx)` already resolves to `studies/<study>/viz/atlas/index.html`.

- [ ] **Step 1: Write the failing test** — extend `tests/test_workbench_atlas_viewer.py`:
```python
def test_atlas_viewer_requires_observables():
    from viva_human_atlas.workbench_viewers import get_viewers
    import tempfile, pathlib
    ws = pathlib.Path(tempfile.mkdtemp())
    (ws / "studies" / "hra-atlas-browser" / "viz" / "atlas").mkdir(parents=True)
    (ws / "studies" / "hra-atlas-browser" / "viz" / "atlas" / "atlas.json").write_text("{}")
    viewer = next(v for v in get_viewers(ws) if v["id"] == "hra-atlas-browser")
    assert viewer.get("requires") == ["observables"]
```
- [ ] **Step 2: RED.**
- [ ] **Step 3:** Add `"requires": ["observables"]` to the `hra-atlas-browser` viewer dict in `get_viewers`. Do not change the existing `targets`/`launch`/`applies`.
- [ ] **Step 4: GREEN + full suite.**
- [ ] **Step 5:** (Verification, non-blocking) If a live `vivarium-workbench serve` is available, confirm the Runs table shows an "Atlas Browser" link on a run with observables and the viewer opens; otherwise note it as manual verification.
- [ ] **Step 6: Commit**
```bash
git add viva_human_atlas/workbench_viewers.py tests/test_workbench_atlas_viewer.py
git commit -m "feat: surface Atlas Browser as a per-run analysis tool (requires observables)"
```

---

### Task 8: Full-suite verification + branch hygiene

- [ ] **Step 1:** `.venv/bin/python -m pytest -m "not network" -q` → PASS (record count).
- [ ] **Step 2:** `git log --oneline origin/main..HEAD` → only atlas-browser + annotation commits, no foreign commits (stop if any foreign appears).
- [ ] **Step 3:** Add a short README note under the existing HRA Atlas Browser pointer: the annotation-recall studies and that the Atlas Browser is launchable per-run from the Analyses tab.
- [ ] **Step 4: Commit** `git add README.md && git commit -m "docs: annotation studies + per-run Atlas Browser note"`.

---

## Self-Review

**Spec coverage:**
- Annotation matcher (extract/map/annotate/build) → Task 1. ✓
- Full-corpus committed catalog → Task 2 (script) + Task 4 (run/commit). ✓
- Recall-gain comparison → Task 3; figure → Task 6. ✓
- Two studies (mechanism + gain) under hra-integration → Task 5; registration + reframe → Task 6. ✓
- Investigation reframed & linked to Atlas Browser → Task 6. ✓
- Per-run workbench link, workspace-only, no workbench changes → Task 7. ✓
- Testing offline via fixtures/hand-built + committed catalogs → Tasks 1,3,5,6,7. ✓

**Placeholder scan:** No TBD/TODO; every code step carries real code. Task 5 study-YAML numbers are filled from Task 4's measured output (explicitly flagged, not a placeholder). ✓

**Type consistency:** catalog shape `{biomodel_dos, organ_index, organ_to_models}` identical across Tasks 1–6; `compare_catalogs` return shape matches the figure consumer (Task 6) and study Step (Task 5); `annotate_model`/`build_annotation_catalog`/`fetch_sbml`/`write_catalog_envelope` signatures consistent Tasks 1–2. ✓

**Ordering note:** Task 4 (network build) must complete before Task 5/6 can use real numbers, but Task 5/6 CODE is testable with fixtures/hand-built data regardless. If Task 4 is still running, implement 5/6 against the committed catalog once it lands, or use the small fixtures for the load tests and backfill the study-card numbers.
