#!/usr/bin/env python3
"""
Build the project footprint library, footprints/kv260-ias2rf.pretty: the
packages KiCad does not ship in the right form.

  LFCSP-32-1EP_5x5mm_P0.5mm_EP2.7x2.7mm   ADCLK948 (CP-32-21, datasheet Rev. B p.12).
      KiCad's 5x5 LFCSP-32s all have a 3.1 mm or larger exposed pad; this is
      KiCad's EP3.1 footprint with the pad at the datasheet's 2.70 nominal.
  LFCSP-56-1EP_8x8mm_P0.5mm_EP5.1x5.1mm   AD9484 (CP-56-5, datasheet Rev. A p.23).
      KiCad's 8x8 LFCSP-56 has a 6.6 mm pad; the AD9484's is 5.10 nominal.
      Leads are the same in both (L 0.40 nominal, pitch 0.5).
  MiniCircuits_DQ3005                     M3SWA2-34DR+ (case style DQ3005,
      Mini-Circuits drawing Rev. OR): 3 x 3 mm, 16 leads at 0.5 mm, the
      drawing's own "PCB Land Pattern" - 0.22 mm pads, 3.30 mm over the pad
      tips, 1.54 mm exposed pad (pad 17). The pad length, 0.55 mm, is scaled
      off the drawing, which does not dimension it.
  J-BM20B(0.8)-34DP                       Hirose, the IAS connector. Taken as
      text from the original Allied Vision board (J8_IAS1, which is placed
      on the bottom face, rotated 180) and returned to the top face,
      orientation 0: y mirrored, B.* layers to F.*, pad angles un-rotated.
      Its 3D model (embedded in the original board) is not carried over.

The exposed pads keep KiCad's own convention: copper and mask on the pad,
paste as a grid of smaller squares covering about 60 %.

Usage:  py _work/make_footprints.py
"""

import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import schgen                                        # noqa: E402

STOCK = "E:/Program Files/KiCad/10.0/share/kicad/footprints/"
OUT = os.path.join(ROOT, "footprints", "kv260-ias2rf.pretty")
BOARD = os.path.join(ROOT, "CSI2-KRIA-KV260_Rev01.kicad_pcb")
T = "\t"


def f(v):
    return schgen.fmt(round(v, 4))


def paste_grid(ep, n, cover=0.6):
    """n x n paste squares over an ep x ep pad, about `cover` of its area."""
    side = ep * math.sqrt(cover) / n
    pitch = ep / n
    out = []
    for i in range(n):
        for j in range(n):
            x = -ep / 2 + pitch * (i + 0.5)
            y = -ep / 2 + pitch * (j + 0.5)
            out.append(f'{T}(pad "" smd roundrect\n{T}{T}(at {f(x)} {f(y)})\n{T}{T}(size {f(side)} {f(side)})\n'
                       f'{T}{T}(layers "F.Paste")\n{T}{T}(roundrect_rratio 0.25)\n{T})')
    return out


def ep_pad(num, ep):
    return (f'{T}(pad "{num}" smd rect\n{T}{T}(at 0 0)\n{T}{T}(size {f(ep)} {f(ep)})\n'
            f'{T}{T}(layers "F.Cu" "F.Mask")\n{T}{T}(zone_connect 2)\n{T})')


def from_stock(stock, name, ep_num, ep, grid, descr):
    text = open(STOCK + stock, encoding="utf-8").read()
    old = re.match(r'\(footprint "([^"]+)"', text).group(1)
    out, i = [], 0
    for m in re.finditer(r"\n\t\(pad ", text):
        s = m.start() + 2
        e = s + len(schgen._block(text, s))
        num = re.match(r'\(pad "([^"]*)"', text[s:e]).group(1)
        if num in (ep_num, ""):
            out.append(text[i:m.start()])
            i = e
    out.append(text[i:])
    text = "".join(out)
    tail = text.rindex("\n\t(embedded_fonts")
    text = (text[:tail] + "\n" + ep_pad(ep_num, ep) + "\n" + "\n".join(paste_grid(ep, grid))
            + text[tail:])
    text = text.replace(f'(footprint "{old}"', f'(footprint "{name}"', 1)
    text = re.sub(r'\(descr "[^"]*"\)', f'(descr "{descr}")', text, count=1)
    text = text.replace(f'"Value" "{old}"', f'"Value" "{name}"')
    text = re.sub(r'\(model "[^"]*"', f'(model "${{KICAD10_3DMODEL_DIR}}/{stock.split("/")[0].replace(".pretty", ".3dshapes")}/{old}.step"', text)
    assert schgen._balanced(text)
    return name, text


