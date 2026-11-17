//! Transmit interlock: whether the transmitter may key.
//!
//! The rule from `docs/HMI.md`: transmit only while the vehicle is parked and
//! the licence flag is set, and never for longer than the time-out. It runs on
//! R5F core 0 every millisecond, so it holds while Linux is busy or restarting,
//! and it fails safe: no fresh speed from anywhere means "moving".
//!
//! - **Speed source.** The ECU stream first (road speed, `0x000D` on the GM
//!   engine module, through opendash), GPS second. A source is fresh for
//!   [`Config::ecu_stale`] / [`Config::gps_stale`] seconds after its last value.
//! - **Parked** means below [`Config::parked`] continuously for
//!   [`Config::parked_hold`] seconds; **moving** is at or above
//!   [`Config::moving`]. Between the two the last state holds, so a car creeping
//!   in traffic does not flick the transmitter on and off.
//! - **Time-out.** Keyed continuously for [`Config::tx_timeout`] seconds ends
//!   the transmission, and the request has to be released and
//!   [`Config::cooldown`] seconds pass before it can key again.
//!
//! Times are ticks of the PL counter that `kria_pps` exposes (`NOW`), shared by
//! Linux and the R5F, so a stamp written by one is read correctly by the other.

#[derive(Clone, Copy, Debug)]
pub struct Config {
    pub tick_hz: u64,
    /// Speeds in 0.01 km/h.
    pub moving: u32,
    pub parked: u32,
    /// Seconds.
    pub parked_hold: u64,
    pub ecu_stale: u64,
    pub gps_stale: u64,
    pub tx_timeout: u64,
    pub cooldown: u64,
}

impl Default for Config {
    fn default() -> Self {
        Self {
            tick_hz: 100_000_000,
            moving: 300,
            parked: 100,
            parked_hold: 3,
            ecu_stale: 1,
            gps_stale: 2,
            tx_timeout: 180,
            cooldown: 10,
        }
    }
}

/// A speed and when it was measured.
#[derive(Clone, Copy, Debug)]
pub struct Speed {
    /// 0.01 km/h.
    pub centi_kmh: u32,
    /// PL ticks.
    pub stamp: u64,
}

#[derive(Clone, Copy, Debug, Default)]
pub struct Inputs {
    pub now: u64,
    pub ecu: Option<Speed>,
    pub gps: Option<Speed>,
    pub licensed: bool,
    /// The operator holds the transmit button.
    pub request: bool,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[repr(u8)]
pub enum Reason {
    Keyed = 0,
    Idle = 1,
    NoLicence = 2,
    Moving = 3,
    SpeedUnknown = 4,
    Settling = 5,
    TimedOut = 6,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[repr(u8)]
pub enum Source {
    None = 0,
    Ecu = 1,
    Gps = 2,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Decision {
    pub transmit: bool,
    pub reason: Reason,
    pub source: Source,
}

pub struct Interlock {
    cfg: Config,
    parked: bool,
    slow_since: Option<u64>,
    keyed_since: Option<u64>,
    timed_out_at: Option<u64>,
}

impl Interlock {
    pub fn new(cfg: Config) -> Self {
        Self { cfg, parked: false, slow_since: None, keyed_since: None, timed_out_at: None }
    }

    fn fresh(&self, s: Option<Speed>, now: u64, stale_s: u64) -> Option<u32> {
        let s = s?;
        if now >= s.stamp && now - s.stamp <= stale_s * self.cfg.tick_hz {
            Some(s.centi_kmh)
        } else {
            None
        }
    }

