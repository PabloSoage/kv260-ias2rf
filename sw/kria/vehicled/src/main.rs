//! kria-vehicled: the ECU stream on the board.
//!
//! Connects to an `opendash-telemetry/1` server (opendash on the phone, port
//! 35001, or any bridge that speaks it), asks for a selection, keeps the latest
//! value of every row, and every 50 ms hands road speed to R5F core 0 through
//! the shared mailbox (`kria_core::mailbox`), stamped with the PL clock both
//! sides read. R5F core 0 runs the transmit interlock on it; this daemon only
//! reports.
//!
//! ```text
//! kria-vehicled [--server HOST:PORT] [--select ID,ID,..] [--always ID,..]
//!               [--speed-id 0x000D] [--licensed] [--mailbox devmem|none]
//!               [--interlock] [--seconds N] [--csv FILE]
//!               [--then-select ID,..] [--then-after S]
//!               [--can BITRATE] [--can-speed ID:START:LEN:intel|motorola:NUM/DEN[:OFFSET]] [--can-active]
//! ```
//!
//! `--mailbox devmem` (Linux on the KV260) writes the mailbox at
//! `kria_core::mailbox::BASE` and reads the PL clock from `kria_pps` through
//! `/dev/mem`. `none` keeps a local clock and writes nothing, for a PC.
//! `--can` enables the vehicle's CAN bus on R5F core 1 (`kria_core::can`):
//! it writes `CanConfig` into the mailbox, listen-only unless `--can-active`.
//! `--can-speed` is the car's road-speed signal as its DBC gives it, scaled to
//! 0.01 km/h (`0x0D0:16:16:intel:1/1` is a 16-bit Intel signal from bit 16 in
//! 0.01 km/h; an extended identifier ends in `x`, e.g. `0x18FEF100x`). Core 1
//! then decodes the speed straight from the bus, and core 0 takes whichever of
//! that and this daemon's ECU stream is fresher. With `--can` and no
//! telemetry server, the daemon keeps running on the bus alone.
//!
//! `--interlock` runs the R5F's interlock here as well and prints its decision,
//! so the whole chain can be watched on a PC. `--then-select` sends a second
//! selection after `--then-after` seconds, the way a screen would on changing
//! page, and the CSV shows the gap that costs.

use kria_core::interlock::{Config as IlConfig, Inputs, Interlock, Speed};
use kria_core::can::{self, CanConfig, Signal};
use kria_core::mailbox::{self, ToR5f};
use kria_core::telemetry::{self, Line};
use std::collections::HashMap;
use std::io::{BufRead, BufReader, Write};
use std::net::TcpStream;
use std::time::{Duration, Instant};

const TICK_HZ: u64 = 100_000_000;
/// `kria_pps` registers at 0x8002_0000: NOW_LO, NOW_HI.
#[cfg(unix)]
const PPS_BASE: u64 = 0x8002_0000;
#[cfg(unix)]
const NOW_LO: u64 = 0x2C;
#[cfg(unix)]
const NOW_HI: u64 = 0x30;

struct Args {
    server: String,
    select: Vec<String>,
    always: Vec<String>,
    speed_id: String,
    licensed: bool,
    devmem: bool,
    interlock: bool,
    seconds: Option<u64>,
    csv: Option<String>,
    then_select: Vec<String>,
    then_after: u64,
    can: Option<CanConfig>,
}

/// `ID[x]:START:LEN:intel|motorola:NUM/DEN[:OFFSET]`
fn parse_signal(s: &str) -> Option<Signal> {
    let f: Vec<&str> = s.split(':').collect();
    if f.len() < 5 {
        return None;
    }
    let (idt, extended) = match f[0].strip_suffix('x') {
        Some(x) => (x, true),
        None => (f[0], false),
    };
    let id = u32::from_str_radix(idt.trim_start_matches("0x"), 16).ok()?;
    let (num, den) = f[4].split_once('/').unwrap_or((f[4], "1"));
    Some(Signal {
        id,
        extended,
        start: f[1].parse().ok()?,
        len: f[2].parse().ok()?,
        motorola: match f[3] {
            "motorola" => true,
            "intel" => false,
            _ => return None,
        },
        num: num.parse().ok()?,
        den: den.parse().ok()?,
        offset: f.get(5).map_or(Some(0), |o| o.parse().ok())?,
    })
}

