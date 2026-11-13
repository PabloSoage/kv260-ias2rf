# IAS1-to-RF Link Pin Map & Polarity Verification

**Scope:** End-to-end hardware signal trace from the RF/DAQ front-end Artix-7 (`U1101`, `XC7A50T-FTG256`) across the adapter PCB (`CSI2-KRIA-KV260_Rev01`), board-to-board connector (`J101`), KV260 carrier IAS1 connector (`J8`), carrier-side buffers/translators (`U18`, `U19`, `U72`), SOM connector (`SOM240_1`), to the Kria K26 SOM (`XCK26-SFVC784-2LV-C`), plus the two Pmod headers (`J2` on KV260 carrier and `J1102` on the adapter board).

**Result (Task 2a Check):** All five differential `LINK_*` pairs land **P-on-P and N-on-N** between Artix-7 and Kria K26. There is **no** polarity inversion on any differential pair and **no** pin/direction conflict on any of the four single-ended IAS1 signals (`HK_SCL`, `HK_SDA`, `FPGA_PROG_B`, `FPGA_IRQ`).

---

## Verification Legend & Primary Sources

Every table entry is tagged with its verification basis:
- **`[M]` Measured / Direct Inspection** from project schematics/PCB, Vivado part/board files, or AMD KV260 carrier schematic (`XTP682`).
- **`[I]` Inferred** (none required for the pin map tables below; every link row is `[M]`).

Primary sources inspected:
1. Adapter schematics & PCB: `rev03/CONTROL.kicad_sch`, `rev03/IAS_LINK.kicad_sch`, `CSI2-KRIA-KV260_Rev01.kicad_pcb`
2. Artix-7 package pins & delays: `_work/layout/xc7a50t_ftg256_pkg_delays.csv`, `_work/layout/lvds_skew.py`
3. KV260 carrier schematic: AMD `XTP682` (`KV260_v2/038-05058-03-A1.pdf`, sheets 6, 8, 13, 17)
4. Vivado Board Store & K26 package definitions (`Vivado 2026.1`):
   - `D:\AMDDesignTools\2026.1\Vivado\data\xhub\boards\XilinxBoardStore\boards\Xilinx\kv260_carrier\2.0\board.xml`
   - `D:\AMDDesignTools\2026.1\Vivado\data\xhub\boards\XilinxBoardStore\boards\Xilinx\kv260_som\2.0\part0_pins.xml`
   - `D:\AMDDesignTools\2026.1\Vivado\data\xhub\boards\XilinxBoardStore\boards\Xilinx\k26c\2.0\part0_pins.xml`
   - `D:\AMDDesignTools\2026.1\Vivado\data\parts\xilinx\zynquplus\public\ibis\pkg\xck26_sfvc784.pkg`

---

## 1. Five Differential `LINK_*` Pairs

