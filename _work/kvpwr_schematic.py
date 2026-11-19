#!/usr/bin/env python3
"""
Single power entry (docs/POWER_SPEC.md section 1.4): the schematic edits outside the new KVPWR sheet
(_work/sheets/kvpwr.py), as text edits.

POWER
  - J1001 pin 1 no longer wires straight to F1001: J1001 pin 1 is VIN_JACK, F1001 pin 1 is VIN_J, both hierarchical
    labels led up from the pins; L1004 on KVPWR joins them (and feeds the KV260 branch from VIN_J).
  - J1001 pin 2 (the sleeve) loses its ground symbol: it is GND_IN, led down to a hierarchical label; L1004's second
    winding joins it to GND. The power flag that sat on that ground moves to the ground symbol at (66.04, 83.82).
root
  - KVPWR's block beside POWER's, joined pin to pin: VIN_JACK, GND_IN, VIN_J.

Usage:  py _work/kvpwr_schematic.py          (refuses to run twice)
"""
import os
import re
import sys
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "sheets"))
import kvpwr                                                       # noqa: E402

ROOT = os.path.dirname(HERE)
ROOT_SCH = os.path.join(ROOT, "KV260-IAS2RF.kicad_sch")
POWER = os.path.join(ROOT, "sheets", "POWER.kicad_sch")
T, NL = "\t", "\n"
U = lambda: str(uuid.uuid4())


def wire(a, b):
    return (f"{T}(wire{NL}{T*2}(pts{NL}{T*3}(xy {a[0]:g} {a[1]:g}) (xy {b[0]:g} {b[1]:g}){NL}{T*2}){NL}{T*2}(stroke{NL}"
            f"{T*3}(width 0){NL}{T*3}(type default){NL}{T*2}){NL}{T*2}(uuid \"{U()}\"){NL}{T})")


def hlabel(name, shape, x, y, ang, justify):
    return (f'{T}(hierarchical_label "{name}"{NL}{T*2}(shape {shape}){NL}{T*2}(at {x:g} {y:g} {ang}){NL}'
            f"{T*2}(effects{NL}{T*3}(font{NL}{T*4}(size 1.27 1.27){NL}{T*3}){NL}{T*3}(justify {justify}){NL}{T*2}){NL}"
            f'{T*2}(uuid "{U()}"){NL}{T})')


def power_sheet():
    t = open(POWER, encoding="utf-8").read()
    assert 'hierarchical_label "VIN_J"' not in t, "already applied"
    # 1. the J1001 -> F1001 wire
    w = re.search(r"\n\t\(wire\n\t\t\(pts\n\t\t\t\(xy 45\.72 76\.2\) \(xy 54\.61 76\.2\)\n\t\t\)[\s\S]*?\n\t\)", t)
    assert w, "J1001-F1001 wire"
    t = t[:w.start()] + t[w.end():]
    # 2. the ground symbol on J1001 pin 2 goes; the power flag moves to the ground at (66.04, 83.82)
    g = re.search(r'\n\t\(symbol\n\t\t\(lib_id "power:GND"\)\n\t\t\(at 45\.72 81\.28 0\)[\s\S]*?\n\t\)(?=\n)', t)
    assert g, "J1001 ground"
    t = t[:g.start()] + t[g.end():]
    f = re.search(r'\n\t\(symbol\n\t\t\(lib_id "power:PWR_FLAG"\)\n\t\t\(at 45\.72 81\.28 0\)[\s\S]*?\n\t\)(?=\n)', t)
    assert f, "power flag"
    blk = f.group(0).replace("(at 45.72 81.28 0)", "(at 66.04 83.82 0)", 1)
    blk = blk.replace("(at 45.72 85.09 0)", "(at 66.04 87.63 0)").replace("(at 45.72 77.47 0)", "(at 66.04 80.01 0)")
    blk = re.sub(r"\(at 45\.72 81\.28 0\)", "(at 66.04 83.82 0)", blk)
    t = t[:f.start()] + blk + t[f.end():]
    # 3. hierarchical labels, led up from J1001 pin 1 and F1001 pin 1, down from J1001 pin 2
    new = [wire((45.72, 76.2), (45.72, 68.58)), hlabel("VIN_JACK", "output", 45.72, 68.58, 90, "left"),
           wire((54.61, 76.2), (54.61, 68.58)), hlabel("VIN_J", "input", 54.61, 68.58, 90, "left"),
           wire((45.72, 81.28), (45.72, 88.9)), hlabel("GND_IN", "passive", 45.72, 88.9, 270, "right")]
    k = t.rfind("\n\t(sheet_instances")
    k = k if k > 0 else t.rstrip().rfind(")")
    t = t[:k] + NL + NL.join(new) + t[k:]
    open(POWER, "w", encoding="utf-8", newline=NL).write(t)
    print("POWER: VIN_JACK, VIN_J and GND_IN hierarchical labels; J1001 sleeve off GND")


