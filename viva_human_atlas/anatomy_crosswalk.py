"""Crosswalk a model's parsed ontology ids/terms to ADDITIONAL Uberon/CL
terms, beyond what SBML/BioPAX directly annotate.

Two sources, each loaded once at import time (module-level cache), resolved
relative to `datasets/` at the repo root:

- BTO -> Uberon: `datasets/bto_uberon_crosswalk.json`, a curated
  `{"BTO:xxxx": "UBERON:yyyy"}` map (see `bto_crosswalk.py`, which builds it).
- MeSH -> Uberon/CL: `datasets/mesh-uberon-cl-human-mapping.sssom.csv`, an
  SSSOM mapping keyed by MeSH *label* (not id) -- BioModels' SBML/BioPAX
  essentially never carry MeSH ids, but PubMed assigns MeSH headings per
  paper (see `literature.fetch_pubmed_mesh`), and the SSSOM CSV's MeSH
  M-concept ids don't line up with PubMed's D-descriptor ids, so the join
  key that survives both sources is the human-readable label.
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

_DATASETS = Path(__file__).resolve().parents[1] / "datasets"
_BTO_UBERON_PATH = _DATASETS / "bto_uberon_crosswalk.json"
_MESH_LABEL_CSV_PATH = _DATASETS / "mesh-uberon-cl-human-mapping.sssom.csv"

_OBJECT_ID_RE = re.compile(r"/(UBERON|CL)_(\d+)$")


def _normalize_bto(s: str) -> str:
    return re.sub(r"[^0-9A-Za-z]", "", s or "").upper()


def norm_label(s: str) -> str:
    """Lowercase, alphanumeric-only normalization for MeSH label matching."""
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def load_bto_uberon(path=None) -> dict:
    """`{BTO curie: uberon curie}`, or `{}` if the file is missing."""
    p = Path(path) if path else _BTO_UBERON_PATH
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def load_mesh_label_crosswalk(path=None) -> dict:
    """`{norm(subject_label): {"uberon": [...], "cl": [...]}}` built from the
    SSSOM CSV, or `{}` if the file is missing. `object_id` is a
    `.../obo/UBERON_0002107` or `.../obo/CL_0000182` style URI, rebuilt into
    a `UBERON:0002107` / `CL:0000182` CURIE."""
    p = Path(path) if path else _MESH_LABEL_CSV_PATH
    if not p.exists():
        return {}
    out: dict = {}
    with p.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            label = row.get("subject_label")
            object_id = row.get("object_id") or ""
            m = _OBJECT_ID_RE.search(object_id)
            if not label or not m:
                continue
            onto, num = m.groups()
            key = norm_label(label)
            entry = out.setdefault(key, {"uberon": [], "cl": []})
            entry[onto.lower()].append(f"{onto}:{num}")
    return out


# Loaded once; injectable via the `bto_map`/`mesh_label_map` params below.
_BTO_MAP = load_bto_uberon()
_MESH_LABEL_MAP = load_mesh_label_crosswalk()


def crosswalk_anatomy(ontology_ids: dict, *, bto_map=None, mesh_map=None) -> dict:
    """Derive additional Uberon (and, historically, CL) terms from a model's
    BTO ids via the curated BTO->Uberon crosswalk.

    `ontology_ids["bto"]` entries are matched against `bto_map` both by exact
    CURIE and by a normalized form (strip non-alphanumerics + uppercase), so
    `BTO:0000759` and `bto0000759` compare equal regardless of which side is
    which. `bto_map` defaults to the module-level `load_bto_uberon()` result.

    Returns `{"uberon": [...], "cl": [...]}`, sorted + deduped. (`cl` is
    currently always empty here -- MeSH-derived CL comes from
    `crosswalk_mesh_labels` instead.)
    """
    bto_map = _BTO_MAP if bto_map is None else bto_map
    norm_index = {_normalize_bto(k): v for k, v in bto_map.items()}

    uberon = set()
    for bto_id in ontology_ids.get("bto", []) or []:
        hit = norm_index.get(_normalize_bto(bto_id))
        if hit:
            uberon.add(hit)
    return {"uberon": sorted(uberon), "cl": []}


def crosswalk_mesh_labels(mesh_terms, label_map=None) -> dict:
    """Derive Uberon/CL terms from a list of MeSH terms (as returned by
    `literature.fetch_pubmed_mesh`: `[{"id": "D008099", "label": "Liver"}]`)
    via the label-keyed SSSOM crosswalk.

    `label_map` defaults to the module-level `load_mesh_label_crosswalk()`
    result. Returns `{"uberon": [...], "cl": [...]}`, sorted + deduped.
    """
    label_map = _MESH_LABEL_MAP if label_map is None else label_map
    uberon, cl = set(), set()
    for term in mesh_terms or []:
        hit = label_map.get(norm_label(term.get("label")))
        if hit:
            uberon.update(hit.get("uberon", []))
            cl.update(hit.get("cl", []))
    return {"uberon": sorted(uberon), "cl": sorted(cl)}