All five pairs are AC-coupled with 100 nF capacitors (`C101`–`C110`) on the adapter PCB near `J101`.
- **Artix -> Kria pairs (`LINK_RX_*`):** Driven by Artix Bank 34 (`VCCO = 2.5 V`, `LVDS_25`), received by K26 Bank 66 HP (`VCCO = 1.2 V`, `PL_1V2`, AC-coupled `DIFF_SSTL12` with `ODT = RTT_48` and `EQUALIZATION` enabled per `link-decisions.md` #3).
- **Kria -> Artix pairs (`LINK_TX_*`):** Driven by K26 Bank 66 HP (`VCCO = 1.2 V`, `DIFF_SSTL12` with `OUTPUT_IMPEDANCE = RDRV_60_60`), received by Artix Bank 14 HR (`VCCO = 3.3 V`) as `LVDS_25` inputs **without** `DIFF_TERM` (`DIFF_TERM = FALSE`, external `100 ohm` differential termination `R105`, `R106` and `10k ohm` pull-ups to `+1V2` `R101`–`R104`, `Vcm = 1.2 V`).

> **Pin-ordering note on `J101` / `J8`:** On `LINK_RX_D1` (pins 29/30) and `LINK_TX_D0` (pins 26/27), the lower connector pin number carries `_N` (`29`, `26`) and the higher pin number carries `_P` (`30`, `27`) on **both** the adapter (`J101` in `CSI2-KRIA-KV260_Rev01.kicad_pcb`) and the KV260 carrier (`J8` in `XTP682` sh. 13). P still lands on P and N still lands on N.

| Signal | Dir | Artix `U1101` Ball & Function (Bank / CC) | Adapter Coupling / Term | `J101` Pin | KV260 `J8` Pin & Net (`XTP682` sh.13) | `SOM240_1` Pin (`XTP682` sh.6) | K26 `SFVC784` Ball & Function (Bank / CC) | P-on-P? | Basis |
| :--- | :---: | :--- | :--- | :---: | :--- | :---: | :--- | :---: | :---: |
| `LINK_RX_D0_P` | A->K | `L4` (`IO_L1P_T0_34`, Bk34, non-CC) | `C101` (100nF) -> `J_LINK_RX_D0_P` | `4` | `4` (`HPA06_P`) | `A3` | `A2` (`IO_L8P_T1L_N2_AD5P_66`, Bk66 HP, non-CC) | **Yes (P->P)** | `[M]` |
| `LINK_RX_D0_N` | A->K | `M4` (`IO_L1N_T0_34`, Bk34, non-CC) | `C102` (100nF) -> `J_LINK_RX_D0_N` | `5` | `5` (`HPA06_N`) | `A4` | `A1` (`IO_L8N_T1L_N3_AD5N_66`, Bk66 HP, non-CC) | **Yes (N->N)** | `[M]` |
| `LINK_RX_D1_P` | A->K | `M2` (`IO_L2P_T0_34`, Bk34, non-CC) | `C105` (100nF) -> `J_LINK_RX_D1_P` | `30` | `30` (`HPA07_P`) | `B7` | `B3` (`IO_L9P_T1L_N4_AD12P_66`, Bk66 HP, non-CC) | **Yes (P->P)** | `[M]` |
| `LINK_RX_D1_N` | A->K | `M1` (`IO_L2N_T0_34`, Bk34, non-CC) | `C106` (100nF) -> `J_LINK_RX_D1_N` | `29` | `29` (`HPA07_N`) | `B8` | `A3` (`IO_L9N_T1L_N5_AD12N_66`, Bk66 HP, non-CC) | **Yes (N->N)** | `[M]` |
| `LINK_RX_CLK_P` | A->K | `N3` (`IO_L3P_T0_DQS_34`, Bk34, DQS) | `C103` (100nF) -> `J_LINK_RX_CLK_P` | `7` | `7` (`HPA05_CC_P`) | `B1` | `C1` (`IO_L7P_T1L_N0_QBC_AD13P_66`, Bk66 HP, **`QBC`**) | **Yes (P->P)** | `[M]` |
| `LINK_RX_CLK_N` | A->K | `N2` (`IO_L3N_T0_DQS_34`, Bk34, DQS) | `C104` (100nF) -> `J_LINK_RX_CLK_N` | `8` | `8` (`HPA05_CC_N`) | `B2` | `B1` (`IO_L7N_T1L_N1_QBC_AD13N_66`, Bk66 HP, **`QBC`**) | **Yes (N->N)** | `[M]` |
| `LINK_TX_D0_P` | K->A | `M16` (`IO_L7P_T1_D09_14`, Bk14, non-CC) | `C107` (100nF), `R105=100R`, `R101=10k->+1V2` | `27` | `27` (`HPA08_P`) | `C9` | `B4` (`IO_L10P_T1U_N6_QBC_AD4P_66`, Bk66 HP, `QBC`) | **Yes (P->P)** | `[M]` |
| `LINK_TX_D0_N` | K->A | `N16` (`IO_L7N_T1_D10_14`, Bk14, non-CC) | `C108` (100nF), `R105=100R`, `R102=10k->+1V2` | `26` | `26` (`HPA08_N`) | `C10` | `A4` (`IO_L10N_T1U_N7_QBC_AD4N_66`, Bk66 HP, `QBC`) | **Yes (N->N)** | `[M]` |
| `LINK_TX_CLK_P` | K->A | `N13` (`IO_L11P_T1_SRCC_14`, Bk14, **`SRCC`**) | `C109` (100nF), `R106=100R`, `R103=10k->+1V2` | `10` | `10` (`HPA09_P`) | `D10` | `D4` (`IO_L11P_T1U_N8_GC_66`, Bk66 HP, **`GC`**) | **Yes (P->P)** | `[M]` |
| `LINK_TX_CLK_N` | K->A | `P13` (`IO_L11N_T1_SRCC_14`, Bk14, **`SRCC`**) | `C110` (100nF), `R106=100R`, `R104=10k->+1V2` | `11` | `11` (`HPA09_N`) | `D11` | `C4` (`IO_L11N_T1U_N9_GC_66`, Bk66 HP, **`GC`**) | **Yes (N->N)** | `[M]` |

### Clock-Capability Notes (`[M]`)
- **`LINK_RX_CLK_P/N` -> K26 `C1/B1` (`IO_L7P/N_T1L_N0/N1_QBC_AD13P/N_66`):** `QBC` (Quad-Byte Clock) in UltraScale+ Bank 66 HP. Although XTP682 labels the carrier net `HPA05_CC_P/N`, `C1/B1` is a `QBC` pin (`GC` pins in Bank 66 are `L11..L14`), which directly drives Bank 66 byte-clock routing (`BITSLICE` / `ISERDESE3` component-mode `CLK` via `BUFGCE`/`BUFGCE_DIV` or same-bank MMCM/PLL per UG572). `LINK_RX_D0` (`A2/A1` in `T1L_N2/N3`) and `LINK_RX_D1` (`B3/A3` in `T1L_N4/N5`) sit in the **exact same `T1L` lower nibble/byte group** as `LINK_RX_CLK`.
- **`LINK_TX_CLK_P/N` -> Artix `N13/P13` (`IO_L11P/N_T1_SRCC_14`):** `SRCC` (Single-Region Clock Capable) in Artix-7 Bank 14. Drives `BUFIO` + `BUFR` directly in Bank 14, and `LINK_TX_D0` (`M16/N16`, `IO_L7P/N_T1_14`) sits in the same `T1` byte group of Bank 14.

### Routed PCB & Package Delays (`[M]` / `[I]`)
Measured by `_work/layout/lvds_skew.py` on `CSI2-KRIA-KV260_Rev01.kicad_pcb` (with `_work/layout/xc7a50t_ftg256_pkg_delays.csv`), K26 SOM trace delays (`k26c/2.0/part0_pins.xml`), and KV260 carrier estimate (`kv260_carrier/2.0/board.xml` / `XTP682`):

| Pair | Adapter PCB + Artix Pkg P / N (ps) | K26 SOM Min–Max P / N (ps) | K26 SOM Mid P / N (ps) | KV260 Carrier `J8 <-> SOM240_1` (ps) | End-to-End Total P / N (ps) | Skew vs Ref Clock (ps) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| `LINK_RX_CLK` (`A->K`) | `678` / `677` (`[M]`) | `371.84–454.47` / `371.74–454.36` (`[M]`) | **`413` / `413`** (`[M]`) | `180` / `180` (`[I]`*) | **`1271` / `1270`** | Reference (`A->K`) |
| `LINK_RX_D0` (`A->K`) | `773` / `772` (`[M]`) | `365.49–446.71` / `365.46–446.68` (`[M]`) | **`406` / `406`** (`[M]`) | `180` / `180` (`[I]`*) | **`1359` / `1358`** | **`+88` ps** vs `LINK_RX_CLK` |
| `LINK_RX_D1` (`A->K`) | `717` / `717` (`[M]`) | `364.58–445.60` / `364.68–445.72` (`[M]`) | **`405` / `405`** (`[M]`) | `180` / `180` (`[I]`*) | **`1302` / `1302`** | **`+31` ps** vs `LINK_RX_CLK` (**`-57` ps** vs `D0`) |
| `LINK_TX_CLK` (`K->A`) | `661` / `665` (`[M]`) | `364.37–445.35` / `364.28–445.23` (`[M]`) | **`405` / `405`** (`[M]`) | `180` / `180` (`[I]`*) | **`1246` / `1250`** | Reference (`K->A`) |
| `LINK_TX_D0` (`K->A`) | `805` / `810` (`[M]`) | `366.85–448.37` / `366.99–448.55` (`[M]`) | **`408` / `408`** (`[M]`) | `180` / `180` (`[I]`*) | **`1393` / `1398`** | **`+147` / `+148` ps** vs `LINK_TX_CLK` |

*\*Carrier delay note (`[I]`): `kv260_carrier/2.0/board.xml` lists a uniform placeholder `typical_delay="5"` on every `connection_map` entry and `XTP682` does not publish per-net PCB trace lengths. The `J8 <-> SOM240_1` carrier flight time is modeled as `[I] 180 ps` common-mode (~27 mm length-matched MIPI CSI-2 stripline/microstrip with `< 5 ps` inter-pair skew).*

---

## 2. Four Single-Ended IAS1 Signals

All `J8`/`J101` single-ended I/Os operate at **`1.8 V`** (`+1V8_D` on adapter, `PL_1V8` on KV260 carrier). `U1101` Bank 35 is powered at `1.8 V`.

| Signal | Dir | Artix `U1101` Ball (Bank / Func) | Adapter Buffering / Passives | `J101` / `J8` Pin | KV260 Carrier Net & Active Path (`XTP682`) | `SOM240_1` Pin | K26 `SFVC784` Ball (Bank / Func / CC) | Basis |
| :--- | :---: | :--- | :--- | :---: | :--- | :---: | :--- | :---: |
| `HK_SCL` | Bi/OD | `K5` (`IO_25_35`, Bk35) | Shared w/ `U1105.6` (CAT24C02), `U1106` (TMP1075) | `14` | `IAS1_I2C_SCK` -> `U18` (`TCA9546A`, sh.8) ch1 `SC1` <-> `SCL` -> `HDA00_CC` | `D16` | `G11` (`IO_L5P_HDGC_45`, Bk45 HD, `HDGC`) | `[M]` |
| `HK_SDA` | Bi/OD | `J5` (`IO_L19P_T3_35`, Bk35) | Shared w/ `U1105.5` (CAT24C02), `U1106` (TMP1075) | `22` | `IAS1_I2C_SDA` -> `U18` (`TCA9546A`, sh.8) ch1 `SD1` <-> `SDA` -> `HDA01` | `D17` | `F10` (`IO_L5N_HDGC_45`, Bk45 HD, `HDGC`) | `[M]` |
| `FPGA_PROG_B` | K->A | `L9` (`PROGRAM_B_0`, Bk0) | `U1103` (`74LVC1G07` OD buffer: pin 2 `A` <- `/FPGA_PROG_B`, pin 4 `Y` -> `/CONTROL/PROGRAM_B`) | `21` | `IAS1_RESET_B` (pull-up to `PL_1V8`) <- `U19` (`SLG7XL46528`, sh.8) `PL_RESET_OUT2_B` <- `PL_RESET_IN2_B` <- `HDA04` | `B17` | `K13` (`IO_L2P_AD14P_45`, Bk45 HD) * | `[M]` |
| `FPGA_IRQ` | A->K | `H5` (`IO_L18P_T2_35`, Bk35) | `R1133 = 47k` pull-down to `GND` | `15` | `HPA13_FLASH` -> `U72` (`SN74AVC4T245`, sh.13) `2A1`(8, `1.8V`) -> `2B1`(13, `1.2V`) w/ `2DIR`(5)=`PL_1V8` (`A->B`) -> `HPA13_P` | `A12` | `G8` (`IO_L16P_T2U_N6_QBC_AD3P_66`, Bk66 HP, `QBC`) | `[M]` |

*\*Board Store note for `som240_1_b17` (`HDA04`):* `k26c/2.0/part0_pins.xml` maps `som240_1_b17` to K26 ball `K13` (and `b16->J10`, `b18->K12`), whereas `kv260_som/2.0/part0_pins.xml` has an off-by-one `loc` shift on `b16/b17/b18` (`b17` lists `loc="J10"` alongside `K13`'s trace delay `0.39667..0.48483 ns`). Always verify/override against the K26 SOM schematic (`K26` `XDC` from Vivado board preset `k26c` vs `kv260_som`) before carrier bring-up bitgen.

---

## 3. Pmod Headers (`J2` on KV260 Carrier, `J1102` on Adapter)

These two 12-pin Pmod headers are **independent** hardware ports (not wired to each other):
- **`J2` (KV260 Carrier, `XTP682` sh. 17):** Connected to Kria K26 Bank 45 HD (`3.3 V` via `PMOD_HDA*`).
- **`J1102` (Adapter Board, `rev03/CONTROL.kicad_sch` / `CSI2-KRIA-KV260_Rev01.kicad_pcb`):** Connected to Artix-7 Bank 15 (`3.3 V` HR) for radar SPI / PPS / strobe debug.

### 3a. KV260 Carrier Pmod `J2` -> Kria K26 (`[M]`)

| `J2` Pin | Carrier Net (`XTP682` sh.17) | `SOM240_1` Pin (`XTP682` sh.6) | K26 `SFVC784` Ball | K26 Function (Bank 45 HD) | Basis |
| :---: | :--- | :---: | :---: | :--- | :---: |
| `1` | `PMOD_HDA11` | `A17` | `H12` | `IO_L4N_AD12N_45` | `[M]` |
| `3` | `PMOD_HDA12` | `D20` | `E10` | `IO_L7P_HDGC_45` (`HDGC`) | `[M]` |
| `5` | `PMOD_HDA13` | `D21` | `D10` | `IO_L7N_HDGC_45` (`HDGC`) | `[M]` |
| `7` | `PMOD_HDA14` | `D22` | `C11` | `IO_L9P_AD11P_45` | `[M]` |
| `2` | `PMOD_HDA15` | `B20` | `B10` | `IO_L9N_AD11N_45` | `[M]` |
| `4` | `PMOD_HDA16_CC` | `B21` | `E12` | `IO_L8P_HDGC_45` (`HDGC`) | `[M]` |
| `6` | `PMOD_HDA17` | `B22` | `D11` | `IO_L8N_HDGC_45` (`HDGC`) | `[M]` |
| `8` | `PMOD_HDA18` | `C22` | `B11` | `IO_L10P_AD10P_45` | `[M]` |
| `9, 10` | `GND` | — | — | — | `[M]` |
| `11, 12` | `PMOD_3V3` | — | — | — | `[M]` |

### 3b. Adapter Pmod `J1102` -> Artix-7 `U1101` (`[M]`)

| `J1102` Pin | Adapter Net (`CONTROL`) | Artix `U1101` Ball | Artix Function (Bank 15, `3.3 V`) | Basis |
| :---: | :--- | :---: | :--- | :---: |
| `1` | `/CONTROL/PMOD_CS` | `H16` | `IO_L22P_T3_A17_15` | `[M]` |
| `2` | `/CONTROL/BEAM_STROBE` | `J16` | `IO_L23N_T3_FWE_B_15` | `[M]` |
| `3` | `/CONTROL/PMOD_MOSI` | `G16` | `IO_L22N_T3_A16_15` | `[M]` |
| `4` | `/CONTROL/PPS_SYNC` | `H14` | `IO_L24P_T3_RS1_15` | `[M]` |
| `5` | `/CONTROL/PMOD_MISO` | `J15` | `IO_L23P_T3_FOE_B_15` | `[M]` |
| `6` | `/CONTROL/PMOD_SPARE1` | `G15` | `IO_L24N_T3_RS0_15` | `[M]` |
| `7` | `/CONTROL/PMOD_SCLK` | `D13` | `IO_L12P_T1_MRCC_15` (`MRCC`) | `[M]` |
| `8` | `/CONTROL/PMOD_SPARE2` | `G11` | `IO_25_15` | `[M]` |
| `9, 10` | `GND` | — | — | `[M]` |
| `11, 12` | Unconnected (NC) | — | — | `[M]` |
