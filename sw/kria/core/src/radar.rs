//! Radar scan scheduling, for R5F core 1.
//!
//! The 10.5 GHz radar steers its beam with eight ADAR1000s. The Artix holds
//! up to 32 beams' weights and, in scan mode (`ADAR_CTRL[13]`, Rev08), loads
//! the next of beams `0..=scan_last` on every `BEAM_STROBE`. The Kria's
//! `kria_radar_proc` turns each CPI (16 chirps of 64 samples) into a
//! range-Doppler map and CA-CFAR detections, and `RADAR_STAT` gives the CPI
//! count (modulo 64), the number of detections and the strongest cell.
//!
//! [`Scheduler::poll`] runs whenever R5F core 1 reads `RADAR_STAT`, much
//! faster than the CPI rate. On each new CPI it:
//!
//! - ignores the CPI if a strobe happened during it ([`Config::settle`] CPIs
//!   after each strobe, since part of it was on the previous beam);
//! - reports the CPI's strongest detection, if there was one, with the beam's
//!   azimuth and the bin turned into range and radial speed;
//! - dwells [`Config::dwell`] CPIs on a beam, plus [`Config::dwell_hit`] more
//!   for each CPI with detections, up to [`Config::dwell_max`], then strobes to
//!   the next beam. A beam with something in it is looked at longer, which is
//!   where the extra CPIs help most (non-coherent integration, track updates).
//!
//! CPIs that complete between two polls are counted in [`Scheduler::missed`];
//! only the last one's figures are in `RADAR_STAT`.

/// `RADAR_STAT` (`kria_dsp_suite` `0x7C`, read).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Stat {
    /// CPIs completed, modulo 64.
    pub cpi: u8,
    pub detections: u16,
    pub peak_doppler: u8,
    pub peak_range: u8,
}

impl Stat {
    pub fn from_reg(v: u32) -> Self {
        Stat {
            cpi: (v >> 26) as u8 & 0x3F,
            detections: (v >> 10) as u16,
            peak_doppler: (v >> 6) as u8 & 0xF,
            peak_range: v as u8 & 0x3F,
        }
    }
    pub fn to_reg(&self) -> u32 {
        (self.cpi as u32 & 0x3F) << 26
            | (self.detections as u32) << 10
            | (self.peak_doppler as u32 & 0xF) << 6
            | (self.peak_range as u32 & 0x3F)
    }
}

pub const RANGE_N: u8 = 64;
pub const DOPPLER_M: u8 = 16;
pub const MAX_BEAMS: usize = 32;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Config {
    /// Beams in the scan: the Artix's `scan_last` + 1.
    pub beams: u8,
    /// Azimuth of each beam, 0.01 degree, positive left of boresight.
    pub az_cdeg: [i16; MAX_BEAMS],
    pub dwell: u8,
    pub dwell_hit: u8,
    pub dwell_max: u8,
    pub settle: u8,
    /// Minimum `RADAR_STAT` detections for a CPI to count as a hit.
    pub min_det: u16,
    /// Range per bin, in centimetres (c / 2B for the chirp).
    pub range_bin_cm: u32,
    /// Radial speed per Doppler bin, in cm/s (lambda / (2 M PRI)).
    pub doppler_bin_cms: i32,
}

impl Default for Config {
    fn default() -> Self {
        // 13 beams from -45 to +45 degrees in 7.5 degree steps, as in the
        // G-8 beam-scan case.
        let mut az = [0i16; MAX_BEAMS];
        for (k, a) in az.iter_mut().enumerate().take(13) {
            *a = -4500 + 750 * k as i16;
        }
        Config {
            beams: 13,
            az_cdeg: az,
            dwell: 2,
            dwell_hit: 2,
            dwell_max: 8,
            settle: 1,
            min_det: 1,
            range_bin_cm: 150,
            doppler_bin_cms: 50,
        }
    }
}

/// The strongest detection of one CPI.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Detection {
    pub beam: u8,
    pub az_cdeg: i16,
    /// The target's range bin (0..63), the map's conjugate spectrum undone.
    pub range_bin: u8,
    /// Signed Doppler bin (-8..7), positive approaching.
    pub doppler_bin: i8,
    pub range_cm: u32,
    pub speed_cms: i32,
    pub count: u16,
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Step {
    /// Pulse `BEAM_STROBE` now.
    pub strobe: bool,
    pub detection: Option<Detection>,
}

#[derive(Clone, Copy, Debug)]
pub struct Scheduler {
    cfg: Config,
    beam: u8,
    on_beam: u8,
    extra: u8,
    settle_left: u8,
    last_cpi: Option<u8>,
    started: bool,
    pub cpis: u32,
    pub missed: u32,
    pub strobes: u32,
    pub hits: u32,
}

impl Scheduler {
    pub fn new(cfg: Config) -> Self {
        let mut cfg = cfg;
        cfg.beams = cfg.beams.clamp(1, MAX_BEAMS as u8);
        cfg.dwell = cfg.dwell.max(1);
        cfg.dwell_max = cfg.dwell_max.max(cfg.dwell);
        Self { cfg, beam: 0, on_beam: 0, extra: 0, settle_left: 0, last_cpi: None, started: false, cpis: 0, missed: 0, strobes: 0, hits: 0 }
    }

    pub fn config(&self) -> &Config {
        &self.cfg
    }

    /// The beam the Artix has loaded (after the first strobe).
    pub fn beam(&self) -> u8 {
        self.beam
    }

