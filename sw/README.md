# KV260 PS Software Bring-Up (`sw/`)

Host/target userspace test utilities and Linux devicetree overlay for the KV260
Zynq UltraScale+ PL bitstream (`fpga/kria/bd.tcl` + `fpga/kria/kria_pl_link.v`).

## Files

- `ias2rf_pl.dtsi` — Device Tree overlay fragment for Ubuntu/PetaLinux (`xmutil`
  or `configfs` DT overlay), exposing:
  - `ias2rf_link@80000000` (`kria_pl_link` AXI4-Lite CSRs `0x00..0x34`, interrupts `irq_fpga` / `irq_link_up`)
  - `axi_dma_0@80010000` (Direct-register 64-bit AXI DMA S2MM uplink + MM2S downlink)
  - `i2c0` (EMIO I2C to Artix/board `HK_SCL`/`HK_SDA`)
  - `spi0` (EMIO SPI over KV260 Pmod J2)
- `ias2rf_dma_test.c` — Standalone C smoke test (`mmap` `/dev/mem` + optional `u-dma-buf` `/dev/udmabuf0`):
  - Prints all IAS1 link CSRs (`0x00..0x34`) and flags `0xDEAD_C10C` if the Artix `LINK_RX_CLK` is not yet running.
  - Supports `--retrain` (pulses `LINK_CTRL[2]`) and `--rd-adcs` (sends a Stream `0x10` register-read request for Artix `0x0038 ADCS_STATUS` via `MM2S`, then captures 4 KB of uplink frames via `S2MM`).

## Build & Run on KV260 (Linux)

```bash
gcc -O2 -Wall -o ias2rf_dma_test ias2rf_dma_test.c
sudo ./ias2rf_dma_test
# Optional DMA S2MM + Artix register-read roundtrip (with u-dma-buf loaded):
sudo modprobe u-dma-buf udmabuf0=1048576
sudo ./ias2rf_dma_test --rd-adcs
```
