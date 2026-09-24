"""
Draw rev03/ADC_RADAR.kicad_sch from coordinates.

The connections this drawing must make are listed, separately, in
adc_radar_spec.py; _work/check_sheet.py verifies the one against the other
after KiCad has exported the netlist. Values and footprints come from the
spec, so they are stated in exactly one place.

Layout: three power rows along the top; the signal chain left to right
across the middle - IF input, U502, the interstage network, U503, the ADC
input network, U501 - with the data outputs leaving U501 to the right.

Each AD8352 has its external parts in columns 10.16 mm apart (RG, RN, RD,
CD from the pins outwards), wide enough for each part's text. The symbol's pin order (_work/make_symbols.py,
SYMBOL_LAYOUT) puts each pair that takes a part one resistor length apart,
so every part sits straight across its two pins and nothing crosses.

Usage:  py _work/sheets/adc_radar.py
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import schgen                                         # noqa: E402
from adc_radar_spec import PARTS, DATA, AVDD, DRVDD   # noqa: E402

ROOT = os.path.dirname(os.path.dirname(HERE))
SHEET = os.path.join(ROOT, "rev03", "ADC_RADAR.kicad_sch")
FILE_UUID = "f516a8bf-8a6f-57ae-bb4a-d2d154fceb63"          # keep the sheet's identity
ROOT_UUID = "56c49378-41a8-4cbc-b1f4-3d0ea65d2366"
BLOCK_UUID = "098c3043-9761-501a-810e-811ea671fbd3"          # ADC_RADAR block in the root

s = schgen.Sheet(SHEET, FILE_UUID, "ADC_RADAR - AD9484 radar ADC and its AD8352 drivers",
                 "CSI2-KRIA-KV260_Rev01", f"/{ROOT_UUID}/{BLOCK_UUID}",
                 generator="_work/sheets/adc_radar.py", ref_base=500)
s.lib("kv260-ias2rf", os.path.join(ROOT, "symbols", "kv260-ias2rf.kicad_sym"))


def part(ref, at, rot=0, text_at=None):
    lib_id, value, fp, _ = PARTS[ref]
    return s.place(lib_id, ref, value, at, rot, footprint=fp, text_at=text_at)


def gnd(at):
    s.power("power:GND", "GND", at)


def rail(name, at):
    s.power("power:+5V" if name.startswith("+5") else "power:+1V8", name, at)


def hcap(ref, x, y):
    """Horizontal two-pin part centred at (x, y): pin 1 left, pin 2 right."""
    return part(ref, (x, y), rot=90)


def vpart(ref, x, top):
    """Vertical two-pin part with pin 1 at (x, top), pin 2 7.62 mm below."""
    return part(ref, (x, top + 3.81))


# ---------------------------------------------------------------- power rows
ROW = 38.1


def power_row(src, fb, local, caps, x0):
    s.power("power:+5V" if src.startswith("+5") else "power:+1V8", src, (x0, ROW))
    f = part(fb, (x0 + 7.62, ROW), rot=90)
    s.wire((x0, ROW), f.pin(1))
    s.power("power:PWR_FLAG", "PWR_FLAG", (x0 + 15.24, ROW))
    rail(local, (x0 + 19.05, ROW))
    x = x0 + 25.4
    for ref in caps:
        c = vpart(ref, x, ROW)
        gnd(c.pin(2))
        x += 10.16                      # room for each part's text
    s.wire(f.pin(2), (x - 10.16, ROW))


power_row("+5V0", "FB501", "+5V_IFR", ["C520", "C505", "C506", "C514", "C515"], 25.4)
power_row("+1V8_A", "FB502", "+1V8_ADCR_A", ["C521"] + [f"C{522 + i}" for i in range(11)], 111.76)
power_row("+1V8_D", "FB503", "+1V8_ADCR_D", ["C533", "C534", "C535", "C536"], 266.7)
s.text("C505/C506: at U502 VCC pins 8/13. C514/C515: at U503 VCC pins 8/13 (AD8352 eval board).",
       (25.4, 55.88))
s.text("C522-C532: one at each AVDD pin, C534-C536: one at each DRVDD pin (AD9484 eval board).",
       (25.4, 58.42))

# ---------------------------------------------------------------- the two AD8352 stages
CY = 100.33                         # both stages on one row: the legs run straight
CX1, CX2 = 101.6, 191.77
CYA = CY + 30.48                    # puts U501 VIN- level with the N leg
CXA = 278.13
COL = 10.16                         # spacing of the RG / RN / RD / CD columns


def driver(ref, cx, rg, rd, cd, vcm, rn=None):
    """Place one AD8352 with RG, RN, RD, CD and VCM; ENB tied to VCC on top."""
    U = part(ref, (cx, CY), text_at=(cx + 13.97, CY + 17.78))
    vip, rgn, rgp, rdp, rdn = (U.pin(n) for n in (16, 3, 2, 1, 4))
    xp = vip[0]                                     # left pin ends
    cols = iter(xp - 7.62 - COL * k for k in range(4))
    # RG across RGN/RGP, RN (if any) from VIP down to RGN, RD and CD across RDP/RDN
    r_g = vpart(rg, next(cols), rgn[1])
    s.wire(rgp, r_g.pin(2))
    if rn:
        r_n = vpart(rn, next(cols), vip[1])
        s.wire(rgn, r_n.pin(2))
    else:
        s.wire(rgn, r_g.pin(1))
    r_d = vpart(rd, next(cols), rdp[1])
    c_d = vpart(cd, next(cols), rdp[1])
    s.wire(rdp, c_d.pin(1))
    s.wire(r_d.pin(2), (r_d.pin(2)[0], rdn[1]))
    s.wire(c_d.pin(2), (c_d.pin(2)[0], rdn[1]))
    s.wire(rdn, (c_d.pin(2)[0], rdn[1]))
    # VCM decoupled (AD8352 Table 4)
    vcmp = U.pin(14)
    s.wire(vcmp, (xp - 5.08, vcmp[1]))
    c = vpart(vcm, xp - 5.08, vcmp[1])
    gnd(c.pin(2))
    # VCC and ENB onto one bus: ENB tied to the supply (AD8352 eval board R10)
    top = U.pin(8)[1] - 5.08
    for n in (8, 13, 15):
        s.wire(U.pin(n), (U.pin(n)[0], top))
    s.wire((U.pin(8)[0], top), (U.pin(15)[0], top))
    rail("+5V_IFR", (U.pin(13)[0], top))
    bot = U.pin(6)[1] + 5.08
    for n in (6, 7, 9, 12, 17):
        s.wire(U.pin(n), (U.pin(n)[0], bot))
    s.wire((U.pin(6)[0], bot), (U.pin(17)[0], bot))
    gnd((cx, bot))
    return U


U2 = driver("U502", CX1, "R504", "R505", "C503", "C504", rn="R502")
U3 = driver("U503", CX2, "R508", "R509", "C512", "C513")

# stage 1 input: 65 ohm termination, AC coupling, VIN to 25 ohm (AD8352 Figure 26)
vip1, vin1 = U2.pin(16), U2.pin(5)
xp1 = vip1[0]
c501 = hcap("C501", xp1 - 25.4, vip1[1])
s.wire(vip1, c501.pin(2))
r501 = vpart("R501", xp1 - 35.56, vip1[1])
gnd(r501.pin(2))
s.wire(c501.pin(1), (xp1 - 43.18, vip1[1]))
s.hlabel("IF_RX_B", "input", (xp1 - 43.18, vip1[1]), side="left")
c502 = hcap("C502", xp1 - 25.4, vin1[1])
s.wire(vin1, c502.pin(2))
r503 = vpart("R503", xp1 - 35.56, vin1[1])
gnd(r503.pin(2))
s.wire(c502.pin(1), r503.pin(1))

# ---------------------------------------------------------------- between the stages
vop1, von1 = U2.pin(11), U2.pin(10)
xo1 = vop1[0]
c507, c508 = hcap("C507", xo1 + 6.35, vop1[1]), hcap("C508", xo1 + 6.35, von1[1])
s.wire(vop1, c507.pin(1))
s.wire(von1, c508.pin(1))
XCH = xo1 + 15.24
r506 = vpart("R506", XCH, vop1[1])
r507 = vpart("R507", XCH, von1[1] - 7.62)
s.wire(r506.pin(2), r507.pin(1))
c509 = hcap("C509", XCH + 3.81, CY - 5.08)
s.wire(c509.pin(2), (c509.pin(2)[0] + 5.08, c509.pin(2)[1]))   # keeps "GND" clear of "100n"
gnd((c509.pin(2)[0] + 5.08, c509.pin(2)[1]))
c510, c511 = hcap("C510", xo1 + 27.94, vop1[1]), hcap("C511", xo1 + 27.94, von1[1])
s.wire(c507.pin(2), c510.pin(1))
s.wire(c508.pin(2), c511.pin(1))
s.wire(c510.pin(2), U3.pin(16))
s.wire(c511.pin(2), U3.pin(5))

# ---------------------------------------------------------------- into the ADC (AD9484 Figure 30)
U = part("U501", (CXA, CYA), text_at=(CXA - 7.62, CYA - 2.54))
xa = U.pin(35)[0]                                    # U501 left pin ends
vop2, von2 = U3.pin(11), U3.pin(10)
xo2 = vop2[0]
c516, c517 = hcap("C516", xo2 + 6.35, vop2[1]), hcap("C517", xo2 + 6.35, von2[1])
s.wire(vop2, c516.pin(1))
s.wire(von2, c517.pin(1))
XCH2 = xo2 + 15.24
r510 = vpart("R510", XCH2, vop2[1])
r511 = vpart("R511", XCH2, von2[1] - 7.62)
s.wire(r510.pin(2), r511.pin(1))
s.wire((XCH2, CY - 5.08), (XCH2 + 2.54, CY - 5.08))
s.label("ADCR_VCM", (XCH2 + 2.54, CY - 5.08))
r512, r513 = hcap("R512", xo2 + 25.4, vop2[1]), hcap("R513", xo2 + 25.4, von2[1])
s.wire(c516.pin(2), r512.pin(1))
s.wire(c517.pin(2), r513.pin(1))
c519 = vpart("C519", xo2 + 33.02, vop2[1])
s.wire(c519.pin(2), (c519.pin(2)[0], von2[1]))
vinp, vinn = U.pin(35), U.pin(36)
assert vinn[1] == von2[1], (vinn, von2)             # N leg runs straight in
assert xa - 2.54 > c519.pin(1)[0] + 7.62, "P jog would run into C519's text"
s.wire(r512.pin(2), (xa - 2.54, vop2[1]), (xa - 2.54, vinp[1]), vinp)
s.wire(r513.pin(2), vinn)

# CML: the common-mode node, joined by label; 0.1 uF at the pin
cml = U.pin(40)
s.wire(cml, (xa - 20.32, cml[1]))
s.label("ADCR_VCM", (xa - 20.32, cml[1]), side="left")
c518 = vpart("C518", xa - 15.24, cml[1])
gnd(c518.pin(2))
# VREF: 20 kohm to ground selects the internal reference
vref = U.pin(31)
s.wire(vref, (xa - 5.08, vref[1]))
r515 = vpart("R515", xa - 5.08, vref[1])
gnd(r515.pin(2))

# Clock: 100 ohm across the pair at the receiver
ckp, ckn = U.pin(44), U.pin(45)
XL = xa - 20.32
r514 = vpart("R514", xa - 10.16, ckp[1])
s.wire(ckp, (XL, ckp[1]))
s.wire(ckn, (xa - 5.08, ckn[1]), (xa - 5.08, r514.pin(2)[1]), (XL, r514.pin(2)[1]))
s.hlabel("CLK_ADCR_P", "input", (XL, ckp[1]), side="left")
s.hlabel("CLK_ADCR_N", "input", (XL, r514.pin(2)[1]), side="left")

# SPI; PWDN tied low (power-down is available through SPI register 0x08)
for pin, name, shape in ((25, "CONV_SPI_SDIO", "bidirectional"), (26, "CONV_SPI_SCLK", "input"),
                         (27, "CONV_SPI_CSB_R", "input")):
    p = U.pin(pin)
    s.wire(p, (XL, p[1]))
    s.hlabel(name, shape, (XL, p[1]), side="left")
gnd(U.pin(29))

# Data out
for name, pin in DATA.items():
    p = U.pin(pin)
    s.wire(p, (p[0] + 5.08, p[1]))
    s.hlabel(name, "output", (p[0] + 5.08, p[1]))

# Supplies: AVDD and DRVDD buses on top, grounds below, DNC flagged
bus = U.pin(AVDD[0])[1] - 5.08
for grp, name in ((AVDD, "+1V8_ADCR_A"), (DRVDD, "+1V8_ADCR_D")):
    for n in grp:
        s.wire(U.pin(n), (U.pin(n)[0], bus))
    s.wire((U.pin(grp[0])[0], bus), (U.pin(grp[-1])[0], bus))
    rail(name, (U.pin(grp[len(grp) // 2])[0], bus))
gbus = U.pin(57)[1] + 5.08
for n in (57, 8, 23, 48):
    s.wire(U.pin(n), (U.pin(n)[0], gbus))
s.wire((U.pin(57)[0], gbus), (U.pin(48)[0], gbus))
gnd((U.pin(8)[0], gbus))
for n in (1, 2, 28, 51, 52, 53, 54, 55, 56):
    s.no_connect(U.pin(n))

# ---------------------------------------------------------------- captions and notes
s.text("U502: single-ended in, 15 dB (AD8352 Fig. 26, Table 7)", (45.72, 144.78))
s.text("U503: differential, 10 dB (AD8352 Table 5)", (152.4, 144.78))
s.text("Input network: AD9484 Fig. 30", (215.9, 71.12))
s.text("To the FPGA: 100 ohm across each pair at the receiver (AD9484 p.16).", (276.86, 172.72))
notes = [
    "ADC_RADAR - how this sheet works",
    "1. The radar IF (120 MHz, AERIS-10) arrives single-ended on IF_RX_B from the routing switch.",
    "2. Two AD8352s give 25 dB, as AERIS-10's two cascaded stages; the first also converts to differential.",
    "3. U501 samples at 400 MSPS (radar) or 500 MSPS (SDR plan): the clock comes from CLOCK, Q0.",
    "4. CONV_SPI_* are 1.8 V signals: AD9484 abs. max DRVDD + 0.2 V. The FPGA must drive them from a 1.8 V bank.",
    "5. Every value on this sheet is justified in _work/sheets/adc_radar_spec.py and docs/ADC_RADAR_SPEC.md.",
]
for i, t in enumerate(notes):
    s.text(t, (25.4, 190.5 + 3.81 * i), size=1.524 if i == 0 else 1.27)

n, w, j = s.write()
print(f"wrote {os.path.relpath(SHEET, ROOT)}: {n} symbols, {w} wire segments, {j} junctions")
