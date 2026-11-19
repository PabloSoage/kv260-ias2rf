#!/usr/bin/env node
/**
 * Build site/assets/components.json by parsing CSI2-KRIA-KV260_Rev01.kicad_pcb as text
 * (never pcbnew) and joining with BOM CSVs, _work/sheets/*_spec.py (read as text),
 * _work/manual/board_manual.py (read as text), and the measured KV260 part catalogue.
 */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SITE_DIR = path.dirname(HERE);
const ROOT_DIR = path.dirname(SITE_DIR);
const PCB_PATH = path.join(ROOT_DIR, "CSI2-KRIA-KV260_Rev01.kicad_pcb");
const OUT_PATH = path.join(SITE_DIR, "assets", "components.json");

function readText(p) {
  return fs.existsSync(p) ? fs.readFileSync(p, "utf8") : "";
}

function topLevelBlocks(text, head) {
  const key = "\n\t(" + head.trimEnd();
  const out = [];
  let idx = text.indexOf(key);
  while (idx >= 0) {
    const nextCh = text[idx + key.length] || "";
    if (!/\s/.test(nextCh)) {
      idx = text.indexOf(key, idx + key.length);
      continue;
    }
    const start = idx + 2;
    let depth = 0;
    let j = start;
    let inStr = false;
    while (j < text.length) {
      const ch = text[j];
      if (inStr) {
        if (ch === "\\") j += 2;
        else {
          if (ch === '"') inStr = false;
          j++;
        }
      } else if (ch === '"') {
        inStr = true;
        j++;
      } else if (ch === "(") {
        depth++;
        j++;
      } else if (ch === ")") {
        depth--;
        j++;
        if (depth === 0) break;
      } else {
        j++;
      }
    }
    out.push(text.slice(start, j));
    idx = text.indexOf(key, j);
  }
  return out;
}

