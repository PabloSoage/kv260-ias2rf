"""
Draw rev03/POWER.kicad_sch from coordinates. Connections: power_spec.py,
checked by _work/check_sheet.py power.

A2 page. Top row: input protection, then the LMR33630 (12 V -> 5 V). Middle
row: the three TPS562201 bucks. Bottom row: the three TPS7A8300 LDOs. Right
column: the LM2663 inverter and the +1V2 divider. Blocks are joined by rail
symbols, not wires: each block starts at its input rail and ends at its
output rail, which is how the power tree in docs/POWER_AND_STACKUP.md reads.

Usage:  py _work/sheets/power.py
"""

from kit import Kit
from power_spec import PARTS, BUCKS, LDOS, PROG

k = Kit("POWER", "POWER - 12 V input, protection, bucks, LDOs, -3V3", PARTS, 1000,
        "_work/sheets/power.py", paper="A2")
s = k.s


def flag(at):
    s.power("power:PWR_FLAG", "PWR_FLAG", at)


def hang(ref, x, y):
    """Vertical part from a horizontal line at y down to ground."""
    c = k.vpart(ref, x, y)
    k.gnd(c.pin(2))
    return c


# ---------------------------------------------------------------- input
Y0 = 76.2
J = k.part("J1001", (38.1, Y0 + 2.54))
assert J.pin(1) == (45.72, Y0)
k.gnd(J.pin(2))
flag(J.pin(2))                     # the board's ground enters here
f = k.hpart("F1001", 58.42, Y0)
s.wire(J.pin(1), f.pin(1))
Q = k.part("Q1001", (81.28, Y0 + 2.54), rot=90)
qd, qs, qg = Q.pin(5), Q.pin(1), Q.pin(4)          # D, S, G
assert qd[1] == Y0 and qs[1] == Y0
s.wire(f.pin(2), qd)
rg = hang("R1001", qg[0], qg[1])
z = k.part("D1002", (96.52, Y0 + 3.81), rot=270)        # K on the line, A down at the gate
s.wire(z.pin(2), qg)
tv = k.part("D1001", (111.76, Y0 + 3.81), rot=90)        # A2 on the line, A1 to ground
k.gnd(tv.pin(1))
hang("C1001", 129.54, Y0)
s.wire(qs, (144.78, Y0))
flag((139.7, Y0))
k.rail("+12V", (144.78, Y0))
s.text("Reverse polarity: Q1001 conducts only when the jack is the right way round.",
       (30.48, Y0 + 25.4))

# ---------------------------------------------------------------- +5V0: LMR33630
U = k.part("U1001", (205.74, Y0 + 7.62), text_at=(200.66, Y0 - 11.43))
vin, en, vcc, pg = U.pin(2), U.pin(3), U.pin(6), U.pin(4)
boot, sw, fb = U.pin(7), U.pin(8), U.pin(5)
k.rail("+12V", (157.48, vin[1]))
s.wire((157.48, vin[1]), vin)
hang("C1002", 165.1, vin[1])
hang("C1003", 177.8, vin[1])
s.wire(en, (en[0] - 2.54, en[1]), (en[0] - 2.54, vin[1]))   # EN tied to VIN
s.wire(vcc, (vcc[0] - 10.16, vcc[1]))
hang("C1004", vcc[0] - 10.16, vcc[1])
s.no_connect(pg)
cb = k.vpart("C1005", boot[0] + 2.54, boot[1])
assert cb.pin(2)[1] == sw[1]
s.wire(boot, cb.pin(1))
s.wire(sw, cb.pin(2))
L = k.hpart("L1001", sw[0] + 12.7, sw[1])
s.wire(cb.pin(2), L.pin(1))
xr = L.pin(2)[0] + 3.81
rt = k.vpart("R1002", xr, sw[1])
assert rt.pin(2)[1] == fb[1]
s.wire(fb, rt.pin(2))
hang("R1003", xr, fb[1])
x = xr + 12.7
for i in range(4):
    hang(f"C{1006 + i}", x, sw[1])
    x += 12.7
