from viva_human_atlas.organ_simulation import normalize_result

def test_normalize_sbml():
    raw = {"time": [0.0, 1.0], "columns": ["A", "B"], "values": [[1.0, 2.0], [3.0, 4.0]]}
    n = normalize_result("copasi", raw)
    assert n["time"] == [0.0, 1.0]
    assert n["series"] == {"A": [1.0, 3.0], "B": [2.0, 4.0]}

def test_normalize_opencor():
    raw = {"time": [0.0, 1.0], "state": {"m/x": [1.0, 0.5]}, "variables": {}, "rates": {}, "constants": {}}
    n = normalize_result("opencor", raw)
    assert n["time"] == [0.0, 1.0]
    assert n["series"] == {"m/x": [1.0, 0.5]}
