//! PPS discipline: keeps the PL's generated second on the GPS second.
//!
//! `kria_pps` timestamps every GPS edge (`CAP`) and every generated edge
//! (`GEN`) on one free-running PL counter, and generates its pulse from a
//! fractional period (`GEN_PERIOD_INT` + `GEN_PERIOD_FRAC` / 2^32 ticks) plus a
//! one-shot `GEN_ADJUST`. Once per GPS capture this module turns the two
//! timestamps into the next period and adjustment:
//!
//! - **Frequency** over a long baseline: ticks between the first capture of the
//!   window and this one, divided by the GPS seconds between them. One capture
//!   carries the receiver's jitter (tens of ns) and the counter's +-1 tick; N of
//!   them carry 1/N of it. The window restarts every [`Config::window`] seconds
//!   so the estimate follows the oscillator as it warms up.
//! - **Phase**: the generated edge minus the GPS edge, wrapped to half a second,
//!   removed a fraction [`Config::phase_gain`] at a time through `GEN_ADJUST`.
//! - **Outliers**: a capture whose interval to the previous one is off the
//!   nominal second by more than [`Config::max_ppm`], or off the estimate by
//!   more than [`Config::max_jump`] ticks once locked, is ignored: a receiver
//!   that loses its fix can emit a pulse at the wrong time before it stops.
//! - **Holdover**: no capture for more than 1.25 s (`STATUS.missing`). The
//!   generator keeps the last period and nothing is adjusted.
//!
//! `tb_kria_pps` runs the same loop against the RTL; the tests below run it
//! against a model of the hardware with a 37 ppm oscillator, receiver jitter,
//! a frequency step, dropouts and a false pulse.

/// Settings. [`Config::default`] is for the 100 MHz PL clock.
#[derive(Clone, Copy, Debug)]
pub struct Config {
    /// Nominal ticks per second.
    pub nominal: u32,
    /// Reject an interval further than this from the nominal second.
    pub max_ppm: u32,
    /// Once locked, reject an interval further than this from the estimate.
    pub max_jump: u32,
    /// Phase error (ticks) under which a second counts towards lock.
    pub lock_ticks: u32,
    /// Consecutive good seconds to declare lock.
    pub lock_after: u32,
    /// Fraction of the phase error removed per second, as num/den.
    pub phase_gain: (i64, i64),
    /// Integral gain: ticks/s of period correction per tick of phase error,
    /// as num/den. The long-baseline estimate lags an oscillator that is
    /// drifting (warming up); without this term the lag shows up as a constant
    /// phase error of lag/phase_gain.
    pub integral_gain: (i64, i64),
    /// Seconds in one frequency window.
    pub window: u32,
}

impl Default for Config {
    fn default() -> Self {
        Self {
            nominal: 100_000_000,
            max_ppm: 200,
            max_jump: 200,
            lock_ticks: 20,
            lock_after: 5,
            phase_gain: (1, 2),
            integral_gain: (1, 16),
            window: 1024,
        }
    }
}

/// What `kria_pps` reported for one GPS edge.
#[derive(Clone, Copy, Debug)]
pub struct Capture {
    /// `CAP_HI:CAP_LO`, the GPS edge.
    pub cap: u64,
    /// `GEN_HI:GEN_LO`, the last generated edge.
    pub generated: u64,
    /// `STATUS[31:16]`, GPS edges counted by the hardware (wraps at 2^16).
    /// Reported, not used: see `Discipline::seconds`.
    pub count: u16,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum State {
    /// No GPS yet, or after a reset of the estimate.
    Acquiring,
    /// The generated edge is within `lock_ticks` of the GPS edge.
    Locked,
    /// GPS lost; the generator runs on the last estimate.
    Holdover,
}

/// What to write to `kria_pps` after a capture.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Command {
    pub period_int: u32,
    pub period_frac: u32,
    /// Signed ticks for `GEN_ADJUST`; 0 means do not write it.
    pub adjust: i32,
    /// Restart the generator at NOW + period (first lock only).
    pub restart: bool,
}

/// What happened to a capture.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Outcome {
    Applied(Command),
    /// The capture was not used. The count goes up in [`Discipline::rejected`].
    Rejected,
}

