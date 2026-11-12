# Signal and power integrity — review of 11 November 2026

*Board `CSI2-KRIA-KV260_Rev01.kicad_pcb` as committed on 11 Nov · stack JLC06161H-2116A · figures
and their data in [`docs/sim/`](sim/)*

> **12 November 2026: the board is now 8 layers (JLC08161H-2116C).** Sections 1–7 are the record of
> the 6-layer review. §8 is the 8-layer board, measured with the same scripts and compared with the
> 6-layer one and with an ideal line; where it changes a statement above, §8 says so.

An RF/high-speed engineer looked at the board of 10 November and raised the points below. Every one
was checked against the board's own copper, fixed where it was right, and measured or simulated
again. This page is the record: what was wrong, what changed, the numbers before and after, and
what is still a compromise.

| Point raised | Verdict | Now |
|---|---|---|
| The switch → SMA legs were not 50 Ω | **Right**: the RF50 net class missed the auto-named nets, so they were 0.10 mm | Every RF50 net (28) at 183 µm, checked by net class and DRC (§2); the only narrower copper is deliberate: 0.15 mm necks at 0.5 mm-pitch pins and 0.1 mm sections that tune out each ESD diode (§7.1) |
| The SMA launch is not a transmission line | **Right**: one ground via per SMA, pad over L2 | Three vias per ground leg, L2–L4 cut out under the pad; openEMS: return loss 13.5 → 24.5 dB at 1 GHz (§2.1) |
| Controlled impedance and length matching | Half right: lengths were matched, but the LVDS legs were 59 Ω single tracks (119 Ω pairs) | Legs widened to 50 Ω where they run apart: 74 % of their length at 50 Ω, eye as an ideal pair (§3) |
| Power planes / decoupling loop inductance | **Right** for VCCINT: its L4 island was cut off from its own decoupling and from the regulator by the plane clearance | Zone clearance 0.15 mm, island extended under its caps, four 0.47 µF on the bottom face under the BGA; VCCINT meets its target to 100 MHz (was over it from 26 MHz) (§4) |
| Autorouted, "random" placement | A style point | The checks below are what decides whether it works; they were all run |

Other things a reviewer would look at, found and fixed in the same pass: return vias at the LVDS
and clock layer changes, two clock lines coupled at −19.5 dB, a clock leg beside a data leg on the
link, legs of different pairs side by side (§3.5), exposed pads without vias, the board edge without stitching, the power plane running to the
edge (§5).

---

## 1. Stack and impedance

2D field solver (`_work/field_solver.py`, finite differences on the 2116A cross-sections; JLCPCB's
calculator agrees within 1–3 %, POWER_AND_STACKUP §2.6):

| Line | Width | Z0 |
|---|---|---|
| L1/L6 microstrip over L2/L5 (0.1164 mm) | 0.183 mm | 49.8 Ω |
| L3 stripline (L2 0.13 mm above, L4 0.93 mm below) | 0.175 / 0.183 mm | 50.2 / 48.9 Ω |
| L4 track (L5 0.13 mm below, L2 1.06 mm above) | 0.175 mm | 50.4 Ω |
| L1 RF line beside the L1 ground pour, 0.3 / 0.5 mm gap | 0.183 mm | 49.3 / 49.8 Ω |
| Neck-down at a 0.5 mm-pitch pin (first mm) | 0.15 mm | 53–54 Ω |

Every signal layer has a ground plane 0.12–0.13 mm away: L1 and L3 reference L2, L4 and L6
reference L5. That is why a split in L4 (the power layer) under an L3 line costs little: the line's
return runs in L2.

**Reference-plane check.** The two ground planes were filled the way KiCad fills them and every
RF50/LVDS/clock segment was walked in 0.1 mm steps: is the strip under it (trace width + 0.1 mm a
side) solid copper? Over 3,628 mm, 10 places run more than 1 mm over a void, 11 mm in all, each a
crossing of a via cluster's antipads in the BGA field. No slot, no split.

---

## 2. RF band (switch → DC block → SMA)

Rebuilt by hand, not by the router:

- every leg a straight 183 µm microstrip on L1, no via, 100 pF DC block next to the switch pin;
- the DC-bias parts (100 nF, Zener, resistors) moved to the bottom, under each switch cell;
- four vias in each switch's exposed pad; L1 and L6 ground pours over the band, tied to L2/L5 by a
  via fence 0.8 mm off each line at 1 mm pitch (226 vias);
- the 64.9 Ω terminations of the long IF lines moved under their DC-block caps (R501, R601, R621):
  the 7–10 mm stubs to them are gone;
