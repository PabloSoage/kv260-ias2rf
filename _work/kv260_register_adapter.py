#!/usr/bin/env python3
"""
Register the adapter onto the KV260 3D model and measure where it can grow.

Closes docs/INTERFACE_SPEC.md §5.3 - "which way may the board grow" - which
until now needed a ruler on the assembled hardware.

THE REGISTRATION (three independent sources, each checking the others)
----------------------------------------------------------------------
1. The KV260 STEP assembly gives the two IAS connectors by part name and
   world transform (_work/kv260_step_locate.py): CONN_928X90X80_38P at
   X 21.647, Y 11.986 and Y 62.024 - 50.038 mm apart. The adapter's own
   layout puts its mating pair 50.040 mm apart. That match is what identifies
   the part.
2. The XTP681 layout plot (default.pdf) says which is which. It has no text
   layer, but its silkscreen renders: J7 (IAS0) is the +Y connector, J8
   (IAS1) the -Y one, and both have their pin-1 mark at the -Y end.
3. The adapter's .kicad_pcb gives J8_IAS0 and J8_IAS1 and their pad 1.

From 1 and 3 the transform adapter -> model is a rotation and a translation
(no mirror: both are top views; KiCad's Y axis points down, which is undone
first). Three checks that it is right, none of which was used to build it:
  1. pad 1 of the adapter connector must land on the pin-1 end of the
     carrier connector (source 2). It does, 3.20 mm towards -Y.
  2. the ORIGINAL Allied Vision outline is a shipping product that fits, so
     no carrier part should rise through the adapter's PCB inside it. 10 of
     11 958 cells do: the notch the designers cut for J18 (the IAS0 autofocus
     jumper, a fitted 2-pin header) falls 1.0 mm short of the header body as
     the official model draws it. Real, or a generic header model drawn too
     big - the model cannot say. Rev03 must clear it either way.
  3. the adapter's two 3.4 mm mounting holes must land on the carrier's own
     corner holes if the board is screwed down through them. They land within
     5 um - and holes have nothing to do with the connectors.

THE CLEARANCE MAP
-----------------
The STL is a triangle soup. For every 0.5 mm cell a vertical ray is cast
through its centre; each triangle it crosses is an entry into a solid (facet
facing down) or an exit (facing up). Counting entries and exits gives the
OCCUPIED Z-INTERVALS of that column - which distinguishes a solid block from a
heatsink overhanging empty space, something a plain height map cannot do.

The adapter occupies, in each column it covers,
    Z = STACK .. STACK + PCB          the board itself
    Z = STACK + PCB .. ceiling        room for top-side parts
where STACK is the Hirose mated height and nothing can go on the adapter's
bottom side (0.8 mm is less than any component).

Usage:
    py _work/kv260_register_adapter.py <kv260.stp> <kv260.stl> [--svg out.svg]
"""

import math
import os
import re
import struct
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import kv260_step_locate as sl        # noqa: E402

PCB_FILE = os.path.join(ROOT, "CSI2-KRIA-KV260_Rev01.kicad_pcb")

STACK = 0.80        # [V] BM20B(0.8): 0.8 mm mated height; the STEP part is 0.80 tall
PCB = 1.60          # [V] board thickness in the .kicad_pcb (1.61) and the stackup
TOL = 0.05          # geometric tolerance, mm
CELL = 0.5          # clearance map resolution, mm

# Source 2 - read off the rendered XTP681 plot: J7 is the connector at larger Y.
J7_IS_PLUS_Y = True


# --------------------------------------------------------------------------
# The adapter side
# --------------------------------------------------------------------------

def blocks(text, head):
    """Yield every balanced (head ...) block."""
    i = 0
    while True:
        s = text.find(head, i)
        if s < 0:
            return
        depth, j, in_str = 0, s, False
        while j < len(text):
            c = text[j]
            if in_str:
                if c == "\\":
                    j += 2
                    continue
                if c == '"':
                    in_str = False
            elif c == '"':
                in_str = True
            elif c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        yield text[s:j + 1]
        i = j + 1


