#!/usr/bin/env python3
"""
The board changes made before the Rev08 tag (18 November 2026), as text edits (pcbnew is not used).

  1. J1501 becomes the HRO TYPE-C-31-E-17 (surface mount only), at the same point and angle; the copper of its
     nets under and round it is lifted, to be routed again (fastroute.py, the commands in docs/LAYOUT.md 6.8).
  2. The GPS PPS path of the STATUS sheet: J1502 (15-way 1 mm FPC to the KV260's J9) at the board's top edge east
     of the IAS1 tongue, the cable leaving towards the carrier; J1503 (the GPS receiver's JST-SH) below it; the
     buffer, ESD, PTC and passives on the bottom face of the same corner, which lies beyond the carrier's edge
     (KiCad y > 107.25), so nothing there faces the carrier.
  3. A ground stitching via that J1502's east tab covers moves 0.85 mm up, and a via per grounded or driven FPC
     contact, each with its stub, is placed beside the contact row.
The skew meanders of LAYOUT 6.8 are made on the input before this script (meander.py).

Usage:  py _work/rev08_final_pcb.py <in.kicad_pcb> <out.kicad_pcb>
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
J1501_AT = (133.6, 93.4, 90)
J1502_AT = (197.4, 106.65, 180)       # cable side on the board edge (y 102.25); courtyard clear of H2
J1503_AT = (193.8, 112.6, 180)         # receptacle opening towards the carrier, like the FFC
USB_NETS = ["/STATUS/USB_DP", "/STATUS/USB_DN", "/STATUS/USB_CC1", "/STATUS/USB_CC2", "VBUS_USB"]
USB_BOX = (130.9, 88.4, 136.45, 98.45)
H2 = (203.0, 112.25, 3.2)
BOTTOM_BOX = (187.0, 107.8, 199.8, 115.6)   # beyond the carrier's edge; ETH_RSTN runs at y 116.3
BOTTOM = [  # ref, anchor (x, y): next to the pin each one serves
    ("D1530", (194.3, 113.9)), ("R1540", (193.3, 113.4)), ("R1541", (192.2, 112.6)), ("U1505", (191.0, 111.4)),
    ("C1542", (189.4, 111.0)), ("R1542", (192.6, 110.2)), ("R1543", (196.0, 111.0)), ("F1501", (196.6, 113.4)),
    ("C1540", (198.6, 112.4)), ("C1541", (198.6, 111.0)),
]


def seg(a, b, w, layer, net):
    return (f'\t(segment\n\t\t(start {a[0]:g} {a[1]:g})\n\t\t(end {b[0]:g} {b[1]:g})\n\t\t(width {w:g})\n'
            f'\t\t(layer "{layer}")\n\t\t(net "{net}")\n\t\t(uuid "{U()}")\n\t)\n')


def via(p, net):
    return (f'\t(via\n\t\t(at {p[0]:g} {p[1]:g})\n\t\t(size 0.45)\n\t\t(drill 0.2)\n'
            f'\t\t(layers "F.Cu" "B.Cu")\n\t\t(net "{net}")\n\t\t(uuid "{U()}")\n\t)\n')


def pad_xy(at, local, bottom=False):
    x, y, a = at
    px, py = local
    if bottom:
        py = -py
    dx, dy = P._rot(px, py, a)
    return round(x + dx, 4), round(y + dy, 4)


def allowed_bottom(b):
    x0, y0, x1, y1 = b
    if not (BOTTOM_BOX[0] <= x0 and x1 <= BOTTOM_BOX[2] and BOTTOM_BOX[1] <= y0 and y1 <= BOTTOM_BOX[3]):
        return False
    cx, cy = max(x0, min(H2[0], x1)), max(y0, min(H2[1], y1))
    return math.hypot(cx - H2[0], cy - H2[1]) > H2[2] + 0.25


def main(src, dst):
    t = open(src, encoding="utf-8").read()
    comps, pins = P.netlist()
    # 1. J1501
    for s, e, ref in P.footprints(t):
        if ref == "J1501":
            blk = P.place(P.lib_text(comps["J1501"]["footprint"]), comps["J1501"]["footprint"], "J1501",
                          comps["J1501"], pins["J1501"], *J1501_AT, False)
            t = t[:s] + blk.strip("\n") + t[e:]
            break
    for net in USB_NETS:
        t = P.rip(t, net, USB_BOX, mode="any")
    t = P.rip(t, "GND", USB_BOX, mode="any")
    # 2. the moved stitching via
    old = re.search(r'\n\t\(via\n\t\t\(at 207\.2 104\.75\)\n.*?\n\t\)', t, re.S)
    assert old, "stitching via at 207.2 104.75 not found"
    t = t[:old.start()] + "\n" + via((207.3, 103.9), "GND").rstrip("\n") + t[old.end():]
    # 3. J1502, J1503
    have = {r for _, _, r in P.footprints(t)}
    blocks = []
    for ref, at in (("J1502", J1502_AT), ("J1503", J1503_AT)):
        assert ref not in have
        blocks.append(P.place(P.lib_text(comps[ref]["footprint"]), comps[ref]["footprint"], ref, comps[ref],
                              pins[ref], *at, False))
    s = max(e for _, e, _ in P.footprints(t))
    t = t[:s] + "\n" + "".join(blocks).rstrip("\n") + t[s:]
    # 4. FPC and JST contacts: a via beside each, with its stub (top)
    items = []
    fpc = {n: pad_xy(J1502_AT, (-7.0 + n - 1, -1.30)) for n in range(1, 16)}
    for n, net, vy, dx in ((4, "/STATUS/J9_PPS4", 109.4, -0.5), (6, "GND", 109.5, 0), (7, "GND", 109.5, 0),
                           (9, "GND", 109.5, 0), (10, "GND", 109.5, 0), (12, "/STATUS/J9_PPS12", 109.5, 0)):
        x, y = fpc[n]
        v = (round(x + dx, 4), vy)
        items += [seg((x, y), (x, 108.85), 0.2, "F.Cu", net), seg((x, 108.85), v, 0.2, "F.Cu", net), via(v, net)]
    for x in (-9.2, 9.2):                               # the fixing tabs (MP, ground)
        tx, ty = pad_xy(J1502_AT, (x, 1.30))
        if tx < 195:
            v = (tx, 107.25)
            items += [seg((tx, ty), v, 0.3, "F.Cu", "GND"), via(v, "GND")]
        else:
            items += [seg((tx, ty), (207.3, 103.9), 0.3, "F.Cu", "GND")]
    jst = {str(n): pad_xy(J1503_AT, (-1.5 + n - 1, -2.0)) for n in range(1, 5)}
    for n, net in (("1", "/STATUS/GPS_3V3"), ("2", "/STATUS/GPS_PPS_IN"), ("3", "GND"), ("4", "GND")):
        x, y = jst[n]
        v = (x, round(y + 1.2, 4))
        items += [seg((x, y), v, 0.2, "F.Cu", net), via(v, net)]
    for x in (-2.8, 2.8):
        tx, ty = pad_xy(J1503_AT, (x, 1.875))
        if tx < 194:
            v = (tx, round(ty - 1.35, 4))
            items += [seg((tx, ty), v, 0.3, "F.Cu", "GND"), via(v, "GND")]
        else:                                           # the east tab shares J1502 pin 9's via
            items += [seg((tx, ty), (fpc[9][0], 109.5), 0.3, "F.Cu", "GND")]
    s = t.rfind("\n\t(embedded_fonts")
    t = t[:s] + "\n" + "".join(items).rstrip("\n") + t[s:]
    # 5. the bottom parts
    anchors = [(ref, comps[ref]["footprint"], xy, "B", allowed_bottom) for ref, xy in BOTTOM]
    packed = P.pack(t, comps, pins, anchors)
    s = max(e for _, e, _ in P.footprints(t))
    t = t[:s] + "\n" + "".join(packed).rstrip("\n") + t[s:]
    missing = [r for r in comps if r not in {x for _, _, x in P.footprints(t)}]
    if missing:
        print("not on the board:", missing)
    open(dst, "w", encoding="utf-8", newline="\n").write(t)
    print(f"J1501 replaced, J1502/J1503 placed, {len(packed)} of {len(BOTTOM)} bottom parts packed -> {dst}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
