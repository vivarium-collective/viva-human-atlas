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
  selCount: document.getElementById("sel-count"),
  legendMax: document.getElementById("legend-max"),
  bpTitle: document.getElementById("bp-title"),
  bpSub: document.getElementById("bp-sub"),
  bpList: document.getElementById("biomodels-list"),
};
const setStatus = (t) => { if (els.status) els.status.textContent = t; };

// Viridis colormap (perceptually-uniform, high chroma variation) so distinct
// model counts read as distinct colors — dark purple (few) -> teal -> green ->
// yellow (many) — far more separable than a single-hue green ramp. n==0 (no
// model) is a neutral grey, off the ramp entirely.
const VIRIDIS = [
  [68, 1, 84], [71, 44, 122], [59, 81, 139], [44, 113, 142], [33, 144, 141],
  [39, 173, 129], [92, 200, 99], [170, 220, 50], [253, 231, 37],
];
function viridis(t) {
  t = Math.max(0, Math.min(1, t));
  const x = t * (VIRIDIS.length - 1);
  const i = Math.floor(x), f = x - i;
  const a = VIRIDIS[i], b = VIRIDIS[Math.min(i + 1, VIRIDIS.length - 1)];
  return new THREE.Color(
    (a[0] + (b[0] - a[0]) * f) / 255,
    (a[1] + (b[1] - a[1]) * f) / 255,
    (a[2] + (b[2] - a[2]) * f) / 255,
  );
}
// Log scale so the low-count majority (1..9) still spreads across the ramp
// instead of bunching at one end while pancreas (36) dominates.
function countColor(n, max) {
  if (!n) return new THREE.Color(NOMODEL);
  const t = max > 1 ? Math.log1p(n) / Math.log1p(max) : 1;
  return viridis(t);
}
const cssColor = (n, max) => "#" + countColor(n, max).getHexString();

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
  for (const m of organ.models) {
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
    a.innerHTML = `<div>${m.name} ${badge}</div><div class="mid">${m.biomodel_id}</div>`;
    els.bpList.appendChild(a);
  }
}

