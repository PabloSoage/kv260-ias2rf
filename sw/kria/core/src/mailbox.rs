//! The blocks Linux and the two R5F cores share.
//!
//! A 64 KiB `reserved-memory` region (`rpu_mailbox` in `sw/ias2rf_pl.dtsi`,
//! physical [`BASE`]), uncached on every side:
//!
//! | Offset | Block | Writer |
//! |---|---|---|
//! | `0x000` | [`ToR5f`]: speeds, licence, transmit request | Linux |
//! | `0x040` | [`FromR5f`]: PPS, interlock, IAS1 link | core 0 |
//! | `0x080` | [`Core1Status`]: radar scan and grid | core 1 |
//! | `0x100` | [`Core1Config`]: scan, beams, grid cadence | Linux |
//! | `0x1000` | the grid command ring ([`crate::ring`]) | both, one word each |
//!
//! Each block has one writer. A sequence word (word 1) makes it a seqlock: the
//! writer makes it odd, writes, makes it even; a reader that sees it odd, or
//! different before and after, reads again. The codec here turns the structs
//! into bytes and back; the actual memory access belongs to each side
//! (`/dev/mem` on Linux, volatile accesses on the R5F).
//!
//! Times are PL ticks (`kria_pps` `NOW`), the clock all three can read.

use crate::interlock::{Reason, Source, Speed};
use crate::link::Health;
use crate::pps::State;

/// Physical address of the region.
pub const BASE: u64 = 0x3EE0_0000;
pub const TO_R5F: usize = 0;
pub const FROM_R5F: usize = 64;
pub const HALF: usize = 64;
pub const CORE1_STATUS: usize = 0x80;
pub const CORE1_CONFIG: usize = 0x100;
pub const CONFIG_LEN: usize = 128;
/// The region's size in the device tree.
pub const REGION: usize = 0x10000;
/// Two grid frames after the region, written by `axi_dma_1`.
pub const FRAMES: u64 = BASE + REGION as u64;
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
    pub link: Health,
    pub link_retrains: u32,
    pub link_crc_per_s: u32,
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
    b[0x0C] = m.link as u8;
    put32(&mut b, 0x30, m.link_retrains);
    put32(&mut b, 0x34, m.link_crc_per_s);
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
    let link = match b[0x0C] {
        0 => Health::Unknown,
        1 => Health::Up,
        2 => Health::Errors,
        3 => Health::Down,
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
        link,
        link_retrains: get32(b, 0x30),
        link_crc_per_s: get32(b, 0x34),
    })
}

/// What Linux tells core 1: the scan, the beams' azimuths and the grid's
/// cadence. Core 1 rereads it when `seq` changes.
#[derive(Clone, Copy, Debug)]
pub struct Core1Config {
    /// Run the radar scan (strobes and detections).
    pub scan: bool,
    /// Feed detections and the ring into the grid, decay and dump it.
    pub grid: bool,
    pub radar: crate::radar::Config,
    /// Decay pass and dump every this many milliseconds; 0: never (Linux asks
    /// through the ring instead).
    pub frame_ms: u32,
    pub cell_cm: u32,
    /// The 10.5 GHz array on the vehicle.
    pub mount: crate::bev::Mount,
    pub heartbeat: u64,
}

impl Default for Core1Config {
    fn default() -> Self {
        Self {
            scan: false,
            grid: false,
            radar: crate::radar::Config::default(),
            frame_ms: 100,
            cell_cm: 50,
            mount: crate::bev::Mount { x_cm: 380, y_cm: 0, yaw_cdeg: 0 },
            heartbeat: 0,
        }
    }
}

pub fn encode_core1_config(m: &Core1Config, seq: u32) -> [u8; CONFIG_LEN] {
    let mut b = [0u8; CONFIG_LEN];
    put32(&mut b, 0, MAGIC);
    put32(&mut b, SEQ, seq);
    put32(&mut b, 0x08, m.scan as u32 | (m.grid as u32) << 1);
    let r = &m.radar;
    b[0x0C] = r.beams;
    b[0x0D] = r.dwell;
    b[0x0E] = r.dwell_hit;
    b[0x0F] = r.dwell_max;
    b[0x10] = r.settle;
    b[0x12..0x14].copy_from_slice(&r.min_det.to_le_bytes());
    put32(&mut b, 0x14, r.range_bin_cm);
    put32(&mut b, 0x18, r.doppler_bin_cms as u32);
    put32(&mut b, 0x1C, m.frame_ms);
    put32(&mut b, 0x20, m.cell_cm);
    put32(&mut b, 0x24, m.mount.x_cm as u32);
    put32(&mut b, 0x28, m.mount.y_cm as u32);
    put32(&mut b, 0x2C, m.mount.yaw_cdeg as u32);
    put64(&mut b, 0x30, m.heartbeat);
    for (k, a) in r.az_cdeg.iter().enumerate() {
        b[0x40 + 2 * k..0x42 + 2 * k].copy_from_slice(&a.to_le_bytes());
    }
    b
}

