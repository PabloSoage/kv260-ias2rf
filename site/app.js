import * as THREE from "./vendor/three-0.170.0/three.module.min.js";
import { OrbitControls } from "./vendor/three-0.170.0/OrbitControls.js";
import { GLTFLoader } from "./vendor/three-0.170.0/GLTFLoader.js";
import { RoomEnvironment } from "./vendor/three-0.170.0/RoomEnvironment.js";
import { MeshoptDecoder } from "./vendor/three-0.170.0/meshopt_decoder.module.js";
import { initMockups } from "./mockups.js";

const REPO_BLOB = "https://github.com/PabloSoage/kv260-ias2rf/blob/main";

// World registration constants (from docs/INTERFACE_SPEC.md & build_mount.py)
// Board KiCad origin -> Kria Y-up metres: (0.107247, 0.0008, -0.198004), rotY = -PI/2
const BOARD_REG_POS = new THREE.Vector3(0.107247, 0.0008, -0.198004);
const BOARD_REG_ROTY = -Math.PI / 2;

const GALLERY_SECTIONS = [
  {
    title: "G-8 End-to-End RF, SDR & FMCW Radar Simulations (FPGA -> DSP -> Demod)",
    items: [
      { src: "assets/img/sim/g8_overview.png", title: "G-8 Suite Overview", cap: "Cross-mode SNR, dynamic range and link verification across all 8 RF/radar paths." },
      { src: "assets/img/sim/g8_fm_broadcast.png", title: "WBFM 98.1 MHz Stereo + RDS", cap: "Polar discriminator, 19 kHz pilot lock, 38 kHz stereo separation and RBDS group decode." },
      { src: "assets/img/sim/g8_airband_am.png", title: "VHF Airband AM 121.5 MHz", cap: "Channelizer passband response, hang AGC attack/decay and ATIS voice recovery." },
      { src: "assets/img/sim/g8_hf_am.png", title: "HF Shortwave AM 7.1 MHz", cap: "Direct-sampling Nyquist-1 capture through 30 MHz roofing LPF and carrier-track demod." },
      { src: "assets/img/sim/g8_hf_ssb.png", title: "HF SSB (USB/LSB) 7.074 MHz", cap: "Phasing weaver demodulator > 55 dB opposite-sideband rejection on closely spaced tones." },
      { src: "assets/img/sim/g8_vhf_uhf_nbfm.png", title: "VHF / UHF NBFM + CTCSS", cap: "12.5 kHz FM discriminator output with Goertzel sub-audible CTCSS tone detection." },
      { src: "assets/img/sim/g8_adsb_1090.png", title: "ADS-B 1090 MHz Mode-S", cap: "8 us preamble match, Manchester bit slicer, CRC-24 validation and CPR aircraft decode." },
      { src: "assets/img/sim/g8_radar_rd_cfar.png", title: "10.5 GHz FMCW Range-Doppler", cap: "2-D range/velocity FFT across ADAR1000 beam CPI with CA-CFAR target extraction." },
      { src: "assets/img/sim/g8_tx_masks.png", title: "TX Spectral Masks (SSB & NBFM)", cap: "Adjacent-channel power and harmonic compliance gated behind hardware TX_KEY interlock." },
    ],
  },
  {
    title: "Vehicle & PL Integration Benchmarks (GPS PPS, Radar/LiDAR Fusion, CAN, SDR)",
    items: [
      { src: "assets/img/integrations/pps_discipline.png", title: "GPS PPS Si549 Discipline", cap: "R5F 0 servo locking kria_pps within 31 s (41 ns worst locked error, 120 s holdover)." },
      { src: "assets/img/integrations/radar_grid_e2e.png", title: "PL BEV Fusion Grid (kria_bev_grid)", cap: "100 M cell updates/s RTL vs reference combining 10.5 GHz radar, 77 GHz radar and LiDAR." },
      { src: "assets/img/integrations/bev_fusion_fog.png", title: "All-Weather BEV Fusion in Fog", cap: "LiDAR range collapse in heavy fog bridged seamlessly by 10.5 GHz & 77 GHz radar returns." },
      { src: "assets/img/integrations/fog_ranges.png", title: "Detection Range vs Visibility", cap: "Optical LiDAR vs X-band / W-band radar detection range curves across fog density." },
      { src: "assets/img/integrations/radar_bus_load.png", title: "77 GHz Radar Bus Utilization", cap: "Classic CAN vs CAN FD vs 100BASE-T1 bus utilization for 20 Hz object lists." },
      { src: "assets/img/integrations/telemetry_e2e.png", title: "Vehicle Telemetry -> TX_KEY Lock", cap: "Montero V80 CAN 2.0 & opendash latency, stale expiry and fail-safe TX lockout." },
      { src: "assets/img/integrations/kraken_doa_e2e.png", title: "KrakenSDR 5-Ch Coherent DoA", cap: "PL Bartlett scan + A53 MUSIC bearing estimator verified end to end over USB 2.0." },
      { src: "assets/img/integrations/hackrf_sweep_e2e.png", title: "HackRF Pro 0-7.2 GHz Sweep", cap: "PL averaging FFT panorama pipeline at 1,220 blocks/s with TX interlock check." },
    ],
  },
  {
    title: "Rev08 Hardware & Closed-Case v2 Mechanical Renders",
    items: [
      { src: "assets/img/board_iso.png", title: "Rev08 Adapter Isometric Render", cap: "calibrated soldermask, ENIG copper pads, SMAs, XC7A50T, AD9484 and Si549 clock tree." },
      { src: "assets/img/board_top.png", title: "Rev08 Top Side (RF & Converters)", cap: "Front SMA launch panel, ADAR1000 header, DAC/ADC banks and Artix-7 FPGA." },
      { src: "assets/img/board_bottom.png", title: "Rev08 Bottom Side (KV260 Mate)", cap: "J101/J102/J103 IAS/RPi plugs, J1501 USB-C, J1502 J9 FFC, J1503 CAN+PPS & RJ45." },
      { src: "assets/img/case_v2_closed.jpg", title: "Closed Enclosure v2 (PETG-CF + TPU)", cap: "Dual-fan intake/exhaust enclosure with printable filter frame and corner bumpers." },
      { src: "assets/img/case_v2_open.jpg", title: "Closed Enclosure v2 (Open Service View)", cap: "Internal heatsink clearance, dual OD5015 lid fan and captive connector exits." },
    ],
  },
];

