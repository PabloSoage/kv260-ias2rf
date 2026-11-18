# Third-Party Licences and Asset Attribution (`site/`)

No proprietary CAD files, no EasyEDA models and no GPL binaries are redistributed on this site. Every 3-D asset, script, software package and library bundled in `site/` is listed below with its licence and provenance.

## 1. 3-D Assets (`site/assets/`)

| Asset | Contents | Source & Licence |
|---|---|---|
| `board.glb` | Rev08 adapter FR4 substrate, 3-D ENIG pads/vias, and 3-D component packages | PCB layout, 2048x2048 top/bottom surface textures baked from vector SVGs, and `mech/models3d/USB_C_HRO_TYPE-C-31-E-17.wrl` (`J1501`): project hardware (**Apache-2.0**, see the repository `LICENSE`). Standard STEP component bodies exported by `kicad-cli` from KiCad 10 official 3-D library and `mech/models3d/*.step` (including substituted footprints `U1301..U1314`, `U1501..U1502`, `L1001..L1030`, `F1001`, `Y401`, `Y1301`, `FL1302..FL1303`, `J1001`, `J1201`, `J1502`): **CC-BY-SA 4.0 with the KiCad Libraries Exception** (attribution: KiCad Library Team). All EasyEDA / LCSC cached models (`_work/mech/cache/models3d/`) are stripped before export, and the 9 unmapped EasyEDA footprints (`T701`, `T801`, `T802`, `T1301`, `T1302`, `FL1301`, `J101..J103`) use centered project-authored procedural geometry (**Apache-2.0 / MIT**). |
| `kv260.glb` | Simplified Kria KV260 carrier card, K26 SOM, SOM240 connectors, XCK26, DDR4, eMMC, 18-fin heatsink, 4010 fan, and carrier ports (`J8`, `J7`, `J9`, `J2`, `J10`, `U44`, `U46`, `J5`, `J6`, `J12`, `J4`, `J11`, Fan) | KV260 and K26 are AMD products. This is a simplified model drawn for this project from AMD's public documentation, for illustration only; it is not AMD's CAD model. Carrier geometry written from scratch in `site/scripts/build_assets.mjs` (**Apache-2.0 / MIT**), using KiCad 10 official connector `.step` models (**CC-BY-SA 4.0 with the KiCad Libraries Exception**) for the port bodies. AMD proprietary `XTP679` STEP/STL is **not** converted or redistributed. Dimensions and pinout notes come from public AMD documentation (`UG1089`, `DS987`, `XTP682`) and measured mechanical coordinates (`docs/INTERFACE_SPEC.md`, `_work/mech/build_mount.py`). |
| `enclosure.glb` | High-resolution closed v2 enclosure STLs (`mech/case_v2_*.stl`, `case_bumper_*.stl` with 30 deg crease-angle smooth normals), adapter heatsinks `HS1..HS4`, and `OD5015` 50 mm lid fan | Generated from the repository's own STL files in `mech/` and procedural thermal geometry in `site/scripts/build_assets.mjs`: **Apache-2.0** (project authors). |
| `layers/*.svg` | Per-layer vector plots (`F.Cu`, `In1.Cu..In6.Cu`, `B.Cu`, `F.SilkS`, `B.SilkS`, `F.Mask`, `B.Mask`, `Edge.Cuts`) | Exported directly from `CSI2-KRIA-KV260_Rev01.kicad_pcb` via `kicad-cli`: **Apache-2.0** (project hardware). |
| `img/*` | Board renders (`docs/img/`), G-8 RF/radar figures (`docs/img/sim/`), integration figures (`docs/img/integrations/`) | Generated from repository scripts and simulations: **Apache-2.0** (project authors). |

## 2. Vendored JavaScript Libraries (`site/vendor/`)

Zero CDN requests are made at run time. All client dependencies are pinned and vendored under `site/vendor/`:

