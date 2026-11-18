//! The native screens: `kria-hmi [--connect HOST:PORT]` opens the window (on the KV260 straight on DRM/KMS) and
//! follows kria-hmid over WebSocket. `kria-hmi --screenshots OUT --snapshots DIR [--scale 1.5]` renders every
//! screen from dumped snapshots with Slint's software renderer, headless, into PNGs (the images in HMI.md).

use kria_hmi::{apply, AppWindow, Hmi, Model};
use serde_json::Value;
use slint::ComponentHandle;
use std::cell::RefCell;
use std::sync::mpsc::channel;
use std::time::Duration;

thread_local! {
    static MODEL: RefCell<Model> = RefCell::new(Model::default());
}

fn arg(name: &str) -> Option<String> {
    let v: Vec<String> = std::env::args().collect();
    v.iter().position(|a| a == name).and_then(|i| v.get(i + 1).cloned())
}

fn main() {
    if let Some(out) = arg("--screenshots") {
        let dir = arg("--snapshots").expect("--snapshots DIR");
        let scale: f32 = arg("--scale").and_then(|s| s.parse().ok()).unwrap_or(1.5);
        screenshots(&out, &dir, scale);
        return;
    }
    let addr = arg("--connect").unwrap_or_else(|| "127.0.0.1:8080".into());
    let ui = AppWindow::new().expect("window");
    let (cmd_tx, cmd_rx) = channel::<String>();
    ui.global::<Hmi>().on_send(move |c| {
        let _ = cmd_tx.send(c.to_string());
    });
    let weak = ui.as_weak();
    std::thread::spawn(move || loop {
        match tungstenite::connect(format!("ws://{addr}/ws")) {
            Ok((mut ws, _)) => {
                if let tungstenite::stream::MaybeTlsStream::Plain(s) = ws.get_ref() {
                    let _ = s.set_read_timeout(Some(Duration::from_millis(30)));
                }
                loop {
                    while let Ok(c) = cmd_rx.try_recv() {
                        let _ = ws.send(tungstenite::Message::Text(c.into()));
                    }
                    match ws.read() {
                        Ok(tungstenite::Message::Text(t)) => {
                            let t = t.to_string();
                            let w = weak.clone();
                            let _ = slint::invoke_from_event_loop(move || {
                                if let (Some(ui), Ok(v)) = (w.upgrade(), serde_json::from_str::<Value>(&t)) {
                                    MODEL.with(|m| apply(&ui, &mut m.borrow_mut(), &v));
                                }
                            });
                        }
                        Ok(_) => {}
                        Err(tungstenite::Error::Io(e))
                            if matches!(e.kind(), std::io::ErrorKind::WouldBlock | std::io::ErrorKind::TimedOut) => {}
                        Err(_) => break,
                    }
                }
            }
            Err(_) => std::thread::sleep(Duration::from_secs(1)),
        }
        let w = weak.clone();
        let _ = slint::invoke_from_event_loop(move || {
            if let Some(ui) = w.upgrade() {
                ui.global::<Hmi>().set_connected(false);
            }
        });
    });
    ui.run().expect("run");
}

mod headless {
    use slint::platform::software_renderer::{MinimalSoftwareWindow, RepaintBufferType};
    use slint::platform::{Platform, WindowAdapter};
    use std::rc::Rc;

    pub struct Headless(pub Rc<MinimalSoftwareWindow>);
    impl Platform for Headless {
        fn create_window_adapter(&self) -> Result<Rc<dyn WindowAdapter>, slint::PlatformError> {
            Ok(self.0.clone())
        }
    }
    pub fn window() -> Rc<MinimalSoftwareWindow> {
        MinimalSoftwareWindow::new(RepaintBufferType::NewBuffer)
    }
}

/// Screen index, snapshot it is drawn from, image name.
const SHOTS: [(i32, &str, &str); 10] = [
    (0, "system", "hmi_home"),
    (1, "tx_moving", "hmi_vehicle"),
    (2, "radio_fm", "hmi_radio"),
    (3, "radio_fm", "hmi_spectrum"),
    (4, "system", "hmi_wideband"),
    (5, "system", "hmi_bearing"),
    (6, "adsb", "hmi_adsb"),
    (7, "radar", "hmi_radar"),
    (8, "tx_parked", "hmi_transmit"),
    (9, "system", "hmi_system"),
];

fn screenshots(out: &str, dir: &str, scale: f32) {
    use slint::platform::software_renderer::PremultipliedRgbaColor;
    use slint::platform::WindowEvent;
    let win = headless::window();
    slint::platform::set_platform(Box::new(headless::Headless(win.clone()))).expect("platform");
    let ui = AppWindow::new().expect("window");
    let (w, h) = ((1280.0 * scale) as u32, (720.0 * scale) as u32);
    win.dispatch_event(WindowEvent::ScaleFactorChanged { scale_factor: scale });
    win.set_size(slint::PhysicalSize::new(w, h));
    ui.show().expect("show");
    std::fs::create_dir_all(out).expect("out dir");
    for (screen, snap, name) in SHOTS {
        let text = std::fs::read_to_string(format!("{dir}/{snap}.json")).unwrap_or_else(|_| panic!("{dir}/{snap}.json"));
        let v: Value = serde_json::from_str(&text).expect("snapshot");
        let mut m = Model::default();
        apply(&ui, &mut m, &v);
        ui.global::<Hmi>().set_screen(screen);
        slint::platform::update_timers_and_animations();
        let mut buf = vec![PremultipliedRgbaColor::default(); (w * h) as usize];
        win.request_redraw();
        win.draw_if_needed(|r| {
            r.render(&mut buf, w as usize);
        });
        let path = format!("{out}/{name}.png");
        let f = std::fs::File::create(&path).expect("png");
        let mut enc = png::Encoder::new(std::io::BufWriter::new(f), w, h);
        enc.set_color(png::ColorType::Rgba);
        enc.set_depth(png::BitDepth::Eight);
        let mut wr = enc.write_header().expect("png header");
        let bytes: Vec<u8> = buf.iter().flat_map(|p| [p.red, p.green, p.blue, 255]).collect();
        wr.write_image_data(&bytes).expect("png data");
        eprintln!("wrote {path}");
    }
}
