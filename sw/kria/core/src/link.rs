//! Watchdog on the IAS1 link (`kria_pl_link`), for R5F core 0.
//!
//! The link trains itself at power-up (`link_rx_train_fsm`), but nothing
//! retrains it if it drops later: a cable knock, the front end restarting, a
//! clock-mode switch. Every millisecond the R5F reads `LINK_STATUS` and the
//! CRC error count and this module decides:
//!
//! - **Down** (`link_up` low) for [`Config::down_ms`]: pulse `LINK_CTRL[2]`
//!   (retrain). If it does not come back, retrain again after a back-off that
//!   doubles from [`Config::backoff_ms`] up to [`Config::backoff_max_ms`], so a
//!   front end that is off is not hammered.
//! - **Errors** while up: more than [`Config::crc_per_s`] CRC errors within one
//!   second of link time means the eye has moved (temperature, a marginal
//!   cable); the link is retrained once, then the error window starts again.
//! - **Up** for [`Config::stable_ms`] resets the back-off.
//! - **Start**: the first training gets [`Config::first_ms`] before the first
//!   retrain.
//!
//! The health goes to Linux in the mailbox, and transmit is allowed only while
//! the link is [`Health::Up`]: with the link down the transmit samples do not
//! reach the front end, and when it returns they should not resume on their own.

#[derive(Clone, Copy, Debug)]
pub struct Config {
    pub down_ms: u32,
    /// Grace for the training after start, before the first retrain.
    pub first_ms: u32,
    pub backoff_ms: u32,
    pub backoff_max_ms: u32,
    pub crc_per_s: u32,
    pub stable_ms: u32,
}

impl Default for Config {
    fn default() -> Self {
        Self { down_ms: 20, first_ms: 3000, backoff_ms: 100, backoff_max_ms: 5000, crc_per_s: 100, stable_ms: 2000 }
    }
}

/// `LINK_STATUS[6]`.
pub const STATUS_LINK_UP: u32 = 1 << 6;
/// `LINK_CTRL[2]`, self-clearing.
pub const CTRL_RETRAIN: u32 = 1 << 2;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[repr(u8)]
pub enum Health {
    /// Never seen up since start.
    Unknown = 0,
    Up = 1,
    /// Up, but the error window overflowed and a retrain was asked for.
    Errors = 2,
    Down = 3,
}

#[derive(Clone, Copy, Debug)]
pub struct Watchdog {
    cfg: Config,
    health: Health,
    ever_up: bool,
    down_for: u32,
    up_for: u32,
    wait: u32,
    backoff: u32,
    win_ms: u32,
    win_base: u32,
    last_crc: u32,
    pub retrains: u32,
    /// CRC errors in the last complete one-second window.
    pub crc_last_s: u32,
}

impl Watchdog {
    pub fn new(cfg: Config) -> Self {
        Self {
            cfg,
            health: Health::Unknown,
            ever_up: false,
            down_for: 0,
            up_for: 0,
            wait: 0,
            backoff: cfg.backoff_ms,
            win_ms: 0,
            win_base: 0,
            last_crc: 0,
            retrains: 0,
            crc_last_s: 0,
        }
    }

    pub fn health(&self) -> Health {
        self.health
    }

    pub fn up(&self) -> bool {
        self.health == Health::Up
    }

