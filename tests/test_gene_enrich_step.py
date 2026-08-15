from viva_human_atlas.core import build_core
from viva_human_atlas.enrich import GeneEnrichStep

def test_gene_enrich_step_offline_counts_committed_db():
    # process_bigraph.Step requires a `core` (raises "must provide a core"
    # otherwise) -- same pattern as every other Step test in this repo
    # (e.g. tests/test_model_harvest_step.py, tests/test_biomodel_hra_step.py).
    step = GeneEnrichStep({"db_path": "datasets/model_hra_map.json",
                           "asctb_path": "datasets/asctb_tables.json",
                           "live": False}, core=build_core())
    out = step.update({})
    assert out["db_path"] == "datasets/model_hra_map.json"     # passthrough
    assert out["n_models_enriched"] > 0                         # committed DB is enriched
    assert "summary" in out

def test_gene_enrich_step_registered_in_modules():
    # `core.access(...)` is for the *type* registry (bigraph_schema.core.Core.access):
    # for an unregistered string key it falls through to visit_expression() and just
    # returns the string back, so it returns non-None even for a bogus/unregistered
    # name -- it never consults core.link_registry and can't prove a Step is
    # registered. build_core() registers Steps via core.register_link(dotted, cls),
    # which writes into core.link_registry (a plain dict) -- check that directly.
    core = build_core()
    assert core.link_registry.get("viva_human_atlas.enrich.GeneEnrichStep") is GeneEnrichStep
