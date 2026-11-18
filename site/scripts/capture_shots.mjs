#!/usr/bin/env node
/**
 * Local static server + headless Chrome CDP verification, Rust vs Three.js hover benchmarks,
 * deep-link/CAN checks, intro sequence storyboard, and responsive screenshots in site/shots/.
 * Pure Node.js (zero Python, zero npm packages).
 */

import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SITE_DIR = path.dirname(HERE);
const SHOTS_DIR = path.join(SITE_DIR, "shots");

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "application/javascript; charset=utf-8",
  ".mjs": "application/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".wasm": "application/wasm",
  ".svg": "image/svg+xml",
  ".glb": "model/gltf-binary",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".md": "text/markdown; charset=utf-8",
};

function findChrome() {
  const candidates = [
    process.env.CHROME_PATH,
    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
  ].filter(Boolean);
  for (const p of candidates) {
    if (fs.existsSync(p)) return p;
  }
  throw new Error("Chrome / Chromium executable not found");
}

function startStaticServer() {
  return new Promise((resolve) => {
    const server = http.createServer((req, res) => {
      const urlPath = decodeURIComponent((req.url || "/").split("?")[0]);
      const rel = urlPath === "/" ? "index.html" : urlPath.replace(/^\/+/, "");
      const filePath = path.resolve(SITE_DIR, rel);
      if (!filePath.startsWith(path.resolve(SITE_DIR))) {
        res.writeHead(403);
        res.end("Forbidden");
        return;
      }
      if (!fs.existsSync(filePath) || fs.statSync(filePath).isDirectory()) {
        res.writeHead(404);
        res.end("Not Found: " + rel);
        return;
      }
      const ext = path.extname(filePath).toLowerCase();
      res.writeHead(200, { "Content-Type": MIME[ext] || "application/octet-stream" });
      fs.createReadStream(filePath).pipe(res);
    });
    server.listen(0, "127.0.0.1", () => {
      resolve({ server, port: server.address().port });
    });
  });
}

class CdpClient {
  constructor(wsUrl) {
    this.ws = new WebSocket(wsUrl);
    this.nextId = 1;
    this.pending = new Map();
    this.events = [];
  }

  async connect() {
    await new Promise((res, rej) => {
      this.ws.addEventListener("open", res, { once: true });
      this.ws.addEventListener("error", rej, { once: true });
    });
    this.ws.addEventListener("message", (ev) => {
      const msg = JSON.parse(String(ev.data));
      if (msg.id) {
        const p = this.pending.get(msg.id);
        if (p) {
          this.pending.delete(msg.id);
          if (msg.error) p.rej(new Error(JSON.stringify(msg.error)));
          else p.res(msg.result);
        }
      } else {
        this.events.push(msg);
      }
    });
  }

