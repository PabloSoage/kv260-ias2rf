//! End-to-end simulation of R5F core 1: the radar scan and the fusion grid's
//! command stream, from a scene.
//!
//! `cargo run --example radar_grid -- [OUT_DIR]` (default `fpga/sim/out/radar_grid`)
//!
//! What runs is `kria-core`'s code, in the order `sw/kria/r5f/src/bin/core1.rs`
//! runs it every 100 us: `radar::Scheduler::poll` on `RADAR_STAT`, the beam
//! strobe, each detection through `bev::Mount::to_vehicle` and
//! `bev::Grid::to_cells` into a `bev::Command`; then Linux's ring (the 77 GHz
//! radar's object list every 50 ms, pushed with `ring::has_room` and drained
//! 64 at a time); then a decay pass every 100 ms. Around it, models of what the
//! code talks to:
//!
//! - the Artix's beam scan (`ADAR_CTRL[13]`): each strobe loads the next beam,
//!   0 first; the CPI in progress then mixes two beams;
//! - `kria_radar_proc`: a CPI every 400 us (16 chirps of 20 us plus the FFTs);
//!   each target inside the loaded beam's 7.5 degree width gives 3 CFAR cells,
//!   and `RADAR_STAT` holds the CPI count and the strongest cell, at the map
//!   position the DDC's conjugate spectrum puts it (64 - r, 16 - d);
//! - the scene: a car ahead closing slowly, a pedestrian, a cyclist crossing
//!   from right to left, and a parked van; the 77 GHz radar sees the same
//!   objects with 20 cm of noise.
//!
//! It writes the grid bench's files (`bev_cfg.txt`, `bev_stim.hex`; the last
//! command is the one dump, at the end), and `trace.csv` (per CPI: time,
//! loaded beam, strobe, detection) for the figure. `radar_grid_replay.py`
//! turns the stimulus into the expected grid, and `tb_kria_bev_axi` runs it
//! through the RTL.

use kria_core::bev::{Command, Config, Grid, Mount, Sensor};
use kria_core::radar::{self, Scheduler, Stat};
use kria_core::ring;
use std::fmt::Write as _;
use std::io::Write as _;

const TICK_US: u64 = 100;
const CPI_US: u64 = 400;
const RUN_MS: u64 = 2000;
const BEAM_HALF_CDEG: i32 = 375;

#[derive(Clone, Copy)]
struct Target {
    /// Vehicle frame, metres, at t = 0, and velocity in m/s.
    x: f64,
    y: f64,
    vx: f64,
    vy: f64,
}

impl Target {
    fn at(&self, t: f64) -> (f64, f64) {
        (self.x + self.vx * t, self.y + self.vy * t)
    }
}

