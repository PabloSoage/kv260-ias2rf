//! The wideband view (HMI.md §3.4): FFT of a link stream's I/Q on the A53s, averaged, in dBFS, and a waterfall.
//!
//! The streams are 16-bit I/Q (`frame::iq_samples`). Each frame of `n` samples is windowed (Hann), transformed
//! (radix-2, in place), turned into power relative to a full-scale tone, shifted so DC is in the middle and
//! averaged exponentially. Every `rows_every` frames the average is reduced to `width` columns (the maximum of
//! the bins in each) and pushed as a waterfall row; the newest row is first.

use std::f64::consts::PI;

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct C {
    pub re: f64,
    pub im: f64,
}

pub fn fft(x: &mut [C]) {
    let n = x.len();
    assert!(n.is_power_of_two());
    let mut j = 0;
    for i in 1..n {
        let mut bit = n >> 1;
        while j & bit != 0 {
            j ^= bit;
            bit >>= 1;
        }
        j |= bit;
        if i < j {
            x.swap(i, j);
        }
    }
    let mut len = 2;
    while len <= n {
        let w = -2.0 * PI / len as f64;
        for s in (0..n).step_by(len) {
            for k in 0..len / 2 {
                let (sn, cs) = (w * k as f64).sin_cos();
                let a = x[s + k];
                let b = x[s + k + len / 2];
                let t = C { re: b.re * cs - b.im * sn, im: b.re * sn + b.im * cs };
                x[s + k] = C { re: a.re + t.re, im: a.im + t.im };
                x[s + k + len / 2] = C { re: a.re - t.re, im: a.im - t.im };
            }
        }
        len <<= 1;
    }
}

pub struct Spectrum {
    pub n: usize,
    pub width: usize,
    pub rows: usize,
    pub rows_every: usize,
    pub alpha: f64,
    win: Vec<f64>,
    acc: Vec<(i16, i16)>,
    avg: Vec<f64>,
    frames: usize,
    pub waterfall: std::collections::VecDeque<Vec<f32>>,
}

impl Spectrum {
    pub fn new(n: usize, width: usize, rows: usize) -> Self {
        let win: Vec<f64> = (0..n).map(|k| 0.5 - 0.5 * (2.0 * PI * k as f64 / n as f64).cos()).collect();
        Self {
            n,
            width,
            rows,
            rows_every: 4,
            alpha: 0.3,
            win,
            acc: Vec::with_capacity(n),
            avg: vec![-140.0; n],
            frames: 0,
            waterfall: Default::default(),
        }
    }

    /// Full-scale tone through the Hann window: (32767 * n / 2)^2.
    fn ref_power(&self) -> f64 {
        (32767.0 * self.n as f64 * 0.5).powi(2)
    }

    pub fn push(&mut self, samples: &[(i16, i16)]) {
        for &s in samples {
            self.acc.push(s);
            if self.acc.len() == self.n {
                self.frame();
                self.acc.clear();
            }
        }
    }

    fn frame(&mut self) {
        let mut x: Vec<C> = self
            .acc
            .iter()
            .zip(&self.win)
            .map(|(&(i, q), w)| C { re: i as f64 * w, im: q as f64 * w })
            .collect();
        fft(&mut x);
        let rp = self.ref_power();
        let n = self.n;
        for k in 0..n {
            let b = x[(k + n / 2) % n];
            let p = 10.0 * ((b.re * b.re + b.im * b.im) / rp).max(1e-16).log10();
            self.avg[k] = if self.frames == 0 { p } else { self.avg[k] + self.alpha * (p - self.avg[k]) };
        }
        self.frames += 1;
        if self.frames % self.rows_every == 0 {
            let row = self.display(self.width);
            self.waterfall.push_front(row);
            self.waterfall.truncate(self.rows);
        }
    }

    /// The averaged spectrum in `width` columns, the maximum of the bins in each.
    pub fn display(&self, width: usize) -> Vec<f32> {
        let per = (self.n as f64 / width as f64).max(1.0);
        (0..width)
            .map(|c| {
                let a = (c as f64 * per) as usize;
                let b = (((c + 1) as f64 * per) as usize).clamp(a + 1, self.n);
                self.avg[a..b].iter().cloned().fold(f64::MIN, f64::max) as f32
            })
            .collect()
    }

    pub fn frames(&self) -> usize {
        self.frames
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_tone_lands_in_its_bin_at_its_level() {
        let fs = 25e6;
        let n = 1024;
        let f = fs * 100.0 / n as f64; // bin 100 above DC
        let amp = 32767.0 * 0.1; // -20 dBFS
        let s: Vec<(i16, i16)> = (0..8 * n)
            .map(|k| {
                let ph = 2.0 * PI * f * k as f64 / fs;
                ((amp * ph.cos()) as i16, (amp * ph.sin()) as i16)
            })
            .collect();
        let mut sp = Spectrum::new(n, n, 8);
        sp.push(&s);
        let d = sp.display(n);
        let (peak, lvl) = d.iter().enumerate().fold((0, f32::MIN), |b, (k, &v)| if v > b.1 { (k, v) } else { b });
        assert_eq!(peak, n / 2 + 100);
        assert!((lvl + 20.0).abs() < 0.2, "{lvl}");
        assert_eq!(sp.waterfall.len(), 2);
    }
}
