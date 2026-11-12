#!/usr/bin/env python3
"""
The termination of the two pairs the FPGA receives from the Kria moved to the receiver
(11 Nov 2026, 8-layer board; docs/SIGNAL_INTEGRITY.md §3):

LINK_TX_D0 and LINK_TX_CLK are AC-coupled (C107-C110) and were terminated by 2 x 49.9 ohm to
+1V2 per pair (R101-R104) next to the capacitors, at the connector: 45 mm from the receiver, so
the line was terminated at its source end and open at the FPGA's balls. Now:

  * R105, R106 (CONTROL): 100 ohm across each pair, on the bottom face on the pair's two ball vias,
    as R1101-R1114 are for the ADCs' pairs;
  * R101-R104 (IAS_LINK): 49.9 -> 10k, so they only set the common mode at +1V2 (an AC-coupled
    LVDS input needs its bias restored; HR banks have none for this case), 10k against the 100 ohm
    termination loads the pair by 1 %.

Text edit with _work/add_esd.py's helpers. Run once; it refuses to run twice. Then ERC.

Usage:  py _work/link_tx_termination.py
"""
import os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import add_esd as E                                  # noqa: E402

NEW = [("R105", "LINK_TX_D0"), ("R106", "LINK_TX_CLK")]
X0, Y = 152.4, 508.0                                  # beside C1184-C1187 (add_vccint_bottom_caps.py)


def main():
    c = E.Sheet("rev03/CONTROL.kicad_sch")
    if '"R105"' in c.t: sys.exit("already added")
    for k, (ref, pair) in enumerate(NEW):
        x = X0 + 12.7 * k
        c.new.append(E.instance("Device:R", ref, "100", "Resistor_SMD:R_0402_1005Metric", x, Y, 0,
                                ["1", "2"], c.ipath, c.project))
        c.new.append(E.label(pair + "_P", x, Y - 3.81, 0))        # Device:R pin 1 at the top
        c.new.append(E.label(pair + "_N", x, Y + 3.81, 0))
    c.new.append('\t(text "LINK_TX termination at the receiver (bottom face, on the ball vias)"\n\t\t(exclude_from_sim no)\n'
                 f'\t\t(at {X0 - 2.54:.2f} {Y - 10.16:.2f} 0)\n\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1.27 1.27)\n'
                 f'\t\t\t)\n\t\t\t(justify left)\n\t\t)\n\t\t(uuid "{E.U()}")\n\t)')
    c.save()
    s = E.Sheet("rev03/IAS_LINK.kicad_sch")
    n = 0
    for ref in ("R101", "R102", "R103", "R104"):
        i = s.t.find(f'(property "Reference" "{ref}"'); st = s.t.rfind("\n\t(symbol", 0, i); en = s.t.find("\n\t)", i)
        b = s.t[st:en]
        b2 = re.sub(r'\(property "Value" "49\.9"', '(property "Value" "10k"', b, count=1)
        if b2 != b: n += 1
        s.t = s.t[:st] + b2 + s.t[en:]
    s.save()
    print("added: R105, R106 (CONTROL); R101-R104 49.9 -> 10k:", n)


if __name__ == "__main__":
    main()
