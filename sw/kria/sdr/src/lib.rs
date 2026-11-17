//! The USB receivers on the KV260's A53s: a KrakenSDR for direction finding and a HackRF Pro for the bands above
//! this board's front ends. Each pairs with a block in the K26's PL (`fpga/kria/integrations/kria_doa.v`,
//! `kria_sweep.v`); the design and the end-to-end tests are in docs/INTEGRATIONS.md sections 9 and 10.
//!
//! - [`kraken`]: the five channels' alignment and calibration from the noise source, the PL's stream and
//!   steering table, a bit-exact model of `kria_doa`, MUSIC.
//! - [`hackrf`]: sweep blocks, a bit-exact model of `kria_sweep`, the panorama, and the transmit gate.
//! - [`pl`]: the two blocks' registers through `/dev/mem` on the KV260 (feature `hw`).

pub mod cplx;
pub mod hackrf;
pub mod kraken;
pub mod pl;
#[cfg(feature = "hw")]
pub mod usb;