// Global application state
const state = {
  ready: false,
  tab: "explorer",
  theme: "dark",
  explodePct: 0,
  enclosureMode: "closed", // closed | open | hidden
  showKvFan: true,
  showKvHs: true,
  somLiftMm: 0,
  isolateMode: "all", // all | board | kv260 | thermal | enclosure
  selectedId: null,
  activeNet: null,
};

let catalogue = null;
const partById = new Map();
const nodeById = new Map();
const compByNet = new Map();

// Main 3-D viewport objects
let renderer, scene, camera, controls;
const assemblyRoot = new THREE.Group();
const adapterGroup = new THREE.Group();
let boardModel = null;
let kv260Model = null;
let enclosureModel = null;
const kvNodes = {};
const encNodes = {};
let hoverBox = null;
let selectBox = null;
const netHighlightGroup = new THREE.Group();

// Layer viewer objects
let layerRenderer, layerScene, layerCamera, layerControls;
const layerPlanesGroup = new THREE.Group();
const layerEntries = [];
let layerActiveId = "F.Cu";
let l2dZoom = 1.0;
let l2dPan = { x: 0, y: 0 };

// Wait helpers
function $(sel) {
  return document.querySelector(sel);
}

function escapeHtml(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// ---------------------------------------------------------------------------
// Initialisation
// ---------------------------------------------------------------------------

async function boot() {
  initMockups($("#mockups-root"));
  renderGallery();
  wireUiEvents();

  const resp = await fetch("assets/components.json");
  if (!resp.ok) throw new Error(`Failed loading components.json: ${resp.status}`);
  catalogue = await resp.json();
  indexCatalogue(catalogue);

  initExplorerThree();
  await loadModels();
  initLayerViewer();

  applyAssemblyTransforms();
  updateStatsPill();
  $("#loading-overlay").classList.add("hidden");
  state.ready = true;
}

function indexCatalogue(cat) {
  for (const c of cat.components) {
    partById.set(c.ref, { kind: "board", data: c });
    for (const net of c.nets || []) {
      if (!compByNet.has(net)) compByNet.set(net, []);
      compByNet.get(net).push(c.ref);
    }
  }
  for (const k of cat.kv260_parts) {
    partById.set(k.id, { kind: k.subassembly === "cooling" ? "kv_cooling" : "kv260", data: k });
  }
  for (const ex of cat.extra_parts || []) {
    partById.set(ex.id, { kind: "extra", data: ex });
  }
}

// ---------------------------------------------------------------------------
// Three.js Explorer Setup & Lighting (calibrated materials + RoomEnvironment)
// ---------------------------------------------------------------------------

function initExplorerThree() {
  const canvas = $("#webgl-canvas");
  renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: "high-performance" });
  renderer.setClearColor(0x000000, 0);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;

  scene = new THREE.Scene();
  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
  scene.environmentIntensity = 0.85;
  pmrem.dispose();

  const hemi = new THREE.HemisphereLight(0xdbe8f8, 0x1a2029, 0.55);
  scene.add(hemi);

  const keyLight = new THREE.DirectionalLight(0xfff8ef, 1.35);
  keyLight.position.set(0.45, 0.78, 0.52);
  scene.add(keyLight);

  const rimLight = new THREE.DirectionalLight(0x9bc4ff, 0.52);
  rimLight.position.set(-0.55, 0.35, -0.52);
  scene.add(rimLight);

  const botLight = new THREE.DirectionalLight(0xeef4fc, 0.38);
  botLight.position.set(0.05, -0.85, 0.25);
  scene.add(botLight);

  camera = new THREE.PerspectiveCamera(38, 16 / 10, 0.005, 4.0);
  camera.position.set(-0.22, 0.19, 0.24);

  controls = new OrbitControls(camera, canvas);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.minDistance = 0.025;
  controls.maxDistance = 1.2;

  adapterGroup.position.copy(BOARD_REG_POS);
  adapterGroup.rotation.y = BOARD_REG_ROTY;

  assemblyRoot.add(adapterGroup);
  scene.add(assemblyRoot);
  scene.add(netHighlightGroup);

  hoverBox = new THREE.Box3Helper(new THREE.Box3(), 0x4cc2ff);
  hoverBox.visible = false;
  scene.add(hoverBox);

  selectBox = new THREE.Box3Helper(new THREE.Box3(), 0xffb020);
  selectBox.visible = false;
  scene.add(selectBox);

  const resizeExplorer = () => {
    const wrap = canvas.parentElement;
    if (!wrap) return;
    const w = Math.max(100, wrap.clientWidth);
    const h = Math.max(100, wrap.clientHeight);
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  };
  canvas._resizeFn = resizeExplorer;
  new ResizeObserver(resizeExplorer).observe(canvas.parentElement);
  resizeExplorer();

  wireViewportPicking(canvas);

  const tick = () => {
    requestAnimationFrame(tick);
    if (state.tab === "explorer") {
      controls.update();
      renderer.render(scene, camera);
    }
  };
  requestAnimationFrame(tick);
}

async function loadModels() {
  const loader = new GLTFLoader();
  loader.setMeshoptDecoder(MeshoptDecoder);
  const loadGlb = (url) => new Promise((res, rej) => loader.load(url, res, undefined, rej));

  const [bGltf, kGltf, eGltf] = await Promise.all([
    loadGlb("assets/board.glb"),
    loadGlb("assets/kv260.glb"),
    loadGlb("assets/enclosure.glb"),
  ]);

  boardModel = bGltf.scene;
  adapterGroup.add(boardModel);

  kv260Model = kGltf.scene;
  assemblyRoot.add(kv260Model);

  enclosureModel = eGltf.scene;
  assemblyRoot.add(enclosureModel);

  // Index selectable Object3D nodes by exact ID/Ref
  const collect = (root) => {
    root.traverse((obj) => {
      if (obj.name && partById.has(obj.name) && !nodeById.has(obj.name)) {
        nodeById.set(obj.name, obj);
      }
      if (obj.name && (obj.name.startsWith("KV260_") || obj.name.startsWith("K26_") || obj.name.startsWith("SOM240_"))) {
        kvNodes[obj.name] = obj;
      }
      if (obj.name && (obj.name.startsWith("ENCLOSURE_") || obj.name.startsWith("ADAPTER_") || obj.name.startsWith("CASE_") || obj.name === "FAN2_5015")) {
        encNodes[obj.name] = obj;
      }
    });
  };
  collect(boardModel);
  collect(kv260Model);
  collect(enclosureModel);

  setCameraPreset("iso");
}

