//! The bird's-eye-view fusion grid in the PL (`fpga/kria/kria_bev_axi.v`).
//!
//! The grid is 256 x 256 signed log-odds cells around the vehicle, x forward
//! and y left, the vehicle at cell (128, 128). This module turns what the
//! sensors report into the grid's commands and its configuration into register
//! words; the register writes themselves belong to whoever owns the grid (R5F
//! core 1, `sw/kria/r5f`).
//!
//! - [`Command`]: one 36-bit command (`DET_XY` + `DET_CMD`, or one beat of
//!   `s_axis_det`): a detection at a point, a decay pass, or a dump.
//! - [`Grid`]: cell size, and centimetres to Q8.8 cells.
//! - [`Mount`] and [`Mount::to_vehicle`]: a detection at a range and azimuth
//!   from a sensor to vehicle coordinates.
//! - [`Config`]: the per-sensor origin, hit, miss and ray-casting registers.
//!
//! The grid's own bench (`fpga/sim/tb_kria_bev_axi.v`) and the end-to-end run
//! (`examples/radar_grid.rs`) use these encodings.

/// The grid's four sensor slots (`s_tdata[33:32]`).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[repr(u8)]
pub enum Sensor {
    Lidar = 0,
    Radar77 = 1,
    /// The board's own 10.5 GHz radar, scanned by R5F core 1.
    Radar10 = 2,
    Spare = 3,
}

impl Sensor {
    pub fn from_u8(v: u8) -> Self {
        match v & 3 {
            0 => Sensor::Lidar,
            1 => Sensor::Radar77,
            2 => Sensor::Radar10,
            _ => Sensor::Spare,
        }
    }
}

const OP_DETECT: u64 = 0;
const OP_DECAY: u64 = 1;
const OP_DUMP: u64 = 2;

/// One command: `[15:0]` x and `[31:16]` y in signed Q8.8 cells from the
/// centre, `[33:32]` sensor, `[35:34]` operation.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Command(pub u64);

impl Command {
    pub fn detect(sensor: Sensor, x_q8: i16, y_q8: i16) -> Self {
        Command((OP_DETECT << 34) | ((sensor as u64) << 32) | ((y_q8 as u16 as u64) << 16) | (x_q8 as u16 as u64))
    }
    pub fn decay() -> Self {
        Command(OP_DECAY << 34)
    }
    pub fn dump() -> Self {
        Command(OP_DUMP << 34)
    }
    /// The `DET_XY` register word.
    pub fn xy(self) -> u32 {
        self.0 as u32
    }
    /// The `DET_CMD` register word, whose write pushes the command.
    pub fn cmd(self) -> u32 {
        ((self.0 >> 32) & 0xF) as u32
    }
    pub fn is_detect(self) -> bool {
        (self.0 >> 34) & 3 == OP_DETECT
    }
}

/// Register offsets in `kria_bev_axi`.
pub mod reg {
    pub const ID: usize = 0x00;
    pub const STATUS: usize = 0x04;
    pub const ORIGIN_X: usize = 0x08;
    pub const ORIGIN_Y: usize = 0x0C;
    pub const HIT: usize = 0x10;
    pub const MISS: usize = 0x14;
    pub const RAY: usize = 0x18;
    pub const DET_XY: usize = 0x1C;
    pub const DET_CMD: usize = 0x20;
    pub const COUNT: usize = 0x24;
    pub const ID_BEV1: u32 = 0x4245_5631;
    pub const ST_BUSY: u32 = 1 << 0;
    pub const ST_FULL: u32 = 1 << 1;
    pub const ST_OVERFLOW: u32 = 1 << 2;
    pub const ST_EMPTY: u32 = 1 << 3;
    /// Queue depth.
    pub const QUEUE: u32 = 512;
    pub fn level(status: u32) -> u32 {
        (status >> 16) & 0x3FF
    }
}

pub const SIZE: usize = 256;
/// Bytes in one dump: one signed byte per cell, address `{x, y}`.
pub const FRAME_BYTES: usize = SIZE * SIZE;