    /// One millisecond: the `LINK_STATUS` word and `ERR_CNT_CRC`. Returns true
    /// when `LINK_CTRL[2]` should be pulsed now.
    pub fn step(&mut self, status: u32, crc: u32) -> bool {
        let up = status & STATUS_LINK_UP != 0;
        let prev = self.last_crc;
        self.last_crc = crc;
        self.wait = self.wait.saturating_sub(1);
        if !up {
            self.up_for = 0;
            self.win_ms = 0;
            self.win_base = crc;
            self.down_for = self.down_for.saturating_add(1);
            // The first training (an eye scan of every tap) gets longer than a later drop.
            let limit = if self.ever_up { self.cfg.down_ms } else { self.cfg.first_ms };
            if self.ever_up || self.down_for >= limit {
                self.health = Health::Down;
            }
            return self.down_for >= limit && self.wait == 0 && self.retrain();
        }

        // Up.
        if self.down_for > 0 || !self.ever_up || self.win_ms == 0 {
            self.win_base = prev;
        }
        self.ever_up = true;
        self.down_for = 0;
        self.up_for = self.up_for.saturating_add(1);
        if self.up_for >= self.cfg.stable_ms {
            self.backoff = self.cfg.backoff_ms;
        }
        self.win_ms += 1;
        let errs = crc.wrapping_sub(self.win_base);
        if errs > self.cfg.crc_per_s && self.wait == 0 {
            self.crc_last_s = errs;
            self.win_ms = 0;
            self.win_base = crc;
            self.health = Health::Errors;
            return self.retrain();
        }
        if self.win_ms >= 1000 {
            self.crc_last_s = errs;
            self.win_ms = 0;
            self.win_base = crc;
        }
        if self.health != Health::Errors || self.wait == 0 {
            self.health = Health::Up;
        }
        false
    }

    fn retrain(&mut self) -> bool {
        self.retrains = self.retrains.wrapping_add(1);
        self.wait = self.backoff;
        self.backoff = (self.backoff.saturating_mul(2)).min(self.cfg.backoff_max_ms);
        true
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn run(w: &mut Watchdog, ms: u32, status: u32, crc: &mut u32, crc_per_ms: u32) -> u32 {
        let mut n = 0;
        for _ in 0..ms {
            *crc += crc_per_ms;
            if w.step(status, *crc) {
                n += 1;
            }
        }
        n
    }

    #[test]
    fn retrains_with_backoff_and_resets_once_stable() {
        let mut w = Watchdog::new(Config::default());
        let mut crc = 0;
        // Training at power-up: down for 10 ms, then up; no retrain.
        assert_eq!(run(&mut w, 10, 0, &mut crc, 0), 0);
        assert_eq!(w.health(), Health::Unknown);
        assert_eq!(run(&mut w, 3000, STATUS_LINK_UP, &mut crc, 0), 0);
        assert!(w.up());
        // Drops for good: retrains at 20 ms, then 100, 200, 400, 800 ms later...
        let mut at = [0u32; 8];
        let mut k = 0;
        for t in 1..=4000u32 {
            if w.step(0, crc) && k < at.len() {
                at[k] = t;
                k += 1;
            }
        }
        assert_eq!(w.health(), Health::Down);
        assert_eq!(&at[..5], &[20, 120, 320, 720, 1520]);
        // Back: up, and after stable_ms the back-off is short again.
        assert_eq!(run(&mut w, 2500, STATUS_LINK_UP, &mut crc, 0), 0);
        assert!(w.up());
        let mut first = 0;
        for t in 1..=200u32 {
            if w.step(0, crc) {
                first = if first == 0 { t } else { first };
                break;
            }
        }
        assert_eq!(first, 20);
    }

    #[test]
    fn crc_burst_retrains_once_slow_errors_do_not() {
        let mut w = Watchdog::new(Config::default());
        let mut crc = 0;
        // 1 error every 20 ms = 50/s: below the threshold, counted.
        assert_eq!(run(&mut w, 2000, STATUS_LINK_UP, &mut crc, 0), 0);
        let mut n = 0;
        for t in 0..3000u32 {
            if t % 20 == 0 {
                crc += 1;
            }
            if w.step(STATUS_LINK_UP, crc) {
                n += 1;
            }
        }
        assert_eq!(n, 0);
        assert_eq!(w.crc_last_s, 50);
        assert!(w.up());
        // 1 per ms: the window overflows after ~100 ms and the link is retrained, not again before the back-off.
        let n = run(&mut w, 150, STATUS_LINK_UP, &mut crc, 1);
        assert_eq!(n, 1);
        assert_eq!(w.health(), Health::Errors);
        assert!(!w.up());
    }
}
