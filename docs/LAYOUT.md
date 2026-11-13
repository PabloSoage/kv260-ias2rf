# Layout — board, rules, placement and routing

*25 September 2026 · `CSI2-KRIA-KV260_Rev01.kicad_pcb` · built by `_work/layout/build_board.py`
from the schematic's netlist; placement refined and L4 drawn the same day*

The Rev03 board exists. It has:
- the outline and the 8-layer stackup (6 layers until 12 November 2026, §6.5);
- design rules and net classes;
- the two ground planes and the split power layer;
- **every one of the 479 parts with its nets**, linked to its symbol (472 until the housekeeping
  devices were added on 2 October);
- the holes and fiducials;
- a placement with every passive at its pin, and a readable silkscreen.

**It is fully routed** (§6): 0 DRC errors, 0 unrouted connections, 0 schematic-parity problems.
The LVDS skew and termination stubs were reviewed and fixed, and the trace widths confirmed in
JLCPCB's calculator, on 10 November (§6.2–6.3). **On 11 November an RF/high-speed review** rebuilt the
RF band, widened the LVDS legs to 50 Ω, fixed VCCINT's plane and decoupling, and added return
vias, exposed-pad vias and an edge fence (§6.4, [SIGNAL_INTEGRITY.md](SIGNAL_INTEGRITY.md)). **On 12 November
it moved to 8 layers** (JLC08161H-2116C): two inner signal layers, L4 for power only, the LVDS pairs
re-routed (9 of 19 as coupled 100 Ω pairs, the rest as matched 50 Ω legs), their terminations moved
under the FPGA's balls on the bottom face, and LINK_TX terminated at its receiver (§6.5).

The original Allied Vision board is kept, untouched, as
`_deprecated/CSI2-KRIA-KV260_Rev01_AlliedVision.kicad_pcb`.

---

## 1. Outline: 119 × 132 mm

| | |
|---|---|
| **Kept from the original** | The upper, U-shaped part: the two tongues that reach the IAS connectors, and the band over the carrier down to its edge (y 117.25). It is known to clear every part on the KV260 (INTERFACE_SPEC §5.3) |
| **Changed** | The IAS0 tongue's right edge moves from x 144.9 to **142.4**, 1.5 mm clear of the carrier's J18 jumper. The original overlapped it by 1.0 mm (INTERFACE_SPEC §5.3) |
| **Removed** | The slots for the cameras' flat cables along the old bottom edge |
| **New** | Everything from y 127.25 to **y 214.75**, full width. Outward, off the carrier, where the KV260 has nothing at all |
| **Tab (13 Nov 2026)** | x 208–229, y 117.5–136 on the east edge, for the Ethernet RJ45 J1201 (CONTROL_SPEC §7). It is off the carrier (y > 117.25) and past its front edge, where INTERFACE_SPEC §5.3 found 25+ mm free. The bounding box becomes **140 × 132 mm**. The GND planes follow the tab |

**Why 120 mm and not the ~90 estimated before the schematic existed.** The parts' courtyards add up
to **5,700 mm²**. At 119 × 90 mm they would cover 75 % of a board that is populated on one face
only, with nothing left to route between them. At 119 × 120 mm they cover about half. **On 10
October it grew 12 mm more, to 132 mm**, to give the routing room. The overhang past the
carrier's edge is now 97 mm, which is why three supports are added at the outer edge.

**One face only, and no through-hole parts over the carrier.** Below the board there is 0.8 mm to
the carrier (the Hirose mated height), so nothing can go on the bottom there, and through-hole pins
would hit it. The placement enforces it: no through-hole part above y 118.5. The carrier's edge is
drawn on `Dwgs.User`.

---

## 2. What is fixed by measurement

| Item | Where | Source |
|---|---|---|
| **J101** (IAS1, the link) and **J102** (IAS0, mechanical) | (186.02, 85.60) and (135.98, 85.60), bottom face, 180° | Copied from the original board: position, face, rotation and pads, checked identical by script. They register the adapter on the KV260 |
| **H1, H2**, M3 through the KV260's corner holes | (94.0, 112.25), (203.0, 112.25) | The original's holes, within 5 µm of the carrier's (INTERFACE_SPEC §5.3) |
| **H3, H4, H5**, supports | (93.0, 209.75), (148.5, 192.5), (204.0, 209.75) | 8 mm M3 standoffs to the surface the KV260 stands on (INTERFACE_SPEC §5.3: 7.9 mm) |

All five holes are plated and on GND. H3–H5, the fiducials and the holes are *board-only*
footprints: they have no symbol. FID1–FID3 are on the top face; FID4–FID6, added on 13 Nov, on the
bottom face at (104, 119), (100, 190) and (201, 196) for that face's assembly pass.

