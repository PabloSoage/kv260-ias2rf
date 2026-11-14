# Full-System Co-Simulation (`tb_system`)

End-to-end mixed-signal/digital XSim co-simulation connecting the real front-end Artix-7 RTL ([`artix_top`](artix/top.v), `ENABLE_ETH = 1`) and the real Kria K26 PL wrapper ([`kria_pl_link`](kria/kria_pl_link.v)) across Rev05 LVDS and Rev06 SGMII (`ETH_SGTX 404/402 ps`, `ETH_SGRX 464/468 ps`) channel models, behavioral converter/RF/housekeeping peripherals, and a behavioral RTL8211FSI + PS GEM3 SGMII/UDP peer. Both eye-scan FSMs (`u_kria.u_train_fsm`, `u_artix.u_dl_train_fsm`) run at their hardware-default `TAP_DWELL_CYCLES = 1800` with live front-end streaming enabled from `t = 0` (`emio_gpio_o = 8'h00`).

Run from the repository root (`D:\Repos\kv260-ias2rf-gemini`):

```powershell
.\fpga\sim\run.ps1 tb_system
.\fpga\sim\run.ps1 tb_link_a2k
.\fpga\sim\run.ps1 tb_link_a2k -Define STREAM_FROM_T0
.\fpga\sim\run.ps1 tb_link_a2k -Mutate no_train_gate
.\fpga\sim\run.ps1 tb_rev06
```

Optional fault/mutation checks (max 2 concurrent runs, batch XSim only):

```powershell
.\fpga\sim\run.ps1 tb_system -Mutate bad_channel_skew
.\fpga\sim\run.ps1 tb_system -Mutate no_echo_return
.\fpga\sim\run.ps1 tb_system -Mutate eth_skip_fcs
.\fpga\sim\run.ps1 tb_system -Mutate no_retrain
```

Note: [`run.ps1`](sim/run.ps1) copies [`fpga/sim/design.txt`](sim/design.txt) (`TEMP 42.5`, `VCCINT 1.00`, `VCCAUX 1.80`) into `fpga/sim/out/work_<runName>/` so the Artix XADC model receives deterministic telemetry stimulus.

---

## Modeled Interfaces & Behavioral Components

