#!/usr/bin/env node
/**
 * Build and optimize site/assets/board.glb, kv260.glb, and enclosure.glb in pure Node.js.
 * Zero Python, zero EasyEDA models, zero AMD XTP679 geometry redistributed.
 * Applies the owner's render calibration rules (KV260 green, ENIG copper, no burnt whites,
 * metallic shields with reflection-ready roughness).
 */

import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SITE_DIR = path.dirname(HERE);
const ROOT_DIR = path.dirname(SITE_DIR);
const ASSETS_DIR = path.join(SITE_DIR, "assets");
const RAW_BOARD_PATH = process.argv[2];

if (!RAW_BOARD_PATH || !fs.existsSync(RAW_BOARD_PATH)) {
  console.error("Usage: node site/scripts/build_assets.mjs <raw_board.glb>");
  process.exit(1);
}

// ---------------------------------------------------------------------------
// Low-level GLB Reader / Writer + Mesh Builder Helpers
// ---------------------------------------------------------------------------

function readGlb(filePath) {
  const buf = fs.readFileSync(filePath);
  if (buf.readUInt32LE(0) !== 0x46546c67) throw new Error("Not a valid GLB file");
  const jsonLen = buf.readUInt32LE(12);
  const gltf = JSON.parse(buf.subarray(20, 20 + jsonLen).toString("utf8"));
  let bin = Buffer.alloc(0);
  const binOff = 20 + jsonLen;
  if (binOff + 8 <= buf.length && buf.readUInt32LE(binOff + 4) === 0x004e4942) {
    const binLen = buf.readUInt32LE(binOff);
    bin = buf.subarray(binOff + 8, binOff + 8 + binLen);
  }
  return { gltf, bin };
}

function writeGlb(filePath, gltf, binChunks) {
  const rawBin = Buffer.concat(binChunks);
  const binPad = (4 - (rawBin.length % 4)) % 4;
  const bin = binPad ? Buffer.concat([rawBin, Buffer.alloc(binPad, 0)]) : rawBin;
  gltf.buffers = [{ byteLength: bin.length }];

  const jsonRaw = Buffer.from(JSON.stringify(gltf), "utf8");
  const jsonPad = (4 - (jsonRaw.length % 4)) % 4;
  const json = jsonPad ? Buffer.concat([jsonRaw, Buffer.alloc(jsonPad, 0x20)]) : jsonRaw;

  const header = Buffer.alloc(12);
  header.writeUInt32LE(0x46546c67, 0);
  header.writeUInt32LE(2, 4);
  header.writeUInt32LE(12 + 8 + json.length + 8 + bin.length, 8);

  const jsonHdr = Buffer.alloc(8);
  jsonHdr.writeUInt32LE(json.length, 0);
  jsonHdr.writeUInt32LE(0x4e4f534a, 4);

  const binHdr = Buffer.alloc(8);
  binHdr.writeUInt32LE(bin.length, 0);
  binHdr.writeUInt32LE(0x004e4942, 4);

  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, Buffer.concat([header, jsonHdr, json, binHdr, bin]));
}

class GlbBuilder {
  constructor() {
    this.materials = [];
    this.meshes = [];
    this.nodes = [];
    this.accessors = [];
    this.bufferViews = [];
    this.binParts = [];
    this.byteOffset = 0;
  }

  addMaterial(name, [r, g, b, a = 1.0], metallic = 0.0, roughness = 0.5, doubleSided = false) {
    const idx = this.materials.length;
    const mat = {
      name,
      pbrMetallicRoughness: {
        baseColorFactor: [r, g, b, a],
        metallicFactor: metallic,
        roughnessFactor: roughness,
      },
    };
    if (a < 0.999) mat.alphaMode = "BLEND";
    if (doubleSided) mat.doubleSided = true;
    this.materials.push(mat);
    return idx;
  }

  appendBufferView(buf, target) {
    const pad = (4 - (this.byteOffset % 4)) % 4;
    if (pad) {
      this.binParts.push(Buffer.alloc(pad, 0));
      this.byteOffset += pad;
    }
    const bvIdx = this.bufferViews.length;
    const bv = { buffer: 0, byteOffset: this.byteOffset, byteLength: buf.length };
    if (target) bv.target = target;
    this.bufferViews.push(bv);
    this.binParts.push(buf);
    this.byteOffset += buf.length;
    return bvIdx;
  }

  addPrimitive(positions, normals, indices, materialIdx) {
    const prims = this.addOptimizedPrimitives(positions, normals, indices, materialIdx, 0);
    return prims[0];
  }

  addOptimizedPrimitives(positions, normals, indices, materialIdx, weldQuant = 200000) {
    let wPos = positions;
    let wNorm = normals;
    let wIdx = indices;

    if (weldQuant > 0) {
      const welded = weldVertices(positions, normals, indices, weldQuant);
      wPos = welded.positions;
      wNorm = welded.normals;
      wIdx = welded.indices;
    }

    const totalTris = Math.floor(wIdx.length / 3);
    const totalVerts = wPos.length / 3;
    if (totalTris === 0 || totalVerts === 0) return [];

    // Fast path when vertices fit cleanly inside a single 16-bit indexed primitive
    if (totalVerts <= 65535) {
      return [this._writeRawPrimitive(wPos, wNorm, wIdx, materialIdx)];
    }

    // Split into <= 65,535-vertex chunks so every primitive uses compact 16-bit indices
    const batches = chunkTrianglesUint16(wPos, wNorm, wIdx, 65000);
    return batches.map((b) => this._writeRawPrimitive(b.positions, b.normals, b.indices, materialIdx));
  }

  _writeRawPrimitive(positions, normals, indices, materialIdx) {
    const vCount = positions.length / 3;
    let min = [Infinity, Infinity, Infinity];
    let max = [-Infinity, -Infinity, -Infinity];
    for (let i = 0; i < vCount; i++) {
      for (let k = 0; k < 3; k++) {
        const v = positions[i * 3 + k];
        if (v < min[k]) min[k] = v;
        if (v > max[k]) max[k] = v;
      }
    }

    const posBuf = Buffer.from(positions.buffer, positions.byteOffset, positions.byteLength);
    const normBuf = Buffer.from(normals.buffer, normals.byteOffset, normals.byteLength);
    const posBv = this.appendBufferView(posBuf, 34962);
    const normBv = this.appendBufferView(normBuf, 34962);

    const posAcc = this.accessors.length;
    this.accessors.push({ bufferView: posBv, componentType: 5126, count: vCount, type: "VEC3", min, max });
    const normAcc = this.accessors.length;
    this.accessors.push({ bufferView: normBv, componentType: 5126, count: vCount, type: "VEC3" });

    let idxTyped = indices;
    let idxComp = 5125; // UNSIGNED_INT
    if (vCount <= 65535 && !(indices instanceof Uint16Array)) {
      idxTyped = new Uint16Array(indices);
      idxComp = 5123;
    } else if (indices instanceof Uint16Array) {
      idxComp = 5123;
    }
    const idxBuf = Buffer.from(idxTyped.buffer, idxTyped.byteOffset, idxTyped.byteLength);
    const idxBv = this.appendBufferView(idxBuf, 34963);
    const idxAcc = this.accessors.length;
    this.accessors.push({ bufferView: idxBv, componentType: idxComp, count: idxTyped.length, type: "SCALAR" });

    return { attributes: { POSITION: posAcc, NORMAL: normAcc }, indices: idxAcc, material: materialIdx, mode: 4 };
  }

