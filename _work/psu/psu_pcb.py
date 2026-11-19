#!/usr/bin/env python3
"""
PSU board: psu/psu.kicad_pcb from the schematic's netlist, as text (no pcbnew): outline, stackup, every
footprint placed (PLACE), the copper pours of the power nets (POURS) and the ground planes, the tracks and vias
(TRACKS, VIAS, the routing's result).

4 layers, 1.6 mm, 2 oz outer: F.Cu parts and the power pours, In1.Cu ground, In2.Cu ground and the +12V bus
pour, B.Cu ground and short signal links. All three connectors on the left edge (the cables leave one side). The
power flows in a U: J1 (top left) -> protection -> filter (top row, to the right) -> the LM5177's power stage
(bottom row, to the left) -> U3 / U4 -> J2 / J3 (bottom left).

Usage:  py _work/psu/psu_pcb.py
"""
import os
import re
import subprocess
import sys
import tempfile
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from toolpaths import KICAD_CLI, stock_footprints          # noqa: E402
import rev08_pcb as P                                       # noqa: E402

ROOT = os.path.dirname(os.path.dirname(HERE))
PSU = os.path.join(ROOT, "psu")
BOARD = os.path.join(PSU, "psu.kicad_pcb")
NS = uuid.UUID("5d2e7c41-9a3b-4f6e-8c1d-2b3a4c5d6e7f")
X0, Y0, W, H = 100.0, 100.0, 110.0, 70.0


def U(*k):
    return str(uuid.uuid5(NS, "/".join(map(str, k))))


def netlist():
    out = os.path.join(tempfile.mkdtemp(), "psu.net")
    subprocess.run([KICAD_CLI, "sch", "export", "netlist", "--format", "kicadsexpr", "-o", out,
                    os.path.join(PSU, "psu.kicad_sch")], check=True, capture_output=True)
    t = open(out, encoding="utf-8").read()
    comps = {}
    cs, ce = t.find("(components"), t.find("\n\t(libparts")
    for blk in re.split(r"\n\t\t\(comp\b", t[cs:ce])[1:]:
        ref = re.search(r'\(ref "([^"]+)"\)', blk).group(1)
        val = re.search(r'\(value ' + P.STR + r'\)', blk).group(1)
        fp = re.search(r'\n\t\t\t\(footprint "([^"]*)"\)', blk)
        sp = re.search(r'\(sheetpath\s*\(names "([^"]*)"\)\s*\(tstamps "([^"]*)"\)\s*\)\s*\(tstamps "([^"]*)"\)', blk)
        comps[ref] = dict(value=val, footprint=fp.group(1) if fp else "", sheet=sp.group(1) if sp else "/",
                          path=(sp.group(2) + sp.group(3)) if sp else "", sheetfile="psu.kicad_sch",
                          dnp='(name "dnp")' in blk)
    pins = {}
    for m in re.finditer(r'\(net\s*\(code "?\d+"?\)\s*\(name ' + P.STR + r'\)(.*?)\n\t\t\)', t[t.find("\n\t(nets"):],
                         re.S):
        for n in re.finditer(r'\(ref "([^"]+)"\)\s*\(pin "([^"]+)"\)', m.group(2)):
            pins.setdefault(n.group(1), {})[n.group(2)] = m.group(1)
    return comps, pins


# 3-D bodies: KiCad's library names models it does not ship (the SON-8 MOSFETs, J1, J2/J3), and its electrolytics'
# and SON-8's near-white metal (0.82) burns out in the raytracer; tone_models() writes toned copies into mech/models3d
KIMOD = "${KICAD10_3DMODEL_DIR}/"
OWN = "${KIPRJMOD}/../mech/models3d/"
MODELS = {
    KIMOD + "Package_SON.3dshapes/Infineon_PG-TDSON-8_6.15x5.15mm.step": OWN + "TDSON-8-1.step",
    KIMOD + "Connector_JST.3dshapes/JST_VH_B2PS-VH_1x02_P3.96mm_Horizontal.step":
        OWN + "JST_VH_B2PS-VH_1x02_P3.96mm_Horizontal.step",
    KIMOD + "Connector_AMASS.3dshapes/AMASS_XT30PW-M_1x02_P2.50mm_Horizontal.step":
        OWN + "AMASS_XT30PW-M_1x02_P2.50mm_Horizontal.step",
    KIMOD + "Capacitor_SMD.3dshapes/CP_Elec_8x10.step": OWN + "CP_Elec_8x10.step",
    KIMOD + "Capacitor_SMD.3dshapes/CP_Elec_10x10.step": OWN + "CP_Elec_10x10.step",
    KIMOD + "Capacitor_SMD.3dshapes/CP_Elec_6.3x5.8.step": OWN + "CP_Elec_6.3x5.8.step",
}
TONED = {"TDSON-8-1.step": "Package_TO_SOT_SMD.3dshapes/TDSON-8-1.step",
         "CP_Elec_8x10.step": "Capacitor_SMD.3dshapes/CP_Elec_8x10.step",
         "CP_Elec_10x10.step": "Capacitor_SMD.3dshapes/CP_Elec_10x10.step",
         "CP_Elec_6.3x5.8.step": "Capacitor_SMD.3dshapes/CP_Elec_6.3x5.8.step"}


