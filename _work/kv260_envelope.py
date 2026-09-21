#!/usr/bin/env python3
"""
Measure the KV260's mechanical envelope from the official 3D model.

Closes R-04: "how far can the adapter board grow without fouling the heatsink,
the front connectors or the enclosure". Until now that was unmeasured and the
documentation carried an estimate.

Input: the official 3D CAD model (XTP679), converted to binary STL.
   \\\\tnas\\Preserver\\CAD\\KV260V2-Starter-Kit.stl

What it produces:
  1. The overall bounding box of the Starter Kit.
  2. A top-down height map: for each XY cell, the highest point of the model.
     That is what tells you where a board stacked on top can and cannot go.
  3. A horizontal slice at a chosen height, showing the occupied footprint at
     the level an adapter would sit.

Pure Python, no dependencies: the machine that has KiCad has no numpy.
Streaming the 1.3 M triangles takes about a minute.

Usage:
    py _work/kv260_envelope.py [--cell 2.0] [--slice 20.0]
"""

import os
import struct
import sys

STL = "//tnas/Preserver/CAD/KV260V2-Starter-Kit.stl"

CELL = 2.0          # height map resolution, mm
SLICE_Z = None      # if set, also report the footprint above this height

for i, a in enumerate(sys.argv):
    if a == "--cell" and i + 1 < len(sys.argv):
        CELL = float(sys.argv[i + 1])
    if a == "--slice" and i + 1 < len(sys.argv):
        SLICE_Z = float(sys.argv[i + 1])


def read_triangles(path):
    """Yield (v1, v2, v3) for every triangle in a binary STL."""
    with open(path, "rb") as fh:
        header = fh.read(84)
        count = struct.unpack("<I", header[80:84])[0]
        # Read in blocks so the whole 66 MB never sits in memory twice.
        block = 20000
        unpack = struct.Struct("<12fH").unpack_from
        done = 0
        while done < count:
            n = min(block, count - done)
            buf = fh.read(50 * n)
            if len(buf) < 50 * n:
                break
            for k in range(n):
                d = unpack(buf, 50 * k)
                yield (d[3], d[4], d[5]), (d[6], d[7], d[8]), (d[9], d[10], d[11])
            done += n


def main():
    if not os.path.exists(STL):
        print(f"Model not found: {STL}")
        return 1

    print(f"Reading {STL}")
    print(f"  height map cell: {CELL} mm")

    minx = miny = minz = float("inf")
    maxx = maxy = maxz = float("-inf")
    tris = []

    # Pass 1: bounding box. Vertices are kept as a flat list of tuples so the
    # second pass does not have to re-read 66 MB over the network.
    for a, b, c in read_triangles(STL):
        for (x, y, z) in (a, b, c):
            if x < minx: minx = x
            if x > maxx: maxx = x
            if y < miny: miny = y
            if y > maxy: maxy = y
            if z < minz: minz = z
            if z > maxz: maxz = z
        tris.append((a, b, c))

    print()
    print("Bounding box of the Starter Kit as modelled:")
    print(f"    X  {minx:9.2f} .. {maxx:9.2f}   ({maxx-minx:7.2f} mm)")
    print(f"    Y  {miny:9.2f} .. {maxy:9.2f}   ({maxy-miny:7.2f} mm)")
    print(f"    Z  {minz:9.2f} .. {maxz:9.2f}   ({maxz-minz:7.2f} mm)")
    print(f"    triangles: {len(tris):,}")

    # --- height map -----------------------------------------------------
    nx = int((maxx - minx) / CELL) + 1
    ny = int((maxy - miny) / CELL) + 1
    print()
    print(f"Height map grid: {nx} x {ny} cells")

    hmap = [[None] * nx for _ in range(ny)]
    for a, b, c in tris:
        for (x, y, z) in (a, b, c):
            ix = int((x - minx) / CELL)
            iy = int((y - miny) / CELL)
            cur = hmap[iy][ix]
            if cur is None or z > cur:
                hmap[iy][ix] = z

    # --- histogram of heights -------------------------------------------
    heights = [h for row in hmap for h in row if h is not None]
    heights.sort()
    print(f"  occupied cells: {len(heights):,} of {nx*ny:,}")

    def pct(p):
        return heights[int(len(heights) * p)] if heights else 0.0

    print()
    print("Height distribution over the occupied area (relative to Z min):")
    for p in (0.50, 0.75, 0.90, 0.95, 0.99, 1.0):
        idx = min(int(len(heights) * p), len(heights) - 1)
        print(f"    p{int(p*100):<3}  {heights[idx] - minz:7.2f} mm")

    # --- tall obstacles --------------------------------------------------
    print()
    print("Tall regions (the things an adapter has to clear):")
    tall_levels = [10, 20, 25, 30, 35, 40]
    for lv in tall_levels:
        cells = [(ix, iy) for iy in range(ny) for ix in range(nx)
                 if hmap[iy][ix] is not None and hmap[iy][ix] - minz > lv]
        if not cells:
            print(f"    above {lv:2d} mm : nothing")
            continue
        xs = [minx + ix * CELL for ix, _ in cells]
        ys = [miny + iy * CELL for _, iy in cells]
        area = len(cells) * CELL * CELL
        print(f"    above {lv:2d} mm : {len(cells):5d} cells ({area:7.0f} mm2)  "
              f"X {min(xs):7.1f}..{max(xs):7.1f}  Y {min(ys):7.1f}..{max(ys):7.1f}")

    # --- ASCII top view ---------------------------------------------------
    print()
    print("Top view, height above the model's Z minimum:")
    print("   . <5mm   - <10   = <20   # <30   @ >=30   (blank = nothing)")
    step_x = max(1, nx // 100)
    step_y = max(1, ny // 44)
    print("   " + "+" + "-" * (nx // step_x) + "+")
    for iy in range(ny - 1, -1, -step_y):
        line = []
        for ix in range(0, nx, step_x):
            best = None
            for jy in range(iy, min(iy + step_y, ny)):
                for jx in range(ix, min(ix + step_x, nx)):
                    h = hmap[jy][jx]
                    if h is not None and (best is None or h > best):
                        best = h
            if best is None:
                line.append(" ")
            else:
                d = best - minz
                line.append("." if d < 5 else "-" if d < 10 else
                            "=" if d < 20 else "#" if d < 30 else "@")
        print("   |" + "".join(line) + "|")
    print("   " + "+" + "-" * (nx // step_x) + "+")
    print(f"   X from {minx:.1f} to {maxx:.1f} mm, Y from {miny:.1f} to {maxy:.1f} mm")

    if SLICE_Z is not None:
        print()
        occupied = [(minx + ix * CELL, miny + iy * CELL)
                    for iy in range(ny) for ix in range(nx)
                    if hmap[iy][ix] is not None and hmap[iy][ix] - minz > SLICE_Z]
        print(f"Footprint of everything taller than {SLICE_Z} mm: "
              f"{len(occupied)} cells")
        if occupied:
            xs = [p[0] for p in occupied]
            ys = [p[1] for p in occupied]
            print(f"    X {min(xs):.1f} .. {max(xs):.1f}   Y {min(ys):.1f} .. {max(ys):.1f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
