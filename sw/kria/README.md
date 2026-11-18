# Software for the K26's processors

Rust, with the logic in one crate that has no I/O, so that it runs on the A53s and on the R5F real-time cores alike and is tested on a PC. The design and the results are in [docs/INTEGRATIONS.md §6.1 and §7](../../docs/INTEGRATIONS.md); this file is how to build and run it.

| Crate | Target | What |
|---|---|---|
| `core` (`kria-core`) | any; `no_std`, no allocation, no `unsafe` | `pps` (GPS PPS discipline of `kria_pps`), `interlock` (transmit lock), `link` (IAS1 link watchdog), `radar` (the 10.5 GHz beam scan), `bev` (the PL grid's commands and coordinates), `ring` (Linux's grid commands for core 1), `telemetry` (`opendash-telemetry/1`), `mailbox` (the shared blocks) |
| `vehicled` (`kria-vehicled`) | A53, `aarch64-unknown-linux-gnu` | The ECU stream from opendash into the mailbox, and the HMI's transmit request (`/run/kria-hmi/tx`) |
| `hmi-core` (`kria-hmi-core`) | any (host-tested) | The screens' data plane, no I/O: `frame` (the `kria_ps_framer` blocks), `audio` (stream 0x20, RDS decoder), `adsb` (CRC-24, CPR, the aircraft table), `radar` (streams 0x22, 0x23), `spectrum` (FFT, waterfall), `modes` (a frequency and mode to register writes), `state` (the snapshot and the screens' commands) |
| `hmid` (`kria-hmid`) | A53 (`--features hw`), or a PC with the simulated board | The HMI's data service: DMA blocks in, audio out (ALSA), register writes, I/Q recording, the snapshot over WebSocket, the browser build over HTTP |
| `sdr` (`kria-sdr`, `kria-sdrd`) | A53, `aarch64-unknown-linux-gnu` | The KrakenSDR (alignment, calibration, `kria_doa`, MUSIC) and the HackRF Pro (`kria_sweep`, panorama, transmit gate); the USB libraries and `/dev/mem` behind feature `hw` |
| `r5f`: `kria-r5f0` | R5F core 0, `armv7r-none-eabihf` | 1 kHz loop: PPS discipline, IAS1 link watchdog, transmit interlock, status |
| `r5f`: `kria-r5f1` | R5F core 1, `armv7r-none-eabihf` | 10 kHz loop: radar beam scan, the fusion grid's command port and frames, status |

## Build and test

```
cd sw/kria
cargo test -p kria-core                       # 29 tests on the host
cargo run --release -p kria-core --example pps_sim > pps.csv
cargo run --release -p kria-core --example radar_grid   # core 1 end to end: fpga/sim/out/radar_grid
cargo build --release -p kria-vehicled        # for the PC
cargo build --release -p kria-vehicled --target aarch64-unknown-linux-gnu   # for the KV260 (needs an aarch64 linker)
cd r5f && cargo build --release               # r5f/target/armv7r-none-eabihf/release/kria-r5f0 and kria-r5f1
```

## The HMI (docs/HMI.md)

```
cd sw/kria
cargo test -p kria-hmi-core                   # 17 tests: RDS, ADS-B vectors, CPR, radar words, framer blocks
cargo run --release -p kria-hmid -- --sim --listen 0.0.0.0:8080 --www ../hmi/app/www --sdr-out ../hmi/sdr
cargo build --release -p kria-hmid --features hw --target aarch64-unknown-linux-gnu   # on the KV260, as root
cd ../hmi/app && cargo run --release -- --connect 127.0.0.1:8080   # the screens, native (Linux KMS on the KV260)
sh build_web.sh                               # the browser build into www/pkg; then open http://<host>:8080/
sw/hmi/make_images.sh                         # from the root: the images in docs/img/hmi
```

The screens (`sw/hmi/app`, crate `kria-hmi`) are a separate workspace so that only they depend on Slint. Their source is MIT like these crates; a built `kria-hmi` binary links Slint and is therefore distributed under Slint's terms, GPL-3.0 on the KV260 (HMI.md §5). `kria-hmi-core` and `kria-hmid` do not link Slint.

