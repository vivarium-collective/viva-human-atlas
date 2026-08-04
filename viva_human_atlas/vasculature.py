"""Load the HRA / VCCF vasculature data and build a whole-body blood-transport
network from it.

This is the data-pull + graph-build that the ``blood-vasculature-network`` study
runs, and the foundation for the blood-circulation simulation planned in
``docs/blood-circulation-simulation-plan.md`` (organ models coupled through a
shared blood compartment routed along this network).

Two complementary sources, both under ``datasets/vasculature/`` (see the README
there for provenance + licenses):

  * ``FTU_Table_S1_260611.csv`` — for each of 28 functional tissue units (FTUs),
    an *ordered* heart -> FTU -> heart vessel path. ``PathStep`` runs negative on
    the arterial side (toward the FTU), ``0`` at the FTU capillary, positive on
    the venous side (back to the heart). This is the cleanest topology source: a
    complete transport route per FTU, so the union over all FTUs is a directed
    whole-body circuit.

  * ``vccf/Vessel.csv`` — the VCCF master vessel table (type/subtype, body part,
    artery-vein pairing, ``BranchesFrom`` parent links). Present under
    ``datasets/vasculature/`` as reference/provenance only; it is NOT read by
    this builder. Vessel class (artery / vein / capillary / chamber) is derived
    from the ``FTU_Table_S1`` ``PathStep`` sign and the heart-chamber set (see
    ``_klass_for``), not from ``Vessel.csv``.

The builder is deliberately dependency-light (stdlib ``csv`` only, an adjacency
dict rather than a networkx import) so it runs anywhere the workspace does.

Data seam: ``load_ftu_table`` parses the CSV into ``(ftu_paths, ftu_ids)``;
``build_vascular_graph`` / ``vascular_network_summary`` accept those parsed
structures directly (``ftu_paths=`` / ``ftu_ids=``) so the file read can be
lifted into an upstream ``FTUPathTableStep`` and handed over in-graph, rather
than every consumer reading a hardcoded dataset path.
"""
from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

# Heart chambers that anchor the circuit (a path that starts/ends here is
# "closed" through the heart). Names as they appear in FTU_Table_S1.
HEART_CHAMBERS = {
    "right atrium", "right ventricle", "left atrium", "left ventricle",
}


def _dataset_dir(ws_root: Path | str | None = None) -> Path:
    """``datasets/vasculature`` under the workspace root (default: this repo)."""
    if ws_root is not None:
        return Path(ws_root) / "datasets" / "vasculature"
    # viva_human_atlas/vasculature.py -> repo root -> datasets/vasculature
    return Path(__file__).resolve().parent.parent / "datasets" / "vasculature"


@dataclass
class VascularNetwork:
    """A directed blood-transport graph built from the FTU paths.

    * ``nodes``: vessel/chamber name -> {id, klass}. ``klass`` is one of
      ``artery`` / ``capillary`` / ``vein`` / ``chamber`` (inferred from the
      FTU-path side + heart-chamber set).
    * ``edges``: set of (upstream, downstream) directed flow edges.
    * ``ftu_routes``: FTU name -> ordered list of vessel names (heart -> FTU ->
      heart), the per-organ route a solute takes.
    * ``ftu_ids``: FTU name -> ontology id (Uberon/FMA).
    """

    nodes: dict[str, dict] = field(default_factory=dict)
    edges: set[tuple[str, str]] = field(default_factory=set)
    ftu_routes: dict[str, list[str]] = field(default_factory=dict)
    ftu_ids: dict[str, str] = field(default_factory=dict)

    # ---- adjacency helpers -------------------------------------------------
    def downstream(self, vessel: str) -> list[str]:
        return sorted(d for (u, d) in self.edges if u == vessel)

    def upstream(self, vessel: str) -> list[str]:
        return sorted(u for (u, d) in self.edges if d == vessel)


