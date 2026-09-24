#!/usr/bin/env python3
"""
Draw rev03/CLOCK.kicad_sch from coordinates.

The connections this drawing must make are listed, separately, in
clock_spec.py; _work/check_sheet.py verifies the one against the other after
KiCad has exported the netlist. Values and footprints come from the spec, so
they are stated in exactly one place.

Layout, left to right:
    power row (top left) - ferrite, bulk and per-pin decoupling
    inputs  - SMA reference -> CLK0;  Si549 -> CLK1;  IN_SEL pull-up
    U401 ADCLK948
    outputs - four blocks: pull-downs, series capacitors, labels / SMA

Differential pairs are drawn with their two legs 12.7 mm apart wherever
components hang off them, so that no pull-down resistor has to cross the
other leg.

Usage:  py _work/sheets/clock.py
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import schgen                      # noqa: E402
from clock_spec import PARTS       # noqa: E402

ROOT = os.path.dirname(os.path.dirname(HERE))
SHEET = os.path.join(ROOT, "rev03", "CLOCK.kicad_sch")
FILE_UUID = "423bdb5f-8c25-5c72-9810-ebc4bd82ce94"          # keep the sheet's identity
ROOT_UUID = "56c49378-41a8-4cbc-b1f4-3d0ea65d2366"
BLOCK_UUID = "86907de8-dbaa-540c-95d7-38c6f0e48980"          # CLOCK block in the root

s = schgen.Sheet(SHEET, FILE_UUID,
                 "CLOCK - master XO, reference select, fan-out",
                 "CSI2-KRIA-KV260_Rev01", f"/{ROOT_UUID}/{BLOCK_UUID}",
                 generator="_work/sheets/clock.py")
s.lib("kv260-ias2rf", os.path.join(ROOT, "symbols", "kv260-ias2rf.kicad_sym"))


def part(ref, at, rot=0, mirror=False):
    lib_id, value, fp, _ = PARTS[ref]
    return s.place(lib_id, ref, value, at, rot, footprint=fp, mirror=mirror)


def gnd(at):
    s.power("power:GND", "GND", at)


def vclk(at):
    s.power("power:+3V3", "+3V3_CLK", at)


# ---------------------------------------------------------------- power row
RAIL = 38.1
s.power("power:+3V3", "+3V3_D", (38.1, RAIL))
fb = part("FB401", (45.72, RAIL), rot=90)
s.wire((38.1, RAIL), fb.pin(1))
s.power("power:PWR_FLAG", "PWR_FLAG", (53.34, RAIL))
vclk((57.15, RAIL))
caps = ["C401", "C402"] + [f"C{403 + i}" for i in range(6)] + ["C422"]
x = 63.5
for ref in caps:
    c = part(ref, (x, RAIL + 3.81))
    gnd(c.pin(2))
    x += 7.62
s.wire(fb.pin(2), (x - 7.62, RAIL))
s.text("C403-C408: one at each U401 VCC pin (ADCLK948 p.10). C422 at Y401 VDD.", (60.96, 53.34))

# ---------------------------------------------------------------- U401
U = part("U401", (215.9, 139.7))
vcc = [U.pin(n) for n in (10, 15, 16, 25, 26, 31)]
BUS = vcc[0][1] - 5.08
for p in vcc:
    s.wire(p, (p[0], BUS))
s.wire((vcc[0][0], BUS), (vcc[-1][0], BUS))
vclk((215.9, BUS))
gnd(U.pin(33))
s.no_connect(U.pin(9))
for n in (20, 19, 18, 17, 14, 13, 12, 11):         # Q4..Q7 unused
    s.no_connect(U.pin(n))

# ---------------------------------------------------------------- CLK0: SMA reference, single-ended
clk0 = U.pin(1)
j1 = part("J401", (165.1, clk0[1]), mirror=True)   # centre pin faces right
gnd(j1.pin(2))
c412 = part("C412", (180.34, clk0[1]), rot=90)
s.wire(j1.pin(1), c412.pin(1))
s.wire(c412.pin(2), clk0)
TIE = clk0[0] - 2.54                                 # CLK0-bar, VT0, VREF0 tied
for n in (2, 4, 3):
    s.wire(U.pin(n), (TIE, U.pin(n)[1]))
s.wire((TIE, U.pin(2)[1]), (TIE, U.pin(3)[1]))
c413 = part("C413", (TIE, U.pin(3)[1] + 3.81))
gnd(c413.pin(2))
s.text("CLK_REF_IN: 0.4-3.4 Vpp (ADCLK948 Table 1), 50 ohm on chip.", (139.7, 111.76))

# ---------------------------------------------------------------- CLK1: Si549, differential
clk1, clk1n = U.pin(5), U.pin(6)
Y = part("Y401", (132.08, clk1[1] + 1.27))         # CLK+ level with CLK1
xp, xn = Y.pin(4), Y.pin(5)
LOW = clk1[1] + 12.7                                 # lower leg of the pair
r402 = part("R402", (152.4, xp[1] + 3.81))
r403 = part("R403", (152.4, LOW + 3.81))
gnd(r402.pin(2))
gnd(r403.pin(2))
c409 = part("C409", (175.26, clk1[1]), rot=90)
c410 = part("C410", (175.26, LOW), rot=90)
s.wire(xp, c409.pin(1))                              # passes R402 pin 1
s.wire(c409.pin(2), clk1)
s.wire(xn, (147.32, xn[1]), (147.32, LOW), c410.pin(1))   # passes R403 pin 1
s.wire(c410.pin(2), (193.04, LOW), (193.04, clk1n[1]), clk1n)
s.wire(U.pin(7), (TIE, U.pin(7)[1]))
s.wire(U.pin(8), (TIE, U.pin(8)[1]))
s.wire((TIE, U.pin(7)[1]), (TIE, U.pin(8)[1]))
c411 = part("C411", (TIE, U.pin(8)[1] + 3.81))
gnd(c411.pin(2))

# Si549 supply, enable and I2C
vclk(Y.pin(6))
gnd(Y.pin(3))
s.no_connect(Y.pin(1))
oe = Y.pin(2)
s.wire(oe, (116.84, oe[1]), (116.84, oe[1] - 5.08))
vclk((116.84, oe[1] - 5.08))
sda, scl = Y.pin(7), Y.pin(8)
s.wire(sda, (88.9, sda[1]))
s.hlabel("XO_SDA", "bidirectional", (88.9, sda[1]), side="left")
r413 = part("R413", (106.68, sda[1] - 3.81))
vclk(r413.pin(1))
SCLY = scl[1] + 12.7
s.wire(scl, (114.3, scl[1]), (114.3, SCLY), (88.9, SCLY))
s.hlabel("XO_SCL", "input", (88.9, SCLY), side="left")
r414 = part("R414", (101.6, SCLY - 3.81))
vclk(r414.pin(1))
s.text("Si549: order LVPECL, 3.3 V, 5x7 mm, pinout code C. Startup frequency", (88.9, 118.11))
s.text("is irrelevant: the FPGA sets 400 or 500 MHz over I2C.", (88.9, 120.65))

# ---------------------------------------------------------------- IN_SEL
sel = U.pin(32)
SELY = sel[1] + 15.24
s.wire(sel, (195.58, sel[1]), (195.58, SELY), (88.9, SELY))
s.hlabel("CLK_SEL", "input", (88.9, SELY), side="left")
r401 = part("R401", (187.96, SELY - 3.81))
vclk(r401.pin(1))
s.text("CLK_SEL: FPGA open-drain. High/open = CLK1 (Si549), low = CLK0 (SMA).", (88.9, SELY + 5.08))

# ---------------------------------------------------------------- outputs
# Fan-out: eight pins 2.54 mm apart spread to four blocks 30.48 mm apart.
# Lines that rise turn top-first, lines that fall turn bottom-first, so no
# two lines cross (worked through in docs/CLOCK_SPEC.md §4).
BLOCKS = [("Q0", 30, 29, "CLK_ADCR", "to the AD9484 (ADC_RADAR)"),
          ("Q1", 28, 27, "CLK_ADCS", "to the AD9253 (ADC_SDR)"),
          ("Q2", 24, 23, "CLK_FPGA", "to the XC7A50T (CONTROL)"),
          ("Q3", 22, 21, None, "CLK_OUT SMA")]
pins, targets = [], []
for k, (_, pp, pn, _, _) in enumerate(BLOCKS):
    top = 60.96 + 30.48 * k
    pins += [U.pin(pp), U.pin(pn)]
    targets += [top, top + 12.7]
up = [i for i in range(8) if targets[i] < pins[i][1]]
down = [i for i in range(8) if targets[i] >= pins[i][1]]
turn = {}
for rank, i in enumerate(up):
    turn[i] = pins[i][0] + 2.54 * (rank + 1)
for rank, i in enumerate(reversed(down)):
    turn[i] = pins[i][0] + 2.54 * (rank + 1)
XR, XC, XL = 251.46, 264.16, 275.59
for i in range(8):
    k, leg = divmod(i, 2)
    name, _, _, label, note = BLOCKS[k]
    ty = targets[i]
    s.wire(pins[i], (turn[i], pins[i][1]), (turn[i], ty), (XC - 3.81, ty))
    r = part(f"R{404 + i}", (XR, ty + 3.81))
    gnd(r.pin(2))
    c = part(f"C{414 + i}", (XC, ty), rot=90)
    if label:
        s.wire(c.pin(2), (XL, ty))
        s.hlabel(f"{label}_{'P' if leg == 0 else 'N'}", "output", (XL, ty))
    elif leg == 0:
        s.wire(c.pin(2), (XL, ty))
        j2 = part("J402", (XL + 5.08, ty))
        gnd(j2.pin(2))
    else:
        s.wire(c.pin(2), (XL, ty))
        r412 = part("R412", (XL, ty + 3.81))
        gnd(r412.pin(2))
    if leg == 0:
        s.text(f"{name}: {note}", (XC - 7.62, ty - 6.35))
s.text("Receiver side, on the consuming sheet: 100 ohm across each pair (ADCLK948 Figure 17).",
       (243.84, 190.5))

# ---------------------------------------------------------------- notes
notes = [
    "CLOCK - how this sheet works",
    "1. One master clock, 400 or 500 MHz, from the Si549 (CLK1, default) or from AERIS-10 via J401 (CLK0).",
    "2. U401 copies it to the AD9484, the AD9253 and the FPGA. The AD9253 divides it internally (1..8).",
    "3. The DAC clocks are NOT here: both DACs take CMOS clocks, which the FPGA generates with their data.",
    "4. Every value on this sheet is justified in _work/sheets/clock_spec.py and docs/CLOCK_SPEC.md.",
]
for i, t in enumerate(notes):
    s.text(t, (38.1, 215.9 + 3.81 * i), size=1.524 if i == 0 else 1.27)

n, w, j = s.write()
print(f"wrote {os.path.relpath(SHEET, ROOT)}: {n} symbols, {w} wire segments, {j} junctions")
