import json
import scripts.harvest_models as cli  # scripts/__init__.py may be needed; add if missing


def test_cli_runs_selected_source(tmp_path, monkeypatch):
    calls = {}
    def fake_harvest(sources, *, out, query, limit, no_llm, force, rebuild=False, progress=None):
        calls.update(sources=sources, out=out, no_llm=no_llm, limit=limit, rebuild=rebuild)
        json.loads  # noop
        return {"per_source": {"physionet": {"new": 0}}, "total": 0}
    monkeypatch.setattr(cli, "harvest", fake_harvest)
    rc = cli.main(["--source", "physionet", "--no-llm", "--limit", "5", "--out", str(tmp_path/"db.json")])
    assert rc == 0
    assert calls["sources"] == ["physionet"]
    assert calls["no_llm"] is True and calls["limit"] == 5
