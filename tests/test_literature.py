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
