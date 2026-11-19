#!/usr/bin/env python3
"""
PSU board silkscreen: show every part's reference designator on F.SilkS, placed beside its courtyard where it
clears every pad, every other courtyard (when it can), every other reference and the board edge. Runs on the
routed psu/psu.kicad_pcb as text (idempotent: a second run re-places the same references), and also sets the
solder mask colour: a green that lets the copper pours show through, as on a real board.

Usage:  python _work/psu/psu_silk.py [board.kicad_pcb]
"""
import math
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PCB = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "psu", "psu.kicad_pcb")
EDGE = (100.0, 100.0, 210.0, 170.0)
EDGE_MARGIN = 0.6
GAP = 0.25
MASK = "#0F4F26F2"       # green LPI mask, translucent enough to show the pours under it
CHAR_W = 0.80          # KiCad stroke font: advance per character, in units of text height (with stroke)


def blocks(text, head):
    """Top-level-ish '(head ...' blocks with their spans."""
    out = []
    i = 0
    key = "(" + head
    while True:
        i = text.find(key, i)
        if i < 0:
            return out
        depth, j = 0, i
        while True:
            c = text[j]
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    break
            elif c == '"':
                j += 1
                while text[j] != '"':
                    j += 2 if text[j] == "\\" else 1
            j += 1
        out.append((i, j + 1))
        i = j + 1


def fwd(x, y, rot, lx, ly):
    a = math.radians(rot)
    return x + lx * math.cos(a) + ly * math.sin(a), y - lx * math.sin(a) + ly * math.cos(a)


def inv(x, y, rot, wx, wy):
    a = math.radians(rot)
    dx, dy = wx - x, wy - y
    return dx * math.cos(a) - dy * math.sin(a), dx * math.sin(a) + dy * math.cos(a)


def bbox(pts):
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return [min(xs), min(ys), max(xs), max(ys)]


def overlap(a, b, m=0.0):
    return a[0] < b[2] + m and b[0] < a[2] + m and a[1] < b[3] + m and b[1] < a[3] + m


def parse(text):
    fps = []
    for s, e in blocks(text, "footprint "):
        blk = text[s:e]
        at = re.search(r'^\t\t\(at ([-\d.]+) ([-\d.]+)(?: ([-\d.]+))?\)', blk, re.M)
        ref = re.search(r'\(property "Reference" "([^"]+)"', blk)
        if not at or not ref:
            continue
        x, y, rot = float(at.group(1)), float(at.group(2)), float(at.group(3) or 0)
        crt = []
        for m in re.finditer(r'\(fp_(?:line|rect)\s+\(start ([-\d.]+) ([-\d.]+)\)\s+\(end ([-\d.]+) ([-\d.]+)\)'
                             r'(?:(?!\(fp_)[\s\S])*?\(layer "F\.CrtYd"\)', blk):
            for k in ((1, 2), (3, 4), (1, 4), (3, 2)):
                crt.append(fwd(x, y, rot, float(m.group(k[0])), float(m.group(k[1]))))
        for m in re.finditer(r'\(fp_circle\s+\(center ([-\d.]+) ([-\d.]+)\)\s+\(end ([-\d.]+) ([-\d.]+)\)'
                             r'(?:(?!\(fp_)[\s\S])*?\(layer "F\.CrtYd"\)', blk):
            cx, cy = float(m.group(1)), float(m.group(2))
            r = math.hypot(float(m.group(3)) - cx, float(m.group(4)) - cy)
            crt += [fwd(x, y, rot, cx - r, cy - r), fwd(x, y, rot, cx + r, cy + r)]
        pads = []
        for m in re.finditer(r'\(pad "[^"]*" \w+ \w+\s+\(at ([-\d.]+) ([-\d.]+)(?: ([-\d.]+))?\)\s+'
                             r'\(size ([-\d.]+) ([-\d.]+)\)', blk):
            px, py = float(m.group(1)), float(m.group(2))
            prot = float(m.group(3) or 0) - rot      # pad angle in the file is absolute
            w, h = float(m.group(4)) / 2, float(m.group(5)) / 2
            corners = []
            for cx, cy in ((-w, -h), (w, -h), (w, h), (-w, h)):
                lx, ly = fwd(0, 0, prot, cx, cy)
                corners.append(fwd(x, y, rot, px + lx, py + ly))
            pads.append(bbox(corners))
        if not crt:
            crt = [(b[0], b[1]) for b in pads] + [(b[2], b[3]) for b in pads] or [(x - 0.5, y - 0.5), (x + 0.5, y + 0.5)]
        fps.append(dict(ref=ref.group(1), x=x, y=y, rot=rot, crt=bbox(crt), pads=pads, span=(s, e),
                        hole=blk.startswith('(footprint "MountingHole')))
    return fps


