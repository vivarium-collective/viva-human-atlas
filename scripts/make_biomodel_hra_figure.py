"""BioModels -> HRA map: a single summary scientific figure.

Reads datasets/biomodel_hra_map.json and writes
reports/figures/biomodel_hra_summary.png. Run:
    .venv/bin/python scripts/make_biomodel_hra_figure.py
"""
import json
from pathlib import Path

import numpy as np
import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

REPO = Path(__file__).resolve().parents[1]
DB_PATH = REPO / "datasets" / "biomodel_hra_map.json"
OUT_PATH = REPO / "reports" / "figures" / "biomodel_hra_summary.png"

mpl.rcParams.update({
    "font.family": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
    "figure.dpi": 200, "savefig.dpi": 200,
    "axes.edgecolor": "#c9d2da", "axes.linewidth": 0.8,
    "text.color": "#1b2733", "axes.labelcolor": "#1b2733",
    "xtick.color": "#5b6b79", "ytick.color": "#5b6b79",
})

# palette (CVD-safe: blue family = molecular, amber family = HRA/anatomy)
INK, MUTED, FAINT = "#14202b", "#5b6b79", "#9aa8b4"
GRID, SURFACE = "#e9eef2", "#f7f9fb"
MOL = "#2166a5"      # molecular annotations (blue)
ANA = "#d98a1f"      # HRA / anatomy annotations (amber)
ACCENT = "#c2410c"   # deep coral, for hero highlight

d = json.loads(DB_PATH.read_text())
N = len(d)

# (label, family, per-model count fn)
CATS = [
    ("Organs", "ana", lambda e: len(e["organs"])),
    ("Functional tissue units", "ana", lambda e: len(e["functional_tissue_units"])),
    ("Cell types", "ana", lambda e: len(e["cell_types"])),
    ("Uberon (anatomy)", "ana", lambda e: len(e["ontology_ids"]["uberon"])),
    ("HRApop cell types", "ana", lambda e: sum(len(h["cell_types"]) for h in e.get("hra_pop", []))),
    ("MeSH (from paper)", "mol", lambda e: len(e["ontology_ids"]["mesh"])),
    ("CHEBI", "mol", lambda e: len(e["molecular_ids"]["chebi"])),
    ("UniProt", "mol", lambda e: len(e["molecular_ids"]["uniprot"])),
    ("HGNC (gene)", "mol", lambda e: len(e["molecular_ids"].get("hgnc") or [])),
    ("Ensembl (gene)", "mol", lambda e: len(e["molecular_ids"].get("ensembl") or [])),
    ("KEGG", "mol", lambda e: len(e["molecular_ids"]["kegg"])),
    ("GO", "mol", lambda e: len(e["molecular_ids"]["go"])),
]
data = {}
for label, fam, fn in CATS:
    c = np.array([fn(e) for e in d])
    data[label] = dict(fam=fam, counts=c, nz=c[c > 0],
                       cov=int((c > 0).sum()), mean=float(c[c > 0].mean()) if (c > 0).any() else 0.0)

fig = plt.figure(figsize=(16, 11))
fig.patch.set_facecolor("white")

# ===================== HEADER =====================
fig.text(0.045, 0.955, "Harvesting BioModels into the Human Reference Atlas",
         fontsize=26, fontweight="bold", color=INK, va="top")
fig.text(0.045, 0.918,
         "1,096 curated BioModels → molecular identifiers (incl. HGNC / Ensembl genes), organism, "
         "publication links, and HRA organ / FTU / cell-type mapping\n(anatomy crosswalked from paper "
         "MeSH + BTO + ASCT+B gene→Uberon), with HRApop measured cell-type populations.",
         fontsize=12.5, color=MUTED, va="top", linespacing=1.5)

# hero stat tiles
n_ube = data["Uberon (anatomy)"]["cov"]
n_gene = data["HGNC (gene)"]["cov"]
n_org = sum(1 for e in d if e.get("organism"))
heroes = [(f"{N:,}", "models harvested", INK),
          (str(n_gene), f"with gene ids ({round(100*n_gene/N)}%)", MOL),
          (str(n_ube), f"mapped to Uberon ({round(100*n_ube/N)}%)", ANA),
          (str(n_org), f"with organism ({round(100*n_org/N)}%)", ACCENT)]
x0, w, gap = 0.045, 0.212, 0.023
for i, (num, lab, col) in enumerate(heroes):
    x = x0 + i * (w + gap)
    ax = fig.add_axes([x, 0.788, w, 0.088]); ax.axis("off")
    ax.add_patch(FancyBboxPatch((0, 0), 1, 1, boxstyle="round,pad=0.02,rounding_size=0.06",
                 transform=ax.transAxes, facecolor=SURFACE, edgecolor=GRID, linewidth=1.0))
    ax.text(0.06, 0.60, num, fontsize=30, fontweight="bold", color=col, va="center")
    ax.text(0.06, 0.20, lab, fontsize=11.5, color=MUTED, va="center")

