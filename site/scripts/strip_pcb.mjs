#!/usr/bin/env node
/**
 * Copy CSI2-KRIA-KV260_Rev01.kicad_pcb to a temporary file where:
 *  - Any cached EasyEDA / _work model that has an official KiCad 10 STEP equivalent is
 *    rewritten to reference ${KICAD10_3DMODEL_DIR}/.../*.step (CC-BY-SA 4.0 + KiCad Exception),
 *  - Remaining EasyEDA / _work models without a KiCad STEP equivalent are stripped cleanly so
 *    kicad-cli embeds zero non-redistributable EasyEDA geometry.
 */
import fs from "node:fs";

const [, , inPcb, outPcb] = process.argv;
if (!inPcb || !outPcb) {
  console.error("Usage: node strip_pcb.mjs <in.kicad_pcb> <out.kicad_pcb>");
  process.exit(1);
}

const KICAD_STEP_SUBS = {
  "DC-IN-TH_PJ-102AH.wrl": {
    step: "${KICAD10_3DMODEL_DIR}/Connector_BarrelJack.3dshapes/BarrelJack_CUI_PJ-063AH_Horizontal.step",
    offset: "-0.75 -2.2 0",
    rotate: "0 0 0",
  },
  "RJ45-TH_HR911130C.wrl": {
    step: "${KICAD10_3DMODEL_DIR}/Connector_RJ.3dshapes/RJ45_Amphenol_RJHSE538X.step",
    offset: "-3.56 -1.5 0",
    rotate: "0 0 0",
  },
  "JST_SH_BM06B-SRSS-TB_toned.wrl": {
    step: "${KICAD10_3DMODEL_DIR}/Connector_JST.3dshapes/JST_SH_BM06B-SRSS-TB_1x06-1MP_P1.00mm_Vertical.step",
    offset: "0 0 0",
    rotate: "0 0 0",
  },
  "FPC-SMD_15P-P1.00_XUNPU_FPC-1.0FX-15PWCR-H20.wrl": {
    step: "${KICAD10_3DMODEL_DIR}/Connector_FFC-FPC.3dshapes/TE_1-84952-5_1x15-1MP_P1.0mm_Horizontal.step",
    offset: "0 0 0",
    rotate: "0 0 0",
  },
  "SOT-23-6_L2.9-W1.6-H1.5-LS2.8-P0.95.wrl": {
    step: "${KICAD10_3DMODEL_DIR}/Package_TO_SOT_SMD.3dshapes/SOT-23-6.step",
    offset: "0 0 0",
    rotate: "0 0 0",
  },
  "SC-70-6_L2.0-W1.3-H1.0-P0.65.wrl": {
    step: "${KICAD10_3DMODEL_DIR}/Package_TO_SOT_SMD.3dshapes/SOT-363_SC-70-6.step",
    offset: "0 0 0",
    rotate: "0 0 0",
  },
  "SOT343_L2.0-W1.3-H0.9-P1.30-LS2.1-BL.wrl": {
    step: "${KICAD10_3DMODEL_DIR}/Package_TO_SOT_SMD.3dshapes/SOT-343_SC-70-4.step",
    offset: "0 0 0",
    rotate: "0 0 0",
  },
  "QFN-24_L4.0-W4.0-P0.50-BL-EP2.8.wrl": {
    step: "${KICAD10_3DMODEL_DIR}/Package_DFN_QFN.3dshapes/QFN-24-1EP_4x4mm_P0.5mm_EP2.7x2.7mm.step",
    offset: "0 0 0",
    rotate: "0 0 0",
  },
  "WQFN-24_L4.0-W4.0-H0.8-P0.50.wrl": {
    step: "${KICAD10_3DMODEL_DIR}/Package_DFN_QFN.3dshapes/Texas_RTW_WQFN-24-1EP_4x4mm_P0.5mm_EP2.7x2.7mm.step",
    offset: "0 0 0",
    rotate: "0 0 0",
  },
  "QFN-20_L4.0-W4.0-H0.8-P0.50.wrl": {
    step: "${KICAD10_3DMODEL_DIR}/Package_DFN_QFN.3dshapes/QFN-20-1EP_4x4mm_P0.5mm_EP2.5x2.5mm.step",
    offset: "0 0 0",
    rotate: "0 0 0",
  },
  "QFN-14_L2.0-W2.0-H0.5-P0.45-BL-EP.wrl": {
    step: "${KICAD10_3DMODEL_DIR}/Package_DFN_QFN.3dshapes/UQFN-12-1EP_2x2mm_P0.4mm_EP1.1x1.1mm.step",
    offset: "0 0 0",
    rotate: "0 0 0",
  },
  "MSOP-10_L3.0-W3.0-H1.1-LS5.0-P0.50.wrl": {
    step: "${KICAD10_3DMODEL_DIR}/Package_SO.3dshapes/MSOP-10_3x3mm_P0.5mm.step",
    offset: "0 0 0",
    rotate: "0 0 0",
  },
  "F1812_L4.5-W3.2-H1.0.wrl": {
    step: "${KICAD10_3DMODEL_DIR}/Inductor_SMD.3dshapes/L_1812_4532Metric.step",
    offset: "0 0 0",
    rotate: "0 0 0",
  },
  "IND-SMD_SRP7028A-8R2M.wrl": {
    step: "${KICAD10_3DMODEL_DIR}/Inductor_SMD.3dshapes/L_Bourns_SRP6060FA.step",
    offset: "0 0 0",
    rotate: "0 0 0",
  },
  "OSC-SMD_8P-L7.0-W5.0-BL.wrl": {
    step: "${KICAD10_3DMODEL_DIR}/Oscillator.3dshapes/Oscillator_SMD_Abracon_ASV-4Pin_7.0x5.1mm.step",
    offset: "0 0 0",
    rotate: "0 0 0",
  },
  "OSC-SMD_4P-L2.0-W1.6-H0.8.wrl": {
    step: "${KICAD10_3DMODEL_DIR}/Oscillator.3dshapes/Oscillator_SMD_SeikoEpson_SG210-4Pin_2.5x2.0mm.step",
    offset: "0 0 0",
    rotate: "0 0 0",
  },
  "FILTER-SMD_1206-4P-L3.2-W1.6-H0.9-L.wrl": {
    step: "${KICAD10_3DMODEL_DIR}/Filter.3dshapes/Filter_Mini-Circuits_FV1206.step",
    offset: "0 0 0",
    rotate: "0 0 0",
  },
};

