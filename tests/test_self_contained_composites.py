"""Self-containment regression: the previously "incomplete" composites now
produce their catalog / table data with an in-graph upstream Step (loading the
committed cache or building live) and hand it to the consumer through a shared
store — instead of the consumer reading a hidden file path from its `config`.

Two things are asserted per composite:
  1. STRUCTURAL — the composite document wires a producer Step whose output
     store is exactly the consumer Step's input store (so the data dependency
     is visible in the graph, not buried in a Step's config).
  2. FUNCTIONAL — running the composite (as a real multi-Step process-bigraph
     Composite, catalog served from the committed cache) reproduces the
     reference helper's output. These read only committed datasets — no network.

`corpus-coverage` / `model-coverage-3d` also fetch the live ASCT+B-3D crosswalk,
so their functional check is network-only and lives elsewhere; here they get the
structural check (which is offline).
"""
from __future__ import annotations

import pytest

from process_bigraph import Composite

from viva_human_atlas.core import build_core

from viva_human_atlas.composites.corpus_coverage_composite import (
    build_corpus_coverage_document,
)
from viva_human_atlas.composites.ftu_coverage_composite import (
    build_ftu_model_coverage_document,
)
from viva_human_atlas.composites.annotation_composite import (
    build_annotation_organ_matching_document,
    build_annotation_recall_gain_document,
)
from viva_human_atlas.composites.vasculature_network_composite import (
    build_vasculature_network_document,
)


@pytest.fixture(scope="module")
def core():
    return build_core()


def _run(core, doc):
    return Composite(doc, core=core).state


def _producer_feeds_consumer(doc, producer_key, consumer_key, store):
    """Assert `producer_key` writes `store` and `consumer_key` reads it."""
    state = doc["state"]
    assert producer_key in state, f"missing producer step {producer_key!r}"
    assert consumer_key in state, f"missing consumer step {consumer_key!r}"
    produced = [v[0] for v in state[producer_key]["outputs"].values()]
    consumed = [v[0] for v in state[consumer_key]["inputs"].values()]
    assert store in produced, f"{producer_key} does not output store {store!r}"
    assert store in consumed, f"{consumer_key} does not read store {store!r}"


# --------------------------------------------------------------------------
# STRUCTURAL: producer Step wired into consumer (self-containment)
# --------------------------------------------------------------------------

def test_corpus_coverage_wires_catalog_producer():
    _producer_feeds_consumer(
        build_corpus_coverage_document(),
        "corpus_catalog_step", "coverage_step", "corpus_catalog",
    )


def test_ftu_coverage_wires_catalog_producer():
    _producer_feeds_consumer(
        build_ftu_model_coverage_document(),
        "corpus_catalog_step", "ftu_coverage_step", "corpus_catalog",
    )


def test_annotation_matching_wires_catalog_producer():
    _producer_feeds_consumer(
        build_annotation_organ_matching_document(),
        "annotation_catalog_step", "annotation_match_step", "annotation_envelope_json",
    )


def test_recall_gain_wires_both_producers():
    doc = build_annotation_recall_gain_document()
    _producer_feeds_consumer(doc, "corpus_catalog_step", "recall_gain_step", "corpus_catalog")
    _producer_feeds_consumer(
        doc, "annotation_catalog_step", "recall_gain_step", "annotation_envelope_json"
    )


def test_vasculature_wires_table_loader():
    _producer_feeds_consumer(
        build_vasculature_network_document(),
        "ftu_path_table_step", "vasculature_network_step", "ftu_table_json",
    )


# --------------------------------------------------------------------------
# FUNCTIONAL: composite output equals the reference helper (offline)
# --------------------------------------------------------------------------

def test_ftu_coverage_composite_matches_reference(core):
    from viva_human_atlas.ftu_coverage import build_ftu_model_coverage

    s = _run(core, build_ftu_model_coverage_document())
    ref = build_ftu_model_coverage(catalog_path="datasets/biomodel_corpus_catalog.json")
    assert s["ftu_coverage_summary"] == ref["summary"]
    assert len(s["ftu_coverage"]) == len(ref["ftu_coverage"])


def test_annotation_matching_composite_matches_reference(core):
    from viva_human_atlas.annotation_coverage import (
        load_annotation_envelope,
        summarize_annotation_catalog,
    )

    s = _run(core, build_annotation_organ_matching_document())
    ref = summarize_annotation_catalog(
        load_annotation_envelope("datasets/biomodel_annotation_catalog.json")
    )
    assert s["annotation_summary"] == ref["annotation_summary"]
    assert len(s["sample_provenance"]) == len(ref["sample_provenance"])


def test_recall_gain_composite_matches_reference(core):
    from viva_human_atlas.coverage import load_corpus_catalog
    from viva_human_atlas.annotation_gain import compare_catalogs

    s = _run(core, build_annotation_recall_gain_document())
    ref = compare_catalogs(
        load_corpus_catalog("datasets/biomodel_corpus_catalog.json"),
        load_corpus_catalog("datasets/biomodel_annotation_catalog.json"),
    )
    assert s["gain"]["summary"] == ref["summary"]
    assert s["gain"]["union"] == ref["union"]


def test_vasculature_composite_matches_reference(core):
    from viva_human_atlas.vasculature import vascular_network_summary

    s = _run(core, build_vasculature_network_document())
    assert s["vascular_network_summary"] == vascular_network_summary()
    assert len(s["ftu_routes"]) == s["vascular_network_summary"]["n_ftus"]
