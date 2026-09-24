"""
Draw rev03/ADC_SDR.kicad_sch from coordinates. Connections: adc_sdr_spec.py,
checked by _work/check_sheet.py adc_sdr.

Layout: power rows on top; channel A's chain (U602) upper left, channel B's
(U603) lower left, both running into U601 AD9253 on the right. The AD9253
symbol puts channel A's inputs at the top of its left side and channel B's at
the bottom, with the reference, bias, clock and SPI pins between them, so
channel A's N leg and channel B's P leg run straight in and the other leg of
each jogs outside everything else.

Usage:  py _work/sheets/adc_sdr.py
"""

from kit import Kit
from adc_sdr_spec import PARTS, CH, DATA, AVDD, DRVDD

k = Kit("ADC_SDR", "ADC_SDR - AD9253 SDR ADC, two channels, AD8352 drivers", PARTS, 600,
        "_work/sheets/adc_sdr.py")
s = k.s

# ---------------------------------------------------------------- power rows
ROW = 35.56
k.power_row("+5V0", "FB601", "+5V_IFS", ["C660", "C661", "C662", "C663", "C664"], 25.4, ROW)
k.power_row("+1V8_A", "FB602", "+1V8_ADCS_A", ["C665"] + [f"C{666 + i}" for i in range(7)],
            111.76, ROW)
k.power_row("+1V8_D", "FB603", "+1V8_ADCS_D", ["C673", "C674", "C675"], 228.6, ROW)
s.text("C661/C662 at U602 VCC 8/13, C663/C664 at U603. C666-C672 one per AVDD pin, "
       "C674/C675 one per DRVDD pin.", (25.4, 50.8))

# ---------------------------------------------------------------- the ADC
CXA, CYA = 190.5, 147.32
U = k.part("U601", (CXA, CYA), text_at=(CXA - 7.62, CYA - 2.54))
xa = U.pin(36)[0]
XL = xa - 20.32

# drivers: channel A's VON level with VIN-A, channel B's VOP level with VIN+B
CX = 101.6
drivers = []
for n, (u, lbl, vp, vn, r) in enumerate(CH):
    cy = U.pin(vn)[1] - 11.43 if n == 0 else U.pin(vp)[1] + 21.59
    D = k.ad8352(u, CX, cy, r["rg"], r["rd"], r["cd"], r["vcm"], "+5V_IFS", rn=r["rn"])
    k.se_input(D, lbl, r["term"], r["cin"], r["cvin"], r["rvin"])
    k.adc_input(D, U.pin(vp), U.pin(vn), xa,
                {"cp": r["cp"], "cn": r["cn"], "rp": r["rp"], "rn": r["rl"], "ccm": r["ccm"],
                 "rcm": r["rcm"], "sp": r["sp"], "sn": r["sn"], "csh": r["csh"]},
                "ADCS_VCM", straight="N" if n == 0 else "P")
    drivers.append(D)

# VCM: decoupled at the pin, joined by label to both centre taps and to C/D
vcm = U.pin(43)
s.wire(vcm, (xa - 15.24, vcm[1]))
s.label("ADCS_VCM", (xa - 15.24, vcm[1]), side="left")
c = k.vpart("C643", xa - 10.16, vcm[1])
k.gnd(c.pin(2))
# VREF: 1 uF || 0.1 uF
vref = U.pin(42)
s.wire(vref, (xa - 17.78, vref[1]))
for ref, x in (("C641", xa - 7.62), ("C642", xa - 17.78)):
    c = k.vpart(ref, x, vref[1])
    k.gnd(c.pin(2))
