//! KrakenSDR direction finding on the KV260.
//!
//! The KrakenSDR is five RTL2832U + R820T2 receivers on one clock behind a USB hub, with a noise source that the
//! control channel's bias-tee GPIO switches onto all five inputs. Each RTL device streams unsigned 8-bit I/Q
//! (zero at 127.5) at 2.4 MS/s. Two things differ from channel to channel and are measured here, from the noise
//! source's bursts:
//!
//! - **when each stream started**: a whole number of samples, found as the peak of the cross-correlation with
//!   channel 0 over +/-`max_lag` samples ([`estimate_delays`]);
//! - **each channel's complex gain** (the R820T2's synthesiser phase and the chain's gain): from the dominant
//!   eigenvector of the aligned channels' covariance, which for one common source is the vector of gains up to
//!   a common factor, with the amplitude taken from each channel's power ([`estimate_weights`]).
//!
//! Then the aligned, quantised snapshots go to the PL (`fpga/kria/integrations/kria_doa.v`) with the weights; it
//! returns the covariance R and the Bartlett spectrum. [`music`] finds the bearings from R.
//!
//! The methods are the textbook ones (cross-correlation for delay, the principal eigenvector for the array's
//! calibration, MUSIC and Bartlett for direction finding), written here from their definitions. KrakenRF's
//! `heimdall_daq_fw` and `krakensdr_doa` do the same jobs on a Raspberry Pi; no code of theirs is used.

use crate::cplx::{jacobi_sym, C};

pub const M: usize = 5;
pub const NA: usize = 360;

/// Unsigned 8-bit RTL I/Q to signed: u - 128 (the stream's zero, 127.5, becomes -0.5; the PL takes int8).
pub fn rtl_to_i8(u: u8) -> i8 {
    (u as i16 - 128) as i8
}

pub fn rtl_to_c(buf: &[u8]) -> Vec<C> {
    buf.chunks_exact(2).map(|p| C::new(p[0] as f64 - 127.5, p[1] as f64 - 127.5)).collect()
}

/// Reassembles each channel's byte stream from the USB transfers as they complete, in any interleaving: the
/// librtlsdr callbacks of the five devices arrive in no fixed order, each with one transfer of one device.
pub struct Reassembler {
    pub streams: [Vec<u8>; M],
}

impl Default for Reassembler {
    fn default() -> Self {
        Reassembler { streams: Default::default() }
    }
}

impl Reassembler {
    pub fn push(&mut self, ch: usize, transfer: &[u8]) {
        self.streams[ch].extend_from_slice(transfer);
    }
}

/// Lag of each channel against channel 0: `x_k[i]` lines up with `x_0[i + lag_k]`.
pub fn estimate_delays(ch: &[Vec<C>], n: usize, max_lag: usize) -> [usize; M] {
    let mut out = [0usize; M];
    for k in 1..M {
        let mut best = (0usize, 0.0f64);
        for lag in 0..=max_lag {
            let mut s = C::ZERO;
            for i in 0..n {
                s += ch[0][i + lag] * ch[k][i].conj();
            }
            if s.abs() > best.1 {
                best = (lag, s.abs());
            }
        }
        out[k] = best.0;
    }
    out
}

/// Index where each channel's aligned data begin, given the lags: all channels then start at the same instant.
pub fn align_starts(lag: &[usize; M]) -> [usize; M] {
    let dmax = *lag.iter().max().unwrap();
    let mut s = [0usize; M];
    for k in 0..M {
        s[k] = dmax - lag[k];
    }
    s
}

pub fn covariance(x: &[&[C]], n: usize) -> Vec<Vec<C>> {
    let mut r = vec![vec![C::ZERO; M]; M];
    for t in 0..n {
        for i in 0..M {
            for j in 0..M {
                r[i][j] += x[i][t] * x[j][t].conj();
            }
        }
    }
    r
}

/// Calibration weights from the noise-source burst (aligned), such that `w_k x_k` all carry the common source
/// with channel 0's phase and amplitude.
pub fn estimate_weights(x: &[&[C]], n: usize) -> [C; M] {
    let r = covariance(x, n);
    // dominant eigenvector by power iteration (the common source dominates by tens of dB)
    let mut v = [C::ONE; M];
    for _ in 0..60 {
        let mut nv = [C::ZERO; M];
        for i in 0..M {
            for j in 0..M {
                nv[i] += r[i][j] * v[j];
            }
        }
        let nrm = nv.iter().map(|c| c.norm2()).sum::<f64>().sqrt();
        for i in 0..M {
            v[i] = nv[i].scale(1.0 / nrm);
        }
    }
    let p: Vec<f64> = (0..M).map(|i| r[i][i].re).collect();
    let mut w = [C::ONE; M];
    for k in 0..M {
        let ph = v[0] / v[k];
        w[k] = ph.scale(1.0 / ph.abs() * (p[0] / p[k]).sqrt());
    }
    w
}

