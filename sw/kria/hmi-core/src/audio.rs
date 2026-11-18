//! Stream 0x20 (kria_dsp_out): demodulated audio from `kria_channel_rx`, and the RDS bits it recovers.
//!
//! Each word is `{flags[15:0], mono[15:0], right[15:0], left[15:0]}`; flags bit 0 is the 19 kHz pilot lock, bit 1
//! the CTCSS detector, bit 2 "an RDS bit came with this sample" and bit 3 that bit.
//!
//! RDS (IEC 62106): 26-bit blocks, 16 bits of information and a 10-bit check word, `g(x) = x^10 + x^8 + x^7 + x^5
//! + x^4 + x^3 + 1`, with an offset word per block position (A, B, C or C', D) added to the check. A group is four
//! blocks. The decoder looks for any valid block at every bit until it holds sync, then reads blocks in place
//! and drops sync after too many bad ones. It keeps the programme identification, the programme type, the eight-
//! character programme service name (groups 0A/0B) and the 64-character RadioText (2A; 32 for 2B).

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct AudioWord {
    pub left: i16,
    pub right: i16,
    pub mono: i16,
    pub pilot: bool,
    pub ctcss: bool,
    pub rds: Option<bool>,
}

pub fn decode(words: &[u64]) -> impl Iterator<Item = AudioWord> + '_ {
    words.iter().map(|&w| {
        let f = (w >> 48) as u16;
        AudioWord {
            left: w as i16,
            right: (w >> 16) as i16,
            mono: (w >> 32) as i16,
            pilot: f & 1 != 0,
            ctcss: f & 2 != 0,
            rds: if f & 4 != 0 { Some(f & 8 != 0) } else { None },
        }
    })
}

pub fn encode(a: &AudioWord) -> u64 {
    let f = a.pilot as u64 | (a.ctcss as u64) << 1 | (a.rds.is_some() as u64) << 2 | (a.rds == Some(true)) as u64 * 8;
    (a.left as u16 as u64) | (a.right as u16 as u64) << 16 | (a.mono as u16 as u64) << 32 | f << 48
}

const POLY: u32 = 0x5B9;
pub const OFFSET_A: u16 = 0x0FC;
pub const OFFSET_B: u16 = 0x198;
pub const OFFSET_C: u16 = 0x168;
pub const OFFSET_CP: u16 = 0x350;
pub const OFFSET_D: u16 = 0x1B4;

/// The 10-bit check word of 16 information bits, before the offset.
pub fn check(info: u16) -> u16 {
    let mut r = (info as u32) << 10;
    for bit in (10..26).rev() {
        if r & (1 << bit) != 0 {
            r ^= POLY << (bit - 10);
        }
    }
    r as u16
}

pub fn block(info: u16, offset: u16) -> u32 {
    (info as u32) << 10 | (check(info) ^ offset) as u32
}

/// A group's 104 bits, first bit first.
pub fn encode_group(blocks: [u16; 4], version_b: bool) -> Vec<bool> {
    let offs = [OFFSET_A, OFFSET_B, if version_b { OFFSET_CP } else { OFFSET_C }, OFFSET_D];
    let mut out = Vec::with_capacity(104);
    for (b, o) in blocks.iter().zip(offs) {
        let w = block(*b, o);
        for k in (0..26).rev() {
            out.push(w >> k & 1 != 0);
        }
    }
    out
}

#[derive(Clone, Debug, Default, PartialEq, Eq, serde::Serialize)]
pub struct RdsInfo {
    pub pi: Option<u16>,
    pub pty: Option<u8>,
    pub ps: String,
    pub radiotext: String,
    pub groups: u32,
    pub bad_blocks: u32,
}

pub struct RdsDecoder {
    reg: u32,
    nbits: u32,
    synced: bool,
    expect: usize, // 0 A, 1 B, 2 C/C', 3 D
    since: u32,
    bad_run: u32,
    group: [Option<u16>; 4],
    ps: [u8; 8],
    rt: [u8; 64],
    pub info: RdsInfo,
}

impl Default for RdsDecoder {
    fn default() -> Self {
        Self {
            reg: 0,
            nbits: 0,
            synced: false,
            expect: 0,
            since: 0,
            bad_run: 0,
            group: [None; 4],
            ps: [b' '; 8],
            rt: [b' '; 64],
            info: RdsInfo::default(),
        }
    }
}

impl RdsDecoder {
    /// The block position a 26-bit word is valid for: A 0, B 1, C or C' 2, D 3.
    fn which(w: u32) -> Option<usize> {
        match (w & 0x3FF) as u16 ^ check((w >> 10) as u16) {
            OFFSET_A => Some(0),
            OFFSET_B => Some(1),
            OFFSET_C | OFFSET_CP => Some(2),
            OFFSET_D => Some(3),
            _ => None,
        }
    }

