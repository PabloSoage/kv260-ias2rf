import * as THREE from "./vendor/three-0.170.0/three.module.min.js";
import { OrbitControls } from "./vendor/three-0.170.0/OrbitControls.js";
import { GLTFLoader } from "./vendor/three-0.170.0/GLTFLoader.js";
import { RoomEnvironment } from "./vendor/three-0.170.0/RoomEnvironment.js";
import { MeshoptDecoder } from "./vendor/three-0.170.0/meshopt_decoder.module.js";
import { mergeGeometries } from "./vendor/three-0.170.0/BufferGeometryUtils.js";
import initCore, { SiteCore } from "./core/pkg/ias2rf_site_core.js";
import { initMockups } from "./mockups.js";
import { createSimController } from "./sim_mode.js";

const REPO_BLOB = "https://github.com/PabloSoage/kv260-ias2rf/blob/main";
const BOARD_REG_POS = new THREE.Vector3(0.107247, 0.0008, -0.198004);
const BOARD_REG_ROTY = -Math.PI / 2;

const DOC_PDF_PAGE_MAP = {
  "README.md": 6,
  "docs/BOARD_MANUAL.md": 30,
  "docs/FPGA_GATEWARE.md": 39,
  "docs/SYSTEM_SIM.md": 65,
  "fpga/SYSTEM_SIM.md": 65,
  "docs/LINK_PROTOCOL.md": 68,
  "docs/PINMAP.md": 74,
  "docs/HMI.md": 86,
  "docs/INTEGRATIONS.md": 94,
  "docs/IAS_LINK_SPEC.md": 114,
  "docs/CLOCK_SPEC.md": 118,
  "docs/CONTROL_SPEC.md": 132,
  "docs/POWER_SPEC.md": 139,
  "docs/POWER_AND_STACKUP.md": 139,
  "docs/LAYOUT.md": 166,
  "docs/SIGNAL_INTEGRITY.md": 176,
  "docs/AUDIT_Rev08.md": 204,
  "docs/3D_MODELS.md": 215,
  "docs/MECHANICAL.md": 219,
  "docs/ENCLOSURE.md": 223,
  "docs/ENCLOSURE_V2_THERMAL.md": 237,
  "docs/FABRICATION.md": 259,
  "docs/JLCPCB_QUOTE.md": 262,
  "fpga/README.md": 63,
  "fpga/eth/REV06.md": 78,
  "fpga/eth/REDUNDANCY.md": 80,
  "sw/README.md": 85,
  "docs/ADC_RADAR_SPEC.md": 121,
  "docs/ADC_SDR_SPEC.md": 124,
  "docs/DAC_RADAR_SPEC.md": 126,
  "docs/DAC_SDR_SPEC.md": 128,
  "docs/ROUTING_SPEC.md": 130,
  "docs/PSU_SPEC.md": 148,
  "docs/SYMBOLS.md": 161,
  "docs/img/highres/README.md": 270,
  "docs/PSU_ENCLOSURE.md": 155,
};

function docToPdfHref(docPath) {
  const clean = String(docPath || "docs/BOARD_MANUAL.md").split("#")[0];
  if (clean.endsWith(".pdf")) return `pdf.html?file=${encodeURI(clean)}#page=1`;
  const pg = DOC_PDF_PAGE_MAP[clean] || 23;
  return `pdf.html?file=${encodeURIComponent("docs/KV260-IAS2RF_Documentation.pdf")}#page=${pg}`;
}

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
      { src: "assets/img/board_bottom.png", title: "Rev08 Final Bottom Side", cap: "U1506 TCAN3403DDFRQ1 CAN transceiver, Q1530/Q1531 NOR pair, D1531 PESD1CAN, J101/J102 plugs." },
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
  isolateMode: "all", // all | board | kv260 | thermal | enclosure | psu
  selectedId: null,
  activeNet: null,
  activeNetIsPower: false,
  allNets: false,
  partAllNets: null, // a part whose every net is shown at once ("Select All Nets" in its inspector)
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
let psuData = null; // assets/psu.json: the PSU board (parts, nets, copper, analysis); ids and nets prefixed "PSU:"
let siteCore = null;
const partList = [];
const partIndexById = new Map();
const partById = new Map();
const nodeById = new Map();
const compByNet = new Map();

// Main 3-D objects
let renderer, scene, camera, controls;
let needsRender = true;
function requestRender() {
  needsRender = true;
}
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
const psuGroup = new THREE.Group(); // the PSU board, beside the assembly; KiCad mm map to (x, -, y) as on the adapter
const psuPulseGroup = new THREE.Group();
let psuModel = null;
let psuCaseModel = null; // its enclosure (assets/psu_case.glb): tray and lid, in the board's own frame
const psuCaseNodes = {};
const PSU_TRAY_BOTTOM_M = 0.0085; // the tray's underside is 8.5 mm below the board's
const PSU_CENTRE_MM = [155, 135];
const psuNet = (n) => String(n || "").startsWith("PSU:");
const netLabel = (n) => String(n || "").replace(/^PSU:/, "");
let activeTraceSegs = [];
let activePulseMesh = null;

// Layer viewer objects
let layerRenderer, layerScene, layerCamera, layerControls;
let layerNeedsRender = true;
function requestLayerRender() {
  layerNeedsRender = true;
}
const layerPlanesGroup = new THREE.Group();
const layerEntries = [];
let layerActiveId = "F.Cu";
let layerPeelStart = -1;
let l2dZoom = 1.0;
let l2dPan = { x: 0, y: 0 };
let mockupCtrl = null;
let simCtrl = null;

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

  const [_, catResp, traceResp, simResp, psuResp] = await Promise.all([
    initCore(),
    fetch("assets/components.json"),
    fetch("assets/net_traces.json"),
    fetch("assets/simulations.json"),
    fetch("assets/psu.json").catch(() => null),
  ]);
  if (!catResp.ok) throw new Error(`components.json HTTP ${catResp.status}`);
  catalogue = await catResp.json();
  if (traceResp.ok) netTraces = await traceResp.json();
  const simData = simResp.ok ? await simResp.json() : null;
  if (psuResp && psuResp.ok) {
    psuData = await psuResp.json();
    for (const [n, segs] of Object.entries(psuData.traces || {})) netTraces[`PSU:${n}`] = segs;
    for (const c of psuData.components) {
      c.nets = (c.nets || []).map((n) => `PSU:${n}`);
      for (const k of Object.keys(c.pads || {})) if (c.pads[k] !== "(nc)") c.pads[k] = `PSU:${c.pads[k]}`;
    }
  }

  setLoadProgress(28, "Building Spatial BVH/Grid in Rust WASM...", `${catalogue.components.length} board + ${catalogue.kv260_parts.length} KV260 parts`);
  siteCore = new SiteCore();
  indexAndLoadCore(catalogue);

  initExplorerThree();
  simCtrl = createSimController({
    THREE,
    scene,
    adapterGroup,
    nodeById,
    partById,
    encNodes,
    kvNodes,
    getNetTraces: () => netTraces,
    selectPart,
    focusPartCamera,
    setIsolate,
    setEnclosure,
    setCameraPreset,
    openImageModal: (src, cap) => {
      const mImg = $("#img-modal-img");
      const mCap = $("#img-modal-cap");
      const modal = $("#img-modal");
      if (mImg && mCap && modal) {
        mImg.src = src;
        mCap.textContent = cap || "Simulation Figure";
        modal.classList.add("open");
      }
    },
    applyAnimatedScene,
    syncHash,
    escapeHtml,
    isReducedMotion,
    REPO_BLOB,
  });
  simCtrl.wireDomEvents();
  if (simData) simCtrl.setData(simData);
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
  // the PSU board: group 8, bounds set from its meshes once it is placed (refreshPsuPickerBounds)
  for (const c of psuData?.components || []) {
    const [x0, y0, x1, y1] = c.bbox_board_mm;
    pushPart(c.id, "psu", c, 8, [x0 * 0.001, 0, y0 * 0.001], [x1 * 0.001, 0.003, y1 * 0.001]);
  }
}

