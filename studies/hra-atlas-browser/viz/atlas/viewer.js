// HRA Computational Model Atlas — self-contained three.js multi-organ browser.
//
// Reads config.json -> {atlas, coverage, ...}, then atlas.json (all 50
// GLB-backed HRA organs + model counts + BioModels links). No build step; no
// query params.
//
// Interaction (parsimony-style): a left menu lists every organ. You can
//   - click a row to ADD/REMOVE that organ from the composed scene
//     ("click through and add them through selection"),
//   - click the row's "only" button to isolate that one organ,
//   - "All modeled" to compose all organs that have >=1 model, "None" to clear.
// The individual HRA reference-organ GLBs share one body coordinate space, so
// selected organs assemble into an anatomically-correct scene, each colored by
// its model count. Clicking an organ (row or 3D mesh) shows its BioModels in
// the right panel, each linking to https://www.ebi.ac.uk/biomodels/<id>.
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

const NOMODEL = 0x5a616b;

const els = {
  status: document.getElementById("status"),
  summary: document.getElementById("summary-line"),
  list: document.getElementById("organ-list"),
  search: document.getElementById("organ-search"),
  btnAllModeled: document.getElementById("btn-all-modeled"),
  btnAll: document.getElementById("btn-all"),
  btnCollapseAll: document.getElementById("btn-collapse-all"),
  btnExpandAll: document.getElementById("btn-expand-all"),
  btnCenter: document.getElementById("btn-center"),
  btnDownload: document.getElementById("btn-download"),
  sexFemale: document.getElementById("sex-female"),
  sexMale: document.getElementById("sex-male"),
  modelSearch: document.getElementById("model-search"),
  selCount: document.getElementById("sel-count"),
  legendMax: document.getElementById("legend-max"),
  bpTitle: document.getElementById("bp-title"),
  bpSub: document.getElementById("bp-sub"),
  bpList: document.getElementById("biomodels-list"),
  sourceChips: document.getElementById("source-chips"),
  organMenu: document.getElementById("organ-menu"),
  biomodelsPanel: document.getElementById("biomodels-panel"),
  collapseLeft: document.getElementById("collapse-left"),
  collapseRight: document.getElementById("collapse-right"),
  reopenLeft: document.getElementById("reopen-left"),
  reopenRight: document.getElementById("reopen-right"),
  resizeLeft: document.getElementById("resize-left"),
  resizeRight: document.getElementById("resize-right"),
};
const setStatus = (t) => { if (els.status) els.status.textContent = t; };

// Escape untrusted text before it is interpolated into an innerHTML template
// literal. Model `name` (PhysioNet titles come from external DataCite
// metadata), `source_id`, and `repository` all flow into innerHTML below and
// must never be trusted as markup.
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => (
  { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
));

// --- model sources (general-purpose) ---------------------------------------
// Every `repository` present in the atlas becomes a toggleable source. All are
// active by default, so the model lists are COMBINED across sources unless the
// user narrows them. Nothing here is hardcoded to biomodels/physionet — a new
// source in the data appears as a chip automatically. Defined at module scope
// so both the top-level renderers and the ones inside main() can share it.
const ACTIVE_SOURCES = new Set();     // repositories currently shown
let ALL_SOURCES = [];                 // every repository present, sorted
const SOURCE_LABELS = { biomodels: "BioModels", physionet: "PhysioNet", physiome: "Physiome" };
const SOURCE_DOTS = { biomodels: "#4c92ff", physionet: "#ff8a4c", physiome: "#7bd88f" };
const FALLBACK_DOTS = ["#4c92ff", "#ff8a4c", "#7bd88f", "#e0a0ff", "#ffd166", "#5ad1c9"];
const sourceLabel = (r) => SOURCE_LABELS[r] || (r ? r[0].toUpperCase() + r.slice(1) : "Other");
function sourceColor(r) {
  if (SOURCE_DOTS[r]) return SOURCE_DOTS[r];
  const i = Math.max(0, ALL_SOURCES.indexOf(r));
  return FALLBACK_DOTS[i % FALLBACK_DOTS.length];
}
function initSources(atlas) {
  const seen = new Set();
  for (const o of atlas.organs) {
    for (const m of o.models || []) if (m.repository) seen.add(m.repository);
    for (const s of o.subregions || []) for (const m of s.models || []) if (m.repository) seen.add(m.repository);
  }
  ALL_SOURCES = [...seen].sort();
  ACTIVE_SOURCES.clear();
  ALL_SOURCES.forEach((r) => ACTIVE_SOURCES.add(r));
}
// Keep only models whose source is active (all active => list unchanged).
const filterBySource = (models) => (models || []).filter((m) => ACTIVE_SOURCES.has(m.repository));
// Per-source DISTINCT counts (dedup by source_id) — the honest count when a
// model list spans several organs (the same model placed on N organs must count
// once, not N times). Used by the chips. Always distinct: there is deliberately
// no occurrence-based counter, so a cross-organ view can't accidentally inflate.
function distinctSourceCounts(models) {
  const seen = {};
  for (const m of models || []) (seen[m.repository] ||= new Set()).add(m.source_id);
  const c = {};
  for (const r in seen) c[r] = seen[r].size;
  return c;
}
// Human-readable distinct-per-source breakdown, e.g. "78 BioModels · 15 PhysioNet".
function distinctBreakdown(models) {
  const seen = {};
  for (const m of models || []) (seen[m.repository] ||= new Set()).add(m.source_id);
  return ALL_SOURCES.filter((r) => seen[r] && seen[r].size)
    .map((r) => `${seen[r].size} ${sourceLabel(r)}`).join(" · ");
}
// Model counts restricted to the active source chips. With all sources active
// (the default) these equal the organ's/subregion's full totals, so default
// coloring is unchanged; narrowing the chips shrinks the counts that drive the
// 3D coloring, the menu counts, and the color ramp.
// Distinct model count of a list (dedup by repository:source_id).
const distinctCount = (models) =>
  new Set((models || []).map((m) => m.repository + ":" + m.source_id)).size;
const activeCount = (organ) => filterBySource(organ && organ.models).length;
// A subregion's models are (mostly) a SUBSET of the organ's own list, not
// additional — so its count is the DISTINCT union of organ + localized models,
// never their sum (which would double-count and disagree with the rendered
// rows). With all sources this equals the organ count unless the subregion
// carries a model the organ list lacks.
const activeSubCount = (organ, sub) =>
  distinctCount([...filterBySource(organ && organ.models), ...filterBySource(sub && sub.models)]);

