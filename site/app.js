import * as THREE from "./vendor/three-0.170.0/three.module.min.js";
import { OrbitControls } from "./vendor/three-0.170.0/OrbitControls.js";
import { GLTFLoader } from "./vendor/three-0.170.0/GLTFLoader.js";
import { RoomEnvironment } from "./vendor/three-0.170.0/RoomEnvironment.js";
import { MeshoptDecoder } from "./vendor/three-0.170.0/meshopt_decoder.module.js";
import initCore, { SiteCore } from "./core/pkg/ias2rf_site_core.js";
import { initMockups } from "./mockups.js";

const REPO_BLOB = "https://github.com/PabloSoage/kv260-ias2rf/blob/main";
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
    title: "Final Vehicle-CAN Rev08 Board & Closed-Case v2 Renders",
    items: [
      { src: "assets/img/board_iso.png", title: "Rev08 Final Adapter Isometric", cap: "Updated Rev08 board with routed vehicle CAN (U1506, Q1530/Q1531, J1503 6-way JST-SH)." },
      { src: "assets/img/board_top.png", title: "Rev08 Final Top Side", cap: "Front SMA launch panel, ADAR1000 header, J1502 15-way FFC, J1503 6-pin CAN+PPS & Artix-7." },
      { src: "assets/img/board_bottom.png", title: "Rev08 Final Bottom Side", cap: "U1506 TCAN330DCNT CAN transceiver, Q1530/Q1531 NOR pair, D1531 PESD1CAN, J101/J102 plugs." },
      { src: "assets/img/case_v2_closed.jpg", title: "Closed Enclosure v2 (PETG-CF + TPU)", cap: "Dual-fan intake/exhaust enclosure with printable filter frame and corner bumpers." },
      { src: "assets/img/case_v2_open.jpg", title: "Closed Enclosure v2 (Open Service View)", cap: "Internal heatsink clearance, dual OD5015 lid fan and captive connector exits." },
    ],
  },
];

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
  useWasmPicker: true,
};

// Interpolated / animated state for eased motion & slide-out teardown
const anim = {
  explodePct: 0,
  somLiftMm: 0,
  lidOpen: 0,
  caseVisFade: 1,
  kvFanSlide: 0,
  kvHsSlide: 0,
};
let tweenHandles = {
  explode: null,
  somLift: null,
  cam: null,
  intro: null,
};

let catalogue = null;
let netTraces = {};
let siteCore = null;
const partList = [];
const partIndexById = new Map();
const partById = new Map();
const nodeById = new Map();
const compByNet = new Map();

// Main 3-D objects
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
const netPulseGroup = new THREE.Group();
let activeTraceSegs = [];
let activePulseMesh = null;

// Layer viewer objects
let layerRenderer, layerScene, layerCamera, layerControls;
const layerPlanesGroup = new THREE.Group();
const layerEntries = [];
let layerActiveId = "F.Cu";
let layerPeelStart = -1;
let l2dZoom = 1.0;
let l2dPan = { x: 0, y: 0 };
let mockupCtrl = null;

function $(sel) {
  return document.querySelector(sel);
}

const isReducedMotion = () => window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches === true;
const easeOutCubic = (u) => 1 - Math.pow(1 - Math.min(1, Math.max(0, u)), 3);

function escapeHtml(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function setLoadProgress(pct, stage, detail) {
  const fill = $("#load-bar-fill");
  const pctEl = $("#load-pct");
  const stEl = $("#load-stage");
  const dtEl = $("#load-detail");
  if (fill) fill.style.width = `${Math.min(100, Math.max(4, pct))}%`;
  if (pctEl) pctEl.textContent = `${Math.round(pct)}%`;
  if (stage && stEl) stEl.textContent = stage;
  if (detail && dtEl) dtEl.textContent = detail;
}

// ---------------------------------------------------------------------------
// Boot & Parallel Asset / Rust WASM Streaming
// ---------------------------------------------------------------------------

async function boot() {
  wireUiEvents();
  setupScrollStory();
  renderGallery();
  setLoadProgress(10, "Loading Rust/WASM Core & Component Catalogue...", "site/core/pkg/ias2rf_site_core_bg.wasm");

  const [_, catResp, traceResp] = await Promise.all([
    initCore(),
    fetch("assets/components.json"),
    fetch("assets/net_traces.json"),
  ]);
  if (!catResp.ok) throw new Error(`components.json HTTP ${catResp.status}`);
  catalogue = await catResp.json();
  if (traceResp.ok) netTraces = await traceResp.json();

  setLoadProgress(28, "Building Spatial BVH/Grid in Rust WASM...", `${catalogue.components.length} board + ${catalogue.kv260_parts.length} KV260 parts`);
  siteCore = new SiteCore();
  indexAndLoadCore(catalogue);

  initExplorerThree();
  await loadModelsWithProgress();
  await initLayerViewer();

  mockupCtrl = initMockups($("#mockups-root"), () => siteCore, () => state.tab === "mockups");

  applyTransformsInstant();
  updateStatsPill();
  $("#hud-perf").textContent = `Rust Grid: ${siteCore.part_count()} AABBs ready`;

  setLoadProgress(100, "Ready", "Loaded GLBs & Rust/WASM core");
  $("#loading-overlay").classList.add("hidden");
  state.ready = true;

  const hasHash = applyHashParams();
  if (!hasHash && !location.search.includes("noIntro=1") && !isReducedMotion()) {
    playIntro();
  }
}

function indexAndLoadCore(cat) {
  let idx = 0;
  const pushPart = (id, kind, data, groupId, bmin, bmax) => {
    partIndexById.set(id, idx);
    partList[idx] = id;
    partById.set(id, { kind, data });
    const nets = data.nets || [];
    for (const net of nets) {
      if (!compByNet.has(net)) compByNet.set(net, []);
      compByNet.get(net).push(id);
    }
    siteCore.add_part(
      idx,
      id,
      data.ref || id,
      data.value || data.part || "",
      data.mpn || "",
      data.description || data.role || "",
      nets.join("\n"),
      groupId,
      bmin[0], bmin[1], bmin[2],
      bmax[0], bmax[1], bmax[2]
    );
    idx++;
  };

  for (const c of cat.components) {
    const [kx0, ky0, kx1, ky1, kz0, kz1] = c.bbox_world_mm;
    pushPart(c.ref, "board", c, 0, [kx0 * 0.001, kz0 * 0.001, -ky1 * 0.001], [kx1 * 0.001, kz1 * 0.001, -ky0 * 0.001]);
  }
  for (const k of cat.kv260_parts) {
    const [kx0, ky0, kx1, ky1, kz0, kz1] = k.bbox_mm;
    const gid = k.id === "KV260_FAN" ? 3 : k.id === "KV260_HEATSINK" ? 4 : k.subassembly === "som" ? 2 : 1;
    pushPart(k.id, k.subassembly === "cooling" ? "kv_cooling" : "kv260", k, gid, [kx0 * 0.001, kz0 * 0.001, -ky1 * 0.001], [kx1 * 0.001, kz1 * 0.001, -ky0 * 0.001]);
  }
  for (const ex of cat.extra_parts || []) {
    const [kx0, ky0, kx1, ky1, kz0, kz1] = ex.bbox_mm;
    const gid = ex.id === "FAN2_5015" ? 6 : 7;
    pushPart(ex.id, "extra", ex, gid, [kx0 * 0.001, kz0 * 0.001, -ky1 * 0.001], [kx1 * 0.001, kz1 * 0.001, -ky0 * 0.001]);
  }
}

// ---------------------------------------------------------------------------
// Three.js Explorer Scene & Lighting
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

  scene.add(new THREE.HemisphereLight(0xdbe8f8, 0x1a2029, 0.55));
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
  controls.maxDistance = 1.4;

  // Cancel scripted camera/intro motions immediately on user input
  const cancelAutoMotion = () => {
    tweenHandles.intro = null;
    tweenHandles.cam = null;
  };
  canvas.addEventListener("pointerdown", cancelAutoMotion, { passive: true });
  canvas.addEventListener("wheel", cancelAutoMotion, { passive: true });
  canvas.addEventListener("touchstart", cancelAutoMotion, { passive: true });

  adapterGroup.position.copy(BOARD_REG_POS);
  adapterGroup.rotation.y = BOARD_REG_ROTY;
  adapterGroup.add(netPulseGroup);

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

  const tick = (now) => {
    requestAnimationFrame(tick);
    stepTweens(now);
    stepPulseDots(now);
    if (state.tab === "explorer") {
      controls.update();
      renderer.render(scene, camera);
    }
  };
  requestAnimationFrame(tick);
}

