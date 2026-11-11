"""Impedances on JLCPCB's 8-layer stack JLC08161H-2116A, with the solver of field_solver.py.

L1 35 um | 2116 0.1164 er 4.16 | L2 | core 0.25 er 4.23 | L3 | 2 x 2116 0.2328 er 4.16 | L4 |
core 0.25 | L5 | 2 x 2116 0.2328 | L6 | core 0.25 | L7 | 2116 0.1164 | L8 35 um
(JLCPCB's impedance-template API, 11 Nov 2026). L1/L8 over L2/L7 are as on the 6-layer
JLC06161H-2116A. L3 and L6 are mirror images: a track on a core's inner face, embedded in the
0.2328 mm prepreg, between two planes. JLC08161H-2116B (the 6-layer stack with two layers added
round the middle core) was looked at first and dropped: its L3/L6 sit 0.13 and 0.109 mm from
their planes, so 50 ohm is 85 um wide and a 100 ohm pair 70-77 um, under JLCPCB's 90 um minimum.

Usage:  py _work/field_solver8.py
"""
import sys
import field_solver as F

PP_IN, CORE, ER_CORE = 0.2328, 0.25, 4.23


def stripline_in(w, s=None):
    """L3 (or L6 mirrored): plane, 0.25 core, track (in the prepreg), 0.2328 prepreg, plane."""
    def build(odd):
        g = F.Grid(F.BOX_W, PP_IN + CORE)
        g.layer(0, PP_IN, F.ER_2116)
        g.layer(PP_IN, PP_IN + CORE, ER_CORE)
        xs = [(F.BOX_W - w) / 2] if not odd else [F.BOX_W / 2 - s / 2 - w, F.BOX_W / 2 + s / 2]
        for k, x in enumerate(xs):
            g.conductor(x, x + w, PP_IN - F.T_IN, PP_IN, 1.0 if k == 0 else -1.0)
        return g
    return build


def main():
    F.check()
    print()
    print("JLC08161H-2116A, L3 / L6 stripline")
    w, z = F.solve_width(lambda w: F.impedance(stripline_in(w), False), 50.0, lo=0.08, hi=0.4)
    print(f"  50 ohm single: W = {w * 1000:.0f} um -> {z:.1f} ohm")
    for w in (0.1, 0.117, 0.15, 0.175, 0.183, 0.2):
        print(f"  W {w * 1000:.0f} um single: {F.impedance(stripline_in(w), False):.1f} ohm")
    for s in (0.127, 0.15, 0.2, 0.25):
        w, z = F.solve_width(lambda w, s=s: F.impedance(stripline_in(w, s), True), 100.0, lo=0.06, hi=0.3)
        print(f"  100 ohm pair, S = {s * 1000:.0f} um: W = {w * 1000:.0f} um -> {z:.1f} ohm")
    for w, s in ((0.1, 0.1), (0.1, 0.127), (0.127, 0.127), (0.13, 0.15), (0.14, 0.2)):
        print(f"  pair W {w * 1000:.0f} S {s * 1000:.0f}: {F.impedance(stripline_in(w, s), True):.1f} ohm")
    return 0


if __name__ == "__main__":
    sys.exit(main())
