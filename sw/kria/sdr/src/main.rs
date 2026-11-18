//! kria-sdrd: the KrakenSDR and HackRF Pro daemon for the KV260's A53s.
//!
//! On the board (`--features hw`) it reads the devices over USB and drives the PL blocks through `/dev/mem`.
//! On a PC it runs the same processing on captures, which is how the end-to-end test runs
//! (docs/INTEGRATIONS.md sections 9 and 10):
//!
//! ```text
//! kria-sdrd kraken-pre  DIR   USB transfers -> alignment, calibration -> the PL's stimulus and expected output
//! kria-sdrd kraken-post DIR   the RTL's R and Bartlett spectrum -> MUSIC -> kraken_doa.json for the screen
//! kria-sdrd hackrf-pre  DIR   sweep transfers -> the PL's stimulus and expected output
//! kria-sdrd hackrf-post DIR   the RTL's bins -> panorama, signals, transmit gate -> hackrf_sweep.json
//! ```

use kria_sdr::cplx::C;
use kria_sdr::hackrf::{self, Panorama, TxGate};
use kria_sdr::kraken::{self, Array, PlModel, M, NA};
use kria_sdr::pl;
use std::collections::HashMap;
use std::fmt::Write as _;
use std::fs;
use std::path::{Path, PathBuf};

fn setup(dir: &Path) -> HashMap<String, f64> {
    let t = fs::read_to_string(dir.join("setup.txt")).expect("setup.txt");
    t.lines()
        .filter_map(|l| l.split_once('='))
        .map(|(k, v)| (k.trim().to_string(), v.trim().parse::<f64>().expect("number")))
        .collect()
}

fn json_arr(v: &[f64], prec: usize) -> String {
    let mut s = String::from("[");
    for (i, x) in v.iter().enumerate() {
        if i > 0 {
            s.push(',');
        }
        write!(s, "{:.*}", prec, x).unwrap();
    }
    s.push(']');
    s
}

/// Reads the five channels' files the way the transfers arrive: one 256 KiB transfer at a time from whichever
/// device's callback fires next (a fixed pseudo-random order here).
fn read_kraken(dir: &Path, xfer: usize) -> kraken::Reassembler {
    let files: Vec<Vec<u8>> = (0..M).map(|k| fs::read(dir.join(format!("ch{k}.u8"))).expect("channel file")).collect();
    let mut pos = [0usize; M];
    let mut ra = kraken::Reassembler::default();
    let mut seed: u64 = 0x2545_f491_4f6c_dd1d;
    loop {
        let pending: Vec<usize> = (0..M).filter(|&k| pos[k] < files[k].len()).collect();
        if pending.is_empty() {
            break;
        }
        seed ^= seed << 13;
        seed ^= seed >> 7;
        seed ^= seed << 17;
        let k = pending[(seed % pending.len() as u64) as usize];
        let end = (pos[k] + xfer).min(files[k].len());
        ra.push(k, &files[k][pos[k]..end]);
        pos[k] = end;
    }
    ra
}