def sheet_pin(name, shape, x, y, ang):
    j = "right" if ang == 0 else "left"
    return (f'{T*2}(pin "{name}" {shape}{NL}{T*3}(at {x:.2f} {y:.2f} {ang}){NL}{T*3}(uuid "{U()}"){NL}'
            f"{T*3}(effects{NL}{T*4}(font{NL}{T*5}(size 1.143 1.143){NL}{T*4}){NL}{T*4}(justify {j}){NL}{T*3}){NL}{T*2})")


def root():
    t = open(ROOT_SCH, encoding="utf-8").read()
    assert '"KVPWR"' not in t, "already applied"
    names = [("VIN_JACK", "output", "input"), ("GND_IN", "passive", "passive"), ("VIN_J", "input", "output")]
    # POWER's block (25.4, 266.7, 50.8 wide): pins on its right edge
    m = re.search(r'\(property "Sheetname" "POWER"', t)
    k = t.find(T * 2 + "(instances", m.start())
    t = t[:k] + NL.join(sheet_pin(n, sp, 76.2, 269.24 + 2.54 * i, 0) for i, (n, sp, _) in enumerate(names)) + NL + t[k:]
    X, Y, W = 101.6, 266.7, 50.8
    H = 2.54 * (len(names) + 2)
    blk = (f"{T}(sheet{NL}{T*2}(at {X} {Y}){NL}{T*2}(size {W} {H:.2f}){NL}{T*2}(exclude_from_sim no){NL}"
           f"{T*2}(in_bom yes){NL}{T*2}(on_board yes){NL}{T*2}(dnp no){NL}{T*2}(fields_autoplaced yes){NL}"
           f"{T*2}(stroke{NL}{T*3}(width 0.254){NL}{T*3}(type solid){NL}{T*3}(color 30 64 128 1){NL}{T*2}){NL}"
           f"{T*2}(fill{NL}{T*3}(color 245 248 255 0.9){NL}{T*2}){NL}{T*2}(uuid \"{kvpwr.BLOCK_UUID}\"){NL}"
           f'{T*2}(property "Sheetname" "KVPWR"{NL}{T*3}(at {X} {Y - 1:.2f} 0){NL}{T*3}(show_name no){NL}'
           f"{T*3}(do_not_autoplace no){NL}{T*3}(effects{NL}{T*4}(font{NL}{T*5}(size 1.524 1.524){NL}"
           f"{T*5}(bold yes){NL}{T*4}){NL}{T*4}(justify left bottom){NL}{T*3}){NL}{T*2}){NL}"
           f'{T*2}(property "Sheetfile" "sheets/KVPWR.kicad_sch"{NL}{T*3}(at {X} {Y + H + 0.8:.2f} 0){NL}'
           f"{T*3}(show_name no){NL}{T*3}(do_not_autoplace no){NL}{T*3}(effects{NL}{T*4}(font{NL}"
           f"{T*5}(size 1.143 1.143){NL}{T*4}){NL}{T*4}(justify left top){NL}{T*3}){NL}{T*2}){NL}"
           + NL.join(sheet_pin(n, kp, X, 269.24 + 2.54 * i, 180) for i, (n, _, kp) in enumerate(names))
           + f"{NL}{T*2}(instances{NL}{T*3}(project \"KV260-IAS2RF\"{NL}"
           f"{T*4}(path \"/{kvpwr.ROOT_UUID}\"{NL}{T*5}(page \"13\"){NL}{T*4}){NL}{T*3}){NL}{T*2}){NL}{T})")
    new = [blk] + [wire((76.2, 269.24 + 2.54 * i), (X, 269.24 + 2.54 * i)) for i in range(len(names))]
    end = t.rstrip().rfind(")")
    t = t[:end].rstrip(NL) + NL + NL.join(new) + NL + ")" + NL
    open(ROOT_SCH, "w", encoding="utf-8", newline=NL).write(t)
    print("root: KVPWR block, joined to POWER by VIN_JACK, GND_IN, VIN_J")


if __name__ == "__main__":
    power_sheet()
    root()
