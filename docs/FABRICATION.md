# Fabrication — ordering the board from JLCPCB

*26 September 2026 · outputs by `_work/fab/make_fab.py` · stack JLC08161H-2116C since 12 November 2026*

> **8 layers since 12 Nov 2026.** Order **8 layers, stack JLC08161H-2116C**, as `fab/<date>/ORDER.txt`
> says; the widths for that stack are in LAYOUT §3 and `_work/field_solver8.py`. The 6-layer 2116A
> figures further down are the record of the earlier board.

One command writes everything JLCPCB asks for into `fab/`. That folder is git-ignored: the files are
always regenerated, never edited.

```
py _work/fab/make_fab.py
```

**Since 10 Nov the output is not a draft:** DRC reports no errors and no unrouted connections, so
the script names the folder without `DRAFT-`. The LVDS review of LAYOUT §6.2–6.3 and the
calculator check above were closed on 10 Nov; the RF/high-speed review of 11 Nov
([SIGNAL_INTEGRITY.md](SIGNAL_INTEGRITY.md)) was checked the same way. The script copies the
project's custom rules (`CSI2-KRIA-KV260_Rev01.kicad_dru`) with the board: without them the RF
lines' 0.15 mm necks at 0.5 mm-pitch pins read as clearance errors.

---

## 1. What the script does

| Step | How | Why |
|---|---|---|
| **Check the board** | `kicad-cli pcb drc --refill-zones --schematic-parity` on a copy in `fab/_work/` | Any error or unrouted connection makes the output a DRAFT. The zones are filled on the copy only; the board in git stays unfilled |
| **Gerbers** | L1–L6, paste, silkscreen, mask, outline. Protel extensions, soldermask subtracted from silkscreen, zones checked | JLCPCB's KiCad guide, point by point |
| **Drill** | Excellon, mm, decimal, absolute origin, alternate mode for oval holes, plus a PDF drill map | Same guide |
| **Zip** | Gerbers + drill in one zip, spaces in the layer names replaced by `_` | The zip is what is uploaded |
| **BOM** | `Comment, Designator, Footprint, LCSC Part #, Quantity`, one line per value and footprint: 110 lines, 478 parts | JLCPCB's BOM columns |
| **CPL** | `Designator, Mid X, Mid Y, Layer, Rotation`, from KiCad's position file: 478 placements (fiducials, holes and the solder jumper JP1101 left out: they are copper only) | JLCPCB's CPL columns |
| **ORDER.txt** | The order form's values, and the DRC result | So the order is entered the same way every time |

---

## 2. The order form

| Field | Value | Why |
|---|---|---|
| Layers | **8** (6 until 12 Nov) | |
| Thickness | 1.6 mm | |
| **Impedance control** | **Yes, JLC08161H-2116C** (8 layers; JLC06161H-2116A until 12 Nov) | The stack the widths were solved for (`_work/field_solver8.py`). Any other stack changes every impedance |
| Copper | 1 oz outer, 0.5 oz inner | The stack's own |
| **Via covering** | **Epoxy filled & capped (POFV)** | 543 vias sit in pads since 11 Nov (0402 passives, butted decoupling vias, every IC's exposed pad, five in L1030's output pad). JLCPCB fills and caps them free, and by default, on 6–20-layer boards. Most of the BGA's fan-out vias sit between its balls; 29 sit in ball pads (LAYOUT §6.1) |
| Min via | 0.20 mm hole, 0.45 mm pad | Within JLCPCB's 8-layer capability |
| Min track / space | **0.09** / 0.10 mm | Inner LVDS pairs 0.10 / 0.15 mm, 0.09 / 0.12 mm under the FPGA (110 segments at 0.09 mm); L1 pairs 0.117 / 0.150 mm |
| **Surface finish** | **ENIG** | Flat pads for the 1.0 mm BGA and the LFCSPs; HASL is not flat enough |

---

## 3. What is left for the day of the order

**The board is routed** (0 errors, 0 unrouted since 10 Nov). Run the script again after any change:
the folder loses its `DRAFT-` prefix only when DRC reports zero errors and zero unrouted connections.