def place(fps):
    pads = [p for f in fps for p in f["pads"]]
    crts = [(f["ref"], f["crt"]) for f in fps]
    taken = []
    plan = {}
    order = sorted(fps, key=lambda f: (f["crt"][2] - f["crt"][0]) * (f["crt"][3] - f["crt"][1]))
    for f in order:
        if f["hole"]:
            continue
        c = f["crt"]
        cx, cy = (c[0] + c[2]) / 2, (c[1] + c[3]) / 2
        best = None
        for size in (1.0, 0.8):
            w, h = CHAR_W * size * len(f["ref"]), size
            cands = [
                (cx, c[1] - GAP - h / 2, 0), (cx, c[3] + GAP + h / 2, 0),
                (c[0] - GAP - w / 2, cy, 0), (c[2] + GAP + w / 2, cy, 0),
                (c[0] - GAP - h / 2, cy, 90), (c[2] + GAP + h / 2, cy, 90),
                (c[0] + w / 2, c[1] - GAP - h / 2, 0), (c[2] - w / 2, c[1] - GAP - h / 2, 0),
                (c[0] + w / 2, c[3] + GAP + h / 2, 0), (c[2] - w / 2, c[3] + GAP + h / 2, 0),
            ]
            for strict in (True, False):
                for tx, ty, ang in cands:
                    bw, bh = (w, h) if ang == 0 else (h, w)
                    box = [tx - bw / 2, ty - bh / 2, tx + bw / 2, ty + bh / 2]
                    if (box[0] < EDGE[0] + EDGE_MARGIN or box[1] < EDGE[1] + EDGE_MARGIN
                            or box[2] > EDGE[2] - EDGE_MARGIN or box[3] > EDGE[3] - EDGE_MARGIN):
                        continue
                    if any(overlap(box, p, 0.2) for p in pads):
                        continue
                    if any(overlap(box, t, 0.3) for t in taken):
                        continue
                    if strict and any(overlap(box, cb, 0.0) for r, cb in crts if r != f["ref"]):
                        continue
                    best = (tx, ty, ang, size, box)
                    break
                if best:
                    break
            if best:
                break
        if best:
            taken.append(best[4])
            plan[f["ref"]] = best[:4]
    return plan


def apply(text, fps, plan):
    out, last = [], 0
    for f in fps:
        s, e = f["span"]
        blk = text[s:e]
        m = re.search(r'(\(property "Reference" "[^"]+"\s*\(at )([-\d. ]+)(\)[\s\S]*?\(layer "F\.SilkS"\))'
                      r'(\s*\(hide yes\))?([\s\S]*?\(font\s*\(size )([-\d.]+) ([-\d.]+)(\)\s*\(thickness )([-\d.]+)',
                      blk)
        if m and f["ref"] in plan:
            tx, ty, ang, size = plan[f["ref"]]
            lx, ly = inv(f["x"], f["y"], f["rot"], tx, ty)
            new = (m.group(1) + f"{lx:.3f} {ly:.3f} {ang:g}" + m.group(3) + m.group(5)
                   + f"{size:g} {size:g}" + m.group(8) + f"{0.15 * size:.3f}")
            blk = blk[:m.start()] + new + blk[m.end():]
        elif m and not m.group(4):          # no room: keep it hidden (it stays on the assembly drawing)
            blk = blk[:m.end(3)] + "\n\t\t\t(hide yes)" + blk[m.end(3):]
        out.append(text[last:s])
        out.append(blk)
        last = e
    out.append(text[last:])
    return "".join(out)


def main():
    text = open(PCB, encoding="utf-8").read()
    text = re.sub(r'(\(layer "[FB]\.Mask" \(type "(?:Top|Bottom) Solder Mask"\) )(?:\(color "[^"]*"\) )?',
                  lambda m: m.group(1) + f'(color "{MASK}") ', text)
    fps = parse(text)
    plan = place(fps)
    text = apply(text, fps, plan)
    open(PCB, "w", encoding="utf-8", newline="\n").write(text)
    missing = [f["ref"] for f in fps if not f["hole"] and f["ref"] not in plan]
    print(f"{len(plan)} references placed; not placed: {missing or 'none'}")


if __name__ == "__main__":
    main()
