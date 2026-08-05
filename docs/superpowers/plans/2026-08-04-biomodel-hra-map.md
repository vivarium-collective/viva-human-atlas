# BioModels → HRA mapping extractor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reusable script that maps every curated BioModel to HRA anatomy/cell-type entities, molecular ids, and paper-extracted details, emitting a JSON DB keyed by model id.

**Architecture:** Thin CLI orchestrator (`scripts/build_biomodel_hra_map.py`) over four focused, unit-testable library modules in `viva_human_atlas/`. Each per-model stage (SBML parse, metadata, HRA mapping, literature fetch, LLM extract) is independently cached and error-isolated; results are upserted into a JSON DB with atomic writes and resume.

**Tech Stack:** Python 3.12, `libsbml` (SBML parse), the `biomodels` client (SBML + metadata), `requests` (NCBI E-utilities + Europe PMC), the `anthropic` SDK (Claude structured extraction). Tests: pytest, everything network/LLM mocked offline; live paths marked `network`.

## Global Constraints

- Reuse existing seams, do not duplicate: `annotation_match.fetch_sbml` / `_curie_from_uri` / `_QUALIFIERS`, `biomodel_do.build_organ_index` / `_match_organ_key`, `ftu_coverage.HRA_FTUS`, `biomodels_search.fetch_all_biomodel_ids`.
- All list-valued id fields are **sorted, deduped** lists of strings.
- Ontology CURIEs are upper-cased with a colon (`CHEBI:17234`, `UBERON:0001264`, `GO:0006006`, `CL:0000169`); accession-style ids keep their native case (UniProt `P01308`, KEGG `C00031`).
- Every network/LLM function takes an injectable client/`_get` seam and a `cache_dir`; tests pass stubs and never hit the network.
- `identifier` IRI form: `https://identifiers.org/biomodels.db:<BIOMD id>`.
- Default LLM model id: `claude-haiku-4-5-20251001`. `--no-llm` must fully skip the `anthropic` import and API use.
- Offline test suite (`pytest -m "not network"`) stays green; live stages are marked `@pytest.mark.network`.

---

### Task 1: `sbml_identifiers` — extract all identifier classes from SBML

**Files:**
- Create: `viva_human_atlas/sbml_identifiers.py`
- Test: `tests/test_sbml_identifiers.py`

**Interfaces:**
- Consumes: `libsbml`; the CVTerm-walking pattern from `annotation_match._element_curies`.
- Produces:
  - `collection_of_uri(uri: str) -> tuple[str, str] | None` — `(collection, curie_or_accession)` where `collection ∈ {chebi,uniprot,kegg,go,cl,uberon,fma,bto}`, else `None`.
  - `extract_identifiers(sbml_text: str) -> dict` — `{"chebi":[...], "uniprot":[...], "kegg":[...], "go":[...], "cl":[...], "uberon":[...], "fma":[...], "bto":[...], "n_species": int}` (each list sorted+deduped).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_sbml_identifiers.py
from viva_human_atlas.sbml_identifiers import collection_of_uri, extract_identifiers


def test_collection_of_uri_recognises_each_class():
    cases = {
        "http://identifiers.org/chebi/CHEBI:17234": ("chebi", "CHEBI:17234"),
        "http://identifiers.org/uniprot/P01308": ("uniprot", "P01308"),
        "http://identifiers.org/kegg.compound/C00031": ("kegg", "C00031"),
        "http://identifiers.org/go/GO:0006006": ("go", "GO:0006006"),
        "http://purl.obolibrary.org/obo/CL_0000169": ("cl", "CL:0000169"),
        "http://identifiers.org/uberon/UBERON:0001264": ("uberon", "UBERON:0001264"),
        "urn:miriam:obo.fma:FMA%3A16016": ("fma", "FMA:16016"),
        "http://identifiers.org/bto/BTO:0000991": ("bto", "BTO:0000991"),
    }
    for uri, expected in cases.items():
        assert collection_of_uri(uri) == expected
    assert collection_of_uri("http://identifiers.org/pubmed/11073807") is None


_SBML = """<?xml version="1.0" encoding="UTF-8"?>
<sbml xmlns="http://www.sbml.org/sbml/level3/version1/core" level="3" version="1">
 <model id="m">
  <listOfSpecies>
   <species id="glucose" metaid="s1">
    <annotation><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
      xmlns:bqbiol="http://biomodels.net/biology-qualifiers/">
     <rdf:Description rdf:about="#s1">
      <bqbiol:is><rdf:Bag>
        <rdf:li rdf:resource="http://identifiers.org/chebi/CHEBI:17234"/>
        <rdf:li rdf:resource="http://identifiers.org/kegg.compound/C00031"/>
      </rdf:Bag></bqbiol:is>
      <bqbiol:isPartOf><rdf:Bag>
        <rdf:li rdf:resource="http://identifiers.org/uberon/UBERON:0001264"/>
      </rdf:Bag></bqbiol:isPartOf>
     </rdf:Description>
    </rdf:RDF></annotation>
   </species>
   <species id="insulin" metaid="s2">
    <annotation><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
      xmlns:bqbiol="http://biomodels.net/biology-qualifiers/">
     <rdf:Description rdf:about="#s2">
      <bqbiol:is><rdf:Bag>
        <rdf:li rdf:resource="http://identifiers.org/uniprot/P01308"/>
      </rdf:Bag></bqbiol:is>
     </rdf:Description>
    </rdf:RDF></annotation>
   </species>
  </listOfSpecies>
 </model>
</sbml>"""


