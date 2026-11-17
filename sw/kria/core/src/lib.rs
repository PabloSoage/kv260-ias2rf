//! Logic for the KV260's processors, with no I/O.
//!
//! The same crate runs on the A53s under Linux and on the two R5F real-time
//! cores, so it is `no_std` and allocation-free: bytes and numbers in, numbers
//! out, which is also what lets every piece be tested on a PC.
//!
//! - [`pps`]: disciplines the PL's PPS generator (`fpga/kria/kria_pps.v`) to a
//!   GPS receiver's pulse, with holdover. R5F core 0, once a second.
//! - [`interlock`]: whether the transmitter may key, from vehicle speed (ECU
//!   stream first, GPS second), the licence flag and a transmit time-out.
//!   R5F core 0, every millisecond.
//! - [`telemetry`]: the `opendash-telemetry/1` lines that carry the ECU stream
//!   from opendash (or a bench bridge) to the board. A53, `kria-vehicled`.
//! - [`mailbox`]: the shared-memory block through which Linux and R5F core 0
//!   exchange those values.
#![cfg_attr(not(test), no_std)]
#![forbid(unsafe_code)]

pub mod interlock;
pub mod mailbox;
pub mod pps;
pub mod telemetry;