/// Written by kria-hmid: the screens' transmit request and licence flag.
const HMI_TX_FILE: &str = "/run/kria-hmi/tx";

fn args() -> Args {
    let mut a = Args {
        server: "127.0.0.1:35001".into(),
        select: vec!["0x000D".into(), "0x000C".into(), "0x0005".into(), "0x000B".into()],
        always: vec!["0x000D".into()],
        speed_id: "0x000D".into(),
        licensed: false,
        devmem: cfg!(target_os = "linux") && cfg!(target_arch = "aarch64"),
        interlock: false,
        seconds: None,
        csv: None,
        then_select: vec![],
        then_after: 10,
        can: None,
    };
    let v: Vec<String> = std::env::args().skip(1).collect();
    let list = |s: &str| s.split(',').filter(|x| !x.is_empty()).map(String::from).collect::<Vec<_>>();
    let mut i = 0;
    while i < v.len() {
        let next = v.get(i + 1).cloned().unwrap_or_default();
        match v[i].as_str() {
            "--server" => { a.server = next; i += 1 }
            "--select" => { a.select = list(&next); i += 1 }
            "--always" => { a.always = list(&next); i += 1 }
            "--speed-id" => { a.speed_id = next; i += 1 }
            "--licensed" => a.licensed = true,
            "--mailbox" => { a.devmem = next == "devmem"; i += 1 }
            "--interlock" => a.interlock = true,
            "--seconds" => { a.seconds = next.parse().ok(); i += 1 }
            "--csv" => { a.csv = Some(next); i += 1 }
            "--then-select" => { a.then_select = list(&next); i += 1 }
            "--then-after" => { a.then_after = next.parse().unwrap_or(10); i += 1 }
            "--can" => {
                let c = a.can.get_or_insert_with(CanConfig::default);
                c.enabled = true;
                c.bitrate = next.parse().unwrap_or(500_000);
                i += 1
            }
            "--can-speed" => {
                let sig = parse_signal(&next).unwrap_or_else(|| {
                    eprintln!("--can-speed: expected ID[x]:START:LEN:intel|motorola:NUM/DEN[:OFFSET], got {next}");
                    std::process::exit(2)
                });
                a.can.get_or_insert_with(|| CanConfig { enabled: true, ..Default::default() }).speed = Some(sig);
                i += 1
            }
            "--can-active" => a.can.get_or_insert_with(|| CanConfig { enabled: true, ..Default::default() }).active = true,
            other => {
                eprintln!("unknown argument {other}");
                std::process::exit(2);
            }
        }
        i += 1;
    }
    a
}

/// The PL clock and the mailbox. On the board both are physical memory.
trait Platform {
    fn now(&mut self) -> u64;
    fn write_mailbox(&mut self, half: &[u8; mailbox::HALF], seq_odd: u32, seq_even: u32);
    fn read_r5f(&mut self) -> Option<mailbox::FromR5f>;
    /// Seqlock write of a 64-byte block this daemon owns, at `off` in the mailbox.
    fn write_block(&mut self, _off: usize, _b: &[u8; 64], _seq_odd: u32, _seq_even: u32) {}
    /// Core 1's report on the bus.
    fn read_can(&mut self) -> Option<can::CanStatus> {
        None
    }
}

struct Pc {
    t0: Instant,
}

impl Platform for Pc {
    fn now(&mut self) -> u64 {
        (self.t0.elapsed().as_nanos() * TICK_HZ as u128 / 1_000_000_000) as u64
    }
    fn write_mailbox(&mut self, _: &[u8; mailbox::HALF], _: u32, _: u32) {}
    fn read_r5f(&mut self) -> Option<mailbox::FromR5f> {
        None
    }
}

#[cfg(unix)]
struct DevMem {
    f: std::fs::File,
}

