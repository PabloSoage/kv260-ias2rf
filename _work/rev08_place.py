"""
Rev08 placement table for _work/rev08_pcb.py (phase 5). KiCad board coordinates in mm, y down; rotation in
degrees anticlockwise; side "F" (top) or "B" (bottom: only where the board is off the carrier, y > 117.9).

Blocks (REV08_PLAN 11.4, adjusted to the schematic's real part count):
  west     J961 on the edge, ESD, the bias tee and its switch, between H1's clamp and frame A;
  frame A  x 103.8-120.9: the LNA and its bypass (south-west), preselector A (the two PE42442, one above the
           other) with the FM reject and FM band-pass filters west of them;
  frame B  x 121.3-141.6: preselector B (SKY13418 pair, UHF low-pass, SAW, the two LTCC filters) in its west
           half, the converter (bypass pair, baluns, RFFC5072, TCXO, loop filter) in its east half;
  IF       anti-alias low-pass, IF amplifier, attenuator, east of frame B (a via fence, no can);
  tongue   the RF expander (0x20), the debug USB-C and its bridge, J103 over J102;
  LEDs     a column north of the west block, beside H1's clamp; the LED expander under it on the bottom.
The trial put preselector B in frame A; with the schematic's parts it does not fit there, frame B has room.

Decoupling capacitors and pull-ups go on the bottom under their part where the board is off the carrier, next
to it on the top elsewhere (near()); the RF parts are placed along their line (two(), ladder()).
"""
import math
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OURS = os.path.join(ROOT, "footprints", "kv260-ias2rf.pretty")

RENAME = {"/CONTROL/PMOD_SPARE1": "/PMOD_SPARE1", "/CONTROL/PMOD_SPARE2": "/PMOD_SPARE2"}
MOVE = {"J1002": (91.85, 127.75, 0), "C1092": (96.5, 123.8, 0), "FID1": (130.6, 125.2, 0), "FID4": (122.6, 132.0, 0)}
RIP = [("/POWER/FAN_5V", (89, 119, 103, 130)), ("GND", (92.5, 119.5, 101.5, 124.5)), ("GND", (132.4, 82.9, 139.6, 88.4), "any"), ("GND", (88.9, 120.0, 93.2, 122.6))]
TEMPLATE = {"J961": "J922"}
PLACE = {}
FP = {}
FRAMES = {"SH1": (103.8, 107.7, 120.9, 126.9), "SH2": (121.3, 107.7, 141.6, 123.7)}

# ---------------------------------------------------------------- footprint geometry
LIBS = {"C_0402": "Capacitor_SMD:C_0402_1005Metric", "R_0402": "Resistor_SMD:R_0402_1005Metric",
        "L_0402": "Inductor_SMD:L_0402_1005Metric", "LED_0402": "LED_SMD:LED_0402_1005Metric",
        "L_0603": "Inductor_SMD:L_0603_1608Metric", "L_0805": "Inductor_SMD:L_0805_2012Metric",
        "D_SOD-882": "Diode_SMD:D_SOD-882", "C_0805": "Capacitor_SMD:C_0805_2012Metric"}
D2 = {"C_0402": 0.48, "R_0402": 0.51, "L_0402": 0.485, "LED_0402": 0.485, "L_0603": 0.7875, "L_0805": 1.0625,
      "D_SOD-882": 0.35, "C_0805": 0.95}
DIRS = {"E": 0, "N": 90, "W": 180, "S": 270}
UNIT = {"E": (1, 0), "N": (0, -1), "W": (-1, 0), "S": (0, 1)}
_LIB = {}


def lib_pads(name):
    if name not in _LIB:
        lib, fp = name.split(":")
        if lib == "kv260-ias2rf":
            p = os.path.join(OURS, fp + ".kicad_mod")
        else:
            from toolpaths import stock_footprints
            p = os.path.join(stock_footprints(), lib + ".pretty", fp + ".kicad_mod")
        t = open(p, encoding="utf-8").read()
        _LIB[name] = {n: (float(x), float(y)) for n, x, y in
                      re.findall(r'\(pad "([^"]+)" \w+ \w+\s*\(at ([-\d.]+) ([-\d.]+)', t)}
    return _LIB[name]


