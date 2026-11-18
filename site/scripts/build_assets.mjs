#!/usr/bin/env node
/**
 * Build and optimize site/assets/board.glb, kv260.glb, and enclosure.glb in pure Node.js.
 * Zero Python, zero EasyEDA models, zero AMD XTP679 geometry redistributed.
 *
 * Key optimizations & quality fixes:
 *  - Excludes flat PCB copper/mask/silk meshes from board.glb (baked into 2-D textures in app.js),
 *    keeping 3-D FR4 substrate, THT/SMD pads, vias, and component packages.
 *  - Fixes negative-determinant transforms and checks every triangle winding against its normals
 *    so bottom-side parts render right-side-up with clean outward normals (no DoubleSide hack).
 *  - Parses repo-authored VRML mech/models3d/USB_C_HRO_TYPE-C-31-E-17.wrl for J1501.
 *  - Centers the 9 unmapped procedural parts at exact footprint bounds center.
 *  - Computes 30-degree crease-angle smooth normals on full-resolution enclosure STLs with PETG-CF / TPU PBR.
 *  - Builds a detailed custom KV260 + K26 SOM model using official KiCad 10 STEP connectors at UG1089 coords.
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
const KV260_CONN_PATH = process.argv[3] || "";

if (!RAW_BOARD_PATH || !fs.existsSync(RAW_BOARD_PATH)) {
  console.error("Usage: node site/scripts/build_assets.mjs <raw_board.glb> [kv260_conn.glb]");
  process.exit(1);
}

// ---------------------------------------------------------------------------
// Low-level GLB Reader / Writer + Mesh & Math Helpers
// ---------------------------------------------------------------------------

function readGlb(filePath) {
  const buf = fs.readFileSync(filePath);
  if (buf.readUInt32LE(0) !== 0x46546c67) throw new Error("Not a valid GLB file: " + filePath);
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

function mat4FromNode(nd) {
  if (nd.matrix) return nd.matrix;
  const [tx, ty, tz] = nd.translation || [0, 0, 0];
  const [qx, qy, qz, qw] = nd.rotation || [0, 0, 0, 1];
  const [sx, sy, sz] = nd.scale || [1, 1, 1];
  const x2 = qx + qx, y2 = qy + qy, z2 = qz + qz;
  const xx = qx * x2, xy = qx * y2, xz = qx * z2;
  const yy = qy * y2, yz = qy * z2, zz = qz * z2;
  const wx = qw * x2, wy = qw * y2, wz = qw * z2;
  return [
    (1 - (yy + zz)) * sx, (xy + wz) * sx, (xz - wy) * sx, 0,
    (xy - wz) * sy, (1 - (xx + zz)) * sy, (yz + wx) * sy, 0,
    (xz + wy) * sz, (yz - wx) * sz, (1 - (xx + yy)) * sz, 0,
    tx, ty, tz, 1,
  ];
}

function mulMat4(a, b) {
  const o = new Array(16).fill(0);
  for (let c = 0; c < 4; c++) {
    for (let r = 0; r < 4; r++) {
      o[c * 4 + r] = a[r] * b[c * 4] + a[4 + r] * b[c * 4 + 1] + a[8 + r] * b[c * 4 + 2] + a[12 + r] * b[c * 4 + 3];
    }
  }
  return o;
}

function det3(m) {
  return (
    m[0] * (m[5] * m[10] - m[6] * m[9]) -
    m[1] * (m[4] * m[10] - m[6] * m[8]) +
    m[2] * (m[4] * m[9] - m[5] * m[8])
  );
}

/**
 * Fix triangle winding against vertex normals (and optionally bake a negative-det reflection).
 * Ensures 100% of front faces point outward with FrontSide culling (zero inside-out parts).
 */
