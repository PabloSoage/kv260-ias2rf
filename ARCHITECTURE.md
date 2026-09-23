# KV260-IAS2RF — Architecture, Rev03

**Adapter board for the AMD Kria KV260, with a front-end FPGA**
**SDR chain (HF / VHF / UHF) plus a 10.5 GHz radar chain on AERIS-10**

*Revision 03 · 21 September 2026 · All five Rev02 blockers are closed*
*Architecture **approved** 21 September 2026: front-end FPGA accepted, radar is AERIS-10*

---

## 0. Why there is a Rev03

Rev02 started from: *IAS0 as the receive path, IAS1 as the transmit path, a common clock*. When the
blockers closed, that premise turned out not to be realisable:

> **The KV260's IAS0 (J7) connector does not reach the programmable logic.** Its four MIPI lanes
> run into an AP1302 ISP soldered on the carrier card. Only **IAS1 (J8)** is wired straight to the
> SOM.
>
> **And there is no 40-pin Raspberry Pi header on the KV260.** J9 is a 15-pin *camera* connector.
> The only general-purpose expansion is the **Pmod J2**, with 8 signals.

Full evidence in [docs/BLOCKERS_AND_RISKS.md](docs/BLOCKERS_AND_RISKS.md).

The real I/O budget between a KV260 and an external board is **8 differential pairs and about 14
loose signals**. That is an order of magnitude less than the previous architecture assumed, and it
forces a fundamental change: **a front-end FPGA on the adapter board**.

### Notation

| Mark | Meaning |
|---|---|
| `[V]` | **Verified** against files in this repository, in `PLFM_RADAR`, or cited official documentation |
| `[E]` | **Engineering estimate**, to be confirmed against a datasheet or simulation |
| `[?]` | **Unknown** that constrains the design |

### Contents