def rot(px, py, a):
    r = math.radians(a)
    return px * math.cos(r) + py * math.sin(r), -px * math.sin(r) + py * math.cos(r)


def at(ref, x, y, a=0, side="F", fp=None):
    PLACE[ref] = (round(x, 4), round(y, 4), a % 360, side)
    if fp:
        FP[ref] = fp


def pin(ref, n):
    x, y, a, side = PLACE[ref]
    px, py = lib_pads(FP[ref])[n]
    if side == "B":
        py = -py
    dx, dy = rot(px, py, a)
    return round(x + dx, 4), round(y + dy, 4)


def ic(ref, fp, a, n, x, y, side="F"):
    """Place an IC so that its pin n lands on (x, y)."""
    at(ref, 0, 0, a, side, fp)
    px, py = pin(ref, n)
    at(ref, x - px, y - py, a, side)


def two(ref, kind, x, y, d, side="F", first="1"):
    """Two-pin part with pad `first` at (x, y), the other pad toward d (E, N, W, S). Returns the other pad."""
    h = D2[kind]
    a = DIRS[d] + (180 if first == "2" else 0)
    ux, uy = UNIT[d]
    at(ref, x + ux * h, y + uy * h, a, side, LIBS[kind])
    return round(x + 2 * ux * h, 4), round(y + 2 * uy * h, 4)


def step(p, d, k):
    return round(p[0] + UNIT[d][0] * k, 4), round(p[1] + UNIT[d][1] * k, 4)


SIDE = {("E", "L"): "N", ("E", "R"): "S", ("W", "L"): "S", ("W", "R"): "N",
        ("N", "L"): "W", ("N", "R"): "E", ("S", "L"): "E", ("S", "R"): "W"}


CY = {"C_0402": (0.91, 0.46), "R_0402": (0.93, 0.47), "L_0402": (0.93, 0.47), "LED_0402": (0.93, 0.47),
      "L_0603": (1.48, 0.73), "L_0805": (1.75, 0.85), "D_SOD-882": (0.8, 0.6), "C_0805": (1.7, 0.85)}
G = 0.03                                     # courtyard to courtyard


def ladder(p, d, hand, elems):
    """A filter along a line from p toward d; shunt branches to the `hand` side (L or R of the direction).
    Courtyards abut (G apart): series parts end to end, shunts beside the line at the node between them.
    elems: ("s", ref, kind)                 series part on the line
           ("p", ref, kind[, ref2, kind2])  shunt from the node to ground (a second part stacked after it)
           ("pp", ref, kind, ref2, kind2)   two shunt parts side by side on the node
           ("sp", ref, kind, ref2, kind2)   a series part with a second one beside it, across the same nodes
    Returns the end point of the line."""
    sd = SIDE[(d, hand)]
    od = {"N": "S", "S": "N", "E": "W", "W": "E"}[sd]
    cur = p                                  # where the next series courtyard may start
    wl = max(CY[e[2]][1] for e in elems if e[0] in ("s", "sp"))       # half width of the line's parts
    for e in elems:
        k = e[0]
        if k in ("s", "sp"):
            hl, hw = CY[e[2]]
            c = step(cur, d, hl)
            two(e[1], e[2], *step(c, d, -D2[e[2]]), d)
            if k == "sp":
                h2 = CY[e[4]]
                two(e[3], e[4], *step(step(c, od, hw + G + h2[1]), d, -D2[e[4]]), d)
            cur = step(c, d, hl + G)
        else:
            node = cur
            off = wl + G
            if k == "p":
                hl1 = CY[e[2]][0]
                c1 = step(node, sd, off + hl1)
                two(e[1], e[2], *step(c1, sd, -D2[e[2]]), sd)
                if len(e) > 3:
                    hl2 = CY[e[4]][0]
                    c2 = step(c1, sd, hl1 + G + hl2)
                    two(e[3], e[4], *step(c2, sd, -D2[e[4]]), sd)
            else:                            # pp
                for ref, kind, s in ((e[1], e[2], -1), (e[3], e[4], 1)):
                    hl1, hw1 = CY[kind]
                    c1 = step(step(node, sd, off + hl1), d, s * (hw1 + G / 2))
                    two(ref, kind, *step(c1, sd, -D2[kind]), sd)
    return cur


