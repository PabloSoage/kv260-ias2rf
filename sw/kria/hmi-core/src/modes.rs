//! Tuning: from a frequency and a mode to the register writes that make the board receive it.
//!
//! * Below 31 MHz: AD9253 channel B (`J951`, the 30 MHz low-pass), the Artix's `sdr_ddc` NCO B (`0x48`, 2^32 f /
//!   62.5 MHz) and decimation by 4 (`0x4C`), stream 0x05 at 15.625 MS/s.
//! * 30-170 MHz: the RX_VU front end straight to the AD9484 (`VU_CONV_ON` low), preselector A on the FM band-pass
//!   (88-108 MHz) or the FM reject; the AERIS DDC's NCO through the radar NCO override (`RADAR_CTRL[2]`, a 24-bit
//!   word at 400 MHz in `[31:8]`), stream 0x01 at 25 MS/s.
//! * 300 MHz to 3 GHz: through the RFFC5072 converter to the 135 MHz IF (a high-pass in front of preselector B cuts
//!   the band below 300 MHz; 170-300 MHz is not covered). The LO sits above the signal up to 1 GHz, below it above
//!   (RFFC5072_PROGRAMMING §4.1), preselector B on the UHF low-pass, the 1090 MHz SAW, the 1 GHz high-pass, or the
//!   LFCN-1000+ 1 GHz low-pass (where the gateware forces `VU_LNA_ON` = 1).
//! The channel itself (`kria_channel_rx`) is set as the G-8 cases set it (FPGA_GATEWARE §6.1): CIC and FIR
//! decimation, de-emphasis, pilot, CTCSS and RDS words. The AERIS DDC delivers the conjugate spectrum and a high
//! LO inverts it again, so sidebands and the residual tuning offset are flipped when they need to be.

use serde::{Deserialize, Serialize};

pub const HF_FS: f64 = 62.5e6;
pub const HF_STREAM: f64 = 62.5e6 / 4.0;
pub const VU_FS: f64 = 400e6;
pub const VU_STREAM: f64 = 25e6;
pub const IF_HZ: f64 = 135e6;
pub const DIRECT_MAX_HZ: f64 = 170e6;
pub const CONVERTED_MIN_HZ: f64 = 300e6;

/// True when `freq_hz` is covered by the RF front end (170..300 MHz is excluded by the preselector-B 300 MHz high-pass).
pub fn is_covered(freq_hz: f64) -> bool {
    !(freq_hz > DIRECT_MAX_HZ && freq_hz < CONVERTED_MIN_HZ)
}

/// Gateware R3 rule: `VU_LNA_ON` (bit 5) is forced high whenever `VU_CONV_ON` (bit 6) = 1,
/// preselector A = B (`V2V1` = `2'b11`), and preselector B = LFCN-1000+ (`V1V2V3` = `3'b011`).
pub fn lna_forced_for_port0(p0: u8) -> bool {
    (p0 & 0x40) != 0 && (p0 & 0x03) == 0x03 && ((p0 >> 2) & 0x07) == 0x03
}

