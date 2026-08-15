from viva_human_atlas.viz import organ_dashboard_html


def test_dashboard_renders_ran_and_failed():
    result = {"organ": "kidney",
        "models": [
            {"key": "B1", "name": "ran model", "simulator": "copasi", "status": "ran",
             "time": [0, 1, 2], "series": {"A": [1, 2, 3]}, "error": None},
            {"key": "P2", "name": "failed model", "simulator": "opencor", "status": "failed",
             "time": [], "series": {}, "error": "libOpenCOR could not load model"}],
        "summary": {"n_models": 2, "n_ran": 1, "n_failed": 1, "by_simulator": {"copasi": 1, "opencor": 1}}}
    html = organ_dashboard_html(result)
    assert "<html" in html.lower() and "plotly" in html.lower()
    assert "ran model" in html and "failed model" in html
    assert "libOpenCOR could not load model" in html      # failure reason shown
    assert "Plotly.newPlot" in html or "plotly-graph-div" in html  # a real plot embedded
