//! R5F core 0: the real-time half of the board's control.
//!
//! Runs from TCM, started by Linux through remoteproc, and keeps going whatever
//! Linux is doing. A 1 kHz loop timed by the PL clock (`kria_pps` `NOW`):
//!
//! - **PPS discipline.** On every GPS capture (`STATUS.cap_pending`) it runs
//!   `kria_core::pps::Discipline` and writes the generator's period and phase
//!   adjustment back to `kria_pps`; on `STATUS.missing` it goes to holdover. It
//!   puts `kria_pps` in mode 2 once the generator is running, so PPS_SYNC to the
//!   front end (and the Si549 discipline there) follows the disciplined second,
//!   which keeps going through GPS dropouts.
//! - **Transmit interlock.** Reads the mailbox Linux writes (road speed from
//!   the ECU stream, GPS speed, licence flag, transmit request), runs
//!   `kria_core::interlock::Interlock`, and owns `DSP_CTRL[1]` (transmit
//!   enable): set only while the interlock allows it and the operator asks,
//!   cleared within a millisecond otherwise. Linux never writes that bit.
//! - **Status** back to Linux in the other half of the mailbox, with a
//!   heartbeat.
//!
//! Caches and the MPU are left as at reset (off), so the mailbox in DDR and the
//! PL registers are seen as they are without maintenance. Interrupts are not
//! used: the GPS capture is polled once a millisecond, which delays the
//! correction by up to 1 ms and costs nothing in accuracy, since the capture
//! itself is a hardware timestamp.
#![no_std]
#![no_main]

use core::panic::PanicInfo;
use core::ptr::{read_volatile, write_volatile};
use kria_core::interlock::{self, Interlock};
use kria_core::mailbox::{self, FromR5f};
use kria_core::pps::{self, Capture, Discipline, Outcome};

// ---------------------------------------------------------------- addresses

/// kria_pps on M_AXI_HPM0_LPD (fpga/kria/bd.tcl).
const PPS: usize = 0x8002_0000;
const PPS_CTRL: usize = PPS + 0x00;
const PPS_STATUS: usize = PPS + 0x04;
const PPS_CAP_LO: usize = PPS + 0x08;
const PPS_CAP_HI: usize = PPS + 0x0C;
const PPS_PERIOD_INT: usize = PPS + 0x14;
const PPS_PERIOD_FRAC: usize = PPS + 0x18;
const PPS_ADJUST: usize = PPS + 0x1C;
const PPS_GEN_LO: usize = PPS + 0x20;
const PPS_GEN_HI: usize = PPS + 0x24;
const PPS_NOW_LO: usize = PPS + 0x2C;
const PPS_NOW_HI: usize = PPS + 0x30;
const PPS_ID: usize = PPS + 0x34;

/// kria_pl_link DSP_CTRL (docs/FPGA_GATEWARE.md 5.5); bit 1 is transmit enable.
const DSP_CTRL: usize = 0x8000_0040;
const TX_EN: u32 = 1 << 1;

const ST_CAP: u32 = 1 << 0;
const ST_MISSING: u32 = 1 << 1;
const ST_GEN: u32 = 1 << 3;

const CTRL_MODE_GEN: u32 = 2;
const CTRL_GEN_EN: u32 = 1 << 3;
const CTRL_RESTART: u32 = 1 << 4;

const TICK_HZ: u64 = 100_000_000;
const LOOP_TICKS: u64 = TICK_HZ / 1000;

fn rd(a: usize) -> u32 {
    unsafe { read_volatile(a as *const u32) }
}
fn wr(a: usize, v: u32) {
    unsafe { write_volatile(a as *mut u32, v) }
}
fn now() -> u64 {
    let lo = rd(PPS_NOW_LO) as u64; // latches NOW_HI
    (rd(PPS_NOW_HI) as u64) << 32 | lo
}

fn read_half(at: usize) -> [u8; mailbox::HALF] {
    let mut b = [0u8; mailbox::HALF];
    for (k, w) in b.chunks_exact_mut(4).enumerate() {
        w.copy_from_slice(&rd(at + 4 * k).to_le_bytes());
    }
    b
}

