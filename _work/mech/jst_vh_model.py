#!/usr/bin/env python3
"""Parametric 3-D STEP model of the JST B2PS-VH 2-pin 3.96 mm right-angle header (J1004).

Aligned to KiCad footprint Connector_JST:JST_VH_B2PS-VH_1x02_P3.96mm_Horizontal:
  - Pin 1 through-hole post at STEP (0.00, 0.00), Pin 2 at (+3.96, 0.00) mm
  - Mating housing extends toward STEP -Y (KiCad +Y_2D) from -4.0 mm to -13.4 mm
  - Right-angle 1.14 x 1.14 mm square tin-plated brass posts extend to STEP Y = -14.9 mm
  - Housing width 7.86 mm (X = -1.95..+5.91) at rear flange, height Z = 0.0..8.5 mm above PCB top face

Colours follow the project render rules (warm dark ivory PA66 insulator, satin tin-brass posts;
never pure white).

Usage (WSL CadQuery/OCP environment):
    /home/varuna/micromamba/envs/cq/bin/python _work/mech/jst_vh_model.py
"""
import os

import cadquery as cq

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "mech", "models3d", "JST_VH_B2PS-VH_1x02_P3.96mm_Horizontal.step")

PA66_COLOR = cq.Color(0.58, 0.54, 0.47)
PIN_COLOR = cq.Color(0.68, 0.69, 0.70)


def make_housing():
    """Create PA66 warm-ivory right-angle friction-lock JST VH 2-pin housing in STEP mm."""
    # Rear retention block / flange across full 7.86 mm width (X in [-1.95, 5.91], Y in [-7.2, -4.0])
    rear = (
        cq.Workplane("XY")
        .workplane(offset=0.0)
        .center(1.98, -5.60)
        .rect(7.86, 3.20)
        .extrude(8.50)
    )
    # Forward mating base floor under the contacts (X in [-0.90, 4.86], Y in [-13.4, -7.2], Z in [0.0, 2.0])
    base = (
        cq.Workplane("XY")
        .workplane(offset=0.0)
        .center(1.98, -10.30)
        .rect(5.76, 6.20)
        .extrude(2.00)
    )
    # Top friction-lock shroud hood (X in [-0.90, 4.86], Y in [-13.4, -7.2], Z in [6.8, 8.5])
    hood = (
        cq.Workplane("XY")
        .workplane(offset=6.80)
        .center(1.98, -10.30)
        .rect(5.76, 6.20)
        .extrude(1.70)
    )
    # Front locking catch lip under hood edge (Y in [-13.4, -11.9], Z in [6.0, 6.8])
    latch = (
        cq.Workplane("XY")
        .workplane(offset=6.00)
        .center(1.98, -12.65)
        .rect(5.00, 1.50)
        .extrude(0.80)
    )
    # Small side guide rails along mating entrance (Y in [-9.8, -7.2], Z in [2.0, 6.8])
    left_rib = (
        cq.Workplane("XY")
        .workplane(offset=2.00)
        .center(-0.58, -8.50)
        .rect(0.64, 2.60)
        .extrude(4.80)
    )
    right_rib = (
        cq.Workplane("XY")
        .workplane(offset=2.00)
        .center(4.54, -8.50)
        .rect(0.64, 2.60)
        .extrude(4.80)
    )
    body = rear.union(base).union(hood).union(latch).union(left_rib).union(right_rib)
    body = body.edges("|Y").chamfer(0.12)
    return body


def make_pins():
    """Create the two 1.14 mm square L-bent tin-plated brass contact posts at X = 0 and X = 3.96."""
    pw = 1.14
    z_bot = -3.40
    z_axis = 4.25
    y_tip = -14.90
    pins = None
    for px in (0.0, 3.96):
        # Vertical through-hole tail up through elbow top
        vert = (
            cq.Workplane("XY")
            .workplane(offset=z_bot)
            .center(px, 0.0)
            .rect(pw, pw)
            .extrude(z_axis + pw * 0.5 - z_bot)
        )
        # Horizontal mating pin extending forward toward Y = -14.90 mm
        hlen = -y_tip + pw * 0.5
        horiz = (
            cq.Workplane("XY")
            .workplane(offset=z_axis - pw * 0.5)
            .center(px, (y_tip + pw * 0.5) * 0.5)
            .rect(pw, hlen)
            .extrude(pw)
        )
        p = vert.union(horiz)
        pins = p if pins is None else pins.union(p)
    return pins


def build():
    housing = make_housing()
    pins = make_pins()

    assy = cq.Assembly(name="JST_VH_B2PS-VH_1x02_P3.96mm_Horizontal")
    assy.add(housing, name="pa66_housing", color=PA66_COLOR)
    assy.add(pins, name="brass_posts", color=PIN_COLOR)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    assy.save(OUT, exportType="STEP")

    bb = assy.toCompound().BoundingBox()
    sz = os.path.getsize(OUT)
    print(f"Wrote {OUT} ({sz} B, {sz/1024:.1f} KB)")
    print(
        f"Bounding box mm: X=[{bb.xmin:.3f}, {bb.xmax:.3f}], "
        f"Y=[{bb.ymin:.3f}, {bb.ymax:.3f}], Z=[{bb.zmin:.3f}, {bb.zmax:.3f}]"
    )
    assert abs(bb.zmax - 8.50) < 0.05, f"Expected height ~8.5 mm, got {bb.zmax}"


if __name__ == "__main__":
    build()
