#!/usr/bin/env python3
"""
Rev08 RF and power audit (docs/AUDIT_Rev08.md, 18 November 2026): the board edits, as text edits (no pcbnew).

  1. The front end's rail is +2V8_RF (LP5907-2.8, P8): the net is renamed everywhere.
  2. Values: U1002 TPS563201 (P5), R1031 3.24k (P7), U1315 LP5907MFX-2.8 (P8), U1506 TCAN3403DDFRQ1 (P1),
     F1001 PTC 2A hold (P3), R1542/R1543 330 ohm (the GPS PPS into an unpowered K26, under 10 mA).
  3. U1006 pin 5 (50 mV ANY-OUT) to its exposed pad, ground: +1V8_D at 1.85 V (P4).
  4. U1506 pin 5 becomes VIO: its ground via goes, a stub joins it to the +3V3_D track 0.45 mm below (P1).
  5. F1001 holds 2.0 A (P3): value only, the same 1812 footprint (a 2920 does not fit between J1001, Q1001, R1004, TP4).
  6. The 300 MHz high-pass ahead of preselector B (R1, C1441-C1445, L1441-L1442), in frame A between U1304 and the
     frame's east wall: series capacitors up a spine at x 118.4, the two shunt branches at x 119.4 grounded straight
     to the wall, C1445 at x 117.35 to a via at (116.65, 116.5); from there VU_PSB_HP runs on B.Cu to
     the old crossing under the wall and on to U1306 (pad 13 now VU_PSB_HP) as before. The old stub, via and B.Cu diagonal of VU_PSB_IN go.

Usage:  py _work/rev08_audit_pcb.py <in.kicad_pcb> <out.kicad_pcb>
"""
import os
import re
import sys
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rev08_pcb as P                                    # noqa: E402

U = lambda: str(uuid.uuid4())
W_RF = 0.2


def seg(a, b, w, layer, net):
    return (f'\t(segment\n\t\t(start {a[0]:g} {a[1]:g})\n\t\t(end {b[0]:g} {b[1]:g})\n\t\t(width {w:g})\n'
            f'\t\t(layer "{layer}")\n\t\t(net "{net}")\n\t\t(uuid "{U()}")\n\t)\n')


def via(p, net):
    return (f'\t(via\n\t\t(at {p[0]:g} {p[1]:g})\n\t\t(size 0.45)\n\t\t(drill 0.2)\n'
            f'\t\t(layers "F.Cu" "B.Cu")\n\t\t(net "{net}")\n\t\t(uuid "{U()}")\n\t)\n')


def fp_block(t, ref):
    for s, e, r in P.footprints(t):
        if r == ref:
            return s, e
    raise SystemExit(ref)


def set_value(t, ref, value):
    s, e = fp_block(t, ref)
    b, n = re.subn(r'\(property "Value" "[^"]*"', f'(property "Value" "{value}"', t[s:e], count=1)
    assert n == 1
    return t[:s] + b + t[e:]


def set_pad_net(t, ref, pad, net):
    s, e = fp_block(t, ref)
    blk = t[s:e]
    m = re.search(r'\(pad "' + pad + r'" [\s\S]*?\n\t\t\t\(net "([^"]*)"\)', blk)
    assert m, (ref, pad)
    i = m.start() + m.group(0).rfind('(net "')
    blk = blk[:i] + f'(net "{net}")' + blk[i + len(f'(net "{m.group(1)}")'):]
    return t[:s] + blk + t[e:]


def items(t):
    """(start, end, kind, body) of every top-level segment and via."""
    for m in re.finditer(r'\n\t\((segment|via)\n(.*?)\n\t\)', t, re.S):
        yield m.start(), m.end(), m.group(1), m.group(2)


def drop(t, pred):
    out, pos, n = [], 0, 0
    for s, e, kind, b in items(t):
        if pred(kind, b):
            out.append(t[pos:s]); pos = e; n += 1
    out.append(t[pos:])
    return "".join(out), n