Simulation resolution is `` `timescale 1ps/10fs `` ([`tb_system.v`](sim/tb_system.v); `xsim` reports `Time resolution is 10 fs`).

| Component / Model | File | Modeled Behavior |
| :--- | :--- | :--- |
| Artix-7 Top RTL | [`artix/top.v`](artix/top.v) | Real `artix_top` (`ENABLE_ETH = 1`), nominal `100.000 MHz` (`#5000.000` ps half-period) |
| Kria K26 PL Wrapper | [`kria/kria_pl_link.v`](kria/kria_pl_link.v) | Real `kria_pl_link` with AXI4-Lite CSRs, 64-bit AXI4-Stream TX/RX DMA, MMCM, `IDELAYE3`/`ISERDESE3`, `u_train_fsm`, configurable `pl_clk_100m` (`4999.500` ps `+100 ppm` initial, `-100 ppm` in S5) |
| LVDS Channel & Fault Hook | [`sim/models/board_lvds_channel.v`](sim/models/board_lvds_channel.v) | `sim_board_lvds_channel`: independent `DLY_P_PS` / `DLY_N_PS` leg delays, PRNG differential timing jitter (`JITTER_SPREAD_PS`), transport delays preserving multi-UI transitions (`>1000 ps` @ 1 Gbps), dynamic `cut_fault` and `glitch_inj` inputs |
| AD9484 400 MSPS Radar ADC | [`sim/models/ad9484_radar_model.v`](sim/models/ad9484_radar_model.v) | `sim_ad9484_model`: 3-wire SPI (Chip ID `0x6C`), inverted DCO routing, `lvds_skew.py` per-bit skew + eye spread; `mode=0` (`0xAA`/`0x55` IDELAY calibration), `mode=1` (`121.5625 MHz` IF CW -> `+1.5625 MHz` baseband @ 25 MSPS), `mode=2` (closed-loop echo sampling `dacr_d`/`dacr_clk` delayed by `ECHO_DELAY_DAC_CYC = 250` @ 125 MHz DAC clock, upconverted to `120 MHz` IF + noise, `no_echo_mut` fault control) |
| AD9253 Dual 14-bit SDR ADC | [`sim/models/ad9253_sdr_model.v`](sim/models/ad9253_sdr_model.v) | `sim_ad9253_model`: 3-wire SPI (Chip ID `0x8F`), coherent `6.25 MHz` (Ch A) + `12.5 MHz` (Ch B) @ 50 MSPS, `lvds_skew.py` skew (`ADCS_D0 -8 ps`, `ADCS_D1 -34 ps`, `ADCS_FCO -18 ps` vs DCO) with `25 ps` transport margin |
| 8x ADAR1000 SPI Array | [`sim/models/adar1000_array_model.v`](sim/models/adar1000_array_model.v) | `sim_adar1000_array`: 8 independent slaves on `adar_csb[7:0]`, 24-bit SPI read/write + `tx_load`/`rx_load` active latching, real-time `tr_viol` monitor |
| AD9708 & AD9767 DAC Monitors | [`sim/models/dac_monitor_models.v`](sim/models/dac_monitor_models.v) | `sim_dac_radar_mon` (AD9708 setup `>=2.0 ns`, hold `>=1.5 ns`, LFM chirp zero-crossing slope check) and `sim_dac_sdr_mon` (AD9767 `IQWRT`/`IQCLK`/`IQSEL` 14-bit I/Q quadrature capture) |
| Housekeeping I2C Slaves | [`sim/models/hk_i2c_periph_models.v`](sim/models/hk_i2c_periph_models.v) | `sim_hk_i2c_slave`: open-drain I2C slaves for TMP1075 (`0x48`, `0x2A80`), CAT24C02 EEPROM (`0x50`), and Si549 XO (`0x55`) |
| SGMII PHY + PS GEM3 Peer | [`sim/models/sgmii_phy_kria_peer.v`](sim/models/sgmii_phy_kria_peer.v) | Behavioral RTL8211FSI + GEM3 peer: `K28.5` comma-pair CDR lock (`ui_tick <= 2'd3` 2-tick = `400..600 ps` UI-center sampling) with 4-error auto-relock, MDIO, UDP/IPv4/ARP TX/RX, and packet sequence scoreboard (`seen_eth_s1`, `seen_eth_s2`) |

---

## Simulation Speed Scaling

To complete all six multi-domain scenarios in ~6 minutes of batch XSim while running both eye-scan FSMs at their true hardware-default `TAP_DWELL_CYCLES = 1800` (no dwell `defparam`), [`tb_system.v`](sim/tb_system.v) overrides only slow housekeeping/MDIO/watchdog timers via `defparam`:

| Parameter | Simulation Value | Hardware Role / Comment |
| :--- | :---: | :--- |
| `ETH_ALIVE_TIMEOUT` | `25000` | `200 us` watchdog window (vs `1 s` hw) |
| `HK_POLL_DIV` | `16000` | Accelerated housekeeping I2C poll period |
| `XO_FCAL_WAIT_CYC` | `150` | Accelerated Si549 XO FCAL wait |
| `ETH_MDIO_POLL_DIV` | `1200` | Accelerated MDIO status poll divider |

---

## RTL Bugs Caught & Fixed During Co-Simulation

1. **`kria_pl_link` async FIFO reset sensitivity & downlink unpack width (`fpga/kria/kria_pl_link.v`):**
   - `kria_pl_async_fifo` originally used synchronous-only `@(posedge wr_clk)` / `@(posedge rd_clk)` resets and uninitialized pointer/synchronizer registers, and `pcs_rst_rx` lacked an initial value. Added async reset sensitivity (`or posedge wr_rst` / `or posedge rd_rst`) and deterministic `= 0` / `= 1'b1` initial values.
   - `u_fifo_dl` / `dl_fifo_rd_data` had a width mismatch (`130` bits declared vs `122` bits packed: `2` sop/eop + `8` stream_id + `16` len + `32` seq + `64` data), leaving the upper control/ID MSBs `X`/`0`. Aligned to `122` bits and sliced `[121:0]`.
