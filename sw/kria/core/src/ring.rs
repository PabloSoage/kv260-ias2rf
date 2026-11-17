//! Linux's queue of grid commands for R5F core 1.
//!
//! R5F core 1 owns the fusion grid's command port: `DET_XY` then `DET_CMD` is
//! two writes, and a second writer in between would pair one's position with
//! the other's command. Everything else that wants a cell updated (the 77 GHz
//! radar's objects decoded on the A53s, a LiDAR, the decay and dump cadence
//! when Linux sets it) goes through this ring, which core 1 drains into the
//! grid between radar polls.
//!
//! Single producer (Linux), single consumer (core 1), in the shared region
//! after the mailbox ([`BASE`]):
//!
//! | Offset | Field |
//! |---|---|
//! | 0x00 | magic `KRG1` |
//! | 0x04 | capacity (entries, a power of two) |
//! | 0x08 | `head`: entries written, ever (Linux) |
//! | 0x0C | `tail`: entries consumed, ever (core 1) |
//! | 0x10 | entries dropped because the ring was full (Linux) |
//! | 0x40 | `capacity` entries of 8 bytes: a [`crate::bev::Command`] |
//!
//! The counters only grow (wrapping at 2^32), so each side writes only its
//! own word. The producer writes the entry, then a barrier, then `head`; the
//! consumer reads `head`, a barrier, the entries, then writes `tail`. The
//! region is uncached on both sides (`no-map` in the device tree, caches off
//! on the R5F), so the barriers only order the accesses.

/// Physical address of the ring: 4 KiB into the mailbox region.
pub const BASE: u64 = crate::mailbox::BASE + 0x1000;
pub const MAGIC: u32 = u32::from_le_bytes(*b"KRG1");
pub const CAPACITY: u32 = 1024;
pub const OFF_MAGIC: usize = 0x00;
pub const OFF_CAP: usize = 0x04;
pub const OFF_HEAD: usize = 0x08;
pub const OFF_TAIL: usize = 0x0C;
pub const OFF_DROPS: usize = 0x10;
pub const OFF_ENTRIES: usize = 0x40;
pub const BYTES: usize = OFF_ENTRIES + 8 * CAPACITY as usize;

/// Byte offset of entry `n` (a head or tail count).
pub fn slot(n: u32) -> usize {
    OFF_ENTRIES + 8 * (n % CAPACITY) as usize
}

/// Entries waiting.
pub fn pending(head: u32, tail: u32) -> u32 {
    head.wrapping_sub(tail)
}

/// Whether the producer may write one more.
pub fn has_room(head: u32, tail: u32) -> bool {
    pending(head, tail) < CAPACITY
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn counters_wrap() {
        assert_eq!(pending(5, 3), 2);
        assert_eq!(pending(2, u32::MAX - 1), 4);
        assert!(has_room(CAPACITY - 1, 0));
        assert!(!has_room(CAPACITY, 0));
        assert!(!has_room(3, 3u32.wrapping_sub(CAPACITY)));
        assert_eq!(slot(0), 0x40);
        assert_eq!(slot(CAPACITY + 1), 0x48);
        assert!(BYTES <= 0xF000, "the ring fits the mailbox region after its first 4 KiB");
    }
}
