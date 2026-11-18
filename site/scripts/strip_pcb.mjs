#!/usr/bin/env node
/**
 * Copy CSI2-KRIA-KV260_Rev01.kicad_pcb to a temporary file with EasyEDA / _work
 * 3-D model references removed so KiCad GLB export embeds zero non-redistributable models.
 */
import fs from "node:fs";

const [, , inPcb, outPcb] = process.argv;
if (!inPcb || !outPcb) {
  console.error("Usage: node strip_pcb.mjs <in.kicad_pcb> <out.kicad_pcb>");
  process.exit(1);
}

const txt = fs.readFileSync(inPcb, "utf8");
let res = "";
let i = 0;
let stripped = 0;

while (i < txt.length) {
  const idx = txt.indexOf('(model "', i);
  if (idx < 0) {
    res += txt.slice(i);
    break;
  }
  const endQuote = txt.indexOf('"', idx + 8);
  const modelPath = txt.slice(idx + 8, endQuote);
  if (modelPath.includes("_work/mech/cache/models3d/") || (modelPath.endsWith(".wrl") && !modelPath.includes("mech/models3d/"))) {
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
    i = j;
    stripped++;
  } else {
    res += txt.slice(i, endQuote + 1);
    i = endQuote + 1;
  }
}

fs.writeFileSync(outPcb, res, "utf8");
console.log(`Stripped ${stripped} cached/VRML model blocks -> ${outPcb}`);
