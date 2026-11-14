#!/usr/bin/env python3
"""
Rev06: the SGMII receiver's common-mode bias made locally, at the PHY (14 Nov 2026).

R1215/R1216 (10 k from each ETH_SGRX_FPGA leg) first went to +1V2, which exists only near J101 and on a few vias
30 mm from the PHY. Placed by those vias they hung off the legs as 23 mm / 11 mm branches (157 / 75 ps stubs,
lvds_skew.py): an open stub resonates near 1.6 GHz, inside a 1.25 Gb/s signal's spectrum. Now they sit on the legs
next to C1218/C1219, and their common node is made there from +3V3_D:

  R1212  10 k   +3V3_D -> ETH_VCM
  R1217  5.6 k  ETH_VCM -> GND          VCM = 3.3 x 5.6 / 15.6 = 1.18 V (LVDS_25 input common mode 0.3-1.5 V)
  C1222  100 nF ETH_VCM -> GND
  R1215, R1216  10 k  ETH_SGRX_FPGA_P/N -> ETH_VCM (were -> +1V2)

Text edit of rev03/CONTROL.kicad_sch with add_ethernet.py's helpers. Refuses to run twice.
Usage:  py _work/rev06_vcm.py
"""
import os, re, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "_work"))
import add_ethernet as AE                                          # noqa: E402
from rev06_eth import highest                                      # noqa: E402

AE.POWER["+3V3_D"] = ("power:+3V3", "+3V3_D")


def main():
    s = AE.Sheet()
    if "ETH_VCM" in s.t: sys.exit("already applied")
    AE.PWR[0] = highest("#PWR")
    # the two +1V2 symbols on R1215/R1216's pin 2 become ETH_VCM labels
    for x in (810.26, 820.42):
        m = re.search(r'\n\t\(symbol\n\t\t\(lib_id "power:\+1V2"\)\n\t\t\(at ' + re.escape(f"{x:g}") + r' 539\.75 0\).*?\n\t\)\n',
                      s.t, re.S)
        assert m, x
        s.t = s.t[:m.start()] + "\n" + s.t[m.end():]
        s.new.append(AE.label("ETH_VCM", x, 539.75, 0))
    X, Y = 830.58, 535.94
    p = s.inst("Device:R", "R1212", "10k", AE.R0402, X, Y, "SGMII RX common mode: top of the divider")
    s.connect(p["1"], "+3V3_D"); s.connect(p["2"], "ETH_VCM")
    p = s.inst("Device:R", "R1217", "5.6k", AE.R0402, X + 10.16, Y, "SGMII RX common mode: bottom, 1.18 V")
    s.connect(p["1"], "ETH_VCM"); s.connect(p["2"], "GND")
    p = s.inst("Device:C", "C1222", "100n", AE.C0402, X + 20.32, Y, "SGMII RX common mode decoupling")
    s.connect(p["1"], "ETH_VCM"); s.connect(p["2"], "GND")
    s.save()
    print("ETH_VCM made locally; #PWR up to", AE.PWR[0])


if __name__ == "__main__":
    main()
