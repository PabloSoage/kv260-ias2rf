//! The I/Q recorder behind "Record IQ": the spectrum stream to a `.cs16` file (interleaved little-endian 16-bit
//! I and Q) with a `.json` beside it that says what it is.

use kria_hmi_core::state::Hmi;
use std::fs::File;
use std::io::{BufWriter, Write};
use std::path::PathBuf;
use std::time::{SystemTime, UNIX_EPOCH};

pub struct Recorder {
    dir: PathBuf,
    out: Option<(BufWriter<File>, PathBuf, u64)>,
}

impl Recorder {
    pub fn new(dir: PathBuf) -> Self {
        Self { dir, out: None }
    }

    /// Opens, writes or closes the file to follow `hmi.snap.system.recording`, and reports into the snapshot.
    pub fn step(&mut self, hmi: &mut Hmi) {
        let on = hmi.snap.system.recording;
        if on && self.out.is_none() {
            match self.open(hmi) {
                Ok(o) => {
                    hmi.snap.system.rec_file = o.1.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_default();
                    self.out = Some(o);
                }
                Err(e) => {
                    eprintln!("kria-hmid: cannot record into {}: {e}", self.dir.display());
                    hmi.snap.system.recording = false;
                    hmi.snap.system.rec_file = format!("error: {e}");
                }
            }
        }
        if let Some((w, path, n)) = &mut self.out {
            let mut buf = Vec::with_capacity(hmi.rec_out.len() * 4);
            for &(i, q) in &hmi.rec_out {
                buf.extend_from_slice(&i.to_le_bytes());
                buf.extend_from_slice(&q.to_le_bytes());
            }
            if let Err(e) = w.write_all(&buf) {
                eprintln!("kria-hmid: recording stopped, {}: {e}", path.display());
                hmi.snap.system.recording = false;
            }
            *n += buf.len() as u64;
            hmi.snap.system.rec_bytes = *n;
            if !hmi.snap.system.recording {
                let _ = w.flush();
                eprintln!("kria-hmid: recorded {} bytes into {}", n, path.display());
                self.out = None;
            }
        }
        hmi.rec_out.clear();
    }

    fn open(&self, hmi: &Hmi) -> std::io::Result<(BufWriter<File>, PathBuf, u64)> {
        std::fs::create_dir_all(&self.dir)?;
        let sp = &hmi.snap.spectrum;
        let unix = SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0);
        let stem = format!("iq_{:.6}MHz_{:.0}kSps_s{:02X}_{unix}", sp.center_hz / 1e6, sp.span_hz / 1e3, sp.stream);
        let path = self.dir.join(format!("{stem}.cs16"));
        let meta = serde_json::json!({
            "format": "cs16: interleaved I, Q; signed 16-bit little-endian",
            "center_hz": sp.center_hz,
            "sample_rate": sp.span_hz,
            "stream": sp.stream,
            "mode": hmi.snap.radio.mode,
            "unix_time": unix,
        });
        std::fs::write(self.dir.join(format!("{stem}.json")), serde_json::to_string_pretty(&meta).unwrap_or_default())?;
        let f = File::create(&path)?;
        Ok((BufWriter::with_capacity(1 << 20, f), path.clone(), 0)).map(|o| {
            eprintln!("kria-hmid: recording into {}", path.display());
            o
        })
    }
}
