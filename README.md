# KV260-IAS2RF: an RF front-end carrier for the AMD Kria KV260

**Status (15 November 2026): schematic and layout complete, on 8 layers. The board is fully routed, with zero
DRC errors and zero schematic-parity problems. It has not been fabricated, and no hardware has
been validated.** The hardware, dual-FPGA Vivado gateware, Enclosure v2 cooling, and full-system co-simulation are complete ([Status](#status)).

> **Current `main` Hardware & Gateware Baseline:** **8-layer `JLC08161H-2116C`** RF front-end adapter PCB with dedicated-pin **1000BASE-T Ethernet (`U1201 RTL8211FSI`) + dual-lane `IAS1` (`~2.94 Gb/s` aggregate)**, failover in the dual-FPGA Vivado 2026.1 gateware ([docs/FPGA_GATEWARE.md](docs/FPGA_GATEWARE.md)), `5 V` header `J1002` for filtered Enclosure v2 active cooling ([ENCLOSURE.md](docs/ENCLOSURE.md)), and `0` KiCad DRC / parity errors. Historical design evolution from initial drafts is archived in [docs/history/README.md](docs/history/README.md) and tagged `rev01`–`rev06`.

![The board, 3D render](docs/img/board_iso.png)

**Explore it in 3-D:** [pablosoage.github.io/kv260-ias2rf](https://pablosoage.github.io/kv260-ias2rf/). Turn the board, the KV260 and the enclosure, open the case, hover a part to see what it is and what it does, and look at the board layer by layer.

An adapter board for the **AMD Kria KV260 Vision AI Starter Kit**. It plugs into the KV260's IAS1
camera connector and carries the converters, a common clock and a front-end FPGA. It serves two
signal chains:

- **Software-defined radio**: HF to 30 MHz directly; FM, airband, VHF/UHF amateur bands, PMR446 and ADS-B
  through the on-board VHF/UHF front end on its own SMA, 30 MHz to 3 GHz ([RX_VU_SPEC](docs/RX_VU_SPEC.md)).
  Receive, and transmit on the bands a licence covers.
- **Radar at 10.5 GHz**: the IF of the X-band chain from the open
  [AERIS-10 / PLFM_RADAR](https://github.com/NawfalMotii79/PLFM_RADAR) project, with ADAR1000
  beamforming. The 10.5 GHz chain itself is reused from AERIS-10, not redesigned here. The board
  is sized for 8 ADAR1000s (32 channels), so it covers both the Nexus variant (4 chips) and the
  Extended one (8 chips).

> ### The finding that shapes the whole project
>
> The **IAS0 (J7) connector on the KV260 does not reach the programmable logic**: its MIPI lanes
> run into an AP1302 ISP soldered on the carrier card. Only **IAS1 (J8)** is wired straight to
> the SOM. On top of that, **the KV260 has no 40-pin Raspberry Pi header** (J9 is a 15-pin
> camera connector), and **the GTH transceivers are not exposed**.
>
> The real I/O budget between a KV260 and an external board is **8 differential pairs and about
> 14 single-ended signals**. That is why the board has its own FPGA. The evidence and sources are
> in [docs/BLOCKERS_AND_RISKS.md](docs/BLOCKERS_AND_RISKS.md).

---

## The board at a glance

| | |
|---|---|
| Size | 119 × 132 mm, 140 × 132 with the RJ45's tab. It mounts on the KV260's IAS connectors and corner holes and overhangs to one side ([INTERFACE_SPEC §5.3](docs/INTERFACE_SPEC.md)) |
| Stackup | 8 layers, JLCPCB `JLC08161H-2116C`: `L1 SIG – L2 GND – L3 SIG – L4 PWR (split) – L5 GND – L6 SIG – L7 GND – L8 SIG` ([LAYOUT §3](docs/LAYOUT.md)) |
| Parts | 561 fitted, none DNP: 485 on the top face and 76 on the bottom (the Hirose connectors, the LVDS terminations and VCCINT caps under the FPGA, the switches' bias parts, the input protection) |
| Front-end FPGA | Xilinx XC7A50T-2FTG256I (the same part as AERIS-10) with a 128 Mb QSPI flash, plus JTAG |
| Radar ADC | AD9484, 8 bit, 400 MSPS, driven by two cascaded AD8352s |
| SDR ADC | AD9253, 14 bit, two channels at 62.5 MSPS (one LVDS lane each) |
| Radar DAC | AD9708, with reconstruction filter and balun |
| SDR DAC | AD9767, dual 14 bit, two output chains |
| Clock | Si549 programmable XO (400 or 500 MHz, GPS-disciplinable) into an ADCLK948 LVPECL fan-out |
| RF routing | Four M3SWA2-34DR+ SPDT switches and ten edge SMAs, plus two clock SMAs and the VHF/UHF antenna SMA `J961` on the back wall: thirteen in all. The HF ports J951 (receive, through an on-board 30 MHz 7th-order elliptic anti-alias filter) and J952 (transmit) have no switch in their path ([SIGNAL_INTEGRITY §9.9](docs/SIGNAL_INTEGRITY.md)) |
| Link to the Kria | IAS1 (Hirose BM20B), five LVDS pairs at up to 1 Gb/s each, AC-coupled; the Pmod J2 for control |
| Ethernet | Gigabit RJ45 through an RTL8211FSI SGMII PHY on its own FPGA pins, so it runs alongside IAS1 ([CONTROL_SPEC §8](docs/CONTROL_SPEC.md)) |
| To AERIS-10 | 2×20 IDC ribbon for eight ADAR1000s |
| Power | 12 V single power entry (`J1001` via `L1004` to adapter + `U1010`/`J1004` 3.0 A output to KV260 `J12`); buck and LDO tree for 5 V, 3.3 V, 2.5 V, 1.8 V and 1.0 V, plus -3.3 V for the switches ([POWER_SPEC §1.4](docs/POWER_SPEC.md), [BOARD_MANUAL §6](docs/BOARD_MANUAL.md#6-powering-the-kv260-together-with-the-board)) |

```mermaid
flowchart LR
  KV260["Kria KV260<br/>(K26 SOM)"] <-- "IAS1: 5 LVDS pairs<br/>Pmod: control" --> FPGA["XC7A50T<br/>front-end FPGA"]
  FPGA <-- LVDS --> ADCR["AD9484<br/>radar ADC"]
  FPGA <-- LVDS --> ADCS["AD9253<br/>SDR ADC"]
  FPGA --> DACR["AD9708<br/>radar DAC"]
  FPGA --> DACS["AD9767<br/>SDR DAC"]
  CLK["Si549 + ADCLK948<br/>clock"] --> ADCR & ADCS & DACR & DACS & FPGA
  ADCR & ADCS & DACR & DACS <--> RF["RF switches<br/>10 SMAs"]
  FPGA <-- "IDC ribbon" --> AERIS["AERIS-10<br/>8 × ADAR1000"]
  RF <--> AERIS
```

| Top | Bottom |
|---|---|
| ![Top](docs/img/board_top.png) | ![Bottom](docs/img/board_bottom.png) |

The renders come from KiCad. The shield frames' walls show only their pads; the debug USB-C `J1501` has a model
drawn from its maker's drawing, since no library has one ([3D_MODELS](docs/3D_MODELS.md)).

---

<!-- board-manual:start -->
## Board manual

Every connector, LED, switch and chip, numbered as in the drawing; the bottom side, the switches, the chips, troubleshooting and typical uses are in [docs/BOARD_MANUAL.md](docs/BOARD_MANUAL.md). Generated with the tables from the board file by `_work/manual/board_manual.py`.

![Board manual, top side](docs/img/manual/board_top.png)

| No. | Ref | Side | Name | What it is for |
|---|---|---|---|---|
| 1 | `J101` | bottom | BM20B(0.8)-34DP | IAS1 to the KV260 (its `J8`), underneath: five LVDS pairs at up to 1 Gb/s each (three data lanes, two clocks), the housekeeping I2C (temperature sensor, ID EEPROM) and the FPGA's interrupt. The board's only data link to the Kria |
| 2 | `J102` | bottom | BM20B(0.8)-34DP | IAS0 to the KV260 (its `J7`), underneath. Every pin is passed through to `J103`; the board uses none |
| 3 | `J103` | top | BM20B(0.8)-34DS-0.4V(51) | IAS0 pass-through receptacle on the tongue's top face, pin for pin with `J102`: an IAS camera module plugs in here as it would on the carrier |
| 4 | `J401` | top | CLK_REF_IN | Reference clock input (SMA) to the ADCLK948, 0.4-3.4 V p-p differential range, 50 ohm on chip. Leave open to run from the on-board Si549 |
| 5 | `J402` | top | CLK_OUT | Clock output (SMA), ADCLK948 Q3, LVPECL: to share the master clock with an instrument |
| 6 | `J911` | top | SDR_RX_A | SDR receive A (SMA): through SW1's default throw to the AD9253 channel A. Full scale about -2.4 dBm; DC-blocked |
| 7 | `J912` | top | AERIS_IF_A | Radar IF into the 14-bit AD9253 (SMA), through SW1's second throw |
| 8 | `J921` | top | AERIS_IF | Radar IF from AERIS-10 (SMA): through SW2's default throw to the 500 MSPS AD9484. Full scale about -17.6 dBm |
| 9 | `J922` | top | SDR_RX_WB | Wideband SDR receive (SMA), SW2's second throw. Not connected as built: `C926` is not fitted and the VHF/UHF front end takes the throw (`C927`); swap the two 0402s to use this port |
| 10 | `J931` | top | SDR_TX_A | SDR transmit A (SMA): AD9767 DAC1 through SW3's default throw, 10 mA full scale |
| 11 | `J932` | top | AERIS_TX_A | Radar chirp from the 14-bit AD9767 DAC1 (SMA), SW3's second throw |
| 12 | `J941` | top | AERIS_TX | Radar chirp to AERIS-10 (SMA): the AD9708 through SW4's default throw, 20 mA full scale into a 2:1 balun |
| 13 | `J942` | top | SDR_TX_WB | Wideband SDR transmit from the AD9708 (SMA), SW4's second throw |
| 14 | `J951` | top | SDR_RX_C | HF receive (SMA), no switch: a 30 MHz 7th-order elliptic low-pass, then the AD9253 channel B. Full scale about -3.0 dBm. The default HF input |
| 15 | `J952` | top | SDR_TX_C | HF transmit (SMA), no switch: AD9767 DAC2. The default HF output |
| 16 | `J961` | top | VU_ANT | VHF/UHF antenna (SMA, back wall): the Rev08 front end, direct 30-170 MHz and converted from 300 MHz to 3 GHz (170-300 MHz not covered: the converter's 300 MHz high-pass, AUDIT_Rev08 R1), into the AD9484 through SW2. Bias tee for an active antenna (off at power-up, 5 V or 3.3 V by `JP1301`, 125 mA limit; prefer 3.3 V where the antenna accepts it). Full scale -52 dBm at maximum gain, up to about +2 dBm with the attenuator and the LNA bypassed. No limiter: keep it away from a transmitter on the same vehicle (+25 dBm destroys the LNA) |
| 17 | `J1001` | top | 12V IN | 12 V input, barrel jack (CUI PJ-102AH, 5 A). Single power entry for both boards (`L1004` on both lines): feeds the adapter (11.7 W typical, 13.4 W / 1.12 A worst; `F1001` 2 A PTC, 18.3 V OVP) and the KV260 via `U1010`/`J1004` (3.0 A / 3.19 A max limit; 1.89 A typical, 4.12 A rated, 4.31 A worst combined). See POWER_SPEC section 1.4 and section 6 |
| 18 | `J1002` | top | FAN 5V | Enclosure fan, JST PH 2-pin: pin 1 +5 V (0.5 A PTC `F1002`), pin 2 GND |
| 19 | `J1004` | top | B2PS-VH | 12 V output to the KV260's `J12` (JST VH 2-pin right-angle, 10 A: pin 1 `+12V_KV`, pin 2 `GND`): protected by `U1010` (8.0 V UVLO, 14.4 V OVP, 3.0 A limit via `R1043` 6.04 kohm, -60 V reverse); see section 6 |
| 20 | `J1101` | top | JTAG 2x7 2mm | Xilinx JTAG for the XC7A50T and its flash (Platform Cable or any 2 mm 14-pin JTAG adapter) |
| 21 | `J1102` | top | Pmod | Pmod from the KV260's `J2` (cable): SPI to the FPGA's register file, beam strobe, PPS and the debug UART. Pin by pin below |
| 22 | `J1103` | top | AERIS ADAR | AERIS-10 beam-steering ribbon (2x20 IDC): the ADAR1000 SPI and its control lines |
| 23 | `J1201` | top | HR911130C | Gigabit Ethernet (RJ45, magnetics and LEDs inside), from the RTL8211FS over SGMII to the FPGA: the board standalone |
| 24 | `J1501` | top | TYPE-C-31-E-17 | Debug USB-C (vertical, on the tongue): the FPGA's console through a CH340X, 115,200 baud 8N1, powered from the cable. Lid off |
| 25 | `J1502` | top | FPC-1.0FX-15PWCR-H20 | GPS PPS and the vehicle CAN to the KV260's `J9` (Raspberry Pi camera connector) by a 100 mm 15-way 1 mm FFC, either cable type: the pulse reaches `J9` pin 12, a PL pin (`kria_pps`); CAN TX leaves on `J9` pin 6 and RX comes back on pin 8 (PS `CAN1`, R5F core 1) |
| 26 | `J1503` | top | BM06B-SRSS-TB | GPS receiver and vehicle CAN, JST-SH 6-pin, vertical, the plug from above: 1 GND, 2 CANL, 3 CANH, 4 GND, 5 PPS in (3.3 V), 6 +3.3 V out (0.2 A PTC) (no termination: it taps the car's bus) |

| No. | LED | Meaning when lit |
|---|---|---|
| 30 | `D1501` CFG green | FPGA configured and the clock sequencer finished |
| 30 | `D1502` CLK yellow | Master clock mode: on 500 MHz, off 400 MHz |
| 30 | `D1503` LINK green | IAS1 link to the Kria trained |
| 30 | `D1504` ADCR red | The radar ADC (AD9484) clipped since the last read (sticky) |
| 30 | `D1505` ADCS red | The SDR ADC (AD9253) clipped since the last read (sticky) |
| 30 | `D1506` LO green | The RFFC5072 synthesiser is locked |
| 30 | `D1507` TX red | A DAC is driving an SMA |
| 30 | `D1508` ERR red | Any sticky error: CRC, FIFO overflow, I2C no-acknowledge, over-temperature |
| 30 | `D1509` HB blue | Heartbeat: flickers with every line the FPGA prints on the debug UART, once a second |
| 31 | `D1520` +12V green | +12V present (after the input protection) |
| 31 | `D1521` +5V0 green | +5V0 present |
| 31 | `D1522` +3V3_D green | +3V3_D present |
| 31 | `D1523` +1V8_D green | +1V8_D present (switched from +3V3_D by `Q1520`) |
| 31 | `D1524` +1V0 green | +1V0 (FPGA core) present (switched from +3V3_D by `Q1521`) |
| 32 | `D1101` green | DONE: the FPGA has loaded a bitstream |
<!-- board-manual:end -->

---

## Schematics and layout

- **[Schematic, all 11 sheets including full wired overview (PDF)](docs/KV260-IAS2RF_schematic.pdf)** · [High-res SVGs & 4K PNGs](docs/img/highres/README.md#1-schematics-sch)
- **[Layout, all 8 copper layers + combined + transparent tracks (PDF)](docs/KV260-IAS2RF_layout.pdf)** · [Per-layer SVGs & 4K PNGs](docs/img/highres/README.md#2-8-layer-pcb-layout-layout)
- **[Complete Project Documentation Book (PDF)](docs/KV260-IAS2RF_Documentation.pdf)** (reproducible locally via [`export_documentation.py`](export_documentation.py))
- KiCad 10 sources: [`CSI2-KRIA-KV260_Rev01.kicad_pro`](CSI2-KRIA-KV260_Rev01.kicad_pro), the root
  schematic and [`rev03/`](rev03/) (nine hierarchical sheets), the 8-layer board
  [`CSI2-KRIA-KV260_Rev01.kicad_pcb`](CSI2-KRIA-KV260_Rev01.kicad_pcb), and custom libraries in
  [`symbols/`](symbols/) and [`footprints/`](footprints/). *(Root KiCad project filenames and `rev03/` directory names are preserved for tool/netlist continuity; see [docs/history/README.md](docs/history/README.md) for revision history.)*

| Sheet | Contents | Specification |
|---|---|---|
| [Full Circuit](docs/img/sch/ROOT.png) | Complete wired schematic overview & hierarchy (`FULL_CIRCUIT` + `ROOT`) | [ARCHITECTURE](ARCHITECTURE.md) |
| [IAS_LINK](docs/img/sch/IAS_LINK.png) | The Hirose connectors, AC coupling and terminations of the link | [IAS_LINK_SPEC](docs/IAS_LINK_SPEC.md) |
| [CLOCK](docs/img/sch/CLOCK.png) | Si549, reference select and LVPECL fan-out | [CLOCK_SPEC](docs/CLOCK_SPEC.md) |
| [ADC_RADAR](docs/img/sch/ADC_RADAR.png) | AD9484 and its two AD8352 drivers | [ADC_RADAR_SPEC](docs/ADC_RADAR_SPEC.md) |
| [ADC_SDR](docs/img/sch/ADC_SDR.png) | AD9253, two channels | [ADC_SDR_SPEC](docs/ADC_SDR_SPEC.md) |
| [DAC_RADAR](docs/img/sch/DAC_RADAR.png) | AD9708, filter and balun | [DAC_RADAR_SPEC](docs/DAC_RADAR_SPEC.md) |
| [DAC_SDR](docs/img/sch/DAC_SDR.png) | AD9767 in interleaved mode, two output chains | [DAC_SDR_SPEC](docs/DAC_SDR_SPEC.md) |
| [ROUTING](docs/img/sch/ROUTING.png) | Four RF switches and the SMAs | [ROUTING_SPEC](docs/ROUTING_SPEC.md) |
| [CONTROL](docs/img/sch/CONTROL.png) | The front-end FPGA: banks, configuration, Pmod, AERIS ribbon, housekeeping | [CONTROL_SPEC](docs/CONTROL_SPEC.md) |
| [POWER](docs/img/sch/POWER.png) | The power tree | [POWER_SPEC](docs/POWER_SPEC.md) |

![Full wired circuit overview (all sheets connected)](docs/img/sch/ROOT.png)

> *High-resolution vector PDF ([`FULL_CIRCUIT.pdf`](docs/img/highres/sch/FULL_CIRCUIT.pdf)) and 4K schematic PNGs are indexed in [docs/img/highres/README.md](docs/img/highres/README.md).*

---

## Status

| Check | Result |
|---|---|
| ERC | 0 errors; 7 warnings, all explained: configuration and XADC pins tied to power on purpose ([CONTROL_SPEC §5](docs/CONTROL_SPEC.md)) |
| DRC, zones refilled | **0 errors, 0 unrouted connections, 0 schematic-parity problems** on the 8-layer `JLC08161H-2116C` board (`local/kvpwr`, 785 BOM parts; checked by `make_fab.py`) |
| Signal and power integrity | Full-wave openEMS + ngspice verification ([SIGNAL_INTEGRITY.md](docs/SIGNAL_INTEGRITY.md)): SMA launch `S11 = -30.9 dB` at 1 GHz (`-13.7 dB` at 3 GHz) with ESD diode, LVDS eyes within `1–26 mV` of ideal except `LINK_RX_D0` (`-52 mV`), worst intra-pair skew `9 ps`, `VCCINT` impedance `41 / 63 mΩ` (`target 120 mΩ`), ESD protection on every SMA, Pmod and JTAG, GND via within `3 mm` of all `89` LVDS layer changes |
| Planes | L2, L5, and L7 carry solid ground; L4 carries split power islands (`_work/layout/planechk.py`) |
| Dual-FPGA Gateware & Vivado Timing | **Complete and routed in Vivado 2026.1** ([FPGA_GATEWARE.md](docs/FPGA_GATEWARE.md)): `artix_top` (`ENABLE_ETH=1`) uses `25,068` LUTs (`76.9%`), `28,881` FFs (`44.3%`), `18.0` BRAM36 (`24.0%`), `119` DSP48E1 (`99.2%`), `WNS = +0.076 ns` over every clock of both `CLK_FPGA` modes (`400` and `500 MHz`); `ias2rf_k26_bd` with the DSP suite, the GPS PPS block, the fusion grid and the KrakenSDR and HackRF Pro blocks uses `51,870` Slice LUTs (`44.3%`), `44,547` FFs (`19.0%`), `40` BRAM36 (`27.8%`), `229` DSP48E2 (`18.3%`), `WNS = +1.125 ns`; end-to-end XSim (`tb_system`) `S1..S6 PASS` |
| Final RF review (15 Nov) | Five limits found ([SIGNAL_INTEGRITY §9.8](docs/SIGNAL_INTEGRITY.md)) and addressed ([§9.9](docs/SIGNAL_INTEGRITY.md)): a 30 MHz 7th-order anti-alias filter on the HF input J951 (≥ 60 dB from 50 MHz); the switch-free J951/J952 as the default HF ports; DAC clocks from `CLK_FPGA` ÷ 4 without an MMCM (clock uncertainty `0.165 → 0.035 ns`); no transmit copper within 1.5 mm of any receive line; the enclosure's honest rating below. Still to measure on the first board: TX→RX isolation, the RF switches at 1–5 MHz, the filter above 700 MHz, switcher spurs |
| Rev08 front end and diagnostics (16–17 Nov) | VHF/UHF receive on `J961`, 30 MHz to 3 GHz: noise figure 2.0 dB and full scale −52 dBm at maximum gain in the direct VHF path, FM-reject ≥ 40 dB with real tolerances; `J961` launch `S11 ≤ −18.1 dB` to 1.1 GHz with its ESD diode and bias tee; no front-end copper within 1.5 mm of either ADC input or the clock tree ([REV08_PLAN §5.5, §11.7](docs/REV08_PLAN.md), [SIGNAL_INTEGRITY §9.10](docs/SIGNAL_INTEGRITY.md)). 14 status and rail LEDs, a USB-C debug console, the IAS0 camera pass-through, and the [board manual](docs/BOARD_MANUAL.md) |
| Mechanical fit | Registered on AMD's 3D model of the KV260: mounting holes land within `5 µm` ([INTERFACE_SPEC §5.3](docs/INTERFACE_SPEC.md)) |

**Design & verification highlights** ([docs/LAYOUT.md](docs/LAYOUT.md), [docs/SIGNAL_INTEGRITY.md](docs/SIGNAL_INTEGRITY.md)):

1. **Power & analog isolation.** Supply trunks widened (`865 mm` at `>= 0.5 mm`); `+1V8_A` trimmed to `1.85 V`; DAC1/DAC2 filters colocated under their baluns (`T801`/`T802`), dropping balun common mode by `9–21 dB` (DAC2) and `1–6 dB` (DAC1); `FB401` upgraded to a `2 A / <= 0.1 Ω` bead (`48 mV` drop max, `0.1–0.4 mVpp` ripple on the clock tree).
2. **Differential pairs & LVDS routing.** Nine of 19 data/link pairs plus `CLK_ADCS` and `CLK_FPGA` run coupled `100 Ω` end-to-end on L1/L3/L6; the remaining pairs use `50 Ω` legs matched to `<= 9 ps` worst-case intra-pair skew with on-pad `100 Ω` terminations.
3. **ADCR data to DCO skew (`-90 to +5 ps`).** `ADCR_DCO` legs are swapped cleanly at the Artix-7 BGA (`N14 = DCO_N`, `P14 = DCO_P`); `adc_capture.v` compensates with `ISERDESE2` inversion + per-bit `IDELAYE2` calibration.
4. **8-layer `JLC08161H-2116C` fabrication stack.** Controlled impedances verified against JLCPCB's solver ([FABRICATION.md](docs/FABRICATION.md)); 5 bare boards quoted at `$287.96` (`140 × 132 mm` with Ethernet tab).
5. **Kria IAS1 I/O standard.** `DIFF_SSTL12` with `RTT_48` on-die split termination (`~96 Ω` to `0.6 V`) and `RDRV_60_60` driver ([INTERFACE_SPEC §6.3](docs/INTERFACE_SPEC.md)); `2 Gb/s` uplink (`2` pairs) + `1 Gb/s` downlink (`1` pair), `1.25 Gb/s` per lane silicon headroom.
6. **3-D full-wave EM, RF cascade & thermal envelope.** openEMS 3-D sub-models cover L1–L6 vias (`S11 < -29 dB`), BGA escapes (`< -24 dB`), adjacent-pair NEXT (`1.9%`), and `J101` launch (`< -25 dB`). Receive cascades (`cascade.py`) give `NF = 26.8 dB` (radar) / `22 dB` (SDR). Enclosure v2 (`50 × 50 × 15 mm` filtered lid fan + `HS1`–`HS3` heatsinks) is rated for `56 °C` ambient with the stock KV260, whose commercial K26 is the limit (`Tj` `85 °C`), and `70 °C` with an industrial K26I SOM, unchanged by Rev08's front end and camera ([ENCLOSURE_V2_THERMAL.md §8](docs/ENCLOSURE_V2_THERMAL.md)).
7. **Dual-FPGA Vivado 2026.1 gateware & XSim verification.** Full RTL, constraints, Vivado post-route floorplans/schematics, and XSim end-to-end testbenches live in `fpga/` ([docs/FPGA_GATEWARE.md](docs/FPGA_GATEWARE.md)). *(Design evolution history is archived in [docs/history/README.md](docs/history/README.md).)*

**Estimated cost** ([docs/JLCPCB_QUOTE.md](docs/JLCPCB_QUOTE.md)): about **$2,443 for two assembled boards** and **$4,785 for five** (19 Nov, single power entry + RJ45 shield RC; parts + assembly + `JLC08161H-2116C` bare boards).

---

## Documentation

| Document | Contents |
|---|---|
| **[docs/BOARD_MANUAL.md](docs/BOARD_MANUAL.md)** | **Board manual.** Every connector, LED, switch, jumper, test point and chip, with drawings of both sides, the Pmod pin-out, troubleshooting by LED and typical uses |
| **[docs/VEHICLE_PLATFORM.md](docs/VEHICLE_PLATFORM.md)** | **System view.** Complete vehicle platform: LiDAR, SDR, radar, OBD2 |
| [docs/FPGA_GATEWARE.md](docs/FPGA_GATEWARE.md) | **Dual-FPGA Gateware.** Artix-7 + Kria K26 RTL, Vivado 2026.1 utilization/timing/floorplans/schematics, CSR map, wideband SDR & AERIS-10 radar DSP, and XSim e2e simulation |
| [docs/HMI.md](docs/HMI.md) | **In-car HMI.** The ten touchscreen screens, a Slint application in Rust that runs on the KV260 (Linux KMS), a PC or a phone's browser, its data service and the PL's result streams behind it, and which job runs on the PL, the A53s, the R5F cores, the GPU and the VCU |
| [docs/INTEGRATIONS.md](docs/INTEGRATIONS.md) | **Possible integrations.** USB GPS, a 77 GHz radar over CAN, engine live data through opendash (measured against an emulated ECU), a 3D LiDAR, their behaviour in fog, and `kria_bev_grid`, a fusion occupancy grid for the PL |
| [docs/KV260-IAS2RF_Documentation.pdf](docs/KV260-IAS2RF_Documentation.pdf) | **Unified Offline Book.** Combined project manual with vector Vivado floorplans, 11-sheet schematic, 10-sheet 8-layer layout, 4K renders, and simulations (generated via [`export_documentation.py`](export_documentation.py)) |
| [docs/SHOPPING_LIST.md](docs/SHOPPING_LIST.md) | Parts and checklist per stage, with indicative costs |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Master system architecture and BOM |
| [docs/BLOCKERS_AND_RISKS.md](docs/BLOCKERS_AND_RISKS.md) | Engineering blockers closed, with evidence and sources, plus open risks |
| [docs/INTERFACE_SPEC.md](docs/INTERFACE_SPEC.md) | Pin map for J8 and the Pmod, mechanical envelope, adapter registration on KV260 |
| [docs/POWER_AND_STACKUP.md](docs/POWER_AND_STACKUP.md) | Per-rail current budget and impedance solver foundations (see [LAYOUT §3](docs/LAYOUT.md) for final 8-layer stack) |
| [docs/SYMBOLS.md](docs/SYMBOLS.md) | Custom KiCad symbols cross-checked against datasheets and second sources |
| Sheet specifications | One per schematic sheet, in the table above |
| [docs/LAYOUT.md](docs/LAYOUT.md) | Outline, 8-layer stackup (`JLC08161H-2116C`), design rules, split power layer, placement, routing, and LVDS review |
| [docs/SIGNAL_INTEGRITY.md](docs/SIGNAL_INTEGRITY.md) | Full-wave openEMS & ngspice verification: impedance, SMA launch, LVDS eyes, PDN impedance and DC drop, crosstalk, return vias, DAC filters, RF cascade, and 2-D thermal map (`docs/sim/`) |
| [docs/ENCLOSURE.md](docs/ENCLOSURE.md) & [docs/ENCLOSURE_V2_THERMAL.md](docs/ENCLOSURE_V2_THERMAL.md) | Enclosure v2 CAD, CalculiX 3-D shock/vibration FEA, 3-D CFD cooling, and `HS1`–`HS5` heatsink sizing |
| [docs/FABRICATION.md](docs/FABRICATION.md) | JLCPCB ordering instructions, stackup verification, and output script (`_work/fab/make_fab.py`) |
| [docs/JLCPCB_QUOTE.md](docs/JLCPCB_QUOTE.md) | Itemized JLCPCB board, assembly, and LCSC BOM pricing |
| [docs/img/highres/README.md](docs/img/highres/README.md) | Index of all 4K PNG renders and lossless SVG/PDF vector schematics, layouts, heatsinks, and Vivado FPGA views |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Staged development plan and exit criteria |
| [docs/history/README.md](docs/history/README.md) | **Revision Archive.** Preserved engineering audit notes and stack/revision milestones (`rev01`–`rev06`) |

---

## Repository layout

| Path | Contents |
|---|---|
| `CSI2-KRIA-KV260_Rev01.*`, `rev03/` | KiCad 10 hardware source project (root + nine schematic sheets + 8-layer PCB) |
| `fpga/` | Synthesizable Verilog gateware (`artix/`, `kria/`, `link/`, `eth/`), Vivado constraints/build scripts, and full-system XSim co-simulation ([`fpga/README.md`](fpga/README.md)) |
| `sw/` | Linux PS software & control utilities |
| `symbols/`, `footprints/`, `mech/` | Custom KiCad libraries, 3-D models, and Enclosure v2 STL files |
| `docs/` | Specifications, layout/SI/thermal/gateware documentation, renders, vector PDFs, and [`docs/history/`](docs/history/README.md) |
| `export_documentation.py` | Standalone Python script to build the offline `docs/KV260-IAS2RF_Documentation.pdf` compendium |
| `_work/` | Reproducible automation scripts (symbol/sheet generators, `build_board.py`, field solvers, openEMS/ngspice/CFD/FEA, Vivado floorplan exporters) |
| `fab/` | Not tracked. `python _work/fab/make_fab.py` writes Gerbers, drill, BOM, and CPL for JLCPCB |
| `PCB/`, `Documents/` | Original Allied Vision reference sources |

Reproducing hardware checks, Vivado gateware, and offline PDF documentation:

```bash
kicad-cli sch erc --severity-all CSI2-KRIA-KV260_Rev01.kicad_sch
kicad-cli pcb drc --schematic-parity --refill-zones --severity-all CSI2-KRIA-KV260_Rev01.kicad_pcb
python _work/fab/make_fab.py                                      # fab/: Gerbers, drill, BOM, CPL
python _work/layout/lvds_skew.py CSI2-KRIA-KV260_Rev01.kicad_pcb  # LVDS delays, skew and stubs
python export_documentation.py                                    # docs/KV260-IAS2RF_Documentation.pdf
```

---

## Related work

The DSP core this board will need already exists, runs on real silicon and is published
separately:

**[scanner64](https://github.com/PabloSoage/scanner64)**: a real-time multichannel DDC bank for
the KV260's PL. Measured on the board: 100.05 MSPS sustained, no samples dropped across
200 million, bit-exact against its Python model, 8.38 mW per channel, 169.9 MHz Fmax post-route.

That project answers, with hardware, the question this board is built around: whether the PL can
sustain a converter stream in real time. It can.

---

## Where the project came from, and attribution

This is a **fork** of the open hardware design
[Allied Vision Adapter Board CSI-2 for Kria KV260](https://github.com/alliedvision), published
under the MIT licence (see [LICENSE](LICENSE)). What is kept from that design:

- the board's mechanical fit to the KV260 (the outline was extended)
- the two Hirose BM20B(0.8)-34DP connectors (IAS0 / IAS1) and their wiring to the SOM

Everything else (the MIPI camera electronics, level shifters, USB power) was removed and replaced
by the RF chain described here. **This repository no longer produces an Allied Vision camera
adapter board.** If that is what you want, use the original project.

---

## Dual-FPGA Gateware, Silicon Floorplan & Vivado Circuit Schematics

Both FPGAs carry complete, post-route verified Vivado 2026.1 gateware and end-to-end mixed-signal/digital XSim co-simulation ([`fpga/`](fpga/), full specification in [docs/FPGA_GATEWARE.md](docs/FPGA_GATEWARE.md)):

- **Wideband SDR (Front-End Artix-7):** Dual 14-bit `62.5 MSPS` ADC channels (`AD9253`) feeding a direct HF/CB bypass path (`stream_id = 8'h03`; first Nyquist zone `0–31.25 MHz` at `62.5 MSPS`, `0–25 MHz` at `50 MSPS`, and `0–30 MHz` on `J951` behind its low-pass) plus a tunable NCO + CIC + FIR DDC (`stream_id = 8'h02`); `VHF`, `FM`, walkie-talkie (`PMR446` / `GMRS`), `UHF` and ADS-B come from the Rev08 front end on `J961` into the AD9484 (radar ADC) path through SW2, not into this one; paired with the `14-bit 125 MSPS` `AD9767` TX DAC (`DAC_SDR`).
- **AERIS-10 X-Band Radar (`10.5 GHz` / `20 km` / `8× ADAR1000`):** `400 MSPS` `AD9484` IF capture into the verbatim `AERIS-10 / PLFM_RADAR` (`62d4c55`) 400 -> 100 MSPS I/Q DDC (`stream_id = 8'h01`), `AD9708` chirp DAC (`DAC_RADAR`), `ADF4382` LO + `8× ADAR1000` beamformer SPI controller (`u_adar_ctrl`), and `u_rf_switch` T/R sequencing.
- **High-Speed Interconnect:** Dual-lane Clause-49 `64B/66B` `IAS1` LVDS (`1.0–1.25 Gb/s` per lane, `2.0–2.5 Gb/s` uplink + `0.5–1.0 Gb/s` downlink) plus dedicated-pin `1000BASE-T` SGMII/UDP over `U1201 RTL8211FSI` (`~2.94 Gb/s` combined).

| Target FPGA (`Vivado 2026.1`) | Slice LUTs | Flip-Flops | BRAM36 eq. | DSP48 | Timing (`WNS` / `WHS`) |
|---|---|---|---|---|---|
| **`artix_top` (`XC7A50T-FTG256-2`, `ENABLE_ETH=1`)** | `17,450 / 32,600` (`53.5%`) | `19,029 / 65,200` (`29.2%`) | `16.0 / 75` (`21.3%`) | `110 / 120` (`91.7%`) | **`+0.071 ns` / `+0.014 ns`** (all clocks of both `CLK_FPGA` modes; AD9484 domain at `400 MSPS` only) |
| **`ias2rf_k26_bd_wrapper` (`XCK26-SFVC784-2LV-c`)** | `11,038 / 117,120` (`9.4%`) | `18,210 / 234,240` (`7.8%`) | `3.0 / 144` (`2.1%`) | `0 / 1,248` | **`+0.814 ns` / `+0.011 ns`** |

| Artix-7 Silicon Die Floorplan (`XC7A50T`) | Artix-7 Post-Route Vivado Circuit Schematic |
|---|---|
| ![Artix-7 Silicon Floorplan](docs/img/fpga/artix7_silicon_floorplan.png) | ![Artix-7 Vivado Schematic](docs/img/fpga/artix7_vivado_schematic.png) |
| **Kria K26 Silicon Die Floorplan (`XCK26`)** | **Kria K26 PS+PL Block Design Schematic** |
| ![Kria K26 Silicon Floorplan](docs/img/fpga/kria_k26_silicon_floorplan.png) | ![Kria K26 Vivado BD Schematic](docs/img/fpga/kria_k26_vivado_bd_schematic.png) |

![Dual-FPGA Radar & Wideband SDR Signal-Chain Schematic](docs/img/fpga/dsp_radar_sdr_pipeline_schematic.png)

*(Lossless vector PDF/SVG and 4K PNGs of all Vivado floorplans and schematics live in [`docs/img/highres/fpga/`](docs/img/highres/README.md#3-vivado-20261-fpga-silicon-floorplans--schematics-fpga).)*

---

## Receiver, transmitter and radar simulations (G-8)

Every use of the board is simulated with realistic signals through the real RTL: the ADC model, the Artix DDC, the board's LVDS channel model, the IAS1 link and the Kria's DSP. Each result is compared with a floating-point reference fed the same input, and each case includes a deliberate fault (a mutation) that its checks must catch. All eight cases pass ([docs/FPGA_GATEWARE.md §6.1](docs/FPGA_GATEWARE.md); `python fpga/sim/signals/g8_suite.py`). Levels are at the antenna connector.

![G-8 sensitivity of every receive mode](docs/img/sim/g8_overview.png)

| Case | Path | Result (RTL, with the reference in brackets) |
|---|---|---|
| HF AM, 7.2 MHz | AD9253, `sdr_ddc`, AM | 10 dB SINAD at -104.4 dBm (-104.3); a +40 dB signal 9 kHz away costs 2.0 dB |
| HF SSB, 14.2 MHz USB | AD9253, `sdr_ddc`, USB | 10 dB SINAD at -118.5 dBm (-118.2); opposite sideband 56.4 dB down |
| VHF FM broadcast, 98.1 MHz | AD9484, AERIS DDC, WBFM | 30 dB SINAD at -108.9 dBm (-110.2); stereo separation 32.6 dB; RDS without errors from -105 dBm |
| VHF airband AM, 121.5 MHz | AD9484, AERIS DDC, AM | 10 dB SINAD at -114.3 dBm (-114.1); 8.33 kHz neighbours cost 0.1 dB at most |
| UHF PMR446 NBFM, 446 MHz | Converter, AD9484, NBFM | 12 dB SINAD at -122.5 dBm (-122.8); CTCSS detected at that level |
| ADS-B, 1090 MHz | Converter, AD9484, `kria_adsb_rx` | 90 % of frames decoded at -86.4 dBm (-89.0); 3 of 3 overlapping replies decoded |
| Radar, FMCW | AD9484, `kria_radar_proc` | Pd 0.5 at -18.8 dB per sample (model -18.7); Pfa 1.99e-2 (2.00e-2); beam scan finds the target at -15 degrees |
| Transmit | `kria_tx_mod`, link, AD9767 | AM and NBFM SINAD 83 and 58 dB; adjacent channel -80 and -66 dBc; USB opposite sideband 49.9 dB down |

| | |
|---|---|
| ![HF AM](docs/img/sim/g8_hf_am.png) | ![HF SSB](docs/img/sim/g8_hf_ssb.png) |
| ![FM broadcast](docs/img/sim/g8_fm_broadcast.png) | ![Airband AM](docs/img/sim/g8_airband_am.png) |
| ![PMR446 NBFM](docs/img/sim/g8_vhf_uhf_nbfm.png) | ![ADS-B](docs/img/sim/g8_adsb_1090.png) |
| ![Radar range-Doppler and CFAR](docs/img/sim/g8_radar_rd_cfar.png) | ![Transmit spectra and masks](docs/img/sim/g8_tx_masks.png) |

## In-car screens

The touchscreen application ([docs/HMI.md](docs/HMI.md)) is written in Rust and Slint and runs on the KV260, a PC or a phone's browser. These images are drawn by the application itself, from the data its service decodes out of the simulated board's DMA blocks.

| | |
|---|---|
| ![Home screen](docs/img/hmi/hmi_home.png) | ![Spectrum screen](docs/img/hmi/hmi_spectrum.png) |
| ![Radar screen](docs/img/hmi/hmi_radar.png) | ![ADS-B screen](docs/img/hmi/hmi_adsb.png) |

## Simulation results (8-layer JLC08161H-2116C)

All electromagnetic, transient SPICE, thermal, and power integrity checks are run on the routed **8-layer `JLC08161H-2116C`** board ([docs/SIGNAL_INTEGRITY.md](docs/SIGNAL_INTEGRITY.md); vector plots in [`docs/img/highres/sim/`](docs/img/highres/README.md#5-signal--power-integrity-vector-plots-sim); historical comparisons archived in [`docs/history/`](docs/history/README.md)).

| Check | 8-Layer `JLC08161H-2116C` Result |
|---|---|
| DRC / schematic parity | `0` violations, `0` unrouted connections, `0` parity mismatches |
| Differential coupling (`L1` / `L3` / `L6`) | `9` of `19` data/link pairs + `CLK_ADCS` & `CLK_FPGA` coupled `100 Ω` end-to-end |
| Worst intra-pair `\|P−N\|` skew (with package delay) | **`9 ps`** |
| Eye lost to routing vs. ideal (`20` pairs, `1 Gb/s` PRBS7) | mean **`-8 mV`**, worst **`-52 mV`** |
| Zero-crossing spread added by routing | mean **`1 ps`**, worst **`10 ps`** |
| Layer changes without a GND via within `3 mm` | **`0 of 89`** |
| Parallel adjacent-pair legs within `0.25 mm` | `65.8 mm` (`3D NEXT <= 1.9%`) |
| `ADCR` data minus `DCO` skew | `-90 ... +5 ps` (absorbed by per-bit `IDELAYE2`) |
| `VCCINT` PDN impedance (`target 120 mΩ`) | `41 mΩ` in-band max, `63 mΩ` at `100 MHz` |
| DC drop on `+2V5` at `601 mA` | `122–129 mV` |
| Edge SMA launch `S11` (openEMS, with ESD diode) | **`-30.9 dB` at `1 GHz`**, **`-13.7 dB` at `3 GHz`** |

**LVDS & SGMII eyes** (`ngspice`, PRBS7 at `1.0–1.25 Gb/s`, real routed copper sections vs. ideal `100 Ω` line):

| Pair | Ideal line | 8-layer routed (`eye / jitter`) |
|---|---|---|
| `LINK_RX_D1` | `385 mV, 41 ps` | **`372 mV, 51 ps`** |
| `LINK_RX_D0` | `509 mV, 25 ps` | **`457 mV, 31 ps`** |
| `LINK_RX_CLK` | `395 mV, 10 ps` | **`392 mV, 10 ps`** |
| `ADCS_FCO` | `628 mV, 17 ps` | **`617 mV, 17 ps`** |
| `ADCR_DCO` | `609 mV, 17 ps` | **`610 mV, 18 ps`** |
| `ETH_SGTX` (`1.25 Gb/s`) | n/a | **`> 350 mV` open** ([`eye_ETH_SGTX_1P25G.png`](docs/sim/eye_ETH_SGTX_1P25G.png)) |
| `ETH_SGRX` (`1.25 Gb/s`) | n/a | **`> 600 mV` open** ([`eye_ETH_SGRX_1P25G.png`](docs/sim/eye_ETH_SGRX_1P25G.png)) |

![Folded 8-layer LVDS eyes](docs/sim/eyes_1g.png)

![Eye openings and spread across all pairs](docs/sim/eye_openings.png)

![Intra-pair skew](docs/sim/lvds_skew.png)

![PDN impedance](docs/sim/pdn_impedance.png)

![Edge SMA launch S11](docs/sim/sma_launch.png)

![DAC reconstruction filters](docs/sim/dac_filters.png)

![Clock ferrite filter FB401](docs/sim/fb401_filter.png)

![2-D PCB thermal map (8.2 W in still air)](docs/sim/board_thermal.png)

![Five cooling configurations compared](docs/sim/board_cooling.png)

![3-D LVDS via transition](docs/sim/via_layer_change.png)

![3-D openEMS full-wave sub-models](docs/sim/em_3d_submodels.png)

---

## Mounted on the KV260

A printed base holds the KV260 and the adapter together: posts in place of the carrier's rubber feet,
posts under the overhang, a wall that takes the SMA cables' torque, and a pedestal and strap that
carry the Ethernet tab ([MECHANICAL](docs/MECHANICAL.md); STLs in `mech/`). Rendered in Blender
(Cycles) with AMD's KV260 model.

![The KV260 and the adapter on the printed base](docs/img/mount_iso.jpg)

| The RJ45 tab, pedestal and strap | The SMA wall |
|---|---|
| ![RJ45](docs/img/mount_rj45.jpg) | ![SMA wall](docs/img/mount_sma.jpg) |

![From the other side](docs/img/mount_iso_back.jpg)

---

## Heatsink Placement, Mechanical Envelope & Thermal Cooling (`Enclosure v2`)

The closed field enclosure (**Enclosure v2**, PETG-CF / ASA / PAHT-CF with optional TPU 95A drop bumpers; [ENCLOSURE.md](docs/ENCLOSURE.md), [ENCLOSURE_V2_THERMAL.md](docs/ENCLOSURE_V2_THERMAL.md)) integrates a `50 × 50 × 15 mm` filtered intake fan (Orion OD5015-05HB, `0.13 A`) on `J1002` directly above the RF/clock hot strip and specifies five mechanically decoupled heatsinks (`HS1`–`HS5`) with verified structural clearances:

| Heatsink | Target Component | Dimensions (`L × W × H`) | Assembly centre (`X, Y`, case frame) | Vertical Envelope & Clearance |
|---|---|---|---|---|
| **`HS1`** | `U501` (`AD9484` 400 MSPS ADC) | **`14 × 14 × 8.5 mm`** (black anodized Al, `0.18 mm` TIM) | `(-51.8, +10.55) mm` | Fin top `11.8 mm` (`1.9 mm` below the fan at `z = 13.75 mm`) |
| **`HS2`** | `U401` (`ADCLK948` LVPECL fan-out) | **`9 × 7 × 8 mm`** (blue anodized Al, `-1.0 mm` Y shift) | `(-34.9, -1.20) mm` | Fin top `11.2 mm` (`y_max = +2.3 mm`) |
| **`HS3`** | `Y401` (`Si549` Programmable XO) | **`9 × 7 × 8 mm`** (blue anodized Al, `+1.0 mm` Y shift) | `(-35.0, +9.80) mm` | Fin top `12.0 mm`, `1.8 mm` under the fan (`y_min = +6.3 mm` -> **`4.0 mm` thermal air gap** to `HS2`) |
| **`HS4`** | `U1101` (`XC7A50T` Artix-7, **fit it in a vehicle**) | **`14 × 14 × 5 mm`** (low-profile Cu/Al) | `(-42.75, +40.0) mm` | Fin top `~9.0 mm` (with Vivado's FPGA power the CFD gives `102.1 °C` at `70 °C` ambient without it, `93.4 °C` with it; limit `100 °C`: AUDIT_Rev08 P6) |
| **`HS5`** | `K26 SOM` (`XCK26` OEM cooler) | **`68 × 58 × 18 mm` + `54 mm` fan** | `(+86.1, +47.0) mm` | Fin top `~25.1 mm` (`7.6 mm` to Enclosure v2 roof honeycomb vent) |

![Annotated 4K heatsink placement over KV260 + IAS2RF assembly](docs/img/board_heatsinks.jpg)

![Mechanical heatsink keep-out & clearance drawing](docs/img/heatsink_mechanical_map.png)

### Enclosure v2: Filtered Active Cooling & 3-D FEA

With `HS1`–`HS4` plus the `50 × 50 × 15 mm` lid fan (`J1002`) pressurising the housing (`7.5 CFM`, `+5.2 Pa`) and exhausting through 17 right-wall and 9 back-wall slots, the fine-mesh 3-D CFD of the enclosure with the Rev08 board, Vivado FPGA power (`1.25 / 1.60 W` upper bound) and audited regulator losses rates it for **`56.1 °C` ambient with the stock KV260** (whose commercial K26 reaches its `85 °C` junction limit there; UG1090), **`63.3 °C` by the adapter's own `TA = 85 °C` parts** (`U401` board temperature), and **`70.9 °C` with an industrial K26I SOM when `HS4` is fitted** (`68.0 °C` without `HS4`, because `XC7A50T` reaches `102.08 °C` of `100 °C` at `70 °C` vs. **`93.38 °C` clean / `94.24 °C` clogged with `HS4`**; `K26I` itself stays `99.21 °C`). At `70 °C` with `HS4` fitted the adapter's hottest junctions are the `LMR33630` at `117.71 °C` (of `125 °C`), `U1006` (`+1V8_D` LDO) at `111.09 °C` (of `125 °C`), the `ADCLK948` at `98.13 °C` (`Tb = 91.87 °C`), the `XC7A50T` at `93.38 °C` (of `100 °C`), and the `RFFC5072` at `91.37 °C` ([ENCLOSURE §6](docs/ENCLOSURE.md), [ENCLOSURE_V2_THERMAL.md §8](docs/ENCLOSURE_V2_THERMAL.md)). A 197k-tetrahedra 3-D CalculiX FEA under a `50 g` shock keeps peak case stress at `9.6 MPa` (`1.8×` margin at `70 °C`) and BGA strain `<= 96 µε` (vs. `500 µε` limit; [ENCLOSURE §5.3](docs/ENCLOSURE.md)).

![Enclosure v2 closed, with 50 mm filtered intake fan and TPU bumpers](docs/img/case_v2_closed.jpg)

| Version 2 opened (`case_v2`) | Cross-section: fan duct, SMAs & Kria K26 heatsink |
|---|---|
| ![v2 open](docs/img/case_v2_open.jpg) | ![v2 section](docs/img/case_v2_section.jpg) |
| **Version 2 lifted lid: `50 × 50 × 15 mm` fan in its duct** | **3-D 50 g FEA: peak stress `9.3 MPa` / BGA strain `<= 162 µε`** |
| ![v2 fan](docs/img/case_v2_fan.jpg) | ![FEA stress](docs/img/case3d_v2_stress.jpg) |

*(4K `3840 × 2160` Cycles renders `board_iso_4k.png`, `board_heatsinks_closeup_4k.jpg`, `case_v2_closed_4k.jpg`, `case_v2_open_4k.jpg`, and `case_v2_section_4k.jpg` are in [`docs/img/highres/renders/`](docs/img/highres/README.md#4-hardware-heatsink--enclosure-4k-renders-renders).)*

![FEA by material](docs/sim/case_materials.png)

---

## Legal notice

This design transmits on regulated bands. Operating the SDR transmitter requires an amateur radio
licence or equivalent authorisation, and emission in 10.4–10.6 GHz is subject to national
allocations that are **not** free to use in every country. See the compliance section of
[ARCHITECTURE.md](ARCHITECTURE.md). Staying within the applicable law is the responsibility of
whoever builds and operates the equipment.

## Licence

Licensed under the **Apache License 2.0**; see [`LICENSE`](LICENSE). Third-party MIT notices for the inherited Allied Vision CSI-2 adapter reference (`2023`) and verbatim `AERIS-10 / PLFM_RADAR` DSP modules (`fpga/third_party/aeris/`) are preserved in [`LICENSE`](LICENSE).
