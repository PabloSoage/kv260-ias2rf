#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""
Checks the tables of the documentation PDF page by page (REV08_PLAN 11.2), from what is drawn, not from the HTML.

Flags:
  (a) a header band (the navy fill of a table header) with no text in it;
  (b) a cell whose text crosses a row border (a cell taller than its row);
  (c) a table that starts at the top of a page with no header band above its first row.
(c) also catches tables that have no header at all; those are listed separately so they can be checked by eye.

Usage:  py _work/pdf_table_check.py [docs/KV260-IAS2RF_Documentation.pdf]    exit 1 if (a) or (b) is found
"""
import sys
from pathlib import Path

import pymupdf as fitz

NAVY = (0x0F / 255, 0x3A / 255, 0x60 / 255)
GRID = (0xCB / 255, 0xD5 / 255, 0xE1 / 255)
TOP = 46.0                       # export_documentation.py MARGIN_TOP
BOTTOM = 841.89 - 42.0           # A4 height less MARGIN_BOT; drawing below it is clipped


def near(c, t):
    return c is not None and len(c) >= 3 and all(abs(a - b) < 0.03 for a, b in zip(c, t))


def main():
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/KV260-IAS2RF_Documentation.pdf")
    doc = fitz.open(path)
    bad, look = [], []
    for pno, page in enumerate(doc, 1):
        words = [fitz.Rect(w[:4]) for w in page.get_text("words")]
        draws = page.get_drawings()
        navy = [d["rect"] for d in draws
                if near(d.get("fill"), NAVY) and d["rect"].width > 20 and TOP - 1 <= d["rect"].y0 and d["rect"].y1 <= BOTTOM + 1]
        # header cells only: drop the inline-code backgrounds drawn inside them
        navy = [r for r in navy if not any(o is not r and o.contains(r) and o != r for o in navy)]
        # (a) header rows: navy cells grouped by their top edge
        rows = {}
        for r in navy:
            rows.setdefault(round(r.y0), []).append(r)
        for y, cells in rows.items():
            band = fitz.Rect(min(c.x0 for c in cells), min(c.y0 for c in cells),
                             max(c.x1 for c in cells), max(c.y1 for c in cells))
            if band.height < 6 or not any(band.contains(w) or (w & band).height > 0.6 * w.height for w in words):
                bad.append(f"p{pno}: (a) empty header band at y={band.y0:.0f}, {band.height:.1f} pt tall")
        # (b) grid borders: thin horizontal strokes or fills in the table grid colour
        hlines = []
        for d in draws:
            col = d.get("color") if d.get("color") is not None else d.get("fill")
            if not near(col, GRID):
                continue
            r = d["rect"]
            if r.height <= 1.2 and r.width > 4:
                hlines.append(r)
        # a row border runs across the whole table: extend each border to the span of all borders at its height
        # (where cells are taller than their row, the other cells' borders stop short of the tall cell)
        spans = []
        for ln in sorted(hlines, key=lambda r: r.y0):
            y = (ln.y0 + ln.y1) / 2
            if spans and abs(spans[-1][0] - y) < 0.6:
                spans[-1][1] = min(spans[-1][1], ln.x0)
                spans[-1][2] = max(spans[-1][2], ln.x1)
            else:
                spans.append([y, ln.x0, ln.x1])
        for w in words:
            for ymid, x0, x1 in spans:
                if w.y0 + 1.0 < ymid < w.y1 - 1.0 and x0 < w.x1 - 1 and x1 > w.x0 + 1:
                    bad.append(f"p{pno}: (b) text crosses a row border at ({w.x0:.0f}, {ymid:.0f})")
                    break
        # (c) a table whose first border is at the top of the page with no navy band right there
        tops = [ln.y0 for ln in hlines if TOP - 1 <= ln.y0 < TOP + 14]
        if tops and not any(r.y0 < TOP + 14 for r in navy):
            look.append(f"p{pno}: (c) a table starts at the top of the page without a header band")
    for line in bad:
        print(line)
    for line in look:
        print(line)
    print(f"{len(doc)} pages: {len(bad)} defects (a, b); {len(look)} pages to check by eye (c)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
