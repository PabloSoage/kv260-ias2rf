#!/usr/bin/env python3
"""
Two land patterns added before the Rev08 tag (18 November 2026), into footprints/kv260-ias2rf.pretty.

* USB_C_HRO_TYPE-C-31-E-17: the debug USB-C J1501, now the HRO TYPE-C-31-E-17 (LCSC C7424785), a vertical
  receptacle 6.0 mm tall that is surface mount throughout. Drawn from the maker's "RECOMMENDED PCB LAYOUT (TOP
  VIEW)" [V, drawing read 18 Nov 2026]: 16 contacts 0.30 x 0.69 mm, the A row (A1 A4 A5 A6 A7 A8 A9 A12) and the
  B row (B12 B9 B8 B7 B6 B5 B4 B1) with their centres 1.62 mm apart, at x = -2.75, -1.25, -0.75, -0.25, 0.25,
  0.75, 1.25, 2.75; four shell tabs 0.60 x 1.02 mm at x = +-2.29, y = +-2.08 (the symbol's shield pin, SH); a
  round hole of 0.50 mm at x = -3.75 and a slot 0.70 x 0.52 mm at x = +3.75 for the two plastic pegs, which are
  0.70 mm long and so stop inside the 1.6 mm board.
  The part it replaces, HX-TYPE-C 16P 180 LT H10.0, has four through-hole shell legs that reach 2.1 mm below its
  seat (its drawing); on the IAS0 tongue, 0.8 mm above the carrier, they would have touched the carrier.
* FPC_1.0_15P_XUNPU_FPC-1.0FX-15PWCR-H20: J1502, the 15-way 1.0 mm FPC receptacle (XUNPU FPC-1.0FX-15PWCR-H20,
  LCSC C19269358, hinged lid, contacts on the bottom), from the maker's "PCB LAYOUT" [V]: 15 pads 0.50 x 1.50 mm at
  1.00 mm pitch, two fixing tabs 2.00 x 1.70 mm whose outer edges are 3.20 mm past the end pads, 4.20 mm from the
  pads' outer edge to the tabs' far edge. The tabs are pad "MP" (the symbol's mounting pin). The cable goes in on
  the tabs' side (+y here), away from the solder tails.

Usage:  py _work/rev08_final_footprints.py
"""
import os
import sys
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from rev08_footprints import pad, npth, rect, text_prop, DST, T   # noqa: E402

U = lambda: str(uuid.uuid4())


def slot(x, y, w, h):
    """A non-plated oval hole, w along x."""
    return (f'{T}(pad "" np_thru_hole oval\n{T*2}(at {x:g} {y:g})\n{T*2}(size {w:g} {h:g})\n'
            f'{T*2}(drill oval {w:g} {h:g})\n{T*2}(layers "*.Cu" "*.Mask")\n{T*2}(uuid "{U()}")\n{T})\n')


def line(layer, x0, y0, x1, y1, width):
    return (f'{T}(fp_line\n{T*2}(start {x0:g} {y0:g})\n{T*2}(end {x1:g} {y1:g})\n'
            f'{T*2}(stroke\n{T*3}(width {width:g})\n{T*3}(type solid)\n{T*2})\n'
            f'{T*2}(layer "{layer}")\n{T*2}(uuid "{U()}")\n{T})\n')


def model(path, rot=0):
    return (f'{T}(model "{path}"\n{T*2}(offset\n{T*3}(xyz 0 0 0)\n{T*2})\n{T*2}(scale\n{T*3}(xyz 1 1 1)\n{T*2})\n'
            f'{T*2}(rotate\n{T*3}(xyz 0 0 {rot:g})\n{T*2})\n{T})\n')


def head(name, descr, tags, ref_y, val_y):
    return (f'(footprint "{name}"\n{T}(version 20260206)\n{T}(generator "pcbnew")\n{T}(generator_version "10.0")\n'
            f'{T}(layer "F.Cu")\n{T}(descr "{descr}")\n{T}(tags "{tags}")\n'
            + text_prop("Reference", "REF**", ref_y, "F.SilkS") + text_prop("Value", name, val_y, "F.Fab")
            + text_prop("Datasheet", "", 0, "F.Fab", hide=True) + text_prop("Description", "", 0, "F.Fab", hide=True)
            + f'{T}(attr smd)\n')


