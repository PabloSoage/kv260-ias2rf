/**
 * Interactive [Mock-up] browser widgets for key KV260-IAS2RF hardware & firmware mechanisms.
 * Pure client-side models tagged clearly with [Mock-up] badges.
 */

const SIGNAL_MODES = [
  {
    id: "wbfm",
    name: "WBFM 98.1 MHz",
    band: "87.5 - 108 MHz",
    chain: [
      { label: "J601 V/UHF SMA", spec: "50 ohm coaxial input -> ESD + BPF", detail: "Wideband VHF antenna feed routed to SPDT RF switch matrix (U601/U602) on RX_VU." },
      { label: "SKY13384 / LNA", spec: "Bandpass 70-200 MHz", detail: "Selects VHF-band analog conditioning and sets flat passband gain ahead of AD9253 Ch A." },
      { label: "AD9253 (U701)", spec: "14-bit @ 62.5 MSPS (500 MHz XO)", detail: "Dual-channel SDR ADC samples Nyquist zones via Transformer T701; 1-lane DDR LVDS to XC7A50T." },
      { label: "Artix DDC + FIFO", spec: "CIC / FIR -> 1.0 MSPS IQ", detail: "XC7A50T (U1101) digitally down-converts and packs 16-bit I/Q frames over IAS1 64b/66b." },
      { label: "K26 PL + R5F/A53", spec: "FM Quad + 19 kHz Pilot + RDS", detail: "Polar discriminator, stereo 38 kHz DSB-SC decode, de-emphasis 50 us, and RBDS/RDS parser." },
    ],
  },
  {
    id: "airband",
    name: "Airband AM 121.5",
    band: "108 - 137 MHz",
    chain: [
      { label: "J601 V/UHF SMA", spec: "VHF Airband AM rx", detail: "Aviation distress / ATC channel received on VHF antenna path." },
      { label: "VHF Preselector", spec: "Sub-octave helical / LC", detail: "Rejects strong 88-108 MHz FM broadcast carriers before ADC quantization." },
      { label: "AD9253 (U701)", spec: "14-bit @ 62.5 MSPS", detail: "Undersampling captures 121.5 MHz in 4th Nyquist zone with low clock jitter from Si549." },
      { label: "Artix DDC", spec: "25 kHz / 8.33 kHz channel", detail: "Tight half-band + equiripple FIR channelizer selects narrow AM channel." },
      { label: "K26 AM Envelope", spec: "Synchronous / Env + AGC + Squelch", detail: "DC blocker + envelope detector + hang AGC feeds cockpit audio & waterfall display." },
    ],
  },
  {
    id: "hf_am",
    name: "HF AM 7.10 MHz",
    band: "0.5 - 30 MHz",
    chain: [
      { label: "J602 HF SMA", spec: "Direct-sampling HF port", detail: "Routed through 30 MHz 7-pole low-pass roofing filter to block VHF aliases." },
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
      { label: "J602 HF SMA", spec: "50 ohm HF front end", detail: "HF port with gas discharge & ESD clamp feeding transformer-coupled LPF." },
      { label: "T701 / LPF", spec: "DC-30 MHz differential", detail: "1:1 RF transformer balances single-ended antenna into AD9253 Ch B inputs." },
      { label: "AD9253 (U701)", spec: "50 or 62.5 MSPS", detail: "14-bit dynamic range supports weak FT8 / SSB signals next to strong broadcasters." },
      { label: "Artix + IAS1", spec: "3 kHz SSB slice", detail: "Decimated complex I/Q stream with 64b/66b framing & SGMII split-failover path." },
      { label: "K26 Phasing USB/LSB", spec: "Weaver / Hilbert 2.4 kHz", detail: "Opposite-sideband rejection > 55 dB; feeds Slint passband tuning & spectrum." },
    ],
  },
  {
    id: "nbfm",
    name: "VHF/UHF NBFM",
    band: "144 / 433 MHz",
    chain: [
      { label: "J601 V/UHF SMA", spec: "2 m / 70 cm band", detail: "Switched VHF/UHF path selected over ROUTING coaxial switch matrix." },
      { label: "BPF + LNA", spec: "Saw/ceramic bank", detail: "Selects 144-148 MHz or 430-440 MHz BPF window." },
      { label: "AD9253 (U701)", spec: "Harmonic / IF sampling", detail: "Digitizes VHF/UHF signals via Si549 low-phase-noise sample clock." },
      { label: "Artix DDC", spec: "12.5 kHz / 25 kHz FM", detail: "Packs narrowband I/Q stream and sends RSSI / squelch frames." },
      { label: "K26 NBFM + CTCSS", spec: "2.5/5 kHz dev + PL tones", detail: "Limiting discriminator + Goertzel 67-254 Hz CTCSS tone decoder." },
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
      { label: "AD9708 (U901)", spec: "8-bit 100 MSPS Chirp DAC", detail: "Generates linear FM up-chirp on DAC_RADAR -> upconverted to X-band LO." },
      { label: "8x ADAR1000 Array", spec: "SPI csb[7:0], TR_BEAM", detail: "R5F Core 1 + Artix sweep azimuth beams via SPI phase/gain weights & beam strobes." },
      { label: "AD9484 (U501)", spec: "8-bit @ 400 MSPS", detail: "Samples 120 MHz echo IF via LVDS DDR pairs with 512-tap IDELAY calibration." },
      { label: "Artix + K26 BEV", spec: "Range-Doppler + CA-CFAR", detail: "2-D FFT + CFAR targets fused with LiDAR in `kria_bev_grid` PL accelerator." },
      { label: "HMI Polar PPI", spec: "Range vs Azimuth map", detail: "Live targets rendered on Radar PPI and fused BEV occupancy map." },
    ],
  },
  {
    id: "tx",
    name: "TX SSB / NBFM",
    band: "TX_KEY Interlock Gated",
    chain: [
      { label: "R5F + TX_KEY CSR", spec: "0x8000_0038 Interlock", detail: "Hardware safety gate requires speed == 0 km/h (Parked), licence OK, and PTT <= 180 s." },
      { label: "K26 A53/PL Mod", spec: "SSB / NBFM Baseband", detail: "Generates complex envelope; `DSP_CTRL[1]` mirrors hardware `dsp_tx_en` RO state." },
      { label: "AD9767 (U1001)", spec: "Dual 14-bit @ 100 MSPS", detail: "Quadrature DAC (IQWRT / IQCLK / IQSEL) converts complex I/Q back to analog." },
      { label: "TX Filter / PA", spec: "Harmonic LPF > 48 dBc", detail: "Attenuates images & spurious emissions prior to TX T/R relay / switch." },
      { label: "J601 / J602 SMA", spec: "Ant out (gated by HW)", detail: "RF output only enabled when R5F holds TX_KEY valid; hardware kills TX on motion." },
    ],
  },
];