NEAR = []                                   # (ref, kind, anchor (ref, pin), side): packed by the engine
ESCAPES = []                                # ((ref, pin), dx, dy): a 0.12 mm stub from the pin and a via at its end,
                                            # on the copper of the part's side


def escape(ref, n, dx, dy):
    """Pre-route a pin that the router would otherwise wall in: stub and via, the router takes it from there."""
    ESCAPES.append(((ref, n), dx, dy))


def near(ref, kind, anchor, side="B"):
    NEAR.append((ref, kind, anchor, side))
    FP[ref] = LIBS[kind]


# ======================================================================== west: SMA, ESD, bias tee
Y = 121.3                                    # the antenna line, J961's axis
at("J961", 91.1, Y, 180)                     # Rev07's SMA launch (J922); centre pin ends at x 92.7
two("D1301", "D_SOD-882", 94.6, Y, "S")
two("FB1302", "L_0402", 95.75, Y, "N")        # bead (was 56 nH L1302): VU_ANT -> VU_BIAS_MID
two("C1301", "C_0402", 97.6, Y, "E")         # DC block
two("L1301", "L_0805", 95.9, 118.55, "E")    # 1 uH: VU_BIAS_MID -> VU_BIAS_OUT
at("U1314", 100.6, 119.2, 90, fp="kv260-ias2rf:SOT-23-6_L2.9-W1.6-P0.95-LS2.8-BL")
two("C1361", "C_0402", 98.3, 116.95, "W")     # BIAS_OUT -> GND
two("C1360", "C_0402", 102.9, pin("U1314", "1")[1], "N")      # BIAS_IN -> GND
at("JP1301", 99.45, 123.5, 0, side="B", fp="Jumper:SolderJumper-3_P1.3mm_Bridged12_RoundedPad1.0x1.5mm")
near("R1362", "R_0402", ("U1314", "5"))
# the 3.0 V regulator for the whole block, on the bottom of the west block
ic("U1315", "Package_TO_SOT_SMD:SOT-23-5", 0, "5", 99.0, 120.0, side="B")
near("C1380", "C_0402", ("U1315", "1"))
near("C1381", "C_0402", ("U1315", "5"))
near("C1382", "C_0402", ("U1315", "5"))
near("FB1301", "L_0603", ("U1315", "3"))

# ======================================================================== frame A
# ---- LNA and its bypass, on the antenna line (south-west)
ic("U1302", "kv260-ias2rf:SC-70-6_L2.2-W1.3-P0.65-LS2.1-BL", 90, "5", 105.76, Y)   # RFC W, RF1 E-low, RF2 E-up
p = pin("U1302", "1")
q = two("C1302", "C_0402", p[0] + 0.7, p[1], "E")
ic("U1301", "kv260-ias2rf:SOT343_L2.0-W1.3-P1.30-LS2.1-BL", 90, "3", q[0] + 0.75, q[1])   # IN W-up, OUT E-low
o = pin("U1301", "1")
two("FB1304", "L_0402", o[0], o[1] + 0.9, "S", first="2")         # LNA_OUT -> LNA_BIAS
r = two("C1303", "C_0402", o[0] + 0.75, o[1], "E")
ic("U1303", "kv260-ias2rf:SC-70-6_L2.2-W1.3-P0.65-LS2.1-BL", 270, "1", r[0] + 0.7, r[1])  # RF1 W-up, RFC E
two("C1305", "C_0402", pin("FB1304", "1")[0] + 0.75, pin("FB1304", "1")[1], "E", side="B")          # LNA_BIAS -> GND, under the choke
two("L1303", "L_0603", pin("FB1304", "1")[0] - 0.75, pin("FB1304", "1")[1], "W", side="B", first="2")   # +3V0_RF -> LNA_BIAS
near("C1304", "C_0402", ("L1303", "1"))
near("C1306", "C_0402", ("U1302", "6"))
near("C1307", "C_0402", ("U1303", "6"))
# ---- preselector A: U1304 (in) south, U1305 (out) north; both switches' controls toward x 113
ic("U1304", "kv260-ias2rf:QFN-24_L4.0-W4.0-P0.50-BL-EP2.8", 90, "22", 115.75, 122.2)   # IN S
ic("U1305", "kv260-ias2rf:QFN-24_L4.0-W4.0-P0.50-BL-EP2.8", 270, "22", 115.25, 109.5)  # OUT N
two("C1310", "C_0402", pin("U1304", "16")[0] - 0.75, pin("U1304", "16")[1], "W", side="F")   # west of its VDD pin,
escape("U1304", "17", -0.8, 0.35)                    # so PSA_V1 can leave south-west past it
near("C1311", "C_0402", ("U1305", "16"), side="F")
# FM reject, 9th order, northward along x 112.3 from y 119.0, shunts west
e = ladder((112.6, 119.6), "N", "L", [
    ("s", "C1421", "C_0402"), ("p", "L1421", "L_0402", "C1422", "C_0402"),
    ("s", "C1423", "C_0402"), ("p", "L1422", "L_0402", "C1424", "C_0402"),
    ("s", "C1425", "C_0402"), ("p", "L1423", "L_0402", "C1426", "C_0402"),
    ("s", "C1427", "C_0402"), ("p", "L1424", "L_0603", "C1428", "C_0402"),
    ("s", "C1429", "C_0402")])
