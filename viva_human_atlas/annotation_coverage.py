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
from typing import Any, Dict, Optional

from process_bigraph import Step

from viva_human_atlas.annotation_gain import compare_catalogs
from viva_human_atlas.annotation_match import build_annotation_catalog, fetch_sbml
from viva_human_atlas.coverage import load_corpus_catalog

_DEFAULT_BTO_CROSSWALK_PATH = "datasets/bto_uberon_crosswalk.json"

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


def _build_annotation_envelope_live(model_dos: list, organ_index: dict, bto: Optional[dict]) -> dict:
    """Build the annotation-catalog envelope live (fetches each model's SBML)
    — the in-Step equivalent of `scripts/build_annotation_catalog.py:main`."""
    catalog = build_annotation_catalog(
        model_dos, organ_index, fetch=fetch_sbml, bto_crosswalk=bto
    )
    return {
        "n_ids": len(model_dos),
        "n_named": sum(1 for d in model_dos if d.get("name")),
        "n_tagged": sum(1 for do in catalog["biomodel_dos"] if do.get("organs")),
        "catalog": catalog,
    }


class AnnotationCatalogStep(Step):
    """Step: produce the annotation (SBML MIRIAM -> Uberon) organ catalog
    IN-GRAPH.

    Self-contained source of the annotation-catalog envelope that
    `AnnotationMatchStep` / `RecallGainStep` consume, so the catalog is no
    longer a hidden `config` file read. When `annotation_catalog_path` names
    an existing committed catalog it is loaded (fast, offline — the file is an
    optional cache/override); otherwise it is built live from the corpus
    catalog + BTO crosswalk by fetching every model's SBML (the work
    `scripts/build_annotation_catalog.py` does, promoted to a Step). The
    corpus catalog comes from an upstream `CorpusCatalogStep` (the
    `corpus_catalog` input) when the live path is taken.
    """

    description = (
        "Produce the annotation (SBML MIRIAM + BTO crosswalk) organ catalog "
        "in-graph: load the committed catalog cache if present, else build it "
        "live by fetching each model's SBML."
    )

    config_schema = {
        "annotation_catalog_path": "string",
        "corpus_catalog_path": "string",
        "bto_crosswalk_path": "string",
    }

    def inputs(self):
        # Used only on the live-build path; empty on the (default) cache path.
        return {"corpus_catalog": "biomodel_catalog"}

    def outputs(self):
        # The annotation envelope's `catalog.biomodel_dos[].organs[]` carry a
        # loose `via` (SBML CVTerm) shape that doesn't fit a clean struct type,
        # so it's handed over as a JSON string — a verbatim, wiring-safe blob
        # the consumer Steps json.loads. (The corpus catalog, whose shape is
        # fixed, uses the typed `biomodel_catalog` store instead.)
        return {"annotation_envelope_json": "string"}

    def update(self, inputs):
        cache = self.config.get("annotation_catalog_path") or _DEFAULT_ANNOTATION_CATALOG_PATH
        if cache and Path(cache).exists():
            envelope = load_annotation_envelope(cache)
        else:
            # Live build (no cache): corpus from the upstream store, else disk.
            corpus = (inputs or {}).get("corpus_catalog") or None
            if not (corpus and corpus.get("biomodel_dos")):
                corpus = load_corpus_catalog(
                    self.config.get("corpus_catalog_path") or _DEFAULT_NAME_CATALOG_PATH
                )
            bto = None
            bto_path = self.config.get("bto_crosswalk_path") or _DEFAULT_BTO_CROSSWALK_PATH
            if Path(bto_path).exists():
                bto = json.loads(Path(bto_path).read_text(encoding="utf-8"))
            envelope = _build_annotation_envelope_live(
                corpus["biomodel_dos"], corpus["organ_index"], bto
            )
        return {"annotation_envelope_json": json.dumps(envelope)}


AnnotationCatalogStep.contract = {
    "summary": AnnotationCatalogStep.description,
    "outputs": {
        "annotation_envelope_json": (
            "The annotation-catalog envelope `{n_ids, n_named, n_tagged, "
            "catalog}` as a JSON string — loaded from the committed cache "
            "(`annotation_catalog_path`) or built live from the corpus catalog "
            "+ BTO crosswalk."
        ),
    },
    "assumptions": [
        "`annotation_catalog_path` is a cache/override, not a hard "
        "prerequisite: absent the file, the Step builds the catalog live "
        "(network — fetches each model's SBML), which is what makes the "
        "annotation composites self-contained.",
    ],
}


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
        # Wired to the upstream `AnnotationCatalogStep`'s
        # `annotation_envelope_json` store; falls back to the committed
        # `catalog_path` when standalone.
        return {"annotation_envelope_json": "string"}

    def outputs(self):
        return {
            "annotation_summary": "tree",
            "sample_provenance": "list[tree]",
        }

    def update(self, inputs):
        envelope_json = (inputs or {}).get("annotation_envelope_json") or ""
        if envelope_json:
            envelope = json.loads(envelope_json)
        else:
            envelope = load_annotation_envelope(
                self.config.get("catalog_path") or _DEFAULT_ANNOTATION_CATALOG_PATH
            )
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
        # `name_catalog` <- upstream CorpusCatalogStep (typed catalog);
        # `annotation_envelope_json` <- upstream AnnotationCatalogStep (JSON
        # blob). Both fall back to committed files when wired standalone.
        return {"name_catalog": "biomodel_catalog", "annotation_envelope_json": "string"}

    def outputs(self):
        return {"gain": "tree"}

    def update(self, inputs):
        inp = inputs or {}
        name_catalog = inp.get("name_catalog") or None
        if not (name_catalog and name_catalog.get("biomodel_dos")):
            name_catalog = load_corpus_catalog(
                self.config.get("name_catalog_path") or _DEFAULT_NAME_CATALOG_PATH
            )
        envelope_json = inp.get("annotation_envelope_json") or ""
        if envelope_json:
            annotation_catalog = json.loads(envelope_json)["catalog"]
        else:
            annotation_catalog = load_corpus_catalog(
                self.config.get("annotation_catalog_path") or _DEFAULT_ANNOTATION_CATALOG_PATH
            )
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
