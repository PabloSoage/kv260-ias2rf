# Rev08 — plan and analysis

*16 November 2026 · analysis and plan only: nothing in the schematic, the board or the gateware has changed*

> **Status.** Scope approved on 16 November 2026: **all of it** (WP1–WP6 and the 500 MSPS gateware of
> section 7), the thirteenth SMA on the back wall, the camera pass-through receptacle, and a vertical debug USB
> inside the box. Section 12 records the decisions. Nothing is to be bought yet: parts are chosen for the
> design, and their stock is re-checked when the board is ordered. Implementation has not started; it begins
> with phase 1 of section 11 when the owner says so.

Rev07 closed the final RF review. This document studies what a Rev08 could add so that the board needs less
around it, and what a fresh look at Rev07 still finds to correct. It answers six questions:

1. Can the board show its own state (LEDs)?
2. Can it have a serial port for debugging?
3. Can the unused IAS0 connector do something?
4. Can it receive FM, airband, VHF and UHF handhelds with nothing external but the antenna?
5. What about above 500 MHz?
6. Is anything else wrong in Rev07, board or gateware?

Marks: **[V]** measured or read today from the board file, a datasheet or a tool; **[E]** an estimate, with its
basis. Stock and prices are JLCPCB's parts API on 16 November 2026.

---

## 0. Summary

| # | Work package | Verdict | Board area | Parts cost per board | Risk |
|---|---|---|---|---|---|
| WP1 | Status LEDs: 5 rail LEDs, 8 status LEDs behind an I²C expander | **Approved** | 40 mm² | $1.1 | Low |
| WP2 | Debug serial: UART on the two spare Pmod lines, USB bridge with a vertical USB-C inside the box | **Approved.** The gateware half needs no board change | 60 mm² | $1.1 | Low |
| WP3 | IAS0: camera pass-through receptacle on the top face, pin for pin | **Approved**, fitted | 30 mm² | $0.2 | Low electrically, medium mechanically |
| WP4 | VHF receive front end, 30–170 MHz, direct sampling on the AD9484: own SMA (the thirteenth), bias tee, LNA, three preselector paths, anti-alias filter, IF amplifier, step attenuator | **Approved** | 430 mm² | $32 | Medium |
| WP5 | Converter for 170 MHz – 3 GHz: RFFC5072 mixer and synthesiser, second preselector | **Approved**, behind a bypass switch so the board works without it | 260 mm² | $34 | Medium–high |
| WP6 | Corrections from the audit (section 8): two timing-constraint errors, a hard-coded NCO, documentation | **Approved**, first; independent of the board | — | — | Low |

Totals: about 820 mm² of the 1,090 mm² that is free in one block (section 1), about $68 of parts per board in
some 17 new part types, and 0.8 W more at 12 V (+9 %).

**What the audit found (section 8).** Two timing constraints in `xc7a50t.xdc` do not describe the clocks the
board produces, so "timing closed at 400 and 500 MHz" is true for the master-clock domain only. The radar DDC's
NCO is a constant for 400 MSPS. `FPGA_GATEWARE.md` §4.1 and one line of the README give sample rates and
connector names that are wrong. None of this needs a board change.

**Two statements made before this analysis were wrong and are corrected here.**
- "FM fits the second Nyquist zone of the wideband channel at 125 MSPS." The AD9253 runs at 62.5 MSPS (50 MSPS
  with the 400 MHz master) [V], and the FM band straddles a zone boundary at both rates (93.75 and 100 MHz).
- "Airband is in the third zone." It straddles 125 MHz.

The board already has the right converter for these bands: the AD9484 at 400 MSPS, which `SW2` connects to
`J922`. Its first Nyquist zone is 0–200 MHz, so FM, airband, 2 m and marine VHF are all sampled directly. What
is missing is everything between the antenna and that ADC: gain, filtering and level control. That is WP4.

---

## 1. Where the room is

Measured from `CSI2-KRIA-KV260_Rev01.kicad_pcb` as text, per copper layer [V].