def arc_points(p0, pm, p1, n=24):
    """Polyline through three points of a circular arc."""
    (x1, y1), (x2, y2), (x3, y3) = p0, pm, p1
    d = 2 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
    if abs(d) < 1e-12:
        return [p0, p1]
    ux = ((x1**2 + y1**2) * (y2 - y3) + (x2**2 + y2**2) * (y3 - y1) + (x3**2 + y3**2) * (y1 - y2)) / d
    uy = ((x1**2 + y1**2) * (x3 - x2) + (x2**2 + y2**2) * (x1 - x3) + (x3**2 + y3**2) * (x2 - x1)) / d
    r = math.hypot(x1 - ux, y1 - uy)
    a0 = math.atan2(y1 - uy, x1 - ux)
    am = math.atan2(y2 - uy, x2 - ux)
    a1 = math.atan2(y3 - uy, x3 - ux)
    # choose the sweep direction that passes through the mid point
    def norm(a):
        return a % (2 * math.pi)
    ccw = norm(am - a0) < norm(a1 - a0)
    sweep = norm(a1 - a0) if ccw else -norm(a0 - a1)
    return [(ux + r * math.cos(a0 + sweep * k / n), uy + r * math.sin(a0 + sweep * k / n))
            for k in range(n + 1)]


def adapter():
    """Outline segments, and the IAS connectors with their pad 1 (KiCad frame)."""
    text = open(PCB_FILE, encoding="utf-8").read()
    segs = []
    skipped = 0
    for kind in ("(gr_line", "(gr_arc", "(gr_rect", "(gr_poly", "(gr_circle"):
        for b in blocks(text, kind):
            if '(layer "Edge.Cuts")' not in b:
                continue
            pt = lambda k: tuple(map(float, re.search(r"\(" + k + r" ([-\d.]+) ([-\d.]+)\)", b).groups()))
            if kind == "(gr_line":
                segs.append((pt("start"), pt("end")))
            elif kind == "(gr_arc":
                p = arc_points(pt("start"), pt("mid"), pt("end"))
                segs += list(zip(p, p[1:]))
            elif kind == "(gr_rect":
                (x0, y0), (x1, y1) = pt("start"), pt("end")
                c = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
                segs += list(zip(c, c[1:]))
            elif kind == "(gr_poly":
                c = [tuple(map(float, q)) for q in re.findall(r"\(xy ([-\d.]+) ([-\d.]+)\)", b)]
                c.append(c[0])
                segs += list(zip(c, c[1:]))
            else:
                skipped += 1
    if skipped:
        print(f"  WARNING: {skipped} Edge.Cuts circles ignored")
    if "fp_line" in text and re.search(r'\(fp_\w+[^()]*(?:\([^()]*\))*[^()]*\(layer "Edge.Cuts"\)', text):
        print("  WARNING: some Edge.Cuts geometry lives inside footprints and is ignored")

    conns = {}
    for b in blocks(text, "(footprint "):
        ref = re.search(r'\(property "Reference" "([^"]+)"', b)
        if not ref or not re.match(r"J8_IAS[01]$", ref.group(1)):
            continue
        at = re.search(r'\n\t\t\(at ([-\d.]+) ([-\d.]+)(?: ([-\d.]+))?\)', b)
        x, y, rot = float(at.group(1)), float(at.group(2)), float(at.group(3) or 0)
        p1 = re.search(r'\(pad "1" \w+ \w+\s*\(at ([-\d.]+) ([-\d.]+)', b)
        lx, ly = float(p1.group(1)), float(p1.group(2))
        a = math.radians(rot)
        # KiCad: screen rotation, Y down
        px = x + lx * math.cos(a) + ly * math.sin(a)
        py = y - lx * math.sin(a) + ly * math.cos(a)
        conns[ref.group(1)] = ((x, y), (px, py))
    return segs, conns


# --------------------------------------------------------------------------
# The transform
# --------------------------------------------------------------------------