const txt = fs.readFileSync(inPcb, "utf8");
let res = "";
let i = 0;
let stripped = 0;
let substituted = 0;

while (i < txt.length) {
  const idx = txt.indexOf('(model "', i);
  if (idx < 0) {
    res += txt.slice(i);
    break;
  }
  const endQuote = txt.indexOf('"', idx + 8);
  const modelPath = txt.slice(idx + 8, endQuote);
  const baseName = modelPath.split("/").pop();
  const isCached =
    modelPath.includes("_work/mech/cache/models3d/") ||
    (modelPath.endsWith(".wrl") && !modelPath.includes("mech/models3d/"));

  if (isCached) {
    res += txt.slice(i, idx);
    let depth = 0;
    let j = idx;
    let inStr = false;
    while (j < txt.length) {
      const ch = txt[j];
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
    const sub = KICAD_STEP_SUBS[baseName];
    if (sub) {
      res += `(model "${sub.step}" (offset (xyz ${sub.offset})) (scale (xyz 1 1 1)) (rotate (xyz ${sub.rotate})))`;
      substituted++;
    } else {
      stripped++;
    }
    i = j;
  } else {
    res += txt.slice(i, endQuote + 1);
    i = endQuote + 1;
  }
}

fs.writeFileSync(outPcb, res, "utf8");
console.log(`Substituted ${substituted} KiCad official STEP models, stripped ${stripped} unmapped cached VRML blocks -> ${outPcb}`);
