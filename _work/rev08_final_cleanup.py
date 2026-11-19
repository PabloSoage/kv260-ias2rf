#!/usr/bin/env python3
"""
Rev08 final re-audit (19 November 2026, docs/AUDIT_Rev08.md section 5): the DRC warnings that were left on the board,
cleared as text edits (no pcbnew). None of them broke a connection; one was a drilling risk, the rest dead copper.

  1. hole_to_hole: two vias of Net-(C1414-Pad2) at 0.30 mm pitch (0.10 mm between drills, the rule is 0.25 mm).
     The via at (146.5, 118.55) and its dead F.Cu stub go; C1415 pad 1 joins the via at (146.2, 118.6) on B.Cu.
  2. Vias in a pad that reach no other layer: a dead drill and a 1.6 mm via stub on the line, nothing else (the
     board's vias in pads are filled and capped, so solder wicking is not the issue): Y401 pad 7 (XO_SDA),
     C927 pad 1 (U902 RFOUT2), FL1303 pad 1 (VU_LP1G_IN), C1332 pad 2 (VU_ATT_IN).
  3. Through vias used as a junction between two tracks on one layer: VU_SCLK (B.Cu), VU_TCXO_OUT (In2), VU_RESETX
     (B.Cu). Each via becomes a short track on that layer; VU_RESETX's 0.58 mm dead end past the via goes too.
  4. Dead track stubs on GND, +3V3_D and +2V8_RF (0.01-0.65 mm), and a chain of four 0.125 mm +1V8_D pieces lying
     on top of the 1 mm +1V8_D diagonal they duplicate, with the 0.7 mm piece after them (the diagonal now
     meets the vertical at its own end, (130.8, 148.15)).

Usage:  py _work/rev08_final_cleanup.py <in.kicad_pcb> <out.kicad_pcb>
"""
import math
import re
import sys
import uuid

U = lambda: str(uuid.uuid4())
NUM = r"(-?[\d.]+)"
SEG = re.compile(r'\t\(segment\n\t\t\(start ' + NUM + ' ' + NUM + r'\)\n\t\t\(end ' + NUM + ' ' + NUM +
                 r'\)\n\t\t\(width ([\d.]+)\)\n\t\t\(layer "([^"]+)"\)\n\t\t\(net "([^"]*)"\)\n\t\t\(uuid "[^"]+"\)\n\t\)\n')
VIA = re.compile(r'\t\(via\n\t\t\(at ' + NUM + ' ' + NUM + r'\)\n(?:\t\t[^\n]*\n)*?\t\t\(net "([^"]*)"\)\n(?:\t\t[^\n]*\n)*?\t\)\n')