async function loadModelsWithProgress() {
  const loader = new GLTFLoader();
  loader.setMeshoptDecoder(MeshoptDecoder);
  const progressMap = { board: 0, kv: 0, enc: 0 };
  const updateLoaderUi = (label) => {
    const avg = (progressMap.board * 0.85 + progressMap.kv * 0.05 + progressMap.enc * 0.10);
    setLoadProgress(30 + avg * 68, "Streaming 3-D CAD Assemblies...", label);
  };
  const loadGlb = (url, key, label) => new Promise((res, rej) => {
    loader.load(url, (g) => {
      progressMap[key] = 1;
      updateLoaderUi(`${label} ready`);
      res(g);
    }, (ev) => {
      if (ev.total > 0) {
        progressMap[key] = ev.loaded / ev.total;
        updateLoaderUi(`${label} (${(ev.loaded / 1e6).toFixed(1)} / ${(ev.total / 1e6).toFixed(1)} MB)`);
      }
    }, rej);
  });

  const [bGltf, kGltf, eGltf] = await Promise.all([
    loadGlb("assets/board.glb", "board", "board.glb"),
    loadGlb("assets/kv260.glb", "kv", "kv260.glb"),
    loadGlb("assets/enclosure.glb", "enc", "enclosure.glb"),
  ]);

  boardModel = bGltf.scene;
  adapterGroup.add(boardModel);

  kv260Model = kGltf.scene;
  assemblyRoot.add(kv260Model);

  enclosureModel = eGltf.scene;
  assemblyRoot.add(enclosureModel);

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

  setCameraPreset("iso", true);
}

// ---------------------------------------------------------------------------
// Tweens, Slide-Out Part Animations, Intro Sequence & Scene Application
// ---------------------------------------------------------------------------

function startScalarTween(key, from, to, durationMs) {
  if (isReducedMotion() || durationMs <= 0) {
    tweenHandles[key] = null;
    anim[key] = to;
    applyAnimatedScene();
    return;
  }
  tweenHandles[key] = { from, to, start: performance.now(), dur: Math.min(900, durationMs) };
}

function stepTweens(now) {
  let dirty = false;

  // 1. Intro sequence (~2050 ms total, interruptible)
  if (tweenHandles.intro) {
    const tr = tweenHandles.intro;
    const u = Math.min(1, (now - tr.start) / tr.dur);
    applyIntroAtProgress(u);
    if (u >= 1) {
      tweenHandles.intro = null;
      syncHash();
    }
  }

  // 2. Smooth explode / SOM lift scalars
  for (const key of ["explodePct", "somLiftMm"]) {
    const h = tweenHandles[key];
    if (!h) continue;
    const u = Math.min(1, (now - h.start) / h.dur);
    anim[key] = h.from + (h.to - h.from) * easeOutCubic(u);
    dirty = true;
    if (u >= 1) tweenHandles[key] = null;
  }

  // 3. Smooth slide-out offsets for enclosure lid, KV260 fan & heatsink
  const stepRate = isReducedMotion() ? 1.0 : 0.16;
  const targets = {
    lidOpen: state.enclosureMode === "open" ? 1 : 0,
    caseVisFade: state.enclosureMode === "hidden" ? 0 : 1,
    kvFanSlide: state.showKvFan ? 0 : 1,
    kvHsSlide: state.showKvHs ? 0 : 1,
  };
  for (const [k, tgt] of Object.entries(targets)) {
    const diff = tgt - anim[k];
    if (Math.abs(diff) > 0.002) {
      anim[k] += diff * stepRate;
      dirty = true;
    } else if (anim[k] !== tgt) {
      anim[k] = tgt;
      dirty = true;
    }
  }

  // 4. Camera tween (<= 750 ms eased)
  if (tweenHandles.cam) {
    const c = tweenHandles.cam;
    const u = easeOutCubic(Math.min(1, (now - c.start) / c.dur));
    camera.position.lerpVectors(c.fromPos, c.toPos, u);
    controls.target.lerpVectors(c.fromTgt, c.toTgt, u);
    controls.update();
    if (u >= 1) tweenHandles.cam = null;
  }

  if (dirty) applyAnimatedScene();
}

