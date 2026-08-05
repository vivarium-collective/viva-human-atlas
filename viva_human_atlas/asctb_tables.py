"""Harvest the HRA ASCT+B tables (Anatomical Structures, Cell Types +
Biomarkers) and build a gene->Uberon index.

Each organ has an ASCT+B table published as a CSV digital object on the HRA
CDN; the ASCT+B API parses one into JSON rows, where each row ties a set of
anatomical structures (Uberon) and cell types (Cell Ontology) to the
biomarker genes (HGNC) that characterise them. `harvest_asctb_tables` pulls
every organ's table (disk-cached per organ), and `build_gene_uberon_index`
inverts them into a `HGNC -> {uberon, cl, organs}` crosswalk.

Disk-cached; injectable `_get` for offline tests.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Callable, Dict, List, Optional
from urllib.parse import quote

from process_bigraph import Step

ASCTB_API = "https://apps.humanatlas.io/asctb-api/v2/csv"
CDN_CSV = (
    "https://cdn.humanatlas.io/digital-objects/asct-b/{organ}/latest/"
    "assets/asct-b-vh-{organ}.csv"
)
SHEET_CONFIG_URL = (
    "https://raw.githubusercontent.com/hubmapconsortium/ccf-asct-reporter/"
    "main/projects/v2/src/assets/sheet-config.json"
)

_REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT_PATH = _REPO / "datasets" / "asctb_tables.json"


def _default_get():
    import requests
    return requests.get


def _cdn_csv_url(organ: str) -> str:
    return CDN_CSV.format(organ=organ)


def list_asctb_organs(*, _get: Optional[Callable] = None) -> List[str]:
    """GET the ccf-asct-reporter `sheet-config.json` (a JSON list of
    `{name, sheetId, gid, ...}`) and return each entry's `name`, excluding the
    special aggregate `"all"`. ~40 organs.

    `_get` is an injectable requests.get-compatible callable (for tests);
    defaults to the real requests.get.
    """
    if _get is None:
        _get = _default_get()
    try:
        resp = _get(SHEET_CONFIG_URL, timeout=30)
        resp.raise_for_status()
        items = resp.json() or []
    except Exception:  # noqa: BLE001
        return []
    organs = []
    seen = set()
    for item in items:
        name = (item or {}).get("name")
        if not name or name == "all":
            continue
        # The CDN organ slug is lowercase-hyphenated; some sheet-config names
        # carry spaces/capitals (e.g. "small intestine" -> "small-intestine"),
        # which 404 against the CDN unless slugified.
        slug = re.sub(r"[^a-z0-9]+", "-", str(name).lower()).strip("-")
        if slug and slug not in seen:
            seen.add(slug)
            organs.append(slug)
    return organs


def fetch_asctb_table(organ: str, *, _get: Optional[Callable] = None) -> List[dict]:
    """Fetch one organ's ASCT+B table, returning the parsed JSON's `data` list
    (rows). Each row carries `anatomical_structures[]` / `cell_types[]`
    ({id, rdfs_label}) and `biomarkers_gene[]` ({id: "HGNC:3802", rdfs_label,
    name}). Returns `[]` on any failure.

    `_get` is an injectable requests.get-compatible callable (for tests);
    defaults to the real requests.get.
    """
    if _get is None:
        _get = _default_get()
    try:
        cdn_csv = _cdn_csv_url(organ)
        url = f"{ASCTB_API}?csvUrl={quote(cdn_csv)}&output=json"
        resp = _get(url, timeout=60)
        resp.raise_for_status()
        payload = resp.json() or {}
        return payload.get("data") or []
    except Exception:  # noqa: BLE001
        return []


def harvest_asctb_tables(
    *,
    organs: Optional[List[str]] = None,
    _get: Optional[Callable] = None,
    cache_dir: Optional[str] = None,
) -> Dict[str, List[dict]]:
    """Fetch each organ's ASCT+B table, disk-caching per organ under
    `cache_dir` as `<organ>.json` (loaded if present). Returns
    `{organ: rows}`; organs that fail are skipped (never aborts the harvest).

    `organs` defaults to `list_asctb_organs()`.
    """
    if organs is None:
        organs = list_asctb_organs(_get=_get)
    cache = Path(cache_dir) if cache_dir else None
    if cache:
        cache.mkdir(parents=True, exist_ok=True)
    tables: Dict[str, List[dict]] = {}
    for organ in organs:
        rows: Optional[List[dict]] = None
        cache_path = cache / f"{organ}.json" if cache else None
        if cache_path and cache_path.exists():
            try:
                rows = json.loads(cache_path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                rows = None
        if rows is None:
            rows = fetch_asctb_table(organ, _get=_get)
            if not rows:
                continue
            if cache_path:
                try:
                    tmp = cache_path.with_suffix(".json.tmp")
                    tmp.write_text(json.dumps(rows), encoding="utf-8")
                    os.replace(tmp, cache_path)
                except Exception:  # noqa: BLE001
                    pass
        tables[organ] = rows
    return tables


def _gene_label(gene: dict) -> str:
    return (gene.get("rdfs_label") or gene.get("name") or "").strip()


def build_gene_uberon_index(tables: Dict[str, List[dict]]) -> Dict[str, dict]:
    """Invert the harvested tables into a `HGNC -> {label, uberon, cl, organs}`
    crosswalk. For each `HGNC:` biomarker gene in each row, union that row's
    `UBERON:` anatomical-structure ids, `CL:` cell-type ids, and the organ the
    table came from.
    """
    index: Dict[str, dict] = {}
    for organ, rows in (tables or {}).items():
        for row in rows or []:
            uberon = {
                s.get("id")
                for s in (row.get("anatomical_structures") or [])
                if (s.get("id") or "").startswith("UBERON:")
            }
            cl = {
                c.get("id")
                for c in (row.get("cell_types") or [])
                if (c.get("id") or "").startswith("CL:")
            }
            for gene in row.get("biomarkers_gene") or []:
                gid = gene.get("id")
                if not gid or not gid.startswith("HGNC:"):
                    continue
                entry = index.get(gid)
                if entry is None:
                    entry = {
                        "label": _gene_label(gene),
                        "uberon": set(),
                        "cl": set(),
                        "organs": set(),
                    }
                    index[gid] = entry
                elif not entry["label"]:
                    entry["label"] = _gene_label(gene)
                entry["uberon"].update(uberon)
                entry["cl"].update(cl)
                entry["organs"].add(organ)
    return {
        gid: {
            "label": e["label"],
            "uberon": sorted(e["uberon"]),
            "cl": sorted(e["cl"]),
            "organs": sorted(e["organs"]),
        }
        for gid, e in index.items()
    }


def write_asctb_json(tables: Dict[str, List[dict]], path) -> None:
    """Write the harvested `{organ: rows}` to `path` (JSON, indent=2, sorted
    keys), atomically."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(
        json.dumps(tables, indent=2, sort_keys=True), encoding="utf-8"
    )
    os.replace(tmp, p)


