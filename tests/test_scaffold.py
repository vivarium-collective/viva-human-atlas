def test_build_core_and_imports():
    import pbg_biomodels  # reused machinery must be importable
    import pbg_copasi, pbg_tellurium  # noqa: F401
    from viva_human_atlas.core import build_core
    core = build_core()
    assert core is not None
    # copasi + tellurium are known simulators in the reused registry
    from pbg_biomodels.simulators import resolve_simulators
    sims = resolve_simulators("copasi,tellurium")
    assert sims == ["copasi", "tellurium"]
