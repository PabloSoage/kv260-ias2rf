/**
 * Simulated kria-hmid WebSocket backend for the Slint WebAssembly HMI when
 * hosted statically on GitHub Pages (or loaded offline without kria-hmid).
 * Implements the JSON snapshot schema read by sw/hmi/app/src/lib.rs and
 * responds to interactive commands from sw/hmi/app/ui/app.slint.
 */

export function installHmiSimWebSocket() {
  const params = new URLSearchParams(location.search);
  const liveUrl = params.get("ws");
  if (liveUrl) return { live: true };

  const simState = {
    t: 0,
    fn: "radio",
    freq_hz: 98.1e6,
    mode: "wbfm",
    gain_db: 12,
    recording: false,
    rec_bytes: 0,
    marker_frac: 0.5,
    presets: [
      { name: "HF AM 7.2", freq_hz: 7.2e6, mode: "am" },
      { name: "HF USB 14.2", freq_hz: 14.2e6, mode: "usb" },
      { name: "FM 98.1", freq_hz: 98.1e6, mode: "wbfm" },
      { name: "Air 121.5", freq_hz: 121.5e6, mode: "am" },
      { name: "PMR 446", freq_hz: 446.00625e6, mode: "nbfm" },
      { name: "ADS-B", freq_hz: 1090.0e6, mode: "adsb" },
    ],
    speed_kmh: 0,
    parked_s: 5.0,
    rpm: 760,
    coolant_c: 86,
    fuel_pct: 64,
    veh_source: "CAN1 (R5F1) + opendash",
    tx_freq_hz: 7.1e6,
    tx_mode: "lsb",
    tx_level: 0.5,
    tx_licensed: true,
    tx_requested: false,
    alpha_q8: 1536,
    frames: 100,
    cpis: 4200,
    adsb_frames: 312,
    packets: 205000,
    blocks: 2940,
  };

  window.__IAS2RF_HMI_SIM = simState;

  // Build initial 64x16 radar range-Doppler map with 3 synthetic targets
  function buildRadarMap(t) {
    const rows = [];
    const targets = [
      { r: 18, d: 10, p: -6 },
      { r: 34, d: 5, p: -14 },
      { r: 48, d: 13, p: -22 },
    ];
    for (let r = 0; r < 64; r++) {
      const row = [];
      for (let d = 0; d < 16; d++) {
        let v = -56 + Math.sin(r * 1.7 + d * 2.3 + t) * 2.2;
        for (const tg of targets) {
          const dr = r - tg.r;
          const dd = d - tg.d;
          v = Math.max(v, tg.p - (dr * dr * 5.0 + dd * dd * 7.5));
        }
        row.push(+v.toFixed(1));
      }
      rows.push(row);
    }
    return rows;
  }

  function makeSnapshot() {
    simState.t += 0.15;
    simState.frames += 1;
    simState.cpis += 40;
    simState.adsb_frames += 2;
    simState.packets += 340;
    simState.blocks += 5;
    if (simState.recording) simState.rec_bytes += 96000;

    if (simState.speed_kmh < 1.0) simState.parked_s += 0.15;
    else if (simState.speed_kmh >= 3.0) simState.parked_s = 0;

    const isHf = simState.freq_hz < 30e6;
    const isDirect = simState.freq_hz >= 30e6 && simState.freq_hz <= 170e6;
    const isGap = simState.freq_hz > 170e6 && simState.freq_hz < 300e6;
    const path = isHf ? "hf" : isDirect ? "direct" : isGap ? "uncovered" : "converted";
    const span = isHf ? 2.5e6 : 2.5e6;

    const trace = [];
    const nSpec = 128;
    const sigPos = 0.5 + 0.18 * Math.sin(simState.t * 0.25);
    for (let i = 0; i < nSpec; i++) {
      const x = i / (nSpec - 1);
      const dMain = (x - 0.5) * 48;
      const dNbr = (x - sigPos) * 40;
      const floor = -98 + 2.5 * Math.sin(i * 0.9 + simState.t * 3.0);
      const sig = -26 * Math.exp(-dMain * dMain) - 48 * Math.exp(-dNbr * dNbr);
      trace.push(+(floor + sig + 40).toFixed(1));
    }

    const row = trace.slice(0, 128);
    const txAllowed =
      simState.tx_licensed &&
      simState.parked_s >= 3.0 &&
      simState.tx_freq_hz < 12.5e6;
    const txKeyed = txAllowed && simState.tx_requested;
    let txReason = "idle";
    if (!simState.tx_licensed) txReason = "no licence";
    else if (simState.speed_kmh >= 3.0) txReason = "moving (>= 3 km/h)";
    else if (simState.parked_s < 3.0) txReason = `settling (${(3.0 - simState.parked_s).toFixed(1)} s)`;
    else if (simState.tx_freq_hz >= 12.5e6) txReason = "HF only (< 12.5 MHz)";

    const wbTrace = [];
    for (let i = 0; i < 180; i++) {
      const f = i * 40e6;
      let p = -86 + 2.0 * Math.sin(i * 1.1 + simState.t);
      if (Math.abs(f - 98e6) < 40e6) p = -28;
      if (Math.abs(f - 446e6) < 40e6) p = -34;
      if (Math.abs(f - 1090e6) < 40e6) p = -31;
      if (Math.abs(f - 2440e6) < 80e6) p = -39;
      wbTrace.push(+p.toFixed(1));
    }

    const bart = [];
    const mus = [];
    for (let d = 0; d < 72; d++) {
      const deg = d * 5;
      const diff1 = Math.min(Math.abs(deg - 117), 360 - Math.abs(deg - 117));
      const diff2 = Math.min(Math.abs(deg - 250), 360 - Math.abs(deg - 250));
      bart.push(+(-22 + 18 * Math.exp(-(diff1 * diff1) / 380) + 15 * Math.exp(-(diff2 * diff2) / 420)).toFixed(2));
      mus.push(+(-36 + 34 * Math.exp(-(diff1 * diff1) / 22) + 30 * Math.exp(-(diff2 * diff2) / 24)).toFixed(2));
    }

    return {
      t: simState.t,
      function: simState.fn,
      radio: {
        freq_hz: simState.freq_hz,
        mode: simState.mode === "adsb" ? "am" : simState.mode,
        path,
        lo_hz: path === "converted" ? simState.freq_hz - 120e6 : 0,
        level_dbfs: -18.4 + Math.sin(simState.t * 4.0) * 1.2,
        audio_rate: 48000,
        pilot: simState.mode === "wbfm",
        ctcss: simState.mode === "nbfm",
        gain_db: simState.gain_db,
        rds: simState.mode === "wbfm"
          ? { ps: "KV260FM ", radiotext: "KV260-IAS2RF Browser Sim (G-8 WBFM + RDS)", pi: 0xe201, pty: 10, groups: simState.frames }
          : { ps: "", radiotext: "", pty: 0, groups: 0 },
        presets: simState.presets.map((p) => ({ name: p.name, freq_hz: p.freq_hz })),
      },
      spectrum: {
        trace,
        row,
        center_hz: simState.freq_hz,
        span_hz: span,
        marker_hz: simState.freq_hz + (simState.marker_frac - 0.5) * span,
        stream: isHf ? 0x04 : 0x01,
        frames: simState.frames,
      },
      adsb: {
        frames: simState.adsb_frames,
        own: [43.3623, -8.4115],
        aircraft: [
          { callsign: "IBE3412", icao: "34510A", range_km: 28, bearing_deg: (35 + simState.t * 2) % 360, alt_ft: 34000, speed_kt: 452, track_deg: 195 },
          { callsign: "RYR88K", icao: "4CA211", range_km: 54, bearing_deg: (142 - simState.t) % 360, alt_ft: 38000, speed_kt: 468, track_deg: 25 },
          { callsign: "VLG2104", icao: "3442C1", range_km: 71, bearing_deg: 278, alt_ft: 29500, speed_kt: 410, track_deg: 112 },
          { callsign: "EZY49P", icao: "406A12", range_km: 41, bearing_deg: 310, alt_ft: 36000, speed_kt: 440, track_deg: 165 },
        ],
      },
      radar: {
        cpi: simState.cpis % 64,
        cpis: simState.cpis,
        dropped: 0,
        alpha_q8: simState.alpha_q8,
        floor: 1250,
        map: { power_db: buildRadarMap(simState.t) },
        detections: [
          { range_m: 142.0, speed_mps: 8.5, power_db: -6.0, doppler_bin: 2, range_bin: 18 },
          { range_m: 268.5, speed_mps: -12.0, power_db: -14.0, doppler_bin: -3, range_bin: 34 },
          { range_m: 379.0, speed_mps: 20.5, power_db: -22.0, doppler_bin: 5, range_bin: 48 },
        ],
      },
      vehicle: {
        speed_kmh: simState.speed_kmh,
        rpm: simState.speed_kmh > 1 ? Math.round(900 + simState.speed_kmh * 32) : 760,
        coolant_c: simState.coolant_c,
        fuel_pct: simState.fuel_pct,
        source: simState.veh_source,
      },
      tx: {
        freq_hz: simState.tx_freq_hz,
        mode: simState.tx_mode,
        level: simState.tx_level,
        keyed: txKeyed,
        licensed: simState.tx_licensed,
        requested: simState.tx_requested,
        reason: txKeyed ? "idle" : txReason,
      },
      wideband: {
        trace_db: wbTrace,
        covered: 1.0,
        signals: [
          { f: 98.1e6, dbfs: -28 },
          { f: 446.006e6, dbfs: -34 },
          { f: 1090.0e6, dbfs: -31 },
          { f: 2440.0e6, dbfs: -39 },
        ],
      },
      bearing: {
        f_rf: 145.5e6,
        sources: 2,
        eig_db: [38, 34, 12, 11, 10],
        cal: { lag: [0, 1, -1, 0, 2] },
        bartlett_db: bart,
        music_db: mus,
        music_bearings: [117.0, 250.0],
        beam_power_db: [14.2, 11.8],
      },
      system: {
        link_up: true,
        packets: simState.packets,
        blocks: simState.blocks,
        seq_gaps: 0,
        crc_errors: 0,
        stream_mbps: 18.4,
        temp_k26_c: 54.2,
        temp_artix_c: 48.7,
        r5f0: txKeyed ? "TX_KEY = 0x4B45_5901" : "TX_KEY = 0x4B45_5900",
        r5f1: `CAN1 SNOOP (${simState.speed_kmh} km/h)`,
        platform: "Browser WASM Sim (Mock kria-hmid)",
        rec_file: simState.recording ? "iq_sim_demo.u64" : "",
        rec_bytes: simState.rec_bytes,
        recording: simState.recording,
      },
    };
  }

  function handleCommand(raw) {
    try {
      const c = JSON.parse(raw);
      switch (c.cmd) {
        case "step":
          simState.freq_hz = Math.max(100e3, simState.freq_hz + (c.hz || 0));
          break;
        case "tune":
          simState.freq_hz = Math.max(100e3, c.freq_hz || simState.freq_hz);
          if (simState.freq_hz < 20e6 && simState.mode === "wbfm") simState.mode = "usb";
          if (simState.freq_hz >= 87.5e6 && simState.freq_hz <= 108e6) simState.mode = "wbfm";
          break;
        case "set_mode":
          simState.mode = c.mode || simState.mode;
          break;
        case "preset": {
          const p = simState.presets[c.index];
          if (p) {
            simState.freq_hz = p.freq_hz;
            simState.mode = p.mode;
          }
          break;
        }
        case "marker_frac":
          simState.marker_frac = Math.min(1, Math.max(0, c.x ?? 0.5));
          break;
        case "listen_at_marker":
          simState.freq_hz += (simState.marker_frac - 0.5) * 2.5e6;
          simState.marker_frac = 0.5;
          break;
        case "record":
          simState.recording = !!c.on;
          break;
        case "function":
          simState.fn = c.function || "radio";
          break;
        case "radar_alpha_step":
          simState.alpha_q8 = Math.max(256, Math.min(4096, simState.alpha_q8 + (c.step || 0)));
          break;
        case "tx_set":
          if (typeof c.freq_hz === "number") simState.tx_freq_hz = c.freq_hz;
          if (c.mode) simState.tx_mode = c.mode;
          if (typeof c.level === "number") simState.tx_level = Math.max(0, Math.min(1, c.level));
          break;
        case "licence":
          simState.tx_licensed = !!c.on;
          break;
        case "tx_request":
          simState.tx_requested = !!c.on;
          break;
      }
    } catch (_) {
      // Ignore malformed commands
    }
  }

  class MockWebSocket {
    constructor(url) {
      this.url = url;
      this.readyState = 0; // CONNECTING
      this.binaryType = "blob";
      this.onopen = null;
      this.onmessage = null;
      this.onclose = null;
      this.onerror = null;
      this._listeners = {};
      setTimeout(() => {
        this.readyState = 1; // OPEN
        const ev = new Event("open");
        if (this.onopen) this.onopen(ev);
        (this._listeners.open || []).forEach((fn) => fn(ev));
        this._push();
        this._timer = setInterval(() => this._push(), 150);
      }, 30);
    }
    _push() {
      if (this.readyState !== 1) return;
      const ev = new MessageEvent("message", { data: JSON.stringify(makeSnapshot()) });
      if (this.onmessage) this.onmessage(ev);
      (this._listeners.message || []).forEach((fn) => fn(ev));
    }
    addEventListener(type, fn) {
      (this._listeners[type] ||= []).push(fn);
    }
    removeEventListener(type, fn) {
      this._listeners[type] = (this._listeners[type] || []).filter((f) => f !== fn);
    }
    send(data) {
      handleCommand(data);
      this._push();
    }
    close() {
      this.readyState = 3;
      if (this._timer) clearInterval(this._timer);
    }
  }

  MockWebSocket.CONNECTING = 0;
  MockWebSocket.OPEN = 1;
  MockWebSocket.CLOSING = 2;
  MockWebSocket.CLOSED = 3;

  window.WebSocket = MockWebSocket;
  return { live: false, simState };
}