#[cfg(unix)]
impl DevMem {
    fn open() -> std::io::Result<Self> {
        let f = std::fs::OpenOptions::new().read(true).write(true).open("/dev/mem")?;
        Ok(Self { f })
    }
    fn rd32(&self, addr: u64) -> u32 {
        use std::os::unix::fs::FileExt;
        let mut b = [0u8; 4];
        let _ = self.f.read_at(&mut b, addr);
        u32::from_le_bytes(b)
    }
}

#[cfg(unix)]
impl Platform for DevMem {
    fn now(&mut self) -> u64 {
        // Reading NOW_LO latches NOW_HI, and both R5F cores read it too, so
        // another reader's latch can land between ours: two pairs that agree,
        // with no wrap of the low word between them, are consistent.
        loop {
            let lo = self.rd32(PPS_BASE + NOW_LO);
            let hi = self.rd32(PPS_BASE + NOW_HI);
            let lo2 = self.rd32(PPS_BASE + NOW_LO);
            let hi2 = self.rd32(PPS_BASE + NOW_HI);
            if hi == hi2 && lo2 >= lo {
                return (hi as u64) << 32 | lo as u64;
            }
        }
    }
    fn write_mailbox(&mut self, half: &[u8; mailbox::HALF], seq_odd: u32, seq_even: u32) {
        use std::os::unix::fs::FileExt;
        let at = mailbox::BASE + mailbox::TO_R5F as u64;
        let seq = at + mailbox::SEQ as u64;
        let _ = self.f.write_at(&seq_odd.to_le_bytes(), seq);
        let _ = self.f.write_at(&half[..mailbox::SEQ], at);
        let _ = self.f.write_at(&half[mailbox::SEQ + 4..], seq + 4);
        let _ = self.f.write_at(&seq_even.to_le_bytes(), seq);
    }
    fn write_block(&mut self, off: usize, b: &[u8; 64], seq_odd: u32, seq_even: u32) {
        use std::os::unix::fs::FileExt;
        let at = mailbox::BASE + off as u64;
        let seq = at + mailbox::SEQ as u64;
        let _ = self.f.write_at(&seq_odd.to_le_bytes(), seq);
        let _ = self.f.write_at(&b[..mailbox::SEQ], at);
        let _ = self.f.write_at(&b[mailbox::SEQ + 4..], seq + 4);
        let _ = self.f.write_at(&seq_even.to_le_bytes(), seq);
    }
    fn read_can(&mut self) -> Option<can::CanStatus> {
        use std::os::unix::fs::FileExt;
        let at = mailbox::BASE + can::STATUS as u64;
        for _ in 0..4 {
            let mut x = [0u8; 64];
            let mut y = [0u8; 64];
            self.f.read_at(&mut x, at).ok()?;
            self.f.read_at(&mut y, at).ok()?;
            if x == y {
                return can::decode_status(&x);
            }
        }
        None
    }
    fn read_r5f(&mut self) -> Option<mailbox::FromR5f> {
        use std::os::unix::fs::FileExt;
        let at = mailbox::BASE + mailbox::FROM_R5F as u64;
        for _ in 0..4 {
            let mut a = [0u8; mailbox::HALF];
            let mut b = [0u8; mailbox::HALF];
            self.f.read_at(&mut a, at).ok()?;
            self.f.read_at(&mut b, at).ok()?;
            if a == b {
                return mailbox::decode_from_r5f(&a);
            }
        }
        None
    }
}

fn platform(devmem: bool) -> Box<dyn Platform> {
    #[cfg(unix)]
    if devmem {
        match DevMem::open() {
            Ok(d) => return Box::new(d),
            Err(e) => eprintln!("/dev/mem: {e}; running without the mailbox"),
        }
    }
    let _ = devmem;
    Box::new(Pc { t0: Instant::now() })
}

fn send_select(s: &mut TcpStream, rows: &[String], always: &[String]) -> std::io::Result<()> {
    let r: Vec<&str> = rows.iter().map(String::as_str).collect();
    let a: Vec<&str> = always.iter().map(String::as_str).collect();
    let mut line = String::new();
    telemetry::write_select(&mut line, &r, &a, true).expect("formatting");
    s.write_all(line.as_bytes())
}

