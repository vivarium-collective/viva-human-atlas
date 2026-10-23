// HRA GLB Viewer — self-contained three.js analysis tool (HRA-3D Task D.3).
//
// No build step: three.js + its addons are pinned via the importmap in
// index.html (unpkg CDN). All data comes from sibling files discovered
// through `config.json` — there are no query params to parse:
//   config.json        -> {glb, organ, coverage, links, node_field}
//   <config.coverage>   -> {coverage: [{uberon, label, organ_glb, node_name,
//                            n_models, model_ids, covered}, ...],
//                            summary: {...}}
//   <config.links>      -> {links: [{biomodel_id, uberon, node_name,
//                            organ_glb, ...}], summary: {...}}  (optional)
//
// Scene nodes are matched to a coverage row primarily by the row's
// `node_field` value (`node_name` by default — the crosswalk's own GLB
// scene-node name, the most reliable key), case-insensitively: exact match
// first, then a normalized (lowercase, non-alnum stripped) match so minor
// naming-convention drift between the crosswalk and the exported GLB still
// lines up. If neither matches, fall back to substring matching against
// uberon / organ_glb / the node-field value, for GLBs whose node names don't
// line up with the crosswalk at all.
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

const COLOR_COVERED = 0x4caf78;
const COLOR_UNCOVERED = 0x6b7480;

const statusEl = document.getElementById("status");
const summaryEl = document.getElementById("summary-line");
const hoverPanel = document.getElementById("hover-panel");
const hoverLabel = document.getElementById("hp-label");
const hoverUberon = document.getElementById("hp-uberon");
const hoverModels = document.getElementById("hp-models");

function setStatus(text) {
  if (statusEl) statusEl.textContent = text;
}

// ---- coverage index: node-name (exact/normalized) -> row, with a
// uberon/organ_glb/node-field substring fallback --------------------------
function normalizeKey(value) {
  return String(value || "").toLowerCase().replace(/[^a-z0-9]/g, "");
}

function buildCoverageIndex(coverageData, nodeField) {
  const index = { exact: new Map(), normalized: new Map(), substring: new Map() };
  const rows = (coverageData && coverageData.coverage) || [];
  for (const row of rows) {
    addRowToIndex(index, row, nodeField);
  }
  return index;
}

function addRowToIndex(index, row, nodeField) {
  const nameKey = row[nodeField] != null ? row[nodeField] : row.node_name;
  if (nameKey) {
    const lower = String(nameKey).toLowerCase();
    if (!index.exact.has(lower)) index.exact.set(lower, row);
    const norm = normalizeKey(nameKey);
    if (!index.normalized.has(norm)) index.normalized.set(norm, row);
  }
  const keys = [row.uberon, row.organ_glb, row[nodeField]];
  for (const key of keys) {
    if (key && !index.substring.has(String(key))) index.substring.set(String(key), row);
  }
}

function lookupRow(index, name) {
  if (!name) return null;
  // 1. node-name match, case-insensitive: exact first, then normalized.
  const lower = String(name).toLowerCase();
  if (index.exact.has(lower)) return index.exact.get(lower);
  const norm = normalizeKey(name);
  if (index.normalized.has(norm)) return index.normalized.get(norm);
  // 2. fall back to a substring match against uberon/organ_glb/node-field
  // keys — GLB exporters sometimes suffix/prefix node names (e.g.
  // "VH_F_Liver_mesh") in ways normalization alone won't reconcile.
  for (const [key, row] of index.substring) {
    const keyLower = key.toLowerCase();
    if (lower.includes(keyLower) || keyLower.includes(lower)) return row;
  }
  return null;
}