  send(method, params = {}) {
    const id = this.nextId++;
    return new Promise((res, rej) => {
      this.pending.set(id, { res, rej });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }

  async evalJs(expression) {
    const r = await this.send("Runtime.evaluate", {
      expression,
      awaitPromise: true,
      returnByValue: true,
    });
    if (r.exceptionDetails) {
      throw new Error("JS exception: " + JSON.stringify(r.exceptionDetails));
    }
    return r.result ? r.result.value : undefined;
  }

  close() {
    this.ws.close();
  }
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function waitFor(fn, timeoutMs = 45000, stepMs = 200) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeoutMs) {
    const val = await fn();
    if (val) return val;
    await sleep(stepMs);
  }
  throw new Error("Timed out after " + timeoutMs + " ms");
}

async function run() {
  fs.mkdirSync(SHOTS_DIR, { recursive: true });
  const { server, port } = await startStaticServer();
  const baseUrl = `http://127.0.0.1:${port}/?noIntro=1`;
  const cdpPort = 9222 + Math.floor(Math.random() * 400);
  const userDataDir = fs.mkdtempSync(path.join(os.tmpdir(), "ias2rf_chrome_"));
  const chromePath = findChrome();

  const chrome = spawn(
    chromePath,
    [
      "--headless=new",
      `--remote-debugging-port=${cdpPort}`,
      `--user-data-dir=${userDataDir}`,
      "--no-first-run",
      "--no-default-browser-check",
      "--enable-webgl",
      "--use-gl=angle",
      "--use-angle=swiftshader-webgl",
      "--enable-unsafe-swiftshader",
      "--ignore-gpu-blocklist",
      "--window-size=1440,900",
      baseUrl,
    ],
    { stdio: "ignore" }
  );

  let client;
  try {
    const target = await waitFor(async () => {
      try {
        const r = await fetch(`http://127.0.0.1:${cdpPort}/json/list`);
        if (!r.ok) return null;
        const list = await r.json();
        return list.find((x) => x.type === "page");
      } catch {
        return null;
      }
    }, 15000, 200);

    client = new CdpClient(target.webSocketDebuggerUrl);
    await client.connect();
    await client.send("Page.enable");
    await client.send("Runtime.enable");
    await client.send("Network.enable");
    await client.send("Log.enable");

    const setViewport = async (width, height, mobile = false) => {
      await client.send("Emulation.setDeviceMetricsOverride", {
        width,
        height,
        deviceScaleFactor: 1,
        mobile,
      });
      await sleep(350);
    };

    const snap = async (filename, waitMs = 450) => {
      await sleep(waitMs);
      const { data } = await client.send("Page.captureScreenshot", { format: "png" });
      fs.writeFileSync(path.join(SHOTS_DIR, filename), Buffer.from(data, "base64"));
      console.log("Captured", filename);
      return data;
    };

    await setViewport(1440, 900, false);

    await waitFor(async () => {
      return await client.evalJs("window.__SITE_API && window.__SITE_API.isReady()");
    }, 60000, 300);

    const stats = await client.evalJs("window.__SITE_API.getStats()");
    console.log("Site ready stats:", stats);

    // Check Rust WASM search & CAN part specs
    const canSearch = await client.evalJs(`JSON.stringify({
      u1506: window.__SITE_API.searchCore("U1506").slice(0, 3),
      j1503: window.__SITE_API.searchCore("J1503").slice(0, 3),
      tcan: window.__SITE_API.searchCore("TCAN330").slice(0, 3)
    })`);
    console.log("Rust Core CAN search:", canSearch);

    // Benchmark 60 Info-Mode hover frames on Desktop (1440x900)
    await client.evalJs(`
      window.__SITE_API.scrollToExplorer();
      window.__SITE_API.isolate("board");
      window.__SITE_API.setCameraPreset("iso");
    `);
    await sleep(300);
    const deskThree = await client.evalJs(`window.__SITE_API.benchmarkHover({ frames: 60, useWasm: false })`);
    const deskWasm = await client.evalJs(`window.__SITE_API.benchmarkHover({ frames: 60, useWasm: true })`);
    console.log("Benchmark Desktop (1440x900) Three.js mesh raycast:", deskThree);
    console.log("Benchmark Desktop (1440x900) Rust WASM spatial grid:", deskWasm);

    // 1. Landing Section Hero + 3-D Explorer Top Preview
    await client.evalJs(`
      window.__SITE_API.setTheme("dark");
      window.__SITE_API.selectTab("explorer");
      window.__SITE_API.isolate("all");
      window.__SITE_API.setExplode(0);
      window.__SITE_API.setEnclosure("closed");
      window.__SITE_API.setCameraPreset("iso");
      window.__SITE_API.scrollToTop();
    `);
    await snap("landing_hero.png");

    // 2. Capture 4 Intro Sequence frames & compose intro_seq.png 2x2 storyboard
    await client.evalJs(`window.__SITE_API.scrollToExplorer();`);
    const introFramesB64 = [];
    for (const [u, label] of [[0.0, "t=0.0s Fly-In (Closed)"], [0.35, "t=0.7s Lid Opening"], [0.70, "t=1.4s Explode + SOM Lift"], [1.0, "t=2.1s Settled Cutaway"]]) {
      await client.evalJs(`window.__SITE_API.setIntroFrame(${u});`);
      await sleep(350);
      const { data } = await client.send("Page.captureScreenshot", { format: "png" });
      introFramesB64.push({ label, data });
    }
    const seqPngB64 = await client.evalJs(`(async (frames) => {
      const cvs = document.createElement("canvas");
      cvs.width = 1440;
      cvs.height = 900;
      const ctx = cvs.getContext("2d");
      ctx.fillStyle = "#0b0d10";
      ctx.fillRect(0, 0, 1440, 900);
      for (let i = 0; i < 4; i++) {
        const img = new Image();
        img.src = "data:image/png;base64," + frames[i].data;
        await new Promise((r) => { img.onload = r; });
        const x = (i % 2) * 720, y = Math.floor(i / 2) * 450;
        ctx.drawImage(img, x, y, 720, 450);
        ctx.fillStyle = "rgba(11, 13, 16, 0.85)";
        ctx.fillRect(x + 12, y + 12, 230, 26);
        ctx.fillStyle = "#ffb020";
        ctx.font = "bold 14px monospace";
        ctx.fillText(frames[i].label, x + 20, y + 30);
      }
      return cvs.toDataURL("image/png").split(",")[1];
    })(${JSON.stringify(introFramesB64)})`);
    fs.writeFileSync(path.join(SHOTS_DIR, "intro_seq.png"), Buffer.from(seqPngB64, "base64"));
    console.log("Captured intro_seq.png");

    // 3. Desktop Dark (Closed Assembly Iso inside Explorer)
    await client.evalJs(`
      window.__SITE_API.setTheme("dark");
      window.__SITE_API.scrollToExplorer();
      window.__SITE_API.setExplode(0);
      window.__SITE_API.setEnclosure("closed");
      window.__SITE_API.isolate("all");
      window.__SITE_API.setCameraPreset("iso");
    `);
    await snap("desktop_dark.png");

    // 4. Desktop Light (Open Lid Cutaway)
    await client.evalJs(`
      window.__SITE_API.setTheme("light");
      window.__SITE_API.setEnclosure("open");
      window.__SITE_API.setExplode(15);
      window.__SITE_API.setCameraPreset("iso");
    `);
    await snap("desktop_light.png");

    // 5. Exploded View
    await client.evalJs(`
      window.__SITE_API.setTheme("dark");
      window.__SITE_API.setEnclosure("open");
      window.__SITE_API.setExplode(78);
      window.__SITE_API.setCameraPreset("iso");
    `);
    await snap("exploded_view.png");

    // 6. KV260 Teardown & Info Mode
    await client.evalJs(`
      window.__SITE_API.setExplode(0);
      window.__SITE_API.setTeardown({ fan: false, hs: false, somLiftMm: 22, isolate: "kv260", select: "KV260_J9_RPI" });
      window.__SITE_API.setCameraPreset("iso");
    `);
    await snap("kv260_teardown_info.png");

    // 7. Board Info Mode + Pulsing Copper Net Highlight
    await client.evalJs(`
      window.__SITE_API.isolate("board");
      window.__SITE_API.selectPart("U501", false);
      window.__SITE_API.selectNet("+1V8_ADCR_A");
      window.__SITE_API.setCameraPreset("iso");
    `);
    await snap("board_info_mode.png");

    // 8. Final Vehicle CAN Parts Deep-Link Info Mode (#part=U1506&view=board&explode=0&net=/STATUS/CAN_TXD&cam=bottom)
    await client.evalJs(`
      location.hash = "#part=U1506&view=board&explode=0&net=%2FSTATUS%2FCAN_TXD&cam=bottom";
      window.__SITE_API.applyHash();
      window.__SITE_API.scrollToExplorer();
    `);
    await snap("can_parts_info.png");

    // 8b. 3-D Simulations Mode (All 5 domains + Per-Component Cross-Reference)
    const simCheck = await client.evalJs(`JSON.stringify({
      u501_count: window.__SITE_API.getPartSims("U501").length,
      u1101_count: window.__SITE_API.getPartSims("U1101").length,
      j951_count: window.__SITE_API.getPartSims("J951").length
    })`);
    console.log("Sim component index check:", simCheck);

    await client.evalJs(`
      window.__SITE_API.setTheme("dark");
      window.__SITE_API.selectNet(null);
      window.__SITE_API.setSimMode(true, "rf", "ADCS_D0");
      window.__SITE_API.selectPart("U601", false);
      window.__SITE_API.setCameraPreset("top");
      window.__SITE_API.scrollToExplorer();
    `);
    await snap("sim_mode_rf.png", 550);

    await client.evalJs(`
      window.__SITE_API.setSimMode(true, "power", "+1V0");
      window.__SITE_API.selectPart("U1004", false);
      window.__SITE_API.setCameraPreset("top");
    `);
    await snap("sim_mode_power.png", 550);

    await client.evalJs(`
      window.__SITE_API.setTeardown({ fan: true, hs: true, somLiftMm: 0, isolate: "all" }, true);
      window.__SITE_API.setSimMode(true, "thermal", "rev08_clean_fine_70C");
      window.__SITE_API.selectPart("U501", false);
      window.__SITE_API.setCameraPreset("iso");
    `);
    await snap("sim_mode_thermal.png", 600);

    await client.evalJs(`
      window.__SITE_API.setSimMode(true, "mech", "Zm");
      window.__SITE_API.selectPart("U1101", false);
      window.__SITE_API.setCameraPreset("iso");
    `);
    await snap("sim_mode_mech.png", 600);

    await client.evalJs(`
      window.__SITE_API.setSimMode(true, "g8", "radar");
      window.__SITE_API.selectPart("U501", false);
      window.__SITE_API.setCameraPreset("top");
    `);
    await snap("sim_mode_g8.png", 600);

    await client.evalJs(`window.__SITE_API.setSimMode(false);`);

    // 9. Layer Stack-up Mode (with peeled SVGs)
    await client.evalJs(`
      window.__SITE_API.selectTab("layers");
      window.__SITE_API.select2dLayer("F.Cu");
    `);
    await snap("layer_mode.png", 1000);

    // 10. Live Slint WASM HMI Mode
    await client.evalJs(`window.__SITE_API.selectTab("hmi");`);
    await waitFor(async () => {
      return await client.evalJs(`(() => {
        const ifr = document.getElementById("hmi-iframe");
        if (!ifr || !ifr.contentDocument) return false;
        const w = ifr.contentDocument.getElementById("wait");
        const c = ifr.contentDocument.getElementById("canvas");
        return !w && c && c.width > 100 && c.height > 100;
      })()`);
    }, 30000, 300);
    await snap("hmi_wasm.png", 900);

    // 11. Animated Rust Mock-ups & Final Sim Gallery
    await client.evalJs(`window.__SITE_API.selectTab("mockups");`);
    await snap("mockups_gallery.png", 700);

    await client.evalJs(`window.__SITE_API.selectTab("gallery");`);
    await snap("sim_gallery.png", 600);

    // 12. Phone Profile (390x844) + Hover Benchmark
    await setViewport(390, 844, true);
    await client.evalJs(`
      window.__SITE_API.setTheme("dark");
      window.__SITE_API.selectTab("explorer");
      window.__SITE_API.isolate("board");
      window.__SITE_API.selectNet(null);
      window.__SITE_API.selectPart("J1503", false);
      window.__SITE_API.setCameraPreset("iso");
      window.__SITE_API.scrollToExplorer();
    `);
    await sleep(300);
    const mobThree = await client.evalJs(`window.__SITE_API.benchmarkHover({ frames: 60, useWasm: false })`);
    const mobWasm = await client.evalJs(`window.__SITE_API.benchmarkHover({ frames: 60, useWasm: true })`);
    console.log("Benchmark Phone (390x844) Three.js mesh raycast:", mobThree);
    console.log("Benchmark Phone (390x844) Rust WASM spatial grid:", mobWasm);
    await snap("phone_dark.png");

    await client.evalJs(`
      window.__SITE_API.setTheme("light");
      window.__SITE_API.isolate("all");
      window.__SITE_API.setEnclosure("open");
      window.__SITE_API.setExplode(50);
      window.__SITE_API.setCameraPreset("iso");
      window.__SITE_API.scrollToExplorer();
    `);
    await snap("phone_light.png");

    // Check errors across Runtime, Console, Log, and local Network
    const errors = [];
    for (const ev of client.events) {
      if (ev.method === "Runtime.exceptionThrown") {
        errors.push(`Runtime.exception: ${JSON.stringify(ev.params.exceptionDetails)}`);
      } else if (ev.method === "Runtime.consoleAPICalled" && ev.params.type === "error") {
        errors.push(`Console.error: ${JSON.stringify(ev.params.args)}`);
      } else if (ev.method === "Log.entryAdded" && ev.params.entry.level === "error") {
        errors.push(`Log.error: ${ev.params.entry.text} (${ev.params.entry.url})`);
      } else if (ev.method === "Network.responseReceived" && ev.params.response.status >= 400) {
        errors.push(`HTTP ${ev.params.response.status}: ${ev.params.response.url}`);
      } else if (ev.method === "Network.loadingFailed") {
        errors.push(`Network.loadingFailed: ${ev.params.errorText}`);
      }
    }

    if (errors.length) {
      console.error("Browser verification detected errors:\n" + errors.join("\n"));
      process.exitCode = 1;
    } else {
      console.log("VERIFICATION PASSED: 0 console errors, 0 page exceptions, 0 failed HTTP requests.");
    }
  } finally {
    if (client) client.close();
    chrome.kill("SIGKILL");
    server.close();
    await sleep(300);
    try { fs.rmSync(userDataDir, { recursive: true, force: true }); } catch {}
  }
}

run().catch((err) => {
  console.error(err);
  process.exit(1);
});