function unescapeKiCad(s) {
  return s.replace(/\\"/g, '"').replace(/\\\\/g, "\\");
}

function extractProp(block, name) {
  const re = new RegExp(`\\(property "${name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}" "((?:[^"\\\\]|\\\\.)*)"`);
  const m = block.match(re);
  return m ? unescapeKiCad(m[1]) : "";
}

function localPts(block, allowedLayers) {
  const pts = [];
  const re = /\((fp_line|fp_rect|fp_poly|fp_circle|fp_arc)\b([\s\S]*?)\(layer "([^"]+)"\)/g;
  let m;
  while ((m = re.exec(block)) !== null) {
    if (!allowedLayers.has(m[3])) continue;
    const body = m[2];
    const coords = [];
    const cr = /\((?:start|end|mid|center|xy) ([-\d.]+) ([-\d.]+)\)/g;
    let c;
    while ((c = cr.exec(body)) !== null) {
      coords.push([parseFloat(c[1]), parseFloat(c[2])]);
    }
    if (m[1] === "fp_circle" && coords.length === 2) {
      const [[cx, cy], [ex, ey]] = coords;
      const r = Math.hypot(ex - cx, ey - cy);
      pts.push([cx - r, cy - r], [cx + r, cy + r]);
    } else {
      pts.push(...coords);
    }
  }
  return pts;
}

function padPts(block) {
  const pts = [];
  const re = /\(pad "[^"]*" \w+ \w+\s*\(at ([-\d.]+) ([-\d.]+)(?: [-\d.]+)?\)\s*\(size ([-\d.]+) ([-\d.]+)\)/g;
  let m;
  while ((m = re.exec(block)) !== null) {
    const x = parseFloat(m[1]);
    const y = parseFloat(m[2]);
    const w = parseFloat(m[3]);
    const h = parseFloat(m[4]);
    pts.push([x - w / 2, y - h / 2], [x + w / 2, y + h / 2]);
  }
  return pts;
}

function parseEdgeCuts(text) {
  let minx = Infinity, miny = Infinity, maxx = -Infinity, maxy = -Infinity;
  const segs = [];
  for (const kind of ["gr_line", "gr_arc", "gr_rect", "gr_poly"]) {
    for (const b of topLevelBlocks(text, kind + " ")) {
      if (!b.includes('(layer "Edge.Cuts")')) continue;
      const coords = [];
      const re = /\((?:start|mid|end|xy) ([-\d.]+) ([-\d.]+)\)/g;
      let m;
      while ((m = re.exec(b)) !== null) {
        const px = parseFloat(m[1]);
        const py = parseFloat(m[2]);
        minx = Math.min(minx, px);
        miny = Math.min(miny, py);
        maxx = Math.max(maxx, px);
        maxy = Math.max(maxy, py);
        coords.push([px, py]);
      }
      if (coords.length >= 2) segs.push(coords);
    }
  }
  return {
    xmin: +minx.toFixed(3),
    ymin: +miny.toFixed(3),
    xmax: +maxx.toFixed(3),
    ymax: +maxy.toFixed(3),
    width_mm: +(maxx - minx).toFixed(3),
    height_mm: +(maxy - miny).toFixed(3),
    segments: segs,
  };
}

function parseCsv(text) {
  const lines = text.split(/\r?\n/).filter((l) => l.trim().length > 0);
  if (!lines.length) return [];
  const splitRow = (line) => {
    const cells = [];
    let cur = "";
    let inQ = false;
    for (let i = 0; i < line.length; i++) {
      const ch = line[i];
      if (inQ) {
        if (ch === '"' && line[i + 1] === '"') {
          cur += '"';
          i++;
        } else if (ch === '"') {
          inQ = false;
        } else {
          cur += ch;
        }
      } else if (ch === '"') {
        inQ = true;
      } else if (ch === ",") {
        cells.push(cur);
        cur = "";
      } else {
        cur += ch;
      }
    }
    cells.push(cur);
    return cells;
  };
  const header = splitRow(lines[0]);
  return lines.slice(1).map((line) => {
    const vals = splitRow(line);
    const obj = {};
    for (let i = 0; i < header.length; i++) obj[header[i]] = vals[i] ?? "";
    return obj;
  });
}

function parseBom() {
  const byKey = new Map();
  const lcscText = readText(path.join(ROOT_DIR, "_work", "fab", "lcsc_parts.csv"));
  for (const r of parseCsv(lcscText)) {
    const val = (r.Comment || "").trim();
    const fp = (r.Footprint || "").trim();
    byKey.set(`${val}@@${fp}`, {
      lcsc: r.LCSC || "",
      mpn: r.MPN || "",
      manufacturer: r.Manufacturer || "",
      bom_desc: r.Description || "",
      library: r.Library || "",
    });
  }
  const quoteText = readText(path.join(ROOT_DIR, "_work", "fab", "quote.csv"));
  for (const r of parseCsv(quoteText)) {
    const fp = (r.Footprint || "").trim();
    for (const v of (r.Value || "").split(" / ")) {
      const key = `${v.trim()}@@${fp}`;
      if (!byKey.has(key)) {
        byKey.set(key, {
          lcsc: r.LCSC || "",
          mpn: r.MPN || "",
          manufacturer: r.Manufacturer || "",
          bom_desc: "",
          library: r.Library || "",
        });
      } else if (r.LCSC && !byKey.get(key).lcsc) {
        byKey.get(key).lcsc = r.LCSC;
      }
    }
  }
  return byKey;
}

function extractPythonStringArgs(expr) {
  // Concatenate adjacent string literals in the last string-containing argument
  const strings = [];
  let i = 0;
  let current = "";
  let inStr = false;
  let qChar = "";
  while (i < expr.length) {
    const ch = expr[i];
    if (inStr) {
      if (ch === "\\") {
        current += expr[i + 1] ?? "";
        i += 2;
      } else if (ch === qChar) {
        inStr = false;
        i++;
        // Check if whitespace/newline connects to another literal string
        let k = i;
        while (k < expr.length && /\s/.test(expr[k])) k++;
        if (expr[k] === '"' || expr[k] === "'") {
          qChar = expr[k];
          inStr = true;
          i = k + 1;
        } else {
          strings.push(current);
          current = "";
        }
      } else {
        current += ch;
        i++;
      }
    } else if (ch === '"' || ch === "'") {
      qChar = ch;
      inStr = true;
      current = "";
      i++;
    } else {
      i++;
    }
  }
  return strings;
}

function balancedCall(txt, parenStart) {
  let depth = 0;
  let j = parenStart;
  let inStr = false;
  let qChar = "";
  while (j < txt.length) {
    const ch = txt[j];
    if (inStr) {
      if (ch === "\\") j += 2;
      else {
        if (ch === qChar) inStr = false;
        j++;
      }
    } else if (ch === '"' || ch === "'") {
      inStr = true;
      qChar = ch;
      j++;
    } else if (ch === "(") {
      depth++;
      j++;
    } else if (ch === ")") {
      depth--;
      j++;
      if (depth === 0) return j;
    } else {
      j++;
    }
  }
  return j;
}

function bestDescFromStrs(strs, ref) {
  let best = "";
  for (const s of strs) {
    if (/^[A-Za-z0-9_.+-]+:[A-Za-z0-9_.+-]+$/.test(s)) continue;
    if (/^(Device|Resistor_|Capacitor_|Inductor_|Diode_|LED_|Switch|Button_|Connector|Package_|Transistor_|FPGA_|74xGxx|kv260-ias2rf|AVT_KHK_Lib|Interface_|Regulator_|Power_)/.test(s) && !s.includes(" ")) continue;
    if (/_Metric$|^Package_|^Device:|^Connector/.test(s)) continue;
    if (s === ref || s.length <= 2) continue;
    if (s.length > best.length) best = s;
  }
  return best;
}

function parseSheetSpecs() {
  const dir = path.join(ROOT_DIR, "_work", "sheets");
  const specs = new Map();
  if (!fs.existsSync(dir)) return specs;
  for (const fn of fs.readdirSync(dir).filter((f) => f.endsWith("_spec.py"))) {
    const txt = readText(path.join(dir, fn));

    // 1. Dictionary entries: "REF": (lib, val, fp, why)
    const re = /^\s*"([A-Z]{1,4}\d+[A-Z]?)"\s*:\s*/gm;
    let m;
    while ((m = re.exec(txt)) !== null) {
      const ref = m[1];
      const start = m.index + m[0].length;
      const open = txt[start];
      if (open !== "(" && !/^[A-Z]+\(/.test(txt.slice(start, start + 10))) continue;
      const parenStart = txt.indexOf("(", start);
      if (parenStart < 0 || parenStart - start > 12) continue;
      const j = balancedCall(txt, parenStart);
      const strs = extractPythonStringArgs(txt.slice(start, j));
      const best = bestDescFromStrs(strs, ref);
      if (best) specs.set(ref, { desc: best, source_file: `_work/sheets/${fn}` });
    }

    // 2. Two-terminal helper calls: two("REF", R|C|C0402|L|LED("val", "why"), ...)
    const twoRe = /^\s*two\(\s*"([A-Z]{1,4}\d+[A-Z]?)"\s*,/gm;
    while ((m = twoRe.exec(txt)) !== null) {
      const ref = m[1];
      const parenStart = m.index + m[0].indexOf("(");
      const j = balancedCall(txt, parenStart);
      const strs = extractPythonStringArgs(txt.slice(parenStart, j));
      const best = bestDescFromStrs(strs, ref);
      if (best && !specs.has(ref)) {
        specs.set(ref, { desc: best, source_file: `_work/sheets/${fn}` });
      }
    }
  }

  // 3. Programmatic STATUS LED & rail LED entries generated in _work/sheets/status_spec.py
  const statusTxt = readText(path.join(dir, "status_spec.py"));
  const stMatch = statusTxt.match(/STATUS\s*=\s*\[([\s\S]*?)\n\]/);
  if (stMatch) {
    const itemRe = /\(\s*"(D\d+)"\s*,\s*"([^"]+)"\s*,\s*"([^"]+)"\s*,\s*"([^"]+)"\s*\)/g;
    let sm;
    let k = 0;
    while ((sm = itemRe.exec(stMatch[1])) !== null) {
      const [, dRef, shortName, colour, why] = sm;
      const rRef = `R15${11 + k}`;
      k++;
      if (!specs.has(dRef)) specs.set(dRef, { desc: `Status LED (${shortName}, ${colour}): ${why}`, source_file: "_work/sheets/status_spec.py" });
      if (!specs.has(rRef)) specs.set(rRef, { desc: `${shortName} status LED current-limit resistor (~1.3 mA from +3V3_D)`, source_file: "_work/sheets/status_spec.py" });
    }
  }
  const railMap = {
    D1520: "+12V rail present green LED (~1 mA)",
    R1520: "+12V rail LED series resistor (~1 mA)",
    D1521: "+5V0 rail present green LED (~1 mA)",
    R1521: "+5V0 rail LED series resistor (~1 mA)",
    D1522: "+3V3_D rail present green LED (~1 mA)",
    R1522: "+3V3_D rail LED series resistor (~1 mA)",
    D1523: "+1V8_D rail present green LED (switched from +3V3_D via Q1520)",
    R1523: "+1V8_D rail LED resistor from +3V3_D",
    R1525: "Base drive resistor for Q1520 (+1V8_D rail sense, 35-110 uA)",
    D1524: "+1V0 rail present green LED (switched from +3V3_D via Q1521)",
    R1524: "+1V0 rail LED resistor from +3V3_D",
    R1526: "Base drive resistor for Q1521 (+1V0 rail sense, 35-110 uA)",
  };
  for (const [ref, desc] of Object.entries(railMap)) {
    if (!specs.has(ref)) specs.set(ref, { desc, source_file: "_work/sheets/status_spec.py" });
  }

  return specs;
}

function parseManualCatalog() {
  const txt = readText(path.join(ROOT_DIR, "_work", "manual", "board_manual.py"));
  const manual = new Map();
  const sectionForList = {
    CONNECTORS: "docs/BOARD_MANUAL.md#1-connectors",
    SWITCHES: "docs/BOARD_MANUAL.md#2-switches-and-jumpers",
    LEDS: "docs/BOARD_MANUAL.md#3-leds",
    ICS: "docs/BOARD_MANUAL.md#4-chips",
    OTHER: "docs/BOARD_MANUAL.md#4-chips",
  };
  let calloutNum = 0;
  for (const listName of ["CONNECTORS", "SWITCHES", "LEDS", "ICS", "OTHER"]) {
    const anchor = sectionForList[listName];
    const startIdx = txt.indexOf(`${listName} = [`);
    if (startIdx < 0) continue;
    const endIdx = txt.indexOf("\n]", startIdx);
    const block = txt.slice(startIdx, endIdx);
    const entryRe = /\(\s*"([^"]+)"\s*,\s*"([^"]*)"\s*,(?:\s*"([^"]*)"\s*,)?\s*"([^"]*)"\s*\)/g;
    let m;
    while ((m = entryRe.exec(block)) !== null) {
      calloutNum++;
      const ref = m[1];
      const nameOrVal = m[2];
      const why = m[4];
      manual.set(ref, {
        name: nameOrVal,
        desc: why,
        manual_section: anchor,
        callout: listName === "LEDS" ? (ref.startsWith("D152") ? 30 : ref === "D1101" ? 31 : 29) : calloutNum,
      });
    }
  }
  return manual;
}

function sheetLink(sheet, ref) {
  if (/^TP\d+$/.test(ref)) return "docs/BOARD_MANUAL.md#12-test-points";
  if (ref === "J1102") return "docs/BOARD_MANUAL.md#11-pmod-j1102";
  if (/^(J1502|J1503|U1506|D1531|Q1530|Q1531|C1550|R155[1-7])$/.test(ref)) {
    return "docs/INTEGRATIONS.md#22-the-vehicles-can-bus-on-r5f-core-1";
  }
  const map = {
    CONTROL: "docs/CONTROL_SPEC.md",
    POWER: "docs/POWER_SPEC.md",
    CLOCK: "docs/CLOCK_SPEC.md",
    ADC_RADAR: "docs/CONVERTER_SPEC.md",
    ADC_SDR: "docs/CONVERTER_SPEC.md",
    DAC_RADAR: "docs/CONVERTER_SPEC.md",
    DAC_SDR: "docs/CONVERTER_SPEC.md",
    ROUTING: "docs/ROUTING_SPEC.md",
    IAS_LINK: "docs/INTERFACE_SPEC.md",
    RX_VU: "docs/RX_VU_SPEC.md",
    STATUS: "docs/LAYOUT.md#68-debug-usb-c-gps-pps-and-vehicle-can",
    KVPWR: "docs/POWER_SPEC.md#14-single-power-entry-for-the-kv260-and-adapter",
  };
  return map[sheet] || "docs/BOARD_MANUAL.md";
}

function estimateHeightMm(ref, fp, hasStep) {
  if (/^(FID|TP|MH|JP|NT)/.test(ref)) return 0.1;
  if (/^J1201/.test(ref)) return 13.5;
  if (/^J1001/.test(ref)) return 11.0;
  if (/^J1004/.test(ref)) return 9.0;
  if (/^J1103/.test(ref)) return 8.8;
  if (/^J1102/.test(ref)) return 8.5;
  if (/^J1501/.test(ref)) return 9.3;
  if (/^J(4|9)/.test(ref)) return 6.35;
  if (/^J1503/.test(ref)) return 2.95;
  if (/^J1502/.test(ref)) return 2.55;
  if (/^J10[123]/.test(ref)) return 0.8;
  if (/^L1004/.test(ref)) return 4.8;
  if (/^L10/.test(ref)) return 2.8;
  if (/^T7|^T8/.test(ref)) return 2.84;
  if (/^Y401/.test(ref)) return 1.65;
  if (/^U1101/.test(ref)) return 1.75;
  if (fp.includes("0402")) return 0.55;
  if (fp.includes("0603")) return 0.8;
  if (fp.includes("0805")) return 1.25;
  if (fp.includes("1206") || fp.includes("1210")) return 1.6;
  if (hasStep) return 1.2;
  return 1.0;
}

const KV260_PARTS = [
  {
    id: "KV260_CARRIER",
    ref: "KV260 Carrier",
    value: "128-05058-01 Rev B01",
    part: "AMD Kria KV260 Vision AI Starter Kit Carrier Card",
    assembly: "kv260",
    subassembly: "carrier",
    bbox_mm: [-10.0, -10.0, 130.0, 109.0, -1.59, 0.0],
    role: "Carrier PCB (140 x 119 x 1.59 mm) providing PS peripherals, USB 3.0 hub, Gigabit Ethernet, HDMI/DP, Pmod J2, RPi camera J9, and IAS0/IAS1 connectors.",
    citation: "AMD UG1089 (KV260 User Guide); XTP682 (Carrier Schematic)",
    manual_link: "docs/INTERFACE_SPEC.md#5-mechanical-envelope-measured",
  },
  {
    id: "K26_SOM",
    ref: "K26 SOM",
    value: "128-05057-01 (K26)",
    part: "AMD Kria K26 System-on-Module PCB",
    assembly: "kv260",
    subassembly: "som",
    bbox_mm: [47.63, 16.98, 124.63, 76.98, 5.0, 6.9],
    role: "77 x 60 mm SOM carrier board carrying the XCK26 MPSoC, 4 GB DDR4, eMMC/QSPI, power rails, and two 240-pin Samtec SOM240 connectors underneath.",
    citation: "AMD DS987 (K26 SOM Data Sheet)",
    manual_link: "docs/FPGA_GATEWARE.md#33-k26-block-design--post-route-resources-fpga_kria_reports",
  },
  {
    id: "K26_XCK26",
    ref: "U1 (K26)",
    value: "XCK26-SFVC784-2LV-C",
    part: "Zynq UltraScale+ MPSoC (Quad A53 + Dual R5F + PL)",
    assembly: "kv260",
    subassembly: "som",
    bbox_mm: [80.57, 26.95, 103.57, 49.95, 6.91, 10.03],
    role: "Main SoC: 4x A53 (Linux, kria-hmid, kria-vehicled, kria-sdrd), 2x R5F (kria-r5f0 interlock/PPS/watchdog, kria-r5f1 radar scan/BEV grid/CAN1), Mali-400 GPU, VCU, and PL (53,336 LUTs = 45.5%, 229 DSP48E2, WNS +1.043 ns, WHS +0.010 ns).",
    citation: "AMD DS987 / DS891 / UG1085",
    manual_link: "docs/HMI.md#5-processing-partition",
  },
  {
    id: "K26_DDR4",
    ref: "U11-U14 (K26)",
    value: "4x 16-bit DDR4-2400 (4 GB)",
    part: "K26 SOM PS DDR4 Memory",
    assembly: "kv260",
    subassembly: "som",
    bbox_mm: [67.18, 58.64, 105.16, 72.14, 6.9, 8.1],
    role: "4 GB PS DDR4 holding the 0x3EE0_0000 R5F shared mailbox, BEV grid frames, KrakenSDR and HackRF DMA buffers, and kria_ps_framer 64 KiB udmabuf0 blocks.",
    citation: "AMD DS987; sw/ias2rf_pl.dtsi",
    manual_link: "docs/INTEGRATIONS.md#7-software-on-the-k26s-processors",
  },
  {
    id: "K26_EMMC",
    ref: "U133 (K26)",
    value: "16 GB eMMC + QSPI",
    part: "K26 Non-Volatile Boot Storage",
    assembly: "kv260",
    subassembly: "som",
    bbox_mm: [107.48, 52.92, 118.98, 65.92, 7.2, 8.0],
    role: "Stores U-Boot, Linux kernel, device-tree overlay, and R5F firmware images for remoteproc boot.",
    citation: "AMD DS987 / UG1089",
    manual_link: "sw/kria/README.md#on-the-kv260",
  },
  {
    id: "SOM240_1",
    ref: "JA1 (SOM240_1)",
    value: "Samtec ADF6/ADM6 240-pin",
    part: "SOM-to-Carrier Connector 1 (PL HP/HD I/O)",
    assembly: "kv260",
    subassembly: "som",
    bbox_mm: [50.32, 25.57, 55.32, 68.39, 0.02, 5.0],
    role: "Routes PL HP Bank 66 (1.2 V: IAS1 5x LVDS pairs and J9 PS CAN1 EMIO on A9/G6 and C13/D6) plus HD Bank 45 (3.3 V: J9 GPS PPS on A16/J12 and J2 Pmod).",
    citation: "AMD DS987 & XTP682; INTERFACE_SPEC.md §3.1",
    manual_link: "docs/FPGA_GATEWARE.md#511-ps-can1-through-emio-18-nov",
  },
  {
    id: "SOM240_2",
    ref: "JA2 (SOM240_2)",
    value: "Samtec ADF6/ADM6 240-pin",
    part: "SOM-to-Carrier Connector 2 (PS MIO/GTR/Power)",
    assembly: "kv260",
    subassembly: "som",
    bbox_mm: [116.3, 25.57, 121.3, 68.39, 0.02, 5.0],
    role: "Routes PS MIO peripherals, 4x PS-GTR transceivers (DisplayPort, USB 3.0, SGMII Ethernet), and K26 main power rails.",
    citation: "AMD DS987 & UG1089",
    manual_link: "docs/HMI.md#1-the-display-path-on-the-kv260",
  },
  {
    id: "KV260_HEATSINK",
    ref: "HEATSINK (KV260)",
    value: "HSP-00076-01 Extruded Al",
    part: "K26 OEM Aluminium Heatsink",
    assembly: "kv260",
    subassembly: "cooling",
    bbox_mm: [52.43, 20.78, 119.83, 73.18, 5.81, 25.11],
    role: "Stock K26 aluminium heatsink mounted with four spring screws over the XCK26 die (removed in this view to expose the K26 SOM).",
    citation: "AMD XTP679 / UG1089",
    manual_link: "docs/ENCLOSURE_V2_THERMAL.md",
  },
  {
    id: "KV260_FAN",
    ref: "FAN (KV260)",
    value: "40x40x10 mm Axial PWM Fan",
    part: "K26 OEM Cooling Fan & Shroud",
    assembly: "kv260",
    subassembly: "cooling",
    bbox_mm: [51.13, 18.98, 121.13, 74.98, 10.12, 28.75],
    role: "Stock 4010 PWM cooling fan in shroud (top at Z = 28.75 mm; enclosure v2 lid clears it by 4 mm behind a 27 mm hex intake grille).",
    citation: "AMD UG1089; ENCLOSURE.md §2",
    manual_link: "docs/ENCLOSURE.md#2-geometry",
  },
  {
    id: "KV260_J8_IAS1",
    ref: "J8 (KV260 IAS1)",
    value: "BM20B(0.8)-34DS-0.4V(51)",
    part: "Carrier IAS1 Camera Connector",
    assembly: "kv260",
    subassembly: "carrier",
    bbox_mm: [20.45, 7.3, 22.85, 16.68, 0.0, 0.8],
    role: "Mates directly with adapter J101 underneath. Direct 1.2 V Bank 66 HPA05..HPA09 connection to the K26 SOM for the 64b/66b 5x LVDS link plus 1.8 V HK I2C, FPGA_PROG_B, and FPGA_IRQ.",
    citation: "AMD UG1089 / XTP682 p.13; INTERFACE_SPEC.md §3.1, §4.1",
    manual_link: "docs/INTERFACE_SPEC.md#3-link-allocation-frozen",
  },
  {
    id: "KV260_J7_IAS0",
    ref: "J7 (KV260 IAS0)",
    value: "BM20B(0.8)-34DS-0.4V(51)",
    part: "Carrier IAS0 Camera Connector (via AP1302 U27)",
    assembly: "kv260",
    subassembly: "carrier",
    bbox_mm: [20.45, 57.33, 22.85, 66.71, 0.0, 0.8],
    role: "Routed through the onsemi AP1302 ISP (U27). Mates with adapter J102 and passes pin-for-pin up to J103 on the adapter tongue so an IAS camera module still works.",
    citation: "AMD UG1089 / XTP682 p.13; INTERFACE_SPEC.md §3.1",
    manual_link: "docs/BOARD_MANUAL.md#1-connectors",
  },
  {
    id: "KV260_U27_AP1302",
    ref: "U27 (KV260)",
    value: "onsemi AP1302 ISP",
    part: "Image Co-Processor for IAS0",
    assembly: "kv260",
    subassembly: "carrier",
    bbox_mm: [25.86, 68.39, 38.01, 80.54, 0.0, 1.7],
    role: "Carrier image signal processor sitting in front of J7 (IAS0), which is why our high-speed link uses direct J8 (IAS1) instead of J7.",
    citation: "AMD XTP682 p.13; INTERFACE_SPEC.md §3.1",
    manual_link: "docs/INTERFACE_SPEC.md#31-som-side-mapping-verified-against-the-carrier-schematic",
  },
  {
    id: "KV260_J9_RPI",
    ref: "J9 (KV260 RPi CSI)",
    value: "TE 1-1734248-5 (15-way 1 mm FFC)",
    part: "Raspberry Pi Camera Connector",
    assembly: "kv260",
    subassembly: "carrier",
    bbox_mm: [86.41, -8.57, 91.26, 13.83, 0.0, 5.68],
    role: "Joined by a 100 mm 15-way FFC to adapter J1502: pin 12 carries 3.3 V GPS PPS (HDA10, ball J12 -> kria_pps); pin 6 carries EMIO CAN1 TX (can1_txn, ball G6, 1.2 V) and pin 8 carries EMIO CAN1 RX (can1_rx, ball D6, 1.2 V -> PS CAN1 on R5F core 1).",
    citation: "AMD UG1089 / XTP682 p.13; INTEGRATIONS.md §2.1, §2.2",
    manual_link: "docs/INTEGRATIONS.md#22-the-vehicles-can-bus-on-r5f-core-1",
  },
  {
    id: "KV260_J2_PMOD",
    ref: "J2 (KV260 Pmod)",
    value: "12-pin 2x6 2.54 mm Header",
    part: "Pmod Control & Debug Header",
    assembly: "kv260",
    subassembly: "carrier",
    bbox_mm: [13.65, -9.99, 29.65, 3.2, -1.59, 5.2],
    role: "Cabled to adapter J1102: carries 3.3 V Artix SPI (CS, MOSI, MISO, SCLK), BEAM_STROBE from R5F core 1, PPS_SYNC from kria_pps, and EMIO PS UART1 console (/dev/ttyPS1, 115,200 baud).",
    citation: "AMD UG1089; BOARD_MANUAL.md §1.1",
    manual_link: "docs/BOARD_MANUAL.md#11-pmod-j1102",
  },
  {
    id: "KV260_J10_RJ45",
    ref: "J10 (KV260 GbE)",
    value: "L829-1J1T-43 + RTL8211F",
    part: "Gigabit Ethernet RJ45 MagJack (PS GEM3)",
    assembly: "kv260",
    subassembly: "carrier",
    bbox_mm: [96.83, 86.96, 117.21, 111.53, -3.86, 12.52],
    role: "Carrier PS GEM3 Gigabit Ethernet port: connects to adapter J1201 for the redundant 1000BASE-T UDP data and control link.",
    citation: "AMD UG1089; fpga/eth/REDUNDANCY.md",
    manual_link: "docs/INTEGRATIONS.md#1-summary",
  },
  {
    id: "KV260_U44_USB3",
    ref: "U44 (KV260 USB3)",
    value: "Dual USB 3.0 Type-A Stack",
    part: "USB 3.0 Host Ports (via U43 USB5744 Hub)",
    assembly: "kv260",
    subassembly: "carrier",
    bbox_mm: [77.57, 91.15, 93.5, 110.85, -3.73, 15.72],
    role: "Connects external vehicle peripherals: USB GPS (NMEA to gpsd/chrony), 77 GHz radar CAN FD adapter, or 3D LiDAR USB-to-Gigabit Ethernet adapter.",
    citation: "AMD UG1089; INTEGRATIONS.md §1",
    manual_link: "docs/INTEGRATIONS.md#1-summary",
  },
  {
    id: "KV260_U46_USB3",
    ref: "U46 (KV260 USB3)",
    value: "Dual USB 3.0 Type-A Stack",
    part: "USB 3.0 Host Ports (via U43 USB5744 Hub)",
    assembly: "kv260",
    subassembly: "carrier",
    bbox_mm: [58.26, 91.15, 74.2, 110.85, -3.73, 15.72],
    role: "Connects USB 2.0/3.0 SDR peripherals and UI hardware: KrakenSDR (5x RTL2832U, 24 MB/s), HackRF Pro (20 MB/s), Wi-Fi adapter (opendash), and USB touchscreen.",
    citation: "AMD UG1089; INTEGRATIONS.md §1, §9, §10",
    manual_link: "docs/INTEGRATIONS.md#9-direction-finding-with-a-krakensdr",
  },
  {
    id: "KV260_J5_HDMI",
    ref: "J5 (KV260 HDMI)",
    value: "HDMI 1.4 Type-A",
    part: "Video Output (STDP4320 Splitter from PS DP)",
    assembly: "kv260",
    subassembly: "carrier",
    bbox_mm: [38.76, 99.8, 54.96, 109.87, -2.05, 6.08],
    role: "Drives the 1280 x 720 in-car touchscreen display directly from PS DisplayPort controller via Linux DRM/KMS (kria-hmi on Slint); the PL is not in the display path.",
    citation: "AMD UG1089 / XTP682 p.10-12; HMI.md §1",
    manual_link: "docs/HMI.md#1-the-display-path-on-the-kv260",
  },
  {
    id: "KV260_J6_DP",
    ref: "J6 (KV260 DP)",
    value: "Molex 472720001 DisplayPort 1.2a",
    part: "DisplayPort Output (STDP4320 Splitter)",
    assembly: "kv260",
    subassembly: "carrier",
    bbox_mm: [15.3, 94.93, 33.09, 109.82, -2.1, 6.65],
    role: "Second display output shared with J5 HDMI via the carrier STDP4320 hub from two PS-GTR lanes (GTR_DP0, GTR_DP1).",
    citation: "AMD UG1089 / XTP682 p.10-12; HMI.md §1",
    manual_link: "docs/HMI.md#1-the-display-path-on-the-kv260",
  },
  {
    id: "KV260_J12_DC12V",
    ref: "J12 (KV260 12V)",
    value: "CUI PJ-202AH Barrel Jack",
    part: "12 V DC Carrier Power Input",
    assembly: "kv260",
    subassembly: "carrier",
    bbox_mm: [1.78, 92.96, 11.18, 107.36, -3.0, 11.5],
    role: "12 V 3 A power input for the KV260 carrier and K26 SOM, fed from adapter J1004 via a VHR-2N jumper through the U1010 3.0 A eFuse (POWER_SPEC.md §1.4, BOARD_MANUAL.md §6; never power J1001 and J12 from separate supplies).",
    citation: "AMD UG1089; POWER_SPEC.md §1.4",
    manual_link: "docs/POWER_SPEC.md#14-single-power-entry-for-the-kv260-and-adapter",
  },
  {
    id: "KV260_J4_UART",
    ref: "J4 (KV260 USB-JTAG)",
    value: "Micro-AB USB + FT4232H",
    part: "PS UART / PL JTAG Debug Port",
    assembly: "kv260",
    subassembly: "carrier",
    bbox_mm: [40.06, -11.57, 48.71, -5.67, -0.49, 2.9],
    role: "USB-to-JTAG and UART console bridge for the K26 PS Linux console, R5F debugging, and Vivado JTAG programming.",
    citation: "AMD UG1089",
    manual_link: "docs/ENCLOSURE.md#2-geometry",
  },
  {
    id: "KV260_J11_SD",
    ref: "J11 (KV260 microSD)",
    value: "Molex 5025700893 microSD",
    part: "microSD Card Slot",
    assembly: "kv260",
    subassembly: "carrier",
    bbox_mm: [93.45, -8.2, 107.25, 7.3, 0.1, 1.9],
    role: "Holds the PetaLinux / Ubuntu root filesystem, device tree overlay, and recordings on the carrier.",
    citation: "AMD UG1089",
    manual_link: "docs/ENCLOSURE.md#2-geometry",
  },
  {
    id: "KV260_J_FAN",
    ref: "J13 (KV260 4010 Fan Header)",
    value: "Molex 4-pin PWM Header",
    part: "SOM / Carrier Fan Header",
    assembly: "kv260",
    subassembly: "carrier",
    bbox_mm: [112.0, 74.0, 116.5, 84.0, 0.0, 6.5],
    role: "4-pin PWM header powering the KV260 4010 SOM cooler fan.",
    citation: "AMD UG1089",
    manual_link: "docs/ENCLOSURE_V2_THERMAL.md",
  },
];

const KICAD_STEP_REPLACED = new Set([
  "DC-IN-TH_PJ-102AH.wrl",
  "RJ45-TH_HR911130C.wrl",
  "FPC-SMD_15P-P1.00_XUNPU_FPC-1.0FX-15PWCR-H20.wrl",
  "SOT-23-6_L2.9-W1.6-H1.5-LS2.8-P0.95.wrl",
  "SC-70-6_L2.0-W1.3-H1.0-P0.65.wrl",
  "SOT343_L2.0-W1.3-H0.9-P1.30-LS2.1-BL.wrl",
  "QFN-24_L4.0-W4.0-P0.50-BL-EP2.8.wrl",
  "WQFN-24_L4.0-W4.0-H0.8-P0.50.wrl",
  "QFN-20_L4.0-W4.0-H0.8-P0.50.wrl",
  "QFN-14_L2.0-W2.0-H0.5-P0.45-BL-EP.wrl",
  "MSOP-10_L3.0-W3.0-H1.1-LS5.0-P0.50.wrl",
  "F1812_L4.5-W3.2-H1.0.wrl",
  "IND-SMD_SRP7028A-8R2M.wrl",
  "OSC-SMD_8P-L7.0-W5.0-BL.wrl",
  "OSC-SMD_4P-L2.0-W1.6-H0.8.wrl",
  "FILTER-SMD_1206-4P-L3.2-W1.6-H0.9-L.wrl",
  "JST_SH_BM06B-SRSS-TB_toned.wrl",
]);

const EXTRA_PARTS = [
  {
    id: "HS1_U501_AD9484",
    ref: "HS1 (U501 Heatsink)",
    value: "14x14x8.5 mm Finned Black Al",
    part: "Stick-on Aluminium Heatsink on AD9484",
    assembly: "heatsinks",
    bbox_mm: [-58.8, 3.55, -44.8, 17.55, 3.34, 11.84],
    role: "7-fin anodised heatsink over U501 (AD9484 500 MSPS radar ADC, ~1.05 W) with 0.18 mm TIM gap pad.",
    manual_link: "docs/ENCLOSURE_V2_THERMAL.md",
  },
  {
    id: "HS2_U401_ADCLK948",
    ref: "HS2 (U401 Heatsink)",
    value: "9x7x8 mm Finned Blue Al",
    part: "Stick-on Aluminium Heatsink on ADCLK948",
    assembly: "heatsinks",
    bbox_mm: [-39.4, -4.7, -30.4, 2.3, 3.15, 11.15],
    role: "5-fin heatsink on U401 (ADCLK948 clock fan-out, ~0.95 W), decoupled from HS3 by a 4.0 mm air gap.",
    manual_link: "docs/ENCLOSURE_V2_THERMAL.md",
  },
  {
    id: "HS3_Y401_Si549",
    ref: "HS3 (Y401 Heatsink)",
    value: "9x7x8 mm Finned Blue Al",
    part: "Stick-on Aluminium Heatsink on Si549 XO",
    assembly: "heatsinks",
    bbox_mm: [-39.5, 6.3, -30.5, 13.3, 3.99, 11.99],
    role: "5-fin heatsink on Y401 (Si549 low-jitter XO), separated from U401 by 4.0 mm so the clock buffer does not heat the crystal.",
    manual_link: "docs/ENCLOSURE_V2_THERMAL.md",
  },
  {
    id: "HS4_U1101_XC7A50T",
    ref: "HS4 (U1101 Heatsink)",
    value: "14x14x5 mm Finned Copper",
    part: "Low-Profile Heatsink on XC7A50T FPGA",
    assembly: "heatsinks",
    bbox_mm: [-49.75, 33.0, -35.75, 47.0, 3.84, 8.84],
    role: "8-fin low-profile copper heatsink on U1101 (XC7A50T front-end FPGA, 1.25/1.60 W; required in a vehicle: 102.1 -> 93.4 C clean / 94.2 C clogged at 70 C).",
    manual_link: "docs/ENCLOSURE_V2_THERMAL.md",
  },
  {
    id: "FAN2_5015",
    ref: "OD5015 Lid Fan",
    value: "Orion OD5015-05HB (50x50x15 mm)",
    part: "5 V Intake Blowing Fan over Adapter",
    assembly: "enclosure",
    bbox_mm: [-65.0, -11.0, -15.0, 39.0, 13.75, 28.75],
    role: "5 V 0.13 A 14 CFM intake fan powered from J1002 through a 100-mesh stainless dust filter in case_v2_filter_frame.",
    manual_link: "docs/ENCLOSURE_V2_THERMAL.md",
  },
];

const STACKUP = [
  { id: "F.Cu", name: "L1 Top Copper (F.Cu)", role: "1 oz ENIG signal & component pads, controlled-impedance RF microstrip", thickness_mm: 0.035, z_mm: 1.6, color: "#d99b38" },
  { id: "In1.Cu", name: "L2 Ground (In1.Cu)", role: "0.5 oz solid reference ground plane under L1 microstrips and LVDS", thickness_mm: 0.017, z_mm: 1.48, color: "#4aa868" },
  { id: "In2.Cu", name: "L3 Inner Signal (In2.Cu)", role: "0.5 oz inner signal routing and <1 ps meandered LVDS differential pairs", thickness_mm: 0.017, z_mm: 1.15, color: "#e06d53" },
  { id: "In3.Cu", name: "L4 Power (In3.Cu)", role: "0.5 oz split analogue and digital power planes (+3V3_A, +3V3_D, +1V8_A/D, +2V5, +1V0)", thickness_mm: 0.017, z_mm: 0.90, color: "#5c9ce6" },
  { id: "In4.Cu", name: "L5 Ground (In4.Cu)", role: "0.5 oz internal ground return plane", thickness_mm: 0.017, z_mm: 0.65, color: "#4aa868" },
  { id: "In5.Cu", name: "L6 Inner Signal (In5.Cu)", role: "0.5 oz inner signal routing and matched clock/IAS1 pairs", thickness_mm: 0.017, z_mm: 0.40, color: "#c985e6" },
  { id: "In6.Cu", name: "L7 Ground (In6.Cu)", role: "0.5 oz reference ground plane above bottom copper", thickness_mm: 0.017, z_mm: 0.12, color: "#4aa868" },
  { id: "B.Cu", name: "L8 Bottom Copper (B.Cu)", role: "1 oz ENIG bottom pads (J101, J102, LM74502 protection, PE4312, TCA6416A)", thickness_mm: 0.035, z_mm: 0.0, color: "#48b5c4" },
  { id: "F.Mask", name: "Top Soldermask (F.Mask)", role: "KV260 translucent green LPI mask over copper", thickness_mm: 0.02, z_mm: 1.64, color: "#197a3a" },
  { id: "F.SilkS", name: "Top Silkscreen (F.SilkS)", role: "Off-white reference designators and pin-1 markers", thickness_mm: 0.01, z_mm: 1.66, color: "#e6e6e0" },
  { id: "Edge.Cuts", name: "Board Outline (Edge.Cuts)", role: "140 x 132 mm milled perimeter, RJ45 tab, J961 & J18 clearances", thickness_mm: 0.0, z_mm: 0.8, color: "#f0b429" },
];

function extractNetTraces(pcbText) {
  const layerIdxMap = {
    "F.Cu": 0, "In1.Cu": 1, "In2.Cu": 2, "In3.Cu": 3,
    "In4.Cu": 4, "In5.Cu": 5, "In6.Cu": 6, "B.Cu": 7,
  };
  const byNet = new Map();
  for (const blk of topLevelBlocks(pcbText, "segment")) {
    const netM = blk.match(/\(net\s+(?:\d+\s+)?"((?:[^"\\]|\\.)*)"\)/);
    if (!netM) continue;
    const net = unescapeKiCad(netM[1]);
    if (!net || net === "GND") continue;
    const stM = blk.match(/\(start\s+([-\d.]+)\s+([-\d.]+)\)/);
    const enM = blk.match(/\(end\s+([-\d.]+)\s+([-\d.]+)\)/);
    const lyM = blk.match(/\(layer\s+"([^"]+)"\)/);
    if (!stM || !enM || !lyM) continue;
    const x1 = +parseFloat(stM[1]).toFixed(2);
    const y1 = +parseFloat(stM[2]).toFixed(2);
    const x2 = +parseFloat(enM[1]).toFixed(2);
    const y2 = +parseFloat(enM[2]).toFixed(2);
    if (x1 === x2 && y1 === y2) continue;
    const lIdx = layerIdxMap[lyM[1]] ?? 0;
    let arr = byNet.get(net);
    if (!arr) {
      arr = [];
      byNet.set(net, arr);
    }
    arr.push([x1, y1, x2, y2, lIdx]);
  }
  const out = {};
  for (const [k, v] of byNet.entries()) out[k] = v;
  const tracesPath = path.join(SITE_DIR, "assets", "net_traces.json");
  fs.writeFileSync(tracesPath, JSON.stringify(out));
  console.log(`Wrote ${tracesPath}: ${byNet.size} routed signal nets.`);
}

function build() {
  const pcbText = fs.readFileSync(PCB_PATH, "utf8");
  const edgeCuts = parseEdgeCuts(pcbText);
  extractNetTraces(pcbText);
  const bom = parseBom();
  const sheetSpecs = parseSheetSpecs();
  const manual = parseManualCatalog();

  const components = [];
  const netSet = new Set();

  for (const block of topLevelBlocks(pcbText, "footprint ")) {
    const fpMatch = block.match(/^\(footprint "([^"]+)"/);
    if (!fpMatch) continue;
    const fpid = fpMatch[1];
    const footprint = fpid.includes(":") ? fpid.split(":")[1] : fpid;
    const side = /^\t\t\(layer "B\.Cu"\)/m.test(block) ? "bottom" : "top";
    const atMatch = block.match(/^\t\t\(at ([-\d.]+) ([-\d.]+)(?: ([-\d.]+))?\)/m);
    if (!atMatch) continue;
    const x = parseFloat(atMatch[1]);
    const y = parseFloat(atMatch[2]);
    const rot = parseFloat(atMatch[3] || "0");
    const ref = extractProp(block, "Reference");
    if (!ref) continue;
    const value = extractProp(block, "Value");
    const sheetMatch = block.match(/\(sheetname "([^"]*)"\)/);
    const sheet = (sheetMatch ? sheetMatch[1].replace(/^\/|\/$/g, "") : "") || "root";
    const attrMatch = block.match(/\(attr[^)]*\)/);
    const dnp = !!(attrMatch && attrMatch[0].includes(" dnp"));

    // Model provenance
    const modelPaths = [...block.matchAll(/\(model\s+"([^"]+)"/g)].map((m) => m[1]);
    let modelSource = "none";
    if (modelPaths.some((p) => KICAD_STEP_REPLACED.has(p.split("/").pop()))) {
      modelSource = "kicad-step";
    } else if (modelPaths.some((p) => p.includes("mech/models3d/USB_C_HRO"))) {
      modelSource = "repo-vrml";
    } else if (modelPaths.some((p) => p.includes("_work/mech/cache/models3d/"))) {
      modelSource = "procedural-replacement";
    } else if (modelPaths.some((p) => p.endsWith(".wrl") && !p.endsWith(".step"))) {
      modelSource = "procedural-replacement";
    } else if (modelPaths.some((p) => p.includes("${KICAD10_3DMODEL_DIR}") || p.includes("mech/models3d/"))) {
      modelSource = "kicad-step";
    }

    // Bounding box
    const prefix = side === "bottom" ? "B" : "F";
    let pts = localPts(block, new Set([`${prefix}.CrtYd`]));
    if (!pts.length) pts = localPts(block, new Set([`${prefix}.Fab`]));
    if (!pts.length) pts = padPts(block);
    if (!pts.length) pts = [[-0.5, -0.5], [0.5, 0.5]];
    const lxs = pts.map((p) => p[0]);
    const lys = pts.map((p) => p[1]);
    const lxmin = Math.min(...lxs);
    const lxmax = Math.max(...lxs);
    const lymin = Math.min(...lys);
    const lymax = Math.max(...lys);
    const rad = (rot * Math.PI) / 180;
    const ca = Math.cos(rad);
    const sa = Math.sin(rad);
    const corners = [
      [lxmin, lymin],
      [lxmax, lymin],
      [lxmax, lymax],
      [lxmin, lymax],
    ].map(([px, py]) => [x + px * ca + py * sa, y - px * sa + py * ca]);
    const bxmin = Math.min(...corners.map((p) => p[0]));
    const bxmax = Math.max(...corners.map((p) => p[0]));
    const bymin = Math.min(...corners.map((p) => p[1]));
    const bymax = Math.max(...corners.map((p) => p[1]));

    // Pads & nets (KiCad 10 omits net code in pad block: `(net "NAME")`, older KiCad uses `(net 1 "NAME")`)
    const pads = {};
    const compNets = new Set();
    const padRe = /\(pad "([^"]*)"[\s\S]*?\(net (?:\d+\s+)?"((?:[^"\\]|\\.)*)"\)/g;
    let pm;
    while ((pm = padRe.exec(block)) !== null) {
      const pNum = pm[1] || "?";
      const net = unescapeKiCad(pm[2]);
      if (net && !net.startsWith("unconnected-")) {
        pads[pNum] = net;
        compNets.add(net);
        netSet.add(net);
      } else if (net) {
        pads[pNum] = "(nc)";
      }
    }

    const bomInfo = bom.get(`${value}@@${footprint}`) || bom.get(`${value}@@`) || null;
    const specInfo = sheetSpecs.get(ref) || null;
    const manualInfo = manual.get(ref) || null;

    const cleanBomDesc = bomInfo && bomInfo.bom_desc
      ? bomInfo.bom_desc.replace(/[\u4E00-\u9FFF]+/g, "").replace(/\s{2,}/g, " ").trim()
      : "";

    let description = "no description yet";
    const meaningfulSpec = specInfo && specInfo.desc && specInfo.desc !== value && specInfo.desc !== footprint;
    const specOverlapsManual = manualInfo && meaningfulSpec && (
      manualInfo.desc.includes(specInfo.desc) ||
      (/1\s*(?:GND|ground)/i.test(manualInfo.desc) && /1\s*=\s*(?:GND|ground)/i.test(specInfo.desc)) ||
      specInfo.desc.split(/\W+/).filter((w) => w.length > 3).filter((w) => manualInfo.desc.toLowerCase().includes(w.toLowerCase())).length >= 5
    );
    const REV08_AUDIT_OVERRIDES = {
      C1441: {
        desc: "11 pF C0G 0402 series input capacitor, preselector B high-pass (Rev08 audit R1)",
        link: "docs/AUDIT_Rev08.md",
      },
      L1441: {
        desc: "24 nH LQW15AN 0402 shunt inductor with C1442 (36 pF), preselector B high-pass (Rev08 audit R1)",
        link: "docs/AUDIT_Rev08.md",
      },
      C1442: {
        desc: "36 pF C0G 0402 shunt capacitor with L1441 (24 nH), preselector B high-pass (Rev08 audit R1)",
        link: "docs/AUDIT_Rev08.md",
      },
      C1443: {
        desc: "5.6 pF C0G 0402 series arm capacitor, preselector B high-pass (Rev08 audit R1)",
        link: "docs/AUDIT_Rev08.md",
      },
      L1442: {
        desc: "22 nH LQW15AN 0402 shunt inductor with C1444 (91 pF), preselector B high-pass (Rev08 audit R1)",
        link: "docs/AUDIT_Rev08.md",
      },
      C1444: {
        desc: "91 pF C0G 0402 shunt capacitor with L1442 (22 nH), preselector B high-pass (Rev08 audit R1)",
        link: "docs/AUDIT_Rev08.md",
      },
      C1445: {
        desc: "8.2 pF C0G 0402 output capacitor to VU_PSB_HP, preselector B high-pass (Rev08 audit R1)",
        link: "docs/AUDIT_Rev08.md",
      },
      U1002: {
        desc: "TPS563201 (3 A) synchronous buck converter for +3V3_D (upgraded from 2 A TPS562201, 63% worst-case use; Rev08 audit P5)",
        link: "docs/AUDIT_Rev08.md",
      },
      U1006: {
        desc: "TPS7A8300RGR low-noise LDO for +1V8_D set to 1.85 V (pin 5 ANY-OUT grounded; VCCAUX 1.714-1.873 V at balls, 0.91 W worst; Rev08 audit P4)",
        link: "docs/AUDIT_Rev08.md",
      },
      U1315: {
        desc: "LP5907MFX-2.8 ultra-low-noise LDO for +2V8_RF front-end rail (232 mV worst-case headroom vs 180 mV dropout; Rev08 audit P8)",
        link: "docs/AUDIT_Rev08.md",
      },
      U1506: {
        desc: "TCAN3403DDFRQ1 3.3 V CAN transceiver (+-58 V bus fault protection, pin 5 VIO on +3V3_D, STB low; Rev08 audit P1)",
        link: "docs/AUDIT_Rev08.md",
      },
      F1001: {
        desc: "mSMD200-24V 1812 PTC resettable fuse, 2.0 A hold (trips above 83.9 C at 12 V / 73.1 C at 10.5 V worst case; Rev08 audit P3)",
        link: "docs/AUDIT_Rev08.md",
      },
      R1031: {
        desc: "3.24 kOhm 0402 1% feedback divider resistor setting +1V0 buck to 1.017 V nominal (0.983 V at balls at full load; Rev08 audit P7)",
        link: "docs/AUDIT_Rev08.md",
      },
      R1542: {
        desc: "330 Ohm 0402 series resistor on GPS PPS line limiting back-powering into unpowered K26 to 7.6 mA (Rev08 audit P2b)",
        link: "docs/AUDIT_Rev08.md",
      },
      R1543: {
        desc: "330 Ohm 0402 series resistor on GPS PPS line copy limiting back-powering into unpowered K26 to 7.6 mA (Rev08 audit P2b)",
        link: "docs/AUDIT_Rev08.md",
      },
      J961: {
        desc: "VHF/UHF SMA antenna input: direct 30-170 MHz and converted from 300 MHz to 3 GHz (170-300 MHz not covered); selectable 3.3/5 V bias tee via AP22652 (Rev08 audit R1/R6/R7)",
        link: "docs/AUDIT_Rev08.md",
      },
      J1102: {
        desc: "12-pin 2x6 Pmod header (Artix bank 15 <-> K26 HDA); Pmod back-powering gated in gateware on both FPGAs (kria_present / adapter_alive, PMOD_SPARE2 open-drain; Rev08 audit P2)",
        link: "docs/AUDIT_Rev08.md",
      },
      J1004: {
        desc: "JST B2PS-VH 2-pin 3.96 mm horizontal 12 V output header feeding KV260 J12 over a short VHR-2N jumper (single-entry return via BM20 link by design, 132 mA/contact at 3.19 A worst)",
        link: "docs/POWER_SPEC.md#14-single-power-entry-for-the-kv260-and-adapter",
      },
      L1004: {
        desc: "ZEGMCM9070-501T 6 A common-mode choke (600 Ohm @ 100 MHz, 450 Ohm min, 2 x 8 mOhm) on both J1001 entry lines (attenuates common-mode noise by 2.9 dB at 65 kHz to 9.5 dB at 100 MHz; 0.30 W at 4.31 A worst)",
        link: "docs/POWER_SPEC.md#14-single-power-entry-for-the-kv260-and-adapter",
      },
      U1010: {
        desc: "TPS26631PWPR eFuse for KV260 12 V feed: 3.0 A limit set by R1043 (2.77-3.19 A across tolerance, capping BM20 contact current), OVP 14.4 V, UVLO 8.0 V",
        link: "docs/POWER_SPEC.md#14-single-power-entry-for-the-kv260-and-adapter",
      },
      Q1010: {
        desc: "DMT10H015LFG 100 V 13.5 mOhm reverse-blocking N-FET (source on VIN_J) providing -60 V reverse polarity protection with Q1011 (57.3 V peak VDS in ISO 7637-2 pulse 1; 0.137 W at 3.19 A)",
        link: "docs/POWER_SPEC.md#14-single-power-entry-for-the-kv260-and-adapter",
      },
      Q1011: {
        desc: "2N7002 N-FET (VDS >= 15 V, Ciss <= 50 pF) coupling U1010 DRV to Q1010 B_GATE for -60 V reverse polarity protection (SLVSE94G §8.3.5)",
        link: "docs/POWER_SPEC.md#14-single-power-entry-for-the-kv260-and-adapter",
      },
      D1004: {
        desc: "SS34 40 V 3 A SMA Schottky diode on +12V_KV to GND clamping inductive negative kick on the KV260 jumper when U1010 opens on fault (SLVSE94G §9.5.1)",
        link: "docs/POWER_SPEC.md#14-single-power-entry-for-the-kv260-and-adapter",
      },
      R1043: {
        desc: "6.04 kOhm 0603 1% ILIM resistor setting U1010 TPS26631 current limit to 3.0 A nominal (3.19 A worst case)",
        link: "docs/POWER_SPEC.md#14-single-power-entry-for-the-kv260-and-adapter",
      },
      C1223: {
        desc: "1 nF 2 kV X7R 1206 capacitor across the J1201 Ethernet shield-to-ground RC network (breaks DC/50 Hz earth loops to earthed switches)",
        link: "docs/AUDIT_Rev08.md",
      },
      R1218: {
        desc: "1 MOhm 0603 bleed resistor in parallel with C1223 on the J1201 Ethernet RJ45 shield",
        link: "docs/AUDIT_Rev08.md",
      },
    };

    const auditOv = REV08_AUDIT_OVERRIDES[ref] || null;
    if (auditOv) {
      description = auditOv.desc;
    } else if (manualInfo && meaningfulSpec && !specOverlapsManual) {
      description = `${manualInfo.desc}. Spec: ${specInfo.desc}`;
    } else if (manualInfo) {
      description = manualInfo.desc;
    } else if (meaningfulSpec) {
      description = specInfo.desc;
    } else if (cleanBomDesc) {
      description = cleanBomDesc;
    }
    description = description.replace(/\+3V0_RF/g, "+2V8_RF").replace(/\bTCAN330\b/g, "TCAN3403");
    const calloutText = manualInfo
      ? (typeof manualInfo.callout === "string" ? manualInfo.callout.replace(/\+3V0_RF/g, "+2V8_RF") : manualInfo.callout)
      : null;

    // Registration into KV260 model frame: k2m(x, y) = (107.247 - y, 198.004 - x)
    const mx = +(107.247 - y).toFixed(3);
    const my = +(198.004 - x).toFixed(3);
    const h = estimateHeightMm(ref, footprint, modelSource === "kicad-step");
    const mz0 = side === "top" ? 2.4 : 0.8 - h;
    const mz1 = side === "top" ? 2.4 + h : 0.8;

    components.push({
      id: ref,
      ref,
      value,
      footprint,
      side,
      x_mm: +x.toFixed(3),
      y_mm: +y.toFixed(3),
      rot_deg: +rot.toFixed(2),
      bbox_board_mm: [+bxmin.toFixed(3), +bymin.toFixed(3), +bxmax.toFixed(3), +bymax.toFixed(3)],
      model_pos_mm: [mx, my, +(side === "top" ? 2.4 : 0.8).toFixed(3)],
      bbox_world_mm: [
        +(107.247 - bymax).toFixed(3),
        +(198.004 - bxmax).toFixed(3),
        +(107.247 - bymin).toFixed(3),
        +(198.004 - bxmin).toFixed(3),
        +mz0.toFixed(3),
        +mz1.toFixed(3),
      ],
      local_size_mm: [+(lxmax - lxmin).toFixed(2), +(lymax - lymin).toFixed(2), +h.toFixed(2)],
      sheet,
      dnp,
      model_source: modelSource,
      lcsc: bomInfo ? bomInfo.lcsc : "",
      mpn: bomInfo ? bomInfo.mpn : "",
      manufacturer: bomInfo ? bomInfo.manufacturer : "",
      bom_desc: cleanBomDesc,
      description,
      callout: calloutText,
      manual_link: (auditOv && auditOv.link) || (manualInfo && manualInfo.manual_section) || sheetLink(sheet, ref),
      nets: [...compNets].sort(),
      pads,
    });
  }

  fs.mkdirSync(path.dirname(OUT_PATH), { recursive: true });
  const payload = {
    generated_at: new Date().toISOString(),
    pcb_file: "CSI2-KRIA-KV260_Rev01.kicad_pcb",
    registration: {
      note: "k2m(x, y) = (107.247 - y, 198.004 - x); board underside at Z = 0.8 mm, top at Z = 2.4 mm",
      translation_mm: [107.247, 198.004, 0.8],
      rotation_z_deg: -90,
      thickness_mm: 1.6,
    },
    board_outline: edgeCuts,
    counts: {
      total_components: components.length,
      described: components.filter((c) => c.description !== "no description yet").length,
      undescribed: components.filter((c) => c.description === "no description yet").length,
      kicad_step_models: components.filter((c) => c.model_source === "kicad-step").length,
      procedural_replacements: components.filter((c) => c.model_source === "procedural-replacement").length,
      unique_nets: netSet.size,
      kv260_parts: KV260_PARTS.length,
    },
    layer_stack: STACKUP,
    components,
    kv260_parts: KV260_PARTS,
    extra_parts: EXTRA_PARTS,
  };

  fs.writeFileSync(OUT_PATH, JSON.stringify(payload, null, 2));
  console.log(
    `Wrote ${OUT_PATH}: ${components.length} board components (${payload.counts.described} described, ${payload.counts.undescribed} "no description yet", ${payload.counts.procedural_replacements} procedural replacements), ${KV260_PARTS.length} KV260 parts, ${EXTRA_PARTS.length} thermal parts.`
  );
}

build();
