"""Task B: corpus coverage — `build_coverage(catalog=...)` fast-path,
`load_corpus_catalog`, and `build_corpus_coverage`.

Offline (mocked/tmp file): no network calls. `build_coverage` with an
explicit `catalog=` must use it directly (skip the live BioModels
search/annotate entirely — `build_biomodel_do_catalog` must not be called),
while the existing live-query path (`catalog=None`) keeps working exactly as
before (mocked exactly like `tests/test_coverage.py`).
"""
from __future__ import annotations

import json

import viva_human_atlas.coverage as cov


def _boom(*a, **k):
    raise AssertionError("build_biomodel_do_catalog must not be called when catalog= is given")


class _FakeCrosswalkResp:
    """Minimal requests.Response stand-in for `hra_api.fetch_crosswalk`'s
    injectable `_get` — it wants a CSV-text response, not parsed rows."""

    def __init__(self, text: str):
        self.text = text

    def raise_for_status(self):
        pass


_CROSSWALK_CSV = (
    "ASCT+B 3D models crosswalk\n"
    "\n"
    "anatomical_structure_of,label,OntologyID,representation_of,node_type,"
    "glb file of single organs,node_name\n"
    ",liver,UBERON:0002107,,mesh,VH_F_Liver,VH_F_liver\n"
    ",kidney,UBERON:0002113,,mesh,VH_F_Kidney,VH_F_kidney\n"
)


def _fake_get_crosswalk(url, timeout=None):
    return _FakeCrosswalkResp(_CROSSWALK_CSV)


def test_build_coverage_with_catalog_skips_live_search(monkeypatch):
    monkeypatch.setattr(cov, "build_biomodel_do_catalog", _boom)

    catalog = {
        "biomodel_dos": [
            {
                "biomodel_id": "B1",
                "name": "hepatic glucose",
                "organs": [{"organ": "liver", "uberon": "UBERON:0002107"}],
            }
        ],
        "organ_to_models": {"UBERON:0002107": ["B1"]},
        "organ_index": {
            "liver": {"uberon": "UBERON:0002107", "asset_urls": ["x/VH_F_Liver.glb"]}
        },
    }

    out = cov.build_coverage(catalog=catalog, _get_xwalk=_fake_get_crosswalk)
    by = {r["uberon"]: r for r in out["coverage"]}

    assert by["UBERON:0002107"]["covered"] is True
    assert by["UBERON:0002107"]["n_models"] == 1
    assert by["UBERON:0002113"]["covered"] is False
    assert out["summary"]["n_as"] == 2
    assert out["summary"]["n_as_covered"] == 1


def test_build_coverage_live_path_still_works(monkeypatch):
    # Same fakes/shape as tests/test_coverage.py's organ-granularity test —
    # verifies catalog=None (the default) preserves the existing behavior.
    monkeypatch.setattr(
        cov,
        "build_biomodel_do_catalog",
        lambda q, n, **k: {
            "biomodel_dos": [
                {
                    "biomodel_id": "BIOMD1",
                    "name": "hepatic glucose",
                    "organs": [{"organ": "liver", "uberon": "UBERON:0002107"}],
                }
            ],
            "organ_index": {
                "liver": {"uberon": "UBERON:0002107", "asset_urls": ["x/3d-vh-f-liver.glb"]}
            },
            "organ_to_models": {"UBERON:0002107": ["BIOMD1"]},
        },
    )
    monkeypatch.setattr(
        cov,
        "fetch_crosswalk",
        lambda **k: [
            {
                "node_name": "VH_F_liver",
                "label": "liver",
                "uberon": "UBERON:0002107",
                "representation_of": "",
                "node_type": "mesh",
                "organ_glb": "VH_F_Liver",
                "parent": "",
            },
        ],
    )

    out = cov.build_coverage(max_results=1)
    by = {r["uberon"]: r for r in out["coverage"]}
    assert by["UBERON:0002107"]["covered"] is True
    assert by["UBERON:0002107"]["n_models"] == 1


def test_load_corpus_catalog_reads_inner_catalog(tmp_path):
    payload = {
        "n_ids": 2,
        "n_named": 2,
        "n_tagged": 1,
        "catalog": {
            "biomodel_dos": [{"biomodel_id": "B1", "name": "x", "organs": []}],
            "organ_to_models": {"UBERON:0002107": ["B1"]},
            "organ_index": {"liver": {"uberon": "UBERON:0002107", "asset_urls": []}},
        },
    }
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(payload))

    catalog = cov.load_corpus_catalog(path=str(path))

    assert catalog == payload["catalog"]
    assert "n_ids" not in catalog


def test_build_corpus_coverage_uses_catalog_and_injected_xwalk(tmp_path, monkeypatch):
    monkeypatch.setattr(cov, "build_biomodel_do_catalog", _boom)

    payload = {
        "n_ids": 1,
        "n_named": 1,
        "n_tagged": 1,
        "catalog": {
            "biomodel_dos": [
                {
                    "biomodel_id": "B1",
                    "name": "hepatic glucose",
                    "organs": [{"organ": "liver", "uberon": "UBERON:0002107"}],
                }
            ],
            "organ_to_models": {"UBERON:0002107": ["B1"]},
            "organ_index": {
                "liver": {"uberon": "UBERON:0002107", "asset_urls": ["x/VH_F_Liver.glb"]}
            },
        },
    }
    path = tmp_path / "corpus_catalog.json"
    path.write_text(json.dumps(payload))

    out = cov.build_corpus_coverage(catalog_path=str(path), _get_xwalk=_fake_get_crosswalk)

    assert out["summary"]["n_as"] == 2
    assert out["summary"]["n_as_covered"] == 1
    assert out["summary"]["query"] == "corpus (1096 curated)"
    assert out["summary"]["query"] != "glucose regulation"


def test_discover_generators_includes_corpus_coverage():
    try:
        from viva_superpowers.composite_generator import discover_generators
    except ModuleNotFoundError:
        from pbg_superpowers.composite_generator import discover_generators

    import viva_human_atlas.composites  # noqa: F401 registers generators

    names = {g.name for g in discover_generators().values()}
    assert "corpus-coverage" in names