2. **Mid-run Ethernet peer silence detection (`fpga/artix/top.v`):**
   - `eth_path_ok` previously ignored `eth_remote_alive_stat`, so cutting the peer RX link or stopping peer keepalives did not degrade `eth_healthy` after `ETH_ALIVE_TIMEOUT`. Added `eth_seen_remote_alive` in the `link_clk` domain so `eth_path_ok = eth_link_up_stat & ~ctrl_force_eth_fault & (eth_remote_alive_stat | ~eth_seen_remote_alive)`, allowing initial AN/bring-up before the first peer frame while triggering deterministic failover on mid-run loss.
3. **Mid-packet arbitration & abort drain in `dual_path_mux` (`fpga/artix/dual_path_mux.v`):**
   - When `eth_healthy` dropped during `POL_SPLIT` while `eth_in_lock == 2'd2` (packet `s1` already mid-transfer into `u_fifo_eth`), `ias_in_sel` could latch `s1` mid-packet (`s1_sop == 0`), injecting a headless (`out_sop == 0`) fragment into `u_fifo_ias` that stalled `link_framer`. Added `s0_avail_*` / `s1_avail_*` SOP gating, cross-port lock exclusion (`eth_in_lock` / `ias_in_lock`), and `drop_s0` / `drop_s1` drain on FIFO abort.
4. **Bidirectional uplink idle/AM training gate & MDIO edge/free-run cleanup (`fpga/artix/top.v`, `fpga/artix/eth_mdio.v`, `fpga/artix/xc7a50t.xdc`):**
   - `u_ul_pcs_tx` is now gated (`ul_tx_allow = dl_up_sync[1] & dl_rem_sync2[0]` with packet-boundary `ul_in_pkt` hold) so only `/I/` + `/A/` training blocks are transmitted whenever either direction is unlocked, allowing Kria uplink eye training (`u_kria.train_cnt_l0/l1`) and S6 retrain to lock cleanly with live front-end traffic active from `t = 0`.
   - `eth_mdio.v` now stops `eth_mdc` low (`ST_IDLE`) between 1 ms status polls and reduces IOBUF drive to `4 mA`, paired with `SLEW SLOW` and `DRIVE 4` in [`artix/xc7a50t.xdc`](artix/xc7a50t.xdc).

---

## Verification Results (Vivado XSim 2026.1)

Post-fold checks below ran directly after all Rev06 / training-gate / MDIO / `t=0` edits on `gemini/work`:

### Baseline Full-System Pass (`tb_system`, Hardware `TAP_DWELL_CYCLES = 1800`, `t = 0` Live Streaming)

- Command: `.\fpga\sim\run.ps1 tb_system` -> **Exit code `0`**, elapsed **`358.98 s`**
- Observed output:
  - `[S1] PASS REG_LINK_STATUS=0x003500fd mdio_polls=6 dl_up=1 eth_up=1 eye0=[216..416]@316 eye1=[224..424]@324` (`u_kria.train_cnt_l0=316`, `train_cnt_l1=324`, inside `0..511`)
  - `[S2] PASS AD9253=0x8F AD9484=0x6C TMP1075=0x2A80 PPS=1251(+800 ppm)`
  - `[S3] PASS chirp zc1=18->zc2=34 echo_snr=159.8x cw_img_rej=61.3 dB`
  - `[S4] PASS rx04=3(max=8579) rx05=3(max=8373) dacs_i=36 dacs_q=35`
  - `[S5] PASS -100ppm MIRROR_1P1 + mid-run ETH/IAS1 cuts lost_s1=0 lost_s2=0 mdio_wrs=1`
  - `[S6] PASS glitch->crc_err->clear->retrain(drop=1,up=1,post_crc=0)`
  - `PASS: tb_system full-system verification (S1..S6, +/-100 ppm, Rev05 SI, ETH+IAS1) passed`

