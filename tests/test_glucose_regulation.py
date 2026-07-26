import viva_human_atlas.composites.glucose_regulation as gr


def test_build_glucose_regulation_delegates_to_compare(monkeypatch):
    monkeypatch.setattr(gr, "search_biomodels",
                        lambda q, n, **k: ["BIOMD0000000372", "BIOMD0000000340"])
    captured = {}
    def fake_build(ids, simulators=None):
        captured["ids"] = ids
        captured["simulators"] = simulators
        return {"state": {"marker": True}, "run_steps_on_init": True}
    monkeypatch.setattr(gr, "build_compare_document", fake_build)

    doc = gr.build_glucose_regulation(
        query="glucose regulation", max_results=2, simulators="copasi,tellurium")

    assert doc["state"]["marker"] is True
    assert captured["ids"] == ["BIOMD0000000372", "BIOMD0000000340"]
    assert captured["simulators"] == "copasi,tellurium"


def test_generator_is_discovered():
    try:
        from viva_superpowers.composite_generator import discover_generators
    except ModuleNotFoundError:
        from pbg_superpowers.composite_generator import discover_generators
    import viva_human_atlas  # noqa: F401  (fires decorators)
    # discover_generators() returns dict[spec_id, GeneratorEntry]; the
    # installed viva_superpowers API keys by id, not by name (verified
    # against pbg-superpowers' own test_composite_generator.py usage).
    names = {g.name for g in discover_generators().values()}
    assert "glucose-regulation" in names
