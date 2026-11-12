"""Impedances on JLCPCB's 8-layer stack JLC08161H-2116C, with the solver of field_solver.py.

L1 35 um | 2116 0.1194 er 4.29 | L2 | core 0.13 er 4.17 | L3 | 2116+1080+2116 0.3658 er 4.29 | L4 |
core 0.13 | L5 | 0.3658 | L6 | core 0.13 | L7 | 2116 0.1194 | L8 35 um
(JLCPCB's impedance-template API, 11 Nov 2026). L3 is etched on the L2/L3 core's lower face, 0.13 mm
under L2 (GND) and 0.366 mm over L4 (PWR); L6 mirrors it over L7 (GND), under L5 (GND). L4/L5 are a
0.13 mm plane pair, as on the 6-layer board. Outer layers: 183 um is 50.4 ohm here (49.8 on the
6-layer 2116A), so the RF widths stand.

Two other 8-layer stacks were looked at and dropped: 2116A (0.25 mm cores everywhere: the L4/L5 plane
pair twice as far apart, half the plane capacitance) and 2116B (inner lines 0.11-0.13 mm from both
planes: a 100 ohm pair needs 70-77 um legs, under JLCPCB's 90 um).

Usage:  py _work/field_solver8.py
"""
import sys
import field_solver as F

PP_IN, ER_PP, CORE, ER_CORE = 0.3658, 4.29, 0.13, 4.17
PP_OUT, ER_OUT = 0.1194, 4.29


def stripline_in(w, s=None):
    """L3 (or L6 mirrored): plane, 0.13 core, track (in the prepreg), 0.3658 prepreg, plane."""
    def build(odd):
        g = F.Grid(F.BOX_W, PP_IN + CORE)
        g.layer(0, PP_IN, ER_PP)
        g.layer(PP_IN, PP_IN + CORE, ER_CORE)
        xs = [(F.BOX_W - w) / 2] if not odd else [F.BOX_W / 2 - s / 2 - w, F.BOX_W / 2 + s / 2]
        for k, x in enumerate(xs):
            g.conductor(x, x + w, PP_IN - F.T_IN, PP_IN, 1.0 if k == 0 else -1.0)
        return g
    return build


def main():
    F.check()
    print()
    print("JLC08161H-2116C, L3 / L6 stripline")
    w, z = F.solve_width(lambda w: F.impedance(stripline_in(w), False), 50.0, lo=0.05, hi=0.4)
    print(f"  50 ohm single: W = {w * 1000:.0f} um -> {z:.1f} ohm")
    for w, s in ((0.1, 0.15), (0.09, 0.12), (0.09, 0.1), (0.1, 0.1)):
        print(f"  pair W {w * 1000:.0f} S {s * 1000:.0f} um: {F.impedance(stripline_in(w, s), True):.1f} ohm")
    F.PP_2116, F.ER_2116 = PP_OUT, ER_OUT
    print(f"  outer 183 um over L2/L7: {F.impedance(F.microstrip(0.183), False):.1f} ohm")
    return 0


if __name__ == "__main__":
    sys.exit(main())
