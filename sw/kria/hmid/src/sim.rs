//! The simulated board: the DMA blocks `kria_ps_framer` would write for what the registers ask, from a scene.
//!
//! It reads the Kria register writes the HMI makes (`DSP_CTRL` above all) to know which function runs, then
//! produces that function's streams exactly as the PL packs them:
//! * receiver: stream 0x20 at the plan's audio rate, the programme of the station on that frequency if the scene
//!   has one (FM 98.1 with stereo tones, the pilot and an RDS station name and text; AM, SSB, NBFM with CTCSS),
//!   noise elsewhere; and 4096-sample I/Q bursts of the receiver's stream for the spectrum;
//! * ADS-B: stream 0x21 from six aircraft flying round the vehicle (identification, CPR positions, velocity);
//! * radar: stream 0x22 for 20 CPIs a second and 0x23 for every fourth, three targets on a noise floor.
//! It also runs the transmit interlock as R5F core 0 would (`kria_core::interlock`), on a vehicle that drives
//! and parks, and reports simulated temperatures. Everything it sends goes through `kria_hmi_core`'s encoders.

use kria_core::interlock::{Config as IlCfg, Inputs, Interlock, Reason, Speed};
use kria_hmi_core::adsb;
use kria_hmi_core::audio::{self, AudioWord};
use kria_hmi_core::frame::{encode_packet, iq_words, tid};
use kria_hmi_core::modes::{kria_reg, Write};
use kria_hmi_core::radar::map_cell;
use kria_hmi_core::state::{SystemView, TxView, VehicleView};
use std::f64::consts::PI;

struct Rng(u64);
impl Rng {
    fn next(&mut self) -> f64 {
        self.0 ^= self.0 << 13;
        self.0 ^= self.0 >> 7;
        self.0 ^= self.0 << 17;
        (self.0 >> 11) as f64 / (1u64 << 53) as f64
    }
    fn gauss(&mut self) -> f64 {
        let (a, b) = (self.next().max(1e-12), self.next());
        (-2.0 * a.ln()).sqrt() * (2.0 * PI * b).cos()
    }
}

struct Station {
    freq: f64,
    kind: &'static str,
    level: f64,
}

const STATIONS: [Station; 6] = [
    Station { freq: 98.1e6, kind: "wbfm", level: 0.30 },
    Station { freq: 7.2e6, kind: "am", level: 0.20 },
    Station { freq: 121.5e6, kind: "am", level: 0.12 },
    Station { freq: 14.2e6, kind: "usb", level: 0.15 },
    Station { freq: 446.00625e6, kind: "nbfm", level: 0.25 },
    Station { freq: 145.6e6, kind: "nbfm", level: 0.18 },
];

struct Plane {
    icao: u32,
    call: &'static str,
    lat: f64,
    lon: f64,
    alt: i32,
    kt: f64,
    trk: f64,
    vr: i32,
}

pub struct Sim {
    rng: Rng,
    t: f64,
    seq: u16,
    dsp_ctrl: u32,
    pub freq: f64,
    audio_rate: f64,
    audio_phase: f64,
    audio_n: f64,
    rds_bits: Vec<bool>,
    rds_pos: usize,
    rds_acc: f64,
    planes: Vec<Plane>,
    own: (f64, f64),
    adsb_acc: f64,
    cpi: u16,
    cpi_acc: f64,
    il: Interlock,
    pub tx_req: bool,
    pub licensed: bool,
}

