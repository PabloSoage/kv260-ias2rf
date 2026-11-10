# Shopping list and checklist

*21 September 2026 · Vehicle platform on a Kria KV260*

Organised by **stage** (the reasoning behind the order is in
[VEHICLE_PLATFORM.md](VEHICLE_PLATFORM.md) §6). Every stage delivers something usable on its own.

**Prices are indicative `[E]`**, meant for sizing the effort — they are not quotes. Spanish VAT at
21 % included where it applies.

**Key:** ☑ already have · ☐ to buy · ◆ to design/fabricate · ⚑ paperwork

---

## Stage 0 — Start today, designing nothing

> **The most important stage in the project.** Do not design a board to find out what you need.

| | Item | What for | Price `[E]` |
|---|---|---|---|
| ☑ | **Kria KV260** | The brain | *already bought, €300* |
| ☐ | 12 V / 3 A supply or on-board adapter | Powering the KV260 | €20 |
| ☐ | microSD 32–64 GB class A2 | Linux boot | €15 |
| ☐ | USB 3.0 SSD (256 GB+) | Recording RF captures and point clouds | €40 |
| ☐ | **bladeRF 2.0 micro xA4** (47 MHz – 6 GHz, 2×2, full duplex, 12-bit) — or an AD9361 **AntSDR E200** | Wideband RX/TX, **2.4 and 5.8 GHz for drones**, two coherent channels | €550 |
| ☐ | **SDRplay RSPdx-R2** (1 kHz – 2 GHz, 14-bit, RX only) | HF, AM, airband and weak signals; replaces the HF upconverter | €200 |
| ☐ | **KrakenSDR** (5 coherent channels, 24 MHz – 1.766 GHz) | **Direction finding, ready to use** | €500 |
| ☐ | Antenna set: discone, HF whip, 5× VHF/UHF for the Kraken | Coverage and DF | €200 |
| ☐ | USB GPS (u-blox) + IMU | Position and heading for triangulation and SLAM | €80 |
| | | **Subtotal** | **~€1,600** |

