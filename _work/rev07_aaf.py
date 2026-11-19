#!/usr/bin/env python3
"""
Rev07: an anti-alias low-pass on IF_RX_C (J951 -> AD9253 channel B), SIGNAL_INTEGRITY section 9.9.

The AD9253 samples at 62.5 MSPS (50 with the 400 MHz master). Without a filter, everything up to several hundred
MHz folds into HF at full strength: FM broadcast lands on 17-31 MHz. J951 is also the input with no RF switch in
its path (the M3SWA2 is not specified below 10 MHz), so it becomes the board's HF input, filtered on the board.
Channel A (J911 through SW1) stays wideband: its RF2 throw carries the radar IF to the same ADC.

7th-order elliptic ladder between 50 ohm at both ends, values from _work/sim/aaf_lpf.py (E24 C0G; 0805 wirewound
inductors, Q about 40 at 30 MHz: LQW2BASR22J, SDWL2012CR27G, LQW2BASR33G; the 0603 LQW18AN of the DAC filters have
3.4 ohm and would cost about 1 dB more):

  IF_RX_C_AAF (C951) --+-- L951 || C954 --+-- L952 || C956 --+-- L953 || C958 --+-- IF_RX_C
                       |   220n    47p    |   270n    39p    |   330n    10p    |
                     C953 82p           C955 150p          C957 160p          C959 100p     (to GND)

On the ROUTING sheet: the wire from C951 to the IF_RX_C hierarchical label is removed; C951's end becomes the
local net IF_RX_C_AAF, the ladder is drawn with wires in the free area under the sheet's notes, and the
hierarchical label moves to the filter's output. Text edit with add_ethernet.py's helpers. Refuses to run twice.

Usage:  py _work/rev07_aaf.py
"""
import os, re, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "_work"))
import add_ethernet as AE                                          # noqa: E402
from add_esd import label                                          # noqa: E402
from rev06_eth import highest                                      # noqa: E402

AE.SHEET = os.path.join(ROOT, "sheets", "ROUTING.kicad_sch")
C0402, L0805 = "Capacitor_SMD:C_0402_1005Metric", "Inductor_SMD:L_0805_2012Metric"
IN, N1, N2, OUT = "IF_RX_C_AAF", "AAF_C_N1", "AAF_C_N2", "IF_RX_C"
# ref -> (lib, value, footprint, description)
PARTS = {
    "C953": ("Device:C", "82p", C0402, "anti-alias LPF on IF_RX_C, shunt 1 (C0G)"),
    "L951": ("Device:L", "220n", L0805, "anti-alias LPF, series 1 (LQW2BASR22J00L, 5 %)"),
    "C954": ("Device:C", "47p", C0402, "anti-alias LPF, across L951: zero at 49 MHz (C0G)"),
    "C955": ("Device:C", "150p", C0402, "anti-alias LPF, shunt 2 (C0G)"),
    "L952": ("Device:L", "270n", L0805, "anti-alias LPF, series 2 (SDWL2012CR27GSTF, 2 %)"),
    "C956": ("Device:C", "39p", C0402, "anti-alias LPF, across L952: zero at 49 MHz (C0G)"),
    "C957": ("Device:C", "160p", C0402, "anti-alias LPF, shunt 3 (C0G)"),
    "L953": ("Device:L", "330n", L0805, "anti-alias LPF, series 3 (LQW2BASR33G00L, 2 %)"),
    "C958": ("Device:C", "10p", C0402, "anti-alias LPF, across L953: zero at 88 MHz (C0G)"),
    "C959": ("Device:C", "100p", C0402, "anti-alias LPF, shunt 4 (C0G)"),
}
SHUNT = ("C953", "C955", "C957", "C959")
SERIES = (("L951", "C954"), ("L952", "C956"), ("L953", "C958"))
# the line at Y; input label at X_IN, the four nodes, the hierarchical label at X_OUT (all on the 1.27 mm grid)
Y, X_IN, NODES, X_OUT = 190.5, 297.18, (304.8, 325.12, 345.44, 365.76), 373.38
TAB, NL = "\t", "\n"


def wire(x1, y1, x2, y2):
    return (TAB + "(wire" + NL + TAB * 2 + "(pts" + NL + TAB * 3 + f"(xy {x1:.2f} {y1:.2f}) (xy {x2:.2f} {y2:.2f})" + NL
            + TAB * 2 + ")" + NL + TAB * 2 + "(stroke" + NL + TAB * 3 + "(width 0)" + NL + TAB * 3 + "(type default)" + NL
            + TAB * 2 + ")" + NL + TAB * 2 + f'(uuid "{AE.U()}")' + NL + TAB + ")")


def junction(x, y):
    return (TAB + "(junction" + NL + TAB * 2 + f"(at {x:.2f} {y:.2f})" + NL + TAB * 2 + "(diameter 0)" + NL
            + TAB * 2 + "(color 0 0 0 0)" + NL + TAB * 2 + f'(uuid "{AE.U()}")' + NL + TAB + ")")


def text(s_, x, y):
    return (TAB + f'(text "{s_}"' + NL + TAB * 2 + "(exclude_from_sim no)" + NL + TAB * 2 + f"(at {x:.2f} {y:.2f} 0)" + NL
            + TAB * 2 + "(effects" + NL + TAB * 3 + "(font" + NL + TAB * 4 + "(size 1.27 1.27)" + NL + TAB * 3 + ")" + NL
            + TAB * 3 + "(justify left)" + NL + TAB * 2 + ")" + NL + TAB * 2 + f'(uuid "{AE.U()}")' + NL + TAB + ")")