def dq3005():
    """M3SWA2 package, from the DQ3005 drawing's land pattern."""
    name = "MiniCircuits_DQ3005"
    L, W, tip, ep = 0.55, 0.22, 3.30 / 2, 1.54
    c = tip - L / 2                                   # pad centre from the package centre
    pads = []
    for k in range(16):
        side, idx = divmod(k, 4)
        o = (idx - 1.5) * 0.5
        if side == 0:
            x, y, sx, sy = -c, o, L, W                # pins 1-4 left, top to bottom
        elif side == 1:
            x, y, sx, sy = o, c, W, L                 # 5-8 bottom, left to right
        elif side == 2:
            x, y, sx, sy = c, -o, L, W                # 9-12 right, bottom to top
        else:
            x, y, sx, sy = -o, -c, W, L               # 13-16 top, right to left
        pads.append(f'{T}(pad "{k + 1}" smd roundrect\n{T}{T}(at {f(x)} {f(y)})\n{T}{T}(size {f(sx)} {f(sy)})\n'
                    f'{T}{T}(layers "F.Cu" "F.Mask" "F.Paste")\n{T}{T}(roundrect_rratio 0.25)\n{T})')
    body, crt = 1.5, 1.95
    g = []
    for layer, h, w in (("F.Fab", body, 0.1), ("F.CrtYd", crt, 0.05)):
        g.append(f'{T}(fp_rect\n{T}{T}(start {f(-h)} {f(-h)})\n{T}{T}(end {f(h)} {f(h)})\n'
                 f'{T}{T}(stroke\n{T}{T}{T}(width {w})\n{T}{T}{T}(type solid)\n{T}{T})\n{T}{T}(fill no)\n'
                 f'{T}{T}(layer "{layer}")\n{T})')
    for (x1, y1, x2, y2) in ((-1.6, -1.6, -1.15, -1.6), (-1.6, -1.6, -1.6, -1.15),
                             (1.6, -1.6, 1.15, -1.6), (1.6, -1.6, 1.6, -1.15),
                             (-1.6, 1.6, -1.15, 1.6), (-1.6, 1.6, -1.6, 1.15),
                             (1.6, 1.6, 1.15, 1.6), (1.6, 1.6, 1.6, 1.15)):
        g.append(f'{T}(fp_line\n{T}{T}(start {f(x1)} {f(y1)})\n{T}{T}(end {f(x2)} {f(y2)})\n'
                 f'{T}{T}(stroke\n{T}{T}{T}(width 0.12)\n{T}{T}{T}(type solid)\n{T}{T})\n{T}{T}(layer "F.SilkS")\n{T})')
    g.append(f'{T}(fp_circle\n{T}{T}(center -1.95 -1.0)\n{T}{T}(end -1.85 -1.0)\n'
             f'{T}{T}(stroke\n{T}{T}{T}(width 0.2)\n{T}{T}{T}(type solid)\n{T}{T})\n{T}{T}(fill yes)\n{T}{T}(layer "F.SilkS")\n{T})')
    props = []
    for k, v, y, lay, hide in (("Reference", "REF**", -2.6, "F.SilkS", False),
                               ("Value", name, 2.6, "F.Fab", False),
                               ("Datasheet", "https://www.minicircuits.com/case_style/DQ3005.pdf", 0, "F.Fab", True),
                               ("Description", "Mini-Circuits DQ3005, 3x3 mm, 16 leads, P0.5, EP1.54 (M3SWA2-34DR+)", 0, "F.Fab", True)):
        props.append(f'{T}(property "{k}" "{v}"\n{T}{T}(at 0 {f(y)} 0)\n{T}{T}(layer "{lay}")\n'
                     + (f"{T}{T}(hide yes)\n" if hide else "")
                     + f'{T}{T}(effects\n{T}{T}{T}(font\n{T}{T}{T}{T}(size 0.8 0.8)\n{T}{T}{T}{T}(thickness 0.12)\n{T}{T}{T})\n{T}{T})\n{T})')
    text = "\n".join([f'(footprint "{name}"', f"{T}(version 20241229)", f'{T}(generator "kv260-ias2rf/_work/make_footprints.py")',
                      f'{T}(layer "F.Cu")',
                      f'{T}(descr "Mini-Circuits case style DQ3005 (M3SWA2-34DR+), land pattern from the case drawing Rev. OR")',
                      f'{T}(tags "Mini-Circuits DQ3005 QFN-16")'] + props + [f"{T}(attr smd)"] + g + pads
                     + [ep_pad("17", 1.54)] + paste_grid(1.54, 1, 0.6) + [f"{T}(embedded_fonts no)", ")"]) + "\n"
    assert schgen._balanced(text)
    return name, text