def tone_models():
    """copies of KiCad's models with the near-white metal (0.82) set to an aluminium grey (0.50)"""
    src = os.path.join(os.path.dirname(os.path.dirname(stock_footprints())), "3dmodels")
    dst = os.path.join(ROOT, "mech", "models3d")
    for name, rel in TONED.items():
        t = open(os.path.join(src, rel), encoding="utf-8", errors="replace").read()
        t2 = t.replace("COLOUR_RGB('',0.824000000954,0.819999992847,0.78100001812)", "COLOUR_RGB('',0.50,0.50,0.49)")
        assert t2 != t, name
        open(os.path.join(dst, name), "w", encoding="utf-8", newline="\n").write(t2)


def lib_text(lib_id):
    lib, name = lib_id.split(":", 1)
    d = os.path.join(PSU, "psu.pretty") if lib == "psu" else os.path.join(stock_footprints(), lib + ".pretty")
    t = open(os.path.join(d, name + ".kicad_mod"), encoding="utf-8").read()
    for old, new in MODELS.items():
        t = t.replace(f'(model "{old}"', f'(model "{new}"')
    return t


# ref: (x, y, rotation, side)
PLACE = {
    # input and protection (top left)
    "J1": (113.0, 112.0, 90, "F"), "D1": (113.0, 129.0, 270, "F"), "D2": (121.0, 129.0, 270, "F"),
    "C4": (119.0, 103.5, 0, "F"), "C5": (119.0, 107.0, 0, "F"),
    "Q1": (129.0, 109.0, 180, "F"), "Q2": (146.0, 108.0, 0, "F"),
    "U1": (136.0, 123.5, 0, "F"),
    "R4": (127.5, 130.0, 0, "F"), "C1": (132.5, 128.0, 90, "F"), "D3": (126.0, 134.0, 0, "F"),
    "D4": (130.3, 134.0, 0, "F"), "D5": (136.0, 135.0, 0, "F"), "R5": (129.5, 121.0, 90, "F"),
    "R6": (129.5, 124.5, 90, "F"), "R7": (142.5, 121.0, 90, "F"), "R8": (142.5, 124.5, 90, "F"),
    "C2": (140.5, 128.5, 0, "F"), "C3": (136.5, 118.6, 0, "F"), "D6": (140.0, 116.3, 0, "F"),
    "D7": (142.0, 113.0, 0, "F"), "R9": (143.5, 131.5, 0, "F"), "D11": (147.0, 131.5, 0, "F"),
    # first filter stage
    "C6": (154.0, 126.0, 0, "F"), "C7": (155.0, 104.5, 0, "F"), "C8": (155.0, 108.5, 0, "F"),
    "C9": (155.0, 112.0, 0, "F"), "C10": (155.0, 114.5, 0, "F"),
    "L3": (167.5, 110.0, 0, "F"), "C11": (164.0, 121.5, 0, "F"), "C12": (170.0, 121.5, 0, "F"),
    "L2": (183.5, 110.0, 0, "F"), "R2": (193.0, 110.0, 90, "F"),
    "C18": (201.5, 109.0, 0, "F"), "C17": (201.5, 121.5, 0, "F"),
    "C13": (191.6, 130.5, 0, "F"), "C14": (196.2, 130.5, 0, "F"), "C15": (200.8, 130.5, 0, "F"),
    "C16": (205.4, 130.5, 0, "F"), "C19": (192.4, 127.0, 0, "F"),
    # power stage (bottom row, right to left)
    "Q3": (199.0, 138.0, 90, "F"), "Q4": (199.0, 147.5, 90, "F"), "R1": (191.5, 151.5, 270, "F"),
    "L1": (178.0, 158.5, 180, "F"), "Q6": (162.0, 139.0, 90, "F"), "Q5": (162.0, 148.5, 90, "F"),
    "U2": (179.0, 137.0, 270, "F"),
    # U2's parts: three rows above it, the driver side below it
    "R20": (170.4, 129.2, 90, "F"), "R21": (173.6, 129.2, 90, "F"), "C28": (175.2, 129.2, 90, "F"),
    "R23": (178.4, 129.2, 90, "F"), "R25": (183.2, 129.2, 90, "F"), "R10": (186.4, 129.2, 90, "F"),
    "R19": (170.4, 125.6, 90, "F"), "C27": (172.0, 129.2, 90, "F"), "C26": (173.6, 125.6, 90, "F"),
    "R22": (176.8, 129.2, 90, "F"), "R24": (180.0, 129.2, 90, "F"), "C29": (183.2, 125.6, 90, "F"),
    "R11": (184.8, 129.2, 90, "F"), "R26": (181.6, 129.2, 90, "F"), "R12": (188.0, 129.2, 90, "F"),
    "C20": (188.0, 125.6, 90, "F"),
    "C21": (180.2, 145.2, 90, "F"), "C22": (177.9, 145.2, 90, "F"),
    "C23": (184.6, 143.5, 90, "F"), "C24": (174.6, 143.5, 90, "F"),
    "R17": (187.2, 145.2, 0, "F"), "R18": (187.2, 147.2, 0, "F"), "C25": (184.6, 147.6, 90, "F"),
    "R13": (203.8, 141.0, 90, "F"), "R14": (203.8, 150.5, 90, "F"), "R15": (166.0, 153.0, 180, "F"),
    "R16": (166.5, 139.5, 180, "F"),
    # output (bottom left)
    "C32": (145.0, 134.0, 0, "F"), "C33": (149.7, 134.0, 0, "F"), "C34": (154.4, 134.0, 0, "F"),
    "C35": (145.0, 138.8, 0, "F"), "C36": (149.7, 138.8, 0, "F"), "C37": (154.4, 138.8, 0, "F"),
    "C38": (149.0, 146.0, 0, "F"), "C39": (149.0, 155.0, 0, "F"),
    "R29": (140.5, 149.0, 90, "F"), "D10": (140.5, 152.5, 90, "F"),
    "U3": (129.0, 145.0, 180, "F"), "U4": (129.0, 160.0, 180, "F"),
    "R40": (136.5, 142.0, 0, "F"), "R41": (136.5, 144.0, 0, "F"), "R42": (136.5, 146.0, 0, "F"),
    "R43": (136.5, 148.0, 0, "F"), "C40": (139.0, 145.0, 90, "F"), "C41": (123.0, 141.0, 90, "F"),
    "D8": (123.0, 148.5, 90, "F"), "J2": (115.4, 145.0, 270, "F"),
    "R50": (136.5, 157.0, 0, "F"), "R51": (136.5, 159.0, 0, "F"), "R52": (136.5, 161.0, 0, "F"),
    "R53": (136.5, 163.0, 0, "F"), "C50": (139.0, 160.0, 90, "F"), "C51": (123.0, 156.0, 90, "F"),
    "D9": (123.0, 163.5, 90, "F"), "J3": (115.4, 160.0, 270, "F"),
}
# the power pours on F.Cu: (net, layer, polygon, priority). KiCad's fill keeps the clearance to every other
# net's pad, so the outlines only have to keep the nets apart from each other.
POURS = [
    ("/VBAT", "F", [(106.0, 101.0), (134.6, 101.0), (134.6, 114.6), (116.6, 114.6), (116.6, 127.6),
                    (109.4, 127.6), (109.4, 120.0), (106.0, 120.0)], 2),
    ("/TVS_MID", "F", [(110.6, 130.2), (123.6, 130.2), (123.6, 134.6), (110.6, 134.6)], 2),
    ("/VS", "F", [(135.0, 103.0), (144.3, 103.0), (144.3, 109.2), (135.0, 109.2)], 2),
    ("/B0", "F", [(144.6, 101.0), (163.8, 101.0), (163.8, 116.6), (158.4, 116.6), (158.4, 129.6),
                  (148.6, 129.6), (148.6, 116.6), (144.6, 116.6)], 2),
    ("/B", "F", [(171.3, 102.0), (179.6, 102.0), (179.6, 124.2), (161.6, 124.2), (161.6, 119.4),
                 (171.3, 119.4)], 2),
    ("/B2", "F", [(187.4, 102.5), (190.9, 102.5), (190.9, 111.2), (194.4, 111.2), (194.4, 115.3),
                  (187.4, 115.3)], 3),
    ("/VIN", "F", [(191.6, 102.5), (209.4, 102.5), (209.4, 139.9), (196.4, 139.9), (196.4, 132.9),
                   (189.4, 132.9), (189.4, 125.2), (191.6, 125.2)], 2),
    ("/SW1", "F", [(189.8, 140.2), (200.2, 140.2), (200.2, 142.0), (202.4, 142.0), (202.4, 149.6),
                   (189.8, 149.6)], 2),
    ("/LX", "F", [(183.8, 151.8), (193.6, 151.8), (193.6, 166.2), (183.8, 166.2)], 2),
    ("/SW2", "F", [(158.6, 140.9), (163.2, 140.9), (163.2, 142.6), (172.4, 142.6), (172.4, 166.2),
                   (168.4, 166.2), (168.4, 150.6), (158.6, 150.6)], 2),
    ("+12V", "F", [(140.4, 131.8), (164.8, 131.8), (164.8, 140.7), (157.2, 140.7), (157.2, 157.2),
                   (142.6, 157.2), (142.6, 141.6), (140.4, 141.6)], 2),
    ("/OUT_A", "F", [(101.6, 141.3), (124.6, 141.3), (124.6, 145.45), (127.6, 145.45), (127.6, 146.6),
                     (124.6, 146.6), (124.6, 152.6), (101.6, 152.6)], 2),
    ("/OUT_K", "F", [(101.6, 156.3), (124.6, 156.3), (124.6, 160.45), (127.6, 160.45), (127.6, 161.6),
                     (124.6, 161.6), (124.6, 168.6), (101.6, 168.6)], 2),
]
BOARD_POLY = [(100.0, 100.0), (210.0, 100.0), (210.0, 170.0), (100.0, 170.0)]
# the planes: In1 ground, In2 +12V, and ground poured over whatever F.Cu and B.Cu leave free
PLANES = [("GND", "In1.Cu", 0), ("+12V", "In2.Cu", 0), ("GND", "F.Cu", 0), ("GND", "B.Cu", 0)]
LAYER = {"F": "F.Cu", "B": "B.Cu"}


