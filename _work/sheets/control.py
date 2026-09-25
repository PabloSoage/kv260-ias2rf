"""
Draw rev03/CONTROL.kicad_sch from coordinates. Connections: control_spec.py,
checked by _work/check_sheet.py control.

A1 page. The FPGA is four units, and an FPGA sheet is read by net name: every
ball gets a short stub and a label, and the circuits it talks to are drawn
as small blocks nearby, wired, with the same labels where they meet the
FPGA. A hierarchical label at a ball means the net leaves the sheet; a plain
label means it stays on it.

  top row:     LVDS terminations and the CLK_FPGA pad | unit 1 (banks 14, 15)
               | DAC series arrays, Pmod | unit 2 (banks 34, 35) | AERIS ribbon
  bottom row:  unit 3 (configuration) and its circuits, JTAG, flash | unit 4
               (power) and the XADC filter | UG483 decoupling

Usage:  py _work/sheets/control.py
"""

from kit import Kit
from schgen import snap
import control_spec as S

k = Kit("CONTROL", "CONTROL - XC7A50T front-end FPGA, configuration, Pmod, AERIS ribbon",
        S.PARTS, 1100, "_work/sheets/control.py", paper="A1")
s = k.s
RAIL_UP = {"+1V0", "+1V2", "+1V8_D", "+2V5", "+3V3_D"}


def side_rail(name, at, d):
    """A power symbol turned to point along a stub (d = +1 right, -1 left),
    its name beyond it."""
    if name == "GND":
        rot = 90 if d > 0 else 270
    else:
        rot = 270 if d > 0 else 90
    lib = "power:GND" if name == "GND" else None
    w = 1.1 * len(name)
    tx = at[0] + 5.08 if d > 0 else at[0] - 5.08 - w
    if lib:
        s.power(lib, name, at, rot=rot, text_at=(tx, at[1]))
    else:
        k_lib = {"+1V0": "power:+1V0", "+1V2": "power:+1V2", "+1V8_D": "power:+1V8",
                 "+2V5": "power:+2V5", "+3V3_D": "power:+3V3"}[name]
        s.power(k_lib, name, at, rot=rot, text_at=(tx, at[1]))


def tag(end, net, d):
    """Put the right kind of name on a wire end: rail, sheet port or label."""
    side = "right" if d > 0 else "left"
    if net in RAIL_UP or net == "GND":
        side_rail(net, end, d)
    elif net in S.HIER:
        s.hlabel(net, S.HIER[net], end, side=side)
    else:
        s.label(net, end, side=side)


def stub(pin, net, d, length=5.08):
    end = (pin[0] + d * length, pin[1])
    s.wire(pin, end)
    tag(end, net, d)
    return end


def vstub(pin, net, dy, d=1):
    """Vertical stub (dy = -1 up, +1 down), label reading to the right."""
    end = (pin[0], pin[1] + dy * 2.54)
    s.wire(pin, end)
    tag(end, net, d)
    return end


def bus(pins, d, net, length=5.08, end="top"):
    """Join pins lying in one column with stubs and a vertical wire; the net
    name goes on a rail at the top or bottom of that wire."""
    x = pins[0][0] + d * length
    for p in pins:
        s.wire(p, (x, p[1]))
    ys = sorted(p[1] for p in pins)
    s.wire((x, ys[0]), (x, ys[-1]))
    if net == "GND":
        s.wire((x, ys[-1]), (x, ys[-1] + 2.54))
        k.gnd((x, ys[-1] + 2.54))
    elif end == "top":
        s.wire((x, ys[0]), (x, ys[0] - 2.54))
        k.rail(net, (x, ys[0] - 2.54))
    else:
        tag((x, ys[0]), net, d)


def fpga_unit(unit, at, table, nc=(), text_dy=76.2):
    U = k.part("U1101", at, unit=unit, text_at=(at[0] - 12.7, at[1] + text_dy))
    for ball, net in table.items():
        p = U.pin(ball)
        stub(p, net, -1 if p[0] < at[0] else 1)
    for ball in nc:
        s.no_connect(U.pin(ball))
    return U


def vcco(U, balls, net):
    """VCCO balls along the top: one bus above them, one rail."""
    pts = [U.pin(b) for b in balls]
    y = pts[0][1] - 5.08
    for p in pts:
        s.wire(p, (p[0], y))
    xs = sorted(p[0] for p in pts)
    s.wire((xs[0], y), (xs[-1], y))
    k.rail(net, (xs[0], y))


