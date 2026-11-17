//! Register and shared-memory access for both R5F images.

use core::ptr::{read_volatile, write_volatile};
use kria_core::mailbox;

/// `kria_pps` on `M_AXI_HPM0_LPD` (`fpga/kria/bd.tcl`).
pub const PPS: usize = 0x8002_0000;
pub const PPS_NOW_LO: usize = PPS + 0x2C;
pub const PPS_NOW_HI: usize = PPS + 0x30;
pub const TICK_HZ: u64 = 100_000_000;

pub fn rd(a: usize) -> u32 {
    unsafe { read_volatile(a as *const u32) }
}
pub fn wr(a: usize, v: u32) {
    unsafe { write_volatile(a as *mut u32, v) }
}

/// A read that may abort (SLVERR): `None` if it did.
pub fn try_rd(a: usize) -> Option<u32> {
    let before = crate::rt::aborts();
    let v = rd(a);
    (crate::rt::aborts() == before).then_some(v)
}

pub fn dmb() {
    unsafe { core::arch::asm!("dmb", options(nostack, preserves_flags)) }
}

/// The PL clock. Reading `NOW_LO` latches `NOW_HI`, and Linux and the other
/// core read it too, so another reader's latch can land between our two
/// reads. Two pairs that agree, with no wrap of the low word between them,
/// are consistent.
pub fn now() -> u64 {
    loop {
        let lo = rd(PPS_NOW_LO);
        let hi = rd(PPS_NOW_HI);
        let lo2 = rd(PPS_NOW_LO);
        let hi2 = rd(PPS_NOW_HI);
        if hi == hi2 && lo2 >= lo {
            return (hi as u64) << 32 | lo as u64;
        }
    }
}

pub fn read_block<const N: usize>(at: usize) -> [u8; N] {
    let mut b = [0u8; N];
    for (k, w) in b.chunks_exact_mut(4).enumerate() {
        w.copy_from_slice(&rd(at + 4 * k).to_le_bytes());
    }
    b
}

/// Seqlock read of a block another side writes.
pub fn read_stable<const N: usize>(off: usize) -> Option<[u8; N]> {
    let at = mailbox::BASE as usize + off;
    for _ in 0..4 {
        let s0 = rd(at + mailbox::SEQ);
        dmb();
        let b = read_block::<N>(at);
        dmb();
        if s0 & 1 == 0 && rd(at + mailbox::SEQ) == s0 {
            return Some(b);
        }
    }
    None
}

/// Seqlock write of our own block: `encode(seq)` gives the bytes for a
/// sequence value.
pub fn write_stable<const N: usize>(off: usize, seq: &mut u32, encode: impl Fn(u32) -> [u8; N]) {
    let at = mailbox::BASE as usize + off;
    *seq = seq.wrapping_add(1) | 1;
    wr(at + mailbox::SEQ, *seq); // odd: being written
    dmb();
    let b = encode(seq.wrapping_add(1));
    for (k, w) in b.chunks_exact(4).enumerate() {
        if 4 * k != mailbox::SEQ {
            wr(at + 4 * k, u32::from_le_bytes([w[0], w[1], w[2], w[3]]));
        }
    }
    dmb();
    *seq = seq.wrapping_add(1);
    wr(at + mailbox::SEQ, *seq); // even: stable
}
