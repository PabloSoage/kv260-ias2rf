# Layout — board, rules, placement and first routing

*25 September 2026 · `CSI2-KRIA-KV260_Rev01.kicad_pcb` · built by `_work/layout/build_board.py`
from the schematic's netlist; placement refined and L4 drawn the same day*

The Rev03 board exists. It has:
- the outline and the 6-layer stackup;
- design rules and net classes;
- the two ground planes and the split power layer;
- **every one of the 479 parts with its nets**, linked to its symbol (472 until the housekeeping
  devices were added on 2 October);
- the holes and fiducials;
- a placement with every passive at its pin, and a readable silkscreen.

**It is autorouted, not finished** (2–14 October 2026, §6): 20 connections are left, and the
LVDS pairs need a hand review (§6.3).

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

**Why 120 mm and not the ~90 estimated before the schematic existed.** The parts' courtyards add up
to **5,700 mm²**. At 119 × 90 mm they would cover 75 % of a board that is populated on one face
only, with nothing left to route between them. At 119 × 120 mm they cover about half. **On 10
October it grew 12 mm more, to 132 mm**, to give the router room (§6.2). The overhang past the
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

All five holes are plated and on GND. H3–H5, the three fiducials FID1–FID3 and the holes are
*board-only* footprints: they have no symbol.

---

## 3. Stackup and rules

The stackup is **JLCPCB's JLC06161H-2116A**: 6 layers, 1.556 mm. It has the shape of
POWER_AND_STACKUP §2.1, and the reasons it was chosen are in §2.6.

| Layer | Use | Dielectric below |
|---|---|---|
| L1 F.Cu | SIG: IAS pairs, converter LVDS, IF lines | 2116 prepreg 0.1164 mm, Er 4.16 |
| L2 In1.Cu | **GND plane** (zone drawn, to fill in KiCad) | core 0.130, Er 4.17 |
| L3 In2.Cu | SIG | 2116 + core 0.70 + 2116, 0.933 mm (one layer in KiCad, Er 4.44 weighted) |
| L4 In3.Cu | **PWR, split** (zones drawn, §3.1) | core 0.130, Er 4.17 |
| L5 In4.Cu | **GND plane** (zone drawn) | 2116 prepreg 0.1164, Er 4.16 |
| L6 B.Cu | SIG, slow | — |

The rules in the project file are for a standard 6-layer process, with a 0.2 mm drill for fanning
out the 1.0 mm-pitch BGA:

| Rule | Value |
|---|---|
| Track / clearance | 0.10 mm minimum; Default class 0.15 mm track, **0.10 mm clearance** (§6.2) |
| Via | 0.45 mm pad, 0.2 mm drill |
| Copper to edge | 0.3 mm |

| Net class | Track | Applies to (patterns in the project file) |
|---|---|---|
| **LVDS100** | 0.117 mm, gap 0.150 mm (100 Ω differential on L1) | Link pairs, ADC data and clock pairs, `CLK_ADC*`, `CLK_FPGA`, `FPGA_CLK` |
| **RF50** | 0.183 mm (50 Ω on L1) | `IF_RX_*`, `IF_TX_*` |
| **Power** | 0.4 mm | Every rail, VIN and switch nodes |
| Default | 0.15 mm (0.10 mm where the router needed it), 0.10 mm clearance | The rest |

The impedance widths come from a field solver run on this stack, solder mask included
(`_work/field_solver.py`, POWER_AND_STACKUP §2.6). It agrees with exact references within 1–2.4 %.
Before ordering, run the same geometries through JLCPCB's impedance calculator as a last check.

### 3.1 L4, the power layer

**+3V3_D is the background plane**, over the whole board: it has the most pins (62) and they are
everywhere. On top of it, islands at higher priority, 0.3 mm apart, each drawn around its own
rail's pads so they follow the placement:

| Island | Where | Why a plane |
|---|---|---|
| **+1V0** | Under the BGA and its keep-out ring, and an L-shaped corridor, 5 mm wide, from the buck's inductor L1030 | FPGA VCCINT, 700 mA, the highest current per pin |
| **+5V0** | The POWER block | The input of the three bucks and two LDOs: 1.6 A |
| **+3V3_CLK** | The CLOCK block | The ADCLK948 and Si549, isolated from the digital 3.3 V |
| **+5V_IFR, +5V_IFS** | Around each pair of AD8352 drivers | The drivers' supplies |
| **+1V8_ADCR_A/D, +1V8_ADCS_A/D** | Around each ADC | Their analogue and digital supplies, kept apart |

