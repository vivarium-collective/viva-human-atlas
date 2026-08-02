"""Transparent, committed BTO -> HRA-organ crosswalk.

BioModels annotate anatomy mostly via BRENDA-Tissue (BTO), not Uberon
(278/1096 corpus models carry BTO terms). `annotation_match.map_curie_to_organ`
resolves a BTO curie by looking it up in a `bto_crosswalk` dict expected to
map `BTO:xxxx -> "<organ's uberon-or-fma CURIE>"`, then recursing into
`organ_index` to find the organ. This module builds that crosswalk from a
small curated `label -> organ base-name` table (`LABEL2ORGAN`) crossed with
the corpus catalog's `organ_index`, so only unambiguous BTO labels are
mapped — anything not in `LABEL2ORGAN` (e.g. "infected cell") is left out
rather than guessed at.
"""
from __future__ import annotations

import re

# Curated, hand-validated: lowercase BTO label -> HRA organ base-name (the
# organ_index slug with any `-(female|male|left|right)` suffix stripped).
# Deliberately conservative — omit anything ambiguous rather than guess.
LABEL2ORGAN = {
    "blood plasma": "blood", "blood": "blood", "erythrocyte": "blood",
    "red blood cell": "blood", "serum": "blood", "platelet": "blood", "blood serum": "blood",
    "liver": "liver", "hepatocyte": "liver",
    "intestine": "intestine", "gut": "intestine", "small intestine": "intestine",
    "large intestine": "intestine", "colon": "intestine", "mesenteric lymph node": "intestine",
    "pancreas": "pancreas", "pancreatic beta cell": "pancreas", "pancreatic islet": "pancreas",
    "pancreatic acinar cell": "pancreas", "pancreatic cancer cell": "pancreas",
    "islet of langerhans": "pancreas",
    "brain": "brain", "neuron": "brain", "astrocyte": "brain", "cerebral cortex": "brain",
    "hippocampus": "brain",
    "heart": "heart", "cardiac muscle": "heart", "cardiomyocyte": "heart",
    "cardiac myocyte": "heart", "myocardium": "heart",
    "kidney": "kidney", "nephron": "kidney", "renal tubule": "kidney",
    "skin": "skin", "keratinocyte": "skin", "epidermis": "skin",
    "lung": "lung", "respiratory smooth muscle": "lung", "alveolar macrophage": "lung",
    "lung parenchyma": "lung", "bronchus": "lung",
    "adipose tissue": "adipose", "adipocyte": "adipose",
    "white adipose tissue": "adipose", "brown adipose tissue": "adipose",
    "follicular fluid": "ovary", "oocyte": "ovary", "ovarian follicle": "ovary", "ovary": "ovary",
    "uterus": "uterus", "myometrium": "uterus", "endometrium": "uterus",
    "prostate": "prostate", "prostate gland": "prostate",
    "spleen": "spleen", "thymus": "thymus", "lymph node": "lymph-node",
    "urinary bladder": "urinary-bladder", "bladder": "urinary-bladder",
    "trachea": "trachea", "larynx": "larynx",
}

_SEX_SIDE_SUFFIX = re.compile(r"-(?:female|male|left|right)")


def organ_base_uberon(organ_index: dict) -> dict:
    """`{base_name: uberon}` plus `{slug: uberon}`, built by stripping any
    `-(female|male|left|right)` fragment from each `organ_index` slug (e.g.
    `"ovary-female-left"` -> base `"ovary"`). First slug encountered for a
    given base wins. Slugs whose entry has no `uberon` are skipped."""
    out: dict = {}
    for slug, entry in organ_index.items():
        uberon = entry.get("uberon")
        if not uberon:
            continue
        out.setdefault(slug, uberon)
        base = _SEX_SIDE_SUFFIX.sub("", slug)
        out.setdefault(base, uberon)
    return out


def build_bto_uberon_crosswalk(bto_terms: dict, organ_index: dict) -> dict:
    """`{BTO curie: uberon}` for every `bto_terms` entry whose (lowercased)
    label is in `LABEL2ORGAN` and whose organ base-name resolves to a
    `uberon` in `organ_index`. Unmapped/ambiguous labels are simply absent
    from the result."""
    base_uberon = organ_base_uberon(organ_index)
    crosswalk = {}
    for curie, info in bto_terms.items():
        label = (info.get("label") or "").strip().lower()
        organ = LABEL2ORGAN.get(label)
        if organ is None:
            continue
        uberon = base_uberon.get(organ)
        if uberon is None:
            continue
        crosswalk[curie] = uberon
    return crosswalk