# FM band-pass, southward along x 105.65 from y 109.2, shunt pairs east
ladder((105.4, 109.6), "S", "L", [
    ("pp", "L1431", "L_0402", "C1431", "C_0402"),
    ("s", "L1432", "L_0603"), ("s", "C1432", "C_0402"),
    ("pp", "L1433", "L_0402", "C1433", "C_0402")])

# ======================================================================== frame B
# ---- preselector B (west half): U1306 in, U1307 out, the two LTCC filters and the SAW north of the pair,
#      the UHF low-pass south of it
ic("U1306", "kv260-ias2rf:QFN-14_L2.0-W2.0-P0.45-BL-EP", 0, "13", 123.05, 117.2)     # IN W
ic("U1307", "kv260-ias2rf:QFN-14_L2.0-W2.0-P0.45-BL-EP", 180, "13", 131.75, 117.2)   # OUT E
at("FL1301", 127.4, 114.6, 0, fp="kv260-ias2rf:FILTER-SMD_6P-L3.8-W3.8-P1.27-TL-3")  # SAW 1090
at("FL1303", 124.6, 110.75, 0, fp="kv260-ias2rf:FILTER-SMD_1206-4P-L3.2-W1.6-L")     # LPF 1 GHz
at("FL1302", 129.4, 110.75, 0, fp="kv260-ias2rf:FILTER-SMD_1206-4P-L3.2-W1.6-L")     # HPF 1 GHz
ladder((124.0, 120.0), "E", "R", [
    ("p", "C1401", "C_0402"), ("sp", "L1401", "L_0402", "C1402", "C_0402"),
    ("p", "C1403", "C_0402"), ("sp", "L1402", "L_0402", "C1404", "C_0402"),
    ("p", "C1405", "C_0402"), ("sp", "L1403", "L_0402", "C1406", "C_0402"),
    ("p", "C1407", "C_0402")])
two("C1312", "C_0402", pin("U1306", "4")[0] + 1.07, pin("U1306", "4")[1] - 0.12, "E", side="F")   # along the south row:
escape("U1306", "7", 0.8, -0.15)                     # the channel to U1307 stays free for PSB_V1..V3
escape("U1307", "13", 0.75, 0.0)                     # PSB_OUT leaves east, down to L3 at once
# J103 over J102: one via per contact, in two staggered ranks outside each row (REV08_PLAN 4.3); the engine
# draws J103's pad to it on the top and J102's on the bottom
PASS = [(n, 1.75 if (n - 1) % 2 == 0 else 2.30) for n in range(1, 35)]
two("C1313", "C_0402", pin("U1307", "4")[0], pin("U1307", "4")[1] - 0.75, "N", side="F")   # north of its VDD pin
near("C1308", "C_0402", ("U1308", "6"), side="F")
near("C1309", "C_0402", ("U1309", "6"), side="F")
near("C1322", "C_0402", ("T1302", "2"), side="F")
# ---- converter (east half): RFFC5072 turned so that its mixer input faces south (input balun T1301 below
#      it, fed by the bypass switch U1308) and its output east (through the wall on L3 to T1302 outside)
ic("U1312", "Package_DFN_QFN:QFN-32-1EP_5x5mm_P0.5mm_EP3.45x3.45mm", 270, "33", 136.4, 114.6)
ic("T1301", "kv260-ias2rf:XFMR-SMD_TC1-1TX", 0, "1", pin("U1312", "23")[0] - 0.4, pin("U1312", "23")[1] + 1.7)
ic("U1308", "kv260-ias2rf:SC-70-6_L2.2-W1.3-P0.65-LS2.1-BL", 90, "1", pin("T1301", "6")[0] - 3.0,
   pin("T1301", "6")[1])                                                           # RFC W, RF1 E-low