impl Sim {
    pub fn new(own: (f64, f64)) -> Self {
        let rds_bits = audio::station_groups(0xE2A1, 10, "KV260FM", "Rev08 in the car: simulated board, real decoders")
            .concat();
        let p = |icao, call, dlat, dlon, alt, kt, trk, vr| Plane { icao, call, lat: own.0 + dlat, lon: own.1 + dlon, alt, kt, trk, vr };
        Self {
            rng: Rng(0x9E37_79B9_7F4A_7C15),
            t: 0.0,
            seq: 0,
            dsp_ctrl: 0,
            freq: 0.0,
            audio_rate: 0.0,
            audio_phase: 0.0,
            audio_n: 0.0,
            rds_bits,
            rds_pos: 0,
            rds_acc: 0.0,
            planes: vec![
                p(0x3C6586, "IBE3213", 0.30, 0.25, 23000, 412.0, 63.0, -1280),
                p(0x4CA8F2, "RYR82KD", -0.42, 0.10, 36000, 448.0, 200.0, 0),
                p(0x345041, "VLG1347", 0.12, -0.55, 12500, 300.0, 120.0, 1600),
                p(0x400A57, "EZY69QL", -0.20, -0.35, 38000, 460.0, 20.0, 0),
                p(0x346213, "AEA7262", 0.55, -0.10, 31000, 430.0, 175.0, -900),
                p(0x495299, "TAP1041", -0.05, 0.62, 8000, 250.0, 280.0, -700),
            ],
            own,
            adsb_acc: 0.0,
            cpi: 0,
            cpi_acc: 0.0,
            il: Interlock::new(IlCfg { tick_hz: 1000, ..Default::default() }),
            tx_req: false,
            licensed: false,
        }
    }

    pub fn write(&mut self, w: &Write) {
        if let Write::Kria { off, val } = *w {
            if off == kria_reg::DSP_CTRL {
                self.dsp_ctrl = val;
            }
        }
    }

    pub fn set_tuning(&mut self, freq: f64, audio_rate: f64) {
        self.freq = freq;
        self.audio_rate = audio_rate;
    }