// ---------------------------------------------------------------------------
// Explode, Teardown, Isolate & Camera Framing
// ---------------------------------------------------------------------------

function applyAssemblyTransforms() {
  const t = state.explodePct / 100;
  const somOffset = state.somLiftMm * 0.001 + 0.028 * t;
  const showEnc = state.isolateMode === "all" || state.isolateMode === "enclosure";
  const showBoard = state.isolateMode === "all" || state.isolateMode === "board";
  const showKv = state.isolateMode === "all" || state.isolateMode === "kv260";
  const showThermal = state.isolateMode === "all" || state.isolateMode === "thermal";

  adapterGroup.visible = showBoard;
  adapterGroup.position.set(BOARD_REG_POS.x, BOARD_REG_POS.y + 0.072 * t, BOARD_REG_POS.z);

  if (kv260Model) {
    kv260Model.visible = showKv || state.isolateMode === "thermal";
  }
  if (kvNodes.KV260_CARRIER_GROUP) kvNodes.KV260_CARRIER_GROUP.visible = showKv;
  if (kvNodes.K26_SOM_GROUP) {
    kvNodes.K26_SOM_GROUP.visible = showKv;
    kvNodes.K26_SOM_GROUP.position.y = somOffset;
  }
  if (kvNodes.KV260_COOLING_GROUP) {
    kvNodes.KV260_COOLING_GROUP.visible = showKv || showThermal;
    kvNodes.KV260_COOLING_GROUP.position.y = somOffset + 0.040 * t;
  }
  if (kvNodes.KV260_FAN) kvNodes.KV260_FAN.visible = state.showKvFan && (showKv || showThermal);
  if (kvNodes.KV260_HEATSINK) kvNodes.KV260_HEATSINK.visible = state.showKvHs && (showKv || showThermal);

  if (enclosureModel) {
    enclosureModel.visible = showEnc || showThermal;
  }
  const caseVis = showEnc && state.enclosureMode !== "hidden";
  if (encNodes.ENCLOSURE_BOTTOM_GROUP) {
    encNodes.ENCLOSURE_BOTTOM_GROUP.visible = caseVis;
    encNodes.ENCLOSURE_BOTTOM_GROUP.position.y = -0.045 * t;
  }
  if (encNodes.ENCLOSURE_BUMPERS_GROUP) {
    encNodes.ENCLOSURE_BUMPERS_GROUP.visible = caseVis;
    encNodes.ENCLOSURE_BUMPERS_GROUP.position.y = -0.025 * t;
  }
  if (encNodes.ENCLOSURE_LID_GROUP) {
    const lidOpenOffset = state.enclosureMode === "open" ? 0.085 : 0.0;
    encNodes.ENCLOSURE_LID_GROUP.visible = caseVis;
    encNodes.ENCLOSURE_LID_GROUP.position.y = lidOpenOffset + 0.150 * t;
  }
  if (encNodes.ADAPTER_HEATSINKS_GROUP) {
    encNodes.ADAPTER_HEATSINKS_GROUP.visible = showThermal;
    encNodes.ADAPTER_HEATSINKS_GROUP.position.y = 0.105 * t;
  }

  scene.updateMatrixWorld(true);
  updateSelectionBox();
  rebuildNetHighlightBoxes();
}

function getActiveBounds() {
  const box = new THREE.Box3();
  const candidates = [];
  if (adapterGroup.visible) candidates.push(adapterGroup);
  if (kvNodes.KV260_CARRIER_GROUP?.visible) candidates.push(kvNodes.KV260_CARRIER_GROUP);
  if (kvNodes.K26_SOM_GROUP?.visible) candidates.push(kvNodes.K26_SOM_GROUP);
  if (kvNodes.KV260_COOLING_GROUP?.visible && (kvNodes.KV260_FAN?.visible || kvNodes.KV260_HEATSINK?.visible)) {
    candidates.push(kvNodes.KV260_COOLING_GROUP);
  }
  if (encNodes.ENCLOSURE_BOTTOM_GROUP?.visible) candidates.push(encNodes.ENCLOSURE_BOTTOM_GROUP);
  if (encNodes.ENCLOSURE_LID_GROUP?.visible) candidates.push(encNodes.ENCLOSURE_LID_GROUP);
  if (encNodes.ADAPTER_HEATSINKS_GROUP?.visible) candidates.push(encNodes.ADAPTER_HEATSINKS_GROUP);

  for (const obj of candidates) box.expandByObject(obj);
  if (box.isEmpty()) box.set(new THREE.Vector3(-0.08, -0.02, -0.12), new THREE.Vector3(0.14, 0.06, 0.03));
  return box;
}

function setCameraPreset(preset) {
  scene.updateMatrixWorld(true);
  const box = getActiveBounds();
  const center = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3());
  const span = Math.max(size.x, size.y, size.z, 0.08);
  const dist = span * 1.48;

  const dirs = {
    iso: new THREE.Vector3(-0.72, 0.62, 0.78),
    reset: new THREE.Vector3(-0.72, 0.62, 0.78),
    top: new THREE.Vector3(0.0, 1.0, 0.04),
    bottom: new THREE.Vector3(0.0, -1.0, 0.04),
    front: new THREE.Vector3(-1.0, 0.28, 0.08),
    back: new THREE.Vector3(1.0, 0.30, -0.08),
  };
  const d = (dirs[preset] || dirs.iso).clone().normalize();
  controls.target.copy(center);
  camera.position.copy(center).addScaledVector(d, dist);
  controls.update();
}