def test_extract_identifiers_collects_all_classes():
    out = extract_identifiers(_SBML)
    assert out["chebi"] == ["CHEBI:17234"]
    assert out["kegg"] == ["C00031"]
    assert out["uniprot"] == ["P01308"]
    assert out["uberon"] == ["UBERON:0001264"]
    assert out["n_species"] == 2
    assert out["go"] == [] and out["cl"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=$PWD pytest tests/test_sbml_identifiers.py -q`
Expected: FAIL — `ModuleNotFoundError: viva_human_atlas.sbml_identifiers`.

- [ ] **Step 3: Write minimal implementation**

```python
# viva_human_atlas/sbml_identifiers.py
"""Extract every identifier class MIRIAM-annotated in a BioModel's SBML.

Generalizes annotation_match.py's anatomy-only CVTerm walk to also collect the
molecular (CHEBI/UniProt/KEGG/GO) and cell-type (CL) identifiers, keyed by the
identifiers.org collection each resource URI belongs to."""
from __future__ import annotations

import libsbml

# identifiers.org collection substring (lowercased URI) -> output key.
# Order matters: check "kegg.compound"/"kegg.reaction" etc. via the "kegg" stem.
_COLLECTIONS = (
    ("chebi", "chebi"),
    ("uniprot", "uniprot"),
    ("kegg", "kegg"),
    ("/go/", "go"), ("obo/go", "go"), (":go:", "go"), ("_go_", "go"),
    ("/cl/", "cl"), ("obo/cl", "cl"), (":cl:", "cl"),
    ("uberon", "uberon"),
    ("fma", "fma"),
    ("bto", "bto"),
)
# Prefixed CURIE classes (id keeps a PREFIX:number form, upper-cased).
_CURIE_KEYS = {"chebi", "go", "cl", "uberon", "fma", "bto"}


def collection_of_uri(uri: str):
    """`(collection, curie_or_accession)` for a MIRIAM resource URI, or None."""
    u = uri.replace("%3A", ":").replace("%3a", ":")
    low = u.lower()
    token = u.rstrip("/").rsplit("/", 1)[-1]
    for needle, key in _COLLECTIONS:
        if needle in low:
            tail = token.rsplit(":", 1)[-1].rsplit("_", 1)[-1]
            if key in _CURIE_KEYS:
                return key, f"{key.upper()}:{tail}"
            return key, tail  # uniprot / kegg accession, native case
    return None


def _element_ids(sbo_obj, bucket: dict) -> None:
    for i in range(sbo_obj.getNumCVTerms()):
        cv = sbo_obj.getCVTerm(i)
        if cv.getQualifierType() != libsbml.BIOLOGICAL_QUALIFIER:
            continue
        for j in range(cv.getNumResources()):
            hit = collection_of_uri(cv.getResourceURI(j))
            if hit:
                key, ident = hit
                bucket[key].add(ident)


def extract_identifiers(sbml_text: str) -> dict:
    keys = ["chebi", "uniprot", "kegg", "go", "cl", "uberon", "fma", "bto"]
    bucket = {k: set() for k in keys}
    doc = libsbml.readSBMLFromString(sbml_text)
    model = doc.getModel()
    if model is None:
        return {**{k: [] for k in keys}, "n_species": 0}
    _element_ids(model, bucket)
    for i in range(model.getNumCompartments()):
        _element_ids(model.getCompartment(i), bucket)
    for i in range(model.getNumSpecies()):
        _element_ids(model.getSpecies(i), bucket)
    out = {k: sorted(v) for k, v in bucket.items()}
    out["n_species"] = model.getNumSpecies()
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=$PWD pytest tests/test_sbml_identifiers.py -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add viva_human_atlas/sbml_identifiers.py tests/test_sbml_identifiers.py
git commit -m "feat(sbml): extract chebi/uniprot/kegg/go/cl/uberon/fma/bto from SBML"
```

---

### Task 2: `HRA_FTUS` Uberon enrichment + `hra_mapping`

**Files:**
- Modify: `viva_human_atlas/ftu_coverage.py` (add `"uberon"` to each `HRA_FTUS` entry)
- Create: `viva_human_atlas/hra_mapping.py`
- Test: `tests/test_hra_mapping.py`

**Interfaces:**
- Consumes: `biomodel_do.build_organ_index`, `biomodel_do._match_organ_key`, `ftu_coverage.HRA_FTUS` (now with `uberon`).
- Produces: `map_to_hra(uberon_ids, name, organ_index, *, ftus=None) -> dict` returning `{"organs":[{"label","uberon"}], "functional_tissue_units":[{"label","uberon"}], "cell_types":[{"label","cl"}], "uberon_organ_ids":[...], "uberon_subregion_ids":[...]}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_hra_mapping.py
from viva_human_atlas.hra_mapping import map_to_hra
from viva_human_atlas.ftu_coverage import HRA_FTUS


def test_hra_ftus_have_uberon_ids():
    for f in HRA_FTUS:
        assert f.get("uberon", "").startswith("UBERON:"), f["ftu"]


ORGAN_INDEX = {
    "pancreas": {"uberon": "UBERON:0001264", "asset_urls": []},
    "liver": {"uberon": "UBERON:0002107", "asset_urls": []},
}


def test_map_to_hra_organ_ftu_celltype():
    out = map_to_hra(["UBERON:0001264", "UBERON:0000006"], "beta-cell insulin model", ORGAN_INDEX)
    assert {"label": "pancreas", "uberon": "UBERON:0001264"} in out["organs"]
    ftu_labels = {f["label"] for f in out["functional_tissue_units"]}
    assert any("islet" in l for l in ftu_labels)
    assert all(f["uberon"].startswith("UBERON:") for f in out["functional_tissue_units"])
    cl_ids = {c["cl"] for c in out["cell_types"]}
    assert "CL:0000169" in cl_ids  # beta cell, from the islet FTU
    assert "UBERON:0001264" in out["uberon_organ_ids"]
    assert "UBERON:0000006" in out["uberon_subregion_ids"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=$PWD pytest tests/test_hra_mapping.py -q`
Expected: FAIL — module missing and `HRA_FTUS` entries lack `uberon`.

- [ ] **Step 3a: Add `uberon` to each `HRA_FTUS` entry**

In `viva_human_atlas/ftu_coverage.py`, add a `"uberon"` key to every dict in `HRA_FTUS`. Values (verify against the Uberon ontology; these are the standard FTU terms):

```
pancreatic islet of Langerhans   -> UBERON:0000006
kidney renal corpuscle/glomerulus-> UBERON:0001229
kidney nephron                    -> UBERON:0001285
liver lobule                      -> UBERON:0004647
lung alveolus                     -> UBERON:0002299
large-intestine crypt of Lieberkuhn -> UBERON:0001984
small-intestine crypt-villus axis -> UBERON:0013640
cardiac muscle / myocardium unit  -> UBERON:0002349
ovarian follicle                  -> UBERON:0001305
skin epidermis unit               -> UBERON:0001003
lymph node follicle               -> UBERON:0010393
```

- [ ] **Step 3b: Write `hra_mapping.py`**

```python
# viva_human_atlas/hra_mapping.py
"""Map a model's Uberon ids + name to HRA organs, FTUs (with Uberon), and the
FTUs' cell types (with CL) — the curated HRA view for the biomodel-HRA DB."""
from __future__ import annotations

from typing import Optional

from viva_human_atlas.biomodel_do import _match_organ_key
from viva_human_atlas.ftu_coverage import HRA_FTUS


def map_to_hra(uberon_ids, name: str, organ_index: dict, *, ftus: Optional[list] = None) -> dict:
    ftu_defs = ftus if ftus is not None else HRA_FTUS
    uberon_ids = list(uberon_ids or [])
    organ_uberons = {e["uberon"] for e in organ_index.values() if e.get("uberon")}

    uberon_organ_ids = sorted(u for u in uberon_ids if u in organ_uberons)
    uberon_subregion_ids = sorted(u for u in uberon_ids if u not in organ_uberons)

    # organs: organ-level Uberon hits + name-synonym organ matches.
    ub_to_organ = {e["uberon"]: k for k, e in organ_index.items() if e.get("uberon")}
    organ_keys = {ub_to_organ[u] for u in uberon_organ_ids}
    name_key = _match_organ_key((name or "").lower())
    if name_key:
        organ_keys.add(name_key)
    organs = sorted(
        ({"label": k, "uberon": organ_index.get(k, {}).get("uberon")} for k in organ_keys),
        key=lambda o: o["label"],
    )

    # FTUs whose organ is among the model's organs, carrying their Uberon + CL.
    ftu_out, cell_types, seen_cl = [], [], set()
    for f in ftu_defs:
        if f["organ"] in organ_keys or (name_key and f["organ"] == name_key):
            ftu_out.append({"label": f["ftu"], "uberon": f.get("uberon")})
            for ct in f.get("cell_types", []):
                if ct["cl"] not in seen_cl:
                    seen_cl.add(ct["cl"])
                    cell_types.append({"label": ct["label"], "cl": ct["cl"]})

    return {
        "organs": organs,
        "functional_tissue_units": ftu_out,
        "cell_types": cell_types,
        "uberon_organ_ids": uberon_organ_ids,
        "uberon_subregion_ids": uberon_subregion_ids,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=$PWD pytest tests/test_hra_mapping.py tests/test_ftu_coverage.py -q`
Expected: PASS (new tests + existing FTU tests still green).

- [ ] **Step 5: Commit**

```bash
git add viva_human_atlas/hra_mapping.py viva_human_atlas/ftu_coverage.py tests/test_hra_mapping.py
git commit -m "feat(hra): map uberon+name to organs/FTUs/cell-types; add uberon to HRA_FTUS"
```

---

### Task 3: `literature` — abstract + open-access full text

**Files:**
- Create: `viva_human_atlas/literature.py`
- Test: `tests/test_literature.py`

**Interfaces:**
- Consumes: `requests` (default), an injectable `_get` for tests, a `cache_dir`.
- Produces:
  - `fetch_abstract(pmid, *, _get=None, cache_dir=None) -> str | None`
  - `fetch_oa_fulltext(pmid, *, _get=None, cache_dir=None) -> str | None`
  - `get_literature_text(pmid, doi=None, *, _get=None, cache_dir=None) -> dict` → `{"abstract","fulltext","text_source","has_fulltext"}` where `text_source ∈ {"none","abstract","abstract+fulltext"}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_literature.py
from viva_human_atlas.literature import fetch_abstract, get_literature_text

_EFETCH = """<?xml version="1.0"?><PubmedArticleSet><PubmedArticle><MedlineCitation>
<Article><Abstract><AbstractText>Beta-cell mass adapts to glucose.</AbstractText>
</Abstract></Article></MedlineCitation></PubmedArticle></PubmedArticleSet>"""

_EPMC_EMPTY = '<?xml version="1.0"?><responseWrapper><resultList></resultList></responseWrapper>'


class _Resp:
    def __init__(self, text): self.text = text
    def raise_for_status(self): pass


def test_fetch_abstract_parses_efetch():
    got = fetch_abstract("11073807", _get=lambda url, **k: _Resp(_EFETCH))
    assert got == "Beta-cell mass adapts to glucose."


def test_get_literature_text_abstract_only_when_no_oa():
    def _get(url, **k):
        return _Resp(_EFETCH if "efetch" in url else _EPMC_EMPTY)
    out = get_literature_text("11073807", _get=_get)
    assert out["abstract"].startswith("Beta-cell")
    assert out["fulltext"] is None
    assert out["has_fulltext"] is False
    assert out["text_source"] == "abstract"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=$PWD pytest tests/test_literature.py -q`
Expected: FAIL — module missing.

- [ ] **Step 3: Write minimal implementation**

```python
# viva_human_atlas/literature.py
"""Fetch a model's paper text: PubMed abstract (NCBI E-utilities) + Europe PMC
open-access full text. Disk-cached; injectable `_get` for offline tests."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Callable, Optional
from xml.etree import ElementTree as ET

import requests

_EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
_EPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest"
_TIMEOUT = 30


def _cached(cache_dir, key, produce):
    if not cache_dir:
        return produce()
    p = Path(cache_dir) / (hashlib.sha1(key.encode()).hexdigest() + ".txt")
    if p.exists():
        t = p.read_text(encoding="utf-8")
        return t or None
    val = produce()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(val or "", encoding="utf-8")
    return val


def fetch_abstract(pmid, *, _get: Optional[Callable] = None, cache_dir=None):
    if not pmid:
        return None
    get = _get or requests.get

    def produce():
        r = get(_EFETCH, params={"db": "pubmed", "id": str(pmid), "rettype": "abstract", "retmode": "xml"}, timeout=_TIMEOUT)
        r.raise_for_status()
        root = ET.fromstring(r.text)
        parts = [(e.text or "") for e in root.iter("AbstractText")]
        text = " ".join(p.strip() for p in parts if p).strip()
        return text or None

    return _cached(cache_dir, f"abstract:{pmid}", produce)


def fetch_oa_fulltext(pmid, *, _get: Optional[Callable] = None, cache_dir=None):
    if not pmid:
        return None
    get = _get or requests.get

    def produce():
        s = get(f"{_EPMC}/search", params={"query": f"EXT_ID:{pmid} AND SRC:MED", "format": "json", "resultType": "core"}, timeout=_TIMEOUT)
        s.raise_for_status()
        if '"isOpenAccess":"Y"' not in s.text and '"inEPMC":"Y"' not in s.text:
            return None
        f = get(f"{_EPMC}/MED/{pmid}/fullTextXML", timeout=_TIMEOUT)
        if getattr(f, "status_code", 200) != 200:
            return None
        txt = re.sub(r"<[^>]+>", " ", f.text)
        txt = re.sub(r"\s+", " ", txt).strip()
        return txt or None

    return _cached(cache_dir, f"fulltext:{pmid}", produce)


def get_literature_text(pmid, doi=None, *, _get: Optional[Callable] = None, cache_dir=None) -> dict:
    abstract = fetch_abstract(pmid, _get=_get, cache_dir=cache_dir)
    fulltext = fetch_oa_fulltext(pmid, _get=_get, cache_dir=cache_dir) if abstract or pmid else None
    if fulltext:
        source = "abstract+fulltext"
    elif abstract:
        source = "abstract"
    else:
        source = "none"
    return {"abstract": abstract, "fulltext": fulltext, "text_source": source, "has_fulltext": bool(fulltext)}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=$PWD pytest tests/test_literature.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add viva_human_atlas/literature.py tests/test_literature.py
git commit -m "feat(literature): pubmed abstract + europe pmc OA full text, cached"
```

---

### Task 4: `llm_extract` — Claude structured extraction

**Files:**
- Create: `viva_human_atlas/llm_extract.py`
- Test: `tests/test_llm_extract.py`

**REQUIRED READ:** load the `claude-api` skill before writing this task — confirm the current `anthropic` SDK Messages + tool-use call shape and the Haiku model id.

**Interfaces:**
- Consumes: `anthropic` SDK (default client), an injectable `client` stub, a `cache_dir`.
- Produces:
  - `LITERATURE_TOOL` — a tool dict with `name="record_model_facts"` and an `input_schema` for the `literature` fields (organs, anatomical_structures, tissues, cell_types, ftus, disease, species, model_type, scale, key_process, candidate_uberon, candidate_cl, summary).
  - `extract(name, abstract, fulltext, *, model="claude-haiku-4-5-20251001", client=None, cache_dir=None) -> dict` — returns the tool input (the `literature` block); returns `{}` when there is no text.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_llm_extract.py
from viva_human_atlas import llm_extract


class _FakeClient:
    def __init__(self, payload): self._payload = payload; self.calls = 0
    class _Messages:
        pass
    @property
    def messages(self):
        outer = self
        class M:
            def create(self, **kwargs):
                outer.calls += 1
                class Block:  # a tool_use content block
                    type = "tool_use"; name = "record_model_facts"; input = outer._payload
                class Resp: content = [Block()]
                return Resp()
        return M()


def test_extract_returns_tool_input():
    client = _FakeClient({"organs": ["pancreas"], "disease": "type 2 diabetes", "summary": "x"})
    out = llm_extract.extract("Topp2000", "beta-cell mass...", None, client=client)
    assert out["organs"] == ["pancreas"]
    assert out["disease"] == "type 2 diabetes"


def test_extract_no_text_returns_empty_and_no_call():
    client = _FakeClient({})
    assert llm_extract.extract("x", None, None, client=client) == {}
    assert client.calls == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=$PWD pytest tests/test_llm_extract.py -q`
Expected: FAIL — module missing.

- [ ] **Step 3: Write minimal implementation**

```python
# viva_human_atlas/llm_extract.py
"""Claude structured extraction of HRA-relevant facts from a model's paper text.
Forced tool-use call -> a fixed `literature` schema; cached by (id-free) text hash."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Optional

_STR_LIST = {"type": "array", "items": {"type": "string"}}
LITERATURE_TOOL = {
    "name": "record_model_facts",
    "description": "Record HRA-relevant facts extracted from a systems-biology model's paper.",
    "input_schema": {
        "type": "object",
        "properties": {
            "organs": _STR_LIST, "anatomical_structures": _STR_LIST, "tissues": _STR_LIST,
            "cell_types": _STR_LIST, "ftus": _STR_LIST,
            "disease": {"type": "string"}, "species": {"type": "string"},
            "model_type": {"type": "string"}, "scale": {"type": "string"},
            "key_process": {"type": "string"}, "summary": {"type": "string"},
            "candidate_uberon": _STR_LIST, "candidate_cl": _STR_LIST,
        },
        "required": ["organs", "anatomical_structures", "cell_types", "summary"],
    },
}
_MAX_CHARS = 40000  # full-text truncation budget


def _cache_get(cache_dir, key):
    if not cache_dir:
        return None
    p = Path(cache_dir) / (key + ".json")
    return json.loads(p.read_text()) if p.exists() else None


def _cache_put(cache_dir, key, value):
    if cache_dir:
        p = Path(cache_dir) / (key + ".json")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(value))


def extract(name, abstract, fulltext, *, model="claude-haiku-4-5-20251001", client=None, cache_dir=None) -> dict:
    text = "\n\n".join(t for t in (abstract, fulltext) if t)[:_MAX_CHARS]
    if not text:
        return {}
    key = hashlib.sha256((model + "|" + (name or "") + "|" + text).encode()).hexdigest()
    cached = _cache_get(cache_dir, key)
    if cached is not None:
        return cached
    if client is None:
        import anthropic
        client = anthropic.Anthropic()
    prompt = (
        f"Model: {name}\n\nPaper text:\n{text}\n\n"
        "Extract the HRA-relevant facts using the record_model_facts tool. "
        "Only include organs/anatomical structures/cell types actually studied by the model. "
        "For candidate_uberon/candidate_cl, give CURIEs only when confident; else leave empty."
    )
    resp = client.messages.create(
        model=model, max_tokens=1024,
        tools=[LITERATURE_TOOL], tool_choice={"type": "tool", "name": "record_model_facts"},
        messages=[{"role": "user", "content": prompt}],
    )
    result = {}
    for block in resp.content:
        if getattr(block, "type", None) == "tool_use":
            result = dict(block.input)
            break
    _cache_put(cache_dir, key, result)
    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=$PWD pytest tests/test_llm_extract.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add viva_human_atlas/llm_extract.py tests/test_llm_extract.py
git commit -m "feat(llm): claude structured extraction of paper facts (forced tool schema)"
```

---

### Task 5: Orchestrator — assemble per-model entry, JSON DB, CLI

**Files:**
- Create: `scripts/build_biomodel_hra_map.py`
- Test: `tests/test_build_biomodel_hra_map.py`

**Interfaces:**
- Consumes: Tasks 1–4 (`sbml_identifiers.extract_identifiers`, `hra_mapping.map_to_hra`, `literature.get_literature_text`, `llm_extract.extract`), `biomodel_do.build_organ_index`, `annotation_match.fetch_sbml`, `biomodels` client, `biomodels_search.fetch_all_biomodel_ids`.
- Produces:
  - `build_entry(biomodel_id, organ_index, *, cache_dir=None, no_llm=False, llm_model=..., _sbml=None, _meta=None, _lit=None, _llm=None) -> dict` — one per-model object (all injectable seams default to the real fetchers).
  - `upsert_db(db, entry) -> None`; `write_db(db, path) -> None` (atomic); `load_db(path) -> dict`.
  - `main(argv=None) -> int`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_build_biomodel_hra_map.py
import json, importlib.util, pathlib
spec = importlib.util.spec_from_file_location(
    "bhm", pathlib.Path("scripts/build_biomodel_hra_map.py"))
bhm = importlib.util.module_from_spec(spec); spec.loader.exec_module(bhm)

ORGAN_INDEX = {"pancreas": {"uberon": "UBERON:0001264", "asset_urls": []}}


def test_build_entry_shape():
    entry = bhm.build_entry(
        "BIOMD0000000341", ORGAN_INDEX, no_llm=True,
        _sbml=lambda i: "<sbml/>",
        _ids=lambda s: {"chebi": ["CHEBI:17234"], "uniprot": [], "kegg": [], "go": [],
                        "cl": [], "uberon": ["UBERON:0001264"], "fma": [], "bto": [], "n_species": 1},
        _meta=lambda i: {"name": "Topp2000", "pmid": "11073807", "doi": "10.1006/x", "journal": "JTB", "year": 2000, "title": "T"},
        _lit=lambda pmid, doi, **k: {"abstract": None, "fulltext": None, "text_source": "none", "has_fulltext": False},
    )
    assert entry["identifier"] == "https://identifiers.org/biomodels.db:BIOMD0000000341"
    assert entry["repository"] == "biomodels"
    assert entry["paper_doi"] == "10.1006/x"
    assert {"label": "pancreas", "uberon": "UBERON:0001264"} in entry["organs"]
    assert entry["molecular_ids"]["chebi"] == ["CHEBI:17234"]
    assert entry["ontology_ids"]["uberon"] == ["UBERON:0001264"]
    assert "literature" not in entry  # no_llm
    assert entry["provenance"]["pmid"] == "11073807"


def test_db_upsert_and_atomic_write(tmp_path):
    db = {}
    bhm.upsert_db(db, {"identifier": "x", "biomodel_id": "BIOMD1"})
    path = tmp_path / "db.json"
    bhm.write_db(db, str(path))
    loaded = bhm.load_db(str(path))
    assert "BIOMD1" in loaded
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=$PWD pytest tests/test_build_biomodel_hra_map.py -q`
Expected: FAIL — script/functions missing.

- [ ] **Step 3: Write minimal implementation**

```python
#!/usr/bin/env python
"""Build the BioModels -> HRA mapping JSON DB (keyed by model id).

Reusable, resumable: each per-model stage (SBML / metadata / HRA / literature /
LLM) is cached and error-isolated; the DB is upserted and atomically written.
See docs/superpowers/specs/2026-08-04-biomodel-hra-map-design.md.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from viva_human_atlas.sbml_identifiers import extract_identifiers
from viva_human_atlas.hra_mapping import map_to_hra
from viva_human_atlas.literature import get_literature_text
from viva_human_atlas import llm_extract
from viva_human_atlas.biomodel_do import build_organ_index
from viva_human_atlas.annotation_match import fetch_sbml

_IRI = "https://identifiers.org/biomodels.db:{}"


def _default_meta(biomodel_id: str) -> dict:
    import biomodels
    m = biomodels.get_metadata(biomodel_id) or {}
    pub = (m.get("publication") or {})
    return {"name": m.get("name") or biomodel_id, "pmid": pub.get("pmid") or pub.get("id"),
            "doi": pub.get("doi"), "journal": pub.get("journal"), "year": pub.get("year"),
            "title": pub.get("title")}


def build_entry(biomodel_id, organ_index, *, cache_dir=None, no_llm=False,
                llm_model="claude-haiku-4-5-20251001",
                _sbml=fetch_sbml, _ids=extract_identifiers, _meta=_default_meta,
                _lit=get_literature_text, _llm=None) -> dict:
    errors = []
    ids = {"chebi": [], "uniprot": [], "kegg": [], "go": [], "cl": [], "uberon": [], "fma": [], "bto": [], "n_species": 0}
    try:
        ids = _ids(_sbml(biomodel_id))
    except Exception as e:  # noqa: BLE001
        errors.append(f"sbml:{e}")
    try:
        meta = _meta(biomodel_id)
    except Exception as e:  # noqa: BLE001
        meta = {"name": biomodel_id}; errors.append(f"metadata:{e}")

    hra = map_to_hra(ids["uberon"], meta.get("name", ""), organ_index)
    # merge SBML-annotated CL directly into cell_types
    cl_seen = {c["cl"] for c in hra["cell_types"]}
    for cl in ids["cl"]:
        if cl not in cl_seen:
            hra["cell_types"].append({"label": None, "cl": cl})

    entry = {
        "identifier": _IRI.format(biomodel_id),
        "repository": "biomodels",
        "biomodel_id": biomodel_id,
        "name": meta.get("name"),
        "paper_doi": meta.get("doi"),
        "organs": hra["organs"],
        "functional_tissue_units": hra["functional_tissue_units"],
        "cell_types": hra["cell_types"],
        "molecular_ids": {k: ids[k] for k in ("chebi", "uniprot", "kegg", "go")},
        "ontology_ids": {k: ids[k] for k in ("cl", "uberon", "fma", "bto")},
        "provenance": {
            "pmid": meta.get("pmid"), "title": meta.get("title"),
            "journal": meta.get("journal"), "year": meta.get("year"),
            "n_species": ids["n_species"],
            "uberon_organ_ids": hra["uberon_organ_ids"],
            "uberon_subregion_ids": hra["uberon_subregion_ids"],
            "text_source": "none", "has_fulltext": False, "errors": errors,
        },
    }

    if not no_llm:
        try:
            lit = _lit(meta.get("pmid"), meta.get("doi"), cache_dir=cache_dir)
            entry["provenance"]["text_source"] = lit["text_source"]
            entry["provenance"]["has_fulltext"] = lit["has_fulltext"]
            extractor = _llm or llm_extract.extract
            entry["literature"] = extractor(meta.get("name"), lit["abstract"], lit["fulltext"],
                                            model=llm_model, cache_dir=cache_dir)
        except Exception as e:  # noqa: BLE001
            errors.append(f"llm:{e}")
    return entry


def upsert_db(db: dict, entry: dict) -> None:
    db[entry["biomodel_id"]] = entry


def load_db(path: str) -> dict:
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def write_db(db: dict, path: str) -> None:
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(db, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build the BioModels -> HRA mapping JSON DB.")
    ap.add_argument("--out", default=str(REPO / "datasets" / "biomodel_hra_map.json"))
    ap.add_argument("--ids-file"); ap.add_argument("--query"); ap.add_argument("--limit", type=int)
    ap.add_argument("--cache-dir", default=str(REPO / ".cache" / "biomodel_hra_map"))
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--llm-model", default="claude-haiku-4-5-20251001")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)

    if a.ids_file:
        ids = [x.strip() for x in Path(a.ids_file).read_text().split() if x.strip()]
    elif a.query:
        from viva_human_atlas.biomodels_search import search_biomodels
        ids = search_biomodels(a.query, a.limit or 25)
    else:
        from viva_human_atlas.biomodels_search import fetch_all_biomodel_ids
        ids = fetch_all_biomodel_ids()
    if a.limit:
        ids = ids[: a.limit]

    db = load_db(a.out)
    organ_index = build_organ_index()
    Path(a.cache_dir).mkdir(parents=True, exist_ok=True)
    for i, bid in enumerate(ids, 1):
        if bid in db and not a.force:
            continue
        try:
            upsert_db(db, build_entry(bid, organ_index, cache_dir=a.cache_dir,
                                      no_llm=a.no_llm, llm_model=a.llm_model))
        except Exception as e:  # noqa: BLE001 — never abort the whole run
            print(f"  ERROR {bid}: {e}")
        if i % 10 == 0:
            write_db(db, a.out); print(f"  {i}/{len(ids)} (db={len(db)})")
    write_db(db, a.out)
    print(f"Wrote {a.out}: {len(db)} models")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=$PWD pytest tests/test_build_biomodel_hra_map.py -q`
Expected: PASS.

- [ ] **Step 5: Run the full offline suite (regression) + commit**

Run: `PYTHONPATH=$PWD pytest -m "not network" -q` → expect all green.

```bash
git add scripts/build_biomodel_hra_map.py tests/test_build_biomodel_hra_map.py
git commit -m "feat(script): assemble biomodel->HRA JSON DB (resume, atomic write, CLI)"
```

---

### Task 6: Subset validation (live, gated on go-ahead)

**Files:** none (a live run + inspection). Do NOT commit the output DB in this task.

- [ ] **Step 1:** Confirm `ANTHROPIC_API_KEY` is set (or plan `--no-llm` first).
- [ ] **Step 2:** Structural-only smoke (no API):
  `PYTHONUTF8=1 PYTHONPATH=$PWD .venv/bin/python scripts/build_biomodel_hra_map.py --query "glucose regulation" --limit 20 --no-llm --out /tmp/hra_map_smoke.json`
- [ ] **Step 3:** Inspect `/tmp/hra_map_smoke.json`: every entry has `identifier`, `repository`, `organs`, `functional_tissue_units` (with `uberon`), `cell_types`, `molecular_ids`, `ontology_ids`; `provenance.errors` are sane.
- [ ] **Step 4:** With go-ahead + API key, re-run the 20 WITHOUT `--no-llm`; confirm `literature` blocks populate and cache hits on a second run (no new API calls).
- [ ] **Step 5:** Report cost/latency for 20 → extrapolate to 1096; get explicit go-ahead before the full run.

---

## Self-Review

**Spec coverage:** identifier IRI ✓ (T5), repository ✓ (T5), paper_doi ✓ (T5), organs+uberon / FTUs+uberon / cell_types+cl ✓ (T2,T5), molecular_ids CHEBI/UniProt/KEGG/GO ✓ (T1,T5), SBML ontology CL/Uberon/FMA/BTO ✓ (T1,T5), literature incl. anatomical_structures ✓ (T4,T5), abstract+OA fulltext ✓ (T3), resume/atomic/cache/error-isolation ✓ (T5), CLI flags ✓ (T5), Physiome-ready `repository`+IRI ✓ (T5), subset-first rollout ✓ (T6).

**Placeholder scan:** none — every code step has runnable content.

**Type consistency:** `extract_identifiers` dict keys match across T1/T5; `map_to_hra` return keys (`organs/functional_tissue_units/cell_types/uberon_organ_ids/uberon_subregion_ids`) match T2 test and T5 consumer; `get_literature_text` keys (`abstract/fulltext/text_source/has_fulltext`) match T3/T5; `extract(...)` signature matches T4/T5; injectable seam names in T5 (`_sbml/_ids/_meta/_lit/_llm`) match the test.

**Note for implementer:** the `_default_meta` publication-field names (`pub["pmid"]/["doi"]/["journal"]/["year"]/["title"]`) are the expected shape of `biomodels.get_metadata`; verify the real client's field names during Task 6 Step 2 and adjust `_default_meta` only (all tests inject `_meta`, so they're unaffected).

---

### Task 7: BioPAX identifiers — complementary Xref source (increment)

**Files:**
- Create: `viva_human_atlas/biopax_identifiers.py`
- Modify: `scripts/build_biomodel_hra_map.py` (add a BioPAX stage to `build_entry`; union into `molecular_ids`; add `reactome`; record `provenance.id_sources` + `provenance.taxonomy`)
- Test: `tests/test_biopax_identifiers.py`, extend `tests/test_build_biomodel_hra_map.py`

**Interfaces:**
- Produces:
  - `extract_biopax_identifiers(owl_text: str) -> {"chebi","uniprot","kegg","go","reactome","taxonomy"}` (each sorted+deduped list).
  - `fetch_biopax(biomodel_id, *, _get=None, cache_dir=None) -> str | None` (GET `.../model/download/{id}?filename={id}-biopax3.owl`, fall back to `-biopax2.owl`, atomic-cache).
- `build_entry` gains injectable seams `_biopax=fetch_biopax`, `_biopax_ids=extract_biopax_identifiers`.

**Global constraints (same as the rest of the plan):** injectable `_get`/seams; tests stub and never hit network; sorted+deduped; ontology CURIEs upper-case with colon; atomic cache writes; per-stage error isolation (a BioPAX failure records `biopax:{e}` in `provenance.errors`, never aborts).

- [ ] **Step 1: Write the failing test (`tests/test_biopax_identifiers.py`)**

```python
from viph := None  # placeholder to avoid import at collection if module missing
from viva_human_atlas.biopax_identifiers import extract_biopax_identifiers

_OWL = """<?xml version="1.0" encoding="UTF-8"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
 xmlns:bp="http://www.biopax.org/release/biopax-level3.owl#">
 <bp:UnificationXref rdf:about="a">
  <bp:id>C00013</bp:id><bp:db>KEGG Compound</bp:db></bp:UnificationXref>
 <bp:UnificationXref rdf:about="b">
  <bp:id>CHEBI:89363</bp:id><bp:db>ChEBI</bp:db></bp:UnificationXref>
 <bp:UnificationXref rdf:about="c">
  <bp:id>GO:0005783</bp:id><bp:db>Gene Ontology</bp:db></bp:UnificationXref>
 <bp:UnificationXref rdf:about="d">
  <bp:id>P01308</bp:id><bp:db>UniProt</bp:db></bp:UnificationXref>
 <bp:UnificationXref rdf:about="e">
  <bp:id>R-HSA-70171</bp:id><bp:db>Reactome</bp:db></bp:UnificationXref>
 <bp:UnificationXref rdf:about="f">
  <bp:id>9606</bp:id><bp:db>Taxonomy</bp:db></bp:UnificationXref>
 <bp:PublicationXref rdf:about="g">
  <bp:id>26935066</bp:id><bp:db>PubMed</bp:db></bp:PublicationXref>
</rdf:RDF>"""


def test_extract_biopax_identifiers_by_db():
    out = extract_biopax_identifiers(_OWL)
    assert out["kegg"] == ["C00013"]
    assert out["chebi"] == ["CHEBI:89363"]
    assert out["go"] == ["GO:0005783"]
    assert out["uniprot"] == ["P01308"]
    assert out["reactome"] == ["R-HSA-70171"]
    assert out["taxonomy"] == ["NCBITaxon:9606"]  # normalized to a CURIE


def test_extract_biopax_ignores_publication_and_bad_xml():
    out = extract_biopax_identifiers(_OWL)
    assert "26935066" not in out["chebi"] + out["kegg"]  # PublicationXref skipped
    assert extract_biopax_identifiers("not xml")["chebi"] == []
```
(Delete the `from viph := None` placeholder line — it is only there so you remember the module must exist; write the real import.)

- [ ] **Step 2: Run test to verify it fails** — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `viva_human_atlas/biopax_identifiers.py`**

```python
"""Extract cross-reference identifiers from a BioModel's auto-generated BioPAX
Level-3 OWL/RDF — a clean complementary source to the SBML MIRIAM annotations.
BioPAX Xrefs carry <bp:db>/<bp:id> pairs with human-readable db names; harvest
CHEBI/UniProt/KEGG/GO/Reactome ids + organism NCBI Taxon, via stdlib
ElementTree (no rdflib/pybiopax dependency)."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Callable, Optional
from xml.etree import ElementTree as ET

import requests

_BP = "{http://www.biopax.org/release/biopax-level3.owl#}"
_DOWNLOAD = "https://www.ebi.ac.uk/biomodels/model/download/{}"
_TIMEOUT = 60

# db-name substring (lowercased) -> output collection key.
_DB_MAP = (
    ("chebi", "chebi"), ("uniprot", "uniprot"), ("kegg", "kegg"),
    ("gene ontology", "go"), ("reactome", "reactome"), ("taxonomy", "taxonomy"),
)
_KEYS = ["chebi", "uniprot", "kegg", "go", "reactome", "taxonomy"]


def _normalize(collection: str, ident: str) -> str:
    ident = (ident or "").strip()
    if collection == "chebi" and not ident.upper().startswith("CHEBI:"):
        ident = "CHEBI:" + ident.split(":")[-1]
    elif collection == "go" and not ident.upper().startswith("GO:"):
        ident = "GO:" + ident.split(":")[-1]
    elif collection == "taxonomy" and not ident.upper().startswith("NCBITAXON:"):
        ident = "NCBITaxon:" + ident.split(":")[-1]
    return ident


def extract_biopax_identifiers(owl_text: str) -> dict:
    buckets = {k: set() for k in _KEYS}
    try:
        root = ET.fromstring(owl_text)
    except ET.ParseError:
        return {k: [] for k in _KEYS}
    for el in root.iter():
        if el.tag.split("}")[-1] not in ("UnificationXref", "RelationshipXref"):
            continue
        db = (el.findtext(_BP + "db") or "").lower()
        ident = el.findtext(_BP + "id")
        if not ident:
            continue
        for needle, key in _DB_MAP:
            if needle in db:
                buckets[key].add(_normalize(key, ident))
                break
    return {k: sorted(v) for k, v in buckets.items()}


def fetch_biopax(biomodel_id: str, *, _get: Optional[Callable] = None, cache_dir=None) -> Optional[str]:
    get = _get or requests.get

    def produce():
        for fn in (f"{biomodel_id}-biopax3.owl", f"{biomodel_id}-biopax2.owl"):
            r = get(_DOWNLOAD.format(biomodel_id), params={"filename": fn}, timeout=_TIMEOUT)
            if getattr(r, "status_code", 200) == 200 and (r.text or "").strip():
                return r.text
        return None

    if not cache_dir:
        return produce()
    p = Path(cache_dir) / (hashlib.sha1(f"biopax:{biomodel_id}".encode()).hexdigest() + ".owl")
    if p.exists():
        return p.read_text(encoding="utf-8") or None
    val = produce()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(val or "", encoding="utf-8")
    os.replace(tmp, p)
    return val
```

- [ ] **Step 4: Run test to verify it passes.**

- [ ] **Step 5: Wire into `build_entry`** (`scripts/build_biomodel_hra_map.py`)

Add imports: `from viva_human_atlas.biopax_identifiers import extract_biopax_identifiers, fetch_biopax`.
Add seams to `build_entry(...)`: `_biopax=fetch_biopax, _biopax_ids=extract_biopax_identifiers`.
After the SBML/ids stage, add an error-isolated BioPAX stage and change the molecular-id assembly to union SBML+BioPAX with source provenance:

```python
    biopax = {"chebi": [], "uniprot": [], "kegg": [], "go": [], "reactome": [], "taxonomy": []}
    try:
        owl = _biopax(biomodel_id, cache_dir=cache_dir)
        if owl:
            biopax = _biopax_ids(owl)
    except Exception as e:  # noqa: BLE001
        errors.append(f"biopax:{e}")

    # union SBML + BioPAX per molecular collection, tracking each source
    molecular, id_sources = {}, {}
    for k in ("chebi", "uniprot", "kegg", "go"):
        s, b = set(ids[k]), set(biopax[k])
        molecular[k] = sorted(s | b)
        id_sources[k] = {"sbml": len(s), "biopax": len(b), "biopax_only": sorted(b - s)}
    molecular["reactome"] = sorted(biopax["reactome"])
    id_sources["reactome"] = {"sbml": 0, "biopax": len(biopax["reactome"]),
                              "biopax_only": sorted(biopax["reactome"])}
```

Then set `entry["molecular_ids"] = molecular` (replacing the old `{k: ids[k] for k in (...)}`), and in `provenance` add `"id_sources": id_sources` and `"taxonomy": biopax["taxonomy"]`. Leave `ontology_ids` (cl/uberon/fma/bto) as the SBML set.

- [ ] **Step 6: Extend `tests/test_build_biomodel_hra_map.py`** — a `build_entry` test injecting `_biopax`/`_biopax_ids` stubs that assert: BioPAX kegg/chebi union with SBML into `molecular_ids`; `reactome` populated; `provenance.id_sources["kegg"]["biopax_only"]` lists the BioPAX-only id; `provenance.taxonomy` set; and a `_biopax` that raises records `biopax:` in `provenance.errors` without aborting.

- [ ] **Step 7:** Run the full offline suite `-m "not network"`; commit `feat(biopax): union BioPAX Xref ids (chebi/uniprot/kegg/go/reactome/taxonomy) with source provenance`.
