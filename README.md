# KV260-IAS2RF — an RF front-end carrier for the AMD Kria KV260

**Status (12 November 2026): schematic and layout complete, on 8 layers. The board is fully routed, with zero
DRC errors and zero schematic-parity problems. It has not been fabricated, and no hardware has
been validated.** A few review items remain before an order (see [Status](#status)).

![The board, 3D render](docs/img/board_iso.png)

An adapter board for the **AMD Kria KV260 Vision AI Starter Kit**. It plugs into the KV260's IAS1
camera connector and carries the converters, a common clock and a front-end FPGA. It serves two
signal chains:

- **Software-defined radio**: HF, AM, FM, airband, amateur bands and PMR446. Receive, and
  transmit on the bands a licence covers.
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
| Size | 119 × 132 mm. It mounts on the KV260's IAS connectors and corner holes and overhangs to one side ([INTERFACE_SPEC §5.3](docs/INTERFACE_SPEC.md)) |
| Stackup | 8 layers, JLCPCB JLC08161H-2116C: signal, GND, signal, split power, GND, signal, GND, signal ([LAYOUT §3](docs/LAYOUT.md); 6 layers until 12 Nov, [compared in EIGHT_LAYERS](docs/EIGHT_LAYERS.md)) |
| Parts | 499: the top face, plus 20 on the bottom face under the FPGA (LVDS terminations and VCCINT caps) |
| Front-end FPGA | Xilinx XC7A50T-2FTG256I (the same part as AERIS-10) with a 128 Mb QSPI flash, plus JTAG |
| Radar ADC | AD9484, 8 bit, 400 MSPS, driven by two cascaded AD8352s |
| SDR ADC | AD9253, 14 bit, two channels at 62.5 MSPS (one LVDS lane each) |
| Radar DAC | AD9708, with reconstruction filter and balun |
| SDR DAC | AD9767, dual 14 bit, two output chains |
| Clock | Si549 programmable XO (400 or 500 MHz, GPS-disciplinable) into an ADCLK948 LVPECL fan-out |
| RF routing | Four M3SWA2-34DR+ SPDT switches and ten edge SMAs, plus two clock SMAs |
| Link to the Kria | IAS1 (Hirose BM20B), five LVDS pairs at up to 1 Gb/s each, AC-coupled; the Pmod J2 for control |
| To AERIS-10 | 2×20 IDC ribbon for eight ADAR1000s |
| Power | 12 V in; buck and LDO tree for 5 V, 3.3 V, 2.5 V, 1.8 V and 1.0 V, plus −3.3 V for the switches |

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

The renders come from KiCad. Some parts have no 3D model, so they show only their pads (the FPGA's
BGA, for one).

---

## Schematics and layout

- **[Schematic, all 10 sheets (PDF)](docs/CSI2-KRIA-KV260_Rev03_schematic.pdf)**
- **[Layout, the eight copper layers and both silkscreens (PDF)](docs/CSI2-KRIA-KV260_Rev03_layout.pdf)**
- KiCad 10 sources: [`CSI2-KRIA-KV260_Rev01.kicad_pro`](CSI2-KRIA-KV260_Rev01.kicad_pro), the root
  schematic and [`rev03/`](rev03/) (the nine sheets), the board
  [`CSI2-KRIA-KV260_Rev01.kicad_pcb`](CSI2-KRIA-KV260_Rev01.kicad_pcb), and the project's own
  symbols and footprints in [`symbols/`](symbols/) and [`footprints/`](footprints/). The file names
  keep the Rev01 name of the board they started from; the contents are Rev03.

| Sheet | Contents | Specification |
|---|---|---|
| [Root](docs/img/sch/ROOT.png) | Sheet hierarchy and the interface nets | [ARCHITECTURE](ARCHITECTURE.md) |
| [IAS_LINK](docs/img/sch/IAS_LINK.png) | The Hirose connectors, AC coupling and terminations of the link | [IAS_LINK_SPEC](docs/IAS_LINK_SPEC.md) |
| [CLOCK](docs/img/sch/CLOCK.png) | Si549, reference select and LVPECL fan-out | [CLOCK_SPEC](docs/CLOCK_SPEC.md) |
| [ADC_RADAR](docs/img/sch/ADC_RADAR.png) | AD9484 and its two AD8352 drivers | [ADC_RADAR_SPEC](docs/ADC_RADAR_SPEC.md) |
| [ADC_SDR](docs/img/sch/ADC_SDR.png) | AD9253, two channels | [ADC_SDR_SPEC](docs/ADC_SDR_SPEC.md) |
| [DAC_RADAR](docs/img/sch/DAC_RADAR.png) | AD9708, filter and balun | [DAC_RADAR_SPEC](docs/DAC_RADAR_SPEC.md) |
| [DAC_SDR](docs/img/sch/DAC_SDR.png) | AD9767 in interleaved mode, two output chains | [DAC_SDR_SPEC](docs/DAC_SDR_SPEC.md) |
| [ROUTING](docs/img/sch/ROUTING.png) | Four RF switches and the SMAs | [ROUTING_SPEC](docs/ROUTING_SPEC.md) |
| [CONTROL](docs/img/sch/CONTROL.png) | The front-end FPGA: banks, configuration, Pmod, AERIS ribbon, housekeeping | [CONTROL_SPEC](docs/CONTROL_SPEC.md) |
| [POWER](docs/img/sch/POWER.png) | The power tree | [POWER_SPEC](docs/POWER_SPEC.md) |

![Root sheet](docs/img/sch/ROOT.png)

---

## Status

| Check | Result |
|---|---|
| ERC | 0 errors; 7 warnings, all explained: configuration and XADC pins tied to power on purpose ([CONTROL_SPEC §5](docs/CONTROL_SPEC.md)) |
| DRC, zones refilled | **0 violations, 0 unrouted connections, 0 schematic-parity problems** (12 Nov, on 8 layers) |
| Signal and power integrity | Reviewed on 11 Nov and re-run on 8 layers on 12 Nov, ideal / 6 / 8 layers side by side ([EIGHT_LAYERS.md](docs/EIGHT_LAYERS.md), [SIGNAL_INTEGRITY.md](docs/SIGNAL_INTEGRITY.md)): SMA launch in openEMS (S11 −30.9 dB at 1 GHz with the ESD diode), LVDS eyes within 1–26 mV of ideal except LINK_RX_D0 (−52 mV), worst intra-pair skew 9 ps, VCCINT under its target to 100 MHz with four caps under the BGA; ESD protection on every SMA, the Pmod and JTAG, a GND via within 3 mm of every LVDS layer change, exposed-pad vias and an edge fence |
| Planes | L2 and L5 carry only ground, no supply track (`_work/layout/planechk.py`); every supply pin reaches its island (the DRC's zero unrouted) |
| Mechanical fit | Registered on AMD's 3D model of the KV260: the mounting holes land within 5 µm ([INTERFACE_SPEC §5.3](docs/INTERFACE_SPEC.md)) |

**Open before ordering** ([docs/LAYOUT.md §6.2–6.3](docs/LAYOUT.md)):

1. **Ten of the 19 LVDS pairs are not coupled.** Since 12 Nov the board has 8 layers and nine pairs
   run coupled at 100 Ω end to end ([EIGHT_LAYERS.md](docs/EIGHT_LAYERS.md)). The other ten are
   two 50 Ω legs matched to ±5 ps, within 1–26 mV of their ideal eye except LINK_RX_D0 (−52 mV).
   LINK_RX leaves bank 34, the only 2.5 V bank, in the BGA's south-east corner, and crosses every
   ADC pair to AC capacitors spread 9 mm apart; moving it to the bank's outer balls was tried on
   12 Nov and dropped (the corner has no room left for the vias). Coupling it would need the
   capacitors at J101 moved together first.
2. **ADCR data to DCO skew, −90 to +5 ps** (was −177 to −28). DCO's legs are swapped at the FPGA
   (N14 = DCO_N, P14 = DCO_P) so the pair reaches the AD9484 the right way round without going
   round the chip: 39 mm instead of 51. **The gateware must invert that clock** (ISERDESE2
   `IS_CLK_INVERTED`, or capture on the other edge) ([CONTROL_SPEC §1](docs/CONTROL_SPEC.md)).
   The rest is inside IDELAYE2's range and calibrated per bit.
3. **Order the 2116C stack explicitly** (JLC08161H-2116C): the widths are solved for it
   ([FABRICATION.md](docs/FABRICATION.md)). Five 8-layer bare boards: $282.92 ($236.88 on 6 layers).
4. **The AERIS-10 end of the ribbon does not exist yet.**
5. **No firmware.** The FPGA design for the front end and the Kria side of the link are not
   written yet.

**Cost** ([docs/JLCPCB_QUOTE.md](docs/JLCPCB_QUOTE.md), bare boards re-quoted on 8 layers on 12 Nov 2026): about **$2,070 for two
assembled boards** and $4,240 for five, three quarters of it parts. Seven parts are out of stock at
LCSC today (the ADCs, the RF switches, the clock buffer, the DAC, a balun and the drivers): JLCPCB's
global sourcing or consigned parts cover them.

---

## Documentation

| Document | Contents |
|---|---|
| **[docs/VEHICLE_PLATFORM.md](docs/VEHICLE_PLATFORM.md)** | **System view.** The whole vehicle project: LiDAR, SDR, radar, OBD2 |
| [docs/SHOPPING_LIST.md](docs/SHOPPING_LIST.md) | Parts and checklist per stage, with indicative costs |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Master document for this board: the Rev03 architecture and BOM |
| [docs/BLOCKERS_AND_RISKS.md](docs/BLOCKERS_AND_RISKS.md) | The five blockers, closed, with evidence and sources, plus the open risks |
| [docs/INTERFACE_SPEC.md](docs/INTERFACE_SPEC.md) | Pin map for J8 and the Pmod, the mechanical envelope, the adapter registered on the KV260 model |
| [docs/POWER_AND_STACKUP.md](docs/POWER_AND_STACKUP.md) | Per-rail current budget and the original 6-layer stackup with computed trace widths |
| [docs/SYMBOLS.md](docs/SYMBOLS.md) | The project's symbols, each from its datasheet, cross-checked against a second source where one exists |
| Sheet specifications | One per schematic sheet, in the table above: every value and where it comes from |
| [docs/LAYOUT.md](docs/LAYOUT.md) | The board: outline, stackup, rules, the split power layer, placement, routing and the LVDS review |
| [docs/EIGHT_LAYERS.md](docs/EIGHT_LAYERS.md) | The 8-layer board against the 6-layer one: stacks, every check side by side, eyes, skew, PDN, SMA, and what the same corrections would give on 6 layers |
| [docs/SIGNAL_INTEGRITY.md](docs/SIGNAL_INTEGRITY.md) | The RF/high-speed review (11 Nov) and the 8-layer re-run (12 Nov, §8): impedance, SMA launch (openEMS), LVDS eyes (ngspice), PDN impedance and DC drop, crosstalk, return vias, what is still a compromise; figures and data in [docs/sim/](docs/sim/) |
| [docs/FABRICATION.md](docs/FABRICATION.md) | Ordering from JLCPCB: the output script, the order form, what is left for the day of the order |
| [docs/JLCPCB_QUOTE.md](docs/JLCPCB_QUOTE.md) | What the JLCPCB order would cost (10 Nov 2026, bare boards on 8 layers 12 Nov): boards, assembly fees and every part with its LCSC link and price. About $2,070 for two assembled boards, $4,240 for five |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Staged plan with verifiable exit criteria |
| [docs/AUDIT_Rev01.md](docs/AUDIT_Rev01.md), [docs/HISTORY_Rev01.md](docs/HISTORY_Rev01.md) | What the inherited files contained, and the record of the earlier work |

---

## Repository layout

| Path | Contents |
|---|---|
| `CSI2-KRIA-KV260_Rev01.*`, `rev03/` | The KiCad project: root schematic, nine sheets, board |
| `symbols/`, `footprints/` | The project's own libraries |
| `docs/` | Specifications, layout and fabrication notes, renders and the PDFs |
| `_work/` | The scripts behind every finding and every step of the layout: symbols and footprints, sheet checks, placement (`_work/layout/build_board.py`), plane and LVDS checks, fabrication outputs |
| `fab/` | Not tracked. `python _work/fab/make_fab.py` writes Gerbers, drill, BOM and CPL there for JLCPCB |
| `PCB/`, `Documents/` | The original Allied Vision sources (Altium) and their outputs, untouched |
| `_backup_original/`, `_deprecated/` | Snapshots of the inherited files and the sheets removed from the project |

Reproducing the checks and the outputs (KiCad 10):

```bash
kicad-cli sch erc --severity-all CSI2-KRIA-KV260_Rev01.kicad_sch
kicad-cli pcb drc --schematic-parity --refill-zones --severity-all CSI2-KRIA-KV260_Rev01.kicad_pcb
python _work/fab/make_fab.py                                   # fab/: Gerbers, drill, BOM, CPL
python _work/fab/quote.py                                      # today's LCSC prices and stock; refreshes docs/JLCPCB_QUOTE.md
python _work/layout/lvds_skew.py CSI2-KRIA-KV260_Rev01.kicad_pcb  # LVDS delays, skew and stubs; --stubs PS lists the branches (needs shapely)
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

## Simulation results

Every figure compares three cases: an **ideal** line, the board on **6 layers** (JLC06161H-2116A,
11 November 2026) and on **8 layers** (JLC08161H-2116C, the board in this repository), all run
through the same scripts. The full comparison is in [docs/EIGHT_LAYERS.md](docs/EIGHT_LAYERS.md),
the method in [docs/SIGNAL_INTEGRITY.md](docs/SIGNAL_INTEGRITY.md).

| Check | 6 layers | 8 layers |
|---|---|---|
| Pairs routed coupled | 0 of 19 | 9 of 19 |
| Worst intra-pair \|P−N\| | 84 ps | 9 ps |
| Eye lost to routing (routed − ideal) | mean −22 mV, worst −113 mV | mean −8 mV, worst −52 mV |
| Zero-crossing spread added | mean 5 ps, worst 29 ps | mean 1 ps, worst 10 ps |
| Layer changes with no GND via within 3 mm | 1 of 186 | 0 of 89 |
| Other pairs' legs within 0.25 mm | 97.6 mm | 65.8 mm |
| Signal tracks on L4 under the BGA | 64 segments | 3 (supply stubs) |
| ADCR data − DCO | −88 … −23 ps | −90 … +5 ps (DCO re-routed 12 Nov; IDELAY absorbs it) |
| VCCINT impedance, max in band / at 100 MHz (target 120 mΩ) | 51 / 61 mΩ | 41 / 63 mΩ |
| DC drop +2V5 at 601 mA | 173–185 mV | 122–129 mV |
| SMA launch S11 at 1 / 3 GHz, with the ESD diode | −30.6 / −13.5 dB | −30.9 / −13.7 dB |

**LVDS eyes** (ngspice, PRBS7 at 1 Gb/s, each leg's copper by layer and width). The ideal line
depends on each board's pair length and termination, so each board is shown against its own ideal.

| Pair | 6 layers: ideal / routed | 8 layers: ideal / routed |
|---|---|---|
| LINK_RX_D1 | 575 / 559 mV, 75 / 77 ps | 385 / 372 mV, 41 / 51 ps |
| LINK_RX_D0 | 607 / 559 mV, 35 / 30 ps | 509 / 457 mV, 25 / 31 ps |
| LINK_RX_CLK | 548 / 516 mV, 12 / 14 ps | 395 / 392 mV, 10 / 10 ps |
| ADCS_FCO | 648 / 650 mV, 49 / 46 ps | 628 / 617 mV, 17 / 17 ps |
| ADCR_DCO | 626 / 581 mV, 24 / 35 ps | 609 / 610 mV, 17 / 18 ps |

Eye opening at the centre of the bit, then zero-crossing spread. The LINK_RX eyes end at the AC
capacitors, not at the Kria's receiver, so they are indicative only; the opening is in every case
several times the receiver's ±100 mV threshold.

![Folded eyes: ideal, 6 layers, 8 layers](docs/sim/rev04_eyes.png)

![Eye penalty per pair](docs/sim/rev04_eye_penalty.png)

**Intra-pair skew**, ball to pad, with the FPGA's package delay.

![Intra-pair skew](docs/sim/rev04_skew.png)

**Power distribution** seen from the XC7A50T's balls. The L4/L5 plane pair keeps its spacing, so
the impedance barely moves.

![PDN impedance](docs/sim/rev04_pdn.png)

**Edge SMA launch** (openEMS FDTD) with its ESD diode. The outer prepreg is the same on both
stacks, and so is the launch.

![SMA launch](docs/sim/rev04_sma.png)

---

## Legal notice

This design transmits on regulated bands. Operating the SDR transmitter requires an amateur radio
licence or equivalent authorisation, and emission in 10.4–10.6 GHz is subject to national
allocations that are **not** free to use in every country. See the compliance section of
[ARCHITECTURE.md](ARCHITECTURE.md). Staying within the applicable law is the responsibility of
whoever builds and operates the equipment.

## Licence

MIT — see [LICENSE](LICENSE). The licence and attribution of the original Allied Vision project
are preserved.
