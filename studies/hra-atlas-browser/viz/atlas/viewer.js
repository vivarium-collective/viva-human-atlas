// HRA Atlas Browser — self-contained three.js multi-organ browser.
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
  btnNone: document.getElementById("btn-none"),
  btnCenter: document.getElementById("btn-center"),
  sexFemale: document.getElementById("sex-female"),
  sexMale: document.getElementById("sex-male"),
  modelSearch: document.getElementById("model-search"),
  selCount: document.getElementById("sel-count"),
  legendMax: document.getElementById("legend-max"),
  bpTitle: document.getElementById("bp-title"),
  bpSub: document.getElementById("bp-sub"),
  bpList: document.getElementById("biomodels-list"),
  sourceFilter: document.querySelector("[data-source-filter]"),
};
const setStatus = (t) => { if (els.status) els.status.textContent = t; };

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

// A subregion's displayed model count = the organ's whole-organ models + the
// models specifically placed at this structure.
const subregionCount = (organ, sub) => organ.n_models + (sub.n_models || 0);

function renderBioModels(organ) {
  els.bpTitle.textContent = organ.label;
  els.bpSub.textContent = organ.n_models
    ? `${organ.n_models} BioModel${organ.n_models > 1 ? "s" : ""} · ${organ.uberon || ""}`
    : `no models · ${organ.uberon || ""}`;
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
  for (const m of shown) {
    const a = document.createElement("a");
    a.href = m.url;
    a.target = "_blank";
    a.rel = "noopener";
    const by = m.matched_by || [];
    // provenance badge: how this model was linked to the organ
    const badge = by.length
      ? `<span class="prov prov-${by.length === 2 ? "both" : by[0]}">${
          by.length === 2 ? "name+annotation" : by[0]}</span>`
      : "";
    // source badge: which repository (BioModels vs PhysioNet) this model
    // came from — distinct from the provenance badge above.
    const srcBadge = `<span class="src-badge src-${m.repository}">${m.repository}</span>`;
    a.innerHTML = `<div>${m.name} ${srcBadge} ${badge}</div><div class="mid">${m.source_id}</div>`;
    els.bpList.appendChild(a);
  }
}