**Test pads (13 Nov).** TP1–TP13 are bare 1.0 mm pads on the top face, board-only as the holes
(project footprint `TestPad_D1.0mm_BoardOnly`, the name on F.Fab, no silkscreen), each on a via
of its rail or joined to one by a short track:

| Pad | Net | At | Pad | Net | At |
|---|---|---|---|---|---|
| TP1 | +5V0 | (174.3, 177.05) | TP8 | +1V0 | (116.9, 172.6) |
| TP2 | +3V3_D | (151.65, 129.59) | TP9 | −3V3 | (98.4, 203.8) |
| TP3 | +3V3_A | (128.90, 127.00) | TP10 | +3V3_CLK | (184.1, 146.8) |
| TP4 | +2V5 | (110.02, 154.53) | TP11 | DONE | (138.90, 160.78) |
| TP5 | +1V8_D | (179.87, 184.93) | TP12 | GND | (203.5, 182.8) |
| TP6 | +1V8_A | (187.4, 188.8) | TP13 | GND | (170.25, 199.75) |
| TP7 | +1V2 | (171.99, 130.11) | | | |

+12V has none: J1001's pins and D1001 are reachable.

---

## 3. Stackup and rules

The stackup is **JLCPCB's JLC08161H-2116C**: 8 layers, 1.54 mm (6 layers, JLC06161H-2116A, until
12 November 2026: §6.5). Same outer prepreg as before, so the outer 50 Ω width stands.

| Layer | Use | Dielectric below |
|---|---|---|
| L1 F.Cu | SIG: RF lines, fan-outs, part of the LVDS | 2116 prepreg 0.1194 mm, Er 4.29 |
| L2 In1.Cu | **GND plane** | core 0.130, Er 4.17 |
| L3 In2.Cu | SIG: LVDS pairs (LINK, ADCR), slow nets | 2116 + 1080 + 2116 prepreg 0.3658, Er 4.29 |
| L4 In3.Cu | **PWR, split** (§3.1); no signal tracks | core 0.130, Er 4.17 |
| L5 In4.Cu | **GND plane** (new) | prepreg 0.3658, Er 4.29 |
| L6 In5.Cu | SIG: LVDS pairs (ADCR, ADCS, LINK_RX_CLK), between two GND planes | core 0.130, Er 4.17 |
| L7 In6.Cu | **GND plane** | 2116 prepreg 0.1194, Er 4.29 |
| L8 B.Cu | SIG: slow nets, the 100 Ω terminations under the FPGA, VCCINT caps | — |

The rules in the project file are for a standard 8-layer process, with a 0.2 mm drill for fanning
out the 1.0 mm-pitch BGA:

| Rule | Value |
|---|---|
| Track / clearance | 0.09 mm minimum (the LVDS necks under the FPGA); Default class 0.15 mm track, **0.10 mm clearance** |
| Via | 0.45 mm pad, 0.2 mm drill |
| Copper to edge | 0.3 mm |
| Zones on L2, L4, L5, L7 | 0.15 mm clearance; L4 kept 1 mm in from the edge |
| Custom rules (`CSI2-KRIA-KV260_Rev01.kicad_dru`) | An RF50 track under 0.18 mm (the 0.15 mm neck at a 0.5 mm-pitch pin) keeps the default clearance; the ESD tuning sections keep 0.24 mm; an LVDS pair's two legs keep 0.10 mm to each other, and inside the FPGA's courtyard an LVDS track keeps 0.10 mm to everything but supply copper (the Power class's 0.15 mm holds: KiCad takes the larger of the two items' rules, so the rules are written for both orders) |

| Net class | Track | Applies to (patterns in the project file) |
|---|---|---|
| **LVDS100** | Coupled: 0.10 mm, gap 0.15 mm (100.2 Ω on L3/L6), necked to 0.09 / 0.12 mm under the FPGA (98.5 Ω); on L1 0.117 / 0.15. Legs that run apart are 50 Ω each: 0.151 mm on L3/L6, 0.183 mm on L1/L8 | Link pairs, ADC data and clock pairs, `CLK_ADC*`, `CLK_FPGA`, `FPGA_CLK` |
| **RF50** | 0.183 mm (50.4 Ω on L1), 0.2 mm clearance | `IF_RX_*`, `IF_TX_*`, the auto-named switch/SMA nets `Net-(J4*-In)`, `Net-(J9*-In)`, `Net-(U90*-RFOUT*)` and U401's `CLK0`/`Q3` |
| **Power** | 0.4 mm, 0.15 mm clearance | Every rail, VIN and switch nodes |
| Default | 0.15 mm (0.10 mm in the dense areas), 0.10 mm clearance | The rest |

