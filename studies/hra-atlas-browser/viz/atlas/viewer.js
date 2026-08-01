// HRA Atlas Browser — self-contained three.js organ browser.
// Reads config.json -> {atlas, coverage, overview_glb, node_field}, then
// atlas.json (organ selector + model counts + BioModels links) and
// coverage.json (per-node coverage: node_name, uberon, n_models, model_ids,
// covered). No build step; no query params.
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
  const ov = document.createElement("option");
  ov.value = "__overview__";
  ov.textContent = "Overview (whole body)";
  els.select.appendChild(ov);
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

const normKey = (s) => String(s || "").toLowerCase().replace(/[^a-z0-9]/g, "");

// ---- coverage index: GLB mesh node name -> coverage.json row -------------
// Mirrors the model-coverage-3d viewer's exact->normalized node_name match:
// try the row's node_name verbatim first, then a normalized (lowercase,
// non-alnum stripped) match so minor naming-convention drift between the
// GLB export and the crosswalk still lines up. No substring fallback here —
// the coverage rows are keyed one-to-one by node_name, unlike the fuzzy
// organ-key substring matcher this replaces.
function buildCoverageIndex(coverageData) {
  const exact = new Map();
  const normalized = new Map();
  for (const row of (coverageData && coverageData.coverage) || []) {
    const name = row.node_name;
    if (!name) continue;
    if (!exact.has(name)) exact.set(name, row);
    const norm = normKey(name);
    if (!normalized.has(norm)) normalized.set(norm, row);
  }
  return { exact, normalized };
}

function lookupCoverageRow(index, nodeName) {
  if (!nodeName) return null;
  if (index.exact.has(nodeName)) return index.exact.get(nodeName);
  const norm = normKey(nodeName);
  if (index.normalized.has(norm)) return index.normalized.get(norm);
  return null;
}

// ---- uberon -> atlas organ, for drill-in + BioModels panel from a row ----
function buildUberonIndex(organs) {
  const m = new Map();
  for (const o of organs) {
    if (o.uberon && !m.has(o.uberon)) m.set(o.uberon, o);
  }
  return m;
}

