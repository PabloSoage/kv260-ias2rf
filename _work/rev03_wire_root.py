#!/usr/bin/env python3
"""
Wire the Rev03 root sheet: every sheet pin gets a short wire and a net label,
so the root reads as a block diagram whose connections are by name.

What it does to CSI2-KRIA-KV260_Rev01.kicad_sch:

  1. removes the Rev01 IAS0 and IAS1 sheet blocks, the four power symbols
     beside them and their captions. Their child file,
     CSI2-KRIA-KV260_Rev01-2.kicad_sch, goes to _deprecated/ (IAS_LINK replaced
     it) and leaves the project's sheet list;
  2. rebuilds each Rev03 sheet block: position, size, and its pins taken from
     the child's own hierarchical labels - inputs on the left edge, outputs
     and bidirectionals on the right, in name order;
  3. gives each pin a 5.08 mm wire and a label of the same name;
  4. numbers the pages (root 1, then signal order).

Left alone: the frame and logo inherited from the original Altium design,
the fiducials and the PCB-text symbols, which belong to the board.

The result is checked by _work/check_root.py against the sheets' own
connection lists.

Usage:  py _work/rev03_wire_root.py [--dry-run]
"""

import json
import os
import re
import shutil
import sys
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import schgen                                        # noqa: E402

ROOT_SCH = os.path.join(ROOT, "CSI2-KRIA-KV260_Rev01.kicad_sch")
PRO = os.path.join(ROOT, "CSI2-KRIA-KV260_Rev01.kicad_pro")
OLD_CHILD = "CSI2-KRIA-KV260_Rev01-2.kicad_sch"
ROOT_UUID = "56c49378-41a8-4cbc-b1f4-3d0ea65d2366"
PROJECT = "CSI2-KRIA-KV260_Rev01"
DRY = "--dry-run" in sys.argv
NS = uuid.UUID("2f6e1c7a-94b3-4d0e-a1c8-5b7d3e9f0a61")
T = "\t"


def uid(*p):
    return str(uuid.uuid5(NS, "|".join(str(x) for x in p)))


def fmt(v):
    return schgen.fmt(v)


# name -> (x, y, width, page). Signal flow left to right: the Kria link and
# the clock feed the FPGA; the FPGA feeds the converters; the converters
# meet the SMAs through the routing switches. The frame inherited from the
# Altium design sits at x 236-389, y 256-292 and is kept clear of.
LAYOUT = {
    "IAS_LINK":  (40.64, 40.64, 50.8, 2),
    "CLOCK":     (40.64, 111.76, 50.8, 4),
    "POWER":     (40.64, 170.18, 50.8, 10),
    "CONTROL":   (193.04, 40.64, 55.88, 3),
    "ADC_RADAR": (345.44, 40.64, 50.8, 5),
    "ADC_SDR":   (345.44, 124.46, 50.8, 6),
    "DAC_RADAR": (345.44, 175.26, 50.8, 7),
    "DAC_SDR":   (464.82, 40.64, 50.8, 8),
    "ROUTING":   (464.82, 124.46, 50.8, 9),
}
FRAME = (236.22, 256.0, 388.62, 292.0)
PITCH = 2.54
STUB = 5.08


def natural(s):
    return [int(p) if p.isdigit() else p for p in re.split(r"(\d+)", s)]


def child_labels(path):
    text = open(os.path.join(ROOT, path), encoding="utf-8").read()
    out = {}
    for m in re.finditer(r'\(hierarchical_label "([^"]+)"\s*\(shape (\w+)\)', text):
        out.setdefault(m.group(1), m.group(2))
    return out


def blocks(text, head):
    """(start, end) of every top-level block starting with `head`."""
    out = []
    for m in re.finditer(r"\n\t\(" + head + r"[\s\n]", text):
        s = m.start() + 2                              # the "(" after newline and tab
        out.append((s, s + len(schgen._block(text, s))))
    return out