The impedance widths come from a field solver run on this stack, solder mask included
(`_work/field_solver8.py`; `_work/field_solver.py` for the 6-layer stack and the solver's checks
against exact references, within 1–2.4 %). Order stack JLC08161H-2116C explicitly
([FABRICATION.md](FABRICATION.md)): 2116A and 2116B were looked at and dropped (the field solver's
docstring says why).

### 3.1 L4, the power layer

**+3V3_D is the background plane**, over the whole board: it has the most pins (62) and they are
everywhere. On top of it, islands at higher priority, 0.3 mm apart, each drawn around its own
rail's pads so they follow the placement:

| Island | Where | Why a plane |
|---|---|---|
| **+1V0** | Under the BGA, south and west of it under VCCINT's 0.47 µF caps (11 Nov), and a corridor from the buck's inductor L1030 (five vias in its pad) | FPGA VCCINT, 700 mA, the highest current per pin |
| **+5V0** | The POWER block | The input of the three bucks and two LDOs: 1.6 A |
| **+3V3_CLK** | The CLOCK block | The ADCLK948 and Si549, isolated from the digital 3.3 V |
| **+5V_IFR, +5V_IFS** | Around each pair of AD8352 drivers | The drivers' supplies |
| **+1V8_ADCR_A/D, +1V8_ADCS_A/D** | Around each ADC | Their analogue and digital supplies, kept apart |

Where two islands overlap, the smaller wins. **Everything else is routed as tracks**: +1V8_D, +2V5 (a
0.5 mm trunk where it fits, since 12 Nov),
+3V3_A, +1V8_A, +12V, −3V3, +1V2 and the XADC supply. They are either low current or have too few
pins in one place for a plane to be worth it.

- **L3 references L2**, 0.13 mm away, far more than L4, 0.37 mm away, so the splits on L4 matter
  little to L3's signals. **L6 sits between L5 and L7**, both ground. Since 12 Nov L4 carries no
  signal track, only a few supply stubs.
- The islands are fed by their pads' vias since the routing (§6).

---

## 4. Placement

**Anchored by hand:**
- **the 12 SMAs**, along the bottom edge at 8.5 mm pitch, **ordered by where each signal comes
  from**. Left to right:
  - TX_A (J931/J932) and TX_B (J941/J942), under the DACs;
  - SDR_TX_C (J952) and SDR_RX_C (J951);
  - RX_A (J911/J912) and RX_B (J921/J922), under the ADCs;
  - the clock in/out (J401/J402) at the right end, nearest the ADCLK948.
- **the DC jack**, opening at the left edge;
- **the AERIS ribbon** (IDC 2×20), in a band under CONTROL, above the RF row. It was along the
  top of the main area until 10 October; from there its 35 bank-35 lines crossed both DAC buses;
- **the AD9767's five series arrays** (RN1103–RN1107), in a column left of the BGA, on the way to
  U801. Placed by rule they sat above the BGA, and the DAC lines doubled back;
- **the Pmod and JTAG headers**;
- **the FPGA**, rotated 90°, so bank 15 faces the DACs and bank 14 faces the ADCs and J101. **A
  3.5 mm ring around it is kept free of parts** (2.5 mm until 19 Oct), so the outer rows can escape on L1 and the inner
  rows' fan-out vias have room.

- **the POWER block, along the flow of the power** (below);
- **the FPGA's VCCINT bulk** (330 µF, 100 µF and 3 × 4.7 µF), right after its ring, from the
  +1V0 ball nearest the edge outward. Those balls are in the middle of the BGA, so about 11 mm is
  the least these can be; they land at 10.7–12.4 mm. UG483 p.24: *"Bulk capacitors can be placed
  almost anywhere on the PCB, but the best placement is as close as possible to the FPGA."*

**The POWER block follows the flow of the power** (POWER_SPEC §1), from the jack's pin 1:
- **Input chain, going up from the jack:** PTC F1001 at the jack's VIN, MOSFET Q1001 above it
  (drain down, sources up), then the LMR33630 with its inductor L1001 to its left. The switch pin
  faces the inductor, and the input pins face the MOSFET.
- **+5V0 feeds three buck cells in a row below the jack:** chip, inductor below, output capacitors
  under the inductor. +1V0 is on the right, nearest the FPGA, where its L4 corridor starts.
- **A column of LDOs on the block's right edge:** +3V3_A at the top, next to the DACs, then
  +1V8_D, then +1V8_A.