/// A cell of a dumped frame (x forward, y left, both 0..255, 128 = vehicle).
pub fn cell(frame: &[u8], x: u8, y: u8) -> i8 {
    frame[(x as usize) << 8 | y as usize] as i8
}

#[derive(Clone, Copy, Debug)]
pub struct Grid {
    /// Cell size in centimetres (50 gives 128 m x 128 m).
    pub cell_cm: u32,
}

impl Grid {
    /// Centimetres from the vehicle to Q8.8 cells, or `None` off the grid.
    pub fn to_cells(&self, x_cm: i32, y_cm: i32) -> Option<(i16, i16)> {
        let q = |v: i32| -> Option<i16> {
            let c = (v as i64 * 256) / self.cell_cm as i64;
            (-(128 * 256)..128 * 256).contains(&c).then_some(c as i16)
        };
        Some((q(x_cm)?, q(y_cm)?))
    }

    /// The cell a point in centimetres falls in (0..255), for a sensor origin.
    pub fn cell_of(&self, x_cm: i32, y_cm: i32) -> Option<(u8, u8)> {
        let (x, y) = self.to_cells(x_cm, y_cm)?;
        Some((((x >> 8) + 128) as u8, ((y >> 8) + 128) as u8))
    }
}

/// Where a sensor sits on the vehicle and where it points.
#[derive(Clone, Copy, Debug, Default)]
pub struct Mount {
    pub x_cm: i32,
    pub y_cm: i32,
    /// Boresight, 0.01 degree, counter-clockwise from forward (positive = left).
    pub yaw_cdeg: i32,
}

impl Mount {
    /// A detection at `range_cm` and `az_cdeg` (0.01 degree from the sensor's
    /// boresight, positive left) in vehicle centimetres.
    pub fn to_vehicle(&self, range_cm: u32, az_cdeg: i32) -> (i32, i32) {
        let a = (self.yaw_cdeg + az_cdeg) as f32 * (core::f32::consts::PI / 18_000.0);
        let (s, c) = sin_cos(a);
        let r = range_cm as f32;
        (self.x_cm + round(r * c), self.y_cm + round(r * s))
    }
}

fn round(v: f32) -> i32 {
    if v >= 0.0 {
        (v + 0.5) as i32
    } else {
        (v - 0.5) as i32
    }
}

/// sin and cos without libm: reduced to [-pi/4, pi/4], then Taylor to x^9 and
/// x^8 (error below 4e-9 there).
pub fn sin_cos(a: f32) -> (f32, f32) {
    use core::f32::consts::{FRAC_PI_2, PI};
    let tau = 2.0 * PI;
    let mut x = a - tau * floor(a / tau + 0.5);
    let q = floor(x / FRAC_PI_2 + 0.5) as i32; // -2..2
    x -= q as f32 * FRAC_PI_2;
    let x2 = x * x;
    let s = x * (1.0 - x2 / 6.0 * (1.0 - x2 / 20.0 * (1.0 - x2 / 42.0 * (1.0 - x2 / 72.0))));
    let c = 1.0 - x2 / 2.0 * (1.0 - x2 / 12.0 * (1.0 - x2 / 30.0 * (1.0 - x2 / 56.0)));
    match q.rem_euclid(4) {
        0 => (s, c),
        1 => (c, -s),
        2 => (-s, -c),
        _ => (-c, s),
    }
}

fn floor(v: f32) -> f32 {
    let t = v as i32 as f32;
    if t > v {
        t - 1.0
    } else {
        t
    }
}

/// The grid's configuration registers.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Config {
    /// Origin cell of each sensor (128 = the vehicle's centre).
    pub origin_x: [u8; 4],
    pub origin_y: [u8; 4],
    /// Log-odds added for a detection, 0..127.
    pub hit: [u8; 4],
    /// Log-odds removed from each cell a beam crossed, 0..127.
    pub miss: [u8; 4],
    pub ray: [bool; 4],
}