async function main() {
  setStatus("loading config…");
  const cfg = await fetch("config.json").then((r) => r.json());
  const atlas = await fetch(cfg.atlas).then((r) => r.json());
  const coverageData = await fetch(cfg.coverage).then((r) => r.json());
  const organsByKey = new Map(atlas.organs.map((o) => [o.key, o]));
  const coverageIndex = buildCoverageIndex(coverageData);
  const uberonToOrgan = buildUberonIndex(atlas.organs);
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
  // Tracks which organ (or null == "whole body" summary) is currently shown
  // in the BioModels panel while in overview mode, so hover only re-renders
  // the panel DOM when the hovered organ actually changes.
  let panelOrgan = null;

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

  function resetWholeBodyPanel() {
    els.bpTitle.textContent = "Whole body";
    els.bpSub.textContent = `${atlas.summary.n_modeled}/${atlas.summary.n_organs} organs modeled`;
    els.bpList.innerHTML = "";
  }

  // Load one organ's GLB, color it by the organ's model count, and outline
  // each sub-region mesh so regions read as distinct shapes.
  function loadOrgan(key) {
    hovered = null;
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

  // Load the united whole-body GLB and color each mesh node by its matched
  // coverage.json row's n_models (the authoritative per-node crosswalk —
  // see buildCoverageIndex/lookupCoverageRow above). Three visual states:
  //   (a) no coverage row at all -> faint/low-opacity NOMODEL ("not in
  //       crosswalk", e.g. anatomy the GLB carries that HRA doesn't map)
  //   (b) row present but n_models===0 -> solid NOMODEL ("no model")
  //   (c) row present with n_models>0 -> the count gradient
  // Falls back to the top organ if there's no overview GLB configured or it
  // fails to load.
  function loadOverview(cfg, atlas) {
    hovered = null;
    if (!cfg.overview_glb) {
      els.select.value = atlas.organs[0].key;
      loadOrgan(atlas.organs[0].key);
      return;
    }
    resetWholeBodyPanel();
    panelOrgan = null;
    setStatus("loading whole-body overview…");
    loader.load(cfg.overview_glb, (gltf) => {
      if (currentRoot) scene.remove(currentRoot);
      meshes.length = 0;
      currentRoot = gltf.scene;
      let colored = 0;
      const organHits = new Set();
      currentRoot.traverse((node) => {
        if (!node.isMesh) return;
        const row = lookupCoverageRow(coverageIndex, node.name);
        const organ = row && row.uberon && uberonToOrgan.has(row.uberon)
          ? uberonToOrgan.get(row.uberon) : null;
        let color, opacity = 1;
        if (!row) {
          color = new THREE.Color(NOMODEL);
          opacity = 0.35;
        } else if (row.n_models > 0) {
          color = countColor(row.n_models, atlas.max_models);
          colored++;
        } else {
          color = new THREE.Color(NOMODEL);
        }
        node.material = new THREE.MeshStandardMaterial({
          color, transparent: opacity < 1, opacity,
        });
        const edges = new THREE.LineSegments(
          new THREE.EdgesGeometry(node.geometry, 30),
          new THREE.LineBasicMaterial({ color: 0x0e1116, transparent: true, opacity: 0.55 })
        );
        node.add(edges);
        node.userData.regionName = node.name;
        node.userData.coverageRow = row;
        node.userData.overviewOrgan = organ;
        if (organ) organHits.add(organ.key);
        meshes.push(node);
      });
      scene.add(currentRoot);
      frameObject(currentRoot);
      setStatus(`overview: ${colored} / ${meshes.length} nodes colored (${organHits.size} organs)`);
    }, undefined, () => {
      setStatus("overview GLB failed — showing top organ");
      els.select.value = atlas.organs[0].key;
      loadOrgan(atlas.organs[0].key);
    });
  }

  els.select.addEventListener("change", (e) => {
    if (e.target.value === "__overview__") loadOverview(cfg, atlas);
    else loadOrgan(e.target.value);
  });
  // clicking an organ in the overview drills into it
  renderer.domElement.addEventListener("click", () => {
    if (els.select.value !== "__overview__" || !hovered) return;
    const organ = hovered.userData.overviewOrgan;
    if (organ) { els.select.value = organ.key; loadOrgan(organ.key); }
  });

  // Hover: brighten the hovered region and show its name in the status line.
  // In overview mode, hovering a mapped organ also previews its BioModels
  // list in the side panel (before the click that drills into it); leaving
  // all meshes (or hovering an unmapped region) reverts the panel to the
  // "Whole body" summary. `panelOrgan` gates DOM rebuilds so hovering
  // around inside the SAME organ's regions doesn't re-render the panel.
  const ray = new THREE.Raycaster();
  const ndc = new THREE.Vector2();
  let hovered = null;
  renderer.domElement.addEventListener("pointermove", (event) => {
    const rect = renderer.domElement.getBoundingClientRect();
    ndc.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    ndc.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
    ray.setFromCamera(ndc, camera);
    const hit = ray.intersectObjects(meshes, false)[0];
    const hitObject = hit ? hit.object : null;
    if (hovered && hovered !== hitObject) hovered.material.emissive?.setHex(0x000000);
    hovered = hitObject;

    if (!hovered) {
      if (els.select.value === "__overview__" && panelOrgan !== null) {
        resetWholeBodyPanel();
        panelOrgan = null;
      }
      return;
    }
    hovered.material.emissive = new THREE.Color(0x2b3a44);
    if (els.select.value === "__overview__") {
      const organ = hovered.userData.overviewOrgan;
      if (organ) {
        if (panelOrgan !== organ) { renderBioModels(organ); panelOrgan = organ; }
        setStatus(`${organ.label} (${organ.n_models} model${organ.n_models === 1 ? "" : "s"})`);
      } else {
        if (panelOrgan !== null) { resetWholeBodyPanel(); panelOrgan = null; }
        const row = hovered.userData.coverageRow;
        setStatus(row
          ? `${hovered.userData.regionName} · ${row.n_models} model${row.n_models === 1 ? "" : "s"} (unmapped organ)`
          : `${hovered.userData.regionName} · not in crosswalk`);
      }
    } else {
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

  // Landing: default to the whole-body overview; loadOverview falls back to
  // the top organ (first in the sorted list) if there's no overview GLB or
  // it fails to load.
  els.select.value = "__overview__";
  loadOverview(cfg, atlas);
}

main().catch((err) => { console.error(err); setStatus(`error: ${err?.message || err}`); });
