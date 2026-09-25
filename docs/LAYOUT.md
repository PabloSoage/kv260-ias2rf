# Layout — board, rules and first placement

*25 September 2026 · `CSI2-KRIA-KV260_Rev01.kicad_pcb` · built by `_work/layout/build_board.py`
from the schematic's netlist*

The Rev03 board exists. It has:
- the outline and the 6-layer stackup;
- design rules and net classes;
- the two ground planes;
- **every one of the 472 parts with its nets**, linked to its symbol;
- the holes and fiducials;
- a first placement.

**It is not routed.** Routing is the next step, done in KiCad (§6).

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

The stackup is POWER_AND_STACKUP §2.1 exactly: 6 layers, 1.56 mm.

| Layer | Use | Dielectric below |
|---|---|---|
| L1 F.Cu | SIG: IAS pairs, converter LVDS, IF lines | prepreg 0.100 mm, Er 4.05 |
| L2 In1.Cu | **GND plane** (zone drawn, to fill in KiCad) | core 0.200, Er 4.30 |
| L3 In2.Cu | SIG | prepreg 0.800, Er 4.30 |
| L4 In3.Cu | PWR, split planes (to draw) | core 0.200, Er 4.30 |
| L5 In4.Cu | **GND plane** (zone drawn) | prepreg 0.100, Er 4.05 |
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
| **LVDS100** | 0.136 mm, gap 0.150 mm (100 Ω differential on L1, POWER_AND_STACKUP §2.2) | Link pairs, ADC data and clock pairs, `CLK_ADC*`, `CLK_FPGA`, `FPGA_CLK` |
| **RF50** | 0.174 mm (50 Ω on L1) | `IF_RX_*`, `IF_TX_*` |
| **Power** | 0.4 mm | Every rail, VIN and switch nodes |
| Default | 0.15 mm | The rest |

The impedance widths are closed-form estimates, ±10 %. They must be replaced with the chosen
fabricator's field-solver numbers before ordering (POWER_AND_STACKUP §2.5).

---

## 4. Placement: the first pass

**Anchored by hand:**
- the 12 SMAs, along the bottom edge at 8.5 mm pitch;
- the DC jack, opening at the left edge;
- the AERIS ribbon (IDC 2×20), along the top of the main area;
- the Pmod and JTAG headers;
- the FPGA, rotated 90°, so bank 15 faces the DACs, bank 14 the ADCs and J101.

**Everything else** goes to its sheet's region:

| Region | Sheet |
|---|---|
| Left | POWER, beside the jack |
| Centre-left | DAC_RADAR, DAC_SDR |
| Centre | CONTROL, around the FPGA |
| Right | CLOCK, ADC_RADAR, ADC_SDR |
| Top-right tongue | IAS_LINK, beside J101 |
| Bottom band | ROUTING, beside the SMAs |

Within its region a part keeps the relative position it has on its schematic sheet, scaled down,
so a chip lands with its own passives around it. A legaliser then moves each part, biggest first,
to the nearest spot where its courtyard is free, inside the outline and off the carrier if it is
through-hole.

**This is a starting point, not a layout.** It puts parts in the right neighbourhood. Moving them
to their best positions, the decoupling capacitors above all, is done in KiCad as the routing is
planned.

---

## 5. How it was checked

| Check | Result |
|---|---|
| `kicad-cli pcb drc --schematic-parity` | **0 parity problems**: every symbol has its footprint, every pad its net. **No shorts, clearance or courtyard violations** |
| | **499 unconnected**: the unrouted board. **~430 silkscreen warnings**: reference designators on top of each other and of pads, to tidy as parts are moved; the Hirose footprints' 0.5 mm pin-number text is below the default minimum height |
| J101/J102 against the original board | Position, face, rotation and all 38 pads identical. Nets as INTERFACE_SPEC §3–§4 (pin 4/5 `LINK_RX_D0`, 7/8 `LINK_RX_CLK`, 14 `HK_SCL`, 21 `FPGA_PROG_B`, 22 `HK_SDA`, 15 `FPGA_IRQ`: moved from 32 after the check against the carrier, INTERFACE_SPEC §4.3) |
| Footprints | All 472 exist. Four are new, in `footprints/kv260-ias2rf.pretty` (`_work/make_footprints.py`): ADCLK948 and AD9484 LFCSPs with their datasheets' exposed pads, the M3SWA2's DQ3005 from its Mini-Circuits case drawing, and the Hirose BM20B |

Parts chosen for this step, each checked against its datasheet (all fetched by
`_work/fetch_datasheets.py`):

| Part | Choice | Why |
|---|---|---|
| **T701, T801, T802** | **Mini-Circuits ADT2-1T+**, CD542 | Impedance ratio 2, 0.4–450 MHz, 50 Ω. The 100 Ω secondary (6/4) goes to the DAC, the primary (3/1) to the line. KiCad's PL-052 variant of the footprint grounds pin 4, which a balun must not, so the plain CD542 pads are used |
| **L1001** | Bourns SRP7028A-8R2M | Isat 7.5 A ≥ the LMR33630's 5.05 A current limit; Irms 4 A |
| **L1010, L1020, L1030** | Bourns SRP7028A-3R3M, -3R3M, -2R2M | Isat 12 / 12 / 14 A ≥ 3.5 A |
| **Q1001** | Diodes DMP3013SFV | −30 V, −12 A, 9.5 mΩ at −10 V, VGSS ±25 V |

---

## 6. What comes next: routing, in this order

1. **Fill the planes** (L2, L5) and draw the power splits on L4.
2. **The link**: five pairs from J101 on the bottom face. Via to L1 once, then run on L1 over an
   unbroken L2 to the AC-coupling capacitors and the FPGA. Keep the N-before-P pairs as they are
   (INTERFACE_SPEC §3.2).
3. **Clocks**: the ADCLK948 outputs to the AD9484, AD9253 and the FPGA's CLK_FPGA pad, as
   100 Ω pairs.
4. **ADC LVDS**: AD9484 (10 pairs) and AD9253 (4 pairs) into bank 14, terminations at the FPGA.
5. **FPGA fan-out** with 0.2 mm vias, then the DAC buses through the 22 Ω arrays.
6. **IF lines** as 50 Ω on L1, through the switches to the SMAs.
7. **Power**, then the slow signals.

Before anything is ordered: the fabricator's stackup, and DRC with zero errors and zero
unconnected items (ROADMAP phase 3).

```
py _work/layout/build_board.py        # rebuilds the board: overwrites any hand placement
kicad-cli pcb drc --schematic-parity CSI2-KRIA-KV260_Rev01.kicad_pcb
```

**Once parts are moved or tracks laid by hand, do not run `build_board.py` again.** From then on the
board file is the source, as the drawn sheets are once accepted.
