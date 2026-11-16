#!/usr/bin/env python3
"""
Rev08 footprints into footprints/kv260-ias2rf.pretty (16 Nov 2026).

* The LCSC parts' land patterns used by the placement trial (REV08_PLAN section 11.4): EasyEDA footprints
  exported with easyeda2kicad and upgraded with `kicad-cli fp upgrade`, kept in _work/footprints_rev08/
  (the source of this script). Copied as they are, except:
    - the BM20B(0.8)-34DS receptacle (J103): its four metal fittings, pads 35-38, are renamed "MP" so that
      they meet the symbol's mounting pin (Conn_02x17_Odd_Even_MountingPin);
    - the 3-D model references are dropped (the board renders take their models from _work/mech).
* USB_C_HX_16P_180_LT_H10: the vertical USB-C (HX-TYPE-C 16P 180 LT H10.0, LCSC C49261569), drawn from the
  maker's "RECOMMENDED P.C.B. LAYOUT" [V, drawing read 16 Nov 2026]: two rows of eight pads, 0.50 x 1.14 mm
  at 1.00 mm pitch over 7.00 mm, rows 2.96 mm apart (B01 B04 ... B12 on one row, A12 A09 ... A01 on the
  other), two non-plated holes of 0.90 mm for the 0.70 mm locating pegs, 8.45 mm apart. No soldered shell
  tabs. The pegs' length against the board (1.54 mm) and the 0.8 mm gap to the carrier is checked in phase 5.
  The placement trial's provisional pattern (0.5 mm pitch, four shell tabs) was wrong and is not used.

Usage:  py _work/rev08_footprints.py
"""
import os
import re
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "_work", "footprints_rev08")
DST = os.path.join(ROOT, "footprints", "kv260-ias2rf.pretty")
COPY = ["CONN-SMD_34P-P0.40_BM20B-0.8-34DS-0.4V-51", "FILTER-SMD_1206-4P-L3.2-W1.6-L",
        "FILTER-SMD_6P-L3.8-W3.8-P1.27-TL-3", "MSOP-10_L3.0-W3.0-P0.50-LS5.0-BL", "OSC-SMD_4P-L2.0-W1.6-BL",
        "QFN-14_L2.0-W2.0-P0.45-BL-EP", "QFN-20_L4.0-W4.0-P0.50-BL-EP2.2", "QFN-24_L4.0-W4.0-P0.50-BL-EP2.8",
        "SC-70-6_L2.2-W1.3-P0.65-LS2.1-BL", "SOT-23-5_L3.0-W1.7-P0.95-LS2.8-BL", "SOT-23-6_L2.9-W1.6-P0.95-LS2.8-BL",
        "SOT343_L2.0-W1.3-P1.30-LS2.1-BL", "WQFN-24_L4.0-W4.0-P0.50-TL-EP2.5", "XFMR-SMD_TC1-1TX"]
U = lambda: str(uuid.uuid4())
T = "\t"


def block_at(t, i):
    depth, j, q = 0, i, False
    while True:
        c = t[j]
        if q:
            if c == "\\":
                j += 1
            elif c == '"':
                q = False
        elif c == '"':
            q = True
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return j + 1
        j += 1


def copy(name):
    t = open(os.path.join(SRC, name + ".kicad_mod"), encoding="utf-8").read()
    while True:
        i = t.find("\n\t(model ")
        if i < 0:
            break
        t = t[:i] + t[block_at(t, i + 1):]
    if name.startswith("CONN-SMD_34P"):
        t = re.sub(r'\(pad "3[5-8]"', '(pad "MP"', t)
    open(os.path.join(DST, name + ".kicad_mod"), "w", encoding="utf-8", newline="\n").write(t)


def pad(name, x, y, w, h):
    return (f'{T}(pad "{name}" smd roundrect\n{T*2}(at {x:g} {y:g})\n{T*2}(size {w:g} {h:g})\n'
            f'{T*2}(layers "F.Cu" "F.Mask" "F.Paste")\n{T*2}(roundrect_rratio 0.25)\n{T*2}(uuid "{U()}")\n{T})\n')