two("C1320", "C_0402", pin("U1308", "1")[0] + 0.55, pin("U1308", "1")[1], "E")
two("C1321", "C_0402", *pin("T1301", "4"), "S", side="B")      # INR -> GND
at("Y1301", 133.6, 110.0, 0, fp="kv260-ias2rf:OSC-SMD_4P-L2.0-W1.6-BL")
for k, vdd in enumerate(("5", "22", "19")):                 # ANA_VDD1, ANA_VDD2, DIG_VDD: 33 p then 10 n, first
    for ref in (f"C13{51 + 2 * k}", f"C13{52 + 2 * k}"):
        near(ref, "C_0402", ("U1312", vdd), side="F")
for ref in ("C1340", "C1347", "C1348", "R1347", "R1348", "R1349", "C1349", "C1350", "R1346", "C1341"):
    near(ref, "C_0402" if ref[0] == "C" else "R_0402", ("U1312", "33"), side="F")
for ref in ("R1340", "R1341", "R1345"):                      # DC parts: no room left in the can, on the bottom
    near(ref, "R_0402", ("U1312", "33"))
for ref in ("C1342", "C1343", "C1344", "C1345", "C1346"):
    near(ref, "C_0402", ("U1313", "13"))                      # the serial lines' 33 pF, at their driving end

# ======================================================================== IF side, east of frame B
# output balun and bypass-out switch on the top, unshielded (135 MHz); the IF chain on the bottom under them
ic("T1302", "kv260-ias2rf:XFMR-SMD_TC1-1TX", 90, "3", 144.4, 113.9)               # balanced W, OUT E-low
ic("U1309", "kv260-ias2rf:SC-70-6_L2.2-W1.3-P0.65-LS2.1-BL", 270, "1", pin("T1302", "6")[0] + 1.3,
   pin("T1302", "6")[1] + 1.4)                                                       # RF1 W-up, RFC E
two("C1323", "C_0402", pin("T1302", "6")[0], pin("T1302", "6")[1] + 1.4, "S")
two("C1324", "C_0402", pin("T1302", "4")[0] + 1.0, pin("T1302", "4")[1], "E")
ladder((150.4, 119.4), "W", "R", [
    ("p", "C1411", "C_0402"), ("sp", "L1411", "L_0402", "C1412", "C_0402"),
    ("p", "C1413", "C_0402"), ("sp", "L1412", "L_0402", "C1414", "C_0402"),
    ("p", "C1415", "C_0402"), ("sp", "L1413", "L_0402", "C1416", "C_0402"),
    ("p", "C1417", "C_0402")])
for k in [r for r in list(PLACE) if r[:3] in ("C14", "L14") and r[3] == "1"]:
    x, y, a, s = PLACE[k]
    PLACE[k] = (x, y, a, "B")
ic("U1310", "kv260-ias2rf:SOT343_L2.0-W1.3-P1.30-LS2.1-BL", 0, "3", 142.0, 121.8, side="B")
ic("U1311", "kv260-ias2rf:QFN-20_L4.0-W4.0-P0.50-BL-EP2.2", 0, "2", 146.0, 123.8, side="B")
for ref, kind in (("C1330", "C_0402"), ("C1332", "C_0402"), ("L1305", "L_0603"), ("C1331", "C_0402"),
                  ("C1333", "C_0402"), ("C1334", "C_0402"), ("R1330", "R_0402")):
    near(ref, kind, ("U1311", "21") if ref != "C1330" else ("U1310", "3"))
two("C927", "C_0402", 178.6, 206.52, "E")                    # beside C926: SW2's RF2 throw to IF_VU