def usb_hro():
    name = "USB_C_HRO_TYPE-C-31-E-17"
    s = head(name, "Vertical USB 2.0 Type-C receptacle, 16 contacts, H 6.0 mm, IPX5, surface mount only: HRO "
                   "TYPE-C-31-E-17 (LCSC C7424785). Land pattern from the maker's recommended PCB layout: contacts "
                   "0.30 x 0.69 mm at 0.50 mm, rows 1.62 mm apart, four shell tabs 0.60 x 1.02 mm, a 0.50 mm hole and "
                   "a 0.70 x 0.52 mm slot for the 0.70 mm pegs. _work/rev08_final_footprints.py",
             "USB C Type-C vertical receptacle 16P SMD", -3.4, 3.4)
    xs = (-2.75, -1.25, -0.75, -0.25, 0.25, 0.75, 1.25, 2.75)
    for x, n in zip(xs, ("A1", "A4", "A5", "A6", "A7", "A8", "A9", "A12")):
        s += pad(n, x, -0.81, 0.30, 0.69)
    for x, n in zip(xs, ("B12", "B9", "B8", "B7", "B6", "B5", "B4", "B1")):
        s += pad(n, x, 0.81, 0.30, 0.69)
    for x in (-2.29, 2.29):
        for y in (-2.08, 2.08):
            s += pad("SH", x, y, 0.60, 1.02)
    s += npth(-3.75, 0, 0.5) + slot(3.75, 0, 0.70, 0.52)
    s += rect("F.Fab", -4.85, -2.295, 4.85, 2.295, 0.1)          # the 9.70 x 4.59 mm housing seen from above
    s += rect("F.CrtYd", -5.25, -2.65, 5.25, 2.65, 0.05)         # the seal flange is 10.38 mm across
    s += line("F.SilkS", -5.3, -2.7, -3.0, -2.7, 0.12) + line("F.SilkS", 3.0, -2.7, 5.3, -2.7, 0.12)
    s += line("F.SilkS", -5.3, 2.7, -3.0, 2.7, 0.12) + line("F.SilkS", 3.0, 2.7, 5.3, 2.7, 0.12)
    s += line("F.SilkS", -3.4, -1.6, -3.4, -1.2, 0.12)          # A1 mark
    s += model("${KIPRJMOD}/mech/models3d/USB_C_HRO_TYPE-C-31-E-17.wrl")
    s += ")\n"
    open(os.path.join(DST, name + ".kicad_mod"), "w", encoding="utf-8", newline="\n").write(s)


def fpc_xunpu():
    name = "FPC_1.0_15P_XUNPU_FPC-1.0FX-15PWCR-H20"
    s = head(name, "FPC/FFC receptacle, 15 contacts at 1.00 mm, hinged lid, bottom contact, H 2.0 mm: XUNPU "
                   "FPC-1.0FX-15PWCR-H20 (LCSC C19269358). Pads 0.50 x 1.50 mm, fixing tabs 2.00 x 1.70 mm (MP). The "
                   "cable enters on the +y side. _work/rev08_final_footprints.py",
             "FPC FFC 1.0mm 15P connector", -3.2, 5.6)
    for k in range(15):
        s += pad(str(k + 1), -7.0 + k, -1.30, 0.50, 1.50)
    for x in (-9.2, 9.2):
        s += pad("MP", x, 1.30, 2.00, 1.70)
    s += rect("F.Fab", -10.45, -0.55, 10.45, 4.35, 0.1)          # the 20.9 mm body
    s += rect("F.CrtYd", -10.7, -2.1, 10.7, 4.6, 0.05)
    s += line("F.SilkS", -10.2, 2.4, -10.2, 4.0, 0.12) + line("F.SilkS", 10.55, 2.4, 10.55, 4.0, 0.12)  # -x is the board edge side
    s += line("F.SilkS", -7.6, -2.25, -7.0, -2.25, 0.12)          # pin 1 mark
    s += model("${KIPRJMOD}/_work/mech/cache/models3d/FPC-SMD_15P-P1.00_XUNPU_FPC-1.0FX-15PWCR-H20.wrl")
    s += ")\n"
    open(os.path.join(DST, name + ".kicad_mod"), "w", encoding="utf-8", newline="\n").write(s)


if __name__ == "__main__":
    usb_hro()
    fpc_xunpu()
    print("wrote USB_C_HRO_TYPE-C-31-E-17 and FPC_1.0_15P_XUNPU_FPC-1.0FX-15PWCR-H20")
