//! `kria-hmi`: the screens. `apply` turns one of kria-hmid's snapshots (JSON) into the Slint `Hmi` global's
//! properties: formatted figures, the traces as SVG path commands in a 1000-unit view box, the waterfall and
//! the radar map as images. The native binary (`main.rs`) and the browser build (`start`, WebAssembly) share it.

slint::include_modules!();

use serde_json::Value;
use slint::{Image, ModelRc, Rgba8Pixel, SharedPixelBuffer, SharedString, VecModel};
use std::collections::VecDeque;

#[derive(Default)]
pub struct Model {
    wf: VecDeque<Vec<f32>>,
    last_row_frames: u64,
}

fn f(v: &Value, k: &str) -> Option<f64> {
    v.get(k).and_then(|x| x.as_f64())
}
fn s(v: &Value, k: &str) -> String {
    v.get(k).and_then(|x| x.as_str()).unwrap_or("").to_string()
}
fn b(v: &Value, k: &str) -> bool {
    v.get(k).and_then(|x| x.as_bool()).unwrap_or(false)
}

fn mode_name(m: &str) -> &'static str {
    match m {
        "am" => "AM",
        "usb" => "USB",
        "lsb" => "LSB",
        "nbfm" => "NFM",
        "wbfm" => "WFM",
        "adsb" => "ADS-B",
        _ => "",
    }
}

pub fn freq_text(hz: f64) -> String {
    if hz < 30e6 {
        format!("{:.4}", hz / 1e6)
    } else {
        format!("{:.3}", hz / 1e6)
    }
}

/// A trace as path commands: `vals` from `lo` to `hi` dB onto y 300..0, x over 0..1000.
pub fn trace_path(vals: &[f64], lo: f64, hi: f64) -> String {
    if vals.is_empty() {
        return String::new();
    }
    let n = vals.len().max(2) - 1;
    let mut p = String::with_capacity(vals.len() * 14);
    for (k, v) in vals.iter().enumerate() {
        let x = 1000.0 * k as f64 / n as f64;
        let y = 300.0 * (1.0 - ((v - lo) / (hi - lo)).clamp(0.0, 1.0));
        p.push_str(&format!("{}{:.1} {:.1} ", if k == 0 { "M" } else { "L" }, x, y));
    }
    p
}

/// A spectrum in degrees (index = bearing clockwise from the nose) as a closed polar curve, view box 1000.
pub fn polar_path(db: &[f64]) -> String {
    if db.is_empty() {
        return String::new();
    }
    let hi = db.iter().cloned().fold(f64::MIN, f64::max);
    let lo = (hi - 40.0).max(db.iter().cloned().fold(f64::MAX, f64::min));
    let mut p = String::new();
    for (k, v) in db.iter().enumerate() {
        let r = 470.0 * ((v - lo) / (hi - lo)).clamp(0.02, 1.0);
        let a = (k as f64 * 360.0 / db.len() as f64).to_radians();
        p.push_str(&format!("{}{:.1} {:.1} ", if k == 0 { "M" } else { "L" }, 500.0 + r * a.sin(), 500.0 - r * a.cos()));
    }
    p.push('Z');
    p
}

fn heat(v: f32) -> [u8; 3] {
    // dark ground to amber to pale: the design's spectrum colour scale (HMI.md §2)
    let stops: [(f32, [f32; 3]); 4] = [(0.0, [10.0, 12.0, 15.0]), (0.45, [27.0, 58.0, 92.0]), (0.8, [255.0, 176.0, 32.0]), (1.0, [255.0, 243.0, 196.0])];
    let v = v.clamp(0.0, 1.0);
    for w in stops.windows(2) {
        let ((a, ca), (b, cb)) = (w[0], w[1]);
        if v <= b {
            let t = (v - a) / (b - a);
            return [0, 1, 2].map(|i| (ca[i] + t * (cb[i] - ca[i])) as u8);
        }
    }
    [255, 243, 196]
}