  addMesh(name, primitives) {
    const idx = this.meshes.length;
    this.meshes.push({ name, primitives });
    return idx;
  }

  addNode(nodeObj) {
    const idx = this.nodes.length;
    this.nodes.push(nodeObj);
    return idx;
  }

  save(filePath, rootNodes) {
    const gltf = {
      asset: { version: "2.0", generator: "kv260-ias2rf-site-builder" },
      scene: 0,
      scenes: [{ nodes: rootNodes }],
      nodes: this.nodes,
      meshes: this.meshes,
      materials: this.materials,
      accessors: this.accessors,
      bufferViews: this.bufferViews,
      buffers: [],
    };
    writeGlb(filePath, gltf, this.binParts);
  }
}

// Geometry primitive builders in mm converted to m
function createBoxGeom(x0, x1, y0, y1, z0, z1) {
  // Coordinates here are in glTF Y-up metres! Wait: pass (x0..x1, y0_up..y1_up, z0..z1) directly in m.
  const pts = [
    // +Z
    [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1],
    // -Z
    [x1, y0, z0], [x0, y0, z0], [x0, y1, z0], [x1, y1, z0],
    // +Y (top)
    [x0, y1, z1], [x1, y1, z1], [x1, y1, z0], [x0, y1, z0],
    // -Y (bottom)
    [x0, y0, z0], [x1, y0, z0], [x1, y0, z1], [x0, y0, z1],
    // +X
    [x1, y0, z1], [x1, y0, z0], [x1, y1, z0], [x1, y1, z1],
    // -X
    [x0, y0, z0], [x0, y0, z1], [x0, y1, z1], [x0, y1, z0],
  ];
  const nrms = [
    [0, 0, 1], [0, 0, -1], [0, 1, 0], [0, -1, 0], [1, 0, 0], [-1, 0, 0],
  ];
  const positions = new Float32Array(24 * 3);
  const normals = new Float32Array(24 * 3);
  const indices = new Uint16Array(36);
  for (let f = 0; f < 6; f++) {
    for (let v = 0; v < 4; v++) {
      const vi = f * 4 + v;
      positions.set(pts[vi], vi * 3);
      normals.set(nrms[f], vi * 3);
    }
    const base = f * 4;
    indices.set([base, base + 1, base + 2, base, base + 2, base + 3], f * 6);
  }
  return { positions, normals, indices };
}

function createCylY(cx, y0, y1, cz, radius, seg = 24) {
  const pos = [];
  const norm = [];
  const idx = [];
  // Side ring
  const sideStart = 0;
  for (let i = 0; i <= seg; i++) {
    const a = (i / seg) * Math.PI * 2;
    const ca = Math.cos(a), sa = Math.sin(a);
    pos.push(cx + radius * ca, y0, cz + radius * sa);
    norm.push(ca, 0, sa);
    pos.push(cx + radius * ca, y1, cz + radius * sa);
    norm.push(ca, 0, sa);
  }
  for (let i = 0; i < seg; i++) {
    const a = sideStart + i * 2;
    idx.push(a, a + 2, a + 3, a, a + 3, a + 1);
  }
  // Top & bottom caps
  const topC = pos.length / 3;
  pos.push(cx, y1, cz);
  norm.push(0, 1, 0);
  for (let i = 0; i <= seg; i++) {
    const a = (i / seg) * Math.PI * 2;
    pos.push(cx + radius * Math.cos(a), y1, cz + radius * Math.sin(a));
    norm.push(0, 1, 0);
  }
  for (let i = 0; i < seg; i++) idx.push(topC, topC + 1 + i, topC + 2 + i);

  const botC = pos.length / 3;
  pos.push(cx, y0, cz);
  norm.push(0, -1, 0);
  for (let i = 0; i <= seg; i++) {
    const a = (i / seg) * Math.PI * 2;
    pos.push(cx + radius * Math.cos(a), y0, cz + radius * Math.sin(a));
    norm.push(0, -1, 0);
  }
  for (let i = 0; i < seg; i++) idx.push(botC, botC + 2 + i, botC + 1 + i);

  return { positions: new Float32Array(pos), normals: new Float32Array(norm), indices: new Uint16Array(idx) };
}

function createCylX(x0, x1, cy, cz, radius, seg = 24) {
  const { positions, normals, indices } = createCylY(0, x0, x1, 0, radius, seg);
  // Rotate Y->X: (x, y, z) -> (y, z + cy? wait: create box mapping (y, -x, z))
  const outP = new Float32Array(positions.length);
  const outN = new Float32Array(normals.length);
  for (let i = 0; i < positions.length; i += 3) {
    outP[i] = positions[i + 1];
    outP[i + 1] = cy + positions[i + 2];
    outP[i + 2] = cz + positions[i];
    outN[i] = normals[i + 1];
    outN[i + 1] = normals[i + 2];
    outN[i + 2] = normals[i];
  }
  return { positions: outP, normals: outN, indices };
}

function weldVertices(positions, normals, indices, qScale) {
  const map = new Map();
  const outPos = [];
  const outNorm = [];
  const outIdx = [];
  const remap = new Int32Array(positions.length / 3);
  remap.fill(-1);

  const vertUsed = new Uint8Array(positions.length / 3);
  for (let i = 0; i < indices.length; i++) vertUsed[indices[i]] = 1;

  for (let vi = 0; vi < remap.length; vi++) {
    if (!vertUsed[vi]) continue;
    const o = vi * 3;
    const x = positions[o], y = positions[o + 1], z = positions[o + 2];
    const nx = normals[o], ny = normals[o + 1], nz = normals[o + 2];
    const key =
      `${Math.round(x * qScale)},${Math.round(y * qScale)},${Math.round(z * qScale)}|` +
      `${Math.round(nx * 32)},${Math.round(ny * 32)},${Math.round(nz * 32)}`;
    let ni = map.get(key);
    if (ni === undefined) {
      ni = outPos.length / 3;
      map.set(key, ni);
      outPos.push(x, y, z);
      outNorm.push(nx, ny, nz);
    }
    remap[vi] = ni;
  }

  for (let t = 0; t + 2 < indices.length; t += 3) {
    const a = remap[indices[t]];
    const b = remap[indices[t + 1]];
    const c = remap[indices[t + 2]];
    if (a >= 0 && b >= 0 && c >= 0 && a !== b && b !== c && a !== c) {
      outIdx.push(a, b, c);
    }
  }

  const vCount = outPos.length / 3;
  return {
    positions: new Float32Array(outPos),
    normals: new Float32Array(outNorm),
    indices: vCount <= 65535 ? new Uint16Array(outIdx) : new Uint32Array(outIdx),
  };
}

function chunkTrianglesUint16(positions, normals, indices, maxVerts = 65000) {
  const chunks = [];
  const totalTris = Math.floor(indices.length / 3);
  let tStart = 0;
  while (tStart < totalTris) {
    const vMap = new Map();
    const cPos = [];
    const cNorm = [];
    const cIdx = [];
    let t = tStart;
    for (; t < totalTris; t++) {
      const i0 = indices[t * 3];
      const i1 = indices[t * 3 + 1];
      const i2 = indices[t * 3 + 2];
      let needed = 0;
      if (!vMap.has(i0)) needed++;
      if (i1 !== i0 && !vMap.has(i1)) needed++;
      if (i2 !== i0 && i2 !== i1 && !vMap.has(i2)) needed++;
      if (cPos.length / 3 + needed > maxVerts && cIdx.length > 0) break;

      for (const orig of [i0, i1, i2]) {
        let local = vMap.get(orig);
        if (local === undefined) {
          local = cPos.length / 3;
          vMap.set(orig, local);
          const o = orig * 3;
          cPos.push(positions[o], positions[o + 1], positions[o + 2]);
          cNorm.push(normals[o], normals[o + 1], normals[o + 2]);
        }
        cIdx.push(local);
      }
    }
    chunks.push({
      positions: new Float32Array(cPos),
      normals: new Float32Array(cNorm),
      indices: new Uint16Array(cIdx),
    });
    tStart = t;
  }
  return chunks;
}

