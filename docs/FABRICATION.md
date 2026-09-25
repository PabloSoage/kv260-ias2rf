# Fabrication — ordering the board from JLCPCB

*26 September 2026 · outputs by `_work/fab/make_fab.py` · stack JLC06161H-2116A*

One command writes everything JLCPCB asks for into `fab/`. That folder is git-ignored: the files are
always regenerated, never edited.

```
py _work/fab/make_fab.py
```

**Today the output is a DRAFT.** The board is placed, not routed: DRC reports 0 errors and 499
unrouted connections. So the script names the folder `DRAFT-…` and writes *DO NOT ORDER* in the
notes. The draft is there to check the files, not to order from.

---

## 1. What the script does

| Step | How | Why |
|---|---|---|
| **Check the board** | `kicad-cli pcb drc --refill-zones --schematic-parity` on a copy in `fab/_work/` | Any error or unrouted connection makes the output a DRAFT. The zones are filled on the copy only; the board in git stays unfilled |
| **Gerbers** | L1–L6, paste, silkscreen, mask, outline. Protel extensions, soldermask subtracted from silkscreen, zones checked | JLCPCB's KiCad guide, point by point |
| **Drill** | Excellon, mm, decimal, absolute origin, alternate mode for oval holes, plus a PDF drill map | Same guide |
| **Zip** | Gerbers + drill in one zip, spaces in the layer names replaced by `_` | The zip is what is uploaded |
| **BOM** | `Comment, Designator, Footprint, LCSC Part #, Quantity`, one line per value and footprint: 108 lines, 472 parts | JLCPCB's BOM columns |
| **CPL** | `Designator, Mid X, Mid Y, Layer, Rotation`, from KiCad's position file: 472 placements (fiducials and holes left out) | JLCPCB's CPL columns |
| **ORDER.txt** | The order form's values, and the DRC result | So the order is entered the same way every time |

---

## 2. The order form

| Field | Value | Why |
|---|---|---|
| Layers | 6 | |
| Thickness | 1.6 mm | |
| **Impedance control** | **Yes, JLC06161H-2116A** | The stack the widths were solved for (POWER_AND_STACKUP §2.6). Any other stack changes every impedance |
| Copper | 1 oz outer, 0.5 oz inner | The stack's own |
| Via covering | Tented | The BGA's fan-out vias sit between pads, not in them |
| Min via | 0.20 mm hole, 0.45 mm pad | Within JLCPCB's six-layer capability |
| Min track / space | 0.10 / 0.10 mm | The LVDS pairs are 0.117 / 0.150 mm |
| **Surface finish** | **ENIG** | Flat pads for the 1.0 mm BGA and the LFCSPs; HASL is not flat enough |

---

## 3. What is left for the day of the order

**Route the board.** Then run the script again: the folder loses its `DRAFT-` prefix only when DRC
reports zero errors and zero unrouted connections.

**Fill in the LCSC column of the BOM.** The symbols carry no LCSC or manufacturer part number: chips
carry their part number as the value (LMR33630ADDA, XC7A50T-2FTG256I…), passives carry only a value.
In JLCPCB's BOM step:
- match each line to a part;
- for passives, choose the voltage and dielectric:
  - X7R or X5R, never Y5V;
  - 0402 decoupling at 10 V or more;
  - the 22 µF output capacitors at 10 V;
  - the input capacitors at 25 V, as their values say;
- check the parts JLCPCB does not stock. The XC7A50T, the AD converters, the ADCLK948, the Si549
  and the M3SWA2 switches are likely to be consigned or "global sourcing".

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
| Script run on the placed board | 15 files in the zip (6 copper layers, 2 mask, 2 paste, 2 silkscreen, outline, drill, job file), BOM 108 lines / 472 parts, CPL 472 placements, DRC 0 errors |
| CPL against BOM | The same 472 references in both |
| Settings against JLCPCB's KiCad guide | Protel extensions, subtract soldermask, zone check; Excellon mm, decimal, absolute, alternate oval mode — all as the guide lists |
