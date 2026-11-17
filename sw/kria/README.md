# Software for the K26's processors

Rust, with the logic in one crate that has no I/O, so that it runs on the A53s and on the R5F real-time cores alike and is tested on a PC. The design and the results are in [docs/INTEGRATIONS.md §6.1 and §7](../../docs/INTEGRATIONS.md); this file is how to build and run it.

| Crate | Target | What |
|---|---|---|
| `core` (`kria-core`) | any; `no_std`, no allocation, no `unsafe` | `pps` (GPS PPS discipline of `kria_pps`), `interlock` (transmit lock), `link` (IAS1 link watchdog), `radar` (the 10.5 GHz beam scan), `bev` (the PL grid's commands and coordinates), `ring` (Linux's grid commands for core 1), `telemetry` (`opendash-telemetry/1`), `mailbox` (the shared blocks) |
| `vehicled` (`kria-vehicled`) | A53, `aarch64-unknown-linux-gnu` | The ECU stream from opendash into the mailbox |
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

After `radar_grid`, `python sw/integrations/radar_grid_replay.py` writes the expected grid and the figure, and `fpga/sim/run.ps1 tb_kria_bev_axi -PlusArg BEV_DIR=../radar_grid` runs the commands through the RTL.

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
