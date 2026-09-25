#!/usr/bin/env python3
"""
Measure the placement on the board file: for every passive that belongs to
a pin (build_board.attachments), the distance from its pad to that pin.

Pad positions are computed from the board text: footprint position plus the
pad's local position rotated by the footprint's angle. That transform is
checked first against the pad coordinates KiCad itself prints in its DRC
report, so the distances below are KiCad's, not this script's opinion.

Usage:  py _work/layout/check_placement.py [drc.rpt]
"""

import math
import os
import re
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_board as B                              # noqa: E402
import pcbdata as P                                  # noqa: E402

schgen = P.schgen


def board_pads(path=B.BOARD):
    """ref -> [(pad, x, y, net)] in board coordinates. A list: a footprint
    can have several pads with one number (an SMA's grounds)."""
    text = open(path, encoding="utf-8").read()
    out = {}
    for m in re.finditer(r"\n\t\(footprint ", text):
        blk = schgen._block(text, m.start() + 2)
        ref = re.search(r'\(property "Reference" "([^"]+)"', blk).group(1)
        at = re.search(r'\n\t\t\(at ([\d.\-]+) ([\d.\-]+)(?: ([\d.\-]+))?\)', blk)
        fx, fy, fa = float(at.group(1)), float(at.group(2)), float(at.group(3) or 0)
        pads = []
        for pm in re.finditer(r'\n\t\t\(pad "([^"]*)"', blk):
            pb = schgen._block(blk, pm.start() + 3)
            pa = re.search(r'\(at ([\d.\-]+) ([\d.\-]+)', pb)
            net = re.search(r'\(net "([^"]*)"\)', pb)
            dx, dy = B.rot_pt(float(pa.group(1)), float(pa.group(2)), fa)
            pads.append((pm.group(1), fx + dx, fy + dy, net.group(1) if net else ""))
        out[ref] = pads
    return out


def check_transform(pads, rpt):
    """Compare against '@(x mm, y mm): Pad N [net] of REF' lines of a DRC report."""
    worst, n = 0.0, 0
    for x, y, pad, ref in re.findall(
            r"@\(([\d.\-]+) mm, ([\d.\-]+) mm\): Pad (\S+) \[[^\]]*\] of (\S+)", open(rpt, encoding="utf-8").read()):
        same = [(px, py) for p, px, py, _ in pads.get(ref, []) if p == pad]
        if same:
            worst = max(worst, min(math.dist(q, (float(x), float(y))) for q in same))
            n += 1
    return n, worst


def main():
    pads = board_pads()
    if len(sys.argv) > 1:
        n, worst = check_transform(pads, sys.argv[1])
        print(f"pad transform vs KiCad's DRC report: {n} pads compared, worst {worst * 1000:.1f} um")
        assert n > 50 and worst < 0.01, "pad transform disagrees with KiCad"
    comps = P.netlist()
    attach = B.attachments(comps, B.schematic_positions())
    rows = []
    for ref, (owner, net, rail, key) in attach.items():
        mine = [(x, y) for _, x, y, n in pads[ref] if n == net]
        theirs = [(x, y) for _, x, y, n in pads[owner] if n == net]
        if mine and theirs:
            d = min(math.dist(a, b) for a in mine for b in theirs)
            rows.append((d, ref, owner, net, key[0]))
    for kind, name in ((0, "decoupling <= 1 uF"), (1, "tied to a signal pin"), (2, "bulk decoupling")):
        ds = [r[0] for r in rows if r[4] == kind]
        if ds:
            print(f"{name:22s} {len(ds):4d} parts   median {statistics.median(ds):5.2f} mm   "
                  f"90% {sorted(ds)[int(0.9 * len(ds))]:5.2f} mm   max {max(ds):5.2f} mm")
    print("\nfarthest:")
    for d, ref, owner, net, kind in sorted(rows, reverse=True)[:15]:
        print(f"  {d:6.2f} mm  {ref:7s} -> {owner:6s} {net}")


if __name__ == "__main__":
    main()
