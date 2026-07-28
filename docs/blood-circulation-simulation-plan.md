# Blood-circulation simulation — design plan

**Goal.** Turn the atlas's isolated organ models into one *circulating whole* by
coupling them through a blood-transport network built from the HRA/VCCF
vasculature data. Blood carries a shared solute vector (glucose, O₂, insulin,
lactate, …) from organ to organ around a closed heart-driven circuit, with
transport delays set by the vascular path and flow rate. This is the connective
substrate that lets, e.g., hepatic glucose output reach the pancreatic β-cell —
physically, with the right ordering and lag — instead of the organs being
simulated as islands.

Companion study: [`studies/blood-vasculature-network`](../studies/blood-vasculature-network/study.yaml).
Data + provenance: [`datasets/vasculature/README.md`](../datasets/vasculature/README.md).
Loader/graph: [`viva_human_atlas/vasculature.py`](../viva_human_atlas/vasculature.py).

---

## 1. Data foundation (done — v1)

`VasculatureNetworkStep` builds a **directed whole-body transport graph** from
`datasets/vasculature/`:

- **Nodes** — 191 vessels/chambers/capillaries, class-tagged (94 artery · 20
  capillary · 73 vein · 4 heart chamber).
- **Edges** — 444 directed flow edges (upstream → downstream), from the ordered
  FTU paths.
- **FTU routes** — 28 functional tissue units, each a *closed* heart → FTU
  capillary → heart circuit (validated: 28 closed, 0 open).
- Richer connectivity available but not yet used: VCCF `Vessel.csv`
  (`BranchesFrom` parent tree, 1082 vessels; artery↔vein pairing) and
  `Geometry.csv` (per-vessel radius/length for resistances).

That graph `G = (V, E)` is the substrate everything below runs on.

## 2. Architecture — a process-bigraph composite

Model the circulation as one composite with three kinds of part sharing a
**blood compartment store**:

```
composite: blood-circulation
  stores:
    blood/<vessel>        # per-vessel plasma state: {volume, flow_Q, solutes:{glucose,O2,...}}
  processes:
    heart          Process   # the pump — sets total cardiac output, drives chamber outflow
    transport      Process   # BloodTransportProcess — advects solutes along E each tick
    organs/<name>  Process   # an EXISTING organ model, perfused by its FTU's capillary store
```

- **`BloodTransportProcess`** (new) — the heart of it. Reads the graph `G`, and
  each tick moves solute mass along every edge `(u→v)` by the flow `Q(u→v)`:
  `dSolute_v = Σ_u Q(u→v)·C_u − Σ_w Q(v→w)·C_v` (advective mixing; concentration
  `C = solute/volume`). At branch points, inflows mix in proportion to their `Q`.
  Ports: one blood sub-store per vessel; config: `G`, per-edge `Q`, `dt`.
- **`heart`** — sets total cardiac output `CO` and pushes it out of the
  ventricles; closes the loop by summing venous return at the atria. v1 can be a
  constant `CO`; later a simple contractile model.
- **`organs/<name>`** — a *wrapped existing organ Process* (a glucose biomodel,
  an FTU model). It reads the solute concentration of the capillary store it is
  perfused by (`blood/<FTU-capillary>`) and writes its uptake/production back
  into that store. The organ's internal dynamics are unchanged; only a thin
  **perfusion adapter** couples its boundary metabolites to the blood.

This is deliberately the vivarium/process-bigraph idiom: organs stay independent
Processes; the blood store + transport process are what wire them together. Any
organ model that exposes boundary solute exchange can be plugged in.

## 3. Assigning per-edge flow `Q` (the hemodynamics)

The topology gives edges; we still need a flow on each. Two routes, in order of
increasing fidelity:

1. **Cardiac-output partition (v2, start here).** Split total `CO` across FTUs
   by organ perfusion fraction (well-tabulated: brain ~15%, kidneys ~20%, etc.),
   then push each FTU's share down its (series) arterial path and back up its
   venous path. Mass-conserving and needs no geometry. **This is exactly the
   approach of Font-Clos et al. 2020** (`optimize_organ_coefficients.py` fits
   per-organ flow fractions; `solve_flows_network.py` solves the network flows) —
   our closest published precedent for a whole-body organ-flow network.