- **The −3V3 charge pump at the bottom,** towards the RF switches that use it.

Each chip's orientation is chosen from its pad map. Every capacitor, inductor and resistor on POWER
ends up within 5.9 mm of its pin.

**Every other chip** goes to its sheet's region, at the relative position it has on its schematic
sheet, scaled down:

| Region | Sheet |
|---|---|
| Left | POWER, beside the jack |
| Centre-left | DAC_RADAR, DAC_SDR |
| Centre | CONTROL, around the FPGA |
| Right | CLOCK, ADC_RADAR, ADC_SDR (each ADC next to the FPGA, its front end outboard, since 14 October) |
| Top-right tongue | IAS_LINK, beside J101 |
| Bottom band | ROUTING. Each RF switch sits right above its own pair of SMAs |

**Every passive goes next to the pin it belongs to.** The script finds that pin from the netlist:
- a decoupling capacitor goes to the supply pin it decouples. Which chip that is, in this order:
  - the chip its spec description names ("ADCLK948 p.10: 1 µF bypass", "… at the Si549's VDD");
  - the chip whose pin it is drawn next to (under 15 mm on the sheet);
  - otherwise, the chip with the most pins on that rail. That is how CONTROL's decoupling block
    reaches the FPGA, and between two identical chips (the AD8352 pairs) the capacitors are
    shared out;
- a termination, series resistor, coupling or reference capacitor goes to the pin it connects to.
  Only chips and connectors on the passive's **own** sheet count: a termination belongs at the
  receiver on its own sheet, and a 22 Ω series array at the FPGA, which drives it;
- on POWER:
  - a buck's inductor goes to its switch pin, first;
  - its output capacitors go to the inductor;
  - every regulator capacitor, whatever its value, comes before anything else, because the input
    and output capacitors close the switcher's high-current loop.
- a pull-up or pull-down (≥ 1 kΩ to a rail, outside POWER) goes last: it is DC and can be a few
  mm further out.

**The order is the one a person would follow:** a chip, then at once its own passives (small
decoupling first), then the next chip. So each chip's pins get their neighbourhood before a
neighbour can take it. A legaliser puts each part at the nearest spot where its courtyard, grown
to include its own silkscreen, is free, **0.5 mm from every other** (0.2 mm until 10 October, which
left no room for tracks between the passives). The spot must be inside the outline, and off the
carrier if the part is through-hole.

**The silkscreen** gets a reference for every part where one fits:
- clear of every pad, of other silk and of other parts' bodies;
- at 1.0 mm, or at the 0.8 mm minimum;
- beside the part, or up to 3 mm away for chips, connectors and inductors.

155 references fit. The other 332 are hidden on the silkscreen, but every one stays on F.Fab, the
assembly drawing. Most of them are 0402 passives in dense groups. The Hirose connectors' silkscreen
is moved to B.Fab: its 0.5 mm text is below the minimum, its outline runs over its own pads, and it
sits mated to the carrier where nobody can read it.

**This is a placement to route from, not a finished layout.** Expect to move parts in KiCad as the
routing is planned.

---

## 5. How it was checked

*The figures below are for the first placement (0.2 mm between courtyards, 25 September); the
re-placement of 7–19 October moved parts by up to a few millimetres.*

| Check | Result |
|---|---|
| `kicad-cli pcb drc --schematic-parity` | **0 parity problems**: every symbol has its footprint, every pad its net. **No shorts, clearance or courtyard violations** |
| | Before routing, **499 unconnected** listed: a cap on KiCad's list, not the count (the netlist needs about 1,390 connections). No silkscreen warnings. After routing: §6.1 |
| `_work/layout/check_placement.py`: each passive's distance to its pin, from the board file | Decoupling ≤ 1 µF: median **2.9 mm** (first pass: 10 mm). Parts on a signal pin: median 3.4 mm, 90 % within 7.0 mm. Bulk: median 8.6 mm, none over 14 mm. On POWER, everything within 5.9 mm of its pin. The FPGA's 0.47 µF sit further out (median 8.9 mm): VCCINT is in the middle of the BGA and nothing may enter the 2.5 mm escape ring on the top (four more, C1184–C1187, sit on the bottom face inside the footprint on ball vias since 11 Nov). The script's pad positions are checked against the coordinates KiCad prints in its DRC report: 964 pads, 0 µm apart |
| L4 filled on a copy (`kicad-cli pcb drc --refill-zones`) | All islands fill. The only new reports are the islands' `isolated_copper`, expected until their vias are placed |
| J101/J102 against the original board | Position, face, rotation and all 38 pads identical. Nets as INTERFACE_SPEC §3–§4 (pin 4/5 `LINK_RX_D0`, 7/8 `LINK_RX_CLK`, 14 `HK_SCL`, 21 `FPGA_PROG_B`, 22 `HK_SDA`, 15 `FPGA_IRQ`: moved from 32 after the check against the carrier, INTERFACE_SPEC §4.3) |
| Footprints | All 479 exist. Four are new, in `footprints/kv260-ias2rf.pretty` (`_work/make_footprints.py`): ADCLK948 and AD9484 LFCSPs with their datasheets' exposed pads, the M3SWA2's DQ3005 from its Mini-Circuits case drawing, and the Hirose BM20B |
| TPS7A8300 (U1005–U1007) against TI's RGR0020A drawings (SBVS197, pp. 44–45) | KiCad's `QFN-20-1EP_3.5x3.5mm_P0.5mm_EP2x2mm` fits: 3.5 mm body, pin 1 top-left and the same pin order. Its exposed pad is 2.0 mm against TI's 2.05 mm land, still 0.25 mm clear of the pins. TI's example puts four 0.2 mm vias in the pad: added on 11 Nov (four in each), for the +1V8_D LDO's 0.50 W |