function applyTransformsInstant() {
  anim.explodePct = state.explodePct;
  anim.somLiftMm = state.somLiftMm;
  anim.lidOpen = state.enclosureMode === "open" ? 1 : 0;
  anim.caseVisFade = state.enclosureMode === "hidden" ? 0 : 1;
  anim.kvFanSlide = state.showKvFan ? 0 : 1;
  anim.kvHsSlide = state.showKvHs ? 0 : 1;
  applyAnimatedScene();
}

function applyAnimatedScene() {
  const t = anim.explodePct / 100;
  const somY = anim.somLiftMm * 0.001 + 0.028 * t;
  const showEnc = state.isolateMode === "all" || state.isolateMode === "enclosure";
  const showBoard = state.isolateMode === "all" || state.isolateMode === "board";
  const showKv = state.isolateMode === "all" || state.isolateMode === "kv260";
  const showThermal = state.isolateMode === "all" || state.isolateMode === "thermal";

  const yBoard = 0.072 * t;
  adapterGroup.visible = showBoard;
  adapterGroup.position.set(BOARD_REG_POS.x, BOARD_REG_POS.y + yBoard, BOARD_REG_POS.z);

  const ySom = somY;
  const yCoolingBase = somY + 0.040 * t;
  const yFanSlide = anim.kvFanSlide * 0.042;
  const yHsSlide = anim.kvHsSlide * 0.042;
  const fanVis = (showKv || showThermal) && anim.kvFanSlide < 0.98;
  const hsVis = (showKv || showThermal) && anim.kvHsSlide < 0.98;

  if (kv260Model) kv260Model.visible = showKv || showThermal;
  if (kvNodes.KV260_CARRIER_GROUP) kvNodes.KV260_CARRIER_GROUP.visible = showKv;
  if (kvNodes.K26_SOM_GROUP) {
    kvNodes.K26_SOM_GROUP.visible = showKv;
    kvNodes.K26_SOM_GROUP.position.y = ySom;
  }
  if (kvNodes.KV260_COOLING_GROUP) {
    kvNodes.KV260_COOLING_GROUP.visible = fanVis || hsVis;
    kvNodes.KV260_COOLING_GROUP.position.y = yCoolingBase;
  }
  if (kvNodes.KV260_FAN) {
    kvNodes.KV260_FAN.visible = fanVis;
    kvNodes.KV260_FAN.position.y = yFanSlide;
  }
  if (kvNodes.KV260_HEATSINK) {
    kvNodes.KV260_HEATSINK.visible = hsVis;
    kvNodes.KV260_HEATSINK.position.y = yHsSlide;
  }

  const caseVis = showEnc && anim.caseVisFade > 0.02;
  const hideSlide = (1 - anim.caseVisFade) * 0.06;
  const yBottom = -0.045 * t - hideSlide;
  const yLid = anim.lidOpen * 0.085 + 0.150 * t + hideSlide;
  const yAdpHs = 0.105 * t;

  if (enclosureModel) enclosureModel.visible = showEnc || showThermal;
  if (encNodes.ENCLOSURE_BOTTOM_GROUP) {
    encNodes.ENCLOSURE_BOTTOM_GROUP.visible = caseVis;
    encNodes.ENCLOSURE_BOTTOM_GROUP.position.y = yBottom;
  }
  if (encNodes.ENCLOSURE_BUMPERS_GROUP) {
    encNodes.ENCLOSURE_BUMPERS_GROUP.visible = caseVis;
    encNodes.ENCLOSURE_BUMPERS_GROUP.position.y = -0.025 * t - hideSlide * 0.5;
  }
  if (encNodes.ENCLOSURE_LID_GROUP) {
    encNodes.ENCLOSURE_LID_GROUP.visible = caseVis;
    encNodes.ENCLOSURE_LID_GROUP.position.y = yLid;
  }
  if (encNodes.ADAPTER_HEATSINKS_GROUP) {
    encNodes.ADAPTER_HEATSINKS_GROUP.visible = showThermal;
    encNodes.ADAPTER_HEATSINKS_GROUP.position.y = yAdpHs;
  }

  scene.updateMatrixWorld(true);
  updateSelectionBox();
  rebuildNetHighlightBoxes();

  if (siteCore) {
    const mask =
      (showBoard ? 1 << 0 : 0) |
      (showKv ? 1 << 1 : 0) |
      (showKv ? 1 << 2 : 0) |
      (fanVis ? 1 << 3 : 0) |
      (hsVis ? 1 << 4 : 0) |
      (caseVis ? 1 << 5 : 0) |
      (caseVis ? 1 << 6 : 0) |
      (showThermal ? 1 << 7 : 0);
    const offsets = new Float32Array([
      yBoard,
      0.0,
      ySom,
      yCoolingBase + yFanSlide,
      yCoolingBase + yHsSlide,
      yBottom,
      yLid,
      yAdpHs,
    ]);
    siteCore.set_group_transforms(offsets, mask);
  }
}

