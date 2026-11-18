//! Streams 0x22 and 0x23 (kria_dsp_out): the CPI's CFAR detections and, every 2^n CPIs, the whole 64 x 16 map.
//!
//! Detection word: {power[31:0], cpi[15:0], 4'd0, dbin[3:0], 2'd0, rbin[5:0]}; the packet ends with the summary
//! {0xFF, cpi[15:0], detections[15:0], dropped[7:0], 0}. Map word: two cells, the first in [31:0], each
//! {det, dbin[3:0], rbin[5:0], exponent[4:0], mantissa[15:0]}, power about 1.mantissa x 2^exponent.
//! Bins are converted to target coordinates as `kria_core::radar` does: the DDC delivers the conjugate spectrum,
//! so map cell (r, d) is a target at range bin (64 - r) mod 64 and Doppler bin (16 - d) mod 16, signed.

use kria_core::radar::{Config, DOPPLER_M, RANGE_N};
use serde::Serialize;

#[derive(Clone, Copy, Debug, PartialEq, Serialize)]
pub struct Detection {
    pub range_bin: u8,
    pub doppler_bin: i8,
    pub range_m: f64,
    pub speed_mps: f64,
    pub power_db: f64,
}

#[derive(Clone, Debug, Default, PartialEq, Serialize)]
pub struct Cpi {
    pub cpi: u16,
    pub detections: Vec<Detection>,
    pub total: u16,
    pub dropped: u8,
}

pub fn target_bins(rbin: u8, dbin: u8) -> (u8, i8) {
    let r = (RANGE_N - rbin % RANGE_N) % RANGE_N;
    let d = (DOPPLER_M - dbin % DOPPLER_M) % DOPPLER_M;
    (r, if d >= DOPPLER_M / 2 { d as i8 - DOPPLER_M as i8 } else { d as i8 })
}

fn db(p: f64) -> f64 {
    10.0 * p.max(1.0).log10()
}

pub fn decode_cpi(words: &[u64], cfg: &Config) -> Option<Cpi> {
    let (&sum, dets) = words.split_last()?;
    if sum >> 56 != 0xFF {
        return None;
    }
    let detections = dets
        .iter()
        .map(|&w| {
            let (r, d) = target_bins((w & 0x3F) as u8, ((w >> 8) & 0xF) as u8);
            Detection {
                range_bin: r,
                doppler_bin: d,
                range_m: r as f64 * cfg.range_bin_cm as f64 / 100.0,
                speed_mps: d as f64 * cfg.doppler_bin_cms as f64 / 100.0,
                power_db: db((w >> 32) as f64),
            }
        })
        .collect();
    Some(Cpi { cpi: (sum >> 40) as u16, detections, total: (sum >> 24) as u16, dropped: (sum >> 16) as u8 })
}

/// The map in target coordinates: `power_db[range][doppler + 8]` and the CFAR flags, range 0..63, Doppler -8..7.
#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct Map {
    pub power_db: Vec<Vec<f32>>,
    pub det: Vec<Vec<bool>>,
}

pub fn decode_map(words: &[u64]) -> Option<Map> {
    if words.len() != 512 {
        return None;
    }
    let mut power_db = vec![vec![0f32; 16]; 64];
    let mut det = vec![vec![false; 16]; 64];
    for &w in words {
        for c in [w as u32, (w >> 32) as u32] {
            let e = (c >> 16) & 0x1F;
            let m = c & 0xFFFF;
            let p = (1.0 + m as f64 / 65536.0) * 2f64.powi(e as i32);
            let (r, d) = target_bins(((c >> 21) & 0x3F) as u8, ((c >> 27) & 0xF) as u8);
            power_db[r as usize][(d + 8) as usize] = db(p) as f32;
            det[r as usize][(d + 8) as usize] = c >> 31 != 0;
        }
    }
    Some(Map { power_db, det })
}

/// The PL's map cell for a power and flags (the simulation's encoder, kria_dsp_out's `map_word`).
pub fn map_cell(det: bool, rbin: u8, dbin: u8, p: u32) -> u32 {
    let e = 31 - p.max(1).leading_zeros();
    let sh = if p == 0 { 0 } else { p << (31 - e) };
    (det as u32) << 31 | (dbin as u32 & 0xF) << 27 | (rbin as u32 & 0x3F) << 21 | e << 16 | (sh >> 15) & 0xFFFF
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn cpi_packet_in_target_coordinates() {
        let cfg = Config::default();
        // a cell at map (52, 13): target range bin 12, Doppler -3 (conjugate spectrum)
        let det = 40000u64 << 32 | 7 << 16 | 13 << 8 | 52;
        let sum = 0xFFu64 << 56 | 7 << 40 | 1 << 24;
        let c = decode_cpi(&[det, sum], &cfg).unwrap();
        assert_eq!(c.cpi, 7);
        assert_eq!(c.total, 1);
        assert_eq!((c.detections[0].range_bin, c.detections[0].doppler_bin), (12, 3));
        assert!((c.detections[0].range_m - 18.0).abs() < 1e-9);
        assert!((c.detections[0].power_db - 46.02).abs() < 0.01);
    }

    #[test]
    fn map_cells_round_trip_the_pl_encoding() {
        let mut words = Vec::new();
        for k in 0..512u32 {
            let a = map_cell(k == 3, ((2 * k) % 64) as u8, ((2 * k) / 64) as u8, 1000 + 37 * k);
            let b = map_cell(false, ((2 * k + 1) % 64) as u8, ((2 * k + 1) / 64) as u8, 90_000 * (k + 1));
            words.push(a as u64 | (b as u64) << 32);
        }
        let m = decode_map(&words).unwrap();
        // cell index 6 = map (6, 0) -> target (58, 0); power 1000 + 37 * 3
        assert!((m.power_db[58][8] as f64 - 10.0 * (1111f64).log10()).abs() < 0.01);
        assert!(m.det[58][8]);
    }
}
