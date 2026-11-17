//! HackRF Pro on the KV260: the wideband sweep through the PL, and transmit above this board's range.
//!
//! What the HackRF Pro adds to the board and the other integrations (docs/INTEGRATIONS.md section 10):
//! reception and transmission from 1.1 to 6 GHz (tunable from 0 to 7.1 GHz), where this board's front ends stop
//! (HF, VHF/UHF to 1.1 GHz, the radar's IF), at up to 20 MS/s; and its sweep mode, which retunes every block
//! for a panorama of the whole range.
//!
//! In sweep mode the firmware tunes the LO to `f + 7.5 MHz` for a block whose header carries `f`, steps `f` by
//! +5 MHz and +15 MHz alternately, and discards one block after each retune on the Pro (two on the One). Each
//! 16,384-byte block that reaches USB begins with 0x7F 0x7F and `f` as a little-endian u64. The PL block
//! `kria_sweep` turns each into 128 power bins (two 5 MHz quarter bands of a 256-point FFT); this module places
//! them on the panorama, keeps the peak-hold, and lists the strongest signals.

use crate::cplx::C;

pub const BLOCK: usize = 16384;
pub const N: usize = 256;
pub const FS: f64 = 20e6;
pub const OFFSET: f64 = 7.5e6;
pub const BIN_HZ: f64 = FS / N as f64;

/// One block's header: the frequency `f` if the magic is there.
pub fn block_freq(b: &[u8]) -> Option<u64> {
    if b.len() >= 10 && b[0] == 0x7F && b[1] == 0x7F {
        Some(u64::from_le_bytes(b[2..10].try_into().unwrap()))
    } else {
        None
    }
}

/// The sweep's tuning sequence for [f_min, f_max) in MHz, as the firmware's INTERLEAVED style steps it.
pub fn sweep_plan(f_min_mhz: u64, f_max_mhz: u64) -> Vec<u64> {
    let mut v = Vec::new();
    let mut f = f_min_mhz * 1_000_000;
    let step = 20_000_000u64;
    let mut odd = true;
    loop {
        v.push(f);
        if !odd && f + step >= f_max_mhz * 1_000_000 {
            break;
        }
        f += if odd { step / 4 } else { 3 * step / 4 };
        odd = !odd;
    }
    v
}

/// Q1.15 window and twiddle tables for the PL (written once at start).
pub fn window_q15() -> Vec<u16> {
    (0..N)
        .map(|i| {
            let w = 0.5 * (1.0 - (2.0 * core::f64::consts::PI * i as f64 / (N as f64 - 1.0)).cos());
            (w * 32767.0).round() as u16
        })
        .collect()
}

pub fn twiddles_q15() -> Vec<u32> {
    (0..N / 2)
        .map(|k| {
            let ph = -2.0 * core::f64::consts::PI * k as f64 / N as f64;
            let c = (ph.cos() * 32767.0).round() as i16 as u16 as u32;
            let s = (ph.sin() * 32767.0).round() as i16 as u16 as u32;
            c | (s << 16)
        })
        .collect()
}

fn bitrev8(v: usize) -> usize {
    (v as u8).reverse_bits() as usize
}

/// Bit-exact model of kria_sweep for one block: the frequency and the 128 powers in the PL's output order, each
/// the sum over the block's last 2^`nseg_log2` segments of 256 samples, shifted right by `pshift`.
pub fn pl_block(b: &[u8], win: &[u16], twd: &[u32], pshift: u32, nseg_log2: u32) -> Option<(u64, Vec<u32>)> {
    let f = block_freq(b)?;
    if b.len() != BLOCK {
        return None;
    }
    let nseg = 1usize << nseg_log2;
    let mut acc = [0u64; 128];
    for s in 0..nseg {
        let seg = &b[BLOCK - 2 * N * (nseg - s)..BLOCK - 2 * N * (nseg - s - 1)];
        let (re, im) = fft_segment(seg, win, twd);
        for (j, k) in (161..225).chain(33..97).enumerate() {
            acc[j] += (re[k] * re[k] + im[k] * im[k]) as u64;
        }
    }
    let out = acc.iter().map(|&a| (a >> pshift).min(u32::MAX as u64) as u32).collect();
    Some((f, out))
}

/// One segment of 256 samples through the PL's windowed radix-2 FFT (1/2 per stage), bit-exact.
fn fft_segment(seg: &[u8], win: &[u16], twd: &[u32]) -> ([i64; N], [i64; N]) {
    let mut re = [0i64; N];
    let mut im = [0i64; N];
    for i in 0..N {
        let xr = seg[2 * i] as i8 as i64;
        let xi = seg[2 * i + 1] as i8 as i64;
        let w = win[i] as i64;
        re[bitrev8(i)] = (xr * w) >> 7;
        im[bitrev8(i)] = (xi * w) >> 7;
    }
    for st in 0..8 {
        let half = 1usize << st;
        for bf in 0..N / 2 {
            let pos = bf & (half - 1);
            let grp = bf >> st;
            let i0 = (grp << (st + 1)) | pos;
            let i1 = i0 + half;
            let t = twd[pos << (7 - st)];
            let wc = (t & 0xffff) as u16 as i16 as i64;
            let ws = (t >> 16) as u16 as i16 as i64;
            let tr = (wc * re[i1] - ws * im[i1]) >> 15;
            let ti = (wc * im[i1] + ws * re[i1]) >> 15;
            let (ar, ai) = (re[i0], im[i0]);
            re[i0] = (ar + tr) >> 1;
            im[i0] = (ai + ti) >> 1;
            re[i1] = (ar - tr) >> 1;
            im[i1] = (ai - ti) >> 1;
        }
    }
    (re, im)
}