function applyIntroAtProgress(u) {
  const c = new THREE.Vector3(0.02, 0.02, -0.05);
  let explodeTarget = 0;
  let somTarget = 0;
  let lidMode = "closed";
  let camOffset;

  if (u < 0.35) {
    const p = easeOutCubic(u / 0.35);
    lidMode = p > 0.45 ? "open" : "closed";
    anim.lidOpen = lidMode === "open" ? Math.min(1, (p - 0.45) / 0.55) : 0;
    explodeTarget = p * 12;
    camOffset = new THREE.Vector3().lerpVectors(
      new THREE.Vector3(-0.34, 0.25, 0.34),
      new THREE.Vector3(-0.23, 0.19, 0.24),
      p
    );
  } else if (u < 0.72) {
    const p = easeOutCubic((u - 0.35) / 0.37);
    lidMode = "open";
    anim.lidOpen = 1;
    explodeTarget = 12 + p * 46; // up to 58%
    somTarget = p * 14;
    camOffset = new THREE.Vector3().lerpVectors(
      new THREE.Vector3(-0.23, 0.19, 0.24),
      new THREE.Vector3(-0.25, 0.21, 0.25),
      p
    );
  } else {
    const p = easeOutCubic((u - 0.72) / 0.28);
    lidMode = "open";
    anim.lidOpen = 1;
    explodeTarget = 58 - p * 40; // settles at 18% cutaway
    somTarget = 14 * (1 - p);
    camOffset = new THREE.Vector3().lerpVectors(
      new THREE.Vector3(-0.25, 0.21, 0.25),
      new THREE.Vector3(-0.21, 0.17, 0.21),
      p
    );
  }

  state.enclosureMode = lidMode;
  state.explodePct = Math.round(explodeTarget);
  state.somLiftMm = Math.round(somTarget);
  anim.explodePct = explodeTarget;
  anim.somLiftMm = somTarget;
  document.querySelectorAll("[data-enc]").forEach((b) => b.classList.toggle("active", b.dataset.enc === lidMode));
  $("#range-explode").value = state.explodePct;
  $("#val-explode").textContent = `${state.explodePct}%`;
  $("#range-som-lift").value = state.somLiftMm;
  $("#val-som-lift").textContent = `${state.somLiftMm} mm`;

  applyAnimatedScene();
  controls.target.copy(c);
  camera.position.copy(c).add(camOffset);
  controls.update();
}

function playIntro() {
  if (isReducedMotion()) {
    state.enclosureMode = "open";
    state.explodePct = 18;
    state.somLiftMm = 0;
    document.querySelectorAll("[data-enc]").forEach((b) => b.classList.toggle("active", b.dataset.enc === "open"));
    $("#range-explode").value = 18;
    $("#val-explode").textContent = "18%";
    applyTransformsInstant();
    setCameraPreset("iso", true);
    return;
  }
  tweenHandles.cam = null;
  tweenHandles.intro = { start: performance.now(), dur: 2050 };
}

function getActiveBounds() {
  const box = new THREE.Box3();
  const candidates = [
    adapterGroup,
    kvNodes.KV260_CARRIER_GROUP,
    kvNodes.K26_SOM_GROUP,
    kvNodes.KV260_COOLING_GROUP,
    encNodes.ENCLOSURE_BOTTOM_GROUP,
    encNodes.ENCLOSURE_LID_GROUP,
    encNodes.ADAPTER_HEATSINKS_GROUP,
  ];
  for (const obj of candidates) {
    if (obj && isObjectEffectivelyVisible(obj)) box.expandByObject(obj);
  }
  if (box.isEmpty()) box.set(new THREE.Vector3(-0.08, -0.02, -0.12), new THREE.Vector3(0.14, 0.06, 0.03));
  return box;
}

function moveCameraEased(targetCenter, targetPos, durationMs = 620) {
  if (isReducedMotion() || durationMs <= 0) {
    tweenHandles.cam = null;
    controls.target.copy(targetCenter);
    camera.position.copy(targetPos);
    controls.update();
    return;
  }
  tweenHandles.cam = {
    fromPos: camera.position.clone(),
    toPos: targetPos.clone(),
    fromTgt: controls.target.clone(),
    toTgt: targetCenter.clone(),
    start: performance.now(),
    dur: Math.min(900, durationMs),
  };
}

function setCameraPreset(preset, instant = false) {
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
  const pos = center.clone().addScaledVector(d, dist);
  moveCameraEased(center, pos, instant ? 0 : 620);
}

function focusPartCamera(id, instant = false) {
  const obj = nodeById.get(id);
  if (!obj) return;
  scene.updateMatrixWorld(true);
  const box = new THREE.Box3().setFromObject(obj);
  if (box.isEmpty()) return;
  const center = box.getCenter(new THREE.Vector3());
  const sz = box.getSize(new THREE.Vector3());
  const dist = Math.max(Math.max(sz.x, sz.y, sz.z) * 2.8, 0.048);
  const dir = camera.position.clone().sub(controls.target).normalize();
  if (dir.lengthSq() < 0.01) dir.set(-0.5, 0.7, 0.6).normalize();
  moveCameraEased(center, center.clone().addScaledVector(dir, dist), instant ? 0 : 580);
}

// ---------------------------------------------------------------------------
// Hover & Click Picking (Rust WASM SiteCore + Three.js Fallback Benchmark)
// ---------------------------------------------------------------------------

const _raycaster = new THREE.Raycaster();
const _ptr = new THREE.Vector2();

function pickAtNdc(ndcX, ndcY) {
  _ptr.set(ndcX, ndcY);
  _raycaster.setFromCamera(_ptr, camera);
  if (state.useWasmPicker && siteCore) {
    const r = _raycaster.ray;
    const hitIdx = siteCore.pick_ray(
      r.origin.x, r.origin.y, r.origin.z,
      r.direction.x, r.direction.y, r.direction.z
    );
    if (hitIdx >= 0) {
      const id = partList[hitIdx];
      return { id, object: nodeById.get(id) || null };
    }
    return null;
  }

  // Fallback / baseline Three.js mesh traversal
  const hits = _raycaster.intersectObject(assemblyRoot, true);
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
    const nm = h.object.name || "";
    if ((nm === "PCB_LAYER_SOLDERMASK" || nm === "PCB_LAYER_SILKSCREEN") && hits[i + 1] && hits[i + 1].distance - h.distance < 0.002) {
      continue;
    }
    return null;
  }
  return null;
}