Where two islands overlap, the smaller wins. **Everything else is routed as tracks**: +1V8_D, +2V5,
+3V3_A, +1V8_A, +12V, −3V3, +1V2 and the XADC supply. They are either low current or have too few
pins in one place for a plane to be worth it.

- **L3 references L2**, 0.2 mm away, far more than L4, 0.8 mm away. So the splits on L4 matter
  little to L3's signals. Anything impedance-controlled stays on L1 anyway (POWER_AND_STACKUP §2.3).
- **The islands have no vias yet.** A fill in KiCad reports each one as isolated copper until its
  vias to the pads are placed.

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
  top of the main area until 10 October; from there its 35 bank-35 lines crossed both DAC buses
  (§6.2);
- **the AD9767's five series arrays** (RN1103–RN1107), in a column left of the BGA, on the way to
  U801. Placed by rule they sat above the BGA, and the DAC lines doubled back;
- **the Pmod and JTAG headers**;
- **the FPGA**, rotated 90°, so bank 15 faces the DACs and bank 14 faces the ADCs and J101. **A
  3.5 mm ring around it is kept free of parts** (2.5 mm until 19 Oct, §6.2), so the outer rows can escape on L1 and the inner
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
| Right | CLOCK, ADC_RADAR, ADC_SDR (each ADC next to the FPGA, its front end outboard: §6.2, 14 October) |
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
to include its own silkscreen, is free, **0.5 mm from every other** (0.2 mm until 10 October: the
router found no way between the passives). The spot must be inside the outline, and off the
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
re-placement of §6.2 moved parts by up to a few millimetres.*

| Check | Result |
|---|---|
| `kicad-cli pcb drc --schematic-parity` | **0 parity problems**: every symbol has its footprint, every pad its net. **No shorts, clearance or courtyard violations** |
| | Before routing, **499 unconnected** listed: a cap on KiCad's list, not the count (the netlist needs about 1,390 connections). No silkscreen warnings. After routing: §6.1 |
| `_work/layout/check_placement.py`: each passive's distance to its pin, from the board file | Decoupling ≤ 1 µF: median **2.9 mm** (first pass: 10 mm). Parts on a signal pin: median 3.4 mm, 90 % within 7.0 mm. Bulk: median 8.6 mm, none over 14 mm. On POWER, everything within 5.9 mm of its pin. The FPGA's 0.47 µF sit further out (median 8.9 mm): VCCINT is in the middle of the BGA and nothing may enter the 2.5 mm escape ring. The script's pad positions are checked against the coordinates KiCad prints in its DRC report: 964 pads, 0 µm apart |
| L4 filled on a copy (`kicad-cli pcb drc --refill-zones`) | All islands fill. The only new reports are the islands' `isolated_copper`, expected until their vias are placed |
| J101/J102 against the original board | Position, face, rotation and all 38 pads identical. Nets as INTERFACE_SPEC §3–§4 (pin 4/5 `LINK_RX_D0`, 7/8 `LINK_RX_CLK`, 14 `HK_SCL`, 21 `FPGA_PROG_B`, 22 `HK_SDA`, 15 `FPGA_IRQ`: moved from 32 after the check against the carrier, INTERFACE_SPEC §4.3) |
| Footprints | All 479 exist. Four are new, in `footprints/kv260-ias2rf.pretty` (`_work/make_footprints.py`): ADCLK948 and AD9484 LFCSPs with their datasheets' exposed pads, the M3SWA2's DQ3005 from its Mini-Circuits case drawing, and the Hirose BM20B |
| TPS7A8300 (U1005–U1007) against TI's RGR0020A drawings (SBVS197, pp. 44–45) | KiCad's `QFN-20-1EP_3.5x3.5mm_P0.5mm_EP2x2mm` fits: 3.5 mm body, pin 1 top-left and the same pin order. Its exposed pad is 2.0 mm against TI's 2.05 mm land, still 0.25 mm clear of the pins. TI's example puts four 0.2 mm vias in the pad: add them when routing, for the +1V8_D LDO's 0.50 W |

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