After `radar_grid`, `python sw/integrations/radar_grid_replay.py` writes the expected grid and the figure, and `fpga/sim/run.ps1 tb_kria_bev_axi -PlusArg BEV_DIR=../radar_grid` runs the commands through the RTL.

The KrakenSDR and HackRF Pro chains (docs/INTEGRATIONS.md §9 and §10), from the repository root:

```
python sw/integrations/kraken_sim.py                       # five RTL streams into fpga/sim/out/kraken
cargo run --release -p kria-sdr --bin kria-sdrd -- kraken-pre fpga/sim/out/kraken   # from sw/kria, path ../../...
fpga/sim/run.ps1 tb_kria_doa                               # kria_doa against the A53's model
cargo run --release -p kria-sdr --bin kria-sdrd -- kraken-post fpga/sim/out/kraken  # MUSIC, kraken_doa.json
python sw/integrations/hackrf_sim.py                       # one sweep, 0 to 7.2 GHz, into fpga/sim/out/hackrf
cargo run --release -p kria-sdr --bin kria-sdrd -- hackrf-pre fpga/sim/out/hackrf
fpga/sim/run.ps1 tb_kria_sweep
cargo run --release -p kria-sdr --bin kria-sdrd -- hackrf-post fpga/sim/out/hackrf  # panorama, hackrf_sweep.json
cp fpga/sim/out/kraken/kraken_doa.json fpga/sim/out/hackrf/hackrf_sweep.json sw/hmi/sdr/
sw/hmi/make_images.sh; python sw/integrations/usb_sdr_figures.py
```

`cargo test -p kria-sdr` runs its 6 host tests. On the KV260, `cargo build --release -p kria-sdr --features hw --target aarch64-unknown-linux-gnu` needs KrakenRF's librtlsdr and libhackrf in the sysroot; that build and the `hw` paths have not been run.

Targets: `rustup target add armv7r-none-eabihf aarch64-unknown-linux-gnu`.

`r5f` is a workspace of its own, so a plain `cargo test` in `sw/kria` stays a host build. Both images use one linker script (`r5f/r5f.ld`): code in ATCM at 0, data and stacks in BTCM at `0x20000`, the local TCM addresses each core sees, as Linux remoteproc loads them. They share the start-up (`src/rt.rs`: vectors, a data-abort handler that counts and resumes, the resource table) and the register access (`src/hw.rs`).

## On the KV260

1. Bitstream from `fpga/kria/bd.tcl` (`kria_pps` at `0x8002_0000`, the grid at `0x8003_0000`, its DMA at `0x8004_0000`) and the overlay `sw/ias2rf_pl.dtsi`, which adds those nodes and reserves the mailbox region at `0x3EE0_0000` (64 KiB) and the grid's two frames after it.
2. The two R5F cores, through remoteproc (split mode):
   ```
   cp kria-r5f0 kria-r5f1 /lib/firmware/
   echo kria-r5f0 > /sys/class/remoteproc/remoteproc0/firmware
   echo kria-r5f1 > /sys/class/remoteproc/remoteproc1/firmware
   echo start > /sys/class/remoteproc/remoteproc0/state
   echo start > /sys/class/remoteproc/remoteproc1/state
   ```
3. On Linux, with opendash's "Telemetry out" running on the phone:
   ```
   sudo kria-vehicled --server <phone>:35001 --licensed
   ```
   It writes the mailbox through `/dev/mem` and prints the R5F's PPS and interlock state every 5 s.
4. For core 1's scan: load the Artix's beam table in scan order, set `ADAR_CTRL[13]` and `scan_last`, write the grid's weights and origins, then `Core1Config` in the mailbox with `scan` and `grid` set and a heartbeat at least once a second. Linux must leave EMIO GPIO 1 (`BEAM_STROBE`) to core 1.

None of this has been run on a KV260 yet. The remoteproc steps are the standard Xilinx ones `[E]`; check the remoteproc indices and that the kernel allows `/dev/mem` on the reserved regions.
