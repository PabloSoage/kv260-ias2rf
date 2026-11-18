//! `kria-hmid`: the HMI's data service on the A53s (HMI.md §6).
//!
//! ```text
//! kria-hmid [--sim | --hw] [--listen 0.0.0.0:8080] [--www DIR] [--sdr-out DIR] [--own LAT,LON]
//!           [--secs N] [--dump DIR] [--script FILE] [--rec-dir DIR]
//! ```
//! Each 20 ms it takes the DMA blocks (`--hw`: axi_dma_0 through kria_ps_framer; `--sim`: the simulated board),
//! feeds them to `kria_hmi_core::state::Hmi`, plays the audio, applies the screens' commands as register writes,
//! and every 100 ms sends the snapshot to every WebSocket client. `--www` serves the browser build of the screens.
//! `--sdr-out` points at kria-sdrd's outputs (kraken_doa.json, hackrf_sweep.json) for the Bearing and Wideband
//! screens. `--dump` writes the snapshot of each function after `--script`'s commands (one JSON command a line,
//! with `{"wait": seconds}` lines), for the documentation and the tests. "Record IQ" on the Spectrum screen writes
//! the spectrum stream to `--rec-dir` (default `recordings`, on the SSD on the car): interleaved 16-bit I and Q,
//! little-endian (`.cs16`, what GNU Radio, SDR# and inspectrum open), with a `.json` beside it giving the centre
//! frequency, the sample rate and the stream.

mod rec;

mod server;
mod sim;
#[cfg(all(feature = "hw", target_os = "linux"))]
mod hw;

use kria_hmi_core::modes::Write;
use kria_hmi_core::state::{Command, Hmi};
use std::path::PathBuf;
use std::time::{Duration, Instant};

struct Args {
    hw: bool,
    listen: Option<String>,
    www: Option<PathBuf>,
    sdr_out: Option<PathBuf>,
    own: (f64, f64),
    secs: Option<f64>,
    dump: Option<PathBuf>,
    script: Option<PathBuf>,
    rec_dir: PathBuf,
}

fn args() -> Args {
    let mut a = Args { hw: false, listen: None, www: None, sdr_out: None, own: (43.3623, -8.4115), secs: None, dump: None, script: None, rec_dir: "recordings".into() };
    let v: Vec<String> = std::env::args().skip(1).collect();
    let mut i = 0;
    while i < v.len() {
        let next = |i: usize| v.get(i + 1).cloned().unwrap_or_default();
        match v[i].as_str() {
            "--hw" => a.hw = true,
            "--sim" => a.hw = false,
            "--listen" => { a.listen = Some(next(i)); i += 1; }
            "--www" => { a.www = Some(next(i).into()); i += 1; }
            "--sdr-out" => { a.sdr_out = Some(next(i).into()); i += 1; }
            "--secs" => { a.secs = next(i).parse().ok(); i += 1; }
            "--dump" => { a.dump = Some(next(i).into()); i += 1; }
            "--script" => { a.script = Some(next(i).into()); i += 1; }
            "--rec-dir" => { a.rec_dir = next(i).into(); i += 1; }
            "--own" => {
                let s = next(i);
                let mut it = s.split(',').filter_map(|x| x.parse::<f64>().ok());
                if let (Some(la), Some(lo)) = (it.next(), it.next()) {
                    a.own = (la, lo);
                }
                i += 1;
            }
            "-h" | "--help" => {
                eprintln!("kria-hmid [--sim|--hw] [--listen ADDR] [--www DIR] [--sdr-out DIR] [--own LAT,LON] [--secs N] [--dump DIR] [--script FILE] [--rec-dir DIR]");
                std::process::exit(0);
            }
            o => eprintln!("ignored: {o}"),
        }
        i += 1;
    }
    a
}

enum Board {
    Sim(sim::Sim),
    #[cfg(all(feature = "hw", target_os = "linux"))]
    Hw(hw::Board),
}

fn load_json(dir: &Option<PathBuf>, name: &str) -> Option<serde_json::Value> {
    // kria-sdrd writes into one directory per receiver (kraken/, hackrf/); take either layout
    let d = dir.as_ref()?;
    let t = [d.join(name), d.join("kraken").join(name), d.join("hackrf").join(name)]
        .iter()
        .find_map(|p| std::fs::read_to_string(p).ok())?;
    serde_json::from_str(&t).ok()
}