def hirose():
    """J8_IAS1 from the original board, back to the top face at orientation 0."""
    board = open(BOARD, encoding="utf-8").read()
    i = board.index('(property "Reference" "J8_IAS1"')
    s = board.rfind("\n\t(footprint", 0, i) + 2
    blk = schgen._block(board, s)
    rot = float(re.search(r"\n\t\t\(at [\d.\-]+ [\d.\-]+ ([\d.\-]+)\)", blk).group(1))
    assert '(layer "B.Cu")' in blk[:200] and rot == 180
    # drop placement-only parts: position, uuids, path, the model and its file
    blk = re.sub(r'\n\t\t\(at [\d.\-]+ [\d.\-]+(?: [\d.\-]+)?\)', "", blk, count=1)
    for head in ("model", "embedded_files"):
        m = re.search(r"\n\t\t\(" + head + r"[\s\n]", blk)
        if m:
            e = m.start() + 3 + len(schgen._block(blk, m.start() + 3))
            blk = blk[:m.start()] + blk[e:]
    blk = re.sub(r'\n\t*\(uuid "[^"]+"\)', "", blk)

    def mirror_xy(m):
        return f"({m.group(1)} {m.group(2)} {f(-float(m.group(3)))}"
    blk = re.sub(r"\((start|end|mid|center|xy) ([\d.\-]+) ([\d.\-]+)", mirror_xy, blk)

    def at(m):
        x, y = m.group(1), -float(m.group(2))
        a = m.group(3)
        if a is None:
            return f"(at {x} {f(y)})"
        a = (-(float(a) - rot)) % 360
        return f"(at {x} {f(y)} {f(a)})"
    blk = re.sub(r"\(at ([\d.\-]+) ([\d.\-]+)(?: ([\d.\-]+))?\)", at, blk)
    # texts (pin-number marks, reference, value) read upright: angle 0
    blk = re.sub(r'(\((?:fp_text user|property) "[^"]*"\s*\(at [\d.\-]+ [\d.\-]+) [\d.\-]+\)', r"\1 0)", blk)
    blk = re.sub(r'"B\.(Cu|Mask|Paste|SilkS|Fab|CrtYd|Adhes)"', r'"F.\1"', blk)
    blk = blk.replace(" mirror)", ")").replace("(justify mirror)", "")
    blk = re.sub(r'\(net "[^"]*"\)\n\t*', "", blk)
    blk = re.sub(r'"Reference" "J8_IAS1"', '"Reference" "REF**"', blk)
    blk = blk.replace('(footprint "AVT_KHK_Lib:J-BM20B(0.8)-34DP"',
                      '(footprint "J-BM20B(0.8)-34DP"\n\t\t(version 20241229)\n\t\t'
                      '(generator "kv260-ias2rf/_work/make_footprints.py")\n\t\t'
                      '(descr "Hirose BM20B(0.8)-34DP-0.4V, as placed on the original Allied Vision board '
                      '(J8_IAS1), returned to the top face")', 1)
    # de-indent one level: board children are two tabs deep, library ones one
    blk = "\n".join(line[1:] if line.startswith("\t") else line for line in blk.split("\n"))
    assert schgen._balanced(blk)
    return "J-BM20B(0.8)-34DP", blk + "\n"


def main():
    os.makedirs(OUT, exist_ok=True)
    parts = [
        from_stock("Package_CSP.pretty/LFCSP-32-1EP_5x5mm_P0.5mm_EP3.1x3.1mm.kicad_mod",
                   "LFCSP-32-1EP_5x5mm_P0.5mm_EP2.7x2.7mm", "33", 2.70, 2,
                   "LFCSP-32 5x5 mm, EP 2.7 mm (Analog Devices CP-32-21, ADCLK948 Rev. B p.12)"),
        from_stock("Package_CSP.pretty/LFCSP-56-1EP_8x8mm_P0.5mm_EP6.6x6.6mm.kicad_mod",
                   "LFCSP-56-1EP_8x8mm_P0.5mm_EP5.1x5.1mm", "57", 5.10, 3,
                   "LFCSP-56 8x8 mm, EP 5.1 mm (Analog Devices CP-56-5, AD9484 Rev. A p.23)"),
        dq3005(),
        hirose(),
    ]
    for name, text in parts:
        with open(os.path.join(OUT, name + ".kicad_mod"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        pads = re.findall(r'\(pad "([^"]*)"', text)
        print(f"  {name:42s} {len([p for p in pads if p])} pads, {pads.count('')} paste-only")
    return 0


if __name__ == "__main__":
    sys.exit(main())