# ===================== BODY GRID =====================
gs = fig.add_gridspec(2, 5, left=0.045, right=0.975, top=0.685, bottom=0.135,
                      hspace=0.95, wspace=0.42)
ax_cov = fig.add_subplot(gs[:, 0:2])
hist_axes = [fig.add_subplot(gs[r, 2 + c]) for r in range(2) for c in range(3)]

# ---- Coverage bars (how many models carry each annotation) ----
order = sorted(CATS, key=lambda t: data[t[0]]["cov"])
labels = [t[0] for t in order]
covs = [data[l]["cov"] for l in labels]
cols = [ANA if data[l]["fam"] == "ana" else MOL for l in labels]
y = np.arange(len(labels))
ax_cov.barh(y, [N] * len(labels), color="#eef2f5", height=0.66, zorder=1)  # track
ax_cov.barh(y, covs, color=cols, height=0.66, zorder=3)
for yi, l in zip(y, labels):
    c = data[l]["cov"]
    ax_cov.text(c + N * 0.012, yi, f"{c}  ({round(100*c/N)}%)", va="center", ha="left",
                fontsize=10.5, color=INK, fontweight="bold", zorder=4)
ax_cov.set_yticks(y); ax_cov.set_yticklabels(labels, fontsize=11, color=INK)
ax_cov.set_xlim(0, N * 1.18); ax_cov.set_xticks([0, 274, 548, 822, 1096])
ax_cov.set_xlabel("models with ≥ 1 term  (of 1,096)", fontsize=10.5, color=MUTED)
ax_cov.set_title("How many models carry each annotation", fontsize=14, fontweight="bold",
                 color=INK, loc="left", pad=12)
for s in ["top", "right", "left"]:
    ax_cov.spines[s].set_visible(False)
ax_cov.tick_params(length=0); ax_cov.grid(axis="x", color=GRID, lw=0.8, zorder=0)
ax_cov.set_axisbelow(True)

# ---- Small-multiple distributions (how many terms per model) ----
panel_cats = ["Organs", "Functional tissue units", "Cell types", "Uberon (anatomy)",
              "MeSH (from paper)", "HGNC (gene)"]
for ax, label in zip(hist_axes, panel_cats):
    dat = data[label]; nz = dat["nz"]; fam_col = ANA if dat["fam"] == "ana" else MOL
    cap = int(np.percentile(nz, 97)) if len(nz) else 1
    cap = max(cap, 4)
    if cap <= 20:
        bins = np.arange(0.5, cap + 1.5, 1)
    else:
        bins = np.linspace(0.5, cap + 0.5, 22)
    clipped = np.clip(nz, None, cap)
    ax.hist(clipped, bins=bins, color=fam_col, edgecolor="white", linewidth=0.6, zorder=3)
    ax.axvline(dat["mean"], color=INK, lw=1.4, ls=(0, (3, 2)), zorder=4)
    ax.set_title(label, fontsize=11.5, fontweight="bold", color=INK, loc="left", pad=30)
    ax.text(0.0, 1.055, f"{dat['cov']} models · mean {dat['mean']:.1f}/model · max {int(dat['counts'].max())}",
            transform=ax.transAxes, fontsize=9, color=MUTED, va="bottom")
    ax.text(dat["mean"], ax.get_ylim()[1], "  mean", fontsize=8, color=INK, va="top", ha="left")
    for s in ["top", "right"]:
        ax.spines[s].set_visible(False)
    ax.tick_params(length=0, labelsize=9)
    ax.grid(axis="y", color=GRID, lw=0.7, zorder=0); ax.set_axisbelow(True)
    ax.set_xlabel("terms per model", fontsize=9, color=MUTED)
    ax.set_ylabel("models", fontsize=9, color=MUTED)

# legend for families
fig.text(0.045, 0.045, "■", color=ANA, fontsize=13, va="center")
fig.text(0.060, 0.045, "HRA / anatomy annotation", color=MUTED, fontsize=10.5, va="center")
fig.text(0.235, 0.045, "■", color=MOL, fontsize=13, va="center")
fig.text(0.250, 0.045, "molecular annotation", color=MUTED, fontsize=10.5, va="center")
fig.text(0.975, 0.045, "source: datasets/biomodel_hra_map.json  ·  vivarium-collective/viva-human-atlas",
         color=FAINT, fontsize=9, va="center", ha="right")

OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(OUT_PATH, facecolor="white", bbox_inches="tight", pad_inches=0.3)
print("wrote", OUT_PATH)
