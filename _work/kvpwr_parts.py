#!/usr/bin/env python3
"""
Single power entry for the KV260 (docs/POWER_SPEC.md section 1.4, BOARD_MANUAL section 6): the new library parts.

  TPS26631PWP  symbol, pin table from TI SLVSE94G (June 2024) Table 5-1, HTSSOP (PWP) column:
               1-3 IN, 4 B_GATE, 5 DRV, 6 IN_SYS, 7 UVLO, 8 OVP, 9 GND, 10 dVdT, 11 ILIM, 12 MODE, 13 SHDN,
               14 IMON, 15 FLT, 16 PGTH, 17 PGOOD, 18-20 OUT, 21 PowerPAD (to GND, "not the only GND connection").
               IN, IN_SYS and OUT are passive pins: they join one net each and need no power flag.
               Footprint: KiCad's HTSSOP-20 3.4 x 6.5 mm pad with a 2.96 x 2.96 mm mask opening and thermal vias,
               the land pattern of TI's PWP0020T drawing (same data sheet, Example Board Layout).
  CMC_9070     footprint for the common-mode choke L1004 (ZE ZEGMCM9070-501T, LCSC C53154905; the same 9.0 x 7.0 mm
               package as Coilmaster SMM9070-501). Land pattern from the Coilmaster SMM9070 data sheet, page 1:
               pads 2.5 x 1.5 mm at (+-4.25, +-1.75). The part's windings join its pins 1-4 and 2-3; the pads are
               numbered so that KiCad's Filter:Choke_CommonMode_FerriteCore_1234 symbol (windings 1-2 and 3-4)
               draws them as they are: pad 1 = part pin 1, pad 2 = part pin 4, pad 3 = part pin 2, pad 4 = part pin 3.
               Pads 1 and 3 (part pins 1 and 2) are the dotted ends, the jack side.

Usage:  py _work/kvpwr_parts.py      (rewrites the symbol and the footprint in place)
"""
import os
import sys
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rev08_symbols as RS                                          # noqa: E402

ROOT = os.path.dirname(HERE)
FP_DIR = os.path.join(ROOT, "footprints", "kv260-ias2rf.pretty")
P, I, O, PW, OC = "passive", "input", "output", "power_in", "open_collector"
SRC = "TI SLVSE94G Table 5-1, HTSSOP (PWP) column; see _work/kvpwr_parts.py"

SYM = RS.make(
    "TPS26631PWP", "U",
    "60 V 6 A eFuse, 31 mOhm, adjustable UVLO/OVP cutoff and current limit, reverse polarity with an external N-FET, "
    "HTSSOP-20 PowerPAD",
    "Package_SO:HTSSOP-20-1EP_4.4x6.5mm_P0.65mm_EP3.4x6.5mm_Mask2.96x2.96mm_ThermalVias",
    left=[(P, "IN", 1), (P, "IN", 2), (P, "IN", 3), None, (P, "IN_SYS", 6), (O, "B_GATE", 4), (O, "DRV", 5), None,
          (I, "UVLO", 7), (I, "OVP", 8), None, (I, "SHDN", 13), (I, "MODE", 12)],
    right=[(P, "OUT", 18), (P, "OUT", 19), (P, "OUT", 20), None, (OC, "PGOOD", 17), (I, "PGTH", 16),
           (OC, "~{FLT}", 15), (O, "IMON", 14), None, (P, "ILIM", 11), (P, "dVdT", 10)],
    bottom=[(PW, "GND", 9), (PW, "EP", 21)], w=10.16, source=SRC)


def write_symbol():
    t = open(RS.LIB, encoding="utf-8").read()
    name = "TPS26631PWP"
    i = t.find(f'\n\t(symbol "{name}"\n')
    if i >= 0:
        j = t.find('\n\t(symbol "', i + 5)
        j = j if j > 0 else t.rfind("\n)")
        t = t[:i] + "\n" + SYM + t[j:]
    else:
        k = t.rfind("\n)")
        t = t[:k] + "\n" + SYM + t[k:]
    open(RS.LIB, "w", encoding="utf-8", newline="\n").write(t)
    print("symbol TPS26631PWP written")


NS = uuid.UUID("7d0c1a52-3e8b-4c6f-9a2d-5b4e8f1c0a91")


def U(*k):
    return str(uuid.uuid5(NS, "|".join(map(str, k))))


def line(x1, y1, x2, y2, layer, w):
    return (f'\t(fp_line\n\t\t(start {x1} {y1})\n\t\t(end {x2} {y2})\n\t\t(stroke\n\t\t\t(width {w})\n'
            f'\t\t\t(type solid)\n\t\t)\n\t\t(layer "{layer}")\n\t\t(uuid "{U(x1, y1, x2, y2, layer)}")\n\t)\n')