fn main() {
    let out = std::env::args().nth(1).unwrap_or_else(|| concat!(env!("CARGO_MANIFEST_DIR"), "/../../../fpga/sim/out/radar_grid").into());
    std::fs::create_dir_all(&out).unwrap();

    let scene = [
        Target { x: 34.0, y: 0.5, vx: -2.0, vy: 0.0 },   // car ahead, closing
        Target { x: 14.0, y: 5.0, vx: 0.0, vy: 0.0 },    // pedestrian on the left kerb
        Target { x: 22.0, y: -9.0, vx: 0.0, vy: 4.0 },   // cyclist crossing right to left
        Target { x: 9.0, y: -4.5, vx: 0.0, vy: 0.0 },    // parked van, front right
    ];
    let mount10 = Mount { x_cm: 380, y_cm: 0, yaw_cdeg: 0 };
    let mount77 = Mount { x_cm: 390, y_cm: 0, yaw_cdeg: 0 };
    let grid = Grid { cell_cm: 50 };
    let rcfg = radar::Config::default();
    let mut sched = Scheduler::new(rcfg);

    // Grid configuration as Linux writes it.
    let mut gcfg = Config { hit: [12, 30, 20, 0], miss: [4, 0, 0, 0], ray: [true, false, false, false], ..Default::default() };
    gcfg.set_mount(Sensor::Lidar, &grid, &Mount::default());
    gcfg.set_mount(Sensor::Radar77, &grid, &mount77);
    gcfg.set_mount(Sensor::Radar10, &grid, &mount10);
    gcfg.set_mount(Sensor::Spare, &grid, &Mount::default());

    // Artix and kria_radar_proc models.
    let mut artix_beam: Option<u8> = None; // nothing loaded before the first strobe
    let mut artix_next: u8 = 0;
    let mut cpi_beams: Vec<Option<u8>> = Vec::new(); // beams seen during the CPI in progress
    let mut cpi_count: u8 = 0;
    let mut stat = Stat { cpi: 0, detections: 0, peak_doppler: 0, peak_range: 0 };

    // Linux's ring (the shared-memory one, as a vector of slots and the two counters).
    let mut ring_mem = vec![0u64; ring::CAPACITY as usize];
    let (mut head, mut tail, mut drops) = (0u32, 0u32, 0u32);
    let mut rng = 0x1234_5678u32;
    let mut noise = || {
        rng ^= rng << 13;
        rng ^= rng >> 17;
        rng ^= rng << 5;
        (rng as f64 / u32::MAX as f64 - 0.5) * 0.4 // +-20 cm
    };

    let mut stim: Vec<Command> = Vec::new();
    let mut trace = String::from("t_ms,beam,strobe,range_cm,az_cdeg,doppler_bin,count\n");
    let mut n_det10 = 0;
    let mut n_det77 = 0;
    let mut n_decay = 0;
    let mut wrong = 0;

    let ticks = RUN_MS * 1000 / TICK_US;
    for k in 0..ticks {
        let t_us = k * TICK_US;
        let t = t_us as f64 * 1e-6;

        // --- kria_radar_proc: finish a CPI every CPI_US
        cpi_beams.push(artix_beam);
        if t_us > 0 && t_us % CPI_US == 0 {
            cpi_count = (cpi_count + 1) & 0x3F;
            let mut cells = 0u16;
            let mut best: Option<(f64, u8, u8)> = None;
            for tg in &scene {
                let (x, y) = tg.at(t);
                let dx = x - mount10.x_cm as f64 / 100.0;
                let r = (dx * dx + y * y).sqrt();
                let az = (y.atan2(dx).to_degrees() * 100.0) as i32;
                let rbin = (r * 100.0 / rcfg.range_bin_cm as f64).round() as i32;
                if !(1..64).contains(&rbin) {
                    continue;
                }
                // radial speed, positive approaching, in Doppler bins
                let vr = -(tg.vx * dx + tg.vy * y) / r;
                let dbin = ((vr * 100.0 / rcfg.doppler_bin_cms as f64).round() as i32).clamp(-8, 7);
                // A target counts if every beam loaded during the CPI covered it (a mixed CPI smears it: no cell).
                let seen = cpi_beams.iter().all(|b| match b {
                    Some(b) => (rcfg.az_cdeg[*b as usize] as i32 - az).abs() <= BEAM_HALF_CDEG,
                    None => false,
                });
                if seen {
                    cells += 3;
                    let p = 1.0 / (r * r);
                    if best.map_or(true, |(bp, _, _)| p > bp) {
                        let mr = ((64 - rbin) % 64) as u8;
                        let md = ((16 + 16 - dbin) % 16) as u8;
                        best = Some((p, mr, md));
                    }
                }
            }
            stat = Stat { cpi: cpi_count, detections: cells, peak_doppler: best.map_or(0, |b| b.2), peak_range: best.map_or(0, |b| b.1) };
            cpi_beams.clear();
        }

        // --- core 1, radar
        let step = sched.poll(stat.to_reg());
        if step.strobe {
            artix_beam = Some(artix_next);
            artix_next = if artix_next >= rcfg.beams - 1 { 0 } else { artix_next + 1 };
        }
        if let Some(d) = step.detection {
            let (x, y) = mount10.to_vehicle(d.range_cm, d.az_cdeg as i32);
            if let Some((cx, cy)) = grid.to_cells(x, y) {
                stim.push(Command::detect(Sensor::Radar10, cx, cy));
                n_det10 += 1;
            }
            // The reported beam must cover a real target at the reported range (one bin).
            let ok = scene.iter().any(|tg| {
                let (x, y) = tg.at(t);
                let dx = x - mount10.x_cm as f64 / 100.0;
                let r = (dx * dx + y * y).sqrt() * 100.0;
                let az = y.atan2(dx).to_degrees() * 100.0;
                (az - d.az_cdeg as f64).abs() <= BEAM_HALF_CDEG as f64 + 1.0
                    && (r - d.range_cm as f64).abs() <= rcfg.range_bin_cm as f64
            });
            if !ok {
                wrong += 1;
            }
            let _ = writeln!(trace, "{:.1},{},0,{},{},{},{}", t * 1e3, d.beam, d.range_cm, d.az_cdeg, d.doppler_bin, d.count);
        }
        if step.strobe {
            let _ = writeln!(trace, "{:.1},{},1,,,,", t * 1e3, sched.beam());
        }

        // --- Linux: the 77 GHz radar's object list every 50 ms, into the ring
        if t_us % 50_000 == 0 {
            for tg in &scene {
                let (x, y) = tg.at(t);
                let (xc, yc) = (((x + noise()) * 100.0) as i32, ((y + noise()) * 100.0) as i32);
                if let Some((cx, cy)) = grid.to_cells(xc, yc) {
                    if ring::has_room(head, tail) {
                        ring_mem[(head % ring::CAPACITY) as usize] = Command::detect(Sensor::Radar77, cx, cy).0;
                        head = head.wrapping_add(1);
                    } else {
                        drops += 1;
                    }
                }
            }
        }

        // --- core 1, ring drain (64 per loop)
        let mut n = 0;
        while ring::pending(head, tail) > 0 && n < 64 {
            stim.push(Command(ring_mem[(tail % ring::CAPACITY) as usize]));
            tail = tail.wrapping_add(1);
            n += 1;
            n_det77 += 1;
        }

        // --- core 1, frames: a decay pass every 100 ms (the bench takes one dump, at the end)
        if t_us > 0 && t_us % 100_000 == 0 {
            stim.push(Command::decay());
            n_decay += 1;
        }
    }
    stim.push(Command::dump());

    let mut f = std::fs::File::create(format!("{out}/bev_stim.hex")).unwrap();
    for c in &stim {
        writeln!(f, "{:09X}", c.0).unwrap();
    }
    let r = gcfg.regs();
    let unpack8 = |v: u32| (0..4).map(|k| ((v >> (8 * k)) & 0xFF).to_string()).collect::<Vec<_>>().join(" ");
    let unpack7 = |v: u32| (0..4).map(|k| ((v >> (7 * k)) & 0x7F).to_string()).collect::<Vec<_>>().join(" ");
    let ray = (0..4).map(|k| ((r[4] >> k) & 1).to_string()).collect::<Vec<_>>().join(" ");
    std::fs::write(
        format!("{out}/bev_cfg.txt"),
        format!("{}\n{}\n{}\n{}\n{}\n", unpack8(r[0]), unpack8(r[1]), unpack7(r[2]), unpack7(r[3]), ray),
    )
    .unwrap();
    std::fs::write(format!("{out}/trace.csv"), trace).unwrap();

    println!("radar_grid: {} s, {} CPIs ({} missed), {} strobes, {} CPIs with a detection", RUN_MS / 1000, sched.cpis, sched.missed, sched.strobes, sched.hits);
    println!("  commands: {} total, {} 10.5 GHz detections, {} 77 GHz objects through the ring ({} dropped), {} decay passes, 1 dump",
             stim.len(), n_det10, n_det77, drops, n_decay);
    println!("  detections not on a real target's beam and range: {wrong}");
    println!("  -> {out}");
    assert_eq!(wrong, 0, "a detection was reported on the wrong beam or range");
}
