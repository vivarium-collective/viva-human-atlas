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
    # Linear / Log / Normalized view toggle present on the plot.
    assert "Linear" in html_out and "Log" in html_out and "Normalized" in html_out


def test_dashboard_drops_constant_series():
    # A ran model whose only series is dead-constant → no plot, a steady-state note.
    result = {"organ": "kidney",
        "models": [{"key": "C1", "name": "flat model", "simulator": "opencor", "status": "ran",
                    "time": [0, 1, 2], "series": {"k/const": [4500.0, 4500.0, 4500.0]}, "error": None}],
        "summary": {"n_models": 1, "n_ran": 1, "n_failed": 0, "by_simulator": {"opencor": 1}}}
    html_out = organ_dashboard_html(result)
    assert "steady state" in html_out.lower()          # constant series dropped, honest note
    assert "Plotly.newPlot" not in html_out            # no plot for an all-constant model


def test_dashboard_varying_series_survive_next_to_constant():
    # A model with one varying + one constant series plots (the varying one), with the toggle.
    result = {"organ": "kidney",
        "models": [{"key": "M1", "name": "mixed", "simulator": "opencor", "status": "ran",
                    "time": [0, 1, 2],
                    "series": {"V": [-0.15, 1.0, 1.85], "k/const": [4500.0, 4500.0, 4500.0]},
                    "error": None}],
        "summary": {"n_models": 1, "n_ran": 1, "n_failed": 0, "by_simulator": {"opencor": 1}}}
    html_out = organ_dashboard_html(result)
    assert "plotly-graph-div" in html_out or "Plotly.newPlot" in html_out
    assert "Normalized" in html_out
