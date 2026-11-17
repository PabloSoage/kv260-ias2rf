//! A minimal complex type, enough for the receivers' arithmetic (no dependency).

use core::ops::{Add, AddAssign, Div, Mul, Neg, Sub};

#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub struct C {
    pub re: f64,
    pub im: f64,
}

impl C {
    pub const ZERO: C = C { re: 0.0, im: 0.0 };
    pub const ONE: C = C { re: 1.0, im: 0.0 };
    pub fn new(re: f64, im: f64) -> C {
        C { re, im }
    }
    pub fn cis(ph: f64) -> C {
        C { re: ph.cos(), im: ph.sin() }
    }
    pub fn conj(self) -> C {
        C { re: self.re, im: -self.im }
    }
    pub fn norm2(self) -> f64 {
        self.re * self.re + self.im * self.im
    }
    pub fn abs(self) -> f64 {
        self.norm2().sqrt()
    }
    pub fn arg(self) -> f64 {
        self.im.atan2(self.re)
    }
    pub fn scale(self, k: f64) -> C {
        C { re: self.re * k, im: self.im * k }
    }
}

impl Add for C {
    type Output = C;
    fn add(self, o: C) -> C {
        C { re: self.re + o.re, im: self.im + o.im }
    }
}
impl AddAssign for C {
    fn add_assign(&mut self, o: C) {
        self.re += o.re;
        self.im += o.im;
    }
}
impl Sub for C {
    type Output = C;
    fn sub(self, o: C) -> C {
        C { re: self.re - o.re, im: self.im - o.im }
    }
}
impl Neg for C {
    type Output = C;
    fn neg(self) -> C {
        C { re: -self.re, im: -self.im }
    }
}
impl Mul for C {
    type Output = C;
    fn mul(self, o: C) -> C {
        C { re: self.re * o.re - self.im * o.im, im: self.re * o.im + self.im * o.re }
    }
}
impl Div for C {
    type Output = C;
    fn div(self, o: C) -> C {
        let d = o.norm2();
        C { re: (self.re * o.re + self.im * o.im) / d, im: (self.im * o.re - self.re * o.im) / d }
    }
}

/// Eigen-decomposition of a real symmetric matrix (cyclic Jacobi). Returns the eigenvalues in descending order
/// and the eigenvectors as the columns of `v` in the same order.
pub fn jacobi_sym(a_in: &[Vec<f64>]) -> (Vec<f64>, Vec<Vec<f64>>) {
    let n = a_in.len();
    let mut a: Vec<Vec<f64>> = a_in.to_vec();
    let mut v = vec![vec![0.0; n]; n];
    for (i, row) in v.iter_mut().enumerate() {
        row[i] = 1.0;
    }
    for _sweep in 0..100 {
        let mut off = 0.0;
        for i in 0..n {
            for j in (i + 1)..n {
                off += a[i][j] * a[i][j];
            }
        }
        if off < 1e-24 * (1.0 + (0..n).map(|i| a[i][i] * a[i][i]).sum::<f64>()) {
            break;
        }
        for p in 0..n {
            for q in (p + 1)..n {
                if a[p][q].abs() < 1e-300 {
                    continue;
                }
                let theta = (a[q][q] - a[p][p]) / (2.0 * a[p][q]);
                let t = theta.signum() / (theta.abs() + (theta * theta + 1.0).sqrt());
                let t = if theta == 0.0 { 1.0 } else { t };
                let c = 1.0 / (t * t + 1.0).sqrt();
                let s = t * c;
                for k in 0..n {
                    let akp = a[k][p];
                    let akq = a[k][q];
                    a[k][p] = c * akp - s * akq;
                    a[k][q] = s * akp + c * akq;
                }
                for k in 0..n {
                    let apk = a[p][k];
                    let aqk = a[q][k];
                    a[p][k] = c * apk - s * aqk;
                    a[q][k] = s * apk + c * aqk;
                }
                for row in v.iter_mut() {
                    let vkp = row[p];
                    let vkq = row[q];
                    row[p] = c * vkp - s * vkq;
                    row[q] = s * vkp + c * vkq;
                }
            }
        }
    }
    let mut idx: Vec<usize> = (0..n).collect();
    idx.sort_by(|&x, &y| a[y][y].partial_cmp(&a[x][x]).unwrap());
    let vals = idx.iter().map(|&i| a[i][i]).collect();
    let vecs = (0..n).map(|r| idx.iter().map(|&i| v[r][i]).collect()).collect();
    (vals, vecs)
}

/// Eigen-decomposition of an n x n Hermitian matrix through its 2n x 2n real form [[Re, -Im], [Im, Re]]. Each
/// eigenvalue appears twice there; this returns the n distinct ones, descending, with one complex eigenvector each.
pub fn eig_hermitian(r: &[Vec<C>]) -> (Vec<f64>, Vec<Vec<C>>) {
    let n = r.len();
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
    // take every other one of the paired eigenvalues; rebuild a complex vector from each real one
    let mut out_v = Vec::new();
    let mut out_l = Vec::new();
    let mut k = 0;
    while out_l.len() < n && k < 2 * n {
        let col: Vec<C> = (0..n).map(|i| C::new(vecs[i][k], vecs[i + n][k])).collect();
        // skip a vector that is j times one already taken (the pair's twin)
        let dup = out_v.iter().any(|u: &Vec<C>| {
            let ip: C = u.iter().zip(&col).fold(C::ZERO, |s, (a, b)| s + a.conj() * *b);
            ip.abs() > 0.5
        });
        if !dup {
            let nrm = col.iter().map(|c| c.norm2()).sum::<f64>().sqrt();
            out_v.push(col.iter().map(|c| c.scale(1.0 / nrm)).collect());
            out_l.push(vals[k]);
        }
        k += 1;
    }
    (out_l, out_v)
}