function focusPartCamera(id) {
  const obj = nodeById.get(id);
  if (!obj) return;
  scene.updateMatrixWorld(true);
  const box = new THREE.Box3().setFromObject(obj);
  if (box.isEmpty()) return;
  const center = box.getCenter(new THREE.Vector3());
  const sz = box.getSize(new THREE.Vector3());
  const dist = Math.max(Math.max(sz.x, sz.y, sz.z) * 2.8, 0.045);
  const dir = camera.position.clone().sub(controls.target).normalize();
  if (dir.lengthSq() < 0.01) dir.set(-0.5, 0.7, 0.6).normalize();
  controls.target.copy(center);
  camera.position.copy(center).addScaledVector(dir, dist);
  controls.update();
}

// ---------------------------------------------------------------------------
// Raycasting, Hover Tooltip, Tap Selection & Inspector Rendering
// ---------------------------------------------------------------------------

function resolvePartHit(hits) {
  for (let i = 0; i < hits.length; i++) {
    const h = hits[i];
    if (!h.object.visible) continue;
    let cur = h.object;
    while (cur) {
      if (cur.name && partById.has(cur.name)) {
        return { id: cur.name, object: nodeById.get(cur.name) || cur };
      }
      cur = cur.parent;
    }
    // If closest hit is soldermask/silkscreen, allow next hit within 0.2 mm behind it
    const nm = h.object.name || "";
    if ((nm === "PCB_LAYER_SOLDERMASK" || nm === "PCB_LAYER_SILKSCREEN") && hits[i + 1] && hits[i + 1].distance - h.distance < 0.002) {
      continue;
    }
    // Otherwise opaque PCB core / carrier / case blocks rear items
    return null;
  }
  return null;
}

function wireViewportPicking(canvas) {
  const raycaster = new THREE.Raycaster();
  const pointer = new THREE.Vector2();
  const tip = $("#hover-tooltip");
  let downPos = null;

  const setPointer = (ev) => {
    const rect = canvas.getBoundingClientRect();
    pointer.x = ((ev.clientX - rect.left) / rect.width) * 2 - 1;
    pointer.y = -((ev.clientY - rect.top) / rect.height) * 2 + 1;
    return rect;
  };

  canvas.addEventListener("pointermove", (ev) => {
    if (!state.ready) return;
    const rect = setPointer(ev);
    raycaster.setFromCamera(pointer, camera);
    const hits = raycaster.intersectObject(assemblyRoot, true);
    const found = resolvePartHit(hits);
    if (found && found.object) {
      const entry = partById.get(found.id);
      const label = entry.kind === "board"
        ? `${entry.data.ref} &middot; ${escapeHtml(entry.data.value)}`
        : `${entry.data.ref || entry.data.id} &middot; ${escapeHtml(entry.data.part || entry.data.value)}`;
      const role = entry.kind === "board"
        ? entry.data.description
        : entry.data.role;
      tip.innerHTML = `<strong>${label}</strong><br><span style="color:var(--text-muted)">${escapeHtml((role || "").slice(0, 88))}</span>`;
      tip.style.left = `${Math.min(rect.width - 210, Math.max(8, ev.clientX - rect.left + 12))}px`;
      tip.style.top = `${Math.min(rect.height - 65, Math.max(8, ev.clientY - rect.top + 12))}px`;
      tip.style.display = "block";
      hoverBox.box.setFromObject(found.object);
      hoverBox.visible = !hoverBox.box.isEmpty();
      canvas.style.cursor = "pointer";
    } else {
      tip.style.display = "none";
      hoverBox.visible = false;
      canvas.style.cursor = "grab";
    }
  });

  canvas.addEventListener("pointerleave", () => {
    tip.style.display = "none";
    hoverBox.visible = false;
  });

  canvas.addEventListener("pointerdown", (ev) => {
    downPos = { x: ev.clientX, y: ev.clientY };
  });

  canvas.addEventListener("pointerup", (ev) => {
    if (!downPos || !state.ready) return;
    const moved = Math.hypot(ev.clientX - downPos.x, ev.clientY - downPos.y);
    downPos = null;
    if (moved > 5) return; // orbit drag, not a tap
    setPointer(ev);
    raycaster.setFromCamera(pointer, camera);
    const found = resolvePartHit(raycaster.intersectObject(assemblyRoot, true));
    if (found) selectPart(found.id, false);
  });

  canvas.addEventListener("dblclick", (ev) => {
    if (!state.ready) return;
    setPointer(ev);
    raycaster.setFromCamera(pointer, camera);
    const hits = raycaster.intersectObject(assemblyRoot, true);
    if (!hits.length) {
      setIsolate("all");
      return;
    }
    let cur = hits[0].object;
    while (cur) {
      if (cur === adapterGroup) { setIsolate(state.isolateMode === "board" ? "all" : "board"); return; }
      if (cur === kv260Model) { setIsolate(state.isolateMode === "kv260" ? "all" : "kv260"); return; }
      if (cur === encNodes.ADAPTER_HEATSINKS_GROUP) { setIsolate(state.isolateMode === "thermal" ? "all" : "thermal"); return; }
      if (cur === enclosureModel) { setIsolate(state.isolateMode === "enclosure" ? "all" : "enclosure"); return; }
      cur = cur.parent;
    }
  });
}

function updateSelectionBox() {
  if (!state.selectedId) {
    selectBox.visible = false;
    return;
  }
  const obj = nodeById.get(state.selectedId);
  if (!obj || !isObjectEffectivelyVisible(obj)) {
    selectBox.visible = false;
    return;
  }
  selectBox.box.setFromObject(obj);
  selectBox.visible = !selectBox.box.isEmpty();
}

function isObjectEffectivelyVisible(obj) {
  let c = obj;
  while (c) {
    if (!c.visible) return false;
    c = c.parent;
  }
  return true;
}

function rebuildNetHighlightBoxes() {
  while (netHighlightGroup.children.length) netHighlightGroup.remove(netHighlightGroup.children[0]);
  if (!state.activeNet || !adapterGroup.visible) return;
  const refs = compByNet.get(state.activeNet) || [];
  for (const ref of refs) {
    const obj = nodeById.get(ref);
    if (!obj) continue;
    const bx = new THREE.Box3().setFromObject(obj);
    if (!bx.isEmpty()) {
      netHighlightGroup.add(new THREE.Box3Helper(bx, 0x4cc2ff));
    }
  }
}

