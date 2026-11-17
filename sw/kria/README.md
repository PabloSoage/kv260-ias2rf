# Software for the K26's processors

Rust, with the logic in one crate that has no I/O, so that it runs on the A53s and on the R5F real-time cores alike and is tested on a PC. The design and the results are in [docs/INTEGRATIONS.md §7](../../docs/INTEGRATIONS.md); this file is how to build and run it.

| Crate | Target | What |
|---|---|---|
| `core` (`kria-core`) | any; `no_std`, no allocation, no `unsafe` | `pps` (GPS PPS discipline of `kria_pps`), `interlock` (transmit lock), `telemetry` (`opendash-telemetry/1`), `mailbox` (the Linux/R5F block) |
| `vehicled` (`kria-vehicled`) | A53, `aarch64-unknown-linux-gnu` | The ECU stream from opendash into the mailbox |
| `r5f` (`kria-r5f`) | R5F core 0, `armv7r-none-eabihf` | 1 kHz loop: PPS discipline, transmit interlock, status |

## Build and test

```
cd sw/kria
cargo test -p kria-core                       # 16 tests on the host
cargo run --release -p kria-core --example pps_sim > pps.csv
cargo build --release -p kria-vehicled        # for the PC
cargo build --release -p kria-vehicled --target aarch64-unknown-linux-gnu   # for the KV260 (needs an aarch64 linker)
cd r5f && cargo build --release               # R5F firmware ELF: r5f/target/armv7r-none-eabihf/release/kria-r5f
```

Targets: `rustup target add armv7r-none-eabihf aarch64-unknown-linux-gnu`.

`r5f` is a workspace of its own, so a plain `cargo test` in `sw/kria` stays a host build. Its linker script (`r5f/r5f.ld`) puts code in ATCM at 0 and data and stack in BTCM at `0x20000`, the core's local TCM addresses, as Linux remoteproc loads them.

## On the KV260

1. Bitstream from `fpga/kria/bd.tcl` (it includes `kria_pps` at `0x8002_0000`) and the overlay `sw/ias2rf_pl.dtsi`, which adds the PPS node and reserves the mailbox at `0x3EE0_0000`.
2. R5F core 0, through remoteproc:
   ```
   cp kria-r5f /lib/firmware/
   echo kria-r5f > /sys/class/remoteproc/remoteproc0/firmware
   echo start > /sys/class/remoteproc/remoteproc0/state
   ```
3. On Linux, with opendash's "Telemetry out" running on the phone:
   ```
   sudo kria-vehicled --server <phone>:35001 --licensed
   ```
   It writes the mailbox through `/dev/mem` and prints the R5F's PPS and interlock state every 5 s.

None of this has been run on a KV260 yet. The remoteproc steps are the standard Xilinx ones `[E]`; check the remoteproc index and that the kernel allows `/dev/mem` on the reserved region.