def zone(net, layer, prio, pts, name, clearance=0.3):
    xy = " ".join(f"(xy {x:g} {y:g})" for x, y in pts)
    return (f'\t(zone\n\t\t(net "{net}")\n\t\t(layer "{layer}")\n\t\t(uuid "{U("zone", name)}")\n'
            f'\t\t(name "{name}")\n\t\t(hatch edge 0.5)\n\t\t(priority {prio})\n\t\t(connect_pads yes\n'
            f'\t\t\t(clearance {clearance:g})\n\t\t)\n\t\t(min_thickness 0.25)\n\t\t(fill yes\n'
            f'\t\t\t(thermal_gap 0.3)\n\t\t\t(thermal_bridge_width 0.3)\n\t\t\t(island_removal_mode 0)\n\t\t)\n'
            f'\t\t(polygon\n\t\t\t(pts\n\t\t\t\t{xy}\n\t\t\t)\n\t\t)\n\t)\n')


def seg(a, b, w, layer, net, k):
    return (f'\t(segment\n\t\t(start {a[0]:g} {a[1]:g})\n\t\t(end {b[0]:g} {b[1]:g})\n\t\t(width {w:g})\n'
            f'\t\t(layer "{layer}")\n\t\t(net "{net}")\n\t\t(uuid "{U("seg", k)}")\n\t)\n')


