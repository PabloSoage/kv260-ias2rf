#!/usr/bin/env python3
"""
Build the Rev03 board, CSI2-KRIA-KV260_Rev01.kicad_pcb, from the schematic:
outline, 6-layer stackup, every footprint with its nets, and a first
placement. Routing is not attempted here.

What is fixed by measurement, and kept exactly:
  * the two Hirose connectors (J101 = IAS1, J102 = IAS0), copied from the
    original Allied Vision board with their position, face and rotation -
    they are what registers the adapter on the KV260 (INTERFACE_SPEC §5.3);
  * the two M3 holes through the KV260's corner holes (94.0/203.0, 112.25);
  * the upper, U-shaped part of the original outline, which is known to
    clear the carrier. Its IAS0 tongue's right edge moves from x 144.9 to
    142.4, 1.5 mm clear of the carrier's J18 jumper (INTERFACE_SPEC §5.3).

What is new:
  * the outline grows outward (+y) to y 202.75: 119 x 120 mm. The parts'
    courtyards add up to 5700 mm2; at 119 x 90 that would be 75 % of the
    board, one-sided, with nothing left to route in. Past the carrier's edge
    (y 117.25) nothing of the KV260 is in the way;
  * no through-hole part over the carrier (y < 118.5): there is 0.8 mm
    below the board there and pins would hit it;
  * the connectors are anchored by hand (below); every other part goes to
    its sheet's region, where it keeps the relative position it has on the
    schematic, and a legaliser moves it to the nearest free spot.

The board file is written as text. KiCad's own Python (pcbnew) is not used:
on Windows it shows every file warning as a dialog on the user's screen.

Usage:  py _work/layout/build_board.py
"""

import json
import math
import os
import re
import shutil
import sys
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pcbdata as P                                  # noqa: E402

schgen = P.schgen
ROOT = P.ROOT
BOARD = os.path.join(ROOT, "CSI2-KRIA-KV260_Rev01.kicad_pcb")
ORIGINAL = os.path.join(ROOT, "_deprecated", "CSI2-KRIA-KV260_Rev01_AlliedVision.kicad_pcb")
PRO = os.path.join(ROOT, "CSI2-KRIA-KV260_Rev01.kicad_pro")
NS = uuid.UUID("0c5b7a4e-9d21-4f38-a6e0-3b1f2c8d7e95")
T = "\t"


def uid(*p):
    return str(uuid.uuid5(NS, "|".join(str(x) for x in p)))


def f(v):
    return schgen.fmt(round(v, 4))


# ---------------------------------------------------------------- outline
Y_EDGE = 202.75
OUTLINE = [(89.0, 107.25), (129.9, 107.25), (129.9, 82.75), (142.4, 82.75), (142.4, 112.25),
           (173.3, 112.25), (173.3, 96.25), (179.4, 96.25), (179.4, 82.75), (193.0, 82.75),
           (193.0, 102.25), (208.0, 102.25), (208.0, Y_EDGE), (89.0, Y_EDGE)]
CARRIER_EDGE = 117.25            # the KV260's side edge in this frame
THT_OK_Y = 118.5                 # through-hole parts only below this

# board-only parts: M3 holes (two through the KV260's corner holes, three
# supports at the outer edge, 8 mm standoffs) and fiducials
HOLES = {"H1": (94.0, 112.25), "H2": (203.0, 112.25),
         "H3": (93.0, 197.75), "H4": (148.5, 180.5), "H5": (204.0, 197.75)}
HOLE_FP = "MountingHole:MountingHole_3.2mm_M3_Pad_Via"
FIDUCIALS = {"FID1": (100.0, 110.0), "FID2": (205.0, 120.5), "FID3": (205.0, 189.0)}
FID_FP = "Fiducial:Fiducial_1mm_Mask2mm"

# ---------------------------------------------------------------- anchors
# ref -> (x, y, rotation). SMAs along the bottom edge (rot 270 points the
# connector at +y; the footprint's "PCB Edge" line is 2.1 mm from its origin).
# Ordered by where each signal comes from: the transmit lines on the left,
# under the DACs; the receive lines on the right, under the ADCs; the clock
# pair at the right end, nearest the ADCLK948 (ROUTING_SPEC §1 for the names).
SMA_ROW = ["J931", "J932",      # IF_TX_A through U903 (DAC_SDR, T801)
           "J941", "J942",      # IF_TX_B through U904 (DAC_RADAR, T701)
           "J952",              # SDR_TX_C, T802 direct
           "J951",              # SDR_RX_C, to the AD9253 channel B
           "J911", "J912",      # IF_RX_A through U901 (ADC_SDR)
           "J921", "J922",      # IF_RX_B through U902 (ADC_RADAR)
           "J401", "J402"]      # clock in / out (CLOCK)
ANCHOR = {r: (101.0 + 8.5 * i, Y_EDGE - 2.1, 270) for i, r in enumerate(SMA_ROW)}
ANCHOR.update({
    "J1001": (103.2, 150.0, 270),        # DC jack, opening at the left edge
    "J1103": (95.5, 125.0, 90),          # AERIS ribbon, 2x20, along the top of the main area
    "J1102": (153.0, 120.5, 90),         # Pmod 2x6
    "J1101": (153.0, 126.5, 90),         # JTAG 2x7, 2 mm
    "U1101": (158.0, 150.0, 90),         # FPGA: bank 15 towards the DACs, 14 towards the ADCs
})
# region of each sheet: (x0, y0, x1, y1)
REGION = {
    "IAS_LINK":  (173.5, 83.0, 193.0, 101.0),
    "CLOCK":     (176.0, 131.0, 207.5, 147.0),
    "ADC_RADAR": (176.0, 147.0, 207.5, 163.0),
    "ADC_SDR":   (176.0, 163.0, 207.5, 177.0),
    "CONTROL":   (142.0, 131.0, 176.0, 177.0),
    "DAC_RADAR": (118.0, 131.0, 142.0, 154.0),
    "DAC_SDR":   (118.0, 154.0, 142.0, 177.0),
    "POWER":     (89.5, 131.0, 118.0, 177.0),
    "ROUTING":   (95.0, 177.0, 207.5, 190.0),
}
CLEAR = 0.2                      # courtyard to courtyard
EDGE_MARGIN = 0.4
# A ring kept free around the BGA so its outer rows can escape on L1 and the
# fan-out vias of the inner rows have room: no part within this of its
# courtyard (1.0 mm pitch, 0.45 mm vias; LAYOUT.md §4).
KEEPOUT = {"U1101": 2.5}