/// A heat map with each cell `sx` x `sy` pixels, so the renderer only scales it smoothly
/// (Slint's software renderer rounds a pixelated scale to whole steps).
fn image_from(rows: &[Vec<f32>], lo: f32, hi: f32, sx: usize, sy: usize) -> Image {
    let h = rows.len().max(1);
    let w = rows.first().map(|r| r.len()).unwrap_or(1).max(1);
    let pw = w * sx;
    let mut buf = SharedPixelBuffer::<Rgba8Pixel>::new(pw as u32, (h * sy) as u32);
    let px = buf.make_mut_slice();
    for (y, row) in rows.iter().enumerate() {
        for x in 0..w {
            let v = row.get(x).copied().unwrap_or(lo);
            let [r, g, b] = heat((v - lo) / (hi - lo));
            for yy in 0..sy {
                let base = (y * sy + yy) * pw + x * sx;
                px[base..base + sx].fill(Rgba8Pixel { r, g, b, a: 255 });
            }
        }
    }
    Image::from_rgba8(buf)
}

/// A trace drawn into a transparent `w` x `h` image: values from `lo` (bottom) to `hi` (top), an anti-aliased
/// line `width` pixels wide in `rgb`, with a faint fill under it.
pub fn trace_image(vals: &[f64], lo: f64, hi: f64, w: usize, h: usize, rgb: [u8; 3], width: f64) -> Image {
    let mut a = vec![0f32; w * h];
    let n = vals.len();
    if n >= 2 && w >= 2 && h >= 2 {
        let pt = |k: usize| {
            let x = k as f64 * (w - 1) as f64 / (n - 1) as f64;
            let y = (h - 1) as f64 * (1.0 - ((vals[k] - lo) / (hi - lo)).clamp(0.0, 1.0));
            (x, y)
        };
        // fill under the trace, fading downwards
        for xx in 0..w {
            let f = xx as f64 * (n - 1) as f64 / (w - 1) as f64;
            let k = (f.floor() as usize).min(n - 2);
            let t = f - k as f64;
            let yt = pt(k).1 * (1.0 - t) + pt(k + 1).1 * t;
            let y0 = yt.max(0.0) as usize;
            for yy in y0..h {
                a[yy * w + xx] = 0.12 * (1.0 - (yy - y0) as f32 / (h - y0).max(1) as f32);
            }
        }
        let r = width / 2.0;
        for k in 1..n {
            let ((x0, y0), (x1, y1)) = (pt(k - 1), pt(k));
            let (dx, dy) = (x1 - x0, y1 - y0);
            let l2 = (dx * dx + dy * dy).max(1e-9);
            let xa = ((x0.min(x1) - r - 1.0).floor().max(0.0)) as usize;
            let xb = ((x0.max(x1) + r + 1.0).ceil() as usize).min(w - 1);
            let ya = ((y0.min(y1) - r - 1.0).floor().max(0.0)) as usize;
            let yb = ((y0.max(y1) + r + 1.0).ceil() as usize).min(h - 1);
            for yy in ya..=yb {
                for xx in xa..=xb {
                    let (px, py) = (xx as f64, yy as f64);
                    let t = (((px - x0) * dx + (py - y0) * dy) / l2).clamp(0.0, 1.0);
                    let d = ((px - x0 - t * dx).powi(2) + (py - y0 - t * dy).powi(2)).sqrt();
                    let cov = (r + 0.5 - d).clamp(0.0, 1.0) as f32;
                    let p = &mut a[yy * w + xx];
                    *p = p.max(cov);
                }
            }
        }
    }
    let mut buf = SharedPixelBuffer::<Rgba8Pixel>::new(w as u32, h as u32);
    for (p, al) in buf.make_mut_slice().iter_mut().zip(a) {
        *p = Rgba8Pixel { r: rgb[0], g: rgb[1], b: rgb[2], a: (al.min(1.0) * 255.0) as u8 };
    }
    Image::from_rgba8(buf)
}

fn ss(x: impl Into<String>) -> SharedString {
    SharedString::from(x.into())
}

