from viva_human_atlas.model_process import model_process


def test_physiome_uses_organ_placing_category():
    # co-filed cellular categories are ignored in favor of the organ-placing one
    e = {"repository": "physiome", "name": "Warren 2010",
         "categories": ["electrophysiology", "calcium_dynamics", "signal_transduction"]}
    assert model_process(e) == "Electrophysiology"
    assert model_process({"repository": "physiome", "categories": ["ion_transport"]}) == "Ion transport"
    assert model_process({"repository": "physiome", "categories": ["metabolism"]}) == "Metabolism"


def test_physiome_reads_categories_from_provenance_too():
    e = {"repository": "physiome", "provenance": {"categories": ["neurobiology"]}}
    assert model_process(e) == "Neural"


def test_biomodels_falls_back_to_name_keyword():
    assert model_process({"repository": "biomodels", "name": "Schoeberl2002 - EGF MAPK"}) == "Signaling"
    assert model_process({"repository": "biomodels", "name": "Cardiac action potential"}) == "Electrophysiology"
    assert model_process({"repository": "physionet", "name": "12-lead ECG viewer"}) == "Electrophysiology"


def test_unmatched_is_other():
    assert model_process({"repository": "biomodels", "name": "An abstract oscillator"}) == "Other"
    assert model_process({"repository": "physiome", "categories": ["cell_cycle"]}) == "Cell cycle"