function refreshPsuPickerBounds() {
  if (!siteCore || !psuData) return;
  scene.updateMatrixWorld(true);
  const box = new THREE.Box3();
  for (const c of psuData.components) {
    const idx = partIndexById.get(c.id);
    if (idx === undefined) continue;
    const [bx0, by0, bx1, by1] = c.bbox_board_mm;
    box.makeEmpty();
    box.expandByPoint(psuGroup.localToWorld(new THREE.Vector3(bx0 * 0.001, 0.0016, by0 * 0.001)));
    box.expandByPoint(psuGroup.localToWorld(new THREE.Vector3(bx1 * 0.001, 0.0019, by1 * 0.001)));
    const obj = nodeById.get(c.id);
    if (obj) box.union(new THREE.Box3().setFromObject(obj));
    const cx = (box.min.x + box.max.x) / 2;
    const cz = (box.min.z + box.max.z) / 2;
    box.min.x = Math.min(box.min.x, cx - 0.00065);
    box.max.x = Math.max(box.max.x, cx + 0.00065);
    box.min.z = Math.min(box.min.z, cz - 0.00065);
    box.max.z = Math.max(box.max.z, cz + 0.00065);
    siteCore.set_part_bounds(idx, 1, box.min.x, box.min.y, box.min.z, box.max.x, box.max.y, box.max.z);
  }
}

// ---------------------------------------------------------------------------
// Three.js Explorer Scene & Lighting
// ---------------------------------------------------------------------------

function initExplorerThree() {
  const canvas = $("#webgl-canvas");
  renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: "high-performance" });
  renderer.setClearColor(0x000000, 0);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
  renderer.shadowMap.enabled = false;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;

  scene = new THREE.Scene();
  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.06).texture;
  scene.environmentIntensity = 0.65;
  pmrem.dispose();

  scene.add(new THREE.HemisphereLight(0xdbe8f8, 0x1a2029, 0.58));
  const keyLight = new THREE.DirectionalLight(0xfff8ef, 1.35);
  keyLight.position.set(0.45, 0.78, 0.52);
  scene.add(keyLight);

  const rimLight = new THREE.DirectionalLight(0x9bc4ff, 0.55);
  rimLight.position.set(-0.55, 0.35, -0.52);
  scene.add(rimLight);

  const botLight = new THREE.DirectionalLight(0xeef4fc, 0.50);
  botLight.position.set(0.05, -0.85, 0.25);
  scene.add(botLight);

  camera = new THREE.PerspectiveCamera(38, 16 / 10, 0.005, 4.0);
  camera.position.set(-0.22, 0.19, 0.24);

  controls = new OrbitControls(camera, canvas);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.minDistance = 0.025;
  controls.maxDistance = 1.4;
  controls.addEventListener("change", requestRender);

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
  psuGroup.add(psuPulseGroup);
  psuGroup.visible = false;
  assemblyRoot.add(psuGroup);
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
    requestRender();
  };
  canvas._resizeFn = resizeExplorer;
  new ResizeObserver(resizeExplorer).observe(canvas.parentElement);
  resizeExplorer();

  wireViewportPicking(canvas);

  const tick = (now) => {
    requestAnimationFrame(tick);
    const tweenDirty = stepTweens(now);
    const pulseDirty = !!(activePulseMesh && activeTraceSegs.length && !isReducedMotion());
    if (pulseDirty) {
      stepPulseDots(now);
      needsRender = true;
    }
    const simDirty = !!(simCtrl && simCtrl.stepAnimation(now));
    if (tweenDirty || simDirty) needsRender = true;
    if (state.tab === "explorer") {
      if (controls.update()) needsRender = true;
      if (needsRender) {
        renderer.render(scene, camera);
        needsRender = false;
      }
    }
  };
  requestAnimationFrame(tick);
}

function refreshBoardPickerBounds(cat) {
  if (!siteCore || !cat) return;
  scene.updateMatrixWorld(true);
  const tmpBox = new THREE.Box3();
  for (const c of cat.components) {
    const idx = partIndexById.get(c.ref);
    if (idx === undefined) continue;
    const [wx0, wy0, wx1, wy1, wz0, wz1] = c.bbox_world_mm;
    let x0 = Math.min(wx0, wx1) * 0.001;
    let x1 = Math.max(wx0, wx1) * 0.001;
    let y0 = Math.min(wz0, wz1) * 0.001;
    let y1 = Math.max(wz0, wz1) * 0.001;
    let z0 = Math.min(-wy0, -wy1) * 0.001;
    let z1 = Math.max(-wy0, -wy1) * 0.001;

    const obj = nodeById.get(c.ref);
    if (obj) {
      tmpBox.setFromObject(obj);
      if (!tmpBox.isEmpty()) {
        x0 = Math.min(x0, tmpBox.min.x);
        x1 = Math.max(x1, tmpBox.max.x);
        y0 = Math.min(y0, tmpBox.min.y);
        y1 = Math.max(y1, tmpBox.max.y);
        z0 = Math.min(z0, tmpBox.min.z);
        z1 = Math.max(z1, tmpBox.max.z);
      }
    }
    // Keep small 0402 parts & bare pads easily hoverable (>= 1.3 mm footprint span)
    const cx = (x0 + x1) * 0.5;
    const cz = (z0 + z1) * 0.5;
    x0 = Math.min(x0, cx - 0.00065);
    x1 = Math.max(x1, cx + 0.00065);
    z0 = Math.min(z0, cz - 0.00065);
    z1 = Math.max(z1, cz + 0.00065);

    const isTht = (y0 < 0.00105 && y1 > 0.00210);
    let sideMask = c.side === "bottom" ? 2 : 1;
    if (isTht) {
      sideMask = 3;
    } else if (sideMask === 2) {
      y0 = Math.min(y0, 0.00035);
      y1 = Math.min(Math.max(y1, 0.00090), 0.00112);
    } else {
      y0 = Math.max(y0, 0.00205);
      y1 = Math.max(y1, 0.00275);
    }
    siteCore.set_part_bounds(idx, sideMask, x0, y0, z0, x1, y1, z1);
  }
}

function materialBatchSignature(mat) {
  const c = mat.color ? mat.color.getHexString() : "ffffff";
  const m = (mat.metalness ?? 0).toFixed(2);
  const r = (mat.roughness ?? 0.5).toFixed(2);
  const op = (mat.opacity ?? 1).toFixed(2);
  const tr = mat.transparent ? 1 : 0;
  const ds = mat.side === THREE.DoubleSide ? 2 : 0;
  const mp = mat.map ? mat.map.uuid : "none";
  return `${c}:${m}:${r}:${op}:${tr}:${ds}:${mp}`;
}

function batchStaticGroupByMaterial(groupRoot, { skipPrefixes = [], batchName = "STATIC_BATCH" } = {}) {
  if (!groupRoot) return;
  groupRoot.updateMatrixWorld(true);
  const rootInv = groupRoot.matrixWorld.clone().invert();
  const buckets = new Map();
  const toHide = [];

  groupRoot.traverse((obj) => {
    if (!obj.isMesh || !obj.geometry) return;
    let cur = obj;
    let skip = false;
    while (cur && cur !== groupRoot) {
      if (cur.name && (cur.name.endsWith("_BATCH") || skipPrefixes.some((p) => cur.name.startsWith(p)))) {
        skip = true;
        break;
      }
      cur = cur.parent;
    }
    if (skip) return;

    const mat = Array.isArray(obj.material) ? obj.material[0] : obj.material;
    if (!mat) return;
    if (!obj.geometry.boundingBox) obj.geometry.computeBoundingBox();

    const relMat = new THREE.Matrix4().multiplyMatrices(rootInv, obj.matrixWorld);
    const keepUv = !!mat.map && !!obj.geometry.getAttribute("uv");
    const key = `${materialBatchSignature(mat)}:${keepUv ? 1 : 0}`;
    let bucket = buckets.get(key);
    if (!bucket) {
      bucket = { mat: mat.clone(), geos: [] };
      buckets.set(key, bucket);
    }

    const g = obj.geometry.clone();
    for (const attrName of Object.keys(g.attributes)) {
      if (attrName !== "position" && attrName !== "normal" && (!keepUv || attrName !== "uv")) {
        g.deleteAttribute(attrName);
      }
    }
    g.applyMatrix4(relMat);
    if (!g.getAttribute("normal")) g.computeVertexNormals();
    if (!g.index) {
      const cnt = g.attributes.position.count;
      const idxArr = new Uint32Array(cnt);
      for (let i = 0; i < cnt; i++) idxArr[i] = i;
      g.setIndex(new THREE.BufferAttribute(idxArr, 1));
    } else if (relMat.determinant() < 0) {
      const ix = g.index;
      for (let t = 0; t + 2 < ix.count; t += 3) {
        const b = ix.getX(t + 1);
        ix.setX(t + 1, ix.getX(t + 2));
        ix.setX(t + 2, b);
      }
    }
    bucket.geos.push(g);
    toHide.push(obj);
  });

  if (!buckets.size) return;
  const batchGroup = new THREE.Group();
  batchGroup.name = batchName;
  let bi = 0;
  for (const { mat, geos } of buckets.values()) {
    const merged = mergeGeometries(geos, false);
    geos.forEach((g) => g.dispose());
    if (!merged) continue;
    const m = new THREE.Mesh(merged, mat);
    m.name = `${batchName}_${bi++}`;
    batchGroup.add(m);
  }
  groupRoot.add(batchGroup);
  for (const orig of toHide) {
    orig.userData.batched = true;
    orig.visible = false;
  }
}

