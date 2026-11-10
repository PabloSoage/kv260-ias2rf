#!/usr/bin/env python3
"""
Check the planes after any change to the routing (19 Oct 2026): no supply or signal track
may run on the GND planes (L2, L5), and signal tracks on L4 under the BGA cut the
+3V3_D background there.

Prints a dict: (layer, net) -> segments for every non-GND segment on In1/In4 (must be
empty), and 'L4-BGA' -> signal segments on In3 with an end inside the BGA box.

Usage:  py _work/layout/planechk.py board.kicad_pcb
"""

import re
import sys
from collections import Counter

BGA = (149.6, 140.6, 166.4, 158.4)
SEG = re.compile(r'\(segment\s*\(start ([-\d.]+) ([-\d.]+)\)\s*\(end ([-\d.]+) ([-\d.]+)\)'
                 r'\s*\(width [\d.]+\)\s*\(layer "([^"]+)"\)\s*\(net "([^"]*)"\)')


def supply(net):
    return net.startswith("+") or net == "-3V3"


def inside(x, y):
    return BGA[0] <= x <= BGA[2] and BGA[1] <= y <= BGA[3]


out = Counter()
for m in SEG.finditer(open(sys.argv[1], encoding="utf-8").read()):
    x0, y0, x1, y1 = map(float, m.group(1, 2, 3, 4))
    layer, net = m.group(5, 6)
    if layer in ("In1.Cu", "In4.Cu") and net != "GND":
        out[(layer, net)] += 1
    elif layer == "In3.Cu" and not supply(net) and (inside(x0, y0) or inside(x1, y1)):
        out["L4-BGA"] += 1
print(dict(out))