pub struct Discipline {
    cfg: Config,
    state: State,
    /// Ticks per second, Q32.32.
    freq_q32: u64,
    have_freq: bool,
    /// First capture of the frequency window, and GPS seconds since it.
    base: Option<(u64, u64)>,
    /// Last accepted capture.
    prev: Option<u64>,
    /// GPS seconds since `base`, counted from the ticks (see `seconds`).
    secs: u64,
    /// Consecutive rejected captures.
    rejected_run: u32,
    good: u32,
    phase: i64,
    /// Integral correction to the period, ticks/s in Q32.32.
    integ_q32: i64,
    started: bool,
    pub rejected: u32,
    pub accepted: u32,
}

impl Discipline {
    pub fn new(cfg: Config) -> Self {
        Self {
            cfg,
            state: State::Acquiring,
            freq_q32: (cfg.nominal as u64) << 32,
            have_freq: false,
            base: None,
            prev: None,
            secs: 0,
            rejected_run: 0,
            good: 0,
            phase: 0,
            integ_q32: 0,
            started: false,
            rejected: 0,
            accepted: 0,
        }
    }

    pub fn state(&self) -> State {
        self.state
    }

    /// Estimated ticks per GPS second, Q32.32.
    pub fn frequency_q32(&self) -> u64 {
        self.freq_q32
    }

    /// Estimated frequency error of the PL clock against GPS, parts per billion.
    pub fn error_ppb(&self) -> i64 {
        let nominal = (self.cfg.nominal as i128) << 32;
        (((self.freq_q32 as i128 - nominal) * 1_000_000_000) / nominal) as i64
    }

    /// Last phase error, generated minus GPS, in ticks.
    pub fn phase_ticks(&self) -> i64 {
        self.phase
    }

    /// `STATUS.missing`: the GPS has gone quiet.
    pub fn on_missing(&mut self) {
        if self.state != State::Acquiring || self.have_freq {
            self.state = State::Holdover;
        }
        self.good = 0;
    }

    /// Whole GPS seconds in `ticks`, from the current estimate. The hardware
    /// counts GPS edges, which says nothing about seconds the GPS was silent;
    /// the ticks do, and an estimate within 200 ppm rounds correctly for any
    /// gap under 40 minutes.
    fn seconds(&self, ticks: u64) -> u64 {
        let per = (self.freq_q32 >> 32).max(1);
        (ticks + per / 2) / per
    }

    /// The period written to the generator: the estimate plus the integral.
    fn period_q32(&self) -> u64 {
        (self.freq_q32 as i64 + self.integ_q32) as u64
    }

    fn command(&self, adjust: i32, restart: bool) -> Command {
        let p = self.period_q32();
        Command {
            period_int: (p >> 32) as u32,
            period_frac: p as u32,
            adjust,
            restart,
        }
    }