**Check the LCSC codes, and refresh them.** The symbols carry no part numbers, so the codes live in
`_work/fab/lcsc_parts.csv`, one per BOM line, and `make_fab.py` copies them into the BOM. They were
chosen on 2 October 2026 by `_work/fab/lcsc_select.py` from JLCPCB's own parts search, by rule:
- the value, the package and, for a chip, the exact model must match;
- capacitors: C0G below 1 nF, X7R or X5R above, never Y5V; the voltage rating at least what the
  line's highest rail needs (16 V on the 0402 decoupling that touches 5 V, 25 V on the 12 V input);
- resistors 1 %;
- among the parts that qualify: JLCPCB "basic" first (no loading fee), then stock.

Stock changes daily: run `py _work/fab/lcsc_select.py` again before ordering and read the diff of the
CSV, then `python _work/fab/quote.py` for today's prices ([JLCPCB_QUOTE.md](JLCPCB_QUOTE.md)). On 10 Nov
two lines were re-selected because their part ran out: the 22.6 kΩ (now C100316) and the PROG switch
(now TL3342F450QG). **109 of 110 lines have a code.** Three are not the drawn value, because that value is not made
(the CSV's Note column says so):

| Line | Drawn | Fitted | Effect |
|---|---|---|---|
| C710, C814, C834 | 106 pF (AERIS C141) | 110 pF C0G | +3.8 % on one element of the DAC reconstruction filter. Or 100 pF plus 5.6 pF by hand |
| L701–L704, L811–L834 | 107.3 nH (AERIS L22) | 110 nH ±2 %, Murata LQW18 | +2.5 %, same filter |
| C1110 | T520V337M2R5ATE025 (UG483) | T520V337M006ATE025 | Same series and case, 6.3 V instead of 2.5 V |

**Not stocked, or not catalogue parts:** the Si549 (Y401) has no code, because Skyworks builds its
ordering code per configuration: order it from Skyworks or a distributor and consign it. Several codes
exist but showed **zero stock** on 2 October: ADCLK948, AD9484, AD9708, M3SWA2-34DR+. Others are
very short (XC7A50T 73, AD8352 9, AD9253 2, ADT2-1T+ 7). JLCPCB's "global sourcing" or consignment
covers them.

**Check every rotation in JLCPCB's placement preview.** KiCad's zero orientation and JLCPCB's
differ for some packages (SOT-23, some QFNs and SOICs). The CPL is KiCad's; correct the rotation
there if a part shows turned.

**Confirm the impedances in JLCPCB's own calculator** (`jlcpcb.com/pcb-impedance-calculator`):
8 layers, 1.6 mm, outer copper 1 oz, inner 0.5 oz, stack **JLC08161H-2116C** (L1 · L2 GND · L3 · L4 PWR ·
L5 GND · L6 · L7 GND · L8). The field solver (`_work/field_solver8.py`, SIGNAL_INTEGRITY §8) gives:

| Row | Type | Layer | References | Width / spacing | Field solver | Used on the board by |
|---|---|---|---|---|---|---|
| 1 | Single-ended | L1 / L8 | L2 / L7 | 183 µm | 50.4 Ω | `IF_RX_*`, `IF_TX_*` (RF50), the SMA launches |
| 2 | Single-ended | L3 / L6 | L2+L4 / L5+L7 | 151 µm | 50 Ω | Single 50 Ω inner lines |
| 3 | Differential | L3 / L6 | as row 2 | 100 / 150 µm | 100.2 Ω | The coupled LVDS pairs |
| 4 | Differential | L3 / L6 | as row 2 | 90 / 120 µm | 98.5 Ω | The same pairs under the FPGA |
| 5 | Differential | L1 | L2 | 117 / 150 µm | 100.4 Ω | The L1 pairs |

The 6-layer check of 10 November (stack JLC06161H-2116A, every width within 1–6 % of JLCPCB's
calculator) is superseded; **enter these five rows in the calculator for the 8-layer stack before
paying**, and order stack 2116C explicitly: a cheaper stack with thinner outer prepreg would move the
RF lines off 50 Ω.

---

## 4. How it was checked

| Check | Result |
|---|---|
| Script run on the placed board | 15 files in the zip (6 copper layers, 2 mask, 2 paste, 2 silkscreen, outline, drill, job file), BOM 110 lines / 478 parts, CPL 478 placements, DRC 0 errors (2 October) |
| CPL against BOM | The same 478 references in both |
| Settings against JLCPCB's KiCad guide | Protel extensions, subtract soldermask, zone check; Excellon mm, decimal, absolute, alternate oval mode — all as the guide lists |
