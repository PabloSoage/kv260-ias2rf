#!/usr/bin/env python3
"""
Render one sheet of the project to PNG crops for visual review.

kicad-cli exports every sheet to SVG; PyMuPDF rasterises the one asked for.
Crops are given in sheet millimetres: x0,y0,x1,y1[,dpi].

Usage:  py _work/render_sheet.py ADC_SDR OUTDIR full=0,0,420,297,70 left=20,50,170,160
"""
import os
import subprocess
import sys
import tempfile

import pymupdf

from toolpaths import KICAD_CLI
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAPER = {"A3": (420, 297), "A2": (594, 420), "A4": (297, 210), "A1": (841, 594)}

name, out = sys.argv[1], sys.argv[2]
tmp = tempfile.mkdtemp()
subprocess.run([KICAD_CLI, "sch", "export", "svg", "-o", tmp,
                os.path.join(ROOT, "CSI2-KRIA-KV260_Rev01.kicad_sch")], check=True,
               capture_output=True)
svg = os.path.join(tmp, f"CSI2-KRIA-KV260_Rev01-{name}.svg" if name != "root"
                   else "CSI2-KRIA-KV260_Rev01.svg")
page = pymupdf.open(svg)[0]
paper = "A3"
for line in open(os.path.join(ROOT, "rev03", f"{name}.kicad_sch") if name != "root" else
                 os.path.join(ROOT, "CSI2-KRIA-KV260_Rev01.kicad_sch"), encoding="utf-8"):
    if "(paper" in line:
        paper = line.split('"')[1]
        break
W, H = PAPER[paper]
sx, sy = page.rect.width / W, page.rect.height / H
os.makedirs(out, exist_ok=True)
for spec in sys.argv[3:]:
    tag, nums = spec.split("=")
    v = [float(x) for x in nums.split(",")]
    dpi = int(v[4]) if len(v) > 4 else 140
    page.get_pixmap(dpi=dpi, clip=pymupdf.Rect(v[0] * sx, v[1] * sy, v[2] * sx, v[3] * sy)
                    ).save(os.path.join(out, f"{name}_{tag}.png"))
    print(os.path.join(out, f"{name}_{tag}.png"))