def standing(refs, x0, y_top, rail, pitch=12.7, label_side=1):
    """A row of pull-ups: rail along the top, each signal labelled below.
    refs: [(ref, net)]."""
    xs = []
    for i, (ref, net) in enumerate(refs):
        x = x0 + i * pitch
        r = k.vpart(ref, x, y_top)
        vstub(r.pin(2), net, 1, label_side)
        xs.append(x)
    s.wire((xs[0], y_top), (xs[-1], y_top))
    k.rail(rail, (xs[0], y_top))


def hanging(refs, x0, y_top, pitch=12.7):
    """A row of pull-downs: each signal labelled above, ground below."""
    for i, (ref, net) in enumerate(refs):
        x = x0 + i * pitch
        r = k.vpart(ref, x, y_top)
        vstub(r.pin(1), net, -1)
        k.gnd(r.pin(2))


# ================================================================ top row
U1 = fpga_unit(1, (228.6, 165.1), {**S.BANK14, **S.BANK15}, S.BANK_NC[14] + S.BANK_NC[15])
vcco(U1, S.FPGA_POWER_PINS["VCCO_14"], "+3V3_D")
vcco(U1, S.FPGA_POWER_PINS["VCCO_15"], "+3V3_D")
s.text("Bank 14, VCCO 3.3 V: AD9484 on AERIS-10's balls, AD9253, link inputs, CLK_FPGA, flash",
       (152.4, 68.58))
s.text("Bank 15, VCCO 3.3 V: DACs (22R series), Pmod, RF switches, clock select, XO I2C",
       (243.84, 72.39))

# ---- LVDS terminations, two rows of seven
x0, y0 = 30.48, 106.68
s.text("100R across each pair at the FPGA. The banks are 3.3 V, where DIFF_TERM is not "
       "allowed (UG471)", (x0 - 2.54, y0 - 10.16))
