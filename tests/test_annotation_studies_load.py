"""Demonstrate-loading tests for the annotation-organ-matching studies
(Task 5): `annotation-organ-matching` (mechanism/provenance: which
qualifiers/ontologies carry organ signal) and `annotation-recall-gain`
(the annotation-vs-name-only comparison).

Offline (mocked/committed-dataset only): each composite generator is built
via `build_core()`, run once, and the RAMEmitter snapshot is asserted
non-empty/shaped as expected. `discover_generators()` must surface both,
and each study's `baseline.composite` must resolve to a registered
generator id. Mirrors `tests/test_hra_3d_studies_load.py`.
"""
from __future__ import annotations

from pathlib import Path

import yaml
from process_bigraph import Composite, gather_emitter_results

import viva_human_atlas.composites.annotation_composite as annotation_composites
from viva_human_atlas.core import build_core

REPO_ROOT = Path(__file__).resolve().parents[1]

STUDY_SLUGS = ["annotation-organ-matching", "annotation-recall-gain"]


def _run(doc):
    core = build_core()
    composite = Composite(doc, core=core)
    composite.run(0.0)  # Steps run on init; this flushes the emitter.
    snap = (gather_emitter_results(composite).get(("emitter",)) or [{}])[-1]
    return snap


def test_annotation_organ_matching_composite_loads():
    doc = annotation_composites.build_annotation_organ_matching()
    snap = _run(doc)
    summary = snap.get("annotation_summary", {})
    assert summary.get("n_organs", 0) >= 1
    assert summary.get("qualifier_counts")
    assert summary.get("ontology_counts")
    assert snap.get("sample_provenance")


def test_annotation_recall_gain_composite_loads():
    doc = annotation_composites.build_annotation_recall_gain()
    snap = _run(doc)
    gain = snap.get("gain", {})
    assert gain.get("delta", {}).get("organs_added")
    assert gain.get("union", {}).get("n_models_total", 0) >= 1


def test_annotation_generators_discovered():
    try:
        from viva_superpowers.composite_generator import discover_generators
    except ModuleNotFoundError:
        from pbg_superpowers.composite_generator import discover_generators
    import viva_human_atlas  # noqa: F401  (fires decorators)

    ids = set(discover_generators().keys())
    assert any(i.endswith("annotation-organ-matching") for i in ids)
    assert any(i.endswith("annotation-recall-gain") for i in ids)


def test_annotation_study_baselines_resolve_to_registered_generators():
    try:
        from viva_superpowers.composite_generator import discover_generators
    except ModuleNotFoundError:
        from pbg_superpowers.composite_generator import discover_generators
    import viva_human_atlas  # noqa: F401  (fires decorators)

    generator_ids = set(discover_generators().keys())
    assert generator_ids, "discover_generators() returned nothing"

    for slug in STUDY_SLUGS:
        study_path = REPO_ROOT / "studies" / slug / "study.yaml"
        study = yaml.safe_load(study_path.read_text(encoding="utf-8"))
        assert study["investigation"] == "hra-integration"
        baseline = study.get("baseline") or []
        assert baseline, f"{slug}: baseline must be non-empty"
        composite_id = baseline[0]["composite"]
        assert composite_id in generator_ids, (
            f"{slug}: baseline.composite {composite_id!r} not in "
            f"discover_generators() keys"
        )