function cullBoardTriangles(positions, indices, boardRole) {
  if (boardRole !== "copper" && boardRole !== "pad" && boardRole !== "via") {
    return indices;
  }
  const kept = [];
  for (let t = 0; t + 2 < indices.length; t += 3) {
    const i0 = indices[t], i1 = indices[t + 1], i2 = indices[t + 2];
    const a = i0 * 3, b = i1 * 3, c = i2 * 3;
    const ax = positions[b] - positions[a], ay = positions[b + 1] - positions[a + 1], az = positions[b + 2] - positions[a + 2];
    const bx = positions[c] - positions[a], by = positions[c + 1] - positions[a + 1], bz = positions[c + 2] - positions[a + 2];
    const nx = ay * bz - az * by;
    const ny = az * bx - ax * bz;
    const nz = ax * by - ay * bx;
    const len = Math.hypot(nx, ny, nz);
    if (len < 1e-12) continue;
    const unitNy = ny / len;
    const ym = (positions[a + 1] + positions[b + 1] + positions[c + 1]) / 3;
    const isOuterFlat = (ym > 0.00075 && unitNy > 0.25) || (ym <= 0.00075 && unitNy < -0.25);
    if (isOuterFlat) {
      kept.push(i0, i1, i2);
    } else if (boardRole === "pad") {
      const yLo = Math.min(positions[a + 1], positions[b + 1], positions[c + 1]);
      const yHi = Math.max(positions[a + 1], positions[b + 1], positions[c + 1]);
      if (yLo < 0.00035 && yHi > 0.0011) kept.push(i0, i1, i2);
    }
  }
  return kept.length > 0 && positions.length / 3 <= 65535 ? new Uint16Array(kept) : new Uint32Array(kept);
}

function mergeGeoms(geoms) {
  let totalV = 0, totalI = 0;
  for (const g of geoms) {
    totalV += g.positions.length / 3;
    totalI += g.indices.length;
  }
  const pos = new Float32Array(totalV * 3);
  const norm = new Float32Array(totalV * 3);
  const idx = totalV > 65535 ? new Uint32Array(totalI) : new Uint16Array(totalI);
  let vOff = 0, iOff = 0;
  for (const g of geoms) {
    pos.set(g.positions, vOff * 3);
    norm.set(g.normals, vOff * 3);
    for (let k = 0; k < g.indices.length; k++) idx[iOff + k] = g.indices[k] + vOff;
    vOff += g.positions.length / 3;
    iOff += g.indices.length;
  }
  return { positions: pos, normals: norm, indices: idx };
}

function kvBoxMm(x0, x1, y0, y1, z0, z1) {
  // KV260 model frame mm (X right, Y forward, Z up) -> glTF Y-up metres (X, Z, -Y)
  const s = 0.001;
  return createBoxGeom(x0 * s, x1 * s, z0 * s, z1 * s, -y1 * s, -y0 * s);
}

// ---------------------------------------------------------------------------
// 1. Optimize & calibrate board.glb + generate procedural replacements
// ---------------------------------------------------------------------------

function lum(c) {
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
}

function calibrateMaterial(mat, isBoardMat) {
  const m = JSON.parse(JSON.stringify(mat));
  const pbr = (m.pbrMetallicRoughness ||= {});
  const c = [...(pbr.baseColorFactor || [0.5, 0.5, 0.5, 1.0])];
  const r = c[0], g = c[1], bl = c[2], a = c[3] ?? 1.0;
  const L = lum(c);
  const sat = Math.max(r, g, bl) - Math.min(r, g, bl);

  const isMask = g > 2.0 * r && g > 1.3 * bl && L < 0.25 && (isBoardMat || a < 0.99);
  const isSilk = isBoardMat && r > 0.9 && g > 0.9 && bl > 0.9;
  const isCopper = isBoardMat && Math.abs(r - 0.7) < 0.06 && Math.abs(g - 0.61) < 0.06 && bl < 0.06;
  const isFR4 = isBoardMat && Math.abs(r - 0.42) < 0.05 && Math.abs(g - 0.45) < 0.05;

  if (isMask) {
    pbr.baseColorFactor = [0.006, 0.088, 0.022, 0.87];
    pbr.metallicFactor = 0.0;
    pbr.roughnessFactor = 0.56;
    m.alphaMode = "BLEND";
    m.doubleSided = true;
    m.name = (m.name || "mask") + "_kv_green";
  } else if (isSilk) {
    pbr.baseColorFactor = [0.90, 0.90, 0.88, 1.0];
    pbr.metallicFactor = 0.0;
    pbr.roughnessFactor = 0.60;
    delete m.alphaMode;
    m.doubleSided = true;
  } else if (isCopper) {
    pbr.baseColorFactor = [0.88, 0.70, 0.40, 1.0];
    pbr.metallicFactor = 0.85;
    pbr.roughnessFactor = 0.30;
  } else if (isFR4) {
    pbr.baseColorFactor = [0.18, 0.19, 0.11, 1.0];
    pbr.metallicFactor = 0.0;
    pbr.roughnessFactor = 0.75;
    delete m.alphaMode;
  } else {
    // Component materials: no pure white burnouts, realistic metals
    const goldish = r > 0.45 && r > g && g > bl && bl < 0.45 * r && sat > 0.20;
    if (goldish && bl > 0.12 * r) {
      pbr.baseColorFactor = [0.86, 0.68, 0.36, 1.0];
      pbr.metallicFactor = 0.95;
      pbr.roughnessFactor = 0.32;
    } else if (sat < 0.15 && L > 0.70) {
      // Pure white EasyEDA/KiCad ceramics or ivory connectors -> toned dark ivory
      pbr.baseColorFactor = [0.24, 0.22, 0.18, a];
      pbr.metallicFactor = 0.0;
      pbr.roughnessFactor = 0.50;
    } else if (sat < 0.12 && L > 0.34 && L <= 0.70) {
      // Tin / nickel / steel shells
      const v = Math.max(0.45, Math.min(0.68, L * 1.1));
      pbr.baseColorFactor = [v, v, v * 0.98, 1.0];
      pbr.metallicFactor = 0.92;
      pbr.roughnessFactor = 0.28;
    } else {
      const k = Math.min(1.0, 0.78 / Math.max(r, g, bl, 1e-4));
      pbr.baseColorFactor = [r * k, g * k, bl * k, a];
      pbr.metallicFactor = 0.0;
      pbr.roughnessFactor = L < 0.08 ? 0.55 : 0.48;
    }
  }
  return { mat: m, kind: isMask ? "mask" : isSilk ? "silk" : "other" };
}