function selectPart(id, shouldFocus = true) {
  const entry = partById.get(id);
  if (!entry) return;
  state.selectedId = id;
  updateSelectionBox();
  if (shouldFocus) focusPartCamera(id);

  // Open mobile inspector drawer cleanly
  $("#inspector-empty").style.display = "none";
  const body = $("#inspector-body");
  body.style.display = "flex";

  if (entry.kind === "board") {
    const c = entry.data;
    const padRows = Object.entries(c.pads || {}).slice(0, 28).map(
      ([pin, net]) => `<tr><td class="mono">${escapeHtml(pin)}</td><td><button type="button" class="net-chip ${state.activeNet === net ? "active" : ""}" data-net="${escapeHtml(net)}">${escapeHtml(net)}</button></td></tr>`
    ).join("");
    const netButtons = (c.nets || []).map(
      (n) => `<button type="button" class="net-chip ${state.activeNet === n ? "active" : ""}" data-net="${escapeHtml(n)}">${escapeHtml(n)}</button>`
    ).join("");

    body.innerHTML = `
      <div class="panel-card">
        <div class="control-row">
          <span class="badge">REV08 ADAPTER</span>
          <span class="mono" style="color:var(--text-muted)">${escapeHtml(c.side)} &middot; ${escapeHtml(c.sheet || "-")}</span>
        </div>
        <h2 style="margin:0;font-size:17px;">${escapeHtml(c.ref)} <small style="font-weight:500;color:var(--text-muted)">${escapeHtml(c.value)}</small></h2>
        <p style="margin:0;font-size:12px;">${escapeHtml(c.description || "no description yet")}</p>
        ${c.callout ? `<p style="margin:0;font-size:11px;color:var(--cyan)"><strong>Manual callout:</strong> ${escapeHtml(c.callout)}</p>` : ""}
        <div class="btn-grid">
          <button id="insp-focus-btn" class="btn btn-sm btn-primary" type="button">Focus Camera</button>
          <a class="btn btn-sm" style="text-align:center" href="${REPO_BLOB}/${encodeURI(c.manual_link || "docs/BOARD_MANUAL.md")}" target="_blank" rel="noopener">Open Manual</a>
        </div>
      </div>

      <div class="panel-card">
        <h3>Specifications</h3>
        <table class="kv-table">
          <tr><th>Footprint</th><td class="mono">${escapeHtml(c.footprint)}</td></tr>
          <tr><th>MPN / Mfg</th><td>${escapeHtml(c.mpn || "-")} ${c.manufacturer ? `(${escapeHtml(c.manufacturer)})` : ""}</td></tr>
          <tr><th>LCSC / Stock</th><td class="mono">${escapeHtml(c.lcsc || "-")} ${c.dnp ? "[DNP]" : ""}</td></tr>
          <tr><th>KiCad Pos</th><td class="mono">(${c.x_mm}, ${c.y_mm}) mm &middot; ${c.rot_deg}&deg;</td></tr>
          <tr><th>3-D Source</th><td class="mono">${escapeHtml(c.model_source)}</td></tr>
        </table>
      </div>

      <div class="panel-card">
        <div class="control-row">
          <h3>Nets (${(c.nets || []).length})</h3>
          ${state.activeNet ? `<button id="insp-clear-net" class="btn btn-sm" type="button">Clear Net</button>` : ""}
        </div>
        <div class="net-list">${netButtons || '<span style="color:var(--text-muted)">No connected nets</span>'}</div>
        ${state.activeNet ? `<div id="insp-net-mates" style="font-size:11px;color:var(--cyan);"></div>` : ""}
      </div>

      ${padRows ? `
      <div class="panel-card">
        <h3>Pinout / Pads (${Object.keys(c.pads || {}).length})</h3>
        <table class="kv-table"><thead><tr><th>Pin</th><th>Net</th></tr></thead><tbody>${padRows}</tbody></table>
      </div>` : ""}
    `;

    if (state.activeNet) {
      const siblings = (compByNet.get(state.activeNet) || []).slice(0, 12);
      const mateBox = body.querySelector("#insp-net-mates");
      if (mateBox) {
        mateBox.innerHTML = `Connected on <code>${escapeHtml(state.activeNet)}</code> (${(compByNet.get(state.activeNet) || []).length} parts): ` +
          siblings.map((r) => `<button type="button" class="net-chip pick-ref" data-ref="${escapeHtml(r)}">${escapeHtml(r)}</button>`).join(" ");
        mateBox.querySelectorAll(".pick-ref").forEach((b) => b.addEventListener("click", () => selectPart(b.dataset.ref, true)));
      }
    }
  } else {
    const k = entry.data;
    const isKv = entry.kind !== "extra";
    body.innerHTML = `
      <div class="panel-card">
        <div class="control-row">
          <span class="badge ${isKv ? "badge-cyan" : ""}">${isKv ? `KV260 ${(k.subassembly || "").toUpperCase()}` : "THERMAL HARDWARE"}</span>
          <span class="mono" style="color:var(--text-muted)">${escapeHtml(k.id)}</span>
        </div>
        <h2 style="margin:0;font-size:17px;">${escapeHtml(k.ref)} <small style="font-weight:500;color:var(--text-muted)">${escapeHtml(k.part || k.value)}</small></h2>
        <p style="margin:0;font-size:12px;">${escapeHtml(k.role || "")}</p>
        <div class="btn-grid">
          <button id="insp-focus-btn" class="btn btn-sm btn-primary" type="button">Focus Camera</button>
          <a class="btn btn-sm" style="text-align:center" href="${REPO_BLOB}/${encodeURI(k.manual_link || "docs/INTERFACE_SPEC.md")}" target="_blank" rel="noopener">Open Citation / Spec</a>
        </div>
      </div>

      <div class="panel-card">
        <h3>Mechanical &amp; Source Citations</h3>
        <table class="kv-table">
          <tr><th>BBox (mm)</th><td class="mono">[${(k.bbox_mm || []).join(", ")}]</td></tr>
          <tr><th>Citation</th><td>${escapeHtml(k.citation || "Simplified project-authored model (AMD XTP679 not redistributed)")}</td></tr>
        </table>
      </div>
    `;
  }

  body.querySelector("#insp-focus-btn")?.addEventListener("click", () => focusPartCamera(id));
  body.querySelector("#insp-clear-net")?.addEventListener("click", () => {
    state.activeNet = null;
    rebuildNetHighlightBoxes();
    selectPart(id, false);
  });
  body.querySelectorAll("[data-net]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.activeNet = state.activeNet === btn.dataset.net ? null : btn.dataset.net;
      rebuildNetHighlightBoxes();
      selectPart(id, false);
    });
  });

  $("#hud-status").innerHTML = `Selected <strong>${escapeHtml(id)}</strong>`;
}