    pub fn push(&mut self, bit: bool) {
        self.reg = (self.reg << 1 | bit as u32) & 0x3FF_FFFF;
        self.nbits = self.nbits.saturating_add(1);
        if self.nbits < 26 {
            return;
        }
        if !self.synced {
            if let Some(k) = Self::which(self.reg) {
                self.synced = true;
                self.expect = (k + 1) % 4;
                self.since = 0;
                self.bad_run = 0;
                self.group = [None; 4];
                self.group[k] = Some((self.reg >> 10) as u16);
            }
            return;
        }
        self.since += 1;
        if self.since < 26 {
            return;
        }
        self.since = 0;
        let pos = self.expect;
        match Self::which(self.reg) {
            Some(k) if k == pos => {
                self.group[pos] = Some((self.reg >> 10) as u16);
                self.bad_run = 0;
            }
            _ => {
                self.group[pos] = None;
                self.info.bad_blocks += 1;
                self.bad_run += 1;
                if self.bad_run >= 12 {
                    self.synced = false;
                }
            }
        }
        if pos == 3 {
            self.finish_group();
            self.group = [None; 4];
        }
        self.expect = (pos + 1) % 4;
    }

    fn finish_group(&mut self) {
        let [a, b, c, d] = self.group;
        if let Some(a) = a {
            self.info.pi = Some(a);
        }
        let Some(b) = b else { return };
        self.info.groups += 1;
        self.info.pty = Some(((b >> 5) & 0x1F) as u8);
        let gtype = b >> 12;
        let version_b = b & 0x800 != 0;
        match (gtype, version_b) {
            (0, _) => {
                if let Some(d) = d {
                    let seg = (b & 3) as usize;
                    self.ps[2 * seg] = (d >> 8) as u8;
                    self.ps[2 * seg + 1] = d as u8;
                    self.info.ps = String::from_utf8_lossy(&self.ps).trim_end().to_string();
                }
            }
            (2, false) => {
                let seg = (b & 0xF) as usize;
                for (k, w) in [c, d].iter().enumerate() {
                    if let Some(w) = w {
                        self.rt[4 * seg + 2 * k] = (*w >> 8) as u8;
                        self.rt[4 * seg + 2 * k + 1] = *w as u8;
                    }
                }
                self.update_rt();
            }
            (2, true) => {
                if let Some(d) = d {
                    let seg = (b & 0xF) as usize;
                    self.rt[2 * seg] = (d >> 8) as u8;
                    self.rt[2 * seg + 1] = d as u8;
                    self.update_rt();
                }
            }
            _ => {}
        }
    }

    fn update_rt(&mut self) {
        let end = self.rt.iter().position(|&c| c == 0x0D).unwrap_or(64);
        self.info.radiotext = String::from_utf8_lossy(&self.rt[..end]).trim_end().to_string();
    }
}

/// The groups that carry a station's name and text, as a transmitter cycles them (for the simulation).
pub fn station_groups(pi: u16, pty: u8, ps: &str, text: &str) -> Vec<Vec<bool>> {
    let mut g = Vec::new();
    let ps: Vec<u8> = format!("{ps:<8}").bytes().take(8).collect();
    for seg in 0..4u16 {
        let b = (pty as u16) << 5 | 0x0008 | seg; // 0A, TP 0, MS 1
        let d = (ps[2 * seg as usize] as u16) << 8 | ps[2 * seg as usize + 1] as u16;
        g.push(encode_group([pi, b, 0xE0CD, d], false));
    }
    let mut t: Vec<u8> = text.bytes().take(63).collect();
    t.push(0x0D);
    while t.len() % 4 != 0 {
        t.push(b' ');
    }
    for (seg, ch) in t.chunks(4).enumerate() {
        let b = 0x2000 | (pty as u16) << 5 | seg as u16;
        g.push(encode_group([pi, b, (ch[0] as u16) << 8 | ch[1] as u16, (ch[2] as u16) << 8 | ch[3] as u16], false));
    }
    g
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn audio_word_round_trip() {
        let a = AudioWord { left: -3, right: 4, mono: 1000, pilot: true, ctcss: false, rds: Some(true) };
        assert_eq!(decode(&[encode(&a)]).next().unwrap(), a);
    }

    #[test]
    fn check_word_is_a_cyclic_code() {
        // a valid block has zero syndrome against its own offset, and the code detects single-bit errors
        let w = block(0x1234, OFFSET_B);
        assert_eq!(RdsDecoder::which(w), Some(1));
        for k in 0..26 {
            assert_ne!(RdsDecoder::which(w ^ (1 << k)), Some(1));
        }
    }

    #[test]
    fn decodes_ps_and_radiotext_from_any_bit_phase() {
        let groups = station_groups(0xE2A1, 10, "KV260FM", "Rev08 in the car, 98.1 MHz");
        let mut dec = RdsDecoder::default();
        for b in [true, false, true, true, false] {
            dec.push(b); // junk ahead of the first block
        }
        for _ in 0..3 {
            for g in &groups {
                for &b in g {
                    dec.push(b);
                }
            }
        }
        assert_eq!(dec.info.pi, Some(0xE2A1));
        assert_eq!(dec.info.pty, Some(10));
        assert_eq!(dec.info.ps, "KV260FM");
        assert_eq!(dec.info.radiotext, "Rev08 in the car, 98.1 MHz");
        assert_eq!(dec.info.bad_blocks, 0);
    }
}
