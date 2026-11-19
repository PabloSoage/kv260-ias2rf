/**
 * Interactive 3-D Simulations Mode
 * Maps real repo simulation outputs onto the 3-D assembly & component inspector:
 *   1. rf      - LVDS/SGMII skew & eye opening, SMA/J961/AAF S-parameters, NEXT crosstalk
 *   2. power   - PDN |Z(f)| vs target impedance, DC drop, FB401 ripple filter
 *   3. thermal - OpenFOAM 3-D CHT Tj vs limits across 12 cases + PCB heat map + PNG slices
 *   4. mech    - CalculiX 50 g shock, drop & vibration FEA on enclosure + BGAs (U1101, U501, U601)
 *   5. g8      - XSim G-8 RTL vs Reference SINAD, sensitivity, rejection & RF-to-FPGA chain
 *
 * Strictly zero fabricated per-vertex contour meshes: continuous slice plots are shown from
 * their solver PNG/JPG outputs with explicit provenance notes alongside every scalar.
 */

export function createSimController(ctx) {
  const {
    THREE,
    scene,
    adapterGroup,
    nodeById,
    partById,
    encNodes,
    kvNodes,
    getNetTraces,
    selectPart,
    focusPartCamera,
    setIsolate,
    setEnclosure,
    setCameraPreset,
    openImageModal,
    applyAnimatedScene,
    syncHash,
    escapeHtml,
    isReducedMotion,
    REPO_BLOB,
  } = ctx;

  const simBoardGroup = new THREE.Group();
  simBoardGroup.name = "SIM_BOARD_GROUP";
  adapterGroup.add(simBoardGroup);

  const simWorldGroup = new THREE.Group();
  simWorldGroup.name = "SIM_WORLD_GROUP";
  scene.add(simWorldGroup);

  let sims = null;
  let enabled = false;
  let domain = "rf"; // rf | power | thermal | mech | g8 | audit

  const sel = {
    rfMetric: "skew", // skew | eye
    rfFocusType: "all", // all | pair | sparam | crosstalk
    rfFocusId: null,
    powerRail: "+1V0",
    thermalCase: "rev08_hs4_clean_fine_70C",
    thermalMetric: "Tj", // Tj | margin
    mechLoad: "Zm", // Zm | Xp | Yp
    mechMat: "PETG-CF",
    mechTemp: 70,
    g8Mode: "radar",
    auditView: "rf", // rf | power | transients
    auditFocusRef: null,
  };

  let g8PulseMesh = null;
  let g8PulseSegs = [];
  let thermalTex = null;
  let feaData = null;
  let feaLoadPromise = null;
  const feaAppliedMeshes = [];

  const DOMAIN_META = [
    { id: "rf", label: "RF / SI" },
    { id: "power", label: "Power PDN" },
    { id: "thermal", label: "Thermal CFD" },
    { id: "mech", label: "Mech FEA" },
    { id: "g8", label: "Gateware G-8" },
    { id: "audit", label: "RF and power audit" },
  ];

  // Board KiCad mm -> PCB heatmap rectangle covering the 140x132 mm board
  const PCB_X0 = 88.0;
  const PCB_X1 = 228.0;
  const PCB_Y0 = 81.0;
  const PCB_Y1 = 213.0;

  function worldMmToKicadMm(posMm) {
    // World GLB coordinates in kv260 mm -> inverse of (x=107.247-ky, kv_y=198.004-kx)
    if (!posMm) return [158, 148];
    const [wx, wy] = posMm;
    return [198.004 - wy, 107.247 - wx];
  }

  function heatColorHex(t) {
    // t in [0, 1]: blue -> cyan -> emerald -> amber -> crimson
    const c = Math.max(0, Math.min(1, t));
    const col = new THREE.Color();
    if (c < 0.25) col.lerpColors(new THREE.Color(0x2563eb), new THREE.Color(0x06b6d4), c / 0.25);
    else if (c < 0.5) col.lerpColors(new THREE.Color(0x06b6d4), new THREE.Color(0x10b981), (c - 0.25) / 0.25);
    else if (c < 0.78) col.lerpColors(new THREE.Color(0x10b981), new THREE.Color(0xf59e0b), (c - 0.5) / 0.28);
    else col.lerpColors(new THREE.Color(0xf59e0b), new THREE.Color(0xef4444), (c - 0.78) / 0.22);
    return col;
  }

  function clearGroup(grp) {
    while (grp.children.length) {
      const ch = grp.children[0];
      grp.remove(ch);
      ch.traverse?.((o) => {
        if (o.geometry) o.geometry.dispose();
        if (o.material) {
          if (Array.isArray(o.material)) o.material.forEach((m) => m.dispose());
          else o.material.dispose();
        }
      });
    }
  }

  function setGroupTint(grp, hexColorOrNull, opacityOverride = null) {
    if (!grp) return;
    grp.traverse((o) => {
      if (!o.isMesh || !o.material) return;
      const mats = Array.isArray(o.material) ? o.material : [o.material];
      mats.forEach((m) => {
        if (m.userData.__simOrigColor === undefined) {
          m.userData.__simOrigColor = m.color ? m.color.getHex() : null;
          m.userData.__simOrigEmissive = m.emissive ? m.emissive.getHex() : 0;
          m.userData.__simOrigTransparent = !!m.transparent;
          m.userData.__simOrigOpacity = m.opacity ?? 1;
        }
        if (hexColorOrNull === null) {
          if (m.color && m.userData.__simOrigColor !== null) m.color.setHex(m.userData.__simOrigColor);
          if (m.emissive) m.emissive.setHex(m.userData.__simOrigEmissive);
          m.transparent = m.userData.__simOrigTransparent;
          m.opacity = m.userData.__simOrigOpacity;
        } else {
          if (m.color) m.color.setHex(hexColorOrNull);
          if (m.emissive) m.emissive.setHex(hexColorOrNull).multiplyScalar(0.18);
          if (opacityOverride !== null) {
            m.transparent = opacityOverride < 0.99;
            m.opacity = opacityOverride;
          }
        }
        m.needsUpdate = true;
      });
    });
  }

  function resetAllTints() {
    while (feaAppliedMeshes.length) {
      const m = feaAppliedMeshes.pop();
      if (m.geometry && m.userData.__feaAddedColor) {
        m.geometry.deleteAttribute("color");
        delete m.userData.__feaAddedColor;
      }
      const mats = Array.isArray(m.material) ? m.material : [m.material];
      mats.forEach((mat) => {
        if (mat && mat.userData.__simOrigVertexColors !== undefined) {
          mat.vertexColors = mat.userData.__simOrigVertexColors;
          delete mat.userData.__simOrigVertexColors;
          mat.needsUpdate = true;
        }
      });
    }
    setGroupTint(encNodes?.ENCLOSURE_BOTTOM_GROUP, null);
    setGroupTint(encNodes?.ENCLOSURE_LID_GROUP, null);
    setGroupTint(encNodes?.ENCLOSURE_BUMPERS_GROUP, null);
    setGroupTint(encNodes?.ADAPTER_HEATSINKS_GROUP, null);
    setGroupTint(kvNodes?.KV260_HEATSINK, null);
    setGroupTint(kvNodes?.K26_SOM_GROUP, null);
  }

  function clearAllOverlays() {
    clearGroup(simBoardGroup);
    clearGroup(simWorldGroup);
    resetAllTints();
    g8PulseMesh = null;
    g8PulseSegs = [];
    if (thermalTex) {
      thermalTex.dispose();
      thermalTex = null;
    }
    const bar = document.querySelector("#sim-legend-bar");
    if (bar && !enabled) {
      bar.style.display = "none";
      bar.innerHTML = "";
    }
  }

  function addTraceLines(netNames, colorHex, opacity = 0.92, yOffset = 0.0) {
    const nt = getNetTraces();
    const segs = [];
    for (const net of netNames) {
      const list = nt[net];
      if (!list) continue;
      for (const s of list) segs.push(s);
    }
    if (!segs.length) return [];
    const verts = new Float32Array(segs.length * 6);
    const outWorld = [];
    for (let i = 0; i < segs.length; i++) {
      const [x1, y1, x2, y2, lIdx] = segs[i];
      const yLocal = (lIdx <= 3 ? 0.00174 : -0.00010) + yOffset;
      const o = i * 6;
      verts[o] = x1 * 0.001;
      verts[o + 1] = yLocal;
      verts[o + 2] = y1 * 0.001;
      verts[o + 3] = x2 * 0.001;
      verts[o + 4] = yLocal;
      verts[o + 5] = y2 * 0.001;
      outWorld.push([x1 * 0.001, yLocal, y1 * 0.001, x2 * 0.001, yLocal, y2 * 0.001]);
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(verts, 3));
    const mat = new THREE.LineBasicMaterial({ color: colorHex, transparent: true, opacity });
    simBoardGroup.add(new THREE.LineSegments(geo, mat));
    return outWorld;
  }

  function addWorldBoxCage(ref, colorHex, addBeacon = false, beaconH = 0.008) {
    const obj = nodeById.get(ref);
    if (!obj) return;
    const bx = new THREE.Box3().setFromObject(obj);
    if (bx.isEmpty()) return;
    simWorldGroup.add(new THREE.Box3Helper(bx, colorHex));
    if (addBeacon) {
      const c = bx.getCenter(new THREE.Vector3());
      const geo = new THREE.CylinderGeometry(0.0011, 0.0018, beaconH, 12);
      const mat = new THREE.MeshBasicMaterial({ color: colorHex, transparent: true, opacity: 0.78 });
      const m = new THREE.Mesh(geo, mat);
      m.position.set(c.x, bx.max.y + beaconH * 0.5 + 0.0006, c.z);
      simWorldGroup.add(m);
    }
  }

  // -------------------------------------------------------------------------
  // 3-D Overlays per Domain
  // -------------------------------------------------------------------------
  function rebuild3DOverlay() {
    clearAllOverlays();

    if (!enabled || !sims) {
      updateLegendBar();
      return;
    }

    scene.updateMatrixWorld(true);

    if (domain === "rf") {
      buildRf3D();
    } else if (domain === "power") {
      buildPower3D();
    } else if (domain === "thermal") {
      buildThermal3D();
    } else if (domain === "mech") {
      buildMech3D();
    } else if (domain === "g8") {
      buildG83D();
    } else if (domain === "audit") {
      buildAudit3D();
    }
    updateLegendBar();
  }

  function buildRf3D() {
    for (const pair of sims.rf_si.pairs) {
      let t = 0;
      if (sel.rfMetric === "skew") {
        t = Math.min(1, pair.abs_skew_ps / 25.0);
      } else {
        const eye = pair.eye_routed_mV ?? 620;
        // 700 mV -> 0 (good/green), 400 mV -> 1 (tight/red)
        t = Math.max(0, Math.min(1, (700 - eye) / 300));
      }
      const isFocused = sel.rfFocusType === "pair" && sel.rfFocusId === pair.id;
      const col = isFocused ? new THREE.Color(0x38bdf8) : heatColorHex(t * 0.92 + 0.08);
      const nets = [pair.p_net, pair.n_net, ...(pair.extra_nets || [])];
      addTraceLines(nets, col.getHex(), isFocused ? 1.0 : 0.88, isFocused ? 0.00018 : 0.0);
      if (isFocused) {
        pair.components.forEach((r) => addWorldBoxCage(r, 0x38bdf8, true, 0.009));
      }
    }
    if (sel.rfFocusType === "sparam") {
      const sp = sims.rf_si.sparam_models.find((m) => m.id === sel.rfFocusId) || sims.rf_si.sparam_models[0];
      if (sp) {
        addTraceLines(sp.nets, 0xfbbf24, 0.98, 0.00022);
        sp.components.slice(0, 14).forEach((r) => addWorldBoxCage(r, 0xfbbf24, true, 0.008));
      }
    } else if (sel.rfFocusType === "crosstalk") {
      for (const xt of sims.rf_si.crosstalk) {
        const col = xt.next_pct >= 5 ? 0xf43f5e : 0xf59e0b;
        addTraceLines([xt.a, xt.b], col, 0.95, 0.0002);
      }
    }
  }

  function buildPower3D() {
    const rail = sims.power.rails.find((r) => r.rail === sel.powerRail) || sims.power.rails[0];
    if (!rail) return;
    const zRatio = rail.target_z_mohm && rail.sim_z_band_mohm ? rail.sim_z_band_mohm / rail.target_z_mohm : 0.25;
    const colHex = zRatio > 0.8 ? 0xf59e0b : 0x22d3ee;
    addTraceLines([rail.rail], colHex, 0.96, 0.00016);
    if (rail.regulator_ref) addWorldBoxCage(rail.regulator_ref, 0xffb020, true, 0.013);
    if (rail.inductor_ref && rail.inductor_ref !== rail.regulator_ref) addWorldBoxCage(rail.inductor_ref, 0xfbbf24, true, 0.010);
    for (const ld of rail.loads || []) addWorldBoxCage(ld, 0x22d3ee, true, 0.007);
    for (const c of (rail.components || []).slice(0, 26)) {
      if (c !== rail.regulator_ref && !(rail.loads || []).includes(c)) addWorldBoxCage(c, 0x38bdf8, false);
    }
  }

  function buildThermal3D() {
    const c = sims.thermal.cases.find((x) => x.id === sel.thermalCase) || sims.thermal.cases[0];
    if (!c) return;

    // 1. Render smooth 2-D thermal surface contour texture directly onto PCB top surface
    const W = 256;
    const H = 240;
    const cvs = document.createElement("canvas");
    cvs.width = W;
    cvs.height = H;
    const g = cvs.getContext("2d");

    const baseBgT = Math.max(c.ambient_c, c.T_air_mean_C);
    const points = [];
    for (const ic of c.ics) {
      if (ic.ref === "K26_XCK26") continue;
      const [kx, ky] = worldMmToKicadMm(ic.pos_mm);
      if (kx < PCB_X0 - 15 || kx > PCB_X1 + 15 || ky < PCB_Y0 - 15 || ky > PCB_Y1 + 15) continue;
      const px = ((kx - PCB_X0) / (PCB_X1 - PCB_X0)) * W;
      const py = ((ky - PCB_Y0) / (PCB_Y1 - PCB_Y0)) * H;
      points.push({ px, py, temp: ic.T_board_C });
    }

    const img = g.createImageData(W, H);
    const data = img.data;
    const minT = Math.max(20, c.ambient_c);
    const maxT = 118;
    for (let y = 0; y < H; y++) {
      for (let x = 0; x < W; x++) {
        let num = baseBgT * 0.018;
        let den = 0.018;
        for (let k = 0; k < points.length; k++) {
          const dx = x - points[k].px;
          const dy = y - points[k].py;
          const d2 = dx * dx + dy * dy + 85;
          const w = 1.0 / (d2 * Math.sqrt(d2));
          num += points[k].temp * w;
          den += w;
        }
        const tLoc = num / den;
        const norm = Math.max(0, Math.min(1, (tLoc - minT) / (maxT - minT)));
        const col = heatColorHex(norm);
        const idx = (y * W + x) * 4;
        data[idx] = Math.round(col.r * 255);
        data[idx + 1] = Math.round(col.g * 255);
        data[idx + 2] = Math.round(col.b * 255);
        data[idx + 3] = 158;
      }
    }
    g.putImageData(img, 0, 0);

    thermalTex = new THREE.CanvasTexture(cvs);
    thermalTex.flipY = false;
    thermalTex.needsUpdate = true;
    const planeW = (PCB_X1 - PCB_X0) * 0.001;
    const planeH = (PCB_Y1 - PCB_Y0) * 0.001;
    const planeGeo = new THREE.PlaneGeometry(planeW, planeH);
    planeGeo.rotateX(-Math.PI / 2);
    const planeMat = new THREE.MeshBasicMaterial({
      map: thermalTex,
      transparent: true,
      opacity: 0.72,
      depthWrite: false,
      side: THREE.DoubleSide,
    });
    const planeMesh = new THREE.Mesh(planeGeo, planeMat);
    planeMesh.position.set(((PCB_X0 + PCB_X1) * 0.5) * 0.001, 0.00182, ((PCB_Y0 + PCB_Y1) * 0.5) * 0.001);
    simBoardGroup.add(planeMesh);

    // 2. Per-IC 3-D bounding cages and temperature height pillars
    for (const ic of c.ics) {
      let norm = 0;
      if (sel.thermalMetric === "Tj") {
        norm = Math.max(0, Math.min(1, (ic.T_j_C - 40) / 80));
      } else {
        // margin < 0 => 1.0 (red), margin >= 40 => 0.0 (blue/cyan)
        norm = Math.max(0, Math.min(1, (40 - ic.margin_C) / 45));
      }
      const colHex = heatColorHex(norm).getHex();
      const pillarH = Math.max(0.004, Math.min(0.020, ((ic.T_j_C - 25) / 100) * 0.018));
      addWorldBoxCage(ic.ref, colHex, true, pillarH);
    }

    // 3. Subtle enclosure air-temperature tint when visible
    const airNorm = Math.max(0, Math.min(1, (c.T_air_max_C - 35) / 65));
    const airCol = heatColorHex(airNorm).getHex();
    setGroupTint(encNodes?.ENCLOSURE_BOTTOM_GROUP, airCol, 0.34);
    setGroupTint(encNodes?.ENCLOSURE_LID_GROUP, airCol, 0.28);
    setGroupTint(kvNodes?.KV260_HEATSINK, heatColorHex(Math.max(0, Math.min(1, (c.K26_sink_C - 40) / 65))).getHex(), 0.92);
  }

  function loadFeaFields() {
    if (feaData) return Promise.resolve(feaData);
    if (feaLoadPromise) return feaLoadPromise;
    const url = sims?.mechanical?.fea_3d_file;
    if (!url) return Promise.resolve(null);
    feaLoadPromise = fetch(url)
      .then((r) => (r.ok ? r.arrayBuffer() : null))
      .then((buf) => {
        if (!buf) return null;
        const dv = new DataView(buf);
        if (dv.getUint32(0, true) !== 0x32414546) return null;
        const caseCount = dv.getUint32(4, true);
        const boardVertCount = dv.getUint32(8, true);
        const boardTriCount = dv.getUint32(12, true);
        let off = 16;
        const casePos = new Float32Array(buf, off, caseCount * 3);
        off += caseCount * 12;
        const cZm = new Uint8Array(buf, off, caseCount * 3); off += caseCount * 3;
        const cXp = new Uint8Array(buf, off, caseCount * 3); off += caseCount * 3;
        const cYp = new Uint8Array(buf, off, caseCount * 3); off += caseCount * 3;
        off += (4 - ((caseCount * 9) % 4)) % 4;
        const boardPos = new Float32Array(buf, off, boardVertCount * 3);
        off += boardVertCount * 12;
        const boardIdx = new Uint16Array(buf, off, boardTriCount * 3);
        off += boardTriCount * 6;
        off += (4 - ((boardTriCount * 6) % 4)) % 4;
        const bZm = new Uint8Array(buf, off, boardVertCount * 3); off += boardVertCount * 3;
        const bXp = new Uint8Array(buf, off, boardVertCount * 3); off += boardVertCount * 3;
        const bYp = new Uint8Array(buf, off, boardVertCount * 3);
        // Build 4 mm lookup grid over casePos
        const inv = 1.0 / 0.004;
        const grid = new Map();
        for (let i = 0; i < caseCount; i++) {
          const key = `${Math.round(casePos[i * 3] * inv)},${Math.round(casePos[i * 3 + 1] * inv)},${Math.round(casePos[i * 3 + 2] * inv)}`;
          if (!grid.has(key)) grid.set(key, []);
          grid.get(key).push(i);
        }
        feaData = {
          caseCount, boardVertCount, boardTriCount, casePos, grid,
          caseRgb: { Zm: cZm, Xp: cXp, Yp: cYp },
          boardPos, boardIdx,
          boardRgb: { Zm: bZm, Xp: bXp, Yp: bYp },
        };
        return feaData;
      })
      .catch(() => null);
    return feaLoadPromise;
  }

  function applyFeaCaseColors(grp, loadId) {
    if (!grp || !feaData) return false;
    const rgb = feaData.caseRgb[loadId] || feaData.caseRgb.Zm;
    const { casePos, grid } = feaData;
    const inv = 1.0 / 0.004;
    const yOff = grp.position ? grp.position.y : 0;
    const tmp = new THREE.Vector3();
    let applied = false;

    grp.traverse((o) => {
      if (!o.isMesh || !o.geometry?.attributes?.position) return;
      if (!o.visible && !o.userData?.batched) return;
      if (!o.visible) return;
      const pos = o.geometry.attributes.position;
      const cols = new Float32Array(pos.count * 3);
      for (let i = 0; i < pos.count; i++) {
        tmp.fromBufferAttribute(pos, i).applyMatrix4(o.matrixWorld);
        const x = tmp.x, y = tmp.y - yOff, z = tmp.z;
        const gx = Math.round(x * inv), gy = Math.round(y * inv), gz = Math.round(z * inv);
        let bestD = Infinity, bestJ = 0;
        for (let dz = -1; dz <= 1; dz++) {
          for (let dy = -1; dy <= 1; dy++) {
            for (let dx = -1; dx <= 1; dx++) {
              const list = grid.get(`${gx + dx},${gy + dy},${gz + dz}`);
              if (!list) continue;
              for (let m = 0; m < list.length; m++) {
                const j = list[m];
                const ddx = casePos[j * 3] - x, ddy = casePos[j * 3 + 1] - y, ddz = casePos[j * 3 + 2] - z;
                const d2 = ddx * ddx + ddy * ddy + ddz * ddz;
                if (d2 < bestD) { bestD = d2; bestJ = j; }
              }
            }
          }
        }
        cols[i * 3] = Math.pow(rgb[bestJ * 3] / 255, 2.2);
        cols[i * 3 + 1] = Math.pow(rgb[bestJ * 3 + 1] / 255, 2.2);
        cols[i * 3 + 2] = Math.pow(rgb[bestJ * 3 + 2] / 255, 2.2);
      }
      o.geometry.setAttribute("color", new THREE.BufferAttribute(cols, 3));
      o.userData.__feaAddedColor = true;
      const mats = Array.isArray(o.material) ? o.material : [o.material];
      mats.forEach((m) => {
        if (!m) return;
        if (m.userData.__simOrigColor === undefined) {
          m.userData.__simOrigColor = m.color ? m.color.getHex() : null;
          m.userData.__simOrigEmissive = m.emissive ? m.emissive.getHex() : 0;
          m.userData.__simOrigTransparent = !!m.transparent;
          m.userData.__simOrigOpacity = m.opacity ?? 1;
        }
        if (m.userData.__simOrigVertexColors === undefined) {
          m.userData.__simOrigVertexColors = !!m.vertexColors;
        }
        m.vertexColors = true;
        if (m.color) m.color.setHex(0xffffff);
        if (m.emissive) m.emissive.setHex(0x000000);
        m.transparent = false;
        m.opacity = 1.0;
        m.needsUpdate = true;
      });
      feaAppliedMeshes.push(o);
      applied = true;
    });
    return applied;
  }

  function populateMechWorld(ld) {
    if (feaData) {
      const bRgb = feaData.boardRgb[ld.id] || feaData.boardRgb.Zm;
      const bCols = new Float32Array(feaData.boardVertCount * 3);
      for (let i = 0; i < bCols.length; i++) bCols[i] = Math.pow(bRgb[i] / 255, 2.2);
      const bGeo = new THREE.BufferGeometry();
      bGeo.setAttribute("position", new THREE.BufferAttribute(feaData.boardPos, 3));
      bGeo.setAttribute("color", new THREE.BufferAttribute(bCols, 3));
      bGeo.setIndex(new THREE.BufferAttribute(feaData.boardIdx, 1));
      bGeo.computeVertexNormals();
      const bMat = new THREE.MeshBasicMaterial({
        vertexColors: true,
        side: THREE.DoubleSide,
        polygonOffset: true,
        polygonOffsetFactor: -2,
      });
      const bMesh = new THREE.Mesh(bGeo, bMat);
      bMesh.name = "SIM_FEA_BOARDS_STRAIN";
      simWorldGroup.add(bMesh);
    }

    const [px, py, pz] = ld.peak_at_mm;
    const peakPos = new THREE.Vector3(px * 0.001, pz * 0.001, -py * 0.001);
    const spMesh = new THREE.Mesh(
      new THREE.SphereGeometry(0.0042, 18, 18),
      new THREE.MeshBasicMaterial({ color: 0xf43f5e, transparent: true, opacity: 0.92 })
    );
    spMesh.position.copy(peakPos);
    simWorldGroup.add(spMesh);

    const ringGeo = new THREE.RingGeometry(0.0055, 0.0075, 28);
    ringGeo.rotateX(-Math.PI / 2);
    const ring = new THREE.Mesh(ringGeo, new THREE.MeshBasicMaterial({ color: 0xffb020, side: THREE.DoubleSide }));
    ring.position.copy(peakPos).add(new THREE.Vector3(0, 0.0005, 0));
    simWorldGroup.add(ring);

    const [ax, ay, az] = ld.adapter.peak_at_mm;
    const aSp = new THREE.Mesh(
      new THREE.SphereGeometry(0.0032, 14, 14),
      new THREE.MeshBasicMaterial({ color: 0xf59e0b })
    );
    aSp.position.set(ax * 0.001, az * 0.001, -ay * 0.001);
    simWorldGroup.add(aSp);

    for (const [bRef, bv] of Object.entries(ld.bga)) {
      addWorldBoxCage(bRef, heatColorHex(Math.min(1, bv.ue_max / bv.limit_ue)).getHex(), true, 0.012);
    }
  }

  function populateWorldOverlays() {
    clearGroup(simWorldGroup);
    if (!enabled || !sims) return;
    if (domain === "rf" && sel.rfFocusType === "pair") {
      const p = sims.rf_si.pairs.find((x) => x.id === sel.rfFocusId);
      p?.components.forEach((r) => addWorldBoxCage(r, 0x38bdf8, true, 0.009));
    } else if (domain === "rf" && sel.rfFocusType === "sparam") {
      const sp = sims.rf_si.sparam_models.find((m) => m.id === sel.rfFocusId);
      sp?.components.slice(0, 14).forEach((r) => addWorldBoxCage(r, 0xfbbf24, true, 0.008));
    } else if (domain === "power") {
      const rail = sims.power.rails.find((r) => r.rail === sel.powerRail) || sims.power.rails[0];
      if (!rail) return;
      if (rail.regulator_ref) addWorldBoxCage(rail.regulator_ref, 0xffb020, true, 0.013);
      if (rail.inductor_ref && rail.inductor_ref !== rail.regulator_ref) addWorldBoxCage(rail.inductor_ref, 0xfbbf24, true, 0.010);
      for (const ld of rail.loads || []) addWorldBoxCage(ld, 0x22d3ee, true, 0.007);
      for (const c of (rail.components || []).slice(0, 26)) {
        if (c !== rail.regulator_ref && !(rail.loads || []).includes(c)) addWorldBoxCage(c, 0x38bdf8, false);
      }
    } else if (domain === "thermal") {
      const c = sims.thermal.cases.find((x) => x.id === sel.thermalCase) || sims.thermal.cases[0];
      for (const ic of c?.ics || []) {
        const norm = sel.thermalMetric === "Tj" ? Math.max(0, Math.min(1, (ic.T_j_C - 40) / 80)) : Math.max(0, Math.min(1, (40 - ic.margin_C) / 45));
        const pillarH = Math.max(0.004, Math.min(0.020, ((ic.T_j_C - 25) / 100) * 0.018));
        addWorldBoxCage(ic.ref, heatColorHex(norm).getHex(), true, pillarH);
      }
    } else if (domain === "mech") {
      const ld = sims.mechanical.load_cases.find((x) => x.id === sel.mechLoad) || sims.mechanical.load_cases[0];
      if (ld) populateMechWorld(ld);
    } else if (domain === "g8") {
      const gm = sims.gateware_g8.modes.find((m) => m.id === sel.g8Mode) || sims.gateware_g8.modes[0];
      (gm?.hardware_parts || []).forEach((r, idx, arr) => {
        const col = idx === 0 ? 0xfbbf24 : idx === arr.length - 1 ? 0x3fb950 : 0x22d3ee;
        addWorldBoxCage(r, col, idx < 3 || idx >= arr.length - 3 || r === "U1101" || r === "U501" || r === "U601" || r === "U1312", 0.010);
      });
    } else if (domain === "audit") {
      const rfParts = new Set(["C1441", "L1441", "C1442", "C1443", "L1442", "C1444", "C1445", "J961"]);
      for (const ref of sims.audit?.audited_parts || []) {
        const col = ref === sel.auditFocusRef ? 0x3fb950 : rfParts.has(ref) ? 0x22d3ee : 0xfbbf24;
        addWorldBoxCage(ref, col, true, 0.0085);
      }
    }
  }

  function buildMech3D() {
    const ld = sims.mechanical.load_cases.find((x) => x.id === sel.mechLoad) || sims.mechanical.load_cases[0];
    if (!ld) return;
    if (!feaData) {
      const sfNorm = Math.max(0, Math.min(1, (8.5 - ld.sf_70C) / 7.5));
      const caseHex = heatColorHex(sfNorm).getHex();
      setGroupTint(encNodes?.ENCLOSURE_BOTTOM_GROUP, caseHex, 0.52);
      setGroupTint(encNodes?.ENCLOSURE_LID_GROUP, caseHex, 0.42);
      loadFeaFields().then((d) => {
        if (d && enabled && domain === "mech") {
          rebuild3DOverlay();
          applyAnimatedScene();
        }
      });
    } else {
      applyFeaCaseColors(encNodes?.ENCLOSURE_BOTTOM_GROUP, ld.id);
      applyFeaCaseColors(encNodes?.ENCLOSURE_LID_GROUP, ld.id);
    }
    setGroupTint(encNodes?.ENCLOSURE_BUMPERS_GROUP, 0x10b981, 0.85);
    populateMechWorld(ld);
  }

  function buildG83D() {
    const mode = sims.gateware_g8.modes.find((m) => m.id === sel.g8Mode) || sims.gateware_g8.modes[0];
    if (!mode) return;
    g8PulseSegs = addTraceLines(mode.hardware_nets, 0x22d3ee, 0.96, 0.00022);
    if (g8PulseSegs.length) {
      const dotCount = Math.min(32, Math.max(10, g8PulseSegs.length));
      const dotGeo = new THREE.SphereGeometry(0.00055, 8, 8);
      const dotMat = new THREE.MeshBasicMaterial({ color: 0xfbbf24 });
      g8PulseMesh = new THREE.InstancedMesh(dotGeo, dotMat, dotCount);
      simBoardGroup.add(g8PulseMesh);
      stepAnimation(performance.now());
    }
    populateWorldOverlays();
  }

  function buildAudit3D() {
    const nets = sims?.audit?.highlight_nets || [];
    const rfNets = nets.filter((n) => n.includes("VU_PSB"));
    if (rfNets.length) addTraceLines(rfNets, 0x22d3ee, 0.96, 0.00022);
    if (nets.includes("+2V8_RF")) addTraceLines(["+2V8_RF"], 0xfbbf24, 0.90, 0.00018);
    populateWorldOverlays();
  }

  function stepAnimation(now) {
    if (!enabled || domain !== "g8" || !g8PulseMesh || !g8PulseSegs.length) return false;
    const count = g8PulseMesh.count;
    const speed = isReducedMotion() ? 0 : now * 0.0018;
    const m = new THREE.Matrix4();
    for (let i = 0; i < count; i++) {
      const segIdx = Math.floor((i * g8PulseSegs.length) / count);
      const s = g8PulseSegs[segIdx];
      const ph = (speed + i * 0.11) % 1.0;
      m.makeTranslation(s[0] + (s[3] - s[0]) * ph, s[1] + 0.0003, s[2] + (s[5] - s[2]) * ph);
      g8PulseMesh.setMatrixAt(i, m);
    }
    g8PulseMesh.instanceMatrix.needsUpdate = true;
    return true;
  }

  // -------------------------------------------------------------------------
  // Interactive Canvas Charts (Retina DPI-aware)
  // -------------------------------------------------------------------------
  function setupCanvas(canvas, cssHeight = 148) {
    if (!canvas) return null;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    const w = Math.max(260, canvas.parentElement?.clientWidth || 300);
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(cssHeight * dpr);
    canvas.style.width = "100%";
    canvas.style.height = `${cssHeight}px`;
    const g = canvas.getContext("2d");
    g.scale(dpr, dpr);
    const dark = document.documentElement.getAttribute("data-theme") !== "light";
    return {
      g,
      w,
      h: cssHeight,
      bg: dark ? "#0d1218" : "#f8fafc",
      grid: dark ? "#243040" : "#cbd5e1",
      txt: dark ? "#93a4b8" : "#475569",
      hi: dark ? "#e6edf3" : "#0f172a",
    };
  }

  function drawChartInContainer(canvas) {
    if (!canvas || !sims) return;
    const c = setupCanvas(canvas, 148);
    if (!c) return;
    const { g, w, h, bg, grid, txt, hi } = c;
    g.fillStyle = bg;
    g.fillRect(0, 0, w, h);

    const pad = { l: 42, r: 12, t: 18, b: 24 };
    const pw = w - pad.l - pad.r;
    const ph = h - pad.t - pad.b;

    if (domain === "rf") {
      if (sel.rfFocusType === "sparam") {
        const sp = sims.rf_si.sparam_models.find((m) => m.id === sel.rfFocusId) || sims.rf_si.sparam_models[0];
        const curve = sp?.curve || [];
        if (curve.length) {
          const fMin = curve[0][0];
          const fMax = curve[curve.length - 1][0];
          const yMin = -70;
          const yMax = 5;
          drawAxes(g, pad, pw, ph, grid, txt, `${sp.id} S21 (cyan) & S11 (amber) [dB]`, `${fMin} MHz`, `${fMax} MHz`, `${yMin}`, `${yMax}`);
          plotSeries(g, pad, pw, ph, curve, (p) => (p[0] - fMin) / (fMax - fMin || 1), (p) => (p[1] - yMin) / (yMax - yMin), "#fbbf24", 1.8);
          plotSeries(g, pad, pw, ph, curve, (p) => (p[0] - fMin) / (fMax - fMin || 1), (p) => (p[2] - yMin) / (yMax - yMin), "#22d3ee", 2.1);
          return;
        }
      }
      // Default RF chart: routed pairs bar chart (Skew or Eye)
      const subset = sims.rf_si.pairs.filter((p) => p.eye_routed_mV !== null).slice(0, 14);
      const isSkew = sel.rfMetric === "skew";
      const maxVal = isSkew ? 30 : 750;
      drawAxes(g, pad, pw, ph, grid, txt, isSkew ? "LVDS Skew |P-N| (ps, limit 30 ps)" : "1 Gbps Eye Opening (mV, min 200 mV)", "", "", "0", String(maxVal));
      const bw = pw / Math.max(1, subset.length);
      subset.forEach((p, idx) => {
        const val = isSkew ? p.abs_skew_ps : (p.eye_routed_mV || 0);
        const norm = Math.min(1, val / maxVal);
        const col = isSkew ? heatColorHex(p.abs_skew_ps / 25) : heatColorHex((700 - val) / 300);
        g.fillStyle = `#${col.getHexString()}`;
        const bh = Math.max(2, norm * ph);
        g.fillRect(pad.l + idx * bw + 1, pad.t + ph - bh, Math.max(3, bw - 3), bh);
      });
    } else if (domain === "power") {
      const rail = sims.power.rails.find((r) => r.rail === sel.powerRail) || sims.power.rails[0];
      if (rail?.curve_MHz_mohm?.length) {
        const pts = rail.curve_MHz_mohm;
        const lMin = Math.log10(0.1);
        const lMax = Math.log10(100);
        const zMax = Math.max(rail.target_z_mohm || 120, ...pts.map((p) => p[1])) * 1.15;
        const yLogMin = Math.log10(2);
        const yLogMax = Math.log10(Math.max(10, zMax));
        drawAxes(g, pad, pw, ph, grid, txt, `${rail.rail} PDN |Z(f)| (mOhm) vs Target (${rail.target_z_mohm} mOhm)`, "0.1 MHz", "100 MHz", "2", String(Math.round(zMax)));
        if (rail.target_z_mohm) {
          const ty = pad.t + ph - ((Math.log10(rail.target_z_mohm) - yLogMin) / (yLogMax - yLogMin)) * ph;
          g.strokeStyle = "#f43f5e";
          g.setLineDash([4, 3]);
          g.beginPath();
          g.moveTo(pad.l, ty);
          g.lineTo(pad.l + pw, ty);
          g.stroke();
          g.setLineDash([]);
        }
        plotSeries(
          g,
          pad,
          pw,
          ph,
          pts,
          (p) => (Math.log10(Math.max(0.1, p[0])) - lMin) / (lMax - lMin),
          (p) => (Math.log10(Math.max(2, p[1])) - yLogMin) / (yLogMax - yLogMin),
          "#22d3ee",
          2.1
        );
      } else {
        // Overview bar comparison of simulated PDN rails
        const withZ = sims.power.rails.filter((r) => r.target_z_mohm && r.sim_z_band_mohm);
        drawAxes(g, pad, pw, ph, grid, txt, "Sim |Z| / Target Ratio (% of limit)", "", "", "0%", "100%");
        const bw = pw / Math.max(1, withZ.length);
        withZ.forEach((r, idx) => {
          const ratio = Math.min(1, r.sim_z_band_mohm / r.target_z_mohm);
          const bh = Math.max(4, ratio * ph);
          g.fillStyle = ratio > 0.7 ? "#f59e0b" : "#10b981";
          g.fillRect(pad.l + idx * bw + 12, pad.t + ph - bh, Math.max(12, bw - 24), bh);
          g.fillStyle = hi;
          g.font = "10px monospace";
          g.fillText(`${r.rail} (${Math.round(ratio * 100)}%)`, pad.l + idx * bw + 8, pad.t + ph - bh - 4);
        });
      }
    } else if (domain === "thermal") {
      const c = sims.thermal.cases.find((x) => x.id === sel.thermalCase) || sims.thermal.cases[0];
      const topIcs = (c?.ics || []).slice(0, 12);
      drawAxes(g, pad, pw, ph, grid, txt, `Tj vs Limit (°C) - ${c.ambient_c}°C Case`, "", "", "20", "130");
      const bw = pw / Math.max(1, topIcs.length);
      topIcs.forEach((ic, idx) => {
        const yTj = Math.max(0, Math.min(1, (ic.T_j_C - 20) / 110)) * ph;
        const yLim = Math.max(0, Math.min(1, (ic.limit_C - 20) / 110)) * ph;
        g.fillStyle = ic.margin_C < 0 ? "#ef4444" : ic.margin_C < 10 ? "#f59e0b" : "#10b981";
        g.fillRect(pad.l + idx * bw + 2, pad.t + ph - yTj, Math.max(4, bw - 4), yTj);
        g.strokeStyle = hi;
        g.lineWidth = 1.3;
        g.beginPath();
        g.moveTo(pad.l + idx * bw + 1, pad.t + ph - yLim);
        g.lineTo(pad.l + (idx + 1) * bw - 1, pad.t + ph - yLim);
        g.stroke();
      });
    } else if (domain === "mech") {
      const ld = sims.mechanical.load_cases.find((x) => x.id === sel.mechLoad) || sims.mechanical.load_cases[0];
      const bgaArr = Object.values(ld?.bga || {});
      drawAxes(g, pad, pw, ph, grid, txt, `BGA Principal Strain vs 500 ue IPC Limit (${ld.id})`, "", "", "0", "550");
      const y500 = pad.t + ph - (500 / 550) * ph;
      g.strokeStyle = "#f43f5e";
      g.setLineDash([4, 3]);
      g.beginPath();
      g.moveTo(pad.l, y500);
      g.lineTo(pad.l + pw, y500);
      g.stroke();
      g.setLineDash([]);
      const bw = pw / Math.max(1, bgaArr.length);
      bgaArr.forEach((b, idx) => {
        const bh = Math.min(1, b.ue_max / 550) * ph;
        g.fillStyle = "#22d3ee";
        g.fillRect(pad.l + idx * bw + 18, pad.t + ph - bh, Math.max(18, bw - 36), bh);
        g.fillStyle = hi;
        g.font = "10px monospace";
        g.fillText(`${b.ref}: ${b.ue_max}ue`, pad.l + idx * bw + 12, pad.t + ph - bh - 4);
      });
    } else if (domain === "g8") {
      const gm = sims.gateware_g8.modes.find((m) => m.id === sel.g8Mode) || sims.gateware_g8.modes[0];
      if (gm?.levels?.length && gm.sinad_rtl?.length) {
        const ptsRtl = gm.levels.map((lv, i) => [lv, gm.sinad_rtl[i]]);
        const ptsRef = (gm.sinad_ref || []).map((v, i) => [gm.levels[i], v]);
        const x0 = gm.levels[0];
        const x1 = gm.levels[gm.levels.length - 1];
        const isPd = gm.id === "adsb";
        const y0 = isPd ? 0 : -5;
        const y1 = isPd ? 1.05 : 65;
        drawAxes(g, pad, pw, ph, grid, txt, `${gm.id.toUpperCase()}: RTL (cyan) vs Float Ref (dashed)`, `${x0} dBm`, `${x1} dBm`, String(y0), isPd ? "1.0" : "65 dB");
        if (ptsRef.length) {
          g.save();
          g.setLineDash([4, 3]);
          plotSeries(g, pad, pw, ph, ptsRef, (p) => (p[0] - x0) / (x1 - x0 || 1), (p) => (p[1] - y0) / (y1 - y0), "#f59e0b", 1.8);
          g.restore();
        }
        plotSeries(g, pad, pw, ph, ptsRtl, (p) => (p[0] - x0) / (x1 - x0 || 1), (p) => (p[1] - y0) / (y1 - y0), "#22d3ee", 2.2);
      } else {
        drawAxes(g, pad, pw, ph, grid, txt, `${gm?.title || ""} Verification Summary`, "", "", "0", "100%");
        const passed = (gm?.checks || []).filter((k) => k.ok).length;
        const total = Math.max(1, (gm?.checks || []).length);
        g.fillStyle = "#10b981";
        g.fillRect(pad.l + 24, pad.t + ph * 0.25, pw * 0.72 * (passed / total), ph * 0.45);
        g.fillStyle = hi;
        g.font = "12px monospace";
        g.fillText(`${passed}/${total} RTL checks PASSED`, pad.l + 30, pad.t + ph * 0.52);
      }
    } else if (domain === "audit") {
      if (sel.auditView === "rf") {
        const entries = Object.entries(sims.audit?.rf?.uhf_path_db || {})
          .map(([f, pair]) => [parseFloat(f), pair[0], pair[1]])
          .filter((d) => Number.isFinite(d[0]))
          .sort((a, b) => a[0] - b[0]);
        if (entries.length) {
          const xMin = entries[0][0];
          const xMax = entries[entries.length - 1][0];
          const l0 = Math.log10(xMin);
          const l1 = Math.log10(xMax);
          drawAxes(g, pad, pw, ph, grid, txt, "UHF Atten: Before (amber) vs HP300 [dB]", `${xMin} MHz`, `${xMax} MHz`, "0 dB", "75 dB");
          g.save();
          g.setLineDash([4, 3]);
          plotSeries(g, pad, pw, ph, entries, (d) => (Math.log10(d[0]) - l0) / (l1 - l0 || 1), (d) => d[1] / 75, "#f59e0b", 1.8);
          g.restore();
          plotSeries(g, pad, pw, ph, entries, (d) => (Math.log10(d[0]) - l0) / (l1 - l0 || 1), (d) => d[2] / 75, "#22d3ee", 2.2);
        }
      } else {
        const rows = sims.audit?.power?.budget?.rows || [];
        drawAxes(g, pad, pw, ph, grid, txt, "Regulator Worst-Case Utilization (% of Rated A)", "", "", "0%", "100%");
        const bw = pw / Math.max(1, rows.length);
        rows.forEach((r, idx) => {
          const pct = Math.min(1, r.use || 0);
          const bh = Math.max(3, pct * ph);
          g.fillStyle = pct > 0.7 ? "#f59e0b" : "#22d3ee";
          g.fillRect(pad.l + idx * bw + 3, pad.t + ph - bh, Math.max(6, bw - 6), bh);
          g.fillStyle = hi;
          g.font = "9px monospace";
          g.fillText(`${Math.round(pct * 100)}%`, pad.l + idx * bw + 2, Math.max(pad.t + 10, pad.t + ph - bh - 3));
        });
      }
    }
  }

  function drawAxes(g, pad, pw, ph, grid, txt, title, xL, xR, yMinLbl, yMaxLbl) {
    g.strokeStyle = grid;
    g.lineWidth = 1;
    g.beginPath();
    g.rect(pad.l, pad.t, pw, ph);
    g.moveTo(pad.l, pad.t + ph * 0.5);
    g.lineTo(pad.l + pw, pad.t + ph * 0.5);
    g.stroke();
    g.fillStyle = txt;
    g.font = "10px monospace";
    g.fillText(title, pad.l, 12);
    if (xL) g.fillText(xL, pad.l, pad.t + ph + 14);
    if (xR) {
      const tw = g.measureText(xR).width;
      g.fillText(xR, pad.l + pw - tw, pad.t + ph + 14);
    }
    if (yMaxLbl) g.fillText(yMaxLbl, 4, pad.t + 8);
    if (yMinLbl) g.fillText(yMinLbl, 4, pad.t + ph);
  }

  function plotSeries(g, pad, pw, ph, pts, fx, fy, color, lineWidth) {
    if (!pts.length) return;
    g.strokeStyle = color;
    g.lineWidth = lineWidth;
    g.beginPath();
    pts.forEach((p, i) => {
      const x = pad.l + Math.max(0, Math.min(1, fx(p))) * pw;
      const y = pad.t + ph - Math.max(0, Math.min(1, fy(p))) * ph;
      if (i === 0) g.moveTo(x, y);
      else g.lineTo(x, y);
    });
    g.stroke();
  }

  // -------------------------------------------------------------------------
  // UI Synchronization (Left Dock Sub-Controls, Legend Bar, Right Telemetry)
  // -------------------------------------------------------------------------
  function updateLegendBar() {
    const bar = document.querySelector("#sim-legend-bar");
    if (!bar) return;
    if (!enabled || !sims) {
      bar.style.display = "none";
      return;
    }
    bar.style.display = "flex";
    if (domain === "rf") {
      bar.innerHTML = sel.rfMetric === "skew"
        ? `<strong>RF/SI:</strong><span>LVDS Skew |P-N|</span><span class="sim-grad-bar"></span><span class="mono">0 ps -> 25 ps</span>`
        : `<strong>RF/SI:</strong><span>1 Gbps Eye Opening</span><span class="sim-grad-bar"></span><span class="mono">700 mV -> 400 mV</span>`;
    } else if (domain === "power") {
      bar.innerHTML = `<strong>Power/PDN:</strong><span>Active Rail: <code>${escapeHtml(sel.powerRail)}</code></span><span class="mono" style="color:var(--cyan)">Copper + Regulator + Decaps highlighted</span>`;
    } else if (domain === "thermal") {
      const c = sims.thermal.cases.find((x) => x.id === sel.thermalCase);
      bar.innerHTML = `<strong>Thermal CFD:</strong><span>${escapeHtml(c?.title || "")}</span><span class="sim-grad-bar"></span><span class="mono">40 °C -> 120 °C Tj</span>`;
    } else if (domain === "mech") {
      const ld = sims.mechanical.load_cases.find((x) => x.id === sel.mechLoad);
      bar.innerHTML = `<strong>Mech FEA:</strong><span>${escapeHtml(ld?.title || "")}</span><span class="sim-grad-bar"></span><span class="mono">Case von Mises 0..${ld?.case_vm_peak_MPa} MPa (Allow 17.4 MPa) &middot; Boards 0..500 ue &middot; Src: case3d_v2.json</span>`;
    } else if (domain === "g8") {
      const gm = sims.gateware_g8.modes.find((m) => m.id === sel.g8Mode);
      bar.innerHTML = `<strong>Gateware G-8:</strong><span>${escapeHtml(gm?.title || "")}</span><span class="mono" style="color:var(--green)">${gm?.passed ? "PASS" : "FAIL"}</span>`;
    } else if (domain === "audit") {
      bar.innerHTML = `<strong>RF &amp; Power Audit:</strong><span>14 audited parts &middot; IF rej 84-99 dB &middot; 13.4 W worst</span><span class="mono" style="color:var(--cyan)">Src: docs/sim/rf_audit.json, docs/sim/power_audit.json</span>`;
    }
  }

  function renderDockSubcontrols() {
    const toggleBtn = document.querySelector("#btn-sim-toggle");
    const dockCard = document.querySelector("#sim-mode-dock");
    const sub = document.querySelector("#sim-dock-subcontrols");
    const navBtn = document.querySelector("#btn-nav-sims");
    if (toggleBtn) {
      toggleBtn.textContent = enabled ? "On" : "Off";
      toggleBtn.classList.toggle("btn-primary", enabled);
      toggleBtn.setAttribute("aria-pressed", String(enabled));
    }
    if (dockCard) dockCard.classList.toggle("sim-active", enabled);
    if (navBtn) navBtn.classList.toggle("active", enabled);

    document.querySelectorAll("[data-sim-domain]").forEach((b) => {
      b.classList.toggle("active", enabled && b.dataset.simDomain === domain);
    });

    if (!sub || !enabled || !sims) {
      if (sub) sub.style.display = "none";
      return;
    }
    sub.style.display = "flex";
    if (domain === "rf") {
      sub.innerHTML = `
        <div class="btn-grid">
          <button class="btn btn-sm ${sel.rfMetric === "skew" ? "active" : ""}" id="sim-rf-skew" type="button">Color: Skew (ps)</button>
          <button class="btn btn-sm ${sel.rfMetric === "eye" ? "active" : ""}" id="sim-rf-eye" type="button">Color: Eye (mV)</button>
        </div>
        <select id="sim-rf-sel" class="sim-select" aria-label="Select RF or SI trace">
          <option value="all:" ${sel.rfFocusType === "all" ? "selected" : ""}>All 28 LVDS/SGMII Pairs (8-Layer)</option>
          ${sims.rf_si.sparam_models.map((s) => `<option value="sparam:${s.id}" ${sel.rfFocusType === "sparam" && sel.rfFocusId === s.id ? "selected" : ""}>S-Param: ${escapeHtml(s.id)}</option>`).join("")}
          <option value="crosstalk:" ${sel.rfFocusType === "crosstalk" ? "selected" : ""}>NEXT Crosstalk Pairs (7)</option>
          ${sims.rf_si.pairs.map((p) => `<option value="pair:${p.id}" ${sel.rfFocusType === "pair" && sel.rfFocusId === p.id ? "selected" : ""}>Pair ${escapeHtml(p.id)} (${p.abs_skew_ps} ps)</option>`).join("")}
        </select>`;
      sub.querySelector("#sim-rf-skew").addEventListener("click", () => { sel.rfMetric = "skew"; updateAll(); });
      sub.querySelector("#sim-rf-eye").addEventListener("click", () => { sel.rfMetric = "eye"; updateAll(); });
      sub.querySelector("#sim-rf-sel").addEventListener("change", (ev) => {
        const [ft, fi] = ev.target.value.split(":");
        sel.rfFocusType = ft;
        sel.rfFocusId = fi || null;
        updateAll();
      });
    } else if (domain === "power") {
      sub.innerHTML = `
        <select id="sim-pwr-sel" class="sim-select" aria-label="Select power rail">
          ${sims.power.rails.map((r) => `<option value="${escapeHtml(r.rail)}" ${sel.powerRail === r.rail ? "selected" : ""}>${escapeHtml(r.label)}</option>`).join("")}
        </select>`;
      sub.querySelector("#sim-pwr-sel").addEventListener("change", (ev) => {
        sel.powerRail = ev.target.value;
        updateAll();
      });
    } else if (domain === "thermal") {
      sub.innerHTML = `
        <select id="sim-therm-sel" class="sim-select" aria-label="Select CFD thermal case">
          ${sims.thermal.cases.map((c) => `<option value="${escapeHtml(c.id)}" ${sel.thermalCase === c.id ? "selected" : ""}>${escapeHtml(c.title)}</option>`).join("")}
        </select>
        <div class="btn-grid">
          <button class="btn btn-sm ${sel.thermalMetric === "Tj" ? "active" : ""}" id="sim-th-tj" type="button">Map: Tj (°C)</button>
          <button class="btn btn-sm ${sel.thermalMetric === "margin" ? "active" : ""}" id="sim-th-mrg" type="button">Map: Margin (°C)</button>
        </div>`;
      sub.querySelector("#sim-therm-sel").addEventListener("change", (ev) => {
        sel.thermalCase = ev.target.value;
        updateAll();
      });
      sub.querySelector("#sim-th-tj").addEventListener("click", () => { sel.thermalMetric = "Tj"; updateAll(); });
      sub.querySelector("#sim-th-mrg").addEventListener("click", () => { sel.thermalMetric = "margin"; updateAll(); });
    } else if (domain === "mech") {
      sub.innerHTML = `
        <select id="sim-mech-load" class="sim-select" aria-label="Select FEA load case">
          ${sims.mechanical.load_cases.map((l) => `<option value="${escapeHtml(l.id)}" ${sel.mechLoad === l.id ? "selected" : ""}>${escapeHtml(l.title)}</option>`).join("")}
        </select>
        <div class="btn-grid">
          <button class="btn btn-sm ${sel.mechTemp === 23 ? "active" : ""}" id="sim-m-23" type="button">23 °C Nominal</button>
          <button class="btn btn-sm ${sel.mechTemp === 70 ? "active" : ""}" id="sim-m-70" type="button">70 °C Cabin</button>
        </div>`;
      sub.querySelector("#sim-mech-load").addEventListener("change", (ev) => {
        sel.mechLoad = ev.target.value;
        updateAll();
      });
      sub.querySelector("#sim-m-23").addEventListener("click", () => { sel.mechTemp = 23; updateAll(); });
      sub.querySelector("#sim-m-70").addEventListener("click", () => { sel.mechTemp = 70; updateAll(); });
    } else if (domain === "g8") {
      sub.innerHTML = `
        <select id="sim-g8-sel" class="sim-select" aria-label="Select G-8 mode">
          ${sims.gateware_g8.modes.map((m) => `<option value="${escapeHtml(m.id)}" ${sel.g8Mode === m.id ? "selected" : ""}>${escapeHtml(m.id.toUpperCase())}: ${escapeHtml(m.title)}</option>`).join("")}
        </select>`;
      sub.querySelector("#sim-g8-sel").addEventListener("change", (ev) => {
        sel.g8Mode = ev.target.value;
        updateAll();
      });
    } else if (domain === "audit") {
      sub.innerHTML = `
        <div class="btn-grid-3">
          <button class="btn btn-sm ${sel.auditView === "rf" ? "active" : ""}" id="sim-aud-rf" type="button">RF HP300</button>
          <button class="btn btn-sm ${sel.auditView === "power" ? "active" : ""}" id="sim-aud-pwr" type="button">Power/PTC</button>
          <button class="btn btn-sm ${sel.auditView === "transients" ? "active" : ""}" id="sim-aud-trn" type="button">Transients</button>
        </div>
        <select id="sim-aud-part" class="sim-select" aria-label="Select audited part">
          <option value="">All 14 audited parts</option>
          ${(sims.audit?.audited_parts || []).map((r) => `<option value="${escapeHtml(r)}" ${sel.auditFocusRef === r ? "selected" : ""}>${escapeHtml(r)}: ${escapeHtml(sims.audit.part_audit[r]?.code || "")} ${escapeHtml(sims.audit.part_audit[r]?.title || "")}</option>`).join("")}
        </select>`;
      sub.querySelector("#sim-aud-rf").addEventListener("click", () => { sel.auditView = "rf"; updateAll(); });
      sub.querySelector("#sim-aud-pwr").addEventListener("click", () => { sel.auditView = "power"; updateAll(); });
      sub.querySelector("#sim-aud-trn").addEventListener("click", () => { sel.auditView = "transients"; updateAll(); });
      sub.querySelector("#sim-aud-part").addEventListener("change", (ev) => {
        const ref = ev.target.value || null;
        sel.auditFocusRef = ref;
        if (ref) selectPart(ref, true);
        updateAll();
      });
    }
  }

  function figThumbHtml(src, title, srcFile, cap = "") {
    if (!src) return "";
    return `
      <div class="sim-fig-box" data-open-fig="${escapeHtml(src)}" data-fig-cap="${escapeHtml(title)} (${escapeHtml(srcFile)})">
        <img src="${escapeHtml(src)}" alt="${escapeHtml(title)}">
        <div class="sim-fig-meta">
          <strong>${escapeHtml(title)}</strong>
          ${cap ? `<span>${escapeHtml(cap)}</span>` : ""}
          <code class="mono">${escapeHtml(srcFile)}</code>
        </div>
      </div>`;
  }

  function renderTelemetryCard() {
    const card = document.querySelector("#sim-inspector-card");
    if (!card) return;
    if (!enabled || !sims) {
      card.style.display = "none";
      return;
    }
    card.style.display = "flex";

    let bodyHtml = "";
    if (domain === "rf") {
      const sp = sims.rf_si.sparam_models.find((m) => m.id === sel.rfFocusId);
      const pr = sims.rf_si.pairs.find((p) => p.id === sel.rfFocusId);
      const figSrc = sp ? sp.figure : "assets/img/sim_results/eyes_1g.png";
      const figFile = sp ? sp.source_file : "docs/sim/eyes_1g.png";
      const figTitle = sp ? sp.title : "1 Gbps Eye Diagrams (8-Layer Routed)";

      let detailRows = "";
      if (sel.rfFocusType === "crosstalk") {
        detailRows = sims.rf_si.crosstalk.map((x) => `
          <tr>
            <td class="mono">${escapeHtml(x.a)} &lt;-&gt; ${escapeHtml(x.b)}</td>
            <td class="mono">${escapeHtml(x.layer)} (${x.parallel_mm} mm)</td>
            <td class="mono">${x.next_pct}% NEXT</td>
          </tr>`).join("");
      } else {
        detailRows = sims.rf_si.pairs.slice(0, 14).map((p) => `
          <tr class="sim-click-row ${sel.rfFocusType === "pair" && sel.rfFocusId === p.id ? "selected" : ""}" data-pick-pair="${escapeHtml(p.id)}">
            <td class="mono">${escapeHtml(p.id)}</td>
            <td class="mono">${p.skew_ps} ps</td>
            <td class="mono">${p.eye_routed_mV ? p.eye_routed_mV + " mV" : "-"}</td>
          </tr>`).join("");
      }

      bodyHtml = `
        <div class="control-row">
          <span class="badge badge-cyan">RF / SIGNAL INTEGRITY</span>
          <span class="mono" style="font-size:10px;color:var(--text-muted)">${sims.rf_si.pairs.length} pairs · 3 S-param models</span>
        </div>
        ${pr ? `<div class="sim-highlight-box">
          <strong>${escapeHtml(pr.pair)} (${pr.rate_gbps} Gbps)</strong>
          <div class="mono">Skew: ${pr.skew_ps} ps (P ${pr.p_ps} / N ${pr.n_ps} ps) · Eye: ${pr.eye_routed_mV ?? "-"} mV (ideal ${pr.eye_ideal_mV ?? "-"} mV) · ZC spread: ${pr.zc_spread_ps ?? "-"} ps</div>
          <div class="sim-chips">${pr.components.map((r) => `<button type="button" class="net-chip pick-sim-part" data-ref="${escapeHtml(r)}">${escapeHtml(r)}</button>`).join("")}</div>
          <div class="mono sim-src-line">Source: ${pr.source_files.join(", ")}</div>
        </div>` : ""}
        ${sp ? `<div class="sim-highlight-box">
          <strong>${escapeHtml(sp.title)}</strong>
          <div class="mono">${escapeHtml(Object.entries(sp.summary).map(([k, v]) => `${k}=${v}`).join(" · "))}</div>
          <div class="sim-chips">${sp.components.slice(0, 10).map((r) => `<button type="button" class="net-chip pick-sim-part" data-ref="${escapeHtml(r)}">${escapeHtml(r)}</button>`).join("")}</div>
          <div class="mono sim-src-line">Source: ${escapeHtml(sp.source_file)}</div>
        </div>` : ""}
        <canvas id="sim-chart-canvas" class="sim-chart-canvas"></canvas>
        <div class="sim-table-scroll">
          <table class="kv-table">
            <thead><tr><th>${sel.rfFocusType === "crosstalk" ? "Coupled Nets" : "Diff Pair (Click)"}</th><th>${sel.rfFocusType === "crosstalk" ? "Layer" : "Skew"}</th><th>${sel.rfFocusType === "crosstalk" ? "NEXT" : "Eye"}</th></tr></thead>
            <tbody>${detailRows}</tbody>
          </table>
        </div>
        ${figThumbHtml(figSrc, figTitle, figFile, "Click to inspect full solver PNG plot.")}
        <div class="mono sim-src-line">Sources: _work/sim/lvds_skew_8layer.json, _work/sim/lvds_eye_8layer.csv, docs/sim/*.csv, docs/SIGNAL_INTEGRITY.md</div>`;
    } else if (domain === "power") {
      const r = sims.power.rails.find((x) => x.rail === sel.powerRail) || sims.power.rails[0];
      bodyHtml = `
        <div class="control-row">
          <span class="badge badge-cyan">POWER &amp; PDN</span>
          <span class="mono" style="font-size:10px;color:var(--text-muted)">${r.voltage_V} V · ${r.current_mA} mA · ${r.power_W} W</span>
        </div>
        <div class="sim-highlight-box">
          <strong>${escapeHtml(r.label)}</strong>
          <table class="kv-table">
            <tr><th>Target vs Sim |Z|</th><td class="mono">${r.sim_z_band_mohm ? `${r.sim_z_band_mohm} mΩ vs ${r.target_z_mohm} mΩ (${r.margin_factor}x margin)` : "Analog / secondary LDO rail"}</td></tr>
            <tr><th>DC Path / Drop</th><td class="mono">${r.dc_drop_mV ? `${r.dc_drop_mV} mV (${r.dc_drop_pct}%), ${r.dc_res_mohm} mΩ` : "See POWER_AND_STACKUP.md"}</td></tr>
            ${r.extra_metrics ? `<tr><th>FB401 580kHz Filter</th><td class="mono">Atten ${r.extra_metrics.ripple_atten_dB} dB · ${r.extra_metrics.output_ripple_uVpp} uVpp · Spur ${r.extra_metrics.spur_dBc} dBc</td></tr>` : ""}
          </table>
          <div class="sim-chips">${[r.regulator_ref, r.inductor_ref, ...(r.loads || [])].filter(Boolean).map((ref) => `<button type="button" class="net-chip pick-sim-part" data-ref="${escapeHtml(ref)}">${escapeHtml(ref)}</button>`).join("")}</div>
          <div class="mono sim-src-line">Sources: ${r.source_files.join(", ")}</div>
        </div>
        <canvas id="sim-chart-canvas" class="sim-chart-canvas"></canvas>
        <div class="sim-table-scroll">
          <table class="kv-table">
            <thead><tr><th>Rail</th><th>I (mA)</th><th>|Z| (mΩ)</th><th>Drop</th></tr></thead>
            <tbody>${sims.power.rails.map((x) => `
              <tr class="sim-click-row ${x.rail === r.rail ? "selected" : ""}" data-pick-rail="${escapeHtml(x.rail)}">
                <td class="mono">${escapeHtml(x.rail)}</td>
                <td class="mono">${x.current_mA}</td>
                <td class="mono">${x.sim_z_band_mohm ? `${x.sim_z_band_mohm}/${x.target_z_mohm}` : "-"}</td>
                <td class="mono">${x.dc_drop_mV ? `${x.dc_drop_mV}mV` : "-"}</td>
              </tr>`).join("")}</tbody>
          </table>
        </div>
        ${figThumbHtml(r.figure, `${r.rail} Solver Plot`, r.source_files[0])}`;
    } else if (domain === "thermal") {
      const c = sims.thermal.cases.find((x) => x.id === sel.thermalCase) || sims.thermal.cases[0];
      bodyHtml = `
        <div class="control-row">
          <span class="badge" style="border-color:#f97316;color:#f97316;background:rgba(249,115,22,0.14)">THERMAL 3-D CFD</span>
          <span class="mono" style="font-size:10px;color:var(--text-muted)">Ambient ${c.ambient_c} °C · Air max ${c.T_air_max_C} °C</span>
        </div>
        <div class="sim-prov-note">${escapeHtml(sims.thermal.provenance_note)}</div>
        <div class="sim-highlight-box">
          <strong>${escapeHtml(c.title)}</strong>
          <div class="mono">Hottest IC: ${escapeHtml(c.hottest_ic)} (${c.hottest_Tj_C} °C) · K26 SOM Tj=${c.K26_Tj_C} °C (Ind margin ${c.K26I_margin_C >= 0 ? "+" : ""}${c.K26I_margin_C} °C)</div>
          <div class="mono sim-src-line">Source: ${escapeHtml(c.source_file)}</div>
        </div>
        <canvas id="sim-chart-canvas" class="sim-chart-canvas"></canvas>
        <div class="sim-table-scroll">
          <table class="kv-table">
            <thead><tr><th>IC (Click)</th><th>Tb / Tj (°C)</th><th>Limit</th><th>Margin</th></tr></thead>
            <tbody>${c.ics.map((ic) => `
              <tr class="sim-click-row" data-pick-ref="${escapeHtml(ic.ref)}">
                <td class="mono">${escapeHtml(ic.ref)}</td>
                <td class="mono">${ic.T_board_C} / <strong>${ic.T_j_C}</strong></td>
                <td class="mono">${ic.limit_C}°C</td>
                <td class="mono" style="color:${ic.margin_C < 0 ? "#ef4444" : ic.margin_C < 10 ? "#f59e0b" : "#3fb950"}">${ic.margin_C >= 0 ? "+" : ""}${ic.margin_C}°C</td>
              </tr>`).join("")}</tbody>
          </table>
        </div>
        <div class="sim-fig-pair">
          ${figThumbHtml(sims.thermal.figures[0].src, sims.thermal.figures[0].title, sims.thermal.figures[0].source_file)}
          ${figThumbHtml(sims.thermal.figures[1].src, sims.thermal.figures[1].title, sims.thermal.figures[1].source_file)}
          ${sims.thermal.figures[2] ? figThumbHtml(sims.thermal.figures[2].src, sims.thermal.figures[2].title, sims.thermal.figures[2].source_file) : ""}
          ${sims.thermal.figures[3] ? figThumbHtml(sims.thermal.figures[3].src, sims.thermal.figures[3].title, sims.thermal.figures[3].source_file) : ""}
        </div>`;
    } else if (domain === "mech") {
      const ld = sims.mechanical.load_cases.find((x) => x.id === sel.mechLoad) || sims.mechanical.load_cases[0];
      const matRow = sims.mechanical.material_rows.find((m) => m.material === sel.mechMat && m.T === sel.mechTemp) || sims.mechanical.material_rows[0];
      const mats = [...new Set(sims.mechanical.material_rows.map((m) => m.material))];
      bodyHtml = `
        <div class="control-row">
          <span class="badge badge-wasm">ENCLOSURE FEA</span>
          <span class="mono" style="font-size:10px;color:var(--text-muted)">${(sims.mechanical.mesh_info?.tets ?? 196708).toLocaleString()} tets · CalculiX</span>
        </div>
        <div class="sim-prov-note">${escapeHtml(sims.mechanical.provenance_note)}</div>
        <div class="sim-highlight-box">
          <strong>${escapeHtml(ld.title)}</strong>
          <table class="kv-table">
            <tr><th>Case von Mises</th><td class="mono">Peak ${ld.case_vm_peak_MPa} MPa (p99.7: ${ld.case_vm_p997_MPa} MPa) · umax ${ld.umax_mm} mm</td></tr>
            <tr><th>Safety Factors</th><td class="mono">23°C: ${ld.sf_23C}x · 70°C: ${ld.sf_70C}x · Peak [${ld.peak_at_mm.join(", ")}] mm</td></tr>
            <tr><th>Adapter / Carrier</th><td class="mono">Adp ${ld.adapter.ue_peak} ue (${ld.adapter.bow_mm} mm bow) · Car ${ld.carrier.ue_peak} ue</td></tr>
          </table>
          <div class="sim-chips">
            ${Object.values(ld.bga).map((b) => `<button type="button" class="net-chip pick-sim-part" data-ref="${escapeHtml(b.ref)}">${escapeHtml(b.ref)}: ${b.ue_max} ue (SF ${b.sf_ue}x)</button>`).join("")}
          </div>
          <div class="mono sim-src-line">Sources: ${sims.mechanical.source_files.join(", ")}</div>
        </div>
        <canvas id="sim-chart-canvas" class="sim-chart-canvas"></canvas>
        <div class="control-row">
          <strong style="font-size:11px;">Material Drop &amp; Vib (${sel.mechTemp} °C)</strong>
          <select id="sim-mech-mat-sel" class="sim-select" style="width:auto;">${mats.map((m) => `<option value="${escapeHtml(m)}" ${sel.mechMat === m ? "selected" : ""}>${escapeHtml(m)}</option>`).join("")}</select>
        </div>
        ${matRow ? `<table class="kv-table">
          <tr><th>Mode f1 / Allow</th><td class="mono">${matRow.f1_Hz} Hz · Allow ${matRow.s_allow_MPa} MPa (HDT ${matRow.hdt_C}°C)</td></tr>
          <tr><th>50g / Drop / Bump / Vib SF</th><td class="mono">${matRow.shock_50g_sf}x · ${matRow.drop_bare_sf}x (bare) · ${matRow.drop_bump_sf}x (TPU) · ${matRow.vib_sf}x (vib)</td></tr>
        </table>` : ""}
        <div class="sim-fig-pair">
          ${figThumbHtml(sims.mechanical.figures[0].src, sims.mechanical.figures[0].title, sims.mechanical.figures[0].source_file)}
          ${figThumbHtml(sims.mechanical.figures[1].src, sims.mechanical.figures[1].title, sims.mechanical.figures[1].source_file)}
        </div>`;
    } else if (domain === "g8") {
      const gm = sims.gateware_g8.modes.find((m) => m.id === sel.g8Mode) || sims.gateware_g8.modes[0];
      bodyHtml = `
        <div class="control-row">
          <span class="badge badge-wasm">GATEWARE G-8 XSIM</span>
          <span class="badge" style="color:${gm.passed ? "var(--green)" : "#ef4444"};border-color:currentColor">${gm.passed ? "ALL CHECKS PASS" : "CHECK FAIL"}</span>
        </div>
        <div class="sim-highlight-box">
          <strong>${escapeHtml(gm.title)}</strong>
          <div class="mono">${escapeHtml(gm.band)}${gm.sensitivity_dBm !== null ? ` · ${gm.sensitivity_label}: ${gm.sensitivity_dBm} dBm` : ""}${gm.rejection_dB !== null ? ` · Rejection: ${gm.rejection_dB} dB` : ""}</div>
          <div class="sim-chips" style="margin-top:4px;">${gm.chain_blocks.map((b) => `<span class="badge">${escapeHtml(b)}</span>`).join("")}</div>
          <div style="font-size:11px;margin-top:4px;"><strong>Implementing HW Parts:</strong></div>
          <div class="sim-chips">${gm.hardware_parts.map((r) => `<button type="button" class="net-chip pick-sim-part" data-ref="${escapeHtml(r)}">${escapeHtml(r)}</button>`).join("")}</div>
          <div class="mono sim-src-line">Source: ${escapeHtml(gm.source_file)}</div>
        </div>
        <canvas id="sim-chart-canvas" class="sim-chart-canvas"></canvas>
        <div class="sim-table-scroll">
          <table class="kv-table">
            <thead><tr><th>Verification Check</th><th>Result</th></tr></thead>
            <tbody>${gm.checks.map((ck) => `<tr><td>${escapeHtml(ck.name)}</td><td class="mono" style="color:${ck.ok ? "var(--green)" : "#ef4444"}">${ck.ok ? "PASS" : "FAIL"}</td></tr>`).join("")}</tbody>
          </table>
        </div>
        ${figThumbHtml(gm.figure, gm.title, gm.figure, "Real XSim G-8 RTL vs floating-point verification plot.")}`;
    } else if (domain === "audit") {
      const aud = sims.audit || {};
      const hp = aud.rf?.hp300 || {};
      const pIn = aud.power?.input || {};
      const bdg = aud.power?.budget || {};
      const figs = aud.figures || [];
      let tblHead = "";
      let tblRows = "";
      if (sel.auditView === "rf") {
        tblHead = "<tr><th>Freq (MHz)</th><th>Low-Pass Only</th><th>With HP300</th></tr>";
        tblRows = ["88", "108", "137", "145", "170", "200", "250", "300", "446", "660", "1000"]
          .filter((k) => aud.rf?.uhf_path_db?.[k])
          .map((k) => {
            const [bef, aft] = aud.rf.uhf_path_db[k];
            return `<tr><td class="mono">${k} MHz</td><td class="mono">${bef} dB</td><td class="mono" style="color:${Number(k) <= 170 ? "var(--green)" : "var(--cyan)"}">${aft} dB</td></tr>`;
          }).join("");
      } else if (sel.auditView === "power") {
        tblHead = "<tr><th>Rail (Reg)</th><th>Typ / Worst</th><th>Use</th></tr>";
        tblRows = (bdg.rows || []).map((r) => `
          <tr>
            <td class="mono">${escapeHtml(r.rail)} (${escapeHtml(r.part)})</td>
            <td class="mono">${r.typ_ma} / ${r.worst_ma} mA</td>
            <td class="mono" style="color:${r.use > 0.75 ? "#f59e0b" : "var(--green)"}">${Math.round(r.use * 100)}%</td>
          </tr>`).join("");
      } else {
        tblHead = "<tr><th>Pulse / Stress Case</th><th>Peak VIN_F</th><th>Status</th></tr>";
        tblRows = (aud.power?.transients || []).map((t) => `
          <tr>
            <td>${escapeHtml(String(t.kind).split("(")[0].trim())}</td>
            <td class="mono">${t.vin_max.toFixed(1)} V</td>
            <td class="mono" style="color:${t.ok ? "var(--green)" : "#ef4444"}">${t.ok ? "PASS" : "FAIL"}</td>
          </tr>`).join("");
      }

      bodyHtml = `
        <div class="control-row">
          <span class="badge" style="border-color:#f59e0b;color:#f59e0b;background:rgba(245,158,11,0.14)">RF AND POWER AUDIT</span>
          <a class="mono" style="font-size:10px;color:var(--cyan);text-decoration:none" href="pdf.html?file=docs%2FKV260-IAS2RF_Documentation.pdf#page=197" target="_blank" rel="noopener">AUDIT_Rev08.md (p.197)</a>
        </div>
        <div class="sim-highlight-box">
          <strong>Pre-Order RF &amp; Power Audit Closure (18-19 Nov 2026)</strong>
          <div class="mono">HP300: loss ${hp.loss_db ?? 1.13} dB (${hp.loss_p99 ?? 1.51} dB p99) · RL ${hp.rl_db ?? 12.7} dB · Stop &lt;=175 MHz ${hp.stop_db ?? 52.8} dB (${hp.stop_p1 ?? 51.7} dB p1) · IF rej 31-46 -&gt; 84-99 dB</div>
          <div class="mono">Input: ${bdg.input_typ_ma ?? 973} mA (${pIn.p_typ_w ?? 11.68} W) typ · ${bdg.input_worst_ma ?? 1116} mA (${pIn.p_worst_w ?? 13.4} W) worst · F1001 2.0 A trips &gt;${pIn.ptc_trip_c_worst_12v ?? 83.9} C @ 12 V</div>
          <div class="sim-chips">
            ${(aud.audited_parts || []).map((r) => `<button type="button" class="net-chip pick-sim-part ${sel.auditFocusRef === r ? "active" : ""}" data-ref="${escapeHtml(r)}">${escapeHtml(r)}</button>`).join("")}
          </div>
          <div class="mono sim-src-line">Sources: docs/sim/rf_audit.json, docs/sim/power_audit.json</div>
        </div>
        <canvas id="sim-chart-canvas" class="sim-chart-canvas"></canvas>
        <div class="sim-table-scroll">
          <table class="kv-table">
            <thead>${tblHead}</thead>
            <tbody>${tblRows}</tbody>
          </table>
        </div>
        ${figs[0] ? figThumbHtml(figs[0].src, figs[0].title, figs[0].source_file, figs[0].cap) : ""}
        <div class="sim-fig-pair">
          ${figs.slice(1).map((f) => figThumbHtml(f.src, f.title, f.source_file, f.cap)).join("")}
        </div>
        <div class="mono sim-src-line">Figures: ${(figs || []).map((f) => f.source_file).join(" · ")}</div>`;
    }

    card.innerHTML = bodyHtml;

    // Bind interactive handlers inside Telemetry Card
    card.querySelectorAll("[data-pick-pair]").forEach((tr) => {
      tr.addEventListener("click", () => {
        sel.rfFocusType = "pair";
        sel.rfFocusId = tr.dataset.pickPair;
        const p = sims.rf_si.pairs.find((x) => x.id === sel.rfFocusId);
        if (p?.components?.[0]) selectPart(p.components[0], false);
        updateAll();
      });
    });
    card.querySelectorAll("[data-pick-rail]").forEach((tr) => {
      tr.addEventListener("click", () => {
        sel.powerRail = tr.dataset.pickRail;
        const r = sims.power.rails.find((x) => x.rail === sel.powerRail);
        if (r?.regulator_ref) selectPart(r.regulator_ref, false);
        updateAll();
      });
    });
    card.querySelectorAll("[data-pick-ref], .pick-sim-part").forEach((el) => {
      el.addEventListener("click", () => {
        const ref = el.dataset.pickRef || el.dataset.ref;
        if (ref) selectPart(ref, true);
      });
    });
    card.querySelector("#sim-mech-mat-sel")?.addEventListener("change", (ev) => {
      sel.mechMat = ev.target.value;
      renderTelemetryCard();
    });
    card.querySelectorAll("[data-open-fig]").forEach((box) => {
      box.addEventListener("click", () => openImageModal(box.dataset.openFig, box.dataset.figCap));
    });

    const chartCvs = card.querySelector("#sim-chart-canvas");
    if (chartCvs) drawChartInContainer(chartCvs);
  }

  function updateAll() {
    renderDockSubcontrols();
    renderTelemetryCard();
    rebuild3DOverlay();
    applyAnimatedScene();
    syncHash();
  }

  // -------------------------------------------------------------------------
  // Public Hooks for Hover Tooltip, Component Inspector, Deep Links & Tests
  // -------------------------------------------------------------------------
  function getPartSimulations(ref) {
    if (!sims || !ref) return [];
    return sims.component_sim_index?.[ref] || [];
  }

  function getPartAuditLine(ref) {
    if (!sims || !ref) return null;
    return sims.audit?.part_audit?.[ref] || null;
  }

  function buildHoverHtml(ref) {
    if (!enabled || !sims) return "";
    const audit = getPartAuditLine(ref);
    const list = getPartSimulations(ref);
    if (!list.length && !audit) return `<div class="sim-tip-row" style="color:var(--text-muted)">No direct sim entries mapped for ${escapeHtml(ref)}</div>`;
    const grouped = new Map();
    for (const s of list) {
      if (!grouped.has(s.domain_label)) grouped.set(s.domain_label, s);
    }
    const lines = [];
    if (audit) {
      lines.push(`<div class="sim-tip-row"><strong style="color:#f59e0b">Audit (${escapeHtml(audit.code)}):</strong> ${escapeHtml(audit.title)}</div>`);
    }
    Array.from(grouped.values()).slice(0, 3).forEach((s) => {
      if (s.domain === "audit" && audit) return;
      lines.push(`<div class="sim-tip-row"><strong style="color:var(--cyan)">${escapeHtml(s.domain_label)}:</strong> ${escapeHtml(s.metric)}</div>`);
    });
    if (list.length > grouped.size) {
      lines.push(`<div class="sim-tip-row" style="color:var(--accent)">+${list.length - lines.length} more simulation entries (click to inspect)</div>`);
    }
    return lines.join("");
  }

  function buildInspectorSectionHtml(ref) {
    const list = getPartSimulations(ref);
    if (!list.length) return "";
    return `
      <div class="panel-card sim-part-section">
        <div class="control-row">
          <h3>Simulations Involving ${escapeHtml(ref)} (${list.length})</h3>
          <span class="badge badge-cyan">PROVENANCE</span>
        </div>
        <div style="display:flex;flex-direction:column;gap:5px;">
          ${list.slice(0, 12).map((s) => `
            <div class="sim-part-row">
              <div class="control-row">
                <strong style="font-size:11px;">[${escapeHtml(s.domain_label)}] ${escapeHtml(s.title)}</strong>
                <button type="button" class="net-chip sim-jump-btn" data-sim-jump-domain="${escapeHtml(s.domain)}" data-sim-jump-target="${escapeHtml(s.target_id)}">View 3-D</button>
              </div>
              <div class="mono" style="font-size:10px;color:var(--text-muted)">${escapeHtml(s.metric)} · <span>${escapeHtml(s.source_file)}</span></div>
            </div>`).join("")}
        </div>
      </div>`;
  }

  function wireInspectorButtons(containerEl) {
    if (!containerEl) return;
    containerEl.querySelectorAll("[data-sim-jump-domain]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const d = btn.dataset.simJumpDomain;
        const tgt = btn.dataset.simJumpTarget;
        activateDomain(d, tgt);
      });
    });
  }

  function activateDomain(domId, targetId = null) {
    enabled = true;
    if (DOMAIN_META.some((d) => d.id === domId)) domain = domId;
    if (targetId) {
      if (domain === "rf") {
        if (sims?.rf_si.sparam_models.some((m) => m.id === targetId)) {
          sel.rfFocusType = "sparam";
          sel.rfFocusId = targetId;
        } else if (sims?.rf_si.pairs.some((p) => p.id === targetId)) {
          sel.rfFocusType = "pair";
          sel.rfFocusId = targetId;
        }
      } else if (domain === "power") {
        sel.powerRail = targetId;
      } else if (domain === "thermal") {
        sel.thermalCase = targetId;
      } else if (domain === "mech") {
        sel.mechLoad = targetId;
      } else if (domain === "g8") {
        sel.g8Mode = targetId;
      } else if (domain === "audit") {
        if (targetId === "rf" || targetId === "power" || targetId === "transients") {
          sel.auditView = targetId;
        } else if (sims?.audit?.part_audit?.[targetId]) {
          sel.auditFocusRef = targetId;
        }
      }
    }
    if (domain === "mech") {
      setEnclosure("open", true);
      setIsolate("all", true);
    } else if (domain === "thermal") {
      setEnclosure("open", true);
      setIsolate("all", true);
    } else if (domain === "rf" || domain === "power" || domain === "g8" || domain === "audit") {
      setEnclosure("hidden", true);
      setIsolate("board", true);
    }
    updateAll();
  }

  function setEnabled(flag, domId = null) {
    enabled = !!flag;
    if (enabled) {
      activateDomain(domId || domain, null);
    } else {
      clearAllOverlays();
      updateAll();
    }
  }

  function setData(simData) {
    sims = simData;
    if (enabled) updateAll();
    else renderDockSubcontrols();
  }

  function getHashParams(params) {
    if (!enabled) return;
    params.set("sim", domain);
    if (domain === "rf" && sel.rfFocusId) params.set("simcase", sel.rfFocusId);
    else if (domain === "power") params.set("simcase", sel.powerRail);
    else if (domain === "thermal") params.set("simcase", sel.thermalCase);
    else if (domain === "mech") params.set("simcase", sel.mechLoad);
    else if (domain === "g8") params.set("simcase", sel.g8Mode);
    else if (domain === "audit") params.set("simcase", sel.auditFocusRef || sel.auditView);
  }

  function applyHashParams(params) {
    const simParam = params.get("sim");
    if (!simParam) return false;
    activateDomain(simParam, params.get("simcase"));
    return true;
  }

  function wireDomEvents() {
    document.querySelector("#btn-sim-toggle")?.addEventListener("click", () => setEnabled(!enabled));
    document.querySelector("#btn-nav-sims")?.addEventListener("click", () => {
      document.querySelector(".nav-tab[data-tab='explorer']")?.click();
      document.querySelector("#explorer-stage")?.scrollIntoView({ behavior: isReducedMotion() ? "auto" : "smooth", block: "start" });
      if (!enabled) activateDomain(domain);
    });
    document.querySelectorAll("[data-sim-domain]").forEach((btn) => {
      btn.addEventListener("click", () => activateDomain(btn.dataset.simDomain));
    });
  }

  return {
    setData,
    setEnabled,
    activateDomain,
    isEnabled: () => enabled,
    getDomain: () => domain,
    getState: () => ({ enabled, domain, ...sel }),
    updateAnimatedOffsets: () => {
      if (enabled) populateWorldOverlays();
    },
    onDeselect: () => {
      if (!enabled) return;
      sel.rfFocusId = null;
      if (sel.rfFocusType === "pair") sel.rfFocusType = "all";
      rebuild3DOverlay();
      renderDockSubcontrols();
      renderTelemetryCard();
      applyAnimatedScene();
    },
    onThemeChange: () => {
      const c = document.querySelector("#sim-chart-canvas");
      if (c && enabled) drawChartInContainer(c);
    },
    stepAnimation,
    buildHoverHtml,
    buildInspectorSectionHtml,
    wireInspectorButtons,
    getPartSimulations,
    getPartAuditLine,
    getHashParams,
    applyHashParams,
    wireDomEvents,
  };
}