def via(x, y, d, drill, net, k):
    return (f'\t(via\n\t\t(at {x:g} {y:g})\n\t\t(size {d:g})\n\t\t(drill {drill:g})\n'
            f'\t\t(layers "F.Cu" "B.Cu")\n\t\t(net "{net}")\n\t\t(uuid "{U("via", k)}")\n\t)\n')


def copper():
    """pours, planes, and the routed tracks and vias of psu_routes.json"""
    import json
    out = []
    for i, (net, layer, pts, prio) in enumerate(POURS):
        out.append(zone(net, LAYER[layer], prio, pts, f"PSU {net.strip('/')} {i}"))
    for net, layer, prio in PLANES:
        out.append(zone(net, layer, prio, BOARD_POLY, f"PSU {net} plane {layer}", clearance=0.3))
    rpath = os.path.join(HERE, "psu_routes.json")
    if os.path.exists(rpath):
        r = json.load(open(rpath))
        for k, (x1, y1, x2, y2, w, layer, net) in enumerate(r["segs"]):
            out.append(seg((x1, y1), (x2, y2), w, LAYER[layer], net, k))
        for k, (x, y, d, drill, net) in enumerate(r["vias"]):
            out.append(via(x, y, d, drill, net, k))
    return "".join(out)


HOLES = [(103.5, 103.5), (206.5, 157.0), (141.0, 166.5), (103.5, 135.0)]