fn kraken_pre(dir: &Path) {
    let s = setup(dir);
    let (f_rf, radius, noise_n, xfer) = (s["f_rf"], s["radius_m"], s["noise_n"] as usize, s["xfer"] as usize);
    let lambda = 299_792_458.0 / f_rf;
    let n_log2 = s.get("n_log2").copied().unwrap_or(15.0) as u32;
    let ra = read_kraken(dir, xfer);
    let ch: Vec<Vec<C>> = ra.streams.iter().map(|b| kraken::rtl_to_c(b)).collect();

    // 1. delays and weights from the noise source's burst
    let lag = kraken::estimate_delays(&ch, 8192, 64);
    let st = kraken::align_starts(&lag);
    let cal_from = 1024;
    let cal_n = noise_n - 1024 - 64;
    let xs: Vec<&[C]> = (0..M).map(|k| &ch[k][st[k] + cal_from..]).collect();
    let w = kraken::estimate_weights(&xs, cal_n);
    let wq: [u32; M] = core::array::from_fn(|k| kraken::q14(w[k]));

    // 2. the CPI after the noise source is off, aligned, as int8 snapshots
    let cpi_from = noise_n + 1024;
    let n = 1usize << n_log2;
    let snaps: Vec<[[i8; 2]; M]> = (0..n)
        .map(|t| {
            core::array::from_fn(|k| {
                let i = st[k] + cpi_from + t;
                let b = &ra.streams[k];
                [kraken::rtl_to_i8(b[2 * i]), kraken::rtl_to_i8(b[2 * i + 1])]
            })
        })
        .collect();

    // 3. the PL's inputs and, from the bit-exact model, what it must return
    let arr = Array::uca(radius);
    let table = kraken::steering_table(&arr, lambda);
    let model = PlModel::accumulate(&wq, &snaps);
    let shift = model.pick_shift();
    let p = model.scan(&table, shift);

    let mut rec = pl::Recorder { id: pl::doa::ID_VALUE, ..Default::default() };
    pl::doa_setup(&mut rec, &wq, &table, n_log2);
    let mut regs = String::new();
    for (a, v) in &rec.writes {
        writeln!(regs, "{:04x} {:08x}", a, v).unwrap();
    }
    fs::write(dir.join("doa_regs.txt"), regs).unwrap();
    let mut stim = String::new();
    for sn in &snaps {
        let b = kraken::pack_beats(sn);
        writeln!(stim, "{:016x}\n{:016x}", b[0], b[1]).unwrap();
    }
    fs::write(dir.join("doa_stim.hex"), stim).unwrap();
    let mut exp = format!("{n_log2} {shift}\n");
    for e in 0..15 {
        writeln!(exp, "{} {}", model.r_re[e], model.r_im[e]).unwrap();
    }
    for v in &p {
        writeln!(exp, "{v}").unwrap();
    }
    fs::write(dir.join("doa_expect.txt"), exp).unwrap();

    let wdeg: Vec<f64> = w.iter().map(|c| c.arg().to_degrees()).collect();
    let wabs: Vec<f64> = w.iter().map(|c| c.abs()).collect();
    let cal = format!(
        "{{\"lag\":{},\"weight_deg\":{},\"weight_abs\":{},\"shift\":{shift},\"n_log2\":{n_log2}}}\n",
        json_arr(&lag.iter().map(|&x| x as f64).collect::<Vec<_>>(), 0),
        json_arr(&wdeg, 3),
        json_arr(&wabs, 4)
    );
    fs::write(dir.join("kraken_cal.json"), cal).unwrap();
    println!("kraken-pre: lags {:?}, weights (deg) {:?}, {} snapshots, SHIFT {}", lag, wdeg.iter().map(|d| d.round()).collect::<Vec<_>>(), n, shift);
}

