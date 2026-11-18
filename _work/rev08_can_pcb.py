#!/usr/bin/env python3
"""
The vehicle CAN on the board (18 November 2026, before the Rev08 tag), as text edits (pcbnew is not used).

  1. J1503 becomes the 6-way JST-SH SM06B-SRSS-TB at the same point and angle: 1 GPS 3.3 V, 2 PPS, 3 ground,
     4 CANH, 5 CANL, 6 ground. Its pads move one pitch, so the vias under the old pins 1 to 4 now sit under the new
     pins 2 to 5 and only change net; pin 1 and pin 6 get their own. The GPS supply and PPS nets are lifted whole,
     to be routed again to F1501 and R1540/D1530.
  2. J1502 again, for its new pad nets: FPC pins 6 and 10 (were ground) carry the K26's CAN TX, whichever cable
     type is fitted, and pin 8 brings CAN RX; their via stubs are redone with those nets.
  3. The transceiver, the NOR pair, the ESD diode and the passives on the bottom of the same corner, beyond the
     carrier's edge (KiCad y > 107.25), in the free L below the GPS circuit.

Usage:  py _work/rev08_can_pcb.py <in.kicad_pcb> <out.kicad_pcb>
"""
import math
import os
import re
import sys
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rev08_pcb as P                                    # noqa: E402

U = lambda: str(uuid.uuid4())
J1502_AT = (197.4, 106.65, 180)
J1503_AT = (193.8, 112.6, 180)
H2 = (203.0, 112.25, 3.2)
VIA_Y_FPC, VIA_Y_JST = 109.5, 115.8
BOTTOM_BOX = (185.6, 107.6, 207.5, 118.7)
BOTTOM = [  # ref, anchor: near the pin each one serves
    ("D1531", (192.6, 117.4)), ("U1506", (189.0, 117.0)), ("C1550", (187.0, 115.0)),
    ("R1556", (187.0, 114.0)), ("R1557", (188.0, 114.0)),
    ("Q1530", (196.0, 117.6)), ("Q1531", (198.4, 117.6)),
    ("R1551", (197.4, 116.4)), ("R1552", (195.0, 116.4)), ("R1553", (196.2, 116.4)), ("R1554", (198.6, 116.4)),
    ("R1555", (193.8, 117.6)),
]


def seg(a, b, w, layer, net):
    return (f'\t(segment\n\t\t(start {a[0]:g} {a[1]:g})\n\t\t(end {b[0]:g} {b[1]:g})\n\t\t(width {w:g})\n'
            f'\t\t(layer "{layer}")\n\t\t(net "{net}")\n\t\t(uuid "{U()}")\n\t)\n')


def via(p, net):
    return (f'\t(via\n\t\t(at {p[0]:g} {p[1]:g})\n\t\t(size 0.45)\n\t\t(drill 0.2)\n'
            f'\t\t(layers "F.Cu" "B.Cu")\n\t\t(net "{net}")\n\t\t(uuid "{U()}")\n\t)\n')


def drop_items(t, pts, nets, tol=0.02):
    """Remove the segments with an end at one of pts, and the vias at one of pts, of the given nets."""
    out, pos, n = [], 0, 0
    for m in re.finditer(r'\n\t\((segment|via)\n(.*?)\n\t\)', t, re.S):
        b = m.group(2)
        net = re.search(r'\(net "([^"]*)"\)', b)
        if not net or net.group(1) not in nets:
            continue
        ends = [tuple(map(float, q)) for q in re.findall(r'\((?:start|end|at) ([-\d.]+) ([-\d.]+)\)', b)]
        if any(math.hypot(x - px, y - py) < tol for x, y in ends for px, py in pts):
            out.append(t[pos:m.start()])
            pos = m.end()
            n += 1
    out.append(t[pos:])
    return "".join(out), n


def rip_net(t, net):
    out, pos, n = [], 0, 0
    for m in re.finditer(r'\n\t\((segment|via|arc)\n(.*?)\n\t\)', t, re.S):
        if f'(net "{net}")' in m.group(2):
            out.append(t[pos:m.start()])
            pos = m.end()
            n += 1
    out.append(t[pos:])
    return "".join(out), n