impl Config {
    /// `ORIGIN_X`, `ORIGIN_Y`, `HIT`, `MISS`, `RAY`, in register order from 0x08.
    pub fn regs(&self) -> [u32; 5] {
        let b8 = |v: [u8; 4]| u32::from_le_bytes(v);
        let b7 = |v: [u8; 4]| v.iter().enumerate().fold(0u32, |a, (k, &x)| a | ((x as u32 & 0x7F) << (7 * k)));
        let ray = self.ray.iter().enumerate().fold(0u32, |a, (k, &r)| a | ((r as u32) << k));
        [b8(self.origin_x), b8(self.origin_y), b7(self.hit), b7(self.miss), ray]
    }

    /// Put a sensor's origin at its mount.
    pub fn set_mount(&mut self, s: Sensor, grid: &Grid, m: &Mount) {
        let (x, y) = grid.cell_of(m.x_cm, m.y_cm).unwrap_or((128, 128));
        self.origin_x[s as usize] = x;
        self.origin_y[s as usize] = y;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn command_words_match_the_rtl_layout() {
        // x = +3.5 cells, y = -2 cells, sensor 2, detection
        let c = Command::detect(Sensor::Radar10, 0x0380, -0x0200);
        assert_eq!(c.0, 0x2_FE00_0380);
        assert_eq!(c.xy(), 0xFE00_0380);
        assert_eq!(c.cmd(), 0x2);
        assert!(c.is_detect());
        assert_eq!(Command::decay().cmd(), 0x4);
        assert_eq!(Command::dump().cmd(), 0x8);
        assert!(!Command::dump().is_detect());
    }

    #[test]
    fn grid_cells_and_edges() {
        let g = Grid { cell_cm: 50 };
        assert_eq!(g.to_cells(175, -100), Some((0x0380, -0x0200)));
        assert_eq!(g.cell_of(175, -100), Some((131, 126)));
        assert_eq!(g.to_cells(6399, 0).map(|c| c.0), Some(0x7FFA)); // 32,762.9 truncated
        assert_eq!(g.to_cells(6400, 0), None);
        assert_eq!(g.to_cells(0, -6400).map(|c| c.1), Some(-0x8000));
    }

    #[test]
    fn sin_cos_and_polar() {
        for k in -720..=720 {
            let a = k as f32 * 0.5 * core::f32::consts::PI / 180.0;
            let (s, c) = sin_cos(a);
            let (s0, c0) = (a as f64).sin_cos();
            assert!((s as f64 - s0).abs() < 2e-6 && (c as f64 - c0).abs() < 2e-6, "{} {} {}", k, s, s0);
        }
        // Radar on the front bumper, 3.8 m ahead of the centre, pointing forward: 20 m at 30 degrees left.
        let m = Mount { x_cm: 380, y_cm: 0, yaw_cdeg: 0 };
        assert_eq!(m.to_vehicle(2000, 3000), (380 + 1732, 1000));
        // Mounted 90 degrees left (a side radar): boresight 10 m is 10 m to the left.
        let m = Mount { x_cm: 0, y_cm: 90, yaw_cdeg: 9000 };
        assert_eq!(m.to_vehicle(1000, 0), (0, 1090));
    }

    #[test]
    fn config_registers() {
        let mut c = Config { hit: [12, 30, 20, 0], miss: [4, 0, 2, 0], ray: [true, false, true, false], ..Default::default() };
        c.set_mount(Sensor::Lidar, &Grid { cell_cm: 50 }, &Mount::default());
        c.set_mount(Sensor::Radar10, &Grid { cell_cm: 50 }, &Mount { x_cm: 380, y_cm: 0, yaw_cdeg: 0 });
        let r = c.regs();
        assert_eq!(r[0] & 0xFF, 128);
        assert_eq!((r[0] >> 16) & 0xFF, 135);
        assert_eq!(r[2], 12 | 30 << 7 | 20 << 14);
        assert_eq!(r[3], 4 | 2 << 14);
        assert_eq!(r[4], 0b0101);
    }

    #[test]
    fn frame_cell_addressing() {
        let mut f = [0u8; FRAME_BYTES];
        f[(131 << 8) | 126] = (-5i8) as u8;
        assert_eq!(cell(&f, 131, 126), -5);
    }
}