function wireViewportPicking(canvas) {
  const tip = $("#hover-tooltip");
  let downPos = null;

  const getNdc = (ev) => {
    const rect = canvas.getBoundingClientRect();
    return {
      rect,
      nx: ((ev.clientX - rect.left) / rect.width) * 2 - 1,
      ny: -((ev.clientY - rect.top) / rect.height) * 2 + 1,
    };
  };

  canvas.addEventListener("pointermove", (ev) => {
    if (!state.ready) return;
    const { rect, nx, ny } = getNdc(ev);
    const t0 = performance.now();
    const found = pickAtNdc(nx, ny);
    const pickMs = performance.now() - t0;
    $("#hud-perf").textContent = `${state.useWasmPicker ? "Rust" : "Three"} pick: ${pickMs.toFixed(2)} ms`;

    if (found && found.object) {
      const entry = partById.get(found.id);
      const label = entry.kind === "board"
        ? `${entry.data.ref} &middot; ${escapeHtml(entry.data.value)}`
        : `${entry.data.ref || entry.data.id} &middot; ${escapeHtml(entry.data.part || entry.data.value)}`;
      const role = entry.kind === "board" ? entry.data.description : entry.data.role;
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
    if (moved > 5) return;
    const { nx, ny } = getNdc(ev);
    const found = pickAtNdc(nx, ny);
    if (found) selectPart(found.id, false);
  });

  canvas.addEventListener("dblclick", (ev) => {
    if (!state.ready) return;
    const { nx, ny } = getNdc(ev);
    _ptr.set(nx, ny);
    _raycaster.setFromCamera(_ptr, camera);
    const hits = _raycaster.intersectObject(assemblyRoot, true);
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

// ---------------------------------------------------------------------------
// Selection Box & Animated Pulsing Copper Net Highlight
// ---------------------------------------------------------------------------

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
  while (netPulseGroup.children.length) netPulseGroup.remove(netPulseGroup.children[0]);
  activeTraceSegs = [];
  activePulseMesh = null;

  if (!state.activeNet || !adapterGroup.visible) return;
  const refs = siteCore
    ? Array.from(siteCore.net_mates(state.activeNet)).map((idx) => partList[idx]).filter(Boolean)
    : (compByNet.get(state.activeNet) || []);

  for (const ref of refs) {
    const obj = nodeById.get(ref);
    if (!obj) continue;
    const bx = new THREE.Box3().setFromObject(obj);
    if (!bx.isEmpty()) netHighlightGroup.add(new THREE.Box3Helper(bx, 0x4cc2ff));
  }

  // Build real routed KiCad copper traces + traveling signal pulses inside adapterGroup
  const rawSegs = netTraces[state.activeNet] || [];
  if (rawSegs.length) {
    const verts = new Float32Array(rawSegs.length * 6);
    activeTraceSegs = [];
    for (let i = 0; i < rawSegs.length; i++) {
      const [x1, y1, x2, y2, lIdx] = rawSegs[i];
      // Place top copper highlight just above top silk (+1.72 mm) and bottom copper just below (-0.09 mm)
      const yLocal = lIdx <= 3 ? 0.00172 : -0.00009;
      const o = i * 6;
      verts[o] = x1 * 0.001;
      verts[o + 1] = yLocal;
      verts[o + 2] = y1 * 0.001;
      verts[o + 3] = x2 * 0.001;
      verts[o + 4] = yLocal;
      verts[o + 5] = y2 * 0.001;
      activeTraceSegs.push([x1 * 0.001, yLocal, y1 * 0.001, x2 * 0.001, yLocal, y2 * 0.001]);
    }
    const lineGeo = new THREE.BufferGeometry();
    lineGeo.setAttribute("position", new THREE.BufferAttribute(verts, 3));
    const lineMat = new THREE.LineBasicMaterial({ color: 0x4cc2ff, transparent: true, opacity: 0.92 });
    netPulseGroup.add(new THREE.LineSegments(lineGeo, lineMat));

    const dotCount = Math.min(28, Math.max(8, activeTraceSegs.length));
    const dotGeo = new THREE.SphereGeometry(0.00045, 8, 8);
    const dotMat = new THREE.MeshBasicMaterial({ color: 0xffb020 });
    activePulseMesh = new THREE.InstancedMesh(dotGeo, dotMat, dotCount);
    netPulseGroup.add(activePulseMesh);
    stepPulseDots(performance.now());
  }
}

function stepPulseDots(now) {
  if (!activePulseMesh || !activeTraceSegs.length) return;
  const count = activePulseMesh.count;
  const speed = isReducedMotion() ? 0 : now * 0.0016;
  const m = new THREE.Matrix4();
  for (let i = 0; i < count; i++) {
    const segIdx = Math.floor((i * activeTraceSegs.length) / count);
    const seg = activeTraceSegs[segIdx];
    const phase = (speed + i * 0.13) % 1.0;
    const x = seg[0] + (seg[3] - seg[0]) * phase;
    const y = seg[1] + 0.0002;
    const z = seg[2] + (seg[5] - seg[2]) * phase;
    m.makeTranslation(x, y, z);
    activePulseMesh.setMatrixAt(i, m);
  }
  activePulseMesh.instanceMatrix.needsUpdate = true;
}

function selectPart(id, shouldFocus = true) {
  const entry = partById.get(id);
  if (!entry) return;
  state.selectedId = id;
  updateSelectionBox();
  if (shouldFocus) focusPartCamera(id);

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
        <div class="btn-grid-3">
          <button id="insp-focus-btn" class="btn btn-sm btn-primary" type="button">Focus Camera</button>
          <a class="btn btn-sm" style="text-align:center" href="${REPO_BLOB}/${encodeURI(c.manual_link || "docs/BOARD_MANUAL.md")}" target="_blank" rel="noopener">Manual</a>
          <button id="insp-copy-link" class="btn btn-sm" type="button">Copy Link</button>
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
        const segCount = (netTraces[state.activeNet] || []).length;
        mateBox.innerHTML = `Connected on <code>${escapeHtml(state.activeNet)}</code> (${(compByNet.get(state.activeNet) || []).length} parts, ${segCount} trace segs): ` +
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
        <div class="btn-grid-3">
          <button id="insp-focus-btn" class="btn btn-sm btn-primary" type="button">Focus Camera</button>
          <a class="btn btn-sm" style="text-align:center" href="${REPO_BLOB}/${encodeURI(k.manual_link || "docs/INTERFACE_SPEC.md")}" target="_blank" rel="noopener">Spec</a>
          <button id="insp-copy-link" class="btn btn-sm" type="button">Copy Link</button>
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
  body.querySelector("#insp-copy-link")?.addEventListener("click", (ev) => {
    syncHash();
    navigator.clipboard?.writeText(location.href).catch(() => {});
    ev.target.textContent = "Copied!";
    setTimeout(() => { ev.target.textContent = "Copy Link"; }, 1200);
  });
  body.querySelector("#insp-clear-net")?.addEventListener("click", () => {
    state.activeNet = null;
    rebuildNetHighlightBoxes();
    selectPart(id, false);
    syncHash();
  });
  body.querySelectorAll("[data-net]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.activeNet = state.activeNet === btn.dataset.net ? null : btn.dataset.net;
      rebuildNetHighlightBoxes();
      selectPart(id, false);
      syncHash();
    });
  });

  $("#hud-status").innerHTML = `Selected <strong>${escapeHtml(id)}</strong>`;
  syncHash();
}