pub fn apply(ui: &AppWindow, m: &mut Model, snap: &Value) {
    let h = ui.global::<Hmi>();
    h.set_connected(true);
    h.set_clock(ss(format!("t+{:.0} s", f(snap, "t").unwrap_or(0.0))));
    h.set_function(ss(snap.get("function").and_then(|x| x.as_str()).unwrap_or("radio")));

    let r = &snap["radio"];
    let freq = f(r, "freq_hz").unwrap_or(0.0);
    h.set_freq_text(ss(freq_text(freq)));
    h.set_mode(ss(mode_name(&s(r, "mode"))));
    let path = s(r, "path");
    h.set_path_text(ss(match path.as_str() {
        "hf" => "HF · AD9253 B".to_string(),
        "direct" => "VHF direct · AD9484".to_string(),
        "converted" => format!("converter · LO {:.3} MHz", f(r, "lo_hz").unwrap_or(0.0) / 1e6),
        _ => String::new(),
    }));
    let lvl = f(r, "level_dbfs").unwrap_or(-120.0);
    h.set_level(((lvl + 90.0) / 90.0) as f32);
    h.set_level_text(ss(format!("{lvl:.1} dBFS audio · {:.1} kS/s", f(r, "audio_rate").unwrap_or(0.0) / 1e3)));
    h.set_pilot(b(r, "pilot"));
    h.set_ctcss(b(r, "ctcss"));
    let rds = &r["rds"];
    h.set_rds_ps(ss(s(rds, "ps")));
    h.set_rds_rt(ss(s(rds, "radiotext")));
    h.set_rds_extra(ss(match rds.get("pi").and_then(|x| x.as_u64()) {
        Some(pi) => format!("PI {pi:04X} · PTY {} · {} groups", rds["pty"].as_u64().unwrap_or(0), rds["groups"].as_u64().unwrap_or(0)),
        None => String::new(),
    }));
    h.set_gain_text(ss(format!("gain {:+.0} dB", f(r, "gain_db").unwrap_or(0.0))));
    let presets: Vec<Preset> = r["presets"]
        .as_array()
        .map(|a| a.iter().map(|p| Preset { name: ss(s(p, "name")), freq: ss(freq_text(f(p, "freq_hz").unwrap_or(0.0))) }).collect())
        .unwrap_or_default();
    h.set_presets(ModelRc::new(VecModel::from(presets)));

    let sp = &snap["spectrum"];
    let trace: Vec<f64> = sp["trace"].as_array().map(|a| a.iter().filter_map(|x| x.as_f64()).collect()).unwrap_or_default();
    h.set_spec_img(trace_image(&trace, -120.0, 0.0, 1600, 420, [255, 176, 32], 2.6));
    let (c, span) = (f(sp, "center_hz").unwrap_or(0.0), f(sp, "span_hz").unwrap_or(1.0).max(1.0));
    h.set_spec_title(ss(format!("SPECTRUM · STREAM 0x{:02X} · {:.3} MHz SPAN", sp["stream"].as_u64().unwrap_or(0), span / 1e6)));
    h.set_spec_left(ss(format!("{:.3} MHz", (c - span / 2.0) / 1e6)));
    h.set_spec_right(ss(format!("{:.3} MHz", (c + span / 2.0) / 1e6)));
    h.set_marker_x((((f(sp, "marker_hz").unwrap_or(c) - c) / span) + 0.5) as f32);
    let to_row = |v: &Value| -> Vec<f32> { v.as_array().map(|a| a.iter().filter_map(|x| x.as_f64()).map(|x| x as f32).collect()).unwrap_or_default() };
    if let Some(hist) = sp.get("history").and_then(|x| x.as_array()) {
        m.wf = hist.iter().map(to_row).collect();
    } else {
        let frames = sp["frames"].as_u64().unwrap_or(0);
        let row = to_row(&sp["row"]);
        if frames != m.last_row_frames && !row.is_empty() {
            m.wf.push_front(row);
            m.wf.truncate(60);
            m.last_row_frames = frames;
        }
    }
    let rows: Vec<Vec<f32>> = m.wf.iter().cloned().collect();
    h.set_waterfall(image_from(&rows, -110.0, -20.0, 2, 6));

    let a = &snap["adsb"];
    let planes: Vec<Plane> = a["aircraft"]
        .as_array()
        .map(|v| {
            v.iter()
                .filter_map(|p| {
                    let (rk, bd) = (f(p, "range_km")?, f(p, "bearing_deg")?);
                    let rr = (rk / 100.0).min(1.0) * 0.5;
                    Some(Plane {
                        callsign: ss(if s(p, "callsign").is_empty() { s(p, "icao") } else { s(p, "callsign") }),
                        alt: ss(f(p, "alt_ft").map(|x| format!("FL{:03.0}", x / 100.0)).unwrap_or_default()),
                        dist: ss(format!("{rk:.0} km")),
                        speed: ss(f(p, "speed_kt").map(|x| format!("{x:.0} kt")).unwrap_or_default()),
                        x: (0.5 + rr * bd.to_radians().sin()) as f32,
                        y: (0.5 - rr * bd.to_radians().cos()) as f32,
                        track: f(p, "track_deg").unwrap_or(0.0) as f32,
                    })
                })
                .collect()
        })
        .unwrap_or_default();
    let own = a["own"].as_array().map(|o| format!("{:.4}, {:.4}", o[0].as_f64().unwrap_or(0.0), o[1].as_f64().unwrap_or(0.0)));
    h.set_adsb_text(ss(format!("{} frames decoded · own position {}", a["frames"].as_u64().unwrap_or(0), own.unwrap_or("unknown".into()))));
    h.set_planes(ModelRc::new(VecModel::from(planes)));

    let rd = &snap["radar"];
    if let Some(map) = rd.get("map").filter(|x| !x.is_null()) {
        let rows: Vec<Vec<f32>> = map["power_db"].as_array().map(|r| r.iter().map(to_row).collect()).unwrap_or_default();
        let hi = rows.iter().flatten().cloned().fold(0f32, f32::max);
        h.set_radar_map(image_from(&rows, hi - 40.0, hi, 40, 12));
    }
    let dets: Vec<Det> = rd["detections"]
        .as_array()
        .map(|v| {
            v.iter()
                .map(|d| Det {
                    range: ss(format!("{:.1} m", f(d, "range_m").unwrap_or(0.0))),
                    speed: ss(format!("{:+.1} m/s", f(d, "speed_mps").unwrap_or(0.0))),
                    power: ss(format!("{:.0} dB", f(d, "power_db").unwrap_or(0.0))),
                    x: ((f(d, "doppler_bin").unwrap_or(0.0) + 8.5) / 16.0) as f32,
                    y: ((f(d, "range_bin").unwrap_or(0.0) + 0.5) / 64.0) as f32,
                })
                .collect()
        })
        .unwrap_or_default();
    h.set_radar_text(ss(format!("CPI {} · {} CPIs seen · {} dropped", rd["cpi"].as_u64().unwrap_or(0), rd["cpis"].as_u64().unwrap_or(0), rd["dropped"].as_u64().unwrap_or(0))));
    let alpha = rd["alpha_q8"].as_u64().unwrap_or(1536);
    h.set_cfar_text(ss(format!("α = {:.2} ({alpha}), floor {}", alpha as f64 / 256.0, rd["floor"].as_u64().unwrap_or(0) * 16)));
    h.set_dets(ModelRc::new(VecModel::from(dets)));

    let v = &snap["vehicle"];
    h.set_speed_text(ss(f(v, "speed_kmh").map(|x| format!("{x:.0}")).unwrap_or("--".into())));
    h.set_rpm_text(ss(f(v, "rpm").map(|x| format!("{x:.0} rpm")).unwrap_or("--".into())));
    h.set_coolant_text(ss(f(v, "coolant_c").map(|x| format!("{x:.0} °C")).unwrap_or("--".into())));
    h.set_fuel_text(ss(f(v, "fuel_pct").map(|x| format!("{x:.0} %")).unwrap_or("--".into())));
    h.set_veh_source(ss(s(v, "source")));

    let t = &snap["tx"];
    h.set_tx_freq(ss(format!("{:.3}", f(t, "freq_hz").unwrap_or(0.0) / 1e6)));
    h.set_tx_mode(ss(s(t, "mode").to_uppercase()));
    h.set_tx_mode_id(ss(s(t, "mode")));
    h.set_tx_freq_hz(f(t, "freq_hz").unwrap_or(0.0) as f32);
    h.set_tx_level_f(f(t, "level").unwrap_or(0.0) as f32);
    h.set_tx_level(ss(format!("{:.0} %", f(t, "level").unwrap_or(0.0) * 100.0)));
    let keyed = b(t, "keyed");
    let reason = s(t, "reason");
    h.set_tx_state(ss(if keyed { "On air".to_string() } else if reason == "idle" { "Ready".to_string() } else { format!("Locked: {reason}") }));
    h.set_tx_keyed(keyed);
    h.set_tx_licensed(b(t, "licensed"));
    h.set_tx_requested(b(t, "requested"));

    if let Some(w) = snap.get("wideband").filter(|x| !x.is_null()) {
        let mut tr: Vec<f64> = w["trace_db"].as_array().map(|a| a.iter().filter_map(|x| x.as_f64()).collect()).unwrap_or_default();
        // bins the sweep has not reached yet read -150 dB: hold the last swept value over them, so the trace keeps
        // its frequency scale without a cliff
        let mut last = tr.iter().cloned().find(|&v| v > -149.0).unwrap_or(-100.0);
        for v in tr.iter_mut() {
            if *v <= -149.0 {
                *v = last;
            } else {
                last = *v;
            }
        }
        let step = (tr.len() / 1000).max(1);
        // whole chunks only: a short last chunk is the sweep's unfilled tail
        let dec: Vec<f64> = tr.chunks_exact(step).map(|c| c.iter().cloned().fold(f64::MIN, f64::max)).collect();
        h.set_wb_img(trace_image(&dec, -100.0, 0.0, 1800, 420, [255, 176, 32], 2.0));
        let mut sigs: Vec<&Value> = w["signals"].as_array().map(|a| a.iter().collect()).unwrap_or_default();
        let marks: Vec<Sig> = sigs
            .iter()
            .map(|g| Sig { label: ss(""), x: (f(g, "f").unwrap_or(0.0) / 7.2e9) as f32, w: 0.0 })
            .collect();
        h.set_wb_signals(ModelRc::new(VecModel::from(marks)));
        sigs.sort_by(|a, b| f(b, "dbfs").partial_cmp(&f(a, "dbfs")).unwrap_or(std::cmp::Ordering::Equal));
        let top: Vec<String> = sigs.iter().take(8).map(|g| format!("{:.2} MHz {:.0} dBFS", f(g, "f").unwrap_or(0.0) / 1e6, f(g, "dbfs").unwrap_or(0.0))).collect();
        h.set_wb_text(ss(format!("{} signals, {:.1} % of the band covered.  {}", w["signals"].as_array().map(|a| a.len()).unwrap_or(0), f(w, "covered").unwrap_or(0.0) * 100.0, top.join(" · "))));
    }
    if let Some(d) = snap.get("bearing").filter(|x| !x.is_null()) {
        let arr = |k: &str| -> Vec<f64> { d[k].as_array().map(|a| a.iter().filter_map(|x| x.as_f64()).collect()).unwrap_or_default() };
        h.set_bart_path(ss(polar_path(&arr("bartlett_db"))));
        h.set_music_path(ss(polar_path(&arr("music_db"))));
        let (bear, pow) = (arr("music_bearings"), arr("beam_power_db"));
        // each source's dot at the tip of its MUSIC peak, on the same scale as polar_path
        let music = arr("music_db");
        let tip = |bd: f64| -> f64 {
            if music.is_empty() {
                return 0.47;
            }
            let hi = music.iter().cloned().fold(f64::MIN, f64::max);
            let lo = (hi - 40.0).max(music.iter().cloned().fold(f64::MAX, f64::min));
            let n = music.len();
            let k = ((bd.rem_euclid(360.0) * n as f64 / 360.0).round() as usize) % n;
            let v = (-2..=2).map(|d| music[(k as i64 + d).rem_euclid(n as i64) as usize]).fold(f64::MIN, f64::max);
            0.47 * ((v - lo) / (hi - lo)).clamp(0.02, 1.0)
        };
        let srcs: Vec<Src> = bear
            .iter()
            .zip(pow.iter().chain(std::iter::repeat(&0.0)))
            .map(|(&bd, &p)| Src {
                bearing: ss(format!("{bd:.1}°")),
                power: ss(format!("{p:.1} dB")),
                x: (0.5 + tip(bd) * bd.to_radians().sin()) as f32,
                y: (0.5 - tip(bd) * bd.to_radians().cos()) as f32,
            })
            .collect();
        h.set_sources(ModelRc::new(VecModel::from(srcs)));
        let eig: Vec<String> = arr("eig_db").iter().map(|x| format!("{x:.0}")).collect();
        h.set_doa_text(ss(format!(
            "{:.3} MHz · {} sources · eigenvalues {} dB · calibration lags {:?}",
            f(d, "f_rf").unwrap_or(0.0) / 1e6,
            d["sources"].as_u64().unwrap_or(0),
            eig.join(" / "),
            d["cal"]["lag"].as_array().map(|a| a.iter().filter_map(|x| x.as_i64()).collect::<Vec<_>>()).unwrap_or_default()
        )));
    }

    let sy = &snap["system"];
    let row = |k: &str, v: String, ok: bool| Row { key: ss(k), value: ss(v), ok };
    let opt = |k: &str| f(sy, k).map(|x| format!("{x:.1} °C")).unwrap_or("--".into());
    let rows = vec![
        row("IAS1 link", if b(sy, "link_up") { "up".into() } else { "down".into() }, b(sy, "link_up")),
        row("Packets / blocks", format!("{} / {}", sy["packets"].as_u64().unwrap_or(0), sy["blocks"].as_u64().unwrap_or(0)), true),
        row("Sequence gaps", format!("{}", sy["seq_gaps"].as_u64().unwrap_or(0)), sy["seq_gaps"].as_u64().unwrap_or(0) == 0),
        row("CRC errors", format!("{}", sy["crc_errors"].as_u64().unwrap_or(0)), sy["crc_errors"].as_u64().unwrap_or(0) == 0),
        row("Stream to the A53s", format!("{:.1} Mb/s", f(sy, "stream_mbps").unwrap_or(0.0)), true),
        row("K26 / Artix", format!("{} / {}", opt("temp_k26_c"), opt("temp_artix_c")), true),
        row("R5F core 0", s(sy, "r5f0"), true),
        row("R5F core 1", s(sy, "r5f1"), true),
        row("Platform", s(sy, "platform"), true),
        row(
            "I/Q recording",
            if s(sy, "rec_file").is_empty() { "none".into() } else { format!("{} ({:.1} MB)", s(sy, "rec_file"), sy["rec_bytes"].as_u64().unwrap_or(0) as f64 / 1e6) },
            !s(sy, "rec_file").starts_with("error"),
        ),
    ];
    h.set_rows(ModelRc::new(VecModel::from(rows)));
    h.set_recording(b(sy, "recording"));
    h.set_rec_text(ss(format!("{:.1} MB", sy["rec_bytes"].as_u64().unwrap_or(0) as f64 / 1e6)));
}

