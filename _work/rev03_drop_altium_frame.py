#!/usr/bin/env python3
"""
Remove the title frame drawn by hand in the original Altium design from the
root sheet: its 27 lines, the texts inside it (x 236-389, y 250-292) and the
Allied Vision logo. KiCad's own title block, filled in below, takes its
place. Attribution to the original Allied Vision design stays in README.md
and LICENSE.

Usage:  py _work/rev03_drop_altium_frame.py
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import schgen                                        # noqa: E402

ROOT_SCH = os.path.join(os.path.dirname(HERE), "CSI2-KRIA-KV260_Rev01.kicad_sch")
text = open(ROOT_SCH, encoding="utf-8").read()
cut = []
for head in ("polyline", "text", "image"):
    for m in re.finditer(r"\n\t\(" + head + r"[\s\n]", text):
        s = m.start() + 2
        e = s + len(schgen._block(text, s))
        x, y = map(float, re.search(r"\((?:at|xy) ([\d.\-]+) ([\d.\-]+)", text[s:e]).groups())
        if 230 <= x <= 395 and 250 <= y <= 295:
            cut.append((s, e, head))
kinds = {h: sum(1 for *_, k in cut if k == h) for h in ("polyline", "text", "image")}
assert kinds["image"] == 1 and kinds["polyline"] == 27, kinds
for s, e, _ in sorted(cut, reverse=True):
    text = text[:s - 2] + text[e:]
tb = schgen._block(text, text.index("(title_block"))
new_tb = ('(title_block\n\t\t(title "KV260-IAS2RF Rev03 - root: sheet hierarchy")\n'
          '\t\t(rev "03")\n\t\t(company "KV260-IAS2RF")\n'
          '\t\t(comment 1 "Derived from the Allied Vision CSI-2 adapter for Kria KV260 (MIT), see README")\n\t)')
text = text.replace(tb, new_tb, 1)
assert schgen._balanced(text)
open(ROOT_SCH, "w", encoding="utf-8", newline="\n").write(text)
print(f"removed {len(cut)} items: {kinds}; title block filled in")
