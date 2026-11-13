#!/usr/bin/env python3
"""
RJ45_Hanrun_HR911130C: the gigabit RJ45 with integrated magnetics and two LEDs (LCSC C50933),
from the HanRun drawing HR911130C Rev. B, "Recommended PCB layout (Component Side View)", page 3.
KiCad ships no footprint for it. Written to footprints/kv260-ias2rf.pretty (13 Nov 2026).

Frame: origin midway between the two 3.25 mm plastic posts; the plug opening (front face) is at
y = -10.80, the rear at +10.40; +x to the right in the component-side view.
  pins 1-10   drill 0.89, 1.27 mm apart alternating rows: pin n at x = (5.5 - n) * 1.27,
              odd pins at y = 8.89, even pins at y = 6.35 (pad 1.40, pin 1 square)
  LED pins    drill 1.02 at y = -4.90: 14 at x -6.625, 13 at -4.085, 12 at +4.085, 11 at +6.625
  shield      drill 1.63 at (+-7.745, 3.05), pads "SH"
  posts       3.25 mm non-plated holes at (+-5.715, 0)
Body 16.00 wide; the shield's spring tabs make the front 18.35 wide.

Usage:  py _work/make_rj45.py
"""
import os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "footprints", "kv260-ias2rf.pretty", "RJ45_Hanrun_HR911130C.kicad_mod")
import uuid
NS = uuid.UUID("5b1c2d6e-7f80-4a91-b2c3-d4e5f6a7b8c9")
U = lambda *p: str(uuid.uuid5(NS, "rj45|" + "|".join(map(str, p))))
T = "\t"


def pad(num, x, y, drill, size, shape="circle"):
    return (f'{T}(pad "{num}" thru_hole {shape}\n{T}{T}(at {x:g} {y:g})\n{T}{T}(size {size:g} {size:g})\n'
            f'{T}{T}(drill {drill:g})\n{T}{T}(layers "*.Cu" "*.Mask")\n{T}{T}(remove_unused_layers no)\n'
            f'{T}{T}(uuid "{U("pad", num, x, y)}")\n{T})')


def npth(x, y, d):
    return (f'{T}(pad "" np_thru_hole circle\n{T}{T}(at {x:g} {y:g})\n{T}{T}(size {d:g} {d:g})\n'
            f'{T}{T}(drill {d:g})\n{T}{T}(layers "*.Cu" "*.Mask")\n{T}{T}(uuid "{U("np", x, y)}")\n{T})')


def line(x1, y1, x2, y2, layer, w):
    return (f'{T}(fp_line\n{T}{T}(start {x1:g} {y1:g})\n{T}{T}(end {x2:g} {y2:g})\n{T}{T}(stroke\n{T}{T}{T}(width {w:g})\n'
            f'{T}{T}{T}(type solid)\n{T}{T})\n{T}{T}(layer "{layer}")\n{T}{T}(uuid "{U("ln", x1, y1, x2, y2, layer)}")\n{T})')


def poly(pts, layer, w):
    p = " ".join(f"(xy {x:g} {y:g})" for x, y in pts)
    return (f'{T}(fp_poly\n{T}{T}(pts\n{T}{T}{T}{p}\n{T}{T})\n{T}{T}(stroke\n{T}{T}{T}(width {w:g})\n{T}{T}{T}(type solid)\n'
            f'{T}{T})\n{T}{T}(fill no)\n{T}{T}(layer "{layer}")\n{T}{T}(uuid "{U("poly", layer)}")\n{T})')


def prop(name, val, x, y, layer, hide=False):
    h = f"\n{T}{T}(hide yes)" if hide else ""
    return (f'{T}(property "{name}" "{val}"\n{T}{T}(at {x:g} {y:g} 0)\n{T}{T}(layer "{layer}"){h}\n'
            f'{T}{T}(uuid "{U("prop", name)}")\n{T}{T}(effects\n{T}{T}{T}(font\n{T}{T}{T}{T}(size 1 1)\n'
            f'{T}{T}{T}{T}(thickness 0.15)\n{T}{T}{T})\n{T}{T})\n{T})')


F, R, W, WT = -10.80, 10.40, 8.0, 9.175
items = [prop("Reference", "REF**", 0, 12.0, "F.SilkS"), prop("Value", "HR911130C", 0, -2.0, "F.Fab"),
         prop("Datasheet", "", 0, 0, "F.Fab", True),
         prop("Description", "", 0, 0, "F.Fab", True),
         f"{T}(attr through_hole)", f"{T}(duplicate_pad_numbers_are_jumpers no)"]
# body on Fab; silk on the three sides that stay on the board (the front overhangs the edge)
items.append(poly([(-W, F), (W, F), (W, R), (-W, R)], "F.Fab", 0.1))
for seg in ((-W - 0.12, -6.2, -W - 0.12, 1.5), (-W - 0.12, 4.6, -W - 0.12, R + 0.12), (-W - 0.12, R + 0.12, W + 0.12, R + 0.12), (W + 0.12, R + 0.12, W + 0.12, 4.6), (W + 0.12, 1.5, W + 0.12, -6.2)):
    items.append(line(*seg, "F.SilkS", 0.12))
cy = [(-WT - 0.25, F - 0.25), (WT + 0.25, F - 0.25), (WT + 0.25, -8.3), (W + 0.25, -8.3), (W + 0.25, R + 0.25),
      (-W - 0.25, R + 0.25), (-W - 0.25, -8.3), (-WT - 0.25, -8.3)]
items.append(poly(cy, "F.CrtYd", 0.05))
for n in range(1, 11):
    items.append(pad(n, (5.5 - n) * 1.27, 8.89 if n % 2 else 6.35, 0.89, 1.4, "rect" if n == 1 else "circle"))
for n, x in ((14, -6.625), (13, -4.085), (12, 4.085), (11, 6.625)):
    items.append(pad(n, x, -4.90, 1.02, 1.6))
for x in (-7.745, 7.745):
    items.append(pad("SH", x, 3.05, 1.63, 2.4))
for x in (-5.715, 5.715):
    items.append(npth(x, 0, 3.25))
items.append(f'{T}(embedded_fonts no)')
txt = ('(footprint "RJ45_Hanrun_HR911130C"\n\t(version 20260206)\n\t(generator "pcbnew")\n\t(generator_version "10.0")\n'
       '\t(layer "F.Cu")\n\t(descr "HanRun HR911130C gigabit RJ45, integrated magnetics, 2 LEDs, right angle, '
       'from the HanRun drawing Rev. B p.3 (_work/make_rj45.py)")\n\t(tags "RJ45 magjack 1000Base-T")\n'
       + "\n".join(items) + "\n)\n")
open(OUT, "w", encoding="utf-8", newline="\n").write(txt)
print("wrote", OUT)