class AsctbTablesStep(Step):
    """Step: harvest the HRA ASCT+B tables and index genes to Uberon/CL.

    Pulls every organ's ASCT+B table (Anatomical Structures, Cell Types +
    Biomarkers) from the HRA CDN via the ASCT+B API, writes the harvested
    `{organ: rows}` DB to `out_path`, and builds the `HGNC -> {uberon, cl,
    organs}` gene index for the emitted counts. Cache-or-load: if `out_path`
    already exists and `force` is off, it loads it instead of re-harvesting.
    """

    description = (
        "Harvest the HRA ASCT+B tables (Anatomical Structures, Cell Types + "
        "Biomarkers) for all ~40 organs and build a gene->Uberon index. "
        "Writes the harvested {organ: rows} DB to out_path; emits organ/gene "
        "counts plus a summary (not the whole DB)."
    )

    config_schema = {
        "out_path": "string",
        "cache_dir": "string",
        "force": "boolean",
        # Injected by the workbench for a `baseline.step` run: when set, a copy
        # of the DB is written there as a downloadable per-run analysis artifact.
        "analysis_out_dir": "string",
    }

    def inputs(self):
        return {}

    def outputs(self):
        return {
            "out_path": "string",
            "n_organs": "integer",
            "n_genes": "integer",
            "summary": "tree",
        }

    def update(self, inputs):
        out_path = Path(self.config.get("out_path") or str(DEFAULT_OUT_PATH))
        force = bool(self.config.get("force", False))
        cache_dir = self.config.get("cache_dir") or None
        tables: Optional[Dict[str, List[dict]]] = None
        if out_path.exists() and not force:
            try:
                tables = json.loads(out_path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                tables = None
        if tables is None:
            tables = harvest_asctb_tables(cache_dir=cache_dir)
            write_asctb_json(tables, out_path)
        index = build_gene_uberon_index(tables)
        n_rows = sum(len(rows or []) for rows in tables.values())
        summary = {
            "n_organs": len(tables),
            "n_genes": len(index),
            "n_rows": n_rows,
            "organs": sorted(tables.keys()),
        }
        self._write_analysis_copy(tables)
        return {
            "out_path": str(out_path),
            "n_organs": len(tables),
            "n_genes": len(index),
            "summary": summary,
        }

    def _write_analysis_copy(self, tables) -> None:
        """When the workbench injects `analysis_out_dir`, write the DB there as
        a downloadable per-run analysis artifact. Best-effort — never fails."""
        out_dir = self.config.get("analysis_out_dir")
        if not out_dir:
            return
        try:
            write_asctb_json(tables, Path(out_dir) / "asctb_tables.json")
        except Exception:  # noqa: BLE001
            pass


AsctbTablesStep.contract = {
    "summary": AsctbTablesStep.description,
    "outputs": {
        "out_path": "Repo-relative path to the harvested {organ: rows} ASCT+B "
                    "DB on disk.",
        "n_organs": "Number of organ tables harvested.",
        "n_genes": "Number of distinct HGNC biomarker genes indexed.",
        "summary": "Harvest summary: n_organs, n_genes, n_rows, and the sorted "
                   "list of organ names.",
    },
}