def header(nets):
    t = ['(kicad_pcb\n\t(version 20241229)\n\t(generator "kv260-ias2rf/_work/psu/psu_pcb.py")\n'
         '\t(generator_version "10.0")\n\t(general\n\t\t(thickness 1.6)\n\t\t(legacy_teardrops no)\n\t)\n'
         '\t(paper "A4")\n\t(title_block\n\t\t(title "PSU - vehicle and bench power for the adapter and the KV260")\n'
         '\t\t(rev "1")\n\t\t(company "kv260-ias2rf")\n\t)\n\t(layers\n'
         '\t\t(0 "F.Cu" signal)\n\t\t(4 "In1.Cu" signal)\n\t\t(6 "In2.Cu" signal)\n\t\t(2 "B.Cu" signal)\n'
         '\t\t(9 "F.Adhes" user "F.Adhesive")\n\t\t(11 "B.Adhes" user "B.Adhesive")\n'
         '\t\t(13 "F.Paste" user)\n\t\t(15 "B.Paste" user)\n\t\t(5 "F.SilkS" user "F.Silkscreen")\n'
         '\t\t(7 "B.SilkS" user "B.Silkscreen")\n\t\t(1 "F.Mask" user)\n\t\t(3 "B.Mask" user)\n'
         '\t\t(17 "Dwgs.User" user "User.Drawings")\n\t\t(19 "Cmts.User" user "User.Comments")\n'
         '\t\t(25 "Edge.Cuts" user)\n\t\t(27 "Margin" user)\n\t\t(31 "F.CrtYd" user "F.Courtyard")\n'
         '\t\t(29 "B.CrtYd" user "B.Courtyard")\n\t\t(35 "F.Fab" user)\n\t\t(33 "B.Fab" user)\n\t)\n'
         '\t(setup\n\t\t(stackup\n'
         '\t\t\t(layer "F.SilkS" (type "Top Silk Screen"))\n\t\t\t(layer "F.Paste" (type "Top Solder Paste"))\n'
         '\t\t\t(layer "F.Mask" (type "Top Solder Mask") (color "#1E6B30E6") (thickness 0.01))\n'
         '\t\t\t(layer "F.Cu" (type "copper") (thickness 0.07))\n'
         '\t\t\t(layer "dielectric 1" (type "prepreg") (thickness 0.2104) (material "FR4") (epsilon_r 4.4) (loss_tangent 0.02))\n'
         '\t\t\t(layer "In1.Cu" (type "copper") (thickness 0.0152))\n'
         '\t\t\t(layer "dielectric 2" (type "core") (thickness 1.065) (material "FR4") (epsilon_r 4.6) (loss_tangent 0.02))\n'
         '\t\t\t(layer "In2.Cu" (type "copper") (thickness 0.0152))\n'
         '\t\t\t(layer "dielectric 3" (type "prepreg") (thickness 0.2104) (material "FR4") (epsilon_r 4.4) (loss_tangent 0.02))\n'
         '\t\t\t(layer "B.Cu" (type "copper") (thickness 0.07))\n'
         '\t\t\t(layer "B.Mask" (type "Bottom Solder Mask") (color "#1E6B30E6") (thickness 0.01))\n'
         '\t\t\t(layer "B.Paste" (type "Bottom Solder Paste"))\n\t\t\t(layer "B.SilkS" (type "Bottom Silk Screen"))\n'
         '\t\t\t(copper_finish "ENIG")\n\t\t\t(dielectric_constraints no)\n\t\t)\n'
         '\t\t(pad_to_mask_clearance 0)\n\t\t(allow_soldermask_bridges_in_footprints no)\n'
         '\t\t(pcbplotparams\n\t\t\t(layerselection 0x00000000_00000000_55555555_5755f5ff)\n'
         '\t\t\t(outputformat 1)\n\t\t\t(outputdirectory "")\n\t\t)\n\t)\n']
    t.append('\t(net 0 "")\n')
    for i, n in enumerate(nets, 1):
        t.append(f'\t(net {i} "{n}")\n')
    return "".join(t)


