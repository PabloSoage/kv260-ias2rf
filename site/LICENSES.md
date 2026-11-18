# Third-Party Licences and Asset Attribution (`site/`)

No proprietary CAD files, no EasyEDA models and no GPL binaries are redistributed on this site. Every 3-D asset, script, software package and library bundled in `site/` is listed below with its licence and provenance.

## 1. 3-D Assets (`site/assets/`)

| Asset | Contents | Source & Licence |
|---|---|---|
| `board.glb` | Rev08 adapter PCB, copper tracks, pads, zones, soldermask, silkscreen, and 3-D component packages | PCB layout, copper/mask/silk geometry, and `mech/models3d/USB_C_HRO_TYPE-C-31-E-17.wrl`: project hardware (Apache-2.0, see the repository LICENSE). Standard STEP component bodies exported by `kicad-cli` from KiCad 10 official 3-D library and `mech/models3d/*.step`: **CC-BY-SA 4.0 with the KiCad Libraries Exception** (attribution: KiCad Library Team). All EasyEDA / LCSC cached models (`_work/mech/cache/models3d/`) are stripped before export and replaced with our own simplified procedural geometry (Apache-2.0 / MIT). |
| `kv260.glb` | AMD Kria KV260 carrier card, K26 SOM, SOM240 connectors, XCK26, DDR4, eMMC, heatsink, 4010 fan, and carrier connectors (`J8`, `J7`, `J9`, `J2`, `J10`, `U44`, `U46`, `J5`, `J6`, `J12`, `J4`, `J11`) | **Simplified model written from scratch** (`site/scripts/build_assets.mjs`, Apache-2.0 / MIT). AMD's proprietary `XTP679` STEP/STL is **not** converted or redistributed. Dimensions and pinout notes come from public AMD documentation (`UG1089`, `DS987`, `XTP682`) and our measured mechanical coordinates (`docs/INTERFACE_SPEC.md`, `_work/mech/build_mount.py`). |
| `enclosure.glb` | Closed v2 enclosure (`case_v2_bottom.stl`, `case_v2_lid.stl`, `case_v2_filter_frame.stl`, corner bumpers, snap pins), adapter heatsinks `HS1..HS4`, and `OD5015` 50 mm lid fan | Generated from the repository's own STL files in `mech/` and procedural thermal geometry in `site/scripts/build_assets.mjs`: **Apache-2.0** (project authors). |
| `layers/*.svg` | Per-layer vector plots (`F.Cu`, `In1.Cu..In6.Cu`, `B.Cu`, `F.SilkS`, `B.SilkS`, `F.Mask`, `B.Mask`, `Edge.Cuts`) | Exported directly from `CSI2-KRIA-KV260_Rev01.kicad_pcb` via `kicad-cli`: **Apache-2.0** (project hardware). |
| `img/*` | Board renders (`docs/img/`), G-8 RF/radar figures (`docs/img/sim/`), integration figures (`docs/img/integrations/`) | Generated from repository scripts and simulations: **Apache-2.0** (project authors). |

## 2. Vendored JavaScript Libraries (`site/vendor/`)

Zero CDN requests are made at run time. All client dependencies are pinned and vendored under `site/vendor/three-0.170.0/`:

| File | Upstream Package & Version | Licence |
|---|---|---|
| `three.module.min.js` | `three` v0.170.0 | MIT License (`Copyright (c) 2010-2024 three.js authors`, copy in `site/vendor/three-0.170.0/LICENSE`) |
| `OrbitControls.js` | `three` v0.170.0 (`examples/jsm/controls/`) | MIT License |
| `GLTFLoader.js` | `three` v0.170.0 (`examples/jsm/loaders/`) | MIT License |
| `RoomEnvironment.js` | `three` v0.170.0 (`examples/jsm/environments/`) | MIT License |
| `BufferGeometryUtils.js` | `three` v0.170.0 (`examples/jsm/utils/`) | MIT License |
| `meshopt_decoder.module.js` | `meshoptimizer` v0.18 (bundled inside `three` v0.170.0 `examples/jsm/libs/`) | MIT License (`Copyright (C) 2016-2022 Arseny Kapoulkine`) |

## 3. Rust/WASM Site Core (`site/core/`)

- **`site/core/` source & compiled bundle (`site/core/pkg/ias2rf_site_core.js`, `site/core/pkg/ias2rf_site_core_bg.wasm`):** Written from scratch for spatial ray-AABB grid picking, search/net graph lookup and live hardware simulations under the **MIT License** (project authors). Uses pinned `wasm-bindgen = 0.2.130` (MIT / Apache-2.0).

## 4. Browser HMI (`site/hmi/`)

- **`sw/hmi/app/` source code:** MIT License (project authors).
- **Compiled WebAssembly bundle (`site/hmi/pkg/kria_hmi.js`, `site/hmi/pkg/kria_hmi_bg.wasm`):** Built from `sw/hmi/app` with `slint` v1.19.0 and distributed strictly as a browser **Web Application** under the **Slint Royalty-free Desktop, Mobile, and Web Applications License v2.0** (`LicenseRef-Slint-Royalty-free-2.0`). Per Section 2(b) of that licence, visible Slint attribution (`Built with Slint`) is displayed directly on the public HMI page (`site/hmi.html` and the Live HMI tab of `site/index.html`) alongside `site/LICENSES.md`. Notice that embedded Linux/KMS binaries on the KV260 hardware remain under GPL-3.0 and are **not** distributed in `site/`.

## 5. Fonts and Styling

`site/index.html`, `site/hmi.html` and `site/styles.css` use only the operating system's built-in sans-serif and monospace UI font stacks (`system-ui`, `-apple-system`, `Segoe UI`, `Roboto`, `ui-monospace`, `Consolas`). No external web fonts are loaded or redistributed.

## 6. GitHub Actions Workflow (`.github/workflows/pages.yml`)

Uses official GitHub Pages actions pinned to major release tags (`actions/checkout@v4`, `actions/configure-pages@v5`, `actions/upload-pages-artifact@v3`, `actions/deploy-pages@v4`), MIT License (GitHub).