// Assigned by main() to re-render whatever the panel currently shows AND recolor
// the 3D scene + menu after a source toggle (so a chip click drives everything).
let onSourcesChanged = () => {};
// Render the source toggle chips (with per-source counts for THIS model set)
// into the panel head. Clicking a chip narrows/combines the list; all-on is the
// default and turning the last one off snaps back to all (never an empty view).
function renderSourceChips(models) {
  const host = els.sourceChips;
  if (!host) return;
  host.innerHTML = "";
  if (ALL_SOURCES.length < 2) return;   // single source: no chooser needed
  const c = distinctSourceCounts(models);
  for (const r of ALL_SOURCES) {
    const active = ACTIVE_SOURCES.has(r);
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "chip" + (active ? "" : " off");
    chip.setAttribute("aria-pressed", active ? "true" : "false");
    chip.innerHTML = `<span class="dot" style="background:${sourceColor(r)}"></span>`
      + `${esc(sourceLabel(r))} <span class="cnt">${c[r] || 0}</span>`;
    chip.addEventListener("click", () => {
      if (ACTIVE_SOURCES.has(r)) ACTIVE_SOURCES.delete(r); else ACTIVE_SOURCES.add(r);
      if (ACTIVE_SOURCES.size === 0) ALL_SOURCES.forEach((s) => ACTIVE_SOURCES.add(s));
      onSourcesChanged();
    });
    host.appendChild(chip);
  }
}

// ColorBrewer YlGnBu (9-class sequential) — a perceptually-ordered
// light-yellow (few) -> green -> teal -> dark-blue (many) ramp, the standard
// sequential scheme for a single magnitude. Distinct in hue from the warm
// subregion ramp, and n==0 (no model) is a neutral grey, off the ramp entirely.
// https://colorbrewer2.org/#type=sequential&scheme=YlGnBu
const YLGNBU = [
  [255, 255, 217], [237, 248, 177], [199, 233, 180], [127, 205, 187],
  [65, 182, 196], [29, 145, 192], [34, 94, 168], [37, 52, 148], [8, 29, 88],
];
function ylGnBu(t) {
  t = Math.max(0, Math.min(1, t));
  const x = t * (YLGNBU.length - 1);
  const i = Math.floor(x), f = x - i;
  const a = YLGNBU[i], b = YLGNBU[Math.min(i + 1, YLGNBU.length - 1)];
  return new THREE.Color(
    (a[0] + (b[0] - a[0]) * f) / 255,
    (a[1] + (b[1] - a[1]) * f) / 255,
    (a[2] + (b[2] - a[2]) * f) / 255,
  );
}
// Log scale so the low-count majority (1..9) still spreads across the ramp
// instead of bunching at one end while blood (51) dominates.
function countColor(n, max) {
  if (!n) return new THREE.Color(NOMODEL);
  const t = max > 1 ? Math.log1p(n) / Math.log1p(max) : 1;
  return ylGnBu(t);
}
const cssColor = (n, max) => "#" + countColor(n, max).getHexString();

// A modeled subregion is colored on the SAME YlGnBu ramp as everything else,
// by its COMBINED count — the organ's whole-organ models PLUS the models
// localized to that structure — so it reads as a darker shade of the same
// scheme than the rest of its organ (see `subregionCount`), not a different hue.
// Normalize a GLB scene-node name for matching against a subregion's
// crosswalk node_names (exporters vary punctuation/case).
const normNode = (s) => (s || "").toLowerCase().replace(/[^a-z0-9]/g, "");

// A subregion's displayed model count = the DISTINCT union of the organ's
// whole-organ models and the models placed at this structure (the structure's
// models are largely a subset of the organ's, so this is NOT a sum).
const subregionCount = (organ, sub) =>
  distinctCount([...(organ.models || []), ...(sub && sub.models || [])]);

// Small badge showing how a model was mapped to the organ + how much to trust it
// (annotation=high, category=medium, keyword=medium). Absent for sources that
// don't record it (e.g. legacy BioModels rows).
const confBadge = (m) => m.confidence
  ? `<span class="conf-badge conf-${esc(m.confidence)}" title="mapped via ${esc(m.mapping_method || "?")} — ${esc(m.confidence)} confidence">${esc(m.confidence)}</span>`
  : "";

// One model rendered as a link row — the single shared builder for the organ
// panel AND the subregion panel (handles both the organ `matched_by` badge and
// the subregion `via` = FTU/cell-type placement badge).
function modelLinkEl(m) {
  const a = document.createElement("a");
  a.href = m.url;
  a.target = "_blank";
  a.rel = "noopener";
  const by = m.matched_by || [];
  let badge = by.length
    ? `<span class="prov prov-${by.length === 2 ? "both" : by[0]}">${
        by.length === 2 ? "name+annotation" : by[0]}</span>`
    : "";
  if (!badge && m.via) {
    badge = `<span class="prov prov-${m.via === "ftu" ? "annotation" : "name"}">${
      m.via === "ftu" ? "FTU" : "cell type"}</span>`;
  }
  const srcBadge = `<span class="src-badge src-${esc(m.repository)}">${esc(m.repository)}</span>`;
  a.innerHTML = `<div>${esc(m.name || m.source_id)} ${srcBadge} ${confBadge(m)} ${badge}</div><div class="mid">${esc(m.source_id)}</div>`;
  return a;
}

// Group models by physiological process -> [{process, models}], biggest first,
// "Other" last. Realizes the anatomical structure -> process -> model unit.
function groupByProcess(models) {
  const groups = new Map();
  for (const m of models || []) {
    const p = m.process || "Other";
    if (!groups.has(p)) groups.set(p, []);
    groups.get(p).push(m);
  }
  return [...groups.entries()]
    .map(([process, ms]) => ({ process, models: ms }))
    .sort((a, b) => (a.process === "Other") - (b.process === "Other")
      || b.models.length - a.models.length
      || a.process.localeCompare(b.process));
}

// Expand-all / collapse-all controls for every process group in `container`.
function appendProcessControls(container) {
  const bar = document.createElement("div");
  bar.className = "proc-controls";
  bar.innerHTML = `<button type="button" class="proc-ctl" data-act="expand">Expand all</button>`
    + `<button type="button" class="proc-ctl" data-act="collapse">Collapse all</button>`;
  bar.addEventListener("click", (e) => {
    const act = e.target && e.target.dataset ? e.target.dataset.act : null;
    if (!act) return;
    const collapse = act === "collapse";
    container.querySelectorAll(".proc-body").forEach((b) => b.classList.toggle("collapsed", collapse));
    container.querySelectorAll(".proc-group .proc-caret").forEach((c) => {
      c.textContent = collapse ? "▸" : "▾";
    });
  });
  container.appendChild(bar);
}

// Append collapsible process groups for `models` into `container`. Groups start
// COLLAPSED (the panel opens as a compact process index; click a header or use
// the Expand-all control to drill in).
function appendProcessGroups(container, models) {
  for (const g of groupByProcess(models)) {
    const header = document.createElement("div");
    header.className = "proc-group";
    header.innerHTML = `<span class="proc-caret">▸</span>`
      + `<span class="proc-name">${esc(g.process)}</span>`
      + `<span class="proc-count">${g.models.length}</span>`;
    const body = document.createElement("div");
    body.className = "proc-body collapsed";
    for (const m of g.models) body.appendChild(modelLinkEl(m));
    header.addEventListener("click", () => {
      const collapsed = body.classList.toggle("collapsed");
      header.querySelector(".proc-caret").textContent = collapsed ? "▸" : "▾";
    });
    container.appendChild(header);
    container.appendChild(body);
  }
}