async function main() {
  setStatus("loading config…");
  const cfg = await fetch("config.json").then((r) => r.json());

  setStatus("loading coverage…");
  const coverageData = await fetch(cfg.coverage).then((r) => r.json());

  let linksData = null;
  if (cfg.links) {
    try {
      linksData = await fetch(cfg.links).then((r) => r.json());
    } catch (err) {
      linksData = null; // links are optional — coverage alone still renders
    }
  }

  const nodeField = cfg.node_field || "node_name";
  const coverageIndex = buildCoverageIndex(coverageData, nodeField);
  // Merge in spatial links (also keyed by node_name/organ_glb/uberon) so a
  // hover can surface the linked model even if `coverage.json` alone
  // wouldn't carry it.
  if (linksData && Array.isArray(linksData.links)) {
    for (const row of linksData.links) {
      addRowToIndex(coverageIndex, row, nodeField);
    }
  }

  const summary = (coverageData && coverageData.summary) || {};
  if (summaryEl) {
    const parts = [];
    if (summary.n_as_covered != null && summary.n_as != null) {
      parts.push(`${summary.n_as_covered}/${summary.n_as} structures covered`);
    }
    if (summary.n_organs_glb_covered != null && summary.n_organs_glb != null) {
      parts.push(`${summary.n_organs_glb_covered}/${summary.n_organs_glb} organs covered`);
    }
    summaryEl.textContent = parts.length ? parts.join(" · ") : cfg.organ || "";
  }

  // ---- three.js scene ------------------------------------------------
  const app = document.getElementById("app");
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0e1116);

  const camera = new THREE.PerspectiveCamera(
    45,
    window.innerWidth / window.innerHeight,
    0.01,
    10000
  );
  camera.position.set(2, 2, 2);

  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(window.devicePixelRatio || 1);
  renderer.setSize(window.innerWidth, window.innerHeight);
  app.appendChild(renderer.domElement);

  scene.add(new THREE.AmbientLight(0xffffff, 0.6));
  const dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
  dirLight.position.set(3, 5, 4);
  scene.add(dirLight);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;

  const coveredMeshes = [];

  setStatus("loading model…");
  const loader = new GLTFLoader();
  loader.load(
    cfg.glb,
    (gltf) => {
      const root = gltf.scene;
      root.traverse((node) => {
        if (!node.isMesh) return;
        const row = lookupRow(coverageIndex, node.name) || lookupRow(coverageIndex, node.parent && node.parent.name);
        const covered = !!(row && row.covered) || (!!row && row.n_models > 0);
        const color = covered ? COLOR_COVERED : COLOR_UNCOVERED;
        // Clone so per-mesh coloring never mutates a material shared across
        // instances of the same source mesh.
        const material = new THREE.MeshStandardMaterial({ color });
        node.material = material;
        node.userData.hraRow = row;
        node.userData.hraCovered = covered;
        coveredMeshes.push(node);
      });
      scene.add(root);

      const box = new THREE.Box3().setFromObject(root);
      const size = box.getSize(new THREE.Vector3()).length() || 1;
      const center = box.getCenter(new THREE.Vector3());
      camera.position.copy(center).add(new THREE.Vector3(size, size * 0.6, size));
      camera.near = size / 100;
      camera.far = size * 100;
      camera.updateProjectionMatrix();
      controls.target.copy(center);
      controls.update();

      setStatus(`${coveredMeshes.length} meshes loaded`);
    },
    undefined,
    (err) => {
      setStatus(`failed to load GLB: ${err && err.message ? err.message : err}`);
    }
  );

  // ---- raycaster hover -------------------------------------------------
  const raycaster = new THREE.Raycaster();
  const pointerNdc = new THREE.Vector2();

  function showHover(row, name) {
    if (!hoverPanel) return;
    if (!row) {
      hoverPanel.hidden = true;
      return;
    }
    hoverLabel.textContent = row.label || row.name || name || "(unnamed)";
    hoverUberon.textContent = row.uberon ? `uberon: ${row.uberon}` : "";
    const nModels = row.n_models != null ? row.n_models : (row.model_ids ? row.model_ids.length : (row.biomodel_id ? 1 : 0));
    hoverModels.innerHTML = `models: <span class="num">${nModels}</span>`;
    hoverPanel.hidden = false;
  }

  function onPointerMove(event) {
    const rect = renderer.domElement.getBoundingClientRect();
    pointerNdc.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    pointerNdc.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
    raycaster.setFromCamera(pointerNdc, camera);
    const hits = raycaster.intersectObjects(coveredMeshes, false);
    if (!hits.length) {
      showHover(null);
      return;
    }
    const hit = hits[0].object;
    showHover(hit.userData.hraRow, hit.name);
  }
  renderer.domElement.addEventListener("pointermove", onPointerMove);

  window.addEventListener("resize", () => {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
  });

  function animate() {
    requestAnimationFrame(animate);
    controls.update();
    renderer.render(scene, camera);
  }
  animate();
}

main().catch((err) => {
  console.error(err);
  setStatus(`error: ${err && err.message ? err.message : err}`);
});