async function main() {
  setStatus("loading config…");
  const cfg = await fetch("config.json").then((r) => r.json());
  const atlas = await fetch(cfg.atlas).then((r) => r.json());
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
      if (o) for (const m of filterBySource(o.models)) ids.add(m.source_id);
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
  const distinctTotal = atlas.summary.n_models_distinct ?? atlas.summary.n_models_total;
  const nSub = atlas.summary.n_subregions || 0;
  els.summary.textContent =
    `${atlas.summary.n_modeled}/${atlas.summary.n_organs} organs modeled · ${distinctTotal} distinct BioModels`
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
  // Active source filter (`all` | `biomodels` | `physionet`), driven by the
  // [data-source-filter] <select> in index.html.
  let sourceFilter = els.sourceFilter ? els.sourceFilter.value : "all";
  // ---- explode (B4) ----
  let explodeAnim = null;              // {meshes:[{mesh,from,to}], start, dur}
  let explodedKey = null;              // organ key currently in exploded state

  // Models restricted to the active source filter (repository = biomodels/physionet).
  function filterBySource(models) {
    return sourceFilter === "all" ? models : models.filter((m) => m.repository === sourceFilter);
  }

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
    if (!modelQuery) return { color: countColor(organ.n_models, maxCount), opacity: 1 };
    const n = matchingModels(organ, modelQuery).length;
    if (!n) return { color: new THREE.Color(NOMODEL), opacity: 0.18 };
    const maxMatch = searchMaxMatch || 1;
    return { color: countColor(n, maxMatch), opacity: 1 };
  }
  let searchMaxMatch = 0;
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
    const count = sub ? subregionCount(organ, sub) : organ.n_models;
    const col = countColor(count, maxCount);
    if (node.material && !node.material.isLineBasicMaterial) {
      node.material.color.copy(col);
      node.material.transparent = false;
      node.material.opacity = 1;
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

  function frameSelection() {
    const box = new THREE.Box3();
    let any = false;
    for (const key of selected) {
      const g = groups.get(key);
      if (g && g.parent === scene) { box.expandByObject(g); any = true; }
    }
    if (!any) return;
    const size = box.getSize(new THREE.Vector3()).length() || 1;
    const center = box.getCenter(new THREE.Vector3());
    camera.position.copy(center).add(new THREE.Vector3(size * 0.7, size * 0.4, size * 0.9));
    camera.near = size / 100;
    camera.far = size * 100;
    camera.updateProjectionMatrix();
    controls.target.copy(center);
    controls.update();
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
    if (modelQuery) { renderModelSearch(); return; }
    const organ = organsByKey.get(key);
    if (organ) renderBioModels(organ);
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
    focus(keys[0]);
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
    return `${selected.size} organ${selected.size === 1 ? "" : "s"} shown · ${distinct} distinct BioModel${distinct === 1 ? "" : "s"} represented`;
  }

  function resetPanel() {
    els.bpTitle.textContent = "Select an organ";
    els.bpSub.textContent = `${atlas.summary.n_modeled}/${atlas.summary.n_organs} organs modeled`;
    els.bpList.innerHTML = "";
  }

  function _modelLink(m) {
    const a = document.createElement("a");
    a.href = m.url; a.target = "_blank"; a.rel = "noopener";
    const by = m.matched_by || [];
    let badge = by.length
      ? `<span class="prov prov-${by.length === 2 ? "both" : by[0]}">${
          by.length === 2 ? "name+annotation" : by[0]}</span>` : "";
    // subregion model rows carry `via` (how the model reached this structure)
    if (!badge && m.via) {
      badge = `<span class="prov prov-${m.via === "ftu" ? "annotation" : "name"}">${
        m.via === "ftu" ? "FTU" : "cell type"}</span>`;
    }
    // source badge: which repository (BioModels vs PhysioNet) this model
    // came from — distinct from the provenance badge above.
    const srcBadge = `<span class="src-badge src-${m.repository}">${m.repository}</span>`;
    a.innerHTML = `<div>${m.name || m.source_id} ${srcBadge} ${badge}</div><div class="mid">${m.source_id}</div>`;
    return a;
  }

  // Right-panel list for one clicked subregion: the models it carries — the
  // organ's whole-organ models PLUS the ones localized here — the localized
  // ones listed first and badged (FTU / cell type); the rest are region-wide.
  function renderSubregion(sub, organ) {
    const localModels = filterBySource(sub.models || []);
    const localIds = new Set(localModels.map((m) => m.source_id));
    const regionWide = filterBySource(organ.models || []).filter((m) => !localIds.has(m.source_id));
    const total = subregionCount(organ, sub);
    els.bpTitle.textContent = sub.label || "Subregion";
    els.bpSub.textContent =
      `${total} BioModel${total === 1 ? "" : "s"} · ${sub.n_models} localized here · ${sub.uberon || ""} · in ${organ.label}`;
    els.bpList.innerHTML = "";
    for (const m of localModels) els.bpList.appendChild(_modelLink(m));
    for (const m of regionWide) els.bpList.appendChild(_modelLink(m));
    if (!localModels.length && !regionWide.length) {
      const d = document.createElement("div");
      d.className = "empty";
      d.textContent = total
        ? "No models match the current source filter."
        : "No models associated with this structure.";
      els.bpList.appendChild(d);
    }
  }

  // Right-panel results for the model keyword search: matching BioModels grouped
  // by the shown organ that carries them, each organ header swatch matching the
  // 3D coloring (so the panel and the lit-up organs read as one view).
  function renderModelSearch() {
    const q = modelQuery;
    els.bpTitle.textContent = `Models matching “${q}”`;
    els.bpList.innerHTML = "";
    const hits = [...selected]
      .map((k) => ({ organ: organsByKey.get(k), models: matchingModels(organsByKey.get(k), q) }))
      .filter((h) => h.organ && h.models.length)
      .sort((a, b) => b.models.length - a.models.length);
    const nModels = new Set(hits.flatMap((h) => h.models.map((m) => m.source_id))).size;
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

  // React to the source filter <select>: re-render whatever the right panel
  // is currently showing (search results or the focused organ) with the new
  // filter applied.
  function onSourceFilter() {
    sourceFilter = els.sourceFilter.value;
    if (modelQuery) renderModelSearch();
    else if (focused) focus(focused);
    else resetPanel();
  }

  // React to the model keyword box: recolor the shown organs by match count and
  // switch the panel between per-organ view and search results.
  function onModelSearch() {
    modelQuery = els.modelSearch.value.trim().toLowerCase();
    recolorShown();
    if (modelQuery) renderModelSearch();
    else if (focused) focus(focused);
    else resetPanel();
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
      group.className = "organ-group";

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
        const row = document.createElement("div");
        row.className = "organ-row" + (o.n_models ? "" : " zero");
        row.dataset.key = o.key;
        row.dataset.label = o.label.toLowerCase();
        row.innerHTML =
          `<span class="chk">✓</span>` +
          `<span class="sw" style="background:${cssColor(o.n_models, maxCount)}"></span>` +
          `<span class="nm" title="${o.label}">${o.label}</span>` +
          `<span class="ct">${o.n_models || ""}</span>` +
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
  els.btnNone.addEventListener("click", clearAll);
  // Recenter the camera on whatever is currently visible.
  els.btnCenter.addEventListener("click", frameSelection);
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
  // Source filter (All / BioModels / PhysioNet): re-render the panel + counts.
  els.sourceFilter?.addEventListener("change", onSourceFilter);

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
      focused = hovered.userData.organKey;
      renderSubregion(sub, organsByKey.get(hovered.userData.organKey));
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

main().catch((err) => { console.error(err); setStatus(`error: ${err?.message || err}`); });