function readAccessorArray(gltf, bin, accIdx) {
  const acc = gltf.accessors[accIdx];
  const bv = gltf.bufferViews[acc.bufferView];
  const offset = (bv.byteOffset || 0) + (acc.byteOffset || 0);
  const comps = { SCALAR: 1, VEC2: 2, VEC3: 3, VEC4: 4 }[acc.type];
  const stride = bv.byteStride || 0;
  const count = acc.count;

  const makeView = (TypedArr, elemSize) => {
    if (!stride || stride === comps * elemSize) {
      return new TypedArr(bin.buffer, bin.byteOffset + offset, count * comps);
    }
    const out = new TypedArr(count * comps);
    for (let i = 0; i < count; i++) {
      const base = offset + i * stride;
      for (let c = 0; c < comps; c++) {
        if (acc.componentType === 5126) out[i * comps + c] = bin.readFloatLE(base + c * 4);
        else if (acc.componentType === 5123) out[i * comps + c] = bin.readUInt16LE(base + c * 2);
        else if (acc.componentType === 5125) out[i * comps + c] = bin.readUInt32LE(base + c * 4);
      }
    }
    return out;
  };

  if (acc.componentType === 5126) return makeView(Float32Array, 4);
  if (acc.componentType === 5123) return makeView(Uint16Array, 2);
  if (acc.componentType === 5125) return makeView(Uint32Array, 4);
  if (acc.componentType === 5121) return makeView(Uint8Array, 1);
  throw new Error(`Unsupported accessor componentType ${acc.componentType}`);
}

function addProceduralComponentMesh(gb, comp, mats) {
  const s = 0.001;
  const [w, l, h] = comp.local_size_mm;
  const hw = Math.max(w * 0.42, 0.4) * s;
  const hl = Math.max(l * 0.42, 0.4) * s;
  const sign = comp.side === "bottom" ? -1 : 1;
  const yBase = 0;
  const yTop = sign * Math.max(h, 0.5) * s;
  const y0 = Math.min(yBase, yTop);
  const y1 = Math.max(yBase, yTop);

  const prims = [];
  if (comp.ref === "J1201") {
    // HR911130C RJ45: outer nickel shield + recessed black opening
    const shell = createBoxGeom(-hw, hw, y0, y1, -hl, hl);
    const port = createBoxGeom(-hw * 0.72, hw * 0.72, y0 + 0.0015, y1 - 0.0015, -hl - 0.0002, -hl + 0.003);
    prims.push(gb.addPrimitive(shell.positions, shell.normals, shell.indices, mats.nickel));
    prims.push(gb.addPrimitive(port.positions, port.normals, port.indices, mats.darkBody));
  } else if (comp.ref === "J1001") {
    // PJ-102AH 12V DC jack: matte black housing + barrel bore + brass center pin
    const body = createBoxGeom(-hw, hw, y0, y1, -hl, hl);
    const pin = createCylX(-hw * 0.85, 0, (y0 + y1) * 0.55, 0, 0.001, 16);
    prims.push(gb.addPrimitive(body.positions, body.normals, body.indices, mats.darkBody));
    prims.push(gb.addPrimitive(pin.positions, pin.normals, pin.indices, mats.gold));
  } else if (comp.ref === "J1501") {
    // HRO TYPE-C-31-E-17 vertical USB-C: stainless outer shell + dark tongue + gold contacts
    const shell = createBoxGeom(-0.00445, 0.00445, 0, 0.0093, -0.0016, 0.0016);
    const inner = createBoxGeom(-0.0032, 0.0032, 0.002, 0.0086, -0.0004, 0.0004);
    prims.push(gb.addPrimitive(shell.positions, shell.normals, shell.indices, mats.nickel));
    prims.push(gb.addPrimitive(inner.positions, inner.normals, inner.indices, mats.darkBody));
  } else if (comp.ref === "J1502" || comp.ref === "J1503") {
    // FPC / JST connector: ivory plastic housing + dark flip latch/slot + metallic solder tabs
    const body = createBoxGeom(-hw * 0.9, hw * 0.9, y0, y1, -hl * 0.85, hl * 0.85);
    const tabs = createBoxGeom(-hw, hw, y0, y0 + sign * 0.0005, -hl * 0.35, hl * 0.35);
    prims.push(gb.addPrimitive(body.positions, body.normals, body.indices, mats.ivory));
    prims.push(gb.addPrimitive(tabs.positions, tabs.normals, tabs.indices, mats.gold));
  } else if (/^J10[123]$/.test(comp.ref)) {
    // Hirose BM20B 34-pin low-profile B2B connector
    const body = createBoxGeom(-0.0046, 0.0046, y0, y1, -0.0012, 0.0012);
    const contacts = createBoxGeom(-0.0036, 0.0036, y0, y1 * 0.95, -0.00135, 0.00135);
    prims.push(gb.addPrimitive(body.positions, body.normals, body.indices, mats.darkBody));
    prims.push(gb.addPrimitive(contacts.positions, contacts.normals, contacts.indices, mats.gold));
  } else if (comp.ref === "Y401" || comp.ref === "Y1301") {
    // Si549 XO / TCXO: dark substrate + nickel lid
    const sub = createBoxGeom(-hw * 0.9, hw * 0.9, y0, (y0 + y1) * 0.45, -hl * 0.9, hl * 0.9);
    const lid = createBoxGeom(-hw * 0.86, hw * 0.86, (y0 + y1) * 0.45, y1, -hl * 0.86, hl * 0.86);
    prims.push(gb.addPrimitive(sub.positions, sub.normals, sub.indices, mats.darkBody));
    prims.push(gb.addPrimitive(lid.positions, lid.normals, lid.indices, mats.nickel));
  } else if (/^L10/.test(comp.ref)) {
    // Bourns SRP7028A shielded inductor
    const body = createBoxGeom(-0.00365, 0.00365, 0, 0.0028, -0.0033, 0.0033);
    const pads = createBoxGeom(-0.00385, 0.00385, 0, 0.0008, -0.0016, 0.0016);
    prims.push(gb.addPrimitive(body.positions, body.normals, body.indices, mats.ferrite));
    prims.push(gb.addPrimitive(pads.positions, pads.normals, pads.indices, mats.nickel));
  } else if (/^(T701|T801|T802)$/.test(comp.ref)) {
    // Mini-Circuits CD542 transformer
    const base = createBoxGeom(-0.0035, 0.0035, 0, 0.00284, -0.0028, 0.0028);
    const leads = createBoxGeom(-0.00395, 0.00395, 0, 0.0005, -0.0026, 0.0026);
    prims.push(gb.addPrimitive(base.positions, base.normals, base.indices, mats.ceramic));
    prims.push(gb.addPrimitive(leads.positions, leads.normals, leads.indices, mats.gold));
  } else {
    // QFN / SOT / Filter / Balun / Fuse replacement with pin-1 indicator
    const body = createBoxGeom(-hw * 0.85, hw * 0.85, y0, y1, -hl * 0.85, hl * 0.85);
    const leads = createBoxGeom(-hw * 0.95, hw * 0.95, y0, y0 + sign * 0.00035, -hl * 0.72, hl * 0.72);
    const matIdx = comp.ref.startsWith("FL") ? mats.ceramic : mats.darkBody;
    prims.push(gb.addPrimitive(body.positions, body.normals, body.indices, matIdx));
    prims.push(gb.addPrimitive(leads.positions, leads.normals, leads.indices, mats.nickel));
  }
  return gb.addMesh(`proc_${comp.ref}`, prims);
}