def npth(x, y, d):
    return (f'{T}(pad "" np_thru_hole circle\n{T*2}(at {x:g} {y:g})\n{T*2}(size {d:g} {d:g})\n{T*2}(drill {d:g})\n'
            f'{T*2}(layers "*.Cu" "*.Mask")\n{T*2}(uuid "{U()}")\n{T})\n')


def rect(layer, x0, y0, x1, y1, width):
    return (f'{T}(fp_rect\n{T*2}(start {x0:g} {y0:g})\n{T*2}(end {x1:g} {y1:g})\n'
            f'{T*2}(stroke\n{T*3}(width {width:g})\n{T*3}(type solid)\n{T*2})\n{T*2}(fill no)\n'
            f'{T*2}(layer "{layer}")\n{T*2}(uuid "{U()}")\n{T})\n')


def text_prop(name, val, y, layer, hide=False):
    h = f"\n{T*2}(hide yes)" if hide else ""
    return (f'{T}(property "{name}" "{val}"\n{T*2}(at 0 {y:g} 0)\n{T*2}(layer "{layer}"){h}\n'
            f'{T*2}(uuid "{U()}")\n{T*2}(effects\n{T*3}(font\n{T*4}(size 1 1)\n{T*4}(thickness 0.15)\n{T*3})\n{T*2})\n{T})\n')


def usb_hx():
    name = "USB_C_HX_16P_180_LT_H10"
    s = (f'(footprint "{name}"\n{T}(version 20260206)\n{T}(generator "pcbnew")\n{T}(generator_version "10.0")\n'
         f'{T}(layer "F.Cu")\n'
         f'{T}(descr "Vertical USB 2.0 Type-C receptacle, 16 contacts, H 10.0 mm, HX-TYPE-C 16P 180 LT H10.0 (LCSC '
         f'C49261569). Land pattern from the maker\'s recommended PCB layout: 2 x 8 pads 0.50 x 1.14 mm, 1.00 mm pitch, '
         f'rows 2.96 mm apart; two 0.90 mm NPTH for the locating pegs. _work/rev08_footprints.py")\n'
         f'{T}(tags "USB C Type-C vertical receptacle 16P")\n'
         + text_prop("Reference", "REF**", -3.4, "F.SilkS") + text_prop("Value", name, 3.4, "F.Fab")
         + text_prop("Datasheet", "", 0, "F.Fab", hide=True) + text_prop("Description", "", 0, "F.Fab", hide=True)
         + f'{T}(attr smd)\n')
    xs = [-3.5 + k for k in range(8)]
    for x, n in zip(xs, ("B1", "B4", "B5", "B6", "B7", "B8", "B9", "B12")):
        s += pad(n, x, -1.48, 0.5, 1.14)
    for x, n in zip(xs, ("A12", "A9", "A8", "A7", "A6", "A5", "A4", "A1")):
        s += pad(n, x, 1.48, 0.5, 1.14)
    s += npth(-4.225, 0, 0.9) + npth(4.225, 0, 0.9)
    s += rect("F.Fab", -4.17, -1.25, 4.17, 1.25, 0.1)          # the 8.34 x 2.50 mm body seen from above
    s += rect("F.CrtYd", -5.0, -2.4, 5.0, 2.4, 0.05)
    s += rect("F.SilkS", -4.4, -2.25, 4.4, 2.25, 0.12)
    s += ")\n"
    open(os.path.join(DST, name + ".kicad_mod"), "w", encoding="utf-8", newline="\n").write(s)


def main():
    for n in COPY:
        copy(n)
    usb_hx()
    print(f"{len(COPY) + 1} footprints written to {os.path.relpath(DST, ROOT)}")


if __name__ == "__main__":
    main()
