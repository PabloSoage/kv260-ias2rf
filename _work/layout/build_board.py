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
SMA_ROW = ["J401", "J402", "J911", "J912", "J921", "J922", "J931", "J932",
           "J941", "J942", "J951", "J952"]
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


# ---------------------------------------------------------------- placement
def place(comps):
    spos = schematic_positions()
    grid = Grid()
    placed = {}
    info = {}
    for c in comps.values():
        text = P.fp_text(c.fpid)
        info[c.ref] = (P.courtyard(text), bool(re.search(r"\(pad \"[^\"]*\" thru_hole", text)), text)
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
        for ref in sorted(refs, key=area):
            sx, sy = spos.get(ref, (scx, scy))
            tx, ty = cx + (sx - scx) * k, cy_ + (sy - scy) * k
            cyd, tht, _ = info[ref]
            spot = None
            for r in [i * 0.25 for i in range(0, 400)]:
                n = max(1, int(2 * math.pi * r / 0.5))
                for j in range(n):
                    ang = 2 * math.pi * j / n
                    x = round((tx + r * math.cos(ang)) / 0.05) * 0.05
                    y = round((ty + r * math.sin(ang)) / 0.05) * 0.05
                    for a in (0, 90):
                        b = box_at(cyd, x, y, a)
                        if box_ok(b, tht) and grid.free(b):
                            spot = (x, y, a, b)
                            break
                    if spot:
                        break
                if spot:
                    break
            if not spot:
                unplaced.append(ref)
                continue
            placed[ref] = spot[:3]
            grid.add(spot[3])
    return placed, info, unplaced


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


def instance(c, text, x, y, a):
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
    body = re.sub(r"\(attr ([^)]*)\)", lambda m: f"(attr {m.group(1)} board_only)"
                  if "board_only" not in m.group(1) else m.group(0), body, count=1)
    if "(attr" not in body:
        body = body.replace(f'\n\t(uuid "{uid("fp", ref)}")', f'\n\t(uuid "{uid("fp", ref)}")\n\t(attr board_only)', 1)
    if fpid == HOLE_FP:
        body = add_nets(body, {"1": "GND"}, 1)
    return "\n".join(T + line for line in body.rstrip("\n").split("\n"))


def hirose_from_original(ref, orig_ref, comp):
    """Copy J8_IAS0/J8_IAS1 from the original board: same place, same face."""
    text = open(ORIGINAL, encoding="utf-8").read()
    i = text.index(f'(property "Reference" "{orig_ref}"')
    s = text.rfind("\n\t(footprint", 0, i) + 2
    blk = schgen._block(text, s)
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


def plane(layer, net, name):
    m = 0.5
    pts = " ".join(f"(xy {f(x)} {f(y)})" for x, y in OUTLINE)
    return [f'{T}(zone', f'{T}{T}(net "{net}")', f'{T}{T}(layer "{layer}")',
            f'{T}{T}(uuid "{uid("zone", layer)}")', f'{T}{T}(name "{name}")',
            f"{T}{T}(hatch edge 0.5)", f"{T}{T}(connect_pads", f"{T}{T}{T}(clearance 0.2)", f"{T}{T})",
            f"{T}{T}(min_thickness 0.2)", f"{T}{T}(filled_areas_thickness no)",
            f"{T}{T}(fill", f"{T}{T}{T}(thermal_gap 0.3)", f"{T}{T}{T}(thermal_bridge_width 0.3)", f"{T}{T})",
            f"{T}{T}(polygon", f"{T}{T}{T}(pts {pts})", f"{T}{T})", f"{T})"]


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
    body = header()
    for ref, c in sorted(comps.items()):
        if ref in ("J101", "J102"):
            body.append(hirose_from_original(ref, {"J101": "J8_IAS1", "J102": "J8_IAS0"}[ref], c))
        elif ref in placed:
            x, y, a = placed[ref]
            body.append(instance(c, info[ref][2], x, y, a))
    for ref, (x, y) in HOLES.items():
        body.append(board_only(ref, HOLE_FP, x, y, "M3"))
    for ref, (x, y) in FIDUCIALS.items():
        body.append(board_only(ref, FID_FP, x, y, "Fiducial"))
    body += outline() + texts()
    body += plane("In1.Cu", "GND", "L2 GND") + plane("In4.Cu", "GND", "L5 GND")
    body.append(f"{T}(embedded_fonts no)")
    body.append(")")
    text = "\n".join(body) + "\n"
    assert schgen._balanced(text)
    open(BOARD, "w", encoding="utf-8", newline="\n").write(text)
    rules()
    print(f"{len(placed)} footprints placed by rule or anchor, {len(unplaced)} not placed: {unplaced}")
    print(f"+ {len(HOLES)} holes, {len(FIDUCIALS)} fiducials; wrote {os.path.relpath(BOARD, ROOT)}")
    return 1 if unplaced else 0


if __name__ == "__main__":
    sys.exit(main())
