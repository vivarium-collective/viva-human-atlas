"""`ModelConnectivityNetwork` — the model-to-model connectivity graph over the
curated BioModels/Physiome/PhysioNet corpus (the ``model_hra_map.json`` DB).

Two models are *connected* when they share biological content, in two
toggleable layers:

- **molecular** — shared molecular-species identifiers (CHEBI / UniProt / KEGG /
  GO / Reactome / HGNC / Ensembl). This is the mechanistic-coupling /
  "variable coverage" layer: an edge means the two models reference the same
  species, so they could in principle be composed through it.
- **anatomy** — shared HRA anatomy (organ / functional-tissue-unit / cell type).
  An edge means the two models describe the same tissue.

To keep the graph legible rather than a hairball, ubiquitous "stop-word"
variables (present in more than ``df_cap_frac`` of nodes, e.g. GO:0005623
"cell") are dropped, only variables shared by >= 2 models contribute edges,
and each node keeps at most ``top_k_edges`` strongest edges per layer.

Pure-Python (no networkx): an inverted index variable -> models drives pairwise
shared-counts; union-find gives connected components. Emits the network pack
(``network.json`` / ``config.json``) alongside the committed viewer assets so a
study's ``viz/network/`` is a self-contained static page (see
``workbench_viewers.get_viewers``).
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from importlib import resources
from itertools import combinations
from pathlib import Path

from process_bigraph import Step

_REPO = Path(__file__).resolve().parents[1]
DEFAULT_DB = _REPO / "datasets" / "model_hra_map.json"
DEFAULT_OUT_DIR = _REPO / "studies" / "model-connectivity" / "viz" / "network"
_VIEWER_ASSET_PACKAGE = "viva_human_atlas.assets.model_network_viewer"
_VIEWER_ASSET_FILES = ("index.html", "viewer.js")

_MOLECULAR_NAMESPACES = ("chebi", "uniprot", "kegg", "go", "reactome", "hgnc", "ensembl")
_ANATOMY_FIELDS = ("organs", "functional_tissue_units", "cell_types")


def load_models(db_path=None) -> list:
    path = Path(db_path) if db_path else DEFAULT_DB
    return json.loads(path.read_text(encoding="utf-8"))


def _molecular_tokens(row) -> set:
    out = set()
    mids = row.get("molecular_ids") or {}
    for ns in _MOLECULAR_NAMESPACES:
        for v in (mids.get(ns) or []):
            if isinstance(v, str) and v:
                out.add(f"{ns}:{v}")
    return out


def _anatomy_tokens(row) -> set:
    out = set()
    for field in _ANATOMY_FIELDS:
        for v in (row.get(field) or []):
            label = v if isinstance(v, str) else (v.get("label") or v.get("name") or v.get("id") if isinstance(v, dict) else None)
            if label:
                out.add(f"{field}:{label}")
    return out


def _primary_organ(row):
    organs = row.get("organs") or []
    if organs:
        o = organs[0]
        return o if isinstance(o, str) else (o.get("label") or o.get("name") or o.get("id"))
    return None


class _UnionFind:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[ra] = rb


def _layer_edges(tokens_per_node, *, df_cap_frac, min_shared, edge_df_cap, top_k_edges, n_nodes):
    """Return (edges, kept_token_df, dropped_stopwords) for one layer.

    edges: list of {"s": i, "t": j, "w": shared, "shared": [tokens...]} using
    node-index endpoints; symmetric pairs deduped (s < t).
    """
    # document frequency per token
    df = Counter()
    for toks in tokens_per_node:
        for t in toks:
            df[t] += 1
    stop_cap = max(2, int(df_cap_frac * n_nodes))
    # tokens that actually contribute edges: shared by >=2 but not ubiquitous,
    # and not so common that their clique dominates (edge_df_cap).
    edge_tokens = {t for t, c in df.items() if 2 <= c <= min(stop_cap, edge_df_cap)}
    stopwords = sorted((t for t, c in df.items() if c > stop_cap), key=lambda t: -df[t])

    inv = defaultdict(list)  # token -> [node indices]
    for i, toks in enumerate(tokens_per_node):
        for t in toks:
            if t in edge_tokens:
                inv[t].append(i)

    pair_shared = defaultdict(list)  # (i,j) -> [tokens]
    for t, nodes in inv.items():
        for i, j in combinations(sorted(nodes), 2):
            pair_shared[(i, j)].append(t)

    raw = [
        {"s": i, "t": j, "w": len(toks), "shared": sorted(toks)[:12]}
        for (i, j), toks in pair_shared.items()
        if len(toks) >= min_shared
    ]
    # per-node top-k by weight, to keep the graph sparse + legible
    by_node = defaultdict(list)
    for e in raw:
        by_node[e["s"]].append(e)
        by_node[e["t"]].append(e)
    keep = set()
    for _node, elist in by_node.items():
        # deterministic tie-break on (s, t) so edge selection is reproducible
        for e in sorted(elist, key=lambda e: (-e["w"], e["s"], e["t"]))[:top_k_edges]:
            keep.add((e["s"], e["t"]))
    edges = [e for e in raw if (e["s"], e["t"]) in keep]
    edges.sort(key=lambda e: (-e["w"], e["s"], e["t"]))
    return edges, df, stopwords


def _coverage(tokens_per_node, namespaces_or_fields, prefix_split=":"):
    """Per-namespace coverage: how many models carry each namespace and the top
    shared variables within it."""
    by_ns_models = defaultdict(set)
    by_ns_df = defaultdict(Counter)
    for i, toks in enumerate(tokens_per_node):
        for t in toks:
            ns = t.split(prefix_split, 1)[0]
            by_ns_models[ns].add(i)
            by_ns_df[ns][t] += 1
    out = {}
    for ns in namespaces_or_fields:
        dfc = by_ns_df.get(ns, Counter())
        out[ns] = {
            "n_models": len(by_ns_models.get(ns, ())),
            "n_distinct": len(dfc),
            "top": [[t.split(prefix_split, 1)[1], c] for t, c in dfc.most_common(10)],
        }
    return out


def build_network(db_path=None, *, df_cap_frac=0.15, min_shared=2, edge_df_cap=40, top_k_edges=8):
    """Compute the two-layer model connectivity network + variable coverage."""
    rows = load_models(db_path)
    mol = [_molecular_tokens(r) for r in rows]
    anat = [_anatomy_tokens(r) for r in rows]
    # node set: any model with >=1 molecular OR >=1 anatomy token
    idx = [i for i in range(len(rows)) if mol[i] or anat[i]]
    remap = {old: new for new, old in enumerate(idx)}
    nodes_rows = [rows[i] for i in idx]
    mol = [mol[i] for i in idx]
    anat = [anat[i] for i in idx]
    n = len(idx)

    mol_edges, mol_df, mol_stop = _layer_edges(
        mol, df_cap_frac=df_cap_frac, min_shared=min_shared,
        edge_df_cap=edge_df_cap, top_k_edges=top_k_edges, n_nodes=n)
    anat_edges, _anat_df, _anat_stop = _layer_edges(
        anat, df_cap_frac=0.5, min_shared=1, edge_df_cap=60, top_k_edges=top_k_edges, n_nodes=n)

    deg_mol = Counter()
    for e in mol_edges:
        deg_mol[e["s"]] += 1
        deg_mol[e["t"]] += 1
    deg_anat = Counter()
    for e in anat_edges:
        deg_anat[e["s"]] += 1
        deg_anat[e["t"]] += 1

    # connected components on the molecular layer (the mechanistic backbone)
    uf = _UnionFind(n)
    for e in mol_edges:
        uf.union(e["s"], e["t"])
    comp_label = {}
    for i in range(n):
        comp_label.setdefault(uf.find(i), len(comp_label))
    comps = Counter(uf.find(i) for i in range(n))
    largest = max(comps.values()) if comps else 0

    nodes = []
    for new_i, r in enumerate(nodes_rows):
        nodes.append({
            "id": r.get("identifier") or r.get("biomodel_id") or f"model-{new_i}",
            "label": (r.get("name") or r.get("identifier") or "")[:80],
            "source": r.get("repository") or "unknown",
            "organ": _primary_organ(r),
            "n_mol": len(mol[new_i]),
            "n_anat": len(anat[new_i]),
            "deg_mol": deg_mol.get(new_i, 0),
            "deg_anat": deg_anat.get(new_i, 0),
            "component": comp_label[uf.find(new_i)],
            "url": r.get("paper_url") or r.get("model_url") or r.get("model_ref"),
        })

    coverage = {
        "molecular": _coverage(mol, _MOLECULAR_NAMESPACES),
        "anatomy": _coverage(anat, _ANATOMY_FIELDS),
    }
    # hub variables: most widely-shared non-stopword molecular variables
    hubs = [
        {"variable": t, "n_models": c}
        for t, c in mol_df.most_common(40)
        if 2 <= c <= max(2, int(df_cap_frac * n))
    ][:12]

    stats = {
        "n_models_total": len(rows),
        "n_nodes": n,
        "n_edges_molecular": len(mol_edges),
        "n_edges_anatomy": len(anat_edges),
        "n_components": len(comps),
        "largest_component": largest,
        "largest_component_frac": round(largest / n, 3) if n else 0,
        "n_molecular_stopwords_dropped": len(mol_stop),
        "molecular_hubs": hubs,
        "params": {"df_cap_frac": df_cap_frac, "min_shared": min_shared,
                   "edge_df_cap": edge_df_cap, "top_k_edges": top_k_edges},
    }
    return {
        "generated_from": "datasets/model_hra_map.json",
        "layers": ["molecular", "anatomy"],
        "nodes": nodes,
        "edges": {"molecular": mol_edges, "anatomy": anat_edges},
        "coverage": coverage,
        "stats": stats,
    }


def materialize_network(study_dir, network) -> Path:
    """Write network.json + config.json and copy the viewer assets into
    `study_dir/viz/network/` (a self-contained static page)."""
    out_dir = Path(study_dir) / "viz" / "network"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "network.json").write_text(json.dumps(network, indent=1), encoding="utf-8")
    (out_dir / "config.json").write_text(
        json.dumps({"data": "network.json", "title": "Model Connectivity Network"}, indent=2),
        encoding="utf-8")
    asset_dir = resources.files(_VIEWER_ASSET_PACKAGE)
    for name in _VIEWER_ASSET_FILES:
        (out_dir / name).write_bytes((asset_dir / name).read_bytes())
    return out_dir


def build_and_write_network(db_path=None, out_dir=None, **kw):
    net = build_network(db_path, **kw)
    target = Path(out_dir) if out_dir else DEFAULT_OUT_DIR  # the viz/network dir
    materialize_network(target.parent.parent, net)  # pass the STUDY dir (…/<slug>)
    return net


class ModelConnectivityNetwork(Step):
    """Step: build the model-to-model connectivity network (molecular + anatomy
    layers) over the curated BioModels/Physiome/PhysioNet corpus and write the
    self-contained network-explorer pack to the study's viz/network/."""

    description = (
        "Build the model connectivity network over the curated corpus: nodes are "
        "models, edges are shared molecular species (CHEBI/UniProt/KEGG/GO/"
        "Reactome) and shared HRA anatomy (organ/FTU/cell-type), ubiquitous "
        "stop-word variables dropped and each node kept to its strongest edges. "
        "Writes network.json + the force-graph explorer to viz/network/; emits "
        "variable-coverage + connectivity stats."
    )

    config_schema = {
        "db_path": "string",
        "out_dir": "string",
        "df_cap_frac": "float",
        "min_shared": "integer",
        "edge_df_cap": "integer",
        "top_k_edges": "integer",
    }

    def inputs(self):
        return {"db_path": "string"}

    def outputs(self):
        return {"coverage": "tree", "stats": "tree", "out_dir": "string"}

    def update(self, inputs):
        out_dir = self.config.get("out_dir") or str(DEFAULT_OUT_DIR)
        db_path = inputs.get("db_path") or self.config.get("db_path") or None
        kw = {}
        for k, cast in (("df_cap_frac", float), ("min_shared", int),
                        ("edge_df_cap", int), ("top_k_edges", int)):
            v = self.config.get(k)
            if v not in (None, ""):
                kw[k] = cast(v)
        net = build_network(db_path, **kw)
        materialize_network(Path(out_dir).parent.parent, net)  # pass the STUDY dir
        return {"coverage": net["coverage"], "stats": net["stats"], "out_dir": str(out_dir)}


ModelConnectivityNetwork.contract = {
    "summary": ModelConnectivityNetwork.description,
    "outputs": {
        "coverage": "Per-namespace variable coverage (molecular + anatomy): how "
                    "many models carry each namespace and its top shared variables.",
        "stats": "Connectivity stats: n_nodes, edges per layer, components, "
                 "largest-component fraction, molecular hub variables.",
        "out_dir": "Directory the network pack (network.json/config.json) was written to.",
    },
    "assumptions": [
        "Edges are co-occurrence of curated identifiers, not verified "
        "mechanistic compatibility: a shared CHEBI/UniProt id means both models "
        "reference that species, not that their rate laws or units agree. "
        "Ubiquitous stop-word variables (present in > df_cap_frac of models) are "
        "dropped so generic terms like GO:0005623 'cell' do not create a "
        "meaningless hairball, and each node keeps only its strongest edges.",
    ],
}
