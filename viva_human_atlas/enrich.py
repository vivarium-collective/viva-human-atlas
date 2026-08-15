"""Enrich an existing BioModels->HRA map DB in place, without a full re-harvest.

Adds, per model, from data the DB already carries:
- `organism`: taxonomic species resolved from `taxonomy` (NCBITaxon) — see
  `organism.organisms_for_taxonomy`.
- `molecular_ids.hgnc` / `molecular_ids.ensembl`: gene ids crosswalked from the
  model's UniProt proteins — see `gene_ids.genes_for_uniprot`.
- extra HRA anatomy: the model's HGNC genes are mapped to Uberon anatomical
  structures via the harvested ASCT+B tables (`asctb_tables.build_gene_uberon_index`),
  unioned into `ontology_ids.uberon`, then re-run through `map_to_hra` so the
  gene-derived anatomy lifts the organ / FTU / cell-type coverage too.

This reuses the SBML/BioPAX/MeSH work already in the DB; only the new
network calls (UniProt per accession, NCBITaxon names) are made, and both are
disk-cached.
"""
from __future__ import annotations

from typing import Callable, Optional, Sequence

from viva_human_atlas.organism import organisms_for_taxonomy
from viva_human_atlas.gene_ids import genes_for_uniprot
from viva_human_atlas.hra_mapping import map_to_hra


def _merge_hra(entry: dict, hra: dict) -> None:
    """Union gene-derived organs / FTUs / cell types into the entry (dedup by id)."""
    have_org = {o.get("uberon") for o in entry.get("organs") or []}
    for o in hra.get("organs") or []:
        if o.get("uberon") not in have_org:
            have_org.add(o.get("uberon"))
            entry.setdefault("organs", []).append(o)
    have_ftu = {f.get("uberon") for f in entry.get("functional_tissue_units") or []}
    for f in hra.get("functional_tissue_units") or []:
        if f.get("uberon") not in have_ftu:
            have_ftu.add(f.get("uberon"))
            entry.setdefault("functional_tissue_units", []).append(f)
    have_cl = {c.get("cl") for c in entry.get("cell_types") or []}
    for c in hra.get("cell_types") or []:
        if c.get("cl") not in have_cl:
            have_cl.add(c.get("cl"))
            entry.setdefault("cell_types", []).append(c)


def enrich_entry(entry: dict, *, gene_index: dict, organ_index: dict,
                 cache_dir: Optional[str] = None) -> dict:
    """Enrich one DB entry in place (organism + gene ids + gene->Uberon anatomy)."""
    # organism (from the taxonomy the DB already stores)
    entry["organism"] = organisms_for_taxonomy(entry.get("taxonomy") or [], cache_dir=cache_dir)

    mol = entry.setdefault("molecular_ids", {})
    accs = mol.get("uniprot") or []
    genes = genes_for_uniprot(accs, cache_dir=cache_dir) if accs else {"hgnc": [], "ensembl": [], "symbols": []}
    mol["hgnc"] = genes["hgnc"]
    mol["ensembl"] = genes["ensembl"]
    entry.setdefault("gene_symbols", genes.get("symbols") or [])

    # gene -> Uberon via the ASCT+B tables, unioned into the model's anatomy
    gene_uberon = set()
    for h in genes["hgnc"]:
        gi = gene_index.get(h)
        if gi:
            gene_uberon |= set(gi.get("uberon") or [])
    ont = entry.setdefault("ontology_ids", {})
    if gene_uberon:
        merged = sorted(set(ont.get("uberon") or []) | gene_uberon)
        ont["uberon"] = merged
        hra = map_to_hra(merged, entry.get("name", ""), organ_index)
        _merge_hra(entry, hra)
    return entry


