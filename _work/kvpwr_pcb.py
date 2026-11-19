#!/usr/bin/env python3
"""
Rev08, 19 November 2026: the single power entry (sheet KVPWR, docs/POWER_SPEC.md section 1.4) onto the board, as a
text edit (no pcbnew).

  1. J1001's pads and F1001's pad 1 take their new nets from the schematic: the jack's sleeve and centre pin are
     GND_IN and VIN_JACK, which reach the rest of the board only through L1004; F1001 now starts at VIN_J.
  2. The old J1001 -> F1001 track (net Net-(F1001-Pad1)) goes, and so does D1003's ground stub to the jack's sleeve
     (D1003 keeps its two ground vias next to its pad).
  3. The KVPWR parts go in at PLACE: all on the bottom, in the overhang past the KV260's edge (y > 117.25), except
     J1004, the right-angle JST VH on the top at the back edge, next to J1001.
  4. Tracks and vias at SEGS and VIAS: VIN_JACK 2.0 mm from the jack to L1004; VIN_J 1.5 mm from L1004 to four vias
     and on the top to F1001; the control signals of U1010 at 0.25 mm; a via (or two) at every ground pad.
  5. Copper pours on B.Cu at ZONES for the power nets (GND_IN, VIN_J to Q1010 and the U1010 sense pins, KV_IN from
     Q1010's drain to U1010's IN, +12V_KV from U1010's OUT to J1004), over a local ground pour of lower priority.
     The repository board is kept unfilled; make_fab fills it.
  6. C1072's reference (top, at J1004's back) moves to the assembly drawing (F.Fab), as most passives' are.

Usage:  py _work/kvpwr_pcb.py <in.kicad_pcb> <out.kicad_pcb>
"""
import os
import re
import sys
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rev08_pcb as P                                    # noqa: E402

U = lambda: str(uuid.uuid4())
NET_LINE = re.compile(r'\n\t\t\t\(net "((?:[^"\\]|\\.)*)"\)')


def board_net(n):
    """The layout's short names -> the schematic's (the sheet's local and hierarchical nets carry /KVPWR/)."""
    return n if n == "GND" else "/KVPWR/" + n


def seg(a, b, w, layer, net):
    return (f'\t(segment\n\t\t(start {a[0]:g} {a[1]:g})\n\t\t(end {b[0]:g} {b[1]:g})\n\t\t(width {w:g})\n'
            f'\t\t(layer "{layer}")\n\t\t(net "{net}")\n\t\t(uuid "{U()}")\n\t)\n')


def via(x, y, d, net):
    drill = 0.3 if d >= 0.6 else 0.2
    return (f'\t(via\n\t\t(at {x:g} {y:g})\n\t\t(size {d:g})\n\t\t(drill {drill:g})\n'
            f'\t\t(layers "F.Cu" "B.Cu")\n\t\t(net "{net}")\n\t\t(uuid "{U()}")\n\t)\n')


def zone(net, prio, pts, name):
    """The same settings as the board's other B.Cu ground pour (L8 RF band GND)."""
    xy = " ".join(f"(xy {x:g} {y:g})" for x, y in pts)
    return (f'\t(zone\n\t\t(net "{net}")\n\t\t(layer "B.Cu")\n\t\t(uuid "{U()}")\n\t\t(name "{name}")\n'
            f'\t\t(hatch edge 0.5)\n\t\t(priority {prio})\n\t\t(connect_pads yes\n\t\t\t(clearance 0.3)\n\t\t)\n'
            f'\t\t(min_thickness 0.25)\n\t\t(fill yes\n\t\t\t(thermal_gap 0.3)\n\t\t\t(thermal_bridge_width 0.3)\n'
            f'\t\t\t(island_removal_mode 0)\n\t\t)\n\t\t(polygon\n\t\t\t(pts\n\t\t\t\t{xy}\n\t\t\t)\n\t\t)\n\t)\n')


def items(t):
    for m in re.finditer(r'\n\t\((segment|via)\n(.*?)\n\t\)', t, re.S):
        yield m.start(), m.end(), m.group(1), m.group(2)