/// The PL's 64-bit beats for one block's output: frequency, then two powers per beat.
pub fn out_beats(f: u64, p: &[u32]) -> Vec<u64> {
    let mut v = vec![f];
    for j in 0..64 {
        v.push(p[2 * j] as u64 | ((p[2 * j + 1] as u64) << 32));
    }
    v
}

/// dB of a PL power, referred to full scale: a full-scale complex tone (|x| = 127 at the int8 input) in one bin
/// gives 0 dBFS. The chain's gain: window mean 0.5, x 2^8 at the input (>> 7 of a Q15 window), / 256 in the FFT.
/// `scale_log2` is PSHIFT minus NSEG_LOG2: the output times 2^scale_log2 is the mean power over the segments.
pub fn dbfs(p: u32, scale_log2: i32) -> f64 {
    let full = 127.0 * 256.0 * 0.5; // amplitude of a full-scale bin after the PL's FFT
    let mean = p.max(1) as f64 * 2f64.powi(scale_log2);
    10.0 * (mean / (full * full)).log10()
}

/// Panorama from 0 to 7.25 GHz in 78.125 kHz bins: the latest sweep and the peak-hold.
pub struct Panorama {
    pub f0: f64,
    pub db: Vec<f64>,
    pub hold: Vec<f64>,
    pub filled: Vec<bool>,
}

impl Panorama {
    pub fn new(f0: f64, f1: f64) -> Panorama {
        let n = ((f1 - f0) / BIN_HZ).ceil() as usize;
        Panorama { f0, db: vec![-150.0; n], hold: vec![-150.0; n], filled: vec![false; n] }
    }
    /// Places one block's 128 bins: [f, f + 5 MHz) from the first 64, [f + 10, f + 15 MHz) from the rest. The PL
    /// order is bins 161.. then 33..; bin 161 sits at f + 7.5 MHz - 95 bins = f + 78 kHz.
    pub fn place(&mut self, f: u64, p: &[u32], scale_log2: i32) {
        for (j, &v) in p.iter().enumerate() {
            let bin = if j < 64 { 161 + j } else { 33 + j - 64 } as f64;
            let rel = if bin >= 128.0 { bin - 256.0 } else { bin };
            let fr = f as f64 + OFFSET + rel * BIN_HZ;
            let idx = ((fr - self.f0) / BIN_HZ).round();
            if idx >= 0.0 && (idx as usize) < self.db.len() {
                let i = idx as usize;
                let d = dbfs(v, scale_log2);
                self.db[i] = d;
                self.filled[i] = true;
                if d > self.hold[i] {
                    self.hold[i] = d;
                }
            }
        }
    }
    pub fn freq(&self, i: usize) -> f64 {
        self.f0 + i as f64 * BIN_HZ
    }
    /// Signals, as (centre Hz, occupied width Hz, peak dBFS), strongest first.
    ///
    /// One FFT per block makes a noise-like signal (LTE, Wi-Fi, DVB-T) a ragged spectrum, so the detector works on
    /// the power averaged over 9 bins (700 kHz), takes the runs `thresh` dB above the median floor, and joins runs
    /// less than 1 MHz apart. A carrier keeps its own bin's level as its peak.
    pub fn signals(&self, thresh: f64) -> Vec<(f64, f64, f64)> {
        let n = self.db.len();
        let lin: Vec<f64> = self.db.iter().map(|d| 10f64.powf(d / 10.0)).collect();
        let sm: Vec<f64> = (0..n)
            .map(|i| {
                let (a, b) = (i.saturating_sub(4), (i + 5).min(n));
                let (s, c) = (a..b).filter(|&k| self.filled[k]).fold((0.0, 0), |(s, c), k| (s + lin[k], c + 1));
                if c > 0 { 10.0 * (s / c as f64).log10() } else { -150.0 }
            })
            .collect();
        let mut v: Vec<f64> = (0..n).filter(|&i| self.filled[i]).map(|i| sm[i]).collect();
        if v.is_empty() {
            return vec![];
        }
        v.sort_by(|a, b| a.partial_cmp(b).unwrap());
        let floor = v[v.len() / 2];
        let above: Vec<bool> = (0..n).map(|i| self.filled[i] && sm[i] > floor + thresh).collect();
        let gap = (1e6 / BIN_HZ) as usize;
        let mut runs: Vec<(usize, usize)> = Vec::new();
        let mut i = 0;
        while i < n {
            if above[i] {
                let s = i;
                while i < n && above[i] {
                    i += 1;
                }
                match runs.last_mut() {
                    Some(last) if s - last.1 <= gap => last.1 = i,
                    _ => runs.push((s, i)),
                }
            }
            i += 1;
        }
        let mut out: Vec<(f64, f64, f64)> = runs
            .iter()
            .map(|&(s, e)| {
                let pk = (s..e).map(|k| self.db[k]).fold(-150.0, f64::max);
                (self.freq(s) + (e - s) as f64 * BIN_HZ / 2.0, (e - s) as f64 * BIN_HZ, pk)
            })
            .collect();
        out.sort_by(|a, b| b.2.partial_cmp(&a.2).unwrap());
        out
    }
}

