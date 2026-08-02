"""Steps over the committed annotation-based organ-matching catalog
(Task 4, `datasets/biomodel_annotation_catalog.json`) — the recall-oriented
complement to `coverage.py`'s name-synonym matching.

`AnnotationMatchStep` summarizes the annotation catalog itself (how many
models/organs it reaches, and which biological qualifiers/ontologies carry
the organ signal — mostly BTO, per `annotation_match.py`'s BRENDA Tissue
crosswalk). `RecallGainStep` runs `annotation_gain.compare_catalogs` against
the name-synonym catalog (`coverage.load_corpus_catalog`) to quantify how
much organ/model coverage annotation-matching adds over name-only matching.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict

from process_bigraph import Step

from viva_human_atlas.annotation_gain import compare_catalogs
from viva_human_atlas.coverage import load_corpus_catalog

_DEFAULT_ANNOTATION_CATALOG_PATH = "datasets/biomodel_annotation_catalog.json"
_DEFAULT_NAME_CATALOG_PATH = "datasets/biomodel_corpus_catalog.json"

_SAMPLE_PROVENANCE_N = 10


def load_annotation_envelope(path: str = _DEFAULT_ANNOTATION_CATALOG_PATH) -> dict:
    """Load the committed annotation-catalog envelope
    (`{n_ids, n_named, n_tagged, catalog}`) as-is (unlike
    `coverage.load_corpus_catalog`, which unwraps to just `catalog`) —
    `AnnotationMatchStep` needs the envelope's `n_ids`/`n_tagged` counts too."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def summarize_annotation_catalog(envelope: dict) -> Dict[str, Any]:
    """Build `annotation_summary` + `sample_provenance` from an annotation
    catalog envelope: qualifier/ontology counts scanned from every
    `biomodel_dos[].organs[].via` entry (the SBML MIRIAM CVTerm hit that
    produced each organ tag), plus the count of distinct organs reached."""
    catalog = envelope["catalog"]
    biomodel_dos = catalog["biomodel_dos"]

    organs: set[str] = set()
    qualifier_counts: Counter[str] = Counter()
    ontology_counts: Counter[str] = Counter()
    sample_provenance: list[dict] = []

    for do in biomodel_dos:
        do_organs = do.get("organs") or []
        if do_organs and len(sample_provenance) < _SAMPLE_PROVENANCE_N:
            sample_provenance.append(
                {
                    "biomodel_id": do.get("biomodel_id"),
                    "name": do.get("name"),
                    "organs": do_organs,
                }
            )
        for organ_hit in do_organs:
            organs.add(organ_hit["organ"])
            via = organ_hit.get("via") or {}
            qualifier = via.get("qualifier")
            if qualifier:
                qualifier_counts[qualifier] += 1
            curie = via.get("curie") or ""
            ontology = curie.split(":", 1)[0] if ":" in curie else curie
            if ontology:
                ontology_counts[ontology] += 1

    annotation_summary = {
        "n_ids": envelope.get("n_ids", len(biomodel_dos)),
        "n_tagged": envelope.get("n_tagged", sum(1 for do in biomodel_dos if do.get("organs"))),
        "n_organs": len(organs),
        "qualifier_counts": dict(qualifier_counts),
        "ontology_counts": dict(ontology_counts),
    }
    return {"annotation_summary": annotation_summary, "sample_provenance": sample_provenance}


class AnnotationMatchStep(Step):
    """Step: summarize the committed annotation-based organ-matching
    catalog — model/organ counts, plus the qualifier/ontology distribution
    behind each organ tag (which biological CVTerm qualifiers and which
    ontologies, e.g. BTO vs Uberon/FMA, carry the organ signal)."""

    description = (
        "Summarize the annotation-based (SBML MIRIAM + BTO crosswalk) "
        "organ-matching catalog: model/organ counts and the "
        "qualifier/ontology distribution behind each organ tag."
    )

    config_schema = {
        "catalog_path": "string",
    }

    def inputs(self):
        return {}

    def outputs(self):
        return {
            "annotation_summary": "tree",
            "sample_provenance": "list[tree]",
        }

    def update(self, inputs):
        catalog_path = self.config.get("catalog_path") or _DEFAULT_ANNOTATION_CATALOG_PATH
        envelope = load_annotation_envelope(catalog_path)
        return summarize_annotation_catalog(envelope)


AnnotationMatchStep.contract = {
    "summary": AnnotationMatchStep.description,
    "outputs": {
        "annotation_summary": (
            "`n_ids`/`n_tagged` (catalog envelope counts), `n_organs` "
            "(distinct organs reached), `qualifier_counts` (biological "
            "CVTerm qualifier -> hit count, e.g. BQB_OCCURS_IN), "
            "`ontology_counts` (ontology prefix -> hit count, e.g. BTO vs "
            "UBERON/FMA) -- both counted by scanning every "
            "`biomodel_dos[].organs[].via` entry."
        ),
        "sample_provenance": (
            "First N organ-tagged `biomodel_dos` entries "
            "(`biomodel_id`/`name`/`organs`), for spot-checking the "
            "annotation mechanism end to end."
        ),
    },
}


class RecallGainStep(Step):
    """Step: compare the annotation catalog against the name-synonym
    catalog (`annotation_gain.compare_catalogs`) to quantify how much
    organ/model coverage annotation-based matching adds over name-only
    matching."""

    description = (
        "Compare the annotation-based organ-matching catalog against the "
        "name-synonym catalog to quantify the recall gain (organs/models "
        "added) from parsing SBML MIRIAM/BTO annotations."
    )

    config_schema = {
        "name_catalog_path": "string",
        "annotation_catalog_path": "string",
    }

    def inputs(self):
        return {}

    def outputs(self):
        return {"gain": "tree"}

    def update(self, inputs):
        name_catalog_path = self.config.get("name_catalog_path") or _DEFAULT_NAME_CATALOG_PATH
        annotation_catalog_path = (
            self.config.get("annotation_catalog_path") or _DEFAULT_ANNOTATION_CATALOG_PATH
        )
        name_catalog = load_corpus_catalog(name_catalog_path)
        annotation_catalog = load_corpus_catalog(annotation_catalog_path)
        return {"gain": compare_catalogs(name_catalog, annotation_catalog)}


RecallGainStep.contract = {
    "summary": RecallGainStep.description,
    "outputs": {
        "gain": (
            "`annotation_gain.compare_catalogs` result: `name`/`annotation`/"
            "`union` stats (organs, n_models_total/tagged), `delta` "
            "(`organs_added`, `n_models_added`, `per_organ`), `summary` "
            "(pct of corpus tagged by each matcher)."
        ),
    },
}