# ---------------------------------------------------------------- geometry
def inside(pt, poly=OUTLINE):
    x, y = pt
    c = False
    for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            c = not c
    return c


def rot_pt(x, y, a):
    r = math.radians(a)
    return (x * math.cos(r) + y * math.sin(r), -x * math.sin(r) + y * math.cos(r))


def box_at(cy, x, y, a):
    pts = [rot_pt(px, py, a) for px in (cy[0], cy[2]) for py in (cy[1], cy[3])]
    return (x + min(p[0] for p in pts), y + min(p[1] for p in pts),
            x + max(p[0] for p in pts), y + max(p[1] for p in pts))


def box_ok(b, tht):
    m = EDGE_MARGIN
    corners = [(b[0] - m, b[1] - m), (b[2] + m, b[1] - m), (b[0] - m, b[3] + m), (b[2] + m, b[3] + m)]
    if not all(inside(c) for c in corners):
        return False
    # the outline is not convex: also sample the edges' midpoints
    mids = [((b[0] + b[2]) / 2, b[1] - m), ((b[0] + b[2]) / 2, b[3] + m),
            (b[0] - m, (b[1] + b[3]) / 2), (b[2] + m, (b[1] + b[3]) / 2)]
    if not all(inside(c) for c in mids):
        return False
    return not (tht and b[1] < THT_OK_Y)