def main(src, dst):
    t = open(src, encoding="utf-8").read()
    assert '"/KVPWR/' not in t, "already applied"
    comps, pins = P.netlist()
    # 1. new nets on J1001 and F1001
    changed = 0
    for s, e, ref in reversed(P.footprints(t)):
        if ref not in ("J1001", "F1001"):
            continue
        want = pins[ref]

        def fix(blk):
            nonlocal changed
            m = re.match(r'\(pad "([^"]*)"', blk)
            num, body = m.group(1), blk[m.end():]
            cur = NET_LINE.search(body)
            if num not in want or not cur or cur.group(1) == want[num]:
                return blk
            changed += 1
            return f'(pad "{num}"' + body[:cur.start()] + f'\n\t\t\t(net "{want[num]}")' + body[cur.end():]
        t = t[:s] + P.map_blocks(t[s:e], r'\(pad "', fix) + t[e:]
    assert changed == 3, changed
    # 2. old copper
    out, pos, gone = [], 0, 0
    for s, e, kind, b in items(t):
        if '(net "Net-(F1001-Pad1)")' in b or ("(start 98.2 147.4)" in b and "(end 97.2 150)" in b and '"GND"' in b):
            out.append(t[pos:s])
            pos = e
            gone += 1
    out.append(t[pos:])
    t = "".join(out)
    assert gone == 3 and "Net-(F1001-Pad1)" not in t, gone
    # 3. parts
    blocks = []
    for ref, (x, y, a, side) in PLACE.items():
        lib = comps[ref]["footprint"]
        b = P.place(P.lib_text(lib), lib, ref, comps[ref], pins[ref], x, y, a, side == "B")
        for old, new in MODELS.items():
            b = b.replace(f'(model "{old}"', f'(model "{new}"')
        blocks.append(b)
    s = max(e for _, e, _ in P.footprints(t))
    t = t[:s] + "\n" + "".join(blocks).rstrip("\n") + t[s:]
    # 6. C1072's reference
    for s0, e0, ref in P.footprints(t):
        if ref == "C1072":
            f, n = re.subn(r'(\(property "Reference" "C1072"\s*\(at [^)]*\)\s*)\(layer "F\.SilkS"\)',
                           r'\1(layer "F.Fab")', t[s0:e0])
            assert n == 1
            t = t[:s0] + f + t[e0:]
            break
    # 4, 5. copper
    cu = [seg(a, b, w, L, board_net(n)) for a, b, w, L, n in SEGS] + [via(x, y, d, board_net(n)) for x, y, d, n in VIAS]
    cu += [zone(board_net(n), p, pts, f"KVPWR {n}") for n, p, pts in ZONES]
    s = t.rfind("\n\t(embedded_fonts")
    s = s if s > 0 else t.rfind("\n)")
    t = t[:s] + "\n" + "".join(cu).rstrip("\n") + t[s:]
    open(dst, "w", encoding="utf-8", newline="\n").write(t)
    print(f"{len(blocks)} parts, {len(SEGS)} tracks, {len(VIAS)} vias, {len(ZONES)} pours, {changed} pad nets, "
          f"{gone} old items removed -> {dst}")


# ---------------------------------------------------------------- the layout
# x, y, rotation, side (a bottom part is mirrored about its x axis, then turned)
# 3-D models the stock footprints name but KiCad 10 does not ship: the plain HTSSOP-20 body, and a JST VH model
# drawn from the catalogue (mech/models3d)
MODELS = {
    "${KICAD10_3DMODEL_DIR}/Package_SO.3dshapes/HTSSOP-20-1EP_4.4x6.5mm_P0.65mm_EP3.4x6.5mm_Mask2.96x2.96mm.step":
        "${KICAD10_3DMODEL_DIR}/Package_SO.3dshapes/HTSSOP-20-1EP_4.4x6.5mm_P0.65mm_EP3.4x6.5mm.step",
    "${KICAD10_3DMODEL_DIR}/Connector_JST.3dshapes/JST_VH_B2PS-VH_1x02_P3.96mm_Horizontal.step":
        "${KIPRJMOD}/mech/models3d/JST_VH_B2PS-VH_1x02_P3.96mm_Horizontal.step",
}

