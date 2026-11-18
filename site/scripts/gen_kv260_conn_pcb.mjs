#!/usr/bin/env node
/**
 * Generate a temporary minimal KiCad PCB containing only standard KiCad 10 STEP connector
 * models used to assemble our custom Apache-2.0 / CC-BY-SA-4.0 KV260 carrier 3-D model.
 */
import fs from "node:fs";

const outPcb = process.argv[2];
if (!outPcb) {
  console.error("Usage: node gen_kv260_conn_pcb.mjs <out.kicad_pcb>");
  process.exit(1);
}

const MODELS = [
  ["CONN_USBA", "${KICAD10_3DMODEL_DIR}/Connector_USB.3dshapes/USB_A_Molex_67643_Horizontal.step"],
  ["CONN_RJ45", "${KICAD10_3DMODEL_DIR}/Connector_RJ.3dshapes/RJ45_Amphenol_RJHSE538X.step"],
  ["CONN_HDMI", "${KICAD10_3DMODEL_DIR}/Connector_Video.3dshapes/HDMI_A_Molex_208658-1001_Horizontal.step"],
  ["CONN_DC", "${KICAD10_3DMODEL_DIR}/Connector_BarrelJack.3dshapes/BarrelJack_Horizontal.step"],
  ["CONN_UUSB", "${KICAD10_3DMODEL_DIR}/Connector_USB.3dshapes/USB_Micro-B_Molex_47346-0001.step"],
  ["CONN_USD", "${KICAD10_3DMODEL_DIR}/Connector_Card.3dshapes/microSD_HC_Hirose_DM3AT-SF-PEJM5.step"],
  ["CONN_PMOD", "${KICAD10_3DMODEL_DIR}/Connector_PinSocket_2.54mm.3dshapes/PinSocket_2x06_P2.54mm_Horizontal.step"],
  ["CONN_J9", "${KICAD10_3DMODEL_DIR}/Connector_PinHeader_2.54mm.3dshapes/PinHeader_2x10_P2.54mm_Vertical.step"],
  ["CONN_FAN", "${KICAD10_3DMODEL_DIR}/Connector_Molex.3dshapes/Molex_KK-254_AE-6410-04A_1x04_P2.54mm_Vertical.step"],
];

const fps = MODELS.map(([ref, step], i) => {
  const x = (i % 5) * 60 + 30;
  const y = Math.floor(i / 5) * 60 + 30;
  return `  (footprint "kv260_ref:${ref}" (layer "F.Cu") (at ${x} ${y})
    (property "Reference" "${ref}" (at 0 0) (layer "F.SilkS"))
    (model "${step}" (offset (xyz 0 0 0)) (scale (xyz 1 1 1)) (rotate (xyz 0 0 0)))
  )`;
}).join("\n");

const content = `(kicad_pcb (version 20241229) (generator "kv260_conn_gen")
  (general (thickness 1.6))
  (layers
    (0 "F.Cu" signal)
    (31 "B.Cu" signal)
    (44 "Edge.Cuts" user)
  )
  (gr_rect (start 0 0) (end 340 160) (stroke (width 0.1) (type solid)) (layer "Edge.Cuts"))
${fps}
)
`;

fs.writeFileSync(outPcb, content, "utf8");
console.log(`Generated ${MODELS.length}-connector temp PCB -> ${outPcb}`);
