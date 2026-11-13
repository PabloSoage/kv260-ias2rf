# Ethernet Load-Balancing & Link Redundancy Architecture (`Rev05` & `Rev06`)

Analysis of pairing Gigabit Ethernet (`U1201 RTL8211FSI-CG` + `J1201 HR911130C`) with the existing `IAS1` LVDS link (`J8`) as a load-balanced second transport or redundant failover channel between the `XC7A50T-2FTG256I` front-end FPGA and the AMD Kria `KV260` (`XCK26-SFVC784-2LV-C`).

---

## 1. Current Board (`Rev05` / `Rev04+ETH`) With `ETH` BOM Option Fitted

Per `docs/CONTROL_SPEC.md §7` and `docs/SIGNAL_INTEGRITY.md §9.7`, selecting the Ethernet assembly option fits `C1218–C1221` (`100 nF` `0402`) and removes `C101, C102, C107, C108`.

### 1.1 Surviving `IAS1` Lanes vs Claimed Pairs

| Signal Pair | Artix-7 Pins (Bank) | K26 SOM Pins (`J8`) | Direction (ETH Option Fitted) | Status |
|---|---|---|---|---|
| `LINK_RX_D0` | `L4 / M4` (Bank 34, `2.5 V`) | `A2 / A1` (`HPA06`, floating) | Artix `OBUFDS` → `C1220/C1221` → `U1201 HSIP/N` (`ETH_SGTX_PHY`) | **Claimed by Ethernet TX (`1.25 Gb/s`)** (`C101/C102` removed) |
| `LINK_TX_D0` | `M16 / N16` (Bank 14, `3.3 V`) | `B4 / A4` (`HPA09`, floating) | `U1201 HSOP/N` → `C1218/C1219` → Artix `IBUFDS_DIFF_OUT` (`ETH_SGRX_PHY`) | **Claimed by Ethernet RX (`1.25 Gb/s`)** (`C107/C108` removed) |
| **`LINK_RX_D1`** | `M2 / M1` (Bank 34, `2.5 V`) | `B3 / A3` (`HPA07`) | Artix → Kria (`DIFF_SSTL12 ODT=RTT_48`) | **Intact (`1` uplink data lane)** |
| **`LINK_RX_CLK`** | `N3 / N2` (Bank 34, `2.5 V`) | `C1 / B1` (`HPA05_CC`) | Artix → Kria (`500–625 MHz` DDR source-sync clock) | **Intact (`1` uplink clock)** |
| **`LINK_TX_CLK`** | `N13 / P13` (Bank 14 SRCC) | `D4 / C4` (`HPA08`) | Kria → Artix | **Intact (unused by Ethernet)** |
| `HK_SCL/SDA`, `FPGA_PROG_B`, `FPGA_IRQ` | Bank 35 (`1.8 V`) | `J8` pins `14, 22, 21, 15` | Slow I2C / reset / interrupt | **Intact** |

Fitting Ethernet does **not** eliminate `IAS1`; it converts `IAS1` from a `2`-lane uplink + `1`-lane downlink into a **`1`-lane uplink (`LINK_RX_D1` + `LINK_RX_CLK`) plus a `1 Gb/s` bidirectional Ethernet path**.

### 1.2 Signal-Integrity Check on Running `LINK_RX_D1` Concurrently with `ETH_SGTX_PHY`

`CONTROL_SPEC.md §7` and `SIGNAL_INTEGRITY.md §9.7` note that `ETH_SGTX_PHY` runs beside `LINK_RX_D1_N` on **L1** for **`5.2 mm` at `0.17 mm` edge-to-edge gap**, and advise holding `LINK_RX_D1` static in an Ethernet-only build. Evaluating concurrent operation (`LINK_RX_D1` + `ETH` both active at `1.25 Gb/s`):

- **Measured board eyes (`SIGNAL_INTEGRITY.md` & `IAS_LINK_SPEC.md`):**
  - `ETH_SGTX_PHY` arrives at `U1201` with **`350 mV` eye / `50 ps` jitter** (Artix LVDS driver launch on `LINK_RX_D0` = `601–607 mV` at `J8` pad).
  - `ETH_SGRX_PHY` arrives at `M16/N16` with **`637 mV` eye / `53 ps` jitter**.
  - `LINK_RX_D1` opens **`491 / 524 mV`** (`P/N`) at `1.25 Gb/s` (`575 / 559 mV` at `1.0 Gb/s`).
  - Receiver threshold for `LVDS_25` (`DS181 Table 11`) is **`100 mV` (`200 mV` differential peak-to-peak)**.
