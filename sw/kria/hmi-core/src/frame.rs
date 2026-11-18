//! The DMA blocks that `kria_ps_framer` writes into DDR (FPGA_GATEWARE §5.10).
//!
//! A block is what one S2MM transfer brought: whole packets, each behind two header words,
//!
//! ```text
//! word 0 = {0xA5, tid, flags, 0x00, words[15:0], seq[15:0]}   flags bit 0: CRC error, bit 1: from the DSP suite
//! word 1 = pl_clk_100m ticks when the packet's last word arrived (10 ns)
//! ```
//!
//! then `words` payload words. A flush packet (tid 0, no payload) ends a block that waited too long.

pub const MAGIC: u8 = 0xA5;

/// Stream ids (LINK_PROTOCOL §6.2, FPGA_GATEWARE §5.1 and §5.10).
pub mod tid {
    pub const FLUSH: u8 = 0x00;
    pub const RADAR_IQ: u8 = 0x01; // AD9484 DDC, 25 MSPS: the radar, or VHF/UHF reception
    pub const SDR_A: u8 = 0x04; // AD9253 channel A
    pub const SDR_B: u8 = 0x05; // AD9253 channel B (HF, J951)
    pub const ARTIX_STATUS: u8 = 0x11;
    pub const AUDIO: u8 = 0x20;
    pub const ADSB: u8 = 0x21;
    pub const RADAR_DET: u8 = 0x22;
    pub const RADAR_MAP: u8 = 0x23;
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Packet<'a> {
    pub tid: u8,
    pub crc_error: bool,
    pub from_dsp: bool,
    pub seq: u16,
    pub time: u64,
    pub words: &'a [u64],
}

#[derive(Debug, Default, Clone, Copy, PartialEq, Eq)]
pub struct BlockStats {
    pub packets: u32,
    pub flushes: u32,
    /// Words skipped while looking for a header (a damaged block).
    pub resync_words: u32,
    /// Packets missing by sequence number, counted against the previous block's last packet too.
    pub seq_gaps: u32,
}

/// Walks a block, calling `f` for every packet but the flushes. `last_seq` carries the sequence across blocks.
pub fn parse_block(block: &[u64], last_seq: &mut Option<u16>, mut f: impl FnMut(Packet)) -> BlockStats {
    let mut st = BlockStats::default();
    let mut i = 0;
    while i + 2 <= block.len() {
        let h = block[i];
        if (h >> 56) as u8 != MAGIC || ((h >> 32) & 0xFF) != 0 {
            st.resync_words += 1;
            i += 1;
            continue;
        }
        let tid = (h >> 48) as u8;
        let flags = (h >> 40) as u8;
        let n = ((h >> 16) & 0xFFFF) as usize;
        let seq = h as u16;
        if i + 2 + n > block.len() {
            st.resync_words += (block.len() - i) as u32;
            break;
        }
        if let Some(prev) = *last_seq {
            let gap = seq.wrapping_sub(prev.wrapping_add(1));
            if gap != 0 && gap < 0x8000 {
                st.seq_gaps += gap as u32;
            }
        }
        *last_seq = Some(seq);
        if tid == tid::FLUSH && n == 0 {
            st.flushes += 1;
        } else {
            st.packets += 1;
            f(Packet {
                tid,
                crc_error: flags & 1 != 0,
                from_dsp: flags & 2 != 0,
                seq,
                time: block[i + 1],
                words: &block[i + 2..i + 2 + n],
            });
        }
        i += 2 + n;
    }
    st
}

/// The framer's encoding of one packet, for the simulated platform and the tests.
pub fn encode_packet(out: &mut Vec<u64>, tid: u8, flags: u8, seq: u16, time: u64, words: &[u64]) {
    out.push(
        (MAGIC as u64) << 56 | (tid as u64) << 48 | (flags as u64) << 40 | (words.len() as u64 & 0xFFFF) << 16 | seq as u64,
    );
    out.push(time);
    out.extend_from_slice(words);
}

/// The 16-bit I/Q samples of a link stream packet: each word {Q1, I1, Q0, I0}.
pub fn iq_samples(words: &[u64], out: &mut Vec<(i16, i16)>) {
    for &w in words {
        out.push((w as i16, (w >> 16) as i16));
        out.push(((w >> 32) as i16, (w >> 48) as i16));
    }
}

pub fn iq_words(samples: &[(i16, i16)]) -> Vec<u64> {
    samples
        .chunks(2)
        .map(|c| {
            let (i0, q0) = c[0];
            let (i1, q1) = *c.get(1).unwrap_or(&(0, 0));
            (i0 as u16 as u64) | (q0 as u16 as u64) << 16 | (i1 as u16 as u64) << 32 | (q1 as u16 as u64) << 48
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn round_trip_with_flush_damage_and_gap() {
        let mut b = Vec::new();
        encode_packet(&mut b, tid::AUDIO, 2, 7, 100, &[1, 2, 3]);
        b.push(0xDEAD_BEEF); // damage between packets
        encode_packet(&mut b, tid::ADSB, 2, 9, 200, &[4, 5]); // seq 8 missing
        encode_packet(&mut b, tid::FLUSH, 0, 10, 300, &[]);
        let mut got = Vec::new();
        let mut last = Some(6);
        let st = parse_block(&b, &mut last, |p| got.push((p.tid, p.seq, p.time, p.words.to_vec(), p.from_dsp)));
        assert_eq!(got, vec![(0x20, 7, 100, vec![1, 2, 3], true), (0x21, 9, 200, vec![4, 5], true)]);
        assert_eq!(st, BlockStats { packets: 2, flushes: 1, resync_words: 1, seq_gaps: 1 });
        assert_eq!(last, Some(10));
    }

    #[test]
    fn iq_packing_matches_the_link() {
        let s = vec![(1, -2), (300, -400), (-5, 6)];
        let mut back = Vec::new();
        iq_samples(&iq_words(&s), &mut back);
        assert_eq!(&back[..3], &s[..]);
    }
}
