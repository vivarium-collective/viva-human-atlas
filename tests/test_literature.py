import time

from viva_human_atlas import literature
from viva_human_atlas.literature import fetch_abstract, get_literature_text

_EFETCH = """<?xml version="1.0"?><PubmedArticleSet><PubmedArticle><MedlineCitation>
<Article><Abstract><AbstractText>Beta-cell mass adapts to glucose.</AbstractText>
</Abstract></Article></MedlineCitation></PubmedArticle></PubmedArticleSet>"""

_EPMC_EMPTY = '<?xml version="1.0"?><responseWrapper><resultList></resultList></responseWrapper>'


class _Resp:
    def __init__(self, text): self.text = text
    def raise_for_status(self): pass


def test_fetch_abstract_parses_efetch():
    got = fetch_abstract("11073807", _get=lambda url, **k: _Resp(_EFETCH))
    assert got == "Beta-cell mass adapts to glucose."


def test_get_literature_text_abstract_only_when_no_oa():
    def _get(url, **k):
        return _Resp(_EFETCH if "efetch" in url else _EPMC_EMPTY)
    out = get_literature_text("11073807", _get=_get)
    assert out["abstract"].startswith("Beta-cell")
    assert out["fulltext"] is None
    assert out["has_fulltext"] is False
    assert out["text_source"] == "abstract"


def test_injected_get_does_not_add_politeness_params_or_sleep(monkeypatch):
    # Tests must not slow down and must not mutate params when `_get` is injected.
    def fail_if_called():
        raise AssertionError("_polite_pause should not be called on the injected-_get path")
    monkeypatch.setattr(literature, "_polite_pause", fail_if_called)

    seen_params = {}

    def _get(url, **k):
        seen_params[url] = k.get("params")
        return _Resp(_EFETCH)

    fetch_abstract("11073807", _get=_get)
    assert "tool" not in (seen_params[literature._EFETCH] or {})
    assert "email" not in (seen_params[literature._EFETCH] or {})


def test_real_path_adds_politeness_params_and_pauses(monkeypatch):
    calls = []
    monkeypatch.setattr(literature, "_polite_pause", lambda: calls.append("pause"))

    seen = {}

    class _FakeRequests:
        @staticmethod
        def get(url, **k):
            seen["params"] = k.get("params")
            return _Resp(_EFETCH)

    monkeypatch.setattr(literature, "requests", _FakeRequests)
    fetch_abstract("11073807")  # no _get -> real path
    assert seen["params"]["tool"] == "viva-human-atlas"
    assert seen["params"]["email"] == "agmon.eran@gmail.com"
    assert calls == ["pause"]
