from pathlib import Path
from viva_human_atlas.physiome import resolve_cellml_url


class _Resp:
    def __init__(self, text, url, status=200):
        self.text = text; self.url = url; self.status_code = status
    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"{self.status_code} error")


def test_resolve_cellml_url_from_fixture():
    html = Path("tests/fixtures/pmr_exposure_22e.html").read_text()
    url = resolve_cellml_url("https://models.physiomeproject.org/e/22e",
                             _get=lambda u, **k: _Resp(html, "https://models.physiomeproject.org/e/22e"))
    assert url == "https://models.physiomeproject.org/e/22e/Eskandari_et_al_2005.cellml"  # /view stripped


def test_resolve_cellml_url_no_link_returns_none():
    url = resolve_cellml_url("https://models.physiomeproject.org/e/zzz",
                             _get=lambda u, **k: _Resp("<html>no models here</html>", "x"))
    assert url is None