def make_transform(a0, a1, m0, m1):
    """Rigid map sending KiCad points a0 -> m0 and a1 -> m1 (Y flipped first)."""
    A0, A1 = (a0[0], -a0[1]), (a1[0], -a1[1])
    ang = math.atan2(m1[1] - m0[1], m1[0] - m0[0]) - math.atan2(A1[1] - A0[1], A1[0] - A0[0])
    c, s = math.cos(ang), math.sin(ang)

    def f(p):
        u, w = p[0] - A0[0], -p[1] - A0[1]
        return (m0[0] + c * u - s * w, m0[1] + s * u + c * w)

    def g(q):                          # inverse: model -> KiCad
        x, y = q[0] - m0[0], q[1] - m0[1]
        u, w = c * x + s * y, -s * x + c * y
        return (u + A0[0], -(w + A0[1]))
    return f, g, math.degrees(ang)


def carrier_holes(ents, pd_name, pd_reps, children, roots):
    """(X, Y, radius) of every circle of radius >= 1 mm in the carrier outline."""
    stack = [(r, sl.IDENTITY) for r in roots]
    world, pd_outline = None, None
    while stack:
        pd, m = stack.pop()
        for child, t, _ in children.get(pd, []):
            wm = sl.mul(m, t)
            if pd_name.get(child) == "BOARD_OUTLINE":
                world, pd_outline = wm, child
            stack.append((child, wm))
    out, seen, todo = set(), set(), list(pd_reps.get(pd_outline, []))
    while todo:
        i = todo.pop()
        if i in seen or i not in ents:
            continue
        seen.add(i)
        t, a = ents[i]
        if t == "CIRCLE":
            radius = sl.floats(a.split(",")[-1])[0]
            m = sl.axis_matrix(ents, sl.refs(a)[0])
            c = sl.apply(world, [m[0][3], m[1][3], m[2][3]])
            if radius >= 1.0:
                out.add((round(c[0], 3), round(c[1], 3), round(radius, 3)))
            continue
        if t != "CARTESIAN_POINT":
            todo.extend(sl.refs(a))
    return sorted(out)


def adapter_holes():
    """[(reference, (u, v), drill)] for through-holes of 2 mm or more."""
    text = open(PCB_FILE, encoding="utf-8").read()
    out = []
    for b in blocks(text, "(footprint "):
        at = re.search(r'\n\t\t\(at ([-\d.]+) ([-\d.]+)(?: ([-\d.]+))?\)', b)
        if not at:
            continue
        fx, fy = float(at.group(1)), float(at.group(2))
        a = math.radians(float(at.group(3) or 0))
        ref = re.search(r'\(property "Reference" "([^"]+)"', b)
        for p in re.finditer(r'\(pad "[^"]*" (?:np_)?thru_hole \w+\s*\(at ([-\d.]+) ([-\d.]+)[^)]*\)'
                             r'\s*\(size [-\d.]+ [-\d.]+\)\s*\(drill ([-\d.]+)', b):
            if float(p.group(3)) < 2.0:
                continue
            lx, ly = float(p.group(1)), float(p.group(2))
            out.append((ref.group(1) if ref else "?",
                        (fx + lx * math.cos(a) + ly * math.sin(a),
                         fy - lx * math.sin(a) + ly * math.cos(a)),
                        float(p.group(3))))
    return out


def inside(pt, segs):
    """Even-odd point-in-outline over all segments (handles cut-outs)."""
    x, y = pt
    n = 0
    for (x1, y1), (x2, y2) in segs:
        if (y1 > y) != (y2 > y):
            if x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
                n += 1
    return n % 2 == 1


# --------------------------------------------------------------------------
# The STL: occupied Z-intervals per column
# --------------------------------------------------------------------------