pub fn decode_core1_config(b: &[u8; CONFIG_LEN]) -> Option<Core1Config> {
    if get32(b, 0) != MAGIC || get32(b, SEQ) & 1 == 1 {
        return None;
    }
    let flags = get32(b, 0x08);
    let mut az = [0i16; crate::radar::MAX_BEAMS];
    for (k, a) in az.iter_mut().enumerate() {
        *a = i16::from_le_bytes([b[0x40 + 2 * k], b[0x41 + 2 * k]]);
    }
    Some(Core1Config {
        scan: flags & 1 != 0,
        grid: flags & 2 != 0,
        radar: crate::radar::Config {
            beams: b[0x0C],
            az_cdeg: az,
            dwell: b[0x0D],
            dwell_hit: b[0x0E],
            dwell_max: b[0x0F],
            settle: b[0x10],
            min_det: u16::from_le_bytes([b[0x12], b[0x13]]),
            range_bin_cm: get32(b, 0x14),
            doppler_bin_cms: get32(b, 0x18) as i32,
        },
        frame_ms: get32(b, 0x1C),
        cell_cm: get32(b, 0x20),
        mount: crate::bev::Mount {
            x_cm: get32(b, 0x24) as i32,
            y_cm: get32(b, 0x28) as i32,
            yaw_cdeg: get32(b, 0x2C) as i32,
        },
        heartbeat: get64(b, 0x30),
    })
}

/// What core 1 reports.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Core1Status {
    pub cpis: u32,
    pub missed: u32,
    pub strobes: u32,
    pub hits: u32,
    pub beam: u8,
    /// `kria_bev_axi` answered with its ID.
    pub grid_ok: bool,
    /// The radar is running (`RADAR_STAT`'s CPI count moves).
    pub radar_ok: bool,
    /// Frame buffer (0 or 1) holding the latest complete dump.
    pub frame: u8,
    /// Complete dumps so far; a reader sees a new frame when it changes.
    pub frame_seq: u32,
    /// Ring entries consumed.
    pub ring_tail: u32,
    /// Commands pushed into the grid.
    pub pushed: u32,
    /// Times the grid's queue was found full (the command waited).
    pub grid_full: u32,
    /// DMA errors on a dump (the DMA was reset and the frame dropped).
    pub dma_errors: u32,
    pub heartbeat: u64,
}

pub fn encode_core1_status(m: &Core1Status, seq: u32) -> [u8; HALF] {
    let mut b = [0u8; HALF];
    put32(&mut b, 0, MAGIC);
    put32(&mut b, SEQ, seq);
    put32(&mut b, 0x08, m.cpis);
    put32(&mut b, 0x0C, m.missed);
    put32(&mut b, 0x10, m.strobes);
    put32(&mut b, 0x14, m.hits);
    b[0x18] = m.beam;
    b[0x19] = m.grid_ok as u8 | (m.radar_ok as u8) << 1;
    b[0x1A] = m.frame;
    put32(&mut b, 0x1C, m.frame_seq);
    put32(&mut b, 0x20, m.ring_tail);
    put32(&mut b, 0x24, m.pushed);
    put64(&mut b, 0x28, m.heartbeat);
    put32(&mut b, 0x30, m.grid_full);
    put32(&mut b, 0x34, m.dma_errors);
    b
}

pub fn decode_core1_status(b: &[u8; HALF]) -> Option<Core1Status> {
    if get32(b, 0) != MAGIC || get32(b, SEQ) & 1 == 1 {
        return None;
    }
    Some(Core1Status {
        cpis: get32(b, 0x08),
        missed: get32(b, 0x0C),
        strobes: get32(b, 0x10),
        hits: get32(b, 0x14),
        beam: b[0x18],
        grid_ok: b[0x19] & 1 != 0,
        radar_ok: b[0x19] & 2 != 0,
        frame: b[0x1A],
        frame_seq: get32(b, 0x1C),
        ring_tail: get32(b, 0x20),
        pushed: get32(b, 0x24),
        heartbeat: get64(b, 0x28),
        grid_full: get32(b, 0x30),
        dma_errors: get32(b, 0x34),
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
            link: Health::Errors,
            link_retrains: 3,
            link_crc_per_s: 250,
        };
        assert_eq!(decode_from_r5f(&encode_from_r5f(&f, 8)), Some(f));
        let mut junk = [0u8; HALF];
        junk[0] = 1;
        assert_eq!(decode_from_r5f(&junk), None);
    }

    #[test]
    fn core1_blocks_round_trip() {
        let mut c = Core1Config { scan: true, grid: true, frame_ms: 50, ..Default::default() };
        c.radar.beams = 7;
        c.radar.az_cdeg[6] = -1234;
        c.mount.yaw_cdeg = -9000;
        c.heartbeat = 1 << 40;
        let d = decode_core1_config(&encode_core1_config(&c, 4)).unwrap();
        assert_eq!((d.scan, d.grid, d.frame_ms, d.mount.yaw_cdeg, d.mount.x_cm, d.heartbeat), (true, true, 50, -9000, 380, 1 << 40));
        assert_eq!((d.radar.beams, d.radar.az_cdeg[6], d.radar.az_cdeg[0], d.radar.range_bin_cm), (7, -1234, -4500, 150));
        assert!(decode_core1_config(&encode_core1_config(&c, 5)).is_none());
        let s = Core1Status {
            cpis: 1000, missed: 2, strobes: 300, hits: 40, beam: 12, grid_ok: true, radar_ok: true,
            frame: 1, frame_seq: 77, ring_tail: 5000, pushed: 6000, grid_full: 1, dma_errors: 2, heartbeat: 9,
        };
        assert_eq!(decode_core1_status(&encode_core1_status(&s, 2)), Some(s));
        assert!(CORE1_CONFIG + CONFIG_LEN <= 0x1000);
    }
}
