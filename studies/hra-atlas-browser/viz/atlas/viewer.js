// HRA Atlas Browser — self-contained three.js organ browser.
// Reads config.json -> {atlas, coverage, overview_glb, node_field}, then
// atlas.json (organ selector + model counts + BioModels links) and
// coverage.json (per-node covered flags). No build step; no query params.
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

const NOMODEL = 0x6b7480;

const els = {
  status: document.getElementById("status"),
  summary: document.getElementById("summary-line"),
  select: document.getElementById("organ-select"),
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

function populateSelect(organs) {
  els.select.innerHTML = "";
  for (const o of organs) {
    const opt = document.createElement("option");
    opt.value = o.key;
    opt.textContent = o.n_models
      ? `${o.label} — ${o.n_models} model${o.n_models > 1 ? "s" : ""}`
      : `${o.label} — no model`;
    els.select.appendChild(opt);
  }
}

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
  els.legendMax.textContent = String(atlas.max_models);
  els.summary.textContent =
    `${atlas.summary.n_modeled}/${atlas.summary.n_organs} organs modeled · ${atlas.summary.n_models_total} model links`;
  populateSelect(atlas.organs);

  // ---- scene ----
  const app = document.getElementById("app");
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0e1116);
  const camera = new THREE.PerspectiveCamera(45, innerWidth / innerHeight, 0.01, 10000);
  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(devicePixelRatio || 1);
  renderer.setSize(innerWidth, innerHeight);
  app.appendChild(renderer.domElement);
  scene.add(new THREE.AmbientLight(0xffffff, 0.65));
  const dir = new THREE.DirectionalLight(0xffffff, 0.8);
  dir.position.set(3, 5, 4);
  scene.add(dir);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  const loader = new GLTFLoader();

  let currentRoot = null;
  const meshes = [];

  function frameObject(root) {
    const box = new THREE.Box3().setFromObject(root);
    const size = box.getSize(new THREE.Vector3()).length() || 1;
    const center = box.getCenter(new THREE.Vector3());
    camera.position.copy(center).add(new THREE.Vector3(size, size * 0.6, size));
    camera.near = size / 100;
    camera.far = size * 100;
    camera.updateProjectionMatrix();
    controls.target.copy(center);
    controls.update();
  }

  // Load one organ's GLB, color it by the organ's model count, and outline
  // each sub-region mesh so regions read as distinct shapes.
  function loadOrgan(key) {
    const organ = organsByKey.get(key);
    if (!organ) return;
    renderBioModels(organ);
    const url = organ.glb.female || organ.glb.male;
    if (!url) { setStatus(`${organ.label}: no GLB asset`); return; }
    setStatus(`loading ${organ.label}…`);
    loader.load(url, (gltf) => {
      if (currentRoot) { scene.remove(currentRoot); }
      meshes.length = 0;
      currentRoot = gltf.scene;
      const color = countColor(organ.n_models, atlas.max_models);
      currentRoot.traverse((node) => {
        if (!node.isMesh) return;
        node.material = new THREE.MeshStandardMaterial({ color: color.clone() });
        const edges = new THREE.LineSegments(
          new THREE.EdgesGeometry(node.geometry, 30),
          new THREE.LineBasicMaterial({ color: 0x0e1116, transparent: true, opacity: 0.55 })
        );
        node.add(edges);
        node.userData.regionName = node.name;
        meshes.push(node);
      });
      scene.add(currentRoot);
      frameObject(currentRoot);
      setStatus(`${organ.label}: ${meshes.length} regions`);
    }, undefined, (err) => setStatus(`failed to load ${organ.label}: ${err?.message || err}`));
  }

  els.select.addEventListener("change", (e) => loadOrgan(e.target.value));

  // Hover: brighten the hovered region and show its name in the status line.
  const ray = new THREE.Raycaster();
  const ndc = new THREE.Vector2();
  let hovered = null;
  renderer.domElement.addEventListener("pointermove", (event) => {
    const rect = renderer.domElement.getBoundingClientRect();
    ndc.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    ndc.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
    ray.setFromCamera(ndc, camera);
    const hit = ray.intersectObjects(meshes, false)[0];
    if (hovered && hovered !== hit?.object) { hovered.material.emissive?.setHex(0x000000); }
    if (hit) {
      hovered = hit.object;
      hovered.material.emissive = new THREE.Color(0x2b3a44);
      const organ = organsByKey.get(els.select.value);
      setStatus(`${hovered.userData.regionName} · ${organ.label} (${organ.n_models} models)`);
    }
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

  // Landing: load the most-modeled organ (first in the sorted list).
  els.select.value = atlas.organs[0].key;
  loadOrgan(atlas.organs[0].key);
}

main().catch((err) => { console.error(err); setStatus(`error: ${err?.message || err}`); });
