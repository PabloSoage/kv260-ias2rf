#!/usr/bin/env python3
"""
A 3-D model of the HRO TYPE-C-31-E-17 vertical USB-C receptacle (J1501), written as VRML 2.0 from the maker's
drawing [V, read 18 Nov 2026]; neither EasyEDA nor KiCad has one. Our own drawing of it, so it lives in the
repository (mech/models3d), unlike the EasyEDA models in _work/mech/cache.

Shapes, in the footprint's frame (x along the receptacle, y across, z up from the board, mm):
  * the plastic housing, 9.70 x 4.59 mm, 0 to 1.20 mm, black;
  * the stainless front shell, a stadium 8.94 x 3.16 mm outside (0.30 mm wall round the 8.34 x 2.56 mm opening),
    1.20 to 6.00 mm, steel grey;
  * the sealing ring, a stadium 10.38 x 4.59 mm, 4.40 to 5.40 mm, dark rubber;
  * the contact tongue, 6.69 x 0.70 mm, 1.20 to 5.40 mm, black, with the opening's floor at 1.25 mm;
  * the 16 contact tails and four shell tabs as thin gold and steel plates on the pads.
Colours follow the render rules (docs/3D_MODELS.md): metal looks like metal, nothing is pure white.
VRML units are 0.1 inch (KiCad's convention), hence the 1/2.54 scale.

Usage:  py _work/mech/usbc_hro_model.py
"""
import math
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "mech", "models3d", "USB_C_HRO_TYPE-C-31-E-17.wrl")
S = 1 / 2.54

BLACK = (0.08, 0.08, 0.09, 0.35)
STEEL = (0.62, 0.63, 0.65, 0.85)
RUBBER = (0.16, 0.16, 0.17, 0.10)
GOLD = (0.83, 0.66, 0.30, 0.80)


def stadium(w, h, n=12):
    """Outline of a w x h stadium (semicircular ends), counter-clockwise."""
    r = h / 2
    cx = w / 2 - r
    pts = []
    for k in range(n + 1):
        a = -math.pi / 2 + math.pi * k / n
        pts.append((cx + r * math.cos(a), r * math.sin(a)))
    for k in range(n + 1):
        a = math.pi / 2 + math.pi * k / n
        pts.append((-cx + r * math.cos(a), r * math.sin(a)))
    return pts


def box(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def prism(outline, z0, z1, colour, hole=None):
    """A vertical prism over the outline; with a hole outline (same point count) the top is a ring."""
    n = len(outline)
    pts = [(x, y, z0) for x, y in outline] + [(x, y, z1) for x, y in outline]
    faces = []
    for i in range(n):
        j = (i + 1) % n
        faces.append([i, j, n + j, n + i])
    faces.append(list(range(n - 1, -1, -1)))
    if hole is None:
        faces.append(list(range(n, 2 * n)))
    else:
        base = len(pts)
        pts += [(x, y, z1) for x, y in hole]
        for i in range(n):
            j = (i + 1) % n
            faces.append([n + i, n + j, base + j, base + i])
        base2 = len(pts)                         # the opening's inner wall, down to the floor
        pts += [(x, y, z0 + 0.05) for x, y in hole]
        for i in range(n):
            j = (i + 1) % n
            faces.append([base + j, base + i, base2 + i, base2 + j])
    return shape(pts, faces, colour)


def shape(pts, faces, colour):
    r, g, b, shin = colour
    coords = ", ".join(f"{x * S:.5f} {y * S:.5f} {z * S:.5f}" for x, y, z in ((p[0], -p[1], p[2]) for p in pts))
    idx = ", ".join(", ".join(str(i) for i in f) + ", -1" for f in faces)
    return (f"Shape {{ appearance Appearance {{ material Material {{ diffuseColor {r} {g} {b} "
            f"specularColor {0.3 + shin * 0.5:.2f} {0.3 + shin * 0.5:.2f} {0.3 + shin * 0.5:.2f} "
            f"shininess {shin} }} }}\n"
            f"  geometry IndexedFaceSet {{ solid FALSE creaseAngle 0.5 coord Coordinate {{ point [ {coords} ] }}\n"
            f"  coordIndex [ {idx} ] }} }}\n")


def main():
    parts = [prism(box(-4.85, -2.295, 4.85, 2.295), 0.0, 1.20, BLACK),
             prism(stadium(8.94, 3.16), 1.20, 6.00, STEEL, hole=stadium(8.34, 2.56)),
             prism(stadium(10.38, 4.59), 4.40, 5.40, RUBBER, hole=stadium(8.98, 3.20)),
             prism(box(-3.345, -0.35, 3.345, 0.35), 1.20, 5.40, BLACK)]
    xs = (-2.75, -1.25, -0.75, -0.25, 0.25, 0.75, 1.25, 2.75)
    for x in xs:
        for y in (-0.81, 0.81):
            parts.append(prism(box(x - 0.11, y - 0.30, x + 0.11, y + 0.30), 0.0, 0.10, GOLD))
    for x in (-2.29, 2.29):
        for y in (-2.08, 2.08):
            parts.append(prism(box(x - 0.25, y - 0.45, x + 0.25, y + 0.45), 0.0, 0.12, STEEL))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write("#VRML V2.0 utf8\n# HRO TYPE-C-31-E-17, drawn from the maker's drawing by _work/mech/usbc_hro_model.py\n")
        f.write("Transform { children [\n" + "".join(parts) + "] }\n")
    print("wrote", os.path.relpath(OUT, ROOT))


if __name__ == "__main__":
    main()