def _parse_ftu_paths(fp: Path) -> dict[str, list[dict]]:
    """FTU name -> ordered path steps (by ``PathStep``) from a CSV file path."""
    by_ftu: dict[str, list[dict]] = defaultdict(list)
    with open(fp, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            step_raw = (r.get("PathStep") or "").strip()
            try:
                step = int(step_raw)
            except ValueError:
                continue
            by_ftu[r["FTU"].strip()].append({
                "step": step,
                "vessel": (r.get("PathVessel") or "").strip(),
                # NOTE: the source header misspells this column as "PahtVesselID".
                "vessel_id": (r.get("PahtVesselID") or r.get("PathVesselID") or "").strip(),
            })
    for ftu in by_ftu:
        by_ftu[ftu].sort(key=lambda s: s["step"])
    return dict(by_ftu)


def _parse_ftu_ids(fp: Path) -> dict[str, str]:
    """FTU name -> ontology id (Uberon/FMA), from a CSV file path."""
    ftu_ids: dict[str, str] = {}
    with open(fp, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            ftu = r["FTU"].strip()
            if ftu and ftu not in ftu_ids and (r.get("FTUID") or "").strip():
                ftu_ids[ftu] = r["FTUID"].strip()
    return ftu_ids


def load_ftu_paths(ws_root: Path | str | None = None) -> dict[str, list[dict]]:
    """FTU name -> ordered path steps (by ``PathStep``) from ``FTU_Table_S1``.

    Each step dict: ``{step, vessel, vessel_id}``.
    """
    return _parse_ftu_paths(_dataset_dir(ws_root) / "FTU_Table_S1_260611.csv")


def load_ftu_table(
    path: Path | str | None = None, ws_root: Path | str | None = None
) -> tuple[dict[str, list[dict]], dict[str, str]]:
    """Parse ``FTU_Table_S1`` into ``(ftu_paths, ftu_ids)``.

    ``path`` names the CSV directly; otherwise it resolves to
    ``datasets/vasculature/FTU_Table_S1_260611.csv`` under ``ws_root`` (default
    this repo). This is the single file-read seam — an upstream
    ``FTUPathTableStep`` calls it once and hands the parsed table to
    ``build_vascular_graph`` in-graph, so consumers no longer read a hardcoded
    dataset path.
    """
    fp = Path(path) if path else (_dataset_dir(ws_root) / "FTU_Table_S1_260611.csv")
    return _parse_ftu_paths(fp), _parse_ftu_ids(fp)


def _klass_for(step: int, vessel: str) -> str:
    if vessel.lower() in HEART_CHAMBERS:
        return "chamber"
    if step < 0:
        return "artery"
    if step > 0:
        return "vein"
    return "capillary"   # step == 0 is the FTU exchange vessel


def build_vascular_graph(
    ws_root: Path | str | None = None,
    *,
    ftu_paths: dict[str, list[dict]] | None = None,
    ftu_ids: dict[str, str] | None = None,
) -> VascularNetwork:
    """Build the directed whole-body transport graph from the FTU paths.

    When ``ftu_paths`` is given (e.g. handed over in-graph by an upstream
    ``FTUPathTableStep``) it is used directly and no file is read; otherwise the
    table is loaded from ``ws_root`` (default this repo).
    """
    if ftu_paths is None:
        ftu_paths, loaded_ids = load_ftu_table(ws_root=ws_root)
        if ftu_ids is None:
            ftu_ids = loaded_ids
    net = VascularNetwork()
    net.ftu_ids = dict(ftu_ids or {})

    for ftu, steps in ftu_paths.items():
        route: list[str] = []
        for s in steps:
            v = s["vessel"]
            if not v:
                continue
            node = net.nodes.setdefault(v, {"id": s["vessel_id"], "klass": _klass_for(s["step"], v)})
            if not node["id"] and s["vessel_id"]:
                node["id"] = s["vessel_id"]
            route.append(v)
        # Directed flow edges between consecutive vessels along the route.
        for a, b in zip(route, route[1:]):
            if a != b:
                net.edges.add((a, b))
        net.ftu_routes[ftu] = route
    return net


def vascular_network_summary(
    ws_root: Path | str | None = None,
    *,
    ftu_paths: dict[str, list[dict]] | None = None,
    ftu_ids: dict[str, str] | None = None,
) -> dict:
    """Structured summary + closed-circuit validation for the study readout.

    Accepts a pre-parsed ``ftu_paths``/``ftu_ids`` (in-graph handover) or loads
    from ``ws_root`` when not given."""
    net = build_vascular_graph(ws_root, ftu_paths=ftu_paths, ftu_ids=ftu_ids)
    klass_counts: dict[str, int] = defaultdict(int)
    for n in net.nodes.values():
        klass_counts[n["klass"]] += 1

    # Closed-circuit check: each FTU route should start AND end at a heart chamber.
    closed, open_routes = [], []
    for ftu, route in net.ftu_routes.items():
        ok = bool(route) and route[0].lower() in HEART_CHAMBERS and route[-1].lower() in HEART_CHAMBERS
        (closed if ok else open_routes).append(ftu)

    chambers_used = sorted({v for v in net.nodes if v.lower() in HEART_CHAMBERS})
    return {
        "n_ftus": len(net.ftu_routes),
        "n_vessels": len(net.nodes),
        "n_edges": len(net.edges),
        "vessel_classes": dict(sorted(klass_counts.items())),
        "heart_chambers": chambers_used,
        "n_closed_circuits": len(closed),
        "n_open_routes": len(open_routes),
        "open_routes": sorted(open_routes),
        "example_route": {
            "ftu": "alveolus of lung",
            "route": net.ftu_routes.get("alveolus of lung", []),
        },
    }


if __name__ == "__main__":   # quick smoke check / study readout
    import json
    print(json.dumps(vascular_network_summary(), indent=2))