function renderBioModels(organ) {
  els.bpTitle.textContent = organ.label;
  const nTotal = organ.models.length;
  const breakdown = distinctBreakdown(organ.models);
  els.bpSub.textContent = nTotal
    ? `${nTotal} model${nTotal > 1 ? "s" : ""}` + (breakdown ? ` (${breakdown})` : "")
      + ` · ${organ.uberon || ""}`
    : `no models · ${organ.uberon || ""}`;
  renderSourceChips(organ.models);
  els.bpList.innerHTML = "";
  if (!organ.models.length) {
    const d = document.createElement("div");
    d.className = "empty";
    d.textContent = "No mechanistic models associated with this organ.";
    els.bpList.appendChild(d);
    return;
  }
  const shown = filterBySource(organ.models);
  if (!shown.length) {
    const d = document.createElement("div");
    d.className = "empty";
    d.textContent = "No models match the current source filter.";
    els.bpList.appendChild(d);
    return;
  }
  // Group the organ's models by physiological process (ion transport,
  // metabolism, …) rather than one flat list — the process is the unit.
  appendProcessControls(els.bpList);
  appendProcessGroups(els.bpList, shown);
}

async function main() {
  setStatus("loading config…");
  const cfg = await fetch("config.json").then((r) => r.json());
  const atlas = await fetch(cfg.atlas).then((r) => r.json());
  initSources(atlas);   // discover every repository present -> toggleable sources
  const organsByKey = new Map(atlas.organs.map((o) => [o.key, o]));
  // Per-organ subregion lookup: organ key -> Map(normalized node_name ->
  // subregion). Lets `colorMesh` decide, per GLB mesh, whether it's a modeled
  // anatomical structure (darker, by its combined count) or organ base.
  const subIndexByKey = new Map();
  for (const o of atlas.organs) {
    const idx = new Map();
    for (const s of o.subregions || []) {
      for (const nn of s.node_names || []) idx.set(normNode(nn), s);
    }
    subIndexByKey.set(o.key, idx);
  }
  // Color scale max includes subregion combined totals (organ + localized),
  // which can exceed any organ's whole-organ count, so the ramp stays accurate.
  const maxCount = Math.max(
    atlas.max_models || 1,
    ...atlas.organs.flatMap((o) => (o.subregions || []).map((s) => subregionCount(o, s))),
  );
  // ---- sex mode (B2) ----
  // Composed views must not overlay both sexes of the same structure (that
  // renders "double legs" — male knee bones poking through the female skin).
  // Instead of collapsing variants, the browser shows ONE sex's anatomy at a
  // time; the Female|Male toggle rebuilds the scene for the chosen sex.
  let sex = "female";
  // Current sex's GLBs for an organ, falling back to the other sex so organs
  // that ship only one side's asset (e.g. prostate) still render.
  function glbsForSex(o) {
    const other = sex === "female" ? "male" : "female";
    return (o.glbs?.[sex]?.length ? o.glbs[sex] : (o.glbs?.[other] || []));
  }
  // Show an organ only in its own sex's view: the manifest's `sex` field
  // ("female"/"male"/"both") covers both key-suffixed variants (ovary-female-*)
  // AND biologically sex-specific organs with plain keys (placenta, uterus,
  // prostate). Falls back to key inference for older manifests without `sex`.
  function visibleForSex(o) {
    const s = o.sex || (/-male/.test(o.key) ? "male" : /-female/.test(o.key) ? "female" : "both");
    return s === "both" || s === sex;
  }
  // Organs kept OUT of the default composed view because they occlude the
  // organs inside them — the whole-body skin, and the placenta. They stay in the
  // menu (clickable to toggle on) and are included by the "All" button; they're
  // just not in the landing / "All modeled" set.
  const OCCLUDING = new Set(["skin", "placenta-full-term"]);
  // Bumped on every sex switch; in-flight GLB loads started under an old value
  // are discarded when they resolve so a stale sex's body can't enter the scene.
  let loadGen = 0;
  // Recomputed for the current sex: keys of the organs the menu/landing use.
  let allKeys = [], modeledKeys = [];
  function recomputeKeys() {
    const vis = atlas.organs.filter(visibleForSex);
    allKeys = vis.map((o) => o.key);                 // "All" — includes occluding
    modeledKeys = vis.filter((o) => o.n_models > 0 && !OCCLUDING.has(o.key))
      .map((o) => o.key);                             // landing / "All modeled"
  }
  recomputeKeys();
  // distinct models (source-filter aware) represented by a set of organ keys
  // (union of ids, across both BioModels and PhysioNet)
  function distinctModels(keys) {
    const ids = new Set();
    for (const k of keys) {
      const o = organsByKey.get(k);
      if (o) for (const m of filterBySource(o.models)) ids.add(m.repository + ":" + m.source_id);
    }
    return ids.size;
  }
  // system -> organs (in the atlas' n_models-desc order), following the
  // manifest's `systems` display order.
  const systemsList = atlas.systems || [...new Set(atlas.organs.map((o) => o.system))];
  const organsBySystem = new Map(systemsList.map((s) => [s, []]));
  for (const o of atlas.organs) {
    if (!organsBySystem.has(o.system)) organsBySystem.set(o.system, []);
    organsBySystem.get(o.system).push(o);
  }
  els.legendMax.textContent = String(atlas.max_models);
  // Combined distinct total across every source, computed from the data (union
  // of repository:source_id), with a per-source breakdown — not a single-source
  // summary field. General-purpose: reflects whatever sources are present.
  const allModels = atlas.organs.flatMap((o) => o.models || []);
  const distinctTotal = new Set(allModels.map((m) => m.repository + ":" + m.source_id)).size;
  const headBreak = distinctBreakdown(allModels);
  const nSub = atlas.summary.n_subregions || 0;
  els.summary.textContent =
    `${atlas.summary.n_modeled}/${atlas.summary.n_organs} organs modeled · ${distinctTotal} distinct models`
    + (headBreak ? ` (${headBreak})` : "")
    + (nSub ? ` · ${nSub} modeled subregion${nSub === 1 ? "" : "s"} in ${atlas.summary.n_organs_with_subregions} organ${atlas.summary.n_organs_with_subregions === 1 ? "" : "s"}` : "");

  // ---- scene ----
  const app = document.getElementById("app");
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0e1116);
  const camera = new THREE.PerspectiveCamera(45, innerWidth / innerHeight, 0.001, 100);
  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(devicePixelRatio || 1);
  renderer.setSize(innerWidth, innerHeight);
  app.appendChild(renderer.domElement);
  scene.add(new THREE.AmbientLight(0xffffff, 0.7));
  const dir = new THREE.DirectionalLight(0xffffff, 0.8);
  dir.position.set(3, 5, 4);
  scene.add(dir);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  const loader = new GLTFLoader();

  // ---- selection state ----
  const selected = new Set();          // organ keys currently in the scene
  const groups = new Map();            // organ key -> THREE.Group (cached GLB)
  const loading = new Map();           // organ key -> in-flight Promise<Group>
  let focused = null;                  // organ key shown in the BioModels panel
  const rows = new Map();              // organ key -> menu row element
  const groupChecks = new Map();       // system -> header checkbox element
  const raycastMeshes = [];            // meshes across all *shown* organs
  let hovered = null;
  let modelQuery = "";                 // active model-search keyword (lowercased)
  // Re-render for the CURRENT panel view, reassigned by focus / subregion /
  // reset so a source-chip toggle refreshes exactly what's shown, in place.
  let rerenderPanel = () => resetPanel();
  // A source-chip toggle drives the whole view: re-render the panel, recolor the
  // 3D scene (organs filtered out dim / go grey), and update the menu counts.
  // Recolor + refresh counts BEFORE re-rendering the panel, so a chip toggle
  // during an active search repaints swatches with the fresh match scale.
  onSourcesChanged = () => { recolorShown(); refreshMenuCounts(); rerenderPanel(); };
  // ---- explode (B4) ----
  let explodeAnim = null;              // {meshes:[{mesh,from,to}], start, dur}
  let explodedKey = null;              // organ key currently in exploded state

  // Models in an organ whose name or source id contains the search keyword,
  // honoring the active source filter.
  function matchingModels(organ, q) {
    if (!q) return [];
    return filterBySource(organ.models).filter(
      (m) => (m.name + " " + m.source_id).toLowerCase().includes(q));
  }
  // Color for one shown organ under the current search: no search -> the normal
  // model-count color; searching -> scaled by how many of its models MATCH
  // (so the selected organs light up where the keyword is represented), and
  // organs with no match dim out.
  function organColorSpec(organ) {
    if (!modelQuery) {
      const n = activeCount(organ);
      // Organ has models but the active source chips exclude them all -> dim it
      // out (reads as "filtered away"); a genuinely model-less organ keeps its
      // normal grey at full opacity.
      if (!n) return { color: new THREE.Color(NOMODEL), opacity: organ.n_models ? 0.18 : 1 };
      return { color: countColor(n, maxCount), opacity: 1 };
    }
    const n = matchingModels(organ, modelQuery).length;
    if (!n) return { color: new THREE.Color(NOMODEL), opacity: 0.18 };
    const maxMatch = searchMaxMatch || 1;
    return { color: countColor(n, maxMatch), opacity: 1 };
  }
  let searchMaxMatch = 0;
  // Update the left menu rows' swatch + count to the active-source counts, in
  // place (no rebuild, so scroll/collapse state survives a source-chip toggle).
  function refreshMenuCounts() {
    for (const [key, row] of rows) {
      const o = organsByKey.get(key);
      if (!o) continue;
      const n = activeCount(o);
      const sw = row.querySelector(".sw");
      const ct = row.querySelector(".ct");
      if (sw) sw.style.background = cssColor(n, maxCount);
      if (ct) ct.textContent = n || "";
      row.classList.toggle("zero", !n);
    }
  }

  // Recolor every currently-shown organ group per organColorSpec.
  function recolorShown() {
    searchMaxMatch = 0;
    if (modelQuery) {
      for (const k of selected) {
        const o = organsByKey.get(k);
        if (o) searchMaxMatch = Math.max(searchMaxMatch, matchingModels(o, modelQuery).length);
      }
    }
    for (const k of selected) {
      const g = groups.get(k), o = organsByKey.get(k);
      if (!g || !o) continue;
      if (!modelQuery) { colorOrganGroup(k); continue; }  // subregion-aware base
      const spec = organColorSpec(o);
      g.traverse((n) => {
        if (!n.isMesh || !n.material || n.material.isLineBasicMaterial) return;
        n.material.color.copy(spec.color);
        n.material.transparent = spec.opacity < 1;
        n.material.opacity = spec.opacity;
      });
    }
    // Legend tracks what the colors mean now: matches-per-organ while searching,
    // else total models-per-organ.
    els.legendMax.textContent = String(modelQuery ? (searchMaxMatch || 0) : atlas.max_models);
  }

  // Color ONE mesh: if its node name matches a modeled subregion, warm ramp by
  // the subregion's own model count (and tag userData.sub for hover/click);
  // otherwise the organ-level viridis base. Stores userData for raycasting.
  function colorMesh(node, organ) {
    const sub = subIndexByKey.get(organ.key)?.get(normNode(node.name)) || null;
    node.userData.organKey = organ.key;
    node.userData.regionName = node.name;
    node.userData.sub = sub;
    // Same YlGnBu ramp for both; a subregion uses its COMBINED count (organ +
    // localized), so it reads as a darker shade than the rest of the organ.
    // Counts honor the active source chips, so narrowing the sources recolors
    // the atlas; an organ whose models are all filtered out dims to read as
    // excluded (rather than pretending it's a genuine no-model grey).
    const organActive = activeCount(organ);
    const count = sub ? activeSubCount(organ, sub) : organActive;
    const col = countColor(count, maxCount);
    const dim = organActive === 0 && organ.n_models > 0;
    if (node.material && !node.material.isLineBasicMaterial) {
      node.material.color.copy(col);
      node.material.transparent = dim;
      node.material.opacity = dim ? 0.18 : 1;
    }
  }
  // Recolor every mesh of a shown organ to its base (subregion-or-organ) colors.
  function colorOrganGroup(key) {
    const g = groups.get(key), organ = organsByKey.get(key);
    if (!g || !organ) return;
    g.traverse((n) => { if (n.isMesh) colorMesh(n, organ); });
  }

  // Build (or reuse) an organ's colored GLB group. Each mesh is colored either
  // by its own modeled-subregion count (warm) or the organ's model count
  // (viridis base), and outlined so sub-regions read as distinct shapes.
  const loadGLB = (url) => new Promise((resolve, reject) =>
    loader.load(url, (gltf) => resolve(gltf.scene), undefined, reject));

  function ensureLoaded(key) {
    if (groups.has(key)) return Promise.resolve(groups.get(key));
    if (loading.has(key)) return loading.get(key);
    const organ = organsByKey.get(key);
    // Load ALL current-sex GLBs for the organ (bilateral/multi-part organs like
    // kidney ship one GLB per side); fall back to the other sex, then to the
    // single glb field for older manifests.
    let urls = organ ? glbsForSex(organ) : [];
    if (!urls.length) {
      const u = organ && organ.glb && (organ.glb.female || organ.glb.male);
      urls = u ? [u] : [];
    }
    if (!urls.length) return Promise.reject(new Error(`${key}: no GLB asset`));
    const gen = loadGen;   // the sex-generation this load belongs to
    const p = Promise.all(urls.map(loadGLB)).then((scenes) => {
      // A sex switch happened while these GLBs were loading — discard them so
      // the previous sex's body can't be added to the scene after the switch.
      if (gen !== loadGen) { loading.delete(key); return null; }
      const group = new THREE.Group();
      for (const s of scenes) group.add(s);
      group.traverse((node) => {
        if (!node.isMesh) return;
        node.material = new THREE.MeshStandardMaterial({ color: 0xffffff });
        const edges = new THREE.LineSegments(
          new THREE.EdgesGeometry(node.geometry, 30),
          new THREE.LineBasicMaterial({ color: 0x0e1116, transparent: true, opacity: 0.5 })
        );
        node.add(edges);
        colorMesh(node, organ);
        node.userData.homePos = node.position.clone();  // for explode/collapse
      });
      groups.set(key, group);
      loading.delete(key);
      return group;
    }).catch((err) => { loading.delete(key); throw err; });
    loading.set(key, p);
    return p;
  }

  // Point the camera to fit an arbitrary world-space bounding box.
  function frameBox(box) {
    if (box.isEmpty()) return;
    const size = box.getSize(new THREE.Vector3()).length() || 1;
    const center = box.getCenter(new THREE.Vector3());
    camera.position.copy(center).add(new THREE.Vector3(size * 0.7, size * 0.4, size * 0.9));
    camera.near = size / 100;
    camera.far = size * 100;
    camera.updateProjectionMatrix();
    controls.target.copy(center);
    controls.update();
  }

  function frameSelection() {
    const box = new THREE.Box3();
    let any = false;
    for (const key of selected) {
      const g = groups.get(key);
      if (g && g.parent === scene) { box.expandByObject(g); any = true; }
    }
    if (any) frameBox(box);
  }

  // Sync the scene graph + raycast targets + menu highlights to `selected`.
  function applySelection(doFrame) {
    for (const [key, g] of groups) {
      const want = selected.has(key);
      if (want && g.parent !== scene) scene.add(g);
      if (!want && g.parent === scene) scene.remove(g);
    }
    raycastMeshes.length = 0;
    for (const key of selected) {
      const g = groups.get(key);
      if (!g) continue;
      g.traverse((n) => { if (n.isMesh) raycastMeshes.push(n); });
    }
    for (const [key, row] of rows) row.classList.toggle("selected", selected.has(key));
    // System header checkbox: none / partial / all of its organs selected.
    for (const [system, chk] of groupChecks) {
      const keys = organsBySystem.get(system).filter(visibleForSex).map((o) => o.key);
      if (!keys.length) continue;
      const on = keys.filter((k) => selected.has(k)).length;
      chk.classList.toggle("on", on === keys.length);
      chk.classList.toggle("partial", on > 0 && on < keys.length);
      chk.textContent = on === keys.length ? "✓" : on > 0 ? "–" : "";
    }
    els.selCount.textContent = selected.size
      ? `${selected.size} organs · ${distinctModels([...selected])} models`
      : "none shown";
    recolorShown();          // keep colors consistent with any active search
    if (doFrame) frameSelection();
  }

  function focus(key) {
    focused = key;
    // While a model search is active the panel stays on the search results
    // (across all shown organs), not a single organ.
    if (modelQuery) { renderModelSearch(); rerenderPanel = () => focus(key); return; }
    const organ = organsByKey.get(key);
    if (organ) renderBioModels(organ);
    rerenderPanel = () => focus(key);
  }

  // Add/remove an organ from the composed scene.
  function toggle(key) {
    collapseExplode(true);
    if (selected.has(key)) {
      selected.delete(key);
      applySelection(false);
      if (focused === key) {
        const next = selected.values().next().value;
        if (next) focus(next); else resetPanel();
      }
      return;
    }
    selected.add(key);
    focus(key);
    const first = selected.size === 1;
    applySelection(false);              // reflect intent immediately
    setStatus(`loading ${organsByKey.get(key).label}…`);
    ensureLoaded(key).then(() => {
      applySelection(first);            // frame only when it's the first organ
      setStatus(selectionStatus());
    }).catch((e) => setStatus(`failed: ${e.message || e}`));
  }

  function selectOnly(key) {
    collapseExplode(true);              // isolating a new organ drops any explode
    selected.clear();
    selected.add(key);
    focus(key);
    applySelection(false);
    setStatus(`loading ${organsByKey.get(key).label}…`);
    ensureLoaded(key).then(() => { applySelection(true); setStatus(selectionStatus()); })
      .catch((e) => setStatus(`failed: ${e.message || e}`));
  }

  // ---- explode / collapse (B4) ----
  const easeInOutCubic = (t) => t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;

  // Return each mesh of the exploded organ to its stored home position.
  // instant=true snaps back (used when the group is being replaced/hidden);
  // otherwise animate the return via the shared explodeAnim.
  function collapseExplode(instant) {
    if (!explodedKey) { if (instant) explodeAnim = null; return; }
    const g = groups.get(explodedKey);
    explodedKey = null;
    if (!g) { explodeAnim = null; return; }
    const meshes = [];
    g.traverse((n) => {
      if (n.isMesh && n.userData.homePos) {
        meshes.push({ mesh: n, from: n.position.clone(), to: n.userData.homePos.clone() });
      }
    });
    if (instant || !meshes.length) {
      for (const m of meshes) m.mesh.position.copy(m.to);
      explodeAnim = null;
      return;
    }
    explodeAnim = { meshes, start: performance.now(), dur: 700 };
  }

  // Push every mesh of the (already loaded, isolated) organ outward from the
  // group's bounding-box center, along the center->mesh-centroid direction, by
  // ~0.6x the organ's size. Local position deltas are derived per mesh so the
  // motion is correct through each mesh's parent transform.
  function runExplode(key) {
    collapseExplode(true);
    const g = groups.get(key);
    if (!g) return;
    g.updateWorldMatrix(true, true);
    const box = new THREE.Box3().setFromObject(g);
    if (box.isEmpty()) return;
    const center = box.getCenter(new THREE.Vector3());
    const dist = (box.getSize(new THREE.Vector3()).length() || 1) * 0.6;
    const meshes = [];
    g.traverse((n) => {
      if (!n.isMesh || !n.userData.homePos) return;
      const mb = new THREE.Box3().setFromObject(n);
      if (mb.isEmpty()) return;
      const dir = mb.getCenter(new THREE.Vector3()).sub(center);
      if (dir.lengthSq() < 1e-9) dir.set(0, 1, 0);
      dir.normalize().multiplyScalar(dist);
      const parent = n.parent;
      const homeLocal = n.userData.homePos.clone();
      const homeWorld = parent.localToWorld(homeLocal.clone());
      const targetLocal = parent.worldToLocal(homeWorld.add(dir));
      meshes.push({ mesh: n, from: n.position.clone(), to: targetLocal });
    });
    if (!meshes.length) return;
    explodeAnim = { meshes, start: performance.now(), dur: 700 };
    explodedKey = key;
    // Zoom out to fit the exploded extent: each mesh flies out ~`dist` from the
    // center, so the exploded object fills roughly the organ box grown by `dist`.
    frameBox(box.clone().expandByScalar(dist));
    setStatus(`exploded ${organsByKey.get(key).label} — click “explode” again to collapse`);
  }

  // Row "explode" button: toggle. If this organ is already exploded, collapse
  // (animated); otherwise isolate it, load it, frame it, then explode.
  function explodeOrgan(key) {
    if (explodedKey === key) { collapseExplode(false); return; }
    collapseExplode(true);
    selected.clear();
    selected.add(key);
    focus(key);
    applySelection(false);
    setStatus(`loading ${organsByKey.get(key).label}…`);
    ensureLoaded(key).then(() => {
      applySelection(true);            // show + frame the organ first
      runExplode(key);                 // then blow it apart
    }).catch((e) => setStatus(`failed: ${e.message || e}`));
  }

  // ---- sex switch (B2) ----
  function updateSexToggle() {
    els.sexFemale?.classList.toggle("active", sex === "female");
    els.sexMale?.classList.toggle("active", sex === "male");
  }
  // Rebuild the whole scene for the chosen sex: the cached groups hold the other
  // sex's GLBs, so drop them, rebuild the menu for the now-visible organs, prune
  // the selection to what exists in this sex, then reload+reframe the survivors.
  function switchSex(next) {
    if (next === sex || (next !== "female" && next !== "male")) return;
    sex = next;
    loadGen++;   // invalidate any in-flight loads from the previous sex
    explodeAnim = null; explodedKey = null;
    for (const [, g] of groups) { if (g.parent === scene) scene.remove(g); }
    groups.clear();
    loading.clear();
    recomputeKeys();
    buildMenu();
    for (const k of [...selected]) {
      if (!visibleForSex(organsByKey.get(k))) selected.delete(k);
    }
    updateSexToggle();
    const keep = [...selected];
    if (keep.length) {
      selectMany(keep, sex === "female" ? "female anatomy" : "male anatomy");
    } else {
      focused = null;
      applySelection(false);
      resetPanel();
      setStatus("nothing selected");
    }
  }

  // Add or remove every organ in a system, based on whether they're all
  // already selected (toggle). Loads any missing GLBs.
  function toggleSystem(system) {
    collapseExplode(true);
    const keys = organsBySystem.get(system).filter(visibleForSex).map((o) => o.key);
    const allOn = keys.every((k) => selected.has(k));
    if (allOn) {
      for (const k of keys) selected.delete(k);
      applySelection(false);
      if (!selected.has(focused)) {
        const next = selected.values().next().value;
        if (next) focus(next); else resetPanel();
      }
      setStatus(selectionStatus());
      return;
    }
    for (const k of keys) selected.add(k);
    focus(keys[0]);
    addMany(keys, system);
  }

  function onlySystem(system) {
    selectMany(organsBySystem.get(system).filter(visibleForSex).map((o) => o.key), system);
  }

  // Load a set of keys already added to `selected`, framing when the batch is in.
  function addMany(keys, label) {
    applySelection(false);
    let done = 0;
    const total = keys.length;
    setStatus(`loading ${label}… 0/${total}`);
    for (const k of keys) {
      ensureLoaded(k).then(() => {
        done++;
        applySelection(done === total);
        setStatus(done === total ? selectionStatus() : `loading ${label}… ${done}/${total}`);
      }).catch(() => { done++; });
    }
  }

  function selectMany(keys, label) {
    collapseExplode(true);
    selected.clear();
    for (const k of keys) selected.add(k);
    // A single organ focuses it; a bulk selection shows the combined panel of
    // every selected organ's models (grouped by organ), not just the first one.
    if (keys.length === 1) {
      focus(keys[0]);
    } else {
      focused = null;
      if (modelQuery) renderModelSearch(); else renderSelectedModels();
    }
    applySelection(false);
    let done = 0;
    const total = keys.length;
    setStatus(`loading ${label}… 0/${total}`);
    for (const k of keys) {
      ensureLoaded(k).then(() => {
        done++;
        // Frame as soon as the first organ lands (so the camera isn't stuck
        // on the default until the heavy GLBs finish), then again at the end.
        applySelection(done === 1 || done === total);
        setStatus(done === total ? selectionStatus() : `loading ${label}… ${done}/${total}`);
      }).catch(() => { done++; });
    }
  }

  function clearAll() {
    collapseExplode(true);
    selected.clear();
    focused = null;
    applySelection(false);
    resetPanel();
    setStatus("nothing selected");
  }

  function selectionStatus() {
    const distinct = distinctModels([...selected]);
    return `${selected.size} organ${selected.size === 1 ? "" : "s"} shown · ${distinct} distinct model${distinct === 1 ? "" : "s"} represented`;
  }

  function resetPanel() {
    els.bpTitle.textContent = "Select an organ";
    els.bpSub.textContent = `${atlas.summary.n_modeled}/${atlas.summary.n_organs} organs modeled`;
    els.bpList.innerHTML = "";
    renderSourceChips([]);
    rerenderPanel = () => resetPanel();
  }

  const _modelLink = modelLinkEl;   // one shared builder (handles matched_by + via)

  // Right-panel list for one clicked subregion: the models it carries — the
  // organ's whole-organ models PLUS the ones localized here — the localized
  // ones listed first and badged (FTU / cell type); the rest are region-wide.
  function renderSubregion(sub, organ) {
    const key = (m) => m.repository + ":" + m.source_id;
    const localModels = filterBySource(sub.models || []);
    const localIds = new Set(localModels.map(key));
    const regionWide = filterBySource(organ.models || []).filter((m) => !localIds.has(key(m)));
    const total = localModels.length + regionWide.length;   // == the rows rendered below
    renderSourceChips([...(sub.models || []), ...(organ.models || [])]);
    els.bpTitle.textContent = sub.label || "Subregion";
    els.bpSub.textContent =
      `${total} model${total === 1 ? "" : "s"} · ${localModels.length} localized here · ${sub.uberon || ""} · in ${organ.label}`;
    els.bpList.innerHTML = "";
    if (!localModels.length && !regionWide.length) {
      const d = document.createElement("div");
      d.className = "empty";
      d.textContent = total
        ? "No models match the current source filter."
        : "No models associated with this structure.";
      els.bpList.appendChild(d);
      return;
    }
    // Models localized to this structure, grouped by physiological process
    // (structure → process → model). Region-wide models follow under a divider.
    appendProcessControls(els.bpList);
    appendProcessGroups(els.bpList, localModels);
    if (regionWide.length) {
      const div = document.createElement("div");
      div.className = "region-divider";
      div.textContent = `Elsewhere in ${organ.label}`;
      els.bpList.appendChild(div);
      appendProcessGroups(els.bpList, regionWide);
    }
  }

  // Right-panel results for the model keyword search: matching BioModels grouped
  // by the shown organ that carries them, each organ header swatch matching the
  // 3D coloring (so the panel and the lit-up organs read as one view).
  function renderModelSearch() {
    const q = modelQuery;
    rerenderPanel = () => renderModelSearch();
    els.bpTitle.textContent = `Models matching “${q}”`;
    // chips reflect matches across all shown organs, regardless of active source
    const allMatch = [...selected].flatMap((k) =>
      (organsByKey.get(k)?.models || []).filter(
        (m) => (m.name + " " + m.source_id).toLowerCase().includes(q)));
    renderSourceChips(allMatch);
    els.bpList.innerHTML = "";
    const hits = [...selected]
      .map((k) => ({ organ: organsByKey.get(k), models: matchingModels(organsByKey.get(k), q) }))
      .filter((h) => h.organ && h.models.length)
      .sort((a, b) => b.models.length - a.models.length);
    const nModels = new Set(hits.flatMap((h) => h.models.map((m) => m.repository + ":" + m.source_id))).size;
    els.bpSub.textContent = hits.length
      ? `${nModels} model${nModels === 1 ? "" : "s"} across ${hits.length} shown organ${hits.length === 1 ? "" : "s"}`
      : `no matches in the ${selected.size} shown organ${selected.size === 1 ? "" : "s"}`;
    if (!hits.length) {
      const d = document.createElement("div");
      d.className = "empty";
      d.textContent = selected.size
        ? "No shown organ has a model matching that keyword."
        : "Select organs first, then filter their models.";
      els.bpList.appendChild(d);
      return;
    }
    for (const { organ, models } of hits) {
      const head = document.createElement("div");
      head.className = "organ-group-head";
      head.innerHTML = `<span class="sw" style="background:${cssColor(models.length, searchMaxMatch || 1)}"></span>` +
        `${organ.label} · ${models.length}`;
      els.bpList.appendChild(head);
      for (const m of models) els.bpList.appendChild(_modelLink(m));
    }
  }

  // Right-panel view when MANY organs are shown and none is singled out (e.g.
  // "All modeled"): every selected organ's models, grouped by organ (combined
  // across sources, honoring the source chips), so the panel reflects the whole
  // left-hand selection rather than one focused organ.
  function renderSelectedModels() {
    rerenderPanel = () => renderSelectedModels();
    const chipModels = [...selected].flatMap((k) => organsByKey.get(k)?.models || []);
    renderSourceChips(chipModels);
    const byOrgan = [...selected]
      .map((k) => ({ organ: organsByKey.get(k), models: filterBySource(organsByKey.get(k)?.models || []) }))
      .filter((g) => g.organ && g.models.length)
      .sort((a, b) => b.models.length - a.models.length);
    const shownModels = byOrgan.flatMap((g) => g.models);   // active-source only
    const distinct = new Set(shownModels.map((m) => m.repository + ":" + m.source_id)).size;
    const brk = distinctBreakdown(shownModels);            // breakdown matches the total
    els.bpTitle.textContent = `${selected.size} organ${selected.size === 1 ? "" : "s"} shown`;
    els.bpSub.textContent = byOrgan.length
      ? `${distinct} distinct model${distinct === 1 ? "" : "s"} across ${byOrgan.length} organ${byOrgan.length === 1 ? "" : "s"}`
        + (brk ? ` · ${brk}` : "")
      : `no models in the ${selected.size} shown organ${selected.size === 1 ? "" : "s"}`;
    els.bpList.innerHTML = "";
    if (!byOrgan.length) {
      const d = document.createElement("div");
      d.className = "empty";
      d.textContent = "No models match the current source filter.";
      els.bpList.appendChild(d);
      return;
    }
    for (const { organ, models } of byOrgan) {
      const head = document.createElement("div");
      head.className = "organ-group-head";
      head.innerHTML = `<span class="sw" style="background:${cssColor(models.length, maxCount)}"></span>`
        + `${esc(organ.label)} · ${models.length}`;
      els.bpList.appendChild(head);
      for (const m of models) els.bpList.appendChild(_modelLink(m));
    }
  }

  // The panel's default state, given the current selection: a single focused
  // organ, else the aggregated all-selected view, else the empty prompt.
  function showDefaultPanel() {
    if (focused) focus(focused);
    else if (selected.size) renderSelectedModels();
    else resetPanel();
  }

  // React to the model keyword box: recolor the shown organs by match count and
  // switch the panel between the default view and search results.
  function onModelSearch() {
    modelQuery = els.modelSearch.value.trim().toLowerCase();
    recolorShown();
    if (modelQuery) renderModelSearch();
    else showDefaultPanel();
  }

  // ---- left menu: organs grouped by anatomical system, collapsible ----
  const groupBodies = new Map();       // system -> the row-container element
  function buildMenu() {
    els.list.innerHTML = "";
    // Rebuilt per sex switch, so drop references to the old (detached) DOM.
    rows.clear();
    groupChecks.clear();
    groupBodies.clear();
    for (const system of systemsList) {
      const organs = (organsBySystem.get(system) || []).filter(visibleForSex);
      if (!organs.length) continue;   // no organs for this sex -> hide the system
      const modeled = organs.filter((o) => o.n_models > 0).length;

      const group = document.createElement("div");
      group.className = "organ-group collapsed";   // systems start collapsed

      const header = document.createElement("div");
      header.className = "group-head";
      header.innerHTML =
        `<span class="caret">▾</span>` +
        `<span class="gchk" role="button" title="Toggle whole system"></span>` +
        `<span class="gname">${system}</span>` +
        `<span class="gcount">${modeled ? modeled + "/" : ""}${organs.length}</span>` +
        `<span class="gonly" role="button" title="Show only this system">only</span>`;
      const body = document.createElement("div");
      body.className = "group-body";

      header.addEventListener("click", (e) => {
        if (e.target.classList.contains("gchk")) { toggleSystem(system); return; }
        if (e.target.classList.contains("gonly")) { onlySystem(system); return; }
        group.classList.toggle("collapsed");   // caret / name toggles collapse
      });

      for (const o of organs) {
        const nActive = activeCount(o);
        const row = document.createElement("div");
        row.className = "organ-row" + (nActive ? "" : " zero");
        row.dataset.key = o.key;
        row.dataset.label = o.label.toLowerCase();
        row.innerHTML =
          `<span class="chk">✓</span>` +
          `<span class="sw" style="background:${cssColor(nActive, maxCount)}"></span>` +
          `<span class="nm" title="${o.label}">${o.label}</span>` +
          `<span class="ct">${nActive || ""}</span>` +
          `<span class="only" role="button">only</span>` +
          `<span class="explode" role="button" title="Isolate and explode this organ">explode</span>`;
        row.addEventListener("click", (e) => {
          if (e.target.classList.contains("only")) { selectOnly(o.key); return; }
          if (e.target.classList.contains("explode")) { explodeOrgan(o.key); return; }
          toggle(o.key);
        });
        body.appendChild(row);
        rows.set(o.key, row);
      }

      group.appendChild(header);
      group.appendChild(body);
      els.list.appendChild(group);
      groupChecks.set(system, header.querySelector(".gchk"));
      groupBodies.set(system, { group, body });
    }
  }

  buildMenu();
  els.search.addEventListener("input", () => {
    const q = els.search.value.trim().toLowerCase();
    for (const [, row] of rows) {
      row.style.display = !q || row.dataset.label.includes(q) ? "" : "none";
    }
    // Hide a whole group when the filter leaves it with no visible organs;
    // force-expand matching groups so hits are visible.
    for (const [system, { group, body }] of groupBodies) {
      const anyVisible = [...body.children].some((r) => r.style.display !== "none");
      group.style.display = anyVisible ? "" : "none";
      if (q && anyVisible) group.classList.remove("collapsed");
    }
  });
  els.btnAllModeled.addEventListener("click", () => selectMany(modeledKeys, "all modeled organs"));
  els.btnAll.addEventListener("click", () => selectMany(allKeys, "all 50 organs"));
  // Collapse / expand every system group in the left menu at once.
  const setAllGroups = (collapsed) =>
    els.list.querySelectorAll(".organ-group").forEach((g) => g.classList.toggle("collapsed", collapsed));
  els.btnCollapseAll.addEventListener("click", () => setAllGroups(true));
  els.btnExpandAll.addEventListener("click", () => setAllGroups(false));
  // Recenter the camera on whatever is currently visible.
  els.btnCenter.addEventListener("click", frameSelection);
  // Download the full atlas metadata (all organs, subregions, model links) as JSON.
  els.btnDownload?.addEventListener("click", () => {
    const blob = new Blob([JSON.stringify(atlas, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "hra-computational-model-atlas.json";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  });
  // Female | Male segmented toggle: rebuild the scene for the chosen sex.
  els.sexFemale?.addEventListener("click", () => switchSex("female"));
  els.sexMale?.addEventListener("click", () => switchSex("male"));
  updateSexToggle();
  addEventListener("keydown", (e) => {
    if (e.key === "f" && !/input|textarea/i.test(e.target.tagName)) frameSelection();
  });
  // Model keyword search (right panel): recolor shown organs by match count
  // + list matching models grouped by organ.
  els.modelSearch.addEventListener("input", onModelSearch);

  // ---- hover + click in the 3D scene ----
  const ray = new THREE.Raycaster();
  const ndc = new THREE.Vector2();
  renderer.domElement.addEventListener("pointermove", (event) => {
    const rect = renderer.domElement.getBoundingClientRect();
    ndc.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    ndc.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
    ray.setFromCamera(ndc, camera);
    const hit = ray.intersectObjects(raycastMeshes, false)[0];
    const obj = hit ? hit.object : null;
    if (hovered && hovered !== obj) hovered.material.emissive?.setHex(0x000000);
    hovered = obj;
    if (!hovered) return;
    hovered.material.emissive = new THREE.Color(0x2b3a44);
    const organ = organsByKey.get(hovered.userData.organKey);
    const sub = hovered.userData.sub;
    if (sub) {
      const total = subregionCount(organ, sub);
      setStatus(`${sub.label} · ${organ.label} — ${total} model${total === 1 ? "" : "s"} (${sub.n_models} localized here · click to list)`);
    } else {
      setStatus(`${hovered.userData.regionName} · ${organ.label} (${organ.n_models} model${organ.n_models === 1 ? "" : "s"})`);
    }
  });
  // Click a structure: a modeled subregion lists its own models; anything else
  // focuses the whole organ's BioModels.
  renderer.domElement.addEventListener("click", () => {
    if (!hovered) return;
    const sub = hovered.userData.sub;
    if (sub && !modelQuery) {
      const organ = organsByKey.get(hovered.userData.organKey);
      focused = hovered.userData.organKey;
      renderSubregion(sub, organ);
      rerenderPanel = () => renderSubregion(sub, organ);
    } else {
      focus(hovered.userData.organKey);
    }
  });

  addEventListener("resize", () => {
    camera.aspect = innerWidth / innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(innerWidth, innerHeight);
  });
  (function animate() {
    requestAnimationFrame(animate);
    // Drive the explode/collapse tween (B4) from the single shared loop.
    if (explodeAnim) {
      let t = (performance.now() - explodeAnim.start) / explodeAnim.dur;
      if (t >= 1) t = 1;
      const e = easeInOutCubic(t);
      for (const m of explodeAnim.meshes) m.mesh.position.lerpVectors(m.from, m.to, e);
      if (t >= 1) explodeAnim = null;
    }
    controls.update();
    renderer.render(scene, camera);
  })();

  // Landing: compose all modeled organs into the colored bodyscape (organs
  // stream in; the small pancreas GLB lands first and frames the view). Use
  // "None" then click rows to browse one at a time, or a row's "only" button.
  selectMany(modeledKeys, "all modeled organs");
}

// Panel chrome: drag the inner edge of either side panel to resize it, and
// collapse a panel to reveal more of the atlas (a reopen tab brings it back).
// Pure DOM/CSS, independent of the 3D scene — the canvas is full-screen behind
// the panels, so resizing/collapsing simply reveals more of it.
function setupPanelChrome() {
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  const collapse = (panel, tab, bodyClass, yes) => {
    if (!panel || !tab) return;
    panel.classList.toggle("collapsed", yes);
    tab.classList.toggle("show", yes);
    document.body.classList.toggle(bodyClass, yes);   // also hides that side's resizer
  };
  els.collapseLeft?.addEventListener("click", () => collapse(els.organMenu, els.reopenLeft, "left-collapsed", true));
  els.reopenLeft?.addEventListener("click", () => collapse(els.organMenu, els.reopenLeft, "left-collapsed", false));
  els.collapseRight?.addEventListener("click", () => collapse(els.biomodelsPanel, els.reopenRight, "right-collapsed", true));
  els.reopenRight?.addEventListener("click", () => collapse(els.biomodelsPanel, els.reopenRight, "right-collapsed", false));

  function drag(handle, getStart, apply) {
    if (!handle) return;
    handle.addEventListener("pointerdown", (e) => {
      e.preventDefault();
      const startX = e.clientX, start = getStart();
      try { handle.setPointerCapture(e.pointerId); } catch { /* older browsers */ }
      handle.classList.add("active");
      const move = (ev) => apply(start, ev.clientX - startX);
      const up = () => {
        handle.classList.remove("active");
        try { handle.releasePointerCapture(e.pointerId); } catch { /* ignore */ }
        removeEventListener("pointermove", move);
        removeEventListener("pointerup", up);
      };
      addEventListener("pointermove", move);
      addEventListener("pointerup", up);
    });
  }
  // Left menu: width grows as its right-edge handle drags right; drive --menu-w
  // so #status and the handle position (offset by it) stay aligned.
  drag(els.resizeLeft,
    () => els.organMenu.getBoundingClientRect().width,
    (start, dx) => document.documentElement.style.setProperty("--menu-w", clamp(start + dx, 220, 620) + "px"));
  // Right panel: width grows as its left-edge handle drags left (dx negative);
  // drive --panel-w so the panel and its handle stay in sync.
  drag(els.resizeRight,
    () => els.biomodelsPanel.getBoundingClientRect().width,
    (start, dx) => document.documentElement.style.setProperty("--panel-w", clamp(start - dx, 240, 640) + "px"));
}
setupPanelChrome();

main().catch((err) => { console.error(err); setStatus(`error: ${err?.message || err}`); });
