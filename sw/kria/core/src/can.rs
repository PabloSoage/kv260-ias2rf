//! The vehicle's CAN bus on R5F core 1: the PS CAN controller's bit timing and
//! frames, the road-speed signal, and the shared blocks (INTEGRATIONS.md 2.2).
//!
//! The PS's CAN1 reaches the bus through EMIO, KV260 `J9` and the adapter's
//! TCAN330. It is CAN 2.0 (classic frames, up to 1 Mbit/s): the powertrain bus
//! that carries the road speed, not the 77 GHz radar's CAN FD (section 3 of
//! INTEGRATIONS.md). Core 1 runs it listen-only by default, so the board never
//! acknowledges or sends on a car's bus unless Linux asks for it.
//!
//! Which frame carries the speed, and how, is the car's (its DBC). Linux puts
//! that in [`CanConfig`]; core 1 decodes every matching frame into
//! [`CanStatus`], where core 0's interlock reads it as the ECU speed, straight
//! from the bus and independent of Linux.

use crate::interlock::Speed;

/// Time quanta per bit: 1 sync + 16 + 3, sample point at 85 %.
pub const TQ_PER_BIT: u32 = 20;

/// `BRPR` and `BTR` of the Zynq UltraScale+ CAN controller (UG1085, CAN
/// chapter) for a reference clock and a bit rate, or `None` if the rate does not
/// divide into whole quanta.
pub fn bit_timing(ref_hz: u32, bitrate: u32) -> Option<(u32, u32)> {
    if bitrate == 0 || ref_hz % (bitrate * TQ_PER_BIT) != 0 {
        return None;
    }
    let brp = ref_hz / (bitrate * TQ_PER_BIT);
    if !(1..=256).contains(&brp) {
        return None;
    }
    let (ts1, ts2, sjw) = (16u32, 3u32, 3u32);
    Some((brp - 1, (ts1 - 1) | (ts2 - 1) << 4 | (sjw - 1) << 7))
}

/// One received frame.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Frame {
    /// 11-bit or 29-bit identifier.
    pub id: u32,
    pub extended: bool,
    pub rtr: bool,
    pub dlc: u8,
    pub data: [u8; 8],
}

impl Frame {
    /// From the controller's `RXFIFO_ID`, `RXFIFO_DLC`, `RXFIFO_DATA1` and
    /// `RXFIFO_DATA2` (data bytes 0 to 3 in DATA1, byte 0 in its top byte).
    pub fn from_regs(id: u32, dlc: u32, dw1: u32, dw2: u32) -> Frame {
        let extended = id & (1 << 19) != 0;
        let (fid, rtr) = if extended {
            ((id >> 21) << 18 | (id >> 1) & 0x3FFFF, id & 1 != 0)
        } else {
            (id >> 21, id & (1 << 20) != 0)
        };
        let mut data = [0u8; 8];
        data[..4].copy_from_slice(&dw1.to_be_bytes());
        data[4..].copy_from_slice(&dw2.to_be_bytes());
        Frame { id: fid, extended, rtr, dlc: ((dlc >> 28) as u8).min(8), data }
    }

    /// The controller's `TXFIFO_ID` word for this frame.
    pub fn id_reg(&self) -> u32 {
        if self.extended {
            (self.id >> 18 & 0x7FF) << 21 | 1 << 20 | 1 << 19 | (self.id & 0x3FFFF) << 1 | self.rtr as u32
        } else {
            (self.id & 0x7FF) << 21 | (self.rtr as u32) << 20
        }
    }
}

/// A signal in a frame, as a DBC describes it.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Signal {
    pub id: u32,
    pub extended: bool,
    /// DBC start bit: the least significant bit for Intel order, the most
    /// significant for Motorola.
    pub start: u8,
    pub len: u8,
    /// Motorola (big-endian) order; Intel otherwise.
    pub motorola: bool,
    /// Physical value in 0.01 km/h = raw * num / den + offset.
    pub num: u32,
    pub den: u32,
    pub offset: i32,
}