class Grid:
    """Occupied boxes, bucketed by 5 mm cells."""

    def __init__(self):
        self.cells = {}

    def keys(self, b):
        for i in range(int(b[0] // 5), int(b[2] // 5) + 1):
            for j in range(int(b[1] // 5), int(b[3] // 5) + 1):
                yield (i, j)

    def free(self, b):
        g = CLEAR
        for k in self.keys(b):
            for o in self.cells.get(k, ()):
                if b[0] < o[2] + g and o[0] < b[2] + g and b[1] < o[3] + g and o[1] < b[3] + g:
                    return False
        return True

    def add(self, b):
        for k in self.keys(b):
            self.cells.setdefault(k, []).append(b)


# ---------------------------------------------------------------- schematic positions
def schematic_positions():
    """ref -> (x, y) on its own sheet, from the rev03 .kicad_sch files."""
    pos = {}
    for fn in os.listdir(os.path.join(ROOT, "rev03")):
        text = open(os.path.join(ROOT, "rev03", fn), encoding="utf-8").read()
        for m in re.finditer(r"\n\t\(symbol\n", text):
            b = schgen._block(text, m.start() + 2)
            ref = re.search(r'\(property "Reference" "([^"]+)"', b).group(1)
            if ref.startswith("#"):
                continue
            at = re.search(r"\(at ([\d.\-]+) ([\d.\-]+)", b)
            pos.setdefault(ref, (float(at.group(1)), float(at.group(2))))
    return pos


# ---------------------------------------------------------------- attachments
# A small passive belongs next to a pin: a decoupling capacitor next to the
# supply pin it decouples, a termination or a series resistor next to the
# pin it serves. Owners are the chips, connectors, transformers and crystals
# of the SAME sheet (a termination sits at the receiver, which is the chip on
# its own sheet; a 22 ohm series array at the FPGA, its driver).
PASSIVE = re.compile(r"^(C|R|RN|FB|L|D)\d")
OWNER = re.compile(r"^(U|J|Y|T|Q)\d")
PAD_AT = re.compile(r'\(pad "([^"]*)" \w+ \w+\s*\(at ([\d.\-]+) ([\d.\-]+)')


def is_gnd(net):
    return "GND" in net


def is_rail(net):
    return net.startswith(("+", "-")) or net.endswith("XADC_VCC")


def farads(v):
    m = re.match(r"([\d.]+)\s*([pnuµm]?)", v)
    if not m:
        return 1.0
    return float(m.group(1)) * {"p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "m": 1e-3, "": 1.0}[m.group(2)]


def pad_positions(text):
    pos = {}
    for m in PAD_AT.finditer(text):
        pos.setdefault(m.group(1), (float(m.group(2)), float(m.group(3))))
    return pos


def attachments(comps, spos):
    """passive ref -> (owner ref, net, is_rail, order key)."""
    out = {}
    for c in comps.values():
        if not PASSIVE.match(c.ref):
            continue
        nets = [n for n in dict.fromkeys(c.pads.values()) if not is_gnd(n)]
        grounded = any(is_gnd(n) for n in c.pads.values())
        same = [o for o in comps.values() if o.sheet == c.sheet and OWNER.match(o.ref)]
        best = None
        for n in nets:
            if is_rail(n):
                continue
            owners = [o for o in same if n in o.pads.values()]
            if owners:
                best = (max(owners, key=lambda o: len(o.pads)).ref, n, False)
                break
        if best is None:
            # a rail's capacitor goes to the nearest (on the schematic) chip
            # on that rail - or, on POWER, to the inductor whose output the
            # rail is: a buck's output capacitors belong at its inductor
            powl = [o for o in comps.values() if c.sheet == "POWER" and o.sheet == "POWER"
                    and o.ref.startswith("L") and o.ref != c.ref]
            for n in nets:
                owners = [o for o in same + powl if o.ref.startswith(("U", "L")) and n in o.pads.values()]
                if owners and is_rail(n):
                    sx, sy = spos.get(c.ref, (0, 0))
                    o = min(owners, key=lambda o: math.dist(spos.get(o.ref, (1e6, 1e6)), (sx, sy)))
                    best = (o.ref, n, True)
                    break
        if best is None:
            continue
        val = farads(c.value) if c.ref.startswith("C") else 0.0
        # small decoupling first, then everything tied to a signal pin, then
        # bulk. On POWER every capacitor at a regulator is first, whatever its
        # value: a switcher's input and output capacitors close its hot loop
        # (LMR33630 and TPS562201 layout guidelines: CIN at VIN/GND)
        if c.sheet == "POWER" and c.ref.startswith("L") and not best[2]:
            key = (-1, 0.0)                         # a buck's inductor, at its SW pin, first
        elif c.sheet == "POWER" and best[2] and grounded:
            key = (0, val)
        else:
            key = (0, val) if best[2] and grounded and val <= 1.1e-6 else \
                  (1, 0.0) if not best[2] else (2, val)
        out[c.ref] = best + (key,)
    return out


def sma_hints(comps):
    """ROUTING's switches: above the SMAs they reach through their DC-block
    capacitor, so each RF path to the edge is short."""
    bynet = {}
    for c in comps.values():
        for n in c.pads.values():
            bynet.setdefault(n, set()).add(c.ref)

    def sig(n):
        return not is_gnd(n) and not is_rail(n)
    out = {}
    for c in comps.values():
        if c.sheet != "ROUTING" or not OWNER.match(c.ref) or c.ref in ANCHOR:
            continue
        hits = set()
        for n in {n for n in c.pads.values() if sig(n)}:
            for p in bynet[n] - {c.ref}:
                if PASSIVE.match(p) and len(comps[p].pads) == 2:
                    for n2 in set(comps[p].pads.values()) - {n}:
                        if sig(n2):
                            hits |= {j for j in bynet.get(n2, ()) if j in SMA_ROW}
        if hits:
            out[c.ref] = (sum(ANCHOR[j][0] for j in hits) / len(hits), Y_EDGE - 12.0)
    return out


# ---------------------------------------------------------------- placement
def extent(text):
    """The courtyard, grown to take in the silkscreen: some footprints draw
    their pin-1 mark outside the courtyard, where it would land on a
    neighbour's pad."""
    c = P.courtyard(text)
    _, silk = fp_obstacles(text, 0, 0, 0)
    xs = [c[0], c[2]] + [b[0] for b in silk] + [b[2] for b in silk]
    ys = [c[1], c[3]] + [b[1] for b in silk] + [b[3] for b in silk]
    return min(xs), min(ys), max(xs), max(ys)


def spiral(grid, cyd, tht, tx, ty, rmax=100.0):
    """Nearest legal, free spot to (tx, ty): (x, y, angle, box) or None."""
    for r in [i * 0.25 for i in range(0, int(rmax / 0.25))]:
        n = max(1, int(2 * math.pi * r / 0.5))
        for j in range(n):
            ang = 2 * math.pi * j / n
            x = round((tx + r * math.cos(ang)) / 0.05) * 0.05
            y = round((ty + r * math.sin(ang)) / 0.05) * 0.05
            for a in (0, 90):
                b = box_at(cyd, x, y, a)
                if box_ok(b, tht) and grid.free(b):
                    return (x, y, a, b)
    return None


def place(comps):
    spos = schematic_positions()
    grid = Grid()
    placed = {}
    info = {}
    for c in comps.values():
        text = P.fp_text(c.fpid)
        info[c.ref] = (extent(text), bool(re.search(r"\(pad \"[^\"]*\" thru_hole", text)), text)
    attach = attachments(comps, spos)
    near_sma = sma_hints(comps)
    load = {}                                        # (owner, pad) -> parts placed at it
    def pad_target(ref):
        """Where an attached passive should go: its owner's pad, absolute."""
        owner, net, rail, _ = attach[ref]
        ox, oy, oa = placed[owner]
        # the Hirose pair is on the bottom face, copied from the original
        # board: its pads' stored positions are already the flipped ones
        text = info[owner][2] if owner not in HIROSE_ORIG else original_block(HIROSE_ORIG[owner])
        pp = pad_positions(text)
        cands = [p for p, n in comps[owner].pads.items() if n == net and p in pp]
        if not cands:
            return None
        cyd = info[owner][0]

        def edge_dist(p):
            x, y = pp[p]
            return min(x - cyd[0], cyd[2] - x, y - cyd[1], cyd[3] - y)
        # spread the capacitors of one rail over its pins, outer pins first
        p = min(cands, key=lambda p: (load.get((owner, p), 0) * 2.0 + edge_dist(p), p))
        load[(owner, p)] = load.get((owner, p), 0) + 1
        dx, dy = rot_pt(*pp[p], oa)
        return ox + dx, oy + dy
    # the Hirose pair is copied from the original board; reserve their area
    for ref, (x, y) in [("J101", (186.021085, 85.603595)), ("J102", (135.981085, 85.603595))]:
        cy = info[ref][0]
        b = box_at(cy, x, y, 180)
        placed[ref] = (x, y, 180)
    for ref, (x, y, a) in ANCHOR.items():
        cy, tht, _ = info[ref]
        b = box_at(cy, x, y, a)
        placed[ref] = (x, y, a)
        grid.add(b)
        if ref in KEEPOUT:
            m = KEEPOUT[ref]
            grid.add((b[0] - m, b[1] - m, b[2] + m, b[3] + m))
    for name, (x, y) in HOLES.items():
        grid.add((x - 3.6, y - 3.6, x + 3.6, y + 3.6))
    for name, (x, y) in FIDUCIALS.items():
        grid.add((x - 1.5, y - 1.5, x + 1.5, y + 1.5))
    # the rest: sheet by sheet, biggest parts first
    by_sheet = {}
    for c in comps.values():
        if c.ref not in placed:
            by_sheet.setdefault(c.sheet, []).append(c.ref)
    unplaced = []
    for sheet, refs in by_sheet.items():
        rx0, ry0, rx1, ry1 = REGION[sheet]
        pts = [spos[r] for r in refs if r in spos]
        sx0, sx1 = min(p[0] for p in pts), max(p[0] for p in pts)
        sy0, sy1 = min(p[1] for p in pts), max(p[1] for p in pts)
        k = min((rx1 - rx0 - 4) / max(sx1 - sx0, 1), (ry1 - ry0 - 4) / max(sy1 - sy0, 1))
        cx, cy_ = (rx0 + rx1) / 2, (ry0 + ry1) / 2
        scx, scy = (sx0 + sx1) / 2, (sy0 + sy1) / 2

        def area(r):
            cyd = info[r][0]
            return -(cyd[2] - cyd[0]) * (cyd[3] - cyd[1])

        # The order a person would follow: a chip, then at once its own
        # passives (small decoupling first; a buck's inductor, then the
        # capacitors on the inductor's output), then the next chip. So each
        # chip's pins get their neighbourhood before a neighbour can take it.
        # Passives of chips already placed (the anchored FPGA, connectors)
        # go first; then the free parts, biggest first.
        children = {}
        for r in refs:
            if r in attach:
                children.setdefault(attach[r][0], []).append(r)
        order = []

        def with_children(r):
            order.append(r)
            for ch in sorted(children.get(r, []), key=lambda c: (attach[c][3], c)):
                with_children(ch)
        for owner in sorted(o for o in children if o in placed):
            for ch in sorted(children[owner], key=lambda c: (attach[c][3], c)):
                with_children(ch)
        for r in sorted([r for r in refs if r not in attach], key=area):
            with_children(r)
        order += sorted([r for r in refs if r not in order], key=lambda r: (attach[r][3], r))
        for ref in order:
            sx, sy = spos.get(ref, (scx, scy))
            tx, ty = cx + (sx - scx) * k, cy_ + (sy - scy) * k
            if ref in attach and attach[ref][0] in placed:
                t = pad_target(ref)
                if t:
                    tx, ty = t
            elif ref in near_sma:
                tx, ty = near_sma[ref]
            cyd, tht, _ = info[ref]
            spot = spiral(grid, cyd, tht, tx, ty)
            if not spot:
                unplaced.append(ref)
                continue
            placed[ref] = spot[:3]
            grid.add(spot[3])
    return placed, info, unplaced


# ---------------------------------------------------------------- silkscreen
# Each reference designator goes where it can be read after assembly: clear
# of every pad (silk is clipped by the mask), of every other silk line and
# text, of other parts' bodies and of the edge. Tried at 1.0 mm, then at the
# 0.8 mm minimum, above, below, beside the part. A reference that fits
# nowhere is hidden on the silkscreen; it stays on F.Fab, the assembly
# drawing, as every library footprint carries it there.
SILK_H = (1.0, 0.8)
SILK_GAP = 0.15
PAD_RE = re.compile(r'\(pad "[^"]*" \w+ \w+\s*\(at ([\d.\-]+) ([\d.\-]+)(?: ([\d.\-]+))?\)\s*'
                    r'\(size ([\d.]+) ([\d.]+)\)')


def _abs_box(pts, x, y, a, grow=0.0):
    q = [rot_pt(px, py, a) for px, py in pts]
    return (x + min(p[0] for p in q) - grow, y + min(p[1] for p in q) - grow,
            x + max(p[0] for p in q) + grow, y + max(p[1] for p in q) + grow)


def fp_obstacles(text, x, y, a):
    """Boxes of a top-side footprint's pads and silkscreen graphics."""
    pads, silk = [], []
    for m in PAD_RE.finditer(text):
        px, py, pa, w, h = (float(m.group(1)), float(m.group(2)), float(m.group(3) or 0),
                            float(m.group(4)), float(m.group(5)))
        corners = [rot_pt(cx, cy, pa) for cx in (-w / 2, w / 2) for cy in (-h / 2, h / 2)]
        pads.append(_abs_box([(px + cx, py + cy) for cx, cy in corners], x, y, a, 0.05))
    for m in re.finditer(r"\((fp_line|fp_rect|fp_poly|fp_circle|fp_arc)\b", text):
        b = schgen._block(text, m.start())
        if '"F.SilkS"' not in b:
            continue
        pts = [(float(u), float(v)) for u, v in
               re.findall(r"\((?:start|end|mid|xy|center) ([\d.\-]+) ([\d.\-]+)\)", b)]
        if m.group(1) == "fp_circle":
            (cx, cy), (ex, ey) = pts[0], pts[1]
            r = math.dist((cx, cy), (ex, ey))
            pts = [(cx - r, cy - r), (cx + r, cy + r), (cx - r, cy + r), (cx + r, cy - r)]
        wd = re.search(r"\(width ([\d.]+)\)", b)
        grow = float(wd.group(1)) / 2 if wd else 0.06
        # a long line's box is only its own line, not the rectangle it spans
        if m.group(1) == "fp_line" or m.group(1) == "fp_arc":
            silk.append(_abs_box(pts, x, y, a, grow))
        elif m.group(1) == "fp_rect":
            (x0, y0), (x1, y1) = pts[0], pts[1]
            for seg in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
                silk.append(_abs_box(seg, x, y, a, grow))
        else:
            silk.append(_abs_box(pts, x, y, a, grow))
    return pads, silk


class Boxes:
    """Tagged boxes in 5 mm buckets: (box, owner ref, kind)."""

    def __init__(self):
        self.cells = {}

    def add(self, b, ref, kind):
        for k in Grid.keys(None, b):
            self.cells.setdefault(k, []).append((b, ref, kind))

    def hit(self, b, ref, gap):
        for k in Grid.keys(None, b):
            for o, oref, kind in self.cells.get(k, ()):
                if kind == "body" and oref == ref:
                    continue                        # over its own body is fine
                g = 0.0 if kind == "body" else gap
                if b[0] < o[2] + g and o[0] < b[2] + g and b[1] < o[3] + g and o[1] < b[3] + g:
                    return True
        return False


def text_box(ref, h, x, y, ang=0):
    w = len(ref) * 0.95 * h + 0.15 * h
    hh = h + 0.15 * h
    if ang == 90:
        w, hh = hh, w
    return (x - w / 2, y - hh / 2, x + w / 2, y + hh / 2)


def silk_refs(comps, placed, info):
    """ref -> (x, y, height) of its silkscreen reference, or None (hidden)."""
    boxes = Boxes()
    top = [r for r in placed if r not in HIROSE_ORIG]
    for ref in top:
        x, y, a = placed[ref]
        cyd, _, text = info[ref]
        pads, silk = fp_obstacles(text, x, y, a)
        for b in pads:
            boxes.add(b, ref, "pad")
        for b in silk:
            boxes.add(b, ref, "silk")
        boxes.add(box_at(cyd, x, y, a), ref, "body")
    for name, (x, y) in HOLES.items():
        boxes.add((x - 3.3, y - 3.3, x + 3.3, y + 3.3), name, "pad")
    for name, (x, y) in FIDUCIALS.items():
        boxes.add((x - 1.1, y - 1.1, x + 1.1, y + 1.1), name, "pad")

    def area(r):
        c = info[r][0]
        return -(c[2] - c[0]) * (c[3] - c[1])
    out = {}
    for ref in sorted(top, key=lambda r: (area(r), r)):
        x, y, a = placed[ref]
        b = box_at(info[ref][0], x, y, a)
        cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
        # chips, connectors, inductors: worth a wider search; a small passive
        # whose reference does not fit beside it is left to the F.Fab drawing
        reach = 3.0 if re.match(r"^(U|J|T|Y|Q|SW|L|D)\d", ref) else 0.0
        out[ref] = None
        for h in SILK_H:
            for tx, ty, ang in silk_candidates(ref, h, b, reach):
                t = text_box(ref, h, tx, ty, ang)
                if box_ok(t, False) and not boxes.hit(t, ref, SILK_GAP):
                    out[ref] = (tx, ty, h, ang)
                    boxes.add(t, ref, "text")
                    break
            if out[ref]:
                break
    return out


def silk_candidates(ref, h, b, reach):
    """Text centres around box b, nearest first: the four sides and corners,
    then (if reach) rings further out, horizontal and vertical."""
    cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
    w = len(ref) * 0.95 * h + 0.15 * h
    hh = h * 1.15
    yield from [(cx, b[1] - hh / 2 - 0.1, 0), (cx, b[3] + hh / 2 + 0.1, 0),
                (b[0] - w / 2 - 0.1, cy, 0), (b[2] + w / 2 + 0.1, cy, 0),
                (b[0] + w / 2, b[1] - hh / 2 - 0.1, 0), (b[2] - w / 2, b[1] - hh / 2 - 0.1, 0),
                (b[0] + w / 2, b[3] + hh / 2 + 0.1, 0), (b[2] - w / 2, b[3] + hh / 2 + 0.1, 0),
                (b[0] - hh / 2 - 0.1, cy, 90), (b[2] + hh / 2 + 0.1, cy, 90)]
    if (b[2] - b[0]) > w + 1 and (b[3] - b[1]) > hh + 1:
        yield (cx, cy, 0)                           # on a big part's own body
    d = 0.35
    while d <= reach:
        for ang in (0, 90):
            tw, th = (w, hh) if ang == 0 else (hh, w)
            x0, x1 = b[0] - d - tw / 2, b[2] + d + tw / 2
            y0, y1 = b[1] - d - th / 2, b[3] + d + th / 2
            n = 12
            for i in range(n + 1):
                u = i / n
                yield from [(x0 + (x1 - x0) * u, y0, ang), (x0 + (x1 - x0) * u, y1, ang),
                            (x0, y0 + (y1 - y0) * u, ang), (x1, y0 + (y1 - y0) * u, ang)]
        d += 0.35


def set_reference(body, ref, x, y, a, silk):
    """Move (or hide) the Reference property of a footprint's text."""
    i = body.index(f'(property "Reference" "{ref}"')
    blk = schgen._block(body, i)
    if silk is None:
        new = blk.replace('(layer "F.SilkS")', '(layer "F.SilkS")\n\t\t(hide yes)', 1)
    else:
        tx, ty, h, ang = silk
        lx, ly = rot_pt(tx - x, ty - y, -a)
        new = re.sub(r"\(at [\d.\-]+ [\d.\-]+(?: [\d.\-]+)?\)", f"(at {f(lx)} {f(ly)} {f(ang)})", blk, count=1)
        new = re.sub(r"\(size [\d.]+ [\d.]+\)", f"(size {f(h)} {f(h)})", new, count=1)
        new = re.sub(r"\(thickness [\d.]+\)", f"(thickness {f(0.15 * h)})", new, count=1)
    return body[:i] + new + body[i + len(blk):]


# ---------------------------------------------------------------- footprint text
def add_nets(body, pads, depth):
    """Give every pad whose number is in `pads` its net, after its layers.
    depth: how many tabs deep the pads sit."""
    ind = T * depth
    out, i = [], 0
    for m in re.finditer("\n" + ind + r'\(pad "([^"]*)"', body):
        s = m.start() + 1 + depth
        e = s + len(schgen._block(body, s))
        blk = body[s:e]
        if m.group(1) in pads:
            k = blk.index("(layers")
            k2 = blk.index(")", k) + 1
            blk = blk[:k2] + "\n" + ind + T + f'(net "{pads[m.group(1)]}")' + blk[k2:]
        out.append(body[i:s])
        out.append(blk)
        i = e
    out.append(body[i:])
    return "".join(out)


def instance(c, text, x, y, a, silk="keep"):
    """A library footprint as a placed board footprint with its nets."""
    body = text
    name = re.match(r'\(footprint "([^"]+)"', body).group(1)
    body = body.replace(f'(footprint "{name}"', f'(footprint "{c.fpid}"', 1)
    body = re.sub(r'\n\t\((version|generator|generator_version) [^\n]*\)', "", body)
    body = re.sub(r'\n\t\(layer "F\.Cu"\)',
                  f'\n\t(layer "F.Cu")\n\t(uuid "{uid("fp", c.ref)}")\n\t(at {f(x)} {f(y)}'
                  + (f" {f(a)})" if a else ")"), body, count=1)
    body = body.replace('(property "Reference" "REF**"', f'(property "Reference" "{c.ref}"', 1)
    body = re.sub(r'\(property "Value" "[^"]*"', f'(property "Value" "{c.value}"', body, count=1)
    if a:
        # pad and text angles are stored absolute: add the footprint's rotation
        def rot(m):
            ang = (float(m.group(3) or 0) + a) % 360
            return f"(at {m.group(1)} {m.group(2)} {f(ang)})"
        body = re.sub(r"\(at ([\d.\-]+) ([\d.\-]+)(?: ([\d.\-]+))?\)(?=\s*\n\t*\((?:size|unlocked|layer|hide|uuid))",
                      rot, body)

    body = add_nets(body, c.pads, 1)
    if silk != "keep":
        body = set_reference(body, c.ref, x, y, a, silk)
    tail = body.rindex("\n\t(embedded_fonts")
    meta = (f'\n\t(path "/{c.path.strip("/")}")\n\t(sheetname "{c.sheetname}")\n'
            f'\t(sheetfile "{c.sheetfile}")')
    body = body[:tail] + meta + body[tail:]
    # re-indent one level: a board's children sit one tab deeper
    body = "\n".join(T + line for line in body.rstrip("\n").split("\n"))
    return body


def board_only(ref, fpid, x, y, value):
    text = P.fp_text(fpid)
    c = P.Comp(ref, value, fpid, "root", "")
    body = text.replace(f'(footprint "{fpid.split(":")[1]}"', f'(footprint "{fpid}"', 1)
    body = re.sub(r'\n\t\((version|generator|generator_version) [^\n]*\)', "", body)
    body = re.sub(r'\n\t\(layer "F\.Cu"\)', f'\n\t(layer "F.Cu")\n\t(uuid "{uid("fp", ref)}")\n\t(at {f(x)} {f(y)})',
                  body, count=1)
    body = body.replace('(property "Reference" "REF**"', f'(property "Reference" "{ref}"', 1)
    body = set_reference(body, ref, x, y, 0, None)          # no silk text for a hole
    body = re.sub(r"\(attr ([^)]*)\)", lambda m: f"(attr {m.group(1)} board_only)"
                  if "board_only" not in m.group(1) else m.group(0), body, count=1)
    if "(attr" not in body:
        body = body.replace(f'\n\t(uuid "{uid("fp", ref)}")', f'\n\t(uuid "{uid("fp", ref)}")\n\t(attr board_only)', 1)
    if fpid == HOLE_FP:
        body = add_nets(body, {"1": "GND"}, 1)
    return "\n".join(T + line for line in body.rstrip("\n").split("\n"))


HIROSE_ORIG = {"J101": "J8_IAS1", "J102": "J8_IAS0"}


def original_block(orig_ref):
    """The footprint block of `orig_ref` on the original board."""
    text = open(ORIGINAL, encoding="utf-8").read()
    i = text.index(f'(property "Reference" "{orig_ref}"')
    s = text.rfind("\n\t(footprint", 0, i) + 2
    return schgen._block(text, s)


def hirose_from_original(ref, orig_ref, comp):
    """Copy J8_IAS0/J8_IAS1 from the original board: same place, same face."""
    blk = original_block(orig_ref)
    # Its silkscreen goes to the fabrication layer: the pin-number texts are
    # 0.5 mm, below the 0.8 mm minimum, and the outline runs over its own
    # pads. It is on the bottom face, mated to the carrier: nobody reads it.
    def fab(m):
        t = schgen._block(blk, m.start())
        return t.replace('(layer "B.SilkS")', '(layer "B.Fab")')
    out, i = [], 0
    for m in re.finditer(r"\((?:fp_text|property|fp_line|fp_arc|fp_circle|fp_poly|fp_rect)\b", blk):
        if m.start() < i:
            continue
        t = fab(m)
        out += [blk[i:m.start()], t]
        i = m.start() + len(schgen._block(blk, m.start()))
    blk = "".join(out) + blk[i:]
    blk = blk.replace('(footprint "AVT_KHK_Lib:J-BM20B(0.8)-34DP"', f'(footprint "{comp.fpid}"', 1)
    blk = blk.replace(f'"Reference" "{orig_ref}"', f'"Reference" "{ref}"')
    blk = re.sub(r'\(property "Value" "[^"]*"', f'(property "Value" "{comp.value}"', blk, count=1)
    blk = re.sub(r'\n\t\t\(path "[^"]*"\)', "", blk)
    blk = re.sub(r'\n\t\t\(sheetname "[^"]*"\)', "", blk)
    blk = re.sub(r'\n\t\t\(sheetfile "[^"]*"\)', "", blk)
    blk = re.sub(r'\n\t\t\t\(net "[^"]*"\)', "", blk)
    blk = re.sub(r'\(uuid "[^"]+"\)', lambda m: f'(uuid "{uid("h", ref, m.start())}")', blk)
    blk = add_nets(blk, comp.pads, 2)
    tail = blk.rindex("\n\t\t(embedded_fonts")
    blk = blk[:tail] + (f'\n\t\t(path "/{comp.path.strip("/")}")\n\t\t(sheetname "{comp.sheetname}")\n'
                        f'\t\t(sheetfile "{comp.sheetfile}")') + blk[tail:]
    # the 3D model is embedded in the original board; drop the reference
    for head in ("model", "embedded_files"):
        m = re.search(r"\n\t\t\(" + head + r"[\s\n]", blk)
        if m:
            e = m.start() + 3 + len(schgen._block(blk, m.start() + 3))
            blk = blk[:m.start()] + blk[e:]
    return T + blk


# ---------------------------------------------------------------- the board
LAYERS = [(0, "F.Cu", "signal", "L1 SIG"), (4, "In1.Cu", "power", "L2 GND"),
          (6, "In2.Cu", "signal", "L3 SIG"), (8, "In3.Cu", "power", "L4 PWR"),
          (10, "In4.Cu", "power", "L5 GND"), (2, "B.Cu", "signal", "L6 SIG"),
          (9, "F.Adhes", "user", "F.Adhesive"), (11, "B.Adhes", "user", "B.Adhesive"),
          (13, "F.Paste", "user", None), (15, "B.Paste", "user", None),
          (5, "F.SilkS", "user", "F.Silkscreen"), (7, "B.SilkS", "user", "B.Silkscreen"),
          (1, "F.Mask", "user", None), (3, "B.Mask", "user", None),
          (17, "Dwgs.User", "user", "User.Drawings"), (19, "Cmts.User", "user", "User.Comments"),
          (21, "Eco1.User", "user", "User.Eco1"), (23, "Eco2.User", "user", "User.Eco2"),
          (25, "Edge.Cuts", "user", None), (27, "Margin", "user", None),
          (31, "F.CrtYd", "user", "F.Courtyard"), (29, "B.CrtYd", "user", "B.Courtyard"),
          (35, "F.Fab", "user", None), (33, "B.Fab", "user", None)]
# POWER_AND_STACKUP.md §2.1
STACK = [("F.Cu", "copper", 0.035), ("dielectric 1", "prepreg", 0.100, 4.05),
         ("In1.Cu", "copper", 0.0175), ("dielectric 2", "core", 0.200, 4.30),
         ("In2.Cu", "copper", 0.0175), ("dielectric 3", "prepreg", 0.800, 4.30),
         ("In3.Cu", "copper", 0.0175), ("dielectric 4", "core", 0.200, 4.30),
         ("In4.Cu", "copper", 0.0175), ("dielectric 5", "prepreg", 0.100, 4.05),
         ("B.Cu", "copper", 0.035)]


def header():
    L = ["(kicad_pcb", f"{T}(version 20260206)", f'{T}(generator "pcbnew")',
         f'{T}(generator_version "10.0")', f"{T}(general", f"{T}{T}(thickness 1.56)",
         f"{T}{T}(legacy_teardrops no)", f"{T})", f'{T}(paper "A3")',
         f"{T}(title_block", f'{T}{T}(title "KV260-IAS2RF Rev03")', f'{T}{T}(rev "03")',
         f'{T}{T}(company "KV260-IAS2RF")',
         f'{T}{T}(comment 1 "Placement by _work/layout/build_board.py - first pass, to be refined by hand")',
         f"{T})", f"{T}(layers"]
    for n, name, kind, user in LAYERS:
        L.append(f'{T}{T}({n} "{name}" {kind}' + (f' "{user}"' if user else "") + ")")
    L += [f"{T})", f"{T}(setup", f"{T}{T}(stackup",
          f'{T}{T}{T}(layer "F.SilkS"', f'{T}{T}{T}{T}(type "Top Silk Screen")', f"{T}{T}{T})",
          f'{T}{T}{T}(layer "F.Paste"', f'{T}{T}{T}{T}(type "Top Solder Paste")', f"{T}{T}{T})",
          f'{T}{T}{T}(layer "F.Mask"', f'{T}{T}{T}{T}(type "Top Solder Mask")', f"{T}{T}{T}{T}(thickness 0.01)", f"{T}{T}{T})"]
    for item in STACK:
        if item[1] == "copper":
            L += [f'{T}{T}{T}(layer "{item[0]}"', f'{T}{T}{T}{T}(type "copper")',
                  f"{T}{T}{T}{T}(thickness {item[2]})", f"{T}{T}{T})"]
        else:
            L += [f'{T}{T}{T}(layer "{item[0]}"', f'{T}{T}{T}{T}(type "{item[1]}")',
                  f"{T}{T}{T}{T}(thickness {item[2]})", f'{T}{T}{T}{T}(material "FR4")',
                  f"{T}{T}{T}{T}(epsilon_r {item[3]})", f"{T}{T}{T}{T}(loss_tangent 0.02)", f"{T}{T}{T})"]
    L += [f'{T}{T}{T}(layer "B.Mask"', f'{T}{T}{T}{T}(type "Bottom Solder Mask")', f"{T}{T}{T}{T}(thickness 0.01)", f"{T}{T}{T})",
          f'{T}{T}{T}(layer "B.Paste"', f'{T}{T}{T}{T}(type "Bottom Solder Paste")', f"{T}{T}{T})",
          f'{T}{T}{T}(layer "B.SilkS"', f'{T}{T}{T}{T}(type "Bottom Silk Screen")', f"{T}{T}{T})",
          f'{T}{T}{T}(copper_finish "ENIG")', f"{T}{T}{T}(dielectric_constraints yes)", f"{T}{T})",
          f"{T}{T}(pad_to_mask_clearance 0.05)", f"{T}{T}(allow_soldermask_bridges_in_footprints no)",
          f"{T}{T}(tenting", f"{T}{T}{T}(front yes)", f"{T}{T}{T}(back yes)", f"{T}{T})", f"{T})"]
    return L


def outline():
    pts = " ".join(f"(xy {f(x)} {f(y)})" for x, y in OUTLINE)
    return [f"{T}(gr_poly", f"{T}{T}(pts {pts})", f"{T}{T}(stroke", f"{T}{T}{T}(width 0.1)",
            f"{T}{T}{T}(type solid)", f"{T}{T})", f"{T}{T}(fill no)", f'{T}{T}(layer "Edge.Cuts")',
            f'{T}{T}(uuid "{uid("outline")}")', f"{T})"]


def zone(layer, net, name, pts=OUTLINE, priority=0, clearance=0.2, key=None):
    pts_s = " ".join(f"(xy {f(x)} {f(y)})" for x, y in pts)
    return ([f'{T}(zone', f'{T}{T}(net "{net}")', f'{T}{T}(layer "{layer}")',
             f'{T}{T}(uuid "{uid("zone", key or layer)}")', f'{T}{T}(name "{name}")']
            + ([f"{T}{T}(priority {priority})"] if priority else [])
            + [f"{T}{T}(hatch edge 0.5)", f"{T}{T}(connect_pads", f"{T}{T}{T}(clearance {f(clearance)})", f"{T}{T})",
               f"{T}{T}(min_thickness 0.2)", f"{T}{T}(filled_areas_thickness no)",
               f"{T}{T}(fill", f"{T}{T}{T}(thermal_gap 0.3)", f"{T}{T}{T}(thermal_bridge_width 0.3)", f"{T}{T})",
               f"{T}{T}(polygon", f"{T}{T}{T}(pts {pts_s})", f"{T}{T})", f"{T})"])


def plane(layer, net, name):
    return zone(layer, net, name)


# ---------------------------------------------------------------- L4, the power layer
# L4 (In3.Cu) is split: +3V3_D, the rail with the most pins (62) and spread
# over the whole board, is the background; islands of higher priority carry
# the rails that have a clear home and either high current or many pins.
# Everything else (+1V8_D, +2V5, +3V3_A, +1V8_A, +12V, -3V3, +1V2, XADC)
# is routed as tracks. Islands are drawn around the rail's own pads, so they
# follow the placement. 0.3 mm between islands.
L4_ISLAND = [
    # net, which pads define it (box), margin mm
    ("+5V0", (89.0, 125.0, 122.0, 180.0), 1.0),     # POWER: the three bucks' and LDOs' input
    ("+3V3_CLK", None, 1.0),                        # CLOCK
    ("+5V_IFR", None, 0.8), ("+5V_IFS", None, 0.8),  # the AD8352 drivers
    ("+1V8_ADCR_A", None, 0.8), ("+1V8_ADCR_D", None, 0.8),
    ("+1V8_ADCS_A", None, 0.8), ("+1V8_ADCS_D", None, 0.8),
]


def abs_pads(comps, placed, info):
    """(net, x, y, ref) of every top-side pad on the board."""
    out = []
    for ref, c in comps.items():
        if ref not in placed or ref in HIROSE_ORIG:
            continue
        x, y, a = placed[ref]
        for pad, (px, py) in pad_positions(info[ref][2]).items():
            if pad in c.pads:
                dx, dy = rot_pt(px, py, a)
                out.append((c.pads[pad], x + dx, y + dy, ref))
    return out


def rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def power_layer(comps, placed, info):
    pads = abs_pads(comps, placed, info)
    out = zone("In3.Cu", "+3V3_D", "L4 +3V3_D", key="L4 +3V3_D")
    islands = []
    for net, clip, m in L4_ISLAND:
        pts = [(x, y) for n, x, y, _ in pads if n == net and
               (clip is None or clip[0] <= x <= clip[2] and clip[1] <= y <= clip[3])]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        islands.append((net, (min(xs) - m, min(ys) - m, max(xs) + m, max(ys) + m)))
    # +1V0, FPGA VCCINT (700 mA): the BGA and its keep-out ring, and a 5 mm
    # corridor to it from the buck's inductor (the POWER inductor on +1V0)
    x, y, a = placed["U1101"]
    bga = box_at(info["U1101"][0], x, y, a)
    k = KEEPOUT["U1101"]
    src = [(px, py) for n, px, py, r in pads if n == "+1V0" and r.startswith("L")
           and comps[r].sheet == "POWER"]
    sx, sy = min(src, key=lambda p: p[0])
    isl = (bga[0] - k, bga[1] - k, bga[2] + k, bga[3] + k)
    islands.append(("+1V0", isl))
    # along from the inductor, then (if it is not level with the BGA) up or
    # down into the island: an L, 5 mm wide
    xe = isl[0] + 5.0
    islands.append(("+1V0", (sx - 2.0, sy - 2.5, xe, sy + 2.5)))
    if sy + 2.5 < isl[1] + 5.0 or sy - 2.5 > isl[3] - 5.0:
        islands.append(("+1V0", (isl[0], min(sy - 2.5, isl[1]), xe, max(sy + 2.5, isl[3]))))
    # smaller islands win where two overlap
    order = sorted(range(len(islands)), key=lambda i: -((islands[i][1][2] - islands[i][1][0])
                                                          * (islands[i][1][3] - islands[i][1][1])))
    for pri, i in enumerate(order, start=1):
        net, bx = islands[i]
        out += zone("In3.Cu", net, f"L4 {net}", rect(*bx), priority=pri, clearance=0.3,
                    key=f"L4 {net} {i}")
    return out, islands


def texts():
    out = []
    for i, (s, x, y) in enumerate([
            ("KV260-IAS2RF Rev03", 150.0, 108.5),
            ("KV260 carrier edge below this line (y 117.25): no through-hole parts above it", 91.0, 116.6)]):
        out += [f'{T}(gr_text "{s}"', f"{T}{T}(at {f(x)} {f(y)} 0)", f'{T}{T}(layer "Dwgs.User" )',
                f'{T}{T}(uuid "{uid("t", i)}")', f"{T}{T}(effects", f"{T}{T}{T}(font",
                f"{T}{T}{T}{T}(size 1 1)", f"{T}{T}{T}{T}(thickness 0.15)", f"{T}{T}{T})",
                f"{T}{T}{T}(justify left)", f"{T}{T})", f"{T})"]
    out += [f"{T}(gr_line", f"{T}{T}(start 89 {CARRIER_EDGE})", f"{T}{T}(end 208 {CARRIER_EDGE})",
            f"{T}{T}(stroke", f"{T}{T}{T}(width 0.15)", f"{T}{T}{T}(type dash)", f"{T}{T})",
            f'{T}{T}(layer "Dwgs.User")', f'{T}{T}(uuid "{uid("carrier")}")', f"{T})"]
    return out


# ---------------------------------------------------------------- project rules
def rules():
    pro = json.load(open(PRO, encoding="utf-8"))
    r = pro["board"]["design_settings"]["rules"]
    r.update({"min_clearance": 0.1, "min_track_width": 0.1, "min_via_diameter": 0.45,
              "min_through_hole_diameter": 0.2, "min_via_annular_width": 0.1,
              "min_copper_edge_clearance": 0.3, "min_hole_to_hole": 0.25, "min_hole_clearance": 0.2})
    ns = pro["net_settings"]
    base = dict(ns["classes"][0])
    base.update({"track_width": 0.15, "clearance": 0.15, "via_diameter": 0.45, "via_drill": 0.2,
                 "diff_pair_width": 0.136, "diff_pair_gap": 0.15})

    def cls(name, **kw):
        c = dict(base, name=name, priority=kw.pop("priority"))
        c.update(kw)
        return c
    ns["classes"] = [
        dict(base, name="Default", priority=2147483647),
        # POWER_AND_STACKUP §2.2: 100 ohm differential on L1, W 136 S 150 um
        cls("LVDS100", priority=0, track_width=0.136, diff_pair_width=0.136, diff_pair_gap=0.15,
            clearance=0.15),
        # 50 ohm single-ended on L1, W 174 um
        cls("RF50", priority=1, track_width=0.174, clearance=0.2),
        cls("Power", priority=2, track_width=0.4, clearance=0.2, via_diameter=0.6, via_drill=0.3),
    ]
    ns["netclass_patterns"] = (
        [{"netclass": "LVDS100", "pattern": p} for p in
         ("*LINK_*_P", "*LINK_*_N", "*ADCR_D*_[PN]", "*ADCR_DCO_[PN]", "*ADCR_OR_[PN]",
          "*ADCS_*_[PN]", "*CLK_ADC*_[PN]", "*CLK_FPGA_[PN]", "*FPGA_CLK_[PN]")]
        + [{"netclass": "RF50", "pattern": p} for p in ("*IF_RX_*", "*IF_TX_*", "*/RF*", "*SMA*")]
        + [{"netclass": "Power", "pattern": p} for p in
           ("+12V", "+5V0", "+3V3_D", "+3V3_A", "+2V5", "+1V8_D", "+1V8_A", "+1V0", "-3V3",
            "*VIN*", "*_SW")])
    ns["netclass_assignments"] = {}
    json.dump(pro, open(PRO, "w", encoding="utf-8", newline="\n"), indent=2)
    with open(PRO, "a", encoding="utf-8", newline="\n") as fh:
        fh.write("\n")


def main():
    if not os.path.exists(ORIGINAL):
        os.makedirs(os.path.dirname(ORIGINAL), exist_ok=True)
        shutil.copy2(BOARD, ORIGINAL)
        print(f"original board kept as {os.path.relpath(ORIGINAL, ROOT)}")
    comps = P.netlist()
    placed, info, unplaced = place(comps)
    silk = silk_refs(comps, placed, info)
    body = header()
    for ref, c in sorted(comps.items()):
        if ref in ("J101", "J102"):
            body.append(hirose_from_original(ref, HIROSE_ORIG[ref], c))
        elif ref in placed:
            x, y, a = placed[ref]
            body.append(instance(c, info[ref][2], x, y, a, silk[ref]))
    for ref, (x, y) in HOLES.items():
        body.append(board_only(ref, HOLE_FP, x, y, "M3"))
    for ref, (x, y) in FIDUCIALS.items():
        body.append(board_only(ref, FID_FP, x, y, "Fiducial"))
    body += outline() + texts()
    body += plane("In1.Cu", "GND", "L2 GND") + plane("In4.Cu", "GND", "L5 GND")
    l4, islands = power_layer(comps, placed, info)
    body += l4
    body.append(f"{T}(embedded_fonts no)")
    body.append(")")
    text = "\n".join(body) + "\n"
    assert schgen._balanced(text)
    open(BOARD, "w", encoding="utf-8", newline="\n").write(text)
    rules()
    print(f"{len(placed)} footprints placed by rule or anchor, {len(unplaced)} not placed: {unplaced}")
    print(f"+ {len(HOLES)} holes, {len(FIDUCIALS)} fiducials; wrote {os.path.relpath(BOARD, ROOT)}")
    for net, bx in islands:
        print(f"  L4 island {net:12s} x {bx[0]:6.1f}-{bx[2]:6.1f}  y {bx[1]:6.1f}-{bx[3]:6.1f}")
    return 1 if unplaced else 0


if __name__ == "__main__":
    sys.exit(main())
