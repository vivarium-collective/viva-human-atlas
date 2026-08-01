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

const NOMODEL = 0x6b7480;

const els = {
  status: document.getElementById("status"),
  summary: document.getElementById("summary-line"),
  list: document.getElementById("organ-list"),
  search: document.getElementById("organ-search"),
  btnAll: document.getElementById("btn-all"),
  btnNone: document.getElementById("btn-none"),
  selCount: document.getElementById("sel-count"),
  legendMax: document.getElementById("legend-max"),
  bpTitle: document.getElementById("bp-title"),
  bpSub: document.getElementById("bp-sub"),
  bpList: document.getElementById("biomodels-list"),
};
const setStatus = (t) => { if (els.status) els.status.textContent = t; };

// Sequential model-count color: grey at 0, dark->bright green up to max.
function countColor(n, max) {
  if (!n) return new THREE.Color(NOMODEL);
  const t = max > 1 ? Math.log1p(n) / Math.log1p(max) : 1; // log scale (pancreas dominates)
  const lo = new THREE.Color(0x22303a), hi = new THREE.Color(0x8fe6b0);
  return lo.clone().lerp(hi, 0.15 + 0.85 * t);
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
    a.innerHTML = `<div>${m.name}</div><div class="mid">${m.biomodel_id}</div>`;
    els.bpList.appendChild(a);
  }
}

async function main() {
  setStatus("loading config…");
  const cfg = await fetch("config.json").then((r) => r.json());
  const atlas = await fetch(cfg.atlas).then((r) => r.json());
  const organsByKey = new Map(atlas.organs.map((o) => [o.key, o]));
  const modeledKeys = atlas.organs.filter((o) => o.n_models > 0).map((o) => o.key);
  els.legendMax.textContent = String(atlas.max_models);
  els.summary.textContent =
    `${atlas.summary.n_modeled}/${atlas.summary.n_organs} organs modeled · ${atlas.summary.n_models_total} model links`;

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
    els.selCount.textContent = selected.size
      ? `${selected.size} shown` : "none shown";
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
    let models = 0;
    for (const k of selected) models += organsByKey.get(k).n_models;
    return `${selected.size} organ${selected.size === 1 ? "" : "s"} shown · ${models} model links`;
  }

  function resetPanel() {
    els.bpTitle.textContent = "Select an organ";
    els.bpSub.textContent = `${atlas.summary.n_modeled}/${atlas.summary.n_organs} organs modeled`;
    els.bpList.innerHTML = "";
  }

  // ---- left menu ----
  function buildMenu() {
    els.list.innerHTML = "";
    for (const o of atlas.organs) {
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
      els.list.appendChild(row);
      rows.set(o.key, row);
    }
  }

  buildMenu();
  els.search.addEventListener("input", () => {
    const q = els.search.value.trim().toLowerCase();
    for (const [, row] of rows) {
      row.style.display = !q || row.dataset.label.includes(q) ? "" : "none";
    }
  });
  els.btnAll.addEventListener("click", () => selectMany(modeledKeys, "all modeled organs"));
  els.btnNone.addEventListener("click", clearAll);

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
