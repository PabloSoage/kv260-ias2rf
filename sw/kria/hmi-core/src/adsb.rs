//! Stream 0x21 (kria_dsp_out): Mode S extended squitters that passed `kria_adsb_rx`'s CRC, decoded on the A53s.
//!
//! A packet is one frame: word 0 = bits 111..48, word 1 = {bits 47..0, the decoder's SNR estimate}. This module
//! reads DF17/18: identification (type codes 1-4), airborne position with barometric altitude (9-18, CPR) and
//! airborne velocity over ground (19, subtypes 1 and 2), keeps a table of aircraft, and places them against the
//! vehicle's own position (range and bearing). Positions come from a CPR even/odd pair (global decode) or, once
//! an aircraft has one, from a single frame against it (local decode). The encoder is for the simulation and
//! the tests.

use serde::Serialize;
use std::collections::BTreeMap;
use std::f64::consts::PI;

const NZ: f64 = 15.0;
const CHARSET: &[u8; 64] = b"#ABCDEFGHIJKLMNOPQRSTUVWXYZ##### ###############0123456789######";

/// CRC-24 of the first `n` bits of a 112-bit frame held in a u128 (Mode S, polynomial 0xFFF409).
pub fn crc24(frame: u128, nbits: u32) -> u32 {
    let mut r: u32 = 0;
    for k in (112 - nbits..112).rev() {
        let bit = (frame >> k) as u32 & 1;
        let top = (r >> 23) & 1;
        r = (r << 1) & 0xFF_FFFF;
        if (bit ^ top) != 0 {
            r ^= 0xFF_F409;
        }
    }
    r
}

pub fn crc_ok(frame: u128) -> bool {
    crc24(frame, 88) == (frame & 0xFF_FFFF) as u32
}

pub fn from_words(w0: u64, w1: u64) -> (u128, u16) {
    (((w0 as u128) << 48) | ((w1 >> 16) as u128), w1 as u16)
}

pub fn to_words(frame: u128, snr: u16) -> [u64; 2] {
    [(frame >> 48) as u64, ((frame as u64) << 16) | snr as u64]
}