/// Seqlock read of Linux's half: retry while it is odd or changes under us.
fn read_to_r5f() -> Option<mailbox::ToR5f> {
    let at = mailbox::BASE as usize + mailbox::TO_R5F;
    for _ in 0..4 {
        let s0 = rd(at + mailbox::SEQ);
        let b = read_half(at);
        if s0 & 1 == 0 && rd(at + mailbox::SEQ) == s0 {
            return mailbox::decode_to_r5f(&b);
        }
    }
    None
}

fn write_from_r5f(m: &FromR5f, seq: &mut u32) {
    let at = mailbox::BASE as usize + mailbox::FROM_R5F;
    *seq = seq.wrapping_add(1);
    wr(at + mailbox::SEQ, *seq); // odd: being written
    let b = mailbox::encode_from_r5f(m, seq.wrapping_add(1));
    for (k, w) in b.chunks_exact(4).enumerate() {
        if 4 * k != mailbox::SEQ {
            wr(at + 4 * k, u32::from_le_bytes([w[0], w[1], w[2], w[3]]));
        }
    }
    *seq = seq.wrapping_add(1);
    wr(at + mailbox::SEQ, *seq); // even: stable
}

#[no_mangle]
pub extern "C" fn main_entry() -> ! {
    let mut disc = Discipline::new(pps::Config::default());
    let mut il = Interlock::new(interlock::Config::default());
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

        // --- interlock
        let input = read_to_r5f().filter(|m| t.saturating_sub(m.heartbeat) < linux_timeout);
        let d = il.step(interlock::Inputs {
            now: t,
            ecu: input.and_then(|m| m.ecu),
            gps: input.and_then(|m| m.gps),
            licensed: input.is_some_and(|m| m.licensed),
            request: input.is_some_and(|m| m.request),
        });
        let ctrl = rd(DSP_CTRL);
        let want = if d.transmit { ctrl | TX_EN } else { ctrl & !TX_EN };
        if want != ctrl {
            wr(DSP_CTRL, want);
        }

        // --- status
        write_from_r5f(
            &FromR5f {
                pps: disc.state(),
                reason: d.reason,
                source: d.source,
                transmit: d.transmit,
                freq_error_ppb: disc.error_ppb(),
                phase_ticks: disc.phase_ticks(),
                pps_accepted: disc.accepted,
                pps_rejected: disc.rejected,
                heartbeat: t,
            },
            &mut seq,
        );
    }
}

#[panic_handler]
fn panic(_: &PanicInfo) -> ! {
    // Transmit off, then stop. The heartbeat stops with us, which Linux sees.
    wr(DSP_CTRL, rd(DSP_CTRL) & !TX_EN);
    loop {}
}

// Reset: stack, VFP on (the eabihf code may use it), .bss cleared, main.
core::arch::global_asm!(
    r#"
    .section .vectors, "ax"
    .arm
    .global _vectors
_vectors:
    ldr pc, =_reset
    b .
    b .
    b .
    b .
    b .
    b .
    b .
_reset:
    ldr sp, =_stack_top
    mrc p15, 0, r0, c1, c0, 2
    orr r0, r0, #(0xF << 20)
    mcr p15, 0, r0, c1, c0, 2
    isb
    mov r0, #0x40000000
    vmsr fpexc, r0
    ldr r0, =__sbss
    ldr r1, =__ebss
    mov r2, #0
1:
    cmp r0, r1
    strlo r2, [r0], #4
    blo 1b
    bl main_entry
    b .
    .ltorg
"#
);

/// The minimal resource table Linux remoteproc expects: version 1, no entries.
#[repr(C, align(8))]
pub struct ResourceTable {
    ver: u32,
    num: u32,
    reserved: [u32; 2],
}

#[no_mangle]
#[link_section = ".resource_table"]
pub static RESOURCE_TABLE: ResourceTable = ResourceTable { ver: 1, num: 0, reserved: [0; 2] };