function buildBoardGlb(compJson) {
  const { gltf, bin } = readGlb(RAW_BOARD_PATH);
  const gb = new GlbBuilder();

  const srcNodes = gltf.nodes || [];
  const srcMeshes = gltf.meshes || [];
  const srcMats = gltf.materials || [];
  const rootIdx = (gltf.scenes && gltf.scenes[0] && gltf.scenes[0].nodes && gltf.scenes[0].nodes[0]) ?? 0;

  const boardRoleRe = /_(copper|pad|via|silkscreen|soldermask|PCB)$/;
  const matRole = new Map();
  for (let mi = 0; mi < srcMeshes.length; mi++) {
    const mName = srcMeshes[mi].name || "";
    const rm = mName.match(boardRoleRe);
    if (rm) {
      for (const p of srcMeshes[mi].primitives) {
        if (p.material !== undefined) matRole.set(p.material, rm[1]);
      }
    }
  }

  for (let i = 0; i < srcMats.length; i++) {
    const role = matRole.get(i);
    if (role === "soldermask") {
      gb.materials.push({
        name: "board_soldermask_kv_green",
        alphaMode: "BLEND",
        doubleSided: true,
        pbrMetallicRoughness: { baseColorFactor: [0.006, 0.088, 0.022, 0.87], metallicFactor: 0.0, roughnessFactor: 0.56 },
      });
    } else if (role === "silkscreen") {
      gb.materials.push({
        name: "board_silkscreen",
        doubleSided: true,
        pbrMetallicRoughness: { baseColorFactor: [0.90, 0.90, 0.88, 1.0], metallicFactor: 0.0, roughnessFactor: 0.60 },
      });
    } else if (role === "copper" || role === "pad" || role === "via") {
      gb.materials.push({
        name: `board_${role}_enig`,
        pbrMetallicRoughness: { baseColorFactor: [0.88, 0.70, 0.40, 1.0], metallicFactor: 0.86, roughnessFactor: 0.30 },
      });
    } else if (role === "PCB") {
      gb.materials.push({
        name: "board_fr4_core",
        pbrMetallicRoughness: { baseColorFactor: [0.18, 0.19, 0.11, 1.0], metallicFactor: 0.0, roughnessFactor: 0.75 },
      });
    } else {
      const { mat } = calibrateMaterial(srcMats[i], false);
      gb.materials.push(mat);
    }
  }

  // Also add materials for procedural replacements
  const procMats = {
    nickel: gb.addMaterial("proc_nickel", [0.60, 0.60, 0.59, 1.0], 0.92, 0.25),
    gold: gb.addMaterial("proc_gold", [0.86, 0.68, 0.36, 1.0], 0.98, 0.30),
    darkBody: gb.addMaterial("proc_epoxy", [0.025, 0.026, 0.030, 1.0], 0.0, 0.55),
    ivory: gb.addMaterial("proc_ivory", [0.22, 0.20, 0.16, 1.0], 0.0, 0.50),
    ceramic: gb.addMaterial("proc_ceramic", [0.38, 0.36, 0.32, 1.0], 0.0, 0.45),
    ferrite: gb.addMaterial("proc_ferrite", [0.06, 0.06, 0.065, 1.0], 0.15, 0.62),
  };

  let boardYMax = 0.00154;
  let boardYMin = 0.0;

  // Optimize & merge primitives by material inside each source mesh, plus deduplicate component meshes
  const dedupCache = new Map();
  const rebuiltMeshMap = new Map();

  function buildMergedMesh(srcMeshIdx) {
    if (rebuiltMeshMap.has(srcMeshIdx)) return rebuiltMeshMap.get(srcMeshIdx);
    const srcM = srcMeshes[srcMeshIdx];
    const roleMatch = (srcM.name || "").match(boardRoleRe);
    const boardRole = roleMatch ? roleMatch[1] : null;
    const isBoard = !!boardRole;
    const byMat = new Map();

    for (const p of srcM.primitives) {
      const mIdx = p.material ?? 0;
      const pos = readAccessorArray(gltf, bin, p.attributes.POSITION);
      const norm = p.attributes.NORMAL !== undefined ? readAccessorArray(gltf, bin, p.attributes.NORMAL) : null;
      let idx;
      if (p.indices !== undefined) {
        idx = readAccessorArray(gltf, bin, p.indices);
      } else {
        idx = new Uint32Array(pos.length / 3);
        for (let k = 0; k < idx.length; k++) idx[k] = k;
      }

      let nArr = norm;
      if (!nArr) {
        nArr = new Float32Array(pos.length);
        for (let k = 0; k < idx.length; k += 3) {
          const i0 = idx[k] * 3, i1 = idx[k + 1] * 3, i2 = idx[k + 2] * 3;
          const ax = pos[i1] - pos[i0], ay = pos[i1 + 1] - pos[i0 + 1], az = pos[i1 + 2] - pos[i0 + 2];
          const bx = pos[i2] - pos[i0], by = pos[i2 + 1] - pos[i0 + 1], bz = pos[i2 + 2] - pos[i0 + 2];
          let nx = ay * bz - az * by, ny = az * bx - ax * bz, nz = ax * by - ay * bx;
          const nl = Math.hypot(nx, ny, nz) || 1;
          nx /= nl; ny /= nl; nz /= nl;
          for (const vi of [i0, i1, i2]) {
            nArr[vi] = nx; nArr[vi + 1] = ny; nArr[vi + 2] = nz;
          }
        }
      }

      // Copy & apply Z-lift (glTF Y-lift) on soldermask / silkscreen of the board
      const posCopy = new Float32Array(pos);
      if (isBoard) {
        idx = cullBoardTriangles(posCopy, idx, boardRole);
        if (boardRole === "soldermask" || boardRole === "silkscreen") {
          const lift = boardRole === "silkscreen" ? 0.00006 : 0.00004;
          for (let k = 1; k < posCopy.length; k += 3) {
            posCopy[k] += posCopy[k] > 0.00075 ? lift : -lift;
          }
        } else if (boardRole === "PCB") {
          let lo = Infinity, hi = -Infinity;
          for (let k = 1; k < posCopy.length; k += 3) {
            if (posCopy[k] < lo) lo = posCopy[k];
            if (posCopy[k] > hi) hi = posCopy[k];
          }
          if (isFinite(lo)) boardYMin = lo;
          if (isFinite(hi)) boardYMax = hi;
        }
      }

      if (idx.length === 0) continue;
      if (!byMat.has(mIdx)) byMat.set(mIdx, []);
      byMat.get(mIdx).push({ positions: posCopy, normals: nArr, indices: idx });
    }

    const mergedList = [];
    const h = crypto.createHash("sha1");
    for (const [mIdx, list] of [...byMat.entries()].sort((a, b) => a[0] - b[0])) {
      const m = mergeGeoms(list);
      mergedList.push({ mIdx, ...m });
      if (!isBoard) {
        h.update(String(mIdx) + ":");
        h.update(Buffer.from(m.positions.buffer, m.positions.byteOffset, m.positions.byteLength));
        h.update(Buffer.from(m.indices.buffer, m.indices.byteOffset, m.indices.byteLength));
      }
    }

    if (!isBoard) {
      const digest = h.digest("hex");
      if (dedupCache.has(digest)) {
        const cached = dedupCache.get(digest);
        rebuiltMeshMap.set(srcMeshIdx, cached);
        return cached;
      }
      const prims = mergedList.flatMap((g) => gb.addOptimizedPrimitives(g.positions, g.normals, g.indices, g.mIdx, 200000));
      const newIdx = gb.addMesh(srcM.name || `mesh_${srcMeshIdx}`, prims);
      dedupCache.set(digest, newIdx);
      rebuiltMeshMap.set(srcMeshIdx, newIdx);
      return newIdx;
    }

    const prims = mergedList.flatMap((g) => gb.addOptimizedPrimitives(g.positions, g.normals, g.indices, g.mIdx, 200000));
    const newIdx = gb.addMesh(`PCB_${boardRole}`, prims);
    rebuiltMeshMap.set(srcMeshIdx, newIdx);
    return newIdx;
  }

  // Rebuild node tree preserving ref designator names
  const existingRefs = new Set();
  function cloneNode(srcIdx) {
    const sn = srcNodes[srcIdx];
    const nd = {};
    if (sn.name) nd.name = sn.name;
    if (sn.translation) nd.translation = sn.translation;
    if (sn.rotation) nd.rotation = sn.rotation;
    if (sn.scale) nd.scale = sn.scale;
    if (sn.matrix) nd.matrix = sn.matrix;
    if (sn.mesh !== undefined) {
      const srcMName = (srcMeshes[sn.mesh] && srcMeshes[sn.mesh].name) || "";
      const rm = srcMName.match(boardRoleRe);
      if (rm) nd.name = `PCB_LAYER_${rm[1].toUpperCase()}`;
      nd.mesh = buildMergedMesh(sn.mesh);
    }
    if (sn.children && sn.children.length) {
      nd.children = sn.children.map((c) => {
        const cn = srcNodes[c];
        if (cn.name) existingRefs.add(cn.name);
        return cloneNode(c);
      });
    }
    return gb.addNode(nd);
  }

  const outRootIdx = cloneNode(rootIdx);

  // Attach procedural replacements for parts stripped from EasyEDA / VRML-only footprints
  const rootChildren = gb.nodes[outRootIdx].children || [];
  let addedProc = 0;
  for (const comp of compJson.components) {
    if (comp.model_source === "none") continue;
    // If KiCad didn't export a mesh child under existingRefs for this ref (because EasyEDA was stripped
    // or VRML wasn't substituted), add a clean procedural 3-D model at its exact KiCad placement!
    let hasMesh = false;
    if (existingRefs.has(comp.ref)) {
      const n = gb.nodes.find((x) => x.name === comp.ref);
      const stack = n ? [n] : [];
      while (stack.length) {
        const cur = stack.pop();
        if (cur.mesh !== undefined) { hasMesh = true; break; }
        for (const ci of cur.children || []) stack.push(gb.nodes[ci]);
      }
    }
    if (!hasMesh || comp.model_source === "procedural-replacement") {
      const meshIdx = addProceduralComponentMesh(gb, comp, procMats);
      const radY = (-comp.rot_deg * Math.PI) / 180;
      const qy = Math.sin(radY / 2);
      const qw = Math.cos(radY / 2);
      const yMount = comp.side === "bottom" ? boardYMin : boardYMax;
      const nodeIdx = gb.addNode({
        name: comp.ref,
        translation: [comp.x_mm * 0.001, yMount, comp.y_mm * 0.001],
        rotation: [0, qy, 0, qw],
        mesh: meshIdx,
      });
      rootChildren.push(nodeIdx);
      addedProc++;
    }
  }
  gb.nodes[outRootIdx].children = rootChildren;

  const outBoardPath = path.join(ASSETS_DIR, "board.glb");
  gb.save(outBoardPath, [outRootIdx]);
  const stat = fs.statSync(outBoardPath);
  console.log(
    `Built board.glb (${(stat.size / 1e6).toFixed(2)} MB, ${gb.meshes.length} unique meshes, ${addedProc} procedural replacements, ${gb.accessors.length} accessors)`
  );
}

