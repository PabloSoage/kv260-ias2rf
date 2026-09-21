#!/usr/bin/env python3
"""
Remove the two sheets that implement the dead architecture from the project.

FRONTEND.kicad_sch and PHASED_ARRAY.kicad_sch were script-generated for the
Rev01/Rev02 architecture, which was invalidated when blocker B-01 closed
(IAS0 does not reach the programmable logic; see docs/BLOCKERS_AND_RISKS.md).
They also have defects of their own: the 8 ADAR1000s in PHASED_ARRAY have no
power connected (their B units are not placed) and the interface connector the
documentation described is not instantiated at all.

Leaving them registered makes KiCad load them and makes ERC mix their
violations with those of the schematic that is actually worth keeping.

What this does:
  1. Removes the (sheet ...) blocks that reference them from the root schematic.
  2. Removes their UUIDs from sheets[] in the .kicad_pro.
  3. Moves the files to _deprecated/.
  4. Checks that the result has balanced parentheses.

Nothing is destroyed: the files stay in _deprecated/ and in git history.

Usage:  py _work/rev03_drop_dead_sheets.py [--dry-run]
"""

import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCH = os.path.join(ROOT, "CSI2-KRIA-KV260_Rev01.kicad_sch")
PRO = os.path.join(ROOT, "CSI2-KRIA-KV260_Rev01.kicad_pro")
DEPRECATED = os.path.join(ROOT, "_deprecated")

DEAD = ["FRONTEND.kicad_sch", "PHASED_ARRAY.kicad_sch"]
DRY = "--dry-run" in sys.argv

BACKSLASH = chr(92)
QUOTE = chr(34)


def _scan(text, start, stop_at_zero):
    """Walk from `start` counting parentheses, honouring quoted strings.

    Returns the index just past the closing paren of the block when
    stop_at_zero is set, otherwise the final depth.
    """
    depth = 0
    in_str = False
    i = start
    while i < len(text):
        c = text[i]
        if in_str:
            if c == BACKSLASH:
                i += 2
                continue
            if c == QUOTE:
                in_str = False
        elif c == QUOTE:
            in_str = True
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if stop_at_zero and depth == 0:
                return i + 1
        i += 1
    return depth


def find_sheet_blocks(text):
    """Return [(start, end, sheetfile)] for every (sheet ...) block."""
    blocks = []
    token = chr(10) + chr(9) + "(sheet" + chr(10)
    i = 0
    while True:
        start = text.find(token, i)
        if start < 0:
            break
        start += 1                       # drop the leading newline
        end = _scan(text, start, True)
        body = text[start:end]
        sheetfile = None
        key = '(property "Sheetfile" "'
        k = body.find(key)
        if k >= 0:
            sheetfile = body[k + len(key):body.find(QUOTE, k + len(key))]
        blocks.append((start, end, sheetfile))
        i = end
    return blocks


def balanced(text):
    return _scan(text, 0, False) == 0


def main():
    text = open(SCH, encoding="utf-8").read()
    blocks = find_sheet_blocks(text)
    print(f"Sheets referenced by the root schematic: {len(blocks)}")
    for _, _, sheetfile in blocks:
        mark = "   <- REMOVED" if sheetfile in DEAD else ""
        print(f"    {sheetfile}{mark}")

    doomed = [b for b in blocks if b[2] in DEAD]
    if not doomed:
        print()
        print("Nothing to do: those sheets are no longer referenced.")
        return 0

    # Back to front, so earlier offsets stay valid.
    out = text
    for start, end, _ in sorted(doomed, reverse=True):
        tail = end
        while tail < len(out) and out[tail] in (chr(10), chr(13)):
            tail += 1
        out = out[:start] + out[tail:]

    if not balanced(out):
        print()
        print("ABORTED: the result does not have balanced parentheses.")
        return 1

    print()
    print(f"Root schematic: {len(text)} -> {len(out)} bytes, parentheses balanced")

    pro = json.load(open(PRO, encoding="utf-8"))
    before = list(pro.get("sheets", []))
    dead_names = {d.replace(".kicad_sch", "") for d in DEAD}
    pro["sheets"] = [s for s in before if not (len(s) > 1 and s[1] in dead_names)]
    print(f".kicad_pro sheets[]: {len(before)} -> {len(pro['sheets'])}")

    if DRY:
        print()
        print("--dry-run: nothing written.")
        return 0

    os.makedirs(DEPRECATED, exist_ok=True)
    with open(SCH, "w", encoding="utf-8", newline=chr(10)) as fh:
        fh.write(out)
    with open(PRO, "w", encoding="utf-8", newline=chr(10)) as fh:
        json.dump(pro, fh, indent=2)
        fh.write(chr(10))

    for d in DEAD:
        for name in (d, d.replace(".kicad_sch", "-erc.rpt")):
            src = os.path.join(ROOT, name)
            if os.path.exists(src):
                shutil.move(src, os.path.join(DEPRECATED, name))
                print(f"moved -> _deprecated/{name}")

    print()
    print("Done. Run ERC to check the result.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
