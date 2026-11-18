//! `kria-hmi-core`: the in-car HMI's data plane and state, with no I/O (HMI.md §6).
//!
//! The PL's `kria_ps_framer` writes every stream for the A53s into DMA blocks; `frame` walks them, the other
//! modules decode each stream (`audio` with RDS, `adsb`, `radar`, `spectrum`), `modes` turns a frequency and mode
//! into register writes, and `state` holds what the screens show and the commands they send. `kria-hmid` is the
//! I/O around it, on the KV260 or simulated; the Slint application draws it, natively or in a browser.

pub mod adsb;
pub mod audio;
pub mod frame;
pub mod modes;
pub mod radar;
pub mod spectrum;
pub mod state;
