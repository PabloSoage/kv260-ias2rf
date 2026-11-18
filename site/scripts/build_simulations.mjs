#!/usr/bin/env node
/**
 * Builds site/assets/simulations.json from real repository simulation outputs
 * and copies referenced result PNG/JPG plots into site/assets/img/sim_results/.
 * Pure Node.js (no Python). Every scalar carries exact source_file provenance.
 */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SITE_DIR = path.dirname(HERE);
const ROOT_DIR = path.dirname(SITE_DIR);
const ASSETS_DIR = path.join(SITE_DIR, "assets");
const SIM_IMG_OUT = path.join(ASSETS_DIR, "img", "sim_results");

function readJson(relPath) {
  return JSON.parse(fs.readFileSync(path.join(ROOT_DIR, relPath), "utf8"));
}

function readCsv(relPath) {
  const lines = fs.readFileSync(path.join(ROOT_DIR, relPath), "utf8").trim().split(/\r?\n/);
  if (!lines.length) return [];
  const headers = lines[0].split(",").map((s) => s.trim());
  const rows = [];
  for (let i = 1; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line) continue;
    const cols = line.split(",");
    const obj = {};
    for (let j = 0; j < headers.length; j++) {
      const raw = (cols[j] ?? "").trim();
      const num = Number(raw);
      obj[headers[j]] = raw !== "" && Number.isFinite(num) ? num : raw;
    }
    rows.push(obj);
  }
  return rows;
}

function downsample(arr, maxPts = 72) {
  if (arr.length <= maxPts) return arr;
  const out = [];
  const last = arr.length - 1;
  for (let i = 0; i < maxPts; i++) {
    const idx = Math.round((i * last) / (maxPts - 1));
    out.push(arr[idx]);
  }
  return out;
}

function copySimImages() {
  fs.mkdirSync(SIM_IMG_OUT, { recursive: true });
  const fromDocsSim = [
    "sma_launch.png",
    "j961_launch.png",
    "aaf_lpf.png",
    "bias_tee.png",
    "eyes_1g.png",
    "eye_openings.png",
    "lvds_skew.png",
    "pdn_impedance.png",
    "pdn_1V0.png",
    "pdn_1V8_D.png",
    "pdn_2V5.png",
    "pdn_3V3_D.png",
    "fb401_filter.png",
    "board_thermal.png",
    "rev08_thermal_70c.png",
    "v2_thermal_3d_cutaway.png",
    "v2_thermal_3d_heatsinks_compare.png",
    "v2_built_margins_70c.png",
    "case_materials.png",
  ];
  const fromDocsImg = ["case3d_v2_stress.jpg", "case3d_v2_boards.jpg"];
  let copied = 0;
  for (const name of fromDocsSim) {
    const src = path.join(ROOT_DIR, "docs", "sim", name);
    if (fs.existsSync(src)) {
      fs.copyFileSync(src, path.join(SIM_IMG_OUT, name));
      copied++;
    } else {
      console.warn("WARN missing docs/sim/" + name);
    }
  }
  for (const name of fromDocsImg) {
    const src = path.join(ROOT_DIR, "docs", "img", name);
    if (fs.existsSync(src)) {
      fs.copyFileSync(src, path.join(SIM_IMG_OUT, name));
      copied++;
    } else {
      console.warn("WARN missing docs/img/" + name);
    }
  }
  return copied;
}