fn kraken_post(dir: &Path) {
    let s = setup(dir);
    let lambda = 299_792_458.0 / s["f_rf"];
    let arr = Array::uca(s["radius_m"]);
    let t = fs::read_to_string(dir.join("doa_rtl.txt")).expect("doa_rtl.txt from the bench");
    let mut lines = t.lines();
    let _hdr = lines.next();
    let mut model = PlModel { r_re: [0; 15], r_im: [0; 15] };
    for e in 0..15 {
        let l = lines.next().unwrap();
        let mut it = l.split_whitespace().map(|x| x.parse::<i64>().unwrap());
        model.r_re[e] = it.next().unwrap();
        model.r_im[e] = it.next().unwrap();
    }
    let p: Vec<f64> = lines.take(NA).map(|l| l.trim().parse::<f64>().unwrap()).collect();
    let pmax = p.iter().cloned().fold(f64::MIN, f64::max);
    let bart: Vec<f64> = p.iter().map(|v| 10.0 * (v.max(1.0) / pmax).log10()).collect();
    let r = model.matrix();
    let (mus, d, eig) = kraken::music(&r, &arr, lambda, 10.0);
    // MUSIC's peak heights say nothing about power: order the sources by the Bartlett (beamformer) power there
    let mut pk = kraken::peaks(&mus, d);
    let bart_at = |b: f64| bart[(b.round() as usize) % NA];
    pk.sort_by(|x, y| bart_at(y.0).partial_cmp(&bart_at(x.0)).unwrap());
    let pk: Vec<(f64, f64)> = pk.iter().map(|q| (q.0, bart_at(q.0))).collect();
    let bpk = kraken::peaks(&bart, 2);
    let eig_db: Vec<f64> = eig.iter().map(|l| 10.0 * (l / eig[M - 1]).log10()).collect();
    let js = format!(
        "{{\"f_rf\":{},\"cal\":{},\"sources\":{d},\"music_bearings\":{},\"beam_power_db\":{},\"bartlett_bearings\":{},\"eig_db\":{},\"bartlett_db\":{},\"music_db\":{}}}\n",
        s["f_rf"],
        fs::read_to_string(dir.join("kraken_cal.json")).map(|c| c.trim().to_string()).unwrap_or_else(|_| "null".into()),
        json_arr(&pk.iter().map(|q| q.0).collect::<Vec<_>>(), 2),
        json_arr(&pk.iter().map(|q| q.1).collect::<Vec<_>>(), 2),
        json_arr(&bpk.iter().map(|q| q.0).collect::<Vec<_>>(), 2),
        json_arr(&eig_db, 2),
        json_arr(&bart, 2),
        json_arr(&mus, 2)
    );
    // kria-hmid passes this record to the Bearing screen (its --sdr-out; a copy is in sw/hmi/sdr/)
    fs::write(dir.join("kraken_doa.json"), js).unwrap();
    println!(
        "kraken-post: {} source(s); MUSIC {:?}; Bartlett {:?}",
        d,
        pk.iter().map(|q| (q.0 * 10.0).round() / 10.0).collect::<Vec<_>>(),
        bpk.iter().map(|q| (q.0 * 10.0).round() / 10.0).collect::<Vec<_>>()
    );
}

fn hackrf_pre(dir: &Path) {
    let s = setup(dir);
    let pshift = s.get("pshift").copied().unwrap_or(3.0) as u32;
    let nseg_log2 = s.get("nseg_log2").copied().unwrap_or(3.0) as u32;
    let raw = fs::read(dir.join("sweep.bin")).expect("sweep.bin");
    let win = hackrf::window_q15();
    let twd = hackrf::twiddles_q15();
    let mut rec = pl::Recorder { id: pl::sweep::ID_VALUE, ..Default::default() };
    pl::sweep_setup(&mut rec, &win, &twd, pshift, nseg_log2);
    let mut regs = String::new();
    for (a, v) in &rec.writes {
        writeln!(regs, "{:03x} {:08x}", a, v).unwrap();
    }
    fs::write(dir.join("sweep_regs.txt"), regs).unwrap();
    let mut stim = String::new();
    let mut exp = String::new();
    let (mut good, mut bad) = (0, 0);
    for b in raw.chunks_exact(hackrf::BLOCK) {
        for q in b.chunks_exact(8) {
            writeln!(stim, "{:016x}", u64::from_le_bytes(q.try_into().unwrap())).unwrap();
        }
        match hackrf::pl_block(b, &win, &twd, pshift, nseg_log2) {
            Some((f, p)) => {
                for v in hackrf::out_beats(f, &p) {
                    writeln!(exp, "{:016x}", v).unwrap();
                }
                good += 1;
            }
            None => bad += 1,
        }
    }
    fs::write(dir.join("sweep_stim.hex"), stim).unwrap();
    fs::write(dir.join("sweep_expect.hex"), exp).unwrap();
    fs::write(dir.join("sweep_counts.txt"), format!("{good} {bad}\n")).unwrap();
    println!("hackrf-pre: {good} blocks for the PL, {bad} with a bad header");
}