// ---------------------------------------------------------------------------
// 8-Layer PCB Stack-up 3-D + 2-D SVG Viewer
// ---------------------------------------------------------------------------

function svgToCanvasTexture(svgText, hexColor) {
  return new Promise((resolve) => {
    const img = new Image();
    const blob = new Blob([svgText], { type: "image/svg+xml;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    img.onload = () => {
      const cvs = document.createElement("canvas");
      cvs.width = 1600;
      cvs.height = 1500;
      const ctx = cvs.getContext("2d");
      ctx.drawImage(img, 0, 0, cvs.width, cvs.height);
      ctx.globalCompositeOperation = "source-in";
      ctx.fillStyle = hexColor;
      ctx.fillRect(0, 0, cvs.width, cvs.height);
      ctx.globalCompositeOperation = "destination-over";
      ctx.fillStyle = "rgba(24, 34, 46, 0.22)";
      ctx.fillRect(0, 0, cvs.width, cvs.height);
      ctx.globalCompositeOperation = "source-over";
      URL.revokeObjectURL(url);
      const tex = new THREE.CanvasTexture(cvs);
      tex.colorSpace = THREE.SRGBColorSpace;
      tex.needsUpdate = true;
      resolve(tex);
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      resolve(null);
    };
    img.src = url;
  });
}

async function initLayerViewer() {
  const listEl = $("#layer-list");
  const allLayers = [
    ...catalogue.layer_stack,
    { id: "B.Mask", name: "Bottom Soldermask", color: "#2d7d3a" },
    { id: "B.SilkS", name: "Bottom Silkscreen", color: "#d6dbe0" },
  ];

  // Build 3-D Layer WebGL scene
  const canvas = $("#layer-webgl-canvas");
  layerRenderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
  layerRenderer.setClearColor(0x000000, 0);
  layerRenderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  layerRenderer.outputColorSpace = THREE.SRGBColorSpace;

  layerScene = new THREE.Scene();
  layerScene.add(new THREE.AmbientLight(0xffffff, 1.0));
  layerCamera = new THREE.PerspectiveCamera(36, 16 / 9, 0.005, 4.0);
  layerCamera.position.set(0.14, 0.14, 0.16);
  layerControls = new OrbitControls(layerCamera, canvas);
  layerControls.enableDamping = true;
  layerScene.add(layerPlanesGroup);

  const resizeLayers = () => {
    const wrap = canvas.parentElement;
    if (!wrap) return;
    const w = Math.max(100, wrap.clientWidth);
    const h = Math.max(100, wrap.clientHeight);
    layerRenderer.setSize(w, h, false);
    layerCamera.aspect = w / h;
    layerCamera.updateProjectionMatrix();
  };
  canvas._resizeFn = resizeLayers;
  new ResizeObserver(resizeLayers).observe(canvas.parentElement);
  resizeLayers();

  const wM = (catalogue.board_outline.width_mm || 141.55) * 0.001;
  const hM = (catalogue.board_outline.height_mm || 132.55) * 0.001;
  const geom = new THREE.PlaneGeometry(wM, hM);
  geom.rotateX(-Math.PI / 2);

  for (let i = 0; i < allLayers.length; i++) {
    const L = allLayers[i];
    L.svgPath = L.svg || `assets/layers/${L.id.replace(/\./g, "_")}.svg`;
    let tex = null;
    try {
      const r = await fetch(L.svgPath);
      if (r.ok) tex = await svgToCanvasTexture(await r.text(), L.color);
    } catch (_) { /* ignore */ }

    const mat = new THREE.MeshBasicMaterial({
      map: tex,
      color: tex ? 0xffffff : L.color,
      transparent: true,
      opacity: 0.85,
      side: THREE.DoubleSide,
      depthWrite: false,
    });
    const mesh = new THREE.Mesh(geom, mat);
    layerPlanesGroup.add(mesh);

    const entry = { meta: L, mesh, visible: true, index: i };
    layerEntries.push(entry);

    const row = document.createElement("div");
    row.className = `layer-row ${L.id === layerActiveId ? "active" : ""}`;
    row.dataset.layerId = L.id;
    row.innerHTML = `
      <div style="display:flex;align-items:center;gap:7px;min-width:0;">
        <span class="layer-swatch" style="background:${L.color}"></span>
        <span style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;"><strong>${escapeHtml(L.id)}</strong> &middot; ${escapeHtml(L.name)}</span>
      </div>
      <input type="checkbox" checked aria-label="Toggle ${escapeHtml(L.id)}">
    `;
    row.querySelector("input").addEventListener("change", (ev) => {
      ev.stopPropagation();
      entry.visible = ev.target.checked;
      updateLayerStackVisuals();
    });
    row.addEventListener("click", () => select2dLayer(L.id));
    listEl.appendChild(row);
  }

  updateLayerStackVisuals();
  select2dLayer("F.Cu");

  const tickLayers = () => {
    requestAnimationFrame(tickLayers);
    if (state.tab === "layers") {
      layerControls.update();
      layerRenderer.render(layerScene, layerCamera);
    }
  };
  requestAnimationFrame(tickLayers);
}

function updateLayerStackVisuals() {
  const spreadM = Number($("#range-layer-spread").value) * 0.001;
  const op = Number($("#range-layer-opacity").value) / 100;
  $("#val-layer-spread").textContent = `${Number($("#range-layer-spread").value).toFixed(1)} mm`;
  $("#val-layer-opacity").textContent = `${Math.round(op * 100)}%`;

  const mid = (layerEntries.length - 1) / 2;
  layerEntries.forEach((e, i) => {
    e.mesh.visible = e.visible;
    e.mesh.position.y = (mid - i) * spreadM;
    e.mesh.material.opacity = e.meta.id === layerActiveId ? Math.min(1.0, op + 0.15) : op;
  });
}

function select2dLayer(id) {
  layerActiveId = id;
  const e = layerEntries.find((x) => x.meta.id === id);
  if (!e) return;
  $("#layer-2d-title").textContent = `${e.meta.id} - ${e.meta.name}`;
  $("#layer-2d-img").src = e.meta.svgPath;
  document.querySelectorAll(".layer-row").forEach((r) => r.classList.toggle("active", r.dataset.layerId === id));
  updateLayerStackVisuals();
}

function apply2dTransform() {
  $("#layer-2d-img").style.transform = `translate(${l2dPan.x}px, ${l2dPan.y}px) scale(${l2dZoom})`;
}

// ---------------------------------------------------------------------------
// Sim Gallery & Lightbox
// ---------------------------------------------------------------------------

function renderGallery() {
  const root = $("#gallery-root");
  const modal = $("#img-modal");
  const mImg = $("#img-modal-img");
  const mCap = $("#img-modal-cap");

  root.innerHTML = "";
  for (const sec of GALLERY_SECTIONS) {
    const h = document.createElement("h3");
    h.className = "gallery-section-title";
    h.textContent = sec.title;
    root.appendChild(h);

    const grid = document.createElement("div");
    grid.className = "gallery-grid";
    for (const item of sec.items) {
      const card = document.createElement("article");
      card.className = "fig-card";
      card.innerHTML = `
        <img src="${item.src}" alt="${escapeHtml(item.title)}" loading="lazy">
        <div class="fig-cap">
          <strong>${escapeHtml(item.title)}</strong>
          <span>${escapeHtml(item.cap)}</span>
        </div>
      `;
      card.addEventListener("click", () => {
        mImg.src = item.src;
        mCap.textContent = `${item.title}: ${item.cap}`;
        modal.classList.add("open");
      });
      grid.appendChild(card);
    }
    root.appendChild(grid);
  }

  $("#img-modal-close").addEventListener("click", () => modal.classList.remove("open"));
  modal.addEventListener("click", (ev) => {
    if (ev.target === modal) modal.classList.remove("open");
  });
}

// ---------------------------------------------------------------------------
// UI Wiring, Search, Tabs & Public Deterministic API
// ---------------------------------------------------------------------------

function selectTab(tabId) {
  state.tab = tabId;
  document.querySelectorAll(".nav-tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === tabId));
  document.querySelectorAll(".tab-panel").forEach((p) => p.classList.toggle("active", p.id === `tab-${tabId}`));
  if (tabId === "explorer") {
    $("#webgl-canvas")?._resizeFn?.();
  } else if (tabId === "layers") {
    $("#layer-webgl-canvas")?._resizeFn?.();
  } else if (tabId === "hmi") {
    const ifr = $("#hmi-iframe");
    if (!ifr.src && ifr.dataset.src) ifr.src = ifr.dataset.src;
  }
}

function setTheme(theme) {
  state.theme = theme === "light" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", state.theme);
  $("#btn-theme").textContent = state.theme === "dark" ? "Light Mode" : "Dark Mode";
}

function setIsolate(mode) {
  state.isolateMode = mode;
  document.querySelectorAll("[data-iso]").forEach((b) => b.classList.toggle("active", b.dataset.iso === mode));
  applyAssemblyTransforms();
  setCameraPreset("iso");
}

function updateStatsPill() {
  if (!catalogue) return;
  const nets = catalogue.counts?.unique_nets ?? compByNet.size;
  $("#hud-stats").textContent = `${catalogue.components.length} Board | ${catalogue.kv260_parts.length} KV260 | ${nets} Nets`;
}

function wireUiEvents() {
  document.querySelectorAll(".nav-tab").forEach((b) => {
    b.addEventListener("click", () => selectTab(b.dataset.tab));
  });

  $("#btn-theme").addEventListener("click", () => {
    setTheme(state.theme === "dark" ? "light" : "dark");
  });

  // Search box across board components, KV260 parts, and nets
  const searchIn = $("#search-input");
  const drop = $("#search-dropdown");

  const runSearch = (qRaw) => {
    const q = qRaw.trim().toLowerCase();
    if (!q || !catalogue) {
      drop.classList.remove("open");
      return;
    }
    const matches = [];
    for (const [id, entry] of partById.entries()) {
      const d = entry.data;
      const hay = `${id} ${d.ref || ""} ${d.value || ""} ${d.part || ""} ${d.mpn || ""} ${d.description || d.role || ""} ${(d.nets || []).join(" ")}`.toLowerCase();
      if (hay.includes(q)) {
        matches.push({ id, entry });
        if (matches.length >= 16) break;
      }
    }
    if (!matches.length) {
      drop.innerHTML = `<div class="search-item"><span>No parts matching "${escapeHtml(qRaw)}"</span></div>`;
      drop.classList.add("open");
      return;
    }
    drop.innerHTML = matches.map(({ id, entry }) => {
      const d = entry.data;
      return `<button type="button" class="search-item" data-pick="${escapeHtml(id)}">
        <div class="search-item-head"><span>${escapeHtml(d.ref || id)}</span><span class="mono" style="color:var(--accent)">${escapeHtml(d.part || d.value || "")}</span></div>
        <div class="search-item-sub">${escapeHtml(d.description || d.role || "")}</div>
      </button>`;
    }).join("");
    drop.classList.add("open");
    drop.querySelectorAll("[data-pick]").forEach((btn) => {
      btn.addEventListener("click", () => {
        drop.classList.remove("open");
        selectTab("explorer");
        selectPart(btn.dataset.pick, true);
      });
    });
  };

  searchIn.addEventListener("input", () => runSearch(searchIn.value));
  document.addEventListener("click", (ev) => {
    if (!ev.target.closest(".search-wrap")) drop.classList.remove("open");
  });

  // Explode & Enclosure
  $("#range-explode").addEventListener("input", (ev) => {
    state.explodePct = Number(ev.target.value);
    $("#val-explode").textContent = `${state.explodePct}%`;
    applyAssemblyTransforms();
  });

  document.querySelectorAll("[data-enc]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.enclosureMode = btn.dataset.enc;
      document.querySelectorAll("[data-enc]").forEach((b) => b.classList.toggle("active", b.dataset.enc === state.enclosureMode));
      applyAssemblyTransforms();
    });
  });

  // KV260 Teardown controls
  $("#chk-kv-fan").addEventListener("change", (ev) => {
    state.showKvFan = ev.target.checked;
    applyAssemblyTransforms();
  });
  $("#chk-kv-hs").addEventListener("change", (ev) => {
    state.showKvHs = ev.target.checked;
    applyAssemblyTransforms();
  });
  $("#range-som-lift").addEventListener("input", (ev) => {
    state.somLiftMm = Number(ev.target.value);
    $("#val-som-lift").textContent = `${state.somLiftMm} mm`;
    applyAssemblyTransforms();
  });

  $("#btn-preset-kv-teardown").addEventListener("click", () => {
    applyTeardownPreset({ fan: false, hs: false, somLiftMm: 22, isolate: "kv260", select: "K26_XCK26" });
  });
  $("#btn-preset-som240").addEventListener("click", () => {
    applyTeardownPreset({ fan: false, hs: false, somLiftMm: 26, isolate: "kv260", select: "SOM240_1" });
  });

  // Isolate & Camera Presets
  document.querySelectorAll("[data-iso]").forEach((btn) => {
    btn.addEventListener("click", () => setIsolate(btn.dataset.iso));
  });
  document.querySelectorAll("[data-cam]").forEach((btn) => {
    btn.addEventListener("click", () => setCameraPreset(btn.dataset.cam));
  });
  document.querySelectorAll(".quick-pick").forEach((btn) => {
    btn.addEventListener("click", () => selectPart(btn.dataset.ref, true));
  });

  // Mobile drawer toggles
  $("#btn-mob-controls").addEventListener("click", () => {
    const open = $("#dock-controls").classList.toggle("mobile-open");
    $("#btn-mob-controls").classList.toggle("active", open);
    $("#btn-mob-controls").textContent = open ? "Hide Controls" : "Show Controls";
  });
  $("#btn-mob-inspector").addEventListener("click", () => {
    const hidden = $("#inspector-pane").classList.toggle("mobile-hidden");
    $("#btn-mob-inspector").classList.toggle("active", !hidden);
  });

  // Layer Viewer Controls
  $("#range-layer-spread").addEventListener("input", updateLayerStackVisuals);
  $("#range-layer-opacity").addEventListener("input", updateLayerStackVisuals);
  $("#btn-layers-all").addEventListener("click", () => {
    layerEntries.forEach((e) => { e.visible = true; });
    $("#layer-list").querySelectorAll("input").forEach((c) => { c.checked = true; });
    updateLayerStackVisuals();
  });
  $("#btn-layers-cu").addEventListener("click", () => {
    layerEntries.forEach((e) => {
      e.visible = e.meta.id.endsWith(".Cu") || e.meta.id === "Edge.Cuts";
      const row = $("#layer-list").querySelector(`[data-layer-id="${e.meta.id}"] input`);
      if (row) row.checked = e.visible;
    });
    updateLayerStackVisuals();
  });

  $("#btn-l2d-in").addEventListener("click", () => { l2dZoom = Math.min(8, l2dZoom * 1.35); apply2dTransform(); });
  $("#btn-l2d-out").addEventListener("click", () => { l2dZoom = Math.max(0.5, l2dZoom / 1.35); apply2dTransform(); });
  $("#btn-l2d-reset").addEventListener("click", () => { l2dZoom = 1; l2dPan = { x: 0, y: 0 }; apply2dTransform(); });

  const stage2d = $("#layer-2d-stage");
  let drag2d = null;
  stage2d.addEventListener("pointerdown", (ev) => { drag2d = { x: ev.clientX - l2dPan.x, y: ev.clientY - l2dPan.y }; });
  window.addEventListener("pointermove", (ev) => {
    if (!drag2d) return;
    l2dPan = { x: ev.clientX - drag2d.x, y: ev.clientY - drag2d.y };
    apply2dTransform();
  });
  window.addEventListener("pointerup", () => { drag2d = null; });
}