    fn station(&self) -> Option<&'static Station> {
        STATIONS.iter().find(|s| (s.freq - self.freq).abs() < 5e3)
    }

    fn push(&mut self, out: &mut Vec<u64>, t: u8, words: &[u64]) {
        let flags = if t >= 0x20 { 2 } else { 0 };
        encode_packet(out, t, flags, self.seq, (self.t * 1e8) as u64, words);
        self.seq = self.seq.wrapping_add(1);
    }

    /// One block covering `dt` seconds of the board.
    pub fn block(&mut self, dt: f64) -> Vec<u64> {
        let mut out = Vec::new();
        let rx = self.dsp_ctrl & 1 != 0;
        let adsb_on = self.dsp_ctrl & (1 << 7) != 0;
        let radar_on = self.dsp_ctrl & (1 << 8) != 0;
        if rx && adsb_on {
            self.adsb(dt, &mut out);
        } else if rx && radar_on {
            self.radar(dt, &mut out);
        } else if rx {
            self.audio(dt, &mut out);
        }
        if rx {
            self.iq(&mut out, adsb_on || radar_on);
        }
        self.t += dt;
        out
    }

    fn audio(&mut self, dt: f64, out: &mut Vec<u64>) {
        let n_total = self.audio_rate * dt + self.audio_n;
        let n = n_total.floor() as usize;
        self.audio_n = n_total - n as f64;
        let st = self.station();
        let mut words = Vec::with_capacity(64);
        for _ in 0..n {
            let tt = self.audio_phase / self.audio_rate;
            self.audio_phase += 1.0;
            let noise = 0.02 * self.rng.gauss();
            let (l, r, pilot, ctcss) = match st.map(|s| s.kind) {
                Some("wbfm") => (0.3 * (2.0 * PI * 440.0 * tt).sin(), 0.3 * (2.0 * PI * 660.0 * tt).sin(), true, false),
                Some("am") => {
                    let a = 0.25 * (2.0 * PI * 1000.0 * tt).sin() * (1.0 + 0.5 * (2.0 * PI * 0.7 * tt).sin());
                    (a, a, false, false)
                }
                Some("usb") => {
                    let a = 0.2 * ((2.0 * PI * 700.0 * tt).sin() + (2.0 * PI * 1900.0 * tt).sin());
                    (a, a, false, false)
                }
                Some(_) => {
                    let a = 0.3 * (2.0 * PI * 1000.0 * tt).sin();
                    (a, a, false, true)
                }
                None => (8.0 * noise, 8.0 * noise, false, false),
            };
            let mut rds = None;
            if st.map(|s| s.kind) == Some("wbfm") {
                self.rds_acc += 1187.5 / self.audio_rate;
                if self.rds_acc >= 1.0 {
                    self.rds_acc -= 1.0;
                    rds = Some(self.rds_bits[self.rds_pos]);
                    self.rds_pos = (self.rds_pos + 1) % self.rds_bits.len();
                }
            }
            let q = |v: f64| ((v + noise) * 32767.0).clamp(-32768.0, 32767.0) as i16;
            words.push(audio::encode(&AudioWord { left: q(l), right: q(r), mono: q(0.5 * (l + r)), pilot, ctcss, rds }));
            if words.len() == 64 {
                self.push(out, tid::AUDIO, &words);
                words.clear();
            }
        }
        if !words.is_empty() {
            self.push(out, tid::AUDIO, &words);
        }
    }

    fn iq(&mut self, out: &mut Vec<u64>, wide_scene: bool) {
        let hf = (self.dsp_ctrl >> 2) & 3 == 1;
        let (fs, stream) = if hf { (15.625e6, tid::SDR_B) } else { (25e6, tid::RADAR_IQ) };
        let mut s = Vec::with_capacity(4096);
        let carriers: Vec<(f64, f64)> = STATIONS
            .iter()
            .map(|st| (st.freq - self.freq, st.level))
            .chain(if wide_scene { vec![(0.0, 0.05)] } else { vec![] })
            .filter(|(d, _)| d.abs() < fs / 2.0)
            .collect();
        for k in 0..4096 {
            let tt = (self.t * fs).floor() / fs + k as f64 / fs;
            let (mut i, mut q) = (0.003 * self.rng.gauss(), 0.003 * self.rng.gauss());
            for &(df, a) in &carriers {
                let fm = if a > 0.29 { 75e3 * (2.0 * PI * 440.0 * tt).sin() / (2.0 * PI * 440.0) } else { 0.0 };
                let ph = 2.0 * PI * (df * tt + fm);
                i += a * ph.cos();
                q += a * ph.sin();
            }
            s.push(((i * 32767.0) as i16, (q * 32767.0) as i16));
        }
        for c in iq_words(&s).chunks(512) {
            self.push(out, stream, c);
        }
    }

    fn adsb(&mut self, dt: f64, out: &mut Vec<u64>) {
        for p in self.planes.iter_mut() {
            let d = p.kt * 1.852 / 3600.0 * dt / 111.2;
            p.lat += d * p.trk.to_radians().cos();
            p.lon += d * p.trk.to_radians().sin() / p.lat.to_radians().cos();
            p.alt = (p.alt + (p.vr as f64 * dt / 60.0) as i32).clamp(2000, 41000);
            if (p.lat - self.own.0).abs() > 0.9 || (p.lon - self.own.1).abs() > 1.2 {
                p.trk = (p.trk + 180.0) % 360.0;
            }
        }
        self.adsb_acc += dt;
        while self.adsb_acc >= 0.25 {
            self.adsb_acc -= 0.25;
            let slot = (self.t / 0.25) as u64;
            let frames: Vec<u128> = self
                .planes
                .iter()
                .map(|p| match slot % 8 {
                    0 => adsb::encode_ident(p.icao, p.call),
                    1 | 5 => adsb::encode_velocity(p.icao, p.kt, p.trk, p.vr),
                    k => adsb::encode_position(p.icao, p.lat, p.lon, p.alt, k % 2 == 1),
                })
                .collect();
            for f in frames {
                let w = adsb::to_words(f, 40 + (self.rng.next() * 20.0) as u16);
                self.push(out, tid::ADSB, &w);
            }
        }
    }

    fn radar(&mut self, dt: f64, out: &mut Vec<u64>) {
        self.cpi_acc += dt * 20.0;
        while self.cpi_acc >= 1.0 {
            self.cpi_acc -= 1.0;
            // three targets in target coordinates (range bin, Doppler bin), moving in range slowly
            let k = self.cpi as f64;
            let targets = [((12.0 + 0.02 * k) % 64.0, 3i8, 4.0e5), ((40.0 - 0.01 * k).rem_euclid(64.0), -5i8, 1.2e5), (6.0, 0i8, 8.0e4)];
            let mut dets = Vec::new();
            let mut cells = Vec::with_capacity(1024);
            for idx in 0..1024u32 {
                let (rb, db) = ((idx % 64) as u8, (idx / 64) as u8);
                // map cell (rb, db) is a target at ((64 - rb) % 64, signed (16 - db) % 16)
                let tr = (64 - rb as u32) % 64;
                let td = { let d = (16 - db as i32) % 16; if d >= 8 { d - 16 } else { d } };
                let mut p = 2000.0 * (1.0 + 0.5 * self.rng.gauss()).abs();
                let mut det = false;
                for &(r, d, a) in &targets {
                    if (r.round() as u32 % 64) == tr && d as i32 == td {
                        p += a * (0.8 + 0.4 * self.rng.next());
                        det = true;
                    }
                }
                if det {
                    dets.push((p as u64) << 32 | (self.cpi as u64) << 16 | (db as u64) << 8 | rb as u64);
                }
                cells.push(map_cell(det, rb, db, p as u32));
            }
            let n = dets.len() as u64;
            dets.push(0xFFu64 << 56 | (self.cpi as u64) << 40 | n << 24);
            self.push(out, tid::RADAR_DET, &dets);
            if self.cpi % 4 == 0 {
                let w: Vec<u64> = cells.chunks(2).map(|c| c[0] as u64 | (c[1] as u64) << 32).collect();
                self.push(out, tid::RADAR_MAP, &w);
            }
            self.cpi = self.cpi.wrapping_add(1);
        }
    }

    /// The vehicle drives for 40 s and parks for 40 s; the interlock runs on its speed.
    pub fn vehicle_and_tx(&mut self, v: &mut VehicleView, tx: &mut TxView) {
        let phase = self.t % 80.0;
        let kmh = if phase < 40.0 { 50.0 + 20.0 * (phase / 40.0 * PI).sin() } else { 0.0 };
        v.speed_kmh = Some(kmh);
        v.rpm = Some(if kmh > 0.0 { 1500.0 + 25.0 * kmh } else { 800.0 });
        v.coolant_c = Some(88.0);
        v.fuel_pct = Some(62.0);
        v.source = "simulated ECU (opendash-telemetry/1)".into();
        let now = (self.t * 1000.0) as u64;
        let d = self.il.step(Inputs {
            now,
            ecu: Some(Speed { centi_kmh: (kmh * 100.0) as u32, stamp: now }),
            gps: None,
            licensed: tx.licensed,
            request: tx.requested,
        });
        tx.keyed = d.transmit;
        tx.reason = match d.reason {
            Reason::Keyed => "keyed",
            Reason::Idle => "idle",
            Reason::NoLicence => "no licence",
            Reason::Moving => "vehicle moving",
            Reason::SpeedUnknown => "speed unknown",
            Reason::Settling => "parked, settling",
            Reason::TimedOut => "time-out",
        }
        .into();
    }

    pub fn system(&mut self, s: &mut SystemView) {
        s.link_up = true;
        s.temp_k26_c = Some(58.0 + 2.0 * (self.t / 30.0).sin());
        s.temp_artix_c = Some(51.0 + 1.5 * (self.t / 40.0).cos());
        s.r5f0 = "running (simulated): PPS locked, link watchdog ok".into();
        s.r5f1 = "running (simulated): beam scan".into();
        s.platform = "simulated board (kria-hmid --sim)".into();
    }
}