    pub fn step(&mut self, i: Inputs) -> Decision {
        let hz = self.cfg.tick_hz;
        let (speed, source) = match self.fresh(i.ecu, i.now, self.cfg.ecu_stale) {
            Some(v) => (Some(v), Source::Ecu),
            None => match self.fresh(i.gps, i.now, self.cfg.gps_stale) {
                Some(v) => (Some(v), Source::Gps),
                None => (None, Source::None),
            },
        };

        match speed {
            None => {
                self.parked = false;
                self.slow_since = None;
            }
            Some(v) if v >= self.cfg.moving => {
                self.parked = false;
                self.slow_since = None;
            }
            Some(v) if v < self.cfg.parked => {
                let since = *self.slow_since.get_or_insert(i.now);
                if i.now - since >= self.cfg.parked_hold * hz {
                    self.parked = true;
                }
            }
            Some(_) => {
                // Between parked and moving: keep the state, restart the timer.
                if !self.parked {
                    self.slow_since = None;
                }
            }
        }

        // After a time-out the button has to be released for the cooldown:
        // `timed_out_at` follows the request while it is held, so the cooldown
        // counts from the release.
        if let Some(t) = self.timed_out_at {
            if i.request {
                self.timed_out_at = Some(i.now);
            } else if i.now - t >= self.cfg.cooldown * hz {
                self.timed_out_at = None;
            }
        }
        if !i.request {
            self.keyed_since = None;
        }

        let blocked = if !i.licensed {
            Some(Reason::NoLicence)
        } else if speed.is_none() {
            Some(Reason::SpeedUnknown)
        } else if !self.parked {
            Some(if self.slow_since.is_some() { Reason::Settling } else { Reason::Moving })
        } else if self.timed_out_at.is_some() {
            Some(Reason::TimedOut)
        } else {
            None
        };

        let reason = match (blocked, i.request) {
            (Some(r), _) => {
                self.keyed_since = None;
                r
            }
            (None, false) => Reason::Idle,
            (None, true) => {
                let since = *self.keyed_since.get_or_insert(i.now);
                if i.now - since >= self.cfg.tx_timeout * hz {
                    self.timed_out_at = Some(i.now);
                    self.keyed_since = None;
                    Reason::TimedOut
                } else {
                    Reason::Keyed
                }
            }
        };
        Decision { transmit: reason == Reason::Keyed, reason, source }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const HZ: u64 = 100_000_000;

    fn at(s: f64) -> u64 {
        (s * HZ as f64) as u64
    }

    fn ecu(kmh: f64, t: f64) -> Option<Speed> {
        Some(Speed { centi_kmh: (kmh * 100.0) as u32, stamp: at(t) })
    }

    fn inputs(now: f64, ecu_s: Option<Speed>, gps_s: Option<Speed>, request: bool) -> Inputs {
        Inputs { now: at(now), ecu: ecu_s, gps: gps_s, licensed: true, request }
    }

    #[test]
    fn locked_while_moving_and_until_parked_for_three_seconds() {
        let mut il = Interlock::new(Config::default());
        let d = il.step(inputs(0.0, ecu(38.0, 0.0), None, true));
        assert_eq!(d, Decision { transmit: false, reason: Reason::Moving, source: Source::Ecu });
        let d = il.step(inputs(1.0, ecu(0.0, 1.0), None, true));
        assert_eq!(d.reason, Reason::Settling);
        let d = il.step(inputs(3.9, ecu(0.0, 3.9), None, true));
        assert!(!d.transmit);
        let d = il.step(inputs(4.0, ecu(0.0, 4.0), None, true));
        assert!(d.transmit);
    }

    #[test]
    fn creeping_does_not_toggle() {
        let mut il = Interlock::new(Config::default());
        for k in 0..50 {
            il.step(inputs(k as f64 * 0.1, ecu(0.0, k as f64 * 0.1), None, false));
        }
        // 2 km/h: between parked and moving, stays parked.
        assert!(il.step(inputs(5.1, ecu(2.0, 5.1), None, true)).transmit);
        // 3 km/h: moving.
        assert_eq!(il.step(inputs(5.2, ecu(3.0, 5.2), None, true)).reason, Reason::Moving);
        // 2 km/h again: not parked until below 1 km/h for 3 s.
        assert!(!il.step(inputs(5.3, ecu(2.0, 5.3), None, true)).transmit);
    }

    #[test]
    fn falls_back_to_gps_then_fails_safe() {
        let mut il = Interlock::new(Config::default());
        for k in 0..40 {
            let t = k as f64 * 0.1;
            il.step(inputs(t, ecu(0.0, t), None, false));
        }
        assert!(il.step(inputs(4.0, ecu(0.0, 4.0), None, true)).transmit);
        // The ECU stream stops (opendash changing its selection takes ~2.5 s).
        // GPS says parked: still allowed, from GPS.
        let d = il.step(inputs(5.5, ecu(0.0, 4.0), Some(Speed { centi_kmh: 20, stamp: at(5.4) }), true));
        assert_eq!((d.transmit, d.source), (true, Source::Gps));
        // GPS stale too: speed unknown, locked.
        let d = il.step(inputs(8.0, ecu(0.0, 4.0), Some(Speed { centi_kmh: 20, stamp: at(5.4) }), true));
        assert_eq!(d, Decision { transmit: false, reason: Reason::SpeedUnknown, source: Source::None });
        // And it has to settle again before keying.
        assert!(!il.step(inputs(8.1, ecu(0.0, 8.1), None, true)).transmit);
    }

    #[test]
    fn no_licence_no_transmit() {
        let mut il = Interlock::new(Config::default());
        for k in 0..40 {
            let t = k as f64 * 0.1;
            il.step(inputs(t, ecu(0.0, t), None, false));
        }
        let mut i = inputs(4.0, ecu(0.0, 4.0), None, true);
        i.licensed = false;
        assert_eq!(il.step(i).reason, Reason::NoLicence);
    }

    #[test]
    fn timeout_then_release_and_cooldown() {
        let cfg = Config { tx_timeout: 10, cooldown: 5, ..Config::default() };
        let mut il = Interlock::new(cfg);
        let mut t = 0.0;
        while t < 4.0 {
            il.step(inputs(t, ecu(0.0, t), None, false));
            t += 0.5;
        }
        assert!(il.step(inputs(4.0, ecu(0.0, 4.0), None, true)).transmit);
        assert!(il.step(inputs(13.9, ecu(0.0, 13.9), None, true)).transmit);
        assert_eq!(il.step(inputs(14.0, ecu(0.0, 14.0), None, true)).reason, Reason::TimedOut);
        // Still held: stays off.
        assert!(!il.step(inputs(20.0, ecu(0.0, 20.0), None, true)).transmit);
        // Released, but within the cooldown.
        il.step(inputs(20.5, ecu(0.0, 20.5), None, false));
        assert_eq!(il.step(inputs(21.0, ecu(0.0, 21.0), None, true)).reason, Reason::TimedOut);
        il.step(inputs(21.5, ecu(0.0, 21.5), None, false));
        il.step(inputs(26.0, ecu(0.0, 26.0), None, false));
        assert!(il.step(inputs(26.1, ecu(0.0, 26.1), None, true)).transmit);
    }
}
