#!/usr/bin/env python3
"""
Locate the IAS connectors in a PDF plot of the KV260 carrier layout.

The Allegro free viewer cannot export DXF and its .brd cannot be parsed (see
_work/brd_probe_NEGATIVE.md), but it will plot to PDF. That plot has no text
layer - it is pure vector - so the connectors cannot be found by their refdes.
They can be found by their geometry.

The signature, measured from the adapter's own layout `[V]`:
  the two mating Hirose connectors are 50.040 mm apart, with identical Y.

Since the PDF's user units are arbitrary, that distance is also what CALIBRATES
the drawing: find two congruent shapes sharing a Y, assume they are the IAS
pair, and the scale follows. The check that it is the right pair is that the
resulting scale makes the board outline come out a sensible size.

Usage:
    py _work/brd_pdf_locate_ias.py <plot.pdf>
"""

import math
import re
import sys
import zlib
from collections import defaultdict

IAS_SEPARATION_MM = 50.040       # [V] from CSI2-KRIA-KV260_Rev01.kicad_pcb
BOARD_MM_RANGE = (100.0, 180.0)  # a KV260 carrier is ~140 mm on its long side


def content_stream(path):
    raw = open(path, "rb").read()
    best = b""
    for m in re.finditer(rb"stream\r?\n", raw):
        s = m.end()
        e = raw.find(b"endstream", s)
        if e < 0:
            continue
        blob = raw[s:e]
        try:
            blob = zlib.decompress(blob)
        except Exception:
            pass
        if len(blob) > len(best):
            best = blob
    return best.decode("latin-1", "replace")


def subpaths(text):
    """Yield the vertex list of every subpath begun by `m`."""
    tok = re.findall(r"(-?\d+\.?\d*)\s+(-?\d+\.?\d*)\s+([ml])|(\bh\b|\bS\b|\bf\b)", text)
    cur = []
    for x, y, op, closer in tok:
        if closer:
            if len(cur) >= 3:
                yield cur
            cur = []
            continue
        px, py = float(x), float(y)
        if op == "m":
            if len(cur) >= 3:
                yield cur
            cur = [(px, py)]
        else:
            cur.append((px, py))
    if len(cur) >= 3:
        yield cur


def bbox(pts):
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def main():
    pdf = sys.argv[1] if len(sys.argv) > 1 else "default.pdf"
    text = content_stream(pdf)
    print(f"content stream: {len(text):,} chars")

    shapes = []
    for pts in subpaths(text):
        x0, y0, x1, y1 = bbox(pts)
        w, h = x1 - x0, y1 - y0
        if w <= 0 or h <= 0:
            continue
        shapes.append({"cx": (x0 + x1) / 2, "cy": (y0 + y1) / 2,
                       "w": w, "h": h, "n": len(pts)})
    print(f"closed subpaths: {len(shapes):,}")

    # The drawing frame / board outline is the largest shape.
    biggest = max(shapes, key=lambda s: s["w"] * s["h"])
    print(f"largest shape: {biggest['w']:.0f} x {biggest['h']:.0f} user units")

    # Group by rounded size, so congruent footprints land together.
    groups = defaultdict(list)
    for s in shapes:
        groups[(round(s["w"], 1), round(s["h"], 1))].append(s)

    print()
    print("Looking for two congruent shapes sharing a Y...")
    print()
    cands = []
    for (w, h), members in groups.items():
        if len(members) < 2 or w < 5 or h < 5:
            continue
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                a, b = members[i], members[j]
                dy = abs(a["cy"] - b["cy"])
                dx = abs(a["cx"] - b["cx"])
                if dy > max(h * 0.05, 2.0):        # must share a Y
                    continue
                if dx < w:                          # must not overlap
                    continue
                scale = IAS_SEPARATION_MM / dx      # mm per user unit
                board_w = biggest["w"] * scale
                board_h = biggest["h"] * scale
                lo, hi = BOARD_MM_RANGE
                plausible = (lo <= max(board_w, board_h) <= hi)
                cands.append({
                    "w": w, "h": h, "dx": dx, "scale": scale,
                    "board": (board_w, board_h), "a": a, "b": b,
                    "plausible": plausible,
                    "aspect": w / h if h else 0,
                })

    cands.sort(key=lambda c: (not c["plausible"], -c["w"] * c["h"]))
    print(f"congruent same-Y pairs: {len(cands)}")
    print()
    shown = 0
    for c in cands:
        if shown >= 10:
            break
        bw, bh = c["board"]
        flag = "PLAUSIBLE" if c["plausible"] else "         "
        print(f"  {flag}  shape {c['w']:7.1f} x {c['h']:6.1f} uu "
              f"(aspect {c['aspect']:5.2f})   separation {c['dx']:8.1f} uu")
        print(f"             -> scale {c['scale']:.6f} mm/uu   "
              f"board would be {bw:.1f} x {bh:.1f} mm")
        print(f"             centres ({c['a']['cx']:.0f}, {c['a']['cy']:.0f}) and "
              f"({c['b']['cx']:.0f}, {c['b']['cy']:.0f})")
        print(f"             footprint would measure "
              f"{c['w']*c['scale']:.2f} x {c['h']*c['scale']:.2f} mm")
        print()
        shown += 1

    print("A Hirose BM20B(0.8)-34DP body is about 11.6 x 2.9 mm, aspect ~4.0.")
    print("The right pair is the one whose footprint comes out near that size")
    print("AND whose implied scale gives a sensible board.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
