//! The KV260 (feature `hw`, Linux): registers through /dev/mem, the PS-bound blocks through axi_dma_0's S2MM
//! channel into a u-dma-buf buffer, Artix commands through its MM2S channel, the R5F's state from the mailbox.
//!
//! Addresses are the block design's (FPGA_GATEWARE §3.3, `sw/ias2rf_pl.dtsi`): `kria_pl_link` at 0x8000_0000,
//! `axi_dma_0` at 0x8001_0000, the mailbox at 0x3EE0_0000. The DMA runs in simple mode: arm S2MM with the
//! largest block the framer makes (69,648 bytes), wait for it to go idle, read S2MM_LENGTH, re-arm; the framer's
//! 32 KiB FIFO covers the gap. Audio goes to `aplay` (raw S16_LE, stereo) on stdin. Not run on a board yet.

use kria_core::mailbox;
use kria_hmi_core::modes::Write;
use std::fs::{File, OpenOptions};
use std::io::Write as _;
use std::os::unix::fs::FileExt;
use std::process::{Child, Command, Stdio};

const LINK: u64 = 0x8000_0000;
const DMA: u64 = 0x8001_0000;
const REG_TX_AXIS_SID: usize = 0x34;
const S2MM_CR: usize = 0x30;
const S2MM_SR: usize = 0x34;
const S2MM_DA: usize = 0x48;
const S2MM_DA_MSB: usize = 0x4C;
const S2MM_LENGTH: usize = 0x58;
const MM2S_CR: usize = 0x00;
const MM2S_SR: usize = 0x04;
const MM2S_SA: usize = 0x18;
const MM2S_SA_MSB: usize = 0x1C;
const MM2S_LENGTH: usize = 0x28;
const BLOCK_BYTES: u32 = 69_648;

struct Map {
    p: *mut u32,
    len: usize,
}

impl Map {
    fn new(f: &File, phys: u64, len: usize) -> std::io::Result<Self> {
        use std::os::unix::io::AsRawFd;
        let p = unsafe {
            libc::mmap(std::ptr::null_mut(), len, libc::PROT_READ | libc::PROT_WRITE, libc::MAP_SHARED, f.as_raw_fd(), phys as i64)
        };
        if p == libc::MAP_FAILED {
            return Err(std::io::Error::last_os_error());
        }
        Ok(Self { p: p as *mut u32, len })
    }
    fn rd(&self, off: usize) -> u32 {
        assert!(off + 4 <= self.len);
        unsafe { std::ptr::read_volatile(self.p.add(off / 4)) }
    }
    fn wr(&self, off: usize, v: u32) {
        assert!(off + 4 <= self.len);
        unsafe { std::ptr::write_volatile(self.p.add(off / 4), v) }
    }
}

pub struct Board {
    mem: File,
    link: Map,
    dma: Map,
    buf: Map,
    buf_phys: u64,
    armed: bool,
    aplay: Option<Child>,
    audio_rate: u32,
}

fn udmabuf_phys() -> std::io::Result<u64> {
    let s = std::fs::read_to_string("/sys/class/u-dma-buf/udmabuf0/phys_addr")?;
    u64::from_str_radix(s.trim().trim_start_matches("0x"), 16).map_err(|e| std::io::Error::other(e.to_string()))
}

impl Board {
    pub fn open() -> std::io::Result<Self> {
        let mem = OpenOptions::new().read(true).write(true).open("/dev/mem")?;
        let link = Map::new(&mem, LINK, 0x1000)?;
        let dma = Map::new(&mem, DMA, 0x1000)?;
        let ub = OpenOptions::new().read(true).write(true).open("/dev/udmabuf0")?;
        let buf = Map::new(&ub, 0, 1 << 18)?; // 256 KiB: the block at 0, the command word at 128 KiB
        let buf_phys = udmabuf_phys()?;
        dma.wr(S2MM_CR, 1);
        dma.wr(MM2S_CR, 1);
        Ok(Self { mem, link, dma, buf, buf_phys, armed: false, aplay: None, audio_rate: 0 })
    }