    /// One read of `RADAR_STAT`.
    pub fn poll(&mut self, reg: u32) -> Step {
        let st = Stat::from_reg(reg);
        let mut out = Step::default();
        let Some(last) = self.last_cpi else {
            // First look: start the scan on beam 0.
            self.last_cpi = Some(st.cpi);
            self.started = true;
            self.beam = 0;
            self.settle_left = self.cfg.settle;
            self.strobes += 1;
            out.strobe = true;
            return out;
        };
        let delta = st.cpi.wrapping_sub(last) & 0x3F;
        if delta == 0 {
            return out;
        }
        self.last_cpi = Some(st.cpi);
        self.cpis += delta as u32;
        self.missed += delta as u32 - 1;

        if self.settle_left > 0 {
            // Wait out the CPI(s) that straddled the strobe.
            self.settle_left = self.settle_left.saturating_sub(delta);
            return out;
        }
        self.on_beam = self.on_beam.saturating_add(delta);
        if st.detections >= self.cfg.min_det && st.detections > 0 {
            self.hits += 1;
            self.extra = (self.extra + self.cfg.dwell_hit).min(self.cfg.dwell_max - self.cfg.dwell);
            out.detection = Some(self.detection(&st));
        }
        if self.on_beam >= self.cfg.dwell + self.extra {
            self.beam = (self.beam + 1) % self.cfg.beams;
            self.on_beam = 0;
            self.extra = 0;
            self.settle_left = self.cfg.settle;
            self.strobes += 1;
            out.strobe = true;
        }
        out
    }

    fn detection(&self, st: &Stat) -> Detection {
        // kria_radar_proc sees the DDC's conjugate spectrum: a target at range
        // bin r and Doppler bin d lands in the map at (64 - r, 16 - d).
        let r = (RANGE_N - st.peak_range % RANGE_N) % RANGE_N;
        let d = (DOPPLER_M - st.peak_doppler % DOPPLER_M) % DOPPLER_M;
        let ds = if d >= DOPPLER_M / 2 { d as i8 - DOPPLER_M as i8 } else { d as i8 };
        Detection {
            beam: self.beam,
            az_cdeg: self.cfg.az_cdeg[self.beam as usize],
            range_bin: r,
            doppler_bin: ds,
            range_cm: r as u32 * self.cfg.range_bin_cm,
            speed_cms: ds as i32 * self.cfg.doppler_bin_cms,
            count: st.detections,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn stat(cpi: u8, det: u16, d: u8, r: u8) -> u32 {
        Stat { cpi, detections: det, peak_doppler: d, peak_range: r }.to_reg()
    }

    #[test]
    fn stat_round_trip() {
        let s = Stat { cpi: 63, detections: 0xABCD, peak_doppler: 15, peak_range: 63 };
        assert_eq!(Stat::from_reg(s.to_reg()), s);
        assert_eq!(s.to_reg() >> 26, 63);
    }

    #[test]
    fn empty_scene_dwells_then_steps_through_every_beam() {
        let cfg = Config { beams: 4, ..Default::default() };
        let mut s = Scheduler::new(cfg);
        assert!(s.poll(stat(5, 0, 0, 0)).strobe, "first poll starts the scan");
        let mut beams = [0u8; 12];
        let mut n = 0;
        let mut cpi = 5u8;
        for _ in 0..60 {
            // several polls per CPI
            assert_eq!(s.poll(stat(cpi, 0, 0, 0)), Step::default());
            cpi = (cpi + 1) & 0x3F;
            let st = s.poll(stat(cpi, 0, 0, 0));
            if st.strobe && n < beams.len() {
                beams[n] = s.beam();
                n += 1;
            }
        }
        // settle 1 + dwell 2 = a strobe every 3 CPIs: 0 -> 1 -> 2 -> 3 -> 0 ...
        assert_eq!(&beams[..8], &[1, 2, 3, 0, 1, 2, 3, 0]);
        assert_eq!(s.cpis, 60);
        assert_eq!(s.missed, 0);
        assert_eq!(s.strobes, 1 + 20);
    }

    #[test]
    fn a_target_holds_the_beam_and_is_reported_in_target_coordinates() {
        let cfg = Config { beams: 3, dwell: 2, dwell_hit: 2, dwell_max: 6, ..Default::default() };
        let mut s = Scheduler::new(cfg);
        s.poll(stat(0, 0, 0, 0));
        // beam 0: settle CPI, then a target every CPI at map cell (64-10, 16-3) = range 10, Doppler +3.
        assert_eq!(s.poll(stat(1, 4, 13, 54)), Step::default(), "the settle CPI is ignored");
        let mut dets = 0;
        let mut cpis_on_0 = 0;
        for c in 2..20u8 {
            let st = s.poll(stat(c, 4, 13, 54));
            if let Some(d) = st.detection {
                if d.beam == 0 {
                    dets += 1;
                    cpis_on_0 += 1;
                    assert_eq!((d.range_bin, d.doppler_bin, d.count), (10, 3, 4));
                    assert_eq!((d.range_cm, d.speed_cms, d.az_cdeg), (1500, 150, -4500));
                }
            }
            if st.strobe {
                break;
            }
        }
        // dwell 2 extended by hits to dwell_max 6 on the target's beam
        assert_eq!(cpis_on_0, 6);
        assert_eq!(dets, 6);
        assert_eq!(s.beam(), 1);
    }

    #[test]
    fn negative_doppler_and_missed_cpis() {
        let mut s = Scheduler::new(Config { beams: 2, settle: 0, dwell: 5, dwell_max: 5, ..Default::default() });
        s.poll(stat(62, 0, 0, 0));
        // map Doppler bin 3 -> target bin 13 -> -3; range bin 0 stays 0; three CPIs since the last poll, wrapping.
        let st = s.poll(stat(1, 1, 3, 0));
        let d = st.detection.unwrap();
        assert_eq!((d.range_bin, d.doppler_bin, d.speed_cms), (0, -3, -150));
        assert_eq!((s.cpis, s.missed), (3, 2));
    }
}
