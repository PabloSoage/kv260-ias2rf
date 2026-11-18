/**
 * Interactive & animated [Mock-up] widgets powered by the Rust/WASM SiteCore engine.
 */

const SIGNAL_MODES = [
  {
    id: "wbfm",
    name: "WBFM 98.1 MHz",
    band: "87.5 - 108 MHz",
    chain: [
      { label: "J601 V/UHF SMA", spec: "50 ohm coax -> ESD + BPF", detail: "Wideband VHF antenna feed routed to SPDT RF switch matrix (U601/U602) on RX_VU." },
      { label: "SKY13384 / LNA", spec: "Passband 70-200 MHz", detail: "Selects VHF-band analog conditioning and flat passband gain ahead of AD9253 Ch A." },
      { label: "AD9253 (U701)", spec: "14-bit @ 62.5 MSPS", detail: "Dual-channel SDR ADC samples Nyquist zones via Transformer T701; 1-lane DDR LVDS to XC7A50T." },
      { label: "Artix DDC + FIFO", spec: "CIC / FIR -> 1.0 MSPS IQ", detail: "XC7A50T (U1101) digitally down-converts and packs 16-bit I/Q frames over IAS1 64b/66b." },
      { label: "K26 PL + R5F/A53", spec: "FM Quad + 19k Pilot + RDS", detail: "Polar discriminator, stereo 38 kHz DSB-SC decode, de-emphasis 50 us and RBDS/RDS parser." },
    ],
  },
  {
    id: "airband",
    name: "Airband AM 121.5",
    band: "108 - 137 MHz",
    chain: [
      { label: "J601 V/UHF SMA", spec: "VHF Airband AM rx", detail: "Aviation distress / ATC channel received on VHF antenna path." },
      { label: "VHF Preselector", spec: "Sub-octave filter", detail: "Rejects strong 88-108 MHz FM broadcast carriers before ADC quantization." },
      { label: "AD9253 (U701)", spec: "14-bit @ 62.5 MSPS", detail: "Undersampling captures 121.5 MHz in 4th Nyquist zone with low clock jitter from Si549." },
      { label: "Artix DDC", spec: "25 kHz / 8.33 kHz chan", detail: "Equiripple FIR channelizer selects narrow AM voice channel." },
      { label: "K26 AM Envelope", spec: "Synchronous + Hang AGC", detail: "DC blocker + envelope detector + hang AGC feeds cockpit audio and waterfall display." },
    ],
  },
  {
    id: "hf_am",
    name: "HF AM 7.10 MHz",
    band: "0.5 - 30 MHz",
    chain: [
      { label: "J602 HF SMA", spec: "Direct-sampling HF port", detail: "HF port with gas discharge & ESD clamp feeding 30 MHz 7-pole low-pass roofing filter." },
      { label: "30 MHz LPF", spec: "7-pole elliptic filter", detail: "> 55 dB stopband attenuation above 35 MHz protecting 1st Nyquist zone." },
      { label: "AD9253 (U701)", spec: "14-bit @ 62.5 MSPS", detail: "Direct baseband Nyquist-1 digitization across DC - 31.25 MHz." },
      { label: "Artix DDC", spec: "NCO + CIC + CFIR", detail: "Tuned to 7.100 MHz with 6 kHz AM bandwidth sent on IAS1 stream." },
      { label: "K26 Demod", spec: "AM carrier tracking", detail: "Exalted-carrier demodulator + notch filter outputs clean shortwave audio." },
    ],
  },
  {
    id: "hf_ssb",
    name: "HF USB 7.074 MHz",
    band: "0.5 - 30 MHz",
    chain: [
      { label: "J602 HF SMA", spec: "50 ohm HF front end", detail: "HF port coupled through transformer balun into 30 MHz anti-alias roofing filter." },
      { label: "T701 / LPF", spec: "DC-30 MHz differential", detail: "1:1 RF transformer balances single-ended antenna into AD9253 Ch B inputs." },
      { label: "AD9253 (U701)", spec: "50 or 62.5 MSPS", detail: "14-bit dynamic range handles weak FT8/SSB signals beside strong broadcasters." },
      { label: "Artix + IAS1", spec: "3 kHz SSB slice", detail: "Decimated complex I/Q stream with 64b/66b framing & SGMII split-failover path." },
      { label: "K26 Phasing USB", spec: "Weaver / Hilbert 2.4 kHz", detail: "Opposite-sideband rejection > 55 dB feeding passband tuning & spectrum." },
    ],
  },
  {
    id: "nbfm",
    name: "VHF/UHF NBFM",
    band: "144 / 433 MHz",
    chain: [
      { label: "J601 V/UHF SMA", spec: "2 m / 70 cm band", detail: "Switched VHF/UHF path selected over ROUTING coaxial switch matrix." },
      { label: "BPF + LNA", spec: "SAW/ceramic preselect", detail: "Selects 144-148 MHz or 430-440 MHz BPF window." },
      { label: "AD9253 (U701)", spec: "IF / harmonic sample", detail: "Digitizes VHF/UHF signals via Si549 low-phase-noise sample clock." },
      { label: "Artix DDC", spec: "12.5 kHz / 25 kHz FM", detail: "Packs narrowband I/Q stream and sends RSSI / squelch frames." },
      { label: "K26 NBFM + CTCSS", spec: "5 kHz dev + Goertzel", detail: "Limiting discriminator + Goertzel 67-254 Hz sub-audible tone decoder." },
    ],
  },
  {
    id: "adsb",
    name: "ADS-B 1090 MHz",
    band: "1090 MHz Mode-S",
    chain: [
      { label: "J603 1090/UHF", spec: "1090 MHz BPF + LNA", detail: "Dedicated L-band ceramic bandpass filter around 1090 MHz (+/-15 MHz)." },
      { label: "AD9484 / IF Down", spec: "High-speed sampling", detail: "Captures 2 Mbps Manchester PPM bursts on 1090 MHz down-converted IF." },
      { label: "Artix Preamble", spec: "8 us pulse detector", detail: "Flags 0, 1.0, 3.5, 4.5 us Mode-S preamble pattern and timestamps to PPS edge." },
      { label: "IAS1 -> K26 PL", spec: "kria_pps 10 ns stamp", detail: "Attaches GPS-disciplined 10 ns counter for CPR & multilateration." },
      { label: "K26 DF17 Decoder", spec: "CRC-24 + CPR Map", detail: "Decodes ICAO 24-bit ID, lat/lon/alt/track and plots aircraft on HMI radar ring." },
    ],
  },
  {
    id: "radar",
    name: "10.5 GHz FMCW Radar",
    band: "8x ADAR1000 Phased Array",
    chain: [
      { label: "AD9708 (U901)", spec: "8-bit 100 MSPS Chirp", detail: "Generates linear FM up-chirp on DAC_RADAR -> upconverted to X-band LO." },
      { label: "8x ADAR1000 Array", spec: "SPI csb[7:0], TR_BEAM", detail: "R5F Core 1 + Artix sweep azimuth beams via SPI phase weights & beam strobes." },
      { label: "AD9484 (U501)", spec: "8-bit @ 400 MSPS", detail: "Samples 120 MHz echo IF via LVDS DDR pairs with 512-tap IDELAY calibration." },
      { label: "Artix + K26 BEV", spec: "Range-Doppler + CFAR", detail: "2-D FFT + CFAR targets fused with LiDAR in `kria_bev_grid` PL accelerator." },
      { label: "HMI Polar PPI", spec: "Range vs Azimuth", detail: "Live targets rendered on Radar PPI and fused BEV occupancy grid." },
    ],
  },
  {
    id: "tx",
    name: "TX SSB / NBFM",
    band: "TX_KEY Interlock Gated",
    chain: [
      { label: "R5F + TX_KEY CSR", spec: "0x8000_0038 Interlock", detail: "Hardware safety gate requires speed == 0 km/h (Parked), licence OK, PTT <= 180 s." },
      { label: "K26 A53/PL Mod", spec: "SSB / NBFM Baseband", detail: "Generates complex envelope; `DSP_CTRL[1]` mirrors hardware `dsp_tx_en` RO state." },
      { label: "AD9767 (U1001)", spec: "Dual 14b @ 100 MSPS", detail: "Quadrature DAC (IQWRT / IQCLK / IQSEL) converts complex I/Q back to analog." },
      { label: "TX Filter / PA", spec: "Harmonic LPF > 48 dBc", detail: "Attenuates images & spurious emissions prior to TX T/R switch." },
      { label: "J601 / J602 SMA", spec: "Ant out (HW gated)", detail: "RF output only enabled when R5F holds TX_KEY valid; hardware kills TX on motion." },
    ],
  },
];