fn hackrf_post(dir: &Path) {
    let s = setup(dir);
    let pshift = s.get("pshift").copied().unwrap_or(3.0) as u32;
    let nseg_log2 = s.get("nseg_log2").copied().unwrap_or(3.0) as u32;
    let t = fs::read_to_string(dir.join("sweep_rtl.hex")).expect("sweep_rtl.hex from the bench");
    let beats: Vec<u64> = t.lines().map(|l| u64::from_str_radix(l.trim(), 16).unwrap()).collect();
    let mut pan = Panorama::new(0.0, 7.25e9);
    for blk in beats.chunks_exact(65) {
        let f = blk[0];
        let mut p = Vec::with_capacity(128);
        for &b in &blk[1..] {
            p.push(b as u32);
            p.push((b >> 32) as u32);
        }
        pan.place(f, &p, pshift as i32 - nseg_log2 as i32);
    }
    // the screen's trace: 1 MHz per point, the maximum of the bins in it
    let mut trace = vec![-150.0f64; 7250];
    for (i, &d) in pan.db.iter().enumerate() {
        let mhz = (pan.freq(i) / 1e6).floor() as usize;
        if mhz < trace.len() && pan.filled[i] {
            trace[mhz] = trace[mhz].max(d);
        }
    }
    let sig = pan.signals(s.get("detect_db").copied().unwrap_or(5.0));
    let covered = pan.filled.iter().filter(|&&f| f).count() as f64 / pan.filled.len() as f64;
    let gate = TxGate::amateur_r1();
    let tx_cases = [(2400.1e6, 12.5e3, true), (2400.1e6, 12.5e3, false), (2412e6, 12.5e3, true), (5760.1e6, 12.5e3, true)];
    let mut txs = String::from("[");
    for (i, (f, bw, il)) in tx_cases.iter().enumerate() {
        if i > 0 {
            txs.push(',');
        }
        write!(txs, "{{\"f\":{f},\"bw\":{bw},\"interlock\":{il},\"state\":\"{:?}\"}}", gate.check(*f, *bw, *il)).unwrap();
    }
    txs.push(']');
    let mut sj = String::from("[");
    for (i, (f, bw, pk)) in sig.iter().take(64).enumerate() {
        if i > 0 {
            sj.push(',');
        }
        write!(sj, "{{\"f\":{:.0},\"bw\":{:.0},\"dbfs\":{:.1}}}", f, bw, pk).unwrap();
    }
    sj.push(']');
    let js = format!(
        "{{\"f0\":0,\"step_hz\":1000000,\"covered\":{:.4},\"trace_db\":{},\"signals\":{},\"tx\":{}}}\n",
        covered,
        json_arr(&trace, 1),
        sj,
        txs
    );
    // kria-hmid passes this record to the Wideband screen (its --sdr-out; a copy is in sw/hmi/sdr/)
    fs::write(dir.join("hackrf_sweep.json"), js).unwrap();
    println!("hackrf-post: {} blocks, {:.1} % of 0-7.25 GHz covered, {} signals", beats.len() / 65, covered * 100.0, sig.len());
    for (f, bw, pk) in sig.iter().take(12) {
        println!("  {:9.3} MHz  {:7.3} MHz wide  {:6.1} dBFS", f / 1e6, bw / 1e6, pk);
    }
}

fn main() {
    let a: Vec<String> = std::env::args().collect();
    if a.len() < 3 {
        eprintln!("usage: kria-sdrd kraken-pre|kraken-post|hackrf-pre|hackrf-post DIR");
        std::process::exit(2);
    }
    let dir = PathBuf::from(&a[2]);
    match a[1].as_str() {
        "kraken-pre" => kraken_pre(&dir),
        "kraken-post" => kraken_post(&dir),
        "hackrf-pre" => hackrf_pre(&dir),
        "hackrf-post" => hackrf_post(&dir),
        _ => {
            eprintln!("unknown command {}", a[1]);
            std::process::exit(2);
        }
    }
}