### 6.1 The first autorouted board (2–6 October 2026)

*Superseded by §6.2, which re-placed the board and routed it again. Kept for the method and what
each step was worth.*

The board was routed by **an external autorouter**, a
Python + Rust router that reads and writes the `.kicad_pcb` text itself. The chain is
`_work/layout/route_krt.sh`: BGA fan-out, then the LVDS pairs, then everything else. It ran on a
copy, and only tracks and vias came back: every footprint and zone is byte-identical.

| | Result |
|---|---|
| BGA fan-out | 146 of 147 nets out of U1101, **dog-bone only**: a 0.45/0.2 mm via between four balls, no via in any pad |
| Tracks and vias | 1,278 through vias of 0.45/0.2 mm (0.6/0.3 not used). **About 400 sit in pads** (0402 passives, chip pads): JLCPCB fills and caps them free on 6-layer boards (POFV), see FABRICATION.md |
| RF lines | The six IF lines ripped up and routed **last**, at 0.183 mm: the router keeps a net's own class clearance, so routed last they keep 0.2 mm from everything (33 RF50 errors went to 1) |
| Dangling copper | 445 stub segments and vias removed by `_work/layout/drop_dangling.py`, which deletes what KiCad's DRC reports dangling (zones refilled) and repeats; the unrouted count did not change |
| Finishing pass (5 Oct) | `_work/layout/route_finish.sh`: every complete net written into the project as protected, then only the incomplete nets routed on a 0.05 mm grid. 100 → 89 unrouted, none worse; a second pass 89 → 87. Allowing rip-up instead made it worse: the router broke the link pair and an IF line to route others |
| L4 opened to tracks (6 Oct) | The same finishing pass with In3.Cu allowed (`LAYERS`/`COSTS` in `route_finish.sh`, cost 3). Tracks there cut the plane, so **every L4 island carries a tracks-only keep-out rule area** ("In3 islands: no tracks"); only the +3V3_D background is open. The **+1V0 island under the BGA shrank** from 24 × 24 mm to a band to the top bulk vias and a block over the nine VCCINT balls with a strip to the bottom vias, which frees L4 around the ring. 87 → 68 unrouted. Without the shrink it stopped at 78 |
| Same-net vias | The 4 hole-to-hole pairs merged: one via of each removed, the FCO_N leg on B.Cu extended to the other |
| L5 for slow nets (6 Oct) | The finishing pass once more with In4.Cu open, at cost 5, **to slow nets only** (`ONLY=` the ADAR bus, JTAG, CONV_SPI, SW_CTRL, XO_SCL; nothing fast, no supply): 68 → 60. About 125 mm of track now slots the L5 ground plane (ADAR_SCLK 27 mm, ADAR_SDIO 25, SW_CTRL3 18, SW_CTRL0 17, JTAG_TMS 14, CONV_SPI_SCLK 11, XO_SCL 10, ADAR8_TR 4). **Nine fast tracks cross those slots**: eight DAC data lines (CMOS) on B.Cu/In3 and **ADCR_D7_N** (LVDS leg on B.Cu). L4 is 0.13 mm away and carries the return across, but review them, ADCR_D7_N first |
| DRC (zones refilled, schematic parity) | **0 parity problems. 60 connections unrouted**. **1 clearance error** (RF50, 0.197 mm against 0.2). No hole-to-hole |

**The Power class clearance is now 0.15 mm** (was 0.2): the rails are 12 V at most, where IPC-2221
asks 0.1 mm, and 0.2 mm kept the router out from between fine-pitch pins. RF50 keeps 0.2 mm,
because there it is part of the 50 Ω line.

**An external autorouter was tried first and stopped at about 540 unrouted** after nine passes and six hours.
The bridge for it stays in the repo (`dsn_export.py`, `ses_import.py`): one polygon per plane
net and keepout strips at the edge are what made it route at all.

### 6.2 Re-placed and routed again (7–11 October 2026)

The first board stopped at 60. What was left was congestion round the BGA, and three causes of it
were in the placement and the pinout, not in the router:
- **the bank-35 bus to the AERIS ribbon** (35 lines) left the BGA's upper-left and crossed both
  DAC buses on its way to J1103 at the top-left;