function loadSvgImage(svgText) {
  return new Promise((resolve) => {
    const img = new Image();
    const url = URL.createObjectURL(new Blob([svgText], { type: "image/svg+xml;charset=utf-8" }));
    img.onload = () => { URL.revokeObjectURL(url); resolve(img); };
    img.onerror = () => { URL.revokeObjectURL(url); resolve(null); };
    img.src = url;
  });
}

function recolorKiCadSvg(svgText, hexColor, forceOpaqueFill = false) {
  let out = svgText.replace(/(fill|stroke):#[0-9A-Fa-f]{6}/g, `$1:${hexColor}`);
  if (forceOpaqueFill) out = out.replace(/fill-opacity:\s*[0-9.]+/g, "fill-opacity:1.0");
  return out;
}

async function bakePcbSideTexture({ cuSvg, maskSvg, silkSvg, edgeSvg, outline, size = 2048, flipY = true }) {
  const [cuSubtleImg, cuGoldImg, maskOpaqueImg, silkImg] = await Promise.all([
    loadSvgImage(recolorKiCadSvg(cuSvg, "#247236")),
    loadSvgImage(recolorKiCadSvg(cuSvg, "#e0be5c")),
    loadSvgImage(recolorKiCadSvg(maskSvg, "#ffffff", true)),
    loadSvgImage(recolorKiCadSvg(silkSvg, "#f0f4f8")),
  ]);

  const cvs = document.createElement("canvas");
  cvs.width = size;
  cvs.height = size;
  const ctx = cvs.getContext("2d");

  const xmin = outline.xmin ?? 89;
  const ymin = outline.ymin ?? 82.75;
  const wMm = outline.width_mm || 140;
  const hMm = outline.height_mm || 132;
  const pts = outline.segments?.[0] || [];

  const traceOutlineClip = (c) => {
    c.beginPath();
    if (pts.length >= 3) {
      pts.forEach(([kx, ky], i) => {
        const px = ((kx - xmin) / wMm) * size;
        const py = ((ky - ymin) / hMm) * size;
        if (i === 0) c.moveTo(px, py);
        else c.lineTo(px, py);
      });
      c.closePath();
    } else {
      c.rect(0, 0, size, size);
    }
  };

  ctx.save();
  traceOutlineClip(ctx);
  ctx.clip();

  // Base green solder mask
  ctx.fillStyle = "#164b25";
  ctx.fillRect(0, 0, size, size);

  // Subtle copper relief underneath solder mask
  if (cuSubtleImg) {
    ctx.globalAlpha = 0.56;
    ctx.drawImage(cuSubtleImg, 0, 0, size, size);
    ctx.globalAlpha = 1.0;
  }

  // Exposed ENIG gold pads & test points through solder mask openings
  if (cuGoldImg && maskOpaqueImg) {
    const exp = document.createElement("canvas");
    exp.width = size;
    exp.height = size;
    const ec = exp.getContext("2d");
    ec.drawImage(cuGoldImg, 0, 0, size, size);
    ec.globalCompositeOperation = "destination-in";
    ec.drawImage(maskOpaqueImg, 0, 0, size, size);
    ctx.drawImage(exp, 0, 0);
  }

  // Crisp component legend silkscreen
  if (silkImg) {
    ctx.globalAlpha = 0.94;
    ctx.drawImage(silkImg, 0, 0, size, size);
    ctx.globalAlpha = 1.0;
  }
  ctx.restore();

  // Punch drilled mounting & THT holes from Edge_Cuts.svg so FR4 holes show cleanly
  if (edgeSvg) {
    const vbMatch = edgeSvg.match(/viewBox="0\.0000\s+0\.0000\s+([0-9.]+)\s+([0-9.]+)"/);
    const svgW = vbMatch ? parseFloat(vbMatch[1]) : wMm;
    const svgH = vbMatch ? parseFloat(vbMatch[2]) : hMm;
    ctx.save();
    ctx.globalCompositeOperation = "destination-out";
    ctx.fillStyle = "#000000";
    const circRe = /<circle\s+cx="([0-9.]+)"\s+cy="([0-9.]+)"\s+r="([0-9.]+)"/g;
    let m;
    while ((m = circRe.exec(edgeSvg)) !== null) {
      const cx = (parseFloat(m[1]) / svgW) * size;
      const cy = (parseFloat(m[2]) / svgH) * size;
      const r = (parseFloat(m[3]) / svgW) * size;
      ctx.beginPath();
      ctx.arc(cx, cy, r, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.restore();
  }

  const tex = new THREE.CanvasTexture(cvs);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = Math.min(4, renderer?.capabilities?.getMaxAnisotropy?.() || 1);
  tex.flipY = flipY;
  tex.needsUpdate = true;
  return tex;
}

async function bakePcbSurfaceTextures(boardRoot, outline = catalogue?.board_outline, layerDir = "assets/layers") {
  let pcbNode = null;
  boardRoot.traverse((o) => {
    if (!pcbNode && (o.name === "PCB_LAYER_PCB" || o.name === "PCB_PCB")) pcbNode = o;
  });
  if (!pcbNode || !outline) return;

  boardRoot.updateMatrixWorld(true);
  const rootInv = boardRoot.matrixWorld.clone().invert();
  const pcbLocalBox = new THREE.Box3();
  const v = new THREE.Vector3();
  pcbNode.traverse((m) => {
    if (!m.isMesh || !m.geometry?.attributes?.position) return;
    const rel = new THREE.Matrix4().multiplyMatrices(rootInv, m.matrixWorld);
    const pos = m.geometry.attributes.position;
    for (let i = 0; i < pos.count; i++) {
      v.fromBufferAttribute(pos, i).applyMatrix4(rel);
      pcbLocalBox.expandByPoint(v);
    }
  });
  if (pcbLocalBox.isEmpty()) return;

  const [edgeSvg, fCuSvg, fMaskSvg, fSilkSvg, bCuSvg, bMaskSvg, bSilkSvg] = await Promise.all(
    ["Edge_Cuts.svg", "F_Cu.svg", "F_Mask.svg", "F_SilkS.svg", "B_Cu.svg", "B_Mask.svg", "B_SilkS.svg"].map(
      (f) => fetch(`${layerDir}/${f}`).then((r) => (r.ok ? r.text() : ""))
    )
  );
  if (!fCuSvg || !bCuSvg) return;

  const [topTex, botTex] = await Promise.all([
    bakePcbSideTexture({ cuSvg: fCuSvg, maskSvg: fMaskSvg, silkSvg: fSilkSvg, edgeSvg, outline, flipY: true }),
    bakePcbSideTexture({ cuSvg: bCuSvg, maskSvg: bMaskSvg, silkSvg: bSilkSvg, edgeSvg, outline, flipY: false }),
  ]);

  const w = pcbLocalBox.max.x - pcbLocalBox.min.x;
  const h = pcbLocalBox.max.z - pcbLocalBox.min.z;
  const cx = (pcbLocalBox.min.x + pcbLocalBox.max.x) * 0.5;
  const cz = (pcbLocalBox.min.z + pcbLocalBox.max.z) * 0.5;

  const topGeo = new THREE.PlaneGeometry(w, h);
  topGeo.rotateX(-Math.PI / 2);
  const topMat = new THREE.MeshStandardMaterial({
    map: topTex,
    roughness: 0.48,
    metalness: 0.10,
    alphaTest: 0.5,
    side: THREE.FrontSide,
    polygonOffset: true,
    polygonOffsetFactor: -1,
  });
  const topMesh = new THREE.Mesh(topGeo, topMat);
  topMesh.name = "PCB_BAKED_TOP";
  topMesh.position.set(cx, pcbLocalBox.max.y + 0.000015, cz);
  boardRoot.add(topMesh);

  const botGeo = new THREE.PlaneGeometry(w, h);
  botGeo.rotateX(Math.PI / 2);
  const botMat = new THREE.MeshStandardMaterial({
    map: botTex,
    roughness: 0.48,
    metalness: 0.10,
    alphaTest: 0.5,
    side: THREE.FrontSide,
    polygonOffset: true,
    polygonOffsetFactor: -1,
  });
  const botMesh = new THREE.Mesh(botGeo, botMat);
  botMesh.name = "PCB_BAKED_BOTTOM";
  botMesh.position.set(cx, pcbLocalBox.min.y - 0.000015, cz);
  boardRoot.add(botMesh);

  requestRender();
}

async function loadModelsWithProgress() {
  const loader = new GLTFLoader();
  loader.setMeshoptDecoder(MeshoptDecoder);
  const progressMap = { board: 0, kv: 0, enc: 0 };
  const updateLoaderUi = (label) => {
    const avg = (progressMap.board * 0.72 + progressMap.kv * 0.14 + progressMap.enc * 0.14);
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

  // Progressive load: display adapter board first while streaming KV260 & enclosure
  const bGltf = await loadGlb("assets/board.glb", "board", "board.glb");
  boardModel = bGltf.scene;
  adapterGroup.add(boardModel);
  collect(boardModel);
  refreshBoardPickerBounds(catalogue);
  batchStaticGroupByMaterial(boardModel, { skipPrefixes: ["PCB_"], batchName: "BOARD_BATCH" });
  setCameraPreset("iso", true);
  requestRender();
  if (renderer) renderer.render(scene, camera);

  const bakePromise = bakePcbSurfaceTextures(boardModel);
  const [kGltf, eGltf] = await Promise.all([
    loadGlb("assets/kv260.glb", "kv", "kv260.glb"),
    loadGlb("assets/enclosure.glb", "enc", "enclosure.glb"),
    bakePromise,
  ]);

  kv260Model = kGltf.scene;
  assemblyRoot.add(kv260Model);
  collect(kv260Model);
  batchStaticGroupByMaterial(kvNodes.KV260_CARRIER_GROUP, { batchName: "KV_CARRIER_BATCH" });
  batchStaticGroupByMaterial(kvNodes.K26_SOM_GROUP, { batchName: "KV_SOM_BATCH" });
  batchStaticGroupByMaterial(kvNodes.KV260_FAN, { batchName: "KV_FAN_BATCH" });
  batchStaticGroupByMaterial(kvNodes.KV260_HEATSINK, { batchName: "KV_HS_BATCH" });

  enclosureModel = eGltf.scene;
  assemblyRoot.add(enclosureModel);
  collect(enclosureModel);
  batchStaticGroupByMaterial(encNodes.ENCLOSURE_BOTTOM_GROUP, { batchName: "ENC_BOT_BATCH" });
  batchStaticGroupByMaterial(encNodes.ENCLOSURE_BUMPERS_GROUP, { batchName: "ENC_BMP_BATCH" });
  batchStaticGroupByMaterial(encNodes.ENCLOSURE_LID_GROUP, { batchName: "ENC_LID_BATCH" });
  batchStaticGroupByMaterial(encNodes.ADAPTER_HEATSINKS_GROUP, { batchName: "ENC_HS_BATCH" });

  if (psuData) {
    try {
      const pGltf = await loadGlb("assets/psu_board.glb", "psu", "psu_board.glb");
      psuModel = pGltf.scene;
      psuModel.traverse((o) => {
        if (o.name && partById.has(`PSU:${o.name}`) && !nodeById.has(`PSU:${o.name}`)) {
          o.name = `PSU:${o.name}`;
          nodeById.set(o.name, o);
        }
      });
      psuGroup.add(psuModel);
      await bakePcbSurfaceTextures(psuModel, psuData.board_outline, "assets/psu_layers");
      try {
        const cGltf = await loadGlb("assets/psu_case.glb", "psucase", "psu_case.glb");
        psuCaseModel = cGltf.scene;
        psuCaseModel.traverse((o) => {
          if (o.name === "PSU_CASE_TRAY") psuCaseNodes.tray = o;
          if (o.name === "PSU_CASE_LID") psuCaseNodes.lid = o;
        });
        psuGroup.add(psuCaseModel);
      } catch (err) {
        console.warn("PSU enclosure not loaded", err);
      }
      placePsuBeside();
    } catch (err) {
      console.warn("PSU board not loaded", err);
    }
  }

  setCameraPreset("iso", true);
  requestRender();
}

// The PSU board lies beside the assembly on the same floor, 40 mm clear of it, J1 (the battery) towards the case
function placePsuBeside() {
  const wasVisible = psuGroup.visible;
  psuGroup.visible = false;
  scene.updateMatrixWorld(true);
  const box = new THREE.Box3();
  for (const o of [adapterGroup, kv260Model, enclosureModel]) if (o) box.expandByObject(o);
  psuGroup.visible = wasVisible;
  const [cx, cy] = PSU_CENTRE_MM;
  const halfW = 0.071; // the enclosure's cable shelf reaches 70.5 mm left of the board's centre
  psuGroup.position.set(box.max.x + 0.04 + halfW - cx * 0.001, box.min.y + PSU_TRAY_BOTTOM_M,
    (box.min.z + box.max.z) / 2 - cy * 0.001);
  applyAnimatedScene();
  refreshPsuPickerBounds();
  applyAnimatedScene();
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
  let moved = false;

  // 1. Intro sequence (~2050 ms total, interruptible)
  if (tweenHandles.intro) {
    const tr = tweenHandles.intro;
    const u = Math.min(1, (now - tr.start) / tr.dur);
    applyIntroAtProgress(u);
    moved = true;
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
    moved = true;
    if (u >= 1) tweenHandles.cam = null;
  }

  if (dirty) applyAnimatedScene();
  return dirty || moved;
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
  const showPsu = !!psuModel && (state.isolateMode === "all" || state.isolateMode === "psu");
  psuGroup.visible = showPsu;

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
  // the PSU's enclosure follows the same Closed / Open Lid / No Case buttons and the explode slider
  const psuCaseVis = showPsu && !!psuCaseModel && anim.caseVisFade > 0.02;
  if (psuCaseModel) {
    psuCaseModel.visible = psuCaseVis;
    if (psuCaseNodes.tray) psuCaseNodes.tray.position.y = -0.02 * t - hideSlide * 0.6;
    if (psuCaseNodes.lid) psuCaseNodes.lid.position.y = anim.lidOpen * 0.045 + 0.05 * t + hideSlide;
  }
  // a closed lid hides the PSU's parts from the pointer, as the main case does the adapter's
  const psuPick = showPsu && !(psuCaseVis && anim.lidOpen < 0.5 && t < 0.2);

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
  simCtrl?.updateAnimatedOffsets();

  if (siteCore) {
    const mask =
      (showBoard ? 1 << 0 : 0) |
      (showKv ? 1 << 1 : 0) |
      (showKv ? 1 << 2 : 0) |
      (fanVis ? 1 << 3 : 0) |
      (hsVis ? 1 << 4 : 0) |
      (caseVis ? 1 << 5 : 0) |
      (caseVis ? 1 << 6 : 0) |
      (showThermal ? 1 << 7 : 0) |
      (psuPick ? 1 << 8 : 0);
    const offsets = new Float32Array([
      yBoard,
      0.0,
      ySom,
      yCoolingBase + yFanSlide,
      yCoolingBase + yHsSlide,
      yBottom,
      yLid,
      yAdpHs,
      0.0,
    ]);
    siteCore.set_group_transforms(offsets, mask);
  }
  requestRender();
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
    psuModel ? psuGroup : null,
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
    requestRender();
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
  requestRender();
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
  let lastHoverId = null;

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

    const nextId = found && found.object ? found.id : null;
    if (found && found.object) {
      const entry = partById.get(found.id);
      const pcbPart = entry.kind === "board" || entry.kind === "psu";
      const label = pcbPart
        ? `${entry.kind === "psu" ? "PSU " : ""}${entry.data.ref} &middot; ${escapeHtml(entry.data.value)}`
        : `${entry.data.ref || entry.data.id} &middot; ${escapeHtml(entry.data.part || entry.data.value)}`;
      const role = pcbPart ? entry.data.description : entry.data.role;
      const simTip = entry.kind === "psu" ? psuHoverHtml(entry.data) : simCtrl ? simCtrl.buildHoverHtml(found.id) : "";
      tip.innerHTML = `<strong>${label}</strong><br><span style="color:var(--text-muted)">${escapeHtml((role || "").slice(0, 88))}</span>${simTip}`;
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
    if (nextId !== lastHoverId) {
      lastHoverId = nextId;
      requestRender();
    }
  });

  canvas.addEventListener("pointerleave", () => {
    tip.style.display = "none";
    if (hoverBox.visible || lastHoverId !== null) {
      hoverBox.visible = false;
      lastHoverId = null;
      requestRender();
    }
  });

  // A click selects (or, on empty space, clears); an orbit, pan or pinch never does, even one that ends where it
  // started: the press counts the farthest the pointer went, how long it lasted and how many pointers took part
  const downPointers = new Set();
  canvas.addEventListener("pointerdown", (ev) => {
    downPointers.add(ev.pointerId);
    if (downPointers.size > 1) { if (downPos) downPos.multi = true; return; }
    downPos = { x: ev.clientX, y: ev.clientY, t: performance.now(), far: 0, multi: false };
  });
  canvas.addEventListener("pointermove", (ev) => {
    if (downPos && downPointers.has(ev.pointerId)) {
      downPos.far = Math.max(downPos.far, Math.hypot(ev.clientX - downPos.x, ev.clientY - downPos.y));
    }
  });
  canvas.addEventListener("pointercancel", (ev) => { downPointers.delete(ev.pointerId); downPos = null; });

  canvas.addEventListener("pointerup", (ev) => {
    downPointers.delete(ev.pointerId);
    if (!downPos || !state.ready) return;
    const press = downPos;
    if (downPointers.size === 0) downPos = null;
    else return;
    const moved = Math.max(press.far, Math.hypot(ev.clientX - press.x, ev.clientY - press.y));
    if (moved > 5 || press.multi || ev.button !== 0 || performance.now() - press.t > 450) return;
    const { nx, ny } = getNdc(ev);
    const found = pickAtNdc(nx, ny);
    if (found) selectPart(found.id, false);
    else clearSelection();
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
      if (cur === psuGroup) { setIsolate(state.isolateMode === "psu" ? "all" : "psu"); return; }
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
    requestRender();
    return;
  }
  const obj = nodeById.get(state.selectedId);
  if (!obj || !isObjectEffectivelyVisible(obj)) {
    selectBox.visible = false;
    requestRender();
    return;
  }
  selectBox.box.setFromObject(obj);
  selectBox.visible = !selectBox.box.isEmpty();
  requestRender();
}

function isObjectEffectivelyVisible(obj) {
  let c = obj;
  while (c) {
    if (!c.visible && !c.userData?.batched) return false;
    c = c.parent;
  }
  return true;
}

function isPowerNetName(n) {
  if (psuNet(n)) return netLabel(n) === "GND"; // on the PSU board the power nets are the signals that matter
  return /^(?:\+|-)\d|^(?:VCC|VDD|VBUS|VREF|VIN|VBAT|GND|AGND|DGND)/i.test(String(n || "").trim());
}

function pickPrimaryNetForComponent(c) {
  const nonGnd = (c.nets || []).filter((n) => n && !/^(?:GND|AGND|DGND)$/i.test(netLabel(n).trim()));
  const sig = nonGnd.find((n) => !isPowerNetName(n) && (netTraces[n]?.length || 0) > 0);
  if (sig) return { net: sig, isPower: false };
  const pwr = nonGnd.find((n) => (netTraces[n]?.length || 0) > 0);
  if (pwr) return { net: pwr, isPower: true };
  return { net: null, isPower: false };
}

function clearSelection() {
  state.selectedId = null;
  state.partAllNets = null;
  state.activeNet = null;
  state.activeNetIsPower = false;
  updateSelectionBox();
  rebuildNetHighlightBoxes();
  const body = $("#inspector-body");
  const empty = $("#inspector-empty");
  if (body) body.style.display = "none";
  if (empty) empty.style.display = "";
  const st = $("#hud-status");
  if (st) st.textContent = "Hover or tap any component";
  simCtrl?.onDeselect?.();
  syncHash();
  requestRender();
}

function rebuildNetHighlightBoxes() {
  for (const g of [netHighlightGroup, netPulseGroup, psuPulseGroup]) {
    while (g.children.length) g.remove(g.children[0]);
  }
  activeTraceSegs = [];
  activePulseMesh = null;

  if (state.allNets) {
    buildAllNetTraces(Object.keys(netTraces));
    requestRender();
    return;
  }
  if (state.partAllNets && partById.get(state.partAllNets)) {
    const nets = partById.get(state.partAllNets).data.nets || [];
    buildAllNetTraces(nets, true);
    const st = $("#hud-status");
    if (st) st.innerHTML = `<strong>${escapeHtml(netLabel(state.partAllNets))}</strong>: all ${nets.length} nets`;
    requestRender();
    return;
  }
  const onPsu = psuNet(state.activeNet);
  const host = onPsu ? psuGroup : adapterGroup;
  if (!state.activeNet || !host.visible) {
    requestRender();
    return;
  }
  const dimPower = !!state.activeNetIsPower;
  const refs = netMates(state.activeNet);

  const boxColor = dimPower ? 0x3b82b8 : 0x4cc2ff;
  for (const ref of refs) {
    const obj = nodeById.get(ref);
    if (!obj) continue;
    const bx = new THREE.Box3().setFromObject(obj);
    if (!bx.isEmpty()) netHighlightGroup.add(new THREE.Box3Helper(bx, boxColor));
  }

  // Real routed KiCad copper (tracks, and the outline of each pour on the PSU board) + travelling pulses
  const rawSegs = netTraces[state.activeNet] || [];
  if (rawSegs.length) {
    const target = onPsu ? psuPulseGroup : netPulseGroup;
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
    const lineMat = new THREE.LineBasicMaterial({
      color: dimPower ? 0x3b82b8 : 0x4cc2ff,
      transparent: true,
      opacity: dimPower ? 0.44 : 0.92,
    });
    target.add(new THREE.LineSegments(lineGeo, lineMat));

    const dotCount = dimPower ? Math.min(12, Math.max(4, activeTraceSegs.length)) : Math.min(28, Math.max(8, activeTraceSegs.length));
    const dotGeo = new THREE.SphereGeometry(dimPower ? 0.00036 : 0.00045, 8, 8);
    const dotMat = new THREE.MeshBasicMaterial({ color: dimPower ? 0x93c5fd : 0xffb020 });
    activePulseMesh = new THREE.InstancedMesh(dotGeo, dotMat, dotCount);
    target.add(activePulseMesh);
    stepPulseDots(performance.now());
  }
  requestRender();
}

function netMates(net) {
  return siteCore
    ? Array.from(siteCore.net_mates(net)).map((idx) => partList[idx]).filter(Boolean)
    : (compByNet.get(net) || []);
}

// Several nets at once, each in its own colour (power and ground dimmed): every routed net of the boards on show
// (the Nets panel), or every net of one part with a box round each part it reaches (its inspector)
function netHue(name) {
  let h = 2166136261;
  for (let i = 0; i < name.length; i++) h = Math.imul(h ^ name.charCodeAt(i), 16777619);
  return ((h >>> 0) % 360) / 360;
}

function buildAllNetTraces(names, withParts = false) {
  const c = new THREE.Color();
  const groups = [
    { host: adapterGroup, target: netPulseGroup, psu: false },
    { host: psuGroup, target: psuPulseGroup, psu: true },
  ];
  let nNets = 0;
  let total = 0;
  const seenParts = new Set();
  for (const g of groups) {
    if (!g.host.visible) continue;
    const mine = names.filter((n) => psuNet(n) === g.psu);
    let count = 0;
    for (const n of mine) count += (netTraces[n] || []).length;
    const verts = new Float32Array(count * 6);
    const cols = new Float32Array(count * 6);
    let o = 0;
    for (const n of mine) {
      const power = isPowerNetName(n);
      if (power) c.setHSL(0.58, 0.35, 0.32);
      else c.setHSL(netHue(n), 0.85, 0.58);
      for (const [x1, y1, x2, y2, lIdx] of netTraces[n] || []) {
        const yLocal = lIdx <= 3 ? 0.00172 : -0.00009;
        verts.set([x1 * 0.001, yLocal, y1 * 0.001, x2 * 0.001, yLocal, y2 * 0.001], o);
        cols.set([c.r, c.g, c.b, c.r, c.g, c.b], o);
        o += 6;
      }
      if (withParts) {
        for (const ref of netMates(n)) {
          if (seenParts.has(ref) || ref === state.partAllNets) continue;
          seenParts.add(ref);
          const obj = nodeById.get(ref);
          if (!obj) continue;
          const bx = new THREE.Box3().setFromObject(obj);
          if (!bx.isEmpty()) netHighlightGroup.add(new THREE.Box3Helper(bx, power ? 0x3b82b8 : c.getHex()));
        }
      }
      nNets++;
    }
    total += count;
    if (count) {
      const geo = new THREE.BufferGeometry();
      geo.setAttribute("position", new THREE.BufferAttribute(verts, 3));
      geo.setAttribute("color", new THREE.BufferAttribute(cols, 3));
      g.target.add(new THREE.LineSegments(geo, new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, opacity: 0.9 })));
    }
  }
  const st = $("#hud-status");
  if (st && !withParts) st.textContent = `All nets: ${nNets} nets, ${total} copper segments`;
  return { nNets, total, parts: seenParts.size };
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

function selectPart(id, shouldFocus = true, autoHighlightNet = true) {
  const entry = partById.get(id);
  if (!entry) return;
  if (state.partAllNets && state.partAllNets !== id) state.partAllNets = null;
  state.selectedId = id;
  const pcbPart = entry.kind === "board" || entry.kind === "psu";
  if (entry.kind === "psu" && !psuGroup.visible) setIsolate("psu", true);
  if (entry.kind === "psu" && psuCaseModel && state.enclosureMode === "closed") setEnclosure("open");
  if (autoHighlightNet && !applyingHash) {
    if (pcbPart) {
      const picked = pickPrimaryNetForComponent(entry.data);
      state.activeNet = picked.net;
      state.activeNetIsPower = picked.isPower;
    } else {
      state.activeNet = null;
      state.activeNetIsPower = false;
    }
  } else {
    state.activeNetIsPower = !!(state.activeNet && isPowerNetName(state.activeNet));
  }
  rebuildNetHighlightBoxes();
  updateSelectionBox();
  if (shouldFocus) focusPartCamera(id);

  $("#inspector-empty").style.display = "none";
  const body = $("#inspector-body");
  body.style.display = "flex";

  if (pcbPart) {
    const c = entry.data;
    const isPsu = entry.kind === "psu";
    const auditLine = isPsu ? null : simCtrl?.getPartAuditLine?.(id) || null;
    const padRows = Object.entries(c.pads || {}).slice(0, 40).map(
      ([pin, net]) => `<tr><td class="mono">${escapeHtml(pin)}</td><td>${net === "(nc)" ? '<span class="mono" style="color:var(--text-muted)">(nc)</span>' : `<button type="button" class="net-chip ${state.activeNet === net ? "active" : ""}" data-net="${escapeHtml(net)}">${escapeHtml(netLabel(net))}</button>`}</td></tr>`
    ).join("");
    const netButtons = (c.nets || []).map(
      (n) => `<button type="button" class="net-chip ${state.activeNet === n || state.partAllNets === id ? "active" : ""}" data-net="${escapeHtml(n)}">${escapeHtml(netLabel(n))}</button>`
    ).join("");
    const allOn = state.partAllNets === id;

    body.innerHTML = `
      <div class="panel-card">
        <div class="control-row">
          <span class="badge ${isPsu ? "badge-cyan" : ""}">${isPsu ? "PSU BOARD" : "REV08 ADAPTER"}</span>
          <span class="mono" style="color:var(--text-muted)">${escapeHtml(c.side)} &middot; ${escapeHtml(c.sheet || "-")}</span>
        </div>
        <h2 style="margin:0;font-size:17px;">${escapeHtml(c.ref)} <small style="font-weight:500;color:var(--text-muted)">${escapeHtml(c.value)}</small></h2>
        <p style="margin:0;font-size:12px;">${escapeHtml(c.description || "no description yet")}</p>
        ${auditLine ? `
        <div class="audit-callout">
          <div class="control-row">
            <strong>Rev08 Audit (${escapeHtml(auditLine.code)}): ${escapeHtml(auditLine.title)}</strong>
            <button type="button" class="net-chip sim-jump-btn" data-sim-jump-domain="audit" data-sim-jump-target="${escapeHtml(id)}">Audit 3-D</button>
          </div>
          <p style="margin:0;font-size:11px;line-height:1.4;">${escapeHtml(auditLine.summary)}</p>
          <div class="mono" style="font-size:10px;color:var(--text-muted);">
            <a href="${docToPdfHref(auditLine.doc_link || "docs/AUDIT_Rev08.md")}" target="_blank" rel="noopener">docs/AUDIT_Rev08.md (p.180)</a> &middot; ${escapeHtml(auditLine.source_file)}
          </div>
        </div>` : ""}
        ${c.callout ? `<p style="margin:0;font-size:11px;color:var(--cyan)"><strong>Manual callout:</strong> ${escapeHtml(c.callout)}</p>` : ""}
        <div class="btn-grid-3">
          <button id="insp-focus-btn" class="btn btn-sm btn-primary" type="button">Focus Camera</button>
          <a class="btn btn-sm" style="text-align:center" href="${docToPdfHref(c.manual_link || "docs/BOARD_MANUAL.md")}" target="_blank" rel="noopener">${isPsu ? "PSU_SPEC" : "Manual"}</a>
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
      ${isPsu ? psuAnalysisHtml(c) : ""}

      <div class="panel-card">
        <div class="control-row">
          <h3>Nets (${(c.nets || []).length})</h3>
          <span style="display:flex;gap:6px;">
            ${(c.nets || []).length > 1 ? `<button id="insp-all-nets" class="btn btn-sm ${allOn ? "active" : ""}" type="button" aria-pressed="${allOn}">${allOn ? "Clear All Nets" : "Select All Nets"}</button>` : ""}
            ${state.activeNet && !allOn ? `<button id="insp-clear-net" class="btn btn-sm" type="button">Clear Net</button>` : ""}
          </span>
        </div>
        <div class="net-list">${netButtons || '<span style="color:var(--text-muted)">No connected nets</span>'}</div>
        ${state.activeNet || allOn ? `<div id="insp-net-mates" style="font-size:11px;color:var(--cyan);"></div>` : ""}
      </div>

      ${padRows ? `
      <div class="panel-card">
        <h3>Pinout / Pads (${Object.keys(c.pads || {}).length})</h3>
        <table class="kv-table"><thead><tr><th>Pin</th><th>Net</th></tr></thead><tbody>${padRows}</tbody></table>
      </div>` : ""}
      ${simCtrl ? simCtrl.buildInspectorSectionHtml(id) : ""}
    `;

    const mateBox = body.querySelector("#insp-net-mates");
    if (mateBox && allOn) {
      const parts = new Set();
      let segs = 0;
      for (const n of c.nets || []) {
        segs += (netTraces[n] || []).length;
        if (!/^(?:GND|AGND|DGND)$/i.test(netLabel(n))) for (const r of netMates(n)) if (r !== id) parts.add(r);
      }
      const list = [...parts].sort();
      mateBox.innerHTML = `All ${(c.nets || []).length} nets of <code>${escapeHtml(c.ref)}</code> (${segs} copper segments) reach ${list.length} parts besides ground: ` +
        list.slice(0, 60).map((r) => `<button type="button" class="net-chip pick-ref" data-ref="${escapeHtml(r)}">${escapeHtml(netLabel(r))}</button>`).join(" ") +
        (list.length > 60 ? ` +${list.length - 60} more` : "");
    } else if (mateBox && state.activeNet) {
      const mates = compByNet.get(state.activeNet) || [];
      const segCount = (netTraces[state.activeNet] || []).length;
      mateBox.innerHTML = `Connected on <code>${escapeHtml(netLabel(state.activeNet))}</code> (${mates.length} parts, ${segCount} copper segments): ` +
        mates.slice(0, 24).map((r) => `<button type="button" class="net-chip pick-ref" data-ref="${escapeHtml(r)}">${escapeHtml(netLabel(r))}</button>`).join(" ") +
        (mates.length > 24 ? ` +${mates.length - 24} more` : "");
    }
    mateBox?.querySelectorAll(".pick-ref").forEach((b) => b.addEventListener("click", () => selectPart(b.dataset.ref, true)));
    body.querySelector("#insp-all-nets")?.addEventListener("click", () => {
      state.partAllNets = state.partAllNets === id ? null : id;
      if (state.partAllNets) state.activeNet = null;
      rebuildNetHighlightBoxes();
      selectPart(id, false, false);
      if (!state.partAllNets) { const st = $("#hud-status"); if (st) st.innerHTML = `Selected <strong>${escapeHtml(netLabel(id))}</strong>`; }
    });
    body.querySelectorAll("[data-psu-fig]").forEach((b) => b.addEventListener("click", () => {
      const f = psuData?.figures?.[Number(b.dataset.psuFig)];
      if (!f) return;
      $("#img-modal-img").src = f.src;
      $("#img-modal-cap").textContent = `${f.title}: ${f.cap}`;
      $("#img-modal").classList.add("open");
    }));
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
          <a class="btn btn-sm" style="text-align:center" href="${docToPdfHref(k.manual_link || "docs/INTERFACE_SPEC.md")}" target="_blank" rel="noopener">Spec</a>
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
      ${simCtrl ? simCtrl.buildInspectorSectionHtml(id) : ""}
    `;
  }

  simCtrl?.wireInspectorButtons(body);
  body.querySelector("#insp-focus-btn")?.addEventListener("click", () => focusPartCamera(id));
  body.querySelector("#insp-copy-link")?.addEventListener("click", (ev) => {
    syncHash();
    navigator.clipboard?.writeText(location.href).catch(() => {});
    ev.target.textContent = "Copied!";
    setTimeout(() => { ev.target.textContent = "Copy Link"; }, 1200);
  });
  body.querySelector("#insp-clear-net")?.addEventListener("click", () => {
    state.activeNet = null;
    state.activeNetIsPower = false;
    rebuildNetHighlightBoxes();
    selectPart(id, false, false);
    syncHash();
  });
  body.querySelectorAll("[data-net]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const next = state.activeNet === btn.dataset.net ? null : btn.dataset.net;
      state.partAllNets = null;
      state.activeNet = next;
      state.activeNetIsPower = !!(next && isPowerNetName(next));
      rebuildNetHighlightBoxes();
      selectPart(id, false, false);
      syncHash();
    });
  });

  if (state.partAllNets !== id) $("#hud-status").innerHTML = `Selected <strong>${escapeHtml(netLabel(id))}</strong>`;
  syncHash();
}

// PSU board parts: the audit row (psu_audit.py), the IC pins against their absolute maxima, the thermal results
// (psu_thermal.py) and the board's simulation figures
function psuHoverHtml(c) {
  const rows = [];
  if (c.audit) {
    const a = c.audit;
    const txt = a.rating_V ? `${a.stress_V} V of ${a.rating_V} V (${Math.round((a.use || 0) * 100)} %)` : a.rating_W ? `${a.worst_W} W of ${a.rating_W} W` : `${a.stress_V ?? ""} V`;
    rows.push(`<div class="sim-tip-row"><strong style="color:#f59e0b">Audit:</strong> ${escapeHtml(txt)} ${a.ok ? "ok" : "FAIL"}</div>`);
  }
  if (c.thermal) {
    const worst = Object.entries(c.thermal).sort((x, y) => (y[1].junction_C || 0) - (x[1].junction_C || 0))[0];
    if (worst) rows.push(`<div class="sim-tip-row"><strong style="color:var(--cyan)">Thermal:</strong> ${worst[1].junction_C.toFixed(0)} C of ${worst[1].limit_C} C (${escapeHtml(worst[0])})</div>`);
  }
  return rows.join("");
}

function psuAnalysisHtml(c) {
  const parts = [];
  if (c.audit) {
    const a = c.audit;
    parts.push(`<table class="kv-table">
      <tr><th>Checked</th><td>${escapeHtml(a.what || "")}</td></tr>
      ${a.stress_V !== undefined ? `<tr><th>Worst voltage</th><td class="mono">${a.stress_V} V${a.rating_V ? ` of ${a.rating_V} V (${Math.round((a.use || 0) * 100)} %)` : ""}</td></tr>` : ""}
      ${a.worst_W !== undefined ? `<tr><th>Worst power</th><td class="mono">${a.worst_W} W of ${a.rating_W} W</td></tr>` : ""}
      <tr><th>Result</th><td>${a.ok ? "within rating" : "<strong>over rating</strong>"}</td></tr>
    </table>`);
  }
  if (c.ic_pins && c.ic_pins.length) {
    const rows = c.ic_pins.map((p) => `<tr><td class="mono">${escapeHtml(p.pin)}</td><td class="mono">${escapeHtml(p.name || "")}</td><td class="mono">${escapeHtml(p.net || "")}</td><td class="mono">${p.net_max_V ?? "-"} / ${p.absmax_V ?? "-"} V</td></tr>`).join("");
    parts.push(`<table class="kv-table"><thead><tr><th>Pin</th><th>Name</th><th>Net</th><th>Max / abs max</th></tr></thead><tbody>${rows}</tbody></table>`);
  }
  if (c.thermal) {
    const rows = Object.entries(c.thermal).map(([k, v]) => `<tr><td>${escapeHtml(k)}</td><td class="mono">${(v.loss_W ?? 0).toFixed(2)} W</td><td class="mono">${(v.junction_C ?? v.board_C ?? 0).toFixed(0)} / ${v.limit_C ?? "-"} C</td></tr>`).join("");
    parts.push(`<table class="kv-table"><thead><tr><th>Thermal case (70 C air)</th><th>Loss</th><th>Junction / limit</th></tr></thead><tbody>${rows}</tbody></table>`);
  }
  const figs = (psuData?.figures || []).map((f, i) => `<button type="button" class="net-chip" data-psu-fig="${i}">${escapeHtml(f.title)}</button>`).join(" ");
  return `
      <div class="panel-card">
        <h3>Analysis (psu_audit, psu_thermal)</h3>
        ${parts.join("") || '<p style="margin:0;font-size:12px;color:var(--text-muted)">No part-level result: see the figures.</p>'}
        <div class="net-list" style="margin-top:6px;">${figs}</div>
      </div>`;
}

// ---------------------------------------------------------------------------
// 8-Layer PCB Stack-up + Sequential Peel Animation
// ---------------------------------------------------------------------------

function svgToCanvasTexture(svgText, hexColor, height = 1500) {
  return new Promise((resolve) => {
    const img = new Image();
    const blob = new Blob([svgText], { type: "image/svg+xml;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    img.onload = () => {
      const cvs = document.createElement("canvas");
      cvs.width = 1600;
      cvs.height = height;
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
  const canvas = $("#layer-webgl-canvas");
  layerRenderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
  layerRenderer.setClearColor(0x000000, 0);
  layerRenderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
  layerRenderer.outputColorSpace = THREE.SRGBColorSpace;

  layerScene = new THREE.Scene();
  layerScene.add(new THREE.AmbientLight(0xffffff, 1.0));
  layerCamera = new THREE.PerspectiveCamera(36, 16 / 9, 0.005, 4.0);
  layerCamera.position.set(0.14, 0.14, 0.16);
  layerControls = new OrbitControls(layerCamera, canvas);
  layerControls.enableDamping = true;
  layerControls.addEventListener("change", requestLayerRender);
  layerScene.add(layerPlanesGroup);

  const resizeLayers = () => {
    const wrap = canvas.parentElement;
    if (!wrap) return;
    const w = Math.max(100, wrap.clientWidth);
    const h = Math.max(100, wrap.clientHeight);
    layerRenderer.setSize(w, h, false);
    layerCamera.aspect = w / h;
    layerCamera.updateProjectionMatrix();
    requestLayerRender();
  };
  canvas._resizeFn = resizeLayers;
  new ResizeObserver(resizeLayers).observe(canvas.parentElement);
  resizeLayers();

  await loadLayerBoard("main");

  const tickLayers = (now) => {
    requestAnimationFrame(tickLayers);
    if (state.tab === "layers") {
      if (layerPeelStart >= 0) {
        updateLayerStackVisuals(now);
        layerNeedsRender = true;
      }
      if (layerControls.update()) layerNeedsRender = true;
      if (layerNeedsRender) {
        layerRenderer.render(layerScene, layerCamera);
        layerNeedsRender = false;
      }
    }
  };
  requestAnimationFrame(tickLayers);
}

// The Layers tab shows one board at a time: the adapter (8 copper layers) or the PSU board (4).
const LAYER_BOARDS = {
  main: {
    title: "8-Layer Stack-up",
    hud: "3-D Sequentially Peeled 8-Cu Stack-up (KiCad vector SVGs)",
    dir: "assets/layers",
    stack: () => [
      ...catalogue.layer_stack,
      { id: "B.Mask", name: "Bottom Soldermask", color: "#2d7d3a" },
      { id: "B.SilkS", name: "Bottom Silkscreen", color: "#d6dbe0" },
    ],
    outline: () => catalogue.board_outline,
  },
  psu: {
    title: "PSU 4-Layer Stack-up",
    hud: "3-D Sequentially Peeled 4-Cu Stack-up of the PSU board (KiCad vector SVGs)",
    dir: "assets/psu_layers",
    stack: () => [
      ...(psuData?.layer_stack || []),
      { id: "B.Mask", name: "Bottom Soldermask", color: "#2d7d3a" },
      { id: "B.SilkS", name: "Bottom Silkscreen", color: "#d6dbe0" },
    ],
    outline: () => psuData?.board_outline,
  },
};
let layerBoard = "main";
let layerLoadToken = 0;

async function loadLayerBoard(board) {
  if (board === "psu" && !psuData?.layer_stack) board = "main";
  const cfg = LAYER_BOARDS[board];
  const token = ++layerLoadToken;
  layerBoard = board;
  document.querySelectorAll("[data-layer-board]").forEach((b) => {
    const on = b.dataset.layerBoard === board;
    b.classList.toggle("active", on);
    b.setAttribute("aria-pressed", String(on));
  });
  $("#layer-stack-title").textContent = cfg.title;
  $("#layer-hud").textContent = cfg.hud;

  const outline = cfg.outline() || {};
  const wMm = outline.width_mm || 140.0;
  const hMm = outline.height_mm || 132.0;
  const allLayers = cfg.stack().map((L) => ({ ...L, svgPath: L.svg || `${cfg.dir}/${L.id.replace(/\./g, "_")}.svg` }));
  const texH = Math.round(1600 * hMm / wMm);
  const textures = await Promise.all(allLayers.map(async (L) => {
    try {
      const r = await fetch(L.svgPath);
      if (r.ok) return await svgToCanvasTexture(await r.text(), L.color, texH);
    } catch (_) { /* ignore */ }
    return null;
  }));
  if (token !== layerLoadToken) {
    textures.forEach((t) => t?.dispose());
    return;
  }

  for (const e of layerEntries) {
    e.mesh.material.map?.dispose();
    e.mesh.material.dispose();
    layerPlanesGroup.remove(e.mesh);
  }
  layerEntries.length = 0;
  const listEl = $("#layer-list");
  listEl.innerHTML = "";

  const geom = new THREE.PlaneGeometry(wMm * 0.001, hMm * 0.001);
  geom.rotateX(-Math.PI / 2);
  for (let i = 0; i < allLayers.length; i++) {
    const L = allLayers[i];
    const tex = textures[i];
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
    row.className = "layer-row";
    row.dataset.layerId = L.id;
    row.title = L.role || "";
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
  l2dZoom = 1;
  l2dPan = { x: 0, y: 0 };
  apply2dTransform();
  select2dLayer(layerEntries.some((e) => e.meta.id === layerActiveId) ? layerActiveId : "F.Cu");
  if (state.tab === "layers") startLayerPeel();
  syncHash();
}

function startLayerPeel() {
  if (isReducedMotion()) {
    layerPeelStart = -1;
    updateLayerStackVisuals();
    return;
  }
  layerPeelStart = performance.now();
  requestLayerRender();
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
  requestLayerRender();
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
  if (state.tab === "layers" && layerBoard !== "main") p.set("board", layerBoard);
  if (state.theme !== "dark") p.set("theme", state.theme);
  simCtrl?.getHashParams(p);
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
    if (simCtrl?.applyHashParams(p)) touched = true;
    if (p.get("part")) { selectPart(p.get("part"), false); touched = true; }
    if (p.get("board") === "psu") {
      const lay = p.get("layer");
      loadLayerBoard("psu").then(() => { if (lay) select2dLayer(lay); });
      touched = true;
    } else if (p.get("layer")) { select2dLayer(p.get("layer")); touched = true; }
    if (p.get("cam")) { setCameraPreset(p.get("cam"), true); touched = true; }
    if (touched && (p.get("part") || view || p.has("explode") || p.has("sim")) && state.tab === "explorer") {
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
    requestRender();
  } else if (tabId === "layers") {
    $("#layer-webgl-canvas")?._resizeFn?.();
    startLayerPeel();
    requestLayerRender();
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
  simCtrl?.onThemeChange?.();
  requestRender();
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
  $("#hud-stats").textContent = `${catalogue.components.length} Board | ${psuData ? `${psuData.components.length} PSU | ` : ""}${catalogue.kv260_parts.length} KV260 | ${nets} Nets`;
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
  window.addEventListener("keydown", (ev) => {
    if (ev.key !== "Escape") return;
    const modal = $("#img-modal");
    if (modal?.classList.contains("open")) {
      modal.classList.remove("open");
      return;
    }
    drop.classList.remove("open");
    clearSelection();
    if (simCtrl?.isEnabled()) simCtrl.setEnabled(false);
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
  document.querySelectorAll("[data-layer-board]").forEach((b) => {
    b.addEventListener("click", () => { if (b.dataset.layerBoard !== layerBoard) loadLayerBoard(b.dataset.layerBoard); });
  });
  $("#btn-all-nets")?.addEventListener("click", () => {
    state.allNets = !state.allNets;
    const b = $("#btn-all-nets");
    b.classList.toggle("active", state.allNets);
    b.setAttribute("aria-pressed", String(state.allNets));
    b.textContent = state.allNets ? "Clear All Nets" : "Select All Nets";
    if (state.allNets && state.isolateMode !== "psu") setIsolate("board", true);   // the copper shows with the case away
    if (!state.allNets) { const st = $("#hud-status"); if (st) st.textContent = "Hover or tap any component"; }
    rebuildNetHighlightBoxes();
  });
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
  requestRender();

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
    draw_calls: renderer.info.render.calls,
    triangles: renderer.info.render.triangles,
  };
}

function benchmarkRender({ frames = 60, useWasm = true } = {}) {
  const prevWasm = state.useWasmPicker;
  const prevPos = camera.position.clone();
  const prevTgt = controls.target.clone();
  state.useWasmPicker = useWasm;
  const gl = renderer.getContext();
  const pickTimes = [];
  const frameTimes = [];
  const gpuTimes = [];
  let hits = 0;

  for (let i = 0; i < frames; i++) {
    const angle = (i / frames) * 0.35 - 0.175;
    camera.position.copy(prevPos).applyAxisAngle(new THREE.Vector3(0, 1, 0), angle * 0.05);
    camera.lookAt(prevTgt);
    const nx = -0.55 + 1.1 * ((i % 12) / 11);
    const ny = -0.45 + 0.9 * (Math.floor(i / 12) / Math.max(1, Math.floor(frames / 12)));
    const f0 = performance.now();
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
    gl.finish();
    const g1 = performance.now();
    pickTimes.push(p1 - f0);
    frameTimes.push(f1 - f0);
    gpuTimes.push(g1 - f0);
  }
  hoverBox.visible = false;
  camera.position.copy(prevPos);
  controls.target.copy(prevTgt);
  controls.update();
  state.useWasmPicker = prevWasm;
  renderer.render(scene, camera);
  gl.finish();

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
    gpu_flushed_frame_mean_ms: +avg(gpuTimes).toFixed(3),
    draw_calls: renderer.info.render.calls,
    triangles: renderer.info.render.triangles,
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
  clearSelection,
  setCameraPreset: (p) => setCameraPreset(p, true),
  setCameraLookAt: (tx, ty, tz, px, py, pz) => {
    tweenHandles.cam = null;
    controls.target.set(tx, ty, tz);
    camera.position.set(px, py, pz);
    controls.update();
    requestRender();
  },
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
    state.activeNetIsPower = !!(net && isPowerNetName(net));
    rebuildNetHighlightBoxes();
    if (state.selectedId) selectPart(state.selectedId, false, false);
  },
  searchCore: (q) => siteCore ? JSON.parse(siteCore.search(q, 16)).map((i) => partList[i]) : [],
  pickAtNdc,
  projectPartCenterNdc: (id) => {
    const obj = nodeById.get(id);
    if (!obj) return null;
    scene.updateMatrixWorld(true);
    const bx = new THREE.Box3().setFromObject(obj);
    if (bx.isEmpty()) return null;
    const c = bx.getCenter(new THREE.Vector3()).project(camera);
    return { x: c.x, y: c.y, z: c.z };
  },
  benchmarkHover,
  benchmarkRender,
  requestRender,
  setSimMode: (flag, domain, targetId) => (flag ? simCtrl?.activateDomain(domain || "rf", targetId || null) : simCtrl?.setEnabled(false)),
  getSimState: () => simCtrl?.getState() || null,
  getPartSims: (ref) => simCtrl?.getPartSimulations(ref) || [],
  getPartAuditLine: (ref) => simCtrl?.getPartAuditLine(ref) || null,
  getStats: () => ({
    ready: state.ready,
    tab: state.tab,
    theme: state.theme,
    boardComponents: catalogue ? catalogue.components.length : 0,
    kv260Parts: catalogue ? catalogue.kv260_parts.length : 0,
    coreParts: siteCore ? siteCore.part_count() : 0,
    selectedId: state.selectedId,
    drawCalls: renderer ? renderer.info.render.calls : 0,
    triangles: renderer ? renderer.info.render.triangles : 0,
  }),
};

boot().catch((err) => {
  console.error(err);
  const st = $("#load-stage");
  if (st) st.textContent = `Load error: ${err.message}`;
});
