"""
Draw rev03/DAC_SDR.kicad_sch from coordinates. Connections: dac_sdr_spec.py,
checked by _work/check_sheet.py dac_sdr.

Layout: port 1 data and the IQ controls in from the left, the tied-low pins
grounded by one bus below them; the reference and the two full-scale
networks hanging under U801; each DAC's output chain running right, DAC1 above
DAC2, into its balun.

Usage:  py _work/sheets/dac_sdr.py
"""

from kit import Kit, dac_output
from dac_sdr_spec import PARTS, DATA, CTRL, TIED_LOW, CHAIN_REFS

k = Kit("DAC_SDR", "DAC_SDR - AD9767 dual SDR DAC, interleaved, filters and baluns",
        PARTS, 800, "_work/sheets/dac_sdr.py")
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


plain_row("+3V3_A", ["C804", "C805"], 38.1)
plain_row("+3V3_D", ["C806", "C807", "C808"], 76.2)
s.text("C805 at AVDD pin 47; C806, C807 at DVDD1/DVDD2 pins 16/22.", (38.1, 53.34))

# ---------------------------------------------------------------- U801
CX, CY = 101.6, 124.46
U = k.part("U801", (CX, CY), text_at=(CX - 7.62, CY - 2.54))
top = CY - 63.5
dv1, dv2, av = U.pin(16), U.pin(22), U.pin(47)
for p in (dv1, dv2, av):
    s.wire(p, (p[0], top))
s.wire((dv1[0], top), (dv2[0], top))
k.rail("+3V3_D", (dv1[0], top))
k.rail("+3V3_A", (av[0], top))

for name, pin in {**DATA, **CTRL}.items():
    p = U.pin(pin)
    s.wire(p, (p[0] - 5.08, p[1]))
    s.hlabel(name, "input", (p[0] - 5.08, p[1]), side="left")
# MODE low (interleaved), GAINCTRL low (independent), SLEEP low, port 2 unused
xt = U.pin(48)[0] - 2.54
for pin in TIED_LOW:
    p = U.pin(pin)
    s.wire(p, (xt, p[1]))
s.wire((xt, U.pin(48)[1]), (xt, U.pin(36)[1]))
k.gnd((xt, U.pin(36)[1]))

# bottom: REFIO 0.1 uF; each FSADJ: RSET, and 256 ohm + 22 nF in series
p = U.pin(43)
c = k.vpart("C801", p[0], p[1])
k.gnd(c.pin(2))
for pin, rs, rn, cn in ((44, "R801", "R802", "C802"), (41, "R803", "R804", "C803")):
    p = U.pin(pin)
    r = k.vpart(rs, p[0], p[1])
    k.gnd(r.pin(2))
    s.wire(p, (p[0] + 10.16, p[1]))
    r2 = k.vpart(rn, p[0] + 10.16, p[1])
    c = k.vpart(cn, p[0] + 10.16, r2.pin(2)[1])
    k.gnd(c.pin(2))
gb = U.pin(38)[1] + 5.08
for n in (38, 15, 21):
    s.wire(U.pin(n), (U.pin(n)[0], gb))
s.wire((U.pin(38)[0], gb), (U.pin(21)[0], gb))
k.gnd((U.pin(15)[0], gb))

# ---------------------------------------------------------------- outputs
for dac, pa, pb, label, r in CHAIN_REFS:
    dac_output(k, U.pin(pa), U.pin(pb), r, label)

s.text("DAC1 -> IF_TX_A, DAC2 -> IF_TX_C. Filters: AERIS-10's, as on DAC_RADAR.", (139.7, 172.72))
k.notes([
    "DAC_SDR - how this sheet works",
    "1. Interleaved mode (MODE low): the FPGA writes I and Q alternately on one 14-bit port; IQSEL steers each word.",
    "2. IQCLK is divided by 2 inside; IQRESET aligns the pair. Series 22 ohm on the data sit at the FPGA, on CONTROL.",
    "3. Internal 1.2 V reference; RSET 3.83 kohm per DAC = 10 mA, 0.5 V on 49.9 ohm: best distortion (p.24).",
    "4. Every value is justified in _work/sheets/dac_sdr_spec.py and docs/DAC_SDR_SPEC.md.",
], (139.7, 200.66))
k.write()
