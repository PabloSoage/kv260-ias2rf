"""
Draw rev03/DAC_RADAR.kicad_sch from coordinates. Connections: dac_radar_spec.py,
checked by _work/check_sheet.py dac_radar.

Layout: data and clock labels into U701 from the left; reference, full-scale
and ground parts hanging below it; COMP1's capacitor to AVDD on top; the
output filter running right, differential legs 15.24 mm apart so the shunt
parts hang between them, into the balun and out as IF_TX_B.

Usage:  py _work/sheets/dac_radar.py
"""

from kit import Kit
from dac_radar_spec import PARTS, DATA

k = Kit("DAC_RADAR", "DAC_RADAR - AD9708 radar chirp DAC, reconstruction filter, balun",
        PARTS, 700, "_work/sheets/dac_radar.py")
s = k.s

# ---------------------------------------------------------------- supplies
ROW = 38.1


def plain_row(rail, caps, x0):
    k.rail(rail, (x0, ROW))
    x = x0 + 6.35
    for ref in caps:
        c = k.vpart(ref, x, ROW)
        k.gnd(c.pin(2))
        x += 10.16
    s.wire((x0, ROW), (x - 10.16, ROW))


plain_row("+3V3_A", ["C702", "C703"], 38.1)
plain_row("+3V3_D", ["C704"], 76.2)
s.text("+3V3_A is the analogue LDO; no extra filter (AD9708 Figure 22 is for a shared supply).",
       (38.1, 55.88))

# ---------------------------------------------------------------- U701
CX, CY = 127.0, 127.0
U = k.part("U701", (CX, CY), text_at=(CX - 7.62, CY - 2.54))
top = CY - 45.72
for pin, rail in ((27, "+3V3_D"), (24, "+3V3_A")):
    p = U.pin(pin)
    s.wire(p, (p[0], top))
    k.rail(rail, (p[0], top))
comp1 = U.pin(19)
s.wire(comp1, (comp1[0], CY - 40.64))
k.hpart("C701", (U.pin(24)[0] + comp1[0]) / 2, CY - 40.64)

# data and clock straight in (series resistors sit at the FPGA, on CONTROL)
for name, pin in list(DATA.items()) + [("DACR_CLK", 28)]:
    p = U.pin(pin)
    s.wire(p, (p[0] - 5.08, p[1]))
    s.hlabel(name, "input", (p[0] - 5.08, p[1]), side="left")
sl = U.pin(15)                                        # SLEEP low: always on
s.wire(sl, (sl[0] - 2.54, sl[1]))
k.gnd((sl[0] - 2.54, sl[1]))
for n in (9, 10, 11, 12, 13, 14, 25):
    s.no_connect(U.pin(n))

# bottom: REFIO 0.1 uF, RSET, COMP2 0.1 uF, then REFLO/ACOM/DCOM to ground
for pin, ref in ((17, "C705"), (18, "R701"), (23, "C706")):
    p = U.pin(pin)
    c = k.vpart(ref, p[0], p[1])
    k.gnd(c.pin(2))
gb = U.pin(16)[1] + 5.08
for n in (16, 20, 26):
    s.wire(U.pin(n), (U.pin(n)[0], gb))
s.wire((U.pin(16)[0], gb), (U.pin(26)[0], gb))
k.gnd((U.pin(20)[0], gb))

# ---------------------------------------------------------------- output filter
P, N = U.pin(22), U.pin(21)
xo = P[0]
for ref, dx, leg in (("R702", 5.08, P), ("R703", 5.08, N), ("C707", 15.24, P), ("C708", 15.24, N)):
    c = k.vpart(ref, xo + dx, leg[1])
    k.gnd(c.pin(2))


def across(ref, x):
    c = k.vpart(ref, x, P[1])
    s.wire(c.pin(2), (x, N[1]))


across("C709", xo + 25.4)
l1p, l1n = k.hpart("L701", xo + 38.1, P[1]), k.hpart("L702", xo + 38.1, N[1])
across("C710", xo + 50.8)
l2p, l2n = k.hpart("L703", xo + 63.5, P[1]), k.hpart("L704", xo + 63.5, N[1])
across("C711", xo + 76.2)
s.wire(P, l1p.pin(1))
s.wire(N, l1n.pin(1))
s.wire(l1p.pin(2), l2p.pin(1))
s.wire(l1n.pin(2), l2n.pin(1))
T = k.part("T701", (xo + 99.06, P[1] + k.s._sym(k.P["T701"][0]).pins["6"][1]),
           text_at=(xo + 113.03, P[1] + 5.08))
aa, ab, sa, sb = T.pin(6), T.pin(4), T.pin(1), T.pin(3)   # ADT2-1T+: secondary 6/4, primary 3/1
assert aa[1] == P[1]
s.wire(l2p.pin(2), aa)
s.wire(l2n.pin(2), (aa[0] - 2.54, N[1]), (aa[0] - 2.54, ab[1]), ab)
s.wire(sb, (sb[0] + 5.08, sb[1]))
s.hlabel("IF_TX_B", "output", (sb[0] + 5.08, sb[1]))
k.gnd(sa)
s.no_connect(T.pin(5))                                   # centre tap unused
s.no_connect(T.pin(2))

s.text("Reconstruction filter: AERIS-10's, as designed (107.3 nH, 32.8/106/22 pF).", (160.02, 165.1))
k.notes([
    "DAC_RADAR - how this sheet works",
    "1. The FPGA sends 8-bit samples and their clock (3.3 V CMOS); series 22 ohm sit at the FPGA end, on CONTROL.",
    "2. Internal 1.2 V reference (REFLO to ACOM), RSET 1.91 kohm: 20 mA full scale. AERIS-10 differs here, see the spec.",
    "3. 50 ohm loads, then AERIS-10's differential LC reconstruction filter, then a 2:1 balun to 50 ohm single-ended.",
    "4. Every value is justified in _work/sheets/dac_radar_spec.py and docs/DAC_RADAR_SPEC.md.",
], (38.1, 190.5))
k.write()