2. **Resistance network (v3).** Treat each vessel as a Poiseuille resistor
   `R = 8ηL/(πr⁴)` from `Geometry.csv` radii/lengths, the heart as a pressure
   source, and solve the linear network `Q = ΔP/R` (Kirchhoff) for all edges —
   giving flows at branch points from first principles rather than tabulated
   fractions.

Both yield a `Q: E → ℝ⁺` that `BloodTransportProcess` consumes; we can swap them
behind the same interface.

## 4. Solute transport & delay

- **State per vessel:** `{volume, solutes:{name→mass}}`; concentration `C = mass/volume`.
- **Advection:** the update in §2 moves mass at `Q`; a solute injected at the
  aorta reaches an FTU after a delay `≈ Σ (volume/Q)` over its arterial path —
  the physiological transport lag we want, emergent from the graph + flows.
- **Exchange at organs:** the organ adapter adds/removes solute at the FTU
  capillary store (uptake, secretion), so downstream (venous) concentrations
  reflect what the organ did.
- **Conservation check:** total solute mass is conserved except at organ
  sources/sinks and (optionally) lung/gut boundary exchange — a built-in
  validation readout.

## 5. First coupling — glucose regulation, circulating

Reuse the existing `glucose-regulation` organ models as the first real payload:

- **liver** (hepatic glucose production/uptake), **pancreas** (β-cell
  insulin secretion vs glucose), **muscle/periphery** (insulin-driven uptake) —
  each perfused by its FTU capillary store.
- Blood carries `glucose` and `insulin` between them around the circuit.
- **Expected emergent behavior:** a glucose bolus at the gut/portal inflow raises
  hepatic then systemic glucose, the pancreas (perfused a transport-delay later)
  raises insulin, insulin circulates to muscle+liver, uptake pulls glucose back
  down — the classic feedback loop, now with vasculature-set delays instead of a
  single well-mixed compartment. That delay structure is the scientific payoff
  over a lumped ODE.

## 6. Roadmap

| Phase | Deliverable | Status |
|------|-------------|--------|
| v1 | VCCF → validated directed transport graph (`VasculatureNetworkStep`) | **done** (this study) |
| v2 | `BloodTransportProcess` + heart pump; cardiac-output-partition flows; advect one tracer around the closed loop; conservation + delay readouts | next |
| v3 | Resistance-network flows from `Geometry.csv`; branch-point mixing via the VCCF `BranchesFrom` tree | planned |
| v4 | Perfusion adapter + couple the glucose-regulation organ models (liver/pancreas/muscle) as the first circulating multi-organ composite | planned |
| v5 | Add organs/solutes (O₂ via lung, lactate, hormones); compare delay-structured vs lumped predictions | planned |

## 7. Open decisions

- **Topology grain:** the 28 curated FTU paths (clean, series routes) vs the full
  VCCF `Vessel.csv` `BranchesFrom` tree (captures shared trunks / mixing, but
  messier). Start with FTU paths; add the tree at v3 for branch mixing. *(the
  study's main expert question.)*
- **Flow model:** cardiac-output partition (fast, tabulated) vs resistance
  network (first-principles, needs geometry). Ship the partition first.
- **Organ interface contract:** the minimal boundary each organ Process must
  expose to be perfusable (which solutes, uptake vs secretion sign convention,
  units). Define once so any atlas organ model can join.
- **Units & timescales:** reconcile organ-model internal timesteps (often
  minutes) with circulation time (~1 min for a full loop) — likely a fast
  transport sub-step within each organ step.

## 8. References

- **Font-Clos F, Zapperi S, La Porta CAM. Blood Flow Contributions to Cancer
  Metastasis. iScience. 2020;23(5):101073.** doi:10.1016/j.isci.2020.101073
  (PMID 32361595; PMCID PMC7200936). Whole-body organ-flow-network precedent;
  code: <https://github.com/ComplexityBiosystems/CTC-model>
  (`solve_flows_network.py`, `optimize_organ_coefficients.py`,
  `launch_tracers_fullsystem.py`). — `references/papers.bib`: `FontClos2020BloodFlow`.
- **HRA VCCF** — <https://humanatlas.io/vccf> · source CSVs
  <https://github.com/hubmapconsortium/hra-vccf> (MIT). — `references/papers.bib`: `HRA_VCCF`.