def column_hits(stl, x0, y0, nx, ny):
    """{(i, j): [(z, +1 entering / -1 leaving), ...]} for cell centres."""
    hits = defaultdict(list)
    x1, y1 = x0 + nx * CELL, y0 + ny * CELL
    with open(stl, "rb") as fh:
        count = struct.unpack("<I", fh.read(84)[80:84])[0]
        up = struct.Struct("<12fH").unpack_from
        done = 0
        while done < count:
            k = min(50000, count - done)
            buf = fh.read(50 * k)
            for t in range(k):
                d = up(buf, 50 * t)
                ax, ay, az, bx, by, bz, cx, cy, cz = d[3:12]
                lo_x = min(ax, bx, cx)
                hi_x = max(ax, bx, cx)
                if hi_x < x0 or lo_x > x1:
                    continue
                lo_y = min(ay, by, cy)
                hi_y = max(ay, by, cy)
                if hi_y < y0 or lo_y > y1:
                    continue
                # facet orientation from the winding (STL normals are unreliable)
                nz = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
                if abs(nz) < 1e-12:
                    continue                     # vertical facet: no z crossing
                sign = +1 if nz < 0 else -1      # facing down = entering the solid
                i0 = max(0, math.ceil((lo_x - x0) / CELL - 0.5))
                i1 = min(nx - 1, math.floor((hi_x - x0) / CELL - 0.5))
                j0 = max(0, math.ceil((lo_y - y0) / CELL - 0.5))
                j1 = min(ny - 1, math.floor((hi_y - y0) / CELL - 0.5))
                if i1 < i0 or j1 < j0:
                    continue
                for i in range(i0, i1 + 1):
                    px = x0 + (i + 0.5) * CELL
                    for j in range(j0, j1 + 1):
                        py = y0 + (j + 0.5) * CELL
                        # barycentric point-in-triangle and z at the point
                        l1 = ((by - cy) * (px - cx) + (cx - bx) * (py - cy)) / nz
                        l2 = ((cy - ay) * (px - cx) + (ax - cx) * (py - cy)) / nz
                        l3 = 1 - l1 - l2
                        if l1 < 0 or l2 < 0 or l3 < 0:
                            continue
                        hits[(i, j)].append((l1 * az + l2 * bz + l3 * cz, sign))
            done += k
    return hits


def intervals(h):
    """Occupied [z_lo, z_hi] intervals from signed crossings."""
    out, depth, start = [], 0, None
    for z, s in sorted(h):
        if s > 0:
            if depth == 0:
                start = z
            depth += 1
        else:
            depth = max(0, depth - 1)
            if depth == 0 and start is not None:
                out.append((start, z))
                start = None
    return out


def classify(iv):
    """(blocked for the PCB?, room above the PCB in mm, floor height)."""
    pcb_lo, pcb_hi = STACK + TOL, STACK + PCB
    blocked = any(lo < pcb_hi and hi > pcb_lo for lo, hi in iv)
    above = [lo for lo, hi in iv if lo >= pcb_hi]
    room = (min(above) - pcb_hi) if above else 99.0
    floor = max([hi for lo, hi in iv if lo < pcb_lo] or [-99.0])
    return blocked, room, floor


