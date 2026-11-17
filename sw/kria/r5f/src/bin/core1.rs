//! R5F core 1: the radar scan and the fusion grid.
//!
//! Started by Linux through remoteproc (`kria-r5f1`), configured through the
//! mailbox (`kria_core::mailbox::Core1Config`). A loop every 100 us, timed by
//! the PL clock:
//!
//! - **Radar scan.** Reads `RADAR_STAT` (`kria_dsp_suite`), runs
//!   `kria_core::radar::Scheduler`, and pulses `BEAM_STROBE` (EMIO GPIO 1,
//!   through the PS GPIO block's masked-write register, so Linux's other EMIO
//!   lines are untouched) to step the Artix's beam scan (`ADAR_CTRL[13]`).
//! - **Grid.** Each detection goes to the PL grid (`kria_bev_axi`) as the
//!   10.5 GHz radar's point, transformed from range and beam azimuth to vehicle
//!   coordinates. Core 1 is the only writer of the grid's command port; Linux's
//!   own commands (the 77 GHz radar's objects, a LiDAR) come through the ring
//!   in shared memory and are drained here.
//! - **Frames.** Every `frame_ms` a decay pass and a dump; `axi_dma_1` writes
//!   the dump into one of two 64 KiB frame buffers, and the status block says
//!   which one holds the latest complete frame.
//!
//! Linux's configuration is a heartbeat too: silent for 1 s, the scan and the
//! grid stop (the beam stays where it is; nothing transmits from here).
#![no_std]
#![no_main]

#[path = "../hw.rs"]
#[allow(dead_code)]
mod hw;
#[path = "../rt.rs"]
#[allow(dead_code)]
mod rt;

use hw::{dmb, now, rd, wr, TICK_HZ};
use kria_core::bev::{self, Command, Grid, Sensor};
use kria_core::mailbox::{self, Core1Config, Core1Status};
use kria_core::radar::Scheduler;
use kria_core::ring;

/// `kria_dsp_suite` RADAR_STAT, through `kria_pl_link` (local, never aborts).
const RADAR_STAT: usize = 0x8000_007C;
/// `kria_bev_axi` and `axi_dma_1` (fpga/kria/bd.tcl).
const BEV: usize = 0x8003_0000;
const DMA1: usize = 0x8004_0000;
const S2MM_DMACR: usize = DMA1 + 0x30;
const S2MM_DMASR: usize = DMA1 + 0x34;
const S2MM_DA: usize = DMA1 + 0x48;
const S2MM_DA_MSB: usize = DMA1 + 0x4C;
const S2MM_LENGTH: usize = DMA1 + 0x58;
const DMACR_RS: u32 = 1 << 0;
const DMACR_RESET: u32 = 1 << 2;
const DMASR_HALTED: u32 = 1 << 0;
const DMASR_IDLE: u32 = 1 << 1;
const DMASR_ERR: u32 = 0x70;
const DMASR_IOC: u32 = 1 << 12;

/// PS GPIO (LPD), bank 3 = EMIO 0..31: masked write of the low half, and
/// direction / output enable.
const GPIO_MASK_DATA_3_LSW: usize = 0xFF0A_0018;
const GPIO_DIRM_3: usize = 0xFF0A_02C4;
const GPIO_OEN_3: usize = 0xFF0A_02C8;
const STROBE_BIT: u32 = 1 << 1;

const LOOP_TICKS: u64 = TICK_HZ / 10_000;
const MS: u64 = TICK_HZ / 1000;
/// Ring entries moved per loop, so a burst from Linux does not hold the scan.
const RING_BURST: u32 = 64;

#[no_mangle]
fn on_panic() {}

/// One grid frame's progress.
#[derive(Clone, Copy, PartialEq, Eq)]
enum Frame {
    Idle,
    Decay,
    Dump,
    InFlight,
}

fn strobe(level: bool) {
    // [31:16] mask: 0 = this bit is written
    wr(GPIO_MASK_DATA_3_LSW, (!STROBE_BIT & 0xFFFF) << 16 | if level { STROBE_BIT } else { 0 });
}

/// The grid's command port, with a count of free queue slots so STATUS is
/// read only when it may be full.
struct GridPort {
    credits: u32,
    pushed: u32,
    full: u32,
}

impl GridPort {
    fn push(&mut self, c: Command) -> bool {
        if self.credits == 0 {
            let st = rd(BEV + bev::reg::STATUS);
            self.credits = bev::reg::QUEUE - bev::reg::level(st);
            if self.credits == 0 {
                self.full += 1;
                return false;
            }
        }
        wr(BEV + bev::reg::DET_XY, c.xy());
        wr(BEV + bev::reg::DET_CMD, c.cmd());
        self.credits -= 1;
        self.pushed += 1;
        true
    }
}

fn ring_rd(off: usize) -> u32 {
    rd(ring::BASE as usize + off)
}