- **NEXT / FEXT coupling magnitude (`SIGNAL_INTEGRITY.md §3.5`):**
  - On `L1` (`0.183 mm` microstrip over `0.1164 mm` prepreg), 2D NEXT at `≥ 25 mm` saturated length is **`14.5%` at `0.15 mm`** and **`7.7%` at `0.25 mm`** (linear interpolation at `0.17 mm` ≈ **`13.1%`**).
  - Scaling linearly below `25 mm` (`5.2 mm / 25 mm = 0.208`) gives a 2D upper bound of **`2.7%`** (`~9.5 mV` on a `350 mV` leg).
  - Per `pair_xtalk.py` (3D openEMS calibration in `SIGNAL_INTEGRITY.md`), 2D overestimates 3D microstrip NEXT by **`~3.5×`** (`12.6 mm @ 0.15 mm` produced **`1.9%`** ≈ `7 mV`). Scaling `1.9%` down to `5.2 mm` and wider `0.17 mm` yields **`~0.7%–0.8%` (`~2.5–3 mV` single-ended)**.
  - Even better, `LINK_RX_D1` and `ETH_SGTX_PHY` are co-directional FPGA outputs (`L4/M4` and `M2/M1`), so direct forward crosstalk dominates and backward NEXT appears primarily from downstream reflections. A `< 10 mV` (`2D` worst-case) / `~3 mV` (`3D` estimate) perturbation leaves **`> 140 mV` (`ETH_SGTX_PHY`) and `> 280 mV` (`LINK_RX_D1` @ `1.25 Gb/s`)** differential margin above the `200 mV` threshold.
- **Conclusion:** Holding `LINK_RX_D1` static is safest when Ethernet alone suffices, **but running `LINK_RX_D1` concurrently with `ETH` is electrically sound (`< 3%` 2D / `~0.8%` 3D coupling)** once eye-tested at `1.25 Gb/s`.

### 1.3 Kria-to-Artix (`K→A`) Control Paths When `ETH` Claims `LINK_TX_D0`

Because `J8` has only one `K→A` high-speed data pair (`LINK_TX_D0`) and Ethernet claims it:

1. **UDP Control over `ETH` (default in-band path):** Bidirectional `1000BASE-T` SGMII natively delivers register writes, `retrain`, `prbs7` test enables, and `ADAR1000` beam updates from Kria Linux (`PS GEM3`) to Artix without extra cables. *Weakness:* shares fate with Ethernet.
2. **External Pmod Cable `J2 ↔ J1102` (out-of-band fail-safe):** Per `fpga/link/PINMAP.md`, Kria `J2` (`Bank 45 HD`, `3.3 V`) and Artix `J1102` (`Bank 15`, `3.3 V`) are not PCB-connected across `J8`; a short 12-pin Pmod ribbon/jumper cable restores the complete `pmod_spi` (`CS_n`, `SCLK`, `MOSI`, `MISO`), hardware `beam_strobe`, `pps_sync`, and `2` spare pins, completely decoupled from both Ethernet and `IAS1`.
3. **Fallback Serial over `LINK_TX_CLK` (`D4/C4 → N13/P13`) + `J8` GPIO:** `LINK_TX_CLK` stays wired `Kria → Artix` through `J8` in `ETH` mode. Repurposing `LINK_TX_CLK` as a DC-balanced Manchester/UART/8b10b low-rate control channel (`10–50 Mb/s`) provides cable-free `K→A` control even if `ETH` is disconnected (and `FPGA_IRQ` + `HK_SCL/SDA` remain intact).

### 1.4 Aggregate Throughput & Redundancy in `Rev05` Dual Mode