    pub fn on_capture(&mut self, c: Capture) -> Outcome {
        if let Some(pcap) = self.prev {
            let dt = c.cap.wrapping_sub(pcap);
            let secs = self.seconds(dt).max(1);
            let per = dt / secs;
            let nominal = self.cfg.nominal as u64;
            let limit = nominal * self.cfg.max_ppm as u64 / 1_000_000;
            let estimate = self.freq_q32 >> 32;
            let off_estimate = per.abs_diff(estimate);
            let bad = per.abs_diff(nominal) > limit
                || (self.state == State::Locked && off_estimate > self.cfg.max_jump as u64);
            if bad {
                self.rejected += 1;
                self.rejected_run += 1;
                // A false pulse is one; three in a row that are all within
                // max_ppm of nominal are the oscillator having moved (a warm-up
                // or temperature step): start the estimate again from here.
                if self.rejected_run < 3 || per.abs_diff(nominal) > limit {
                    return Outcome::Rejected;
                }
                self.state = State::Acquiring;
                self.good = 0;
                self.base = None;
                self.integ_q32 = 0;
            } else {
                self.secs += secs;
            }
        }
        self.rejected_run = 0;
        self.prev = Some(c.cap);
        self.accepted += 1;

        // Frequency over the window.
        match self.base {
            None => {
                self.base = Some((c.cap, 0));
                self.secs = 0;
            }
            Some((bcap, b0)) => {
                let secs = self.secs - b0;
                if secs >= 2 {
                    let ticks = c.cap.wrapping_sub(bcap) as u128;
                    self.freq_q32 = ((ticks << 32) / secs as u128) as u64;
                    self.have_freq = true;
                }
                if secs >= self.cfg.window as u64 {
                    self.base = Some((c.cap, self.secs));
                }
            }
        }

        if !self.started {
            // First capture: start the generator one estimated second from
            // now; the phase loop pulls it onto the GPS edge from there.
            self.started = true;
            self.state = State::Acquiring;
            return Outcome::Applied(self.command(0, true));
        }

        // Phase: the generated edge nearest the GPS edge.
        let period = (self.freq_q32 >> 32) as i64;
        let mut ph = c.generated.wrapping_sub(c.cap) as i64;
        ph = ph.rem_euclid(period);
        if ph > period / 2 {
            ph -= period;
        }
        self.phase = ph;

        if ph.unsigned_abs() <= self.cfg.lock_ticks as u64 {
            self.good += 1;
            if self.good >= self.cfg.lock_after {
                self.state = State::Locked;
            }
        } else {
            self.good = 0;
            if self.state == State::Locked && ph.unsigned_abs() > 10 * self.cfg.lock_ticks as u64 {
                self.state = State::Acquiring;
            } else if self.state == State::Holdover {
                self.state = State::Acquiring;
            }
        }
        if self.state == State::Holdover {
            self.state = State::Acquiring;
        }

        // Integral: only while the phase error is small enough to be a matter
        // of frequency, not the first pull-in after a restart or holdover.
        if ph.unsigned_abs() < 1000 {
            let (inum, iden) = self.cfg.integral_gain;
            let limit = (self.cfg.max_jump as i64) << 32;
            self.integ_q32 = (self.integ_q32 - ((ph << 32) * inum) / iden).clamp(-limit, limit);
        }
        let (num, den) = self.cfg.phase_gain;
        let quarter = period / 4;
        let adj = (-(ph * num) / den).clamp(-quarter, quarter) as i32;
        Outcome::Applied(self.command(adj, false))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A model of kria_pps: a counter at `clk_hz` (a real number, the
    /// oscillator), GPS edges every true second plus jitter, and the
    /// fractional generator with its one-shot adjustment.
    struct Hw {
        clk_hz: f64,
        t: f64,
        gen_next: f64,
        period: f64,
        pending_adj: f64,
        last_gen: u64,
        count: u16,
        rng: u64,
    }

    impl Hw {
        fn new(clk_hz: f64) -> Self {
            Self { clk_hz, t: 0.0, gen_next: f64::MAX, period: 0.0, pending_adj: 0.0, last_gen: 0, count: 0, rng: 0x1234_5678 }
        }
        fn jitter(&mut self, ns: f64) -> f64 {
            // xorshift, uniform in +-ns
            self.rng ^= self.rng << 13;
            self.rng ^= self.rng >> 7;
            self.rng ^= self.rng << 17;
            ((self.rng >> 11) as f64 / (1u64 << 53) as f64 * 2.0 - 1.0) * ns
        }
        /// Advance to the next GPS second; returns the capture.
        fn second(&mut self, jitter_ns: f64, glitch_at: Option<f64>) -> Option<Capture> {
            self.t += 1.0;
            let edge_ticks = (self.t + self.jitter(jitter_ns) * 1e-9) * self.clk_hz;
            // Run the generator up to the edge.
            while self.gen_next <= edge_ticks + 5.0 {
                self.last_gen = self.gen_next.floor() as u64;
                self.gen_next += self.period + self.pending_adj;
                self.pending_adj = 0.0;
            }
            if let Some(g) = glitch_at {
                self.count = self.count.wrapping_add(1);
                return Some(Capture { cap: ((self.t + g) * self.clk_hz) as u64, generated: self.last_gen, count: self.count });
            }
            self.count = self.count.wrapping_add(1);
            Some(Capture { cap: edge_ticks.floor() as u64, generated: self.last_gen, count: self.count })
        }
        fn apply(&mut self, c: Command, now: u64) {
            self.period = c.period_int as f64 + c.period_frac as f64 / 4_294_967_296.0;
            if c.restart {
                self.gen_next = now as f64 + self.period;
            }
            self.pending_adj += c.adjust as f64;
        }
    }

    fn run(clk_hz: f64, secs: u32, jitter_ns: f64) -> (Discipline, Hw, i64) {
        let mut d = Discipline::new(Config::default());
        let mut hw = Hw::new(clk_hz);
        let mut worst = 0i64;
        for s in 0..secs {
            let c = hw.second(jitter_ns, None).unwrap();
            if let Outcome::Applied(cmd) = d.on_capture(c) {
                hw.apply(cmd, c.cap + 10);
            }
            if s > 60 {
                worst = worst.max(d.phase_ticks().abs());
            }
        }
        (d, hw, worst)
    }

    #[test]
    fn locks_a_fast_oscillator_to_gps() {
        // 37 ppm fast, 20 ns of receiver jitter.
        let (d, _, worst) = run(100e6 * (1.0 + 37e-6), 300, 20.0);
        assert_eq!(d.state(), State::Locked);
        assert!((d.error_ppb() - 37_000).abs() < 50, "estimate {} ppb", d.error_ppb());
        assert!(worst <= 6, "phase error after a minute: {} ticks", worst);
    }

    #[test]
    fn locks_a_slow_oscillator() {
        let (d, _, worst) = run(100e6 * (1.0 - 61e-6), 300, 20.0);
        assert_eq!(d.state(), State::Locked);
        assert!((d.error_ppb() + 61_000).abs() < 50);
        assert!(worst <= 6);
    }

    #[test]
    fn follows_a_frequency_step_within_a_window() {
        let mut d = Discipline::new(Config { window: 64, ..Config::default() });
        let mut hw = Hw::new(100e6 * (1.0 + 10e-6));
        for _ in 0..200 {
            let c = hw.second(20.0, None).unwrap();
            if let Outcome::Applied(cmd) = d.on_capture(c) {
                hw.apply(cmd, c.cap + 10);
            }
        }
        // Warm-up step: +2 ppm. Within two windows the estimate follows.
        hw.clk_hz = 100e6 * (1.0 + 12e-6);
        let mut worst = 0;
        for s in 0..400 {
            let c = hw.second(20.0, None).unwrap();
            if let Outcome::Applied(cmd) = d.on_capture(c) {
                hw.apply(cmd, c.cap + 10);
            }
            if s > 200 {
                worst = worst.max(d.phase_ticks().abs());
            }
        }
        assert!((d.error_ppb() - 12_000).abs() < 100, "{}", d.error_ppb());
        assert!(worst <= 10, "{}", worst);
    }

    #[test]
    fn rejects_a_false_pulse_and_keeps_lock() {
        let mut d = Discipline::new(Config::default());
        let mut hw = Hw::new(100e6 * (1.0 + 5e-6));
        for _ in 0..120 {
            let c = hw.second(20.0, None).unwrap();
            if let Outcome::Applied(cmd) = d.on_capture(c) {
                hw.apply(cmd, c.cap + 10);
            }
        }
        assert_eq!(d.state(), State::Locked);
        // A pulse 300 us early, as a receiver losing its fix can emit.
        let c = hw.second(0.0, Some(-300e-6)).unwrap();
        assert_eq!(d.on_capture(c), Outcome::Rejected);
        for _ in 0..10 {
            let c = hw.second(20.0, None).unwrap();
            assert!(matches!(d.on_capture(c), Outcome::Applied(_)));
        }
        assert_eq!(d.state(), State::Locked);
        assert_eq!(d.rejected, 1);
    }

    #[test]
    fn holdover_then_reacquire() {
        let mut d = Discipline::new(Config::default());
        let mut hw = Hw::new(100e6 * (1.0 + 20e-6));
        for _ in 0..120 {
            let c = hw.second(20.0, None).unwrap();
            if let Outcome::Applied(cmd) = d.on_capture(c) {
                hw.apply(cmd, c.cap + 10);
            }
        }
        // 60 s without GPS: the generator free-runs on the estimate.
        d.on_missing();
        assert_eq!(d.state(), State::Holdover);
        for _ in 0..60 {
            hw.second(0.0, None);
            hw.count = hw.count.wrapping_sub(1); // no capture counted
        }
        // Back: the phase after a minute of holdover is a few ticks, not a
        // fraction of a second, because the frequency was right.
        let c = hw.second(20.0, None).unwrap();
        let out = d.on_capture(c);
        assert!(matches!(out, Outcome::Applied(_)));
        assert!(d.phase_ticks().abs() < 50, "after holdover {} ticks", d.phase_ticks());
        if let Outcome::Applied(cmd) = out {
            hw.apply(cmd, c.cap + 10);
        }
        for _ in 0..20 {
            let c = hw.second(20.0, None).unwrap();
            if let Outcome::Applied(cmd) = d.on_capture(c) {
                hw.apply(cmd, c.cap + 10);
            }
        }
        assert_eq!(d.state(), State::Locked);
    }

    #[test]
    fn counter_wraps() {
        let mut d = Discipline::new(Config::default());
        let mut hw = Hw::new(100e6);
        hw.count = 65_500;
        for _ in 0..200 {
            let c = hw.second(10.0, None).unwrap();
            if let Outcome::Applied(cmd) = d.on_capture(c) {
                hw.apply(cmd, c.cap + 10);
            }
        }
        assert_eq!(d.state(), State::Locked);
        assert!(d.error_ppb().abs() < 50);
    }
}