Parts chosen for this step, each checked against its datasheet (all fetched by
`_work/fetch_datasheets.py`):

| Part | Choice | Why |
|---|---|---|
| **T701, T801, T802** | **Mini-Circuits ADT2-1T+**, CD542 | Impedance ratio 2, 0.4–450 MHz, 50 Ω. The 100 Ω secondary (6/4) goes to the DAC, the primary (3/1) to the line. KiCad's PL-052 variant of the footprint grounds pin 4, which a balun must not, so the plain CD542 pads are used |
| **L1001** | Bourns SRP7028A-8R2M | Isat 7.5 A ≥ the LMR33630's 5.05 A current limit; Irms 4 A |
| **L1010, L1020, L1030** | Bourns SRP7028A-3R3M, -3R3M, -2R2M | Isat 12 / 12 / 14 A ≥ 3.5 A |
| **Q1001** | Diodes DMP3013SFV | −30 V, −12 A, 9.5 mΩ at −10 V, VGSS ±25 V |

---

## 6. Routing

### 6.1 The routed board (10 November 2026)

| | |
|---|---|
| Result | **0 DRC errors, 0 unrouted connections, 0 schematic-parity problems** (zones refilled); re-checked after the review of 11 Nov (§6.4) |
| Copper | 12.5 m of track (12 Nov): L1 4.9 m, L3 3.3 m, L6 1.2 m, L8 3.0 m, L4 0.1 m (supply stubs). Mostly 0.10 mm; the supplies 0.30 mm (+2V5 up to 0.5); the RF lines 0.183 mm; LVDS as §3 |
| Vias | 2,089 through vias, 0.45 mm on a 0.20 mm drill; 993 are ground (return vias, the RF band fence, the edge fence, exposed pads). About 590 sit in pads and are filled and capped (FABRICATION.md) |
| L2, L5, L7 | Ground only (`_work/layout/planechk.py`) |
| L4 | No signal tracks since 12 Nov; three supply stubs under the BGA |
| LVDS | 9 of 19 pairs coupled end to end (0.10/0.15 mm on L3/L6), ADCR_D4 for 41 %; the others as two 50 Ω legs matched to ±5 ps. Every pair's 100 Ω termination sits on its two ball vias on the bottom face (§6.5) |

### 6.2 What is left

1. **LVDS skew and termination stubs: fixed 10 Nov (§6.3).** LINK_RX_D0 and LINK_RX_D1 were half
   a bit apart; every pair at 1 Gb/s is now within 42 ps. Four terminations (R1109, R1111, R1112,
   R1113) moved next to the FPGA, where their pairs pass, and R514 turned round, so no leg at
   1 Gb/s has a stub over 27 ps. What is left is in §6.3 and is tolerable.
2. **No supply track on L2 or L5** after any further routing: check with `_work/layout/planechk.py`.
3. **The LVDS pairs: re-routed as pairs on 12 Nov (§6.5).** Ten pairs could not be coupled; a
   LINK_RX's bank 34 is in the BGA's south-east corner; coupling it needs its AC capacitors at
   J101 moved together (§6.6).
4. **No dangling copper** after any rip-up: the DRC's `track_dangling` and `via_dangling` at zero.
5. **Check the planes** after a refill: every L4 island fed by vias, L2 unbroken under the pairs,
   and the tracks on L4 (the +3V3_D background only) not cutting off any +3V3_D via.