const V80_CAN_SAMPLES = [
  { id: "0x215", name: "ABS / Wheel Speed", dlc: 8, bytes: "00 00 1A 90 1A 88 00 40", speedKmh: 68.0, decoded: "FL=68.0 km/h, FR=67.9 km/h -> TX_KEY LOCKED" },
  { id: "0x218", name: "Engine RPM & ECT", dlc: 8, bytes: "00 00 0B B8 5C 00 00 12", speedKmh: 0.0, decoded: "RPM=3000/4=750 idle, Coolant=92 C, Gear=P" },
  { id: "0x236", name: "Steering Wheel Angle", dlc: 6, bytes: "01 F4 00 10 00 00", speedKmh: 0.0, decoded: "Angle=+0.0 deg (centered), Rate=0 deg/s" },
  { id: "0x412", name: "Cluster & Odometer", dlc: 8, bytes: "00 03 8A 20 00 00 02 01", speedKmh: 0.0, decoded: "Odo=231,968 km, Parked=true, Ign=ON" },
];

export function initMockups(root) {
  root.innerHTML = "";

  // 1. Signal Path Explorer
  const sigCard = document.createElement("article");
  sigCard.className = "mockup-card";
  sigCard.innerHTML = `
    <div class="mockup-title">
      <h3>1. Signal Path Explorer (8 Modes)</h3>
      <span class="tag-mockup">[Mock-up]</span>
    </div>
    <div style="display:flex;gap:6px;flex-wrap:wrap;" id="mk-mode-btns"></div>
    <div id="mk-chain" class="chain-strip"></div>
    <div id="mk-chain-detail" class="panel-card" style="font-size:12px;"></div>
  `;
  root.appendChild(sigCard);

  let curMode = SIGNAL_MODES[0];
  let curStepIdx = 0;
  const modeBtnBox = sigCard.querySelector("#mk-mode-btns");
  const chainBox = sigCard.querySelector("#mk-chain");
  const detailBox = sigCard.querySelector("#mk-chain-detail");

  function renderSignalMode() {
    modeBtnBox.innerHTML = "";
    SIGNAL_MODES.forEach((m) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = `btn btn-sm ${m.id === curMode.id ? "active" : ""}`;
      b.textContent = m.name;
      b.addEventListener("click", () => {
        curMode = m;
        curStepIdx = 0;
        renderSignalMode();
      });
      modeBtnBox.appendChild(b);
    });

    chainBox.innerHTML = "";
    curMode.chain.forEach((step, idx) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = `chain-node ${idx === curStepIdx ? "active" : ""}`;
      btn.innerHTML = `<strong style="display:block;font-size:11px;">${step.label}</strong><span style="font-size:10px;color:var(--text-muted)">${step.spec}</span>`;
      btn.addEventListener("click", () => {
        curStepIdx = idx;
        renderSignalMode();
      });
      chainBox.appendChild(btn);
      if (idx < curMode.chain.length - 1) {
        const arr = document.createElement("span");
        arr.className = "chain-arrow";
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
  renderSignalMode();

  // 2. LVDS 512-tap IDELAYE3 Eye Scan & SGMII Failover State Machine
  const eyeCard = document.createElement("article");
  eyeCard.className = "mockup-card";
  eyeCard.innerHTML = `
    <div class="mockup-title">
      <h3>2. LVDS IDELAYE3 Eye Scan &amp; SGMII Failover FSM</h3>
      <span class="tag-mockup">[Mock-up]</span>
    </div>
    <canvas id="mk-eye-canvas" class="eye-canvas" width="560" height="170"></canvas>
    <div class="control-row">
      <label for="mk-skew">Channel Skew Inject</label>
      <strong id="mk-skew-val" class="mono">42 ps</strong>
    </div>
    <input id="mk-skew" type="range" min="0" max="320" value="42">
    <div style="display:flex;gap:6px;flex-wrap:wrap;">
      <button type="button" class="btn btn-sm active" data-fsm="split">POL_SPLIT (IAS1+SGMII)</button>
      <button type="button" class="btn btn-sm" data-fsm="cut_eth">Cut ETH RX</button>
      <button type="button" class="btn btn-sm" data-fsm="glitch">Inject CRC Glitch</button>
      <button type="button" class="btn btn-sm" data-fsm="clk400">Si549 400M</button>
    </div>
    <div id="mk-fsm-log" class="hex-box"></div>
  `;
  root.appendChild(eyeCard);

  const eyeCanvas = eyeCard.querySelector("#mk-eye-canvas");
  const skewRange = eyeCard.querySelector("#mk-skew");
  const skewVal = eyeCard.querySelector("#mk-skew-val");
  const fsmLog = eyeCard.querySelector("#mk-fsm-log");
  let fsmState = "split";

  function renderEyeAndFsm() {
    const skewPs = Number(skewRange.value);
    skewVal.textContent = `${skewPs} ps`;
    const ctx = eyeCanvas.getContext("2d");
    const w = eyeCanvas.width, h = eyeCanvas.height;
    ctx.fillStyle = "#0a0e14";
    ctx.fillRect(0, 0, w, h);

    // Draw 512-tap IDELAYE3 opening window across 1000 ps UI
    const center = 256 + (skewPs * 0.35);
    const halfOpen = Math.max(25, 165 - skewPs * 0.48);
    ctx.strokeStyle = "#1f2a38";
    ctx.lineWidth = 1;
    for (let g = 1; g < 8; g++) {
      ctx.beginPath();
      ctx.moveTo((g * w) / 8, 12);
      ctx.lineTo((g * w) / 8, h - 22);
      ctx.stroke();
    }

    // Eye mask region
    const optStart = Math.max(0, center - halfOpen);
    const optEnd = Math.min(511, center + halfOpen);
    ctx.fillStyle = "rgba(63, 185, 80, 0.14)";
    ctx.fillRect((optStart / 511) * w, 16, ((optEnd - optStart) / 511) * w, h - 42);

    // Draw synthetic eye traces
    ctx.lineWidth = 1.4;
    for (let tr = 0; tr < 18; tr++) {
      ctx.strokeStyle = tr % 2 ? "rgba(76, 194, 255, 0.45)" : "rgba(255, 176, 32, 0.45)";
      ctx.beginPath();
      for (let x = 0; x <= w; x += 6) {
        const tap = (x / w) * 511;
        const dist = Math.abs(tap - center);
        const jitter = ((tr * 37) % 13) - 6;
        const transition = Math.min(1, Math.max(-1, (dist - halfOpen * 0.85) / 28));
        const lvl = tr % 2 ? -transition : transition;
        const y = h * 0.48 - lvl * (h * 0.30) + jitter * 0.8;
        if (x === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();
    }

    // Center locked tap marker
    const cx = (center / 511) * w;
    ctx.strokeStyle = "#3fb950";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(cx, 12);
    ctx.lineTo(cx, h - 24);
    ctx.stroke();

    ctx.fillStyle = "#e6edf3";
    ctx.font = "11px monospace";
    const eyeWidthPs = Math.round(((optEnd - optStart) / 511) * 1000);
    ctx.fillText(`Tap=${Math.round(center)}/511 | Eye Open=${eyeWidthPs} ps | Dwell=1800 cyc`, 10, h - 8);

    const lines = {
      split: `FSM: ST_LOCKED (POL_SPLIT)\nIAS1: UP (dl_up=1, ul_up=1, tap=${Math.round(center)}) | ETH SGMII: UP (802.3az off, ui_tick<=3)\nLost packets s1=0, s2=0 | Active Policy: Split Telemetry & IQ`,
      cut_eth: `FSM: ST_FAILOVER -> POL_MIRROR_1P1\nETH peer silent > ETH_ALIVE_TIMEOUT -> eth_healthy=0\ndual_path_mux drains aborted FIFO without headless fragments; IAS1 carries all streams cleanly.`,
      glitch: `FSM: ST_RETRAIN -> ST_LOCKED\nCRC error detected -> u_dl_train_fsm sweeps 512 taps (dwell=1800), relocks tap=${Math.round(center)}; post_crc=0`,
      clk400: `Si549 Clock Switch: 500 MHz -> 400 MHz\nddc_en=1 cap_rst=0 | AD9253=50.0 MSPS, AD9484=400 MSPS -> REG_LINK_STATUS=0x00460436`,
    };
    fsmLog.textContent = lines[fsmState];
  }

  skewRange.addEventListener("input", renderEyeAndFsm);
  eyeCard.querySelectorAll("[data-fsm]").forEach((btn) => {
    btn.addEventListener("click", () => {
      eyeCard.querySelectorAll("[data-fsm]").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      fsmState = btn.dataset.fsm;
      renderEyeAndFsm();
    });
  });
  renderEyeAndFsm();

  // 3. R5F Shared Mailbox (0x3EE0_0000) & TX_KEY (0x8000_0038) Interlock
  const txCard = document.createElement("article");
  txCard.className = "mockup-card";
  txCard.innerHTML = `
    <div class="mockup-title">
      <h3>3. R5F Mailbox (0x3EE0_0000) &amp; TX_KEY (0x8000_0038)</h3>
      <span class="tag-mockup">[Mock-up]</span>
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
    <div id="mk-tx-dump" class="hex-box"></div>
  `;
  root.appendChild(txCard);

  const spdInput = txCard.querySelector("#mk-spd-can");
  const pttInput = txCard.querySelector("#mk-ptt-sec");
  const licChk = txCard.querySelector("#mk-lic");
  const pttChk = txCard.querySelector("#mk-ptt-on");
  const gpsChk = txCard.querySelector("#mk-gps-ok");
  const txDump = txCard.querySelector("#mk-tx-dump");
  let mboxSeq = 1042;

  function renderTxInterlock() {
    mboxSeq++;
    const spd = Number(spdInput.value);
    const pttSec = Number(pttInput.value);
    txCard.querySelector("#mk-spd-can-val").textContent = `${spd} km/h`;
    txCard.querySelector("#mk-ptt-val").textContent = `${pttSec} s`;

    const parked = spd === 0;
    const lic = licChk.checked;
    const ptt = pttChk.checked;
    const timeoutOk = pttSec <= 180;
    const unlocked = parked && lic && ptt && timeoutOk;

    let reason = "UNLOCKED (RF TX Permitted)";
    if (!parked) reason = "LOCKED: Vehicle in motion (speed > 0 km/h)";
    else if (!lic) reason = "LOCKED: No valid TX licence loaded";
    else if (!ptt) reason = "LOCKED: Receive standby (PTT idle)";
    else if (!timeoutOk) reason = "LOCKED: PTT TOT > 180 s expired";

    const txKeyHex = unlocked ? "0x4B455901" : "0x00000000";
    const dspCtrlHex = unlocked ? "0x00000003 (RO[1]=1)" : "0x00000001 (RO[1]=0)";
    const ppsWord = gpsChk.checked ? "LOCKED_GPS (±41ns)" : "HOLDOVER_XO";

    txDump.textContent =
`R5F Shared OCM Mailbox @ 0x3EE0_0000 (seq=${mboxSeq})
  magic      = 0x4B524941 ("KRIA")   source = CAN1_EMIO
  speed_kmh  = ${String(spd).padEnd(3)}   pps_state = ${ppsWord}
PL Register @ 0x8000_0038 TX_KEY   = ${txKeyHex}
PL Register @ 0x8000_0004 DSP_CTRL = ${dspCtrlHex}
Interlock Verdict -> ${reason}`;
  }

  [spdInput, pttInput, licChk, pttChk, gpsChk].forEach((el) => el.addEventListener("input", renderTxInterlock));
  renderTxInterlock();

  // 4. Vehicle CAN 2.0 & Mirror-Safe FFC (J9 <-> J1502) Simulator
  const canCard = document.createElement("article");
  canCard.className = "mockup-card";
  canCard.innerHTML = `
    <div class="mockup-title">
      <h3>4. Vehicle CAN 2.0 &amp; Mirror-Safe FFC (J9 &lt;-&gt; J1502)</h3>
      <span class="tag-mockup">[Mock-up]</span>
    </div>
    <div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;">
      <button type="button" class="btn btn-sm active" id="mk-ffc-a">Type A FFC (Straight n->n)</button>
      <button type="button" class="btn btn-sm" id="mk-ffc-d">Type D FFC (Reversed n->16-n)</button>
      <label class="check-row" style="margin-left:8px;"><input id="mk-can-tx" type="checkbox" checked><span>can1_txn Dominant (1)</span></label>
    </div>
    <div id="mk-ffc-map" class="hex-box"></div>
    <div style="display:flex;gap:5px;flex-wrap:wrap;" id="mk-can-frames"></div>
    <div id="mk-can-decoded" class="panel-card" style="font-size:12px;"></div>
  `;
  root.appendChild(canCard);

  let ffcType = "A";
  let selectedCanIdx = 0;
  const ffcMapBox = canCard.querySelector("#mk-ffc-map");
  const canFramesBox = canCard.querySelector("#mk-can-frames");
  const canDecBox = canCard.querySelector("#mk-can-decoded");
  const canTxChk = canCard.querySelector("#mk-can-tx");

  function renderCanFfc() {
    canCard.querySelector("#mk-ffc-a").classList.toggle("active", ffcType === "A");
    canCard.querySelector("#mk-ffc-d").classList.toggle("active", ffcType === "D");
    const canTx = canTxChk.checked ? 1 : 0;
    const rev = ffcType === "D";
    const mapPin = (n) => (rev ? 16 - n : n);

    ffcMapBox.textContent =
`FFC Mode: Type ${ffcType} (${rev ? "Opposite-side contacts: adapter pin n -> J9 pin 16-n" : "Same-side contacts: adapter pin n -> J9 pin n"})
  J1502 pin 4  (PPS_220R)   -> J9 pin ${String(mapPin(4)).padEnd(2)} ${mapPin(4) === 4 ? "(GND sink, safe)" : "(HDA10 PL PPS INPUT ACTIVE)"}
  J1502 pin 12 (PPS_220R)   -> J9 pin ${String(mapPin(12)).padEnd(2)} ${mapPin(12) === 12 ? "(HDA10 PL PPS INPUT ACTIVE)" : "(GND sink, safe)"}
  J1502 pin 6  (MMBT3904_A) -> J9 pin ${String(mapPin(6)).padEnd(2)} (${rev ? "GND" : "PS can1_txn=" + canTx}) | Dual-NPN NOR
  J1502 pin 10 (MMBT3904_B) -> J9 pin ${String(mapPin(10)).padEnd(2)} (${rev ? "PS can1_txn=" + canTx : "GND"}) | CAN TX=${canTx ? "DOMINANT" : "RECESSIVE"}
  J9 pins 11,13,14,15 (Reset/I2C/3V3) -> NC / open on adapter (Zero back-drive risk)`;

    canFramesBox.innerHTML = "";
    V80_CAN_SAMPLES.forEach((f, idx) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = `btn btn-sm ${idx === selectedCanIdx ? "active" : ""}`;
      b.textContent = `${f.id} ${f.name}`;
      b.addEventListener("click", () => {
        selectedCanIdx = idx;
        renderCanFfc();
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

  canCard.querySelector("#mk-ffc-a").addEventListener("click", () => { ffcType = "A"; renderCanFfc(); });
  canCard.querySelector("#mk-ffc-d").addEventListener("click", () => { ffcType = "D"; renderCanFfc(); });
  canTxChk.addEventListener("input", renderCanFfc);
  renderCanFfc();
}