1. [The KV260's I/O budget](#1-the-kv260s-io-budget)
2. [Architecture: a front-end FPGA](#2-architecture-a-front-end-fpga)
3. [How 400 MSPS gets sampled](#3-how-400-msps-gets-sampled)
4. [The link to the Kria](#4-the-link-to-the-kria)
5. [Converters and clock](#5-converters-and-clock)
6. [Frequency plan](#6-frequency-plan)
7. [Integration with AERIS-10](#7-integration-with-aeris-10)
8. [Split of processing](#8-split-of-processing)
9. [Power tree](#9-power-tree)
10. [Rev03 BOM](#10-rev03-bom)
11. [Alternatives to the KV260](#11-alternatives-to-the-kv260)
12. [Regulatory compliance](#12-regulatory-compliance)

---

## 1. The KV260's I/O budget

`[V]` Verified in UG1089 v1.0 and v1.3, and corroborated by AMD's platform documentation.

| Connector | Differential pairs | Single-ended | Destination |
|---|---|---|---|
| **J8 — IAS1** | **5** (4 data + 1 clock) | ~4 (I2C, PWDN, GPIO) | **HPA bank, direct to the SOM** |
| **J9 — RPi camera** | **3** (2 data + 1 clock) | ~2 | **HPA bank, direct to the SOM** |
| **J2 — Pmod** | — | **8** at 3.3 V, 100 mA | HD bank |
| ~~J7 — IAS0~~ | ~~4~~ | — | **Ends at the AP1302 ISP** |
| **Total** | **8 pairs** | **~14** | |

Three facts worth keeping in mind:

- **The J8 and J9 pins go straight to the SOM**, with no buffers or translators. They are ordinary
  FPGA I/O on an HP bank: bidirectional, configurable as LVDS or LVCMOS.
- **The K26's GTHs do not come out to any user connector** on the KV260. JESD204B is ruled out,
  which was the natural route for a fast converter with few pins.
- `[?]` The exact `VCCO` of the HPA bank is still to be confirmed (HP banks accept 1.0–1.8 V; MIPI
  D-PHY usually implies 1.2 V). It determines the usable I/O standard and whether AC coupling is
  required.

### 1.1 What happens to the adapter's IAS0 connector

The inherited board has two Hirose footprints. The IAS0 one stays **populated for mechanical
reasons** (board retention) and to pick up the 2.75 V / 1.8 V / 1.2 V rails, but **its differential
pairs are left unconnected**. `[?]` Whether its I2C and GPIO signals reach the SOM or the AP1302 is
still open; until that is known, they are not counted on.

---

## 2. Architecture: a front-end FPGA

With eight differential pairs you cannot connect a fast converter directly to the Kria. The answer
is to put an FPGA on the adapter board that talks **wide and short** to the converters and **narrow
and fast** to the Kria.

```
+--------------+                  +-----------------------------------------+
|              |   J8 / IAS1      |        ADAPTER BOARD                    |
|  Kria KV260  |<=== 3 pairs =====|                                         |
|              |      RX          |   +-------------------+                 |
|  PL: pulse   |==== 2 pairs ====>|   |  front-end FPGA   |<--10 pairs--ADC |
|   compress., |      TX          |   |  XC7A50T-FTG256   |                 |
|   Doppler,   |                  |   |                   |--parallel-->DAC |
|   CFAR,      |   J2 / Pmod      |   |  · ADC capture    |                 |
|   tracking   |<---- 8 SE ------>|   |  · DDC + decim.   |--43 lines-->    |
|  PS: Linux,  |      control     |   |  · FMCW chirp     |     ADAR1000    |
|   DPU / AI,  |                  |   |  · ADAR fan-out   |     control     |
|   network,   |   J7 / IAS0      |   |  · level          |                 |
|   GUI        |<- mechanical and |   |    translation    |--SPI/UART-->    |
|              |   power only     |   +-------------------+   AERIS STM32   |
+--------------+                  |   Common clock · Power · 4× SPDT        |
                                  +------------+--------------+-------------+
                                        IF+ctrl |              | IF+ctrl
                                  +-------------+--+  +--------+-----------+
                                  | SDR front end  |  |  AERIS-10          |
                                  | HF/VHF/UHF     |  |  4 or 8× ADAR1000  |
                                  +----------------+  +--------------------+
```

### 2.1 What it solves at a stroke

The front-end FPGA is not a patch: it simultaneously resolves **the five problems** the previous
architecture could not close.

| Problem | How it is resolved |
|---|---|
| Only 8 pairs to the Kria | An in-house serial link, at whatever rate is chosen |
| The AD9484 needs 10 pairs | They connect to the FPGA, 2 cm away |
| 43 ADAR1000 control lines | Fan-out from the FPGA, with a synchronous strobe |
| Level translation across 1.2 / 1.8 / 3.3 V | Separate I/O banks on the FPGA itself |
| Crosstalk from using coupled pairs single-ended | Gone: the pairs are used as LVDS, which is what they are for |

### 2.2 Choosing the FPGA

**Recommendation: XC7A50T-2FTG256I** — exactly the part AERIS-10 uses `[V]`.

The deciding argument is not technical but about risk: **all of AERIS-10's FPGA firmware runs on
that part with nothing ported**. `ddc_400m.v`, the chirp controller, pulse compression, Doppler,
MTI and CFAR are written and tested for it, with documented regressions and timing closure at
400 MHz `[V]`. Its design occupies 6,092 LUTs (4.5 %), 9,024 FFs, 16 BRAMs and 140 DSP48s `[V]`:
there is ample room to add the link to the Kria.

Cheaper alternatives: Spartan-7 XC7S25/S50 (same Vivado flow, no transceivers, which are not needed
here). The cost would be having to port the firmware.

### 2.3 Status: approved

**The front-end FPGA was accepted on 21 September 2026**, for the reason in §1: the KV260 does not
expose enough pins for a converter to connect directly.

Two scope decisions came with it:

- **The radar is AERIS-10**, for surveillance at range. It is understood as a project rather than
  something that will be operated on air; the licensing position is in
  [docs/BLOCKERS_AND_RISKS.md](docs/BLOCKERS_AND_RISKS.md) R-06.
- **Obstacle detection leaves this board.** It will be a commercial automotive radar over USB —
  cheaper, licence-free at 76–77 GHz and purpose-built. Nothing in this schematic has to account
  for it.

### 2.4 The cost, stated plainly

This stops being an adapter board and becomes **an FPGA board**: QSPI boot memory, sequenced
multi-rail power (VCCINT, VCCAUX, VCCO ×3), JTAG, dense decoupling, and a second toolchain. It is
the most important project decision still open (R-09 in
[docs/BLOCKERS_AND_RISKS.md](docs/BLOCKERS_AND_RISKS.md)).

**The no-FPGA alternative exists** but is very poor: 2 channels at 62.5 MSPS over IAS1 (4 pairs) and
an 8-bit DAC split between J9 and the Pmod with translators. 6 m radar resolution, three different
connectors, and the ADAR1000 fan-out unsolved. I do not recommend it.

---

## 3. How 400 MSPS gets sampled

Yes, with the funnel board — and there are two ways to do it.

### 3.1 Dumb funnel: serialise and forward

The FPGA captures the AD9484's 10 pairs and re-serialises towards the Kria.

| Item | Figure |
|---|---|
| Raw rate, 1 channel | 8 bits × 400 MSPS = **3.2 Gbps** |
| Pairs available to the Kria (IAS1) | 4 data + 1 clock |
| Rate per pair | 3.2 / 4 = **800 Mbps** `[E]` — comfortable for LVDS on an HP bank |

**One channel at 400 MSPS fits raw.** Two channels would be 6.4 Gbps, that is 1.6 Gbps per pair: at
the limit, with no margin.

Upside: the Kria receives raw samples and does all the processing. Downside: it consumes the whole
link and leaves nothing for the transmit path.

### 3.2 Smart funnel: DDC and decimation before the link *(recommended)*

In a radar nobody processes the raw ADC stream: the first thing you do is bring it down to baseband
and decimate. **AERIS already has that module written**: `ddc_400m.v`, which converts a 120 MHz IF
sampled at 400 MSPS `[V]`.

| Stage | Rate |
|---|---|
| Raw ADC, 1 channel | 8 b × 400 MSPS = 3.2 Gbps |
| After DDC and ÷16 decimation | 2 × 16 b × 25 MSPS = **0.8 Gbps** |
| **2 channels** | **1.6 Gbps** |

With 2 data pairs to the Kria there is room to spare, and pairs are left for the transmit path.

**This is the recommendation**: port `ddc_400m.v` to the front-end FPGA, where it would run in its
native 400 MSPS domain with no adaptation at all, and send decimated I/Q to the Kria.

> The DSP core for this has already been built and measured on real silicon:
> [scanner64](https://github.com/PabloSoage/scanner64) sustains 100.05 MSPS on the KV260's own PL,
> one sample per clock, with no samples dropped across 200 million, bit-exact against its model, at
> 8.38 mW per channel. It settles the question of whether the PL can carry a converter stream.

### 3.3 What that buys

| Configuration | Bandwidth | Resolution ΔR = c/2B |
|---|---|---|
| **With funnel FPGA (AD9484 at 400 MSPS)** | 200 MHz | **0.75 m** |
| No funnel, AD9253 1 channel at 125 MSPS | ~50 MHz | 3.0 m |
| No funnel, AD9253 2 channels at 62.5 MSPS | ~25 MHz | 6.0 m |

The funnel FPGA **recovers AERIS-10's performance in full**. Without it you lose a factor of 4 to 8
in resolution.

---

## 4. The link to the Kria

### 4.1 Proposed allocation

Only **J8 (IAS1) and the Pmod** are used. J9 is kept as an optional expansion: it adds 3 more pairs
but it is a 15-pin FFC located elsewhere on the carrier, which complicates the mechanics (R-04).

| Resource | Pairs / signals | Use | Rate `[E]` |
|---|---|---|---|
| J8, pairs 1–2 | 2 | **RX**: decimated I/Q, FPGA → Kria | 2 × 1 Gbps |
| J8, pair 3 | 1 | Source-synchronous clock, FPGA → Kria | — |
| J8, pair 4 | 1 | **TX**: baseband, Kria → FPGA | 1 Gbps |
| J8, pair 5 | 1 | Clock, Kria → FPGA | — |
| J8, single-ended | ~4 | Housekeeping I2C, reset, interrupt | — |
| Pmod J2 | 8 | Control SPI (3), beam strobe, PPS, 3 spare | — |

Usable rate: **2 Gbps receive and 1 Gbps transmit**, comfortable for decimated I/Q on two channels
each way.

### 4.2 Protocol

`[E]` An in-house source-synchronous DDR serial link, with:

- an alignment word at the start of each frame (the equivalent of a serial ADC's `FCO`);
- 8b/10b coding **or** scrambling, to guarantee transitions and let the Kria's receiver align its
  recovered clock;
- a return channel for control and error counters.

Nothing has to be invented: it is the same pattern any serial LVDS receiver implements, and the Kria
deserialises it with `ISERDESE3`.

---

## 5. Converters and clock

### 5.1 ADC

**Recommendation: AD9484BCPZ-500**, the same one AERIS-10 uses `[V]`. 8 bits, up to 500 MSPS,
parallel LVDS output on 10 pairs (`D0..D7`, `DCO`, `OR`) `[V — net names from the AERIS schematic]`.

Eight bits looks thin until you remember that pulse compression recovers the dynamic range: it is
the choice of a 10.5 GHz radar that works.

> **The AD9253 is dropped as the main part.** B-02 closed: its one-lane mode is capped at
> **62.5 MSPS** (16 framing bits × f_s ÷ lanes, with a 1000 Mbps per-lane maximum). It remains a
> good candidate for a **second ADC dedicated to the SDR**, where 14 bits matter far more than
> speed.

**A two-converter arrangement** is what fits the two chains best:

| Converter | Chain | Bits | f_s | Rationale |
|---|---|---|---|---|
| AD9484-500 | Radar | 8 | 400 MSPS | Bandwidth; pulse compression supplies the dynamic range |
| AD9253 (2 of 4 channels) | SDR | 14 | 62.5 MSPS | Dynamic range; the SDR does not need 400 MSPS |

Both hang off the FPGA, which has I/O to spare. That is cheaper than forcing one converter to do two
incompatible jobs.

### 5.2 DAC

**AD9708AR** (8 bits, 125 MSPS), AERIS's part `[V]`, for the radar chirp; and **AD9767** (dual
14 bits) for the SDR if transmit quality matters. Both with a parallel bus **local to the FPGA**,
where bus width is no longer a problem.

This removes at the root the Rev02 compromise, which forced 8-bit transmission for want of pins.

### 5.3 Clock

**Revised on 23 September 2026, when the sheet was drawn.** The Rev02 plan (TCXO, selector,
ADCLK944 feeding ADC, DAC and FPGA) did not survive contact with the datasheets: a fan-out copies
one frequency to every output, the DACs take CMOS clocks, and a TCXO cannot reach 400 MHz. Full
account in [docs/CLOCK_SPEC.md](docs/CLOCK_SPEC.md). What is drawn:

```
  J401 SMA CLK_REF_IN <-- AERIS-10, AD9523 output, 400 MHz   (radar mode)   -> CLK0
  Y401 Si549 programmable XO, 400 or 500 MHz via I2C         (SDR mode, default) -> CLK1
  U401 ADCLK948: selects CLK0/CLK1, 8 LVPECL outputs, AC-coupled with 200 ohm + 100 pF
        Q0 --> AD9484   (400/500 MSPS)
        Q1 --> AD9253   (divides by 8 internally: 50 / 62.5 MSPS)
        Q2 --> front-end FPGA (generates the DACs' CMOS clocks with their data)
        Q3 --> J402 SMA CLK_OUT
```

**The master clock is AERIS's AD9523 whenever the radar is in use** `[V]`: it already phase-aligns
the references for the ADC, the DAC and both ADF4382 synthesisers. Duplicating it would break that
alignment, which is precisely what has to be preserved for a coherent radar.

Every LVPECL output needs **coupling capacitors and a bias network** — what was missing in Rev01,
where the BOM listed only *"R_term 100 Ω ×4"*.

---

## 6. Frequency plan

### 6.1 Radar — 120 MHz IF

`[V]` **AERIS-10's IF is 120 MHz** (`ddc_400m.v`, parameter `IF_FREQ = 120_000_000`), sampled at
400 MSPS. Since 120 < 200 MHz it falls in the first Nyquist zone: direct sampling, no tricks.

**And AERIS's IF filters are unspecified**: the `BPF2` part in its BOM (2 off, `U$2, U$3`) has as
its manufacturer part number literally **"Not a component"** `[V]`. There is no third-party hardware
to modify, and the IF is a free parameter should it need changing.

### 6.2 SDR

Two paths, on the SDR front-end board:

**Path 1 — HF by direct sampling, 0.1–30 MHz**
```
Antenna - Limiter - T/R switch - 30 MHz LPF - Attenuator - LNA --> SDR ADC
```
Covers LW/MW, shortwave, **CB (26.9–27.4)** and 10 m.

**Path 2 — VHF/UHF by conversion**

| Sub-band | LO (IF = 20 MHz) | Bands |
|---|---|---|
| 50–70 MHz | 30–50 MHz | 6 m |
| 85–150 MHz | 65–130 MHz | **FM broadcast 88–108**, airband, **2 m** |
| 400–470 MHz | 380–450 MHz | 70 cm, **PMR446 walkies at 446** |

> The walkies worth listening to are at 446 MHz. Rev01 declared coverage of *"AM, FM, CB, VHF,
> PMR"* over a range of *"1–50 MHz"*: none of those three bands falls inside it. Path 2 exists for
> exactly that.

**Blocks that were entirely missing in Rev01** and remain essential: anti-alias filter,
reconstruction filter, LNA, gain control, preselector, input limiter, baluns, and an **LO
synthesiser** (Rev01 brought it in from outside over an SMA).

---

## 7. Integration with AERIS-10

### 7.1 What gets reused

| AERIS-10 block | Destination |
|---|---|
| ADAR1000s, ADTR1107s, array, LTC5552 mixers, ADF4382 synthesisers, AD9523 clock | **Reused as-is** |
| The Main Board's AD9484 and AD9708 | Replicated on the adapter board, next to the FPGA |
| XC7A50T and its firmware | **Part and firmware both kept**, now on the adapter board |
| STM32F746 (housekeeping) | **Kept** on AERIS — see §7.3 |

### 7.2 ADAR1000 control

`[V]` AERIS gives each chip four dedicated lines: `ADAR_n_CS`, `ADAR_TX_LOAD_n`, `ADAR_RX_LOAD_n`,
`ADAR_TR_n`, plus `TR_SW_POS_n` per group and a shared SPI bus.

| | 4 chips (Nexus) | 8 chips (Extended) |
|---|---|---|
| Total signals | 23 | **43** |

The board is sized for **8 chips / 32 channels**. With the front-end FPGA this stops being a
problem: 43 outputs are trivial for an FTG256, and it additionally allows **applying them all on a
single synchronous strobe**, which is exactly the semantics a coherent array wants. The Kria sends a
compact command over the Pmod and the FPGA expands it.

`[?]` **B-05 remains partly open**: AERIS's published Main Board carries 4 ADAR1000s, and its README
mentions 16 PA boards for the Extended variant (which match 16 channels, not 32). Worth confirming
with the author before freezing the connector.

### 7.3 Why keep the AERIS STM32

`[V]` The STM32 performs **power-up and power-down sequencing** and the quiescent-current
calibration of the amplifiers, via 2× DAC5578 and 2× ADS7830 with INA241A3 current sense amplifiers.

A sequencing fault **destroys the GaN amplifiers**. That code exists, works and is tested. Split by
timing requirement:

| Function | Owner |
|---|---|
| Sequencing, Idq calibration, GPS, IMU, thermal | **AERIS STM32** |
| Beam SPI, `LOAD`, `TR` (pulse-to-pulse updates) | **Front-end FPGA** |
| ADC capture, DDC, decimation, chirp generation | **Front-end FPGA** |
| Pulse compression, Doppler, MTI, CFAR, tracking, AI | **Kria** |

### 7.4 Routing switches

`[V]` **B-03, corrected:** the `M3SWA2-34DR+` is an absorptive GaAs SPDT with an internal driver,
DC–30 GHz — but its datasheet requires **VDD +3.3 V *and* VEE −3.3 V**. The control logic is
positive (`VCTRL` 0 to +3.6 V), which is not the same as a single-rail supply, and an earlier
reading conflated the two. **The charge-pump inverter stays in the power tree.** The draw is
negligible: 1.8 mA maximum per switch, 7.2 mA for four. See
[docs/BLOCKERS_AND_RISKS.md](docs/BLOCKERS_AND_RISKS.md) B-03.

Four SPDTs on the adapter let each converter channel be reassigned between the SDR chain and the
radar chain, enabling mixed mode, SDR I/Q, and **radar I/Q** (needed to tell the sign of the Doppler
shift).

---

## 8. Split of processing

With a front-end FPGA, the fair question is *"then what is the Kria for?"*. The answer is that each
does what it is good at:

| Front-end FPGA (XC7A50T) | Kria KV260 (K26) |
|---|---|
| ADC capture at 400 MSPS | Pulse compression |
| DDC, decimation, CIC/FIR filtering | Doppler FFT, MTI, CFAR |
| Chirp generation and DAC control | Target tracking |
| ADAR1000 fan-out and strobe | **Inference on the DPU**: target classification |
| Level translation | Linux, networking, storage, user interface |
| *AERIS firmware, almost unported* | *Replaces AERIS's Python GUI on a PC* |

That last point is the real value: AERIS ends in a USB link to a PC running a Python GUI. With the
Kria you have an embedded SoC with four Cortex-A53s, a DPU for inference and networking, sitting
right behind the radar.

---

## 9. Power tree

The authoritative version, with currents, dissipation and sources, is
[docs/POWER_AND_STACKUP.md](docs/POWER_AND_STACKUP.md) §1, generated by `_work/power_budget.py`.
In outline:

```
12 V DC jack
  +-- TVS SMBJ15A · PTC · P-MOSFET ideal diode        <- reverse polarity, was missing
  +-- buck 12 V -> +5V0                               1.3 A
        +-- buck -> +3V3_D   logic, DAC DVDD, clock (ADCLK948, Si549), switches, FPGA VCCO
        |     +-- LDO -> +1V8_D   FPGA VCCAUX, AD9484 DRVDD, AD9253 DRVDD
        |     +-- LDO -> +1V2     FPGA VCCO, IAS-facing bank
        |     +-- charge pump -> -3V3   RF switch VEE (B-03)
        +-- buck -> +3V6 -> LDO -> +3V3_A   DAC AVDD, AD8352 drivers   (analogue)
        +-- buck -> +2V5 -> LDO -> +1V8_A   ADC AVDD                   (analogue)
        +-- buck -> +1V0     FPGA VCCINT, sequenced
```

The first draft of this tree had `+3V3_A` as an LDO straight off 5 V and `+1V8_A` off `+3V3_A`.
The budget showed those LDOs dissipating 1.43 W and 0.90 W, the same class of error as Rev01's
ADP151. The analogue rails now have a pre-regulating buck in front of their LDOs.

FPGA power is what grows most against Rev02: it needs a **start-up sequence** and a fair amount of
VCCINT current. A sequencer or an integrated PMIC handles this cleanly.

### 9.1 Corrections still standing from Rev01

| Rev01 | Problem | Rev03 |
|---|---|---|
| `ADP151` as the 1.8 V LDO, *"300 mA"* | It is a **200 mA** part, and with 3.2 V of drop it dissipates 1.6 W in a TSOT-23-5 | LDO of ≥ 500 mA, fed from a **2.5 V pre-regulating buck** (0.35 W). Fed from 3.3 V it would still dissipate 0.90 W |
| `AD9767 AVDD` on the 1.8 V rail | The AD9767 is a **3.3 V** device | To `+3V3_A` |
| A single 3.3 V rail | Digital switching noise on the analogue references | `+3V3_D` and `+3V3_A` separated |
| No reverse-polarity protection | A reversed supply destroys the board | P-MOSFET ideal diode |
| ADAR1000s fed over a ribbon cable from +5 V | >3 A through a ribbon cable | AERIS powers itself |
| Hirose rails used as a power source | Available current unknown | Not used as a power source |

---

## 10. Rev03 BOM

**C** = confirmed · **X** = reasoned candidate · **P** = pending · **D** = dropped.

| Ref | Function | Part | State | Note |
|---|---|---|---|---|
| `U_FPGA1` | Front-end FPGA | XC7A50T-2FTG256I | X | Same as AERIS `[V]`: its firmware runs unported |
| `U_CFG1` | Configuration flash | QSPI 32 Mb | P | |
| `U_ADC1` | Radar ADC | AD9484BCPZ-500 | X | 8 b / 400 MSPS, AERIS's part `[V]` |
| `U_ADC2` | SDR ADC | AD9253BCPZ-125 | X | 14 b, 2 of 4 channels, ≤62.5 MSPS in 1-lane. **AVDD and DRVDD both 1.8 V** (DRVDD abs. max 2.0 V) |
| `U_DAC1` | Radar DAC | AD9708AR | X | AERIS's part `[V]` |
| `U_DAC2` | SDR DAC | AD9767ASTZ | X | Dual 14 b, 3.3 V |
| `U_AMP1..2` | Differential input drivers | AD8352ACPZ | X | Used by AERIS `[V]` |
| `U401` | Reference select + LVPECL 1:8 fan-out | ADCLK948BCPZ | C | Drawn: rev03/CLOCK. Replaces the ADCLK944 + separate selector |
| `Y401` | Programmable master XO, 400/500 MHz | Si549, LVPECL, 3.3 V, 5×7 mm, pinout C | C | Replaces the TCXO; GPS-disciplined through its ±950 ppm DCO |
| `U_SW1..4` | Routing SPDTs | M3SWA2-34DR+ | X | Positive 3.3 V control, but **bipolar supply: VDD +3.3 V and VEE −3.3 V** (B-03). Exposed paddle to GND |
| `U_PWR*` | Bucks, LDOs and sequencer | — | P | Includes FPGA power |
| `U_INV1` | −3.3 V charge-pump inverter | LM2663 or equivalent | X | **Reinstated.** VEE for the four RF switches, 8 mA. It had been dropped when B-03 was closed wrongly |
| `Q_REV1` | Reverse-polarity protection | P-MOSFET + Zener | P | |
| `D_TVS1` | TVS | SMBJ15A | C | |
| `J_PWR1` | DC jack | PJ-102AH | C | |
| `J8` ×2 | Hirose BM20B(0.8)-34DP | — | C | IAS1 functional; IAS0 mechanical and power only |
| `H1..2` | M3 screws through the KV260's corner holes | M3 + standoff | C | `[V]` The original board's holes land on the carrier's within 5 µm (docs/INTERFACE_SPEC.md §5.3) |
| `H3..` | Outer-edge supports | M3 standoff, ~8 mm | P | The widened board overhangs the carrier; 7.9 mm from its underside to the plane of the KV260's feet |
| `J_PMOD1` | Cable to the KV260's Pmod J2 | 2×6, 2.54 mm | P | |
| `J_IF*` | IF and clock SMAs | Edge-mount | P | |
| `J_EXT1` | IDC 2×20 to AERIS | — | P | Up to 8 ADAR1000s |
| ~~`U_MIX1`~~ | ~~ADL5801~~ | | **D** | Does not reach 10.5 GHz; AERIS does the mixing |
| ~~`U_PWR3`~~ | ~~ADP151~~ | | **D** | 200 mA is not enough |
| ~~`U_DEC1`~~ | ~~74HC138~~ | | **D** | The FPGA does the fan-out |
| ~~8× `U_ADR`~~ | ~~ADAR1000~~ | | **D** | Supplied by AERIS |

---

## 11. Alternatives to the KV260

Worth saying clearly: **the KV260 is I/O-poor for this project.** Eight differential pairs and
fourteen loose signals is very little. If the radar is the real goal, it is worth weighing:

| Option | I/O available | Cost |
|---|---|---|
| **KV260 + front-end FPGA** *(this architecture)* | 8 pairs, in-house serial link | One FPGA on the adapter |
| **KR260** (Robotics Starter Kit) | 4× Pmod, PL Ethernet, more I/O | Change board |
| **Custom carrier for the K26 SOM** | ~180 user I/O + **4 GTH lanes at 12.5 Gb/s** | Design a 240-pin carrier |

The third enables JESD204B and removes all of this gymnastics, in exchange for a considerably larger
project. I am not proposing it, but it should be on the table before committing.

---

## 12. Regulatory compliance

| Subsystem | Position |
|---|---|
| **Receive** | No emission restriction. Watch for LO re-radiation from the antenna: mixer isolation has to be guaranteed `[E]` |
| **SDR transmit** | Requires an **amateur radio licence** and staying within allocated bands. FM broadcast, airband and PMR446 are **receive-only** here |
| **Transmit at 10.5 GHz** | `[?]` **Check the national allocation table.** Not a licence-free ISM band everywhere. With 10 W GaN amplifiers per channel, the Extended variant is not equipment you simply switch on |
| **EMC** | A bench prototype needs no CE marking; distributing the equipment does |

**Design recommendation:** switchable 50 Ω loads on the TX outputs, so the whole system can be
validated in conducted loopback without radiating. It costs almost nothing and unblocks bring-up
without depending on a licence.

---

## 13. Related documents

| Document | Contents |
|---|---|
| [docs/VEHICLE_PLATFORM.md](docs/VEHICLE_PLATFORM.md) | The system this board belongs to |
| [docs/BLOCKERS_AND_RISKS.md](docs/BLOCKERS_AND_RISKS.md) | The 5 blockers closed, with evidence and sources, plus open risks |
| [docs/AUDIT_Rev01.md](docs/AUDIT_Rev01.md) | What the repository files actually contain |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Staged plan with exit criteria |
| [docs/HISTORY_Rev01.md](docs/HISTORY_Rev01.md) | Record of earlier work and its assessment |

---

*Rev03 · 21 September 2026. The open decision is §2.3: whether the front-end FPGA is accepted. The
whole schematic depends on that answer.*