def outline():
    pts = [(X0, Y0), (X0 + W, Y0), (X0 + W, Y0 + H), (X0, Y0 + H)]
    out = []
    for i, (a, b) in enumerate(zip(pts, pts[1:] + pts[:1])):
        out.append(f'\t(gr_line\n\t\t(start {a[0]:g} {a[1]:g})\n\t\t(end {b[0]:g} {b[1]:g})\n\t\t(stroke\n'
                   f'\t\t\t(width 0.1)\n\t\t\t(type default)\n\t\t)\n\t\t(layer "Edge.Cuts")\n\t\t(uuid "{U("edge", i)}")\n\t)\n')
    return "".join(out)


def hole(i, x, y):
    return (f'\t(footprint "MountingHole:MountingHole_3.2mm_M3"\n\t\t(layer "F.Cu")\n\t\t(uuid "{U("hole", i)}")\n'
            f'\t\t(at {x:g} {y:g})\n\t\t(property "Reference" "H{i + 1}"\n\t\t\t(at 0 -4.2 0)\n\t\t\t(layer "F.SilkS")\n'
            f'\t\t\t(hide yes)\n\t\t\t(uuid "{U("hole", i, "ref")}")\n\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1 1)\n'
            f'\t\t\t\t\t(thickness 0.15)\n\t\t\t\t)\n\t\t\t)\n\t\t)\n\t\t(property "Value" "M3"\n\t\t\t(at 0 4.2 0)\n'
            f'\t\t\t(layer "F.Fab")\n\t\t\t(hide yes)\n\t\t\t(uuid "{U("hole", i, "val")}")\n\t\t\t(effects\n'
            f'\t\t\t\t(font\n\t\t\t\t\t(size 1 1)\n\t\t\t\t\t(thickness 0.15)\n\t\t\t\t)\n\t\t\t)\n\t\t)\n'
            f'\t\t(attr exclude_from_pos_files exclude_from_bom board_only)\n'
            f'\t\t(fp_circle\n\t\t\t(center 0 0)\n\t\t\t(end 3.45 0)\n\t\t\t(stroke\n\t\t\t\t(width 0.05)\n'
            f'\t\t\t\t(type solid)\n\t\t\t)\n\t\t\t(fill no)\n\t\t\t(layer "F.CrtYd")\n\t\t\t(uuid "{U("hole", i, "cy")}")\n\t\t)\n'
            f'\t\t(pad "" np_thru_hole circle\n\t\t\t(at 0 0)\n\t\t\t(size 3.2 3.2)\n\t\t\t(drill 3.2)\n'
            f'\t\t\t(layers "*.Cu" "*.Mask")\n\t\t\t(uuid "{U("hole", i, "pad")}")\n\t\t)\n\t)\n')


def build(extra=""):
    comps, pins = netlist()
    nets = sorted({n for p in pins.values() for n in p.values()})
    t = header(nets) + outline()
    for i, (x, y) in enumerate(HOLES):
        t += hole(i, x, y)
    for ref, (x, y, a, side) in PLACE.items():
        c = comps[ref]
        t += P.place(lib_text(c["footprint"]), c["footprint"], ref, c, pins[ref], x, y, a, side == "B")
    missing = set(comps) - set(PLACE)
    t += extra
    t += "\t(embedded_fonts no)\n)\n"
    open(BOARD, "w", encoding="utf-8", newline="\n").write(t)
    return comps, pins, missing


if __name__ == "__main__":
    tone_models()
    c, p, missing = build(copper())
    print(f"wrote {os.path.relpath(BOARD, ROOT)}: {len(PLACE)} parts; not placed: {sorted(missing)}")