impl Signal {
    fn raw(&self, d: &[u8; 8], dlc: u8) -> Option<u64> {
        let dlc = dlc.min(8) as usize;
        if self.len == 0 || self.len > 32 {
            return None;
        }
        let mut v = 0u64;
        if self.motorola {
            // DBC Motorola: start is the MSB; bits run down within a byte, then to the next byte's bit 7
            let (mut byte, mut bit) = ((self.start / 8) as usize, (self.start % 8) as i32);
            for _ in 0..self.len {
                if byte >= dlc {
                    return None;
                }
                v = v << 1 | (d[byte] >> bit & 1) as u64;
                bit -= 1;
                if bit < 0 {
                    bit = 7;
                    byte += 1;
                }
            }
        } else {
            let le = u64::from_le_bytes(*d);
            if self.start as usize + self.len as usize > 8 * dlc {
                return None;
            }
            v = le >> self.start & ((1u64 << self.len) - 1);
        }
        Some(v)
    }

    /// The speed in 0.01 km/h from a frame, if this frame carries the signal.
    pub fn decode(&self, f: &Frame) -> Option<u32> {
        if f.id != self.id || f.extended != self.extended || f.rtr || self.den == 0 {
            return None;
        }
        let raw = self.raw(&f.data, f.dlc)?;
        let v = raw as i64 * self.num as i64 / self.den as i64 + self.offset as i64;
        Some(v.clamp(0, 50_000) as u32)
    }
}

/// What Linux tells core 1 about the bus.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct CanConfig {
    pub enabled: bool,
    pub bitrate: u32,
    /// Send and acknowledge on the bus. Off by default: listen only (the
    /// controller's snoop mode).
    pub active: bool,
    /// The road-speed signal, or none.
    pub speed: Option<Signal>,
    pub heartbeat: u64,
}

impl Default for CanConfig {
    fn default() -> Self {
        Self { enabled: false, bitrate: 500_000, active: false, speed: None, heartbeat: 0 }
    }
}

/// The controller's state as core 1 last saw it.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub enum BusState {
    #[default]
    Off,
    /// Configured, no frame yet.
    Idle,
    Receiving,
    ErrorPassive,
    BusOff,
}

/// What core 1 reports about the bus; core 0 takes `speed` as the ECU speed.
#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub struct CanStatus {
    pub state: BusState,
    pub frames: u32,
    pub speed_frames: u32,
    pub errors: u32,
    pub overflows: u32,
    /// The latest decoded road speed, stamped with the PL tick of its frame.
    pub speed: Option<Speed>,
    /// Frames written to the ring so far (the ring's head).
    pub ring_head: u32,
    pub heartbeat: u64,
}

/// Mailbox offsets of the blocks and the frame ring.
pub const STATUS: usize = 0x0C0;
pub const CONFIG: usize = 0x180;
pub const BLOCK: usize = 64;
/// The ring of received frames for Linux, [`RING_LEN`] entries of 16 bytes,
/// written by core 1 only, oldest overwritten; Linux follows `ring_head`.
pub const RING: usize = 0x4000;
pub const RING_LEN: usize = 128;
pub const RING_ENTRY: usize = 16;

const MAGIC: u32 = u32::from_le_bytes(*b"KCN1");
const NONE: u32 = u32::MAX;

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

pub fn encode_config(m: &CanConfig, seq: u32) -> [u8; BLOCK] {
    let mut b = [0u8; BLOCK];
    put32(&mut b, 0, MAGIC);
    put32(&mut b, crate::mailbox::SEQ, seq);
    put32(&mut b, 0x08, m.enabled as u32 | (m.active as u32) << 1 | (m.speed.is_some() as u32) << 2);
    put32(&mut b, 0x0C, m.bitrate);
    if let Some(s) = m.speed {
        put32(&mut b, 0x10, s.id);
        b[0x14] = s.start;
        b[0x15] = s.len;
        b[0x16] = s.motorola as u8 | (s.extended as u8) << 1;
        put32(&mut b, 0x18, s.num);
        put32(&mut b, 0x1C, s.den);
        put32(&mut b, 0x20, s.offset as u32);
    }
    put64(&mut b, 0x28, m.heartbeat);
    b
}