- the RF50 net-class patterns now cover the auto-named nets (`Net-(J4*-In)`, `Net-(J9*-In)`,
  `Net-(U90*-RFOUT*)`, U401's clock nets). A design rule (`CSI2-KRIA-KV260_Rev01.kicad_dru`) lets
  the 0.15 mm neck at a 0.5 mm-pitch pin keep the default clearance, and a second one keeps the
  ground pour 0.24 mm off the 0.1 mm ESD compensation sections (§7.1).

The eight long RF lines (six IF, CLK_REF_IN, CLK_OUT) are 183 µm end to end with at most two vias
each, and every via has two ground vias within 0.75–1.8 mm.

### 2.1 SMA launch, simulated

openEMS 0.37 (FDTD), the stack as built, FR-4 loss tan δ 0.02, the L1 pour, the via fence and the
SMA's stitching vias. Through-line model: 183 µm line → the SMA's 1.27 × 3.2 mm signal pad → line.
A bare line through the same set-up is the control: |S11| ≤ −32 dB, |S21| −0.15 dB to 4.5 GHz.

![SMA launch](sim/sma_launch.png)

| |S11| | 0.5 GHz | 1 GHz | 2 GHz | 3 GHz |
|---|---|---|---|---|
| Pad over L2 (10 Nov) | −19.4 dB | −13.5 dB | −8.0 dB | −5.2 dB |
| L2–L4 cut out under the pad | −30.2 dB | −24.4 dB | −19.0 dB | −16.4 dB |
| Cut-out + ESD diode, uncompensated | −34.0 dB | −26.8 dB | −17.6 dB | −11.8 dB |
| **Cut-out + ESD diode, compensated (on the board, §7.1)** | **−39.0 dB** | **−30.6 dB** | **−19.9 dB** | **−13.5 dB** |
| Bare line (the set-up's floor) | −42.5 dB | −38.4 dB | −33.8 dB | −31.9 dB |

The wide pad 0.116 mm over L2 is a 13 Ω shunt capacitance; with the planes cleared it references
L5 (1.36 mm down) and comes close to 50 Ω. |S21| at 3 GHz: −1.76 → −0.28 dB.

How to read the figure: the bare line is not a target a connector can reach, it is what the
simulation itself returns for a uniform 50 Ω line with no connector (mesh and port error), so it is
the floor. The band the SMAs carry ends at 500 MHz (shaded). There the board's launch is at
−39 dB, 3.5 dB from the floor; return loss better than 20 dB (VSWR 1.22, the dotted line) holds to
2 GHz, four times the highest frequency used. Above 2 GHz the ESD diode's capacitance shows: the
cost of protecting the connector, and outside the band.

---

## 3. LVDS

### 3.1 What the router left

The LVDS pairs (link to the Kria, both ADCs' data and clocks) were laid as two separate legs:
89 % of their length runs more than 1 mm apart, so they are loosely coupled pairs. A loosely coupled
pair's impedance is twice its legs' Z0, and the legs were 0.117 mm (the coupled-pair width):
59 Ω each, 117–119 Ω for the pair against a 100 Ω termination.

### 3.2 What changed

Each leg was widened to its layer's 50 Ω width (0.183 mm on L1/L6, 0.175 mm on L3/L4) wherever the
clearances allow, judged in 0.5 mm pieces so a leg necks only where something is in the way. The
centre lines did not move, so lengths and skew are unchanged.

| Width | Length | Leg Z0 | Pair |
|---|---|---|---|
| 0.183 / 0.175 mm | 1,896 mm, 74 % | 49–50 Ω | ≈ 100 Ω |
| 0.15 mm | 270 mm, 11 % | 53–54 Ω | ≈ 107 Ω |
| 0.13 mm | 102 mm, 4 % | 57 Ω | ≈ 114 Ω |
| 0.117 mm (no room: BGA escapes) | 237 mm, 9 % | 58–59 Ω | ≈ 118 Ω |
| coupled stretches, left as they were | 55 mm, 2 % | — | 100 Ω |

### 3.3 Eye, simulated

ngspice, PRBS7 at 1 Gb/s, LVDS current driver (3.5 mA, 300 ps edges), 100 Ω across the receiver and
2 pF per input; each leg is its own copper by layer and width, with Z0 and delay from the field
solver, the mismatched sections put together at the receiver end (ordered by Z0; sections under
3 mm lumped). Re-run on the final board of 11 Nov (with the ESD parts); differences from the first
run are within 15 mV and 10 ps.
Three cases per pair: an ideal 100 Ω pair of the same length and termination, the board on 6 layers
(11 Nov) and on 8 layers (12 Nov, §8).

![LVDS eyes: ideal, 6 and 8 layers](sim/rev04_eyes.png)

| Pair | 6 layers: ideal / routed | 8 layers: ideal / routed |
|---|---|---|
| ADCR_D0 | 600 / 583 mV, 29 / 25 ps | 634 / 632 mV, 16 / 16 ps |
| ADCR_D1 | 515 / 484 mV, 14 / 15 ps | 474 / 473 mV, 19 / 19 ps |
| ADCR_D2 | 594 / 481 mV, 27 / 56 ps | 465 / 463 mV, 23 / 23 ps |
| ADCR_D3 | 531 / 526 mV, 62 / 53 ps | 464 / 463 mV, 23 / 23 ps |
| ADCR_D4 | 542 / 557 mV, 34 / 54 ps | 633 / 607 mV, 19 / 17 ps |
| ADCR_D5 | 458 / 446 mV, 54 / 71 ps | 505 / 505 mV, 16 / 16 ps |
| ADCR_D6 | 540 / 513 mV, 20 / 41 ps | 471 / 500 mV, 22 / 25 ps |
| ADCR_D7 | 633 / 609 mV, 18 / 18 ps | 471 / 466 mV, 16 / 17 ps |
| ADCR_DCO | 626 / 581 mV, 24 / 35 ps | 609 / 610 mV, 17 / 18 ps |
| ADCR_OR | 450 / 465 mV, 69 / 85 ps | 647 / 646 mV, 19 / 18 ps |
| ADCS_D0 | 581 / 564 mV, 41 / 51 ps | 618 / 614 mV, 22 / 25 ps |
| ADCS_D1 | 589 / 533 mV, 53 / 39 ps | 625 / 607 mV, 16 / 15 ps |
| ADCS_DCO | 597 / 602 mV, 40 / 35 ps | 632 / 609 mV, 18 / 20 ps |
| ADCS_FCO | 648 / 650 mV, 49 / 46 ps | 628 / 617 mV, 17 / 17 ps |
| FPGA_CLK | 448 / 446 mV, 16 / 17 ps | 517 / 499 mV, 29 / 29 ps |
| LINK_RX_CLK | 548 / 516 mV, 12 / 14 ps | 395 / 392 mV, 10 / 10 ps |
| LINK_RX_D0 | 607 / 559 mV, 35 / 30 ps | 509 / 457 mV, 25 / 31 ps |
| LINK_RX_D1 | 575 / 559 mV, 75 / 77 ps | 385 / 372 mV, 41 / 51 ps |
| LINK_TX_CLK | 661 / 635 mV, 63 / 69 ps | 642 / 643 mV, 63 / 63 ps |
| LINK_TX_D0 | 664 / 653 mV, 65 / 68 ps | 674 / 665 mV, 64 / 62 ps |

*Eye opening at the centre of the bit, then zero-crossing spread; each board against the ideal line of its own pair length and termination.*

The ideal line differs between the two boards because the pair lengths and the termination point
changed (on 8 layers every termination sits on the FPGA's ball vias). The opening is in every case
several times the receiver's ±100 mV threshold. For LINK_RX the model ends at the AC capacitors,
so those eyes are indicative only. The numbers are in [`docs/sim/`](sim/) (`lvds_eye.csv`).

**On the rate.** IAS1 carries five pairs, but two are source-synchronous clocks: three data lanes
at up to 1 Gb/s each (two to the Kria, one back; INTERFACE_SPEC §3). What signal integrity sees is
the rate per lane, 1 Gb/s.

### 3.4 Skew

Unchanged by the widening (`_work/layout/lvds_skew.py`, pin to pin). One change: **LINK_RX_CLK**
was −60 ps, over the 50 ps rule of LAYOUT §6.3; its P leg now has 10 mm of meander on L1, on the
side of its own N leg: **0 ps**. Data to clock on LINK_RX: D0 +79 → +51 ps, D1 +207 → +177 ps
(the Kria's IDELAYE3 trains these).

**With the FPGA's package delays** (11 Nov evening). The figures above are pad to pad. AMD gives each
XC7A50T-FTG256 ball's flight time inside the package (Vivado `get_package_pins`, MIN_DELAY and
MAX_DELAY; 35–133 ps across the I/O balls). They are in `_work/layout/xc7a50t_ftg256_pkg_delays.csv`, and
`lvds_skew.py` now adds each FPGA ball's mean delay to its leg (`--no-pkg` for pad to pad):

| | Pad to pad | With the package |
|---|---|---|
| Package share of a pair's P−N | — | −4.4 to +9.4 ps |
| Worst P−N, pairs at 1 Gb/s | ±42 ps | ±40 ps (ADCS_D1 +40, LINK_TX_CLK −36) |
| LINK_RX data − clock | D0 +51, D1 +177 ps | D0 +41, D1 +190 ps |
| LINK_TX data − clock | +2 ps | −17 ps |
| ADCS (AD9253) data − DCO | −74 to +45 ps | −81 to +26 ps |
| ADCR (AD9484) data − DCO | −80 to −16 ps | −88 to 0 ps |

The P−N skews stay within the rule. The data-to-clock offsets are what each lane's IDELAY calibrates
at start-up (78 ps taps on the Artix-7, 1.1 ns range on the K26's IDELAYE3).

### 3.5 Crosstalk

Parallel runs closer than three widths for more than 2 mm were listed and the coupling computed
with the field solver (even/odd mode):

| Run | Before | Fix | After |
|---|---|---|---|
| U401's reference input (CLK0) and its output Q3, 47 mm side by side on L3 | 0.22 mm gap, NEXT −19.5 dB: the buffer's output fed back into its own input pin | Q3 moved out to the board edge (x 207.55) and its diagonal 1.3 mm off | 1.0–1.3 mm, about −45 dB |
| LINK_RX_CLK_P beside LINK_RX_D0_P, 31 mm on L1 | 0.16 mm gap, about −18 dB | Each P leg moved next to its own N leg | 1.0 mm between the pairs, about −46 dB |

**Legs of different pairs side by side.** Because the pairs are not coupled, a leg can run beside
a leg of another pair with nothing of its own partner to cancel it. Every fast leg was walked in
0.25 mm steps against every other pair's copper on its layer: 133 mm (of 3,639 mm) ran with less
than 0.25 mm to another pair's leg, at the class clearance of 0.15 mm in the worst places. Field
solver, 0.183 mm legs on L1/L6: backward coupling 14.5 % at a 0.15 mm gap, 7.7 % at 0.25 mm,
4.6 % at 0.35 mm, 2 % at 0.55 mm (L3: 16.7 / 9.7 / 6.1 / 2.8 %). A run shorter than 25 mm (half
a 300 ps edge) couples in proportion to its length.

Where there was room the leg was moved away with a 45° jog at each end (seven runs, 42 mm; skew
changed by 3 ps at most): ADCS_FCO_N off ADCS_D1_N (14 mm, 0.15 → 0.35 mm), off LINK_RX_CLK_P,
ADCR_D2_P off ADCR_D0_P, LINK_RX_D0_N off ADCR_OR_N and three shorter ones. **98 mm are left**
with less than 0.25 mm, none with room to move without re-routing its neighbours. The worst:

| Run | Layer | Length under 0.25 mm | Near-end crosstalk on the victim leg |
|---|---|---|---|
| ADCR_D0_P beside ADCR_D1_N | L6 | 12.6 mm at 0.15 mm | 7 % of the aggressor's swing |
| ADCR_D1_P beside ADCR_D3_P | L1 | 7.7 mm | 4.5 % |
| F_DACR_CLK beside LINK_RX_CLK_N | L1 | 6.4 mm | 3.7 % |
| ADCR_D4_P beside ADCS_FCO_P | L1 | 6.0 mm | 3.5 % |
| ADCR_OR_N beside ADCS_D1_P | L6 | 5.7 mm | 3.3 % |
| ADCR_D6_N beside ADCR_D7_N | L1 | 5.6 mm | 3.2 % |
| LINK_TX_CLK_P beside LINK_TX_D0_N | L3 | 3.9 mm at 0.18 mm | 2.5 % |

7 % of a 350 mV leg is 25 mV on one leg of a pair whose eye opens 550–650 mV and whose receiver
threshold is ±100 mV: it works, with less margin than a coupled pair would have (a coupled pair
sees the same aggressor on both legs). These are in the escape between the FPGA and the two ADCs;
they go with the fan-out (§6). The rest of the list is a data leg beside a supply track, or flash
and I²C lines that are static while the board runs.

---

## 4. Power distribution

### 4.1 What was wrong

Measured on the board's copper (KiCad-style fill of L4, connectivity by overlap, 0.4 nH/mm of
track, via barrels by height; UG483's criterion is the impedance from 100 kHz to 10 MHz):

- **VCCINT's L4 island under the BGA was cut off from the strip that feeds it** from the buck. With a
  0.3 mm zone clearance, the 0.45 mm vias at 1 mm pitch leave no copper between them: the island
  reached the rest of +1V0 only through tracks. The same clearance on the GND planes left no web
  between neighbouring BGA vias.
- VCCINT's 0.47 µF caps reached the balls through 58–63 nH of track.

### 4.2 What changed

- **Inner-plane zone clearance 0.3 → 0.15 mm** (L2, L4, L5): 0.25 mm of copper between vias at
  1 mm pitch. JLCPCB's inner-layer minimum is 0.1 mm.
- The +1V0 island extended under the four 0.47 µF caps below the BGA (no +3V3_D via needs L4
  there) and a notch cut where it swallowed a DAC's +3V3_D via.
- Five vias in the buck inductor L1030's output pad, straight into the strip.
- Butted vias on decoupling pads where there was room (UG483: "never connect vias to the lands with
  a section of trace").
- **Four more 0.47 µF 0402 (C1184–C1187) on the bottom face inside the BGA footprint**, each pad on
  a +1V0 or a GND ball via (via in pad, filled and capped): L4 is 0.25 mm from the bottom face and
  1.18 mm from the top, so their loops are 0.60–0.71 nH, against 1.1–1.4 nH for the best top-side
  caps and 7–13 nH for the 4.7 µF ones. FPGA_IRQ was re-routed off one of them.

UG483's required caps for the XC7A50T in FTG256 (Table 2-2: VCCINT 1 × 330 µF, 3 × 4.7 µF,
5 × 0.47 µF; VCCBRAM 1 × 100 µF, 1 × 0.47 µF; VCCAUX 1 × 47 µF, 2 × 4.7 µF, 3 × 0.47 µF) are all
on the board. Artix-7 has no capacitors inside its package (UG483 p. 14), so the board's network is
all there is.

### 4.3 Impedance at the balls

![VCCINT](sim/pdn_1V0.png)

| Rail | Target | |Z| max, 0.1–10 MHz (before → now) | Over the target |
|---|---|---|---|
| +1V0 VCCINT | 120 mΩ | 67 → **51 mΩ** | 26 MHz and up → **nowhere to 100 MHz**; 470 → 61 mΩ at 100 MHz |
| +1V8_D VCCAUX, VCCO_35 | 700 mΩ | 127 → 109 mΩ | nowhere to 100 MHz |
| +2V5 VCCO_34 | 2 Ω | 149 → 146 mΩ | nowhere |
| +3V3_D VCCO | 1 Ω | 36 → 37 mΩ | nowhere |

Model (`pdn2.py`): each capacitor's loop is its ESL, its pads and vias, and the copper path to the
balls; the die draws on all its balls of a rail at once, so from a plane the paths to the balls are
in parallel. Both boards above are computed with the same model. Without the four bottom-side
caps VCCINT went over its target from 81 MHz (149 mΩ at 100 MHz). Above 100 MHz the package and
the die's own capacitance take over, which a board model cannot see; UG483 sets the board's job at
100 kHz–10 MHz, where VCCINT is at less than half its target.

The other rails' plots: [`sim/pdn_1V8_D.png`](sim/pdn_1V8_D.png), [`sim/pdn_2V5.png`](sim/pdn_2V5.png),
[`sim/pdn_3V3_D.png`](sim/pdn_3V3_D.png).

### 4.4 DC drop

Least-resistance copper path from the regulator to the balls (1 oz outer, 0.5 oz inner; parallel
paths ignored, so an upper bound):

| Rail | Current (FPGA's share) | Path | Drop |
|---|---|---|---|
| +1V0 from L1030 | 700 mA | 27–46 mΩ | 19–32 mV (1.9–3.2 %; 34–53 mΩ before the inductor's vias) |
| +1V8_D from U1006 | about 150 mA | 184–263 mΩ | 28–39 mV (1.5–2.2 %) |
| +2V5 from L1020 | about 100 mA | 287–307 mΩ | 29–31 mV (1.2 %) |

VCCINT's limit is ±5 %. With the TPS562201's ±1.5 % and 32 mV, the worst ball sits at about 0.958 V
at full estimated load: inside, with little to spare. If Vivado's power report comes in above
700 mA, set the buck to 1.02 V (one feedback resistor).

---

## 5. Other checks

| Check | Found | Fixed |
|---|---|---|
| Return vias at layer changes (LVDS, clocks) | 145 of 185 reference-changing vias without a ground via within 1 mm | 136 ground vias added (118 at 0.2 mm from other nets, then 18 more at the 0.15 mm the net classes ask for, two of them after moving a supply and an I²C track aside): 50 within 1 mm, 91 within 2 mm, 44 within 3 mm, **one at 3.1 mm** (ADCR_D4_P; λ/20 at the 1.2 GHz knee of a 300 ps edge is 6 mm). RF50: two within 1.8 mm, one exception with one |
| Exposed pads | LMR33630, all three TPS7A8300 (one dissipates 0.5 W), one AD8352 with **no via**; AD9253 3 vias in 31 mm² | Via grids in every pad (POFV): LMR33630 15, each TPS7A8300 4, AD8352s 2–5, AD9253 15, AD9484 16, ADCLK948 6 |
| Board edge | 256 of 1,122 points on the outline had a ground via within 3 mm | 176-via fence 0.8 mm in, 2.5 mm pitch (22 stations blocked by connectors) |
| Power plane at the edge | L4 ran to the edge with L2/L5 | Every L4 zone pulled back 1 mm from the edge |
| Plane splits under fast lines | None (§1) | — |
| Acute angles | 453 junctions under 90°, mostly overlapping collinear segments and the router's 45° steps | None: JLCPCB's process does not need it; no DFM flag |

---

## 6. What is still a compromise

- **11 of the FPGA's 69 supply balls have no via of their own.** Seven have a plane to reach and
  no room for the via: VCCINT K9, L8; GND A1, F8, G13, N5; +3V3_D L16. Each reaches its plane
  through a short top track to a neighbour's via (VCCINT: 7 of 9 balls have their own; the four
  bottom-side caps of §4.3 sit on those vias). The other four (+1V8_D A6, J2, K11; +2V5 R4) are on
  rails that have no plane under the BGA at all: they are fed by tracks, and a via would reach
  nothing. Their impedance is inside the target all the same (§4.3: 109 mΩ against 700, 144 mΩ
  against 2 Ω). Two ways were tried on every ball: ripping what blocks the spot and re-routing
  (GND K7, K14), and leaving the routing alone but bending the blocking tracks round the new via
  (VCCINT F7, G6; GND N15; +3V3_D T11); each kept only at zero unrouted and zero violations. What
  is left needs the escape of those rows redone.
- **The LVDS pairs are loosely coupled**, not routed as coupled pairs: 100 Ω by leg width, but
  less rejection of common-mode noise picked up on the way, and legs of different pairs side by
  side between the FPGA and the ADCs (§3.5: 98 mm under 0.25 mm, 7 % crosstalk on the worst
  leg). A pair-routed board is the better board; on this placement and pin assignment the pairs
  cross each other on the way out of the BGA, which is why the router could not keep them
  together. It is a change of FPGA pin assignment and escape, not a touch-up.
- **One LVDS layer change has its nearest ground via 3.1 mm away** (ADCR_D4_P; the limit set here
  is 3 mm, λ/20 at a 300 ps edge is 6 mm). The other 185 are within 3 mm, 141 of them within 2 mm.
- **VCCINT's 4.7 µF caps** sit 6 mm above the BGA, fed by track (7–13 nH): no room on either face
  over the island. UG483 allows "within two electrical inches"; the impedance target holds.

**What has not been simulated** (12 Nov). Everything above is 2-D field solving, circuit
simulation and the openEMS SMA launch. None of it replaces measuring a built board:
- **No 3-D full-wave model of the board.** The LVDS eyes use lossless lines with the field-solved
  Z0 and delay of each section, and the crosstalk figures are 2-D coupling coefficients times the
  parallel length. Vias, the BGA breakout and the Hirose connector enter only as lumped sections.
- **No cascade analysis of the RF chains.** The ADC drivers' gains (15 + 10 dB, as AERIS-10), the
  baluns, the anti-alias and reconstruction filters and the RF switches are drawn from their data
  sheets and application notes. Nobody has computed a noise figure, IP3 or ripple-and-gain budget
  per channel, nor simulated the filters' responses with the board's parasitics.
- **No thermal analysis** beyond the per-part dissipation and thermal vias in §7.
- **Nothing is measured.** The first boards are for evaluation: the link's bring-up test is in
  IAS_LINK_SPEC §6, and its capacity and rate ceiling in §7.

How each of these would be done is in §9.6. §9 also covers the rest of the board: the supply
tracks, fixed on 12 Nov (§9.1), and what is still open there (§9.2–9.4).

## 7. Environment

| | State |
|---|---|
| Temperature | Every IC industrial or better: XC7A50T-2FTG256**I** (Tj −40 to 100 °C), ADCs, drivers, clock buffer, DACs, regulators −40 to 85/125 °C, RF switches −55 to 105 °C, Hirose BM20B −35 to 85 °C. Capacitors X7R/X5R (X5R to 85 °C) |
| Heat | The 0.5 W LDO now has its thermal vias; the bucks are SOT-23 parts at ≤ 0.4 W |
| Input | 12 V: PTC, reverse-polarity P-FET, SMBJ15CA TVS (POWER_SPEC). Vehicle use needs ISO 7637-2 (VEHICLE_PLATFORM V-05) |
| Mechanics | Five M3 holes (two through the KV260, three to standoffs); edge SMAs soldered and through the board. For vibration: staking of the SMAs and the 7343 capacitor, or a conformal coat, at assembly |
| EMI | Ground planes next to every signal layer, edge fence, power plane pulled back, return vias (§5) |
| ESD | Every external connector: a PESD5V0F1BL (0.4 pF, bidirectional, IEC 61000-4-2) on each of the 12 SMAs, 2.15 mm from the SMA pad and tuned out by 0.1 mm line sections either side; TPD4E05U06DQAR four-channel arrays (0.5 pF) on the Pmod (U1108, U1109) and JTAG (U1110) next to their headers. Each ground pad has its own GND via (0.4–1 mm). The 12 V input already has its SMBJ15CA. §7.1 |

### 7.1 ESD on the SMAs

The SMAs carry HF from 100 kHz, the wideband SDR to about 250 MHz, the radar IF at 120 MHz and the
reference clock to 500 MHz. A shunt inductor to ground (an "RF choke") that does not load 50 Ω at
100 kHz needs more than 80 µH, which self-resonates at a few MHz: it would short VHF and protect
nothing. A low-capacitance TVS is the part for this band. openEMS, the launch of §2.1 with the
diode's pad and 0.5 pF where it is placed (2.15 mm from the SMA pad):

| | 0.5 GHz | 1 GHz | 2 GHz | 3 GHz |
|---|---|---|---|---|
| S11, diode alone | −34.0 dB | −26.8 dB | −17.6 dB | −11.8 dB |
| **S11, compensated (on the board)** | **−39.0 dB** | **−30.6 dB** | **−19.9 dB** | **−13.5 dB** |
| S21, compensated | −0.15 dB | −0.15 dB | −0.20 dB | −0.37 dB |

The diode is a shunt capacitance on the line. It is tuned out by two short high-impedance sections
either side of it (series inductance, so the three make a low-pass π section close to 50 Ω): the
line is 0.1 mm wide from the DC-block pad up to the diode pad (0.76 mm, all the room there is) and
for 1.4 mm past it towards the SMA, with the ground pour kept 0.24 mm off them (a design rule).
openEMS sweep of the length, 0.1 mm each side: 0.8 mm −38.3 dB at 0.5 GHz, 1.4 mm −39.4, 2.0 mm
−37.1, 2.8 mm −32.2; 0.8 mm before and 1.4 or 1.8 mm after, as fits: −39.0 dB
(`_work/sim/sma_launch.py tvsnAA_BB`). With it the launch with the diode is better in the band
than the bare cut-out was (−30.2 dB at 0.5 GHz).

## 8. Eight layers (12 November)

The stack moved to JLC08161H-2116C: L1 · L2 GND · L3 · L4 PWR · L5 GND · L6 · L7 GND · L8, with
2116 prepreg (0.1194 mm) under the outer layers, so the 183 µm RF width and the SMA launch stand.
Field solver (`_work/field_solver8.py`):

| Line | Width / gap | Z |
|---|---|---|
| L1/L8 microstrip | 0.183 mm | 50.4 Ω |
| L3/L6 stripline, single | 0.151 mm | 50 Ω |
| L3/L6 coupled pair | 0.10 / 0.15 mm | 100.2 Ω |
| L3/L6 pair under the FPGA | 0.09 / 0.12 mm | 98.5 Ω |
| L1 coupled pair | 0.117 / 0.15 mm | 100.4 Ω |

What changed on the board: L4 carries no signal; L6 lies between two ground planes; 9 of the 19
LVDS pairs are coupled 100 Ω pairs end to end and the other 10 are two 50 Ω legs matched to ±5 ps;
every 100 Ω termination sits on its pair's two ball vias on the bottom face (no stub); LINK_TX is
terminated at the FPGA (R105/R106 added, R101–R104 now 10 k bias), where before the 2 × 49.9 Ω at
the connector left the FPGA's receiver at the end of a 45 mm open line.

| Check | 6 layers (11 Nov) | 8 layers (12 Nov) |
|---|---|---|
| DRC | 0 errors, 0 unconnected, 0 parity | 0 violations of any kind, 0 unconnected, 0 parity |
| Pairs coupled | 0 of 19 | 9 of 19 (ADCR_D4 41 %) |
| Worst intra-pair \|P−N\|, package included | 84 ps | 9 ps |
| Layer changes without a GND via within 3 mm | 1 of 186 | 0 of 89 |
| Track over a plane void | 10 runs, 11 mm | 5 runs, 5 mm |
| Legs of other pairs within 0.25 / 0.55 mm | 97.6 / 328.4 mm | 69.3 / 213.5 mm |
| Eye lost to the routing (routed − ideal, 20 pairs) | mean −22 mV, worst −113 mV | mean −8 mV, worst −52 mV |
| Zero-crossing spread added by the routing | mean 5 ps, worst 29 ps | mean 1 ps, worst 10 ps |
| VCCINT impedance (target 120 mΩ) | 51 mΩ max to 10 MHz, 61 at 100 MHz | 41 / 63 mΩ |
| +1V8_D / +2V5 / +3V3_D at 100 MHz | 545 / 488 / 40 mΩ | 545 / 460 / 37 mΩ |
| DC drop +2V5 at 601 mA | 173–185 mV | 122–129 mV (trunk widened to 0.5 mm) |
| SMA launch S11 at 1 / 3 GHz, with the ESD diode | −30.6 / −13.5 dB | −30.9 / −13.7 dB |

![LVDS eyes: ideal, 6 and 8 layers](sim/rev04_eyes.png)

The eye model drives each leg from a current source into the routed sections and a 100 Ω, 2 pF
receiver. The receiver's capacitance reflects and the driver re-reflects, so even the ideal line
has some ISI and it depends on length: the "ideal" of a pair differs between the two boards. The
fair comparison is each board against its own ideal line:

![Eye lost to the routing](sim/rev04_eye_penalty.png)
![Eye opening and spread, every pair](sim/rev04_eye_open.png)
![Intra-pair skew](sim/rev04_skew.png)
![PDN impedance](sim/rev04_pdn.png)
![SMA launch](sim/rev04_sma.png)

The third series in the eye and skew plots is the 6-layer board with the same corrections
(terminations at the balls, coupled pairs, LINK_TX at its receiver), routed the same way: only 8
pairs fit coupled, because under the FPGA L4 is +1V0 islands where no track may go and L3 is the
only inner layer, and the board could not be completed (seven nets left unconnected). On six layers
the schematic change, the +2V5 widening and the return vias carry over as they are; the stub-free
terminations and the coupled pairs need the second inner signal layer.

Still open on the 8-layer board:
- **ADCR data to DCO: −90 to +5 ps** (6 layers: −23 to −88; −177 to −28 until 12 Nov). ADCR_DCO's
  legs are swapped at the FPGA (the gateware inverts the clock), so the pair no longer goes round
  the AD9484 to reach its pins the right way round: 39 mm instead of 51, 89 % coupled, eye 2 mV
  under ideal. The rest is inside the IDELAYE2's 2.4 ns range, calibrated per bit at start-up.
- **Ten pairs are not coupled** (LINK_RX_D0/D1, LINK_TX_D0/CLK, the four ADCS pairs, ADCR_D2,
  ADCR_D4 partly). The LINK_RX pairs leave the FPGA's south rows and must cross every ADC pair on
  the way north; the AD9253's 0.5 mm pins leave no room for a coupled fan-out. They are 50 Ω legs
  matched to ±5 ps, within 1–26 mV of their ideal eye except LINK_RX_D0 (−52 mV). LINK_RX's bank 34
  sits in the BGA's south-east corner: there are no north-side balls for it, and its outer balls
  (tried 12 Nov) leave no room for the vias. Coupling it needs the AC capacitors at J101, now 9 mm
  apart, placed together first.
- **CLK_ADCR P−N: −3 ps** (−44 until 12 Nov): C414 and C415 side by side at 1 mm pitch, so both
  legs leave U401 together, and a meander on P on L3.
- Supersedes in §6: the pairs are now partly coupled, and every layer change has a ground via
  within 3 mm.

## 9. The rest of the board (12 November, evening)

Sections 2–8 cover what the review named: the RF band, the LVDS pairs and the FPGA's supplies.
This pass looks at every other net, with three checks run on the board file:
- **Current through each supply track.** Each track that every path from a rail's source to some
  of its loads must cross is given those loads' current (the budget of POWER_AND_STACKUP §1.3–1.4).
  The check reports its IPC-2221 temperature rise and the series drop.
- **Other nets' copper beside analogue nets**, on the same layer, within 0.3 mm. Broadside coupling
  to the next layer is not counted.
- **Each net's routed length against its shortest tree.** In all, 11.5 m of track for 9.4 m of
  minimum tree (×1.21), and 1,099 signal vias.

### 9.1 Supply tracks necked to 0.1 mm (fixed 12 Nov)

The router had necked supply tracks down to 0.1 mm wherever space was short. The `Power` netclass
did not stop it, for two reasons:
- **It sets the default width for new tracks, not a minimum.** The necks on the named rails were
  legal.
- **It does not cover the switch nodes or the input path.** `Net-(U100x-SW)`, `Net-(F1001-Pad1)`
  and `Net-(Q1001-D)` have no name to match: the same gap the review found on the SMA legs.

| Path | Current | Before | After |
|---|---|---|---|
| Input, J1001 → F1001 → Q1001 | 0.75 A | 0.1 mm, 8 mm (ΔT ≈ 32 °C) | 1.0 mm |
| +12V, Q1001 → U1001 | 0.75 A | 0.3 mm, a 1.6 mm piece on L3 | 0.4–1.0 mm |
| U1001's switch node → L1001 (+5V0) | 1.6 A | **0.1 mm, 8 mm (ΔT ≈ 180 °C)** | 0.4–1.0 mm; two 0.4 mm pieces at 0.2 mm by the pins |
| U1002's switch node (+3V3_D) | 1.13 A | 0.1 mm, 6 mm | 0.15–1.0 mm; the narrow 2 mm next to the pins |
| U1003 / U1004's switch nodes (+2V5, +1V0) | 0.6 / 0.7 A | 0.1 mm, 7–9 mm | 0.15–1.0 mm |
| **+1V8_A, U1005 → FB502/FB602**: 75 mm, mostly on L3 (15 µm copper) | 0.5 A | 0.1 mm for 11 mm, then 0.3 mm: 0.50 Ω, **251 mV drop**, ΔT ≈ 240 °C on the narrow part | 1.0 mm for 99 mm, narrower only between vias and pads: **66 + 8 mV** |

The ΔT figures are the IPC-2221 chart for a long track. A piece under a millimetre between wide
copper runs cooler. Every `Power` track was widened where its clearances allowed (1.0, 0.8, 0.6 …
0.15 mm, judged in 0.5 mm pieces):

| `Power`-class track | Before | After |
|---|---|---|
| ≤ 0.15 mm | 365 mm | 161 mm |
| ≥ 0.5 mm | 119 mm | 865 mm |
| Total | 1,554 mm | 1,554 mm |

L4, the supply plane layer, was left alone. DRC is 0 / 0 / 0 with schematic parity.

**+1V8_A, the ADCs' AVDD, now starts at 1.85 V.** Its LDO sits 75 mm from the ADCs.
- **The problem.** At the budget's 0.5 A the copper drops 74 mV and FB502's ferrite up to 30 mV
  (DCR ≤ 0.1 Ω, ADC_RADAR_SPEC). From 1.8 V that leaves 1.69 V at the AD9484, under its 1.7 V
  minimum. Before the widening it would have been about 1.5 V.
- **The fix.** U1005's 50 mV ANY-OUT pin is now grounded (POWER sheet, `power_spec.py`):
  0.8 + 0.05 + 0.2 + 0.8 = 1.85 V. The ADCs see about 1.74 V at full budget and 1.85 V unloaded,
  both inside 1.7–1.9 V even with the LDO's 1 % tolerance.
- **What else would work.** Moving U1005 next to the ADCs would remove the drop, at the cost of a
  re-placement.

### 9.2 Analogue nets beside digital ones (open)

`xtalk.py` (§3.5) compares LVDS legs only. Against the analogue nets, the longest same-layer
parallels within 0.3 mm are:

| Victim | Aggressor | Layer | Parallel, gap |
|---|---|---|---|
| SDR DAC reconstruction filter, DAC2 (C834) | `DACS_D0` | L3 | 12.5 mm at 0.11 mm |
| SDR DAC reconstruction filter, DAC1 (C814) | `+1V0` (a buck's output) | L1 | 13.5 mm at 0.20 mm |
| SDR DAC reconstruction filter, DAC1 (C814) | `DACS_D4` | L8 | 4.0 mm at 0.10 mm |
| SDR DAC reconstruction filter, DAC2 (C834) | `ADAR2_CS` | L3 | 4.1 mm at 0.10 mm |
| SDR ADC input network (C605) | `CONV_SPI_SDIO` | L3 | 4.4 mm at 0.10 mm |
| SDR ADC input network (C607) | `CLK_ADCS_P` | L1 | 4.0 mm at 0.15 mm |
| Radar IF, between the two AD8352s (C508) | the external reference clock `Net-(U401-CLK0)` | L3 | 5.0 mm at 0.28 mm |
| `IF_TX_B` | `FPGA_PROG_B` | L8 | 7.7 mm at 0.26 mm |

**Why it matters.** A data bit beside a filter node couples its edges straight into the SDR's
baseband. The DAC bus toggles at up to 125 MSPS, and the filter passes everything under 50 MHz.

**What was done (12 Nov).** Two scripted passes, each kept only at DRC 0/0/0:
- **The widened supply tracks were narrowed again where they ran beside analogue nodes.** That
  was 64 pieces, cut back to the width that keeps 0.3 mm, but never under 0.3 mm. The widening of
  §9.1 had brought them closer.
- **Seven tracks were moved 0.15–0.5 mm sideways, with a 45° jog at each end.** Four were
  aggressors (`ADAR2_CS`, `CONV_SPI_SDIO`, `+2V5`, `+1V8_D`) and three were analogue legs, moved
  away from `DACS_D0`, `CLK_ADCS_P` and `ADAR2_CS`.

| Same-layer run beside analogue nodes | Board of 11 Nov | After the widening | Now |
|---|---|---|---|
| Within 0.3 mm | 91 mm | 109 mm | **81 mm** |
| Within 0.2 mm | 43 mm | 59 mm | **33 mm** |

**What is left needs parts moved, not tracks.** Every case below is where the SDR DAC's filter is
threaded between the DAC bus and the `+1V0` feed on L1/L3:

| Victim | Aggressor | Run |
|---|---|---|
| C814 | `+1V0` | 13.5 mm at 0.20 mm |
| C834 | `DACS_D0` | 11 mm at 0.11 mm |
| `IF_TX_B` | `FPGA_PROG_B` | 7.7 mm at 0.26 mm |
| C814 | `DACS_D4` | 4 mm at 0.10 mm |
| C834 | `ADAR2_CS` | 3 mm at 0.10 mm |

The fix is the one in §9.3: re-place the filter.

### 9.3 Long differential analogue paths (open)

| Path | P / N | Vias |
|---|---|---|
| SDR DAC1 filter, between its two inductor sections (C814) | 57 / 66 mm | 8 / 6 |
| SDR DAC2 filter (C834) | 39 / 62 mm | 4 / 6 |
| SDR ADC driver → ADC (C605 / C606) | 45 / 32 mm | 4 / 4 |
| Reference oscillator → U401 (Y401 CLK±) | 10.5 / 20.8 mm | 3 / 2 |

- **The DAC filters.** At 0.4 nH/mm, 60 mm of 0.1 mm track is about 25 nH: a quarter of the
  filter's own 107 nH coils. The legs also differ by 23 mm, about 160 ps, which unbalances the
  balun's input.
- **Y401's outputs.** They differ by 10 mm, about 70 ps on the master reference.

These were routed as unrelated nets. The fix is to place the filter parts in two rows beside the
DAC and route each pair together.

**Simulated (12 Nov), and the copper costs little.** Each filter was run in ngspice twice: with
ideal connections, and with every node's copper as a line of its field-solved Z0 and delay. The
balun is taken as ideal.

| Filter | −3 dB, ideal / routed | At 100 MHz, ideal / routed | Common mode below differential, 10 / 50 MHz |
|---|---|---|---|
| AD9708 → T701 | 70 / 67 MHz | −24 / −26 dB | −57 / −36 dB |
| AD9767 DAC1 → T801 | 70 / 64 MHz | −24 / −29 dB | −59 / −35 dB |
| AD9767 DAC2 → T802 | 70 / 64 MHz | −24 / −29 dB | −47 / −31 dB |

- **The passband is unchanged.** It keeps the filter's own ripple of about 2 dB at 30 MHz.
- **The corner moves 4–9 % lower**, and the stop band rolls off slightly faster.
- **The legs' imbalance** leaves a common mode at least 30 dB under the signal inside the passband.

![DAC reconstruction filters, ideal and as routed](sim/rev05_filters.png)

The DAC buses are not matched either:
- `DACS` data bits run 37–84 mm, with `IQSEL` at 104 mm;
- `DACR` runs 34–51 mm.

Those 48 mm are about 0.3 ns on an 8 ns period: inside the FPGA's output timing, set by
constraints.

### 9.4 Pairs not coupled: 13 of 22, counting the clocks

§8 counts 19 data and link pairs, of which 10 are not coupled. Counting U401's three clock pairs
as well, 13 of 22 are not coupled:

| Pair | Coupled | Copper P / N | Vias P / N |
|---|---|---|---|
| `CLK_ADCS` | 0 % | 63 / 67 mm | 5 / 6 |
| `CLK_FPGA` | 0 % | 85 / 71 mm | 2 / 5 |
| `CLK_ADCR` | 36 % | 24 / 28 mm | 2 / 3 |
| ADCS ×4, ADCR_D2, ADCR_D4 | 0–41 % | 27–43 mm | 2–5 |
| LINK_RX_D0/D1, LINK_TX_D0/CLK | 0–2 % | 71–119 mm | 4–9 |

**The order to re-route them in:**
1. **The sampling clocks.** Common-mode noise on them becomes jitter.
2. **The ADCS pairs.** The AD9253's P and N pins are adjacent, so the pair can leave the chip
   together.
3. **LINK.** It needs its AC capacitors at J101 placed together first. It gains least: its eyes
   are already within 1–52 mV of ideal.

The tool is the one that re-routed ADCR_DCO (from 0 to 89 % coupled), driving KiCad's own
push-and-shove router. What coupling buys is common-mode rejection and less crosstalk, not
millivolts of eye.

**Tried on 12 Nov, on `CLK_ADCS`, and stopped before changing the board:**
- **The middle has room.** The legs run 63 and 67 mm, P on L1 and N on L8. An A\* search finds a
  pair corridor on L6 (In5) of 36.5 mm from C416/C417 to above the AD9253, and there is room for
  the pair's vias at (188.0, 165.95) and (189.5, 165.8).
- **The ends do not.**
  - KiCad's router will not start from C416/C417's vias, which sit in the pads.
  - At the AD9253 the clock pins are boxed in by C670 and two supply vias. The router went round
    them for that reason, and a straight descent shorts four nets.

  Coupling it needs C670 moved first.

`CLK_FPGA` is the same case: its series resistors R1115/R1116 sit 12 mm apart, and its bias
resistors R1117/R1118 sit apart too. Both need re-placing before the pair can couple.

### 9.5 Supply balls without their own via

Unchanged: 11 of 69 (§6). Both ways were tried on every ball, and four of them are on rails with
no plane to reach. The impedance is inside the target with margin (+1V0: 41 / 63 mΩ against
120). A further gain needs the BGA's escape redone by hand.

### 9.6 Thermal, RF budget, and what is still not simulated

**Thermal (12 Nov).**
- **The model.** `thermal2d.py` treats the board as a 2-D sheet. In-plane conduction runs through
  each layer's real copper coverage: L2, L5 and L7 85 %, L4 82 %, the outer layers 16–24 %, the
  signal layers 5–7 %. Both faces cool by natural convection.
- **The heat.** 6.9 W, from the power budget (POWER_AND_STACKUP §1.3–1.4), spread over each part's
  pads.
- **The junctions.** Each is the board temperature under the part plus P × θJB, or θJC for the
  exposed-pad parts, from the data sheets read.

| At 25 °C ambient, still air | h = 10 W/m²K per face (convection only) | h = 15 (with radiation) |
|---|---|---|
| Board, mean / hottest rise | +26 / +48 °C | +17 / +38 °C |
| Under the ADCLK948 (0.95 W) | 73 °C | 63 °C |
| AD9484, junction (θJC 1.7 °C/W) | 68 °C | 58 °C |
| LMR33630, junction (θJB 13.6) | 79 °C | 70 °C |
| TPS7A8300 for +1V8_D, junction (θJB 12.3) | 71 °C | 62 °C |
| XC7A50T, under the package | 56 °C | 47 °C |

**On the bench this is comfortable. In a vehicle it is not.**
- **The cause.** The board is small (134 cm²) for 6.9 W. The clock buffer, the radar ADC, the
  four drivers and the 5 V buck share it.
- **The arithmetic.** At 60–70 °C ambient, add 35–45 °C to every figure above. Around the clock
  buffer and the ADCs the board then passes 110 °C.
- **What it exceeds.** The ADCs' 85 °C ambient rating, and the FPGA's 100 °C junction limit
  (I grade) where its own rise is added.
- **What a vehicle install needs.** The KV260's fan blowing across this board, or a thermal path
  to the enclosure, as VEHICLE_PLATFORM plans.
- **Still to compute** with the AMD and ADI θ figures, which could not be fetched here: the FPGA,
  the AD9253, the ADCLK948 and the AD9767.
- **Not modelled.** Heat flowing into the KV260 through the connector and the standoffs, and any
  airflow.

![Board temperature](sim/rev05_thermal.png)

**RF budget (12 Nov), `cascade.py`.** Noise is followed as voltage density node by node:
- the source and its 64.9 Ω termination;
- each AD8352's 2.7 nV/√Hz referred to its input (Rev. C Table 2);
- the ADC's own noise, from its SNR over its Nyquist band.

| Radar receive, IF_RX_B → SW2 → AD8352 15 dB → AD8352 10 dB → AD9484 | |
|---|---|
| Full scale at the SMA | **−17.6 dBm** (ADC_RADAR_SPEC estimated −17) |
| Noise figure, front end only (switch and drivers) | 15.5 dB |
| Noise figure including the ADC | **26.8 dB**: the 8-bit AD9484 is 92 % of the noise |
| Noise floor at the SMA | −147 dBm/Hz; 47 dB SNR over 200 MHz, plus 12 dB of processing gain after the ÷16 DDC |
| Input IP3 | +15 dBm, 33 dB above full scale |

- **The ADC sets the floor.** Its SFDR of 79 dBc, not the drivers' OIP3 of +40 dBm, sets the
  linearity.
- **More gain here would only move full scale down.** The receiver's sensitivity is decided ahead
  of this board, in AERIS-10's own IF chain.
- **The SDR receive chains (AD9253) are still to fill.** Its data sheet could not be fetched here:
  analog.com does not answer this machine, and the Internet Archive was rate-limiting.

| Transmit, full-scale tone at the SMA | |
|---|---|
| AD9708, 20 mA, → T701 → SW4 → `IF_TX_B` | **0 dBm** |
| AD9767 DAC1, 10 mA, → T801 → SW3 → `IF_TX_A` | **−6.1 dBm** |
| AD9767 DAC2, 10 mA, → T802 → `IF_TX_C` | **−5.5 dBm** |

These levels take the 49.9 Ω loads in parallel with the balun's 100 Ω, the balun's 0.4 dB and the
switch's 0.6 dB (ADT2-1T+, M3SWA2-34DR+). The filter's passband ripple, 0 to −2 dB, comes on top.

**What is still not simulated:**

1. **3-D full-wave.** The whole board is out of reach of FDTD: 0.1 mm features over 100 mm. Four
   sub-models in openEMS give the parts that matter, and their S-parameters go into the eye
   simulation in place of the lumped sections:
   - the BGA escape and its via;
   - a layer change with its return via;
   - the Hirose footprint;
   - two parallel pairs, for real rather than 2-D crosstalk.

   A cheaper first step is to add conductor and dielectric loss to `lvds_eye.py`'s lines.
2. **The RF chains in cascade.** Per channel:
   - gain, noise figure (Friis), IP3 and the ADC's full scale, giving the dynamic range from the
     data-sheet figures;
   - the anti-alias and reconstruction filters in ngspice, with this copper (§9.3) and the parts'
     tolerances;
   - the baluns from their manufacturers' S-parameters.
3. **Thermal.**
   - First, a table: each part's dissipation and junction rise from its package's θJA.
   - Then a 2-D conduction map of the board: the real copper per layer and natural convection, for
     the regulator corner and the ADCs.

## 10. How it was checked

The checks were scripts run on the board file, none by hand: a KiCad-style plane fill, the
connectivity graph of each net, the field solver, ngspice and openEMS (built from source in WSL).
The DRC after every change: **0 errors, 0 unconnected, 0 schematic-parity problems** (on 12 Nov,
for the 8-layer board, 0 violations of any kind).