#[no_mangle]
pub extern "C" fn main_entry() -> ! {
    let mut cfg = Core1Config::default();
    let mut cfg_seq = u32::MAX;
    let mut sched = Scheduler::new(cfg.radar);
    let mut grid = Grid { cell_cm: cfg.cell_cm };
    let mut port = GridPort { credits: 0, pushed: 0, full: 0 };
    let mut st = Core1Status { grid_ok: rd(BEV + bev::reg::ID) == bev::reg::ID_BEV1, ..Default::default() };
    let mut seq = 0u32;
    let mut tail = ring_rd(ring::OFF_TAIL);
    let mut last_cpi_move = 0u64;
    let mut last_stat = u32::MAX;
    let mut frame_due = 0u64;
    let mut frame = Frame::Idle;
    let mut next_buf = 0u8;
    let mut running = false;
    let mut scanning = false;

    // EMIO GPIO 1 an output, low.
    strobe(false);
    wr(GPIO_DIRM_3, rd(GPIO_DIRM_3) | STROBE_BIT);
    wr(GPIO_OEN_3, rd(GPIO_OEN_3) | STROBE_BIT);

    // axi_dma_1: reset, then run.
    wr(S2MM_DMACR, DMACR_RESET);
    while rd(S2MM_DMACR) & DMACR_RESET != 0 {}
    wr(S2MM_DMACR, DMACR_RS);

    let mut next = now();
    let mut next_ms = next;
    loop {
        while now() < next {}
        next += LOOP_TICKS;
        let t = now();

        // --- configuration and Linux's heartbeat, once a millisecond
        let tick_ms = t >= next_ms;
        if tick_ms {
            next_ms += MS;
            if let Some(c) = hw::read_stable::<{ mailbox::CONFIG_LEN }>(mailbox::CORE1_CONFIG)
                .and_then(|b| mailbox::decode_core1_config(&b).map(|c| (c, u32::from_le_bytes([b[4], b[5], b[6], b[7]]))))
            {
                let (c, s) = c;
                if s != cfg_seq {
                    if c.radar != cfg.radar {
                        // Linux restarts the Artix's scan (ADAR_CTRL[13] off and on) with a new one,
                        // so the first strobe loads beam 0 again.
                        sched = Scheduler::new(c.radar);
                    }
                    cfg = c;
                    cfg_seq = s;
                    grid = Grid { cell_cm: cfg.cell_cm.max(1) };
                }
                cfg.heartbeat = c.heartbeat;
            }
            running = t.saturating_sub(cfg.heartbeat) < TICK_HZ;
        }
        let scan = running && cfg.scan;
        let feed = running && cfg.grid && st.grid_ok;
        if scan && !scanning {
            sched = Scheduler::new(cfg.radar); // resumed: Linux has restarted the Artix's scan
        }
        scanning = scan;

        // --- radar
        if scan {
            let reg = rd(RADAR_STAT);
            if reg >> 26 != last_stat >> 26 {
                last_cpi_move = t;
            }
            last_stat = reg;
            let step = sched.poll(reg);
            if step.strobe {
                strobe(true);
                dmb();
                let _ = rd(GPIO_MASK_DATA_3_LSW); // the write has landed: >= 3 link_clk cycles high
                strobe(false);
            }
            if let (true, Some(d)) = (feed, step.detection) {
                let (x, y) = cfg.mount.to_vehicle(d.range_cm, d.az_cdeg as i32);
                if let Some((cx, cy)) = grid.to_cells(x, y) {
                    port.push(Command::detect(Sensor::Radar10, cx, cy));
                }
            }
        }
        st.radar_ok = t.saturating_sub(last_cpi_move) < 100 * MS && last_cpi_move != 0;

        // --- Linux's commands
        if feed {
            let head = ring_rd(ring::OFF_HEAD);
            dmb();
            let mut n = 0;
            while ring::pending(head, tail) > 0 && n < RING_BURST {
                let at = ring::slot(tail);
                let c = Command((ring_rd(at + 4) as u64) << 32 | ring_rd(at) as u64);
                if !port.push(c) {
                    break;
                }
                tail = tail.wrapping_add(1);
                n += 1;
            }
            if n > 0 {
                dmb();
                wr(ring::BASE as usize + ring::OFF_TAIL, tail);
            }
        }

        // --- frames: arm the DMA on a free buffer, decay, dump; publish when the DMA is done
        frame = match frame {
            Frame::Idle if feed && cfg.frame_ms > 0 && t >= frame_due => {
                frame_due = t + cfg.frame_ms as u64 * MS;
                let sr = rd(S2MM_DMASR);
                if sr & (DMASR_IDLE | DMASR_HALTED) != 0 || sr == 0 {
                    let buf = mailbox::FRAMES + next_buf as u64 * bev::FRAME_BYTES as u64;
                    wr(S2MM_DA, buf as u32);
                    wr(S2MM_DA_MSB, (buf >> 32) as u32);
                    wr(S2MM_LENGTH, bev::FRAME_BYTES as u32);
                    Frame::Decay
                } else {
                    Frame::Idle
                }
            }
            Frame::Decay if port.push(Command::decay()) => Frame::Dump,
            Frame::Dump if port.push(Command::dump()) => Frame::InFlight,
            Frame::InFlight => {
                let sr = rd(S2MM_DMASR);
                if sr & DMASR_IOC != 0 {
                    wr(S2MM_DMASR, DMASR_IOC);
                    st.frame = next_buf;
                    st.frame_seq = st.frame_seq.wrapping_add(1);
                    next_buf ^= 1;
                    Frame::Idle
                } else if sr & DMASR_ERR != 0 {
                    wr(S2MM_DMACR, DMACR_RESET);
                    while rd(S2MM_DMACR) & DMACR_RESET != 0 {}
                    wr(S2MM_DMACR, DMACR_RS);
                    st.dma_errors = st.dma_errors.wrapping_add(1);
                    Frame::Idle
                } else {
                    Frame::InFlight
                }
            }
            f => f,
        };

        // --- status, once a millisecond
        if tick_ms {
            st.cpis = sched.cpis;
            st.missed = sched.missed;
            st.strobes = sched.strobes;
            st.hits = sched.hits;
            st.beam = sched.beam();
            st.ring_tail = tail;
            st.pushed = port.pushed;
            st.grid_full = port.full;
            st.heartbeat = t;
            let m = st;
            hw::write_stable(mailbox::CORE1_STATUS, &mut seq, |s| mailbox::encode_core1_status(&m, s));
        }
    }
}
