"""
Draw rev03/IAS_LINK.kicad_sch from coordinates. Connections: ias_link_spec.py,
checked by _work/check_sheet.py ias_link.

The Hirose connector splits every pair across its two rows of pins, so it is
drawn with a label on each pin; the coupling capacitors and terminations sit
in an orderly block to the right, one row per line, joined to the connector
by those labels. Grounds on the connector are drawn as sideways ground
symbols at the pins.

Usage:  py _work/sheets/ias_link.py
"""

from kit import Kit
from ias_link_spec import PARTS, PAIRS, SINGLE, GND_PINS, NC_PINS, REFS

k = Kit("IAS_LINK", "IAS_LINK - Hirose IAS1 link to the Kria, AC coupling, terminations",
        PARTS, 100, "_work/sheets/ias_link.py")
s = k.s


def side_gnd(pin, left):
    k.s.power("power:GND", "GND", pin, rot=270 if left else 90, hide_value=True)


def connector(ref, cx, cy, signals=True):
    J = k.part(ref, (cx, cy), text_at=(cx - 2.54, cy - 25.4))
    by_pin = {}
    if signals:
        for name, (pp, pn, _) in PAIRS.items():
            by_pin[pp], by_pin[pn] = (f"J_{name}_P", None), (f"J_{name}_N", None)
        for name, (pin, shape) in SINGLE.items():
            by_pin[pin] = (name, shape)
    for pin in range(1, 35):
        p = J.pin(pin)
        left = pin % 2 == 1
        if pin in GND_PINS:
            side_gnd(p, left)
        elif pin in by_pin:
            name, shape = by_pin[pin]
            end = (p[0] - 5.08, p[1]) if left else (p[0] + 5.08, p[1])
            s.wire(p, end)
            if shape:
                s.hlabel(name, shape, end, side="left" if left else "right")
            else:
                s.label(name, end, side="left" if left else "right")
        else:
            s.no_connect(p)
    return J


connector("J101", 66.04, 110.49)
connector("J102", 66.04, 205.74, signals=False)
s.text("J101: IAS1 (KV260 J8), the link. Pins per INTERFACE_SPEC §2-4.", (38.1, 80.01))
s.text("J102: IAS0 (KV260 J7), mechanical only: grounds, nothing else.", (38.1, 175.26))

# ---------------------------------------------------------------- coupling and terminations
XH, XT, XC, XL = 160.02, 180.34, 215.9, 226.06
y = 55.88
for name, (pp, pn, to_kria) in PAIRS.items():
    r = REFS[name]
    yn = y + (10.16 if to_kria else 15.24)
    for leg, yy, cref in (("P", y, r["cp"]), ("N", yn, r["cn"])):
        c = k.hpart(cref, XC, yy)
        s.wire((XH, yy), c.pin(1))
        s.hlabel(f"{name}_{leg}", "input" if to_kria else "output", (XH, yy), side="left")
        s.wire(c.pin(2), (XL, yy))
        s.label(f"J_{name}_{leg}", (XL, yy))
    if not to_kria:
        rp = k.vpart(r["rp"], XT, y)
        rn = k.vpart(r["rn"], XT, yn - 7.62)
        cm = rp.pin(2)
        s.wire(cm, (XT - 2.54, cm[1]))
        k.s.power("power:+1V2", "+1V2", (XT - 2.54, cm[1]), rot=90)
        s.wire(cm, (XT + 12.7, cm[1]))                    # clear of the resistors' text
        cc = k.hpart(r["cc"], XT + 16.51, cm[1])
        k.gnd_lead(cc.pin(2))
    s.text(f"{name}: {'FPGA -> Kria' if to_kria else 'Kria -> FPGA, terminated here'}",
           (XH, y - 5.08))
    y = yn + 12.7

k.notes([
    "IAS_LINK - how this sheet works",
    "1. Five LVDS pairs to the Kria's HPA bank at 1.2 V: every pair AC-coupled (INTERFACE_SPEC 6.1).",
    "2. Kria -> FPGA pairs: 2 x 49.9 ohm to +1V2 terminate and re-bias them for the FPGA.",
    "3. FPGA -> Kria pairs: terminated and biased inside the SOM (DIFF_TERM_ADV, DQS_BIAS).",
    "4. Pins 26/27 and 29/30 are N before P on the connector and on the carrier alike (3.2).",
    "5. HK_SCL/SDA, FPGA_PROG_B, FPGA_IRQ are the carrier's 1.8 V levels: CONTROL translates.",
], (152.4, 205.74))
k.write()