def enrich_map(entries: Sequence[dict], *, gene_index: dict,
               organ_index: Optional[dict] = None, cache_dir: Optional[str] = None,
               progress: Optional[Callable[[str], None]] = None) -> list:
    """Enrich every entry (organism + genes + gene->Uberon). Returns the list."""
    if organ_index is None:
        from viva_human_atlas.biomodel_do import build_organ_index
        organ_index = build_organ_index()
    total = len(entries)
    for i, e in enumerate(entries, 1):
        try:
            enrich_entry(e, gene_index=gene_index, organ_index=organ_index, cache_dir=cache_dir)
        except Exception as exc:  # noqa: BLE001 — never abort the whole run
            if progress:
                progress(f"  ERROR {e.get('biomodel_id')}: {exc}")
        if progress and i % 25 == 0:
            progress(f"  {i}/{total}")
    return list(entries)


import json
import os
from pathlib import Path
from process_bigraph import Step

from viva_human_atlas.biomodel_hra import load_map, summarize_map
from viva_human_atlas.asctb_tables import build_gene_uberon_index

_REPO = Path(__file__).resolve().parents[1]
_DEFAULT_DB = str(_REPO / "datasets" / "model_hra_map.json")
_DEFAULT_ASCTB = str(_REPO / "datasets" / "asctb_tables.json")


class GeneEnrichStep(Step):
    """Step: enrich the BioModels->HRA DB with organism + gene ids + gene->Uberon
    anatomy (Stage B). live=false replays the committed (already-enriched) DB and
    emits its counts; live=true re-runs enrich_map and rewrites the DB."""

    description = (
        "Enrich each model with its organism (from NCBITaxon), HGNC/Ensembl "
        "genes (from UniProt), and gene-derived Uberon anatomy (via the ASCT+B "
        "gene->Uberon index), re-mapped to HRA organs/FTUs/cell types. Emits "
        "how many models carry gene ids and gene-derived anatomy."
    )

    config_schema = {
        "db_path": "string", "asctb_path": "string",
        "live": "boolean", "cache_dir": "string",
    }

    def inputs(self):
        return {"db_path": "string", "asctb_path": "string"}

    def outputs(self):
        return {"db_path": "string", "n_models_enriched": "integer",
                "n_models_with_uberon": "integer", "summary": "tree"}

    def update(self, inputs):
        db_path = inputs.get("db_path") or self.config.get("db_path") or _DEFAULT_DB
        asctb_path = inputs.get("asctb_path") or self.config.get("asctb_path") or _DEFAULT_ASCTB
        if self.config.get("live"):
            from viva_human_atlas.enrich import enrich_map
            from viva_human_atlas.biomodel_do import build_organ_index
            tables = json.loads(Path(asctb_path).read_text(encoding="utf-8"))
            gene_index = build_gene_uberon_index(tables)
            entries = load_map(db_path)
            enrich_map(entries, gene_index=gene_index, organ_index=build_organ_index(),
                       cache_dir=self.config.get("cache_dir") or None)
            _tmp = Path(db_path).with_suffix(".json.tmp")
            _tmp.write_text(json.dumps(list(entries), indent=2), encoding="utf-8")
            os.replace(_tmp, db_path)
        else:
            entries = load_map(db_path)
        n_enriched = sum(1 for e in entries if (e.get("molecular_ids") or {}).get("hgnc"))
        n_gene_uberon = sum(1 for e in entries if (e.get("ontology_ids") or {}).get("uberon"))
        return {
            "db_path": str(db_path),
            "n_models_enriched": n_enriched,
            "n_models_with_uberon": n_gene_uberon,
            "summary": summarize_map(entries),
        }


GeneEnrichStep.contract = {
    "summary": GeneEnrichStep.description,
    "outputs": {
        "db_path": "Passthrough path to the (rewritten if live) DB.",
        "n_models_enriched": "Models carrying HGNC gene ids.",
        "n_models_with_uberon": "Models carrying Uberon anatomy (any source).",
        "summary": "summarize_map coverage summary of the DB.",
    },
    "assumptions": [
        "live=false is the reproducible default: the committed DB is already "
        "enriched, so this loads and counts it without network. live=true "
        "makes UniProt + NCBITaxon calls (disk-cached) and rewrites the DB.",
    ],
}
