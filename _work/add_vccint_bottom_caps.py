#!/usr/bin/env python3
"""
VCCINT bottom-side decoupling added on 11 Nov 2026 (docs/SIGNAL_INTEGRITY.md §4.3):

Four 0.47 uF 0402 capacitors, C1184-C1187, on +1V0/GND in CONTROL, next to VCCINT's own row. On
the board they sit on the bottom face inside the XC7A50T's footprint, each pad on a +1V0 or GND
ball via (POFV): L4 is 0.25 mm from the bottom face and 1.18 mm from the top, so these loops are
a quarter of the top-side ones'. The other VCCINT caps (UG483 Table 2-2) are unchanged.

Text edit, the same helpers as _work/add_esd.py. Run once; it refuses to run twice. Then ERC.

Usage:  py _work/add_vccint_bottom_caps.py
"""
import os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import add_esd as E                                  # noqa: E402

REFS = ["C1184", "C1185", "C1186", "C1187"]
X0, Y = 101.6, 508.0                                 # an empty band between the VCCINT and VCCO_35 rows


def main():
    c = E.Sheet("rev03/CONTROL.kicad_sch")
    if '"C1184"' in c.t: sys.exit("already added")
    E.PWR = max(int(n) for n in re.findall(r"#PWR(\d+)", c.t + "".join(
        open(os.path.join(E.ROOT, "rev03", f), encoding="utf-8").read()
        for f in os.listdir(os.path.join(E.ROOT, "rev03")) if f.endswith(".kicad_sch"))))
    for k, ref in enumerate(REFS):
        x = X0 + 12.7 * k
        c.new.append(E.instance("Device:C", ref, "0.47u", "Capacitor_SMD:C_0402_1005Metric", x, Y, 0,
                                ["1", "2"], c.ipath, c.project))
        E.PWR += 1
        c.new.append(E.instance("power:+1V0", f"#PWR{E.PWR}", "+1V0", "", x, Y - 3.81, 0, ["1"],
                                c.ipath, c.project, in_bom=False))
        c.gnd(x, Y + 3.81)
    c.new.append('\t(text "VCCINT, bottom face under the BGA (on ball vias)"\n\t\t(exclude_from_sim no)\n'
                 f'\t\t(at {X0 - 2.54:.2f} {Y - 10.16:.2f} 0)\n\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1.27 1.27)\n'
                 f'\t\t\t)\n\t\t\t(justify left)\n\t\t)\n\t\t(uuid "{E.U()}")\n\t)')
    c.save()
    print("added:", ", ".join(REFS), "(CONTROL)")


if __name__ == "__main__":
    main()