const V80_CAN_SAMPLES = [
  { id: "0x215", name: "ABS / Wheel Speed", dlc: 8, bytes: "00 00 1A 90 1A 88 00 40", decoded: "FL=68.0 km/h, FR=67.9 km/h -> TX_KEY LOCKED" },
  { id: "0x218", name: "Engine RPM & ECT", dlc: 8, bytes: "00 00 0B B8 5C 00 00 12", decoded: "RPM=750 idle, Coolant=92 C, Gear=P" },
  { id: "0x236", name: "Steering Angle", dlc: 6, bytes: "01 F4 00 10 00 00", decoded: "Angle=+0.0 deg, Rate=0 deg/s" },
  { id: "0x412", name: "Cluster & Odometer", dlc: 8, bytes: "00 03 8A 20 00 00 02 01", decoded: "Odo=231,968 km, Parked=true, Ign=ON" },
];

export function initMockups(root, getCore, isActiveTab) {
  root.innerHTML = "";

  // 1. Signal Path Explorer + Live Rust DSP Spectrum & Waveform
  const sigCard = document.createElement("article");
  sigCard.className = "mockup-card";
  sigCard.innerHTML = `
    <div class="mockup-title">
      <h3>1. Signal Path Explorer &amp; Rust DSP Chain (8 Modes)</h3>
      <span class="tag-mockup">[Mock-up] WASM</span>
    </div>
    <div style="display:flex;gap:6px;flex-wrap:wrap;" id="mk-mode-btns"></div>
    <div id="mk-chain" class="chain-strip"></div>
    <canvas id="mk-dsp-canvas" class="sim-canvas" width="560" height="155"></canvas>
    <div id="mk-dsp-meters" class="meter-row"></div>
    <div id="mk-chain-detail" class="panel-card" style="font-size:12px;"></div>
  `;
  root.appendChild(sigCard);

  let curModeIdx = 0;
  let curStepIdx = 0;
  let pulseStage = 0;
  const modeBtnBox = sigCard.querySelector("#mk-mode-btns");
  const chainBox = sigCard.querySelector("#mk-chain");
  const detailBox = sigCard.querySelector("#mk-chain-detail");
  const dspCanvas = sigCard.querySelector("#mk-dsp-canvas");
  const meterRow = sigCard.querySelector("#mk-dsp-meters");

  function renderSignalStatic() {
    const curMode = SIGNAL_MODES[curModeIdx];
    modeBtnBox.innerHTML = "";
    SIGNAL_MODES.forEach((m, idx) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = `btn btn-sm ${idx === curModeIdx ? "active" : ""}`;
      b.textContent = m.name;
      b.addEventListener("click", () => {
        curModeIdx = idx;
        curStepIdx = 0;
        renderSignalStatic();
      });
      modeBtnBox.appendChild(b);
    });

    chainBox.innerHTML = "";
    curMode.chain.forEach((step, idx) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = `chain-node ${idx === curStepIdx ? "active" : ""} ${idx === pulseStage ? "pulse-stage" : ""}`;
      btn.innerHTML = `<strong style="display:block;font-size:11px;">${step.label}</strong><span style="font-size:10px;color:var(--text-muted)">${step.spec}</span>`;
      btn.addEventListener("click", () => {
        curStepIdx = idx;
        renderSignalStatic();
      });
      chainBox.appendChild(btn);
      if (idx < curMode.chain.length - 1) {
        const arr = document.createElement("span");
        arr.className = `chain-arrow ${idx === pulseStage ? "lit" : ""}`;
        arr.textContent = "->";
        chainBox.appendChild(arr);
      }
    });

    const s = curMode.chain[curStepIdx];
    detailBox.innerHTML = `
      <div style="display:flex;justify-content:space-between;gap:8px;">
        <strong>${curMode.name} (${curMode.band}) &middot; Stage ${curStepIdx + 1}/${curMode.chain.length}: ${s.label}</strong>
        <span class="mono" style="color:var(--cyan)">${s.spec}</span>
      </div>
      <div style="color:var(--text-muted)">${s.detail}</div>
    `;
  }
  renderSignalStatic();

  // 2. LVDS 512-tap IDELAYE3 Eye Scan & SGMII Failover FSM (Rust state machine)
  const eyeCard = document.createElement("article");
  eyeCard.className = "mockup-card";
  eyeCard.innerHTML = `
    <div class="mockup-title">
      <h3>2. LVDS IDELAYE3 Eye Scan &amp; SGMII Failover FSM</h3>
      <span class="tag-mockup">[Mock-up] WASM</span>
    </div>
    <canvas id="mk-eye-canvas" class="sim-canvas" width="560" height="155"></canvas>
    <div class="control-row">
      <label for="mk-skew">Channel Skew Inject</label>
      <strong id="mk-skew-val" class="mono">42 ps</strong>
    </div>
    <input id="mk-skew" type="range" min="0" max="320" value="42">
    <div style="display:flex;gap:6px;flex-wrap:wrap;">
      <button type="button" class="btn btn-sm active" data-fsm="0">POL_SPLIT (IAS1+SGMII)</button>
      <button type="button" class="btn btn-sm" data-fsm="1">Cut ETH RX</button>
      <button type="button" class="btn btn-sm" data-fsm="2">Inject CRC Glitch</button>
      <button type="button" class="btn btn-sm" data-fsm="3">Si549 400M</button>
    </div>
    <div id="mk-fsm-log" class="hex-box"></div>
  `;
  root.appendChild(eyeCard);

  const eyeCanvas = eyeCard.querySelector("#mk-eye-canvas");
  const skewRange = eyeCard.querySelector("#mk-skew");
  const skewVal = eyeCard.querySelector("#mk-skew-val");
  const fsmLog = eyeCard.querySelector("#mk-fsm-log");
  let fsmMode = 0;

  eyeCard.querySelectorAll("[data-fsm]").forEach((btn) => {
    btn.addEventListener("click", () => {
      eyeCard.querySelectorAll("[data-fsm]").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      fsmMode = Number(btn.dataset.fsm);
    });
  });

  // 3. R5F Shared Mailbox (0x3EE0_0000) & TX_KEY (0x8000_0038)
  const txCard = document.createElement("article");
  txCard.className = "mockup-card";
  txCard.innerHTML = `
    <div class="mockup-title">
      <h3>3. R5F Mailbox (0x3EE0_0000) &amp; TX_KEY (0x8000_0038)</h3>
      <span class="tag-mockup">[Mock-up] WASM</span>
    </div>
    <div class="control-row">
      <label for="mk-spd-can">CAN1 Vehicle Speed</label>
      <strong id="mk-spd-can-val" class="mono">0 km/h</strong>
    </div>
    <input id="mk-spd-can" type="range" min="0" max="120" value="0">
    <div class="control-row">
      <label for="mk-ptt-sec">PTT Hold Duration (max 180 s)</label>
      <strong id="mk-ptt-val" class="mono">12 s</strong>
    </div>
    <input id="mk-ptt-sec" type="range" min="0" max="195" value="12">
    <div style="display:flex;gap:14px;flex-wrap:wrap;">
      <label class="check-row"><input id="mk-lic" type="checkbox" checked><span>TX Licence Valid</span></label>
      <label class="check-row"><input id="mk-ptt-on" type="checkbox" checked><span>PTT Requested</span></label>
      <label class="check-row"><input id="mk-gps-ok" type="checkbox" checked><span>GPS PPS Lock</span></label>
    </div>
    <div class="progress-track"><div id="mk-mbox-fill" class="progress-fill"></div></div>
    <div id="mk-tx-dump" class="hex-box"></div>
  `;
  root.appendChild(txCard);

  const spdInput = txCard.querySelector("#mk-spd-can");
  const pttInput = txCard.querySelector("#mk-ptt-sec");
  const licChk = txCard.querySelector("#mk-lic");
  const pttChk = txCard.querySelector("#mk-ptt-on");
  const gpsChk = txCard.querySelector("#mk-gps-ok");
  const mboxFill = txCard.querySelector("#mk-mbox-fill");
  const txDump = txCard.querySelector("#mk-tx-dump");

  // 4. Vehicle CAN 2.0 & Mirror-Safe FFC (J9 <-> J1502) + CANH/CANL Waveform
  const canCard = document.createElement("article");
  canCard.className = "mockup-card";
  canCard.innerHTML = `
    <div class="mockup-title">
      <h3>4. Vehicle CAN 2.0 &amp; Mirror-Safe FFC (J9 &lt;-&gt; J1502)</h3>
      <span class="tag-mockup">[Mock-up] WASM</span>
    </div>
    <canvas id="mk-can-canvas" class="sim-canvas" width="560" height="120" style="height:120px;"></canvas>
    <div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;">
      <button type="button" class="btn btn-sm active" id="mk-ffc-a">Type A FFC (Straight)</button>
      <button type="button" class="btn btn-sm" id="mk-ffc-d">Type D FFC (Reversed)</button>
      <label class="check-row" style="margin-left:8px;"><input id="mk-can-tx" type="checkbox" checked><span>can1_txn Dominant</span></label>
    </div>
    <div id="mk-ffc-map" class="hex-box"></div>
    <div style="display:flex;gap:5px;flex-wrap:wrap;" id="mk-can-frames"></div>
    <div id="mk-can-decoded" class="panel-card" style="font-size:12px;"></div>
  `;
  root.appendChild(canCard);

  const canCanvas = canCard.querySelector("#mk-can-canvas");
  let ffcTypeD = false;
  let selectedCanIdx = 0;
  const ffcMapBox = canCard.querySelector("#mk-ffc-map");
  const canFramesBox = canCard.querySelector("#mk-can-frames");
  const canDecBox = canCard.querySelector("#mk-can-decoded");
  const canTxChk = canCard.querySelector("#mk-can-tx");

  function renderCanButtons() {
    canCard.querySelector("#mk-ffc-a").classList.toggle("active", !ffcTypeD);
    canCard.querySelector("#mk-ffc-d").classList.toggle("active", ffcTypeD);
    canFramesBox.innerHTML = "";
    V80_CAN_SAMPLES.forEach((f, idx) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = `btn btn-sm ${idx === selectedCanIdx ? "active" : ""}`;
      b.textContent = `${f.id} ${f.name}`;
      b.addEventListener("click", () => {
        selectedCanIdx = idx;
        renderCanButtons();
      });
      canFramesBox.appendChild(b);
    });
    const f = V80_CAN_SAMPLES[selectedCanIdx];
    canDecBox.innerHTML = `
      <div><strong>Montero V80 Frame ${f.id} (${f.name})</strong> &middot; DLC=${f.dlc}</div>
      <div class="mono" style="color:var(--cyan)">Payload: [ ${f.bytes} ]</div>
      <div>${f.decoded}</div>
    `;
  }
  canCard.querySelector("#mk-ffc-a").addEventListener("click", () => { ffcTypeD = false; renderCanButtons(); });
  canCard.querySelector("#mk-ffc-d").addEventListener("click", () => { ffcTypeD = true; renderCanButtons(); });
  renderCanButtons();

  // Animation loop backed by Rust SiteCore (~24 Hz)
  let stepCount = 0;
  let lastTickMs = 0;

  function stepAll(force = false) {
    const core = getCore ? getCore() : null;
    if (!core) return;
    const now = performance.now();
    if (!force && now - lastTickMs < 42) return;
    lastTickMs = now;
    stepCount++;
    const timeS = now * 0.001;

    // Update pulsing stage badge in Signal Chain every ~10 frames
    const nextStage = Math.floor(stepCount / 8) % SIGNAL_MODES[curModeIdx].chain.length;
    if (nextStage !== pulseStage) {
      pulseStage = nextStage;
      chainBox.querySelectorAll(".chain-node").forEach((n, i) => n.classList.toggle("pulse-stage", i === pulseStage));
      chainBox.querySelectorAll(".chain-arrow").forEach((a, i) => a.classList.toggle("lit", i === pulseStage));
    }

    // 1. Rust DSP Time Waveform + FFT Spectrum
    const dsp = core.sim_dsp_tick(curModeIdx, timeS, 42.0);
    {
      const ctx = dspCanvas.getContext("2d");
      const w = dspCanvas.width, h = dspCanvas.height;
      ctx.fillStyle = "#0a0e14";
      ctx.fillRect(0, 0, w, h);

      // Divider: left = Time I/Q, right = 64-bin FFT dBFS
      const mid = Math.floor(w * 0.46);
      ctx.strokeStyle = "#1f2a38";
      ctx.beginPath();
      ctx.moveTo(mid, 6);
      ctx.lineTo(mid, h - 6);
      ctx.stroke();

      // Time-domain trace (0..63)
      ctx.strokeStyle = "#4cc2ff";
      ctx.lineWidth = 1.6;
      ctx.beginPath();
      for (let i = 0; i < 64; i++) {
        const x = 8 + (i / 63) * (mid - 16);
        const y = h * 0.52 - dsp[i] * (h * 0.34);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();

      // FFT spectrum (64..127)
      ctx.strokeStyle = "#ffb020";
      ctx.lineWidth = 1.8;
      ctx.beginPath();
      for (let k = 0; k < 64; k++) {
        const x = mid + 10 + (k / 63) * (w - mid - 18);
        const db = dsp[64 + k];
        const norm = (db + 80) / 80;
        const y = h - 18 - norm * (h - 32);
        if (k === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();

      ctx.fillStyle = "#93a1b3";
      ctx.font = "10px monospace";
      ctx.fillText("Baseband Time (I)", 10, 14);
      ctx.fillText("64-pt Rust DFT Spectrum (dBFS)", mid + 12, 14);

      const curChain = SIGNAL_MODES[curModeIdx].chain;
      meterRow.innerHTML = "";
      for (let j = 0; j < 5; j++) {
        const c = document.createElement("div");
        c.className = "meter-cell";
        c.innerHTML = `<div style="color:var(--text-muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${curChain[j].label.split(" ")[0]}</div><strong class="mono" style="color:var(--green)">${dsp[128 + j].toFixed(1)} dBm</strong>`;
        meterRow.appendChild(c);
      }
    }

    // 2. Rust LVDS Eye + FSM
    const skewPs = Number(skewRange.value);
    skewVal.textContent = `${skewPs} ps`;
    const lvds = core.sim_lvds_tick(skewPs, fsmMode, stepCount);
    {
      const st = lvds[0];
      const tap = lvds[1];
      const eyePs = lvds[2];
      const dwellPct = lvds[3];
      const dlUp = lvds[4];
      const ulUp = lvds[5];
      const ethOk = lvds[6];
      const crc = lvds[7];

      const ctx = eyeCanvas.getContext("2d");
      const w = eyeCanvas.width, h = eyeCanvas.height;
      ctx.fillStyle = "#0a0e14";
      ctx.fillRect(0, 0, w, h);

      ctx.strokeStyle = "#1c2633";
      ctx.lineWidth = 1;
      for (let g = 1; g < 8; g++) {
        ctx.beginPath();
        ctx.moveTo((g * w) / 8, 10);
        ctx.lineTo((g * w) / 8, h - 22);
        ctx.stroke();
      }

      // Draw multi-trace eye from Rust contour
      for (let tr = 0; tr < 12; tr++) {
        ctx.strokeStyle = tr % 2 ? "rgba(76, 194, 255, 0.48)" : "rgba(255, 176, 32, 0.48)";
        ctx.lineWidth = 1.4;
        ctx.beginPath();
        for (let i = 0; i < 64; i++) {
          const x = (i / 63) * w;
          const v = lvds[8 + i];
          const sgn = tr % 2 ? 1 : -1;
          const y = h * 0.47 + sgn * v * (h * 0.30) + ((tr - 6) * 1.1);
          if (i === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.stroke();
      }

      const cx = (tap / 511) * w;
      ctx.strokeStyle = st === 2 ? "#f85149" : "#3fb950";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(cx, 10);
      ctx.lineTo(cx, h - 22);
      ctx.stroke();

      ctx.fillStyle = "#e6edf3";
      ctx.font = "11px monospace";
      ctx.fillText(`Tap=${Math.round(tap)}/511 | Eye=${Math.round(eyePs)} ps | Dwell=${Math.round(dwellPct)}% | CRC=${crc}`, 10, h - 7);

      const fsmNames = [
        "ST_LOCKED (POL_SPLIT): dual IAS1 + SGMII 1000BASE-T active, zero dropped frames.",
        "ST_FAILOVER -> POL_MIRROR_1P1: ETH silent -> dual_path_mux mirrors all traffic onto IAS1.",
        st === 2 ? `ST_RETRAIN (${Math.round(dwellPct)}%): sweeping IDELAYE3 512 taps...` : "ST_LOCKED (Recovered from CRC glitch, post_crc=0).",
        "CLOCK_SWITCH 500 -> 400 MHz: Si549 re-locked, AD9253=50 MSPS, REG=0x00460436.",
      ];
      fsmLog.textContent =
`FSM State: ${fsmNames[fsmMode]}
IAS1 Downlink=${dlUp} Uplink=${ulUp} | SGMII eth_healthy=${ethOk} | Tap=${Math.round(tap)}/511`;
    }

    // 3. Rust R5F Mailbox & TX_KEY Interlock
    const spd = Number(spdInput.value);
    const ptt = Number(pttInput.value);
    txCard.querySelector("#mk-spd-can-val").textContent = `${spd} km/h`;
    txCard.querySelector("#mk-ptt-val").textContent = `${ptt} s`;
    const mb = core.sim_mailbox_tick(spd, ptt, licChk.checked, pttChk.checked, gpsChk.checked, stepCount);
    const reasonText = [
      "UNLOCKED (RF TX Permitted)",
      "LOCKED: Vehicle in motion (speed > 0 km/h)",
      "LOCKED: No valid TX licence loaded",
      "LOCKED: Receive standby (PTT idle)",
      "LOCKED: PTT TOT > 180 s expired",
    ][mb[6]] || "LOCKED";
    mboxFill.style.width = `${12 + ((mb[1] % 16) / 15) * 88}%`;
    txDump.textContent =
`R5F OCM Mailbox @ 0x3EE0_0000 (magic=0x${mb[0].toString(16).toUpperCase()}, seq=${mb[1]})
  CAN1 speed = ${mb[2]} km/h | GPS PPS err = ${mb[3]} ns
PL CSR @ 0x8000_0038 TX_KEY   = 0x${mb[4].toString(16).padStart(8, "0").toUpperCase()}
PL CSR @ 0x8000_0004 DSP_CTRL = 0x${mb[5].toString(16).padStart(8, "0").toUpperCase()} (RO[1]=${(mb[5] >> 1) & 1})
Verdict -> ${reasonText}`;

    // 4. Rust Mirror-Safe J9 FFC + Differential CANH/CANL Bus
    const can = core.sim_can_tick(ffcTypeD, canTxChk.checked, selectedCanIdx, stepCount);
    {
      const ppsPin = Math.round(can[0]);
      const txPin = Math.round(can[1]);
      const dom = can[2] > 0.5;
      const rev = ffcTypeD;
      ffcMapBox.textContent =
`FFC: Type ${rev ? "D (Reversed n->16-n)" : "A (Straight n->n)"} | J1502<->J9 | NOR TXD=${dom ? "DOMINANT" : "RECESSIVE"}
  PPS: J1502 pin 4 & 12 -> J9 pin ${ppsPin} ACTIVE (HDA10 PL)
  CAN: J1502 pin 6 & 10 -> J9 pin ${txPin} NOR (Q1530/Q1531) | RX on J9 pin 8 -> U1506`;

      const ctx = canCanvas.getContext("2d");
      const w = canCanvas.width, h = canCanvas.height;
      ctx.fillStyle = "#0a0e14";
      ctx.fillRect(0, 0, w, h);

      // 2.5V center reference
      ctx.strokeStyle = "#1f2a38";
      ctx.beginPath();
      ctx.moveTo(0, h * 0.5);
      ctx.lineTo(w, h * 0.5);
      ctx.stroke();

      // CANH (orange/green top rail: 2.5V -> 3.5V)
      ctx.strokeStyle = "#ffb020";
      ctx.lineWidth = 1.8;
      ctx.beginPath();
      for (let i = 0; i < 96; i++) {
        const x = (i / 95) * w;
        const y = h * 0.5 - can[4 + i] * (h * 0.34);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();

      // CANL (cyan bottom rail: 2.5V -> 1.5V)
      ctx.strokeStyle = "#4cc2ff";
      ctx.beginPath();
      for (let i = 0; i < 96; i++) {
        const x = (i / 95) * w;
        const y = h * 0.5 + can[4 + i] * (h * 0.34);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();

      ctx.fillStyle = "#93a1b3";
      ctx.font = "10px monospace";
      ctx.fillText("U1506 TCAN330 CANH (3.5V) / CANL (1.5V)", 8, 13);
    }
  }

  function loop() {
    requestAnimationFrame(loop);
    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
    if (isActiveTab() && (!reduced || stepCount === 0)) {
      stepAll(false);
    }
  }
  requestAnimationFrame(loop);

  return {
    forceTick: () => stepAll(true),
  };
}
