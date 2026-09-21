# Blockers and risks

*Updated: 21 September 2026 · **All five blockers are closed***

Two of them closed **against** what the architecture assumed. The result forces a rethink of the
interface to the Kria. This document holds the evidence; the consequences are in
[ARCHITECTURE.md](../ARCHITECTURE.md).

| ID | Question | Outcome |
|---|---|---|
| **B-01** | Can the IAS pins be outputs? Which bank do they reach? | ⛔ **Closes against.** IAS0 does not reach the FPGA at all |
| **B-02** | Does the AD9253 do 125 MSPS in 1-lane mode? | ⛔ **Closes against.** 1-lane is capped at 62.5 MSPS |
| **B-03** | Do the RF switches need negative control? | ✅ **Closes in favour.** Positive control, 3.3 V |
| **B-04** | What is AERIS-10's IF? | ✅ **Closes in favour.** 120 MHz, filters unspecified |
| **B-05** | How is the Extended variant built? | ⚠️ **Partial.** Not published; 8 ADAR1000s per the project owner |

---

## B-01 — Interface to the Kria ⛔ CLOSES AGAINST

### What the official documentation says

Connector table from **UG1089** (v1.0, April 2021 and v1.3, May 2024 — identical on this point):

| Connector | UG1089 description |
|---|---|
| **CC J7 — IAS0** | *"OnSemi image access system (IAS) camera module interface supporting four MIPI lanes. **Connects to OnSemi AP1302 ISP device sensor 0 interface**"* |
| **CC J8 — IAS1** | *"OnSemi IAS camera module interface supporting four MIPI lanes. **Connected directly to the Zynq UltraScale+ MPSoC HPA bank**"* |
| **CC J9 — RPi camera** | *"Raspberry Pi camera module interface. **15-pin variant supporting two MIPI lanes** directly connected to the Zynq UltraScale+ MPSoC HPA bank"* |
| **CC J2 — Pmod** | *"Digilent Pmod 2x6 expansion header"* — 3.3 V, 100 mA |

Later the same guide names them explicitly as *"IAS camera sensor **ISP** interface (J7)"* against
*"IAS camera sensor **direct** interface (J8)"*.

Independently corroborated: *"the first IAS MIPI connector is connected to an external ISP AP1302
from ONSemi, while the second is connected directly to the SOM pins"*.

### The three consequences

**1. IAS0 (J7) does not reach the programmable logic.** Its four MIPI lanes run into an AP1302 ISP
soldered on the carrier card. An ISP is an image processor: it does not pass arbitrary data
through, and it certainly cannot be an output path. **The "IAS0 = RX, IAS1 = TX" architecture is
not realisable.**

**2. There is no 40-pin Raspberry Pi header on the KV260.** The full connector list on the carrier
is J2 (Pmod 2×6), J3 (JTAG), J4 (UART/JTAG over USB), J5 (HDMI), J6 (DisplayPort), J7 (IAS0),
J8 (IAS1), J9 (15-pin RPi camera), J10 (Ethernet), J11 (microSD), J12 (12 V), J13 (fan).
**J9 is a camera connector, not a Raspberry Pi GPIO header.** The original report based the whole
parallel DAC bus on *"the Kria's 40-pin RPi header (28 GPIO available)"*: that connector does not
exist.

**3. The GTH transceivers are not reachable.** The K26 SOM has a 12.5 Gb/s GTH quad, but on the
KV260 it does not come out to any user connector. **JESD204B is ruled out**, which was the natural
route for a fast converter with few pins.

### The real I/O budget from a KV260 to an external board

| Connector | Differential pairs | Single-ended | Destination |
|---|---|---|---|
| **J8 / IAS1** | **5** (4 data + 1 clock) | ~4 (I2C, PWDN, GPIO) | HPA bank, direct to the SOM |
| **J9 / RPi camera** | **3** (2 data + 1 clock) | ~2 | HPA bank, direct |
| **J2 / Pmod** | — | **8** at 3.3 V, 100 mA | HD bank |
| ~~J7 / IAS0~~ | ~~4~~ | — | **Ends at the AP1302 ISP** |
| **Usable total** | **8 pairs** | **~14** | |

Eight differential pairs. That is all there is.

### What did close in favour

- The J8 and J9 pins go **straight to the SOM**, with no buffers or translators in between. They
  are ordinary FPGA I/O on an HP bank: **bidirectional**, configurable as LVDS or LVCMOS.
- The carrier provides **2.75 V, 1.8 V and 1.2 V** rails on the IAS power pins, consistent with
  the pinout read from this repository's `.kicad_pcb`.

`[?]` **Still to confirm:** the exact `VCCO` of the HPA bank as the KV260 configures it (Zynq
UltraScale+ HP banks accept 1.0 V to 1.8 V; MIPI D-PHY usually implies 1.2 V). It determines the
usable I/O standard and whether AC coupling is needed. **Not a blocker for the architecture
decision**, but it is one for closing the schematic.

