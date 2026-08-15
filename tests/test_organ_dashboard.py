from viva_human_atlas.viz import organ_dashboard_html


def test_dashboard_renders_ran_and_failed():
    result = {"organ": "kidney",
        "models": [
            {"key": "B1", "name": "ran model", "simulator": "copasi", "status": "ran",
             "time": [0, 1, 2], "series": {"A": [1, 2, 3]}, "error": None},
            {"key": "P2", "name": "failed model", "simulator": "opencor", "status": "failed",
             "time": [], "series": {}, "error": "libOpenCOR could not load model"},
            {"key": "P3", "name": "xml error model", "simulator": "opencor", "status": "failed",
             "time": [], "series": {}, "error": "bad element <variable> in model"}],
        "summary": {"n_models": 3, "n_ran": 1, "n_failed": 2, "by_simulator": {"copasi": 1, "opencor": 2}}}
    html_out = organ_dashboard_html(result)
    assert "<html" in html_out.lower() and "plotly" in html_out.lower()
    assert "ran model" in html_out and "failed model" in html_out
    assert "libOpenCOR could not load model" in html_out      # failure reason shown
    assert "Plotly.newPlot" in html_out or "plotly-graph-div" in html_out  # a real plot embedded
    assert "&lt;variable&gt;" in html_out    # error text is HTML-escaped
    assert "<variable>" not in html_out      # no raw markup injection from error text