> **Updated 29 September 2026.** Stage 0 used to be a HackRF One plus an HF upconverter
> (~€360). It is now a wideband transceiver plus a dedicated HF–UHF receiver (~€750); the
> reasons and the alternatives are in [Choosing the stage-0 SDRs](#choosing-the-stage-0-sdrs).

**Stage 0 checklist**
- [ ] Ubuntu/PetaLinux booting on the KV260
- [ ] bladeRF and RSPdx-R2 recognised over USB; capture with GNU Radio or SoapySDR
- [ ] Listen to FM, airband and PMR446 from the vehicle
- [ ] Detect a drone by its 5.8 GHz emission
- [ ] KrakenSDR producing bearings; triangulate a source by moving the car
- [ ] **Write down what actually limits you** ← the real deliverable of this stage

### Choosing the stage-0 SDRs

Figures `[V]` from the manufacturers' pages (sources below), checked on 29 September 2026. Prices are
list prices before import and VAT, except where a euro price is given.

| | Coverage | Bandwidth, resolution | TX | Notes |
|---|---|---|---|---|
| HackRF One | 1 MHz – 6 GHz | 20 MHz, 8-bit | half duplex | The previous choice |
| **HackRF Pro** | 100 kHz – 6 GHz | 20 MHz, 8-bit (16-bit mode at low rates) | half duplex | TCXO, USB-C and a small iCE40-UP5K FPGA. ~€430 in the EU. Its own page says the sensitivity is below that of desktop receivers |
| **bladeRF 2.0 micro xA4** | 47 MHz – 6 GHz | 61.44 MS/s, 12-bit, **2×2** | **full duplex** | Cyclone V 49 kLE, open FPGA, USB 3.0. $540 (the xA9, with a 301 kLE FPGA, $860) |
| **AntSDR E200** (AD9361) | 70 MHz – 6 GHz | up to 61.44 MS/s, 12-bit, **2×2** | **full duplex** | Zynq 7020 on board, **Gigabit Ethernet**. $499; the AD9363 version ($299) is limited to 325 MHz – 3.8 GHz |
| USRP B210 | 70 MHz – 6 GHz | 56 MHz, 12-bit, 2×2 | full duplex | The lab standard, ~$2,400 new |
| **SDRplay RSPdx-R2** | 1 kHz – 2 GHz | 10 MHz, 14-bit | no | The best receiver per euro for HF–UHF, ~$199 |
| KrakenSDR | 24 MHz – 1.766 GHz | 5 × 2.56 MHz, coherent | no | Direction finding and passive radar, $749 |
| Flipper Zero | 300–348, 387–464, 779–928 MHz | CC1101, OOK/ASK/FSK only | yes | Not an SDR: remotes, NFC, RFID, IR |

**Why the change:**
- **An AD9361-class transceiver beats the HackRF on every axis except coverage below 47 MHz.**
  That means 12 bits instead of 8, about three times the bandwidth, full duplex, and **two coherent
  receive channels**, which are enough for a two-element interferometer. The RSPdx-R2 covers the
  gap below 47 MHz with better sensitivity than either, so the HF upconverter goes.
- **bladeRF rather than AntSDR on this platform:** the bladeRF talks USB 3.0, and the KV260 has four
  such ports. The AntSDR uses the KV260's only Gigabit Ethernet port, which the stage-1 LiDAR also
  needs. On 1 Gb/s, 16-bit I/Q at 4 bytes per sample carries at most ~31 MS/s `[E]`, half of what the
  AD9361 can produce. The AntSDR remains the better choice when the processing should run on its own
  Zynq.
- **The KrakenSDR stays** for direction finding with more than two elements.

Sources: [HackRF Pro](https://greatscottgadgets.com/hackrf/pro/) ·
[HackRF Pro FPGA](https://www.embedsbc.com/hackrf-pro-sdr-architecture-fpga/) ·
[HackRF Pro price (Elektor)](https://www.elektor.com/products/great-scott-gadgets-hackrf-pro-sdr-100-khz-6-ghz) ·
[bladeRF 2.0 micro xA4](https://www.nuand.com/product/bladerf-xa4/) ·
[AntSDR E200](https://www.crowdsupply.com/microphase-technology/antsdr-e200) ·
[USRP B210](https://www.ettus.com/all-products/ub210-kit/) ·
[RSPdx-R2](https://www.elektor.com/products/sdrplay-rspdx-r2-single-tuner-14-bit-sdr-receiver-1-khz-to-2-ghz) ·
[KrakenSDR](https://www.krakenrf.com/product-page/krakensdr) ·
[Flipper Zero Sub-GHz](https://docs.flipper.net/zero/sub-ghz)

---

## Stage 1 — LiDAR

| | Item | Notes | Price `[E]` |
|---|---|---|---|
| ☐ | **3D LiDAR**: Livox Mid-360 (360°×59°, Ethernet) or Unitree L2 (360°×96°) | Official ROS2 driver; open SLAM (FAST-LIO2) | €600 – 900 |
| ☐ | Industrial Gigabit switch or direct cable | The LiDAR is Ethernet | €30 |
| ☐ | Bar/rack mount with damping | Vibration | €80 |
| ☐ | Shielded cabling and grommets | Clean installation | €50 |
| | | **Subtotal** | **~€800 – 1,100** |

**Checklist**
- [ ] Point cloud arriving at the Kria over Ethernet
- [ ] ROS2 + LiDAR driver running
- [ ] Basic SLAM working while stationary
- [ ] SLAM with vehicle odometry (needs stage 2)
- [ ] Ground/obstacle segmentation **on the DPU**
- [ ] 3D render of the terrain ahead, and "memory" of what passes under the vehicle

---

## Stage 2 — OBD2 / CAN

| | Item | Notes | Price `[E]` |
|---|---|---|---|
| ☑ | **Scanmatik 3** | **Laptop only, in the garage.** No Linux/aarch64 support | *already have* |
| ☐ | **USB-CAN adapter with SocketCAN** (CANable 2.0, PCAN-USB) | What lives on board, permanently | €30 – 250 |
| ☐ | OBD2 to DB9/CAN lead | Connection to the port | €20 |
| | | **Subtotal** | **~€50 – 270** |

**Checklist**
- [ ] `can0` up with SocketCAN on the Kria
- [ ] Frames captured with `candump`
- [ ] Confirmed the V80 uses ISO 15765-4 over CAN
- [ ] Wheel speed, RPM and temperature PIDs identified
- [ ] **Odometry published to the LiDAR SLAM**
- [ ] Persistent logging to the SSD

---

## Stage 3 — Communication that actually works (⚑ and ☐)

> Deliberately independent of the project. See [VEHICLE_PLATFORM.md](VEHICLE_PLATFORM.md) §2.3.

| | Item | Notes | Price `[E]` |
|---|---|---|---|
| ⚑ | **Amateur radio licence** | **Start now**: the paperwork takes months. Study + exam + callsign | €100 – 200 |
| ⚑ | Join **REMER** (civil protection) | Volunteer emergency network; fits this use case | free |
| ☐ | Mobile HF transceiver (e.g. Yaesu FT-891) | Long-distance comms without infrastructure | €700 – 900 |
| ☐ | Dual-band VHF/UHF mobile | Local comms, repeaters | €150 – 300 |
| ☐ | Mobile HF antenna + tuner | What most determines real range | €300 – 500 |
| ☐ | Dual-band antenna + ground plane | | €100 |
| | | **Subtotal** | **~€1,400 – 2,000** |

**Checklist**
- [ ] Licence obtained
- [ ] Equipment installed with direct battery feed and fuse
- [ ] Antennas tuned (SWR measured, not assumed)
- [ ] **Real contact test** from an area with no mobile coverage
- [ ] Verified that transmitting does not disturb the vehicle electronics

---

## Stage 4 — SDR RX adapter (◆ first custom board)

> A simple board, no FPGA. It validates the IAS1 interface, which is the foundation of everything
> that follows.

| | Item | Notes | Price `[E]` |
|---|---|---|---|
| ◆ | **Board design and fabrication** | 6 layers, short run with assembly. **Quoted 10 Nov 2026: ≈ $2,030 for two assembled boards, parts included** ([JLCPCB_QUOTE.md](JLCPCB_QUOTE.md)); the chip lines below are inside that figure | €400 – 800 |
| ☐ | ADC **AD9253BCPZ-125** | 14 b, 2 of 4 channels at 62.5 MSPS, 1-lane | €40 |
| ☐ | Clock: **ADCLK948BCPZ** (select + 1:8 fan-out) + **Si549** programmable XO | Si549 ordered configured: LVPECL, 3.3 V, 5×7 mm, pinout C. See docs/CLOCK_SPEC.md | €50 – 70 |
| ☐ | Differential drivers **AD8352ACPZ** ×2 | The ones AERIS uses | €30 |
| ☐ | Switches **M3SWA2-34DR+** ×4 | Positive 3.3 V control, but they **also need VEE −3.3 V** (B-03) | €80 |
| ☐ | −3.3 V charge-pump inverter (LM2663 or similar) | VEE for the switches, 8 mA | €3 |
| ☐ | Power: bucks, LDOs, reverse-polarity protection | See §9 of the master document | €40 |
| ☐ | Connectors: Hirose BM20B(0.8)-34DP ×2, SMA, Pmod | | €60 |
| ☐ | FFC/Pmod cable to the KV260 | | €20 |
| | | **Subtotal** | **~€700 – 1,100** |

**Prerequisites before ordering anything**
- [ ] Real `VCCO` of the KV260's HPA bank (carrier card schematic)
- [ ] Mechanical envelope measured on the physical board
- [ ] 6-layer stackup agreed with the fabricator, with computed impedances
- [ ] ERC with no errors and every warning justified individually

**Bring-up checklist** (in this order — each step validates the previous one)
- [ ] Rail voltages and ripple on every rail, with no converters fitted
- [ ] Clock on the scope via the CLK_OUT SMA: levels, jitter, termination; Si549 at 400 and 500 MHz
- [ ] **A known sine into the ADC input, recovered in the PL** ← the critical test
- [ ] The 3 switching modes

---

## Stage 5 — SDR front end and transmission (◆)

| | Item | Notes | Price `[E]` |
|---|---|---|---|
| ◆ | RF board design and fabrication | 4–6 layers | €400 – 800 |
| ☐ | **ADF4351** synthesiser | LO from 35 MHz to 4.4 GHz | €25 |
| ☐ | **ADL5801ACPZ** mixer | Here it *is* in range (10 MHz – 6 GHz) | €20 |
| ☐ | LNA (SPF5189Z / PGA-103+) | | €20 |
| ☐ | Filters: 30 MHz LPF + 3 switched BPFs | **Custom design** — do not underestimate them | €100 |
| ☐ | **AD9767ASTZ** or **AD9709** DAC + reconstruction filter | Transmission | €40 |
| ☐ | Input limiter, T/R switching, TX driver | | €80 |
| ☐ | **Switchable 50 Ω loads** | Validate in loopback without radiating | €30 |
| | | **Subtotal** | **~€700 – 1,100** |

---

## Stage 6 — 77 GHz obstacle radar (☐, nothing to design)

> **If the radar's purpose is seeing obstacles and fog, this stage replaces AERIS.**
> 76–77 GHz is allocated to vehicular radar: **no licence**.

| | Item | Notes | Price `[E]` |
|---|---|---|---|
| ☐ | **TI AWR1843AOP** module or similar (antenna on package) | One chip. USB/serial output | €250 – 400 |
| ☐ | Weatherproof enclosure and front mount | | €80 |
| | | **Subtotal** | **~€350 – 500** |

**Checklist**
- [ ] Detections arriving at the Kria
- [ ] Radar + LiDAR fusion (radar penetrates fog; LiDAR gives the resolution)

---

## Stage 7 — Front-end FPGA (◆ major decision still open)

> Needed for 4-channel direction finding and for AERIS. See [ROADMAP.md](ROADMAP.md) §4.3.

| | Item | Notes | Price `[E]` |
|---|---|---|---|
| ◆ | Board redesign with FPGA | QSPI boot, power sequencing, JTAG | €800 – 1,500 |
| ☐ | **XC7A50T-2FTG256I** | Same part as AERIS: its firmware runs unported | €80 |
| ☐ | QSPI flash + sequencing PMIC + JTAG | | €40 |
| ☐ | ADC **AD9484BCPZ-500** (8 b, 400 MSPS) | The one AERIS uses | €120 |
| ☐ | Vivado licence/installation | Free for these devices | — |
| | | **Subtotal** | **~€1,000 – 1,800** |

> The DSP core for this stage **already exists and is measured on silicon**:
> [scanner64](https://github.com/PabloSoage/scanner64) — 100.05 MSPS sustained, no samples
> dropped, 8.38 mW per channel, 169.9 MHz Fmax post-route on the KV260's own PL.

---

## Stage 8 — AERIS-10 (☐ + ◆, the big project)

> Only if the goal is **surveillance at range**. Requires experimental authorisation.

| | Item | Notes | Price `[E]` |
|---|---|---|---|
| ⚑ | Temporary and experimental use authorisation (10.45–10.5 GHz) | Amateur, **secondary** basis | paperwork |
| ◆ | AERIS Main Board | 4 or 8× ADAR1000, 16× ADTR1107, 2× LTC5552, XC7A50T, STM32 | €1,500 – 3,000 |
| ◆ | Frequency synthesiser board | AD9523 + 2× ADF4382 | €400 – 700 |
| ◆ | Power board | With sequencing | €300 |
| ◆ | Antenna array | Rogers, 8×16 patches | €500 – 1,500 |
| ◆ | 16× GaN amplifier boards | **Extended variant only** | €2,000+ |
| ☐ | Calibration instrumentation | **The hidden cost**: anechoic chamber or near-field setup | ??? |
| | | **Subtotal** | **€3,000 – 8,000+** |

---

## Cross-cutting — vehicle installation

Applies from stage 1 onwards. **This is not an accessory: it is what makes the rest work.**

| | Item | Why | Price `[E]` |
|---|---|---|---|
| ☑ | LiFePO4 + secondary alternator | | *already have* |
| ☐ | **ISO 7637-2 protection** on the 12 V input | Load dump and cold crank. A bench TVS is not enough | €50 |
| ☐ | Regulated 12 V DC/DC with input filter | Alternator ripple **will wreck your HF** | €80 |
| ☐ | IP-rated enclosure with filtered ventilation | The KV260's fansink needs clean air | €150 |
| ☐ | Fused distribution with a master cut-off | Safety | €60 |
| ☐ | Shielded cable, ferrites, ground braid | **Problem number one of vehicle radio** | €100 |
| ☐ | Touchscreen or tablet as the interface | | €150 |
| ☐ | Anti-vibration mounting tray | | €80 |
| | | **Subtotal** | **~€700** |

---

## Cost summary `[E]`

| Stage | Cost | Cumulative | Custom hardware |
|---|---|---|---|
| 0 — Commercial SDR | €1,600 | €1,600 | No |
| 1 — LiDAR | €950 | €2,550 | No |
| 2 — OBD/CAN | €150 | €2,700 | No |
| 3 — Type-approved radio | €1,700 | €4,400 | No |
| Cross-cutting — installation | €700 | €5,100 | No |
| 4 — SDR RX adapter | €900 | €6,000 | **Yes** |
| 5 — SDR front end + TX | €900 | €6,900 | **Yes** |
| 6 — 77 GHz radar | €430 | €7,300 | No |
| 7 — Front-end FPGA | €1,400 | €8,700 | **Yes** |
| 8 — AERIS-10 | €3,000 – 8,000+ | **€11,700 – 16,700+** | **Yes** |

**Stages 0 to 3, plus the installation, come to ~€5,100 and require designing no boards at all.**
That is where most of the real usefulness in the vehicle sits: listening, locating, seeing in the
dark, mapping, logging the vehicle, and being able to call for help.

Everything after that is custom RF engineering, and it costs more than all of the above combined.

---

## What you could order this week

If you want to start tomorrow, this is the minimum order that gets the KV260 out of a drawer:

- [ ] microSD A2 + USB SSD — **€55**
- [ ] SDRplay RSPdx-R2 — **€200**
- [ ] Discone antenna + HF whip — **€150**
- [ ] u-blox USB GPS — **€40**
- [ ] USB-CAN adapter with SocketCAN — **€50**

**~€495**, and you have listening from 1 kHz to 2 GHz, position, and vehicle telemetry. Adding the
**bladeRF 2.0 micro xA4 (~€550)** brings 2.4 and 5.8 GHz drone detection and transmission, for
**~€1,045**. Above all, six months of real data with which to decide whether the custom board needs
to be what we think it is today.