---

## B-02 — AD9253 one-lane mode ⛔ CLOSES AGAINST

Two specifications from the AD9253 datasheet:

1. *"the data rate for each serial stream is equal to **16 bits** times the sample clock rate
   divided by the number of lanes"* (16, not 14: there are 2 framing bits).
2. *"a maximum of **1000 Mbps/lane** at 125 MSPS in **two-lane** mode. The maximum conversion rate
   is based on two-lane output mode."*

Check: 16 × 125 MSPS ÷ 2 lanes = 1000 Mbps/lane ✓

Solving for one lane: **f_s ≤ 1000 Mbps ÷ 16 bits = 62.5 MSPS**.

### Consequence for the pair budget

| Configuration | Channels | f_s | Nyquist | Pairs (data + DCO + FCO) |
|---|---|---|---|---|
| 1-lane | 2 | **62.5 MSPS** | 31.25 MHz | 2 + 2 = **4** |
| 2-lane | 2 | 125 MSPS | 62.5 MHz | 4 + 2 = **6** |
| 2-lane | 1 | 125 MSPS | 62.5 MHz | 2 + 2 = **4** |

With 5 pairs on IAS1, **two channels at 125 MSPS do not fit** (6 would be needed). The only direct
options are two channels at 62.5 MSPS, or one channel at 125 MSPS.

`[?]` It would be worth seeing the explicit line in the datasheet's output-mode table. The
arithmetic is determinate given the two quoted specs, but it is a deduction, not a direct citation
of the one-lane limit.

---

## B-03 — RF switches ✅ CLOSES IN FAVOUR

The **M3SWA2-34DR+** (the one AERIS-10 uses, 17 of them) is an absorptive GaAs MMIC SPDT switch
**with an internal driver**, DC – 30 GHz, supply **3.3 – 3.6 V**, in a 3×3 mm QFN, handling
+27 dBm.

The internal driver takes positive logic control: **no negative rail is needed.** The charge-pump
inverter comes out of the power tree.

The `-5V0_ADAR12` / `-5V0_ADAR34` rails AERIS has are for the **ADAR1000s**, not for the switches,
and they live on its own board. They do not affect the adapter.

---

## B-04 — AERIS-10's intermediate frequency ✅ CLOSES IN FAVOUR

**AERIS-10's IF is 120 MHz**, sampled at 400 MSPS. Verified in its own RTL:

```
9_Firmware/9_2_FPGA/ddc_400m.v                  "120MHz IF"
9_Firmware/9_2_FPGA/tb/cosim/radar_scene.py     F_IF = 120
   RTL parameter:  IF_FREQ = 120_000_000
```

**And the IF filters are not specified.** In the Main Board BOM, part `BPF2` (quantity 2,
designators `U$2, U$3`) has as its manufacturer part number literally **"Not a component"**: they
are undefined placeholders.

### Consequences, all favourable

- There is no filtering hardware to replace on the AERIS board. The worry about having to modify
  someone else's board disappears.
- The IF is a **free parameter**: whatever suits the chosen converter can be agreed.
- If the 120 MHz IF is kept, it can be **undersampled**: at 125 MSPS, 120 MHz falls in the second
  Nyquist zone and folds down to 5 MHz. That is textbook bandpass sampling, and it requires the
  anti-alias filter to be a **bandpass centred on 120 MHz**, not a lowpass.

---

## B-05 — AERIS-10X Extended variant ⚠️ PARTIAL

There is no published evidence for the 8-ADAR1000 configuration. What is verified:

- The published Main Board carries **4× ADAR1000ACCZN** and 16× ADTR1107.
- The AERIS README describes the Extended variant as a 32×16 slotted waveguide array with 16
  10 W GaN power amplifier boards. Sixteen PA boards match 16 channels, not 32.
- Control is **per chip**: `ADAR_n_CS`, `ADAR_TX_LOAD_n`, `ADAR_RX_LOAD_n`, `ADAR_TR_n`.

**The project owner's figure (8 chips, 32 channels) is adopted as the sizing requirement**, because
over-sizing the control is cheap and under-sizing it cannot be fixed later. Worth confirming with
the AERIS author before freezing the connector.

---

# Open risks

### R-01 — The KV260 is I/O-poor for this project

**This is the structural risk.** Eight differential pairs and fourteen loose signals is very little
for an RF front end with two chains, two converters and up to 32 beamforming channels.

**Alternatives if it becomes untenable:**

| Option | I/O available | Cost |
|---|---|---|
| KV260 + front-end FPGA | 8 pairs (own serial link) | One more FPGA on the adapter |
| **KR260** (Robotics Starter Kit) | 4× Pmod, PL Ethernet, more I/O | Change board |
| **Custom carrier for the K26 SOM** | ~180 user I/O + 4 GTH lanes at 12.5 Gb/s | Design a 240-pin carrier |