def main():
    text = open(ROOT_SCH, encoding="utf-8").read()

    # ---- 1. what goes
    cut = []
    sheets = {}
    for s, e in blocks(text, "sheet"):
        b = text[s:e]
        name = re.search(r'"Sheetname" "([^"]*)"', b).group(1)
        f = re.search(r'"Sheetfile" "([^"]*)"', b).group(1)
        if name in ("IAS0", "IAS1"):
            cut.append((s, e))
        else:
            sheets[name] = (s, e, f, re.search(r'\(uuid "([^"]+)"\)', b).group(1))
    for s, e in blocks(text, "symbol"):
        ref = re.search(r'\(property "Reference" "([^"]*)"', text[s:e]).group(1)
        if ref in ("#PWR083", "#PWR084", "#PWR085", "#PWR086"):
            cut.append((s, e))
    for s, e in blocks(text, "text"):
        b = text[s:e]
        body = re.match(r'\(text "((?:[^"\\]|\\.)*)"', b, re.S).group(1)
        at = re.search(r"\(at ([\d.]+) ([\d.]+)", b).groups()
        if body in ("IAS0", "IAS1", "Camera Adapter 1, 2") or (body == "" and at == ("285.75", "208.1022")):
            cut.append((s, e))
    assert len(cut) == 2 + 4 + 4, f"expected 10 items to remove, found {len(cut)}"
    assert set(sheets) == set(LAYOUT), sorted(sheets)

    # ---- 2-3. new sheet blocks, wires and labels
    new_blocks, wires, labels = {}, [], []
    for name, (s, e, f, suuid) in sheets.items():
        x, y, w, page = LAYOUT[name]
        pins = child_labels(f)
        left = sorted((n for n, d in pins.items() if d == "input"), key=natural)
        right = sorted((n for n, d in pins.items() if d != "input"), key=natural)
        h = max(len(left), len(right), 3) * PITCH + 2 * PITCH
        assert not (x < FRAME[2] and x + w > FRAME[0] and y + h > FRAME[1]), f"{name} hits the frame"
        o = [f"{T}(sheet", f"{T}{T}(at {fmt(x)} {fmt(y)})", f"{T}{T}(size {fmt(w)} {fmt(h)})",
             f"{T}{T}(exclude_from_sim no)", f"{T}{T}(in_bom yes)", f"{T}{T}(on_board yes)",
             f"{T}{T}(dnp no)", f"{T}{T}(fields_autoplaced yes)",
             f"{T}{T}(stroke", f"{T}{T}{T}(width 0.1524)", f"{T}{T}{T}(type solid)", f"{T}{T})",
             f"{T}{T}(fill", f"{T}{T}{T}(color 0 0 0 0.0000)", f"{T}{T})",
             f'{T}{T}(uuid "{suuid}")']
        for prop, val, py, just in (("Sheetname", name, y - 0.7112, "left bottom"),
                                     ("Sheetfile", f, y + h + 0.5842, "left top")):
            o += [f'{T}{T}(property "{prop}" "{val}"', f"{T}{T}{T}(at {fmt(x)} {fmt(py)} 0)",
                  f"{T}{T}{T}(show_name no)", f"{T}{T}{T}(do_not_autoplace no)",
                  f"{T}{T}{T}(effects", f"{T}{T}{T}{T}(font", f"{T}{T}{T}{T}{T}(size 1.27 1.27)",
                  f"{T}{T}{T}{T})", f"{T}{T}{T}{T}(justify {just})", f"{T}{T}{T})", f"{T}{T})"]
        for side, names in (("L", left), ("R", right)):
            for i, n in enumerate(names):
                py = schgen.snap(y + PITCH * (i + 1))
                px = x if side == "L" else schgen.snap(x + w)
                ang, just, d = (180, "left", -1) if side == "L" else (0, "right", 1)
                o += [f'{T}{T}(pin "{n}" {pins[n]}', f"{T}{T}{T}(at {fmt(px)} {fmt(py)} {ang})",
                      f'{T}{T}{T}(uuid "{uid("pin", name, n)}")',
                      f"{T}{T}{T}(effects", f"{T}{T}{T}{T}(font", f"{T}{T}{T}{T}{T}(size 1.27 1.27)",
                      f"{T}{T}{T}{T})", f"{T}{T}{T}{T}(justify {just})", f"{T}{T}{T})", f"{T}{T})"]
                end = (schgen.snap(px + d * STUB), py)
                wires.append(((px, py), end))
                labels.append((n, end, "left" if d < 0 else "right"))
        o += [f"{T}{T}(instances", f'{T}{T}{T}(project "{PROJECT}"',
              f'{T}{T}{T}{T}(path "/{ROOT_UUID}"', f'{T}{T}{T}{T}{T}(page "{page}")',
              f"{T}{T}{T}{T})", f"{T}{T}{T})", f"{T}{T})", f"{T})"]
        new_blocks[s] = "\n".join(o)

    # every label name must meet at least one other sheet
    count = {}
    for n, _, _ in labels:
        count[n] = count.get(n, 0) + 1
    lonely = sorted(n for n, c in count.items() if c < 2)
    assert not lonely, f"interface names on one sheet only: {lonely}"

    # ---- rebuild the text
    edits = [(s, e, "") for s, e in cut] + [(s, e, new_blocks[s]) for s, e, _, _ in sheets.values()]
    for s, e, rep in sorted(edits, key=lambda q: -q[0]):
        # a removed block takes its own newline and tab with it; a new block
        # brings its own tab
        text = text[:s - 2] + text[e:] if rep == "" else text[:s - 1] + rep + text[e:]
    extra = []
    for a, b in wires:
        extra += [f"{T}(wire", f"{T}{T}(pts", f"{T}{T}{T}(xy {fmt(a[0])} {fmt(a[1])}) (xy {fmt(b[0])} {fmt(b[1])})",
                  f"{T}{T})", f"{T}{T}(stroke", f"{T}{T}{T}(width 0)", f"{T}{T}{T}(type default)",
                  f"{T}{T})", f'{T}{T}(uuid "{uid("w", a, b)}")', f"{T})"]
    for n, at, side in labels:
        ang, just = (0, "left") if side == "right" else (180, "right")
        extra += [f'{T}(label "{n}"', f"{T}{T}(at {fmt(at[0])} {fmt(at[1])} {ang})",
                  f"{T}{T}(effects", f"{T}{T}{T}(font", f"{T}{T}{T}{T}(size 1.27 1.27)", f"{T}{T}{T})",
                  f"{T}{T}{T}(justify {just})", f"{T}{T})", f'{T}{T}(uuid "{uid("l", n, at)}")', f"{T})"]
    i = text.index("\n\t(sheet_instances")
    text = text[:i] + "\n" + "\n".join(extra) + text[i:]
    text = re.sub(r'(\(sheet_instances\s*\(path "/"\s*\(page )"[^"]*"', r'\1"1"', text)
    assert schgen._balanced(text)

    print(f"removed {len(cut)} items (IAS0, IAS1, their power symbols and captions)")
    print(f"{len(sheets)} sheet blocks rebuilt, {len(labels)} pins wired and labelled, "
          f"{len(count)} interface nets")
    if DRY:
        print("--dry-run: nothing written")
        return 0
    open(ROOT_SCH, "w", encoding="utf-8", newline="\n").write(text)

    # the old child and the project's sheet list
    src = os.path.join(ROOT, OLD_CHILD)
    if os.path.exists(src):
        os.makedirs(os.path.join(ROOT, "_deprecated"), exist_ok=True)
        shutil.move(src, os.path.join(ROOT, "_deprecated", OLD_CHILD))
        print(f"moved {OLD_CHILD} to _deprecated/")
    pro = json.load(open(PRO, encoding="utf-8"))
    before = len(pro.get("sheets", []))
    pro["sheets"] = [s for s in pro.get("sheets", []) if s[1] not in ("IAS0", "IAS1")]
    json.dump(pro, open(PRO, "w", encoding="utf-8", newline="\n"), indent=2)
    print(f"project sheet list: {before} -> {len(pro['sheets'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