fn main() {
    let a = args();
    let mut hmi = Hmi::default();
    hmi.set_own_position(a.own.0, a.own.1);
    let mut board = if a.hw {
        #[cfg(all(feature = "hw", target_os = "linux"))]
        {
            Board::Hw(hw::Board::open().expect("open the KV260's /dev/mem and /dev/udmabuf0 (run as root)"))
        }
        #[cfg(not(all(feature = "hw", target_os = "linux")))]
        {
            eprintln!("--hw needs a Linux build with --features hw; running simulated");
            Board::Sim(sim::Sim::new(a.own))
        }
    } else {
        Board::Sim(sim::Sim::new(a.own))
    };
    let srv = a.listen.as_deref().map(|l| server::Server::start(l, a.www.clone()).expect("listen"));
    if let Some(l) = &a.listen {
        eprintln!("kria-hmid: snapshots on ws://{l}/ws{}", if a.www.is_some() { ", screens on http://".to_string() + l + "/" } else { String::new() });
    }

    let apply = |hmi: &mut Hmi, board: &mut Board, c: Command| {
        let writes: Vec<Write> = hmi.command(c);
        match board {
            Board::Sim(s) => {
                for w in &writes {
                    s.write(w);
                }
                if let Some(p) = hmi.plan() {
                    s.set_tuning(p.freq_hz, p.audio_rate);
                }
                s.tx_req = hmi.snap.tx.requested;
                s.licensed = hmi.snap.tx.licensed;
            }
            #[cfg(all(feature = "hw", target_os = "linux"))]
            Board::Hw(b) => {
                for w in &writes {
                    b.write(w);
                }
                b.tx_request(hmi.snap.tx.requested, hmi.snap.tx.licensed);
            }
        }
    };
    apply(&mut hmi, &mut board, Command::Preset { index: 0 });

    // the script: commands with waits, and a dump after each function's settle time
    let mut script: Vec<serde_json::Value> = a
        .script
        .as_ref()
        .and_then(|p| std::fs::read_to_string(p).ok())
        .map(|t| t.lines().filter(|l| !l.trim().is_empty()).filter_map(|l| serde_json::from_str(l).ok()).collect())
        .unwrap_or_default();
    script.reverse();
    let mut wait_until = 0.0f64;

    let mut rec = rec::Recorder::new(a.rec_dir.clone());
    let t0 = Instant::now();
    let mut sim_t = 0.0f64;
    let fast = a.dump.is_some(); // a dump run goes as fast as the machine does
    let mut last_bc = 0.0f64;
    loop {
        let dt = 0.02;
        let now = if fast { sim_t } else { t0.elapsed().as_secs_f64() };
        match &mut board {
            Board::Sim(s) => {
                let b = s.block(dt);
                hmi.on_block(&b, now);
                s.vehicle_and_tx(&mut hmi.snap.vehicle, &mut hmi.snap.tx);
                s.system(&mut hmi.snap.system);
            }
            #[cfg(all(feature = "hw", target_os = "linux"))]
            Board::Hw(b) => {
                while let Some(blk) = b.poll_block() {
                    hmi.on_block(&blk, now);
                }
                if let Some(r) = b.r5f() {
                    hmi.snap.tx.keyed = r.transmit;
                    hmi.snap.tx.reason = format!("{:?}", r.reason);
                    hmi.snap.system.r5f0 = format!("PPS {:?}, link {:?}, {} retrains", r.pps, r.link, r.link_retrains);
                }
                hmi.snap.system.link_up = b.link_up();
                hmi.snap.system.platform = "KV260".into();
            }
        }
        if !hmi.tx_in_range() {
            hmi.snap.tx.reason = format!("outside the board's HF range (below {:.1} MHz)", kria_hmi_core::state::TX_MAX_HZ / 1e6);
        }
        if !hmi.audio_out.is_empty() {
            let rate = hmi.plan().map(|p| p.audio_rate).unwrap_or(0.0);
            match &mut board {
                Board::Sim(_) => {}
                #[cfg(all(feature = "hw", target_os = "linux"))]
                Board::Hw(b) => b.play(rate, &hmi.audio_out),
            }
            let _ = rate;
            hmi.audio_out.clear();
        }
        rec.step(&mut hmi);
        if let Some(s) = &srv {
            while let Ok(t) = s.commands.try_recv() {
                match serde_json::from_str::<Command>(&t) {
                    Ok(c) => apply(&mut hmi, &mut board, c),
                    Err(e) => eprintln!("bad command {t}: {e}"),
                }
            }
            if now - last_bc >= 0.1 {
                last_bc = now;
                hmi.snap.bearing = load_json(&a.sdr_out, "kraken_doa.json");
                hmi.snap.wideband = load_json(&a.sdr_out, "hackrf_sweep.json");
                s.broadcast(hmi.snapshot_json());
            }
        }
        if now >= wait_until {
            if let Some(v) = script.pop() {
                if let Some(w) = v.get("wait").and_then(|w| w.as_f64()) {
                    wait_until = now + w;
                } else if let Some(name) = v.get("dump").and_then(|d| d.as_str()) {
                    if let Some(dir) = &a.dump {
                        hmi.snap.bearing = load_json(&a.sdr_out, "kraken_doa.json");
                        hmi.snap.wideband = load_json(&a.sdr_out, "hackrf_sweep.json");
                        let _ = std::fs::create_dir_all(dir);
                        let _ = std::fs::write(dir.join(format!("{name}.json")), serde_json::to_string_pretty(&hmi.with_history()).unwrap());
                        eprintln!("dumped {name} at t = {now:.2} s");
                    }
                } else {
                    match serde_json::from_value::<Command>(v.clone()) {
                        Ok(c) => apply(&mut hmi, &mut board, c),
                        Err(e) => eprintln!("bad script line {v}: {e}"),
                    }
                }
            } else if fast {
                break;
            }
        }
        if let Some(n) = a.secs {
            if now >= n {
                break;
            }
        }
        sim_t += dt;
        if !fast {
            std::thread::sleep(Duration::from_secs_f64((sim_t - t0.elapsed().as_secs_f64()).max(0.0)));
        }
    }
    hmi.snap.system.recording = false;
    rec.step(&mut hmi);
    let s = &hmi.snap.system;
    eprintln!(
        "kria-hmid: {} blocks, {} packets, {} sequence gaps, {} CRC errors, {} resync words, {} WebSocket clients",
        s.blocks,
        s.packets,
        s.seq_gaps,
        s.crc_errors,
        s.resync_words,
        srv.as_ref().map(|s| s.clients()).unwrap_or(0)
    );
}
