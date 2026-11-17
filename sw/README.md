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
  - `uart1` (EMIO UART to the front-end FPGA's debug console over the two Pmod spare lines: `/dev/ttyPS1`,
    115200 8N1; `screen /dev/ttyPS1 115200` shows the boot banner and the 1 Hz `STAT` line, and `h` lists the
    commands, [FPGA_GATEWARE §5.4](../docs/FPGA_GATEWARE.md))
- `ias2rf_dma_test.c` — Standalone C smoke test (`mmap` `/dev/mem` + optional `u-dma-buf` `/dev/udmabuf0`):
  - Prints all IAS1 link CSRs (`0x00..0x34`) and flags `0xDEAD_C10C` if the Artix `LINK_RX_CLK` is not yet running.
  - Supports `--retrain` (pulses `LINK_CTRL[2]`) and `--rd-adcs` (sends a Stream `0x10` register-read request for Artix `0x0038 ADCS_STATUS` via `MM2S`, then captures 4 KB of uplink frames via `S2MM`).
  - Artix registers through the same command channel: `--rd ADDR`, `--wr ADDR VALUE`, and for the radar path
    `--radar-en 0|1` (`RADAR_CTRL[0]`, `0xE4`) and `--radar-status` (`RADAR_STATUS`, `0xE8`; bit 5 is "link up and
    ADC trained"). Since Rev08 these replace the two Pmod spare GPIOs, which now carry the debug UART.

## Build & Run on KV260 (Linux)

```bash
gcc -O2 -Wall -o ias2rf_dma_test ias2rf_dma_test.c
sudo ./ias2rf_dma_test
# Optional DMA S2MM + Artix register-read roundtrip (with u-dma-buf loaded):
sudo modprobe u-dma-buf udmabuf0=1048576
sudo ./ias2rf_dma_test --rd-adcs
sudo ./ias2rf_dma_test --radar-status       # read-back arrives in the S2MM capture
sudo ./ias2rf_dma_test --radar-en 0         # radar DDC off
```
