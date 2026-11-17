//! The devices on the KV260's USB ports, through their C libraries (feature `hw`): KrakenRF's librtlsdr fork
//! for the KrakenSDR's five RTL2832U, and libhackrf for the HackRF Pro. Only the calls this daemon needs.
//!
//! Build on the KV260 (or with an aarch64 sysroot holding both libraries):
//! `cargo build --release -p kria-sdr --features hw`.

use std::ffi::{c_int, c_void, CString};

#[repr(C)]
pub struct RtlDev {
    _p: [u8; 0],
}
#[repr(C)]
pub struct HackrfDev {
    _p: [u8; 0],
}

#[repr(C)]
pub struct HackrfTransfer {
    pub device: *mut HackrfDev,
    pub buffer: *mut u8,
    pub buffer_length: c_int,
    pub valid_length: c_int,
    pub rx_ctx: *mut c_void,
    pub tx_ctx: *mut c_void,
}

pub type HackrfCb = extern "C" fn(*mut HackrfTransfer) -> c_int;

#[link(name = "rtlsdr")]
extern "C" {
    fn rtlsdr_get_index_by_serial(serial: *const i8) -> c_int;
    fn rtlsdr_open(dev: *mut *mut RtlDev, index: u32) -> c_int;
    fn rtlsdr_set_sample_rate(dev: *mut RtlDev, rate: u32) -> c_int;
    fn rtlsdr_set_center_freq(dev: *mut RtlDev, freq: u32) -> c_int;
    fn rtlsdr_set_tuner_gain_mode(dev: *mut RtlDev, manual: c_int) -> c_int;
    fn rtlsdr_set_tuner_gain(dev: *mut RtlDev, gain: c_int) -> c_int;
    fn rtlsdr_reset_buffer(dev: *mut RtlDev) -> c_int;
    fn rtlsdr_read_sync(dev: *mut RtlDev, buf: *mut c_void, len: c_int, n_read: *mut c_int) -> c_int;
    fn rtlsdr_set_bias_tee_gpio(dev: *mut RtlDev, gpio: c_int, on: c_int) -> c_int;
}

#[link(name = "hackrf")]
extern "C" {
    fn hackrf_init() -> c_int;
    fn hackrf_open(dev: *mut *mut HackrfDev) -> c_int;
    fn hackrf_set_sample_rate(dev: *mut HackrfDev, freq_hz: f64) -> c_int;
    fn hackrf_set_freq(dev: *mut HackrfDev, freq_hz: u64) -> c_int;
    fn hackrf_set_lna_gain(dev: *mut HackrfDev, v: u32) -> c_int;
    fn hackrf_set_vga_gain(dev: *mut HackrfDev, v: u32) -> c_int;
    fn hackrf_set_txvga_gain(dev: *mut HackrfDev, v: u32) -> c_int;
    fn hackrf_init_sweep(
        dev: *mut HackrfDev,
        freqs: *const u16,
        num_ranges: c_int,
        num_bytes: u32,
        step_width: u32,
        offset: u32,
        style: c_int,
    ) -> c_int;
    fn hackrf_start_rx_sweep(dev: *mut HackrfDev, cb: HackrfCb, ctx: *mut c_void) -> c_int;
    fn hackrf_start_tx(dev: *mut HackrfDev, cb: HackrfCb, ctx: *mut c_void) -> c_int;
    fn hackrf_stop_tx(dev: *mut HackrfDev) -> c_int;
}

fn ok(r: c_int, what: &str) -> std::io::Result<()> {
    if r < 0 {
        Err(std::io::Error::new(std::io::ErrorKind::Other, format!("{what}: {r}")))
    } else {
        Ok(())
    }
}

/// The KrakenSDR: five RTL devices by serial number (KrakenRF sets them to 1000..1004; 1000 is the control
/// channel, whose bias-tee GPIO 0 switches the noise source).
pub struct Kraken {
    pub dev: [*mut RtlDev; 5],
}