def renet(t, pred, net):
    out, pos, n = [], 0, 0
    for s, e, kind, b in items(t):
        if pred(kind, b):
            nb = re.sub(r'\(net "[^"]*"\)', f'(net "{net}")', t[s:e], count=1)
            out += [t[pos:s], nb]; pos = e; n += 1
    out.append(t[pos:])
    return "".join(out), n


def is_seg(b, a, c, layer, net, tol=0.02):
    m = re.search(r'\(start ([-\d.]+) ([-\d.]+)\)\s*\(end ([-\d.]+) ([-\d.]+)\)[\s\S]*?\(layer "([^"]+)"\)\s*\(net "([^"]*)"\)', b)
    if not m or m.group(5) != layer or m.group(6) != net:
        return False
    p = [float(x) for x in m.groups()[:4]]
    q = [(p[0], p[1]), (p[2], p[3])]
    same = lambda u, v: abs(u[0] - v[0]) < tol and abs(u[1] - v[1]) < tol
    return (same(q[0], a) and same(q[1], c)) or (same(q[0], c) and same(q[1], a))


def is_via(b, at, net, tol=0.03):
    m = re.search(r'\(at ([-\d.]+) ([-\d.]+)\)[\s\S]*?\(net "([^"]*)"\)', b)
    return bool(m) and abs(float(m.group(1)) - at[0]) < tol and abs(float(m.group(2)) - at[1]) < tol and m.group(3) == net