/// Effective U1313 port 0 byte after applying the gateware's R3 LNA-force rule.
pub fn effective_port0(p0: u8) -> u8 {
    if lna_forced_for_port0(p0) { p0 | 0x20 } else { p0 }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Mode {
    Am,
    Usb,
    Lsb,
    Nbfm,
    Wbfm,
    Adsb,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum Path {
    Hf,
    Direct,
    Converted,
}

/// A register write: to the Kria PL (`kria_pl_link`, byte offset) or to the Artix (through the 0x10 command stream).
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
pub enum Write {
    Kria { off: u32, val: u32 },
    Artix { addr: u16, val: u32 },
}

pub mod kria_reg {
    pub const DSP_CTRL: u32 = 0x40;
    pub const CH_NCO: u32 = 0x44;
    pub const CH_DECIM: u32 = 0x48;
    pub const CH_DEMOD: u32 = 0x4C;
    pub const CH_PILOT: u32 = 0x50;
    pub const CH_CTCSS: u32 = 0x54;
    pub const CH_CTCSS_THR: u32 = 0x58;
    pub const ADSB_CFG: u32 = 0x64;
    pub const TX_CAR: u32 = 0x70;
    pub const TX_TONE: u32 = 0x74;
    pub const TX_CFG: u32 = 0x78;
    pub const RADAR_ALPHA: u32 = 0x7C;
}

pub mod artix_reg {
    pub const SDR_NCO_B: u16 = 0x48;
    pub const SDR_DECIM: u16 = 0x4C;
    pub const RADAR_CTRL: u16 = 0xE4;
    pub const FE_CMD: u16 = 0x110;
}

/// DSP_CTRL bits beyond the mode: the results stream (bit 14) on, a radar map every 2^2 CPIs.
pub const DSP_OUT: u32 = 1 << 14 | 2 << 15;

#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct Plan {
    pub freq_hz: f64,
    pub mode: Mode,
    pub path: Path,
    pub covered: bool,
    pub lna_forced: bool,
    pub stream_rate: f64,
    pub audio_rate: f64,
    pub lo_hz: Option<f64>,
    pub inverted: bool,
    pub writes: Vec<Write>,
}

pub fn ftw32(f: f64, fs: f64) -> u32 {
    ((f / fs) * 4294967296.0).round() as i64 as u32
}

/// RFFC5072 bank-2 frequency registers for an LO (RFFC5072_PROGRAMMING §4.2), and PLLCPL.
pub fn rffc5072_regs(lo_hz: f64) -> ([(u8, u16); 3], u8) {
    let mut n_lo = 0;
    while lo_hz * 2f64.powi(n_lo) <= 2.7e9 && n_lo < 5 {
        n_lo += 1;
    }
    let fvco = lo_hz * 2f64.powi(n_lo);
    let presc: u32 = if fvco > 3.2e9 { 2 } else { 1 };
    let ntot = fvco / (26e6 * 2f64.powi(presc as i32));
    let mut n = ntot.floor() as u32;
    let mut frac = ((ntot - n as f64) * 16777216.0).round() as u32;
    if frac == 1 << 24 {
        n += 1;
        frac = 0;
    }
    (
        [(0x0F, (n << 7 | (n_lo as u32) << 4 | presc << 2) as u16), (0x10, (frac >> 8) as u16), (0x11, ((frac & 0xFF) << 8) as u16)],
        if presc == 2 { 3 } else { 2 },
    )
}

fn fe_cmd(op: u32, arg: u32) -> Write {
    Write::Artix { addr: artix_reg::FE_CMD, val: op << 28 | arg }
}

fn decim_word(cic: u32, fir: u32, n5: bool, gain_shift: i32) -> u32 {
    let stages = if n5 { 5.0 } else { 3.0 };
    let full = (stages * (cic as f64).log2()).round() as i32;
    let shift = (full - gain_shift).clamp(0, full.min(63)) as u32;
    fir << 24 | (shift | if n5 { 0x40 } else { 0 }) << 16 | cic
}

/// The plan for a frequency and mode; `gain_db` lifts the channel's level ahead of its 16-bit path (6 dB a step).
pub fn plan(freq_hz: f64, mode: Mode, gain_db: f64) -> Plan {
    let gain_shift = (gain_db / 6.02).round() as i32 + 4;
    let mut w = Vec::new();
    let covered = is_covered(freq_hz);
    let mut lna_forced = false;
    let (path, lo, inverted, stream, src) = if freq_hz < 31e6 {
        w.push(Write::Artix { addr: artix_reg::SDR_NCO_B, val: ftw32(freq_hz, HF_FS) });
        w.push(Write::Artix { addr: artix_reg::SDR_DECIM, val: 0x0040_0004 });
        (Path::Hf, None, false, HF_STREAM, 1u32)
    } else {
        let conv = freq_hz >= CONVERTED_MIN_HZ;
        let lo = if !conv {
            None
        } else if freq_hz <= 1e9 {
            Some(freq_hz + IF_HZ)
        } else {
            Some(freq_hz - IF_HZ)
        };
        let f_adc = if conv { IF_HZ } else { freq_hz };
        let nco = ((f_adc / VU_FS) * 16777216.0).round() as u32 & 0xFF_FFFF;
        // the DDC's conjugate spectrum, and once more for a high LO
        let inverted = !(conv && lo.unwrap() > freq_hz);
        let err = f_adc - nco as f64 * VU_FS / 16777216.0;
        w.push(Write::Artix { addr: artix_reg::RADAR_CTRL, val: nco << 8 | 0x5 });
        // front end: expander port 0 {bias off, converter, LNA, preselector B, preselector A}, port 1 idle lines
        let psa = if conv { 3 } else if (88e6..=108e6).contains(&freq_hz) { 1 } else { 2 };
        let psb = if !conv { 0 } else if (1080e6..=1100e6).contains(&freq_hz) { 1 } else if freq_hz > 1e9 { 2 } else { 0 };
        let p0_raw = (0x80 | (conv as u32) << 6 | 1 << 5 | psb << 2 | psa) as u8;
        lna_forced = lna_forced_for_port0(p0_raw);
        let p0 = effective_port0(p0_raw) as u32;
        let p1 = 0x62 | if conv { 0x80 } else { 0 };
        w.push(fe_cmd(2, p1 << 8 | p0));
        if let Some(lo) = lo {
            let (regs, pllcpl) = rffc5072_regs(lo);
            // 0x00 LF_CTRL: the power-on 0xFFFB with PLLCPL (bits 2:0) for the prescaler (RFFC5072_PROGRAMMING §3, §4)
            w.push(fe_cmd(4, 0x00 << 16 | 0xFFF8 | pllcpl as u32));
            for (r, v) in regs {
                w.push(fe_cmd(4, (r as u32) << 16 | v as u32));
            }
            // 0x09 PLL_CTRL: the power-on 0x8220 with TVCO = 31 (bits 10:6) and RELOK (bit 3): rerun the VCO selection
            w.push(fe_cmd(4, 0x09 << 16 | 0x87E8));
        }
        // the residual of the 24-bit NCO, taken out by the channel's own NCO
        w.push(Write::Kria { off: kria_reg::CH_NCO, val: ftw32(if inverted { -err } else { err }, VU_STREAM) });
        (if conv { Path::Converted } else { Path::Direct }, lo, inverted, VU_STREAM, 0u32)
    };
    let mode_eff = match (mode, inverted) {
        (Mode::Usb, true) => Mode::Lsb,
        (Mode::Lsb, true) => Mode::Usb,
        (m, _) => m,
    };
    let audio_rate;
    match mode {
        Mode::Adsb => {
            audio_rate = 0.0;
            w.push(Write::Kria { off: kria_reg::ADSB_CFG, val: 131 << 8 | 0x8C });
            w.push(Write::Kria { off: kria_reg::DSP_CTRL, val: 1 | src << 2 | 1 << 7 | DSP_OUT });
        }
        _ => {
            let (cic, fir, n5) = match (mode, path) {
                (Mode::Wbfm, _) => (25, 4, false),
                (Mode::Nbfm, Path::Hf) => (390, 2, false),
                (Mode::Nbfm, _) => (640, 2, false),
                (Mode::Am, Path::Direct) | (Mode::Am, Path::Converted) => (1040, 2, true),
                (_, Path::Hf) => (651, 2, false),
                _ => (1040, 2, true),
            };
            audio_rate = stream / cic as f64 / fir as f64;
            if path == Path::Hf {
                w.push(Write::Kria { off: kria_reg::CH_NCO, val: 0 });
            }
            w.push(Write::Kria { off: kria_reg::CH_DECIM, val: decim_word(cic, fir, n5, gain_shift) });
            let code = match mode_eff {
                Mode::Am => 0,
                Mode::Usb => 1,
                Mode::Lsb => 2,
                Mode::Nbfm => 3,
                _ => 4,
            };
            let alpha = |tau: f64| ((1.0 - (-1.0 / (audio_rate * tau)).exp()) * 32768.0).round() as u32;
            let c2cos = |f: f64| (((2.0 * std::f64::consts::PI * f / audio_rate).cos() * 2.0 * 16384.0).round() as i32 as u32) & 0xFFFF;
            match mode {
                Mode::Wbfm => {
                    w.push(Write::Kria { off: kria_reg::CH_DEMOD, val: c2cos(19e3) << 16 | alpha(50e-6) });
                    w.push(Write::Kria { off: kria_reg::CH_PILOT, val: ftw32(19e3, audio_rate) });
                    w.push(Write::Kria { off: kria_reg::CH_CTCSS, val: ((audio_rate / 1187.5 * 256.0).round() as u32) << 16 });
                }
                Mode::Nbfm => {
                    w.push(Write::Kria { off: kria_reg::CH_DEMOD, val: c2cos(100.0) << 16 | alpha(750e-6) });
                    w.push(Write::Kria { off: kria_reg::CH_CTCSS, val: (audio_rate * 0.1).round() as u32 });
                    w.push(Write::Kria { off: kria_reg::CH_CTCSS_THR, val: 26804 });
                }
                Mode::Am => w.push(Write::Kria { off: kria_reg::CH_DEMOD, val: 0x3000 }),
                _ => w.push(Write::Kria { off: kria_reg::CH_DEMOD, val: 0x4000 }),
            }
            w.push(Write::Kria { off: kria_reg::DSP_CTRL, val: 1 | src << 2 | code << 4 | DSP_OUT });
        }
    }
    Plan { freq_hz, mode, path, covered, lna_forced, stream_rate: stream, audio_rate, lo_hz: lo, inverted, writes: w }
}

/// The radar: the AD9484 at the 120 MHz IF, `kria_radar_proc` with the Hann window, CPIs on the Artix's marks.
pub fn radar_plan(alpha_q8: u16, floor: u16) -> Vec<Write> {
    vec![
        Write::Artix { addr: artix_reg::RADAR_CTRL, val: 0x9 }, // DDC on, the CPI mark in I[0], default NCO
        Write::Kria { off: kria_reg::RADAR_ALPHA, val: (floor as u32) << 16 | alpha_q8 as u32 },
        Write::Kria { off: kria_reg::DSP_CTRL, val: 1 | 1 << 8 | 1 << 9 | 1 << 13 | DSP_OUT },
    ]
}

/// Transmit settings (`kria_tx_mod`); keying is the R5F's (the interlock owns `DSP_CTRL[1]`).
pub fn tx_plan(carrier_hz: f64, tone_hz: f64, mod_param: u16, amp: u16) -> Vec<Write> {
    let fs = 25e6;
    vec![
        Write::Kria { off: kria_reg::TX_CAR, val: ftw32(carrier_hz, fs) },
        Write::Kria { off: kria_reg::TX_TONE, val: ftw32(tone_hz, fs) },
        Write::Kria { off: kria_reg::TX_CFG, val: (amp as u32) << 16 | mod_param as u32 },
    ]
}

#[cfg(test)]
mod tests {
    use super::*;

    fn kria(p: &Plan, off: u32) -> Option<u32> {
        p.writes.iter().rev().find_map(|w| match *w {
            Write::Kria { off: o, val } if o == off => Some(val),
            _ => None,
        })
    }

    #[test]
    fn rffc_table_rows() {
        // RFFC5072_PROGRAMMING §4.1: PMR446 LO 581.1 MHz and ADS-B LO 955 MHz
        assert_eq!(rffc5072_regs(581.1e6).0, [(0x0F, 0x1638), (0x10, 0xB333), (0x11, 0x3300)]);
        assert_eq!(rffc5072_regs(955e6).0, [(0x0F, 0x1228), (0x10, 0xBB13), (0x11, 0xB100)]);
        assert_eq!(rffc5072_regs(2305e6).0, [(0x0F, 0x1618), (0x10, 0x53B1), (0x11, 0x3B00)]);
    }

    #[test]
    fn g8_cases_get_the_g8_channel_words() {
        let fm = plan(98.1e6, Mode::Wbfm, 0.0);
        assert_eq!(fm.path, Path::Direct);
        assert_eq!(fm.audio_rate, 250e3);
        assert_eq!(kria(&fm, kria_reg::DSP_CTRL).unwrap() & 0x3FFF, 0x41);
        assert_eq!(kria(&fm, kria_reg::CH_CTCSS), Some(0xD287 << 16)); // 210.53 samples per RDS bit, Q8.8
        let am = plan(7.2e6, Mode::Am, 0.0);
        assert_eq!(am.path, Path::Hf);
        assert_eq!(kria(&am, kria_reg::DSP_CTRL).unwrap() & 0x3FFF, 0x05);
        assert_eq!(kria(&am, kria_reg::CH_DECIM).unwrap() & 0xFFFF, 651);
        let usb = plan(14.2e6, Mode::Usb, 0.0);
        assert_eq!(kria(&usb, kria_reg::DSP_CTRL).unwrap() & 0x3FFF, 0x15);
        let pmr = plan(446.00625e6, Mode::Nbfm, 0.0);
        assert_eq!((pmr.path, pmr.lo_hz), (Path::Converted, Some(581.00625e6)));
        assert!(!pmr.inverted); // high LO flips the DDC's conjugate back
        assert_eq!(kria(&pmr, kria_reg::DSP_CTRL).unwrap() & 0x3FFF, 0x31);
        let ads = plan(1090e6, Mode::Adsb, 0.0);
        assert_eq!(ads.lo_hz, Some(955e6));
        assert_eq!(kria(&ads, kria_reg::ADSB_CFG), Some(0x838C));
        assert_eq!(kria(&ads, kria_reg::DSP_CTRL).unwrap() & 0x3FFF, 0x81);
    }

    #[test]
    fn sidebands_flip_where_the_spectrum_is() {
        // 2 m SSB direct: the DDC's conjugate spectrum makes USB an LSB demodulation
        let p = plan(144.3e6, Mode::Usb, 0.0);
        assert!(p.inverted);
        assert_eq!((kria(&p, kria_reg::DSP_CTRL).unwrap() >> 4) & 7, 2);
    }

    #[test]
    fn band_boundaries_and_lna_force_rule() {
        // Direct sampling stays 30-170 MHz; 170-300 MHz is not covered; converted starts at 300 MHz
        let direct = plan(170e6, Mode::Nbfm, 0.0);
        assert_eq!((direct.path, direct.covered, direct.lo_hz), (Path::Direct, true, None));
        let gap = plan(250e6, Mode::Nbfm, 0.0);
        assert!(!gap.covered);
        assert_eq!(gap.lo_hz, None);
        let conv = plan(300e6, Mode::Nbfm, 0.0);
        assert_eq!((conv.path, conv.covered, conv.lo_hz), (Path::Converted, true, Some(435e6)));

        // Gateware R3 rule: VU_CONV_ON=1, PSA=B(11), PSB=LFCN-1000+(011) forces VU_LNA_ON=1
        let raw_bypass: u8 = 0x80 | (1 << 6) | (0 << 5) | (3 << 2) | 3; // 0xCF
        assert!(lna_forced_for_port0(raw_bypass));
        assert_eq!(effective_port0(raw_bypass), raw_bypass | 0x20); // 0xEF
        let other_psb: u8 = 0x80 | (1 << 6) | (0 << 5) | (0 << 2) | 3; // UHF LPF
        assert!(!lna_forced_for_port0(other_psb));
        assert_eq!(effective_port0(other_psb), other_psb);
    }
}