# --------------------------------------------------------------------------

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    svg_out = None
    if "--svg" in sys.argv:
        svg_out = sys.argv[sys.argv.index("--svg") + 1]
        args = [a for a in args if a != svg_out]
    if len(args) < 2:
        print(__doc__)
        return 2
    stp, stl = args[0], args[1]

    # ---- model side: the IAS connectors from the STEP -------------------
    ents, _ = sl.load(stp)
    pd_name, pd_reps, children, roots, _ = sl.build(ents)
    found = []
    stack = [(r, sl.IDENTITY) for r in roots]
    while stack:
        pd, m = stack.pop()
        for child, t, _ in children.get(pd, []):
            wm = sl.mul(m, t)
            if pd_name.get(child) == "CONN_928X90X80_38P":
                found.append(sl.apply(wm, [0, 0, 0]))
            stack.append((child, wm))
    found.sort(key=lambda p: p[1])
    m_minus, m_plus = found[0][:2], found[1][:2]
    m_j7, m_j8 = (m_plus, m_minus) if J7_IS_PLUS_Y else (m_minus, m_plus)
    print("MODEL (STEP)")
    print(f"  J7 / IAS0 centre  ({m_j7[0]:.3f}, {m_j7[1]:.3f})")
    print(f"  J8 / IAS1 centre  ({m_j8[0]:.3f}, {m_j8[1]:.3f})   "
          f"separation {math.dist(m_j7, m_j8):.3f} mm")

    # ---- adapter side ----------------------------------------------------
    segs, conns = adapter()
    (a0, a0p1), (a1, a1p1) = conns["J8_IAS0"], conns["J8_IAS1"]
    print("ADAPTER (.kicad_pcb, KiCad frame)")
    print(f"  J8_IAS0 centre    ({a0[0]:.3f}, {a0[1]:.3f})   pad 1 ({a0p1[0]:.3f}, {a0p1[1]:.3f})")
    print(f"  J8_IAS1 centre    ({a1[0]:.3f}, {a1[1]:.3f})   separation {math.dist(a0, a1):.3f} mm")
    print(f"  outline           {len(segs)} segments")

    f, g, ang = make_transform(a0, a1, m_j7, m_j8)
    err = math.dist(f(a1), m_j8)
    print()
    print(f"TRANSFORM  adapter -> model: rotate {ang:+.2f} deg, residual at J8 {err*1000:.1f} um")

    # Check 1: pad 1 lands on the pin-1 end (the -Y end) of the carrier connector.
    p1m = f(a0p1)
    print(f"  check 1: adapter pad 1 maps to ({p1m[0]:.3f}, {p1m[1]:.3f}), "
          f"{p1m[1] - m_j7[1]:+.2f} mm from J7's centre along Y  -> "
          f"{'pin-1 end (-Y) as the silkscreen shows: OK' if p1m[1] < m_j7[1] else 'WRONG END'}")

    mseg = [(f(p), f(q)) for p, q in segs]
    xs = [c for s in mseg for p in s for c in [p[0]]]
    ys = [c for s in mseg for p in s for c in [p[1]]]
    print(f"  adapter outline in the model frame: X {min(xs):.2f} .. {max(xs):.2f}, "
          f"Y {min(ys):.2f} .. {max(ys):.2f}")

    # ---- clearance map -----------------------------------------------------
    MARGIN = 25.0
    x0, y0 = math.floor(min(xs) - MARGIN), math.floor(min(ys) - MARGIN)
    nx = int((max(xs) + MARGIN - x0) / CELL)
    ny = int((max(ys) + MARGIN - y0) / CELL)
    print()
    print(f"CLEARANCE MAP  {nx} x {ny} cells of {CELL} mm, "
          f"X {x0} .. {x0 + nx*CELL}, Y {y0} .. {y0 + ny*CELL}")
    hits = column_hits(stl, x0, y0, nx, ny)
    grid = {}
    for i in range(nx):
        for j in range(ny):
            grid[(i, j)] = classify(intervals(hits.get((i, j), [])))

    def centre(i, j):
        return (x0 + (i + 0.5) * CELL, y0 + (j + 0.5) * CELL)

    # Sanity: the connector cells should show the 0.80 mm connector body.
    ci, cj = int((m_j7[0] - x0) / CELL), int((m_j7[1] - y0) / CELL)
    print(f"  sanity: floor at J7's centre = {grid[(ci, cj)][2]:.2f} mm (connector is 0.80 tall)")

    # Check 2: nothing may rise through the PCB inside the original outline.
    inner = [(i, j) for (i, j) in grid if inside(centre(i, j), mseg)]
    hit = [(i, j) for (i, j) in inner if grid[(i, j)][0]]
    print(f"  check 2: {len(inner)} cells inside the ORIGINAL outline; "
          f"{len(hit)} blocked ({100.0*len(hit)/max(1,len(inner)):.2f} %)")
    if hit:
        worst = sorted(hit, key=lambda c: -grid[c][2])[:8]
        for c in worst:
            p = centre(*c)
            q = g(p)
            print(f"      model ({p[0]:7.2f},{p[1]:7.2f})  adapter ({q[0]:7.2f},{q[1]:7.2f})  "
                  f"floor {grid[c][2]:.2f} mm")
    # Check 3: the adapter's mounting holes against the carrier's. Holes have
    # nothing to do with the connectors the transform was built from, so a
    # match here is independent confirmation.
    print("  check 3: adapter holes (drill >= 2 mm) against the carrier's holes (STEP BOARD_OUTLINE)")
    carrier = carrier_holes(ents, pd_name, pd_reps, children, roots)
    for ref, (u, v), drill in adapter_holes():
        X, Y = f((u, v))
        best = min(carrier, key=lambda h: math.hypot(h[0] - X, h[1] - Y))
        d = math.hypot(best[0] - X, best[1] - Y)
        print(f"      {ref:8s} drill {drill:.2f} -> model ({X:7.3f},{Y:7.3f}); carrier hole "
              f"({best[0]:.3f},{best[1]:.3f}) dia {2*best[2]:.2f}: offset {d*1000:.0f} um"
              f"{'  MATCH' if d < 0.05 else ''}")

    rooms = sorted(grid[c][1] for c in inner)
    if rooms:
        print(f"  room for top-side parts inside the outline: min {rooms[0]:.2f} mm, "
              f"5th percentile {rooms[len(rooms)//20]:.2f} mm")

    # ---- growth profile ----------------------------------------------------
    # The board is U-shaped, so "how far can this side move" has no single
    # answer. Instead, for every 5 mm band along each of the four model
    # directions, scan outward from the board's current extreme in that band
    # until a column is blocked. Directions are named on the CARRIER, where
    # they mean something physical, and translated to the KiCad frame.
    BAND = 5.0
    print()
    print(f"GROWTH PROFILE  (how far the board edge can move before a carrier part "
          f"rises through it; scan limit {MARGIN:.0f} mm)")
    dirs = [
        # name, scan axis, sign, KiCad meaning
        ("-X  off the carrier's side edge", 0, -1, "+v (down in KiCad)"),
        ("+X  inward, toward the SOM",       0, +1, "-v (up in KiCad)"),
        ("-Y  past the carrier's front",     1, -1, "+u (right in KiCad)"),
        ("+Y  toward the rear I/O",          1, +1, "-u (left in KiCad)"),
    ]
    inner_set = set(inner)
    profile = {}
    for name, ax, sign, kmean in dirs:
        other = 1 - ax
        lo_o = min(c[other] for c in inner_set)
        hi_o = max(c[other] for c in inner_set)
        rows = []
        b = lo_o
        nb = int(BAND / CELL)
        while b <= hi_o:
            band = [c for c in inner_set if b <= c[other] < b + nb]
            if band:
                edge = (max if sign > 0 else min)(c[ax] for c in band)
                ds = []
                for k in range(b, min(b + nb, (nx, ny)[other])):
                    step = 0
                    while True:
                        pos = edge + sign * (step + 1)
                        if not (0 <= pos < (nx, ny)[ax]):
                            step = None                     # ran off the map
                            break
                        cell = (pos, k) if ax == 0 else (k, pos)
                        if grid[cell][0]:
                            break
                        step += 1
                    ds.append(None if step is None else step * CELL)
                # The band is only as free as its most obstructed row.
                nums = [d for d in ds if d is not None]
                best = min(nums) if nums else None
                o0 = (x0, y0)[other] + b * CELL
                rows.append((o0, o0 + BAND, (x0, y0)[ax] + (edge + 0.5) * CELL, best))
            b += nb
        profile[name] = rows
        print(f"  {name}   [KiCad {kmean}]")
        axn = "XY"[other]
        for o0, o1, e, d in rows:
            txt = f"{d:5.1f} mm" if d is not None else f"{MARGIN:4.0f}+ mm (nothing in range)"
            print(f"      {axn} {o0:7.1f} .. {o1:7.1f}   board edge at {'XY'[ax]} {e:7.2f}   clear {txt}")

    if svg_out:
        write_svg(svg_out, grid, nx, ny, x0, y0, g, segs, conns)
        print(f"\nwrote {svg_out}")
    return 0