def main(src, dst):
    t = open(src, encoding="utf-8").read()
    assert "VU_PSB_HP" not in t, "already applied"
    comps, pins = P.netlist()
    new = []

    # 1. the rail
    n = t.count('"+3V0_RF"')
    t = t.replace('"+3V0_RF"', '"+2V8_RF"')
    print(f"+3V0_RF -> +2V8_RF: {n} references")

    # 2. values
    for ref, v in (("U1002", "TPS563201"), ("R1031", "3.24k"), ("U1315", "LP5907MFX-2.8"), ("U1506", "TCAN3403DDFRQ1"),
                   ("F1001", "PTC 2A hold"), ("R1542", "330"), ("R1543", "330")):
        assert comps[ref]["value"] == v, (ref, comps[ref]["value"])
        t = set_value(t, ref, v)

    # 3. U1006 pin 5 to its exposed pad
    t = set_pad_net(t, "U1006", "5", "GND")
    new += [seg((115.312, 143.5), (115.95, 143.5), 0.2, "F.Cu", "GND"), seg((115.95, 143.5), (116.25, 143.3), 0.2, "F.Cu", "GND")]

    # 4. U1506 pin 5 (VIO) to +3V3_D
    t = set_pad_net(t, "U1506", "5", "+3V3_D")
    t, k = drop(t, lambda kind, b: kind == "via" and is_via(b, (188.95, 119.85), "GND"))
    assert k == 1, k
    new.append(seg((188.875, 120.35), (188.875, 120.95), 0.25, "B.Cu", "+3V3_D"))

    # 5. F1001: a 2 A hold PTC in the same 1812 footprint (a 2920 does not fit between J1001, Q1001, R1004, TP4)

    # 6. the 300 MHz high-pass
    IN, HP = "/RX_VU/VU_PSB_IN", "/RX_VU/VU_PSB_HP"
    t, k1 = drop(t, lambda kind, b: kind == "segment" and is_seg(b, (118.1, 119.45), (117.85, 119.45), "F.Cu", IN))
    t, k2 = drop(t, lambda kind, b: kind == "via" and is_via(b, (118.1, 119.45), IN))
    t, k3 = drop(t, lambda kind, b: kind == "segment" and is_seg(b, (118.175, 119.375), (120.35, 117.2), "B.Cu", IN))
    assert (k1, k2, k3) == (1, 1, 1), (k1, k2, k3)
    t, k4 = renet(t, lambda kind, b: (kind == "segment" and (is_seg(b, (120.35, 117.2), (122.5, 117.2), "B.Cu", IN)
                                                          or is_seg(b, (122.5, 117.2), (123.05, 117.2), "F.Cu", IN)))
                  or (kind == "via" and is_via(b, (122.5, 117.2), IN)), HP)
    assert k4 == 3, k4
    t = set_pad_net(t, "U1306", "13", HP)
    parts = [  # ref, lib, x, y, angle: at 90 pin 1 is the lower pad, at 270 the upper one
        ("C1441", "Capacitor_SMD:C_0402_1005Metric", 118.40, 117.80, 90),
        ("L1441", "Inductor_SMD:L_0402_1005Metric", 119.40, 117.80, 270),
        ("C1442", "Capacitor_SMD:C_0402_1005Metric", 119.40, 119.80, 270),
        ("C1443", "Capacitor_SMD:C_0402_1005Metric", 118.40, 115.80, 90),
        ("L1442", "Inductor_SMD:L_0402_1005Metric", 119.40, 115.05, 90),
        ("C1444", "Capacitor_SMD:C_0402_1005Metric", 119.40, 113.15, 90),  # courtyard just south of C1311's
        ("C1445", "Capacitor_SMD:C_0402_1005Metric", 117.35, 116.00, 270),
    ]
    blocks = []
    for ref, lib, x, y, a in parts:
        blocks.append(P.place(P.lib_text(lib), lib, ref, comps[ref], pins[ref], x, y, a, False))
    N1 = pins["C1441"]["2"]; N2 = pins["C1443"]["2"]
    M1 = pins["L1441"]["2"]; M2 = pins["L1442"]["2"]
    assert pins["C1441"]["1"] == IN and pins["C1445"]["2"] == HP and pins["C1443"]["1"] == N1
    assert pins["L1441"]["1"] == N1 and pins["C1442"]["1"] == M1 and pins["L1442"]["1"] == N2
    assert pins["C1444"]["1"] == M2 and pins["C1445"]["1"] == N2
    new += [
        seg((117.85, 119.45), (118.4, 118.9), W_RF, "F.Cu", IN), seg((118.4, 118.9), (118.4, 118.28), W_RF, "F.Cu", IN),
        seg((118.4, 117.32), (118.4, 116.28), W_RF, "F.Cu", N1), seg((118.4, 117.32), (119.4, 117.32), W_RF, "F.Cu", N1),
        seg((119.4, 118.28), (119.4, 119.32), W_RF, "F.Cu", M1),
        seg((119.4, 120.28), (120.3, 120.28), 0.25, "F.Cu", "GND"),
        seg((118.4, 115.32), (119.4, 115.53), W_RF, "F.Cu", N2), seg((118.4, 115.32), (117.35, 115.52), W_RF, "F.Cu", N2),
        seg((119.4, 114.57), (119.4, 113.63), W_RF, "F.Cu", M2),
        seg((119.4, 112.67), (120.3, 112.67), 0.25, "F.Cu", "GND"),
        # the output via sits where both inner control lines (VU_PSA_V1 on L6, VU_PSA_V2 on L3) leave 0.16 mm
        seg((117.35, 116.48), (116.65, 116.5), W_RF, "F.Cu", HP),
        via((116.65, 116.5), HP),
        seg((116.65, 116.5), (117.35, 117.2), W_RF, "B.Cu", HP),
        seg((117.35, 117.2), (120.35, 117.2), W_RF, "B.Cu", HP),
    ]
    i = t.find("\n\t(footprint")
    t = t[:i] + "\n" + "".join(blocks).rstrip("\n") + t[i:]
    j = t.rfind("\n)")
    t = t[:j] + "\n" + "".join(new).rstrip("\n") + t[j:]
    open(dst, "w", encoding="utf-8").write(t)
    print(f"wrote {dst}: 7 filter parts, {len(new)} new tracks and vias")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