// ---------------------------------------------------------------------------
// 2. Build simplified KV260 + K26 SOM model (kv260.glb, Apache-2.0 / MIT)
// ---------------------------------------------------------------------------

function buildKv260Glb(compJson) {
  const gb = new GlbBuilder();
  const mGreen = gb.addMaterial("kv_green", [0.0, 0.107, 0.009, 1.0], 0.0, 0.58);
  const mGold = gb.addMaterial("kv_gold", [0.86, 0.68, 0.36, 1.0], 0.96, 0.32);
  const mNickel = gb.addMaterial("kv_nickel", [0.58, 0.58, 0.57, 1.0], 0.92, 0.24);
  const mHeatsink = gb.addMaterial("kv_heatsink", [0.06, 0.065, 0.072, 1.0], 0.85, 0.36);
  const mFanPbt = gb.addMaterial("kv_fan_pbt", [0.032, 0.034, 0.038, 1.0], 0.0, 0.55);
  const mPlastic = gb.addMaterial("kv_plastic", [0.04, 0.042, 0.046, 1.0], 0.0, 0.52);
  const mIvory = gb.addMaterial("kv_ivory", [0.22, 0.20, 0.16, 1.0], 0.0, 0.50);
  const mSilicon = gb.addMaterial("kv_silicon", [0.16, 0.17, 0.18, 1.0], 0.4, 0.35);

  const addPartBox = (id, name, [x0, y0, x1, y1, z0, z1], matIdx, accentMat = null) => {
    const prims = [];
    const main = kvBoxMm(x0, x1, y0, y1, z0, z1);
    prims.push(gb.addPrimitive(main.positions, main.normals, main.indices, matIdx));
    if (accentMat !== null) {
      const trim = kvBoxMm(x0 + 0.4, x1 - 0.4, y0 + 0.4, y1 - 0.4, z1 - 0.25, z1 + 0.05);
      prims.push(gb.addPrimitive(trim.positions, trim.normals, trim.indices, accentMat));
    }
    const mi = gb.addMesh(id, prims);
    return gb.addNode({ name: id, mesh: mi });
  };

  // Carrier assembly children
  const carrierChildren = [];
  carrierChildren.push(addPartBox("KV260_CARRIER", "Carrier PCB", [-10, -10, 130, 109, -1.59, 0.0], mGreen));

  // Corner mounting standoffs/pads in KV260 carrier corners (-5,-5), (-5,104), (125,-5), (125,104)
  const holeGeoms = [[-5, -5], [-5, 104], [125, -5], [125, 104]].map(([x, y]) => {
    const s = 0.001;
    return createCylY(x * s, -0.00165, 0.00008, -y * s, 0.0028, 16);
  });
  const mergedHoles = mergeGeoms(holeGeoms);
  carrierChildren.push(
    gb.addNode({
      name: "KV260_MOUNT_PADS",
      mesh: gb.addMesh("KV260_MOUNT_PADS", [gb.addPrimitive(mergedHoles.positions, mergedHoles.normals, mergedHoles.indices, mGold)]),
    })
  );

  // Carrier connectors & major ICs matching real measured coordinates
  for (const p of compJson.kv260_parts) {
    if (p.subassembly !== "carrier" || p.id === "KV260_CARRIER") continue;
    let mat = mPlastic;
    let acc = mGold;
    if (p.id.includes("RJ45") || p.id.includes("USB") || p.id.includes("HDMI") || p.id.includes("DP") || p.id.includes("UART") || p.id.includes("SD")) {
      mat = mNickel;
      acc = mPlastic;
    } else if (p.id.includes("J9") || p.id.includes("J12")) {
      mat = mIvory;
      acc = mNickel;
    } else if (p.id.includes("U27")) {
      mat = mFanPbt;
      acc = mSilicon;
    }
    const [x0, y0, x1, y1, z0, z1] = p.bbox_mm;
    carrierChildren.push(addPartBox(p.id, p.ref, [x0, y0, x1, y1, z0, z1], mat, acc));
  }

  // Carrier side of SOM240 receptacles
  carrierChildren.push(addPartBox("SOM240_1_CARRIER", "SOM240_1 Carrier", [50.32, 25.57, 55.32, 68.39, 0.0, 2.6], mIvory, mGold));
  carrierChildren.push(addPartBox("SOM240_2_CARRIER", "SOM240_2 Carrier", [116.3, 25.57, 121.3, 68.39, 0.0, 2.6], mIvory, mGold));

  const carrierGroup = gb.addNode({ name: "KV260_CARRIER_GROUP", children: carrierChildren });

  // Liftable K26 SOM group
  const somChildren = [];
  for (const p of compJson.kv260_parts) {
    if (p.subassembly !== "som") continue;
    const [x0, y0, x1, y1, z0, z1] = p.bbox_mm;
    if (p.id === "K26_SOM") {
      somChildren.push(addPartBox("K26_SOM", p.ref, [x0, y0, x1, y1, z0, z1], mGreen));
    } else if (p.id === "K26_XCK26") {
      // Package substrate + shiny silicon die
      somChildren.push(addPartBox("K26_XCK26", p.ref, [x0, y0, x1, y1, z0, z1 - 0.6], mGreen, mSilicon));
    } else if (p.id === "K26_DDR4") {
      // Four individual DDR4 packages along Y 58.64..72.14
      const xStarts = [67.18, 77.34, 87.50, 97.66];
      const boxes = xStarts.map((xs) => kvBoxMm(xs, xs + 7.5, y0, y1, z0, z1));
      const m = mergeGeoms(boxes);
      somChildren.push(gb.addNode({ name: "K26_DDR4", mesh: gb.addMesh("K26_DDR4", [gb.addPrimitive(m.positions, m.normals, m.indices, mFanPbt)]) }));
    } else if (p.id.startsWith("SOM240")) {
      somChildren.push(addPartBox(p.id, p.ref, [x0, y0, x1, y1, 2.5, 5.0], mPlastic, mGold));
    } else {
      somChildren.push(addPartBox(p.id, p.ref, [x0, y0, x1, y1, z0, z1], mFanPbt));
    }
  }
  const somGroup = gb.addNode({ name: "K26_SOM_GROUP", children: somChildren });

  // Removable cooling group (finned heatsink + 4010 fan)
  const sinkFins = [kvBoxMm(52.43, 119.83, 20.78, 73.18, 5.81, 10.1)];
  const nFins = 14;
  for (let i = 0; i < nFins; i++) {
    const fy = 21.5 + (i * (72.2 - 21.5)) / (nFins - 1);
    sinkFins.push(kvBoxMm(52.43, 119.83, fy - 0.6, fy + 0.6, 10.1, 25.1));
  }
  const sinkGeom = mergeGeoms(sinkFins);
  const sinkNode = gb.addNode({
    name: "KV260_HEATSINK",
    mesh: gb.addMesh("KV260_HEATSINK", [gb.addPrimitive(sinkGeom.positions, sinkGeom.normals, sinkGeom.indices, mHeatsink)]),
  });

  // 4010 fan shroud + impeller hub + cover plate (matching KV260_FAN bbox X 51.1..121.1 Y 19..75 Z 10.1..28.75)
  const fanParts = [
    kvBoxMm(64.8, 107.4, 25.7, 68.3, 27.6, 28.75), // top cover plate
    kvBoxMm(51.1, 121.1, 19.0, 21.5, 10.1, 26.0),  // side shroud wall
    kvBoxMm(51.1, 121.1, 72.5, 75.0, 10.1, 26.0),  // opposite shroud wall
    createCylY(0.08615, 0.0165, 0.0265, -0.047, 0.0085, 24), // fan motor hub
  ];
  for (let b = 0; b < 7; b++) {
    const ang = (b * Math.PI * 2) / 7;
    const rx = 86.15 + Math.cos(ang) * 14.0;
    const ry = 47.0 + Math.sin(ang) * 14.0;
    fanParts.push(kvBoxMm(rx - 4.0, rx + 4.0, ry - 1.5, ry + 1.5, 18.0, 24.5));
  }
  const fanGeom = mergeGeoms(fanParts);
  const fanNode = gb.addNode({
    name: "KV260_FAN",
    mesh: gb.addMesh("KV260_FAN", [gb.addPrimitive(fanGeom.positions, fanGeom.normals, fanGeom.indices, mFanPbt)]),
  });
  const coolingGroup = gb.addNode({ name: "KV260_COOLING_GROUP", children: [sinkNode, fanNode] });

  const root = gb.addNode({ name: "KV260_ROOT", children: [carrierGroup, somGroup, coolingGroup] });
  const outPath = path.join(ASSETS_DIR, "kv260.glb");
  gb.save(outPath, [root]);
  console.log(`Built kv260.glb (${(fs.statSync(outPath).size / 1e3).toFixed(1)} KB, simplified multi-part Apache-2.0/MIT model)`);
}

