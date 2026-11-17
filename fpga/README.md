# FPGA Gateware: Dual-FPGA RTL, Vivado Builds & XSim Verification

This folder contains the complete synthesizable Verilog gateware, Vivado 2026.1 constraints/build scripts, and full-system XSim co-simulation testbenches for both FPGAs in the **KV260-IAS2RF** platform (**Apache License 2.0**, with `third_party/aeris/` under MIT).

> **Comprehensive Documentation & Vivado Silicon Renders:** See [`docs/FPGA_GATEWARE.md`](../docs/FPGA_GATEWARE.md) for complete post-route Vivado silicon die floorplans (`XC7A50T` & `XCK26`), hierarchical circuit schematics, complete SDR (direct HF `0–31.25/25 MHz` & external-converter VHF/UHF) & `AERIS-10` (`10.5 GHz` / `20 km` / `8x ADAR1000`) signal chains, the `dbg_uart` monitor, and the full `0x00..0xFC` register map.

---

## Layout

| Folder / File | Purpose |
|---|---|
| `artix/` | Front-end `XC7A50T-FTG256-2` RTL (`top.v` with integrated Radar DDC, Dual-Ch SDR DDC, `dac_radar`, `dac_sdr`, `adar_ctrl`, `rf_switch`, `eth_sgmii_phy`, `eth_mac_udp`, `dual_path_mux`, `dbg_uart`, `hk_*`, `pmod_spi`; Rev08: `fe_ctrl` on `hk_xo_ctrl`'s I2C client port for the two TCA6416A expanders, and through them the VHF/UHF front end's switches, bias tee, RFFC5072 and PE4312 and the status LEDs, `fe_agc`, the 500 MSPS AD9484 path D2 `ddc_500`/`ddc500_rom`, and the beam-scan mode of `adar_ctrl`), `xc7a50t.xdc`, `build_rev06.tcl`, and routed reports (`reports_rev06/`) |
| `kria/` | Kria KV260 `XCK26-SFVC784-2LV-c` PL core (`top.v`, `kria_pl_link.v`, `link_axis.v`, PS `UART1` EMIO; Rev08: the DSP suite `kria_dsp_suite` with `kria_channel_rx`, `kria_adsb_rx`, `kria_radar_proc`, `kria_tx_mod`, `kria_cordic`; `kria_pps`; the fusion grid `kria_bev_axi` with `integrations/kria_bev_grid.v`; the KrakenSDR and HackRF Pro blocks `integrations/kria_doa.v` and `integrations/kria_sweep.v`), Vivado IPI block design (`bd.tcl`), `xck26.xdc`, `build.tcl`, and routed reports (`reports/`) |
| `link/` | Shared bidirectional `64b/66b` IAS1 PCS (`link_crc32`, `link_scrambler`, `link_gearbox`, `link_framer`, `link_lanes`, `link_rx_train_fsm`, `link_top`) + [`LINK_PROTOCOL.md`](link/LINK_PROTOCOL.md) & [`PINMAP.md`](link/PINMAP.md) |
| `third_party/aeris/` | Verbatim `PLFM_RADAR` (`62d4c55`, MIT) 400 -> 100 MSPS radar DDC modules (`ddc_400m.v`, `nco_400m_enhanced.v`, `cic_decimator_4x_enhanced.v`, `fir_lowpass.v`, `ddc_input_interface.v`, `cdc_modules.v`) |
| `eth/` | `1000BASE-T` SGMII feasibility, pin-dedicated implementation notes ([`REV06.md`](eth/REV06.md)), failover architecture ([`REDUNDANCY.md`](eth/REDUNDANCY.md)), and standalone SGMII XSim bench |
| `sim/` | Vivado `xsim` runner (`run.ps1`), behavioral RF/IC/PCB board models (`sim/models/`), unit benches (`tb_*`), and full-system dual-FPGA co-simulation (`tb_system.v`) |
| `export_vivado_views.tcl` | Batch TCL extractor dumping placed cells, clock regions, architectural columns, and module statistics from post-route Artix-7 and Kria K26 checkpoints |

---

## Vivado 2026.1 Post-Route Implementation Status

| Target Device | Top / Wrapper | Slice LUTs | FFs | BRAM36 eq. | DSP | WNS | WHS | DRC |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **`XC7A50T-FTG256-2`** | `artix_top` (`ENABLE_ETH=1`) | `25,068 / 32,600` (`76.9%`) | `28,881 / 65,200` (`44.3%`) | `18.0 / 75` (`24.0%`) | `119 / 120` (`99.2%`) | `+0.076 ns` (`gen_rev06_eth.clk_312p5_u`, SGMII transmit; both `CLK_FPGA` modes; AD9484 at `400 MSPS` through AERIS and at `500 MSPS` through D2) | `+0.049 ns` | `0` Err |
| **`XCK26-SFVC784-2LV-c`** | `ias2rf_k26_bd_wrapper` (BD) | `36,393 / 117,120` (`31.1%`) | `36,562 / 234,240` (`15.6%`) | `32.5 / 144` (`22.6%`) | `106 / 1,248` (`8.5%`) | `+0.874 ns` | `+0.010 ns` | `0` Err |

---

## Batch Build & Simulation Commands (Vivado 2026.1)

```powershell
# Build Artix-7 bitstream & post-route reports
<Vivado 2026.1 install>\bin\vivado.bat -mode batch -nojournal -nolog -source fpga/artix/build_rev06.tcl

# Build Kria K26 Vivado Block Design + XSA + bitstream
<Vivado 2026.1 install>\bin\vivado.bat -mode batch -nojournal -nolog -source fpga/kria/bd.tcl

# Run XSim unit, E2E, SGMII & full-system dual-FPGA co-simulations
.\fpga\sim\run.ps1 tb_system
.\fpga\sim\run.ps1 tb_system -Define FPGA_CLK_400M
.\fpga\sim\run.ps1 tb_dbg_uart
.\fpga\sim\run.ps1 tb_rev06
.\fpga\sim\run.ps1 tb_e2e
```

For detailed simulation results across every testbench, see [`SYSTEM_SIM.md`](SYSTEM_SIM.md). For PetaLinux / user-space software bring-up on the K26 PS, see [`sw/README.md`](../sw/README.md).