/// Q2.14 register value of a weight: [15:0] real, [31:16] imaginary.
pub fn q14(c: C) -> u32 {
    let q = |x: f64| (x * 16384.0).round().clamp(-32768.0, 32767.0) as i16 as u16 as u32;
    q(c.re) | (q(c.im) << 16)
}

pub fn q14_re(v: u32) -> i32 {
    (v & 0xffff) as u16 as i16 as i32
}
pub fn q14_im(v: u32) -> i32 {
    (v >> 16) as u16 as i16 as i32
}

/// The array: element positions in metres, x towards bearing 0, y towards bearing 90 degrees.
#[derive(Clone, Debug)]
pub struct Array {
    pub x: [f64; M],
    pub y: [f64; M],
}

impl Array {
    /// Uniform circular array of five elements, element k at angle 72 k degrees.
    pub fn uca(radius: f64) -> Array {
        let mut a = Array { x: [0.0; M], y: [0.0; M] };
        for k in 0..M {
            let ang = 2.0 * core::f64::consts::PI * k as f64 / M as f64;
            a.x[k] = radius * ang.cos();
            a.y[k] = radius * ang.sin();
        }
        a
    }
    pub fn steering(&self, bearing_deg: f64, lambda: f64) -> [C; M] {
        let th = bearing_deg.to_radians();
        let mut a = [C::ZERO; M];
        for k in 0..M {
            a[k] = C::cis(2.0 * core::f64::consts::PI / lambda * (self.x[k] * th.cos() + self.y[k] * th.sin()));
        }
        a
    }
}

/// The pairs (i < j) in the PL's table order.
pub const PAIRS: [(usize, usize); 10] = [(0, 1), (0, 2), (0, 3), (0, 4), (1, 2), (1, 3), (1, 4), (2, 3), (2, 4), (3, 4)];
/// Covariance entries (i <= j) in the PL's readback order.
pub fn entries() -> Vec<(usize, usize)> {
    let mut v = Vec::new();
    for i in 0..M {
        for j in i..M {
            v.push((i, j));
        }
    }
    v
}

/// Steering cross-products b_p(m) = conj(a_i(m)) a_j(m) for the PL's table, Q1.14, one bearing per degree.
pub fn steering_table(arr: &Array, lambda: f64) -> Vec<[u32; 10]> {
    (0..NA)
        .map(|m| {
            let a = arr.steering(m as f64, lambda);
            let mut row = [0u32; 10];
            for (p, &(i, j)) in PAIRS.iter().enumerate() {
                row[p] = q14(a[i].conj() * a[j]);
            }
            row
        })
        .collect()
}

/// Two 64-bit beats per snapshot, as the PL takes them: channels 0-3 in the first, channel 4 in the second.
pub fn pack_beats(iq: &[[i8; 2]; M]) -> [u64; 2] {
    let lane = |k: usize| ((iq[k][0] as u8 as u64) | ((iq[k][1] as u8 as u64) << 8)) as u64;
    let b0 = lane(0) | (lane(1) << 16) | (lane(2) << 32) | (lane(3) << 48);
    let b1 = lane(4);
    [b0, b1]
}

/// Bit-exact model of kria_doa: the covariance after `snapshots`, then the Bartlett scan with `shift`.
pub struct PlModel {
    pub r_re: [i64; 15],
    pub r_im: [i64; 15],
}

impl PlModel {
    pub fn accumulate(w: &[u32; M], snaps: &[[[i8; 2]; M]]) -> PlModel {
        let mut r_re = [0i64; 15];
        let mut r_im = [0i64; 15];
        let ent = entries();
        for s in snaps {
            let mut yr = [0i64; M];
            let mut yi = [0i64; M];
            for k in 0..M {
                let (wr, wi) = (q14_re(w[k]) as i64, q14_im(w[k]) as i64);
                let (xr, xi) = (s[k][0] as i64, s[k][1] as i64);
                yr[k] = (wr * xr - wi * xi) >> 10;
                yi[k] = (wr * xi + wi * xr) >> 10;
            }
            for (e, &(i, j)) in ent.iter().enumerate() {
                r_re[e] += yr[i] * yr[j] + yi[i] * yi[j];
                r_im[e] += yi[i] * yr[j] - yr[i] * yi[j];
            }
        }
        PlModel { r_re, r_im }
    }

