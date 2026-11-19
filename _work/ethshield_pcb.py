#!/usr/bin/env python3
"""
Rev08, 19 November 2026: the RJ45's shield RC (sheet CONTROL, _work/ethshield_schematic.py) onto the board, as a
text edit (no pcbnew).

  1. J1201's two SH tabs take the net ETH_SHIELD from the schematic (the inner ground planes then clear them).
  2. C1223 (1 nF 2 kV, 1206) and R1218 (1 Mohm, 0603) on the bottom of the jack's tab (x 208-229, past the KV260's
     edge, so nothing faces them), just south of the SH tab at (216.15, 119.0), pin 1 towards it. The tab to both
     pad 1s on B.Cu; both pad 2s to one ground via south of C1223. Nothing of ground lies between C1223's pads, so
     the creepage from the shield to ground is the capacitor's own pad gap. The southern SH tab joins the northern
     one by a track down the jack's middle (its shell joins them inside; the inner ground planes did before).
     The RC is the RF and ESD bond of an isolated port, not a hi-pot barrier: the planes clear ETH_SHIELD by their
     usual clearance.

Usage:  py _work/ethshield_pcb.py <in.kicad_pcb> <out.kicad_pcb>
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rev08_pcb as P                                    # noqa: E402
import kvpwr_pcb as K                                    # noqa: E402

NET = "/CONTROL/ETH_SHIELD"


def board_net(n):
    return NET if n == "ETH_SHIELD" else n


def main(src, dst):
    t = open(src, encoding="utf-8").read()
    assert NET not in t, "already applied"
    comps, pins = P.netlist()
    assert pins["J1201"]["SH"] == NET
    changed = 0
    for s, e, ref in reversed(P.footprints(t)):
        if ref != "J1201":
            continue

        def fix(blk):
            nonlocal changed
            if not blk.startswith('(pad "SH"'):
                return blk
            cur = K.NET_LINE.search(blk)
            changed += 1
            return blk[:cur.start()] + f'\n\t\t\t(net "{NET}")' + blk[cur.end():]
        t = t[:s] + P.map_blocks(t[s:e], r'\(pad "', fix) + t[e:]
    assert changed == 2, changed
    blocks = []
    for ref, (x, y, a, side) in PLACE.items():
        lib = comps[ref]["footprint"]
        blocks.append(P.place(P.lib_text(lib), lib, ref, comps[ref], pins[ref], x, y, a, side == "B"))
    s = max(e for _, e, _ in P.footprints(t))
    t = t[:s] + "\n" + "".join(blocks).rstrip("\n") + t[s:]
    cu = [K.seg(a, b, w, L, board_net(n)) for a, b, w, L, n in SEGS] + [K.via(x, y, d, n) for x, y, d, n in VIAS]
    s = t.rfind("\n\t(embedded_fonts")
    s = s if s > 0 else t.rfind("\n)")
    t = t[:s] + "\n" + "".join(cu).rstrip("\n") + t[s:]
    open(dst, "w", encoding="utf-8", newline="\n").write(t)
    print(f"{len(blocks)} parts, {len(SEGS)} tracks, {len(VIAS)} vias, {changed} SH pads -> {dst}")


PLACE = {
    "C1223": (216.15, 122.65, 270, "B"),
    "R1218": (214.25, 122.05, 270, "B"),
}

# (start, end, width, layer, net)
SEGS = [
    ((216.15, 121.175), (216.15, 119.7), 0.4, "B.Cu", "ETH_SHIELD"),
    ((214.25, 121.225), (215.65, 121.2), 0.3, "B.Cu", "ETH_SHIELD"),
    ((216.15, 124.125), (216.45, 125.025), 0.4, "B.Cu", "GND"),
    ((214.25, 122.875), (215.4, 124), 0.3, "B.Cu", "GND"),
    ((215.4, 124), (216, 124), 0.3, "B.Cu", "GND"),
    # the southern SH tab to the northern one's copper (the jack's shell joins them inside; the planes used to)
    ((216.15, 134.495), (216.15, 126.25), 0.4, "B.Cu", "ETH_SHIELD"),
    ((216.15, 126.25), (217.5, 124.9), 0.4, "B.Cu", "ETH_SHIELD"),
    ((217.5, 124.9), (217.5, 123.2), 0.4, "B.Cu", "ETH_SHIELD"),
    ((217.5, 123.2), (216.2, 121.9), 0.4, "B.Cu", "ETH_SHIELD"),
    ((216.2, 121.9), (216.2, 121.35), 0.4, "B.Cu", "ETH_SHIELD"),
]

VIAS = [
    (216.45, 125.025, 0.45, "GND"),
]

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