for i, n in enumerate(S.TERM):
    x = x0 + (i % 7) * 17.78
    y = y0 + (i // 7) * 30.48
    r = k.vpart(S.TERM_REF[n], x, y)
    vstub(r.pin(1), f"{n}_P", -1)
    vstub(r.pin(2), f"{n}_N", 1)

# ---- CLK_FPGA attenuator
x, yp = 88.9, 182.88
yn = yp + 30.48
s.text("CLK_FPGA: ADCLK948 610-960 mV > LVDS_25 600 mV max (DS181 Table 11).",
       (22.86, yp - 12.7))
s.text("24.9R series + 24.9R shunt per leg: 50R to the line, half the swing.",
       (22.86, yp - 8.89))
for leg, y, rs in (("P", yp, "R1115"), ("N", yn, "R1116")):
    r = k.hpart(rs, x - 15.24, y)
    s.wire(r.pin(2), (x + 7.62, y))
    s.wire(r.pin(1), (x - 30.48, y))
    s.hlabel(f"CLK_FPGA_{leg}", "input", (x - 30.48, y), side="left")
    s.label(f"FPGA_CLK_{leg}", (x + 7.62, y))
r7 = k.vpart("R1117", x, yp)
r8 = k.vpart("R1118", x, yn - 7.62)
yb = yp + 15.24
s.wire(r7.pin(2), r8.pin(1))
s.wire((x, yb), (x + 12.7, yb))
c = k.vpart("C1101", x + 12.7, yb)
k.gnd(c.pin(2))
k.rail("+1V2", (x + 12.7, yb))

# ---- DAC series arrays, right of unit 1
xa, ya = 345.44, 101.6
s.text("22R series on every DAC line, as AERIS-10", (xa - 17.78, ya - 10.16))
lines_by_pack = {}
for n, (ref, a, b) in S.RPACK.items():
    lines_by_pack.setdefault(ref, []).append((n, a, b))
for i, ref in enumerate(sorted(lines_by_pack)):
    y = ya + i * 17.78
    P = k.part(ref, (xa, y + 3.81), rot=270, text_at=(xa - 3.81, y - 7.62))
    assert P.pin(1)[0] < xa < P.pin(8)[0] and P.pin(1)[1] == P.pin(8)[1]
    for n, a, b in lines_by_pack[ref]:
        stub(P.pin(a), f"F_{n}", -1, 2.54)
        stub(P.pin(b), n, 1, 2.54)
for ref, kk in S.RPACK_SPARE:
    P = [p for p in s.parts if p.ref == ref][0]
    s.no_connect(P.pin(kk))
    s.no_connect(P.pin(9 - kk))

# ---- Pmod
J = k.part("J1102", (411.48, 111.76), text_at=(406.4, 99.06))
s.text("Pmod, from the KV260's J2 (INTERFACE_SPEC 4.2). Pmod pin k = pad 2k-1,",
       (386.08, 129.54))
s.text("pin k+6 = pad 2k. Its 3.3 V (pins 6, 12) is not used.", (386.08, 133.35))
for kk, net in S.PMOD_PINS.items():
    pad = S.pmod_pad(kk)
    p = J.pin(pad)
    stub(p, net, -1 if pad % 2 else 1)
for kk in S.PMOD_NC:
    s.no_connect(J.pin(S.pmod_pad(kk)))

# ---- unit 2
U2 = fpga_unit(2, (563.88, 165.1), {**S.BANK34, **S.BANK35}, S.BANK_NC[34] + S.BANK_NC[35])
vcco(U2, S.FPGA_POWER_PINS["VCCO_34"], "+2V5")
vcco(U2, S.FPGA_POWER_PINS["VCCO_35"], "+1V8_D")
s.text("Bank 34, VCCO 2.5 V: the link pairs the FPGA drives", (472.44, 64.77))
s.text("(LVDS_25 outputs need 2.5 V). 14 balls unused.", (472.44, 68.58))
s.text("Bank 35, VCCO 1.8 V: ADAR1000 control, converter SPI, HK, IRQ", (579.12, 72.39))

# ---- AERIS ribbon
J = k.part("J1103", (706.12, 157.48), text_at=(701.04, 124.46))
gnd_r = []
for pin, net in S.IDC.items():
    p = J.pin(pin)
    if net == "GND" and pin % 2 == 0:
        gnd_r.append(p)
    elif net == "GND":
        s.wire(p, (p[0] - 5.08, p[1]))
        k.gnd((p[0] - 5.08, p[1]))
    else:
        stub(p, net, -1 if pin % 2 else 1)
bus(gnd_r, 1, "GND")
s.text("To AERIS-10: 4 lines per ADAR1000 (CS, TX_LOAD,", (688.34, 190.5))
s.text("RX_LOAD, TR) for 8 chips, then the shared SPI. 1.8 V.", (688.34, 194.31))

# ================================================================ bottom row
U3 = fpga_unit(3, (101.6, 391.16), {b: n for b, n in S.CONFIG.items()
                                    if not n.startswith(("XADC", "GND", "+3V3"))},
               text_dy=-48.26)
k.rail("+3V3_D", U3.pin("L6"))                        # VCCO_0
cf = U3.pin("E7")                                     # CFGBVS
s.wire(cf, (cf[0] + 5.08, cf[1]))
side_rail("+3V3_D", (cf[0] + 5.08, cf[1]), 1)
bus([U3.pin(b) for b in ("H8", "J7", "J8", "H7")], 1, "XADC_GND", end="label")
bus([U3.pin(b) for b in ("K8", "K7")], 1, "GND")
s.text("CFGBVS high: banks 0, 14, 15 at 3.3 V (UG470). XADC inputs and on-chip reference to",
       (63.5, 444.5))
s.text("GNDADC (UG480 Figure 1-2); temperature diode unused.", (63.5, 448.31))

# ---- mode, INIT_B, PUDC_B, flash pull-ups
x0, y0 = 177.8, 347.98
s.text("Master SPI x4, UG470 Figure 2-14: M[2:0] = 001", (x0 - 2.54, y0 - 10.16))
standing([("R1120", "MODE_M0"), ("R1119", "PUDC_B"), ("R1123", "INIT_B"),
          ("R1124", "PROGRAM_B")], x0, y0, "+3V3_D")
hanging([("R1121", "MODE_M1"), ("R1122", "MODE_M2")], x0 + 55.88, y0 + 5.08)

# ---- PROGRAM_B: push button and the Kria's reset through an open-drain buffer
xb, yb = 208.28, 403.86
B = k.part("U1103", (xb, yb), text_at=(xb - 27.94, yb + 10.16))
a, y_, vcc, gnd_, nc = (B.pin(n) for n in (2, 4, 5, 3, 1))
s.wire(a, (a[0] - 20.32, a[1]))
s.hlabel("FPGA_PROG_B", "input", (a[0] - 20.32, a[1]), side="left")
r = k.vpart("R1129", a[0] - 10.16, a[1] - 7.62)
k.rail("+1V8_D", r.pin(1))
top = (vcc[0], vcc[1] - 2.54)
k.rail("+1V8_D", top)
cb = k.vpart("C1181", vcc[0] + 10.16, top[1])
s.wire(vcc, top, cb.pin(1))
k.gnd(cb.pin(2))
k.gnd(gnd_)
s.no_connect(nc)
s.wire(y_, (y_[0] + 15.24, y_[1]))
s.label("PROGRAM_B", (y_[0] + 15.24, y_[1]))
sw = k.part("SW1101", (y_[0] + 7.62, y_[1] + 7.62), rot=270,
            text_at=(y_[0] + 11.43, y_[1] + 6.35))
assert sw.pin(1) == (snap(y_[0] + 7.62), snap(y_[1] + 2.54)), sw.pin(1)
s.wire((y_[0] + 7.62, y_[1]), sw.pin(1))
k.gnd(sw.pin(2))
s.text("PROGRAM_B: 4.7k pull-up above; push button (UG470 Table 2-4) and the Kria's",
       (xb - 30.48, yb + 22.86))
s.text("FPGA_PROG_B (1.8 V) through a 74LVC1G07 open-drain buffer at 1.8 V.", (xb - 30.48, yb + 26.67))

# ---- DONE LED
xd, yd = 284.48, 360.68
r = k.vpart("R1130", xd, yd)
k.rail("+3V3_D", r.pin(1))
led = k.part("D1101", (xd, yd + 15.24), rot=90, text_at=(xd - 3.81, yd + 13.97))
assert led.pin(2)[1] == snap(r.pin(2)[1] + 3.81), (led.pin(2), r.pin(2))
s.wire(r.pin(2), led.pin(2))
q = k.part("Q1101", (xd - 2.54, led.pin(1)[1] + 13.97),
           text_at=(xd + 3.81, led.pin(1)[1] + 12.7))
s.wire(led.pin(1), q.pin(3))
k.gnd(q.pin(2))
g = q.pin(1)
s.wire(g, (g[0] - 5.08, g[1]))
s.label("DONE", (g[0] - 5.08, g[1]), side="left")

# ---- JTAG
J = k.part("J1101", (322.58, 386.08), text_at=(317.5, 370.84))
gnd_l = []
for pin, net in S.JTAG.items():
    p = J.pin(pin)
    if net == "GND":
        gnd_l.append(p)
    elif net == "+3V3_D":
        s.wire(p, (p[0] + 5.08, p[1]))
        side_rail(net, (p[0] + 5.08, p[1]), 1)
    else:
        stub(p, net, 1)
bus(gnd_l, -1, "GND", length=2.54)
for pin in S.JTAG_NC:
    s.no_connect(J.pin(pin))
s.text("JTAG: Xilinx 2x7 2 mm, DS593 Figure 14", (309.88, 406.4))

# ---- configuration flash
xf, yf = 406.4, 386.08
F = k.part("U1102", (xf, yf), text_at=(xf - 25.4, yf - 15.24))
for n, net in ((1, "FLASH_CS"), (6, "FLASH_CLK"), (5, "FLASH_DQ0"), (2, "FLASH_DQ1"),
               (3, "FLASH_DQ2"), (7, "FLASH_DQ3")):
    stub(F.pin(n), net, -1)
vf = F.pin(8)
top = (vf[0], vf[1] - 5.08)
k.rail("+3V3_D", top)
k.gnd(F.pin(4))
cf = k.vpart("C1180", xf + 12.7, top[1])
s.wire(vf, top, cf.pin(1))
k.gnd(cf.pin(2))
rc = k.hpart("R1125", xf - 30.48, yf + 25.4)
s.wire(rc.pin(1), (rc.pin(1)[0] - 5.08, rc.pin(1)[1]))
s.label("F_CCLK", (rc.pin(1)[0] - 5.08, rc.pin(1)[1]), side="left")
s.wire(rc.pin(2), (rc.pin(2)[0] + 5.08, rc.pin(2)[1]))
s.label("FLASH_CLK", (rc.pin(2)[0] + 5.08, rc.pin(2)[1]))
standing([("R1126", "FLASH_CS"), ("R1127", "FLASH_DQ2"), ("R1128", "FLASH_DQ3")],
         xf + 22.86, yf - 2.54, "+3V3_D", pitch=15.24)
s.text("MT25QL128: FCS_B 2.4k, W and HOLD 4.7k (UG470 Figure 2-14); CCLK 22R series as AERIS",
       (xf - 43.18, yf + 35.56))

# ---- HK I2C pull-ups
standing([("R1131", "HK_SCL"), ("R1132", "HK_SDA")], 490.22, 347.98, "+1V8_D", pitch=15.24)
s.text("HK I2C pull-ups at 1.8 V (DNP if the carrier has its own)", (477.52, 337.82))

# ---- unit 4, power
U4 = k.part("U1101", (579.12, 406.4), unit=4, text_at=(566.42, 444.5))
pw = S.FPGA_POWER_PINS
left = lambda n: [U4.pin(b) for b in pw[n] if U4.pin(b)[0] < 579.12]   # noqa: E731
right = lambda n: [U4.pin(b) for b in pw[n] if U4.pin(b)[0] > 579.12]  # noqa: E731
bus(left("VCCAUX"), -1, "+1V8_D")
stub(U4.pin(pw["GNDADC_0"][0]), "XADC_GND", -1)
stub(U4.pin(pw["VCCADC_0"][0]), "XADC_VCC", -1)
stub(U4.pin(pw["VCCBATT_0"][0]), "GND", -1)
bus(left("VCCBRAM"), -1, "+1V0", length=10.16, end="side")
bus(left("GND"), -1, "GND")
bus(right("VCCINT"), 1, "+1V0")
bus(right("GND"), 1, "GND")
s.text("VCCBATT to GND: no bitstream encryption (DS181; UG470 Figure 2-14)", (538.48, 452.12))

# ---- XADC supply filter, UG480 Figure 1-2 (right)
x0, y0 = 632.46, 360.68
k.rail("+1V8_D", (x0, y0))
fb = k.hpart("FB1101", x0 + 12.7, y0)
s.wire((x0, y0), fb.pin(1))
s.power("power:PWR_FLAG", "PWR_FLAG", (x0 + 22.86, y0))
s.wire(fb.pin(2), (x0 + 50.8, y0))
s.label("XADC_VCC", (x0 + 50.8, y0))
yg = y0 + 7.62
for i, ref in enumerate(("C1175", "C1176")):
    k.vpart(ref, x0 + 30.48 + 10.16 * i, y0)
s.wire((x0 + 30.48, yg), (x0 + 50.8, yg))
s.power("power:PWR_FLAG", "PWR_FLAG", (x0 + 48.26, yg))
s.label("XADC_GND", (x0 + 50.8, yg))
fb2 = k.vpart("FB1102", x0 + 30.48, yg)
k.gnd(fb2.pin(2))
s.text("XADC: VCCADC from VCCAUX through a ferrite, GNDADC to ground through another",
       (x0 - 5.08, y0 - 12.7))
s.text("(UG480 Figure 1-2, on-chip reference)", (x0 - 5.08, y0 - 8.89))

# ---- decoupling, UG483 Table 2-2
place = {"VCCINT": (30.48, 480.06), "VCCBRAM": (160.02, 480.06), "VCCAUX": (215.9, 480.06),
         "VCCO_0": (309.88, 480.06), "VCCO_14/15": (345.44, 480.06),
         "VCCO_34": (30.48, 530.86), "VCCO_35": (147.32, 530.86)}
s.text("Decoupling per UG483 Table 2-2 (FTG256, XC7A50T); types per Table 2-5",
       (27.94, 462.28), size=1.524)
for rail, group, refs in S.DEC_REFS:
    xg, yg = place[group]
    s.text(group, (xg, yg - 7.62))
    k.rail(rail, (xg, yg))
    x = xg + 7.62
    for ref in refs:
        cc = k.vpart(ref, x, yg)
        k.gnd(cc.pin(2))
        x += 12.7
    s.wire((xg, yg), (x - 12.7, yg))

k.notes([
    "CONTROL - how this sheet works",
    "1. Every FPGA ball has a stub and a name. Hierarchical label = the net leaves the sheet; plain label = it stays here.",
    "2. Bank voltages: 14 and 15 at 3.3 V, 34 at 2.5 V (link outputs only), 35 at 1.8 V. See docs/CONTROL_SPEC.md.",
    "3. Pin table: _work/sheets/control_spec.py, checked against the symbol's ball names (bank, pair, clock capable).",
    "4. Boot: master SPI x4 from U1102 (UG470 Figure 2-14). Reset: SW1101 or the Kria's FPGA_PROG_B via U1103.",
], (525.78, 508.0))
k.write()
