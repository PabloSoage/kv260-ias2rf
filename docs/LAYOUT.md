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

**It is autorouted, not finished** (2–5 October 2026, §6): 89 connections are left for KiCad, and
the LVDS pairs need a hand review.

The original Allied Vision board is kept, untouched, as
`_deprecated/CSI2-KRIA-KV260_Rev01_AlliedVision.kicad_pcb`.

---

## 1. Outline: 119 × 120 mm

| | |
|---|---|
| **Kept from the original** | The upper, U-shaped part: the two tongues that reach the IAS connectors, and the band over the carrier down to its edge (y 117.25). It is known to clear every part on the KV260 (INTERFACE_SPEC §5.3) |
| **Changed** | The IAS0 tongue's right edge moves from x 144.9 to **142.4**, 1.5 mm clear of the carrier's J18 jumper. The original overlapped it by 1.0 mm (INTERFACE_SPEC §5.3) |
| **Removed** | The slots for the cameras' flat cables along the old bottom edge |
| **New** | Everything from y 127.25 to **y 202.75**, full width. Outward, off the carrier, where the KV260 has nothing at all |

**Why 120 mm and not the ~90 estimated before the schematic existed.** The parts' courtyards add up
to **5,700 mm²**. At 119 × 90 mm they would cover 75 % of a board that is populated on one face
only, with nothing left to route between them. At 119 × 120 mm they cover about half. The
overhang past the carrier's edge is now 85 mm, which is why three supports are added at the outer
edge.

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
| **H3, H4, H5**, supports | (93.0, 197.75), (148.5, 180.5), (204.0, 197.75) | 8 mm M3 standoffs to the surface the KV260 stands on (INTERFACE_SPEC §5.3: 7.9 mm) |

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
| Track / clearance | 0.10 mm minimum; 0.15 mm default |
| Via | 0.45 mm pad, 0.2 mm drill |
| Copper to edge | 0.3 mm |

| Net class | Track | Applies to (patterns in the project file) |
|---|---|---|
| **LVDS100** | 0.117 mm, gap 0.150 mm (100 Ω differential on L1) | Link pairs, ADC data and clock pairs, `CLK_ADC*`, `CLK_FPGA`, `FPGA_CLK` |
| **RF50** | 0.183 mm (50 Ω on L1) | `IF_RX_*`, `IF_TX_*` |
| **Power** | 0.4 mm | Every rail, VIN and switch nodes |
| Default | 0.15 mm | The rest |

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
- **the AERIS ribbon** (IDC 2×20), along the top of the main area;
- **the Pmod and JTAG headers**;
- **the FPGA**, rotated 90°, so bank 15 faces the DACs and bank 14 faces the ADCs and J101. **A
  2.5 mm ring around it is kept free of parts**, so the outer rows can escape on L1 and the inner
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
| Right | CLOCK, ADC_RADAR, ADC_SDR |
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
to include its own silkscreen, is free. The spot must be inside the outline, and off the carrier
if the part is through-hole.

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

### 6.1 The autorouted board (2 October 2026)

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
| Finishing pass (5 Oct) | `_work/layout/route_finish.sh`: every complete net written into the project as protected, then only the incomplete nets routed on a 0.05 mm grid. 100 → 89 unrouted, none worse. Allowing rip-up instead made it worse: the router broke the link pair and an IF line to route others |
| DRC (zones refilled, schematic parity) | **0 parity problems. 89 connections unrouted**. **1 clearance error** (RF50, 0.197 mm against 0.2). 2 hole-to-hole: two pairs of same-net vias 0.08 and 0.2 mm apart, each needed (removing either drops a connection): merge them by hand |

**The Power class clearance is now 0.15 mm** (was 0.2): the rails are 12 V at most, where IPC-2221
asks 0.1 mm, and 0.2 mm kept the router out from between fine-pitch pins. RF50 keeps 0.2 mm,
because there it is part of the 50 Ω line.

**An external autorouter was tried first and stopped at about 540 unrouted** after nine passes and six hours.
The bridge for it stays in the repo (`dsn_export.py`, `ses_import.py`): one polygon per plane
net and keepout strips at the edge are what made it route at all.

### 6.2 What is left, by hand in KiCad

1. **The 89 unrouted connections.** Most are long (median about 26 mm), to and from the FPGA: the
   DAC buses through the RN11xx arrays, JTAG, the ADAR ribbon, the HK bus from J101. Congestion
   round the BGA, not hard geometry. `route_finish.sh` can be run again for a few more.
2. **The LVDS pairs.** Only 5 of 26 were routed coupled end to end (the link pairs and CLK_FPGA);
   the router judged the other 21 electrically short and routed their legs singly. Re-route the
   ADC data pairs as pairs, on L1, over unbroken L2.
3. **The last RF clearance** (0.197 mm, at T802), and the **2 hole-to-hole** via pairs (ADCR_D7_P
   near 172.5, 155.4; ADCS_FCO_N near 174.2, 145.4).
4. **Re-run `drop_dangling.py`** after any rip-up, before ordering.
5. **Check the planes** after a refill: every L4 island fed by vias, L2 unbroken under the pairs.

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
