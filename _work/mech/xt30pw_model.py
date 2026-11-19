#!/usr/bin/env python3
"""Stand-in 3-D STEP model of the AMASS XT30PW-M horizontal PCB plug (PSU board J1).

KiCad's footprint AMASS_XT30PW-M_1x02_P2.50mm_Horizontal names a model its library does not ship. This one follows
that footprint's F.Fab outline: the housing spans x -7.45..2.45 mm and y -13.1..-4.1 mm (KiCad Y down), the two
locating pegs at (-8, -10) and (3, -10), the contacts at (0, 0) and (-5, 0). The housing height (5.2 mm) is the
XT30's nominal thickness [E]; it is a stand-in for renders and clearance checks, not a mechanical drawing.

Colours follow the project's render rules: yellow nylon, metallic contacts, nothing white.

Usage (WSL CadQuery/OCP environment):
    /home/varuna/micromamba/envs/cq/bin/python _work/mech/xt30pw_model.py
"""
import os

import cadquery as cq

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "mech", "models3d", "AMASS_XT30PW-M_1x02_P2.50mm_Horizontal.step")

NYLON = cq.Color(0.80, 0.62, 0.10)
METAL = cq.Color(0.72, 0.58, 0.32)      # gold-plated brass, darkened so the raytracer does not burn it out

H = 5.2          # housing height [E]
Z0 = 0.4         # standoff above the board


def housing():
    # footprint (x, y) -> STEP (x, -y)
    body = (cq.Workplane("XY").workplane(offset=Z0).center(-2.5, 8.6).rect(9.9, 9.0).extrude(H)
            .edges("|Y").fillet(0.6))
    # the mating face (far from the pins) with two contact sockets, one with the XT30's chamfered corners
    for x in (0.0, -5.0):
        sock = cq.Workplane("XZ", origin=(0, 13.2, 0)).center(x, Z0 + H / 2).rect(3.6, 3.4).extrude(4.0)
        body = body.cut(sock)
    pegs = None
    for x in (-8.0, 3.0):
        p = cq.Workplane("XY").workplane(offset=Z0).center(x, 10.0).rect(0.7, 2.0).extrude(H * 0.6)
        pegs = p if pegs is None else pegs.union(p)
    return body.union(pegs)


def contacts():
    out = None
    for x in (0.0, -5.0):
        # the bent pin: down into the board at y 0, then back along the board into the housing
        pin = cq.Workplane("XY").workplane(offset=-3.0).center(x, 0).circle(0.75).extrude(3.0 + Z0 + H / 2)
        run = cq.Workplane("XZ", origin=(0, 0, 0)).center(x, Z0 + H / 2).circle(0.75).extrude(-8.0)
        tube = (cq.Workplane("XZ", origin=(0, 12.6, 0)).center(x, Z0 + H / 2).circle(1.25).circle(1.0)
                .extrude(3.0))
        c = pin.union(run).union(tube)
        out = c if out is None else out.union(c)
    return out


def build():
    assy = cq.Assembly(name="AMASS_XT30PW-M")
    assy.add(housing(), name="housing", color=NYLON)
    assy.add(contacts(), name="contacts", color=METAL)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    assy.save(OUT, exportType="STEP")
    bb = assy.toCompound().BoundingBox()
    print(f"wrote {OUT}: X {bb.xmin:.2f}..{bb.xmax:.2f}, Y {bb.ymin:.2f}..{bb.ymax:.2f}, Z {bb.zmin:.2f}..{bb.zmax:.2f}")


if __name__ == "__main__":
    build()