    fn sat25(v: i64, sh: u32) -> i64 {
        (v >> sh).clamp(-(1 << 24), (1 << 24) - 1)
    }

    /// Smallest shift that brings R's largest diagonal entry under 2^24.
    pub fn pick_shift(&self) -> u32 {
        let dmax = [0usize, 5, 9, 12, 14].iter().map(|&e| self.r_re[e]).max().unwrap();
        let mut sh = 0;
        while (dmax >> sh) >= (1 << 24) {
            sh += 1;
        }
        sh
    }

    pub fn scan(&self, table: &[[u32; 10]], shift: u32) -> Vec<i32> {
        let pe = [1usize, 2, 3, 4, 6, 7, 8, 10, 11, 13];
        let tr: i64 = [0usize, 5, 9, 12, 14].iter().map(|&e| Self::sat25(self.r_re[e], shift)).sum();
        table
            .iter()
            .map(|row| {
                let mut s = 0i64;
                for p in 0..10 {
                    let rre = Self::sat25(self.r_re[pe[p]], shift);
                    let rim = Self::sat25(self.r_im[pe[p]], shift);
                    s += q14_re(row[p]) as i64 * rre - q14_im(row[p]) as i64 * rim;
                }
                let tot = (s << 1) + (tr << 14);
                (tot >> 14) as i32
            })
            .collect()
    }

    /// R as complex numbers (full Hermitian matrix), for MUSIC.
    pub fn matrix(&self) -> Vec<Vec<C>> {
        let mut r = vec![vec![C::ZERO; M]; M];
        for (e, &(i, j)) in entries().iter().enumerate() {
            let c = C::new(self.r_re[e] as f64, self.r_im[e] as f64);
            r[i][j] = c;
            r[j][i] = c.conj();
        }
        r
    }
}

/// MUSIC pseudo-spectrum (dB, peak at 0) on a one-degree grid, and the number of sources it found.
///
/// Sources are the eigenvalues more than `thresh_db` above the smallest. The noise subspace's projector is formed
/// in the 2M x 2M real form of R, where each complex eigenvector is a pair of real ones.
pub fn music(r: &[Vec<C>], arr: &Array, lambda: f64, thresh_db: f64) -> (Vec<f64>, usize, Vec<f64>) {
    let n = M;
    let mut a = vec![vec![0.0; 2 * n]; 2 * n];
    for i in 0..n {
        for j in 0..n {
            a[i][j] = r[i][j].re;
            a[i][j + n] = -r[i][j].im;
            a[i + n][j] = r[i][j].im;
            a[i + n][j + n] = r[i][j].re;
        }
    }
    let (vals, vecs) = jacobi_sym(&a);
    let eig: Vec<f64> = (0..n).map(|k| vals[2 * k]).collect();
    let lmin = eig[n - 1].max(1e-30);
    let d = eig.iter().filter(|&&l| 10.0 * (l / lmin).log10() > thresh_db).count().clamp(1, n - 1);
    let noise_cols: Vec<usize> = (2 * d..2 * n).collect();
    let mut p = Vec::with_capacity(NA);
    for m in 0..NA {
        let s = arr.steering(m as f64, lambda);
        let ar: Vec<f64> = (0..n).map(|i| s[i].re).chain((0..n).map(|i| s[i].im)).collect();
        let mut den = 0.0;
        for &c in &noise_cols {
            let ip: f64 = (0..2 * n).map(|i| vecs[i][c] * ar[i]).sum();
            den += ip * ip;
        }
        p.push(1.0 / den.max(1e-30));
    }
    let pmax = p.iter().cloned().fold(0.0, f64::max);
    let db = p.iter().map(|v| 10.0 * (v / pmax).log10()).collect();
    (db, d, eig)
}