s.wire(L.pin(2), (x - 2.54, sw[1]))
flag((x - 5.08, sw[1]))
k.rail("+5V0", (x - 2.54, sw[1]))
gb = U.pin(1)[1] + 5.08
for n in (1, 9):
    s.wire(U.pin(n), (U.pin(n)[0], gb))
s.wire((U.pin(1)[0], gb), (U.pin(9)[0], gb))
k.gnd((U.pin(1)[0], gb))
s.text("U1001 LMR33630: 12 V -> 5.0 V, 3 A, 400 kHz. Values: datasheet Table 9-2, 5 V row.",
       (157.48, Y0 + 38.1))

# ---------------------------------------------------------------- TPS562201 bucks
CYB = 170.18
for (u, rail, r1, l, b), cx in zip(BUCKS, (90.17, 250.19, 410.21)):
    B = k.part(u, (cx, CYB), text_at=(cx - 5.08, CYB - 13.97))
    vin, en, bst, sw, vfb = B.pin(3), B.pin(5), B.pin(6), B.pin(2), B.pin(4)
    k.rail("+5V0", (cx - 53.34, vin[1]))
    s.wire((cx - 53.34, vin[1]), vin)
    hang(f"C{b}", cx - 45.72, vin[1])
    hang(f"C{b + 1}", cx - 33.02, vin[1])
    ren = k.vpart(f"R{b}", cx - 20.32, vin[1])
    assert ren.pin(2)[1] == en[1]
    s.wire(en, ren.pin(2))                     # EN pulled up to VIN
    cb = k.vpart(f"C{b + 2}", bst[0] + 2.54, bst[1])
    s.wire(bst, cb.pin(1))
    s.wire(sw, cb.pin(2))
    Lb = k.hpart(f"L{b}", cx + 22.86, sw[1])
    s.wire(cb.pin(2), Lb.pin(1))
    r_1 = k.vpart(f"R{b + 1}", cx + 30.48, sw[1])
    s.wire(vfb, r_1.pin(2))
    hang(f"R{b + 2}", cx + 30.48, vfb[1])
    hang(f"C{b + 3}", cx + 40.64, sw[1])
    hang(f"C{b + 4}", cx + 53.34, sw[1])
    s.wire(Lb.pin(2), (cx + 63.5, sw[1]))
    flag((cx + 60.96, sw[1]))
    k.rail(rail, (cx + 63.5, sw[1]))
    k.gnd(B.pin(1))
    s.text(f"{u} TPS562201: +5V0 -> {rail}, 2 A (Figure 7-1, Table 7-2).", (cx - 53.34, CYB + 25.4))

# ---------------------------------------------------------------- TPS7A8300 LDOs
CYL = 264.16
for (u, vin_r, vout_r, gnd_pins, b), cx in zip(LDOS, (90.17, 250.19, 410.21)):
    D = k.part(u, (cx, CYL), text_at=(cx - 5.08, CYL - 16.51))
    ins = [D.pin(n) for n in (15, 16, 17, 14)]
    xi = ins[0][0] - 2.54
    for p in ins:
        s.wire(p, (xi, p[1]))
    s.wire((xi, ins[0][1]), (xi, ins[-1][1]))
    k.rail(vin_r, (cx - 35.56, ins[0][1]))
    s.wire((cx - 35.56, ins[0][1]), (xi, ins[0][1]))
    hang(f"C{b}", cx - 27.94, ins[0][1])
    nr = D.pin(13)
    s.wire(nr, (cx - 22.86, nr[1]))
    hang(f"C{b + 1}", cx - 22.86, nr[1])
    s.no_connect(D.pin(12))
    outs = [D.pin(n) for n in (1, 19, 20, 2)]
    xo = outs[0][0] + 2.54
    for p in outs:
        s.wire(p, (xo, p[1]))
    s.wire((xo, outs[0][1]), (xo, outs[-1][1]))
    top = outs[0][1]
    s.wire(outs[0], (cx + 50.8, top))
    cff = k.vpart(f"C{b + 2}", cx + 22.86, top)
    fbp = D.pin(3)
    s.wire(cff.pin(2), (cx + 22.86, fbp[1]), fbp)
    hang(f"C{b + 3}", cx + 33.02, top)
    k.rail(vout_r, (cx + 50.8, top))
    s.no_connect(D.pin(4))
    gpins = list(gnd_pins) + [8, 18, 21]
    gb = D.pin(8)[1] + 5.08
    for n in gpins:
        s.wire(D.pin(n), (D.pin(n)[0], gb))
    xs = sorted(D.pin(n)[0] for n in gpins)
    s.wire((xs[0], gb), (xs[-1], gb))
    k.gnd((D.pin(18)[0], gb))
    for n in PROG:
        if n not in gnd_pins:
            s.no_connect(D.pin(n))
    volts = {(7, 10): "0.8 + 0.2 + 0.8", (5, 7, 10): "0.8 + 0.05 + 0.2 + 0.8", (6, 10, 11): "0.8 + 0.1 + 0.8 + 1.6"}[tuple(gnd_pins)]
    s.text(f"{u} TPS7A8300: {vin_r} -> {vout_r} = {volts} V (ANY-OUT, Table 2).",
           (cx - 40.64, CYL + 30.48))