def place(s, ref, x, y, rot):
    """A two-pin part at (x, y): rot 0 is vertical with pin 1 on top, rot 90 horizontal with pin 1 on the left.
    Returns pin -> (x, y)."""
    lib, val, fp, desc = PARTS[ref]
    s.inst(lib, ref, val, fp, x, y, desc)
    if rot:
        b = s.new[-1]
        b = b.replace(f"(at {x:.2f} {y:.2f} 0)", f"(at {x:.2f} {y:.2f} {rot})", 1)
        # reference above the horizontal part, value below it
        b = b.replace(f'"{ref}"{NL}{TAB * 3}(at {x + 2.54:.2f} {y - 1.27:.2f} 0)', f'"{ref}"{NL}{TAB * 3}(at {x:.2f} {y - 2.54:.2f} 90)', 1)
        b = b.replace(f'"{val}"{NL}{TAB * 3}(at {x + 2.54:.2f} {y + 1.27:.2f} 0)', f'"{val}"{NL}{TAB * 3}(at {x:.2f} {y + 2.54:.2f} 90)', 1)
        s.new[-1] = b
        return {"1": (round(x - 3.81, 2), y), "2": (round(x + 3.81, 2), y)}
    # vertical part: reference and value clear of the capacitor's plates
    s.new[-1] = s.new[-1].replace(f"(at {x + 2.54:.2f} {y - 1.27:.2f} 0)", f"(at {x + 3.81:.2f} {y - 1.27:.2f} 0)", 1) \
                         .replace(f"(at {x + 2.54:.2f} {y + 1.27:.2f} 0)", f"(at {x + 3.81:.2f} {y + 1.27:.2f} 0)", 1)
    return {"1": (x, round(y - 3.81, 2)), "2": (x, round(y + 3.81, 2))}


def main():
    s = AE.Sheet()
    if '"C953"' in s.t: sys.exit("already applied")
    AE.PWR[0] = highest("#PWR")
    # 1. the wire from the hierarchical label to C951 goes; C951's end becomes IF_RX_C_AAF
    m = re.search(r"\n\t\(wire\s*\(pts\s*\(xy 304\.8 91\.44\)\s*\(xy 313\.69 91\.44\)\s*\)[\s\S]*?\n\t\)", s.t)
    assert m, "wire C951 -> IF_RX_C not found"
    s.t = s.t[:m.start()] + s.t[m.end():]
    s.new.append(label(IN, 313.69, 91.44, 180))
    # 2. the ladder
    s.new.append(text("Anti-alias low-pass on IF_RX_C (Rev07): 7th-order elliptic, 50 ohm, flat to 30 MHz,", X_IN, Y - 22.86))
    s.new.append(text("60 dB or more from 50 MHz. ROUTING_SPEC 1.1, SIGNAL_INTEGRITY 9.9.", X_IN, Y - 20.32))
    s.new.append(label(IN, X_IN, Y, 180))
    s.new.append(wire(X_IN, Y, NODES[0], Y))
    for k, ref in enumerate(SHUNT):
        p = place(s, ref, NODES[k], Y + 3.81, 0)
        s.connect((p["2"][0], p["2"][1], 90), "GND")
        s.new.append(junction(NODES[k], Y))
    for k, (lref, cref) in enumerate(SERIES):
        xm = (NODES[k] + NODES[k + 1]) / 2
        pl = place(s, lref, xm, Y, 90)
        pc = place(s, cref, xm, Y - 7.62, 90)
        s.new.append(wire(NODES[k], Y, pl["1"][0], Y))
        s.new.append(wire(pl["2"][0], Y, NODES[k + 1], Y))
        s.new.append(wire(pc["1"][0], pc["1"][1], pl["1"][0], Y))
        s.new.append(wire(pc["2"][0], pc["2"][1], pl["2"][0], Y))
        s.new.append(junction(pl["1"][0], Y)); s.new.append(junction(pl["2"][0], Y))
    s.new.append(wire(NODES[3], Y, X_OUT, Y))
    s.new.append(label(N1, NODES[1], Y, 90)); s.new.append(label(N2, NODES[2], Y, 90))
    # 3. the hierarchical label moves to the filter's output
    h = re.search(r'\(hierarchical_label "IF_RX_C"\s*\(shape output\)\s*\(at 304\.8 91\.44 180\)\s*\(effects\s*\(font\s*'
                  r'\(size 1\.27 1\.27\)\s*\)\s*\(justify right\)', s.t)
    assert h, "hierarchical label IF_RX_C not found"
    s.t = (s.t[:h.start()] + f'(hierarchical_label "IF_RX_C"{NL}{TAB * 2}(shape output){NL}{TAB * 2}(at {X_OUT:.2f} {Y:.2f} 0)'
           f"{NL}{TAB * 2}(effects{NL}{TAB * 3}(font{NL}{TAB * 4}(size 1.27 1.27){NL}{TAB * 3}){NL}{TAB * 3}(justify left)"
           + s.t[h.end():])
    s.save()
    print("anti-alias filter drawn on ROUTING; #PWR up to", AE.PWR[0])


if __name__ == "__main__":
    main()
