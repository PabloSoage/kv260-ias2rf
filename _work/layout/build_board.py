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
_OUT = os.environ.get("BB_OUT", ROOT)
BOARD = os.path.join(_OUT, "CSI2-KRIA-KV260_Rev01.kicad_pcb")
ORIGINAL = os.path.join(ROOT, "_deprecated", "CSI2-KRIA-KV260_Rev01_AlliedVision.kicad_pcb")
PRO = os.path.join(_OUT, "CSI2-KRIA-KV260_Rev01.kicad_pro")
NS = uuid.UUID("0c5b7a4e-9d21-4f38-a6e0-3b1f2c8d7e95")
T = "\t"


def uid(*p):
    return str(uuid.uuid5(NS, "|".join(str(x) for x in p)))


def f(v):
    return schgen.fmt(round(v, 4))


# ---------------------------------------------------------------- variants
# Placement knobs, tried 7-10 Oct 2026. The defaults are the placement the
# board was routed from:
#   BB_GROW=<mm>      the board grows outward (+y) by this much; the RF row,
#                     the SMAs and the outer supports move down with the edge
#                     (default 12);
#   BB_J1103=bottom   the AERIS ribbon in a band under CONTROL, not at the
#                     top-left: its 35 bank-35 lines leave the BGA's lower-left
#                     and no longer cross both DAC buses ("top": the old place);
#   BB_RN=left        the AD9767's series arrays in a column left of the BGA,
#                     on the way to U801, not above the BGA ("top": by rule);
#   BB_CLEAR=<mm>     courtyard-to-courtyard clearance (default 0.5; 0.2 left
#                     the router no way between the passives);
#   BB_BOTTOM=caps    the chips' decoupling capacitors (not POWER's) on the
#                     bottom face, under the pin they decouple. Off: the
#                     router did worse (100 unrouted after the IF step against
#                     73), each bottom pad costing a through via;
#   BB_ADC=mirror     (default; "off" for the old placement) the two ADC sheets
#                     placed mirrored in x (13-14 Oct): the ADC
#                     next to the FPGA and its front end outboard, at the ADC's
#                     input side. Off, the front ends sat between the ADCs and
#                     the BGA and the ADCs' LVDS pairs crossed over them;
#   BB_ROT=REF:a,...  only this rotation for these parts (default U501:0,U601:270:
#                     each ADC's inputs towards its front end, its LVDS side
#                     towards the BGA; the AD9253's LVDS side is south at 0);
#   BB_OUT=<dir>      write the board and project there instead of the repo.
GROW = float(os.environ.get("BB_GROW", "12"))
J1103_BOTTOM = os.environ.get("BB_J1103", "bottom") == "bottom"
BOTTOM_CAPS = os.environ.get("BB_BOTTOM") == "caps"
ADC_MIRROR = os.environ.get("BB_ADC", "mirror") == "mirror"
ROT = {r: int(a) for r, a in (s.split(":") for s in os.environ.get("BB_ROT", "U501:0,U601:270").split(",") if s)}
ON_BOTTOM = set()                # refs placed on the bottom face

# ---------------------------------------------------------------- outline
Y_EDGE = 202.75 + GROW
OUTLINE = [(89.0, 107.25), (129.9, 107.25), (129.9, 82.75), (142.4, 82.75), (142.4, 112.25),
           (173.3, 112.25), (173.3, 96.25), (179.4, 96.25), (179.4, 82.75), (193.0, 82.75),
           (193.0, 102.25), (208.0, 102.25), (208.0, Y_EDGE), (89.0, Y_EDGE)]
CARRIER_EDGE = 117.25            # the KV260's side edge in this frame
THT_OK_Y = 118.5                 # through-hole parts only below this

# board-only parts: M3 holes (two through the KV260's corner holes, three
# supports at the outer edge, 8 mm standoffs) and fiducials
HOLES = {"H1": (94.0, 112.25), "H2": (203.0, 112.25),
         "H3": (93.0, 197.75 + GROW), "H4": (148.5, 180.5 + GROW), "H5": (204.0, 197.75 + GROW)}