| Metric | `IAS1` (`LINK_RX_D1`, 1-lane) | `ETH` (`1000BASE-T` SGMII) | Dual Mode Aggregate |
|---|---|---|---|
| **Line Rate** | `1.00 Gb/s` (nom.) / `1.25 Gb/s` (`-2` max) | `1.25 Gb/s` (8b/10b → `1.00 Gb/s` MAC) | `2.25` / `2.50 Gb/s` wire |
| **Coding & Header Overhead** | `64/66` (`96.97%`) − AM & `/S/`/`/T/`/`CRC` (~`2%`) | `958 Mb/s` (`1500 B` UDP) / **`993 Mb/s`** (`9000 B` jumbo UDP) | — |
| **Usable Uplink Payload** | **`~0.95 Gb/s`** (`1.0G`) / **`~1.19 Gb/s`** (`1.25G`) | **`~0.99 Gb/s`** (jumbo) | **`~1.94 Gb/s`** (`1.0G IAS1`) / **`~2.18 Gb/s`** (`1.25G IAS1`) |
| **Radar + SDR Fit** | Radar `DDC_POST_DECIM=4` (`0.80 Gb/s`) fits 1 lane | Covers SDR I/Q (`<= 0.99 Gb/s`) + control | Covers `1.60 Gb/s` Radar (`DECIM=2`) OR simultaneous Radar (`0.80 Gb/s`) + SDR (`<= 1.19 Gb/s`) |
| **Single-Path Failover** | Survives `RJ45`/switch/PHY fault (`~0.95–1.19 Gb/s` degraded uplink) | Survives `J8` `D1` contact/eye fault (`~0.99 Gb/s` degraded uplink + control) | **Eliminates single connector/cable SPOF** |

---

## 2. KV260 Network Architecture, Bonding vs Application Merge, and Failover

### 2.1 KV260 Ethernet Port Count & PS vs PL Mapping (`UG1089`, `UG1085`)

- **On-board Ethernet port:** Per `UG1089` and Vivado board preset `k26c/2.0/preset.xml` (`PSU__CRL_APB__GEM3_REF_CTRL__FREQMHZ = 125`), the KV260 carrier provides **exactly one** physical Ethernet port: RJ45 **`J10`**, driven by Zynq UltraScale+ MPSoC **`PS GEM3`** (`MIO 64–77`) through an on-board RGMII PHY (`TI DP83867`).
- **PL Ethernet ports:** **None on the KV260 carrier.** `J8` (`IAS1`, `5` pairs) and `J9` (`RPi cam`, `3` pairs) go directly to the K26 `Bank 66 HP` (`VCCO = 1.2 V`, `DIFF_SSTL12`). While `J9` could theoretically host a second external adapter card with another SGMII PHY, off-the-shelf KV260 only exposes `J10` (`GEM3`). Additional external network ports (e.g., for an expedition laptop or `Livox Mid-360` LiDAR per `docs/VEHICLE_PLATFORM.md`) must either share `J10` via a GbE switch or use the KV260's **4× USB 3.0** ports with USB-GbE adapters.

### 2.2 Topologies: Direct Cable vs Switch

| Aspect | Topology A: Direct Patch (`Adapter J1201 ↔ KV260 J10`) | Topology B: Ruggedized GbE Switch (`Adapter + KV260 + LiDAR + PC`) |
|---|---|---|
| **Dedicated BW to KV260** | Full **`993 Mb/s`** (jumbo UDP) uncontended | Shared on `J10` (`1.0 Gb/s` cap minus LiDAR `~10–100 Mb/s` & control) |
| **Added Latency / Jitter** | **`~5–15 µs`** wire + PHY | `+5–20 µs` switch fabric + queuing jitter when LiDAR bursts |
| **External Connectivity** | Needs USB-GbE dongle on KV260 for LiDAR/laptop | Native multi-host LAN (`J10` connects all) |
| **Single Point of Failure** | Minimal (passive cable only) | Switch PSU / PoE / boot becomes common SPOF |

### 2.3 Linux Kernel `bonding` vs Application-Level Merge

Linux kernel `bonding` (`mode=0` `balance-rr`, `mode=1` `active-backup`, `mode=4` `802.3ad`) **is the wrong layer** for combining `IAS1` (`PL AXI-Stream`) and `ETH` (`PS GEM3` `eth0`):

1. `IAS1` enters K26 PL directly into `fpga/kria/link_axis.v` (AXI4-Stream → AXI-DMA to PS DDR), not as a Linux `net_device`. Emulating an Ethernet TAP/netdev around `IAS1` wastes CPU copies and interrupts, and Linux `balance-rr` would severely reorder packets between a **`~1–3 µs` PL DMA path (`IAS1`)** and a **`~50–250 µs` PHY + `GEM3` + `macb` NAPI path (`ETH`)**.
2. **Recommended: Application-Level Merge using `LINK_PROTOCOL.md` Framing:** `LINK_PROTOCOL` already embeds **`stream_id[7:0]`**, **`seq_num[31:0]`**, **`pkt_len[15:0]`**, and **`pps_timestamp_ns[63:0]`** in every packet. Wrapping the same `16 B` metadata header inside `ETH` UDP payloads lets the Kria PS ingest `IAS1` via AXI-DMA ring and `ETH` via `AF_XDP` / `recvmmsg`, merging them directly by `(stream_id, seq_num)` or `pps_timestamp_ns` in shared DDR ring buffers with zero kernel netfilter overhead.

