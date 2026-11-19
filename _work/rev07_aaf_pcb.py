#!/usr/bin/env python3
"""
Rev07: the IF_RX_C anti-alias low-pass on the board (schematic: _work/rev07_aaf.py).

It goes on the straight L1 run of IF_RX_C at y 192.4, between x 166 and 180, where no other copper runs on any layer
(checked: only the B.Cu IF_RX_A diagonal passes x 166-168 at y 190-193, and IF_RX_B's L1 line starts at x 179.25,
y 193.15). Four nodes 4.5 mm apart along the line:

  - each shunt capacitor (0402) stands on the line, signal pad on the track, ground pad above it and a GND via
    0.9 mm above that, to L2;
  - each series inductor (0805) sits in the line between two nodes;
  - each inductor's parallel capacitor (0402) sits above it, its pads tied to the inductor's by short tracks.

The line itself is cut into four pieces, one per node net. Text edit of the board (KiCad's pcbnew module is not
used: it raises dialogs on this machine). Footprints are built from the board's own C951 (0402) and L1201 (0805)
as templates, with new uuids, and point to the schematic symbols by their uuids. Refuses to run twice.

Usage:  py _work/rev07_aaf_pcb.py
"""
import os, re, sys, uuid
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PCB = os.path.join(ROOT, "KV260-IAS2RF.kicad_pcb")
SCH = os.path.join(ROOT, "sheets", "ROUTING.kicad_sch")
SHEET_UUID = "388f8fcb-a039-5966-b84c-c0dd05bb2489"      # the ROUTING sheet's instance in the root
U = lambda: str(uuid.uuid4())

Y = 192.4                                   # the line
NODES = [166.3, 170.8, 175.3, 179.8]        # x of the four nodes
IN, N1, N2, OUT = "/ROUTING/IF_RX_C_AAF", "/ROUTING/AAF_C_N1", "/ROUTING/AAF_C_N2", "/IF_RX_C"
NETS = [IN, N1, N2, OUT]
SHUNT = ["C953", "C955", "C957", "C959"]
SERIES = [("L951", "C954"), ("L952", "C956"), ("L953", "C958")]
VALUES = {"C953": "82p", "L951": "220n", "C954": "47p", "C955": "150p", "L952": "270n", "C956": "39p",
          "C957": "160p", "L953": "330n", "C958": "10p", "C959": "100p"}
W_RF, W_STUB, W_GND = 0.183, 0.2, 0.3
VIA = (0.45, 0.2)


def block(t, ref):
    i = t.find(f'(property "Reference" "{ref}"'); s = t.rfind("\n\t(footprint ", 0, i)
    e = t.find("\n\t(footprint ", i)
    nxt = re.compile(r"\n\t\((segment|via|zone|gr_|arc|group|embedded)").search(t, i)
    if e < 0 or (nxt and nxt.start() < e): e = nxt.start()
    return s, e


def sym_uuids():
    t = open(SCH, encoding="utf-8").read()
    out = {}
    for ref in VALUES:
        i = t.find(f'(property "Reference" "{ref}"'); s = t.rfind("\n\t(symbol", 0, i)
        out[ref] = re.search(r'\(uuid "([^"]+)"\)', t[s:i]).group(1)
    return out


def make_fp(tpl, ref, value, x, y, rot, nets, sym):
    b = tpl
    b = re.sub(r'\(uuid "[^"]+"\)', lambda m: f'(uuid "{U()}")', b)
    b = re.sub(r'\n\t\t\(at [-\d.]+ [-\d.]+(?: [-\d.]+)?\)', f"\n\t\t(at {x:g} {y:g}{' ' + str(rot) if rot else ''})", b, count=1)
    b = re.sub(r'\(property "Reference" "[^"]+"', f'(property "Reference" "{ref}"', b)
    b = re.sub(r'\(property "Value" "[^"]+"', f'(property "Value" "{value}"', b)
    b = re.sub(r'\(path "[^"]+"\)', f'(path "/{SHEET_UUID}/{sym}")', b)
    b = re.sub(r'\(sheetname "[^"]+"\)', '(sheetname "/ROUTING/")', b)
    b = re.sub(r'\(sheetfile "[^"]+"\)', '(sheetfile "sheets/ROUTING.kicad_sch")', b)
    # text and pad angles carry the footprint's rotation
    b = re.sub(r'(\n\t\t\t\(at [-\d.]+ [-\d.]+) [-\d.]+\)', lambda m: m.group(1) + (f" {rot})" if rot else ")"), b)

    def pad(m):
        num = m.group(1); body = m.group(2)
        body = re.sub(r'\(at ([-\d.]+) ([-\d.]+)(?: [-\d.]+)?\)', lambda q: f"(at {q.group(1)} {q.group(2)}{' ' + str(rot) if rot else ''})", body, count=1)
        body = re.sub(r'\n\t\t\t\(net "[^"]*"\)', "", body)
        body = body.replace("\n\t\t\t(uuid", f'\n\t\t\t(net "{nets[num]}")\n\t\t\t(uuid', 1)
        return f'(pad "{num}"{body}'
    b = re.sub(r'\(pad "(\d)"([\s\S]*?\n\t\t\))', pad, b)
    return b


def seg(x1, y1, x2, y2, w, net, layer="F.Cu"):
    return (f'\t(segment\n\t\t(start {x1:g} {y1:g})\n\t\t(end {x2:g} {y2:g})\n\t\t(width {w:g})\n'
            f'\t\t(layer "{layer}")\n\t\t(net "{net}")\n\t\t(uuid "{U()}")\n\t)')