The third is what a serious radar design does, and it enables JESD204B. It is also by far the most
expensive in work.

---

### R-02 — Range resolution limited by the converter

| Configuration | Usable bandwidth | Resolution ΔR = c/2B |
|---|---|---|
| AERIS-10 as built (AD9484, 400 MSPS) | 200 MHz | 0.75 m |
| With front-end FPGA (AD9484 at 400 MSPS) | 200 MHz | **0.75 m** |
| No funnel, AD9253 1 channel at 125 MSPS | ~50 MHz | 3.0 m |
| No funnel, AD9253 2 channels at 62.5 MSPS | ~25 MHz | 6.0 m |

The front-end FPGA is what recovers AERIS's original performance.

---

### R-03 — Crosstalk if coupled pairs are used single-ended

The J8 and J9 pairs are 100 Ω coupled lines. Using their two conductors as independent signals
means strong coupling. **With the front-end FPGA the problem disappears**: the pairs are used as
LVDS pairs, which is what they are for.

---

### R-04 — Mechanical envelope not measured

The current outline is 119 × 44.5 mm. How far the board can grow without fouling the heatsink, the
front connectors or the enclosure has to be measured on the physical board. The Hirose positions
are fixed.

Added since: if **J9 (RPi camera, 15-pin FFC)** is used alongside J8, the adapter needs an FFC
cable reaching that connector, which sits elsewhere on the carrier. That is a real mechanical
complication.

---

### R-05 — Array calibration

32 channels need per-channel phase and amplitude calibration: an anechoic chamber, or at minimum a
near-field setup. It is the largest hidden cost of the radar project. The adapter does not
introduce it, but it belongs in the plan.

---

### R-06 — Regulation of emission at 10.5 GHz

`[?]` Not a licence-free ISM band everywhere. In Spain, 10.45–10.5 GHz is allocated to the amateur
service on a **secondary** basis, and use of 10.0–10.5 GHz requires **special authorisation**;
there is a formal mechanism for temporary and experimental use. That leaves **50 MHz** of room,
which caps the sweep and therefore range resolution at about 3 m.

With 10 W GaN amplifiers per channel, the Extended variant is **not equipment you simply switch
on**.

**Design mitigation:** switchable 50 Ω loads on the TX outputs, so the whole system can be
validated in conducted loopback without radiating. It costs almost nothing and unblocks bring-up
without depending on a licence or an authorised site.

---

### R-07 — Power sequencing of the power amplifiers

A sequencing fault on power-up destroys the GaN amplifiers. AERIS-10 solves this with its STM32.

**Design mitigation:** keep the AERIS STM32 as the housekeeping controller rather than
reimplementing logic that is already proven. Rewriting tested code that protects expensive
hardware is taking on risk for nothing.

---

### R-08 — Porting the AERIS-10 FPGA firmware

Reusable and well tested, but it is not copy-and-paste: clock domains, bit depths and the host
interface all need adapting. **With the front-end FPGA, `ddc_400m.v` ports almost as-is**, because
it would run in its native 400 MSPS domain.

---

### R-09 — Adding an FPGA to the adapter is a step change in complexity

**Accepted, knowingly, on 21 September 2026.** The board stops being an adapter and becomes an FPGA
board: configuration, boot memory, multi-rail sequenced power, JTAG, and a second toolchain.

This is no longer an open decision, but it remains a live risk and the schedule should reflect it.
What reduces it: the part chosen is the one AERIS-10 already uses, so its firmware ports with little
work, and the DSP core has been built and measured on silicon
([scanner64](https://github.com/PabloSoage/scanner64)).

---

## Sources

- [Kria KV260 Vision AI Starter Kit User Guide UG1089 v1.0](https://fpga.eetrend.com/files/2021-11/wen_zhang_/100554954-225561-ug1089-kv260-starter-kit.pdf)
- [Kria KV260 Vision AI Starter Kit User Guide UG1089 v1.3](https://docs.xibif.ch/_downloads/480ec1217d1ac2bd520e695148cfe86f/KV260_Userguide.pdf)
- [Hardware Architecture of the Platform — Kria KV260 docs](https://xilinx.github.io/kria-apps-docs/kv260/2022.1/build/html/docs/nlp-smartvision/docs/hw_arch_platform_nlp.html)
- [Kria K26 SOM Data Sheet DS987 — GTH Transceivers](https://docs.amd.com/r/en-US/ds987-k26-som/GTH-Transceivers)
- [AD9253 Data Sheet — Analog Devices](https://www.analog.com/media/en/technical-documentation/data-sheets/ad9253.pdf)
- [M3SWA2-34DR+ SPDT RF Switch — Mini-Circuits](https://www.minicircuits.com/pdfs/M3SWA2-34DR+.pdf)
- [tomverbeure/kv260_bringup](https://github.com/tomverbeure/kv260_bringup)
