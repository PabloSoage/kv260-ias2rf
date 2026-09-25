#!/usr/bin/env python3
"""
Remove the Altium-import symbols left on the root sheet: PCB1 (the bare board
as a BOM line), MRK1-MRK6 (fiducials), T1/T2 (board text) and LA1 (a label).
None has a library KiCad can find or a footprint, so each gave an ERC warning
and would have given a broken BOM line. Fiducials go back at layout, as KiCad
footprints. The drawn frame and logo from the original design are kept.

Usage:  py _work/rev03_drop_altium_relics.py
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import schgen                                        # noqa: E402

ROOT_SCH = os.path.join(os.path.dirname(HERE), "CSI2-KRIA-KV260_Rev01.kicad_sch")
RELICS = {"PCB1", "MRK1", "MRK2", "MRK3", "MRK4", "MRK5", "MRK6", "T1", "T2", "LA1"}

text = open(ROOT_SCH, encoding="utf-8").read()
cut = []
for m in re.finditer(r"\n\t\(symbol\n", text):
    s = m.start() + 2
    e = s + len(schgen._block(text, s))
    ref = re.search(r'\(property "Reference" "([^"]*)"', text[s:e]).group(1)
    if ref in RELICS:
        cut.append((s, e))
assert len(cut) == len(RELICS), f"found {len(cut)} of {len(RELICS)}"
for s, e in sorted(cut, reverse=True):
    text = text[:s - 2] + text[e:]
assert schgen._balanced(text)
open(ROOT_SCH, "w", encoding="utf-8", newline="\n").write(text)
print(f"removed {len(cut)} symbols: {', '.join(sorted(RELICS))}")
