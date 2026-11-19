#!/usr/bin/env python3
"""
PSU board: the project's own library parts, written to psu/psu.kicad_sym and psu/psu.pretty/.

Symbols (pin tables from the data sheets):
  LM5177      TI SNVSBU4F (January 2025) Table 4-1, 38-pin DCP HTSSOP; pin 39 the PowerPAD (AGND)
  LTC4364MS   Analog Devices LTC4364 rev. B, Pin Functions, MS (16-lead MSOP) column
  TPS26631RGE TI SLVSE94G (June 2024) Table 5-1, VQFN (RGE) column; pin 25 the PowerPAD (GND)
  NMOS_SON8   N-MOSFET in Infineon PG-TDSON-8 (SuperSO8): 1-3 source, 4 gate, 5 drain (pad and tabs)
  NMOS_D2PAK  N-MOSFET in TO-263-2 (D2PAK): 1 gate, 2 drain (tab), 3 source
Footprints (land patterns from the data sheets):
  TI_DCP0038A_HTSSOP-38   TI's DCP0038A example board layout (SNVSBU4F): 38 x 1.5 x 0.3 mm pads at 0.5 mm, rows
                          5.8 mm apart (pad centres), thermal pad 2.9 x 4.7 mm with 0.2 mm vias
  L_KOHER_MDA1870         KOHERelec MDA series size 1870 land pattern: 18.5 mm over, 12.0 mm gap, 12.5 mm tall
  L_KOHER_MDA1365         size 1365: 14.5 mm over, 8.0 mm gap, 5.0 mm tall

Usage:  py _work/psu/psu_parts.py
"""
import os
import sys
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import rev08_symbols as RS                                          # noqa: E402

ROOT = os.path.dirname(os.path.dirname(HERE))
PSU = os.path.join(ROOT, "psu")
SYM_LIB = os.path.join(PSU, "psu.kicad_sym")
FP_DIR = os.path.join(PSU, "psu.pretty")
P, I, O, PW, OC, NC = "passive", "input", "output", "power_in", "open_collector", "no_connect"
FPL = "psu:"


def symbols():
    s = []
    s.append(RS.make(
        "LM5177", "U", "60 V four-switch buck-boost controller, 3.5 to 60 V in (2.8 V with BIAS), 2 A drivers, "
        "average current limiter, HTSSOP-38 PowerPAD", FPL + "TI_DCP0038A_HTSSOP-38",
        left=[(P, "VIN", 3), (I, "EN/UVLO", 4), (P, "BIAS", 1), None, (I, "ISNSP", 23), (I, "ISNSN", 22), None,
              (I, "CSA", 37), (I, "CSB", 38), None, (P, "SW1", 36), (P, "HB1", 35), (O, "HO1", 34), (O, "LO1", 32),
              None, (O, "HO1_LL", 8), (O, "HO2_LL", 9)],
        right=[(I, "VOUT", 20), (I, "FB", 19), (P, "COMP", 18), (P, "SS/ATRK", 16), (P, "RT", 15),
               (P, "SLOPE", 14), (P, "CFG", 13), (I, "MODE", 12), (I, "SYNC", 11), (I, "DTRK", 10),
               (OC, "nFLT", 7), (P, "IMONOUT", 6), None, (P, "SW2", 25), (P, "HB2", 26), (O, "HO2", 27),
               (O, "LO2", 29), (P, "VCC", 31)],
        bottom=[(PW, "AGND", 17), (PW, "PGND", 30), (PW, "EP", 39), (NC, "NC", 2), (NC, "NC", 5), (NC, "NC", 21),
                (NC, "NC", 24), (NC, "NC", 28), (NC, "NC", 33)], w=12.7,
        source="TI SNVSBU4F Table 4-1 (DCP); see _work/psu/psu_parts.py"))
    s.append(RS.make(
        "LTC4364MS", "U", "Surge stopper with ideal diode controller, 4 to 80 V, -40 V reverse, output clamp, fault "
        "timer, MSOP-16 (LTC4364-2: auto-retry)", "Package_SO:MSOP-16_3x4.039mm_P0.5mm",
        left=[(PW, "VCC", 8), None, (I, "UV", 10), (I, "OV", 11), (I, "SHDN", 9)],
        right=[(O, "HGATE", 6), (P, "SOURCE", 5), (O, "DGATE", 4), (I, "SENSE", 2), (I, "OUT", 1), (I, "FB", 16),
               (P, "TMR", 15), (OC, "FLT", 13), (OC, "ENOUT", 14)],
        bottom=[(PW, "GND", 12), (NC, "NC", 3), (NC, "NC", 7)], w=10.16,
        source="Analog Devices LTC4364 rev. B, Pin Functions (MS); see _work/psu/psu_parts.py"))
    s.append(RS.make(
        "TPS26631RGE", "U", "60 V 6 A eFuse, 31 mOhm, adjustable UVLO/OVP cutoff and current limit, VQFN-24 4x4",
        "Package_DFN_QFN:Texas_RGE0024H_VQFN-24-1EP_4x4mm_P0.5mm_EP2.7x2.7mm_ThermalVias",
        left=[(P, "IN", 1), (P, "IN", 2), None, (P, "IN_SYS", 5), (O, "B_GATE", 3), (O, "DRV", 4), None,
              (I, "UVLO", 6), (I, "OVP", 7), None, (I, "SHDN", 12), (I, "MODE", 11)],
        right=[(P, "OUT", 17), (P, "OUT", 18), None, (OC, "PGOOD", 16), (I, "PGTH", 15), (OC, "~{FLT}", 14),
               (O, "IMON", 13), None, (P, "ILIM", 10), (P, "dVdT", 9)],
        bottom=[(PW, "GND", 8), (PW, "EP", 25), (NC, "NC", 19), (NC, "NC", 20), (NC, "NC", 21), (NC, "NC", 22),
                (NC, "NC", 23), (NC, "NC", 24)], w=10.16,
        source="TI SLVSE94G Table 5-1 (VQFN, RGE); see _work/psu/psu_parts.py"))
    s.append(RS.make(
        "NMOS_SON8", "Q", "N-channel MOSFET, PG-TDSON-8 (SuperSO8): 1-3 source, 4 gate, 5 drain",
        "Package_SON:Infineon_PG-TDSON-8_6.15x5.15mm",
        left=[(I, "G", 4)], right=[(P, "D", 5), None, (P, "S", 1), (P, "S", 2), (P, "S", 3)],
        source="Infineon BSC0805LS / BSC026N04LS / BSC040N10NS5 pinout; see _work/psu/psu_parts.py"))
    s.append(RS.make(
        "NMOS_D2PAK", "Q", "N-channel MOSFET, TO-263-2 (D2PAK): 1 gate, 2 drain (tab), 3 source",
        "Package_TO_SOT_SMD:TO-263-2",
        left=[(I, "G", 1)], right=[(P, "D", 2), None, (P, "S", 3)],
        source="Infineon IPB048N15N5 pinout; see _work/psu/psu_parts.py"))
    return s


