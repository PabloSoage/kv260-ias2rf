"""
Shared data for the layout scripts: the netlist KiCad exports from the
schematic, and the footprints it names, read as text (never through
pcbnew - see the note in _work/layout/build_board.py).
"""

import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.dirname(HERE)
ROOT = os.path.dirname(WORK)
sys.path.insert(0, WORK)
import schgen                                        # noqa: E402

KICAD_CLI = "E:/Program Files/KiCad/10.0/bin/kicad-cli.exe"
ROOT_SCH = os.path.join(ROOT, "CSI2-KRIA-KV260_Rev01.kicad_sch")
FP_DIRS = {"kv260-ias2rf": os.path.join(ROOT, "footprints", "kv260-ias2rf.pretty")}
STOCK_FP = "E:/Program Files/KiCad/10.0/share/kicad/footprints/"


class Comp:
    def __init__(self, ref, value, fpid, sheet, path):
        self.ref, self.value, self.fpid, self.sheet, self.path = ref, value, fpid, sheet, path
        self.pads = {}                              # pad number -> net name


def netlist():
    out = os.path.join(tempfile.gettempdir(), "kv260_layout.net")
    subprocess.run([KICAD_CLI, "sch", "export", "netlist", ROOT_SCH, "-o", out],
                   check=True, capture_output=True)
    text = open(out, encoding="utf-8").read()
    comps = {}
    for m in re.finditer(r"\(comp\s*\(ref \"([^\"]+)\"\)", text):
        s = m.start()
        b = schgen._block(text, s)
        ref = m.group(1)
        value = re.search(r'\(value "([^"]*)"\)', b).group(1)
        fpid = re.search(r'\(footprint "([^"]*)"\)', b).group(1)
        names = re.search(r'\(sheetpath\s*\(names "([^"]*)"\)\s*\(tstamps "([^"]*)"\)', b)
        stamp = re.search(r'\n\t\t\t\(tstamps "([^"]+)"', b).group(1)
        sheet = names.group(1).strip("/") or "root"
        sfile = re.search(r'\(name "Sheetfile"\)\s*\(value "([^"]*)"\)', b)
        c = Comp(ref, value, fpid, sheet, names.group(2) + stamp)
        c.sheetname, c.sheetfile = names.group(1), sfile.group(1) if sfile else ""
        comps[ref] = c
    for m in re.finditer(r'\(net\s*\(code "?\d+"?\)\s*\(name "([^"]*)"\)', text):
        b = schgen._block(text, m.start())
        for ref, pin in re.findall(r'\(node\s*\(ref "([^"]+)"\)\s*\(pin "([^"]+)"\)', b):
            comps[ref].pads[pin] = m.group(1)
    return comps


def fp_text(fpid):
    lib, name = fpid.split(":", 1)
    d = FP_DIRS.get(lib, STOCK_FP + lib + ".pretty")
    return open(os.path.join(d, name + ".kicad_mod"), encoding="utf-8").read()


def courtyard(text):
    """(xmin, ymin, xmax, ymax) of F.CrtYd graphics, or of the pads + 0.25."""
    xs, ys = [], []
    for m in re.finditer(r"\((fp_line|fp_rect|fp_poly|fp_circle|fp_arc)\b", text):
        b = schgen._block(text, m.start())
        if '"F.CrtYd"' not in b:
            continue
        pts = [(float(a), float(c)) for a, c in
               re.findall(r"\((?:start|end|mid|xy|center) ([\d.\-]+) ([\d.\-]+)\)", b)]
        if m.group(1) == "fp_circle":
            (cx, cy), (ex, ey) = pts[0], pts[1]
            r = ((ex - cx) ** 2 + (ey - cy) ** 2) ** 0.5
            pts = [(cx - r, cy - r), (cx + r, cy + r)]
        xs += [p[0] for p in pts]
        ys += [p[1] for p in pts]
    if not xs:
        for m in re.finditer(r'\(pad "[^"]*" \w+ \w+\s*\(at ([\d.\-]+) ([\d.\-]+)[^)]*\)\s*\(size ([\d.]+) ([\d.]+)\)', text):
            x, y, w, h = map(float, m.groups())
            xs += [x - w / 2 - 0.25, x + w / 2 + 0.25]
            ys += [y - h / 2 - 0.25, y + h / 2 + 0.25]
    return min(xs), min(ys), max(xs), max(ys)
