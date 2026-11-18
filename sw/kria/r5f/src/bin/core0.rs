//! R5F core 0: the real-time half of the board's control.
//!
//! Runs from TCM, started by Linux through remoteproc (`kria-r5f0`), and keeps
//! going whatever Linux is doing. A 1 kHz loop timed by the PL clock
//! (`kria_pps` `NOW`):
//!
//! - **PPS discipline.** On every GPS capture (`STATUS.cap_pending`) it runs
//!   `kria_core::pps::Discipline` and writes the generator's period and phase
//!   adjustment back to `kria_pps`; on `STATUS.missing` it goes to holdover. It
//!   puts `kria_pps` in mode 2 once the generator is running, so PPS_SYNC to the
//!   front end (and the Si549 discipline there) follows the disciplined second,
//!   which keeps going through GPS dropouts.
//! - **IAS1 link watchdog.** Reads `LINK_STATUS` and the CRC error count and
//!   retrains the link (`LINK_CTRL[2]`) when it drops or its errors climb, with
//!   a back-off (`kria_core::link`). A read that aborts (the link's receive
//!   clock is gone) counts as down.
//! - **Transmit interlock.** Reads the mailbox Linux writes (road speed from
//!   the ECU stream, GPS speed, licence flag, transmit request), runs
//!   `kria_core::interlock::Interlock`, and owns `TX_KEY` (`kria_pl_link`
//!   0x38, the transmit enable): set only while the interlock allows it, the
//!   link is up and the operator asks; cleared within a millisecond otherwise.
//!   The register is this core's alone (`DSP_CTRL[1]` only reads it back), and
//!   a write needs the key word, so nothing Linux writes can key the
//!   transmitter.
//! - **Status** back to Linux in the mailbox, with a heartbeat.
//!
//! Interrupts are not used: the GPS capture is polled once a millisecond,
//! which delays the correction by up to 1 ms and costs nothing in accuracy,
//! since the capture itself is a hardware timestamp.
#![no_std]
#![no_main]

#[path = "../hw.rs"]
mod hw;
#[path = "../rt.rs"]
mod rt;

use hw::{now, rd, try_rd, wr, PPS, TICK_HZ};
use kria_core::can;
use kria_core::interlock::{self, Interlock};
use kria_core::link::{self, Watchdog};
use kria_core::mailbox::{self, FromR5f};
use kria_core::pps::{self, Capture, Discipline, Outcome};

const PPS_CTRL: usize = PPS + 0x00;
const PPS_STATUS: usize = PPS + 0x04;
const PPS_CAP_LO: usize = PPS + 0x08;
const PPS_CAP_HI: usize = PPS + 0x0C;
const PPS_PERIOD_INT: usize = PPS + 0x14;
const PPS_PERIOD_FRAC: usize = PPS + 0x18;
const PPS_ADJUST: usize = PPS + 0x1C;
const PPS_GEN_LO: usize = PPS + 0x20;
const PPS_GEN_HI: usize = PPS + 0x24;
const PPS_ID: usize = PPS + 0x34;

/// `kria_pl_link`: link registers (fpga/link/LINK_PROTOCOL.md 7.2) and
/// TX_KEY (docs/FPGA_GATEWARE.md 5.3): `[31:8]` the key word, `[0]` transmit
/// enable. It is answered on `pl_clk`, so it works with the link down.
const LINK: usize = 0x8000_0000;
const LINK_CTRL: usize = LINK + 0x00;
const LINK_STATUS: usize = LINK + 0x04;
const LINK_CRC: usize = LINK + 0x18;
const TX_KEY: usize = LINK + 0x38;
const TX_KEY_OFF: u32 = 0x4B45_5900;
const TX_KEY_ON: u32 = 0x4B45_5901;

const ST_CAP: u32 = 1 << 0;
const ST_MISSING: u32 = 1 << 1;
const ST_GEN: u32 = 1 << 3;

const CTRL_MODE_GEN: u32 = 2;
const CTRL_GEN_EN: u32 = 1 << 3;
const CTRL_RESTART: u32 = 1 << 4;

const LOOP_TICKS: u64 = TICK_HZ / 1000;

#[no_mangle]
fn on_panic() {
    wr(TX_KEY, TX_KEY_OFF);
}

