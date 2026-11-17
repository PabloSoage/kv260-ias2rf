//! Register maps of the PL blocks, and the driver sequences that run them. The sequences are written against a
//! small trait so that the same code drives the hardware (`/dev/mem` on the KV260) or a recording of what it
//! would do (the end-to-end test hands the recording to the RTL bench).

/// Base addresses on `M_AXI_HPM0_LPD` (fpga/kria/bd.tcl).
pub const DOA_BASE: u64 = 0x8005_0000;
pub const DMA2_BASE: u64 = 0x8006_0000;
pub const SWEEP_BASE: u64 = 0x8007_0000;
pub const DMA3_BASE: u64 = 0x8008_0000;

pub mod doa {
    pub const ID: u64 = 0x0000;
    pub const CTRL: u64 = 0x0004;
    pub const STATUS: u64 = 0x0008;
    pub const N_LOG2: u64 = 0x000C;
    pub const SHIFT: u64 = 0x0010;
    pub const W0: u64 = 0x0020;
    pub const R0: u64 = 0x0100;
    pub const P0: u64 = 0x0800;
    pub const TAB: u64 = 0x8000;
    pub const ID_VALUE: u32 = 0x444F_4131;
}

pub mod sweep {
    pub const ID: u64 = 0x000;
    pub const STATUS: u64 = 0x004;
    pub const BLOCKS: u64 = 0x008;
    pub const BAD: u64 = 0x00C;
    pub const PSHIFT: u64 = 0x010;
    pub const NSEG_LOG2: u64 = 0x014;
    pub const WIN: u64 = 0x400;
    pub const TWD: u64 = 0x800;
    pub const ID_VALUE: u32 = 0x5357_5031;
}

pub trait Regs {
    fn write(&mut self, off: u64, v: u32);
    fn read(&mut self, off: u64) -> u32;
}

/// kria_doa: weights and table, then one CPI: accumulate, read the diagonal, pick SHIFT, scan.
pub fn doa_setup<R: Regs>(r: &mut R, w: &[u32; 5], table: &[[u32; 10]], n_log2: u32) {
    assert_eq!(r.read(doa::ID), doa::ID_VALUE, "kria_doa not found");
    for (k, &v) in w.iter().enumerate() {
        r.write(doa::W0 + 4 * k as u64, v);
    }
    for (m, row) in table.iter().enumerate() {
        for (p, &v) in row.iter().enumerate() {
            r.write(doa::TAB + 64 * m as u64 + 4 * p as u64, v);
        }
    }
    r.write(doa::N_LOG2, n_log2);
}

/// Reads the 15 covariance entries as 48-bit numbers.
pub fn doa_read_r<R: Regs>(r: &mut R) -> ([i64; 15], [i64; 15]) {
    let mut re = [0i64; 15];
    let mut im = [0i64; 15];
    let rd48 = |r: &mut R, a: u64| -> i64 { (r.read(a) as u64 | ((r.read(a + 4) as u64) << 32)) as i64 };
    for e in 0..15u64 {
        re[e as usize] = rd48(r, doa::R0 + 16 * e);
        im[e as usize] = rd48(r, doa::R0 + 16 * e + 8);
    }
    (re, im)
}

pub fn doa_read_p<R: Regs>(r: &mut R) -> Vec<i32> {
    (0..360u64).map(|m| r.read(doa::P0 + 4 * m) as i32).collect()
}

pub fn sweep_setup<R: Regs>(r: &mut R, win: &[u16], twd: &[u32], pshift: u32, nseg_log2: u32) {
    assert_eq!(r.read(sweep::ID), sweep::ID_VALUE, "kria_sweep not found");
    for (i, &v) in win.iter().enumerate() {
        r.write(sweep::WIN + 4 * i as u64, v as u32);
    }
    for (k, &v) in twd.iter().enumerate() {
        r.write(sweep::TWD + 4 * k as u64, v);
    }
    r.write(sweep::PSHIFT, pshift);
    r.write(sweep::NSEG_LOG2, nseg_log2);
}

/// The hardware: the PL's registers mapped through `/dev/mem`.
#[cfg(feature = "hw")]
pub mod devmem {
    use std::fs::OpenOptions;
    use std::os::unix::io::AsRawFd;

    extern "C" {
        fn mmap(addr: *mut u8, len: usize, prot: i32, flags: i32, fd: i32, off: i64) -> *mut u8;
    }

    pub struct DevMem {
        p: *mut u8,
        _f: std::fs::File,
    }

    impl DevMem {
        pub fn open(base: u64, len: usize) -> std::io::Result<DevMem> {
            let f = OpenOptions::new().read(true).write(true).open("/dev/mem")?;
            // PROT_READ | PROT_WRITE, MAP_SHARED
            let p = unsafe { mmap(core::ptr::null_mut(), len, 3, 1, f.as_raw_fd(), base as i64) };
            if p as isize == -1 {
                return Err(std::io::Error::last_os_error());
            }
            Ok(DevMem { p, _f: f })
        }
    }

    impl super::Regs for DevMem {
        fn write(&mut self, off: u64, v: u32) {
            unsafe { core::ptr::write_volatile(self.p.add(off as usize) as *mut u32, v) }
        }
        fn read(&mut self, off: u64) -> u32 {
            unsafe { core::ptr::read_volatile(self.p.add(off as usize) as *const u32) }
        }
    }
}

/// A recording of the register writes, for the RTL bench (address, data per line).
#[derive(Default)]
pub struct Recorder {
    pub writes: Vec<(u64, u32)>,
    pub id: u32,
}

impl Regs for Recorder {
    fn write(&mut self, off: u64, v: u32) {
        self.writes.push((off, v));
    }
    fn read(&mut self, _off: u64) -> u32 {
        self.id
    }
}