| File | Upstream Package & Version | Licence |
|---|---|---|
| `three-0.170.0/three.module.min.js` | `three` v0.170.0 | MIT License (`Copyright (c) 2010-2024 three.js authors`, copy in `site/vendor/three-0.170.0/LICENSE`) |
| `three-0.170.0/OrbitControls.js` | `three` v0.170.0 (`examples/jsm/controls/`) | MIT License |
| `three-0.170.0/GLTFLoader.js` | `three` v0.170.0 (`examples/jsm/loaders/`) | MIT License |
| `three-0.170.0/RoomEnvironment.js` | `three` v0.170.0 (`examples/jsm/environments/`) | MIT License |
| `three-0.170.0/BufferGeometryUtils.js` | `three` v0.170.0 (`examples/jsm/utils/`) | MIT License |
| `three-0.170.0/meshopt_decoder.module.js` | `meshoptimizer` v0.18 (bundled inside `three` v0.170.0 `examples/jsm/libs/`) | MIT License (`Copyright (C) 2016-2022 Arseny Kapoulkine`) |
| `pdfjs-4.10.38/pdf.min.mjs`, `pdf.worker.min.mjs` | `pdfjs-dist` v4.10.38 (Mozilla PDF.js) | Apache-2.0 License (full copy in `site/vendor/pdfjs-4.10.38/LICENSE`) |

## 3. Deployed PDFs in GitHub Pages Artifact

`docs/KV260-IAS2RF_Documentation.pdf`, `docs/KV260-IAS2RF_schematic.pdf`, and `docs/KV260-IAS2RF_layout.pdf` remain outside `site/` in git and are copied into `site/docs/` only inside `.github/workflows/pages.yml` when building the GitHub Pages artifact. `site/pdf.html` streams them on demand via HTTP `Range` requests (`rangeChunkSize: 65536`, `disableAutoFetch: true`).

## 4. Rust/WASM Site Core (`site/core/`)

- **`site/core/` source & compiled bundle (`site/core/pkg/ias2rf_site_core.js`, `site/core/pkg/ias2rf_site_core_bg.wasm`):** Written from scratch for spatial ray-AABB grid picking, search/net graph lookup and live hardware simulations under the **MIT License** (project authors). Uses pinned `wasm-bindgen = 0.2.130` (MIT / Apache-2.0).

## 5. Browser HMI (`site/hmi/`)

- **`sw/hmi/app/` source code:** MIT License (project authors).
- **Compiled WebAssembly bundle (`site/hmi/pkg/kria_hmi.js`, `site/hmi/pkg/kria_hmi_bg.wasm`):** Built from `sw/hmi/app` with `slint` v1.19.0 and distributed strictly as a browser **Web Application** under the **Slint Royalty-free Desktop, Mobile, and Web Applications License v2.0** (`LicenseRef-Slint-Royalty-free-2.0`). Per Section 2(b) of that licence, visible Slint attribution (`Built with Slint`) is displayed directly on the public HMI page (`site/hmi.html` and the Live HMI tab of `site/index.html`) alongside `site/LICENSES.md`. Notice that embedded Linux/KMS binaries on the KV260 hardware remain under GPL-3.0 and are **not** distributed in `site/`.

## 6. Fonts and Styling

`site/index.html`, `site/hmi.html`, `site/pdf.html`, and `site/styles.css` use only the operating system's built-in sans-serif and monospace UI font stacks (`system-ui`, `-apple-system`, `Segoe UI`, `Roboto`, `ui-monospace`, `Consolas`). No external web fonts are loaded or redistributed.

## 7. GitHub Actions Workflow (`.github/workflows/pages.yml`)

Uses official GitHub Pages actions pinned to major release tags (`actions/checkout@v4`, `actions/configure-pages@v5`, `actions/upload-pages-artifact@v3`, `actions/deploy-pages@v4`), MIT License (GitHub).
