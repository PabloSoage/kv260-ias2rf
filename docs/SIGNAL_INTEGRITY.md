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
- **ADCR data to DCO: −28 to −177 ps** (6 layers: −23 to −88). ADCR_DCO leaves the AD9484 on its
  north side and is 51 mm long, the data pairs 27–44 mm. At 400 MSPS that is 7 % of the 2.5 ns
  bit, inside the IDELAYE2's 2.4 ns range, calibrated per bit at start-up as before.
- **Ten pairs are not coupled** (LINK_RX_D0/D1, LINK_TX_D0/CLK, the four ADCS pairs, ADCR_D2,
  ADCR_D4 partly). The LINK_RX pairs leave the FPGA's south rows and must cross every ADC pair on
  the way north; the AD9253's 0.5 mm pins leave no room for a coupled fan-out. They are 50 Ω legs
  matched to ±5 ps, within 1–26 mV of their ideal eye except LINK_RX_D0 (−52 mV). Moving LINK_RX to
  north-side balls (a pin swap in CONTROL) would let them couple.
- Supersedes in §6: the pairs are now partly coupled, and every layer change has a ground via
  within 3 mm.

## 9. How it was checked

The checks were scripts run on the board file, none by hand: a KiCad-style plane fill, the
connectivity graph of each net, the field solver, ngspice and openEMS (built from source in WSL).
The DRC after every change: **0 errors, 0 unconnected, 0 schematic-parity problems** (on 12 Nov,
for the 8-layer board, 0 violations of any kind).