pub fn decode_config(b: &[u8; BLOCK]) -> Option<CanConfig> {
    if get32(b, 0) != MAGIC || get32(b, crate::mailbox::SEQ) & 1 == 1 {
        return None;
    }
    let f = get32(b, 0x08);
    let speed = (f & 4 != 0).then(|| Signal {
        id: get32(b, 0x10),
        start: b[0x14],
        len: b[0x15],
        motorola: b[0x16] & 1 != 0,
        extended: b[0x16] & 2 != 0,
        num: get32(b, 0x18),
        den: get32(b, 0x1C),
        offset: get32(b, 0x20) as i32,
    });
    Some(CanConfig { enabled: f & 1 != 0, active: f & 2 != 0, bitrate: get32(b, 0x0C), speed, heartbeat: get64(b, 0x28) })
}

pub fn encode_status(m: &CanStatus, seq: u32) -> [u8; BLOCK] {
    let mut b = [0u8; BLOCK];
    put32(&mut b, 0, MAGIC);
    put32(&mut b, crate::mailbox::SEQ, seq);
    b[0x08] = m.state as u8;
    put32(&mut b, 0x0C, m.frames);
    put32(&mut b, 0x10, m.speed_frames);
    put32(&mut b, 0x14, m.errors);
    put32(&mut b, 0x18, m.overflows);
    match m.speed {
        Some(s) => {
            put32(&mut b, 0x1C, s.centi_kmh);
            put64(&mut b, 0x20, s.stamp);
        }
        None => put32(&mut b, 0x1C, NONE),
    }
    put32(&mut b, 0x28, m.ring_head);
    put64(&mut b, 0x30, m.heartbeat);
    b
}

pub fn decode_status(b: &[u8; BLOCK]) -> Option<CanStatus> {
    if get32(b, 0) != MAGIC || get32(b, crate::mailbox::SEQ) & 1 == 1 {
        return None;
    }
    let state = match b[0x08] {
        1 => BusState::Idle,
        2 => BusState::Receiving,
        3 => BusState::ErrorPassive,
        4 => BusState::BusOff,
        _ => BusState::Off,
    };
    let v = get32(b, 0x1C);
    Some(CanStatus {
        state,
        frames: get32(b, 0x0C),
        speed_frames: get32(b, 0x10),
        errors: get32(b, 0x14),
        overflows: get32(b, 0x18),
        speed: (v != NONE).then(|| Speed { centi_kmh: v, stamp: get64(b, 0x20) }),
        ring_head: get32(b, 0x28),
        heartbeat: get64(b, 0x30),
    })
}

/// A ring entry: `{id | ext << 31 | rtr << 30, dlc, data[0..8]}`, 16 bytes.
pub fn encode_ring_entry(f: &Frame) -> [u8; RING_ENTRY] {
    let mut b = [0u8; RING_ENTRY];
    put32(&mut b, 0, f.id | (f.extended as u32) << 31 | (f.rtr as u32) << 30);
    put32(&mut b, 4, f.dlc as u32);
    b[8..].copy_from_slice(&f.data);
    b
}

pub fn decode_ring_entry(b: &[u8; RING_ENTRY]) -> Frame {
    let w = get32(b, 0);
    let mut data = [0u8; 8];
    data.copy_from_slice(&b[8..]);
    Frame { id: w & 0x1FFF_FFFF, extended: w >> 31 != 0, rtr: w >> 30 & 1 != 0, dlc: (get32(b, 4) as u8).min(8), data }
}