# (net, x, y)
DROP_VIAS = [
    ("Net-(C1414-Pad2)", 146.5, 118.55),
    ("/XO_SDA", 186.35, 142.25),
    ("Net-(U902-RFOUT2)", 178.3, 206.35),
    ("/RX_VU/VU_LP1G_IN", 122.97, 110.75),
    ("/RX_VU/VU_ATT_IN", 149.5, 125.17),
    ("/RX_VU/VU_SCLK", 125.85, 124.58),
    ("/RX_VU/VU_TCXO_OUT", 132.3, 111.75),
    ("/RX_VU/VU_RESETX", 124.75, 121.3),
]
# (net, layer, (x1, y1), (x2, y2)) in either direction
DROP_SEGS = [
    ("Net-(C1414-Pad2)", "F.Cu", (146.25, 118.55), (146.5, 118.55)),
    ("/RX_VU/VU_RESETX", "B.Cu", (124.175, 121.3), (125.225, 121.3)),
    ("GND", "F.Cu", (113.5, 109.524074), (113.5, 109.5)),
    ("GND", "F.Cu", (134.781, 87.9036), (134.8, 87.9)),
    ("GND", "F.Cu", (134.8, 87.9), (135.1, 88.2)),
    ("GND", "B.Cu", (113.409375, 124.090625), (113.4, 124.1)),
    ("GND", "B.Cu", (144.75, 114.918125), (144.75, 114.9)),
    ("+3V3_D", "B.Cu", (103.94, 127.45), (103.5, 127.45)),
    ("+1V8_D", "F.Cu", (129.946447, 147.146447), (130.034835, 147.234835)),
    ("+1V8_D", "F.Cu", (130.034835, 147.234835), (130.123223, 147.323223)),
    ("+1V8_D", "F.Cu", (130.123223, 147.323223), (130.211612, 147.411612)),
    ("+1V8_D", "F.Cu", (130.211612, 147.411612), (130.3, 147.5)),
    ("+1V8_D", "F.Cu", (130.3, 147.5), (130.8, 148.0)),
    ("+1V8_D", "F.Cu", (130.8, 148.0), (130.8, 148.5)),
    ("+2V8_RF", "B.Cu", (107.070833, 121.6), (107.05, 121.6)),
    ("+2V8_RF", "B.Cu", (146.5, 128.15), (146.5, 127.5)),
]
# (net, layer, width, a, b)
ADD_SEGS = [
    ("Net-(C1414-Pad2)", "B.Cu", 0.2, (146.2, 118.6), (146.62, 118.47)),
    ("/RX_VU/VU_SCLK", "B.Cu", 0.1, (125.85, 124.58), (126.0, 124.45)),
    ("/RX_VU/VU_TCXO_OUT", "In2.Cu", 0.1, (132.3, 111.75), (132.5, 111.675)),
    ("/RX_VU/VU_RESETX", "B.Cu", 0.1, (124.75, 121.3), (125.225, 121.3)),
    ("+1V8_D", "F.Cu", 1.0, (130.8, 148.15), (130.8, 148.5)),
]
EXTRA_DROP = []          # filled from the command line for iterative passes: net,layer,x1,y1,x2,y2


def near(a, b, tol=1e-4):
    return math.hypot(a[0] - b[0], a[1] - b[1]) < tol


def main(src, dst):
    s = open(src, encoding="utf-8").read()
    for net, x, y in DROP_VIAS:
        hits = [m for m in VIA.finditer(s) if m.group(3) == net and near((float(m.group(1)), float(m.group(2))), (x, y))]
        assert len(hits) == 1, ("via", net, x, y, len(hits))
        m = hits[0]
        s = s[:m.start()] + s[m.end():]
    for net, layer, a, b in DROP_SEGS + EXTRA_DROP:
        hits = []
        for m in SEG.finditer(s):
            if m.group(7) != net or m.group(6) != layer:
                continue
            p, q = (float(m.group(1)), float(m.group(2))), (float(m.group(3)), float(m.group(4)))
            if (near(p, a) and near(q, b)) or (near(p, b) and near(q, a)):
                hits.append(m)
        assert len(hits) == 1, ("seg", net, layer, a, b, len(hits))
        m = hits[0]
        s = s[:m.start()] + s[m.end():]
    k = s.index("\t(segment\n")
    add = "".join(f'\t(segment\n\t\t(start {a[0]:g} {a[1]:g})\n\t\t(end {b[0]:g} {b[1]:g})\n\t\t(width {w:g})\n'
                  f'\t\t(layer "{layer}")\n\t\t(net "{net}")\n\t\t(uuid "{U()}")\n\t)\n' for net, layer, w, a, b in ADD_SEGS)
    s = s[:k] + add + s[k:]
    open(dst, "w", encoding="utf-8", newline="\n").write(s)
    print("dropped %d vias, %d segments; added %d segments" % (len(DROP_VIAS), len(DROP_SEGS) + len(EXTRA_DROP), len(ADD_SEGS)))


if __name__ == "__main__":
    for e in sys.argv[3:]:
        n, l, x1, y1, x2, y2 = e.split(",")
        EXTRA_DROP.append((n, l, (float(x1), float(y1)), (float(x2), float(y2))))
    main(sys.argv[1], sys.argv[2])