#[cfg(target_arch = "wasm32")]
mod web {
    use super::*;
    use std::cell::RefCell;
    use std::rc::Rc;
    use wasm_bindgen::prelude::*;
    use web_sys::{MessageEvent, WebSocket};

    #[wasm_bindgen(start)]
    pub fn start() {
        console_error_panic_hook::set_once();
        let ui = AppWindow::new().expect("window");
        let host = web_sys::window().and_then(|w| w.location().host().ok()).unwrap_or_default();
        let ws = WebSocket::new(&format!("ws://{host}/ws")).expect("websocket");
        let model = Rc::new(RefCell::new(Model::default()));
        let weak = ui.as_weak();
        let on_msg = Closure::<dyn FnMut(MessageEvent)>::new(move |e: MessageEvent| {
            if let (Some(t), Some(ui)) = (e.data().as_string(), weak.upgrade()) {
                if let Ok(v) = serde_json::from_str::<Value>(&t) {
                    apply(&ui, &mut model.borrow_mut(), &v);
                }
            }
        });
        ws.set_onmessage(Some(on_msg.as_ref().unchecked_ref()));
        on_msg.forget();
        let ws2 = ws.clone();
        ui.global::<Hmi>().on_send(move |c| {
            let _ = ws2.send_with_str(&c);
        });
        ui.run().expect("run");
    }
}
