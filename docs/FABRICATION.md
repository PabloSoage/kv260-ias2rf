# Fabrication — ordering the board from JLCPCB

*26 September 2026 · outputs by `_work/fab/make_fab.py` · stack JLC06161H-2116A*

One command writes everything JLCPCB asks for into `fab/`. That folder is git-ignored: the files are
always regenerated, never edited.

```
py _work/fab/make_fab.py
```

**Today the output is a DRAFT.** The board is autorouted but not finished (LAYOUT §6): DRC reports
89 unrouted connections, 1 RF clearance error and 2 hole-to-hole via pairs. So the script names
the folder `DRAFT-…` and writes *DO NOT ORDER* in the notes. The draft is there to check the files,
not to order from.

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
| Layers | 6 | |
| Thickness | 1.6 mm | |
| **Impedance control** | **Yes, JLC06161H-2116A** | The stack the widths were solved for (POWER_AND_STACKUP §2.6). Any other stack changes every impedance |
| Copper | 1 oz outer, 0.5 oz inner | The stack's own |
| **Via covering** | **Epoxy filled & capped (POFV)** | The autorouter put about 400 vias in pads (0402 passives, chip pads). JLCPCB fills and caps them free, and by default, on 6–20-layer boards. The BGA's own fan-out vias sit between its balls |
| Min via | 0.20 mm hole, 0.45 mm pad | Within JLCPCB's six-layer capability |
| Min track / space | 0.10 / 0.10 mm | The LVDS pairs are 0.117 / 0.150 mm |
| **Surface finish** | **ENIG** | Flat pads for the 1.0 mm BGA and the LFCSPs; HASL is not flat enough |

---

## 3. What is left for the day of the order

**Route the board.** Then run the script again: the folder loses its `DRAFT-` prefix only when DRC
reports zero errors and zero unrouted connections.

**Check the LCSC codes, and refresh them.** The symbols carry no part numbers, so the codes live in
`_work/fab/lcsc_parts.csv`, one per BOM line, and `make_fab.py` copies them into the BOM. They were
chosen on 2 October 2026 by `_work/fab/lcsc_select.py` from JLCPCB's own parts search, by rule:
- the value, the package and, for a chip, the exact model must match;
- capacitors: C0G below 1 nF, X7R or X5R above, never Y5V; the voltage rating at least what the
  line's highest rail needs (16 V on the 0402 decoupling that touches 5 V, 25 V on the 12 V input);
- resistors 1 %;
- among the parts that qualify: JLCPCB "basic" first (no loading fee), then stock.

Stock changes daily: run `py _work/fab/lcsc_select.py` again before ordering and read the diff of the
CSV. **109 of 110 lines have a code.** Three are not the drawn value, because that value is not made
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

**Confirm the impedances in JLCPCB's own calculator:** 117 / 150 µm differential and 183 µm single
on L1, with stack 2116A selected. The field solver gives 100.2 Ω and 49.8 Ω. JLCPCB's calculator
should agree within a few ohms; if it does not, its widths win (POWER_AND_STACKUP §2.6).

---

## 4. How it was checked

| Check | Result |
|---|---|
| Script run on the placed board | 15 files in the zip (6 copper layers, 2 mask, 2 paste, 2 silkscreen, outline, drill, job file), BOM 110 lines / 478 parts, CPL 478 placements, DRC 0 errors (2 October) |
| CPL against BOM | The same 478 references in both |
| Settings against JLCPCB's KiCad guide | Protel extensions, subtract soldermask, zone check; Excellon mm, decimal, absolute, alternate oval mode — all as the guide lists |