fn main() {
    let a = args();
    let mut pf = platform(a.devmem);
    // the telemetry server; with --can the daemon also runs without one, on the bus alone
    let mut stream = match TcpStream::connect(&a.server) {
        Ok(s) => Some(s),
        Err(e) if a.can.is_some() => {
            eprintln!("cannot reach {}: {e}; running on the vehicle's CAN bus alone", a.server);
            None
        }
        Err(e) => {
            eprintln!("cannot reach {}: {e}", a.server);
            std::process::exit(1);
        }
    };
    let mut reader = None;
    if let Some(s) = stream.as_mut() {
        s.set_nodelay(true).ok();
        s.set_read_timeout(Some(Duration::from_millis(50))).ok();
        reader = Some(BufReader::new(s.try_clone().expect("socket clone")));
        send_select(s, &a.select, &a.always).expect("send selection");
        eprintln!("connected to {}; selection {:?}, always {:?}", a.server, a.select, a.always);
    }
    if let Some(c) = &a.can {
        eprintln!(
            "CAN: {} bit/s, {}, speed {}",
            c.bitrate,
            if c.active { "active (sends and acknowledges)" } else { "listen only" },
            c.speed.map_or("not decoded".to_string(), |s| format!("{s:?}"))
        );
    }
    let mut can_seq: u32 = 0;
    let mut last_can_report = Instant::now();

    let mut csv = a.csv.as_ref().map(|p| {
        let mut f = std::io::BufWriter::new(std::fs::File::create(p).expect("csv"));
        writeln!(f, "recv_ms,t_ms,id,unit,value").ok();
        f
    });
    let start = Instant::now();
    let mut latest: HashMap<String, (f64, u64)> = HashMap::new();
    let mut il = Interlock::new(IlConfig::default());
    let mut seq: u32 = 0;
    let mut last_box = Instant::now();
    let mut last_report = Instant::now();
    let mut count = 0u64;
    let mut switched = a.then_select.is_empty();
    let mut line = String::new();

    loop {
        if let Some(s) = a.seconds {
            if start.elapsed() >= Duration::from_secs(s) {
                break;
            }
        }
        if !switched && start.elapsed() >= Duration::from_secs(a.then_after) {
            switched = true;
            if let Some(s) = stream.as_mut() {
                send_select(s, &a.then_select, &a.always).ok();
            }
            eprintln!("{:8.3} s  selection {:?}", start.elapsed().as_secs_f64(), a.then_select);
        }

        line.clear();
        let Some(reader) = reader.as_mut() else {
            std::thread::sleep(Duration::from_millis(50));
            // no server: the mailbox below still gets the HMI's request and licence, and the bus's speed
            line.clear();
            if last_box.elapsed() >= Duration::from_millis(50) {
                last_box = Instant::now();
                let now = pf.now();
                let hmi = std::fs::read(HMI_TX_FILE).unwrap_or_default();
                let m = ToR5f {
                    ecu: None,
                    gps: None,
                    licensed: a.licensed || hmi.get(1) == Some(&b'1'),
                    request: hmi.first() == Some(&b'1'),
                    heartbeat: now,
                };
                seq = seq.wrapping_add(2);
                pf.write_mailbox(&mailbox::encode_to_r5f(&m, seq), seq.wrapping_sub(1), seq);
                if let Some(c) = &a.can {
                    let c = CanConfig { heartbeat: now, ..*c };
                    can_seq = can_seq.wrapping_add(2);
                    pf.write_block(can::CONFIG, &can::encode_config(&c, can_seq), can_seq.wrapping_sub(1), can_seq);
                }
            }
            if last_can_report.elapsed() >= Duration::from_secs(5) {
                last_can_report = Instant::now();
                if let Some(s) = pf.read_can() {
                    eprintln!("{:8.3} s  CAN {:?}: {} frames, speed {:?}", start.elapsed().as_secs_f64(), s.state, s.frames, s.speed);
                }
            }
            continue;
        };
        match reader.read_line(&mut line) {
            Ok(0) => {
                eprintln!("server closed the connection");
                break;
            }
            Ok(_) => {
                let now = pf.now();
                let recv_ms = start.elapsed().as_secs_f64() * 1e3;
                match telemetry::parse(&line) {
                    Some(Line::Sample(s)) => {
                        count += 1;
                        if let Some(v) = s.v {
                            latest.insert(s.id.to_string(), (v, now));
                        }
                        if let Some(f) = csv.as_mut() {
                            let v = s.v.map_or(String::new(), |v| v.to_string());
                            writeln!(f, "{recv_ms:.3},{},{},{},{v}", s.t, s.id, s.unit).ok();
                        }
                    }
                    Some(Line::State { running, rounds }) => {
                        eprintln!("{:8.3} s  state: running {running}, {rounds} round(s)", start.elapsed().as_secs_f64())
                    }
                    Some(Line::Ack { ok: false }) => eprintln!("refused: {}", line.trim()),
                    _ => {}
                }
            }
            Err(e) if matches!(e.kind(), std::io::ErrorKind::WouldBlock | std::io::ErrorKind::TimedOut) => {}
            Err(e) => {
                eprintln!("read: {e}");
                break;
            }
        }

        if last_box.elapsed() >= Duration::from_millis(50) {
            last_box = Instant::now();
            let now = pf.now();
            let ecu = latest.get(&a.speed_id).map(|&(v, stamp)| Speed {
                centi_kmh: (v.max(0.0) * 100.0).round() as u32,
                stamp,
            });
            // the HMI (kria-hmid) asks for transmit and sets the licence flag through a two-byte file, so this
            // daemon stays the mailbox's only writer: byte 0 '1' = request, byte 1 '1' = licensed
            let hmi = std::fs::read(HMI_TX_FILE).unwrap_or_default();
            let request = hmi.first() == Some(&b'1');
            let licensed = a.licensed || hmi.get(1) == Some(&b'1');
            let m = ToR5f { ecu, gps: None, licensed, request, heartbeat: now };
            seq = seq.wrapping_add(2);
            pf.write_mailbox(&mailbox::encode_to_r5f(&m, seq), seq.wrapping_sub(1), seq);
            if let Some(c) = &a.can {
                let c = CanConfig { heartbeat: now, ..*c };
                can_seq = can_seq.wrapping_add(2);
                pf.write_block(can::CONFIG, &can::encode_config(&c, can_seq), can_seq.wrapping_sub(1), can_seq);
            }
            if a.interlock {
                let d = il.step(Inputs { now, ecu, gps: None, licensed: a.licensed, request: true });
                if let Some(f) = csv.as_mut() {
                    writeln!(
                        f,
                        "{:.3},,interlock,{:?}/{:?},{}",
                        start.elapsed().as_secs_f64() * 1e3,
                        d.reason,
                        d.source,
                        d.transmit as u8
                    )
                    .ok();
                }
            }
        }

        if last_report.elapsed() >= Duration::from_secs(5) {
            let secs = last_report.elapsed().as_secs_f64();
            last_report = Instant::now();
            let speed = latest.get(&a.speed_id).map(|x| x.0);
            let r5f = pf.read_r5f();
            eprintln!(
                "{:8.3} s  {:.0} values/s, {} rows, speed {:?} km/h{}",
                start.elapsed().as_secs_f64(),
                count as f64 / secs,
                latest.len(),
                speed,
                r5f.map_or(String::new(), |r| format!(", R5F: PPS {:?}, transmit {:?}", r.pps, r.reason))
            );
            count = 0;
        }
    }
    if let Some(mut f) = csv {
        f.flush().ok();
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn can_speed_argument() {
        let s = parse_signal("0x0D0:16:16:intel:1/1").unwrap();
        assert_eq!((s.id, s.extended, s.start, s.len, s.motorola, s.num, s.den, s.offset), (0xD0, false, 16, 16, false, 1, 1, 0));
        let s = parse_signal("0x18FEF100x:8:16:intel:100/256:-50").unwrap();
        assert_eq!((s.id, s.extended, s.num, s.den, s.offset), (0x18FE_F100, true, 100, 256, -50));
        assert!(parse_signal("0x1A0:7:12:motorola:625/100").unwrap().motorola);
        assert!(parse_signal("0x1A0:7:12:sideways:1/1").is_none());
        assert!(parse_signal("0x1A0:7").is_none());
    }
}