Before anything is ordered: DRC with zero errors and zero unconnected items, the widths
confirmed in JLCPCB's calculator, and the checks in [FABRICATION.md](FABRICATION.md).

```
py _work/layout/build_board.py        # rebuilds the board: overwrites any hand placement
kicad-cli pcb drc --schematic-parity -o drc.rpt CSI2-KRIA-KV260_Rev01.kicad_pcb
py _work/layout/check_placement.py drc.rpt   # passives' distance to their pins
py _work/fab/make_fab.py                     # Gerbers, drill, BOM, CPL into fab/ (docs/FABRICATION.md)
```

**The board is routed: do not run `build_board.py` again.** It would rebuild the board and drop
every track. From then on the
board file is the source, as the drawn sheets are once accepted.

### 6.3 LVDS skew review (10 Nov)

`_work/layout/lvds_skew.py board` follows each leg from the driver's pin to the receiver's,
across the AC caps (LINK_* and J_LINK_*), the series resistors (CLK_FPGA, FPGA_CLK) and U401's
outputs before their caps. A leg's delay is that of the shortest copper path between the two chip
pins, at 6.0 ps/mm on L1/L6 and 6.9 ps/mm on L3/L4 (POWER_AND_STACKUP §2.5). Copper off that path
is a **stub**, reported apart: usually the branch to a termination resistor that the leg does not
pass through. Rates: LINK ≤ 1 Gb/s a lane (INTERFACE_SPEC §3, 1 ns a bit), ADCS 1 Gb/s a lane
(AD9253 one-lane, 62.5 MSPS × 16), ADCR 400 MSPS.

**What was fixed.** The first review (da14df5) summed all of a net's copper. Measured as paths,
that board had:

| Pair | P − N then | Cause | Now | Fix |
|---|---|---|---|---|
| LINK_RX_D1 | +517 ps | P went round the board's right edge (207 mm) | −16 ps | Both legs re-routed (144 / 148 mm) |
| LINK_RX_D0 | −478 ps | N looped down to y 190 and back (187 mm) | +4 ps | N re-routed (52 mm in the middle); P meandered by 15 mm on L1 |
| ADCS_D1 | +152 ps | N short | +42 ps | N meandered by 18 mm (as far as the room goes) |
| CLK_FPGA | −111 ps | P short | −13 ps | P meandered by 16 mm |
| CLK_ADCR | −74 ps | P short | −42 ps | P meandered by 6 mm; two of its bumps touched and shorted 4 mm out, now apart; no more room |
| ADCS_DCO | −93 ps | P short | −27 ps | P meandered by 13 mm |
| CLK_ADCS | +54 ps | N short | 0 ps | N meandered by 9 mm |
| ADCS_FCO | −11 ps | No skew, but a **55 mm stub** on N to R1114 (346 ps) | −27 ps, stubs 3 / 5 ps | N re-routed through R1114's pad (fly-by), as P was; P meandered by 11 mm |

The re-routes and meanders were checked against every clearance, then by the DRC (§6.1). The
meanders are rectangular bumps of 0.5 mm, 0.5 mm apart, 0.5–1.5 mm high, on L1/L6 and in clear
space only.

**The board now:**

| Pair | P − N ps | Stub P / N ps | Verdict |
|---|---|---|---|
| LINK_RX_D0, D1, LINK_TX_D0, ADCS_D0, ADCS_DCO, ADCS_FCO, CLK_ADCS, CLK_FPGA, ADCR_D1, ADCR_DCO | −27 to +33 | ≤ 27, but CLK_ADCS N 45 (a bias resistor, below) | Fine |
| ADCS_D1 | +42 | 22 / 2 | Tolerable: 0.04 bit; no more room for meanders on N |
| LINK_TX_CLK | −36 | ≤ 19 | Fine |
| LINK_RX_CLK | −60 → **0** (11 Nov: 10 mm of meander on P) | ≤ 3 | Fixed |
| CLK_ADCR | −42 | 11 / 57 (a bias resistor, below) | Tolerable: the 400 MHz sample clock; no more room to meander P |
| ADCR data and OR | −86 to +64 | up to 52 | Tolerable at 400 Mb/s (2.5 ns a bit) |

What a P−N skew does: the two legs switch apart, so the differential voltage sits at zero for the
skew time at every edge; that much of each bit is lost and cannot be tuned out at the receiver
(IDELAY moves the pair, not one leg). Under 50 ps is 0.05 bit at 1 Gb/s.