impl Kraken {
    pub fn open(freq_hz: u32, rate: u32, gain_tenth_db: i32) -> std::io::Result<Kraken> {
        let mut dev = [core::ptr::null_mut(); 5];
        for (k, d) in dev.iter_mut().enumerate() {
            let s = CString::new(format!("{}", 1000 + k)).unwrap();
            let idx = unsafe { rtlsdr_get_index_by_serial(s.as_ptr()) };
            ok(idx, "rtlsdr_get_index_by_serial")?;
            unsafe {
                ok(rtlsdr_open(d, idx as u32), "rtlsdr_open")?;
                ok(rtlsdr_set_sample_rate(*d, rate), "set_sample_rate")?;
                ok(rtlsdr_set_center_freq(*d, freq_hz), "set_center_freq")?;
                ok(rtlsdr_set_tuner_gain_mode(*d, 1), "set_tuner_gain_mode")?;
                ok(rtlsdr_set_tuner_gain(*d, gain_tenth_db), "set_tuner_gain")?;
                ok(rtlsdr_reset_buffer(*d), "reset_buffer")?;
            }
        }
        Ok(Kraken { dev })
    }
    pub fn noise_source(&mut self, on: bool) -> std::io::Result<()> {
        ok(unsafe { rtlsdr_set_bias_tee_gpio(self.dev[0], 0, on as c_int) }, "noise source")
    }
    /// One transfer from channel k (blocking); the daemon runs one thread per channel into the reassembler.
    pub fn read(&mut self, k: usize, buf: &mut [u8]) -> std::io::Result<usize> {
        let mut n: c_int = 0;
        ok(unsafe { rtlsdr_read_sync(self.dev[k], buf.as_mut_ptr() as *mut c_void, buf.len() as c_int, &mut n) }, "read_sync")?;
        Ok(n as usize)
    }
}

pub struct Hackrf {
    pub dev: *mut HackrfDev,
}

impl Hackrf {
    pub fn open() -> std::io::Result<Hackrf> {
        let mut dev = core::ptr::null_mut();
        unsafe {
            ok(hackrf_init(), "hackrf_init")?;
            ok(hackrf_open(&mut dev), "hackrf_open")?;
        }
        Ok(Hackrf { dev })
    }
    /// Sweep [f_min, f_max) MHz in INTERLEAVED style, one 16 KiB block per tuning, as hackrf_sweep does.
    pub fn sweep(&mut self, f_min_mhz: u16, f_max_mhz: u16, lna: u32, vga: u32, cb: HackrfCb, ctx: *mut c_void) -> std::io::Result<()> {
        let fr = [f_min_mhz, f_max_mhz];
        unsafe {
            ok(hackrf_set_sample_rate(self.dev, 20e6), "sample_rate")?;
            ok(hackrf_set_lna_gain(self.dev, lna), "lna")?;
            ok(hackrf_set_vga_gain(self.dev, vga), "vga")?;
            ok(hackrf_init_sweep(self.dev, fr.as_ptr(), 1, 16384, 20_000_000, 7_500_000, 1), "init_sweep")?;
            ok(hackrf_start_rx_sweep(self.dev, cb, ctx), "start_rx_sweep")
        }
    }
    pub fn tx_start(&mut self, freq_hz: u64, rate: f64, txvga: u32, cb: HackrfCb, ctx: *mut c_void) -> std::io::Result<()> {
        unsafe {
            ok(hackrf_set_sample_rate(self.dev, rate), "sample_rate")?;
            ok(hackrf_set_freq(self.dev, freq_hz), "freq")?;
            ok(hackrf_set_txvga_gain(self.dev, txvga), "txvga")?;
            ok(hackrf_start_tx(self.dev, cb, ctx), "start_tx")
        }
    }
    pub fn tx_stop(&mut self) -> std::io::Result<()> {
        ok(unsafe { hackrf_stop_tx(self.dev) }, "stop_tx")
    }
}
