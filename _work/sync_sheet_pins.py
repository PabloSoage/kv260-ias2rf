#!/usr/bin/env python3
"""
Make every sheet block's pins agree with its child's hierarchical labels.

This is what "Synchronize Hierarchical Labels" does in the KiCad GUI, done from
the command line so the result can be measured.

Before: 36 hier_label_mismatch errors, all inherited from the Rev01 work.
Two kinds:

  · 2 orphan pins  - IAS0 carries CLK_KRIA_P and CLK_KRIA_N, sheet pins for a
    hierarchical label that does not exist. They are the remains of the Rev01
    idea of sending a 125 MHz LVPECL clock back into a MIPI pin on the SOM,
    which Rev03 dropped (see docs/AUDIT_Rev01.md §3).
  · 34 missing pins - the shared sheet exposes 25 hierarchical labels, but the
    IAS0 block declares only 16 of them and the IAS1 block only 2.

Both directions are fixed: orphan pins removed, missing pins added with the
direction the child's label declares.

Usage:  py _work/sync_sheet_pins.py [--dry-run]
"""

import os
import re
import sys
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT_SCH = os.path.join(ROOT, "CSI2-KRIA-KV260_Rev01.kicad_sch")
DRY = "--dry-run" in sys.argv
NS = uuid.UUID("9d3c7a10-2b84-4f61-8e05-c7a9b6d4e312")

QUOTE = chr(34)
BACKSLASH = chr(92)
NL = chr(10)
TAB = chr(9)


def scan(text, start):
    """Index just past the paren that closes the block starting at `start`."""
    depth, in_str, i = 0, False, start
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
            if depth == 0:
                return i + 1
        i += 1
    return -1


def child_labels(path):
    """name -> shape, from a child sheet's hierarchical labels."""
    text = open(path, encoding="utf-8").read()
    out = {}
    for m in re.finditer(r'\(hierarchical_label "([^"]+)"\s*\n\s*\(shape (\w+)\)', text):
        out[m.group(1)] = m.group(2)
    return out


def main():
    text = open(ROOT_SCH, encoding="utf-8").read()

    # Locate every top-level (sheet ...) block.
    blocks = []
    tok = NL + TAB + "(sheet" + NL
    i = 0
    while True:
        s = text.find(tok, i)
        if s < 0:
            break
        s += 1
        e = scan(text, s)
        blocks.append((s, e))
        i = e

    print(f"sheet blocks in the root: {len(blocks)}")
    print()

    edits = []          # (start, end, replacement)
    total_add = total_del = 0

    for s, e in blocks:
        blk = text[s:e]
        mf = re.search(r'\(property "Sheetfile" "([^"]+)"', blk)
        mn = re.search(r'\(property "Sheetname" "([^"]+)"', blk)
        if not mf or not mn:
            continue
        name, sheetfile = mn.group(1), mf.group(1)
        child = os.path.join(ROOT, sheetfile)
        if not os.path.exists(child):
            print(f"  {name:12s} child not found: {sheetfile}")
            continue

        labels = child_labels(child)
        pins = dict(re.findall(r'\(pin "([^"]+)" (\w+)', blk))

        orphans = sorted(set(pins) - set(labels))
        missing = sorted(set(labels) - set(pins))
        wrong = sorted(n for n in set(pins) & set(labels) if pins[n] != labels[n])

        print(f"  {name:12s} labels {len(labels):3d}  pins {len(pins):3d}   "
              f"orphan {len(orphans):2d}  missing {len(missing):2d}  wrong-dir {len(wrong)}")
        for o in orphans:
            print(f"        - {o}   (removed)")
        if not (orphans or missing or wrong):
            continue

        new = blk

        # Remove orphan pins. The block is found by matching parentheses, not
        # by indentation: the pins written by rev03_build_hierarchy.py close
        # their (effects ...) on a line indented like the pin's own close, and
        # an indentation-based match cut them short, leaving one stray paren
        # per pin (caught by the balance check below, 23 September).
        for o in orphans:
            k = new.find('\n\t\t(pin "' + o + '" ')
            if k < 0:
                continue
            pin_end = scan(new, k + 1)      # not `e`: that is the block's end
            new = new[:k] + new[pin_end:]
            total_del += 1

        # Correct any pin whose direction disagrees with its label.
        for w in wrong:
            new = re.sub(r'(\(pin "' + re.escape(w) + r'" )\w+',
                         lambda m: m.group(1) + labels[w], new, count=1)

        # Append the missing pins, laid out down the left edge of the block.
        mat = re.search(r'\(at ([-\d.]+) ([-\d.]+)\)', new)
        bx, by = float(mat.group(1)), float(mat.group(2))
        msz = re.search(r'\(size ([-\d.]+) ([-\d.]+)\)', new)
        bh = float(msz.group(2))
        # Start below whatever pins already exist.
        used = [float(m) for m in re.findall(r'\(pin "[^"]+" \w+\s*\n\s*\(at [-\d.]+ ([-\d.]+)', new)]
        py = (max(used) + 2.54) if used else (by + 5.08)
        add = []
        for nm2 in missing:
            add += [f'{TAB}{TAB}(pin "{nm2}" {labels[nm2]}',
                    f'{TAB}{TAB}{TAB}(at {bx} {py:.4f} 180)',
                    f'{TAB}{TAB}{TAB}(uuid "{uuid.uuid5(NS, name + "|" + nm2)}")',
                    f'{TAB}{TAB}{TAB}(effects',
                    f'{TAB}{TAB}{TAB}{TAB}(font',
                    f'{TAB}{TAB}{TAB}{TAB}{TAB}(size 1.27 1.27)',
                    f'{TAB}{TAB}{TAB}{TAB})',
                    f'{TAB}{TAB}{TAB}{TAB}(justify right)',
                    f'{TAB}{TAB}{TAB})',
                    f'{TAB}{TAB})']
            py += 2.54
            total_add += 1

        # Grow the block if the pins now run past its bottom edge.
        need = py - by + 2.54
        if need > bh:
            new = re.sub(r'\(size ([-\d.]+) [-\d.]+\)',
                         lambda m: f'(size {m.group(1)} {need:.2f})', new, count=1)

        new = new[:-1].rstrip(NL + TAB) + NL + NL.join(add) + NL + TAB + ")"
        edits.append((s, e, new))

    print()
    print(f"pins to add: {total_add}   pins to remove: {total_del}")

    if DRY:
        print()
        print("--dry-run: nothing written.")
        return 0

    out = text
    for s, e, new in sorted(edits, reverse=True):
        out = out[:s] + new + out[e:]

    depth = 0
    in_str = False
    i = 0
    while i < len(out):
        c = out[i]
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
        i += 1
    if depth != 0:
        print(f"ABORTED: parentheses unbalanced by {depth}")
        return 1

    with open(ROOT_SCH, "w", encoding="utf-8", newline=NL) as fh:
        fh.write(out)
    print(f"root schematic: {len(text)} -> {len(out)} bytes, parentheses balanced")
    print()
    print("Run ERC. hier_label_mismatch should now be 0.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
