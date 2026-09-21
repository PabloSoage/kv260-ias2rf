#!/usr/bin/env python3
"""
Locate the IAS connectors in the official KV260 3D model.

Registering the adapter board against the KV260 needs a common reference. The
adapter gives us a very distinctive signature: its two Hirose BM20B(0.8)-34DP
connectors sit exactly 50.040 mm apart, aligned on one axis (measured from
CSI2-KRIA-KV260_Rev01.kicad_pcb: J8_IAS0 at 135.981, 85.604 and J8_IAS1 at
186.021, 85.604).

So the search is: find two objects in the model, at low height above the
carrier PCB, whose centres are 50.04 mm apart on one axis. That pair can only
be the mating IAS connectors.

Method:
  1. Z histogram of all vertices, to find the carrier PCB's top surface.
  2. Occupancy grid restricted to a thin band just above that surface.
  3. Connected components on that grid.
  4. Pairwise distances between component centres, looking for 50.04 mm.

Usage:
    py _work/kv260_locate_ias.py [--band-lo 1.0] [--band-hi 6.0] [--cell 0.5]
"""

import math
import os
import struct
import sys

STL = "//tnas/Preserver/CAD/KV260V2-Starter-Kit.stl"

TARGET_MM = 50.040          # spacing between the adapter's two Hirose
TOLERANCE = 0.80            # mm
CELL = 0.5
BAND_LO, BAND_HI = None, None

for i, a in enumerate(sys.argv):
    if a == "--cell":
        CELL = float(sys.argv[i + 1])
    if a == "--band-lo":
        BAND_LO = float(sys.argv[i + 1])
    if a == "--band-hi":
        BAND_HI = float(sys.argv[i + 1])


def read_vertices(path):
    with open(path, "rb") as fh:
        count = struct.unpack("<I", fh.read(84)[80:84])[0]
        unpack = struct.Struct("<12fH").unpack_from
        block, done = 20000, 0
        while done < count:
            n = min(block, count - done)
            buf = fh.read(50 * n)
            if len(buf) < 50 * n:
                break
            for k in range(n):
                d = unpack(buf, 50 * k)
                yield d[3], d[4], d[5]
                yield d[6], d[7], d[8]
                yield d[9], d[10], d[11]
            done += n


def components(cells):
    """Connected components (8-neighbourhood) over a set of (ix, iy)."""
    seen, out = set(), []
    cells = set(cells)
    for c in cells:
        if c in seen:
            continue
        stack, comp = [c], []
        seen.add(c)
        while stack:
            cx, cy = stack.pop()
            comp.append((cx, cy))
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    n = (cx + dx, cy + dy)
                    if n in cells and n not in seen:
                        seen.add(n)
                        stack.append(n)
        out.append(comp)
    return out


def main():
    if not os.path.exists(STL):
        print(f"Model not found: {STL}")
        return 1

    print(f"Reading {STL}")
    verts = list(read_vertices(STL))
    print(f"  vertices: {len(verts):,}")

    zs = sorted(v[2] for v in verts)
    zmin, zmax = zs[0], zs[-1]
    print(f"  Z range: {zmin:.2f} .. {zmax:.2f}")

    # --- Z histogram, 0.5 mm bins ---------------------------------------
    print()
    print("Z histogram (bins with the most vertices — flat surfaces show up here):")
    bins = {}
    for _, _, z in verts:
        bins[round(z * 2) / 2] = bins.get(round(z * 2) / 2, 0) + 1
    top = sorted(bins.items(), key=lambda kv: -kv[1])[:12]
    for z, c in sorted(top):
        bar = "#" * int(40 * c / top[0][1])
        print(f"    z = {z:7.2f}   {c:8,d}  {bar}")

    # The carrier PCB's top face is the densest flat surface in the lower half.
    lower = [(z, c) for z, c in bins.items() if z < zmin + (zmax - zmin) * 0.5]
    pcb_top = max(lower, key=lambda kv: kv[1])[0]
    print()
    print(f"Carrier PCB top surface taken as z = {pcb_top:.2f}")

    lo = BAND_LO if BAND_LO is not None else pcb_top + 0.6
    hi = BAND_HI if BAND_HI is not None else pcb_top + 6.0
    print(f"Searching for connectors in the band z = {lo:.2f} .. {hi:.2f}")

    band = [(x, y) for x, y, z in verts if lo <= z <= hi]
    print(f"  vertices in band: {len(band):,}")
    if not band:
        print("  nothing in that band; adjust --band-lo / --band-hi")
        return 1

    minx = min(p[0] for p in band)
    miny = min(p[1] for p in band)
    grid = {(int((x - minx) / CELL), int((y - miny) / CELL)) for x, y in band}
    print(f"  occupied cells at {CELL} mm: {len(grid):,}")

    comps = components(grid)
    comps.sort(key=len, reverse=True)
    print(f"  connected components: {len(comps)}")

    info = []
    for comp in comps:
        xs = [minx + ix * CELL for ix, _ in comp]
        ys = [miny + iy * CELL for _, iy in comp]
        w, h = max(xs) - min(xs), max(ys) - min(ys)
        info.append({
            "cx": (max(xs) + min(xs)) / 2, "cy": (max(ys) + min(ys)) / 2,
            "w": w, "h": h, "n": len(comp),
        })

    # --- look for the 50.04 mm pair --------------------------------------
    print()
    print(f"Pairs of components {TARGET_MM} mm apart (+/- {TOLERANCE} mm):")
    found = []
    for i in range(len(info)):
        for j in range(i + 1, len(info)):
            a, b = info[i], info[j]
            d = math.hypot(a["cx"] - b["cx"], a["cy"] - b["cy"])
            if abs(d - TARGET_MM) <= TOLERANCE:
                axis = "X" if abs(a["cy"] - b["cy"]) < 2.0 else \
                       "Y" if abs(a["cx"] - b["cx"]) < 2.0 else "diagonal"
                found.append((d, axis, a, b))

    if not found:
        print("    none. Try widening the band or the tolerance.")
    for d, axis, a, b in sorted(found, key=lambda t: -min(t[2]["n"], t[3]["n"]))[:10]:
        print(f"    d = {d:6.2f} mm along {axis}")
        for c in (a, b):
            print(f"        centre ({c['cx']:7.2f}, {c['cy']:7.2f})  "
                  f"size {c['w']:5.2f} x {c['h']:5.2f} mm  {c['n']} cells")

    print()
    print("A Hirose BM20B(0.8)-34DP body is about 11.6 x 2.9 mm, so the right")
    print("pair is the one whose components are that size, aligned on one axis.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