### 2.4 Failover Detection, Switch-Over Loss, and Load-Balancing Policies

- **Detection latency:**
  - `IAS1` failure: `fpga_irq` + Clause 49 `l0_block_lock` / `crc_err` triggers within **`~1–10 µs`** (`3.4 µs` for 64 consecutive invalid sync headers).
  - `ETH` failure: PHY MDIO link-down polling takes `10–100 ms`; in-band `seq_num` watchdog / UDP keepalive timeout in Kria PS or Artix RX heartbeat detects link stall in **`1–10 ms`**.
- **Switch-over packet loss vs BRAM buffering:** At `1.0 Gb/s` (`125 MB/s`), `10 ms` of blind flight equals `1.25 MB` (larger than `XC7A50T`'s `75 × 36 Kb = 337.5 KB` total BRAM). However:
  - For `IAS1` → `ETH` failover (`10 µs` fault detection via `FPGA_IRQ` / local TX monitoring if `LINK_RX_D1` / `K26` back-channels faults via `ETH` or `Pmod`), a **`64 KB` BRAM elastic buffer** (`~15 × 36 Kb` BRAM, `20%` of chip) holds **`512 µs`** of `1 Gb/s` data — sufficient for **zero-loss** fast switchover on `IAS1` link glitches.
  - For **`0`-packet-loss against sudden `RJ45` unplug (`1–10 ms` timeout)**, **Policy 4 (`1+1` Active-Active Hitless Duplication)** sends identical packets (`<= 950 Mb/s`) across both links; the Kria PS deduplicates on `seq_num`, guaranteeing **zero dropped frames** at the cost of no rate aggregation.
- **Load-Balancing Policies:**
  1. **Active-Backup (`Hot Standby`):** `IAS1 D1` primary (`0.95–1.19 Gb/s`), `ETH` warm standby (carries `K→A` control + keepalive). Minimal jitter, simple failover (`1–10 ms` gap).
  2. **Stream-Pinned Split (Recommended default):** `stream_id = 0` (Radar DDC `0.80 Gb/s`) pinned to `IAS1 D1`; `stream_id = 1` (SDR ADC + telemetry) + `K→A` control pinned to `ETH`. Zero cross-path packet reordering; full **`~1.94–2.18 Gb/s`** aggregate; on either path failure, drop low-priority stream or dynamically raise `DDC_POST_DECIM` so the surviving `~0.95 Gb/s` lane keeps the primary sensor online.
  3. **Weighted Packet Striping (`seq_num` Reorder Buffer):** Distribute chunks dynamically across `IAS1` (`~55%` @ `1.25G`) and `ETH` (`~45%`) for a single `> 1.2 Gb/s` burst stream; requires `≥ 512 KB` DDR reorder window on Kria PS to absorb `~50–250 µs` relative `ETH` vs `IAS1` latency skew.
  4. **`1+1` Hitless Duplication:** Mirror `<= 0.95 Gb/s` mission-critical stream on both `IAS1` and `ETH` and deduplicate via `seq_num` in PS (**`0` packet loss** on instant fault).

---

## 3. Protocol, Jumbo Frames (`9000 B`), and FPGA Utilization

### 3.1 Raw Layer-2 (`EtherType`) vs UDP/IPv4 + Jumbo Support

| Protocol Choice | Overhead per Frame (`1500 B` / `9000 B`) | Effective Wire Rate (`1.00 Gb/s` MAC) | Artix Logic Delta | Operational Trade-off |
|---|---|---|---|---|
| **Raw L2 (`EtherType 0x88B5`)** | `14 B` L2 + `4 B` FCS + `20 B` IFG/pre = `38 B` | `975 Mb/s` / `996 Mb/s` | Baseline (`eth_mac_1g` only) | Lowest LUTs, requires `CAP_NET_RAW` (`AF_PACKET`), non-routable across L3 subnets |
| **UDP/IPv4 (Static ARP/IP)** | `42 B` L2/IP/UDP + `4 B` FCS + `20 B` IFG/pre = `66 B` | `958 Mb/s` / **`993 Mb/s`** | `+~400–800` LUTs (fixed header + ARP/UDP TX/RX) | Standard Linux `recvmmsg`/`AF_XDP`, routable across switches/PCs, Wireshark-native |

- **Jumbo Frame Support (`9000 B`) Confirmed End-to-End:**
  - **`RTL8211FSI-CG`:** Per Realtek datasheet summaries (`search_web`), natively supports jumbo frames up to **`16 KB`**.
  - **KV260 `PS GEM3`:** Per AMD `UG1085` and the Linux `macb` driver, `ZynqMP GEM` hardware supports up to **`10,240 B`** frames (`jumbo_frames` / `JML` register), allowing `ip link set eth0 mtu 9000` cleanly.
  - Using **`9000 B` UDP jumbo frames** cuts L2/IP/UDP + preamble overhead from `4.2%` (`958 Mb/s`) to **`0.73%` (`993 Mb/s`)** and reduces Linux PS packet/interrupt rate **6×** (`~13.8 kpps` vs `~82.2 kpps` at `1 Gb/s`).
- **`LINK_PROTOCOL` Reuse:** Prepend the `16 B` `LINK_PROTOCOL.md` header (`{stream_id[7:0], flags[7:0], pkt_len[15:0], seq_num[31:0], pps_timestamp_ns[63:0]}`) directly at UDP payload offset `0` (dropping redundant inner CRC32 if trusting Ethernet `FCS`, or keeping it for end-to-end bus integrity across DMA). That yields `~8,960 B` (`1,120 × 64-bit` ADC/IQ words) per jumbo UDP packet (`99.1%` net sensor efficiency).

### 3.2 Open-Source `verilog-ethernet` (MIT) vs Current `artix_top` Utilization

From `fpga/artix/reports/utilization.rpt`, `fpga/eth/test/reports/utilization.rpt`, `fpga/kria/reports/utilization.rpt`, and Vivado `get_parts`:

| Resource | `XC7A50T-FTG256-2` Available | Current `artix_top` (Task 7) | `sgmii_lvds` PoC (Task 12A) | Custom 8b10b/PCS + `verilog-ethernet` (MIT `eth_mac_1g` + `udp` + `64 KB` replay FIFO) | Projected Artix-7 Total (% Used) | Kria `kria_top` Baseline (Task 10) |
|---|---|---|---|---|---|---|
| **LUTs** | `32,600` | `4,441` (`13.6%`) | `287` (`0.88%`) | `~1,800–3,500` | **`~6,528–8,228` (`20.0%–25.2%`)** | `4,278 / 117,120` (`3.65%`) |
| **Flip-Flops** | `65,200` | `6,311` (`9.7%`) | `364` (`0.56%`) | `~1,800–3,000` | **`~8,475–9,675` (`13.0%–14.8%`)** | `6,817 / 234,240` (`2.91%`) |
| **`36 Kb` BRAM** | `75` (`337.5 KB`) | `0` (`0%`) | `0` (`0%`) | `~18–22` (`2–6` MAC/UDP + `15` for `64 KB` buffer) | **`~18–22` (`24.0%–29.3%`)** | — (`PS GEM3` uses PS DDR) |
| **DSP48E1** | `120` | `87` (`72.5%`) | `0` | `0` | **`87` (`72.5%`)** | — |
| **MMCM** | `5` | `2` (`40%`) | `1` (or shared) | `0` | **`3` (`60%`)** | — |

**Conclusion:** Even with a `64 KB` elastic failover buffer, MIT-licensed `verilog-ethernet` + custom 8b/10b PCS + `sgmii_lvds` uses **`~25%` of LUTs, `~15%` of FFs, and `< 30%` of BRAMs**, leaving over **70% headroom** in `XC7A50T-2FTG256I`. On the Kria side, `GEM3` is a hard PS peripheral requiring **zero PL LUTs**.

---

## 4. Next Board Revision (`Rev06`): Giving Ethernet Its Own FPGA Pins (Report Only)

*No board or schematic files are edited here; hardware findings below are strictly for a future `Rev06` revision.*

### 4.1 Free Artix-7 Banks & Differential Pairs (`_work/sheets/control_spec.py` & `_work/layout/xc7a50t_ftg256_pkg_delays.csv`)

Bank 34 (`VCCO = 2.5 V`) currently uses only **`3` of its `9` differential pairs** (`L4/M4`, `M2/M1`, `N3/N2`). **`6` complete differential pairs and `2` single-ended pins (`14` balls total) are completely unused (`NC`):**

| Free Bank 34 Diff Pair (`VCCO = 2.5 V`) | Pin Function | Suggested `Rev06` Assignment | Legal `IOSTANDARD` & Advantages |
|---|---|---|---|
| **`R2 / R1`** | `IO_L7P/N_T1_34` | **`ETH_SGTX_PHY`** (`Artix → U1201`) | **`LVDS_25`** native output (`2.5 V` bank) |
| **`R3 / T2`** | `IO_L8P/N_T1_34` | **`ETH_SGRX_PHY`** (`U1201 → Artix`) | **`LVDS_25` with `DIFF_TERM = TRUE`** (legal because `VCCO = 2.5 V`! Removes external `100 Ω` stub; `IODELAY_GROUP` or regional `BUFIO` in Bank 34) |
| `T4 / T3` | `IO_L9P/N_T1_DQS_34` | Spare LVDS (or `ETH` clk/sync if needed) | `LVDS_25` |
| `N1 / P1`, `P4 / P3`, `M5 / N4` | `IO_L4..6_T0_34` | Spare LVDS (`T0` nibble shared with `LINK_RX_*`) | `LVDS_25` |
| `L5`, `P5` | `IO_0_34`, `IO_L10P_T1_34` | `ETH_MDIO`, `ETH_MDC` (or `Bank 14/15` `3.3 V` NC pins) | `LVCMOS25` (check `RTL8211FSI` `DVDD_RG`/`VIO` if `2.5 V` or `3.3 V`; if `3.3 V`, use Bank 14/15 NC balls e.g. `K12, M15, K13, L13`) |

Wait-free `3.3 V` single-ended control pins for `U1201` (`ETH_MDC`, `ETH_MDIO`, `ETH_RST_N`, `ETH_INT_N`) are also available in **Bank 14 (`10` free balls: `K12, M15, L14, M14, K13, L13, M12, R12, T12, P6`)** and **Bank 15 (`8` free balls: `E16, F15, E15, H11, H12, H13, G14, F14`)**, removing `Rev05`'s strap-only unmanaged PHY limitation!

Putting `ETH_SGTX/SGRX` in **Bank 34 Tile `T1` (`R2/R1`, `R3/T2`)**:
1. Restores **`LINK_RX_D0` (`L4/M4`)** and **`LINK_TX_D0` (`M16/N16`)** cleanly back to `J8 / IAS1`.
2. Removes all four `C1218–C1221` assembly stubs (`LINK_TX_D0` recovers `+34–41 mV` eye from `477–484` back to `518 mV`).
3. Eliminates the `5.2 mm @ 0.17 mm` `L1` parallel between `ETH_SGTX_PHY` and `LINK_RX_D1_N`.
4. Note on Bank 34 `IDELAYE2`: `XC7A50T` supports `IDELAYE2` + `IDELAYCTRL` in Bank 34 (just like Bank 14), driven from the same shared `200 MHz REFCLK` `BUFG`, so RX `ISERDESE2` + `IDELAYE2` in Bank 34 works identically to our Bank 14 PoC.

### 4.2 Artix-7 Package GTP Transceiver Audit (`DS181` & Vivado `get_parts` / IBIS `.pkg`)

| Package | Total Pins | `XC7A50T` GTP Transceivers (`Quad 216`) | Verified Source |
|---|---|---|---|
| **`FTG256` (current `17×17 mm`, `1.0 mm`)** | `256` | **`0` (none bonded)** | Vivado `xc7a50t_ftg256.pkg` (`MGT_lines = 0`), `get_parts xc7a50tftg256-2` |
| **`CSG324`** | `324` | **`0` (none bonded)** | Vivado `xc7a50t_csg324.pkg` (`MGT_lines = 0`), `get_parts xc7a50tcsg324-2` |
| **`CPG236`** | `236` | **`2` GTP lanes** (`MGTPRX0..1 / MGTPTX0..1`) | Vivado `xc7a50t_cpg236.pkg` (`13` MGT pins), `get_parts xc7a50tcpg236-2` |
| **`CSG325`** | `325` | **`4` GTP lanes** (`MGTPRX0..3 / MGTPTX0..3`) | Vivado `xc7a50t_csg325.pkg` (`23` MGT pins), `get_parts xc7a50tcsg325-2` |
| **`FGG484`** | `484` | **`4` GTP lanes** (`MGTPRX0..3 / MGTPTX0..3`) | Vivado `xc7a50t_fgg484.pkg` (`23` MGT pins), `get_parts xc7a50tfgg484-2` |

Per `DS181 Table 52`, Artix-7 GTPs run `0.500–6.25 Gb/s` on `-2` (`3.75 Gb/s` on `-1`), with `1250 Mb/s` Gigabit Ethernet jitter limits in `Table 59`. However, switching from `FTG256` to `CSG325` (`0.8 mm` pitch) or `FGG484` requires re-fanout of the entire BGA, adding **`1.0 V MGTAVCC`** and **`1.2 V MGTAVTT`** linear/filtered supplies and a dedicated differential `125 MHz MGTREFCLK` — unnecessary when Bank 34 `LVDS_25` SelectIO already achieves `1.25 Gb/s` SGMII cleanly on **`XC7A50T-2FTG256I`**.

---

## 5. Verdict Table Across Operating Modes

| Mode / Hardware Config | Uplink (`A→K`) Capacity | Downlink / Control (`K→A`) | Redundancy & Failover Loss | PCB / BOM Impact | Recommendation |
|---|---|---|---|---|---|
| **1. `IAS1` Only (`Rev05` default)** | **`1.94 Gb/s`** (`1.0G`×2) / **`2.42 Gb/s`** (`1.25G`×2) | **`~0.49 Gb/s`** (`LINK_TX_D0`) + SPI if Pmod wired | None (single `J8` connector) | `C101, C102, C107, C108` fitted (`C1218–21` DNP) | **Best baseline** for pure raw radar/SDR streaming |
| **2. `Rev05` `ETH` Only (`LINK_RX_D1` static)** | **`~0.99 Gb/s`** (`9000 B` jumbo UDP) | **`~0.99 Gb/s`** UDP control (or Pmod cable `J2`) | None (single `RJ45` path) | Fit `C1218–21`, remove `C101..102, 107..108` | **Use for switch/network integration** (`DECIM≥4` radar + telemetry) |
| **3. `Rev05` Dual `IAS1 D1` + `ETH` (Load-Balanced)** | **`~1.94 Gb/s`** (`1.0G`+ETH) / **`~2.18 Gb/s`** (`1.25G`+ETH) | **`~0.99 Gb/s`** (`ETH` UDP) + optional Pmod `J2` / slow `LINK_TX_CLK` | **Active-backup or stream split:** survives either `J8 D1` or `RJ45` failure at `~0.95–1.19 Gb/s` degraded rate | Same `ETH` BOM; activate `LINK_RX_D1` (`~0.8%` 3D NEXT safe) | **Best `Rev05` multi-sensor mode** (Radar on `D1`, SDR+Ctrl on `ETH`) |
| **4. `Rev05` `1+1` Hitless Mirroring** | **`~0.95 Gb/s`** effective (duplicated on both) | **`~0.99 Gb/s`** (`ETH`) + `J2`/`LINK_TX_CLK` | **`0` packet loss** on instant fault via `seq_num` deduplication | Same `ETH` BOM | **Best for critical reliability** (`<= 0.95 Gb/s` streams) |
| **5. `Rev05` `100 Mb/s` Fallback (`-1` or noisy link)** | **`~1.05–1.29 Gb/s`** (`D1` + `100M` ETH) | `100 Mb/s` (`~11.8 MB/s`) UDP control | Survives `D1` fault with `100 Mb/s` degraded telemetry | Same `ETH` BOM (`10×` SGMII oversampling) | **Fallback** if `-1` silicon ever substitutes `-2` |
| **6. `Rev06` Dedicated Bank 34 ETH (`R2/R1`, `R3/T2`)** | **`~2.93–3.41 Gb/s`** (`2× IAS1` + `1G ETH`) | **`~0.49 Gb/s` `IAS1` + `~0.99 Gb/s` `ETH` (dual path)** | **Full `A→K` and `K→A` link-level + connector redundancy** (`0`-loss mirroring or `3+ Gb/s` split) | Future spin only: move `U1201` to free Bank 34 pins + `MDIO/MDC` on Bank 14/15; keep `FTG256-2` | **Recommended `Rev06` hardware improvement** |
