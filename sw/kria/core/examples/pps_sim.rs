//! PPS discipline against a model of kria_pps, for the figure in
//! docs/INTEGRATIONS.md. Prints CSV on stdout:
//!
//! `second,gen_error_ns,state,est_ppb,true_ppb,captured`
//!
//! `gen_error_ns` is the generated edge against the TRUE GPS second (not the
//! jittered capture), i.e. what PPS_SYNC delivers to the front end.
//!
//! Scenario, 900 s: the PL clock starts 37 ppm fast and warms by +0.6 ppm over
//! the first 600 s; the receiver's pulse has +-20 ns of jitter; at 300 s a
//! false pulse 250 us early; from 420 s to 540 s no GPS at all (holdover).
//!
//!     cargo run --release --example pps_sim > pps.csv

use kria_core::pps::{Capture, Config, Discipline, Outcome, State};

fn main() {
    let mut d = Discipline::new(Config::default());
    let mut rng: u64 = 0x9e37_79b9_7f4a_7c15;
    let mut uni = move || {
        rng ^= rng << 13;
        rng ^= rng >> 7;
        rng ^= rng << 17;
        (rng >> 11) as f64 / (1u64 << 53) as f64 * 2.0 - 1.0
    };
    let ppm = |t: f64| 37.0 + 0.6 * (t / 600.0).min(1.0);

    // Integrate the counter: ticks at true time t.
    let tick_at = |t: f64| -> f64 {
        // integral of 1e8 * (1 + ppm(t')*1e-6) dt' from 0 to t
        let warm = if t <= 600.0 { 0.6 * t * t / 1200.0 } else { 0.6 * 300.0 + 0.6 * (t - 600.0) };
        1e8 * t + 1e2 * (37.0 * t + warm)
    };

    let mut period = 0.0f64;
    let mut gen_next = f64::MAX;
    let mut pending = 0.0f64;
    let mut last_gen = 0.0f64;
    let mut count: u16 = 0;
    println!("second,gen_error_ns,state,est_ppb,true_ppb,captured");
    for s in 1..=900u32 {
        let t = s as f64;
        let true_tick = tick_at(t);
        // Generator edges up to this second (+ a margin for the edge itself).
        while gen_next <= true_tick + 2.0e6 {
            last_gen = gen_next;
            gen_next += period + pending;
            pending = 0.0;
        }
        let outage = (420..540).contains(&s);
        let mut captured = 0;
        if !outage {
            let jitter_ns = 20.0 * uni();
            let early = if s == 300 { -250e-6 } else { 0.0 };
            let cap = tick_at(t + jitter_ns * 1e-9 + early).floor() as u64;
            count = count.wrapping_add(1);
            match d.on_capture(Capture { cap, generated: last_gen.floor() as u64, count }) {
                Outcome::Applied(c) => {
                    captured = 1;
                    period = c.period_int as f64 + c.period_frac as f64 / 4_294_967_296.0;
                    if c.restart {
                        gen_next = cap as f64 + period;
                    }
                    pending += c.adjust as f64;
                }
                Outcome::Rejected => captured = 2,
            }
        } else if s == 420 {
            d.on_missing();
        }
        // The generated edge nearest the true second, in ns (one tick = 10 ns).
        let err_ticks = if last_gen == 0.0 { f64::NAN } else {
            let mut e = last_gen - true_tick;
            if e > 5e7 { e -= period }
            e
        };
        let state = match d.state() {
            State::Acquiring => "acquiring",
            State::Locked => "locked",
            State::Holdover => "holdover",
        };
        println!(
            "{s},{:.1},{state},{},{:.1},{captured}",
            err_ticks * 10.0,
            d.error_ppb(),
            ppm(t) * 1000.0
        );
    }
}