PLACE = {
    "L1004": (100.25, 161.75, 270, "B"),
    "J1004": (103.9, 189, 270, "F"),
    "U1010": (102.25, 183.75, 0, "B"),
    "Q1010": (95.75, 186, 0, "B"),
    "Q1011": (92.25, 182, 90, "B"),
    "C1093": (97.25, 179.25, 0, "B"),
    "R1041": (94.75, 178.5, 90, "B"),
    "R1040": (93.25, 178.5, 90, "B"),
    "R1042": (97.25, 177.5, 0, "B"),
    "R1043": (107.75, 180.5, 0, "B"),
    "C1094": (92.05, 186.5, 270, "B"),
    "C1095": (108, 186.5, 90, "B"),
    "D1004": (111, 186.5, 90, "B"),
}

# (start, end, width, layer, net)
SEGS = [
    ((103.2, 150), (103.2, 156), 2, "B.Cu", "VIN_JACK"),
    ((103.2, 156), (102.4, 156.8), 2, "B.Cu", "VIN_JACK"),
    ((106.6, 155), (107.4, 155), 0.6, "F.Cu", "VIN_J"),
    ((106.6, 155), (107.4, 155), 0.6, "B.Cu", "VIN_J"),
    ((106.6, 155), (106.034, 155.566), 0.6, "F.Cu", "VIN_J"),
    ((106.6, 155), (106.034, 155.566), 0.6, "B.Cu", "VIN_J"),
    ((106.6, 155), (105.827, 154.793), 0.6, "F.Cu", "VIN_J"),
    ((106.6, 155), (105.827, 154.793), 0.6, "B.Cu", "VIN_J"),
    ((102, 166), (105.4, 166), 1.5, "B.Cu", "VIN_J"),
    ((105.4, 166), (109.5, 161.9), 1.5, "B.Cu", "VIN_J"),
    ((109.5, 161.9), (109.5, 156.55), 1.5, "B.Cu", "VIN_J"),
    ((109.5, 156.55), (108.1, 155.15), 1.5, "B.Cu", "VIN_J"),
    ((108.1, 155.15), (107.65, 155.15), 1.5, "B.Cu", "VIN_J"),
    ((107.5, 151.637), (107.5, 154.75), 1.5, "F.Cu", "VIN_J"),
    ((99.39, 180.825), (96.475, 180.825), 0.25, "B.Cu", "KV_DVDT"),
    ((96.475, 180.825), (96.475, 179.25), 0.25, "B.Cu", "KV_DVDT"),
    ((99.39, 182.125), (95.62, 182.125), 0.25, "B.Cu", "KV_OVP"),
    ((95.62, 182.125), (95.62, 177.6), 0.25, "B.Cu", "KV_OVP"),
    ((95.62, 177.6), (96.425, 177.6), 0.25, "B.Cu", "KV_OVP"),
    ((95.62, 177.6), (94.75, 177.6), 0.25, "B.Cu", "KV_OVP"),
    ((99.39, 182.775), (95.1, 182.775), 0.25, "B.Cu", "KV_UVLO"),
    ((95.1, 182.775), (95.1, 179.325), 0.25, "B.Cu", "KV_UVLO"),
    ((99.39, 183.425), (94.55, 183.425), 0.3, "B.Cu", "VIN_J"),
    ((99.39, 183.95), (93.2, 183.95), 0.25, "B.Cu", "KV_DRV"),
    ((93.2, 183.95), (93.2, 183.4), 0.25, "B.Cu", "KV_DRV"),
    ((99.39, 184.725), (97.9, 184.725), 0.25, "B.Cu", "KV_BGATE"),
    ((97.9, 184.725), (97.62, 184.45), 0.25, "B.Cu", "KV_BGATE"),
    ((97.62, 184.45), (94.25, 184.45), 0.25, "B.Cu", "KV_BGATE"),
    ((94.25, 184.45), (94.25, 185.025), 0.25, "B.Cu", "KV_BGATE"),
    ((93.45, 185.2), (94.25, 185.025), 0.25, "B.Cu", "KV_BGATE"),
    ((92.25, 181.06), (91.574, 181.241), 0.25, "B.Cu", "KV_BGATE"),
    ((91.574, 181.241), (93.45, 185.2), 0.2, "In5.Cu", "KV_BGATE"),
    ((93.25, 177.675), (94.5, 178.95), 0.25, "B.Cu", "KV_UVLO"),
    ((94.5, 178.95), (94.5, 179.1), 0.25, "B.Cu", "KV_UVLO"),
    ((105.112, 180.825), (105.15, 180.75), 0.25, "B.Cu", "KV_ILIM"),
    ((105.15, 180.75), (106.7, 180.75), 0.25, "B.Cu", "KV_ILIM"),
    ((98.025, 179.25), (98.025, 180.1), 0.4, "B.Cu", "GND"),
    ((98.075, 177.5), (98.825, 177.5), 0.4, "B.Cu", "GND"),
    ((99.3875, 181.475), (98.137, 181.475), 0.4, "B.Cu", "GND"),
    ((105.112, 181.475), (106.263, 181.475), 0.4, "B.Cu", "GND"),
    ((105.112, 184.075), (106.263, 184.075), 0.4, "B.Cu", "GND"),
    ((108.575, 180.5), (109.325, 180.5), 0.4, "B.Cu", "GND"),
    ((92.05, 187.975), (92.296, 188.893), 0.4, "B.Cu", "GND"),
    ((92.05, 187.975), (91.804, 187.057), 0.4, "B.Cu", "GND"),
    ((108, 185.025), (107.754, 184.107), 0.4, "B.Cu", "GND"),
    ((108, 185.025), (108.525, 184.116), 0.4, "B.Cu", "GND"),
    ((111, 184.5), (109.696, 184.151), 0.4, "B.Cu", "GND"),
    ((111, 184.5), (112.304, 184.151), 0.4, "B.Cu", "GND"),
]