function applyTeardownPreset({ fan = false, hs = false, somLiftMm = 20, isolate = "kv260", select = null }) {
  state.showKvFan = fan;
  state.showKvHs = hs;
  state.somLiftMm = somLiftMm;
  $("#chk-kv-fan").checked = fan;
  $("#chk-kv-hs").checked = hs;
  $("#range-som-lift").value = somLiftMm;
  $("#val-som-lift").textContent = `${somLiftMm} mm`;
  setIsolate(isolate);
  if (select) selectPart(select, false);
}

// Expose deterministic helpers for automated screenshot & UI tests
window.__SITE_API = {
  isReady: () => state.ready,
  selectTab,
  setTheme,
  setExplode: (pct) => {
    state.explodePct = pct;
    $("#range-explode").value = pct;
    $("#val-explode").textContent = `${pct}%`;
    applyAssemblyTransforms();
  },
  setEnclosure: (mode) => {
    state.enclosureMode = mode;
    document.querySelectorAll("[data-enc]").forEach((b) => b.classList.toggle("active", b.dataset.enc === mode));
    applyAssemblyTransforms();
  },
  setTeardown: applyTeardownPreset,
  isolate: setIsolate,
  selectPart,
  setCameraPreset,
  select2dLayer,
  getStats: () => ({
    ready: state.ready,
    tab: state.tab,
    theme: state.theme,
    boardComponents: catalogue ? catalogue.components.length : 0,
    kv260Parts: catalogue ? catalogue.kv260_parts.length : 0,
    selectedId: state.selectedId,
  }),
};

boot().catch((err) => {
  console.error(err);
  const ov = $("#loading-overlay");
  if (ov) ov.textContent = `Load error: ${err.message}`;
});