# SENSE to ground: internal 1.0 V reference (Table 9)
sense = U.pin(41)
s.wire(sense, (xa - 2.54, sense[1]))
k.gnd((xa - 2.54, sense[1]))
# RBIAS: 10 kohm 1 %
rb = U.pin(40)
s.wire(rb, (xa - 7.62, rb[1]))
r = k.vpart("R641", xa - 7.62, rb[1])
k.gnd(r.pin(2))
# Clock: 100 ohm across the pair at the receiver
ckp, ckn = U.pin(6), U.pin(5)
rt = k.vpart("R642", xa - 10.16, ckp[1])
s.wire(ckp, (XL, ckp[1]))
s.wire(ckn, (xa - 5.08, ckn[1]), (xa - 5.08, rt.pin(2)[1]), (XL, rt.pin(2)[1]))
s.hlabel("CLK_ADCS_P", "input", (XL, ckp[1]), side="left")
s.hlabel("CLK_ADCS_N", "input", (XL, rt.pin(2)[1]), side="left")
# SPI; PDWN and SYNC low (power-down via SPI; one ADC, nothing to synchronise)
for pin, name, shape in ((31, "CONV_SPI_SDIO", "bidirectional"), (30, "CONV_SPI_SCLK", "input"),
                         (32, "CONV_SPI_CSB_S", "input")):
    p = U.pin(pin)
    s.wire(p, (XL, p[1]))
    s.hlabel(name, shape, (XL, p[1]), side="left")
pd, sy = U.pin(33), U.pin(44)
s.wire(pd, (xa - 2.54, pd[1]), (xa - 2.54, sy[1]), sy)
k.gnd((xa - 2.54, sy[1]))

# Data out; unused lanes flagged
for name, pin in DATA.items():
    p = U.pin(pin)
    s.wire(p, (p[0] + 5.08, p[1]))
    s.hlabel(name, "output", (p[0] + 5.08, p[1]))
for n in (28, 27, 26, 25, 16, 15, 14, 13, 12, 11, 10, 9):
    s.no_connect(U.pin(n))

# Supplies
bus = U.pin(AVDD[0])[1] - 5.08
for grp, name in ((AVDD, "+1V8_ADCS_A"), (DRVDD, "+1V8_ADCS_D")):
    for n in grp:
        s.wire(U.pin(n), (U.pin(n)[0], bus))
    s.wire((U.pin(grp[0])[0], bus), (U.pin(grp[-1])[0], bus))
    k.rail(name, (U.pin(grp[len(grp) // 2])[0], bus))
# Bottom: exposed pad to ground; unused channels C and D tied to VCM
ep = U.pin(49)
s.wire(ep, (ep[0], ep[1] + 5.08))
k.gnd((ep[0], ep[1] + 5.08))
cd = [U.pin(n) for n in (48, 47, 1, 2)]
low = cd[0][1] + 5.08
for p in cd:
    s.wire(p, (p[0], low))
s.wire((cd[0][0], low), (cd[-1][0] + 5.08, low))
s.label("ADCS_VCM", (cd[-1][0] + 5.08, low))

# ---------------------------------------------------------------- captions and notes
s.text("Channel A: U602, single-ended in, 12 dB (AD8352 Fig. 26, Table 7)", (45.72, 133.35))
s.text("Channel B: U603, the same", (45.72, 252.73))
s.text("Channels C, D unused: inputs held at VCM", (205.74, 207.01))
k.notes([
    "ADC_SDR - how this sheet works",
    "1. Two SDR inputs, IF_RX_A and IF_RX_C, single-ended 50 ohm, each through an AD8352 (12 dB).",
    "2. The AD9253 divides the 500 MHz master clock by 8: 62.5 MSPS, one-lane mode (register 0x21, SPI).",
    "3. One-lane: channel A leaves on D0+-B, channel B on D1+-B (AD9253 Table 8, footnote 1).",
    "4. The inputs are not biased inside the AD9253: centre taps go to its VCM pin through 200 ohm (Fig. 58).",
    "5. CONV_SPI_* are 1.8 V signals (abs. max 2.0 V). LVDS terminated at the FPGA, 100 ohm per pair.",
], (228.6, 218.44))
k.write()
