#!/usr/bin/env python3
"""
J1503 becomes the vertical JST-SH BM06B-SRSS-TB (18 November 2026, before the Rev08 tag), as text edits.

The side-entry SM06B opened north, 2.8 mm from the back of J1502: the plug and its wires had no room, and no finger
could reach it. The vertical part takes the plug from above. Its six pads are where the SM06B's were (same x, the
same y 114.6, the same 0.6 x 1.55 mm), so the copper to the pins does not change. Rotated 0 instead of 180, its
pin 1 is the west pad, so the pin-out is the old one mirrored: 1 ground, 2 CANL, 3 CANH, 4 ground, 5 PPS, 6 GPS 3.3 V
(_work/sheets/status_spec.py, the STATUS sheet). Its two mounting tabs sit 1.35 mm further south than the SM06B's:

  - the old tabs' stubs and the west tab's own via go;
  - J9_CAN_TX10, which ran down x 197.45 where the east tab now is, is lifted whole, to be routed again;
  - the tabs get their ground vias with stubvia.py, and J9_CAN_TX10 its route with fastroute.py, after this script.

Then run _work/rev08_final_models.py, which points J1503 at its toned 3-D model.

Usage:  py _work/rev08_j1503_vertical.py <in.kicad_pcb> <out.kicad_pcb>
"""
import math
import os
import re
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from toolpaths import stock_footprints  # noqa: E402

LIB = os.path.join(stock_footprints(),
                   "Connector_JST.pretty", "JST_SH_BM06B-SRSS-TB_1x06-1MP_P1.00mm_Vertical.kicad_mod")
NAME = "Connector_JST:JST_SH_BM06B-SRSS-TB_1x06-1MP_P1.00mm_Vertical"
AT = (194.4, 113.275)            # pads at y 114.6 (local y 1.325), x 191.9 to 196.9 as before
NETS = {"1": "GND", "2": "/STATUS/CAN_L", "3": "/STATUS/CAN_H", "4": "GND", "5": "/STATUS/GPS_PPS_IN",
        "6": "/STATUS/GPS_3V3", "MP": "GND"}
OLD_TABS = [(198.2, 110.725), (190.6, 110.725)]
OLD_TAB_VIA = (190.249, 110.532)
LIFT = "/STATUS/J9_CAN_TX10"
U = lambda: str(uuid.uuid4())


def footprint(old):
    lib = open(LIB, encoding="utf-8").read().strip()
    lib = re.sub(r'\n\t\(version [^)]*\)|\n\t\(generator [^)]*\)|\n\t\(generator_version [^)]*\)', "", lib)
    lib = lib.replace('(footprint "JST_SH_BM06B-SRSS-TB_1x06-1MP_P1.00mm_Vertical"', f'(footprint "{NAME}"', 1)
    keep = lambda k: re.search(r'\n\t\t\(%s [^\n]*' % k, old).group(0)[3:]
    head = f'(layer "F.Cu")\n\t{keep("uuid")}\n\t(at {AT[0]:g} {AT[1]:g})'
    lib = lib.replace('(layer "F.Cu")', head, 1)
    lib = lib.replace('(property "Reference" "REF**"', '(property "Reference" "J1503"', 1)
    lib = re.sub(r'(\(property "Reference" "J1503"\n\t\t\(at [^\n]*\n\t\t\(layer "F.SilkS"\))', r'\1\n\t\t(hide yes)', lib)
    lib = re.sub(r'\(property "Value" "[^"]*"', '(property "Value" "BM06B-SRSS-TB"', lib, count=1)
    link = "\n\t".join(keep(k) for k in ("path", "sheetname", "sheetfile"))
    lib = lib.replace("\t(attr smd)", f"\t{link}\n\t(attr smd)", 1)

    def pad(m):
        body = m.group(0)
        return body[:-2] + f'\t\t(net "{NETS[m.group(1)]}")\n\t\t(uuid "{U()}")\n\t)'
    lib = re.sub(r'\(pad "([^"]+)" smd roundrect\n.*?\n\t\)', pad, lib, flags=re.S)
    return "\n".join("\t" + ln for ln in lib.split("\n"))


def drop(t, pred):
    out, pos, n = [], 0, 0
    for m in re.finditer(r'\n\t\((segment|via|arc)\n(.*?)\n\t\)', t, re.S):
        if pred(m.group(1), m.group(2)):
            out.append(t[pos:m.start()])
            pos = m.end()
            n += 1
    out.append(t[pos:])
    return "".join(out), n


def near(b, pts, tol=0.02):
    ends = [tuple(map(float, q)) for q in re.findall(r'\((?:start|end|at) ([-\d.]+) ([-\d.]+)\)', b)]
    return any(math.hypot(x - px, y - py) < tol for x, y in ends for px, py in pts)


def main(inp, out):
    t = open(inp, encoding="utf-8").read()
    i = t.find('(property "Reference" "J1503"')
    s, e = t.rfind("\n\t(footprint", 0, i) + 1, t.find("\n\t(footprint", i) + 1
    t = t[:s] + footprint(t[s:e]) + "\n" + t[e:]
    t, n1 = drop(t, lambda k, b: '(net "GND")' in b and (
        (k == "segment" and near(b, OLD_TABS)) or (k == "via" and near(b, [OLD_TAB_VIA]))))
    t, n2 = drop(t, lambda k, b: f'(net "{LIFT}")' in b)
    open(out, "w", encoding="utf-8", newline="\n").write(t)
    print(f"J1503 -> {NAME} at {AT}; {n1} old tab items dropped, {LIFT} lifted ({n2} items)")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