**Termination stubs: fixed 10 Nov.** A 100 Ω termination sits across each pair the FPGA receives
(R1101–R1116, CONTROL_SPEC §3, no DIFF_TERM in a 3.3 V bank), and one across each ADC clock at the
ADC (R514, R642). What matters is the copper between the termination and the receiver's pin: it
is an unterminated stub, as is a branch from the leg to a resistor the leg does not pass through.
At 1 Gb/s with edges of about 300 ps, up to about 8 mm (50 ps) is harmless; longer rounds the
edges. `lvds_skew.py --stubs PS` lists every branch longer than PS and where it goes.

| Pair | Was: stub P / N; termination to pin P / N (ps) | Now | Change |
|---|---|---|---|
| ADCS_DCO | 134 / 73; 182 / 110 | 9 / 27; 57 / 64 | R1113 moved from 10 mm out to where the legs part, 6 mm from the FPGA; old branches removed |
| ADCR_DCO | 34 / 79; 88 / 149 | 0 / 12; 53 / 61 | R1109 moved onto P's via, 6 mm from the FPGA; N joined by a 2 mm stub |
| ADCS_D0 | 13 / 66; 83 / 104 | 7 / 7; 36 / 31 | R1111 moved between the legs, 5 mm from the FPGA |
| ADCS_D1 | 2 / 56; 112 / 125 | 22 / 2; 73 / 47 | R1112 moved onto N's via, 6 mm from the FPGA; P joined by a 3 mm stub |
| CLK_ADCR | N 54 to R514; N 132 | none; N 31 | R514 turned 180°, so each leg meets its own pad on the way to its ADC pin; N passes through its pad |

Left as it is:
- **U401's LVPECL pull-downs** R405 (CLK_ADCR N, 9 mm branch) and R407 (CLK_ADCS N, 7 mm): 200 Ω
  to ground, a weak tap; no free spot within 4 mm of the driver.
- **ADCR_D0 N and ADCR_D7 N**, 8 mm branches at 400 Mb/s; no free spot nearer the FPGA.
- **ADCS_FCO N** passes through R1114, which sits 141 ps (about 23 mm of route) from its FPGA pin;
  the area by the FPGA has no room for it. FCO is the frame clock, one edge per sample.

Data to clock, by mean leg delay (ps): LINK_RX_D0 +79 and LINK_RX_D1 +207 against LINK_RX_CLK;
LINK_TX_D0 +2; ADCS_D0 −73, ADCS_D1 −17, ADCS_FCO +45 against ADCS_DCO; ADCR data −16 to −80
against ADCR_DCO. The ADC buses land on the XC7A50T's IDELAYE2 (78 ps taps, 2.5 ns range), so
those are calibrated per lane at start-up. LINK_RX lands on the K26 (IDELAYE3), which can deskew
too, but only if the Kria firmware trains each lane; the KV260's own trace lengths add to this
and are not known here.

Not coupled: no pair runs as a coupled pair (0–3 % of the P leg within 0.35 mm of N, CLK_ADCR
12 %). Each leg is a 0.10 mm track on its own: 64 Ω on L1/L6, 62 Ω on L3 by the field solver
(POWER_AND_STACKUP §2.6), so about 125 Ω between the legs against the 100 Ω termination (some
reflection; less rejection of noise picked up on the way). Many legs also cross L4 (In3.Cu, the
power layer). Acceptable for a first board at these rates; a pair-routed version is the better
board. **Since 11 Nov the legs are 50 Ω** where they run apart (§6.4): the pair is about 100 Ω by
leg width, and the eye simulates as an ideal pair's.

### 6.4 RF and high-speed review (11 Nov)

The full record, with the simulations, is [SIGNAL_INTEGRITY.md](SIGNAL_INTEGRITY.md). In short:

