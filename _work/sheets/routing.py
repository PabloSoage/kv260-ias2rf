"""
Draw rev03/ROUTING.kicad_sch from coordinates. Connections: routing_spec.py,
checked by _work/check_sheet.py routing.

Four identical switch blocks in a 2 x 2 grid; the two unswitched SDR
channels on the right. In each block: the converter port and the control
come in from the left, the two SMAs leave on the right, the VDD network
stacks upward from the switch and the VEE network downward, each part of
them hanging to the side with its own ground.

Usage:  py _work/sheets/routing.py
"""

from kit import Kit
from routing_spec import PARTS, SWITCHES, DIRECT, REFS

k = Kit("ROUTING", "ROUTING - 4 x M3SWA2 SPDT channel routing, IF SMAs", PARTS, 900,
        "_work/sheets/routing.py")
s = k.s


def left_part(ref, xcol, y):
    """Horizontal part to the LEFT of a column at xcol: pin 1 at the outer
    (left) end, pin 2 on the column."""
    return k.hpart(ref, xcol - 3.81, y)


def right_part(ref, xcol, y):
    """Horizontal part to the RIGHT of a column: pin 1 on the column."""
    return k.hpart(ref, xcol + 3.81, y)


def block(n, lbl, shape, cx, cy):
    r = REFS[n]
    U = k.part(r["u"], (cx, cy), text_at=(cx - 5.08, cy - 1.27))
    # ---- VDD: 100 pF left, 0.1 uF right, zener, then 11.5 ohm up to the rail
    vdd = U.pin(8)
    y1, y2 = cy - 19.05, cy - 31.75
    s.wire(vdd, (vdd[0], y2))
    s.power("power:PWR_FLAG", "PWR_FLAG", (vdd[0], cy - 25.4))   # fed through R: flag it
    c = right_part(r["c_vdd1"], vdd[0], y1)
    k.gnd_lead(c.pin(2))
    c = k.part(r["c_vdd2"], (vdd[0] - 3.81, y1), rot=270)     # pin 1 on the column
    k.gnd_lead(c.pin(2), dx=-5.08)
    d = k.part(r["d_vdd"], (vdd[0] + 3.81, y2))               # K on the column
    k.gnd_lead(d.pin(2))
    s.wire((vdd[0], y2), (vdd[0], y2 - 5.08))                  # room for the zener's text
    rr = k.vpart(r["r_vdd"], vdd[0], y2 - 12.7)               # pin 2 on the column
    k.rail("+3V3_D", rr.pin(1))
    # ---- VEE: 0.1 uF, 100 pF, zener to the left, then 11.5 ohm down to the rail
    vee = U.pin(5)
    z1, z2, z3 = cy + 19.05, cy + 31.75, cy + 44.45
    s.wire(vee, (vee[0], z3))
    s.power("power:PWR_FLAG", "PWR_FLAG", (vee[0], cy + 25.4))
    c = left_part(r["c_vee1"], vee[0], z1)
    k.gnd_lead(c.pin(1), dx=-5.08)
    c = left_part(r["c_vee2"], vee[0], z2)
    k.gnd_lead(c.pin(1), dx=-5.08)
    d = k.part(r["d_vee"], (vee[0] - 3.81, z3))               # A on the column, K out
    k.gnd_lead(d.pin(1), dx=-5.08)
    s.wire((vee[0], z3), (vee[0], z3 + 5.08))                  # room for the zener's text
    rv = k.vpart(r["r_vee"], vee[0], z3 + 5.08)
    k.rail("-3V3", rv.pin(2))
    # ---- grounds and NC pads onto one bus
    gp = [2, 4, 7, 9, 11, 14, 16, 17, 1, 12, 13]
    gb = U.pin(2)[1] + 5.08
    for p in gp:
        s.wire(U.pin(p), (U.pin(p)[0], gb))
    s.wire((U.pin(2)[0], gb), (U.pin(13)[0], gb))
    k.gnd((cx, gb))
    # ---- converter port and control
    xl = cx - 41.91
    rfc = U.pin(15)
    s.wire(rfc, (xl, rfc[1]))
    s.hlabel(lbl, shape, (xl, rfc[1]), side="left")
    ctl = U.pin(6)
    rc = k.hpart(r["r_ctl"], ctl[0] - 6.35, ctl[1])
    s.wire(rc.pin(2), ctl)
    s.wire(rc.pin(1), (xl, ctl[1]))
    pd = k.vpart(r["r_pd"], cx - 36.83, ctl[1])
    k.gnd(pd.pin(2))
    s.hlabel(f"SW_CTRL{n - 1}", "input", (xl, ctl[1]), side="left")
    # ---- the two throws: DC block, SMA
    for pin, cref, jref in ((3, r["c_rf1"], r["j1"]), (10, r["c_rf2"], r["j2"])):
        p = U.pin(pin)
        c = k.hpart(cref, p[0] + 6.35, p[1])
        s.wire(p, c.pin(1))
        jx = c.pin(2)[0] + 5.08
        j = k.part(jref, (jx, p[1]), text_at=(jx + 3.81, p[1] - 3.81))
        k.gnd(j.pin(2))
    s.text(f"SW{n}: {lbl}. RF1 when SW_CTRL{n - 1} is low (default), RF2 when high.",
           (cx - 43.18, cy - 53.34))


for (n, lbl, shape, _, _), (cx, cy) in zip(SWITCHES, ((83.82, 78.74), (223.52, 78.74),
                                                     (83.82, 201.93), (223.52, 201.93))):
    block(n, lbl, shape, cx, cy)

# ---- second SDR channels, not switched
for kk, lbl, shape, name in DIRECT:
    y = 71.12 + 20.32 * kk
    c = k.hpart(f"C95{kk}", 317.5, y)
    s.wire((304.8, y), c.pin(1))
    s.hlabel(lbl, shape, (304.8, y), side="left")
    jx = c.pin(2)[0] + 5.08
    j = k.part(f"J95{kk}", (jx, y), text_at=(jx + 3.81, y - 3.81))
    k.gnd(j.pin(2))
s.text("Second SDR channels: straight to their SMAs, DC-blocked.", (289.56, 81.28))

k.notes([
    "ROUTING - how this sheet works",
    "1. Each SPDT connects a converter to its own chain (RF1, default)",
    "   or to the other one (RF2), under SW_CTRL0..3 from the FPGA.",
    "2. Supply and control networks: M3SWA2 datasheet Figure 2, per switch.",
    "3. Every SMA is DC-blocked: 'All RF-ports must be DC blocked or held at 0 V DC'.",
    "4. The switches need VDD +3.3 V and VEE -3.3 V (B-03).",
    "5. Values and sources: _work/sheets/routing_spec.py, docs/ROUTING_SPEC.md.",
], (289.56, 139.7))
k.write()