async function main() {
  setStatus("loading config…");
  const cfg = await fetch("config.json").then((r) => r.json());
  const atlas = await fetch(cfg.atlas).then((r) => r.json());
  const organsByKey = new Map(atlas.organs.map((o) => [o.key, o]));
  // Composed views must not overlay both sexes of the same structure (that
  // renders "double legs" — male knee bones poking through the female skin).
  // Collapse -female-/-male- variants (keeping left/right) to ONE sex,
  // preferring female (matches the default female GLBs), for multi-organ sets.
  function singleSex(keys) {
    const seen = new Set(), out = [];
    for (const k of keys) {
      const base = k.replace(/-(female|male)/, "");   // keep left/right
      const isMale = /-male/.test(k);
      if (isMale && keys.some((o) => o !== k && o.replace(/-(female|male)/, "") === base && /-female/.test(o))) {
        continue;   // a female twin exists -> skip the male duplicate
      }
      if (!seen.has(base)) { seen.add(base); out.push(k); }
    }
    return out;
  }
  const allKeys = singleSex(atlas.organs.map((o) => o.key));
  const modeledKeys = atlas.organs.filter((o) => o.n_models > 0).map((o) => o.key);
  // distinct BioModels represented by a set of organ keys (union of ids)
  function distinctModels(keys) {
    const ids = new Set();
    for (const k of keys) {
      const o = organsByKey.get(k);
      if (o) for (const m of o.models) ids.add(m.biomodel_id);
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
  els.summary.textContent =
    `${atlas.summary.n_modeled}/${atlas.summary.n_organs} organs modeled · ${distinctTotal} distinct BioModels`;

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

  // Build (or reuse) an organ's colored GLB group. Every mesh is colored by
  // the organ's model count (organ-granularity) and outlined so sub-regions
  // read as distinct shapes.
  function ensureLoaded(key) {
    if (groups.has(key)) return Promise.resolve(groups.get(key));
    if (loading.has(key)) return loading.get(key);
    const organ = organsByKey.get(key);
    const url = organ && (organ.glb.female || organ.glb.male);
    if (!url) return Promise.reject(new Error(`${key}: no GLB asset`));
    const p = new Promise((resolve, reject) => {
      loader.load(url, (gltf) => {
        const group = gltf.scene;
        const color = countColor(organ.n_models, atlas.max_models);
        group.traverse((node) => {
          if (!node.isMesh) return;
          node.material = new THREE.MeshStandardMaterial({ color: color.clone() });
          const edges = new THREE.LineSegments(
            new THREE.EdgesGeometry(node.geometry, 30),
            new THREE.LineBasicMaterial({ color: 0x0e1116, transparent: true, opacity: 0.5 })
          );
          node.add(edges);
          node.userData.organKey = key;
          node.userData.regionName = node.name;
        });
        groups.set(key, group);
        loading.delete(key);
        resolve(group);
      }, undefined, (err) => { loading.delete(key); reject(err); });
    });
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
      const keys = organsBySystem.get(system).map((o) => o.key);
      const on = keys.filter((k) => selected.has(k)).length;
      chk.classList.toggle("on", on === keys.length);
      chk.classList.toggle("partial", on > 0 && on < keys.length);
      chk.textContent = on === keys.length ? "✓" : on > 0 ? "–" : "";
    }
    els.selCount.textContent = selected.size
      ? `${selected.size} organs · ${distinctModels([...selected])} models`
      : "none shown";
    if (doFrame) frameSelection();
  }

  function focus(key) {
    focused = key;
    const organ = organsByKey.get(key);
    if (organ) renderBioModels(organ);
  }

  // Add/remove an organ from the composed scene.
  function toggle(key) {
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
    selected.clear();
    selected.add(key);
    focus(key);
    applySelection(false);
    setStatus(`loading ${organsByKey.get(key).label}…`);
    ensureLoaded(key).then(() => { applySelection(true); setStatus(selectionStatus()); })
      .catch((e) => setStatus(`failed: ${e.message || e}`));
  }

  // Add or remove every organ in a system, based on whether they're all
  // already selected (toggle). Loads any missing GLBs.
  function toggleSystem(system) {
    const keys = organsBySystem.get(system).map((o) => o.key);
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
    selectMany(organsBySystem.get(system).map((o) => o.key), system);
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

  // ---- left menu: organs grouped by anatomical system, collapsible ----
  const groupBodies = new Map();       // system -> the row-container element
  function buildMenu() {
    els.list.innerHTML = "";
    for (const system of systemsList) {
      const organs = organsBySystem.get(system) || [];
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
          `<span class="sw" style="background:${cssColor(o.n_models, atlas.max_models)}"></span>` +
          `<span class="nm" title="${o.label}">${o.label}</span>` +
          `<span class="ct">${o.n_models || ""}</span>` +
          `<span class="only" role="button">only</span>`;
        row.addEventListener("click", (e) => {
          if (e.target.classList.contains("only")) { selectOnly(o.key); return; }
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
  addEventListener("keydown", (e) => {
    if (e.key === "f" && !/input|textarea/i.test(e.target.tagName)) frameSelection();
  });

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
    setStatus(`${hovered.userData.regionName} · ${organ.label} (${organ.n_models} model${organ.n_models === 1 ? "" : "s"})`);
  });
  // Click an organ in the 3D scene to focus its BioModels in the panel.
  renderer.domElement.addEventListener("click", () => {
    if (hovered) focus(hovered.userData.organKey);
  });

  addEventListener("resize", () => {
    camera.aspect = innerWidth / innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(innerWidth, innerHeight);
  });
  (function animate() {
    requestAnimationFrame(animate);
    controls.update();
    renderer.render(scene, camera);
  })();

  // Landing: compose all modeled organs into the colored bodyscape (organs
  // stream in; the small pancreas GLB lands first and frames the view). Use
  // "None" then click rows to browse one at a time, or a row's "only" button.
  selectMany(modeledKeys, "all modeled organs");
}

main().catch((err) => { console.error(err); setStatus(`error: ${err?.message || err}`); });