def allowed_bottom(b):
    x0, y0, x1, y1 = b
    if not (BOTTOM_BOX[0] <= x0 and x1 <= BOTTOM_BOX[2] and BOTTOM_BOX[1] <= y0 and y1 <= BOTTOM_BOX[3]):
        return False
    cx, cy = max(x0, min(H2[0], x1)), max(y0, min(H2[1], y1))
    return math.hypot(cx - H2[0], cy - H2[1]) > H2[2] + 0.25


def main(src, dst):
    t = open(src, encoding="utf-8").read()
    comps, pins = P.netlist()
    fpc = {n: (round(204.4 - (n - 1), 4), 107.95) for n in range(1, 16)}
    old_jst = {n: (round(195.3 - (n - 1), 4), 114.6) for n in range(1, 5)}
    new_jst = {n: (round(196.3 - (n - 1), 4), 114.6) for n in range(1, 7)}
    # 1. the old stubs: J1503's pins and tabs, FPC pins 6 and 10 (ground until now)
    pts = [p for p in old_jst.values()] + [(p[0], VIA_Y_JST) for p in old_jst.values()]
    pts += [(191.0, 110.725), (191.0, 109.375), (196.6, 110.725)]
    for n in (6, 10):
        pts += [fpc[n], (fpc[n][0], 108.85), (fpc[n][0], VIA_Y_FPC)]
    t, n = drop_items(t, pts, {"GND", "/STATUS/GPS_3V3", "/STATUS/GPS_PPS_IN"})
    print(f"removed {n} old stub items")
    for net in ("/STATUS/GPS_3V3", "/STATUS/GPS_PPS_IN"):
        t, n = rip_net(t, net)
        print(f"lifted {n} items of {net}")
    # 2. J1503 and J1502 again, with the new pads and nets
    for ref, at in (("J1503", J1503_AT), ("J1502", J1502_AT)):
        for s, e, r in P.footprints(t):
            if r == ref:
                blk = P.place(P.lib_text(comps[ref]["footprint"]), comps[ref]["footprint"], ref, comps[ref],
                              pins[ref], *at, False)
                t = t[:s] + blk.strip("\n") + t[e:]
                break
        else:
            raise SystemExit(f"{ref} not on the board")
    # 3. the new stubs (top)
    items = []
    for n, net in ((6, "/STATUS/J9_CAN_TX6"), (10, "/STATUS/J9_CAN_TX10"), (8, "/STATUS/J9_CAN_RX")):
        x, y = fpc[n]
        v = (x, VIA_Y_FPC)
        items += [seg((x, y), v, 0.2, "F.Cu", net), via(v, net)]
    for n, net in ((1, "/STATUS/GPS_3V3"), (2, "/STATUS/GPS_PPS_IN"), (3, "GND"), (4, "/STATUS/CAN_H"),
                   (5, "/STATUS/CAN_L"), (6, "GND")):
        x, y = new_jst[n]
        v = (x, VIA_Y_JST)
        items += [seg((x, y), v, 0.2, "F.Cu", net), via(v, net)]
    items += [seg((190.0, 110.725), (190.0, 109.375), 0.3, "F.Cu", "GND"), via((190.0, 109.375), "GND")]
    items += [seg((197.6, 110.725), (fpc[7][0], VIA_Y_FPC), 0.3, "F.Cu", "GND")]
    s = t.rfind("\n\t(embedded_fonts")
    t = t[:s] + "\n" + "".join(items).rstrip("\n") + t[s:]
    # 4. the new bottom parts
    have = {r for _, _, r in P.footprints(t)}
    anchors = [(ref, comps[ref]["footprint"], xy, "B", allowed_bottom) for ref, xy in BOTTOM if ref not in have]
    packed = P.pack(t, comps, pins, anchors)
    s = max(e for _, e, _ in P.footprints(t))
    t = t[:s] + "\n" + "".join(packed).rstrip("\n") + t[s:]
    missing = [r for r in comps if r not in {x for _, _, x in P.footprints(t)}]
    if missing:
        print("not on the board:", missing)
    open(dst, "w", encoding="utf-8", newline="\n").write(t)
    print(f"J1503 and J1502 replaced, {len(packed)} of {len(anchors)} bottom parts packed -> {dst}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