// ---------------------------------------------------------------------------
// 8-Layer PCB Stack-up + Sequential Peel Animation
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

  const wM = (catalogue.board_outline.width_mm || 140.0) * 0.001;
  const hM = (catalogue.board_outline.height_mm || 132.0) * 0.001;
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
      updateLayerStackVisuals(performance.now());
    });
    row.addEventListener("click", () => select2dLayer(L.id));
    listEl.appendChild(row);
  }

  updateLayerStackVisuals();
  select2dLayer("F.Cu");

  const tickLayers = (now) => {
    requestAnimationFrame(tickLayers);
    if (state.tab === "layers") {
      if (layerPeelStart >= 0) updateLayerStackVisuals(now);
      layerControls.update();
      layerRenderer.render(layerScene, layerCamera);
    }
  };
  requestAnimationFrame(tickLayers);
}

function startLayerPeel() {
  if (isReducedMotion()) {
    layerPeelStart = -1;
    updateLayerStackVisuals();
    return;
  }
  layerPeelStart = performance.now();
}

function updateLayerStackVisuals(now = performance.now()) {
  const spreadM = Number($("#range-layer-spread").value) * 0.001;
  const op = Number($("#range-layer-opacity").value) / 100;
  $("#val-layer-spread").textContent = `${Number($("#range-layer-spread").value).toFixed(1)} mm`;
  $("#val-layer-opacity").textContent = `${Math.round(op * 100)}%`;

  const mid = (layerEntries.length - 1) / 2;
  let allDone = true;
  layerEntries.forEach((e, i) => {
    e.mesh.visible = e.visible;
    const targetY = (mid - i) * spreadM;
    if (layerPeelStart >= 0) {
      const stagger = i * 48;
      const localU = Math.max(0, Math.min(1, (now - layerPeelStart - stagger) / 420));
      if (localU < 1) allDone = false;
      e.mesh.position.y = targetY * easeOutCubic(localU);
    } else {
      e.mesh.position.y = targetY;
    }
    e.mesh.material.opacity = e.meta.id === layerActiveId ? Math.min(1.0, op + 0.15) : op;
  });
  if (allDone && layerPeelStart >= 0) layerPeelStart = -1;
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
// Gallery, Story Cards & Deep Links (#part=U501&view=board&explode=60)
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

function setupScrollStory() {
  const cards = document.querySelectorAll(".story-card");
  if ("IntersectionObserver" in window && !isReducedMotion()) {
    const io = new IntersectionObserver((entries) => {
      for (const en of entries) {
        if (en.isIntersecting) en.target.classList.add("in-view");
      }
    }, { threshold: 0.15 });
    cards.forEach((c) => io.observe(c));
  }

  const actions = {
    board: () => {
      setIsolate("board");
      setExplode(0);
      selectPart("U1101", true);
    },
    radar: () => {
      setIsolate("board");
      setExplode(0);
      selectPart("U501", true);
    },
    can: () => {
      setIsolate("board");
      setExplode(0);
      state.activeNet = "/STATUS/CAN_TXD";
      setCameraPreset("bottom");
      selectPart("U1506", false);
    },
    kv260: () => {
      applyTeardownPreset({ fan: false, hs: false, somLiftMm: 22, isolate: "kv260", select: "K26_XCK26" });
    },
  };

  cards.forEach((btn) => {
    btn.addEventListener("click", () => {
      $("#explorer-stage")?.scrollIntoView({ behavior: isReducedMotion() ? "auto" : "smooth", block: "start" });
      actions[btn.dataset.story]?.();
    });
  });

  $("#btn-enter-explorer")?.addEventListener("click", () => {
    $("#explorer-stage")?.scrollIntoView({ behavior: isReducedMotion() ? "auto" : "smooth", block: "start" });
  });
  $("#btn-replay-intro-top")?.addEventListener("click", () => {
    $("#explorer-stage")?.scrollIntoView({ behavior: isReducedMotion() ? "auto" : "smooth", block: "start" });
    setIsolate("all");
    playIntro();
  });
}

let applyingHash = false;

function syncHash() {
  if (!state.ready || applyingHash) return;
  const p = new URLSearchParams();
  if (state.tab !== "explorer") p.set("tab", state.tab);
  if (state.isolateMode !== "all") p.set("view", state.isolateMode);
  if (state.selectedId) p.set("part", state.selectedId);
  if (state.explodePct > 0) p.set("explode", String(state.explodePct));
  if (state.enclosureMode !== "closed") p.set("enc", state.enclosureMode);
  if (state.somLiftMm > 0) p.set("som", String(state.somLiftMm));
  if (state.activeNet) p.set("net", state.activeNet);
  if (state.theme !== "dark") p.set("theme", state.theme);
  const str = p.toString();
  history.replaceState(null, "", str ? "#" + str : "#");
}

function applyHashParams() {
  const raw = location.hash.replace(/^#/, "");
  if (!raw) return false;
  const p = new URLSearchParams(raw);
  let touched = false;
  applyingHash = true;
  try {
    if (p.get("theme")) { setTheme(p.get("theme")); touched = true; }
    if (p.get("tab")) { selectTab(p.get("tab")); touched = true; }
    if (p.has("enc")) { setEnclosure(p.get("enc"), true); touched = true; }
    if (p.has("explode")) { setExplode(Number(p.get("explode")) || 0, true); touched = true; }
    if (p.has("som")) {
      state.somLiftMm = Math.max(0, Math.min(30, Number(p.get("som")) || 0));
      $("#range-som-lift").value = state.somLiftMm;
      $("#val-som-lift").textContent = `${state.somLiftMm} mm`;
      applyTransformsInstant();
      touched = true;
    }
    const view = p.get("view") || p.get("iso");
    if (view) { setIsolate(view, true); touched = true; }
    if (p.get("net")) { state.activeNet = p.get("net"); rebuildNetHighlightBoxes(); touched = true; }
    if (p.get("part")) { selectPart(p.get("part"), false); touched = true; }
    if (p.get("layer")) { select2dLayer(p.get("layer")); touched = true; }
    if (p.get("cam")) { setCameraPreset(p.get("cam"), true); touched = true; }
    if (touched && (p.get("part") || view || p.has("explode")) && state.tab === "explorer") {
      const stg = $("#explorer-stage");
      const hdrH = $(".topbar")?.offsetHeight || 54;
      if (stg) window.scrollTo(0, Math.max(0, stg.offsetTop - hdrH));
    }
  } finally {
    applyingHash = false;
  }
  return touched;
}

// ---------------------------------------------------------------------------
// UI Actions, Search via Rust Core & Benchmarking API
// ---------------------------------------------------------------------------

function selectTab(tabId) {
  state.tab = tabId;
  document.querySelectorAll(".nav-tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === tabId));
  document.querySelectorAll(".tab-panel").forEach((p) => p.classList.toggle("active", p.id === `tab-${tabId}`));
  if (tabId === "explorer") {
    $("#webgl-canvas")?._resizeFn?.();
  } else if (tabId === "layers") {
    $("#layer-webgl-canvas")?._resizeFn?.();
    startLayerPeel();
  } else if (tabId === "hmi") {
    const ifr = $("#hmi-iframe");
    if (!ifr.src && ifr.dataset.src) ifr.src = ifr.dataset.src;
  } else if (tabId === "mockups") {
    mockupCtrl?.forceTick?.();
  }
}

function setTheme(theme) {
  state.theme = theme === "light" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", state.theme);
  $("#btn-theme").textContent = state.theme === "dark" ? "Light Mode" : "Dark Mode";
}

function setExplode(pct, instant = false) {
  const clamped = Math.max(0, Math.min(100, Number(pct) || 0));
  const prev = anim.explodePct;
  state.explodePct = clamped;
  $("#range-explode").value = clamped;
  $("#val-explode").textContent = `${clamped}%`;
  if (instant) {
    tweenHandles.explodePct = null;
    anim.explodePct = clamped;
    applyAnimatedScene();
  } else {
    startScalarTween("explodePct", prev, clamped, 550);
  }
}

function setEnclosure(mode, instant = false) {
  state.enclosureMode = mode;
  document.querySelectorAll("[data-enc]").forEach((b) => b.classList.toggle("active", b.dataset.enc === mode));
  if (instant) applyTransformsInstant();
  else applyAnimatedScene();
}

function setIsolate(mode, instant = false) {
  state.isolateMode = mode;
  document.querySelectorAll("[data-iso]").forEach((b) => b.classList.toggle("active", b.dataset.iso === mode));
  applyAnimatedScene();
  setCameraPreset("iso", instant);
}

function applyTeardownPreset({ fan = false, hs = false, somLiftMm = 20, isolate = "kv260", select = null }, instant = false) {
  state.showKvFan = fan;
  state.showKvHs = hs;
  const prevSom = anim.somLiftMm;
  state.somLiftMm = somLiftMm;
  $("#chk-kv-fan").checked = fan;
  $("#chk-kv-hs").checked = hs;
  $("#range-som-lift").value = somLiftMm;
  $("#val-som-lift").textContent = `${somLiftMm} mm`;
  if (instant) {
    anim.somLiftMm = somLiftMm;
    anim.kvFanSlide = fan ? 0 : 1;
    anim.kvHsSlide = hs ? 0 : 1;
  } else {
    startScalarTween("somLiftMm", prevSom, somLiftMm, 520);
  }
  setIsolate(isolate, instant);
  if (select) selectPart(select, false);
}

function updateStatsPill() {
  if (!catalogue) return;
  const nets = catalogue.counts?.unique_nets ?? compByNet.size;
  $("#hud-stats").textContent = `${catalogue.components.length} Board | ${catalogue.kv260_parts.length} KV260 | ${nets} Nets`;
}

function wireUiEvents() {
  window.addEventListener("hashchange", applyHashParams);

  document.querySelectorAll(".nav-tab").forEach((b) => {
    b.addEventListener("click", () => {
      selectTab(b.dataset.tab);
      syncHash();
    });
  });

  $("#btn-theme").addEventListener("click", () => {
    setTheme(state.theme === "dark" ? "light" : "dark");
    syncHash();
  });

  const searchIn = $("#search-input");
  const drop = $("#search-dropdown");

  const runSearch = (qRaw) => {
    const q = qRaw.trim();
    if (!q || !catalogue) {
      drop.classList.remove("open");
      return;
    }
    let indices = [];
    if (siteCore) {
      indices = JSON.parse(siteCore.search(q, 16));
    } else {
      const ql = q.toLowerCase();
      for (const [id, entry] of partById.entries()) {
        const d = entry.data;
        const hay = `${id} ${d.ref || ""} ${d.value || ""} ${d.part || ""} ${d.mpn || ""} ${d.description || d.role || ""} ${(d.nets || []).join(" ")}`.toLowerCase();
        if (hay.includes(ql)) {
          indices.push(partIndexById.get(id));
          if (indices.length >= 16) break;
        }
      }
    }
    if (!indices.length) {
      drop.innerHTML = `<div class="search-item"><span>No parts matching "${escapeHtml(qRaw)}"</span></div>`;
      drop.classList.add("open");
      return;
    }
    drop.innerHTML = indices.map((idx) => {
      const id = partList[idx];
      const entry = partById.get(id);
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
        $("#explorer-stage")?.scrollIntoView({ behavior: isReducedMotion() ? "auto" : "smooth", block: "start" });
        selectPart(btn.dataset.pick, true);
      });
    });
  };

  searchIn.addEventListener("input", () => runSearch(searchIn.value));
  document.addEventListener("click", (ev) => {
    if (!ev.target.closest(".search-wrap")) drop.classList.remove("open");
  });

  $("#range-explode").addEventListener("input", (ev) => setExplode(ev.target.value, true));
  $("#btn-replay-intro").addEventListener("click", () => { setIsolate("all", true); playIntro(); });

  document.querySelectorAll("[data-enc]").forEach((btn) => {
    btn.addEventListener("click", () => setEnclosure(btn.dataset.enc, false));
  });

  $("#chk-kv-fan").addEventListener("change", (ev) => {
    state.showKvFan = ev.target.checked;
    applyAnimatedScene();
  });
  $("#chk-kv-hs").addEventListener("change", (ev) => {
    state.showKvHs = ev.target.checked;
    applyAnimatedScene();
  });
  $("#range-som-lift").addEventListener("input", (ev) => {
    state.somLiftMm = Number(ev.target.value);
    anim.somLiftMm = state.somLiftMm;
    $("#val-som-lift").textContent = `${state.somLiftMm} mm`;
    applyAnimatedScene();
  });

  $("#btn-preset-kv-teardown").addEventListener("click", () => {
    applyTeardownPreset({ fan: false, hs: false, somLiftMm: 22, isolate: "kv260", select: "K26_XCK26" });
  });
  $("#btn-preset-som240").addEventListener("click", () => {
    applyTeardownPreset({ fan: false, hs: false, somLiftMm: 26, isolate: "kv260", select: "SOM240_1" });
  });

  document.querySelectorAll("[data-iso]").forEach((btn) => btn.addEventListener("click", () => setIsolate(btn.dataset.iso)));
  document.querySelectorAll("[data-cam]").forEach((btn) => btn.addEventListener("click", () => setCameraPreset(btn.dataset.cam)));
  document.querySelectorAll(".quick-pick").forEach((btn) => btn.addEventListener("click", () => selectPart(btn.dataset.ref, true)));

  $("#btn-mob-controls").addEventListener("click", () => {
    const open = $("#dock-controls").classList.toggle("mobile-open");
    $("#btn-mob-controls").classList.toggle("active", open);
    $("#btn-mob-controls").textContent = open ? "Hide Controls" : "Show Controls";
  });
  $("#btn-mob-inspector").addEventListener("click", () => {
    const hidden = $("#inspector-pane").classList.toggle("mobile-hidden");
    $("#btn-mob-inspector").classList.toggle("active", !hidden);
  });

  $("#btn-layer-peel").addEventListener("click", startLayerPeel);
  $("#range-layer-spread").addEventListener("input", () => updateLayerStackVisuals());
  $("#range-layer-opacity").addEventListener("input", () => updateLayerStackVisuals());
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

// Benchmark helper: compares Info-Mode hover pick + render time with Three.js vs Rust WASM SiteCore
function benchmarkHover({ frames = 60, useWasm = true } = {}) {
  const prevWasm = state.useWasmPicker;
  state.useWasmPicker = useWasm;
  const pickTimes = [];
  const frameTimes = [];
  let hits = 0;

  for (let i = 0; i < frames; i++) {
    const nx = -0.55 + 1.1 * ((i % 12) / 11);
    const ny = -0.45 + 0.9 * (Math.floor(i / 12) / Math.max(1, Math.floor(frames / 12)));
    const f0 = performance.now();
    const p0 = performance.now();
    const res = pickAtNdc(nx, ny);
    const p1 = performance.now();
    if (res && res.object) {
      hoverBox.box.setFromObject(res.object);
      hoverBox.visible = true;
      hits++;
    } else {
      hoverBox.visible = false;
    }
    renderer.render(scene, camera);
    const f1 = performance.now();
    pickTimes.push(p1 - p0);
    frameTimes.push(f1 - f0);
  }
  hoverBox.visible = false;
  state.useWasmPicker = prevWasm;

  const avg = (a) => a.reduce((s, x) => s + x, 0) / a.length;
  const p95 = (a) => {
    const s = [...a].sort((x, y) => x - y);
    return s[Math.min(s.length - 1, Math.floor(s.length * 0.95))];
  };
  return {
    picker: useWasm ? "rust-wasm" : "three-mesh",
    frames,
    hits,
    pick_mean_ms: +avg(pickTimes).toFixed(3),
    pick_p95_ms: +p95(pickTimes).toFixed(3),
    frame_mean_ms: +avg(frameTimes).toFixed(3),
    frame_p95_ms: +p95(frameTimes).toFixed(3),
  };
}

// Public API for deterministic screenshots, deep-links & benchmarks
window.__SITE_API = {
  isReady: () => state.ready,
  selectTab,
  setTheme,
  setExplode: (pct) => setExplode(pct, true),
  setEnclosure: (mode) => setEnclosure(mode, true),
  setTeardown: (opts) => applyTeardownPreset(opts, true),
  isolate: (m) => setIsolate(m, true),
  selectPart,
  setCameraPreset: (p) => setCameraPreset(p, true),
  select2dLayer,
  scrollToExplorer: () => {
    const el = $("#explorer-stage");
    const hdrH = $(".topbar")?.offsetHeight || 54;
    if (el) window.scrollTo(0, Math.max(0, el.offsetTop - hdrH));
  },
  scrollToTop: () => window.scrollTo(0, 0),
  setIntroFrame: (u) => {
    tweenHandles.intro = null;
    tweenHandles.cam = null;
    applyIntroAtProgress(u);
  },
  applyHash: () => applyHashParams(),
  selectNet: (net) => {
    state.activeNet = net;
    rebuildNetHighlightBoxes();
    if (state.selectedId) selectPart(state.selectedId, false);
  },
  searchCore: (q) => siteCore ? JSON.parse(siteCore.search(q, 16)).map((i) => partList[i]) : [],
  benchmarkHover,
  getStats: () => ({
    ready: state.ready,
    tab: state.tab,
    theme: state.theme,
    boardComponents: catalogue ? catalogue.components.length : 0,
    kv260Parts: catalogue ? catalogue.kv260_parts.length : 0,
    coreParts: siteCore ? siteCore.part_count() : 0,
    selectedId: state.selectedId,
  }),
};

boot().catch((err) => {
  console.error(err);
  const st = $("#load-stage");
  if (st) st.textContent = `Load error: ${err.message}`;
});