### Standalone Link & Rev06 Regression Checks

- `.\fpga\sim\run.ps1 tb_link_a2k` -> **Exit code `0`** (`PASS: tb_link_a2k rate=1000M skew_d1_300=0 tx=20 rx_good=19 crc_err=1 tap0=192 tap1=208`)
- `.\fpga\sim\run.ps1 tb_link_a2k -Define STREAM_FROM_T0` -> **Exit code `0`**, elapsed **`9.74 s`** (`PASS: tb_link_a2k rate=1000M skew_d1_300=0 tx=20 rx_good=19 crc_err=1 tap0=192 tap1=208`)
- `.\fpga\sim\run.ps1 tb_link_a2k -Mutate no_train_gate` -> **Exit code `1`**, elapsed **`10.11 s`** (`FAIL: tb_link_a2k rate=1000M skew_d1_300=0 tx=20 rx_good=0 crc_err=0 mismatches=0 tap0=192 tap1=208`)
- `.\fpga\sim\run.ps1 tb_rev06` -> **Exit code `0`**, elapsed **`47.66 s`** (`PASS: tb_rev06 ias_s1=78 eth_s1=11 ias_s2=53 eth_s2=61 max_s1=77 max_s2=102 phase_sw=55 lost=0`)

### Negative Mutation Runs (`tb_system -Mutate`)

Earlier Part A baseline mutations (`bad_channel_skew` exit `1` in `306.53 s`, `no_echo_return` exit `1` in `270.72 s`, `eth_skip_fcs` exit `1` in `261.98 s`) passed on commit `231fbf6`; `no_retrain` was re-run post-fold:

- `.\fpga\sim\run.ps1 tb_system -Mutate no_retrain` -> **Exit code `1`**, elapsed **`287.13 s`** (`FAIL @ 93784159500 ps: S6: LINK_CTRL[2] retrain did not execute and recover link_up`)

---

## Explicit Verification Limits

1. **Behavioral peripheral & analog/PHY models:** `u_ad9484`, `u_ad9253`, `u_adar1000`, `u_dacr_mon`, `u_dacs_mon`, `sim_hk_i2c_slave`, `sgmii_phy_kria_peer`, and `sim_board_lvds_channel` are Verilog behavioral models approximating datasheet protocols, `lvds_skew.py` static delays, and `SIGNAL_INTEGRITY.md` jitter/noise budgets — not SPICE/IBIS full-wave SI or silicon converter models.
2. **PS firmware & Linux stack excluded:** `tb_system` drives `kria_pl_link` AXI4-Lite/AXIS ports directly via testbench BFMs rather than executing ARM Zynq PS C code, Linux DMA drivers, or GEM3 MAC microcode.
3. **Scaled timers & watchdog intervals:** Simulation speed-up overrides compress housekeeping polling, Si549 FCAL wait, MDIO polling, and `ETH_ALIVE_TIMEOUT` (`200 us` vs `1 s` hardware); `TAP_DWELL_CYCLES` runs at hardware default (`1800`).
4. **XSim UltraScale+ primitive advisory:** Vivado XSim 2026.1 emits `[Unisim IDELAYE3-1]` advisories on `u_kria.u_idelay_d0`/`d1` noting behavioral reset limitations when `DELAY_FORMAT = TIME`.
5. **Pre-existing routed bitstreams/reports not re-run:** The RTL fixes in [`artix/top.v`](artix/top.v), [`artix/dual_path_mux.v`](artix/dual_path_mux.v), and [`kria/kria_pl_link.v`](kria/kria_pl_link.v) are verified in RTL XSim (`tb_system` and `tb_rev06`); the existing Vivado routed reports and `.bit`/`.xsa` artifacts in [`artix/reports/`](artix/reports), [`kria/out/`](kria/out), and [`kria/reports/`](kria/reports) remain from the earlier implementation run and were not re-synthesized/re-routed during this verification task.