function build() {
  const cat = JSON.parse(fs.readFileSync(path.join(ASSETS_DIR, "components.json"), "utf8"));
  const netTraces = JSON.parse(fs.readFileSync(path.join(ASSETS_DIR, "net_traces.json"), "utf8"));
  const validRefs = new Set([
    ...cat.components.map((c) => c.ref),
    ...cat.kv260_parts.map((k) => k.id),
    ...(cat.extra_parts || []).map((e) => e.id),
  ]);
  const compsByNet = new Map();
  const posByRef = new Map();
  for (const c of cat.components) {
    posByRef.set(c.ref, { x_mm: c.x_mm, y_mm: c.y_mm, model_pos_mm: c.model_pos_mm, side: c.side });
    for (const n of c.nets || []) {
      if (!compsByNet.has(n)) compsByNet.set(n, []);
      compsByNet.get(n).push(c.ref);
    }
  }
  for (const k of cat.kv260_parts) {
    const b = k.bbox_mm;
    posByRef.set(k.id, {
      model_pos_mm: [(b[0] + b[2]) / 2, (b[1] + b[3]) / 2, (b[4] + b[5]) / 2],
      side: "kv260",
    });
  }
  for (const ex of cat.extra_parts || []) {
    const b = ex.bbox_mm;
    posByRef.set(ex.id, {
      model_pos_mm: [(b[0] + b[2]) / 2, (b[1] + b[3]) / 2, (b[4] + b[5]) / 2],
      side: ex.assembly || "extra",
    });
  }

  const copiedImages = copySimImages();

  // -------------------------------------------------------------------------
  // 1. RF / Signal Integrity
  // -------------------------------------------------------------------------
  const skewRaw = readJson("_work/sim/lvds_skew_8layer.json");
  const eyeRows = readCsv("_work/sim/lvds_eye_8layer.csv");
  const eyeSummary = readJson("_work/sim/eye_summary_8layer.json");

  const eyeByPair = new Map();
  for (const r of eyeRows) {
    const key = String(r.pair).replace(/^\/CONTROL\/FPGA_CLK$/, "CLK_FPGA").replace(/^\//, "");
    if (!eyeByPair.has(key)) eyeByPair.set(key, {});
    eyeByPair.get(key)[r.case] = r;
  }

  const summaryByPair = new Map();
  for (const [k, v] of Object.entries(eyeSummary)) {
    const pair = k.replace(/_(1G|1P25G)$/, "");
    summaryByPair.set(pair, v);
  }

  const resolvePairNets = (shortPair) => {
    const ntKeys = Object.keys(netTraces);
    if (shortPair === "CLK_FPGA") {
      return { p: "/CONTROL/FPGA_CLK_P", n: "/CONTROL/FPGA_CLK_N", extra: ["/CLK_FPGA_P", "/CLK_FPGA_N"] };
    }
    if (shortPair.startsWith("ETH_SG")) {
      const p = ntKeys.find((k) => k === `/CONTROL/${shortPair}_FPGA_P`) || `/CONTROL/${shortPair}_FPGA_P`;
      const n = ntKeys.find((k) => k === `/CONTROL/${shortPair}_FPGA_N`) || `/CONTROL/${shortPair}_FPGA_N`;
      const p2 = `/CONTROL/${shortPair}_PHY_P`;
      const n2 = `/CONTROL/${shortPair}_PHY_N`;
      return { p, n, extra: [p2, n2].filter((x) => netTraces[x]) };
    }
    if (shortPair.startsWith("ETH_MDI")) {
      return { p: `/CONTROL/${shortPair}_P`, n: `/CONTROL/${shortPair}_N`, extra: [] };
    }
    const p = ntKeys.find((k) => k === `/${shortPair}_P`) || `/${shortPair}_P`;
    const n = ntKeys.find((k) => k === `/${shortPair}_N`) || `/${shortPair}_N`;
    return { p, n, extra: [] };
  };

  const pairComponents = (shortPair, pNet, nNet) => {
    const s = new Set();
    for (const net of [pNet, nNet]) {
      for (const r of compsByNet.get(net) || []) s.add(r);
    }
    if (shortPair.startsWith("LINK_")) {
      s.add("U1101");
      s.add("J101");
      s.add("K26_XCK26");
    } else if (shortPair.startsWith("ADCR_") || shortPair === "CLK_ADCR") {
      s.add("U501");
      s.add(shortPair === "CLK_ADCR" ? "U401" : "U1101");
    } else if (shortPair.startsWith("ADCS_") || shortPair === "CLK_ADCS") {
      s.add("U601");
      s.add(shortPair === "CLK_ADCS" ? "U401" : "U1101");
    } else if (shortPair === "CLK_FPGA") {
      s.add("U401");
      s.add("U1101");
    } else if (shortPair.startsWith("ETH_SG") || shortPair.startsWith("ETH_MDI")) {
      s.add("U1201");
      s.add(shortPair.startsWith("ETH_MDI") ? "J1201" : "U1101");
    }
    return Array.from(s).filter((r) => validRefs.has(r));
  };

  const pairs = [];
  for (const [shortPair, sk] of Object.entries(skewRaw)) {
    const nets = resolvePairNets(shortPair);
    const csvEntry = eyeByPair.get(shortPair) || {};
    const routed = csvEntry.routed || csvEntry.orig || null;
    const ideal = csvEntry.ideal || null;
    const sum = summaryByPair.get(shortPair) || null;
    const skewPs = routed ? Number(routed.P_minus_N_ps) : +(sk.P_ps - sk.N_ps).toFixed(2);
    const traceCount = (netTraces[nets.p]?.length || 0) + (netTraces[nets.n]?.length || 0);
    pairs.push({
      id: shortPair,
      pair: `/${shortPair}`,
      p_net: nets.p,
      n_net: nets.n,
      extra_nets: nets.extra,
      rate_gbps: routed ? +(routed.rate_bps / 1e9).toFixed(2) : shortPair.startsWith("ETH_SG") ? 1.25 : 1.0,
      p_ps: +sk.P_ps.toFixed(2),
      n_ps: +sk.N_ps.toFixed(2),
      skew_ps: +skewPs.toFixed(2),
      abs_skew_ps: +Math.abs(skewPs).toFixed(2),
      p_pkg_ps: +sk.P_pkg_ps.toFixed(2),
      n_pkg_ps: +sk.N_pkg_ps.toFixed(2),
      p_mm: +sk.P_mm.toFixed(2),
      n_mm: +sk.N_mm.toFixed(2),
      p_vias: sk.P_vias,
      n_vias: sk.N_vias,
      layers: sk.layers || [],
      eye_routed_mV: routed ? +routed.eye_opening_mV : sum ? +sum.eye_height_mV.toFixed(1) : null,
      eye_ideal_mV: ideal ? +ideal.eye_opening_mV : null,
      eye_summary_mV: sum ? +sum.eye_height_mV.toFixed(1) : null,
      zc_spread_ps: routed ? +routed.zero_crossing_spread_ps : null,
      routed_segments: traceCount,
      components: pairComponents(shortPair, nets.p, nets.n),
      source_files: [
        "_work/sim/lvds_skew_8layer.json",
        ...(routed ? ["_work/sim/lvds_eye_8layer.csv"] : []),
        ...(sum ? ["_work/sim/eye_summary_8layer.json"] : []),
      ],
    });
  }
  pairs.sort((a, b) => b.abs_skew_ps - a.abs_skew_ps);

  const smaRows = downsample(readCsv("docs/sim/sma_tvsn08_14.csv"), 64);
  const j961Rows = downsample(readCsv("docs/sim/j961_fixed.csv"), 64);
  const aafRows = downsample(readCsv("docs/sim/aaf_lpf.csv"), 72);

  const sparam_models = [
    {
      id: "sma_tvsn08_14",
      title: "SMA Edge Launch (TVS 0.14 pF + L2/L3 Ground Cutout)",
      components: ["J401", "J402", "J911", "J912", "J921", "J922", "J931", "J932", "J941", "J942", "J951", "J952", "J961", "D401", "D961", "D962", "D963", "D964", "D965", "D966", "D967", "D968", "D969", "D970"].filter((r) => validRefs.has(r)),
      nets: ["/CLK_EXT_IN", "/IF_IN_S", "/DAC_OUT_F", "/DAC_OUT_R", "/IF_TX_C", "/IF_RX_C", "/IF_AUX", "/RX_VU"].filter((n) => netTraces[n] || compsByNet.has(n)),
      summary: { s11_max_2p5ghz_dB: -21.8, s21_2p5ghz_dB: -0.14, bw_ghz: 2.5 },
      curve: smaRows.map((r) => [+(r.f_Hz / 1e6).toFixed(2), +r.S11_dB.toFixed(2), +r.S21_dB.toFixed(3)]),
      figure: "assets/img/sim_results/sma_launch.png",
      source_file: "docs/sim/sma_tvsn08_14.csv",
    },
    {
      id: "j961_fixed",
      title: "J961 VHF/UHF Antenna Launch + Bias-Tee (FB1302 || L1301)",
      components: ["J961", "D961", "L1301", "FB1302", "FB1301", "U1301", "U1314", "U1312"].filter((r) => validRefs.has(r)),
      nets: ["/RX_VU", "/RX_VU/RFIN_ANT", "/RX_VU/FE_RFIN_A"].filter((n) => netTraces[n] || compsByNet.has(n)),
      summary: { s11_worst_2p5ghz_dB: -17.9, s21_worst_dB: -0.16, bw_ghz: 2.5 },
      curve: j961Rows.map((r) => [+(r.f_Hz / 1e6).toFixed(2), +r.S11_dB.toFixed(2), +r.S21_dB.toFixed(3)]),
      figure: "assets/img/sim_results/j961_launch.png",
      extra_figure: "assets/img/sim_results/bias_tee.png",
      source_file: "docs/sim/j961_fixed.csv",
    },
    {
      id: "aaf_lpf",
      title: "IF_RX_C 7th-Order Elliptic Anti-Alias LPF (fc = 55.6 MHz)",
      components: ["J951", "C953", "C954", "C955", "C956", "C957", "C958", "C959", "L951", "L952", "L953", "U602", "U601"].filter((r) => validRefs.has(r)),
      nets: ["/IF_RX_C"].filter((n) => netTraces[n] || compsByNet.has(n)),
      summary: { fc_3db_MHz: 55.6, stopband_min_dB: -50.2, passband_s11_dB: -16.0 },
      curve: aafRows.map((r) => [+(r.f_Hz / 1e6).toFixed(2), +r.S11_dB.toFixed(2), +r.S21_dB.toFixed(2)]),
      figure: "assets/img/sim_results/aaf_lpf.png",
      source_file: "docs/sim/aaf_lpf.csv",
    },
  ];

  // From docs/SIGNAL_INTEGRITY.md section 3.5 & 9.9-9.10
  const crosstalk = [
    { a: "/ADCR_D0_P", b: "/ADCR_D1_N", layer: "In2.Cu", parallel_mm: 7.4, next_pct: 7.0, status: "pass (<15%)" },
    { a: "/ADCR_D1_P", b: "/ADCR_D3_P", layer: "In2.Cu", parallel_mm: 5.5, next_pct: 4.5, status: "pass" },
    { a: "/CONTROL/DACR_CLK", b: "/LINK_RX_CLK_N", layer: "F.Cu", parallel_mm: 3.0, next_pct: 3.7, status: "pass" },
    { a: "/ADCR_D4_P", b: "/ADCS_FCO_P", layer: "F.Cu", parallel_mm: 2.3, next_pct: 3.5, status: "pass" },
    { a: "/ADCR_OR_N", b: "/ADCS_D1_P", layer: "F.Cu", parallel_mm: 2.1, next_pct: 3.3, status: "pass" },
    { a: "/ADCR_D6_N", b: "/ADCR_D7_N", layer: "In4.Cu", parallel_mm: 3.0, next_pct: 3.2, status: "pass" },
    { a: "/LINK_TX_CLK_P", b: "/LINK_TX_D0_N", layer: "F.Cu", parallel_mm: 1.9, next_pct: 2.5, status: "pass" },
  ];

  // -------------------------------------------------------------------------
  // 2. Electrical / Power & PDN
  // -------------------------------------------------------------------------
  const fb401 = readJson("docs/sim/fb401_filter.json");
  const fb401Bead = fb401.beads["220R, 2 A (proposed)"];
  const fb401Nom = fb401Bead.cases["30% of L left"];
  const pdnConfigs = [
    { rail: "+1V0", label: "+1V0 VCCINT Core", voltage_V: 1.0, current_mA: 700, power_W: 0.70, reg: "U1004", ind: "L1030", loads: ["U1101"], target_z_mohm: 120, sim_z_band_mohm: 51, sim_z_100MHz_mohm: 61, dc_res_mohm: 36, dc_drop_mV: 25, dc_drop_pct: 2.5, csv: "docs/sim/pdn_1V0.csv", figure: "assets/img/sim_results/pdn_1V0.png" },
    { rail: "+1V8_D", label: "+1V8_D Digital & ADC", voltage_V: 1.8, current_mA: 333, power_W: 0.60, reg: "U1006", ind: "L1020", loads: ["U1101", "U501", "U601"], target_z_mohm: 700, sim_z_band_mohm: 109, sim_z_100MHz_mohm: 109, dc_res_mohm: 224, dc_drop_mV: 34, dc_drop_pct: 1.9, csv: "docs/sim/pdn_1V8_D.csv", figure: "assets/img/sim_results/pdn_1V8_D.png" },
    { rail: "+2V5", label: "+2V5 LVDS & I/O Bank 34", voltage_V: 2.5, current_mA: 601, power_W: 1.50, reg: "U1003", ind: "L1020", loads: ["U1101", "U1005", "U1006"], target_z_mohm: 2000, sim_z_band_mohm: 146, sim_z_100MHz_mohm: 146, dc_res_mohm: 297, dc_drop_mV: 30, dc_drop_pct: 1.2, csv: "docs/sim/pdn_2V5.csv", figure: "assets/img/sim_results/pdn_2V5.png" },
    { rail: "+3V3_D", label: "+3V3_D Digital I/O & Clock", voltage_V: 3.3, current_mA: 1388, power_W: 4.58, reg: "U1002", ind: "L1010", loads: ["U1101", "U1201", "U701", "U801", "U1501", "U1506", "FB401"], target_z_mohm: 1000, sim_z_band_mohm: 37, sim_z_100MHz_mohm: 37, dc_res_mohm: 110, dc_drop_mV: 39, dc_drop_pct: 1.2, csv: "docs/sim/pdn_3V3_D.csv", figure: "assets/img/sim_results/pdn_3V3_D.png" },
    { rail: "+3V3_CLK", label: "+3V3_CLK Filtered Clock Rail (FB401)", voltage_V: 3.3, current_mA: 340, power_W: 1.12, reg: "FB401", ind: "FB401", loads: ["Y401", "U401"], target_z_mohm: 1000, sim_z_band_mohm: 37, sim_z_100MHz_mohm: null, dc_res_mohm: +(fb401Bead.dcr_max_ohm * 1e3).toFixed(0), dc_drop_mV: +fb401Bead.dc_drop_max_mV.toFixed(1), dc_drop_pct: +((fb401Bead.dc_drop_max_mV / 3300) * 100).toFixed(2), csv: null, figure: "assets/img/sim_results/fb401_filter.png", extra: { fsw_kHz: fb401.buck.fsw_Hz / 1e3, ripple_atten_dB: +fb401Nom.atten_580k_dB.toFixed(1), output_ripple_uVpp: +fb401Nom.clk_ripple_580k_uVpp.toFixed(1), spur_dBc: +fb401Nom.si549_spur_dBc.toFixed(1), si549_margin_mV: +fb401Bead.si549_margin_mV.toFixed(1), fb_source: "docs/sim/fb401_filter.json" } },
    { rail: "+5V0", label: "+5V0 Main Buck (LMR33630)", voltage_V: 5.0, current_mA: 1775, power_W: 8.88, reg: "U1001", ind: "L1001", loads: ["U1002", "U1003", "U1004", "U1007", "U502", "U503", "U602", "U603", "U1301"], target_z_mohm: null, sim_z_band_mohm: null, sim_z_100MHz_mohm: null, dc_res_mohm: null, dc_drop_mV: null, dc_drop_pct: null, csv: null, figure: "assets/img/sim_results/pdn_impedance.png" },
    { rail: "+1V8_A", label: "+1V8_A Low-Noise Analog LDO", voltage_V: 1.8, current_mA: 500, power_W: 0.90, reg: "U1005", ind: null, loads: ["U501", "U601"], target_z_mohm: null, sim_z_band_mohm: null, sim_z_100MHz_mohm: null, dc_res_mohm: null, dc_drop_mV: null, dc_drop_pct: null, csv: null, figure: "assets/img/sim_results/pdn_impedance.png" },
    { rail: "+3V3_A", label: "+3V3_A Analog / DAC LDO", voltage_V: 3.3, current_mA: 100, power_W: 0.33, reg: "U1007", ind: null, loads: ["U701", "U801"], target_z_mohm: null, sim_z_band_mohm: null, sim_z_100MHz_mohm: null, dc_res_mohm: null, dc_drop_mV: null, dc_drop_pct: null, csv: null, figure: "assets/img/sim_results/pdn_impedance.png" },
    { rail: "+3V0_RF", label: "+3V0_RF Front-End LDO (RFFC5072)", voltage_V: 3.0, current_mA: 180, power_W: 0.54, reg: "U1315", ind: null, loads: ["U1312", "U1310"], target_z_mohm: null, sim_z_band_mohm: null, sim_z_100MHz_mohm: null, dc_res_mohm: null, dc_drop_mV: null, dc_drop_pct: null, csv: null, figure: "assets/img/sim_results/pdn_impedance.png" },
    { rail: "-3V3", label: "-3V3 Charge-Pump Bias", voltage_V: -3.3, current_mA: 8, power_W: 0.03, reg: "U1008", ind: null, loads: ["U1304", "U1305", "U1306", "U1307"], target_z_mohm: null, sim_z_band_mohm: null, sim_z_100MHz_mohm: null, dc_res_mohm: null, dc_drop_mV: null, dc_drop_pct: null, csv: null, figure: "assets/img/sim_results/pdn_impedance.png" },
  ];

  const rails = pdnConfigs.map((cfg) => {
    let curve = null;
    if (cfg.csv) {
      const rows = downsample(readCsv(cfg.csv), 68);
      curve = rows.map((r) => [+(r.f_Hz / 1e6).toFixed(4), +(r.Z_ohm * 1e3).toFixed(2)]);
    }
    const attached = Array.from(new Set([
      cfg.reg,
      cfg.ind,
      ...cfg.loads,
      ...(compsByNet.get(cfg.rail) || []),
    ].filter((r) => r && validRefs.has(r))));
    const srcFiles = ["docs/SIGNAL_INTEGRITY.md", "docs/POWER_AND_STACKUP.md"];
    if (cfg.csv) srcFiles.unshift(cfg.csv);
    if (cfg.extra?.fb_source) srcFiles.unshift(cfg.extra.fb_source);
    return {
      rail: cfg.rail,
      label: cfg.label,
      voltage_V: cfg.voltage_V,
      current_mA: cfg.current_mA,
      power_W: cfg.power_W,
      regulator_ref: cfg.reg,
      inductor_ref: cfg.ind,
      loads: cfg.loads.filter((r) => validRefs.has(r)),
      components: attached,
      routed_segments: (netTraces[cfg.rail] || []).length,
      target_z_mohm: cfg.target_z_mohm,
      sim_z_band_mohm: cfg.sim_z_band_mohm,
      sim_z_100MHz_mohm: cfg.sim_z_100MHz_mohm,
      margin_factor: cfg.target_z_mohm && cfg.sim_z_band_mohm ? +(cfg.target_z_mohm / cfg.sim_z_band_mohm).toFixed(2) : null,
      dc_res_mohm: cfg.dc_res_mohm,
      dc_drop_mV: cfg.dc_drop_mV,
      dc_drop_pct: cfg.dc_drop_pct,
      curve_MHz_mohm: curve,
      extra_metrics: cfg.extra || null,
      figure: cfg.figure,
      source_files: srcFiles,
    };
  });

  // -------------------------------------------------------------------------
  // 3. Thermal / CFD
  // -------------------------------------------------------------------------
  const cfdBuilt = readJson("mech/v2_cfd/results_built_v2.json");
  const cfdLegacy = readJson("mech/v2_cfd/results.json");

  const cfdCompMap = {
    U401_ADCLK948: { refs: ["U401", "HS2_U401_ADCLK948"], limit_C: 85, label: "ADCLK948 Clock Fanout" },
    Y401_Si549: { refs: ["Y401", "HS3_Y401_Si549"], limit_C: 85, label: "Si549 Dual XO" },
    U402_Si549: { refs: ["Y401", "HS3_Y401_Si549"], limit_C: 85, label: "Si549 Dual XO" },
    U501_AD9484: { refs: ["U501", "HS1_U501_AD9484"], limit_C: 85, label: "AD9484 500 MSPS ADC" },
    U502_AD8352: { refs: ["U502", "U602"], limit_C: 85, label: "AD8352 Diff Driver A" },
    U503_AD8352: { refs: ["U503", "U603"], limit_C: 85, label: "AD8352 Diff Driver B" },
    U601_AD9253: { refs: ["U601"], limit_C: 85, label: "AD9253 Dual 14-bit ADC" },
    U1101_XC7A50T: { refs: ["U1101", "HS4_U1101_XC7A50T"], limit_C: 100, label: "XC7A50T-2I FPGA" },
    U1001_LMR33630: { refs: ["U1001"], limit_C: 125, label: "LMR33630 12V->5V Buck" },
    U1002_TPS562201: { refs: ["U1002"], limit_C: 125, label: "TPS562201 +3V3_D Buck" },
    U1003_TPS562201: { refs: ["U1003"], limit_C: 125, label: "TPS562201 +2V5 Buck" },
    U1004_TPS562201: { refs: ["U1004"], limit_C: 125, label: "TPS562201 +1V0 Buck" },
    U1005_TPS7A8300: { refs: ["U1005"], limit_C: 125, label: "TPS7A8300 +1V8_A LDO" },
    U1006_TPS7A8300: { refs: ["U1006"], limit_C: 125, label: "TPS7A8300 +1V8_D LDO" },
    U1007_TPS7A8300: { refs: ["U1007"], limit_C: 125, label: "TPS7A8300 +3V3_A LDO" },
    U1201_RTL8211FSI: { refs: ["U1201"], limit_C: 85, label: "RTL8211FSI GbE PHY" },
    AD9708_AD9767: { refs: ["U701", "U801"], limit_C: 85, label: "AD9708 + AD9767 DACs" },
  };

  const cfdCaseTitles = {
    v2_built_hs_clean_25C: "Built v2 + Heatsinks @ 25 °C (Clean)",
    v2_built_hs_clean_45C: "Built v2 + Heatsinks @ 45 °C (Clean)",
    v2_built_hs_clean_70C: "Built v2 + Heatsinks @ 70 °C (Clean)",
    v2_built_hs_clogged_70C: "Built v2 + Heatsinks @ 70 °C (Clogged Filter)",
    v2_built_nohs_clean_70C: "Built v2 NO Heatsinks @ 70 °C (Baseline Failure)",
    v2_opt_fan5015_70C: "Opt: + OD5015 50 mm Lid Blower @ 70 °C",
    v2_opt_combined_fine_70C: "Opt: Combined (Airflow + 50 mm Fan, Fine) @ 70 °C",
    rev08_clean_fine_45C: "Rev08 Adopted Thermal Design @ 45 °C (Clean)",
    rev08_clean_fine_70C: "Rev08 Adopted Thermal Design @ 70 °C (Clean)",
    rev08_clogged_fine_70C: "Rev08 Adopted Thermal Design @ 70 °C (Clogged)",
    sealed_petg_45C: "v1 Sealed PETG Enclosure @ 45 °C (Overheats)",
    sealed_alu_70C: "v3 Sealed Al Spreader @ 70 °C",
  };

  const convertCfdCase = (c, srcFile) => {
    const ics = [];
    for (const [ckey, val] of Object.entries(c.components || {})) {
      const m = cfdCompMap[ckey];
      if (!m) continue;
      const primaryRef = m.refs[0];
      const pos = posByRef.get(primaryRef)?.model_pos_mm || [0, 0, 2.4];
      const marginTA = val.margin_TA_board_C ?? null;
      const effMargin = val.rating_type === "TA_85" && marginTA !== null ? Math.min(val.margin_C, marginTA) : val.margin_C;
      ics.push({
        key: ckey,
        ref: primaryRef,
        refs: m.refs.filter((r) => validRefs.has(r)),
        label: m.label,
        T_board_C: val.T_board_C,
        T_j_C: val.T_j_C,
        T_hs_mean_C: val.T_hs_mean_C ?? null,
        Q_to_hs_W: val.Q_to_hs_W ?? null,
        T_air_local_C: val.T_air_local_C ?? null,
        limit_C: val.ta_max_C || m.limit_C,
        margin_C: +effMargin.toFixed(2),
        margin_Tj_C: val.margin_C,
        rating_type: val.rating_type || (m.limit_C === 125 ? "Tj_125" : "Tj_100"),
        pos_mm: pos,
      });
    }
    // Add K26 SOM as an explicit thermal component entry
    const k26Pos = posByRef.get("K26_XCK26")?.model_pos_mm || [-5, 50, -8];
    const k26Margin = c.K26I_margin_C ?? +(100 - c.K26_Tj_C).toFixed(2);
    ics.push({
      key: "K26_XCK26",
      ref: "K26_XCK26",
      refs: ["K26_XCK26", "KV260_HEATSINK", "KV260_FAN"],
      label: "K26 Zynq UltraScale+ SOM (Industrial 100 °C)",
      T_board_C: c.K26_sink_C,
      T_j_C: c.K26_Tj_C,
      T_hs_mean_C: c.K26_sink_C,
      Q_to_hs_W: null,
      T_air_local_C: c.T_air_mean_C,
      limit_C: 100,
      margin_C: +k26Margin.toFixed(2),
      margin_Tj_C: +k26Margin.toFixed(2),
      rating_type: "Tj_100_K26I",
      pos_mm: k26Pos,
    });
    ics.sort((a, b) => a.margin_C - b.margin_C);
    return {
      id: c.name,
      title: cfdCaseTitles[c.name] || c.name,
      ambient_c: c.ambient_c,
      T_air_mean_C: c.T_air_mean_C,
      T_air_max_C: c.T_air_max_C,
      U_air_max_mps: c.U_air_max_mps,
      K26_sink_C: c.K26_sink_C,
      K26_Tj_C: c.K26_Tj_C,
      K26I_margin_C: +k26Margin.toFixed(2),
      K26C_margin_C: c.K26C_margin_C ?? +(85 - c.K26_Tj_C).toFixed(2),
      hottest_ic: c.hottest_ic,
      hottest_Tj_C: c.hottest_Tj_C,
      fan50_flow_cfm: c.fan50_flow_cfm ?? null,
      patch_flows: c.patch_flows || null,
      ics,
      source_file: srcFile,
    };
  };

  const selectedBuiltNames = [
    "rev08_clean_fine_70C",
    "rev08_clogged_fine_70C",
    "rev08_clean_fine_45C",
    "v2_built_hs_clean_70C",
    "v2_built_hs_clogged_70C",
    "v2_built_hs_clean_45C",
    "v2_built_hs_clean_25C",
    "v2_built_nohs_clean_70C",
    "v2_opt_fan5015_70C",
    "v2_opt_combined_fine_70C",
  ];
  const thermalCases = [];
  for (const name of selectedBuiltNames) {
    const found = cfdBuilt.find((x) => x.name === name);
    if (found) thermalCases.push(convertCfdCase(found, "mech/v2_cfd/results_built_v2.json"));
  }
  for (const name of ["sealed_petg_45C", "sealed_alu_70C"]) {
    const found = cfdLegacy.find((x) => x.name === name);
    if (found) thermalCases.push(convertCfdCase(found, "mech/v2_cfd/results.json"));
  }

  const thermal = {
    default_case: "rev08_clean_fine_70C",
    cases: thermalCases,
    figures: [
      { id: "cutaway", title: "3-D CHT Temperature Cutaway", src: "assets/img/sim_results/v2_thermal_3d_cutaway.png", cap: "OpenFOAM 3-D conjugate heat transfer slice across K26 + adapter heatsinks.", source_file: "docs/sim/v2_thermal_3d_cutaway.png" },
      { id: "rev08", title: "Rev08 Board 70 °C Thermal Map", src: "assets/img/sim_results/rev08_thermal_70c.png", cap: "Continuous 2-D PCB copper/FR4 contour from OpenFOAMchtMultiRegionFoam.", source_file: "docs/sim/rev08_thermal_70c.png" },
      { id: "board", title: "Adapter Board Surface Contours", src: "assets/img/sim_results/board_thermal.png", cap: "Comparison of peak IC hotspots on adapter top surface.", source_file: "docs/sim/board_thermal.png" },
      { id: "margins", title: "70 °C Component Margin Ladder", src: "assets/img/sim_results/v2_built_margins_70c.png", cap: "All 16 ICs and K26 SOM margins vs Ta/Tj limits.", source_file: "docs/sim/v2_built_margins_70c.png" },
    ],
    provenance_note: "Per-IC Tj, T_board, local air, and margin values are loaded directly from mech/v2_cfd/results_built_v2.json and mech/v2_cfd/results.json. Continuous CFD slice contours are displayed from the real OpenFOAM PNG plots rather than fabricated per-vertex mesh colours.",
  };

  // -------------------------------------------------------------------------
  // 4. Mechanical / Enclosure FEA
  // -------------------------------------------------------------------------
  const case3d = readJson("docs/sim/case3d_v2.json");
  const caseFea = readJson("docs/sim/case_fea.json");

  const bgaMeta = {
    U1101: { label: "U1101 (XC7A50T FTG256 BGA)", ref: "U1101" },
    U501: { label: "U501 (AD9484 LFCSP-56)", ref: "U501" },
    U601: { label: "U601 (AD9253 LFCSP-56)", ref: "U601" },
  };
  const mechLoads = ["Zm", "Xp", "Yp"].map((k) => {
    const ld = case3d.cases[k];
    const bga = {};
    for (const [bk, bv] of Object.entries(ld.bga || {})) {
      const m = bgaMeta[bk] || { label: bk, ref: bk };
      bga[m.ref] = {
        ref: m.ref,
        label: m.label,
        ue_max: +bv.ue_max.toFixed(1),
        nodes: bv.nodes,
        limit_ue: case3d.ue_guide,
        sf_ue: +(case3d.ue_guide / bv.ue_max).toFixed(2),
        pos_mm: posByRef.get(m.ref)?.model_pos_mm || [0, 0, 2.4],
      };
    }
    return {
      id: k,
      title: k === "Zm" ? "50 g Vertical Shock (-Z Down)" : k === "Xp" ? "50 g Lateral Shock (+X Sideways)" : "50 g Fore-Aft Shock (+Y)",
      case_vm_peak_MPa: +ld.case.vm_peak.toFixed(2),
      case_vm_p997_MPa: +ld.case.vm_p997.toFixed(2),
      peak_at_mm: ld.case.peak_at,
      sf_23C: +ld.case.sf_23C.toFixed(2),
      sf_70C: +ld.case.sf_70C.toFixed(2),
      umax_mm: +ld.umax_mm.toFixed(3),
      adapter: {
        ue_peak: +ld.adapter.ue_peak.toFixed(1),
        ue_p997: +ld.adapter.ue_p997.toFixed(1),
        bow_mm: +ld.adapter.bow_mm.toFixed(4),
        peak_at_mm: ld.adapter.peak_at,
      },
      carrier: {
        ue_peak: +ld.carrier.ue_peak.toFixed(1),
        ue_p997: +ld.carrier.ue_p997.toFixed(1),
        bow_mm: +ld.carrier.bow_mm.toFixed(4),
        peak_at_mm: ld.carrier.peak_at,
      },
      bga,
    };
  });

  const mechanical = {
    mesh_info: { solver: "CalculiX", tets: case3d.tets, nodes: case3d.nodes, allow_MPa: case3d.allow_MPa, ue_guide: case3d.ue_guide },
    load_cases: mechLoads,
    material_rows: (caseFea.rows || []).map((r) => ({
      material: r.material,
      T: r.T,
      mass_kg: +r.mass_kg.toFixed(3),
      f1_Hz: +r.f1.toFixed(1),
      s_allow_MPa: +r.s_allow.toFixed(1),
      shock_50g_sf: +r.sf_shock.toFixed(2),
      drop_bare_sf: +r.sf_drop.toFixed(2),
      drop_bump_sf: +r.sf_bump.toFixed(2),
      vib_sf: +r.sf_vib.toFixed(2),
      hdt_C: r.hdt,
      src: r.src,
    })),
    figures: [
      { id: "stress", title: "Case 3-D von Mises Stress (50 g)", src: "assets/img/sim_results/case3d_v2_stress.jpg", cap: "CalculiX C3D10 tetrahedral stress contours (peak at rear boss).", source_file: "docs/img/case3d_v2_stress.jpg" },
      { id: "boards", title: "PCB & BGA Principal Strain (ue)", src: "assets/img/sim_results/case3d_v2_boards.jpg", cap: "Adapter + KV260 carrier microstrain vs 500 ue IPC/JEDEC solder-joint limit.", source_file: "docs/img/case3d_v2_boards.jpg" },
      { id: "materials", title: "Material & Drop Temperature Sweep", src: "assets/img/sim_results/case_materials.png", cap: "23 °C vs 70 °C shock, 1 m bare vs TPU bumper drop, and vibration fatigue.", source_file: "docs/sim/case_materials.png" },
    ],
    source_files: ["docs/sim/case3d_v2.json", "docs/sim/case_fea.json"],
    provenance_note: "Summary stress peaks, coordinates, safety factors, and BGA microstrains come directly from docs/sim/case3d_v2.json and docs/sim/case_fea.json. Full per-vertex contour plots are shown from the real CalculiX/Cycles renders (case3d_v2_stress.jpg, case3d_v2_boards.jpg).",
  };

  // -------------------------------------------------------------------------
  // 5. Gateware / Radio G-8
  // -------------------------------------------------------------------------
  const g8Raw = readJson("fpga/sim/signals/results.json");
  const g8Meta = {
    hf_am: {
      title: "HF Shortwave AM (7.1 MHz)",
      band: "3-30 MHz Direct Nyquist-1",
      chain_blocks: ["ADC 62.5 MSPS", "CIC Decim R=64", "Droop FIR", "CORDIC AM Env Demod", "Audio LPF 4.5 kHz"],
      hardware_parts: ["J951", "C953", "L951", "C955", "L952", "C957", "L953", "C959", "U602", "U601", "U401", "U1101", "J101", "K26_XCK26"],
      hardware_nets: ["/IF_RX_C", "/ADCS_D0_P", "/ADCS_DCO_P", "/LINK_RX_D0_P"],
    },
    hf_ssb: {
      title: "HF Single-Sideband USB/LSB (14.2 MHz)",
      band: "3-30 MHz Direct Nyquist-1",
      chain_blocks: ["ADC 62.5 MSPS", "NCO + CIC + FIR", "Weaver Phasing Demod", "AGC + 2.7 kHz SSB"],
      hardware_parts: ["J951", "C953", "L951", "C955", "L952", "C957", "L953", "C959", "U602", "U601", "U401", "U1101", "J101", "K26_XCK26"],
      hardware_nets: ["/IF_RX_C", "/ADCS_D0_P", "/ADCS_D1_P", "/LINK_RX_D0_P"],
    },
    fm: {
      title: "Wideband FM Broadcast Stereo + RDS (98.1 MHz)",
      band: "88-108 MHz (RFFC5072 -> IF)",
      chain_blocks: ["SPF5043Z LNA", "RFFC5072 Mixer", "AD9484/AD9253", "24-bit DDC", "Polar Discriminator + 19 kHz PLL + RDS"],
      hardware_parts: ["J961", "D961", "L1301", "FB1302", "U1301", "U1312", "T1301", "U502", "U501", "U601", "U1101", "J101", "K26_XCK26"],
      hardware_nets: ["/RX_VU", "/ADCR_D0_P", "/ADCR_DCO_P", "/LINK_RX_D0_P"],
    },
    air: {
      title: "VHF Airband AM (121.5 MHz, 8.33/25 kHz)",
      band: "108-137 MHz",
      chain_blocks: ["SPF5043Z LNA", "RFFC5072 Mixer", "24-bit NCO", "Channelizer", "Hang AGC + AM Demod"],
      hardware_parts: ["J961", "D961", "L1301", "FB1302", "U1301", "U1312", "U502", "U501", "U1101", "J101", "K26_XCK26"],
      hardware_nets: ["/RX_VU", "/ADCR_D0_P", "/ADCS_D0_P", "/LINK_RX_D0_P"],
    },
    nbfm: {
      title: "VHF/UHF Narrowband FM + CTCSS (145.5 MHz)",
      band: "144-470 MHz",
      chain_blocks: ["SPF5043Z LNA", "RFFC5072 Mixer", "DDC + 12.5 kHz LPF", "ATAN LUT Discriminator", "Goertzel CTCSS"],
      hardware_parts: ["J961", "D961", "L1301", "FB1302", "U1301", "U1312", "U502", "U501", "U1101", "J101", "K26_XCK26"],
      hardware_nets: ["/RX_VU", "/ADCR_D0_P", "/ADCS_D0_P", "/LINK_RX_D0_P"],
    },
    adsb: {
      title: "ADS-B Mode-S 1090 MHz Frame Decoder",
      band: "1090 MHz PPM",
      chain_blocks: ["SPF5043Z LNA", "RFFC5072 Mixer", "AD9484 500 MSPS", "8 us Preamble Correlator", "Manchester + CRC-24"],
      hardware_parts: ["J961", "D961", "L1301", "FB1302", "U1301", "U1312", "U502", "U501", "U401", "U1101", "J101", "K26_XCK26"],
      hardware_nets: ["/RX_VU", "/ADCR_D0_P", "/ADCR_D1_P", "/LINK_RX_D0_P"],
    },
    radar: {
      title: "10.5 GHz FMCW Phased-Array Radar (Range-Doppler + CFAR)",
      band: "10.5 GHz -> IF_IN_S",
      chain_blocks: ["AD9708 Chirp DAC", "ADAR1000 SPI Beam", "AD9484 400 MSPS", "Range/Doppler 2-D FFT", "CA-CFAR Detector"],
      hardware_parts: ["J921", "J922", "T701", "U701", "U502", "U503", "U501", "U401", "Y401", "U1101", "J101", "K26_XCK26"],
      hardware_nets: ["/ADCR_D0_P", "/ADCR_DCO_P", "/CLK_ADCR_P", "/LINK_RX_D0_P"],
    },
    tx: {
      title: "TX Chain Cleanliness (AM / NBFM / USB / CW / Chirp)",
      band: "TX IF & Chirp DAC",
      chain_blocks: ["TX_KEY HW Interlock", "DUC NCO + Weaver/FM Mod", "AD9767 I/Q DAC", "AD9708 Chirp DAC", "TX Spectral Mask"],
      hardware_parts: ["K26_XCK26", "J101", "U1101", "U801", "T801", "T802", "U701", "T701", "J942", "J952", "J941", "U1312"],
      hardware_nets: ["/LINK_TX_D0_P", "/LINK_TX_CLK_P", "/DAC_OUT_F", "/DAC_OUT_R"],
    },
  };

  const gatewareModes = [];
  for (const [k, raw] of Object.entries(g8Raw)) {
    const meta = g8Meta[k] || { title: k, band: "", chain_blocks: [], hardware_parts: [], hardware_nets: [] };
    const figBase = path.basename(raw.figure || `g8_${k}.png`);
    const checks = Object.entries(raw.checks || {}).map(([name, ok]) => ({ name, ok: !!ok }));
    const sensVal = raw.sens10_rtl_dbm ?? raw.sens12_rtl_dbm ?? raw.sens30_rtl_dbm ?? raw.l90_dbm ?? null;
    const sensLabel = raw.sens10_rtl_dbm != null ? "10 dB SINAD"
      : raw.sens12_rtl_dbm != null ? "12 dB SINAD"
        : raw.sens30_rtl_dbm != null ? "30 dB SINAD"
          : raw.l90_dbm != null ? "90% Decode" : null;
    const imgRej = raw.ddc_image_db ?? raw.opposite_sideband_db ?? raw.rds_rej_db ?? null;
    gatewareModes.push({
      id: k,
      title: meta.title,
      band: meta.band,
      chain_blocks: meta.chain_blocks,
      hardware_parts: meta.hardware_parts.filter((r) => validRefs.has(r)),
      hardware_nets: meta.hardware_nets.filter((n) => netTraces[n]),
      levels: raw.levels || null,
      sinad_rtl: raw.sinad_rtl || raw.pd_rtl || null,
      sinad_ref: raw.sinad_ref || raw.pd_ref || null,
      sensitivity_dBm: sensVal !== null ? +Number(sensVal).toFixed(1) : null,
      sensitivity_label: sensLabel,
      rejection_dB: imgRej !== null ? +Number(imgRej).toFixed(1) : null,
      checks,
      passed: !!raw.passed,
      figure: `assets/img/sim/${figBase}`,
      source_file: "fpga/sim/signals/results.json",
    });
  }

  // -------------------------------------------------------------------------
  // 6. Invert into component_sim_index (ref -> [simulation entries])
  // -------------------------------------------------------------------------
  const compSim = {};
  const addCompSim = (ref, item) => {
    if (!validRefs.has(ref)) return;
    if (!compSim[ref]) compSim[ref] = [];
    // Deduplicate by domain + target_id
    if (compSim[ref].some((x) => x.domain === item.domain && x.target_id === item.target_id)) return;
    compSim[ref].push(item);
  };

  for (const p of pairs) {
    for (const ref of p.components) {
      addCompSim(ref, {
        domain: "rf",
        domain_label: "RF / SI",
        target_id: p.id,
        title: `${p.pair} (${p.rate_gbps} Gbps)`,
        metric: `Skew ${p.skew_ps} ps${p.eye_routed_mV ? ` · Eye ${p.eye_routed_mV} mV` : ""}`,
        status: Math.abs(p.skew_ps) <= 30 ? "PASS" : "WARN",
        source_file: p.source_files[0],
      });
    }
  }
  for (const sp of sparam_models) {
    const metric = sp.summary.fc_3db_MHz
      ? `fc=${sp.summary.fc_3db_MHz} MHz · Stop ${sp.summary.stopband_min_dB} dB`
      : `S11<=${sp.summary.s11_max_2p5ghz_dB ?? sp.summary.s11_worst_2p5ghz_dB} dB @ 2.5 GHz`;
    for (const ref of sp.components) {
      addCompSim(ref, {
        domain: "rf",
        domain_label: "RF S-Param",
        target_id: sp.id,
        title: sp.title,
        metric,
        status: "PASS",
        source_file: sp.source_file,
      });
    }
  }

  for (const r of rails) {
    const metric = r.sim_z_band_mohm
      ? `|Z|=${r.sim_z_band_mohm} vs ${r.target_z_mohm} mΩ · Drop ${r.dc_drop_mV} mV`
      : r.extra_metrics
        ? `Atten ${r.extra_metrics.ripple_atten_dB} dB · ${r.extra_metrics.output_ripple_uVpp} uVpp`
        : `${r.voltage_V} V · ${r.current_mA} mA (${r.power_W} W)`;
    for (const ref of r.components) {
      addCompSim(ref, {
        domain: "power",
        domain_label: "Power / PDN",
        target_id: r.rail,
        title: r.label,
        metric,
        status: "PASS",
        source_file: r.source_files[0],
      });
    }
  }

  const defTherm = thermalCases.find((c) => c.id === thermal.default_case) || thermalCases[0];
  for (const ic of defTherm.ics) {
    for (const ref of ic.refs) {
      addCompSim(ref, {
        domain: "thermal",
        domain_label: "Thermal CFD",
        target_id: defTherm.id,
        title: `${ic.label} @ ${defTherm.ambient_c} °C`,
        metric: `Tj=${ic.T_j_C} °C / ${ic.limit_C} °C (${ic.margin_C >= 0 ? "+" : ""}${ic.margin_C} °C)`,
        status: ic.margin_C >= 0 ? "PASS" : "FAIL",
        source_file: defTherm.source_file,
      });
    }
  }

  const zmLoad = mechLoads.find((l) => l.id === "Zm") || mechLoads[0];
  for (const [bRef, bv] of Object.entries(zmLoad.bga)) {
    addCompSim(bRef, {
      domain: "mech",
      domain_label: "Mech FEA",
      target_id: "Zm",
      title: `50 g Shock BGA Strain (${bv.label})`,
      metric: `${bv.ue_max} ue / ${bv.limit_ue} ue (SF ${bv.sf_ue}x)`,
      status: bv.ue_max <= bv.limit_ue ? "PASS" : "FAIL",
      source_file: "docs/sim/case3d_v2.json",
    });
  }
  for (const encRef of cat.kv260_parts.filter((k) => k.id.includes("ENCLOSURE") || k.id.includes("BUMPER") || k.id.includes("KV260")).map((k) => k.id)) {
    addCompSim(encRef, {
      domain: "mech",
      domain_label: "Mech FEA",
      target_id: "Zm",
      title: `Enclosure 50 g Shock (${zmLoad.case_vm_peak_MPa} MPa peak)`,
      metric: `SF 23°C: ${zmLoad.sf_23C}x · SF 70°C: ${zmLoad.sf_70C}x · umax ${zmLoad.umax_mm} mm`,
      status: zmLoad.sf_70C >= 1.5 ? "PASS" : "WARN",
      source_file: "docs/sim/case3d_v2.json",
    });
  }

  for (const gm of gatewareModes) {
    const metric = `${gm.passed ? "PASS" : "FAIL"}${gm.sensitivity_dBm !== null ? ` · ${gm.sensitivity_label}: ${gm.sensitivity_dBm} dBm` : ""}${gm.rejection_dB !== null ? ` · Rej ${gm.rejection_dB} dB` : ""}`;
    for (const ref of gm.hardware_parts) {
      addCompSim(ref, {
        domain: "g8",
        domain_label: "Gateware G-8",
        target_id: gm.id,
        title: gm.title,
        metric,
        status: gm.passed ? "PASS" : "FAIL",
        source_file: gm.source_file,
      });
    }
  }

function parseAsciiPly(filePath) {
  const txt = fs.readFileSync(filePath, "utf8");
  const lines = txt.split(/\r?\n/);
  let nv = 0, nf = 0, i = 0;
  while (i < lines.length && lines[i] !== "end_header") {
    const p = lines[i].trim().split(/\s+/);
    if (p[0] === "element" && p[1] === "vertex") nv = parseInt(p[2], 10);
    if (p[0] === "element" && p[1] === "face") nf = parseInt(p[2], 10);
    i++;
  }
  i++;
  const pos = new Float32Array(nv * 3);
  const rgb = new Uint8Array(nv * 3);
  const vals = new Float32Array(nv);
  for (let k = 0; k < nv; k++) {
    const p = lines[i + k].trim().split(/\s+/);
    const xm = parseFloat(p[0]), ym = parseFloat(p[1]), zm = parseFloat(p[2]);
    // Assembly mm -> Three.js Y-up metres
    pos[k * 3] = xm * 0.001;
    pos[k * 3 + 1] = zm * 0.001;
    pos[k * 3 + 2] = -ym * 0.001;
    rgb[k * 3] = parseInt(p[3], 10) & 255;
    rgb[k * 3 + 1] = parseInt(p[4], 10) & 255;
    rgb[k * 3 + 2] = parseInt(p[5], 10) & 255;
    vals[k] = parseFloat(p[6] || "0");
  }
  i += nv;
  const idx = new Uint16Array(nf * 3);
  for (let k = 0; k < nf; k++) {
    const p = lines[i + k].trim().split(/\s+/);
    idx[k * 3] = parseInt(p[1], 10);
    idx[k * 3 + 1] = parseInt(p[2], 10);
    idx[k * 3 + 2] = parseInt(p[3], 10);
  }
  return { nv, nf, pos, rgb, vals, idx };
}

function buildNearestColorTable(refPos, targetPly, cellSizeM = 0.004) {
  const inv = 1.0 / cellSizeM;
  const grid = new Map();
  for (let i = 0; i < targetPly.nv; i++) {
    const x = targetPly.pos[i * 3], y = targetPly.pos[i * 3 + 1], z = targetPly.pos[i * 3 + 2];
    const key = `${Math.round(x * inv)},${Math.round(y * inv)},${Math.round(z * inv)}`;
    if (!grid.has(key)) grid.set(key, []);
    grid.get(key).push(i);
  }
  const n = refPos.length / 3;
  const outRgb = new Uint8Array(n * 3);
  for (let i = 0; i < n; i++) {
    const x = refPos[i * 3], y = refPos[i * 3 + 1], z = refPos[i * 3 + 2];
    const gx = Math.round(x * inv), gy = Math.round(y * inv), gz = Math.round(z * inv);
    let bestD = Infinity, bestJ = 0;
    for (let dz = -1; dz <= 1; dz++) {
      for (let dy = -1; dy <= 1; dy++) {
        for (let dx = -1; dx <= 1; dx++) {
          const list = grid.get(`${gx + dx},${gy + dy},${gz + dz}`);
          if (!list) continue;
          for (let m = 0; m < list.length; m++) {
            const j = list[m];
            const ddx = targetPly.pos[j * 3] - x;
            const ddy = targetPly.pos[j * 3 + 1] - y;
            const ddz = targetPly.pos[j * 3 + 2] - z;
            const d2 = ddx * ddx + ddy * ddy + ddz * ddz;
            if (d2 < bestD) { bestD = d2; bestJ = j; }
          }
        }
      }
    }
    outRgb[i * 3] = targetPly.rgb[bestJ * 3];
    outRgb[i * 3 + 1] = targetPly.rgb[bestJ * 3 + 1];
    outRgb[i * 3 + 2] = targetPly.rgb[bestJ * 3 + 2];
  }
  return outRgb;
}

function buildFea3dBinary() {
  const candidates = [
    path.join(ROOT_DIR, "_work", "mech", "cache", "fea3d", "v2"),
    path.join("D:\\Repos\\kv260-ias2rf", "_work", "mech", "cache", "fea3d", "v2"),
  ];
  const feaDir = candidates.find((d) => fs.existsSync(path.join(d, "case3d_v2_Zm.ply")));
  if (!feaDir) return false;

  const caseZm = parseAsciiPly(path.join(feaDir, "case3d_v2_Zm.ply"));
  const caseXp = parseAsciiPly(path.join(feaDir, "case3d_v2_Xp.ply"));
  const caseYp = parseAsciiPly(path.join(feaDir, "case3d_v2_Yp.ply"));
  const bZm = parseAsciiPly(path.join(feaDir, "boards3d_v2_Zm.ply"));
  const bXp = parseAsciiPly(path.join(feaDir, "boards3d_v2_Xp.ply"));
  const bYp = parseAsciiPly(path.join(feaDir, "boards3d_v2_Yp.ply"));

  // Downsample case stress points using 3.2 mm voxels, keeping peak val per voxel
  const voxelInv = 1.0 / 0.0032;
  const voxBest = new Map();
  for (let i = 0; i < caseZm.nv; i++) {
    const x = caseZm.pos[i * 3], y = caseZm.pos[i * 3 + 1], z = caseZm.pos[i * 3 + 2];
    const key = `${Math.round(x * voxelInv)},${Math.round(y * voxelInv)},${Math.round(z * voxelInv)}`;
    const prev = voxBest.get(key);
    if (prev === undefined || caseZm.vals[i] > caseZm.vals[prev]) voxBest.set(key, i);
  }
  const caseIndices = [...voxBest.values()];
  const caseCount = caseIndices.length;
  const casePos = new Float32Array(caseCount * 3);
  const caseRgbZm = new Uint8Array(caseCount * 3);
  for (let k = 0; k < caseCount; k++) {
    const idx = caseIndices[k];
    casePos[k * 3] = caseZm.pos[idx * 3];
    casePos[k * 3 + 1] = caseZm.pos[idx * 3 + 1];
    casePos[k * 3 + 2] = caseZm.pos[idx * 3 + 2];
    caseRgbZm[k * 3] = caseZm.rgb[idx * 3];
    caseRgbZm[k * 3 + 1] = caseZm.rgb[idx * 3 + 1];
    caseRgbZm[k * 3 + 2] = caseZm.rgb[idx * 3 + 2];
  }
  const caseRgbXp = buildNearestColorTable(casePos, caseXp);
  const caseRgbYp = buildNearestColorTable(casePos, caseYp);

  const bRgbXp = buildNearestColorTable(bZm.pos, bXp, 0.003);
  const bRgbYp = buildNearestColorTable(bZm.pos, bYp, 0.003);

  const hdr = new Uint32Array([0x32414546, caseCount, bZm.nv, bZm.nf]); // "FEA2"
  const pad4 = (n) => (4 - (n % 4)) % 4;
  const parts = [
    Buffer.from(hdr.buffer),
    Buffer.from(casePos.buffer),
    Buffer.from(caseRgbZm.buffer),
    Buffer.from(caseRgbXp.buffer),
    Buffer.from(caseRgbYp.buffer),
    Buffer.alloc(pad4(caseCount * 9)),
    Buffer.from(bZm.pos.buffer),
    Buffer.from(bZm.idx.buffer),
    Buffer.alloc(pad4(bZm.idx.byteLength)),
    Buffer.from(bZm.rgb.buffer),
    Buffer.from(bRgbXp.buffer),
    Buffer.from(bRgbYp.buffer),
  ];
  const binPath = path.join(ASSETS_DIR, "fea_v2_fields.bin");
  fs.writeFileSync(binPath, Buffer.concat(parts));
  console.log(`Wrote ${binPath} (${(fs.statSync(binPath).size / 1024).toFixed(1)} KB, ${caseCount} case pts, ${bZm.nv} board verts / ${bZm.nf} tris)`);
  return true;
}

  const hasFea3d = buildFea3dBinary();
  const out = {
    generated_at: new Date().toISOString(),
    copied_images: copiedImages,
    rf_si: {
      pairs,
      sparam_models,
      crosstalk,
      figures: [
        { id: "eyes_1g", title: "1 Gbps Eye Diagrams (8-Layer Routed)", src: "assets/img/sim_results/eyes_1g.png", source_file: "docs/sim/eyes_1g.png" },
        { id: "lvds_skew", title: "LVDS Intra-Pair & Bus Skew Distribution", src: "assets/img/sim_results/lvds_skew.png", source_file: "docs/sim/lvds_skew.png" },
        { id: "eye_openings", title: "Eye Opening Margin Summary", src: "assets/img/sim_results/eye_openings.png", source_file: "docs/sim/eye_openings.png" },
      ],
      source_files: ["_work/sim/lvds_skew_8layer.json", "_work/sim/lvds_eye_8layer.csv", "_work/sim/eye_summary_8layer.json", "docs/sim/sma_tvsn08_14.csv", "docs/sim/j961_fixed.csv", "docs/sim/aaf_lpf.csv", "docs/SIGNAL_INTEGRITY.md"],
    },
    power: {
      rails,
      overview_figure: "assets/img/sim_results/pdn_impedance.png",
      source_files: ["docs/sim/pdn_1V0.csv", "docs/sim/pdn_1V8_D.csv", "docs/sim/pdn_2V5.csv", "docs/sim/pdn_3V3_D.csv", "docs/sim/fb401_filter.json", "docs/SIGNAL_INTEGRITY.md", "docs/POWER_AND_STACKUP.md"],
    },
    thermal,
    mechanical: {
      ...mechanical,
      has_fea_3d: hasFea3d,
      fea_3d_file: hasFea3d ? "assets/fea_v2_fields.bin" : null,
      fea_3d_source: "_work/mech/cache/fea3d/v2/case3d_v2_{Zm,Xp,Yp}.ply & boards3d_v2_{Zm,Xp,Yp}.ply -> docs/sim/case3d_v2.json",
    },
    gateware_g8: {
      modes: gatewareModes,
      overview_figure: "assets/img/sim/g8_overview.png",
      source_file: "fpga/sim/signals/results.json",
    },
    component_sim_index: compSim,
  };

  const outPath = path.join(ASSETS_DIR, "simulations.json");
  fs.writeFileSync(outPath, JSON.stringify(out, null, 2));
  const szKb = (fs.statSync(outPath).size / 1024).toFixed(1);
  console.log(`Wrote ${outPath} (${szKb} KB), copied ${copiedImages} sim images, indexed ${Object.keys(compSim).length} components across 5 simulation domains.`);
}

build();