// ---------------------------------------------------------------------------
// 3. Convert repo enclosure STLs + adapter heatsinks/fan -> enclosure.glb
// ---------------------------------------------------------------------------

function readBinaryStlToGltf(stlPath, flipX180 = false) {
  const buf = fs.readFileSync(stlPath);
  const triCount = buf.readUInt32LE(80);
  const vertMap = new Map();
  const positions = [];
  const normSums = [];
  const indices = [];

  const getVert = (rx, ry, rz) => {
    const x = rx;
    const y = flipX180 ? -ry : ry;
    const z = flipX180 ? -rz : rz;
    // Blender STL in mm (X, Y, Z) -> glTF Y-up metres (X, Z, -Y) * 0.001
    const gx = x * 0.001;
    const gy = z * 0.001;
    const gz = -y * 0.001;
    const key = `${Math.round(x * 1000)},${Math.round(y * 1000)},${Math.round(z * 1000)}`;
    let idx = vertMap.get(key);
    if (idx === undefined) {
      idx = positions.length / 3;
      positions.push(gx, gy, gz);
      normSums.push(0, 0, 0);
      vertMap.set(key, idx);
    }
    return idx;
  };

  for (let t = 0; t < triCount; t++) {
    const off = 84 + t * 50;
    if (off + 50 > buf.length) break;
    const i0 = getVert(buf.readFloatLE(off + 12), buf.readFloatLE(off + 16), buf.readFloatLE(off + 20));
    const i1 = getVert(buf.readFloatLE(off + 24), buf.readFloatLE(off + 28), buf.readFloatLE(off + 32));
    const i2 = getVert(buf.readFloatLE(off + 36), buf.readFloatLE(off + 40), buf.readFloatLE(off + 44));
    indices.push(i0, i1, i2);

    const ax = positions[i1 * 3] - positions[i0 * 3];
    const ay = positions[i1 * 3 + 1] - positions[i0 * 3 + 1];
    const az = positions[i1 * 3 + 2] - positions[i0 * 3 + 2];
    const bx = positions[i2 * 3] - positions[i0 * 3];
    const by = positions[i2 * 3 + 1] - positions[i0 * 3 + 1];
    const bz = positions[i2 * 3 + 2] - positions[i0 * 3 + 2];
    const nx = ay * bz - az * by;
    const ny = az * bx - ax * bz;
    const nz = ax * by - ay * bx;
    for (const vi of [i0, i1, i2]) {
      normSums[vi * 3] += nx;
      normSums[vi * 3 + 1] += ny;
      normSums[vi * 3 + 2] += nz;
    }
  }

  const normals = new Float32Array(normSums.length);
  for (let i = 0; i < normSums.length; i += 3) {
    const nx = normSums[i], ny = normSums[i + 1], nz = normSums[i + 2];
    const l = Math.hypot(nx, ny, nz) || 1;
    normals[i] = nx / l;
    normals[i + 1] = ny / l;
    normals[i + 2] = nz / l;
  }

  return {
    positions: new Float32Array(positions),
    normals,
    indices: (positions.length / 3) > 65535 ? new Uint32Array(indices) : new Uint16Array(indices),
  };
}