    /// A finished block, or None while the current one is still filling.
    pub fn poll_block(&mut self) -> Option<Vec<u64>> {
        if !self.armed {
            self.dma.wr(S2MM_DA, self.buf_phys as u32);
            self.dma.wr(S2MM_DA_MSB, (self.buf_phys >> 32) as u32);
            self.dma.wr(S2MM_LENGTH, BLOCK_BYTES);
            self.armed = true;
            return None;
        }
        if self.dma.rd(S2MM_SR) & 0x2 == 0 {
            return None;
        }
        let n = (self.dma.rd(S2MM_LENGTH) / 8) as usize;
        let words: Vec<u64> = (0..n).map(|k| self.buf.rd(8 * k) as u64 | (self.buf.rd(8 * k + 4) as u64) << 32).collect();
        self.armed = false;
        Some(words)
    }

    pub fn write(&mut self, w: &Write) {
        match *w {
            // DSP_CTRL is written whole: its bit 1 only reads back TX_KEY (0x38), R5F core 0's own register
            Write::Kria { off, val } => self.link.wr(off as usize, val),
            Write::Artix { addr, val } => {
                // stream 0x10 command word {op 0x01 write, flags 0, addr, data} through MM2S (sw/ias2rf_dma_test.c)
                let word = 1u64 << 56 | (addr as u64) << 32 | val as u64;
                self.link.wr(REG_TX_AXIS_SID, 0x10);
                self.buf.wr(1 << 17, word as u32);
                self.buf.wr((1 << 17) + 4, (word >> 32) as u32);
                let pa = self.buf_phys + (1 << 17);
                self.dma.wr(MM2S_SA, pa as u32);
                self.dma.wr(MM2S_SA_MSB, (pa >> 32) as u32);
                self.dma.wr(MM2S_LENGTH, 8);
                for _ in 0..10_000 {
                    if self.dma.rd(MM2S_SR) & 0x2 != 0 {
                        break;
                    }
                    std::thread::sleep(std::time::Duration::from_micros(10));
                }
                if addr == kria_hmi_core::modes::artix_reg::FE_CMD {
                    std::thread::sleep(std::time::Duration::from_millis(30)); // fe_ctrl: about 26 ms a register
                }
            }
        }
    }

    pub fn play(&mut self, rate: f64, samples: &[i16]) {
        let r = rate.round() as u32;
        if r == 0 || samples.is_empty() {
            return;
        }
        if self.aplay.is_none() || r != self.audio_rate {
            if let Some(mut c) = self.aplay.take() {
                let _ = c.kill();
            }
            self.aplay = Command::new("aplay")
                .args(["-q", "-t", "raw", "-f", "S16_LE", "-c", "2", "-r", &r.to_string()])
                .stdin(Stdio::piped())
                .spawn()
                .ok();
            self.audio_rate = r;
        }
        if let Some(stdin) = self.aplay.as_mut().and_then(|c| c.stdin.as_mut()) {
            let bytes: Vec<u8> = samples.iter().flat_map(|s| s.to_le_bytes()).collect();
            let _ = stdin.write_all(&bytes);
        }
    }

    /// The R5F's interlock decision and link health (core 0's half of the mailbox).
    pub fn r5f(&self) -> Option<mailbox::FromR5f> {
        let mut b = [0u8; mailbox::HALF];
        self.mem.read_exact_at(&mut b, mailbox::BASE + mailbox::FROM_R5F as u64).ok()?;
        mailbox::decode_from_r5f(&b)
    }

    /// The screens' transmit request and licence for kria-vehicled, the mailbox's writer.
    pub fn tx_request(&self, request: bool, licensed: bool) {
        let _ = std::fs::create_dir_all("/run/kria-hmi");
        let _ = std::fs::write("/run/kria-hmi/tx", [if request { b'1' } else { b'0' }, if licensed { b'1' } else { b'0' }]);
    }

    pub fn link_up(&self) -> bool {
        self.link.rd(0x04) & 1 != 0
    }
}