# ======================================================================== tongue: expander, USB, J103
at("J103", 135.981085, 85.603595, 180, fp="kv260-ias2rf:CONN-SMD_34P-P0.40_BM20B-0.8-34DS-0.4V-51")
UX, UY = 124.6, 127.4                        # under the free top strip south of frame B: through vias have room
at("U1313", UX, UY, 0, side="B", fp="kv260-ias2rf:WQFN-24_L4.0-W4.0-P0.50-TL-EP2.5")
# fan-out of the west, north and east pins: a via each, 0.8 and 1.3 mm past the pad centre in turn (0.5 mm pitch);
# the south pins (I2C, supplies, reset) leave on the bottom, which is free there
for k, n in enumerate(list(range(1, 9)) + list(range(10, 18))):
    x, y = pin("U1313", str(n))
    r = 0.8 if k % 2 == 0 else 1.3
    dx, dy = (-r, 0) if x < UX - 1.5 else ((r, 0) if x > UX + 1.5 else (0, -r))
    escape("U1313", str(n), dx, dy)
near("C1370", "C_0402", ("U1313", "23"))
near("C1371", "C_0402", ("U1313", "21"))
near("R1370", "R_0402", ("U1313", "24"))
for ref in ("R1342", "R1343", "R1344", "R1360", "R1361"):
    near(ref, "R_0402", ("U1313", "25"))
at("J1501", 133.6, 93.4, 90, fp="kv260-ias2rf:USB_C_HX_16P_180_LT_H10")
at("U1503", 138.9, 96.1, 0, fp="Package_TO_SOT_SMD:SOT-23-6")
at("U1502", 138.9, 91.3, 0, fp="kv260-ias2rf:MSOP-10_L3.0-W3.0-P0.50-LS5.0-BL")
at("U1504", 135.4, 100.4, 0, fp="Package_TO_SOT_SMD:SOT-23-5")
for ref in ("C1531", "R1531", "R1532"):
    near(ref, "R_0402" if ref[0] == "R" else "C_0402", ("U1502", "7"), side="F")
near("R1533", "R_0402", ("@", 148.6, 121.0))              # at the Pmod (J1102) end of the debug UART lines
near("R1534", "R_0402", ("@", 148.6, 121.0))
for ref in ("C1532", "C1533", "R1535"):
    near(ref, "R_0402" if ref[0] == "R" else "C_0402", ("U1504", "5"), side="F")

# ======================================================================== LEDs
STATUS = ["D1501", "D1502", "D1503", "D1504", "D1505", "D1506", "D1507", "D1508", "D1509"]
for k, d in enumerate(STATUS):
    y = 108.85 + 0.95 * k
    two(d, "LED_0402", 99.6, y, "E", first="1")        # cathode W, anode E
    two(f"R15{11 + k}" if k < 8 else "R1519", "R_0402", 101.47, y, "E", first="2")   # anode side W, +3V3_D E
ic("U1501", "kv260-ias2rf:WQFN-24_L4.0-W4.0-P0.50-TL-EP2.5", 0, "25", 104.2, 123.6, side="B")
# the decaps sit south of shield wall A (y 126.1-126.9 on the top), where their vias are allowed
two("C1501", "C_0402", pin("U1501", "21")[0], 127.45, "E", side="B")
two("C1502", "C_0402", pin("U1501", "23")[0], 127.45, "W", side="B")
near("R1501", "R_0402", ("U1501", "24"))
# rail LEDs: on the tongue's foot (they need no lid window), the two switched ones with their transistors
RAIL = [("D1520", "R1520"), ("D1521", "R1521"), ("D1522", "R1522"), ("D1523", "R1523"), ("D1524", "R1524")]
for k, (d, r) in enumerate(RAIL):
    x = 131.6 + 1.1 * k
    q = two(r, "R_0402", x, 107.0, "N", first="1")                       # the supply end at the bottom
    two(d, "LED_0402", x, q[1] - 0.95, "N", first="2" if d in ("D1520", "D1521", "D1522") else "1")