def write_symbols():
    os.makedirs(PSU, exist_ok=True)
    head = '(kicad_symbol_lib\n\t(version 20241209)\n\t(generator "kv260-ias2rf/_work/psu/psu_parts.py")\n'
    open(SYM_LIB, "w", encoding="utf-8", newline="\n").write(head + "".join(x if x.endswith("\n") else x + "\n"
                                                                            for x in symbols()) + ")\n")


NS = uuid.UUID("3b8f1e2a-6c4d-4e5f-8a9b-0c1d2e3f4a5b")


def U(*k):
    return str(uuid.uuid5(NS, "/".join(map(str, k))))


def fp_head(name, descr, layer_attr="smd"):
    return (f'(footprint "{name}"\n\t(version 20241229)\n\t(generator "kv260-ias2rf/_work/psu/psu_parts.py")\n'
            f'\t(layer "F.Cu")\n\t(descr "{descr}")\n')


def prop(name, val, x, y, layer, hide, k):
    return (f'\t(property "{name}" "{val}"\n\t\t(at {x:g} {y:g} 0)\n\t\t(layer "{layer}")\n'
            + ('\t\t(hide yes)\n' if hide else '') + f'\t\t(uuid "{U(k, name)}")\n'
            f'\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1 1)\n\t\t\t\t(thickness 0.15)\n\t\t\t)\n\t\t)\n\t)\n')


def rect(x1, y1, x2, y2, layer, w, k, n):
    return (f'\t(fp_rect\n\t\t(start {x1:g} {y1:g})\n\t\t(end {x2:g} {y2:g})\n\t\t(stroke\n\t\t\t(width {w:g})\n'
            f'\t\t\t(type solid)\n\t\t)\n\t\t(fill no)\n\t\t(layer "{layer}")\n\t\t(uuid "{U(k, layer, n)}")\n\t)\n')


def pad(num, kind, shape, x, y, w, h, k, layers='"F.Cu" "F.Paste" "F.Mask"', extra=""):
    return (f'\t(pad "{num}" {kind} {shape}\n\t\t(at {x:g} {y:g})\n\t\t(size {w:g} {h:g})\n'
            + (f'\t\t(drill {extra})\n' if kind == "thru_hole" else "")
            + f'\t\t(layers {layers})\n' + ('\t\t(roundrect_rratio 0.15)\n' if shape == "roundrect" else "")
            + f'\t\t(uuid "{U(k, "pad", num, x, y)}")\n\t)\n')