function buildFinnedHeatsinkGeom(cx, cy, z0, sx, sy, sz, nFins) {
  const padT = 0.18;
  const baseH = Math.min(1.4, sz * 0.28);
  const finH = sz - baseH;
  const finT = (sx * 0.44) / nFins;
  const pitch = (sx - finT) / Math.max(1, nFins - 1);
  const xStart = cx - sx * 0.5 + finT * 0.5;
  const parts = [kvBoxMm(cx - sx * 0.5, cx + sx * 0.5, cy - sy * 0.5, cy + sy * 0.5, z0 + padT, z0 + padT + baseH)];
  for (let i = 0; i < nFins; i++) {
    const fx = xStart + i * pitch;
    parts.push(kvBoxMm(fx - finT * 0.5, fx + finT * 0.5, cy - sy * 0.5, cy + sy * 0.5, z0 + padT + baseH, z0 + sz));
  }
  return mergeGeoms(parts);
}

function buildEnclosureGlb() {
  const gb = new GlbBuilder();
  const mPetg = gb.addMaterial("petg_cf", [0.045, 0.048, 0.055, 1.0], 0.05, 0.72);
  const mTpu = gb.addMaterial("tpu_95a", [0.68, 0.28, 0.04, 1.0], 0.0, 0.62);
  const mHsBlack = gb.addMaterial("hs_black_al", [0.05, 0.055, 0.062, 1.0], 0.88, 0.36);
  const mHsBlue = gb.addMaterial("hs_blue_al", [0.03, 0.09, 0.24, 1.0], 0.88, 0.35);
  const mHsCopper = gb.addMaterial("hs_copper", [0.55, 0.22, 0.09, 1.0], 0.92, 0.32);
  const mFanPbt = gb.addMaterial("od5015_pbt", [0.038, 0.040, 0.044, 1.0], 0.0, 0.55);

  const stlFiles = [
    { name: "CASE_BOTTOM", file: "case_v2_bottom.stl", mat: mPetg, group: "bottom", flipX180: false },
    { name: "CASE_LID", file: "case_v2_lid.stl", mat: mPetg, group: "lid", flipX180: true },
    { name: "CASE_FILTER_FRAME", file: "case_v2_filter_frame.stl", mat: mPetg, group: "lid", flipX180: false },
    { name: "CASE_BUMPER_LF", file: "case_bumper_lfront.stl", mat: mTpu, group: "bumpers", flipX180: false },
    { name: "CASE_BUMPER_RF", file: "case_bumper_rfront.stl", mat: mTpu, group: "bumpers", flipX180: false },
    { name: "CASE_BUMPER_LB", file: "case_bumper_lback.stl", mat: mTpu, group: "bumpers", flipX180: false },
    { name: "CASE_BUMPER_RB", file: "case_bumper_rback.stl", mat: mTpu, group: "bumpers", flipX180: false },
  ];

  const lidNodes = [];
  const bottomNodes = [];
  const bumperNodes = [];

  for (const s of stlFiles) {
    const p = path.join(ROOT_DIR, "mech", s.file);
    if (!fs.existsSync(p)) continue;
    const g = readBinaryStlToGltf(p, s.flipX180);
    const prim = gb.addPrimitive(g.positions, g.normals, g.indices, s.mat);
    const ni = gb.addNode({ name: s.name, mesh: gb.addMesh(s.name, [prim]) });
    if (s.group === "lid") lidNodes.push(ni);
    else if (s.group === "bottom") bottomNodes.push(ni);
    else bumperNodes.push(ni);
  }

  // Add OD5015 50x50x15 mm intake fan inside the v2 lid at (-40, 14) mm, Z 13.75..28.75 mm
  const fx = -40.0, fy = 14.0;
  const fanGeoms = [
    kvBoxMm(fx - 25, fx + 25, fy - 25, fy - 22, 13.75, 28.75),
    kvBoxMm(fx - 25, fx + 25, fy + 22, fy + 25, 13.75, 28.75),
    kvBoxMm(fx - 25, fx - 22, fy - 22, fy + 22, 13.75, 28.75),
    kvBoxMm(fx + 22, fx + 25, fy - 22, fy + 22, 13.75, 28.75),
    createCylY(fx * 0.001, 0.01475, 0.02815, -fy * 0.001, 0.0105, 24),
  ];
  for (let b = 0; b < 7; b++) {
    const ang = (b * Math.PI * 2) / 7;
    const bx = fx + Math.cos(ang) * 16.0;
    const by = fy + Math.sin(ang) * 16.0;
    fanGeoms.push(kvBoxMm(bx - 4.5, bx + 4.5, by - 1.5, by + 1.5, 17.0, 26.0));
  }
  const fMerged = mergeGeoms(fanGeoms);
  const fanNode = gb.addNode({
    name: "FAN2_5015",
    mesh: gb.addMesh("FAN2_5015", [gb.addPrimitive(fMerged.positions, fMerged.normals, fMerged.indices, mFanPbt)]),
  });
  lidNodes.push(fanNode);

  // Add HS1..HS4 adapter heatsinks
  const hsSpecs = [
    { name: "HS1_U501_AD9484", cx: -51.8, cy: 10.55, z0: 3.34, sx: 14, sy: 14, sz: 8.5, n: 7, mat: mHsBlack },
    { name: "HS2_U401_ADCLK948", cx: -34.9, cy: -1.2, z0: 3.15, sx: 9, sy: 7, sz: 8.0, n: 5, mat: mHsBlue },
    { name: "HS3_Y401_Si549", cx: -35.0, cy: 9.8, z0: 3.99, sx: 9, sy: 7, sz: 8.0, n: 5, mat: mHsBlue },
    { name: "HS4_U1101_XC7A50T", cx: -42.75, cy: 40.0, z0: 3.84, sx: 14, sy: 14, sz: 5.0, n: 8, mat: mHsCopper },
  ];
  const hsNodes = [];
  for (const h of hsSpecs) {
    const hg = buildFinnedHeatsinkGeom(h.cx, h.cy, h.z0, h.sx, h.sy, h.sz, h.n);
    hsNodes.push(gb.addNode({ name: h.name, mesh: gb.addMesh(h.name, [gb.addPrimitive(hg.positions, hg.normals, hg.indices, h.mat)]) }));
  }

  const lidGroup = gb.addNode({ name: "ENCLOSURE_LID_GROUP", children: lidNodes });
  const bottomGroup = gb.addNode({ name: "ENCLOSURE_BOTTOM_GROUP", children: bottomNodes });
  const bumpersGroup = gb.addNode({ name: "ENCLOSURE_BUMPERS_GROUP", children: bumperNodes });
  const hsGroup = gb.addNode({ name: "ADAPTER_HEATSINKS_GROUP", children: hsNodes });

  const root = gb.addNode({ name: "ENCLOSURE_ROOT", children: [bottomGroup, lidGroup, bumpersGroup, hsGroup] });
  const outPath = path.join(ASSETS_DIR, "enclosure.glb");
  gb.save(outPath, [root]);
  console.log(`Built enclosure.glb (${(fs.statSync(outPath).size / 1e6).toFixed(2)} MB, from mech/*.stl + HS1..HS4 + OD5015)`);
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------
const compJson = JSON.parse(fs.readFileSync(path.join(ASSETS_DIR, "components.json"), "utf8"));
buildBoardGlb(compJson);
buildKv260Glb(compJson);
buildEnclosureGlb();