at("Q1520", 139.5, 105.6, 90, fp="Package_TO_SOT_SMD:SOT-23")
at("Q1521", 139.5, 101.4, 90, fp="Package_TO_SOT_SMD:SOT-23")
near("R1525", "R_0402", ("Q1520", "1"), side="F")
near("R1526", "R_0402", ("Q1521", "1"), side="F")


# ---------------------------------------------------------------- where packed parts may go
WALL = 0.8


def walls():
    out = []
    for x0, y0, x1, y1 in FRAMES.values():
        out += [(x0, y0, x1, y0 + WALL), (x0, y1 - WALL, x1, y1), (x0, y0, x0 + WALL, y1), (x1 - WALL, y0, x1, y1)]
    return out


def allowed(side, b):
    x0, y0, x1, y1 = b
    if x0 < 89.6 or y1 > 127.2:
        return False
    if y0 < 108.45 and not (130.7 < x0 and x1 < 141.8 and y0 > 83.6):
        return False
    if x1 > 142.2 and y0 < 112.9:
        return False
    if side == "B":                          # U1313 keeps a 0.9 mm ring past its pads for its fan-out vias
        return y0 > 117.95 and not (x0 < UX + 3.75 and UX - 3.75 < x1 and y0 < UY + 3.75 and UY - 3.75 < y1)
    if x0 < 140.0 and 137.5 < x1 and y0 < 116.4 and 112.3 < y1:
        return False                         # east of U1312's control pins 26-32: their fan-out to the wall
    if math.hypot(max(x0, min(94.0, x1)) - 94.0, max(y0, min(112.25, y1)) - 112.25) < 5.2:
        return False                         # H1's clamp
    return not any(x0 < w[2] + 0.15 and w[0] - 0.15 < x1 and y0 < w[3] + 0.15 and w[1] - 0.15 < y1 for w in walls())


def _frame(ref, box):
    x0, y0, x1, y1 = box
    cx, cy, w, h = (x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0
    T = "\t"

    def strip(px, py, sw, sh):
        return (f'{T*2}(pad "1" smd rect\n{T*3}(at {px:g} {py:g})\n{T*3}(size {sw:g} {sh:g})\n'
                f'{T*3}(layers "F.Cu" "F.Mask" "F.Paste")\n{T*3}(net "GND")\n{T*3}(uuid "{uuid.uuid4()}")\n{T*2})\n')
    s = (f'{T}(footprint "kv260-ias2rf:SHIELD_FRAME"\n{T*2}(layer "F.Cu")\n{T*2}(uuid "{uuid.uuid4()}")\n'
         f'{T*2}(at {cx:g} {cy:g})\n'
         f'{T*2}(descr "Shield-can frame land, {w:g} x {h:g} mm, {WALL} mm wall: _work/rev08_place.py")\n'
         f'{T*2}(property "Reference" "{ref}"\n{T*3}(at 0 {-h / 2 - 0.8:g} 0)\n{T*3}(layer "F.SilkS")\n{T*3}(hide yes)\n'
         f'{T*3}(uuid "{uuid.uuid4()}")\n{T*3}(effects\n{T*4}(font\n{T*5}(size 1 1)\n{T*5}(thickness 0.15)\n{T*4})\n{T*3})\n{T*2})\n'
         f'{T*2}(property "Value" "SHIELD_FRAME_{w:g}x{h:g}"\n{T*3}(at 0 {h / 2 + 0.8:g} 0)\n{T*3}(layer "F.Fab")\n{T*3}(hide yes)\n'
         f'{T*3}(uuid "{uuid.uuid4()}")\n{T*3}(effects\n{T*4}(font\n{T*5}(size 1 1)\n{T*5}(thickness 0.15)\n{T*4})\n{T*3})\n{T*2})\n'
         f'{T*2}(attr smd board_only exclude_from_pos_files exclude_from_bom)\n')
    s += strip(0, -h / 2 + WALL / 2, w, WALL) + strip(0, h / 2 - WALL / 2, w, WALL)
    s += strip(-w / 2 + WALL / 2, 0, WALL, h - 2 * WALL) + strip(w / 2 - WALL / 2, 0, WALL, h - 2 * WALL)
    return s + f"{T})\n"


import uuid  # noqa: E402


def extra_items():
    """Board-only footprints made here: the shield-can frames (a ground ring each)."""
    return [_frame(r, b) for r, b in FRAMES.items()]