| Area | KiCad x, y (mm) | Size | Top | L3 / L6 / bottom | Limits |
|---|---|---|---|---|---|
| **Block north-west of the FPGA** | 89–150, 107.25–127 | 61 × 19.7 mm, 1,200 mm² | `J1002`, `C1092`, `F1002` (the fan header's parts), `FID1`, `H1` | Empty but for two tracks on L3 at its east end (`FPGA_PROG_B` and a DAC filter net) | Over the carrier for y < 117.75: 0.8 mm underneath, so no through-hole pins and nothing on the bottom there. `H1`'s clamp takes a 10 mm circle. Net free area about 1,090 mm² |
| **IAS0 tongue** | 129.9–142.4, 82.75–107.25 | 12.5 × 24.5 mm | Empty | `J102` on the bottom, ground vias only | All of it is over the carrier. `J18` on the carrier (7.5 mm pins) stands 1.5 mm east of it |
| Strip above the SMAs | 100–176, 188–200 | — | `IF_TX_A`, `IF_TX_B`, `T802`, the Rev07 filter, `IF_RX_B`, `H4` | L6 carries the AD9767's DAC2 outputs and `SW_CTRL0` | Not usable for new blocks; a route can cross it on L6 |
| Left edge below the block | 89–100, 128–200 | — | The 5 V, 3.3 V and −3.3 V converters | **L6 empty** | A route on L6 passes under the converters between two ground planes |

![Placement study](img/rev08_floorplan.png)

The sketch places every new block at its real size. It is a study, not a layout: gate G1 in section 11 is a
placement trial on a scratch copy of the board.

**Which edges reach the outside.** The board's left edge (x = 89) faces the enclosure's back wall, 3 mm away,
where the 12 V jack already has its opening. The north edge is over the carrier, inside the box. So a new
connector for the outside goes on the left edge, between `H1`'s clamp (ends at y 117.25) and the 5 V buck's
input capacitors `C1007`/`C1008` (start at y 131.2): **13.9 mm** [V]. An edge SMA needs 7.2 mm and a USB-C
9.2 mm. Both do not fit; the SMA takes the edge (section 5.6) and the USB connector goes inside (section 3).

---

## 2. Control lines: what is available without new FPGA balls

The FPGA has 32 unconnected I/O balls [V], and CONTROL_SPEC §7 found that none can still be routed out. Rev08
therefore uses what already arrives at the free block:

| Resource | Where it is today [V] | Use in Rev08 |
|---|---|---|
| `XO_SCL` / `XO_SDA`: an I²C bus the FPGA masters, 3.3 V, only the Si549 on it (address 0x55) | Its tracks run inside x 152–194, y 126–150: they touch the block's east end | Two TCA6416A expanders (0x20, 0x21): 32 static lines for the switches, the attenuator, the synthesiser's serial port and the LEDs |
| `PMOD_SPARE1` (FPGA input, ball G15) and `PMOD_SPARE2` (FPGA output, G11) | From the FPGA to `J1102` pins 6 and 8, x 154–160, y 115–147 | The debug UART. Their present uses are soft: spare1 gates the DDC, spare2 reports link-up; both move to register bits |
| IAS0 pin 15 (`HPA14_FLASH`, into the SOM) and pin 20 (`HPA14_TRIGGER`, out of the SOM), 1.8 V, through the carrier's SN74AVC4T245 `U72` | On `J102`, not connected | **Not used by the board.** Studied and rejected (section 4.2); they pass through to the camera |

**One bus, two rules.** The expanders sit on the Si549's bus. (a) Nothing may toggle on it while receiving:
LED states are written on change only, never blinked through I²C. (b) The gateware's `hk_xo_ctrl` becomes a
shared master with a queue. Clocking the synthesiser's 25-bit words through an expander costs two writes per
bit: about 4 ms per word at 400 kHz, some 25 ms for a retune [E]. That suits a tuned receiver, not a frequency
hopper. A faster port would need three FPGA balls, and there are none.

Rejected: the housekeeping bus (`HK_SCL`/`HK_SDA`, 1.8 V). Linux could drive the expanders on it with a stock
driver and no gateware, but the bus ends 60 mm from the block, it already has two masters, and the front end
would stop working when the board runs from Ethernet without the Kria.

---

## 3. WP1 and WP2 — LEDs and a debug serial port

### 3.1 LEDs

Today the board has `D1101` (DONE) and the two LEDs in the RJ45 [V].

| LED | Driven by | Meaning |
|---|---|---|
| `+12V`, `+5V0`, `+3V3_D`, `+1V8_D`, `+1V0` | The rail itself, 1 mA each | A dead rail shows without a meter. `+1V0` needs a transistor (below an LED's forward voltage) |
| `CFG` | Expander, written once after configuration | The FPGA runs and the clock sequencer finished (`xo_boot_done`) |
| `CLK` | Expander | Master clock mode: on = 500 MHz, off = 400 MHz |
| `LINK` | Expander | IAS1 link trained |
| `ADC-R`, `ADC-S` | Expander | A converter clipped since the last read (sticky) |
| `LO` | Expander | The RFFC5072 is locked |
| `TX` | Expander | A DAC is driving an SMA |
| `ERR` | Expander | Any sticky error: CRC, FIFO overflow, I²C no-acknowledge, over-temperature |

Activity is shown by the UART's transmit line: one LED on `PMOD_SPARE2` blinks with every status line the FPGA
prints, once a second. That is the heartbeat, and it costs no bus traffic.

Placement: a row at the left edge, just south of `J961` (KiCad y 125–131), so they show through a 2 mm slot in
the back wall beside the antenna connector. Parts: KT-0603R class LEDs (basic part, 5.7 M in stock),
TCA6416ARTWR (33 k in stock, $0.82).

### 3.2 Debug serial

| Option | Board change | Gateware | Works with the lid on | Works without the Kria |
|---|---|---|---|---|
| **A. UART on `PMOD_SPARE1/2` to the Kria** (PS UART1 through EMIO, `/dev/ttyPS1`) | None | `dbg_uart` on the Artix, two EMIO pins on the Kria | Yes | No |
| **B. USB bridge on the board**, tapping the same two nets | CH340X, USB-C, ESD, 1 kΩ | Same as A | Only with a hole in the lid | Yes |
| C. UART through JTAG (`BSCANE2`) | None | A JTAG-UART core and a host script | No | Yes, with a JTAG cable |
| D. A text console on a UDP port | None | A second UDP port in `eth_mac_udp` | Yes | Yes, once Ethernet is up |

**Proposal: A and B together**, one gateware block.

- `dbg_uart`, 115,200 baud 8N1 by default: a boot banner (build date, git hash, clock mode), one status line a
  second (lock bits, link state, clip counters, die and board temperature, error flags), and a monitor that
  reads and writes the register file (`r 44`, `w 44 12345678`). About 300–400 LUTs [E]; the device is at 48 %.
- The bridge is powered from the USB cable, so it adds nothing to the board's rails and enumerates with the
  board off. Its TXD reaches `PMOD_SPARE1` through 1 kΩ: the Kria's driver wins when the Pmod cable is fitted,
  and an unpowered FPGA sees at most 3 mA.
- **The connector cannot go on the back wall** (section 1). **Decided: a vertical USB-C inside the box**, on
  the IAS0 tongue at KiCad x 131–141, y 93.5–103.5, reached with the lid off, like JTAG and the Pmod. With the
  lid on, the same console is on the Kria (option A).
- **Why the tongue, and what it demands of the part.** It is the only free top area left once WP4 and WP5 fill
  the block. It is clear of the camera (section 4.3: the module lies across the tongue at y 81–90), of the
  lid's fan (enclosure X −65 to −15; the tongue is at X 0–24.5) and of the KV260's own fan. But the tongue lies
  over the carrier, 0.8 mm above it: **the connector must be surface-mount only, shell tabs included**. A
  vertical USB-C is about 10 mm tall, which leaves 20 mm to the lid.
- Candidates in stock today [V]: U262-161N-4BVC11 (XKB, 35 k, $0.41; its second source SH-U262-161N-4BVC11,
  18 k), JS16L-TYPE-C423-H100 (Jushuo, 1.7 k), HX-TYPE-C 16P 180 H10.0 (3.6 k). Their drawings decide: any with
  through-hole shell legs is out. Fallback if none places: a 1 × 4 header for a USB-TTL cable, same position.

Stock: CH340X 43 k ($0.66), USBLC6-2SC6 38 k.

---

## 4. WP3 — IAS0

### 4.1 What IAS0 carries on the carrier

Read from the carrier schematic XTP682, sheet 13, connector `J7` [V] (the file is AMD's and is not in this
repository):

| `J7` pin | Carrier net | Goes to |
|---|---|---|
| 4/5, 7/8, 10/11, 26/27, 29/30 | `IAS0_D0`, `IAS0_CLK`, `IAS0_D3`, `IAS0_D2`, `IAS0_D1` | The AP1302 ISP's sensor port. Not the SOM |
| 14, 22 | `IAS0_SCL`, `IAS0_SDA` | The AP1302's own sensor I²C master |
| 21, 32 | `IAS0_RESET`, `IAS0_EXTCLK` | AP1302 pins: dead until its firmware runs |
| **15** | **`HPA14_FLASH`** | **Into the SOM** (`HPA14_P`) through `U72`, 1.8 V on this side |
| **20** | **`HPA14_TRIGGER`** | **Out of the SOM** (`HPA14_N`) through `U72`, 1.8 V |
| 13; 17, 18; 23, 24 | `PL_1V8`; `IAS_2V75`; `PL_1V2` | Carrier rails |
| 34 | `VDD_AF2V8_J7` | 2.8 V through jumper `J18` |

So ARCHITECTURE §1.1's open question has an answer: the I²C and reset do not reach the SOM, but **pins 15 and
20 do**. Feeding our own data into the MIPI lanes is not possible: the AP1302 expects a specific sensor and its
firmware.

### 4.2 Pins 15 and 20: are they any use to the board?

**What they are.** Two single wires between IAS0 and programmable-logic pins of the K26, `HPA14_P` and
`HPA14_N`, through the carrier's level translator `U72` (SN74AVC4T245). Their directions are fixed by the
carrier, not by software: pin 15 can only carry a signal **into** the SOM, pin 20 only **out of** it, both at
1.8 V [V, XTP682 sheet 13: `U72`'s 2DIR is tied high, 1DIR low; the same arrangement serves IAS1, where pin 15
is already the board's `FPGA_IRQ`]. They are the camera's flash and trigger lines.

**What they could do for the board, and why each use was rejected.**

| Possible use | Why not |
|---|---|
| Pin 15 as a second interrupt to Linux (front end unlocked, bias-tee fault, clipping) | The FPGA already masters the expanders and already has an interrupt to the SOM (`FPGA_IRQ`, IAS1 pin 15) and a register file Linux reads over the link. A second interrupt adds nothing the first cannot carry |
| Pin 20 as an enable or reset of the front end from Linux | The front end is useless without the FPGA: its samples, its switches and its synthesiser all go through it. The FPGA can switch the 3.0 V rail itself through an expander |
| A timing or trigger line (PPS, radar sync) | The Pmod already carries `PPS_SYNC` and `BEAM_STROBE`, and IAS1 the link clocks |
| Any fast or bidirectional signal | Fixed direction, a CMOS translator, and only one wire each way |

**Conclusion: they are of no real use to this board.** Two wires that need a level shifter, a pull resistor and
a jumper each, to duplicate what IAS1 and the Pmod already do. They are left to their own purpose: they pass
through to the camera receptacle with every other IAS0 pin (section 4.3), so a module that uses flash or
trigger works exactly as on the bare carrier.

### 4.3 Camera pass-through

A second connector on the tongue's top face, wired pin to pin to `J102`, so that an IAS camera module still
plugs in above the adapter and the KV260 keeps its AP1302 camera (radar and camera on the same platform).

- **Part.** `J102` is the header (BM20B(0.8)-34DP). The carrier's `J7` and the new `J103` are the receptacle,
  **BM20B(0.8)-34DS-0.4V(51)**: 18,191 in stock, $0.18 [V].
- **Geometry** [V, Hirose BM20 catalogue]. Receptacle land pattern: pads 0.23 × 0.42 mm, rows 2.18 mm apart.
  `J102`'s pads are 0.23 × 0.60 mm, rows 1.50 mm apart. With `J103` centred on `J102`, pad *n* on the top is
  directly over pad *n* on the bottom, overlapping it by 0.17 mm in plan. The connection is a via beside each
  pad pair: no crossing, no length to match.
- **Vias.** The board's 0.45 / 0.20 mm via does not fit a 0.4 mm pitch in line (0.06 mm to the next pad). Two
  staggered ranks outside each row do: the edge-side row's outer rank sits 0.43 mm from the board edge
  (minimum 0.30). 34 vias, 23 nets; the 11 grounds stitch every plane, and each lane pair (4/5, 7/8, 10/11,
  26/27, 29/30) has a ground pin on both sides, a ground–signal–signal–ground crossing.
- **Signal integrity** [E]. The added path is 1.6 mm of via and two stubs of about 0.6 mm: 15 ps, against a
  D-PHY rise time above 100 ps. The pair's two vias sit in different ranks, 0.55 mm apart: under 4 ps of skew.
  It is one more mated BM20 pair in a link that already has one.
- **Mechanics, not verified.** onsemi's AR1335 IAS module is listed as 8.74 × 24.18 mm with this 34-pin
  header. It would sit 2.4 mm higher than on the bare carrier, overhanging the 12.5 mm tongue sideways. The
  module drawing was not available: its outline in the sketch is an estimate, and its orientation and its
  clearance to `J18` must be checked with a module in hand. A 0.8 mm connector does not hold a module in a
  vehicle: the lid needs a clamp over it and a window for the lens (lid inner face 30.4 mm above the board).

- **Every pin passes through, none is used.** The 23 nets of `J102` become carrier nets on this board: the five
  lanes, the AP1302's I²C, reset and clock (`IAS0_SCL/SDA`, `IAS0_RESET`, `IAS0_EXTCLK`), the flash and trigger
  lines of section 4.2, and the rails the camera draws from the carrier (`PL_1V8` pin 13, `IAS_2V75` 17–18,
  `PL_1V2` 23–24, `VDD_AF2V8_J7` 34 through the carrier's `J18`). The BM20 contact is rated 0.3 A, so each
  doubled rail carries up to 0.6 A; each rail gets two vias. Nothing on the adapter connects to any of them,
  so a wrong camera, or none, cannot disturb the board.
- **Lid** (section 9). A window for the lens over the tongue and a clamp that holds the module down on its
  connector, with a TPU pad, as the enclosure's other clamps.

**Verdict. Approved and fitted.** Electrically simple and nearly free; the open points are mechanical: the
module's outline, its clearance to the carrier's `J18`, and the clamp. They close with a module in hand before
the lid is printed (risk register).

---

## 5. WP4 and WP5 — VHF/UHF receive front end

### 5.1 What is there, and why it is not enough

| Path | Converter | Rate [V] | First Nyquist zone | Filter |
|---|---|---|---|---|
| `J951` | AD9253 channel B, 14 bit | 62.5 / 50 MSPS | 31.25 / 25 MHz | Rev07 low-pass, 30 MHz |
| `J911` | AD9253 channel A, 14 bit | 62.5 / 50 MSPS | 31.25 / 25 MHz | None |
| `J922` through `SW2` | AD9484, 8 bit | 400 MSPS (500 with the other master) | 200 MHz | None |

`J922` into the AD9484 already samples 0–200 MHz. Its noise figure at the SMA is about **27 dB** and its full
scale about −17 dBm [E: AD9484 47 dBFS and 1.5 V p-p behind 25 dB of AD8352, AD8352 2.7 nV/√Hz]. That is a
noise floor of −106 dBm in 12.5 kHz: a narrow-FM signal needs about −94 dBm (4.5 µV) to be readable, some
25 dB worse than a handheld's own receiver. And without a filter everything from 200 MHz to 1 GHz folds onto
the band. So the ADC is right and the front of it is missing.

Above 200 MHz the same ADC can only undersample. For 400–470 MHz that needs a band-pass that rejects
television at 470–700 MHz within a few percent of the band edge, at either sample rate. That is not an LC
filter. Above 200 MHz the board needs a mixer.

### 5.2 Architectures compared

| Architecture | Coverage | Parts in stock at JLCPCB [V] | Verdict |
|---|---|---|---|
| TV-tuner IC (R820T2, R828D, MSi001), IF into the AD9253 | 24–1766 MHz, 8 MHz wide, image-free | **None: 0 stock, consignment only** | Rejected: the simplest circuit, but not buyable through the board's assembly flow, and the R82xx data sheets are not public |
| Quadrature demodulator (ADL5387, LTC5584, AD8348) + PLL, I and Q into the AD9253's two channels | 30 MHz – 2 GHz, 50 MHz wide, 14 bit | ADL5387: 7; the others: 0 | Rejected for stock. It would also take the HF channel away while in use |
| Dual conversion through a 2.4 GHz IF (two RFFC5072, as the HackRF does with one plus a transceiver) | 30 MHz – 4 GHz, image-free | RFFC5072: 64 | Deferred: two synthesisers, twice the area and 0.8 W; section 6 |
| **Direct sampling below 170 MHz, single conversion above, both into the AD9484** | 30 MHz – 3 GHz | All parts in stock | **Proposed** |

### 5.3 Block diagram

```
J961 ─ ESD ─ DC block ─┬─ LNA ─┬─ preselector ─┬─ RFFC5072 ─┬─ low-pass ─ IF amp ─ attenuator ─ L6 stripline ─ SW2 ─ AD8352 x2 ─ AD9484
 SMA     bias tee ─────┘ bypass┘  A or B        └─ bypass ───┘  170 MHz    +21 dB   0–31.5 dB     150 mm        RF2
                                                  LO 85–4200 MHz, TCXO 26 MHz
```

| Block | Part | Stock, price [V] | Key figures |
|---|---|---|---|
| Antenna connector `J961` | SMA-J-P-H-ST-EM1, as the other twelve | 114, $5.45 | Left edge, back wall |
| Bias tee | AP22652 current-limited switch, two inductors, 3.0 or 5 V selectable | 8.5 k, $0.33 | Feeds an active antenna or a mast-head LNA; fault flag to an expander |
| LNA and IF amplifier | SPF5043Z × 2, at 3.0 V | 5,923, $3.39 | 50–4000 MHz; 22.6 dB and NF 0.60 dB at 100 MHz, 18 dB at 900 MHz, 25 mA at 3 V |
| Bypass switches | PE4259 × 4 | 14.7 k, $1.19 | 10 MHz – 3 GHz SPDT |
| Preselector A, 30 MHz up | PE42442 × 2 (SP4T, 30 MHz – 6 GHz) | 245, $4.95 | Paths: straight, FM band-pass, FM-reject high-pass, to preselector B |
| Preselector B, 170 MHz up | SKY13418-485LF × 2 (SP8T, 0.1–3.8 GHz) | 4,562, $1.02 | Paths: UHF low-pass 480 MHz, SAW 1090 MHz (TA1090EC, 149), LTCC high-pass 1 GHz (HFCN-1000+, 302), LTCC low-pass 1 GHz (LFCN-1000+, 615); four spare |
| Converter | **RFFC5072** | **64**, $14.62 | LO 85–4200 MHz, mixer 30–6000 MHz, gain −2 dB, NF 10–13 dB, IIP3 +23 dBm, 125 mA at 2.7–3.3 V, reference 10–104 MHz |
| Baluns | TC1-1-13M+ × 2 | 239, $2.12 | 4.5–3000 MHz |
| Reference | 26 MHz TCXO (KDS 1XXD26000MAA) | 15.7 k, $0.61 | Not locked to the Si549: section 5.9 |
| Anti-alias filter | 7th-order elliptic, 0402 | — | Section 5.4 |
| Step attenuator | PE4312 | 1,557, $2.84 | 0–31.5 dB in 0.5 dB steps, serial |
| Supply | LP5907-3.0 from `+3V3_D` through a ferrite | 32 k, $0.28 | One 3.0 V rail for the whole block |

The frequency ranges of the PE42442, PE4259, PE4312 and TC1-1-13M+ are quoted from memory of their data
sheets [E] and are confirmed when the schematic is drawn; the others were read today.

### 5.4 The three filters the plan depends on

Each was optimised as a 7th-order elliptic ladder with lossy inductors, the method of the Rev07 filter
(`_work/sim/rev08_frontend.py --filters`) [V, ideal element values]:

| Filter | Pass band | Stop band | Inductor Q | Loss in band | Rejection |
|---|---|---|---|---|---|
| Anti-alias for 400 MSPS | 30–170 MHz | from 230 MHz | 50 | 0.1–1.5 dB | **≥ 55.0 dB** |
| FM reject, for airband and VHF | 118–170 MHz | 87–108 MHz | 55 | 0.5–3.2 dB | **≥ 44.9 dB** |
| UHF image filter | 400–480 MHz | from 660 MHz | 60 | 0.5–1.4 dB | **≥ 50.4 dB** |

All three meet their masks. Not done yet: snapping to catalogue values and the tolerance Monte Carlo. The
FM-reject filter has a 9 % transition (108 → 118 MHz) and will be the sensitive one; it sits after the LNA,
where 3 dB of loss costs nothing.

### 5.5 Sensitivity and range

`_work/sim/rev08_frontend.py`, maximum gain [V arithmetic on E inputs]:

| Mode | Gain | Noise figure | Full scale at the antenna | Noise floor in 12.5 kHz |
|---|---|---|---|---|
| Direct, 30–170 MHz | 34.9 dB | 2.0 dB | −51.9 dBm | −131 dBm |
| Direct, FM broadcast | 32.9 dB | 2.3 dB | −49.9 dBm | −131 dBm |
| Direct, airband and VHF | 31.9 dB | 2.5 dB | −48.9 dBm | −131 dBm |
| Converted, UHF 400–480 MHz | 29.3 dB | 3.7 dB | −46.3 dBm | −129 dBm |
| Converted, ADS-B 1090 MHz | 23.4 dB | 7.1 dB | −40.4 dBm | −126 dBm |
| Converted, general coverage | 24.9 dB | 6.1 dB | −41.9 dBm | −127 dBm |

- The attenuator takes off up to 31.5 dB and the LNA bypass another 22 dB, so full scale moves from −52 dBm
  to about +2 dBm.
- **The 8-bit ADC sets the dynamic range**: 47 dB in 200 MHz, which is 89 dB in one 12.5 kHz channel.
  Everything inside the selected preselector path shares that range, so the strongest signal in the path sets
  the gain. That is why FM broadcast has its own path and airband its FM-reject path.
- Compared with today's bare `J922` (NF 27 dB), the improvement is about 25 dB.

### 5.6 Frequency plan at 400 MSPS

| Band | LO | Image | LO as seen by the ADC | Image rejection |
|---|---|---|---|---|
| 30–170 MHz | none | none | — | Aliases from 230 MHz up: ≥ 55 dB |
| PMR446, 446 MHz | 581 MHz | 716 MHz | 181 MHz | ≥ 50 dB (UHF low-pass) |
| 70 cm, 435 MHz | 570 MHz | 705 MHz | 170 MHz | ≥ 50 dB |
| TETRA, 390 MHz | 525 MHz | 660 MHz | 125 MHz | ≥ 50 dB |
| ADS-B, 1090 MHz | 955 MHz | 820 MHz | 155 MHz | ≥ 40 dB (SAW) [E] |
| 868 MHz, GNSS L1, 2.4 GHz | ±135 MHz | ±270 MHz | — | **None**: section 6 |

The IF is centred on 135 MHz and 100–170 MHz reaches the ADC: 70 MHz at once. The LO is always above 230 MHz,
in the anti-alias filter's stop band, and it is one tone at a known frequency. From 170 to 480 MHz the
converter works behind the UHF low-pass; below 390 MHz its image rejection falls with the filter's skirt.

### 5.7 Getting the IF to the ADC

- **Route.** 50 Ω stripline on L6 (0.151 mm, between the L5 and L7 ground planes, LAYOUT §3), from the block
  down the left edge and east along the strip above the SMAs to `SW2`: about 150 mm, 0.5 dB at 170 MHz [E]. L6
  is empty along the left edge [V]. In the strip it meets the AD9767's DAC2 outputs on the same layer [V]: it
  crosses them at right angles through L3, or keeps 1.5 mm. To be shown by routing it on a scratch copy.
- **Connection.** `SW2`'s RF2 throw connects to `J922` through `C926` today. A second footprint for that
  capacitor selects the source: `J922` (as built until now) or the IF line. No new switch in the path, and the
  radar's throw (`J921` → RF1) is untouched. With the IF line fitted, `J922` is free; it can carry the IF out
  for an external receiver.

### 5.8 Control lines (expander 0x20, supplied from the 3.0 V rail on its port side)

| Lines | Function |
|---|---|
| 2 | PE42442 pair, path select |
| 3 | SKY13418 pair, path select |
| 1 + 1 | LNA bypass, converter bypass |
| 1 + 1 | Bias tee enable, bias tee fault (input) |
| 3 | RFFC5072 serial port (ENX, SCLK, SDATA) |
| 1 + 1 | RFFC5072 lock detect (input), reset |
| 1 | PE4312 latch (shares SCLK and SDATA) |
| 1 | Spare |

### 5.9 Open points of this block

| Point | Why it is open | How it closes |
|---|---|---|
| RFFC5072 logic thresholds and serial timing | The data sheet could not be fetched today (Qorvo and Mouser refused the requests); the figures above are from Qorvo's product page and search extracts | Read the data sheet before the schematic. The expander runs at 3.0 V, the part's own supply, so levels are not expected to be an issue |
| RFFC5072 stock | 64 units today, and the A version has none. Nothing is bought during the design | Designed in as the RFFC5072; re-check stock when the board is ordered. Fallback, kept in the schematic as a note: MAX2871 (3,065) with an ADE-1+ mixer (139), about 60 mm² more |
| Switches below their specified band | SKY13418 is specified from 100 MHz, so it only carries paths from 170 MHz up. PE42442 is specified from 30 MHz | Bench check of loss at 30–100 MHz on the first board |
| Reference not locked to the ADC clock | A separate TCXO: the LO and the sample clock drift apart by a few ppm. Harmless for voice and data reception; not for phase-coherent work | Option: feed the synthesiser's reference from `J401`'s 10 MHz when one is connected |
| Shielding | An LO from 85 MHz to 4.2 GHz 40 mm from the JTAG and Pmod headers and 60 mm from the FPGA | Two shield-can frames (LNA and preselector; converter), ground-via fence, the 3.0 V rail's ferrite; coupling estimate as `txrx_isolation.py` |
| Placement density | 820 mm² of blocks in 1,090 mm² | Gate G1 |

---

## 6. Above 500 MHz

What Rev08 as proposed gives:

| Range | How | Image rejection |
|---|---|---|
| 170–480 MHz | Converter behind the UHF low-pass | ≥ 50 dB from 390 MHz up, falling below |
| 1090 MHz | Converter behind a SAW | ≥ 40 dB [E] |
| Any other band with a SAW or LTCC filter narrower than 270 MHz | One of preselector B's four spare paths (433 MHz and GNSS L1 SAWs are stocked; 868 MHz has 4 units) | That filter's |
| 480 MHz – 3 GHz, general coverage | Converter behind a 1 GHz low-pass or high-pass | **None within 270 MHz**: a signal 270 MHz from the tuned one lands on it. Software can pick the LO side whose image is quiet, and can tell images apart by retuning the LO (real signals stay, images move). Good for looking at a band, not for unattended reception next to strong transmitters |
| 3–4.2 GHz | Same, outside the SKY13418's range, LNA gain falling to 7 dB | None |

For image-free coverage of everything the answer is dual conversion: a first RFFC5072 up to a 2.45 GHz IF, a
band-pass there (BFCN-2450+, 80 in stock), a second RFFC5072 down to 135 MHz. It adds one synthesiser, about
250 mm², 0.4 W and $25. **Not in Rev08, because it does not fit**: WP4 and WP5 already take about 820 of the
1,090 mm² of the free block, and the tongue holds the camera and the USB connector. It is the first candidate
for Rev09 if the single-conversion chain proves itself. Preselector B's four spare paths are the way to add
specific bands meanwhile, each with its own SAW or LTCC filter and no layout change.

Transmit above 30 MHz is not part of this plan.

---

## 7. Gateware that Rev08 needs

| Item | What | Notes |
|---|---|---|
| G-1 | `dbg_uart` on the Artix; PS UART1 on EMIO on the Kria; the two soft functions of the spare lines moved to register bits | Board-independent: can be built and tested now |
| G-2 | `hk_xo_ctrl` becomes a shared I²C master: Si549, two TCA6416A with shadow registers, interrupt handling | No traffic while receiving, except on request |
| G-3 | RFFC5072 and PE4312 serial sequencers over the expander; lock detect read back | Bench model of both parts' serial ports |
| G-4 | Tunable DDC for the AD9484 stream. The AERIS DDC's NCO is a constant (section 8, A-3): make it a register, default unchanged, and add a second decimation stage down to channel bandwidths | **Only 10 of 120 DSP48 are free** [V]: the second stage has to be CIC plus a distributed-arithmetic FIR |
| G-5 | AGC: a clip and peak detector on the raw ADC codes drives the attenuator and the LNA bypass, in the FPGA or from Linux | Hold-off so that it does not chatter on bursts |
| G-6 | Status-LED mapping, written on change | — |

**Sample-rate consequence.** The gateware closes timing for the AD9484 at 400 MSPS only (section 8, A-1). The
front end is therefore planned at 400 MSPS, and in that mode the AD9253 runs at 50 MSPS: 25–30 MHz folds onto
20–25 MHz on the HF port (SIGNAL_INTEGRITY §9.9). Receiving HF to 30 MHz and VHF/UHF at the same time needs
the 500 MHz master and a polyphase rewrite of the capture and first DDC stage (two samples per clock at
250 MHz).

| Item | What | Notes |
|---|---|---|
| G-7 | **500 MSPS radar/VHF capture**: the AD9484 path at 500 MHz as two samples per 250 MHz clock (polyphase NCO and CIC), so that HF to 30 MHz on the AD9253 (62.5 MSPS) and VHF/UHF on the AD9484 run at the same time | In scope (full scope approved). The largest gateware item: the AERIS DDC is verbatim third-party code and stays as it is for 400 MSPS; G-7 is a second, selectable path. Its DSP48 cost decides whether it replaces G-4's second stage. Until it exists, A-1's gating holds |

---

## 8. Audit of Rev07: what a fresh look found

Board: nothing new that needs a change. The findings are in the gateware constraints and the documentation.

| # | Severity | Finding | Evidence [V] | Correction |
|---|---|---|---|---|
| **A-1** | **High** | In 500 MHz mode the AD9484 samples at 500 MSPS, but its capture and DDC domain is constrained for 400 MSPS only, and it is the tightest domain of the design | `xc7a50t.xdc` line 229: `clk_adcr_dco` 5.000 ns, no second clock. `timing_summary.rpt`: `clk_400m_unbuf` 2.500 ns, WNS **+0.111 ns** over 6,056 endpoints. At 2.000 ns that is about −0.39 ns. Nothing in `top.v` gates the domain by clock mode | Hold `u_adc_cap` and `u_ddc` in reset whenever the master is 500 MHz, and say so in the documents; or add the 4.000 ns clock and close timing, which the DSP48-based DDC is unlikely to reach. "WNS +0.111 ns at 400 and 500 MHz" in README, `fpga/README.md` and the PDF is true for the master-clock domain only and must be reworded. Rev07's review of the clock rework missed this |
| **A-2** | **Medium** | The AD9253's bit clock is constrained at half its real frequency | `xc7a50t.xdc` line 230: `clk_adcs_dco` 4.000 ns (250 MHz). The RTL programs one-lane 16-bit DDR (`conv_spi.v` step 7; `adcs_capture.v` header: "DCO = 8·f_S"), which is 500 MHz at 62.5 MSPS and 400 MHz at 50 MSPS; the AD9253 data sheet (p.28–29) gives 1 Gbps per lane in that mode. The divided domain is analysed at 16 ns instead of 8 ns: its slack of 9.116 ns becomes about +1.1 ns [E], so it probably still closes, but the pulse-width checks at 500 MHz were never run | Two `create_clock` lines (2.000 ns, and 2.500 ns with `-add`), rebuild, re-read the reports |
| **A-3** | Medium | The radar DDC's NCO is the constant `PHASE_INC_120MHZ = 32'h4CCCCCCD` (0.3 × f_S) | `fpga/third_party/aeris/ddc_400m.v` line 207 | Correct at 400 MSPS; at 500 MSPS it tunes to 150 MHz. Covered by A-1's gating; becomes a register in G-4 |
| **A-4** | Medium | `FPGA_GATEWARE.md` §4.1 describes an SDR the board does not have | "125 MSPS AD9253", "0.1–62.5 MHz Nyquist zone 1", "6 m directly", "0.0291 Hz at 125 MHz", connectors `J901`–`J906` | The ADC runs at 62.5 / 50 MSPS; the first zone ends at 31.25 / 25 MHz; 50 MHz is in the second zone and only on the unfiltered channel; the NCO step is f_S / 2³² = 0.01455 Hz (0.01164 Hz at 50 MSPS), so **a tuning word computed for 125 MHz tunes to half the intended frequency**; the connectors are `J911`, `J951`, `J952`. Also the block diagram's "2x125 MSPS" and the timing line's "437.5 MHz SDR ADC" |
| A-5 | Low | README: "a direct 0–62.5 MHz HF/CB bypass path" | README line 216 | 0–31.25 MHz, and 0–30 MHz on `J951` |
| A-6 | Low | README lists FM, airband and PMR446 as bands of the SDR | README line 15 | True only behind an external converter until Rev08; say so |
| A-7 | Info | DSP48 use is 110 of 120 (91.7 %) | `utilization.rpt` | No room for a multiplier-based addition; see G-4 |
| A-8 | Info | The board is hard to diagnose without instruments | One LED of its own, no serial port | WP1, WP2 |

A-1 to A-6 need no board change and are independent of everything else here.

---

## 9. Power, heat and the enclosure

| Rail | Today [V, `power_budget.py`] | Added | After | Regulator |
|---|---|---|---|---|
| 3.0 V front end (new LDO from `+3V3_D`) | — | 25 + 25 mA amplifiers, 125 mA converter, 5 mA rest | 180 mA | LP5907, 250 mA |
| `+3V3_D` | 1,128 mA | 180 mA + 15 mA of LEDs and expanders | 1,323 mA | 2 A |
| `+5V0` | 1,584 mA | 140 mA | 1,724 mA | 3 A |
| 12 V input | 8.8 W | **0.8 W** | 9.6 W | — |

- The bias tee, when on, adds what the external load draws (limited to 100 mA).
- The USB bridge draws from the USB cable.
- **Thermal** [E]. 0.8 W more inside the box, 0.4 W of it in a 5 × 5 mm package. The enclosure's rating
  (56 °C with the stock KV260, limited by the K26's junction) will move by about 1 °C; the LMR33630, the
  hottest part of the adapter at 109.8 °C of 125 °C in 70 °C air, carries 9 % more current. Both need the CFD
  re-run with the new sources, not an estimate.
- **Enclosure (approved: thirteenth SMA).**
  - `J961`'s notch in the back wall at enclosure X ≈ −14, split at the SMA's centre line as the other twelve,
    so the two shells clamp its body. It lands on the back-wall lug at X = −20 and the exhaust slots at −19.5
    and −25. The lug cannot go west (the 12 V jack's opening spans −51.5 to −31), so it moves east of the
    notch, to about X −5, and the two slots move with it.
  - A 2 mm slot for the LED row beside it (section 3.1).
  - The camera: a lens window in the lid over the tongue, and a clamp with a TPU pad on the module.
  - The fan header `J1002` moves a few millimetres inside the block; its cable is unchanged.
  - The 50 g FEA and the CFD are re-run with the new openings and heat sources.

---

## 10. Cost

Parts per board, JLCPCB prices for small quantities [V]:

| Group | Parts | $ |
|---|---|---|
| WP1 | 13 LEDs, resistors, one TCA6416A | 1.1 |
| WP2 | CH340X, USB-C, ESD array | 1.1 |
| WP3 | BM20B-34DS | 0.2 |
| WP4 | SMA, bias tee, 2 × SPF5043Z, 2 × PE4259, 2 × PE42442, PE4312, LDO, TCA6416A, about 60 passives, shield frame | 31.9 |
| WP5 | RFFC5072, 2 × baluns, TCXO, 2 × PE4259, 2 × SKY13418, SAW, 2 × LTCC, UHF filter, about 35 passives, shield frame | 33.8 |
| **Total** | | **≈ 68** |

About 17 new extended part types add roughly $51 of feeder fees per order. Against Rev07's quote ($2,172 for
two boards) that is about +9 % [E]; the real figure comes from re-running the quote.

---

## 11. Execution plan

| Phase | What | Verification | Gate |
|---|---|---|---|
| 0 | Decisions (section 12) | — | Done, 16 November |
| 1 | Audit corrections A-1 to A-6, and G-1 (debug UART) | Rebuild: timing with the corrected clocks; the existing benches at both clock modes; a new bench for the UART with a mutation; documents and PDF regenerated | Independent of the rest; can be merged as Rev07 gateware |
| 2 | Placement trial on a scratch copy: every block of section 5.3 as real footprints in the free block; `J961` on the edge; the IF line routed to `SW2`; `J103` and its vias; the vertical USB-C on the tongue | DRC on the scratch copy; the IF line's clearance to the DAC outputs; the USB-C's drawing confirms surface-mount legs | **G1: if the blocks do not fit with shield frames, the plan comes back to the owner before any schematic work** |
| 3 | Filters to catalogue values; tolerance Monte Carlo for the three; RFFC5072 data sheet read; loop filter designed | Masks met at the 1st percentile, as for the Rev07 filter | **G2: FM-reject filter ≥ 40 dB with real tolerances** |
| 4 | Schematic: new sheet `RX_VU`; LEDs, expanders and UART bridge on CONTROL; `J103` wired pin for pin to `J102` on IAS_LINK; power additions | ERC unchanged in warnings; `check_sheet` for the new sheet | — |
| 5 | Layout | DRC with zones refilled and schematic parity: 0 / 0 / 0 | — |
| 6 | Simulation of the new copper: coupling of the IF line and the LO into the converters and the clock tree; return loss of `J961`'s launch | Numbers in SIGNAL_INTEGRITY, same method as §9.9 | **G3: LO and IF-line coupling into either ADC below the Rev07 isolation figure** |
| 7 | Gateware G-2 to G-6, then G-7 | A bench for each block with models of the expander, the synthesiser and the attenuator; mutations; build at both clock modes | DSP48 count stays within 120 |
| 8 | Enclosure: `J961` notch, LED slot, lug and slots moved, lens window and camera clamp; CFD and FEA re-run | Rated ambient and stress table updated from the runs | — |
| 9 | Regenerate every output and review every document (section 11.1) | Section 11.1, item by item | **G4: Rev08 is not finished until all of 11.1 is done** |
| 10 | Tag `rev08`, push | — | — |

Phases 1 and 2 can run in parallel. Nothing in phases 4–10 starts before G1.

### 11.1 Definition of done

Rev08 changes the board, the enclosure, the power and the gateware, so **every figure, simulation and result
derived from them is stale until it is re-run**. None may be carried over from Rev07, and none is updated by
editing numbers into a document. Before Rev08 is called finished:

| Group | What is redone from the final Rev08 files |
|---|---|
| Board electrical checks | ERC; DRC with zones refilled and schematic parity (0 / 0 / 0); net-length and skew tables |
| Signal integrity | LVDS eyes and skews, the SMA launch return loss (openEMS) including `J961`, the IF line, coupling and isolation (`txrx_isolation.py` with the new aggressors: LO, IF line, USB), filter responses and Monte Carlo (the Rev07 HF filter and the three new ones), DAC filters, the clock-tree spur estimates, the cascade and frequency plan of section 5 |
| Power | `power_budget.py` with every new load; regulator dissipation; rail LED currents |
| Thermal | Board thermal maps; the enclosure CFD at the rated ambients (stock K26 and K26I), with the new heat sources and openings; heatsink map; rated ambient recomputed |
| Mechanical strength | The 3-D FEA of the enclosure (50 g in three axes), with the new notch, slots, lug, lens window and camera clamp; BGA strain; safety factors at 23 and 70 °C |
| Gateware | Vivado build at both clock modes with the corrected constraints; utilisation, timing, pulse-width, methodology and CDC reports; every bench and its mutations, old and new; the floorplan, schematic and pipeline figures (`render_fpga_views.py`) |
| Renders and 3-D | Board renders (top, iso, 4K), case and mount renders, heatsink renders, FEA images, camera module on the tongue; each checked against the render rules before upload |
| Fabrication | BOM and placement files, LCSC selection with live stock, the quote, the fab package |
| Documents | **Every document reviewed against the final design**, not only the ones the work touched: README, ARCHITECTURE, every `*_SPEC.md`, LAYOUT, SIGNAL_INTEGRITY, POWER, ENCLOSURE and its thermal study, MECHANICAL, FABRICATION, JLCPCB_QUOTE, FPGA_GATEWARE, `fpga/` and `sw/` documents, LINK_PROTOCOL's register map, PINMAP. Numbers checked against the regenerated outputs; no stale part reference, sample rate, connector name or count (thirteen SMAs). Then the schematic, layout and documentation PDFs regenerated and read through |
| This plan | Each item of sections 8 and 12 marked done or explicitly deferred, with the reason |

### Risk register

| Risk | Likelihood | Effect | Mitigation |
|---|---|---|---|
| The block does not hold WP4 + WP5 with shielding | Medium | WP5 slips | G1 before any schematic work |
| RFFC5072 runs out (64 today) before the board is ordered | Medium | No converter | Nothing bought during design (decision 5); stock re-checked at order; MAX2871 + ADE-1+ fallback |
| No vertical USB-C with surface-mount shell legs | Low | Header instead | Three candidates in stock; G1 checks the drawings |
| Strong FM or TV signals use up the 8-bit range | Certain near transmitters | Lower sensitivity there | Dedicated FM and FM-reject paths, AGC, bias-tee for a mast-head filter |
| LO or its harmonics reach an ADC or the clock tree | Medium | Spurs | Distance (60 mm), shield frames, own LDO, power-down when unused, G3 |
| I²C traffic disturbs the Si549 | Low | Close-in spurs while retuning | No traffic while receiving |
| FM-reject filter detunes with tolerances | Medium | Less than 45 dB | 2 % inductors, Monte Carlo, G2 |
| Camera module does not clear `J18` or needs support | Unknown | Receptacle unused | Check with a module before cutting the lid; the footprint costs nothing |
| DSP48 budget | High | G-4 has to be multiplier-free | Stated in G-4 |

---

## 12. Decisions (16 November 2026)

| # | Question | Decision |
|---|---|---|
| 1 | Scope | **Everything**: the audit corrections and all new work, WP1–WP6, G-1 to G-7 |
| 2 | A thirteenth SMA on the back wall for the VHF/UHF antenna | **Yes**, with the enclosure changes of section 9 |
| 3 | IAS0 | Pins 15 and 20 are of no real use to the board (section 4.2), so **the camera pass-through receptacle, pin for pin, is fitted** |
| 4 | Debug USB | **Vertical USB-C inside the box**, where it fits (section 3.2); a 4-pin header only if no surface-mount part places |
| 5 | Buying parts | **Nothing is bought now**: the board is being designed. Parts that are useful and fit go in; their stock is re-checked at order time |
| 6 | Starting the work | **Not yet.** First the analysis and this document; phase 1 starts when the owner says so |
| — | Clock mode for the new receiver | Follows from 1: 400 MSPS first (G-4), the 500 MSPS path (G-7) in scope after it |

---

## 13. How this was measured

| What | How |
|---|---|
| Free areas, tracks per layer, pad geometry, net endpoints | The board file read as text; never `pcbnew.LoadBoard` |
| IAS0 pins | XTP682 sheet 13 rendered and read (AMD's file, not redistributed) |
| Filters, cascade, frequency plan | `_work/sim/rev08_frontend.py` |
| Stock and prices | JLCPCB parts API, the one `_work/fab/lcsc_select.py` uses, 16 November 2026 |
| Timing and utilisation | `fpga/artix/reports_rev06/`, `fpga/artix/xc7a50t.xdc`, the RTL |
| Converter and connector data | AD9484, AD8352 and AD9253 data sheets in `_work/datasheets/`; Hirose BM20 catalogue (land patterns, p.3); Qorvo's SPF5043Z data sheet figures and RFFC5072 product page; Skyworks SKY13418-485LF data sheet figures |
| Not obtained | The RFFC5072 data sheet itself, and onsemi's IAS module drawing |
