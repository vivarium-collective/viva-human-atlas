/* Model Connectivity Network — self-contained canvas force-directed explorer.
 *
 * Reads a sibling config.json -> {"data":"network.json","title":"..."}, then
 * loads network.json from the same directory. d3 v7 is loaded from a CDN in
 * index.html (global `d3`); everything else is inline. No build step, no query
 * params — works served as plain static files.
 *
 * Nodes are computational models; molecular edges link models that share
 * molecular variables (ChEBI/UniProt/GO/…), anatomy edges link models that
 * share anatomical structures (organs/FTUs/cell types). Edge weight `w` is the
 * count of shared variables. Rendered on a <canvas> with a d3-force layout and
 * d3-zoom pan/zoom so ~1456 nodes / ~5000 edges stay smooth.
 */
"use strict";
(function () {
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const overlay = $("overlay");
  function showError(title, msg) {
    overlay.hidden = false;
    overlay.classList.add("err");
    overlay.querySelector(".spinner").style.display = "none";
    $("ov-title").textContent = title;
    $("ov-msg").textContent = msg;
  }

  // ---- read a CSS custom property (theme-aware colors) ----
  const rootStyle = getComputedStyle(document.documentElement);
  const cssVar = (name) => rootStyle.getPropertyValue(name).trim();

  // ---- source + layer palettes (resolved from CSS vars; theme set at load) --
  const SRC_LABELS = { biomodels: "BioModels", physiome: "Physiome", physionet: "PhysioNet" };
  const srcLabel = (s) => SRC_LABELS[s] || (s ? s[0].toUpperCase() + s.slice(1) : "Other");
  const SRC_COLORS = {
    biomodels: cssVar("--src-biomodels") || "#4c92ff",
    physiome: cssVar("--src-physiome") || "#2bb673",
    physionet: cssVar("--src-physionet") || "#ff8a3d",
  };
  const FALLBACK_SRC = ["#4c92ff", "#2bb673", "#ff8a3d", "#e0a0ff", "#ffd166", "#5ad1c9"];
  const EDGE_COLORS = {
    molecular: cssVar("--edge-mol") || "#12a6a1",
    anatomy: cssVar("--edge-anat") || "#c05cd6",
  };
  const NULL_GREY = cssVar("--null-grey") || "#9aa4b2";
  // a 20-hue categorical ramp for organs (Tableau10 + Set3-ish, accessible)
  const ORGAN_PALETTE = [
    "#4e79a7", "#f28e2b", "#59a14f", "#e15759", "#b07aa1", "#76b7b2",
    "#edc948", "#ff9da7", "#9c755f", "#86bcb6", "#d37295", "#8cd17d",
    "#b6992d", "#499894", "#d7b5a6", "#fabfd2", "#79706e", "#f1ce63",
    "#a0cbe8", "#bab0ac",
  ];

  // prettify prefixed variable ids: "chebi:CHEBI:15422" -> "CHEBI:15422";
  // "organs:heart" -> "heart"; "cell_types:podocyte" -> "podocyte".
  function prettyVar(v) {
    const s = String(v || "");
    const i = s.indexOf(":");
    if (i < 0) return s;
    const ns = s.slice(0, i), rest = s.slice(i + 1);
    if (ns === "organs" || ns === "cell_types" || ns === "functional_tissue_units") return rest;
    return rest; // chebi:CHEBI:x / go:GO:x -> CHEBI:x / GO:x
  }
  const NS_LABELS = {
    chebi: "ChEBI", uniprot: "UniProt", kegg: "KEGG", go: "GO",
    reactome: "Reactome", hgnc: "HGNC", ensembl: "Ensembl",
    organs: "Organs", functional_tissue_units: "Functional tissue units",
    cell_types: "Cell types",
  };
  const nsLabel = (n) => NS_LABELS[n] || n;

  let DATA, nodes, linksAll;
  const adj = new Map();            // node index -> [{other, w, shared, layer}]
  const sources = [];               // distinct sources present
  const organs = [];                // distinct non-null organs present
  const hidden = { source: new Set(), organ: new Set() }; // filtered-out categories

  // ---- viewer state ----
  let layer = "molecular";          // molecular | anatomy | both
  let colorBy = "source";           // source | organ
  let minW = 1;
  let searchQ = "";
  let matchSet = new Set();         // node indices matching the search
  let selected = null;              // selected node object
  let frozen = false;

  const canvas = $("graph");
  const ctx = canvas.getContext("2d");
  let W = 0, H = 0, DPR = 1;
  let transform = d3.zoomIdentity;
  let sim = null;

  // -------------------------------------------------------------------------
  async function main() {
    let cfg;
    try {
      cfg = await fetch("config.json").then((r) => {
        if (!r.ok) throw new Error("config.json " + r.status);
        return r.json();
      });
    } catch (e) {
      showError("Could not load config.json",
        "Expected a config.json next to this page: {\"data\":\"network.json\",\"title\":\"…\"}. " + (e.message || e));
      return;
    }
    const title = cfg.title || "Model Connectivity Network";
    document.title = title;
    $("title").firstChild.nodeValue = title;

    const dataFile = cfg.data || "network.json";
    try {
      DATA = await fetch(dataFile).then((r) => {
        if (!r.ok) throw new Error(dataFile + " " + r.status);
        return r.json();
      });
    } catch (e) {
      showError("Could not load the network data",
        "Expected " + esc(dataFile) + " next to this page. " + (e.message || e));
      return;
    }

    try {
      build();
    } catch (e) {
      console.error(e);
      showError("Could not render the network", (e && e.message) || String(e));
      return;
    }
    overlay.hidden = true;
  }

  // -------------------------------------------------------------------------
  function build() {
    nodes = (DATA.nodes || []).map((n, i) => Object.assign({ index: i }, n));
    if (!nodes.length) throw new Error("network.json has no nodes");
    $("subtitle").textContent =
      `${nodes.length.toLocaleString()} models · molecular + anatomy connectivity`;

    // distinct sources / organs present (read from the data, never assumed)
    const srcSet = new Set(), orgSet = new Set();
    for (const n of nodes) {
      if (n.source) srcSet.add(n.source);
      if (n.organ) orgSet.add(n.organ);
    }
    sources.push(...[...srcSet].sort());
    organs.push(...[...orgSet].sort());

    // build link objects (both layers) + adjacency for the detail panel
    const edges = DATA.edges || {};
    linksAll = [];
    for (const lyr of ["molecular", "anatomy"]) {
      for (const e of edges[lyr] || []) {
        if (e.s == null || e.t == null || !nodes[e.s] || !nodes[e.t]) continue;
        const w = e.w || 1;
        const link = { source: e.s, target: e.t, w, shared: e.shared || [], layer: lyr };
        linksAll.push(link);
        pushAdj(e.s, { other: e.t, w, shared: e.shared || [], layer: lyr });
        pushAdj(e.t, { other: e.s, w, shared: e.shared || [], layer: lyr });
      }
    }

    sizeCanvas();
    initColors();
    setupSim();
    renderStats();
    renderCoverage();
    renderLegend();
    wireControls();
    renderDetail();

    // initial fit once the layout has had a few ticks
    setTimeout(() => resetView(true), 400);
  }

  function pushAdj(i, rec) {
    if (!adj.has(i)) adj.set(i, []);
    adj.get(i).push(rec);
  }

  // ---- organ -> color ----
  const organColor = new Map();
  function initColors() {
    organs.forEach((o, i) => organColor.set(o, ORGAN_PALETTE[i % ORGAN_PALETTE.length]));
  }
  function sourceColor(s) {
    if (SRC_COLORS[s]) return SRC_COLORS[s];
    const i = Math.max(0, sources.indexOf(s));
    return FALLBACK_SRC[i % FALLBACK_SRC.length];
  }
  function nodeColor(n) {
    if (colorBy === "organ") return n.organ ? organColor.get(n.organ) : NULL_GREY;
    return sourceColor(n.source);
  }

  // ---- degree in the active layer -> radius ----
  function degreeOf(n) {
    if (layer === "molecular") return n.deg_mol || 0;
    if (layer === "anatomy") return n.deg_anat || 0;
    return (n.deg_mol || 0) + (n.deg_anat || 0);
  }
  const MIN_R = 2.6;
  function radius(n) { return MIN_R + 1.35 * Math.sqrt(degreeOf(n)); }

  // a node is hidden if its source/organ category is filtered off
  function nodeHidden(n) {
    if (hidden.source.has(n.source)) return true;
    if (colorBy === "organ" && hidden.organ.has(n.organ || "\u0000null")) return true;
    return false;
  }
  const edgeActive = (l) => layer === "both" || l.layer === layer;

  // -------------------------------------------------------------------------
  function setupSim() {
    sim = d3.forceSimulation(nodes)
      .force("charge", d3.forceManyBody().strength(-26).distanceMax(360).theta(0.9))
      .force("link", d3.forceLink(linksAll)
        .id((d) => d.index)
        .distance((l) => 26 + 14 / Math.sqrt(l.w))
        .strength((l) => 0.08 + 0.3 * Math.min(1, Math.log1p(l.w) / 6)))
      .force("x", d3.forceX(0).strength(0.035))
      .force("y", d3.forceY(0).strength(0.035))
      .force("collide", d3.forceCollide().radius((d) => radius(d) + 1.5).iterations(1))
      .velocityDecay(0.35)
      .alpha(1).alphaDecay(0.022)
      .on("tick", draw);
  }

  // -------------------------------------------------------------------------
  function sizeCanvas() {
    DPR = Math.min(window.devicePixelRatio || 1, 2);
    const rect = canvas.getBoundingClientRect();
    W = rect.width; H = rect.height;
    canvas.width = Math.round(W * DPR);
    canvas.height = Math.round(H * DPR);
  }

  function draw() {
    if (!ctx) return;
    ctx.save();
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
    ctx.clearRect(0, 0, W, H);
    const t = transform;
    ctx.translate(t.x, t.y);
    ctx.scale(t.k, t.k);

    const searching = searchQ.length > 0;
    const hasSel = !!selected;
    // neighbours of the selected node (active layer) for highlight
    let selNbr = null;
    if (hasSel) {
      selNbr = new Set();
      for (const r of adj.get(selected.index) || []) if (edgeActive(r)) selNbr.add(r.other);
    }

    // ---- edges ----
    const maxW = layer === "anatomy" ? (DATA.stats ? 8 : 8)
      : 1468; // molecular/both can be very large; log-scale caps width
    for (const l of linksAll) {
      if (!edgeActive(l)) continue;
      if (l.w < minW) continue;
      const a = l.source, b = l.target;
      if (nodeHidden(a) || nodeHidden(b)) continue;
      if (a.x == null || b.x == null) continue;
      let alpha = 0.16 + 0.5 * (Math.log1p(l.w) / Math.log1p(maxW));
      let lw = 0.35 + 3.0 * (Math.log1p(l.w) / Math.log1p(maxW));
      // dim non-incident edges when something is selected / searched
      if (hasSel) {
        const inc = a === selected || b === selected;
        alpha = inc ? Math.min(0.95, alpha + 0.35) : alpha * 0.1;
        if (inc) lw = Math.max(lw, 0.9);
      } else if (searching) {
        const inc = matchSet.has(a.index) || matchSet.has(b.index);
        alpha = inc ? alpha : alpha * 0.08;
      }
      ctx.globalAlpha = alpha;
      ctx.strokeStyle = EDGE_COLORS[l.layer] || "#888";
      ctx.lineWidth = lw / t.k;
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      ctx.stroke();
    }
    ctx.globalAlpha = 1;

    // ---- nodes ----
    const minScreenR = 1.6;
    for (const n of nodes) {
      if (n.x == null) continue;
      if (nodeHidden(n)) continue;
      const r = Math.max(radius(n), minScreenR / t.k);
      let alpha = 1;
      if (hasSel) {
        alpha = (n === selected || (selNbr && selNbr.has(n.index))) ? 1 : 0.18;
      } else if (searching) {
        alpha = matchSet.has(n.index) ? 1 : 0.12;
      }
      ctx.globalAlpha = alpha;
      ctx.beginPath();
      ctx.arc(n.x, n.y, r, 0, 2 * Math.PI);
      ctx.fillStyle = nodeColor(n);
      ctx.fill();
      // subtle stroke for legibility
      if (t.k > 0.4) {
        ctx.lineWidth = 0.6 / t.k;
        ctx.strokeStyle = "rgba(0,0,0,.28)";
        ctx.stroke();
      }
    }
    ctx.globalAlpha = 1;

    // highlight rings: search matches + selection
    if (searching) {
      ctx.lineWidth = 2.2 / t.k;
      ctx.strokeStyle = cssVar("--accent") || "#3b6fe0";
      for (const n of nodes) {
        if (!matchSet.has(n.index) || nodeHidden(n) || n.x == null) continue;
        ctx.beginPath();
        ctx.arc(n.x, n.y, Math.max(radius(n), minScreenR / t.k) + 3 / t.k, 0, 2 * Math.PI);
        ctx.stroke();
      }
    }
    if (hasSel && selected.x != null) {
      ctx.lineWidth = 2.6 / t.k;
      ctx.strokeStyle = cssVar("--accent") || "#3b6fe0";
      ctx.beginPath();
      ctx.arc(selected.x, selected.y, radius(selected) + 4 / t.k, 0, 2 * Math.PI);
      ctx.stroke();
    }
    ctx.restore();
  }

  // -------------------------------------------------------------------------
  // pan / zoom
  const zoom = d3.zoom().scaleExtent([0.08, 12]).on("zoom", (ev) => {
    transform = ev.transform;
    draw();
  });
  d3.select(canvas).call(zoom)
    .on("dblclick.zoom", null);

  function resetView(fit) {
    const vis = nodes.filter((n) => n.x != null && !nodeHidden(n));
    if (!vis.length) { d3.select(canvas).call(zoom.transform, d3.zoomIdentity); return; }
    if (fit) {
      let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
      for (const n of vis) { x0 = Math.min(x0, n.x); y0 = Math.min(y0, n.y); x1 = Math.max(x1, n.x); y1 = Math.max(y1, n.y); }
      const pad = 60;
      const k = Math.max(0.08, Math.min(3, 0.9 / Math.max((x1 - x0) / (W - pad), (y1 - y0) / (H - pad))));
      const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
      const tr = d3.zoomIdentity.translate(W / 2 - k * cx, H / 2 - k * cy).scale(k);
      d3.select(canvas).transition().duration(fit === true ? 0 : 500).call(zoom.transform, tr);
    } else {
      d3.select(canvas).call(zoom.transform, d3.zoomIdentity);
    }
  }

  // ---- hit test (screen -> graph coords) ----
  function nodeAt(clientX, clientY) {
    const rect = canvas.getBoundingClientRect();
    const px = clientX - rect.left, py = clientY - rect.top;
    const gx = (px - transform.x) / transform.k;
    const gy = (py - transform.y) / transform.k;
    let best = null, bestD = Infinity;
    for (const n of nodes) {
      if (n.x == null || nodeHidden(n)) continue;
      const rr = Math.max(radius(n), 6 / transform.k) + 3 / transform.k;
      const dx = n.x - gx, dy = n.y - gy, d = dx * dx + dy * dy;
      if (d < rr * rr && d < bestD) { best = n; bestD = d; }
    }
    return best;
  }

  // -------------------------------------------------------------------------
  function renderLegend() {
    const host = $("legend");
    const title = $("legend-title");
    host.innerHTML = "";
    const items = [];
    if (colorBy === "source") {
      title.textContent = "Source · filter";
      for (const s of sources) {
        items.push({ key: s, kind: "source", label: srcLabel(s), color: sourceColor(s),
          count: nodes.filter((n) => n.source === s).length });
      }
    } else {
      title.textContent = "Organ · filter";
      for (const o of organs) {
        items.push({ key: o, kind: "organ", label: o, color: organColor.get(o),
          count: nodes.filter((n) => n.organ === o).length });
      }
      const nNull = nodes.filter((n) => !n.organ).length;
      if (nNull) items.push({ key: "\u0000null", kind: "organ", label: "no organ", color: NULL_GREY, count: nNull });
    }
    items.sort((a, b) => b.count - a.count);
    for (const it of items) {
      const off = hidden[it.kind].has(it.key);
      const el = document.createElement("div");
      el.className = "chip" + (off ? " off" : "");
      el.innerHTML = `<span class="dot" style="background:${it.color}"></span>` +
        `<span class="nm">${esc(it.label)}</span><span class="ct">${it.count}</span>`;
      el.addEventListener("click", () => {
        if (hidden[it.kind].has(it.key)) hidden[it.kind].delete(it.key);
        else hidden[it.kind].add(it.key);
        el.classList.toggle("off");
        if (selected && nodeHidden(selected)) { selected = null; renderDetail(); }
        draw();
      });
      host.appendChild(el);
    }
  }

  // -------------------------------------------------------------------------
  function renderStats() {
    const s = DATA.stats || {};
    const nMol = s.n_edges_molecular ?? (DATA.edges && DATA.edges.molecular ? DATA.edges.molecular.length : 0);
    const nAnat = s.n_edges_anatomy ?? (DATA.edges && DATA.edges.anatomy ? DATA.edges.anatomy.length : 0);
    const frac = s.largest_component_frac != null ? Math.round(s.largest_component_frac * 100) + "%" : "—";
    const cells = [
      ["Models", (s.n_nodes ?? nodes.length).toLocaleString()],
      ["Components", (s.n_components ?? "—").toLocaleString()],
      ["Molecular edges", nMol.toLocaleString()],
      ["Anatomy edges", nAnat.toLocaleString()],
      ["Largest component", (s.largest_component ?? "—").toLocaleString()],
      ["— of network", frac],
    ];
    let html = '<div class="stat-grid">';
    for (const [k, v] of cells) html += `<div class="stat"><div class="v">${esc(v)}</div><div class="k">${esc(k)}</div></div>`;
    html += "</div>";
    $("hdr-stat").textContent =
      `${(s.n_nodes ?? nodes.length).toLocaleString()} models · ${nMol.toLocaleString()} mol / ${nAnat.toLocaleString()} anat edges`;

    const hubs = s.molecular_hubs || [];
    if (hubs.length) {
      html += '<div class="hubs"><div class="edges-h" style="margin:14px 0 6px">Top molecular hub variables</div>';
      for (const h of hubs.slice(0, 8)) {
        html += `<div class="hub-row"><span class="hv" title="${esc(h.variable)}">${esc(prettyVar(h.variable))}</span>` +
          `<span class="hn">${esc((h.n_models || 0).toLocaleString())} models</span></div>`;
      }
      html += "</div>";
    }
    $("stats").innerHTML = html;
  }

  function renderCoverage() {
    const cov = DATA.coverage || {};
    let html = "";
    for (const lyr of ["molecular", "anatomy"]) {
      const group = cov[lyr];
      if (!group) continue;
      html += `<div class="edges-h" style="margin:2px 0 8px;color:${EDGE_COLORS[lyr]}">${lyr} variables</div>`;
      const nss = Object.keys(group).sort((a, b) => (group[b].n_models || 0) - (group[a].n_models || 0));
      for (const ns of nss) {
        const c = group[ns] || {};
        html += `<div class="cov-ns"><div class="cov-head"><b>${esc(nsLabel(ns))}</b>` +
          `<span class="cov-n">${(c.n_models || 0).toLocaleString()} models · ${(c.n_distinct || 0).toLocaleString()} distinct</span></div>`;
        const top = (c.top || []).slice(0, 5);
        if (top.length) {
          html += '<div class="cov-top">';
          for (const [id, cnt] of top) {
            html += `<span class="var-tag" title="${esc(id)}">${esc(prettyVar(ns + ":" + id))} · ${cnt}</span>`;
          }
          html += "</div>";
        }
        html += "</div>";
      }
    }
    $("coverage").innerHTML = html || '<div class="detail-empty">No coverage data.</div>';
  }

  // -------------------------------------------------------------------------
  function renderDetail() {
    const host = $("detail");
    if (!selected) {
      host.innerHTML = '<div class="detail-empty">Click a node to inspect a model and how it connects to its neighbours.</div>';
      return;
    }
    const n = selected;
    const col = nodeColor(n);
    let html = `<div class="d-title">${esc(n.label || n.id)}</div>`;
    html += '<div class="d-badges">';
    html += `<span class="badge" style="background:${sourceColor(n.source)}22;color:${sourceColor(n.source)};border-color:${sourceColor(n.source)}55">${esc(srcLabel(n.source))}</span>`;
    if (n.organ) {
      const oc = organColor.get(n.organ) || NULL_GREY;
      html += `<span class="badge" style="background:${oc}22;color:${oc};border-color:${oc}55">${esc(n.organ)}</span>`;
    } else {
      html += `<span class="badge" style="background:${NULL_GREY}22;color:${NULL_GREY};border-color:${NULL_GREY}55">no organ</span>`;
    }
    html += "</div>";
    html += '<dl class="d-grid">' +
      `<dt>Molecular degree</dt><dd>${(n.deg_mol || 0).toLocaleString()}</dd>` +
      `<dt>Anatomy degree</dt><dd>${(n.deg_anat || 0).toLocaleString()}</dd>` +
      `<dt>Molecular vars</dt><dd>${(n.n_mol || 0).toLocaleString()}</dd>` +
      `<dt>Anatomy vars</dt><dd>${(n.n_anat || 0).toLocaleString()}</dd>` +
      `<dt>Component</dt><dd>#${(n.component ?? "—")}</dd>` +
      "</dl>";
    if (n.url) {
      html += `<a class="d-link" href="${esc(n.url)}" target="_blank" rel="noopener">Open model source ↗</a>`;
    }

    // strongest edges in the active layer(s)
    let recs = (adj.get(n.index) || []).filter(edgeActive).slice();
    recs.sort((a, b) => b.w - a.w);
    const top = recs.slice(0, 6);
    html += `<div class="edges-h">Strongest connections${layer === "both" ? "" : " · " + layer}</div>`;
    if (!top.length) {
      html += '<div class="detail-empty">No connections in this layer.</div>';
    } else {
      for (const r of top) {
        const other = nodes[r.other];
        const dotc = EDGE_COLORS[r.layer];
        html += '<div class="edge-row"><div class="er-top">' +
          `<span class="er-name" data-go="${other.index}" title="${esc(other.label || other.id)}">${esc(other.label || other.id)}</span>` +
          `<span class="er-w" style="background:${dotc}">${r.w} shared</span></div>`;
        const vars = (r.shared || []).slice(0, 6);
        if (vars.length) {
          html += '<div class="er-shared">';
          for (const v of vars) html += `<span class="var-tag" title="${esc(v)}">${esc(prettyVar(v))}</span>`;
          if ((r.shared || []).length > vars.length) html += `<span class="var-tag">+${r.shared.length - vars.length}</span>`;
          html += "</div>";
        }
        html += "</div>";
      }
    }
    host.innerHTML = html;
    host.querySelectorAll(".er-name[data-go]").forEach((el) => {
      el.addEventListener("click", () => {
        const idx = +el.getAttribute("data-go");
        selectNode(nodes[idx], true);
      });
    });
  }

  function selectNode(n, center) {
    selected = n;
    renderDetail();
    draw();
    if (center && n && n.x != null) centerOn([n]);
    if (window.innerWidth <= 760) document.body.classList.add("show-sidebar");
  }

  function centerOn(ns) {
    const pts = ns.filter((n) => n.x != null);
    if (!pts.length) return;
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (const n of pts) { x0 = Math.min(x0, n.x); y0 = Math.min(y0, n.y); x1 = Math.max(x1, n.x); y1 = Math.max(y1, n.y); }
    const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
    const span = Math.max(x1 - x0, y1 - y0, 40);
    const k = pts.length === 1 ? Math.min(2.2, transform.k < 1 ? 1.6 : transform.k)
      : Math.max(0.1, Math.min(2.5, 0.8 * Math.min(W, H) / span));
    const tr = d3.zoomIdentity.translate(W / 2 - k * cx, H / 2 - k * cy).scale(k);
    d3.select(canvas).transition().duration(550).call(zoom.transform, tr);
  }

  // -------------------------------------------------------------------------
  function runSearch(q) {
    searchQ = (q || "").trim().toLowerCase();
    matchSet = new Set();
    const info = $("search-info");
    if (!searchQ) { info.style.display = "none"; draw(); return; }
    const hits = [];
    for (const n of nodes) {
      if (nodeHidden(n)) continue;
      if ((n.label || "").toLowerCase().includes(searchQ) || (n.id || "").toLowerCase().includes(searchQ)) {
        matchSet.add(n.index); hits.push(n);
      }
    }
    info.style.display = "";
    info.textContent = hits.length
      ? `${hits.length} match${hits.length === 1 ? "" : "es"} — highlighted` + (hits.length === 1 ? ", centred" : "")
      : "no models match";
    draw();
    if (hits.length) centerOn(hits.slice(0, 60));
  }

  // -------------------------------------------------------------------------
  function wireControls() {
    // layer segmented toggle
    $("seg-layer").addEventListener("click", (e) => {
      const b = e.target.closest("button[data-layer]");
      if (!b) return;
      layer = b.dataset.layer;
      [...e.currentTarget.children].forEach((c) => c.classList.toggle("active", c === b));
      reheat(0.25);
      renderDetail();
      draw();
    });
    // color-by segmented toggle
    $("seg-color").addEventListener("click", (e) => {
      const b = e.target.closest("button[data-color]");
      if (!b) return;
      colorBy = b.dataset.color;
      [...e.currentTarget.children].forEach((c) => c.classList.toggle("active", c === b));
      renderLegend();
      renderDetail();
      draw();
    });
    // min edge weight slider — range from the data
    const maxWObserved = Math.max(1, ...linksAll.map((l) => l.w));
    const slider = $("minw");
    slider.max = String(Math.min(maxWObserved, 200));
    slider.addEventListener("input", () => {
      minW = +slider.value;
      $("minw-val").textContent = minW;
      draw();
    });
    // search
    let st;
    $("search").addEventListener("input", (e) => {
      clearTimeout(st);
      const v = e.target.value;
      st = setTimeout(() => runSearch(v), 120);
    });
    // buttons
    $("btn-reset").addEventListener("click", () => resetView("anim"));
    const freezeBtn = $("btn-freeze");
    freezeBtn.addEventListener("click", () => {
      frozen = !frozen;
      if (frozen) { sim.stop(); freezeBtn.textContent = "Resume"; }
      else { freezeBtn.textContent = "Freeze"; sim.alpha(0.3).restart(); }
    });
    // collapsible sidebar sections
    document.querySelectorAll("[data-collapse]").forEach((h) => {
      h.addEventListener("click", () => h.closest(".sec").classList.toggle("collapsed"));
    });
    // mobile panel toggles
    $("toggle-controls").addEventListener("click", () => {
      document.body.classList.toggle("show-controls");
      document.body.classList.remove("show-sidebar");
    });
    $("toggle-sidebar").addEventListener("click", () => {
      document.body.classList.toggle("show-sidebar");
      document.body.classList.remove("show-controls");
    });

    // canvas interaction: hover tooltip + click select + drag nodes
    const tooltip = $("tooltip");
    canvas.addEventListener("pointermove", (e) => {
      if (dragging) return;
      const n = nodeAt(e.clientX, e.clientY);
      if (!n) { tooltip.style.display = "none"; canvas.style.cursor = ""; return; }
      canvas.style.cursor = "pointer";
      tooltip.style.display = "block";
      tooltip.innerHTML = `<div class="tt-name">${esc(n.label || n.id)}</div>` +
        `<div class="tt-meta">${esc(srcLabel(n.source))}${n.organ ? " · " + esc(n.organ) : " · no organ"}` +
        ` · mol ${n.deg_mol || 0} / anat ${n.deg_anat || 0}</div>`;
      const pad = 14;
      let x = e.clientX + pad, y = e.clientY + pad;
      const tw = tooltip.offsetWidth, th = tooltip.offsetHeight;
      if (x + tw > window.innerWidth - 8) x = e.clientX - tw - pad;
      if (y + th > window.innerHeight - 8) y = e.clientY - th - pad;
      tooltip.style.left = x + "px";
      tooltip.style.top = y + "px";
    });
    canvas.addEventListener("pointerleave", () => { tooltip.style.display = "none"; });

    // node dragging (so a user can pull nodes around); falls back to pan via zoom
    let dragging = null, dragMoved = false;
    canvas.addEventListener("pointerdown", (e) => {
      const n = nodeAt(e.clientX, e.clientY);
      if (!n) return;               // let d3-zoom handle panning
      dragging = n; dragMoved = false;
      canvas.classList.add("grabbing");
      if (!frozen) sim.alphaTarget(0.2).restart();
      n.fx = n.x; n.fy = n.y;
      e.stopPropagation();
    }, true);
    window.addEventListener("pointermove", (e) => {
      if (!dragging) return;
      dragMoved = true;
      const rect = canvas.getBoundingClientRect();
      dragging.fx = (e.clientX - rect.left - transform.x) / transform.k;
      dragging.fy = (e.clientY - rect.top - transform.y) / transform.k;
      if (frozen) draw();
    });
    window.addEventListener("pointerup", (e) => {
      if (!dragging) return;
      const n = dragging;
      canvas.classList.remove("grabbing");
      if (!frozen) sim.alphaTarget(0);
      n.fx = null; n.fy = null;
      if (!dragMoved) selectNode(n, false);  // a click (no drag) selects
      dragging = null;
    });
    // plain click on empty space clears selection
    canvas.addEventListener("click", (e) => {
      const n = nodeAt(e.clientX, e.clientY);
      if (!n && selected) { selected = null; renderDetail(); draw(); }
    });

    window.addEventListener("resize", () => { sizeCanvas(); draw(); });
    window.addEventListener("keydown", (e) => {
      if (/input|textarea/i.test(e.target.tagName)) return;
      if (e.key === "Escape") { selected = null; renderDetail(); $("search").value = ""; runSearch(""); draw(); }
      if (e.key === "r") resetView("anim");
    });
  }

  function reheat(a) {
    if (frozen || !sim) return;
    sim.force("collide").radius((d) => radius(d) + 1.5);
    sim.alpha(a).restart();
  }

  // -------------------------------------------------------------------------
  if (typeof d3 === "undefined") {
    showError("Could not load d3", "The d3 v7 library failed to load from the CDN. Check your network connection.");
  } else {
    main();
  }
})();