def write_svg(path, grid, nx, ny, x0, y0, g, segs, conns):
    """Clearance map drawn in the ADAPTER's KiCad frame (Y down)."""
    def colour(c):
        b, room, floor = c
        if b:
            return "#d9534f"                 # something rises through the PCB
        if room < 3.0:
            return "#f0ad4e"                 # the PCB fits, tall parts do not
        if room < 99:
            return "#9bd49b"                 # overhead obstacle, 3 mm or more of room
        return None                          # open

    rects = []
    for i in range(nx):
        for j in range(ny):
            col = colour(grid[(i, j)])
            if col is None:
                continue
            u, v = g((x0 + (i + 0.5) * CELL, y0 + (j + 0.5) * CELL))
            rects.append(f'<rect x="{u - CELL/2:.2f}" y="{v - CELL/2:.2f}" '
                         f'width="{CELL}" height="{CELL}" fill="{col}"/>')

    def poly_model(pts, style):
        q = [g(p) for p in pts]
        return (f'<polygon points="{" ".join(f"{a:.2f},{b:.2f}" for a, b in q)}" {style}/>')

    carrier = poly_model([(-10, -10), (130, -10), (130, 109), (-10, 109)],
                         'fill="none" stroke="#555" stroke-width="0.4" stroke-dasharray="2,1"')
    som = poly_model([(47.628, 16.978), (124.628, 16.978), (124.628, 76.978), (47.628, 76.978)],
                     'fill="none" stroke="#7a4fb0" stroke-width="0.4" stroke-dasharray="1,1"')
    outline = " ".join(f"M{p[0]:.2f},{p[1]:.2f} L{q[0]:.2f},{q[1]:.2f}" for p, q in segs)
    conn = "".join(
        f'<rect x="{c[0][0]-4.69:.2f}" y="{c[0][1]-1.2:.2f}" width="9.38" height="2.4" '
        f'fill="none" stroke="#1f3a93" stroke-width="0.4"/>'
        f'<text x="{c[0][0]:.2f}" y="{c[0][1]-2.2:.2f}" font-size="2.2" '
        f'text-anchor="middle" fill="#1f3a93">{n}</text>' for n, c in conns.items())

    corners = [g((x0 + i * CELL, y0 + j * CELL)) for i in (0, nx) for j in (0, ny)]
    umin = min(p[0] for p in corners)
    vmin = min(p[1] for p in corners)
    umax = max(p[0] for p in corners)
    vmax = max(p[1] for p in corners)
    w, h = umax - umin, vmax - vmin
    legend = [("#d9534f", "a carrier part rises through the adapter PCB (0.8-2.4 mm)"),
              ("#f0ad4e", "the PCB fits, but less than 3 mm of room above it"),
              ("#9bd49b", "overhead obstacle, 3 mm or more of room above the PCB"),
              ("#ffffff", "free")]
    leg = "".join(
        f'<rect x="{umin+2:.1f}" y="{vmax+3+5*k:.1f}" width="4" height="3.2" fill="{c}" '
        f'stroke="#555" stroke-width="0.1"/><text x="{umin+7.5:.1f}" y="{vmax+5.6+5*k:.1f}" '
        f'font-size="2.6" fill="#222">{t}</text>' for k, (c, t) in enumerate(legend))
    notes = (f'<text x="{umin+2:.1f}" y="{vmax+25.6:.1f}" font-size="2.6" fill="#222">'
             f'black: original Allied Vision outline - grey dashes: KV260 carrier edge - '
             f'purple dashes: K26 SOM</text>')
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{umin:.1f} {vmin-8:.1f} {w:.1f} {h+38:.1f}" '
           f'width="{w*6:.0f}" height="{(h+38)*6:.0f}" font-family="sans-serif">'
           f'<defs><clipPath id="map"><rect x="{umin:.1f}" y="{vmin:.1f}" width="{w:.1f}" '
           f'height="{h:.1f}"/></clipPath></defs>'
           f'<rect x="{umin:.1f}" y="{vmin-8:.1f}" width="{w:.1f}" height="{h+38:.1f}" fill="#ffffff"/>'
           f'<rect x="{umin:.1f}" y="{vmin:.1f}" width="{w:.1f}" height="{h:.1f}" fill="none" '
           f'stroke="#bbb" stroke-width="0.2"/>'
           f'<text x="{umin+2:.1f}" y="{vmin-3:.1f}" font-size="3.2" fill="#222">KV260 clearance '
           f'under the adapter, in the KiCad frame of CSI2-KRIA-KV260_Rev01.kicad_pcb '
           f'({CELL} mm cells)</text>'
           + '<g clip-path="url(#map)">' + "".join(rects) + carrier + som + '</g>'
           + f'<path d="{outline}" fill="none" stroke="#000" stroke-width="0.35"/>'
           + conn + leg + notes + '</svg>')
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(svg)


if __name__ == "__main__":
    sys.exit(main())