/// The `count` highest local maxima of a circular spectrum, as (bearing, value), highest first.
pub fn peaks(spec: &[f64], count: usize) -> Vec<(f64, f64)> {
    let n = spec.len();
    let mut pk: Vec<(f64, f64)> = (0..n)
        .filter(|&i| spec[i] >= spec[(i + n - 1) % n] && spec[i] > spec[(i + 1) % n])
        .map(|i| {
            // parabolic interpolation on the three points
            let (a, b, c) = (spec[(i + n - 1) % n], spec[i], spec[(i + 1) % n]);
            let den = a - 2.0 * b + c;
            let off = if den.abs() > 1e-12 { 0.5 * (a - c) / den } else { 0.0 };
            (((i as f64 + off) + n as f64) % n as f64, b)
        })
        .collect();
    pk.sort_by(|x, y| y.1.partial_cmp(&x.1).unwrap());
    pk.truncate(count);
    pk
}

#[cfg(test)]
mod tests {
    use super::*;

    fn lcg(seed: &mut u64) -> f64 {
        *seed = seed.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
        ((*seed >> 11) as f64 / (1u64 << 53) as f64) * 2.0 - 1.0
    }

    #[test]
    fn delays_and_weights_from_a_common_source() {
        let mut sd = 7u64;
        let n = 6000;
        let src: Vec<C> = (0..n + 64).map(|_| C::new(lcg(&mut sd), lcg(&mut sd)).scale(30.0)).collect();
        let lag = [0usize, 3, 17, 9, 30];
        let g = [C::new(1.0, 0.0), C::cis(1.0).scale(0.8), C::cis(-2.0).scale(1.2), C::cis(2.5), C::cis(0.3).scale(0.9)];
        let ch: Vec<Vec<C>> = (0..M).map(|k| (0..n).map(|i| src[i + lag[k]] * g[k]).collect()).collect();
        // x_k[i] = src[i + lag_k] = x_0[i + lag_k]
        let est = estimate_delays(&ch, n - 64, 40);
        assert_eq!(est, lag);
        let st = align_starts(&est);
        let x: Vec<&[C]> = (0..M).map(|k| &ch[k][st[k]..]).collect();
        let w = estimate_weights(&x, n - 64);
        for k in 0..M {
            let e = w[k] * g[k];
            assert!((e - g[0]).abs() < 1e-6, "channel {k}: {:?}", e);
        }
    }

    #[test]
    fn music_finds_two_sources() {
        let lam = 0.672;
        let arr = Array::uca(0.5 * lam / (2.0 * (core::f64::consts::PI / 5.0).sin()));
        let mut sd = 11u64;
        let n = 4000;
        let a1 = arr.steering(117.0, lam);
        let a2 = arr.steering(250.0, lam);
        let mut x = vec![vec![C::ZERO; n]; M];
        for t in 0..n {
            let s1 = C::cis(0.37 * t as f64).scale(10.0);
            let s2 = C::cis(-1.21 * t as f64 + 0.4).scale(5.0);
            for k in 0..M {
                x[k][t] = a1[k] * s1 + a2[k] * s2 + C::new(lcg(&mut sd), lcg(&mut sd));
            }
        }
        let xs: Vec<&[C]> = x.iter().map(|v| v.as_slice()).collect();
        let r = covariance(&xs, n);
        let (p, d, _) = music(&r, &arr, lam, 10.0);
        assert_eq!(d, 2);
        let pk = peaks(&p, 2);
        let mut b: Vec<f64> = pk.iter().map(|q| q.0).collect();
        b.sort_by(|a, b| a.partial_cmp(b).unwrap());
        assert!((b[0] - 117.0).abs() < 1.0 && (b[1] - 250.0).abs() < 1.0, "{:?}", b);
    }

    #[test]
    fn pl_model_bartlett_peaks_at_the_source() {
        let lam = 0.672;
        let arr = Array::uca(0.286);
        let a = arr.steering(40.0, lam);
        let w = [q14(C::ONE); M];
        let snaps: Vec<[[i8; 2]; M]> = (0..2048)
            .map(|t| {
                let s = C::cis(0.11 * t as f64).scale(60.0);
                let mut out = [[0i8; 2]; M];
                for k in 0..M {
                    let v = a[k] * s;
                    out[k] = [v.re.round() as i8, v.im.round() as i8];
                }
                out
            })
            .collect();
        let pl = PlModel::accumulate(&w, &snaps);
        let tab = steering_table(&arr, lam);
        let sh = pl.pick_shift();
        let p = pl.scan(&tab, sh);
        let best = (0..NA).max_by_key(|&m| p[m]).unwrap();
        assert!((best as i32 - 40).abs() <= 1, "peak at {best}");
    }
}
