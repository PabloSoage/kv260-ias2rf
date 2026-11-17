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
//! - [`link`]: the watchdog on the IAS1 link: retrain when it drops or its
//!   errors climb, with a back-off. R5F core 0, every millisecond.
//! - [`radar`]: the 10.5 GHz radar's beam scan, one step per CPI, with a
//!   longer dwell where there are detections. R5F core 1.
//! - [`bev`]: the PL fusion grid's commands and configuration, and sensor
//!   coordinates to grid cells. R5F core 1 and the A53s.
//! - [`ring`]: the queue of grid commands from Linux to R5F core 1.
//! - [`mailbox`]: the shared-memory blocks through which Linux and the R5F
//!   cores exchange all of this.
#![cfg_attr(not(test), no_std)]
#![forbid(unsafe_code)]

pub mod bev;
pub mod interlock;
pub mod link;
pub mod mailbox;
pub mod pps;
pub mod radar;
pub mod ring;
pub mod telemetry;