#[no_mangle]
pub extern "C" fn main_entry() -> ! {
    let mut disc = Discipline::new(pps::Config::default());
    let mut il = Interlock::new(interlock::Config::default());
    let mut wd = Watchdog::new(link::Config::default());
    let mut seq = 0u32;
    let have_pps = rd(PPS_ID) == 0x5050_5331;
    let mut generating = false;
    let mut next = now();
    // Linux silent for this long counts as no input at all: speed unknown,
    // no request, so the interlock fails safe.
    let linux_timeout = TICK_HZ / 2;

    loop {
        while now() < next {}
        next += LOOP_TICKS;
        let t = now();

        // --- PPS
        if have_pps {
            let st = rd(PPS_STATUS);
            let seen = st & (ST_CAP | ST_GEN);
            if seen != 0 {
                wr(PPS_STATUS, seen); // clear only what was read (tb_kria_pps)
            }
            if st & ST_CAP != 0 {
                let cap = (rd(PPS_CAP_HI) as u64) << 32 | rd(PPS_CAP_LO) as u64;
                let generated = (rd(PPS_GEN_HI) as u64) << 32 | rd(PPS_GEN_LO) as u64;
                let count = (st >> 16) as u16;
                if let Outcome::Applied(cmd) = disc.on_capture(Capture { cap, generated, count }) {
                    wr(PPS_PERIOD_INT, cmd.period_int);
                    wr(PPS_PERIOD_FRAC, cmd.period_frac);
                    if cmd.adjust != 0 {
                        wr(PPS_ADJUST, cmd.adjust as u32);
                    }
                    if cmd.restart {
                        // Keep PPS_SYNC on the GPS until the generator has a
                        // second to run on, then switch to it.
                        wr(PPS_CTRL, 1 | CTRL_GEN_EN | CTRL_RESTART);
                        generating = true;
                    } else if generating && disc.state() == pps::State::Locked {
                        wr(PPS_CTRL, CTRL_MODE_GEN | CTRL_GEN_EN);
                    }
                }
            } else if st & ST_MISSING != 0 && disc.state() != pps::State::Holdover {
                disc.on_missing();
                if generating {
                    wr(PPS_CTRL, CTRL_MODE_GEN | CTRL_GEN_EN);
                }
            }
        }

        // --- IAS1 link
        let status = try_rd(LINK_STATUS).unwrap_or(0);
        let crc = if status & link::STATUS_LINK_UP != 0 { try_rd(LINK_CRC).unwrap_or(0) } else { 0 };
        if wd.step(status, crc) {
            // A write that fails is an imprecise abort, counted and ignored.
            wr(LINK_CTRL, link::CTRL_RETRAIN);
        }

        // --- interlock
        let input = hw::read_stable::<{ mailbox::HALF }>(mailbox::TO_R5F)
            .and_then(|b| mailbox::decode_to_r5f(&b))
            .filter(|m| t.saturating_sub(m.heartbeat) < linux_timeout);
        // the road speed from the bus itself (core 1), or from Linux's ECU stream: whichever is fresher
        let bus = hw::read_stable::<{ can::BLOCK }>(can::STATUS)
            .and_then(|b| can::decode_status(&b))
            .filter(|s| t.saturating_sub(s.heartbeat) < linux_timeout)
            .and_then(|s| s.speed);
        let d = il.step(interlock::Inputs {
            now: t,
            ecu: can::fresher(bus, input.and_then(|m| m.ecu)),
            gps: input.and_then(|m| m.gps),
            licensed: input.is_some_and(|m| m.licensed),
            request: input.is_some_and(|m| m.request),
        });
        let transmit = d.transmit && wd.up();
        // its own register: a plain write, no read-modify-write shared with Linux
        let want = if transmit { TX_KEY_ON } else { TX_KEY_OFF };
        if rd(TX_KEY) != want {
            wr(TX_KEY, want);
        }

        // --- status
        let m = FromR5f {
            pps: disc.state(),
            reason: d.reason,
            source: d.source,
            transmit,
            freq_error_ppb: disc.error_ppb(),
            phase_ticks: disc.phase_ticks(),
            pps_accepted: disc.accepted,
            pps_rejected: disc.rejected,
            heartbeat: t,
            link: wd.health(),
            link_retrains: wd.retrains,
            link_crc_per_s: wd.crc_last_s,
        };
        hw::write_stable(mailbox::FROM_R5F, &mut seq, |s| mailbox::encode_from_r5f(&m, s));
    }
}
