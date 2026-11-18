//! HTTP for the browser build of the screens, WebSocket (`/ws`) for every client: snapshots out as JSON text
//! messages, commands in. One thread per client; the main loop broadcasts through channels.

use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::path::PathBuf;
use std::sync::mpsc::{channel, Receiver, Sender};
use std::sync::{Arc, Mutex};
use std::time::Duration;
use tungstenite::{accept, Message};

pub struct Server {
    clients: Arc<Mutex<Vec<Sender<Arc<String>>>>>,
    pub commands: Receiver<String>,
}

fn content_type(p: &str) -> &'static str {
    match p.rsplit('.').next() {
        Some("html") => "text/html; charset=utf-8",
        Some("js") => "text/javascript",
        Some("wasm") => "application/wasm",
        Some("css") => "text/css",
        Some("png") => "image/png",
        Some("json") => "application/json",
        _ => "application/octet-stream",
    }
}

fn serve_file(mut s: TcpStream, www: &PathBuf, req: &str) {
    let path = req.split_whitespace().nth(1).unwrap_or("/");
    let path = path.split('?').next().unwrap_or("/");
    let rel = if path == "/" { "index.html" } else { path.trim_start_matches('/') };
    let ok = !rel.contains("..");
    let body = if ok { std::fs::read(www.join(rel)).ok() } else { None };
    let _ = match body {
        Some(b) => {
            let h = format!("HTTP/1.1 200 OK\r\nContent-Type: {}\r\nContent-Length: {}\r\nConnection: close\r\n\r\n", content_type(rel), b.len());
            s.write_all(h.as_bytes()).and_then(|_| s.write_all(&b))
        }
        None => s.write_all(b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"),
    };
}

impl Server {
    pub fn start(addr: &str, www: Option<PathBuf>) -> std::io::Result<Self> {
        let l = TcpListener::bind(addr)?;
        let clients: Arc<Mutex<Vec<Sender<Arc<String>>>>> = Arc::default();
        let (cmd_tx, commands) = channel::<String>();
        let cl = clients.clone();
        std::thread::spawn(move || {
            for s in l.incoming().flatten() {
                let mut peek = [0u8; 2048];
                let n = s.peek(&mut peek).unwrap_or(0);
                let head = String::from_utf8_lossy(&peek[..n]).to_string();
                if head.to_ascii_lowercase().contains("upgrade: websocket") {
                    let (tx, rx) = channel::<Arc<String>>();
                    cl.lock().unwrap().push(tx);
                    let cmd_tx = cmd_tx.clone();
                    std::thread::spawn(move || client(s, rx, cmd_tx));
                } else if let Some(www) = www.clone() {
                    let mut s = s;
                    let mut buf = vec![0u8; n.max(1)];
                    let _ = s.read(&mut buf);
                    serve_file(s, &www, &head);
                }
            }
        });
        Ok(Self { clients, commands })
    }

    pub fn broadcast(&self, msg: String) {
        let m = Arc::new(msg);
        self.clients.lock().unwrap().retain(|c| c.send(m.clone()).is_ok());
    }

    pub fn clients(&self) -> usize {
        self.clients.lock().unwrap().len()
    }
}

fn client(s: TcpStream, rx: Receiver<Arc<String>>, cmd: Sender<String>) {
    let _ = s.set_nodelay(true);
    let Ok(mut ws) = accept(s) else { return };
    let _ = ws.get_ref().set_read_timeout(Some(Duration::from_millis(20)));
    loop {
        match ws.read() {
            Ok(Message::Text(t)) => {
                let _ = cmd.send(t.to_string());
            }
            Ok(Message::Close(_)) => return,
            Ok(_) => {}
            Err(tungstenite::Error::Io(e))
                if matches!(e.kind(), std::io::ErrorKind::WouldBlock | std::io::ErrorKind::TimedOut) => {}
            Err(_) => return,
        }
        let mut last = None;
        while let Ok(m) = rx.try_recv() {
            last = Some(m); // only the newest snapshot matters
        }
        if let Some(m) = last {
            if ws.send(Message::Text(m.as_str().into())).is_err() {
                return;
            }
        }
    }
}