def rect(x1, y1, x2, y2, layer, w):
    return "".join(line(*s, layer, w) for s in ((x1, y1, x2, y1), (x2, y1, x2, y2), (x2, y2, x1, y2), (x1, y2, x1, y1)))


def pad(num, x, y):
    return (f'\t(pad "{num}" smd roundrect\n\t\t(at {x} {y})\n\t\t(size 2.5 1.5)\n\t\t(layers "F.Cu" "F.Mask" "F.Paste")\n'
            f'\t\t(roundrect_rratio 0.1)\n\t\t(uuid "{U("pad", num)}")\n\t)\n')


def prop(name, val, x, y, layer, hide):
    h = "\t\t(hide yes)\n" if hide else ""
    return (f'\t(property "{name}" "{val}"\n\t\t(at {x} {y} 0)\n\t\t(layer "{layer}")\n{h}\t\t(uuid "{U("prop", name)}")\n'
            f'\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1 1)\n\t\t\t\t(thickness 0.15)\n\t\t\t)\n\t\t)\n\t)\n')


DESCR = ("Power common-mode choke 9.0 x 7.0 x 4.8 mm, 4 pads; windings pads 1-2 and 3-4 (part pins 1-4 and 2-3); "
         "pads 1 and 3 dotted. Coilmaster SMM9070-501, ZE ZEGMCM9070-501T (LCSC C53154905)")


def write_footprint():
    name = "CMC_9070_SMD-4P_9.0x7.0mm"
    out = [f'(footprint "{name}"\n\t(version 20260206)\n\t(generator "pcbnew")\n\t(generator_version "10.0")\n'
           f'\t(layer "F.Cu")\n\t(descr "{DESCR}")\n',
           prop("Reference", "REF**", 0, -4.6, "F.SilkS", False),
           prop("Value", name, 0, 4.6, "F.Fab", False),
           prop("Datasheet", "", 0, 0, "F.Fab", True),
           '\t(attr smd)\n\t(duplicate_pad_numbers_are_jumpers no)\n']
    # body 9.0 x 7.0 (x along the pad rows); fab outline, pin-1 chamfer mark
    out.append(rect(-4.5, -3.5, 4.5, 3.5, "F.Fab", 0.1))
    out.append(line(-4.5, -2.6, -3.6, -3.5, "F.Fab", 0.1))
    # silk: the two long sides between the pad columns, clear of the pads, and a pin-1 dot
    out.append(line(-2.8, -3.62, 2.8, -3.62, "F.SilkS", 0.12))
    out.append(line(-2.8, 3.62, 2.8, 3.62, "F.SilkS", 0.12))
    out.append(f'\t(fp_circle\n\t\t(center -6.0 -1.75)\n\t\t(end -5.75 -1.75)\n\t\t(stroke\n\t\t\t(width 0.12)\n'
               f'\t\t\t(type solid)\n\t\t)\n\t\t(fill yes)\n\t\t(layer "F.SilkS")\n\t\t(uuid "{U("dot")}")\n\t)\n')
    # courtyard: the pads reach x +-5.5, the body y +-3.5
    out.append(rect(-5.75, -3.75, 5.75, 3.75, "F.CrtYd", 0.05))
    out.append(f'\t(fp_text user "${{REFERENCE}}"\n\t\t(at 0 0 0)\n\t\t(layer "F.Fab")\n\t\t(uuid "{U("reftext")}")\n'
               f'\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1 1)\n\t\t\t\t(thickness 0.15)\n\t\t\t)\n\t\t)\n\t)\n')
    for num, x, y in (("1", -4.25, -1.75), ("2", 4.25, -1.75), ("3", -4.25, 1.75), ("4", 4.25, 1.75)):
        out.append(pad(num, x, y))
    out.append(f'\t(model "${{KIPRJMOD}}/mech/models3d/CMC_9070_SMD-4P_9.0x7.0mm.step"\n\t\t(offset\n\t\t\t(xyz 0 0 0)\n'
               f'\t\t)\n\t\t(scale\n\t\t\t(xyz 1 1 1)\n\t\t)\n\t\t(rotate\n\t\t\t(xyz 0 0 0)\n\t\t)\n\t)\n)\n')
    path = os.path.join(FP_DIR, name + ".kicad_mod")
    open(path, "w", encoding="utf-8", newline="\n").write("".join(out))
    print("footprint", os.path.relpath(path, ROOT))


if __name__ == "__main__":
    write_symbol()
    write_footprint()