| Area | Change |
|---|---|
| RF band | Rebuilt by hand: straight 183 µm switch → DC block → SMA legs on L1, bias parts on the bottom, four vias in each switch pad, L1/L6 ground pours with a 226-via fence, three vias per SMA ground leg, L2–L4 cut out under each SMA signal pad (openEMS: return loss 13.5 → 24.5 dB at 1 GHz) |
| RF lines | The eight long lines 183 µm end to end, ≤ 2 vias each, two ground vias at every via; the 64.9 Ω terminations moved under their caps (7–10 mm stubs gone); U401's input and output lines separated (−19.5 → about −45 dB) |
| LVDS | Legs widened to 50 Ω (74 % of the length at 0.175–0.183 mm); LINK_RX_CLK skew −60 → 0 ps; LINK_RX_CLK_P and LINK_RX_D0_P pulled apart (−18 → −46 dB); 136 return vias at layer changes (one layer change left with its ground via beyond 3 mm); legs of different pairs moved apart where there was room (SIGNAL_INTEGRITY §3.5) |
| PDN | Zone clearance 0.3 → 0.15 mm on L2/L4/L5; the +1V0 island joined to its corridor and extended under its caps; five vias in L1030's pad; four 0.47 µF (C1184–C1187) on the bottom face under the BGA, on ball vias; VCCINT under its target to 100 MHz (over it from 26 MHz before; `SIGNAL_INTEGRITY.md` §4.3) |
| Pads and edge | Via grids in every exposed pad (LMR33630, TPS7A8300 ×3, AD8352 ×4, ADCs, ADCLK948); a 176-via ground fence round the edge; L4 pulled back 1 mm from the edge |
| ESD | PESD5V0F1BL (D961–D970, D401, D402) on the SMA lines 2.15 mm from each SMA pad, ground pad on its own via, tuned out by 0.1 mm line sections either side (0.76 mm before, 1.4 mm after; openEMS −39 dB at 500 MHz); TPD4E05U06DQAR arrays U1108/U1109 above the Pmod and U1110 beside JTAG, GND vias butted to their ground pins (SIGNAL_INTEGRITY §7.1) |

### 6.5 Eight layers (12 Nov)

The board moved from JLC06161H-2116A to JLC08161H-2116C and the LVDS were redone. The full
comparison with the 6-layer board, with the simulations, is SIGNAL_INTEGRITY §8. What changed:

| Area | Change |
|---|---|
| Stack | L5 GND and L6 SIG added; the old L4's signal tracks moved to L6; SMA launch cut-outs extended to L2–L6, so the pad references L7 at the same depth as it referenced L5 |
| Terminations | R1101–R1114 and the new R105/R106 on the bottom face, each 0402 straddling its pair's two ball vias (via in pad): no stub between the termination and the receiver |
| LINK_TX | Terminated at the FPGA by R105/R106 (100 Ω); R101–R104 become 10 k bias to +1V2. Before, 2 × 49.9 Ω at the connector left the receiver 45 mm down an open line |
| LVDS routing | Pairs ripped and re-routed by a negotiated-congestion pair router: 9 of 19 coupled; the rest completed single-ended, widened to 50 Ω and matched to ±5 ps (worst \|P−N\| 9 ps, was 84) |
| Return vias | 0 of 89 reference-changing vias without a GND via within 3 mm (was 1 of 186) |
| +2V5 | The trunk widened to 0.5 mm where it fits: 122–129 mV drop at 601 mA (173–185 before) |
| Left open | ADCR data to DCO −28 to −177 ps (DCO is 51 mm, the data 27–44 mm): calibrated per bit by IDELAYE2, as before; done 12 Nov (§6.6) |

DRC on 12 Nov: 0 violations of any kind, 0 unconnected, 0 schematic-parity problems (zones refilled).

### 6.6 DCO and CLK_ADCR skew (12 Nov)

| Item | Before | Change | After |
|---|---|---|---|
| ADCR_DCO | 51.6 mm, data − DCO −177 to −28 ps | The AD9484 has DCO's P pin west of N, so the coupled pair from the FPGA arrived crossed and went round the chip. Its legs are swapped at the FPGA instead (N14 = DCO_N, P14 = DCO_P; `INVERTED` in `control_spec.py`, the gateware inverts the clock) and R1109 turned 180°. Re-routed: the old L3 escape to a via pair, L6 to above the AD9484, a coupled drop to its pins | 38.9 mm, 89 % coupled, P−N +2 ps; data − DCO −90 to +5 ps |
| CLK_ADCR | P−N −44 ps: C414 and C415 were 10 mm apart, N 16 mm longer | C414/C415 placed side by side (vertical, 1 mm pitch) next to U401; the pair coupled from the capacitors to R514; 1.5 mm meander on P (L3) between U401 and C414 | P−N −3 ps |
| LINK_RX | South-east balls, legs matched | Moving the pairs to bank 34's outer balls (R2/R1, T4/T3, R3/T2) was tried and dropped: the router completed 3 of 6 legs, T2 and R2 have no free spot for a via on any layer, and T4/T3's vias land on ADCS_D1. Coupling would need the AC capacitors (C101–C106, up to 9 mm apart) moved together first | Unchanged |

DRC on 12 Nov: 0 violations, 0 unconnected, 0 schematic-parity problems. Eyes, PDN, return vias
unchanged (mean eye loss −8 mV, worst LINK_RX_D0 −52 mV; 0 of 95 layer changes without a GND via
within 3 mm); other pairs' legs within 0.25 mm 65.8 mm (was 69.3).
