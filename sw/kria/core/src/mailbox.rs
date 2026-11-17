//! The block Linux and R5F core 0 share.
//!
//! 128 bytes at the start of a 4 KiB `reserved-memory` region (`rpu_mailbox`
//! in `sw/ias2rf_pl.dtsi`, physical [`BASE`]), non-cacheable on the R5F side.
//! Each half has one writer: Linux writes [`ToR5f`] at offset 0, the R5F writes
//! [`FromR5f`] at offset 64. A sequence word makes each half a seqlock: the
//! writer makes it odd, writes, makes it even; a reader that sees it odd, or
//! different before and after, reads again. The codec here turns the structs
//! into bytes and back; the actual memory access belongs to each side
//! (`/dev/mem` on Linux, volatile accesses on the R5F).
//!
//! Times are PL ticks (`kria_pps` `NOW`), the clock both sides can read.

use crate::interlock::{Reason, Source, Speed};
use crate::pps::State;

/// Physical address of the region.
pub const BASE: u64 = 0x3EE0_0000;
pub const TO_R5F: usize = 0;
pub const FROM_R5F: usize = 64;
pub const HALF: usize = 64;
pub const MAGIC: u32 = u32::from_le_bytes(*b"KMB1");
const NONE: u32 = u32::MAX;

#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub struct ToR5f {
    pub ecu: Option<Speed>,
    pub gps: Option<Speed>,
    pub licensed: bool,
    pub request: bool,
    /// Last time Linux wrote, in PL ticks.
    pub heartbeat: u64,
}

impl PartialEq for Speed {
    fn eq(&self, o: &Self) -> bool {
        self.centi_kmh == o.centi_kmh && self.stamp == o.stamp
    }
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct FromR5f {
    pub pps: State,
    pub reason: Reason,
    pub source: Source,
    pub transmit: bool,
    pub freq_error_ppb: i64,
    pub phase_ticks: i64,
    pub pps_accepted: u32,
    pub pps_rejected: u32,
    pub heartbeat: u64,
}

fn put32(b: &mut [u8], at: usize, v: u32) {
    b[at..at + 4].copy_from_slice(&v.to_le_bytes());
}
fn put64(b: &mut [u8], at: usize, v: u64) {
    b[at..at + 8].copy_from_slice(&v.to_le_bytes());
}
fn get32(b: &[u8], at: usize) -> u32 {
    u32::from_le_bytes(b[at..at + 4].try_into().unwrap())
}
fn get64(b: &[u8], at: usize) -> u64 {
    u64::from_le_bytes(b[at..at + 8].try_into().unwrap())
}

/// Word 1 of either half is the sequence; even means stable.
pub const SEQ: usize = 4;

pub fn encode_to_r5f(m: &ToR5f, seq: u32) -> [u8; HALF] {
    let mut b = [0u8; HALF];
    put32(&mut b, 0, MAGIC);
    put32(&mut b, SEQ, seq);
    put32(&mut b, 0x08, m.ecu.map_or(NONE, |s| s.centi_kmh));
    put64(&mut b, 0x10, m.ecu.map_or(0, |s| s.stamp));
    put32(&mut b, 0x18, m.gps.map_or(NONE, |s| s.centi_kmh));
    put32(&mut b, 0x1C, (m.licensed as u32) | ((m.request as u32) << 1));
    put64(&mut b, 0x20, m.gps.map_or(0, |s| s.stamp));
    put64(&mut b, 0x28, m.heartbeat);
    b
}

pub fn decode_to_r5f(b: &[u8; HALF]) -> Option<ToR5f> {
    if get32(b, 0) != MAGIC || get32(b, SEQ) & 1 == 1 {
        return None;
    }
    let speed = |v: u32, at: usize| (v != NONE).then(|| Speed { centi_kmh: v, stamp: get64(b, at) });
    let flags = get32(b, 0x1C);
    Some(ToR5f {
        ecu: speed(get32(b, 0x08), 0x10),
        gps: speed(get32(b, 0x18), 0x20),
        licensed: flags & 1 != 0,
        request: flags & 2 != 0,
        heartbeat: get64(b, 0x28),
    })
}

pub fn encode_from_r5f(m: &FromR5f, seq: u32) -> [u8; HALF] {
    let mut b = [0u8; HALF];
    put32(&mut b, 0, MAGIC);
    put32(&mut b, SEQ, seq);
    b[0x08] = match m.pps {
        State::Acquiring => 0,
        State::Locked => 1,
        State::Holdover => 2,
    };
    b[0x09] = m.reason as u8;
    b[0x0A] = m.source as u8;
    b[0x0B] = m.transmit as u8;
    put64(&mut b, 0x10, m.freq_error_ppb as u64);
    put64(&mut b, 0x18, m.phase_ticks as u64);
    put32(&mut b, 0x20, m.pps_accepted);
    put32(&mut b, 0x24, m.pps_rejected);
    put64(&mut b, 0x28, m.heartbeat);
    b
}

pub fn decode_from_r5f(b: &[u8; HALF]) -> Option<FromR5f> {
    if get32(b, 0) != MAGIC || get32(b, SEQ) & 1 == 1 {
        return None;
    }
    let pps = match b[0x08] {
        0 => State::Acquiring,
        1 => State::Locked,
        2 => State::Holdover,
        _ => return None,
    };
    let reason = match b[0x09] {
        0 => Reason::Keyed,
        1 => Reason::Idle,
        2 => Reason::NoLicence,
        3 => Reason::Moving,
        4 => Reason::SpeedUnknown,
        5 => Reason::Settling,
        6 => Reason::TimedOut,
        _ => return None,
    };
    let source = match b[0x0A] {
        0 => Source::None,
        1 => Source::Ecu,
        2 => Source::Gps,
        _ => return None,
    };
    Some(FromR5f {
        pps,
        reason,
        source,
        transmit: b[0x0B] != 0,
        freq_error_ppb: get64(b, 0x10) as i64,
        phase_ticks: get64(b, 0x18) as i64,
        pps_accepted: get32(b, 0x20),
        pps_rejected: get32(b, 0x24),
        heartbeat: get64(b, 0x28),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn round_trip_and_seqlock() {
        let m = ToR5f {
            ecu: Some(Speed { centi_kmh: 3800, stamp: 123 }),
            gps: None,
            licensed: true,
            request: false,
            heartbeat: 99,
        };
        assert_eq!(decode_to_r5f(&encode_to_r5f(&m, 2)), Some(m));
        assert_eq!(decode_to_r5f(&encode_to_r5f(&m, 3)), None, "odd sequence: being written");
        let f = FromR5f {
            pps: State::Holdover,
            reason: Reason::Settling,
            source: Source::Gps,
            transmit: false,
            freq_error_ppb: -61_000,
            phase_ticks: -3,
            pps_accepted: 10,
            pps_rejected: 1,
            heartbeat: 7,
        };
        assert_eq!(decode_from_r5f(&encode_from_r5f(&f, 8)), Some(f));
        let mut junk = [0u8; HALF];
        junk[0] = 1;
        assert_eq!(decode_from_r5f(&junk), None);
    }
}