def fp_htssop38():
    name = "TI_DCP0038A_HTSSOP-38"
    k = name
    t = fp_head(name, "TI DCP0038A, HTSSOP-38 4.4 x 9.7 mm, 0.5 mm pitch, thermal pad 2.9 x 4.7 mm "
                      "(TI example board layout, SNVSBU4F)")
    t += prop("Reference", "REF**", 0, -6.2, "F.SilkS", False, k) + prop("Value", name, 0, 6.2, "F.Fab", False, k)
    t += prop("Footprint", "", 0, 0, "F.Fab", True, k) + prop("Datasheet", "", 0, 0, "F.Fab", True, k)
    t += prop("Description", "", 0, 0, "F.Fab", True, k)
    t += '\t(attr smd)\n'
    for i in range(19):
        y = -4.5 + 0.5 * i
        t += pad(str(1 + i), "smd", "roundrect", -2.9, y, 1.5, 0.3, k)
        t += pad(str(38 - i), "smd", "roundrect", 2.9, y, 1.5, 0.3, k)
    t += pad("39", "smd", "rect", 0, 0, 2.9, 4.7, k)
    for vx in (-0.8, 0.8):
        for vy in (-1.6, -0.55, 0.55, 1.6):
            t += pad("39", "thru_hole", "circle", vx, vy, 0.45, 0.45, k, layers='"*.Cu"', extra="0.2")
    t += rect(-2.2, -4.85, 2.2, 4.85, "F.Fab", 0.1, k, 1) + rect(-3.9, -5.1, 3.9, 5.1, "F.CrtYd", 0.05, k, 2)
    t += (f'\t(fp_circle\n\t\t(center -3.6 -5.0)\n\t\t(end -3.45 -5.0)\n\t\t(stroke\n\t\t\t(width 0.12)\n'
          f'\t\t\t(type solid)\n\t\t)\n\t\t(fill yes)\n\t\t(layer "F.SilkS")\n\t\t(uuid "{U(k, "dot")}")\n\t)\n')
    t += model("Package_SO.3dshapes/TSSOP-38_4.4x9.7mm_P0.5mm.step")
    return name, t + ")\n"


def model(path):
    """a 3-D body from KiCad's own library"""
    return (f'\t(model "${{KICAD10_3DMODEL_DIR}}/{path}"\n\t\t(offset\n\t\t\t(xyz 0 0 0)\n\t\t)\n\t\t(scale\n'
            f'\t\t\t(xyz 1 1 1)\n\t\t)\n\t\t(rotate\n\t\t\t(xyz 0 0 0)\n\t\t)\n\t)\n')


def fp_inductor(name, descr, over, gap, tall, body_x, body_y, body3d):
    k = name
    w = (over - gap) / 2
    cx = gap / 2 + w / 2
    t = fp_head(name, descr)
    t += prop("Reference", "REF**", 0, -body_y / 2 - 1.2, "F.SilkS", False, k)
    t += prop("Value", name, 0, body_y / 2 + 1.2, "F.Fab", False, k)
    t += prop("Footprint", "", 0, 0, "F.Fab", True, k) + prop("Datasheet", "", 0, 0, "F.Fab", True, k)
    t += prop("Description", "", 0, 0, "F.Fab", True, k)
    t += '\t(attr smd)\n'
    t += pad("1", "smd", "rect", -cx, 0, w, tall, k) + pad("2", "smd", "rect", cx, 0, w, tall, k)
    t += rect(-body_x / 2, -body_y / 2, body_x / 2, body_y / 2, "F.Fab", 0.1, k, 1)
    t += rect(-body_x / 2 - 0.25, -body_y / 2 - 0.25, body_x / 2 + 0.25, body_y / 2 + 0.25, "F.CrtYd", 0.05, k, 2)
    t += rect(-body_x / 2 - 0.12, -body_y / 2 - 0.12, body_x / 2 + 0.12, body_y / 2 + 0.12, "F.SilkS", 0.12, k, 3)
    t += model(body3d)
    return name, t + ")\n"


def write_footprints():
    os.makedirs(FP_DIR, exist_ok=True)
    for name, t in (fp_htssop38(),
                    fp_inductor("L_KOHER_MDA1870", "KOHERelec MDA1870 molded power inductor 17.8 x 16.9 x 6.7 mm; "
                                "land pattern from the MDA series 1870 data sheet; 3-D body: KiCad's Changjiang "
                                "FXL1770, about the same size", 18.5, 12.0, 12.5, 17.8, 16.9,
                                "Inductor_SMD.3dshapes/L_Changjiang_FXL1770.step"),
                    fp_inductor("L_KOHER_MDA1365", "KOHERelec MDA1365 molded power inductor 13.5 x 12.6 x 6.2 mm; "
                                "land pattern from the MDA series 1365 data sheet; 3-D body: KiCad's Changjiang "
                                "FXL1350, about the same size", 14.5, 8.0, 5.0, 13.5, 12.6,
                                "Inductor_SMD.3dshapes/L_Changjiang_FXL1350.step")):
        open(os.path.join(FP_DIR, name + ".kicad_mod"), "w", encoding="utf-8", newline="\n").write(t)


if __name__ == "__main__":
    write_symbols()
    write_footprints()
    print("wrote", os.path.relpath(SYM_LIB, ROOT), "and", os.path.relpath(FP_DIR, ROOT))