HOLE_FP = "MountingHole:MountingHole_3.2mm_M3_Pad_Via"
FIDUCIALS = {"FID1": (100.0, 110.0), "FID2": (205.0, 120.5), "FID3": (205.0, 189.0 + GROW)}
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
# POWER, laid out along the flow of the power (POWER_SPEC §1), not left to
# the legaliser: 12 V comes in at the jack's pin 1 (103.2, 150) and goes up
# through the PTC and the reverse-polarity MOSFET to the LMR33630, whose
# inductor sits to its left; +5V0 then feeds three buck cells below the jack
# (chip above, inductor below, output capacitors under it; +1V0 on the
# right, nearest the FPGA) and a column of LDOs on the right edge of the
# block (+3V3_A at the top, next to the DACs). The charge pump for -3V3 goes
# at the bottom, towards the RF switches that use it. Orientations put each
# chip's switch pin towards its inductor and its input pins towards its
# supply (pad maps of HSOP-8, SOT-23-6, PowerDI3333, 1812).
ANCHOR.update({
    "F1001": (107.5, 149.5, 90),        # pad 1 at the jack's VIN, pad 2 up to Q1001
    "Q1001": (107.5, 143.8, 270),       # drain down to the PTC, sources (+12V) up
    "U1001": (104.0, 137.5, 180),       # VIN pins right, towards Q1001; SW left
    "L1001": (95.5, 137.5, 180),        # SW pad right, at U1001's pin 8; +5V0 left
    "U1002": (93.5, 162.0, 90),         # +3V3_D buck: SW and VIN down, to the inductor
    "L1010": (93.5, 168.7, 270),        # SW pad up, +3V3_D down
    "U1003": (102.5, 162.0, 90),        # +2V5
    "L1020": (102.5, 168.7, 270),
    "U1004": (111.5, 162.0, 90),        # +1V0, nearest the FPGA
    "L1030": (111.5, 168.7, 270),
    "U1007": (117.0, 134.5, 0),         # +3V3_A LDO, next to the DACs
    "U1006": (117.0, 142.5, 0),         # +1V8_D LDO
    "U1005": (117.0, 150.5, 0),         # +1V8_A LDO
    "U1008": (97.0, 181.0, 0),          # -3V3 charge pump
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
    "ROUTING":   (95.0, 177.0 + GROW, 207.5, 190.0 + GROW),
}
if J1103_BOTTOM:
    # pin 1 at the left, as before: its centre at x 145, in the band between
    # CONTROL and the RF row; the top-left it leaves goes to DAC_RADAR
    ANCHOR["J1103"] = (120.9, 178.3 + GROW / 2, 90)
    REGION["DAC_RADAR"] = (118.0, 121.0, 142.0, 154.0)
if os.environ.get("BB_RN", "left") == "left":
    # the AD9767's series arrays in a column left of the BGA, on the way to
    # U801 (pads 1-4, the FPGA side, to the right), not above the BGA
    for i, r in enumerate(["RN1106", "RN1105", "RN1104", "RN1103", "RN1107"]):
        ANCHOR[r] = (145.0, 149.0 + 2.8 * i, 180)
    ANCHOR["U1101"] = ANCHOR.pop("U1101")    # after them: its bulk capacitors go round them
if GROW:
    x0, y0, x1, y1 = REGION["ADC_SDR"]
    REGION["ADC_SDR"] = (x0, y0, x1, y1 + GROW)
CLEAR = float(os.environ.get("BB_CLEAR", "0.5"))   # courtyard to courtyard
EDGE_MARGIN = 0.4
# A ring kept free around the BGA so its outer rows can escape on L1 and the
# fan-out vias of the inner rows have room: no part within this of its
# courtyard (1.0 mm pitch, 0.45 mm vias; LAYOUT.md §4). 3.5 mm since 19 Oct (2.5 until then):
# the wider ring left the escapes more room.
KEEPOUT = {"U1101": float(os.environ.get("BB_RING", "3.5"))}   # BB_RING: its width in mm


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
def schematic_positions(all_units=False):
    """ref -> (x, y) on its own sheet, from the rev03 .kicad_sch files: the
    first unit's; with all_units, ref -> [(x, y) of every unit]."""
    pos = {}
    for fn in os.listdir(os.path.join(ROOT, "rev03")):
        text = open(os.path.join(ROOT, "rev03", fn), encoding="utf-8").read()
        for m in re.finditer(r"\n\t\(symbol\n", text):
            b = schgen._block(text, m.start() + 2)
            ref = re.search(r'\(property "Reference" "([^"]+)"', b).group(1)
            if ref.startswith("#"):
                continue
            at = re.search(r"\(at ([\d.\-]+) ([\d.\-]+)", b)
            xy = (float(at.group(1)), float(at.group(2)))
            if all_units:
                pos.setdefault(ref, []).append(xy)
            else:
                pos.setdefault(ref, xy)
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


def schematic_pins():
    """ref -> {pin number: (x, y)} on its sheet, every unit, from the rev03
    files: each instance's position, rotation and mirror applied to the pin
    positions of the symbol embedded in that file."""
    out = {}
    pin_re = re.compile(r'\(pin \w+ \w+\s*\(at ([-\d.]+) ([-\d.]+)[^)]*\).*?\(number "([^"]*)"', re.S)
    for fn in os.listdir(os.path.join(ROOT, "rev03")):
        text = open(os.path.join(ROOT, "rev03", fn), encoding="utf-8").read()
        lib = {}                                   # (lib_id, unit) -> {number: (x, y)}
        i = text.find("(lib_symbols")
        if i >= 0:
            libs = schgen._block(text, i)
            for m in re.finditer(r'\n\t\t\(symbol "([^"]+)"', libs):
                blk = schgen._block(libs, m.start() + 3)
                name = m.group(1).split(":")[-1]
                for sm in re.finditer(r'\(symbol "' + re.escape(name) + r'_(\d+)_\d+"', blk):
                    u = int(sm.group(1))
                    for pm in pin_re.finditer(schgen._block(blk, sm.start())):
                        lib.setdefault((m.group(1), u), {})[pm.group(3)] = (float(pm.group(1)),
                                                                            float(pm.group(2)))
        for m in re.finditer(r"\n\t\(symbol\n", text):
            b = schgen._block(text, m.start() + 2)
            ref = re.search(r'\(property "Reference" "([^"]+)"', b).group(1)
            if ref.startswith("#"):
                continue
            lib_id = re.search(r'\(lib_id "([^"]+)"', b).group(1)
            at = re.search(r"\(at ([\d.\-]+) ([\d.\-]+)(?: ([\d.\-]+))?", b)
            x, y, rot = float(at.group(1)), float(at.group(2)), float(at.group(3) or 0)
            unit = int(re.search(r"\(unit (\d+)\)", b).group(1))
            mirror = "(mirror y)" in b
            pins = dict(lib.get((lib_id, 0), {}))
            pins.update(lib.get((lib_id, unit), {}))
            a = math.radians(rot)
            for num, (px, py) in pins.items():
                dx, dy = px, -py                   # library Y is up
                if mirror:
                    dx = -dx
                out.setdefault(ref, {})[num] = (x + dx * math.cos(a) + dy * math.sin(a),
                                                y - dx * math.sin(a) + dy * math.cos(a))
    return out


def spec_notes():
    """ref -> the description its sheet's spec gives it (_work/sheets/*_spec.py,
    PARTS: (lib, value, footprint, description)). The schematic symbols do
    not carry it; it often says whose pin a capacitor is for."""
    import importlib
    sheets = os.path.join(os.path.dirname(HERE), "sheets")
    sys.path.insert(0, sheets)
    notes = {}
    for fn in sorted(os.listdir(sheets)):
        if fn.endswith("_spec.py"):
            mod = importlib.import_module(fn[:-3])
            for ref, v in getattr(mod, "PARTS", {}).items():
                if isinstance(v, tuple) and len(v) > 3 and isinstance(v[3], str):
                    notes[ref] = v[3]
    return notes


def ohms(v):
    m = re.match(r"([\d.]+)\s*([kKmM]?)", v)
    if not m:
        return 0.0
    return float(m.group(1)) * {"k": 1e3, "K": 1e3, "M": 1e6, "m": 1e6, "": 1.0}[m.group(2)]


def attachments(comps, spos):
    """passive ref -> (owner ref, net, is_rail, order key)."""
    spins = schematic_pins()
    notes = spec_notes()
    shared = {}
    out = {}
    for c in sorted(comps.values(), key=lambda c: c.ref):
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
                owners = [o for o in same + powl if o.ref.startswith(("U", "L", "Y")) and n in o.pads.values()]
                if owners and is_rail(n):
                    sx, sy = spos.get(c.ref, (0, 0))
                    # nearest by the distance to the owner's own pin on this
                    # rail, not to the symbol's centre: the FPGA's power unit
                    # is 300 mm tall on its sheet

                    def gap(o, n=n):
                        pts = [xy for num, xy in spins.get(o.ref, {}).items()
                               if o.pads.get(num) == n]
                        if not pts:
                            return math.dist(spos.get(o.ref, (1e6, 1e6)), (sx, sy))
                        return min(math.dist(xy, (sx, sy)) for xy in pts)
                    # drawn right at a chip's pin (under 15 mm on the sheet):
                    # that chip. Drawn in a block of its own, away from every
                    # pin (CONTROL's FPGA decoupling, per UG483): the chip
                    # with the most pins on the rail
                    # the spec names the chip: "ADCLK948 p.10: 1 uF bypass",
                    # "... one 100 nF at the Si549's VDD"
                    note = notes.get(c.ref, "")
                    named = [o for o in owners if re.search(r"\b" + re.escape(o.ref) + r"\b", note)
                             or re.search(r"\b" + re.escape(o.value.split()[0]) + r"\b", note)]
                    o = min(owners, key=gap)
                    if len(named) == 1:
                        o = named[0]
                    elif gap(o) > 15.0 and c.sheet != "POWER":
                        # most pins on the rail; between equals (two identical
                        # drivers on one rail), share the capacitors out
                        o = min(owners, key=lambda o, n=n: (-sum(v == n for v in o.pads.values()),
                                                           shared.get((o.ref, n), 0), o.ref))
                        shared[(o.ref, n)] = shared.get((o.ref, n), 0) + 1
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
        elif (c.sheet != "POWER" and c.ref.startswith("R") and not c.ref.startswith("RN")
              and ohms(c.value) >= 1e3 and (grounded or any(is_rail(n) for n in nets))):
            key = (3, 0.0)          # a pull-up or pull-down (>= 1 k to a rail): DC, last
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


def spiral(grid, cyd, tht, tx, ty, rmax=100.0, angles=(0, 90)):
    """Nearest legal, free spot to (tx, ty): (x, y, angle, box) or None."""
    for r in [i * 0.25 for i in range(0, int(rmax / 0.25))]:
        n = max(1, int(2 * math.pi * r / 0.5))
        for j in range(n):
            ang = 2 * math.pi * j / n
            x = round((tx + r * math.cos(ang)) / 0.05) * 0.05
            y = round((ty + r * math.sin(ang)) / 0.05) * 0.05
            for a in angles:
                b = box_at(cyd, x, y, a)
                if box_ok(b, tht) and grid.free(b):
                    return (x, y, a, b)
    return None


def place(comps):
    spos = schematic_positions()
    grid = Grid()
    gridb = Grid()               # the bottom face: through-hole parts, holes, bottom parts
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
        if tht:
            gridb.add(b)
        if ref in KEEPOUT:
            m = KEEPOUT[ref]
            grid.add((b[0] - m, b[1] - m, b[2] + m, b[3] + m))
            # the same ring on the bottom: the fan-out vias and the L6 escape
            gridb.add((b[0] - m, b[1] - m, b[2] + m, b[3] + m))
            # Its VCCINT bulk (330, 100 and 3 x 4.7 uF, +1V0) next,
            # before anything else can take the ring's edge: from the +1V0
            # ball nearest the edge outward. Those balls are in the middle
            # of the BGA, so about 11 mm is the least this can be. UG483
            # p.24: "Bulk capacitors can be placed almost anywhere on the
            # PCB, but the best placement is as close as possible to the FPGA."
            bulk = sorted([r for r, v in attach.items() if v[0] == ref and v[1] == "+1V0"
                           and farads(comps[r].value) >= 4.7e-6],
                          key=lambda r: (-farads(comps[r].value), r))
            pp = pad_positions(info[ref][2])
            balls = [rot_pt(*pp[p], a) for p, n in comps[ref].pads.items() if n == "+1V0" and p in pp]
            for r in bulk:
                bx, by = min(balls, key=lambda q: min(q[0] - (b[0] - x), (b[2] - x) - q[0],
                                                      q[1] - (b[1] - y), (b[3] - y) - q[1]))
                cyd, tht, _ = info[r]
                spot = spiral(grid, cyd, tht, x + bx, y + by, rmax=20.0)
                if spot:
                    placed[r] = spot[:3]
                    grid.add(spot[3])
    for name, (x, y) in HOLES.items():
        grid.add((x - 3.6, y - 3.6, x + 3.6, y + 3.6))
        gridb.add((x - 3.6, y - 3.6, x + 3.6, y + 3.6))
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
            if ADC_MIRROR and sheet in ("ADC_RADAR", "ADC_SDR"):
                tx = cx - (sx - scx) * k
            if ref in attach and attach[ref][0] in placed:
                t = pad_target(ref)
                if t:
                    tx, ty = t
            elif ref in near_sma:
                tx, ty = near_sma[ref]
            cyd, tht, _ = info[ref]
            if bottom(ref, comps, attach):
                # mirrored courtyard; past the carrier's edge only (the
                # through-hole rule), where nothing is under the board
                spot = spiral(gridb, (cyd[0], -cyd[3], cyd[2], -cyd[1]), True, tx, ty)
                if spot:
                    ON_BOTTOM.add(ref)
                    placed[ref] = spot[:3]
                    gridb.add(spot[3])
                    continue
            spot = spiral(grid, cyd, tht, tx, ty, angles=(ROT[ref],) if ref in ROT else (0, 90))
            if not spot:
                unplaced.append(ref)
                continue
            placed[ref] = spot[:3]
            grid.add(spot[3])
            if tht:
                gridb.add(spot[3])
    return placed, info, unplaced


def bottom(ref, comps, attach):
    """Does this part go on the bottom face (BB_BOTTOM)?"""
    return (BOTTOM_CAPS and ref.startswith("C") and ref in attach and attach[ref][2]
            and comps[ref].sheet != "POWER")


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
    top = [r for r in placed if r not in HIROSE_ORIG and r not in ON_BOTTOM]
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
        new = re.sub(r'\(layer "([FB])\.SilkS"\)', lambda m: m.group(0) + "\n\t\t(hide yes)", blk, count=1)
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


def flipped(text, a):
    """A library footprint (top face, unrotated) on the bottom face at
    rotation a, as KiCad's Flip writes it: local y negated, F./B. layers
    swapped, pad and text angles stored absolute as a - p, texts mirrored, an
    arc's start and end exchanged (mirroring reverses its sweep)."""
    def swap(m):
        return '"' + {"F": "B", "B": "F"}[m.group(1)] + "." + m.group(2) + '"'
    out, i = [], 0
    for m in re.finditer(r"\n\t\((\w+)", text):
        s = m.start() + 2
        if s < i:
            continue
        blk = schgen._block(text, s)
        head, new = m.group(1), blk
        if head in ("layer", "pad", "property", "fp_text", "fp_line", "fp_rect", "fp_circle",
                    "fp_arc", "fp_poly"):
            new = re.sub(r'"([FB])\.(\w+)"', swap, new)
        if head.startswith("fp_") and head != "fp_text":
            new = re.sub(r"\((start|end|mid|center|xy) ([\d.\-]+) ([\d.\-]+)\)",
                         lambda q: f"({q.group(1)} {q.group(2)} {f(0.0 - float(q.group(3)))})", new)
            if head == "fp_arc":
                st = re.search(r"\(start [^)]*\)", new).group(0)
                en = re.search(r"\(end [^)]*\)", new).group(0)
                new = new.replace(st, "\0").replace(en, st.replace("start", "end")).replace(
                    "\0", en.replace("end", "start"))
        if head in ("pad", "property", "fp_text"):
            new = re.sub(r"\(at ([\d.\-]+) ([\d.\-]+)(?: ([\d.\-]+))?\)",
                         lambda q: f"(at {q.group(1)} {f(0.0 - float(q.group(2)))} "
                                   f"{f((a - float(q.group(3) or 0)) % 360)})", new, count=1)
            if head == "pad" and "(offset" in new:
                raise ValueError("pad offset: no rule to flip it")
        if head in ("property", "fp_text") and re.search(r'\(layer "[FB]\.', new):
            if "(justify" in new:
                new = re.sub(r"\(justify([^)]*)\)", lambda q: f"(justify{q.group(1)} mirror)", new, count=1)
            else:
                k = new.index("(font")
                k = k + len(schgen._block(new, k))
                new = new[:k] + "\n\t\t\t(justify mirror)" + new[k:]
        out += [text[i:s], new]
        i = s + len(blk)
    return "".join(out) + text[i:]


def instance(c, text, x, y, a, silk="keep", bottom=False):
    """A library footprint as a placed board footprint with its nets."""
    body = flipped(text, a) if bottom else text
    side = "B.Cu" if bottom else "F.Cu"
    name = re.match(r'\(footprint "([^"]+)"', body).group(1)
    body = body.replace(f'(footprint "{name}"', f'(footprint "{c.fpid}"', 1)
    body = re.sub(r'\n\t\((version|generator|generator_version) [^\n]*\)', "", body)
    body = re.sub(r'\n\t\(layer "' + side + r'"\)',
                  f'\n\t(layer "{side}")\n\t(uuid "{uid("fp", c.ref)}")\n\t(at {f(x)} {f(y)}'
                  + (f" {f(a)})" if a else ")"), body, count=1)
    body = body.replace('(property "Reference" "REF**"', f'(property "Reference" "{c.ref}"', 1)
    body = re.sub(r'\(property "Value" "[^"]*"', f'(property "Value" "{c.value}"', body, count=1)
    if a and not bottom:
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
# JLCPCB JLC06161H-2116A (POWER_AND_STACKUP §2.6): the fabricator's own
# stack with the shape of §2.1 - thin dielectric under L1 and L6, L3 close to
# L2 and far from L4. Between L3 and L4 JLCPCB presses 2116 + a 0.70 mm core +
# 2116; it is one layer here, 0.9328 mm, at the thickness-weighted Er.
STACK = [("F.Cu", "copper", 0.035), ("dielectric 1", "prepreg", 0.1164, 4.16),
         ("In1.Cu", "copper", 0.0152), ("dielectric 2", "core", 0.130, 4.17),
         ("In2.Cu", "copper", 0.0152), ("dielectric 3", "prepreg", 0.9328, 4.44),
         ("In3.Cu", "copper", 0.0152), ("dielectric 4", "core", 0.130, 4.17),
         ("In4.Cu", "copper", 0.0152), ("dielectric 5", "prepreg", 0.1164, 4.16),
         ("B.Cu", "copper", 0.035)]


def header():
    L = ["(kicad_pcb", f"{T}(version 20260206)", f'{T}(generator "pcbnew")',
         f'{T}(generator_version "10.0")', f"{T}(general", f"{T}{T}(thickness 1.556)",
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
            if ref in ON_BOTTOM:
                py = -py
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
    # +1V0, FPGA VCCINT (700 mA): the block of its nine balls, and a 3 mm
    # corridor to it from the buck's inductor (the POWER inductor on +1V0).
    # Not the whole BGA and ring any more (6 Oct): tracks may cross L4 outside
    # the islands, and round the BGA is where they need the room.
    balls = [(px, py) for n, px, py, r in pads if n == "+1V0" and r == "U1101"]
    src = [(px, py) for n, px, py, r in pads if n == "+1V0" and r.startswith("L")
           and comps[r].sheet == "POWER"]
    sx, sy = min(src, key=lambda p: p[0])
    isl = (min(p[0] for p in balls) - 1.2, min(p[1] for p in balls) - 1.2,
           max(p[0] for p in balls) + 1.2, max(p[1] for p in balls) + 1.2)
    islands.append(("+1V0", isl))
    # along from the inductor, then (if it is not level with the block) up or
    # down into it: an L, 3 mm wide
    xe = isl[0] + 3.0
    islands.append(("+1V0", (sx - 2.0, sy - 1.5, xe, sy + 1.5)))
    if sy + 1.5 < isl[1] + 3.0 or sy - 1.5 > isl[3] - 3.0:
        islands.append(("+1V0", (isl[0], min(sy - 1.5, isl[1]), xe, max(sy + 1.5, isl[3]))))
    # smaller islands win where two overlap
    order = sorted(range(len(islands)), key=lambda i: -((islands[i][1][2] - islands[i][1][0])
                                                          * (islands[i][1][3] - islands[i][1][1])))
    for pri, i in enumerate(order, start=1):
        net, bx = islands[i]
        out += zone("In3.Cu", net, f"L4 {net}", rect(*bx), priority=pri, clearance=0.3,
                    key=f"L4 {net} {i}")
    # tracks may use L4 (6 Oct), but not across an island: a track there would
    # cut it. A tracks-only keep-out rule area over each; vias and pads allowed
    for i, (net, bx) in enumerate(islands):
        pts_s = " ".join(f"(xy {f(x)} {f(y)})" for x, y in rect(*bx))
        out += [f"{T}(zone", f'{T}{T}(layer "In3.Cu")', f'{T}{T}(uuid "{uid("zone", f"L4 keepout {i}")}")',
                f'{T}{T}(name "In3 islands: no tracks ({net})")', f"{T}{T}(hatch edge 0.5)",
                f"{T}{T}(connect_pads", f"{T}{T}{T}(clearance 0)", f"{T}{T})",
                f"{T}{T}(min_thickness 0.25)", f"{T}{T}(filled_areas_thickness no)",
                f"{T}{T}(keepout", f"{T}{T}{T}(tracks not_allowed)", f"{T}{T}{T}(vias allowed)",
                f"{T}{T}{T}(pads allowed)", f"{T}{T}{T}(copperpour allowed)", f"{T}{T}{T}(footprints allowed)",
                f"{T}{T})", f"{T}{T}(fill", f"{T}{T}{T}(thermal_gap 0.5)", f"{T}{T}{T}(thermal_bridge_width 0.5)",
                f"{T}{T})", f"{T}{T}(polygon", f"{T}{T}{T}(pts {pts_s})", f"{T}{T})", f"{T})"]
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
    base.update({"track_width": 0.15, "clearance": 0.1, "via_diameter": 0.45, "via_drill": 0.2,
                 "diff_pair_width": 0.117, "diff_pair_gap": 0.15})

    def cls(name, **kw):
        c = dict(base, name=name, priority=kw.pop("priority"))
        c.update(kw)
        return c
    ns["classes"] = [
        dict(base, name="Default", priority=2147483647),
        # 100 ohm differential on L1, W 117 S 150 um: _work/field_solver.py on
        # JLC06161H-2116A with solder mask (POWER_AND_STACKUP §2.6)
        cls("LVDS100", priority=0, track_width=0.117, diff_pair_width=0.117, diff_pair_gap=0.15,
            clearance=0.15),
        # 50 ohm single-ended on L1, W 183 um (same source)
        cls("RF50", priority=1, track_width=0.183, clearance=0.2),
        # 0.15 mm, not 0.2 (2 Oct, at routing): 12 V at most, where IPC-2221 asks
        # 0.1 mm; 0.2 left no way between fine-pitch pins
        cls("Power", priority=2, track_width=0.4, clearance=0.15, via_diameter=0.6, via_drill=0.3),
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
            body.append(instance(c, info[ref][2], x, y, a, silk.get(ref), bottom=ref in ON_BOTTOM))
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
    print(f"{len(placed)} footprints placed by rule or anchor ({len(ON_BOTTOM)} on the bottom face), "
          f"{len(unplaced)} not placed: {unplaced}")
    print(f"+ {len(HOLES)} holes, {len(FIDUCIALS)} fiducials; wrote {BOARD}")
    for net, bx in islands:
        print(f"  L4 island {net:12s} x {bx[0]:6.1f}-{bx[2]:6.1f}  y {bx[1]:6.1f}-{bx[3]:6.1f}")
    return 1 if unplaced else 0


if __name__ == "__main__":
    sys.exit(main())