# (x, y, diameter, net): 0.6 mm vias have a 0.3 mm drill, 0.45 mm ones 0.2 mm
VIAS = [
    (106.6, 155, 0.6, "VIN_J"),
    (107.4, 155, 0.6, "VIN_J"),
    (106.034, 155.566, 0.6, "VIN_J"),
    (105.827, 154.793, 0.6, "VIN_J"),
    (93.45, 185.2, 0.45, "KV_BGATE"),
    (91.574, 181.241, 0.45, "KV_BGATE"),
    (97.288, 166.7, 0.6, "GND"),
    (99.712, 165.3, 0.6, "GND"),
    (100.1, 166, 0.6, "GND"),
    (99.45, 164.355, 0.6, "GND"),
    (100.268, 164.232, 0.6, "GND"),
    (97.2, 163.748, 0.6, "GND"),
    (99.9, 163.575, 0.6, "GND"),
    (98.025, 180.1, 0.45, "GND"),
    (98.825, 177.5, 0.45, "GND"),
    (98.137, 181.475, 0.45, "GND"),
    (106.263, 181.475, 0.45, "GND"),
    (106.263, 184.075, 0.45, "GND"),
    (109.325, 180.5, 0.45, "GND"),
    (92.296, 188.893, 0.45, "GND"),
    (91.804, 187.057, 0.45, "GND"),
    (107.754, 184.107, 0.45, "GND"),
    (108.525, 184.116, 0.45, "GND"),
    (109.696, 184.151, 0.45, "GND"),
    (112.304, 184.151, 0.45, "GND"),
]

# (net, priority, outline on B.Cu): the local ground pour has priority 1, under the power pours
ZONES = [
    ("GND_IN", 5, [(95.4, 148.6), (99.6, 148.6), (99.6, 159), (95.4, 159)]),
    ("VIN_J", 5, [(100.9, 164.6), (103.2, 164.6), (103.2, 170.2), (95.6, 170.2), (95.6, 176), (94, 176), (94, 180.5),
                  (94.9, 180.5), (94.9, 188.6), (93.3, 188.6), (93.3, 186.3), (90.6, 186.3), (90.6, 167.6),
                  (100.9, 167.6)]),
    ("KV_IN", 5, [(95.4, 184.9), (100.2, 184.9), (100.2, 187.3), (95.4, 187.3)]),
    ("+12V_KV", 5, [(104.3, 185.05), (112.2, 185.05), (112.2, 190.6), (102.5, 190.6), (102.5, 187.5), (104.3, 187.5)]),
    ("GND", 1, [(89.3, 160), (112.6, 160), (112.6, 197), (89.3, 197)]),
]

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