function fixWindingAndNormals(positions, normals, indices, flipMirror = false) {
  const pos = new Float32Array(positions);
  const norm = new Float32Array(normals);
  const idx = indices instanceof Uint16Array ? new Uint16Array(indices) : new Uint32Array(indices);
  if (flipMirror) {
    for (let i = 0; i < pos.length; i += 3) {
      pos[i] = -pos[i];
      norm[i] = -norm[i];
    }
  }
  let flipped = 0;
  for (let t = 0; t + 2 < idx.length; t += 3) {
    let i0 = idx[t], i1 = idx[t + 1], i2 = idx[t + 2];
    if (flipMirror) {
      idx[t + 1] = i2;
      idx[t + 2] = i1;
      [i1, i2] = [i2, i1];
    }
    const a = i0 * 3, b = i1 * 3, c = i2 * 3;
    const ax = pos[b] - pos[a], ay = pos[b + 1] - pos[a + 1], az = pos[b + 2] - pos[a + 2];
    const bx = pos[c] - pos[a], by = pos[c + 1] - pos[a + 1], bz = pos[c + 2] - pos[a + 2];
    const gx = ay * bz - az * by, gy = az * bx - ax * bz, gz = ax * by - ay * bx;
    const nsx = norm[a] + norm[b] + norm[c];
    const nsy = norm[a + 1] + norm[b + 1] + norm[c + 1];
    const nsz = norm[a + 2] + norm[b + 2] + norm[c + 2];
    if (gx * nsx + gy * nsy + gz * nsz < -1e-18) {
      idx[t + 1] = i2;
      idx[t + 2] = i1;
      flipped++;
    }
  }
  return { positions: pos, normals: norm, indices: idx, flipped };
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

  addPrimitive(positions, normals, indices, materialIdx, weldQuant = 0) {
    const prims = this.addOptimizedPrimitives(positions, normals, indices, materialIdx, weldQuant);
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
    if (totalVerts <= 65535) {
      return [this._writeRawPrimitive(wPos, wNorm, wIdx, materialIdx)];
    }
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
    let idxComp = 5125;
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

function createBoxGeom(x0, x1, y0, y1, z0, z1) {
  const ax0 = Math.min(x0, x1), ax1 = Math.max(x0, x1);
  const ay0 = Math.min(y0, y1), ay1 = Math.max(y0, y1);
  const az0 = Math.min(z0, z1), az1 = Math.max(z0, z1);
  const pts = [
    [ax0, ay0, az1], [ax1, ay0, az1], [ax1, ay1, az1], [ax0, ay1, az1],
    [ax1, ay0, az0], [ax0, ay0, az0], [ax0, ay1, az0], [ax1, ay1, az0],
    [ax0, ay1, az1], [ax1, ay1, az1], [ax1, ay1, az0], [ax0, ay1, az0],
    [ax0, ay0, az0], [ax1, ay0, az0], [ax1, ay0, az1], [ax0, ay0, az1],
    [ax1, ay0, az1], [ax1, ay0, az0], [ax1, ay1, az0], [ax1, ay1, az1],
    [ax0, ay0, az0], [ax0, ay0, az1], [ax0, ay1, az1], [ax0, ay1, az0],
  ];
  const nrms = [[0, 0, 1], [0, 0, -1], [0, 1, 0], [0, -1, 0], [1, 0, 0], [-1, 0, 0]];
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
  const lo = Math.min(y0, y1), hi = Math.max(y0, y1);
  const pos = [], norm = [], idx = [];
  for (let i = 0; i <= seg; i++) {
    const a = (i / seg) * Math.PI * 2;
    const ca = Math.cos(a), sa = Math.sin(a);
    pos.push(cx + radius * ca, lo, cz + radius * sa);
    norm.push(ca, 0, sa);
    pos.push(cx + radius * ca, hi, cz + radius * sa);
    norm.push(ca, 0, sa);
  }
  for (let i = 0; i < seg; i++) {
    const a = i * 2;
    idx.push(a, a + 2, a + 3, a, a + 3, a + 1);
  }
  const topC = pos.length / 3;
  pos.push(cx, hi, cz);
  norm.push(0, 1, 0);
  for (let i = 0; i <= seg; i++) {
    const a = (i / seg) * Math.PI * 2;
    pos.push(cx + radius * Math.cos(a), hi, cz + radius * Math.sin(a));
    norm.push(0, 1, 0);
  }
  for (let i = 0; i < seg; i++) idx.push(topC, topC + 1 + i, topC + 2 + i);

  const botC = pos.length / 3;
  pos.push(cx, lo, cz);
  norm.push(0, -1, 0);
  for (let i = 0; i <= seg; i++) {
    const a = (i / seg) * Math.PI * 2;
    pos.push(cx + radius * Math.cos(a), lo, cz + radius * Math.sin(a));
    norm.push(0, -1, 0);
  }
  for (let i = 0; i < seg; i++) idx.push(botC, botC + 2 + i, botC + 1 + i);

  return { positions: new Float32Array(pos), normals: new Float32Array(norm), indices: new Uint16Array(idx) };
}

function weldVertices(positions, normals, indices, qScale) {
  const map = new Map();
  const outPos = [], outNorm = [], outIdx = [];
  const remap = new Int32Array(positions.length / 3).fill(-1);
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
    const a = remap[indices[t]], b = remap[indices[t + 1]], c = remap[indices[t + 2]];
    if (a >= 0 && b >= 0 && c >= 0 && a !== b && b !== c && a !== c) outIdx.push(a, b, c);
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
    const cPos = [], cNorm = [], cIdx = [];
    let t = tStart;
    for (; t < totalTris; t++) {
      const i0 = indices[t * 3], i1 = indices[t * 3 + 1], i2 = indices[t * 3 + 2];
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
    chunks.push({ positions: new Float32Array(cPos), normals: new Float32Array(cNorm), indices: new Uint16Array(cIdx) });
    tStart = t;
  }
  return chunks;
}

function cullPadViaTriangles(positions, indices, boardRole) {
  const kept = [];
  for (let t = 0; t + 2 < indices.length; t += 3) {
    const i0 = indices[t], i1 = indices[t + 1], i2 = indices[t + 2];
    const a = i0 * 3, b = i1 * 3, c = i2 * 3;
    const ax = positions[b] - positions[a], ay = positions[b + 1] - positions[a + 1], az = positions[b + 2] - positions[a + 2];
    const bx = positions[c] - positions[a], by = positions[c + 1] - positions[a + 1], bz = positions[c + 2] - positions[a + 2];
    const nx = ay * bz - az * by, ny = az * bx - ax * bz, nz = ax * by - ay * bx;
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
  const s = 0.001;
  return createBoxGeom(x0 * s, x1 * s, z0 * s, z1 * s, -y1 * s, -y0 * s);
}

// ---------------------------------------------------------------------------
// 1. Parse repo-authored VRML for J1501 + Centered Procedural Parts
// ---------------------------------------------------------------------------

function buildVrmlMesh(gb, wrlPath, name) {
  const txt = fs.readFileSync(wrlPath, "utf8");
  const shapes = [];
  const shapeRe = /diffuseColor\s+([\d.\s-]+)[\s\S]*?point\s*\[([^\]]+)\][\s\S]*?coordIndex\s*\[([^\]]+)\]/g;
  let m;
  while ((m = shapeRe.exec(txt)) !== null) {
    const [r, g, b] = m[1].trim().split(/\s+/).map(Number);
    const pts = m[2].trim().split(",").map((s) => s.trim().split(/\s+/).map(Number));
    const idxTokens = m[3].trim().split(",").map((s) => parseInt(s.trim(), 10));
    const pos = [];
    const norm = [];
    const idx = [];
    const scaleM = 0.00254; // KiCad VRML units: 0.1 inch = 2.54 mm
    // VRML (x, y, z_up) -> glTF Y-up metres (x, z_up, -y)
    const mapPt = ([vx, vy, vz]) => [vx * scaleM, vz * scaleM, -vy * scaleM];

    let face = [];
    for (const tk of idxTokens) {
      if (tk === -1) {
        if (face.length >= 3) {
          for (let k = 1; k + 1 < face.length; k++) {
            const p0 = mapPt(pts[face[0]]);
            const p1 = mapPt(pts[face[k]]);
            const p2 = mapPt(pts[face[k + 1]]);
            const ax = p1[0] - p0[0], ay = p1[1] - p0[1], az = p1[2] - p0[2];
            const bx = p2[0] - p0[0], by = p2[1] - p0[1], bz = p2[2] - p0[2];
            let nx = ay * bz - az * by, ny = az * bx - ax * bz, nz = ax * by - ay * bx;
            const nl = Math.hypot(nx, ny, nz) || 1;
            nx /= nl; ny /= nl; nz /= nl;
            const base = pos.length / 3;
            pos.push(...p0, ...p1, ...p2);
            norm.push(nx, ny, nz, nx, ny, nz, nx, ny, nz);
            idx.push(base, base + 1, base + 2);
          }
        }
        face = [];
      } else {
        face.push(tk);
      }
    }
    if (!idx.length) continue;
    const isMetal = Math.max(r, g, b) > 0.45 && Math.max(r, g, b) - Math.min(r, g, b) < 0.25;
    const isGold = r > 0.7 && g > 0.5 && b < 0.45;
    const matIdx = gb.addMaterial(
      `${name}_mat_${shapes.length}`,
      [Math.min(0.85, r), Math.min(0.85, g), Math.min(0.85, b), 1.0],
      isMetal || isGold ? 0.90 : 0.0,
      isGold ? 0.28 : isMetal ? 0.26 : 0.52,
      false
    );
    shapes.push(gb.addPrimitive(new Float32Array(pos), new Float32Array(norm), new Uint16Array(idx), matIdx, 0));
  }
  return gb.addMesh(`vrml_${name}`, shapes);
}

function addProceduralComponentMesh(gb, comp, mats) {
  const s = 0.001;
  const [w, l, h] = comp.local_size_mm;
  const hw = Math.max(w * 0.42, 0.4) * s;
  const hl = Math.max(l * 0.42, 0.4) * s;
  const isBot = comp.side === "bottom";
  const sign = isBot ? -1 : 1;
  const y0 = isBot ? -Math.max(h, 0.5) * s : 0;
  const y1 = isBot ? 0 : Math.max(h, 0.5) * s;

  const prims = [];
  if (/^J10[123]$/.test(comp.ref)) {
    const body = createBoxGeom(-0.0046, 0.0046, y0, y1, -0.0012, 0.0012);
    const l0 = isBot ? -0.00045 : 0.0;
    const l1 = isBot ? 0.0 : 0.00045;
    const contacts = createBoxGeom(-0.0036, 0.0036, l0, l1, -0.00145, 0.00145);
    prims.push(gb.addPrimitive(body.positions, body.normals, body.indices, mats.darkBody));
    prims.push(gb.addPrimitive(contacts.positions, contacts.normals, contacts.indices, mats.gold));
  } else if (/^(T701|T801|T802)$/.test(comp.ref)) {
    const base = createBoxGeom(-0.0035, 0.0035, 0.0002, 0.00284, -0.0028, 0.0028);
    const leads = createBoxGeom(-0.00395, 0.00395, 0, 0.00045, -0.0025, 0.0025);
    prims.push(gb.addPrimitive(base.positions, base.normals, base.indices, mats.ceramic));
    prims.push(gb.addPrimitive(leads.positions, leads.normals, leads.indices, mats.gold));
  } else {
    // T1301, T1302, FL1301
    const body = createBoxGeom(-hw * 0.85, hw * 0.85, y0, y1, -hl * 0.85, hl * 0.85);
    const l0 = isBot ? -0.00035 : 0;
    const l1 = isBot ? 0 : 0.00035;
    const leads = createBoxGeom(-hw * 0.95, hw * 0.95, l0, l1, -hl * 0.72, hl * 0.72);
    const matIdx = comp.ref.startsWith("FL") ? mats.ceramic : mats.darkBody;
    prims.push(gb.addPrimitive(body.positions, body.normals, body.indices, matIdx));
    prims.push(gb.addPrimitive(leads.positions, leads.normals, leads.indices, mats.gold));
  }
  return gb.addMesh(`proc_${comp.ref}`, prims);
}

function calibrateMaterial(mat) {
  const m = JSON.parse(JSON.stringify(mat));
  const pbr = (m.pbrMetallicRoughness ||= {});
  const c = [...(pbr.baseColorFactor || [0.5, 0.5, 0.5, 1.0])];
  const r = c[0], g = c[1], bl = c[2], a = c[3] ?? 1.0;
  const L = 0.2126 * r + 0.7152 * g + 0.0722 * bl;
  const sat = Math.max(r, g, bl) - Math.min(r, g, bl);

  const goldish = r > 0.45 && r > g && g > bl && bl < 0.45 * r && sat > 0.20;
  if (goldish && bl > 0.12 * r) {
    pbr.baseColorFactor = [0.86, 0.68, 0.36, 1.0];
    pbr.metallicFactor = 0.95;
    pbr.roughnessFactor = 0.32;
  } else if (sat < 0.14 && L > 0.34) {
    const v = Math.max(0.45, Math.min(0.68, L * 0.92));
    pbr.baseColorFactor = [v, v, v * 0.98, 1.0];
    pbr.metallicFactor = 0.92;
    pbr.roughnessFactor = 0.28;
  } else {
    const k = Math.min(1.0, 0.78 / Math.max(r, g, bl, 1e-4));
    pbr.baseColorFactor = [r * k, g * k, bl * k, a];
    pbr.metallicFactor = 0.0;
    pbr.roughnessFactor = L < 0.08 ? 0.55 : 0.48;
  }
  if (a >= 0.999) delete m.doubleSided;
  return m;
}

// ---------------------------------------------------------------------------
// 2. Build Fast Textured board.glb (3-D FR4 + Pads/Vias + Packages)
// ---------------------------------------------------------------------------

function buildBoardGlb(compJson) {
  const { gltf, bin } = readGlb(RAW_BOARD_PATH);
  const gb = new GlbBuilder();

  const srcNodes = gltf.nodes || [];
  const srcMeshes = gltf.meshes || [];
  const srcMats = gltf.materials || [];
  const rootIdx = (gltf.scenes && gltf.scenes[0] && gltf.scenes[0].nodes && gltf.scenes[0].nodes[0]) ?? 0;

  const boardRoleRe = /_(copper|pad|via|silkscreen|soldermask|PCB)$/;
  const matRole = new Map();
  for (const sm of srcMeshes) {
    const rm = (sm.name || "").match(boardRoleRe);
    if (rm) {
      for (const p of sm.primitives) if (p.material !== undefined) matRole.set(p.material, rm[1]);
    }
  }

  for (let i = 0; i < srcMats.length; i++) {
    const role = matRole.get(i);
    if (role === "pad" || role === "via") {
      gb.materials.push({
        name: `board_${role}_enig`,
        pbrMetallicRoughness: { baseColorFactor: [0.88, 0.70, 0.40, 1.0], metallicFactor: 0.88, roughnessFactor: 0.28 },
      });
    } else if (role === "PCB") {
      gb.materials.push({
        name: "board_fr4_core",
        pbrMetallicRoughness: { baseColorFactor: [0.10, 0.14, 0.08, 1.0], metallicFactor: 0.0, roughnessFactor: 0.78 },
      });
    } else {
      gb.materials.push(calibrateMaterial(srcMats[i]));
    }
  }

  const procMats = {
    nickel: gb.addMaterial("proc_nickel", [0.60, 0.60, 0.59, 1.0], 0.92, 0.25),
    gold: gb.addMaterial("proc_gold", [0.86, 0.68, 0.36, 1.0], 0.96, 0.28),
    darkBody: gb.addMaterial("proc_epoxy", [0.025, 0.026, 0.030, 1.0], 0.0, 0.55),
    ivory: gb.addMaterial("proc_ivory", [0.22, 0.20, 0.16, 1.0], 0.0, 0.50),
    ceramic: gb.addMaterial("proc_ceramic", [0.38, 0.36, 0.32, 1.0], 0.0, 0.45),
  };

  // Tint only explicit white-plastic connector bodies (never metal by colour alone)
  const WHITE_PLASTIC_REFS = new Set(["J1503", "J1502", "J1002"]);
  const METAL_CAN_REFS = new Set(["Y1201", "Y1301", "Y401"]);
  const ivoryPlasticMatIdx = gb.addMaterial("plastic_ivory", [0.24, 0.21, 0.16, 1.0], 0.0, 0.54);
  const metalCanMatIdx = gb.addMaterial("metal_can", [0.48, 0.48, 0.49, 1.0], 0.92, 0.26);

  let boardYMin = 0.0;
  let boardYMax = 0.00145;
  let totalFixedTris = 0;

  const dedupCache = new Map();
  const rebuiltMeshMap = new Map();

  function buildCleanMesh(srcMeshIdx, flipMirror = false, refName = "") {
    const isWhitePlastic = WHITE_PLASTIC_REFS.has(refName);
    const isMetalCan = METAL_CAN_REFS.has(refName);
    const matMode = isWhitePlastic ? "ivory" : isMetalCan ? "can" : "";
    const cacheKey = `${srcMeshIdx}:${flipMirror ? 1 : 0}:${matMode}`;
    if (rebuiltMeshMap.has(cacheKey)) return rebuiltMeshMap.get(cacheKey);
    const srcM = srcMeshes[srcMeshIdx];
    const rm = (srcM.name || "").match(boardRoleRe);
    const boardRole = rm ? rm[1] : null;
    if (boardRole === "copper" || boardRole === "soldermask" || boardRole === "silkscreen") {
      return null; // Flat PCB layers are baked into crisp 2048x2048 textures in app.js
    }

    const byMat = new Map();
    for (const p of srcM.primitives) {
      let mIdx = p.material ?? 0;
      if (isWhitePlastic || isMetalCan) {
        const rc = srcMats[mIdx]?.pbrMetallicRoughness?.baseColorFactor || [0, 0, 0];
        const rL = 0.2126 * rc[0] + 0.7152 * rc[1] + 0.0722 * rc[2];
        if (isWhitePlastic && rL > 0.70) mIdx = ivoryPlasticMatIdx;
        else if (isMetalCan && rL > 0.16 && rL <= 0.34) mIdx = metalCanMatIdx;
      }
      const pos = readAccessorArray(gltf, bin, p.attributes.POSITION);
      let norm = p.attributes.NORMAL !== undefined ? readAccessorArray(gltf, bin, p.attributes.NORMAL) : null;
      let idx = p.indices !== undefined ? readAccessorArray(gltf, bin, p.indices) : (() => {
        const a = new Uint32Array(pos.length / 3);
        for (let k = 0; k < a.length; k++) a[k] = k;
        return a;
      })();

      if (!norm) {
        norm = new Float32Array(pos.length);
        for (let k = 0; k < idx.length; k += 3) {
          const i0 = idx[k] * 3, i1 = idx[k + 1] * 3, i2 = idx[k + 2] * 3;
          const ax = pos[i1] - pos[i0], ay = pos[i1 + 1] - pos[i0 + 1], az = pos[i1 + 2] - pos[i0 + 2];
          const bx = pos[i2] - pos[i0], by = pos[i2 + 1] - pos[i0 + 1], bz = pos[i2 + 2] - pos[i0 + 2];
          let nx = ay * bz - az * by, ny = az * bx - ax * bz, nz = ax * by - ay * bx;
          const nl = Math.hypot(nx, ny, nz) || 1;
          nx /= nl; ny /= nl; nz /= nl;
          for (const vi of [i0, i1, i2]) { nArrSet(norm, vi, nx, ny, nz); }
        }
      }

      const posCopy = new Float32Array(pos);
      if (boardRole === "pad" || boardRole === "via") {
        idx = cullPadViaTriangles(posCopy, idx, boardRole);
      } else if (boardRole === "PCB") {
        for (let k = 1; k < posCopy.length; k += 3) {
          if (posCopy[k] < boardYMin) boardYMin = posCopy[k];
          if (posCopy[k] > boardYMax) boardYMax = posCopy[k];
        }
      }
      if (!idx.length) continue;

      const fixed = fixWindingAndNormals(posCopy, norm, idx, flipMirror);
      totalFixedTris += fixed.flipped;
      if (!byMat.has(mIdx)) byMat.set(mIdx, []);
      byMat.get(mIdx).push(fixed);
    }

    const mergedList = [];
    const h = crypto.createHash("sha1");
    for (const [mIdx, list] of [...byMat.entries()].sort((a, b) => a[0] - b[0])) {
      const m = mergeGeoms(list);
      mergedList.push({ mIdx, ...m });
      if (!boardRole) {
        h.update(String(mIdx) + ":");
        h.update(Buffer.from(m.positions.buffer, m.positions.byteOffset, m.positions.byteLength));
        h.update(Buffer.from(m.indices.buffer, m.indices.byteOffset, m.indices.byteLength));
      }
    }

    if (!boardRole) {
      const digest = matMode + ":" + h.digest("hex");
      if (dedupCache.has(digest)) {
        const cached = dedupCache.get(digest);
        rebuiltMeshMap.set(cacheKey, cached);
        return cached;
      }
      const prims = mergedList.flatMap((g) => gb.addOptimizedPrimitives(g.positions, g.normals, g.indices, g.mIdx, 200000));
      const newIdx = gb.addMesh(srcM.name || `mesh_${srcMeshIdx}`, prims);
      dedupCache.set(digest, newIdx);
      rebuiltMeshMap.set(cacheKey, newIdx);
      return newIdx;
    }

    const prims = mergedList.flatMap((g) => gb.addOptimizedPrimitives(g.positions, g.normals, g.indices, g.mIdx, 200000));
    const newIdx = gb.addMesh(`PCB_${boardRole}`, prims);
    rebuiltMeshMap.set(cacheKey, newIdx);
    return newIdx;
  }

  function nArrSet(arr, off, x, y, z) { arr[off] = x; arr[off + 1] = y; arr[off + 2] = z; }

  const existingRefs = new Set();
  function cloneNode(srcIdx, parentDet = 1, activeRef = "") {
    const sn = srcNodes[srcIdx];
    const refForNode = (WHITE_PLASTIC_REFS.has(sn.name) || METAL_CAN_REFS.has(sn.name)) ? sn.name : activeRef;
    const nd = {};
    if (sn.name) nd.name = sn.name;
    const localMat = mat4FromNode(sn);
    const localDet = det3(localMat);
    const worldDet = parentDet * localDet;

    if (localDet < 0 && sn.scale) {
      nd.scale = [Math.abs(sn.scale[0]), sn.scale[1], sn.scale[2]];
      if (sn.translation) nd.translation = sn.translation;
      if (sn.rotation) nd.rotation = sn.rotation;
    } else {
      if (sn.translation) nd.translation = sn.translation;
      if (sn.rotation) nd.rotation = sn.rotation;
      if (sn.scale) nd.scale = sn.scale;
      if (sn.matrix && localDet >= 0) nd.matrix = sn.matrix;
    }

    if (sn.mesh !== undefined) {
      const srcMName = (srcMeshes[sn.mesh] && srcMeshes[sn.mesh].name) || "";
      const rm = srcMName.match(boardRoleRe);
      if (rm) nd.name = `PCB_LAYER_${rm[1].toUpperCase()}`;
      const builtIdx = buildCleanMesh(sn.mesh, worldDet < 0, refForNode);
      if (builtIdx === null) return null;
      nd.mesh = builtIdx;
    }
    if (sn.children && sn.children.length) {
      const kids = [];
      for (const c of sn.children) {
        const cn = srcNodes[c];
        const cloned = cloneNode(c, worldDet, refForNode);
        if (cloned !== null) {
          if (cn.name) existingRefs.add(cn.name);
          kids.push(cloned);
        }
      }
      if (kids.length) nd.children = kids;
    }
    return gb.addNode(nd);
  }

  const outRootIdx = cloneNode(rootIdx, 1);
  const rootChildren = gb.nodes[outRootIdx].children || [];

  let addedVrml = 0;
  let addedProc = 0;
  for (const comp of compJson.components) {
    if (comp.model_source === "none") continue;
    let hasMesh = false;
    if (existingRefs.has(comp.ref)) {
      const n = gb.nodes.find((x) => x.name === comp.ref);
      const st = n ? [n] : [];
      while (st.length) {
        const cur = st.pop();
        if (cur.mesh !== undefined) { hasMesh = true; break; }
        for (const ci of cur.children || []) st.push(gb.nodes[ci]);
      }
    }
    if (comp.ref === "J1501" && !hasMesh) {
      const wrlPath = path.join(ROOT_DIR, "mech", "models3d", "USB_C_HRO_TYPE-C-31-E-17.wrl");
      if (fs.existsSync(wrlPath)) {
        const meshIdx = buildVrmlMesh(gb, wrlPath, "J1501");
        const radY = (-comp.rot_deg * Math.PI) / 180;
        rootChildren.push(gb.addNode({
          name: "J1501",
          translation: [comp.x_mm * 0.001, boardYMax + 0.00004, comp.y_mm * 0.001],
          rotation: [0, Math.sin(radY / 2), 0, Math.cos(radY / 2)],
          mesh: meshIdx,
        }));
        addedVrml++;
        continue;
      }
    }
    if (!hasMesh || comp.model_source === "procedural-replacement") {
      const meshIdx = addProceduralComponentMesh(gb, comp, procMats);
      // Center procedural model accurately at footprint bounding-box center
      const cx = (comp.bbox_board_mm[0] + comp.bbox_board_mm[2]) * 0.5;
      const cy = (comp.bbox_board_mm[1] + comp.bbox_board_mm[3]) * 0.5;
      const radY = (-comp.rot_deg * Math.PI) / 180;
      const yMount = comp.side === "bottom" ? boardYMin - 0.000085 : boardYMax + 0.00004;
      rootChildren.push(gb.addNode({
        name: comp.ref,
        translation: [cx * 0.001, yMount, cy * 0.001],
        rotation: [0, Math.sin(radY / 2), 0, Math.cos(radY / 2)],
        mesh: meshIdx,
      }));
      addedProc++;
    }
  }
  gb.nodes[outRootIdx].children = rootChildren;

  const outBoardPath = path.join(ASSETS_DIR, "board.glb");
  gb.save(outBoardPath, [outRootIdx]);
  const stat = fs.statSync(outBoardPath);
  console.log(
    `Built board.glb (${(stat.size / 1e6).toFixed(2)} MB, ${gb.meshes.length} meshes, fixed ${totalFixedTris} inverted tris, ${addedVrml} VRML, ${addedProc} centered procedural)`
  );
}

// ---------------------------------------------------------------------------
// 3. Build Upgraded Custom KV260 + K26 SOM Model Using KiCad STEP Connectors
// ---------------------------------------------------------------------------

function extractConnTemplates(glbPath) {
  if (!glbPath || !fs.existsSync(glbPath)) return new Map();
  const { gltf, bin } = readGlb(glbPath);
  const mats = (gltf.materials || []).map((m) => calibrateMaterial(m));
  const out = new Map();

  for (const rootIdx of gltf.scenes?.[0]?.nodes || []) {
    const rNode = gltf.nodes[rootIdx];
    const children = rNode.children || [rootIdx];
    for (const cIdx of children) {
      const nd = gltf.nodes[cIdx];
      const name = nd.name || "";
      if (!name.startsWith("CONN_")) continue;

      const byMat = [];
      let min = [Infinity, Infinity, Infinity], max = [-Infinity, -Infinity, -Infinity];
      function collect(ni, pm) {
        const cur = gltf.nodes[ni];
        const wm = mulMat4(pm, mat4FromNode(cur));
        if (cur.mesh !== undefined) {
          for (const p of gltf.meshes[cur.mesh].primitives) {
            const rawPos = readAccessorArray(gltf, bin, p.attributes.POSITION);
            const rawNrm = readAccessorArray(gltf, bin, p.attributes.NORMAL);
            const rawIdx = readAccessorArray(gltf, bin, p.indices);
            const pos = new Float32Array(rawPos.length);
            const norm = new Float32Array(rawNrm.length);
            for (let i = 0; i < rawPos.length; i += 3) {
              const x = rawPos[i], y = rawPos[i + 1], z = rawPos[i + 2];
              const vx = wm[0] * x + wm[4] * y + wm[8] * z + wm[12];
              const vy = wm[1] * x + wm[5] * y + wm[9] * z + wm[13];
              const vz = wm[2] * x + wm[6] * y + wm[10] * z + wm[14];
              pos[i] = vx; pos[i + 1] = vy; pos[i + 2] = vz;
              min[0] = Math.min(min[0], vx); min[1] = Math.min(min[1], vy); min[2] = Math.min(min[2], vz);
              max[0] = Math.max(max[0], vx); max[1] = Math.max(max[1], vy); max[2] = Math.max(max[2], vz);
              const nx = rawNrm[i], ny = rawNrm[i + 1], nz = rawNrm[i + 2];
              const nwx = wm[0] * nx + wm[4] * ny + wm[8] * nz;
              const nwy = wm[1] * nx + wm[5] * ny + wm[9] * nz;
              const nwz = wm[2] * nx + wm[6] * ny + wm[10] * nz;
              const nl = Math.hypot(nwx, nwy, nwz) || 1;
              norm[i] = nwx / nl; norm[i + 1] = nwy / nl; norm[i + 2] = nwz / nl;
            }
            const fixed = fixWindingAndNormals(pos, norm, rawIdx, det3(wm) < 0);
            const rawSrcMat = (gltf.materials || [])[p.material ?? 0];
            const rc = rawSrcMat?.pbrMetallicRoughness?.baseColorFactor || [0, 0, 0];
            const rL = 0.2126 * rc[0] + 0.7152 * rc[1] + 0.0722 * rc[2];
            const mat = (name === "CONN_J_FAN" && rL > 0.70)
              ? { name: "kv_ivory_plastic", pbrMetallicRoughness: { baseColorFactor: [0.24, 0.21, 0.16, 1.0], metallicFactor: 0.0, roughnessFactor: 0.54 } }
              : mats[p.material ?? 0];
            byMat.push({ mat, ...fixed });
          }
        }
        for (const ci of cur.children || []) collect(ci, wm);
      }
      // Compute local geometry relative to parent's translation so template is origin-centered
      const selfT = mat4FromNode({ ...nd, translation: [0, 0, 0] });
      for (const ci of nd.children || []) collect(ci, selfT);
      if (nd.mesh !== undefined) collect(cIdx, mat4FromNode({}));
      if (byMat.length) out.set(name, { parts: byMat, min, max });
    }
  }
  return out;
}

function fitTemplateIntoBox(gb, tmpl, targetBoxMm, rotDegY, matRemapCache) {
  // targetBoxMm in KV260 mm [x0, y0, x1, y1, z0, z1] -> glTF (X, Z, -Y) * 0.001
  const rad = (rotDegY * Math.PI) / 180;
  const c = Math.cos(rad), s = Math.sin(rad);
  const rotPt = (x, y, z) => [x * c + z * s, y, -x * s + z * c];

  let rMin = [Infinity, Infinity, Infinity], rMax = [-Infinity, -Infinity, -Infinity];
  const rotParts = tmpl.parts.map((pt) => {
    const pos = new Float32Array(pt.positions.length);
    const norm = new Float32Array(pt.normals.length);
    for (let i = 0; i < pos.length; i += 3) {
      const [rx, ry, rz] = rotPt(pt.positions[i], pt.positions[i + 1], pt.positions[i + 2]);
      pos[i] = rx; pos[i + 1] = ry; pos[i + 2] = rz;
      rMin[0] = Math.min(rMin[0], rx); rMin[1] = Math.min(rMin[1], ry); rMin[2] = Math.min(rMin[2], rz);
      rMax[0] = Math.max(rMax[0], rx); rMax[1] = Math.max(rMax[1], ry); rMax[2] = Math.max(rMax[2], rz);
      const [nx, ny, nz] = rotPt(pt.normals[i], pt.normals[i + 1], pt.normals[i + 2]);
      norm[i] = nx; norm[i + 1] = ny; norm[i + 2] = nz;
    }
    return { mat: pt.mat, positions: pos, normals: norm, indices: pt.indices };
  });

  const [x0, y0, x1, y1, z0, z1] = targetBoxMm;
  const tx0 = x0 * 0.001, tx1 = x1 * 0.001;
  const ty0 = z0 * 0.001, ty1 = z1 * 0.001;
  const tz0 = -y1 * 0.001, tz1 = -y0 * 0.001;

  const srcSpanX = Math.max(1e-5, rMax[0] - rMin[0]);
  const srcSpanY = Math.max(1e-5, rMax[1] - rMin[1]);
  const srcSpanZ = Math.max(1e-5, rMax[2] - rMin[2]);
  const sx = (tx1 - tx0) / srcSpanX;
  const sy = (ty1 - ty0) / srcSpanY;
  const sz = (tz1 - tz0) / srcSpanZ;

  return rotParts.map((pt) => {
    const pos = new Float32Array(pt.positions.length);
    for (let i = 0; i < pos.length; i += 3) {
      pos[i] = tx0 + (pt.positions[i] - rMin[0]) * sx;
      pos[i + 1] = ty0 + (pt.positions[i + 1] - rMin[1]) * sy;
      pos[i + 2] = tz0 + (pt.positions[i + 2] - rMin[2]) * sz;
    }
    const key = JSON.stringify(pt.mat.pbrMetallicRoughness);
    let matIdx = matRemapCache.get(key);
    if (matIdx === undefined) {
      matIdx = gb.materials.length;
      gb.materials.push(JSON.parse(JSON.stringify(pt.mat)));
      matRemapCache.set(key, matIdx);
    }
    return gb.addPrimitive(pos, pt.normals, pt.indices, matIdx, 0);
  });
}

function buildKv260Glb(compJson) {
  const connTemplates = extractConnTemplates(KV260_CONN_PATH);
  const gb = new GlbBuilder();
  const matCache = new Map();

  const mGreen = gb.addMaterial("kv_green", [0.006, 0.115, 0.015, 1.0], 0.0, 0.56);
  const mGold = gb.addMaterial("kv_gold", [0.86, 0.68, 0.36, 1.0], 0.96, 0.30);
  const mNickel = gb.addMaterial("kv_nickel", [0.58, 0.58, 0.57, 1.0], 0.92, 0.24);
  const mHeatsink = gb.addMaterial("kv_heatsink", [0.055, 0.060, 0.068, 1.0], 0.85, 0.34);
  const mFanPbt = gb.addMaterial("kv_fan_pbt", [0.030, 0.032, 0.036, 1.0], 0.0, 0.55);
  const mPlastic = gb.addMaterial("kv_plastic", [0.04, 0.042, 0.046, 1.0], 0.0, 0.52);
  const mIvory = gb.addMaterial("kv_ivory", [0.22, 0.20, 0.16, 1.0], 0.0, 0.50);
  const mSilicon = gb.addMaterial("kv_silicon", [0.16, 0.17, 0.18, 1.0], 0.4, 0.32);

  const addPartBox = (id, [x0, y0, x1, y1, z0, z1], matIdx, accentMat = null) => {
    const prims = [];
    const main = kvBoxMm(x0, x1, y0, y1, z0, z1);
    prims.push(gb.addPrimitive(main.positions, main.normals, main.indices, matIdx));
    if (accentMat !== null) {
      const trim = kvBoxMm(x0 + 0.4, x1 - 0.4, y0 + 0.4, y1 - 0.4, z1 - 0.25, z1 + 0.05);
      prims.push(gb.addPrimitive(trim.positions, trim.normals, trim.indices, accentMat));
    }
    return gb.addNode({ name: id, mesh: gb.addMesh(id, prims) });
  };

  const carrierChildren = [];
  // Carrier PCB body (-10..130, -10..109, -1.59..0.0) + gold mounting hole rings
  carrierChildren.push(addPartBox("KV260_CARRIER", [-10, -10, 130, 109, -1.59, 0.0], mGreen));
  const holeGeoms = [[-5, -5], [-5, 104], [125, -5], [125, 104]].map(([x, y]) =>
    createCylY(x * 0.001, -0.00165, 0.00012, -y * 0.001, 0.0031, 20)
  );
  const mergedHoles = mergeGeoms(holeGeoms);
  carrierChildren.push(gb.addNode({
    name: "KV260_MOUNT_PADS",
    mesh: gb.addMesh("KV260_MOUNT_PADS", [gb.addPrimitive(mergedHoles.positions, mergedHoles.normals, mergedHoles.indices, mGold)]),
  }));

  // Map carrier connectors to official KiCad STEP geometries (oriented toward board edge)
  const connPlacement = {
    KV260_J10_RJ45: { tmpl: "CONN_RJ45", rotY: 0 },
    KV260_J5_HDMI: { tmpl: "CONN_HDMI", rotY: 90 },
    KV260_J6_DP: { tmpl: "CONN_HDMI", rotY: 90 },
    KV260_J12_DC12V: { tmpl: "CONN_DC", rotY: -90 },
    KV260_J4_UART: { tmpl: "CONN_UUSB", rotY: 0 },
    KV260_J11_SD: { tmpl: "CONN_USD", rotY: 0 },
    KV260_J2_PMOD: { tmpl: "CONN_PMOD", rotY: 90 },
    KV260_J9_RPI: { tmpl: "CONN_J9", rotY: 0 },
    KV260_J_FAN: { tmpl: "CONN_FAN", rotY: 0 },
  };

  for (const p of compJson.kv260_parts) {
    if (p.subassembly !== "carrier" || p.id === "KV260_CARRIER") continue;
    const [x0, y0, x1, y1, z0, z1] = p.bbox_mm;
    if ((p.id === "KV260_U44_USB3" || p.id === "KV260_U46_USB3") && connTemplates.has("CONN_USBA")) {
      // Stacked dual USB 3.0 Type-A using two KiCad USB-A STEP models inside the stack bbox
      const tmpl = connTemplates.get("CONN_USBA");
      const zm = (z0 + z1) * 0.5;
      const prims = [
        ...fitTemplateIntoBox(gb, tmpl, [x0, y0, x1, y1, z0, zm - 0.3], 180, matCache),
        ...fitTemplateIntoBox(gb, tmpl, [x0, y0, x1, y1, zm + 0.3, z1], 180, matCache),
      ];
      carrierChildren.push(gb.addNode({ name: p.id, mesh: gb.addMesh(p.id, prims) }));
      continue;
    }
    const spec = connPlacement[p.id];
    if (spec && connTemplates.has(spec.tmpl)) {
      const prims = fitTemplateIntoBox(gb, connTemplates.get(spec.tmpl), p.bbox_mm, spec.rotY, matCache);
      carrierChildren.push(gb.addNode({ name: p.id, mesh: gb.addMesh(p.id, prims) }));
      continue;
    }
    const mat = p.id.includes("U27") ? mFanPbt : mPlastic;
    const acc = p.id.includes("U27") ? mSilicon : mGold;
    carrierChildren.push(addPartBox(p.id, [x0, y0, x1, y1, z0, z1], mat, acc));
  }

  carrierChildren.push(addPartBox("SOM240_1_CARRIER", [50.32, 25.57, 55.32, 68.39, 0.0, 2.6], mIvory, mGold));
  carrierChildren.push(addPartBox("SOM240_2_CARRIER", [116.3, 25.57, 121.3, 68.39, 0.0, 2.6], mIvory, mGold));
  const carrierGroup = gb.addNode({ name: "KV260_CARRIER_GROUP", children: carrierChildren });

  // Liftable K26 SOM group
  const somChildren = [];
  for (const p of compJson.kv260_parts) {
    if (p.subassembly !== "som") continue;
    const [x0, y0, x1, y1, z0, z1] = p.bbox_mm;
    if (p.id === "K26_SOM") {
      somChildren.push(addPartBox("K26_SOM", [x0, y0, x1, y1, z0, z1], mGreen));
    } else if (p.id === "K26_XCK26") {
      somChildren.push(addPartBox("K26_XCK26", [x0, y0, x1, y1, z0, z1 - 0.5], mGreen, mSilicon));
    } else if (p.id === "K26_DDR4") {
      const boxes = [67.18, 77.34, 87.50, 97.66].map((xs) => kvBoxMm(xs, xs + 7.5, y0, y1, z0, z1));
      const m = mergeGeoms(boxes);
      somChildren.push(gb.addNode({ name: "K26_DDR4", mesh: gb.addMesh("K26_DDR4", [gb.addPrimitive(m.positions, m.normals, m.indices, mFanPbt)]) }));
    } else if (p.id.startsWith("SOM240")) {
      somChildren.push(addPartBox(p.id, [x0, y0, x1, y1, 2.5, 5.0], mPlastic, mGold));
    } else {
      somChildren.push(addPartBox(p.id, [x0, y0, x1, y1, z0, z1], mFanPbt));
    }
  }
  const somGroup = gb.addNode({ name: "K26_SOM_GROUP", children: somChildren });

  // Finned Aluminum Heatsink (18 fins) + Sculpted 4010 Fan Shroud & 9 Blades
  const sinkFins = [kvBoxMm(52.43, 119.83, 20.78, 73.18, 5.81, 10.2)];
  const nFins = 18;
  for (let i = 0; i < nFins; i++) {
    const fy = 21.4 + (i * (72.3 - 21.4)) / (nFins - 1);
    sinkFins.push(kvBoxMm(52.43, 119.83, fy - 0.55, fy + 0.55, 10.2, 25.1));
  }
  const sinkGeom = mergeGeoms(sinkFins);
  const sinkNode = gb.addNode({
    name: "KV260_HEATSINK",
    mesh: gb.addMesh("KV260_HEATSINK", [gb.addPrimitive(sinkGeom.positions, sinkGeom.normals, sinkGeom.indices, mHeatsink)]),
  });

  const fanParts = [
    kvBoxMm(51.1, 121.1, 19.0, 22.0, 10.1, 26.8),
    kvBoxMm(51.1, 121.1, 72.0, 75.0, 10.1, 26.8),
    kvBoxMm(51.1, 56.0, 22.0, 72.0, 10.1, 26.8),
    kvBoxMm(116.2, 121.1, 22.0, 72.0, 10.1, 26.8),
    kvBoxMm(64.8, 107.4, 25.7, 30.0, 26.8, 28.75),
    kvBoxMm(64.8, 107.4, 64.0, 68.3, 26.8, 28.75),
    createCylY(0.08615, 0.0155, 0.0268, -0.047, 0.0085, 28),
  ];
  for (let b = 0; b < 9; b++) {
    const ang = (b * Math.PI * 2) / 9;
    const rx = 86.15 + Math.cos(ang) * 14.5;
    const ry = 47.0 + Math.sin(ang) * 14.5;
    fanParts.push(kvBoxMm(rx - 3.6, rx + 3.6, ry - 1.3, ry + 1.3, 17.5, 24.5));
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
  console.log(`Built kv260.glb (${(fs.statSync(outPath).size / 1e3).toFixed(1)} KB, ${connTemplates.size} KiCad STEP connector types)`);
}

// ---------------------------------------------------------------------------
// 4. Convert repo enclosure STLs with 30-degree Crease-Angle Smooth Normals
// ---------------------------------------------------------------------------

function readBinaryStlCreaseSmooth(stlPath, flipX180 = false, creaseDeg = 30) {
  const buf = fs.readFileSync(stlPath);
  const triCount = buf.readUInt32LE(80);
  const cosThresh = Math.cos((creaseDeg * Math.PI) / 180);

  // 1. Parse raw vertices per triangle corner, mapping Blender mm (X, Y, Z) -> glTF metres (X, Z, -Y)
  const rawPts = [];
  const rawKeys = [];
  const faceNorms = new Float32Array(triCount * 3);
  const unitFaceNorms = new Float32Array(triCount * 3);
  const incidentTris = new Map();

  let actualTris = 0;
  for (let t = 0; t < triCount; t++) {
    const off = 84 + t * 50;
    if (off + 50 > buf.length) break;
    const triPts = [];
    const triKeys = [];
    for (let c = 0; c < 3; c++) {
      const vo = off + 12 + c * 12;
      const rx = buf.readFloatLE(vo);
      const ry0 = buf.readFloatLE(vo + 4);
      const rz0 = buf.readFloatLE(vo + 8);
      const ry = flipX180 ? -ry0 : ry0;
      const rz = flipX180 ? -rz0 : rz0;
      const gx = rx * 0.001, gy = rz * 0.001, gz = -ry * 0.001;
      const key = `${Math.round(rx * 200)},${Math.round(ry * 200)},${Math.round(rz * 200)}`;
      triPts.push(gx, gy, gz);
      triKeys.push(key);
    }
    const ax = triPts[3] - triPts[0], ay = triPts[4] - triPts[1], az = triPts[5] - triPts[2];
    const bx = triPts[6] - triPts[0], by = triPts[7] - triPts[1], bz = triPts[8] - triPts[2];
    const nx = ay * bz - az * by, ny = az * bx - ax * bz, nz = ax * by - ay * bx;
    const len = Math.hypot(nx, ny, nz);
    if (len < 1e-13) continue;

    const ti = actualTris++;
    faceNorms[ti * 3] = nx; faceNorms[ti * 3 + 1] = ny; faceNorms[ti * 3 + 2] = nz;
    unitFaceNorms[ti * 3] = nx / len; unitFaceNorms[ti * 3 + 1] = ny / len; unitFaceNorms[ti * 3 + 2] = nz / len;
    rawPts.push(...triPts);
    rawKeys.push(...triKeys);
    for (let c = 0; c < 3; c++) {
      const k = triKeys[c];
      let arr = incidentTris.get(k);
      if (!arr) { arr = []; incidentTris.set(k, arr); }
      arr.push(ti);
    }
  }

  // 2. Smooth normals across edges with dihedral angle <= creaseDeg, keeping sharp corners crisp
  const vMap = new Map();
  const outPos = [], outNorm = [], outIdx = [];
  for (let ti = 0; ti < actualTris; ti++) {
    const unx = unitFaceNorms[ti * 3], uny = unitFaceNorms[ti * 3 + 1], unz = unitFaceNorms[ti * 3 + 2];
    for (let c = 0; c < 3; c++) {
      const ci = ti * 3 + c;
      const gx = rawPts[ci * 3], gy = rawPts[ci * 3 + 1], gz = rawPts[ci * 3 + 2];
      const pKey = rawKeys[ci];
      const inc = incidentTris.get(pKey);
      let sx = 0, sy = 0, sz = 0;
      for (let k = 0; k < inc.length; k++) {
        const oti = inc[k];
        const dot = unx * unitFaceNorms[oti * 3] + uny * unitFaceNorms[oti * 3 + 1] + unz * unitFaceNorms[oti * 3 + 2];
        if (dot >= cosThresh) {
          sx += faceNorms[oti * 3];
          sy += faceNorms[oti * 3 + 1];
          sz += faceNorms[oti * 3 + 2];
        }
      }
      const sl = Math.hypot(sx, sy, sz) || 1;
      sx /= sl; sy /= sl; sz /= sl;

      const vKey = `${pKey}|${Math.round(sx * 48)},${Math.round(sy * 48)},${Math.round(sz * 48)}`;
      let vi = vMap.get(vKey);
      if (vi === undefined) {
        vi = outPos.length / 3;
        vMap.set(vKey, vi);
        outPos.push(gx, gy, gz);
        outNorm.push(sx, sy, sz);
      }
      outIdx.push(vi);
    }
  }

  const vCount = outPos.length / 3;
  return {
    positions: new Float32Array(outPos),
    normals: new Float32Array(outNorm),
    indices: vCount > 65535 ? new Uint32Array(outIdx) : new Uint16Array(outIdx),
  };
}

function buildFinnedHeatsinkGeom(cx, cy, z0, sx, sy, sz, nFins) {
  const padT = 0.18;
  const baseH = Math.min(1.4, sz * 0.28);
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
  const mPetg = gb.addMaterial("petg_cf", [0.028, 0.030, 0.035, 1.0], 0.04, 0.70);
  const mTpu = gb.addMaterial("tpu_95a", [0.74, 0.31, 0.05, 1.0], 0.0, 0.58);
  const mHsBlack = gb.addMaterial("hs_black_al", [0.05, 0.055, 0.062, 1.0], 0.88, 0.36);
  const mHsBlue = gb.addMaterial("hs_blue_al", [0.03, 0.09, 0.24, 1.0], 0.88, 0.35);
  const mHsCopper = gb.addMaterial("hs_copper", [0.55, 0.22, 0.09, 1.0], 0.92, 0.32);
  const mFanPbt = gb.addMaterial("od5015_pbt", [0.034, 0.036, 0.040, 1.0], 0.0, 0.55);

  const stlFiles = [
    { name: "CASE_BOTTOM", file: "case_v2_bottom.stl", mat: mPetg, group: "bottom", flipX180: false },
    { name: "CASE_LID", file: "case_v2_lid.stl", mat: mPetg, group: "lid", flipX180: true },
    { name: "CASE_FILTER_FRAME", file: "case_v2_filter_frame.stl", mat: mPetg, group: "lid", flipX180: false },
    { name: "CASE_GROMMET", file: "case_grommet.stl", mat: mTpu, group: "lid", flipX180: false, translateM: [-0.003528, 0.03275, -0.005004] },
    { name: "CASE_BUMPER_LF", file: "case_bumper_lfront.stl", mat: mTpu, group: "bumpers", flipX180: false },
    { name: "CASE_BUMPER_RF", file: "case_bumper_rfront.stl", mat: mTpu, group: "bumpers", flipX180: false },
    { name: "CASE_BUMPER_LB", file: "case_bumper_lback.stl", mat: mTpu, group: "bumpers", flipX180: false },
    { name: "CASE_BUMPER_RB", file: "case_bumper_rback.stl", mat: mTpu, group: "bumpers", flipX180: false },
  ];

  const lidNodes = [], bottomNodes = [], bumperNodes = [];
  for (const s of stlFiles) {
    const p = path.join(ROOT_DIR, "mech", s.file);
    if (!fs.existsSync(p)) continue;
    const g = readBinaryStlCreaseSmooth(p, s.flipX180, 30);
    const prims = gb.addOptimizedPrimitives(g.positions, g.normals, g.indices, s.mat, 0);
    const nodeObj = { name: s.name, mesh: gb.addMesh(s.name, prims) };
    if (s.translateM) nodeObj.translation = s.translateM;
    const ni = gb.addNode(nodeObj);
    if (s.group === "lid") lidNodes.push(ni);
    else if (s.group === "bottom") bottomNodes.push(ni);
    else bumperNodes.push(ni);
  }

  // OD5015 50x50x15 mm intake fan inside the v2 lid at (-40, 14) mm
  const fx = -40.0, fy = 14.0;
  const fanGeoms = [
    kvBoxMm(fx - 25, fx + 25, fy - 25, fy - 22, 13.75, 28.75),
    kvBoxMm(fx - 25, fx + 25, fy + 22, fy + 25, 13.75, 28.75),
    kvBoxMm(fx - 25, fx - 22, fy - 22, fy + 22, 13.75, 28.75),
    kvBoxMm(fx + 22, fx + 25, fy - 22, fy + 22, 13.75, 28.75),
    createCylY(fx * 0.001, 0.01475, 0.02815, -fy * 0.001, 0.0105, 24),
  ];
  for (let b = 0; b < 9; b++) {
    const ang = (b * Math.PI * 2) / 9;
    const bx = fx + Math.cos(ang) * 16.0;
    const by = fy + Math.sin(ang) * 16.0;
    fanGeoms.push(kvBoxMm(bx - 4.0, bx + 4.0, by - 1.3, by + 1.3, 17.0, 26.0));
  }
  const fMerged = mergeGeoms(fanGeoms);
  lidNodes.push(gb.addNode({
    name: "FAN2_5015",
    mesh: gb.addMesh("FAN2_5015", [gb.addPrimitive(fMerged.positions, fMerged.normals, fMerged.indices, mFanPbt)]),
  }));

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

  const root = gb.addNode({
    name: "ENCLOSURE_ROOT",
    children: [
      gb.addNode({ name: "ENCLOSURE_BOTTOM_GROUP", children: bottomNodes }),
      gb.addNode({ name: "ENCLOSURE_LID_GROUP", children: lidNodes }),
      gb.addNode({ name: "ENCLOSURE_BUMPERS_GROUP", children: bumperNodes }),
      gb.addNode({ name: "ADAPTER_HEATSINKS_GROUP", children: hsNodes }),
    ],
  });
  const outPath = path.join(ASSETS_DIR, "enclosure.glb");
  gb.save(outPath, [root]);
  console.log(`Built enclosure.glb (${(fs.statSync(outPath).size / 1e6).toFixed(2)} MB, 30-deg crease smooth STL meshes + HS1..HS4 + OD5015)`);
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------
const compJson = JSON.parse(fs.readFileSync(path.join(ASSETS_DIR, "components.json"), "utf8"));
buildBoardGlb(compJson);
buildKv260Glb(compJson);
buildEnclosureGlb();
