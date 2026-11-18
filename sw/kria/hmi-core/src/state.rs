//! The HMI's state, its commands and the snapshot the screens draw (HMI.md §3, §6).
//!
//! `Hmi` takes the DMA blocks (`on_block`), the R5F's mailbox and the vehicle data from the I/O layer, and the
//! screens' commands (`command`), which come back as register writes for the I/O layer to make. The PL's DSP
//! suite runs one function at a time (its inputs are gated: channel receiver, ADS-B or radar, FPGA_GATEWARE §5.5),
//! and there is one front end, so `Function` says which one is on; the screens of the others show their last data.

use crate::adsb::{self, Aircraft};
use crate::audio::{self, RdsDecoder, RdsInfo};
use crate::frame::{self, tid};
use crate::modes::{self, Mode, Path, Plan, Write};
use crate::radar::{self, Detection, Map};
use crate::spectrum::Spectrum;
use serde::{Deserialize, Serialize};

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Function {
    Radio,
    Adsb,
    Radar,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct Preset {
    pub name: String,
    pub freq_hz: f64,
    pub mode: Mode,
}

pub fn presets() -> Vec<Preset> {
    let p = |n: &str, f: f64, m: Mode| Preset { name: n.into(), freq_hz: f, mode: m };
    vec![
        p("FM 98.1", 98.1e6, Mode::Wbfm),
        p("HF AM 7200", 7.2e6, Mode::Am),
        p("Air 121.5", 121.5e6, Mode::Am),
        p("Marine 16", 156.8e6, Mode::Nbfm),
        p("2 m rpt", 145.6e6, Mode::Nbfm),
        p("PMR446 1", 446.00625e6, Mode::Nbfm),
        p("20 m SSB", 14.2e6, Mode::Usb),
    ]
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(tag = "cmd", rename_all = "snake_case")]
pub enum Command {
    Function { function: Function },
    Tune { freq_hz: f64 },
    Step { hz: f64 },
    SetMode { mode: Mode },
    Preset { index: usize },
    Gain { db: f64 },
    Radar { alpha_q8: u16, floor: u16 },
    TxSet { freq_hz: f64, mode: String, level: f64 },
    TxRequest { on: bool },
    Licence { on: bool },
    Record { on: bool },
    Marker { freq_hz: f64 },
    /// The marker at a fraction of the spectrum's width (a touch on the trace).
    MarkerFrac { x: f64 },
    ListenAtMarker,
    RadarAlphaStep { step: i32 },
}

#[derive(Clone, Debug, Default, Serialize)]
pub struct RadioView {
    pub freq_hz: f64,
    pub mode: Option<Mode>,
    pub path: Option<Path>,
    pub lo_hz: Option<f64>,
    pub covered: bool,
    pub lna_forced: bool,
    pub audio_rate: f64,
    pub level_dbfs: f64,
    pub pilot: bool,
    pub ctcss: bool,
    pub rds: RdsInfo,
    pub gain_db: f64,
    pub presets: Vec<Preset>,
}

#[derive(Clone, Debug, Default, Serialize)]
pub struct SpectrumView {
    pub stream: u8,
    pub center_hz: f64,
    pub span_hz: f64,
    pub trace: Vec<f32>,
    pub row: Vec<f32>,
    pub marker_hz: f64,
    pub frames: usize,
    /// The whole waterfall, newest row first: filled only when a snapshot is dumped (`Hmi::with_history`).
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub history: Vec<Vec<f32>>,
}

#[derive(Clone, Debug, Default, Serialize)]
pub struct AdsbView {
    pub aircraft: Vec<Aircraft>,
    pub frames: u64,
    pub own: Option<(f64, f64)>,
}

#[derive(Clone, Debug, Default, Serialize)]
pub struct RadarView {
    pub cpi: u16,
    pub cpis: u64,
    pub detections: Vec<Detection>,
    pub dropped: u32,
    pub map: Option<Map>,
    pub map_cpi: u16,
    pub alpha_q8: u16,
    pub floor: u16,
    pub beam_az_deg: f64,
}

#[derive(Clone, Debug, Default, Serialize)]
pub struct VehicleView {
    pub speed_kmh: Option<f64>,
    pub rpm: Option<f64>,
    pub coolant_c: Option<f64>,
    pub fuel_pct: Option<f64>,
    pub source: String,
}

#[derive(Clone, Debug, Default, Serialize)]
pub struct TxView {
    pub freq_hz: f64,
    pub mode: String,
    pub level: f64,
    pub requested: bool,
    pub keyed: bool,
    pub reason: String,
    pub licensed: bool,
}

#[derive(Clone, Debug, Default, Serialize)]
pub struct SystemView {
    pub link_up: bool,
    pub packets: u64,
    pub crc_errors: u64,
    pub seq_gaps: u64,
    pub resync_words: u64,
    pub blocks: u64,
    pub stream_mbps: f64,
    pub temp_k26_c: Option<f64>,
    pub temp_artix_c: Option<f64>,
    pub r5f0: String,
    pub r5f1: String,
    pub recording: bool,
    /// The file the recorder is writing, and how much of it (set by the I/O layer).
    pub rec_file: String,
    pub rec_bytes: u64,
    pub platform: String,
}

#[derive(Clone, Debug, Default, Serialize)]
pub struct Snapshot {
    pub t: f64,
    pub function: Option<Function>,
    pub radio: RadioView,
    pub spectrum: SpectrumView,
    pub adsb: AdsbView,
    pub radar: RadarView,
    pub vehicle: VehicleView,
    pub tx: TxView,
    pub system: SystemView,
    /// `kria-sdrd`'s last outputs (INTEGRATIONS §9, §10), passed through as they are.
    pub bearing: Option<serde_json::Value>,
    pub wideband: Option<serde_json::Value>,
}

/// The board transmits on HF only: `kria_tx_mod` puts the carrier inside the 25 MS/s stream to the AD9767, out of
/// `J952` (0 to 30 MHz), so the carrier stays below the stream's Nyquist frequency. VHF and UHF transmit goes through
/// the HackRF Pro's gate (INTEGRATIONS.md §10).
pub const TX_MAX_HZ: f64 = 12.5e6;

/// `DSP_CTRL[12:10]`, `kria_tx_mod`'s mode: 0 CW, 1 AM, 2 NBFM, 3 USB, 4 LSB.
pub fn tx_mode_code(mode: &str) -> u32 {
    match mode {
        "am" => 1,
        "nbfm" => 2,
        "usb" => 3,
        "lsb" => 4,
        _ => 0,
    }
}

pub struct Hmi {
    pub snap: Snapshot,
    /// The last `DSP_CTRL` written, so a transmit change keeps the function's bits.
    dsp_ctrl: u32,
    rds: RdsDecoder,
    adsb: adsb::Table,
    spec: Spectrum,
    radar_cfg: kria_core::radar::Config,
    last_seq: Option<u16>,
    plan: Option<Plan>,
    words_t0: (f64, u64),
    /// Audio for the I/O layer to play: interleaved left, right.
    pub audio_out: Vec<i16>,
    /// While recording: the spectrum stream's I/Q for the I/O layer to write.
    pub rec_out: Vec<(i16, i16)>,
}

impl Default for Hmi {
    fn default() -> Self {
        let mut snap = Snapshot::default();
        snap.radio.presets = presets();
        snap.radar.alpha_q8 = 1536;
        snap.tx = TxView { mode: "am".into(), level: 0.5, reason: "idle".into(), freq_hz: 7.1e6, ..Default::default() };
        Self {
            snap,
            dsp_ctrl: 0,
            rds: RdsDecoder::default(),
            adsb: adsb::Table::default(),
            spec: Spectrum::new(2048, 512, 60),
            radar_cfg: kria_core::radar::Config::default(),
            last_seq: None,
            plan: None,
            words_t0: (0.0, 0),
            audio_out: Vec::new(),
            rec_out: Vec::new(),
        }
    }
}

impl Hmi {
    pub fn set_own_position(&mut self, lat: f64, lon: f64) {
        self.adsb.own = Some((lat, lon));
        self.snap.adsb.own = Some((lat, lon));
    }

    pub fn on_block(&mut self, block: &[u64], now_s: f64) {
        let mut iq = Vec::new();
        let want_iq = self.snap.spectrum.stream;
        let mut audio_n = 0usize;
        let mut audio_pow = 0f64;
        let (rds, adsb, radar_cfg, snap, audio_out) =
            (&mut self.rds, &mut self.adsb, &self.radar_cfg, &mut self.snap, &mut self.audio_out);
        let st = frame::parse_block(block, &mut self.last_seq, |p| {
            if p.crc_error {
                snap.system.crc_errors += 1;
                return;
            }
            match p.tid {
                tid::AUDIO => {
                    for a in audio::decode(p.words) {
                        if let Some(b) = a.rds {
                            rds.push(b);
                        }
                        snap.radio.pilot = a.pilot;
                        snap.radio.ctcss = a.ctcss;
                        audio_pow += (a.mono as f64).powi(2);
                        audio_n += 1;
                        audio_out.push(a.left);
                        audio_out.push(a.right);
                    }
                }
                tid::ADSB if p.words.len() == 2 => {
                    let (f, _) = adsb::from_words(p.words[0], p.words[1]);
                    adsb.push(f, now_s);
                }
                tid::RADAR_DET => {
                    if let Some(c) = radar::decode_cpi(p.words, radar_cfg) {
                        snap.radar.cpi = c.cpi;
                        snap.radar.cpis += 1;
                        snap.radar.dropped += c.dropped as u32;
                        snap.radar.detections = c.detections;
                    }
                }
                tid::RADAR_MAP => {
                    if let Some(m) = radar::decode_map(p.words) {
                        snap.radar.map = Some(m);
                        snap.radar.map_cpi = snap.radar.cpi;
                    }
                }
                t if t == want_iq => frame::iq_samples(p.words, &mut iq),
                _ => {}
            }
        });
        if audio_n > 0 {
            self.snap.radio.level_dbfs = 10.0 * (audio_pow / audio_n as f64 / (32767.0f64 * 32767.0)).max(1e-12).log10();
        }
        self.snap.radio.rds = self.rds.info.clone();
        if self.snap.system.recording {
            self.rec_out.extend_from_slice(&iq);
        }
        if !iq.is_empty() {
            self.spec.push(&iq);
            self.snap.spectrum.trace = self.spec.display(512);
            self.snap.spectrum.row = self.spec.waterfall.front().cloned().unwrap_or_default();
            self.snap.spectrum.frames = self.spec.frames();
        }
        self.adsb.expire(now_s, 60.0);
        self.snap.adsb.aircraft = self.adsb.aircraft.values().cloned().collect();
        self.snap.adsb.frames = self.adsb.frames;
        let s = &mut self.snap.system;
        s.packets += st.packets as u64;
        s.seq_gaps += st.seq_gaps as u64;
        s.resync_words += st.resync_words as u64;
        s.blocks += 1;
        self.words_t0.1 += block.len() as u64;
        if now_s - self.words_t0.0 >= 1.0 {
            s.stream_mbps = self.words_t0.1 as f64 * 64.0 / 1e6 / (now_s - self.words_t0.0);
            self.words_t0 = (now_s, 0);
        }
        self.snap.t = now_s;
    }

    fn retune(&mut self, freq_hz: f64, mode: Mode) -> Vec<Write> {
        let p = modes::plan(freq_hz, mode, self.snap.radio.gain_db);
        let r = &mut self.snap.radio;
        r.freq_hz = freq_hz;
        r.mode = Some(mode);
        r.path = Some(p.path);
        r.lo_hz = p.lo_hz;
        r.covered = p.covered;
        r.lna_forced = p.lna_forced;
        r.audio_rate = p.audio_rate;
        if mode != Mode::Adsb {
            self.rds = RdsDecoder::default();
        }
        let sp = &mut self.snap.spectrum;
        sp.stream = if p.path == Path::Hf { tid::SDR_B } else { tid::RADAR_IQ };
        sp.center_hz = freq_hz;
        sp.span_hz = p.stream_rate;
        sp.marker_hz = freq_hz;
        self.snap.function = Some(if mode == Mode::Adsb { Function::Adsb } else { Function::Radio });
        let w = p.writes.clone();
        self.plan = Some(p);
        w
    }

    /// Whether the transmit carrier is one the board can send (`TX_MAX_HZ`).
    pub fn tx_in_range(&self) -> bool {
        self.snap.tx.freq_hz > 0.0 && self.snap.tx.freq_hz < TX_MAX_HZ
    }

    /// A screen's command as the register writes it needs. Every `DSP_CTRL` write carries the transmit mode in
    /// bits 12:10; bit 1 (transmit enable) is R5F core 0's, which the I/O layer keeps as it is.
    pub fn command(&mut self, c: Command) -> Vec<Write> {
        let mut w = self.command_writes(c);
        let code = tx_mode_code(&self.snap.tx.mode) << 10;
        for x in w.iter_mut() {
            if let Write::Kria { off, val } = x {
                if *off == modes::kria_reg::DSP_CTRL {
                    *val = (*val & !(7 << 10)) | code;
                    self.dsp_ctrl = *val;
                }
            }
        }
        if !self.tx_in_range() {
            self.snap.tx.requested = false;
        }
        w
    }

    fn command_writes(&mut self, c: Command) -> Vec<Write> {
        let mode = self.snap.radio.mode.unwrap_or(Mode::Wbfm);
        let freq = if self.snap.radio.freq_hz > 0.0 { self.snap.radio.freq_hz } else { 98.1e6 };
        match c {
            Command::Function { function: Function::Radio } => self.retune(freq, if mode == Mode::Adsb { Mode::Wbfm } else { mode }),
            Command::Function { function: Function::Adsb } => self.retune(1090e6, Mode::Adsb),
            Command::Function { function: Function::Radar } => {
                self.snap.function = Some(Function::Radar);
                self.snap.spectrum.stream = tid::RADAR_IQ;
                modes::radar_plan(self.snap.radar.alpha_q8, self.snap.radar.floor)
            }
            Command::Tune { freq_hz } => self.retune(freq_hz.clamp(0.1e6, 3e9), mode),
            Command::Step { hz } => self.retune((freq + hz).clamp(0.1e6, 3e9), mode),
            Command::SetMode { mode } => self.retune(freq, mode),
            Command::Preset { index } => match self.snap.radio.presets.get(index).cloned() {
                Some(p) => self.retune(p.freq_hz, p.mode),
                None => vec![],
            },
            Command::Gain { db } => {
                self.snap.radio.gain_db = db.clamp(-12.0, 36.0);
                self.retune(freq, mode)
            }
            Command::Radar { alpha_q8, floor } => {
                self.snap.radar.alpha_q8 = alpha_q8;
                self.snap.radar.floor = floor;
                modes::radar_plan(alpha_q8, floor)
            }
            Command::TxSet { freq_hz, mode, level } => {
                let t = &mut self.snap.tx;
                t.freq_hz = freq_hz;
                t.mode = mode;
                t.level = level.clamp(0.0, 1.0);
                // the AD9767 at 25 MS/s on the stream: on HF the carrier inside the stream is the carrier out of
                // J952; a 1 kHz test tone until a microphone source is added
                let amp = (t.level * 0x7FFF as f64) as u16;
                let par = match t.mode.as_str() {
                    "am" => 0x6666,
                    "nbfm" => 0x00A0,
                    _ => 0,
                };
                let mut w = modes::tx_plan(t.freq_hz.clamp(0.0, TX_MAX_HZ), 1e3, par, amp);
                if self.dsp_ctrl != 0 {
                    // the mode bits are merged in by command()
                    w.push(Write::Kria { off: modes::kria_reg::DSP_CTRL, val: self.dsp_ctrl });
                }
                w
            }
            Command::TxRequest { on } => {
                self.snap.tx.requested = on;
                vec![]
            }
            Command::Licence { on } => {
                self.snap.tx.licensed = on;
                vec![]
            }
            Command::Record { on } => {
                self.snap.system.recording = on;
                vec![]
            }
            Command::Marker { freq_hz } => {
                self.snap.spectrum.marker_hz = freq_hz;
                vec![]
            }
            Command::MarkerFrac { x } => {
                let s = &mut self.snap.spectrum;
                s.marker_hz = s.center_hz + (x.clamp(0.0, 1.0) - 0.5) * s.span_hz;
                vec![]
            }
            Command::ListenAtMarker => self.retune(self.snap.spectrum.marker_hz, mode),
            Command::RadarAlphaStep { step } => {
                let a = (self.snap.radar.alpha_q8 as i32 + step).clamp(256, 16384) as u16;
                self.snap.radar.alpha_q8 = a;
                modes::radar_plan(a, self.snap.radar.floor)
            }
        }
    }

    /// The snapshot with the waterfall's history in it, for a dump.
    pub fn with_history(&self) -> Snapshot {
        let mut s = self.snap.clone();
        s.spectrum.history = self.spec.waterfall.iter().cloned().collect();
        s
    }

    pub fn plan(&self) -> Option<&Plan> {
        self.plan.as_ref()
    }

    pub fn snapshot_json(&self) -> String {
        serde_json::to_string(&self.snap).unwrap_or_else(|_| "{}".into())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::frame::encode_packet;

    #[test]
    fn transmit_mode_rides_on_every_dsp_ctrl_write_and_hf_only() {
        let dsp = |w: &[Write]| w.iter().rev().find_map(|x| match *x {
            Write::Kria { off, val } if off == modes::kria_reg::DSP_CTRL => Some(val),
            _ => None,
        });
        let mut h = Hmi::default();
        h.command(Command::Preset { index: 0 });
        let w = h.command(Command::TxSet { freq_hz: 7.1e6, mode: "usb".into(), level: 0.5 });
        assert_eq!(dsp(&w).unwrap() >> 10 & 7, 3);
        assert_eq!(dsp(&w).unwrap() & 2, 0, "bit 1 is the R5F's");
        // a retune keeps the transmit mode
        let w = h.command(Command::Step { hz: 1e5 });
        assert_eq!(dsp(&w).unwrap() >> 10 & 7, 3);
        assert!(h.tx_in_range());
        h.command(Command::TxRequest { on: true });
        assert!(h.snap.tx.requested);
        // above the stream's Nyquist frequency the request is dropped
        h.command(Command::TxSet { freq_hz: 145.5e6, mode: "nbfm".into(), level: 0.5 });
        h.command(Command::TxRequest { on: true });
        assert!(!h.tx_in_range() && !h.snap.tx.requested);
    }

    #[test]
    fn commands_deserialize_and_plan() {
        let mut h = Hmi::default();
        let c: Command = serde_json::from_str(r#"{"cmd":"preset","index":0}"#).unwrap();
        let w = h.command(c);
        assert!(!w.is_empty());
        assert_eq!(h.snap.radio.mode, Some(Mode::Wbfm));
        assert_eq!(h.snap.spectrum.stream, tid::RADAR_IQ);
        let c: Command = serde_json::from_str(r#"{"cmd":"function","function":"adsb"}"#).unwrap();
        h.command(c);
        assert_eq!(h.snap.function, Some(Function::Adsb));
        assert_eq!(h.snap.radio.lo_hz, Some(955e6));
    }

    #[test]
    fn a_block_feeds_every_screen() {
        let mut h = Hmi::default();
        h.command(Command::Preset { index: 0 });
        h.set_own_position(43.37, -8.40);
        let mut b = Vec::new();
        let aw: Vec<u64> = (0..64)
            .map(|k| audio::encode(&audio::AudioWord { left: k, right: -k, mono: 1000, pilot: true, ctcss: false, rds: None }))
            .collect();
        encode_packet(&mut b, tid::AUDIO, 2, 0, 1, &aw);
        let f = adsb::encode_ident(0x3C6586, "IBE3213");
        encode_packet(&mut b, tid::ADSB, 2, 1, 2, &adsb::to_words(f, 30));
        let sum = 0xFFu64 << 56 | 5 << 40;
        encode_packet(&mut b, tid::RADAR_DET, 2, 2, 3, &[sum]);
        let iq = frame::iq_words(&vec![(1000i16, 0i16); 4096]);
        encode_packet(&mut b, tid::RADAR_IQ, 0, 3, 4, &iq);
        h.on_block(&b, 1.0);
        assert!(h.snap.radio.pilot);
        assert!((h.snap.radio.level_dbfs + 30.3).abs() < 0.1);
        assert_eq!(h.audio_out.len(), 128);
        assert_eq!(h.snap.adsb.aircraft[0].callsign, "IBE3213");
        assert_eq!(h.snap.radar.cpi, 5);
        assert_eq!(h.snap.spectrum.trace.len(), 512);
        assert_eq!(h.snap.system.packets, 4);
        assert!(h.snapshot_json().contains("\"callsign\":\"IBE3213\""));
    }
}