fn me_bits(me: u64, start1: u32, len: u32) -> u64 {
    (me >> (56 - (start1 - 1) - len)) & ((1u64 << len) - 1)
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Message {
    Ident { icao: u32, callsign: [u8; 8] },
    Position { icao: u32, alt_ft: Option<i32>, odd: bool, lat_cpr: u32, lon_cpr: u32 },
    Velocity { icao: u32, speed_kt: f64, track_deg: f64, vrate_fpm: i32 },
    Other { icao: u32, tc: u8 },
}

pub fn decode(frame: u128) -> Option<Message> {
    let df = (frame >> 107) as u8;
    if df != 17 && df != 18 {
        return None;
    }
    let icao = (frame >> 80) as u32 & 0xFF_FFFF;
    let me = (frame >> 24) as u64 & ((1u64 << 56) - 1);
    let tc = me_bits(me, 1, 5) as u8;
    Some(match tc {
        1..=4 => {
            let mut cs = [b' '; 8];
            for (k, c) in cs.iter_mut().enumerate() {
                *c = CHARSET[me_bits(me, 9 + 6 * k as u32, 6) as usize];
            }
            Message::Ident { icao, callsign: cs }
        }
        9..=18 => {
            let a = me_bits(me, 9, 12) as u32;
            let alt_ft = if a & 0x10 != 0 { Some((((a >> 5) << 4) | (a & 0xF)) as i32 * 25 - 1000) } else { None };
            Message::Position {
                icao,
                alt_ft,
                odd: me_bits(me, 22, 1) == 1,
                lat_cpr: me_bits(me, 23, 17) as u32,
                lon_cpr: me_bits(me, 40, 17) as u32,
            }
        }
        19 => {
            let st = me_bits(me, 6, 3);
            if st != 1 && st != 2 {
                return Some(Message::Other { icao, tc });
            }
            let k = if st == 2 { 4.0 } else { 1.0 };
            let vew = (me_bits(me, 15, 10) as f64 - 1.0) * k * if me_bits(me, 14, 1) == 1 { -1.0 } else { 1.0 };
            let vns = (me_bits(me, 26, 10) as f64 - 1.0) * k * if me_bits(me, 25, 1) == 1 { -1.0 } else { 1.0 };
            let vr = (me_bits(me, 38, 9) as i32 - 1) * 64 * if me_bits(me, 37, 1) == 1 { -1 } else { 1 };
            Message::Velocity {
                icao,
                speed_kt: vew.hypot(vns),
                track_deg: vew.atan2(vns).to_degrees().rem_euclid(360.0),
                vrate_fpm: vr,
            }
        }
        _ => Message::Other { icao, tc },
    })
}

/// NL(lat): longitude zones at a latitude (the standard's closed form).
pub fn nl(lat: f64) -> f64 {
    let lat = lat.abs();
    if lat < 1e-9 {
        return 59.0;
    }
    if (lat - 87.0).abs() < 1e-9 {
        return 2.0;
    }
    if lat > 87.0 {
        return 1.0;
    }
    let a = 1.0 - (PI / (2.0 * NZ)).cos();
    let b = (PI / 180.0 * lat).cos().powi(2);
    (2.0 * PI / (1.0 - a / b).acos()).floor()
}

/// Global decode from an even and an odd frame; `odd_newest` picks which one the position is for.
pub fn cpr_global(even: (u32, u32), odd: (u32, u32), odd_newest: bool) -> Option<(f64, f64)> {
    let s = 131072.0;
    let (le, ne) = (even.0 as f64 / s, even.1 as f64 / s);
    let (lo, no) = (odd.0 as f64 / s, odd.1 as f64 / s);
    let j = (59.0 * le - 60.0 * lo + 0.5).floor();
    let mut rle = 6.0 * (j.rem_euclid(60.0) + le);
    let mut rlo = 360.0 / 59.0 * (j.rem_euclid(59.0) + lo);
    if rle >= 270.0 {
        rle -= 360.0;
    }
    if rlo >= 270.0 {
        rlo -= 360.0;
    }
    if nl(rle) != nl(rlo) {
        return None;
    }
    let (lat, ni, x) = if odd_newest { (rlo, (nl(rlo) - 1.0).max(1.0), no) } else { (rle, nl(rle).max(1.0), ne) };
    let m = (ne * (nl(lat) - 1.0) - no * nl(lat) + 0.5).floor();
    let mut lon = 360.0 / ni * (m.rem_euclid(ni) + x);
    if lon >= 180.0 {
        lon -= 360.0;
    }
    Some((lat, lon))
}

/// Local decode of one frame against a reference within 180 NM.
pub fn cpr_local(f: (u32, u32), odd: bool, reference: (f64, f64)) -> (f64, f64) {
    let s = 131072.0;
    let i = if odd { 1.0 } else { 0.0 };
    let dlat = 360.0 / (4.0 * NZ - i);
    let y = f.0 as f64 / s;
    let j = (reference.0 / dlat).floor() + (0.5 + reference.0.rem_euclid(dlat) / dlat - y).floor();
    let lat = dlat * (j + y);
    let dlon = 360.0 / (nl(lat) - i).max(1.0);
    let x = f.1 as f64 / s;
    let m = (reference.1 / dlon).floor() + (0.5 + reference.1.rem_euclid(dlon) / dlon - x).floor();
    (lat, dlon * (m + x))
}

pub fn cpr_encode(lat: f64, lon: f64, odd: bool) -> (u32, u32) {
    let s = 131072.0;
    let i = if odd { 1.0 } else { 0.0 };
    let dlat = 360.0 / (4.0 * NZ - i);
    let yz = (s * lat.rem_euclid(dlat) / dlat + 0.5).floor();
    let rlat = dlat * (yz / s + (lat / dlat).floor());
    let dlon = 360.0 / (nl(rlat) - i).max(1.0);
    let xz = (s * lon.rem_euclid(dlon) / dlon + 0.5).floor();
    ((yz as u32) & 0x1FFFF, (xz as u32) & 0x1FFFF)
}

fn frame_from_me(icao: u32, me: u64) -> u128 {
    let head = (17u128 << 107) | (5u128 << 104) | ((icao as u128) << 80) | ((me as u128) << 24);
    head | crc24(head, 88) as u128
}

pub fn encode_ident(icao: u32, callsign: &str) -> u128 {
    let mut me: u64 = 4 << 51;
    for (k, ch) in format!("{callsign:<8}").bytes().take(8).enumerate() {
        let c = CHARSET.iter().position(|&x| x == ch.to_ascii_uppercase()).unwrap_or(32) as u64;
        me |= c << (42 - 6 * k);
    }
    frame_from_me(icao, me)
}

pub fn encode_position(icao: u32, lat: f64, lon: f64, alt_ft: i32, odd: bool) -> u128 {
    let n = ((alt_ft + 1000) / 25).clamp(0, 2047) as u64;
    let a = ((n >> 4) << 5) | 0x10 | (n & 0xF);
    let (yl, xl) = cpr_encode(lat, lon, odd);
    let me = (11u64 << 51) | (a << 36) | ((odd as u64) << 34) | ((yl as u64) << 17) | xl as u64;
    frame_from_me(icao, me)
}

pub fn encode_velocity(icao: u32, speed_kt: f64, track_deg: f64, vrate_fpm: i32) -> u128 {
    let t = track_deg.to_radians();
    let (ve, vn) = (speed_kt * t.sin(), speed_kt * t.cos());
    let f = |v: f64| ((v < 0.0) as u64, (v.abs().round() as u64 + 1).min(1023));
    let (se, me_) = f(ve);
    let (sn, mn) = f(vn);
    let vr = ((vrate_fpm.unsigned_abs() as u64 + 32) / 64 + 1).min(511);
    let me = (19u64 << 51) | (1u64 << 48) | (se << 42) | (me_ << 32) | (sn << 31) | (mn << 21)
        | (((vrate_fpm < 0) as u64) << 19) | (vr << 10);
    frame_from_me(icao, me)
}

#[derive(Clone, Debug, Default, Serialize)]
pub struct Aircraft {
    pub icao: String,
    pub callsign: String,
    pub alt_ft: Option<i32>,
    pub lat: Option<f64>,
    pub lon: Option<f64>,
    pub speed_kt: Option<f64>,
    pub track_deg: Option<f64>,
    pub vrate_fpm: Option<i32>,
    pub range_km: Option<f64>,
    pub bearing_deg: Option<f64>,
    pub last_seen_s: f64,
    pub frames: u32,
    #[serde(skip)]
    even: Option<((u32, u32), f64)>,
    #[serde(skip)]
    odd: Option<((u32, u32), f64)>,
}

#[derive(Default)]
pub struct Table {
    pub aircraft: BTreeMap<u32, Aircraft>,
    pub frames: u64,
    pub own: Option<(f64, f64)>,
}

/// Great-circle range (km) and initial bearing (degrees from north) from `a` to `b`.
pub fn range_bearing(a: (f64, f64), b: (f64, f64)) -> (f64, f64) {
    let (p1, p2) = (a.0.to_radians(), b.0.to_radians());
    let dl = (b.1 - a.1).to_radians();
    let h = ((p2 - p1) / 2.0).sin().powi(2) + p1.cos() * p2.cos() * (dl / 2.0).sin().powi(2);
    let d = 2.0 * 6371.0 * h.sqrt().asin();
    let y = dl.sin() * p2.cos();
    let x = p1.cos() * p2.sin() - p1.sin() * p2.cos() * dl.cos();
    (d, y.atan2(x).to_degrees().rem_euclid(360.0))
}

impl Table {
    pub fn push(&mut self, frame: u128, now_s: f64) {
        let Some(m) = decode(frame) else { return };
        self.frames += 1;
        let icao = match m {
            Message::Ident { icao, .. }
            | Message::Position { icao, .. }
            | Message::Velocity { icao, .. }
            | Message::Other { icao, .. } => icao,
        };
        let own = self.own;
        let a = self.aircraft.entry(icao).or_insert_with(|| Aircraft { icao: format!("{icao:06X}"), ..Default::default() });
        a.frames += 1;
        a.last_seen_s = now_s;
        match m {
            Message::Ident { callsign, .. } => {
                a.callsign = String::from_utf8_lossy(&callsign).replace('#', "").trim().to_string();
            }
            Message::Velocity { speed_kt, track_deg, vrate_fpm, .. } => {
                a.speed_kt = Some(speed_kt);
                a.track_deg = Some(track_deg);
                a.vrate_fpm = Some(vrate_fpm);
            }
            Message::Position { alt_ft, odd, lat_cpr, lon_cpr, .. } => {
                a.alt_ft = alt_ft;
                let f = (lat_cpr, lon_cpr);
                if odd {
                    a.odd = Some((f, now_s));
                } else {
                    a.even = Some((f, now_s));
                }
                let pos = match (a.lat, a.lon) {
                    (Some(la), Some(lo)) => Some(cpr_local(f, odd, (la, lo))),
                    _ => match (a.even, a.odd) {
                        (Some((e, te)), Some((o, to))) if (te - to).abs() < 10.0 => cpr_global(e, o, to >= te),
                        _ => None,
                    },
                };
                if let Some((la, lo)) = pos {
                    a.lat = Some(la);
                    a.lon = Some(lo);
                }
            }
            Message::Other { .. } => {}
        }
        if let (Some(o), Some(la), Some(lo)) = (own, a.lat, a.lon) {
            let (r, b) = range_bearing(o, (la, lo));
            a.range_km = Some(r);
            a.bearing_deg = Some(b);
        }
    }

    /// Drops aircraft not heard for `age_s`.
    pub fn expire(&mut self, now_s: f64, age_s: f64) {
        self.aircraft.retain(|_, a| now_s - a.last_seen_s <= age_s);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn hex(s: &str) -> u128 {
        u128::from_str_radix(s, 16).unwrap()
    }

    #[test]
    fn published_identification() {
        let f = hex("8D4840D6202CC371C32CE0576098");
        assert!(crc_ok(f));
        match decode(f).unwrap() {
            Message::Ident { icao, callsign } => {
                assert_eq!(icao, 0x4840D6);
                assert_eq!(&callsign, b"KLM1023 ");
            }
            m => panic!("{m:?}"),
        }
    }

    #[test]
    fn published_position_pair() {
        let even = hex("8D40621D58C382D690C8AC2863A7");
        let odd = hex("8D40621D58C386435CC412692AD6");
        assert!(crc_ok(even) && crc_ok(odd));
        let mut t = Table::default();
        t.push(odd, 0.0);
        t.push(even, 2.0);
        let a = &t.aircraft[&0x40621D];
        assert_eq!(a.alt_ft, Some(38000));
        assert!((a.lat.unwrap() - 52.2572).abs() < 1e-3, "{:?}", a.lat);
        assert!((a.lon.unwrap() - 3.91937).abs() < 1e-3, "{:?}", a.lon);
    }

    #[test]
    fn published_velocity() {
        match decode(hex("8D485020994409940838175B284F")).unwrap() {
            Message::Velocity { speed_kt, track_deg, vrate_fpm, .. } => {
                assert!((speed_kt - 159.2).abs() < 0.1);
                assert!((track_deg - 182.88).abs() < 0.05);
                assert_eq!(vrate_fpm, -832);
            }
            m => panic!("{m:?}"),
        }
    }

    #[test]
    fn encoder_round_trips_through_the_table() {
        let icao = 0x3C6586;
        let mut t = Table { own: Some((43.37, -8.40)), ..Default::default() };
        t.push(encode_ident(icao, "IBE3213"), 0.0);
        t.push(encode_position(icao, 43.52, -8.10, 23000, false), 0.5);
        t.push(encode_position(icao, 43.52, -8.10, 23000, true), 1.0);
        t.push(encode_velocity(icao, 412.0, 63.0, -1280), 1.2);
        t.push(encode_position(icao, 43.55, -8.02, 22800, false), 6.0); // local decode from here
        let a = &t.aircraft[&icao];
        assert_eq!(a.callsign, "IBE3213");
        assert!((a.lat.unwrap() - 43.55).abs() < 1e-3 && (a.lon.unwrap() + 8.02).abs() < 1e-3);
        assert_eq!(a.alt_ft, Some(22800));
        assert!((a.speed_kt.unwrap() - 412.0).abs() < 1.5 && (a.track_deg.unwrap() - 63.0).abs() < 0.5);
        assert_eq!(a.vrate_fpm, Some(-1280));
        let r = a.range_km.unwrap();
        assert!(r > 30.0 && r < 40.0, "{r}");
    }
}