def via(x, y, net="GND"):
    return (f'\t(via\n\t\t(at {x:g} {y:g})\n\t\t(size {VIA[0]:g})\n\t\t(drill {VIA[1]:g})\n\t\t(layers "F.Cu" "B.Cu")\n'
            f'\t\t(net "{net}")\n\t\t(uuid "{U()}")\n\t)')


def main():
    t = open(PCB, encoding="utf-8").read()
    if '"Reference" "C953"' in t: sys.exit("already applied")
    sym = sym_uuids()
    s, e = block(t, "C951"); tpl_c = t[s:e]
    s, e = block(t, "L1201"); tpl_l = t[s:e]
    assert '"Inductor_SMD:L_0805_2012Metric"' in tpl_l and '"Capacitor_SMD:C_0402_1005Metric"' in tpl_c
    # pad offsets: 0402 at +-0.48, 0805 at +-1.0625
    fps, items = [], []
    for k, ref in enumerate(SHUNT):                     # rot 90: pad 1 at +0.48 in y (on the line), pad 2 at -0.48
        x = NODES[k]
        fps.append(make_fp(tpl_c, ref, VALUES[ref], x, Y - 0.48, 90, {"1": NETS[k], "2": "GND"}, sym[ref]))
        vx = x - 0.3 if k == 0 else x               # the first via keeps clear of IF_RX_A on B.Cu
        items.append(seg(x, Y - 0.96, vx, Y - 1.85, W_GND, "GND")); items.append(via(vx, Y - 1.85))
    for k, (lref, cref) in enumerate(SERIES):
        lx = (NODES[k] + NODES[k + 1]) / 2
        fps.append(make_fp(tpl_l, lref, VALUES[lref], lx, Y, 0, {"1": NETS[k], "2": NETS[k + 1]}, sym[lref]))
        cy = Y - 1.35
        fps.append(make_fp(tpl_c, cref, VALUES[cref], lx, cy, 0, {"1": NETS[k], "2": NETS[k + 1]}, sym[cref]))
        items.append(seg(lx - 0.48, cy, lx - 1.0625, Y, W_STUB, NETS[k]))
        items.append(seg(lx + 0.48, cy, lx + 1.0625, Y, W_STUB, NETS[k + 1]))
    # the line: replace the straight run with one piece per node net
    m = re.search(r'\n\t\(segment\s*\(start 162\.15 192\.4\)\s*\(end 187\.7 192\.4\)\s*\(width 0\.183\)\s*'
                  r'\(layer "F\.Cu"\)\s*\(net "/IF_RX_C"\)\s*\(uuid "[^"]+"\)\s*\)', t)
    assert m, "IF_RX_C straight run not found"
    t = t[:m.start()] + t[m.end():]
    items.append(seg(162.15, Y, NODES[0], Y, W_RF, IN))
    # the other segment that reaches 162.15,192.4 (the diagonal from C951) changes net too
    t = re.sub(r'(\(start 148\.05 206\.5\)\s*\(end 162\.15 192\.4\)\s*\(width 0\.183\)\s*\(layer "F\.Cu"\)\s*\(net )"/IF_RX_C"',
               r'\1"' + IN + '"', t, count=1)
    t = re.sub(r'(\(start 143\.55 206\.5\)\s*\(end 148\.05 206\.5\)\s*\(width 0\.183\)\s*\(layer "F\.Cu"\)\s*\(net )"/IF_RX_C"',
               r'\1"' + IN + '"', t, count=1)
    t = re.sub(r'(\(start 143\.5 206\.52\)\s*\(end 143\.55 206\.5\)\s*\(width 0\.183\)\s*\(layer "F\.Cu"\)\s*\(net )"/IF_RX_C"',
               r'\1"' + IN + '"', t, count=1)
    for k in range(3):
        lx = (NODES[k] + NODES[k + 1]) / 2
        items.append(seg(NODES[k], Y, lx - 1.0625, Y, W_RF, NETS[k]))
        items.append(seg(lx + 1.0625, Y, NODES[k + 1], Y, W_RF, NETS[k + 1]))
    items.append(seg(NODES[3], Y, 187.7, Y, W_RF, OUT))
    # IF_RX_B ran 9.8 mm beside the filter's output at 0.57 mm (-58 dB at 100 MHz, a path round the filter):
    # moved 2.4 mm down for the same length (txrx_isolation.py: no same-layer copper within 1.5 mm after)
    for pat in (r'\(start 173 199\.4\)\s*\(end 179\.25 193\.15\)', r'\(start 179\.25 193\.15\)\s*\(end 199\.95 193\.15\)'):
        m = re.search(r'\n\t\(segment\s*' + pat + r'\s*\(width 0\.183\)\s*\(layer "F\.Cu"\)\s*\(net "/IF_RX_B"\)\s*'
                      r'\(uuid "[^"]+"\)\s*\)', t)
        assert m, pat
        t = t[:m.start()] + t[m.end():]
    pts = [(173, 199.4), (177.6, 194.8), (188.6, 194.8), (190.25, 193.15), (199.95, 193.15)]
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        items.append(seg(x1, y1, x2, y2, W_RF, "/IF_RX_B"))
    # C951's pad 1 is now on the filter's input net
    s, e = block(t, "C951"); b = t[s:e].replace('(net "/IF_RX_C")', f'(net "{IN}")')
    t = t[:s] + b + "\n" + "\n".join(fps) + t[e:]
    i = t.find("\n\t(segment")
    t = t[:i] + "\n" + "\n".join(items) + t[i:]
    open(PCB, "w", encoding="utf-8", newline="\n").write(t)
    print(f"placed {len(fps)} parts, {len(items)} tracks/vias")


if __name__ == "__main__":
    main()