- **the AD9767 (DACS) lines** went up from bank 15 to their series arrays above the BGA, then back
  down to U801 at the bottom-left;
- **the lines crossed each other.** Drawn straight from each ball to its far end, through a series
  resistor where there is one, the FPGA's nets crossed **823** times; 83 crossings within the
  bank-35 bus alone, 64 within the DACS bus.

**What changed:**

| | Change |
|---|---|
| **FPGA pinout** | Bank 35 as a whole, and the DACS lines within bank 15 (over their own balls and the bank's free ones), **re-assigned by a minimum total-length matching** of ball to far end. A Euclidean minimum matching has no crossings: 83 → 0 and 64 → 0, all FPGA nets 823 → 663. Fixed: the balls reused from AERIS-10 (DACR, ADCR, CLK_FPGA), every pair and every clock-capable ball. The tables are in `_work/sheets/control_spec.py`; `rev03/CONTROL.kicad_sch` was regenerated from it and passes `check_sheet.py control` (CONTROL_SPEC §1) |
| **J1103** | To a band under CONTROL (§4) |
| **RN1103–RN1107** | To a column left of the BGA (§4) |
| **Outline** | 12 mm longer (§1) |
| **Clearance** | 0.5 mm between courtyards, not 0.2 (§4) |

All of it is in `build_board.py`, as defaults of knobs (`BB_GROW`, `BB_J1103`, `BB_RN`, `BB_CLEAR`)
so each can be turned back for a comparison. **Not kept: decoupling capacitors on the bottom face**
(`BB_BOTTOM=caps`, 100 of them under their pins). It routed worse, 100 unrouted after the IF step
against 73: each bottom pad needs its own through via, and 200 more vias block the inner layers.

**The routing** is `_work/layout/route_all.sh`, the whole sequence of §6.1 in one script:
fan-out, pairs, everything with L4 open; the IF lines last; dangling copper; then finishing passes
that alternate all incomplete nets and the slow ones with L5 open. A pass is kept only if the
unrouted count falls and no DRC error is added. The IF step reads the **original** project:
`route.py` writes its `--clearance` into every class of the project it hands on, and with that copy
the IF lines came out with 32 RF50 errors.

| Run | Placement | Result |
|---|---|---|
| v3 | Pinout, J1103, arrays, +12 mm | 52 unrouted, 6 errors |
| v4 | v3 + decoupling on the bottom | 100 after the IF step (v3: 73); stopped |
| **v5** | **v3 + 0.5 mm clearance** | **49 unrouted, 4 errors** (84 → 52 → 51 → 49 in three passes) |

**The four errors** (three RF50 clearances of 0.15–0.195 mm, one same-net via pair) were removed by
`_work/layout/rip_violations.py`, which deletes the track or via behind each DRC error, and the
three nets were routed again by `route_finish.sh` (`ONLY=`). Then:

| | Result |
|---|---|
| DRC (zones refilled, schematic parity) | **0 errors, 0 parity problems, 49 unrouted** |
| Vias | 1,356, all 0.45/0.2 mm; about 500 in pads (POFV, FABRICATION.md) |
| Tracks | L1 5.5 m, L3 3.6 m, L6 2.8 m, L4 0.6 m |
| LVDS pairs routed coupled | 4: LINK_TX_D0, LINK_TX_CLK, CLK_FPGA, ADCS_D1. The rest as single legs, as in §6.1 |
| L5 (slow nets) | JTAG_TMS 15 mm, ADAR1_TX_LOAD 5 mm |

**Power tracks taken off the ground planes.** The router's plane-repair step ("plane
finalize") routed supply connections on layers the run forbids: L2 carried +1V0 (164 mm),
+1V8_ADCS_A (43 mm) and +3V3_D (23 mm), L5 +1V0 (45 mm) and +3V3_D (8 mm). The first board had the
same, unnoticed until now (+5V0 134 mm and +3V3_D 29 mm on L2). The cause is in the router:
`route.py` hands that step its full layer list, the forbidden layers included. A local patch hands
it only the allowed ones (`_work/layout/krt_finalize_layers.patch`, against the autorouter
979287c; apply it to the clone before routing). Then:
- every supply track on L2 and L5 was ripped and those three nets routed again with
  `route_finish.sh`: +1V0 came back on the allowed layers;
- 15 mm of +1V8_ADCS_A and 1 mm of +3V3_D came back on L2 all the same, by another path in the
  router. Moved to L4 by hand (text edit), inside or beside the +1V8_ADCS_A island, DRC-clean;
- one +3V3_D connection (128.2, 172.9) found no way back: **50 unrouted**, 0 errors.

L2 now carries only GND (33 mm of it), and L5 only GND and the two slow tracks above.

**Finer rules for the slow nets (11 October).** The finishing passes had stopped at 50: a run on a
0.025 mm grid gained nothing, and a run allowed to rip the slow control nets (ADAR, FLASH, XADC,
SW_CTRL...) broke five complete nets to connect five, and was rejected. Most of the 50 ended at a
pad or ball boxed in by other nets' copper at 0.15 mm. So the **Default class clearance went from
0.15 to 0.10 mm**, and one finishing pass routed the incomplete nets with 0.10 mm tracks and the
supplies at 0.15 mm (`route_finish.sh` with `CLR=0.1 TW=0.1 PW=0.15`). Six-layer boards at JLCPCB
take 0.09 mm track and space, so 0.10 mm costs nothing; LVDS100, RF50 and Power keep their own
clearances (0.15, 0.2, 0.15 mm), and the router takes the larger of two classes. Then:
- **50 → 40 unrouted**, no DRC error, no supply track on L2 or L5; 213 tracks of 0.10 mm;
- a second identical pass: 40 → 40;
- one +3V3_D gap closed by a short track: `_work/layout/fix_gap.py` joins two islands of a net
  with a grid path on one layer, at most one via and a straight stub, checked against the board's
  clearances (run with the router's venv, it needs shapely). **39 unrouted**, 0 errors, 0 parity
  problems. On the other 38 it finds nothing: the pad or ball is boxed in.

**The DACS bus first (12–13 October).** Two more full re-routes at 0.10 mm did not beat 39. The
first had 499 class clearance errors: the fan-out step writes its clearance into every class of
the project it hands on, and the later steps read that copy (`route_krt.sh` now restores the
original project after each step). The second reached 42. But ten of the 39 were BGA balls of the
DACS bus with **no copper at all**: routed late, they found the BGA's left side full of slow
tracks. So `route_region.sh` ripped every slow net with copper left of the BGA (box 139–158 ×
140–162 mm: 109 nets, 1,779 tracks and vias, supplies, pairs and RF untouched and protected) and
routed them again with the 15 DACS nets **first** (`region_first_dacs.txt`, route.py
`--ordering original`), 0.10 mm tracks and clearance. A first run let tracks onto L4 under the
BGA, which split the +3V3_D plane into three islands; a temporary tracks-only keep-out on L4 under
the BGA, removed after routing, fixed that. **39 → 30 unrouted**, 0 errors, 0 parity problems; L2
and L5 carry only GND.

**The ADCs moved next to the FPGA (13–14 October).** Region passes elsewhere gained nothing (right
of the BGA: 31, then 30 with other nets open; the ADC front ends: 37). The plot showed why: each
ADC sat east, with its front end (U502/U503, U602/U603) **between it and the BGA**, so the ADCs'
LVDS pairs ran over the amplifiers. That boxed in their resistors and capacitors (C508, C509, U503
RDN, U601 VIN-A were unroutable) and put fast digital lines over the analogue inputs. Now the two
ADC sheets are placed mirrored in x (`build_board.py`, `BB_ADC=mirror`, the default): the ADC next
to the FPGA, its front end outboard at the ADC's input side, the IF lines coming up to it from the
SMA row. U501 at 0° (inputs east, LVDS north, west and south) and U601 at 270° (its LVDS side, south
at 0°, towards the BGA): `BB_ROT=U501:0,U601:270`, the default. Three variants were routed in
parallel with the whole chain (`route_all.sh` at 0.10 mm, then the DACS region pass):

| Variant | After IF | After finishing | After the DACS pass |
|---|---|---|---|
| U501 0°, U601 free | 40 | 27 (3 errors) | 29, 0 errors |
| **U501 0°, U601 270°** | 50 | **23** (3 errors) | 24 (3 errors) |
| mirror only | 51 | 43 | 40 |

The second, after its finishing passes, was taken. By hand (text edits, DRC after each):
- the three errors were one +1V8_D track on L1 passing 0.116 mm from ball A3 (ADAR2_TR): its first
  millimetre redrawn 0.5 mm clear of the ball;
- the router's plane step had again put supply tracks on L2: +1V8_ADCS_A (15 tracks, 0.8 mm) and
  +3V3_D (7) moved to L4, where they lie in their own island or the +3V3_D background. Three of
  the +3V3_D tracks, beside the BGA, crossed slow tracks on every layer: removed, which leaves one
  +3V3_D connection open.

**24 unrouted**, 0 errors, 0 parity problems. L2 carries only GND; L5 GND and 19.5 mm of
XADC_GND. Every analogue net of the front ends is now routed.

Then three region passes in parallel on that board: the DACS box with the 15 DACS nets first
(24, no gain), with the six DACS nets still open first and the rest of the bus after them
(**20**), and the box right of the BGA with its open slow nets first (25). The second was taken:
**24 → 20 unrouted**, 0 errors, 0 parity problems; it also closed the open +3V3_D connection and
took XADC_GND off L5, so L2 and L5 carry only GND.

**A wider ring round the BGA (17–19 Oct).** Three placements routed in parallel with the same
chain: the part-free ring round U1101 at 3.5 mm (`BB_RING`, 2.5 until then), 0.6 mm between
parts (`BB_CLEAR`), and both (ring 3.0). After the DACS pass: 21, 49 and 41 unrouted. The 3.5 mm
ring was kept, from its third finishing pass rather than the end of the chain: that pass had
reached 20 unrouted but was dropped for four clearance errors of 0.1493 mm against 0.15 (+3V3_D
vias beside slow tracks, a rounding of the router's grid). `_work/layout/nudge_vias.py` moves
each such via (and its own tracks' ends) by under 0.01 mm until the clearance holds. Then, on
that board:
- the router's plane step had put 30 +3V3_D tracks on L2: removed. They had been carrying
  +3V3_D across an L4 background cut by 74 signal tracks under the BGA, so 25 unrouted;
- a region pass over the whole BGA (box 139–167 × 138–162 mm, the DACS nets and the open slow
  nets first, L4 keep-out under the BGA) took the signal tracks on L4 there from 74 to 11 and
  reached **17**; the DACS box alone gave 19, the open nets first 24;
- `route_finish.sh` on the supplies only (L4 open to them): 15;
- one ADCR_D1_N leg on L2 removed and the open LVDS legs re-routed on L1, L3 and L6;
- two ADCR_D4_N vias 0.14 mm apart (hole to hole) merged into one;
- `route_finish.sh` on the supplies only once more, on a 0.025 mm grid (19 Oct): 14, one +3V3_D
  connection closed.

**24 → 20 → 15 → 14 unrouted**, 0 errors, 0 parity problems; L2 and L5 carry only GND.

What did not help (19 Oct, run in parallel on two extra machines): about 45 region passes from the
15 board, with other boxes, other nets first and other orders, reached 16 at best, so region
passes are now zero-sum; new placements with a 4.0 or 4.5 mm ring, or 3.5 mm with 0.6 mm between
parts, routed worse (30, 35 and 45 unrouted after the finishing passes, against 25 for 3.5 mm).

### 6.3 What is left

1. **The 14 unrouted connections.** By group: supplies (3: +2V5 at ball R4, two +3V3_D
   connections where the L4 background is cut); single legs of LVDS pairs (4: ADCS_D1_P,
   ADCS_D1_N, ADCS_FCO_N, LINK_RX_D1_P); J101, IAS1 (2: J_LINK_TX_D0_P, HK_SDA); slow control
   lines (5: CLK_SEL, HK_SDA, MODE_M1, SW_CTRL1, F_DACS_D10 at RN1105, which KiCad reports under
   an RN1107 "unconnected-" name).
2. **No supply track on L2 or L5** after any further routing: check, as §6.2.
3. **The LVDS pairs.** Re-route the ADC data pairs as pairs, on L1, over unbroken L2.
4. **Re-run `drop_dangling.py`** after any rip-up, before ordering.
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