# ---------------------------------------------------------------- -3V3: LM2663
cx, cy = 500.38, 170.18
M = k.part("U1008", (cx, cy), text_at=(cx - 5.08, cy - 12.7))
vp, sd, lv = M.pin(8), M.pin(1), M.pin(6)
k.rail("+3V3_D", (cx - 25.4, vp[1]))
s.wire((cx - 25.4, vp[1]), vp)
hang("C1070", cx - 17.78, vp[1])
s.wire(sd, (cx - 12.7, sd[1]), (cx - 12.7, lv[1]), lv)
k.gnd((cx - 12.7, lv[1]))
s.no_connect(M.pin(7))
cp, cn, out = M.pin(2), M.pin(4), M.pin(5)
cf = k.vpart("C1071", cp[0] + 2.54, cp[1])
assert cf.pin(2)[1] == cn[1]
s.wire(cp, cf.pin(1))
s.wire(cn, cf.pin(2))
s.wire(out, (cx + 30.48, out[1]))
hang("C1072", cx + 17.78, out[1])
k.rail("-3V3", (cx + 30.48, out[1]))
k.gnd(M.pin(3))
s.text("U1008 LM2663: +3V3_D -> about -3.25 V, for the RF switches' VEE.", (cx - 30.48, cy + 25.4))

# ---------------------------------------------------------------- +1V2 divider
cx, cy = 500.38, 264.16
k.rail("+2V5", (cx, cy - 12.7))
rt = k.vpart("R1080", cx, cy - 12.7)
rb = k.vpart("R1081", cx, rt.pin(2)[1])
k.gnd(rb.pin(2))
node = rt.pin(2)
s.wire(node, (cx + 25.4, node[1]))
hang("C1080", cx + 15.24, node[1])
flag((cx + 22.86, node[1]))
k.rail("+1V2", (cx + 25.4, node[1]))
s.text("+1V2: bias for the two terminated link pairs (IAS_LINK). No DC load.",
       (cx - 30.48, cy + 25.4))

k.notes([
    "POWER - how this sheet works",
    "1. 12 V in through a polyfuse, reverse-polarity P-MOSFET and TVS; LMR33630 makes +5V0 (3 A).",
    "2. From +5V0: three TPS562201 bucks (+3V3_D, +2V5, +1V0) and the +3V3_A LDO.",
    "3. TPS7A8300 LDOs: +1V8_A from +2V5, +1V8_D from +3V3_D. -3V3 from an LM2663 inverter.",
    "4. +2V5 also powers the FPGA's LVDS banks (IAS_LINK_SPEC 3). +1V2 is a divider: bias only.",
    "5. Every value comes from the datasheet's typical application: see docs/POWER_SPEC.md.",
], (38.1, 330.2))
k.write()