/// The fresher of two speeds (by stamp), so core 0 prefers whichever source
/// spoke last: the bus read by core 1, or the ECU stream from Linux.
pub fn fresher(a: Option<Speed>, b: Option<Speed>) -> Option<Speed> {
    match (a, b) {
        (Some(x), Some(y)) => Some(if y.stamp > x.stamp { y } else { x }),
        (x, None) => x,
        (None, y) => y,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn bit_timing_at_100_mhz() {
        // 500 kbit/s: 10 MHz quanta, 20 a bit
        assert_eq!(bit_timing(100_000_000, 500_000), Some((9, 15 | 2 << 4 | 2 << 7)));
        assert_eq!(bit_timing(100_000_000, 250_000).unwrap().0, 19);
        assert_eq!(bit_timing(100_000_000, 1_000_000).unwrap().0, 4);
        assert_eq!(bit_timing(100_000_000, 125_000).unwrap().0, 39);
        assert_eq!(bit_timing(100_000_000, 33_333), None);
    }

    #[test]
    fn frame_registers_round_trip() {
        let std = Frame { id: 0x0D0, extended: false, rtr: false, dlc: 8, data: [1, 2, 3, 4, 5, 6, 7, 8] };
        let f = Frame::from_regs(std.id_reg(), 8 << 28, 0x0102_0304, 0x0506_0708);
        assert_eq!(f, std);
        let ext = Frame { id: 0x18FE_F100, extended: true, rtr: false, dlc: 8, data: [0; 8] };
        assert_eq!(Frame::from_regs(ext.id_reg(), 8 << 28, 0, 0).id, 0x18FE_F100);
        assert!(Frame::from_regs(ext.id_reg(), 8 << 28, 0, 0).extended);
        assert_eq!(decode_ring_entry(&encode_ring_entry(&ext)), ext);
    }

    #[test]
    fn intel_signal() {
        // 16 bits from bit 16, 0.01 km/h per bit: bytes 2 and 3, little-endian
        let s = Signal { id: 0x0D0, extended: false, start: 16, len: 16, motorola: false, num: 1, den: 1, offset: 0 };
        let mut f = Frame { id: 0x0D0, dlc: 8, ..Default::default() };
        f.data[2] = 0x70;
        f.data[3] = 0x17; // 0x1770 = 6000 = 60.00 km/h
        assert_eq!(s.decode(&f), Some(6000));
        f.id = 0x0D1;
        assert_eq!(s.decode(&f), None, "other frame");
        f.id = 0x0D0;
        f.dlc = 3;
        assert_eq!(s.decode(&f), None, "frame too short for the signal");
    }

    #[test]
    fn motorola_signal_with_scale() {
        // J1939 style is Intel; this is a Motorola signal: MSB at bit 7 of byte 0, 12 bits,
        // 0.0625 km/h per bit = 6.25 centi-km/h: raw 0x320 = 800 -> 50.00 km/h
        let s = Signal { id: 0x1A0, extended: false, start: 7, len: 12, motorola: true, num: 625, den: 100, offset: 0 };
        let mut f = Frame { id: 0x1A0, dlc: 2, ..Default::default() };
        f.data[0] = 0x32;
        f.data[1] = 0x00; // 0x32 then the top nibble of byte 1: 0x320
        assert_eq!(s.decode(&f), Some(5000));
        f.dlc = 1;
        assert_eq!(s.decode(&f), None);
    }

    #[test]
    fn blocks_round_trip() {
        let c = CanConfig {
            enabled: true,
            bitrate: 500_000,
            active: false,
            speed: Some(Signal { id: 0x18FE_F100, extended: true, start: 8, len: 16, motorola: false, num: 100, den: 256, offset: 0 }),
            heartbeat: 5,
        };
        assert_eq!(decode_config(&encode_config(&c, 2)), Some(c));
        assert_eq!(decode_config(&encode_config(&c, 3)), None);
        let s = CanStatus {
            state: BusState::Receiving,
            frames: 1000,
            speed_frames: 50,
            errors: 1,
            overflows: 0,
            speed: Some(Speed { centi_kmh: 4321, stamp: 1 << 33 }),
            ring_head: 1000,
            heartbeat: 3,
        };
        assert_eq!(decode_status(&encode_status(&s, 4)), Some(s));
        assert!(STATUS + BLOCK <= crate::mailbox::CORE1_CONFIG);
        assert!(CONFIG >= crate::mailbox::CORE1_CONFIG + crate::mailbox::CONFIG_LEN && CONFIG + BLOCK <= 0x1000);
        assert!(RING >= 0x1000 + crate::ring::BYTES && RING + RING_LEN * RING_ENTRY <= crate::mailbox::REGION);
    }

    #[test]
    fn fresher_speed_wins() {
        let a = Some(Speed { centi_kmh: 100, stamp: 10 });
        let b = Some(Speed { centi_kmh: 200, stamp: 20 });
        assert_eq!(fresher(a, b), b);
        assert_eq!(fresher(b, a), b);
        assert_eq!(fresher(None, a), a);
        assert_eq!(fresher(a, None), a);
    }
}