/// Transmit: the HackRF keys only while R5F core 0's interlock says `transmit` (the same lock as this board's own
/// transmitter: licence, vehicle stopped, time-out), and only inside the bands of the licence.
pub struct TxGate {
    pub bands_hz: Vec<(f64, f64)>,
}

#[derive(Debug, PartialEq, Eq)]
pub enum TxState {
    Keyed,
    BlockedInterlock,
    BlockedBand,
}

impl TxGate {
    /// Amateur allocations from 1.24 to 5.85 GHz (ITU Region 1), where the HackRF goes beyond this board's
    /// transmitter.
    pub fn amateur_r1() -> TxGate {
        TxGate { bands_hz: vec![(1240e6, 1300e6), (2300e6, 2450e6), (3400e6, 3410e6), (5650e6, 5850e6)] }
    }
    pub fn check(&self, f_hz: f64, bw_hz: f64, interlock_transmit: bool) -> TxState {
        if !self.bands_hz.iter().any(|&(a, b)| f_hz - bw_hz / 2.0 >= a && f_hz + bw_hz / 2.0 <= b) {
            TxState::BlockedBand
        } else if !interlock_transmit {
            TxState::BlockedInterlock
        } else {
            TxState::Keyed
        }
    }
}

/// An NBFM test signal at baseband for the HackRF's transmit, signed 8-bit I/Q (its USB format), `amp` <= 127.
pub fn nbfm_tone(n: usize, fs: f64, tone: f64, dev: f64, amp: f64) -> Vec<u8> {
    let mut ph = 0.0;
    let mut out = Vec::with_capacity(2 * n);
    for t in 0..n {
        ph += 2.0 * core::f64::consts::PI * dev * (2.0 * core::f64::consts::PI * tone * t as f64 / fs).sin() / fs;
        let c = C::cis(ph).scale(amp);
        out.push(c.re.round() as i8 as u8);
        out.push(c.im.round() as i8 as u8);
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn plan_covers_the_range_without_gaps() {
        let plan = sweep_plan(2400, 2500);
        // each tuning covers [f, f+5) and [f+10, f+15) MHz
        let mut cov = vec![false; 100];
        for f in plan {
            for d in [0u64, 10] {
                for m in 0..5 {
                    let x = (f / 1_000_000 + d + m) as i64 - 2400;
                    if (0..100).contains(&x) {
                        cov[x as usize] = true;
                    }
                }
            }
        }
        assert!(cov.iter().all(|&c| c));
    }

    #[test]
    fn a_tone_lands_in_its_bin() {
        let win = window_q15();
        let twd = twiddles_q15();
        let f = 2_430_000_000u64;
        let tone = 2_433_000_000.0; // in [f, f+5 MHz)
        let mut b = vec![0u8; BLOCK];
        b[0] = 0x7F;
        b[1] = 0x7F;
        b[2..10].copy_from_slice(&f.to_le_bytes());
        let off = tone - (f as f64 + OFFSET);
        for i in 5..BLOCK / 2 {
            let c = C::cis(2.0 * core::f64::consts::PI * off * i as f64 / FS).scale(100.0);
            b[2 * i] = c.re.round() as i8 as u8;
            b[2 * i + 1] = c.im.round() as i8 as u8;
        }
        let (ff, p) = pl_block(&b, &win, &twd, 3, 3).unwrap();
        assert_eq!(ff, f);
        let mut pan = Panorama::new(2.4e9, 2.5e9);
        pan.place(ff, &p, 0);
        let s = pan.signals(20.0);
        assert!(!s.is_empty());
        assert!((s[0].0 - tone).abs() < BIN_HZ, "found {:?}", s[0]);
        assert!(s[0].2 > -6.0 && s[0].2 < 1.0, "level {}", s[0].2);
    }

    #[test]
    fn transmit_needs_band_and_interlock() {
        let g = TxGate::amateur_r1();
        assert_eq!(g.check(2400e6, 25e3, true), TxState::Keyed);
        assert_eq!(g.check(2400e6, 25e3, false), TxState::BlockedInterlock);
        assert_eq!(g.check(2460e6, 25e3, true), TxState::BlockedBand);
    }
}
