#!/usr/bin/env python3
"""Parametric 3-D STEP model of the 9070-series SMD common-mode power choke (L1004).

Geometry matches the Coilmaster SMM9070-501 / ZE ZEGMCM9070-501T package:
  - overall body envelope: 9.0 x 7.0 x 4.55 mm (4.8 mm max height)
  - four metallic tinned terminals on (+/-4.25, +/-1.75) mm pad centres (2.5 x 1.5 mm pads)
  - origin at footprint centre, terminal undersides flush at Z = 0.00 mm (PCB top face)
  - Pin-1 marker on the top plate at (-3.3, +2.3) mm in STEP XY (matches KiCad pad 1 at (-4.25, -1.75))

Materials follow the project colour rules (dark charcoal ferrite, copper-amber winding,
satin metallic nickel/tin terminals, warm grey pin-1 dot; nothing pure white).

Usage (WSL CadQuery/OCP environment):
    /home/varuna/micromamba/envs/cq/bin/python _work/mech/cmc_9070_model.py
"""
import os
import sys

import cadquery as cq

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "mech", "models3d", "CMC_9070_SMD-4P_9.0x7.0mm.step")

FERRITE_COLOR = cq.Color(0.14, 0.14, 0.15)
COPPER_COLOR = cq.Color(0.62, 0.30, 0.12)
METAL_COLOR = cq.Color(0.48, 0.49, 0.51)
MARK_COLOR = cq.Color(0.46, 0.44, 0.41)


def make_winding():
    """Create rounded bifilar enamelled copper winding mass with stacked coil ribs."""
    parts = []
    # Main rounded rectangular winding block around core post
    base = (
        cq.Workplane("XY")
        .workplane(offset=1.18)
        .rect(7.6, 5.6)
        .extrude(2.44)
        .edges("|Z")
        .fillet(1.1)
    )
    parts.append(base)
    # Subtle bifilar wire ribs along X/Y perimeter for realistic texture in close-up renders
    for k in range(5):
        z0 = 1.30 + k * 0.46
        rib = (
            cq.Workplane("XY")
            .workplane(offset=z0)
            .rect(7.85, 5.85)
            .extrude(0.32)
            .edges("|Z")
            .fillet(1.18)
            .edges("not |Z")
            .fillet(0.12)
        )
        parts.append(rib)
    winding = parts[0]
    for p in parts[1:]:
        winding = winding.union(p)
    return winding


def make_ferrite():
    """Create lower flange, central core post, and chamfered top ferrite plate."""
    # Lower ferrite base collar (notched/narrowed inside terminal wraps)
    base = (
        cq.Workplane("XY")
        .workplane(offset=0.25)
        .rect(8.4, 6.6)
        .extrude(0.90)
        .edges("|Z")
        .fillet(0.40)
    )
    # Central core post
    post = (
        cq.Workplane("XY")
        .workplane(offset=1.15)
        .rect(6.0, 4.4)
        .extrude(2.50)
        .edges("|Z")
        .fillet(0.50)
    )
    # Top ferrite plate (9.0 x 7.0 mm, z = 3.65..4.55 mm <= 4.8 mm max)
    top = (
        cq.Workplane("XY")
        .workplane(offset=3.65)
        .rect(9.0, 7.0)
        .extrude(0.90)
        .edges("|Z")
        .fillet(0.35)
        .edges(">Z")
        .chamfer(0.20)
    )
    # Recessed pocket for pin-1 dot on top face (at (-3.3, +2.3) in STEP XY -> pad 1 corner)
    ferrite = base.union(post).union(top)
    pocket = (
        cq.Workplane("XY")
        .workplane(offset=4.50)
        .center(-3.3, 2.3)
        .circle(0.50)
        .extrude(0.10)
    )
    ferrite = ferrite.cut(pocket)
    return ferrite


def make_terminals():
    """Create 4 tinned SMD solder feet and end wraps on (+/-4.25, +/-1.75) pads."""
    pads = [(-1, -1), (-1, 1), (1, -1), (1, 1)]
    terms = None
    for sx, sy in pads:
        yc = sy * 1.75
        # Bottom solder foot seated flush at Z = 0.00..0.35 mm over pad centre X = +-4.25 ([-4.90, -3.15])
        foot_cx = sx * 4.025
        foot = (
            cq.Workplane("XY")
            .workplane(offset=0.0)
            .center(foot_cx, yc)
            .rect(1.75, 1.50)
            .extrude(0.35)
            .edges("|Z")
            .fillet(0.15)
        )
        # Vertical end wrap hugging the 8.4 mm lower ferrite flange side wall (X in [4.15, 4.50], no gap)
        wrap_cx = sx * 4.325
        wrap = (
            cq.Workplane("XY")
            .workplane(offset=0.0)
            .center(wrap_cx, yc)
            .rect(0.35, 1.50)
            .extrude(1.16)
            .edges("|Z")
            .fillet(0.08)
        )
        t = foot.union(wrap)
        terms = t if terms is None else terms.union(t)
    return terms


def make_pin1_dot():
    """Pin-1 warm grey polarity indicator dot seated at Z = 4.50..4.58 mm."""
    return (
        cq.Workplane("XY")
        .workplane(offset=4.50)
        .center(-3.3, 2.3)
        .circle(0.45)
        .extrude(0.08)
    )


def build():
    ferrite = make_ferrite()
    winding = make_winding()
    terminals = make_terminals()
    dot = make_pin1_dot()

    assy = cq.Assembly(name="CMC_9070_SMD-4P_9.0x7.0mm")
    assy.add(ferrite, name="ferrite_core", color=FERRITE_COLOR)
    assy.add(winding, name="copper_winding", color=COPPER_COLOR)
    assy.add(terminals, name="tinned_terminals", color=METAL_COLOR)
    assy.add(dot, name="pin1_marker", color=MARK_COLOR)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    assy.save(OUT, exportType="STEP")

    bb = assy.toCompound().BoundingBox()
    sz = os.path.getsize(OUT)
    print(f"Wrote {OUT} ({sz} B, {sz/1024:.1f} KB)")
    print(f"Bounding box mm: X=[{bb.xmin:.3f}, {bb.xmax:.3f}], Y=[{bb.ymin:.3f}, {bb.ymax:.3f}], Z=[{bb.zmin:.3f}, {bb.zmax:.3f}]")
    assert abs(bb.zmin) < 1e-4, f"Expected zmin=0, got {bb.zmin}"
    assert bb.zmax <= 4.80 + 1e-4, f"Expected zmax<=4.80, got {bb.zmax}"


if __name__ == "__main__":
    build()
