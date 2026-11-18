"""
Shared drawer for the Rev08 sheets generated from a connection table (RX_VU, STATUS): every IC with a short lead
on each pin ending in its net's label, power symbol, ground or no-connect flag; its passives in rows beneath it,
labelled at both ends; filters as ladders with real wires. The connections are the specification's (PINS,
PARTS, HIER, FILTERS of the spec module); this module only decides where things go.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import schgen                                                     # noqa: E402

ROOT = os.path.dirname(os.path.dirname(HERE))
ROOT_UUID = "56c49378-41a8-4cbc-b1f4-3d0ea65d2366"
PROJECT = "CSI2-KRIA-KV260_Rev01"
RAILS = {"+2V8_RF": "power:VCC", "+3V3_D": "power:+3V3", "+5V0": "power:+5V", "+12V": "power:+12V",
         "+1V8_D": "power:+1V8", "+1V0": "power:+1V0", "+3V3_USB": "power:+3V3", "VBUS_USB": "power:VBUS"}
s = S = None
FLAGGED, flagged = set(), set()


def setup(spec, name, title, paper, ref_base, flagged_nets):
    """Start a sheet rev03/<name>.kicad_sch for the spec module. Returns (sheet, path, block uuid)."""
    global s, S, FLAGGED, flagged
    S = spec
    path = os.path.join(ROOT, "rev03", f"{name}.kicad_sch")
    block = schgen.uid("rev08", "sheet", name)
    s = schgen.Sheet(path, schgen.uid("rev08", name, "file"), title, PROJECT, f"/{ROOT_UUID}/{block}", paper=paper,
                     generator=f"_work/sheets/{name.lower()}.py", ref_base=ref_base)
    s.lib("kv260-ias2rf", os.path.join(ROOT, "symbols", "kv260-ias2rf.kicad_sym"))
    FLAGGED, flagged = set(flagged_nets), set()
    return s, path, block


def angles(lib_id):
    """pin number -> library angle (0: pin points right, i.e. it sits on the left side)."""
    body = s._sym(lib_id).body
    return {m.group(2): int(float(m.group(1))) for m in re.finditer(
        r'\(pin \w+ \w+\s*\(at [-\d.]+ [-\d.]+ ([-\d.]+)\).*?\(number "([^"]+)"', body, re.S)}


def place(ref, at, rot=0, text_at=None):
    lib_id, value, fp, _ = S.PARTS[ref]
    return s.place(lib_id, ref, value, at, rot, footprint=fp, text_at=text_at)


OUT = {0: (-1, 0), 180: (1, 0), 90: (0, 1), 270: (0, -1)}         # outward direction on the sheet (y down)


def outward(lib_ang, rot):
    dx, dy = OUT[lib_ang]
    for _ in range((rot // 90) % 4):                                # the part turned 90 deg anticlockwise
        dx, dy = dy, -dx
    return dx, dy


def terminate(net, p, d, lead=2.54):
    """End a pin at p, outward direction d, on its net."""
    if net == "NC":
        s.no_connect(p)
        return
    end = (p[0] + d[0] * lead, p[1] + d[1] * lead)
    s.wire(p, end)
    if net == "GND":
        s.power("power:GND", "GND", end, rot={(0, 1): 0, (-1, 0): 270, (1, 0): 90, (0, -1): 180}[d], hide_value=d[0] != 0)
    elif net in RAILS:
        s.power(RAILS[net], net, end, rot={(0, -1): 0, (-1, 0): 90, (1, 0): 270, (0, 1): 180}[d])
    elif net in S.HIER:
        if d[1]:
            e2 = (end[0] + 2.54, end[1])
            s.wire(end, e2)
            end = e2
        s.hlabel(net, S.HIER[net], end, side="left" if d[0] < 0 else "right")
    else:
        if d[1]:                                                    # vertical lead: turn right for the text
            e2 = (end[0] + 2.54, end[1])
            s.wire(end, e2)
            end = e2
        s.label(net, end, side="left" if d[0] < 0 else "right")
    if net in FLAGGED and net not in flagged:
        flagged.add(net)
        f = (end[0], end[1] - 2.54) if d[1] == 0 else (end[0] + 2.54, end[1] - 2.54)
        s.wire(end, (f[0], end[1]), f)
        s.power("power:PWR_FLAG", "PWR_FLAG", f)


def ic(ref, at):
    """A multi-pin part at `at`, every pin led out. Bottom grounds share one bar and one symbol; reference and
    value go under that."""
    sym = s._sym(S.PARTS[ref][0])
    lx = min(v[0] for v in sym.pins.values())
    ly = max(-v[1] for v in sym.pins.values())
    P = place(ref, at, text_at=(at[0] + lx + 2.54, at[1] + ly + 10.16))
    ang = angles(P.sym.lib_id)
    pins = S.PINS[ref]
    bottom = [n for n in P.pins if outward(ang[n], 0) == (0, 1) and pins[n] == "GND"]
    if len(bottom) > 1:
        ys = max(P.pin(n)[1] for n in bottom) + 2.54
        xs = sorted(P.pin(n)[0] for n in bottom)
        for n in bottom:
            s.wire(P.pin(n), (P.pin(n)[0], ys))
        s.wire((xs[0], ys), (xs[-1], ys))
        s.power("power:GND", "GND", (xs[len(xs) // 2], ys))
    top = {}
    for n in P.pins:
        if outward(ang[n], 0) == (0, -1) and pins[n] in RAILS:
            top.setdefault(pins[n], []).append(n)
    joined = set()
    for net, ns in top.items():
        if len(ns) > 1:
            yt = min(P.pin(n)[1] for n in ns) - 2.54
            xs = sorted(P.pin(n)[0] for n in ns)
            for n in ns:
                s.wire(P.pin(n), (P.pin(n)[0], yt))
            s.wire((xs[0], yt), (xs[-1], yt))
            s.power(RAILS[net], net, (xs[len(xs) // 2], yt))
            joined |= set(ns)
    for side in ((-1, 0), (1, 0)):                                 # side pins on one supply: one bar, one symbol
        groups = {}
        for n in P.pins:
            if outward(ang[n], 0) == side and (pins[n] in RAILS or pins[n] == "GND"):
                groups.setdefault(pins[n], []).append(n)
        for net, ns in groups.items():
            if len(ns) < 2:
                continue
            xb = P.pin(ns[0])[0] + side[0] * 5.08
            ys = sorted(P.pin(n)[1] for n in ns)
            for n in ns:
                s.wire(P.pin(n), (xb, P.pin(n)[1]))
            if net == "GND":
                s.wire((xb, ys[0]), (xb, ys[-1] + 2.54))
                s.power("power:GND", "GND", (xb, ys[-1] + 2.54))
            else:
                s.wire((xb, ys[-1]), (xb, ys[0] - 2.54))
                s.power(RAILS[net], net, (xb, ys[0] - 2.54))
            joined |= set(ns)
    for n in P.pins:
        if (n in bottom and len(bottom) > 1) or n in joined:
            continue
        terminate(pins[n], P.pin(n), outward(ang[n], 0))
    return P


def extent(ref):
    """(width left of origin, right of origin, above, below) of a part with its leads and labels."""
    lib_id = S.PARTS[ref][0]
    sym = s._sym(lib_id)
    xs = [v[0] for v in sym.pins.values()]
    ys = [-v[1] for v in sym.pins.values()]
    lab = 22.0
    return (-min(xs) + lab, max(xs) + lab, -min(ys) + 8, max(ys) + 24)


def two(ref, x, y):
    """A two-pin part standing at (x, y top): the rail or the signal on top, ground at the bottom."""
    n1, n2 = S.PINS[ref]["1"], S.PINS[ref]["2"]
    flip = n1 == "GND" or (n2 in RAILS and n1 not in RAILS)
    top, bot = ("2", "1") if flip else ("1", "2")
    sym = s._sym(S.PARTS[ref][0])
    for rot in (0, 90, 180, 270):                     # the turn that stands `top` straight above `bot`
        q = schgen.Part(s, sym, ref, "", (0, 0), rot)
        (xt, yt), (xb, yb) = q.pin(top), q.pin(bot)
        if xt == xb and yt < yb:
            break
    P = place(ref, (x, y - yt), rot, text_at=(x + 3.81, y + 2.54) if rot in (90, 270) else None)
    terminate(S.PINS[ref][top], P.pin(top), (0, -1))
    terminate(S.PINS[ref][bot], P.pin(bot), (0, 1))
    return P


SLOT = 22.86
X0, X1, Y0 = 30.48, 815.0, 45.72


def group_size(ics, passives):
    w = sum(extent(r)[0] + extent(r)[1] for r in ics) + 5.08 * (len(ics) - 1)
    w = max(w, min(len(passives), 6) * SLOT)
    rows = (len(passives) + int(w // SLOT) - 1) // max(1, int(w // SLOT)) if passives else 0
    h = max(extent(r)[2] + extent(r)[3] for r in ics) + rows * 25.4
    return w, h, max(1, int(w // SLOT))


def layout(groups, x1=815.0):
    """Place the groups left to right in rows; returns the y where the next thing can go."""
    x, y, row_h = X0, Y0, 0.0
    for ics, passives in groups:
        w, h, per_row = group_size(ics, passives)
        if x + w > x1:
            x, y, row_h = X0, y + row_h + 7.62, 0.0
        cx = x
        top = y
        for r in ics:
            e = extent(r)
            at = (schgen.snap(cx + e[0]), schgen.snap(top + e[2]))
            ic(r, at)
            cx += e[0] + e[1] + 5.08
        base = top + max(extent(r)[2] + extent(r)[3] for r in ics)
        for k, r in enumerate(passives):
            two(r, schgen.snap(x + 7.62 + (k % per_row) * SLOT), schgen.snap(base + (k // per_row) * 25.4))
        row_h = max(row_h, h)
        x += w + 12.7
    y_ladders = y + row_h + 10.16
    return y_ladders


# ---------------------------------------------------------------- the filters as ladders
def ladder(name, y, x0=X0):
    fin, fout, title, elems = S.FILTERS[name]
    x = x0 + 20.32
    s.text(title, (x0, y - 17.78))
    s.label(fin, (x, y), side="left")
    node = x
    for e in elems:
        kind = e[0]
        if kind == "sC":
            P = place(e[1], (node, y + 3.81))
            terminate("GND", P.pin("2"), (0, 1))
            node_next = node
        elif kind == "sLC":
            P = place(e[1], (node, y + 3.81))
            Q = place(e[3], (node, y + 11.43))
            terminate("GND", Q.pin("2"), (0, 1))
            node_next = node
        elif kind == "pLC":
            P = place(e[1], (node, y + 3.81))
            Q = place(e[3], (node + 12.7, y + 3.81))
            s.wire((node, y), (node + 12.7, y))
            terminate("GND", P.pin("2"), (0, 1))
            terminate("GND", Q.pin("2"), (0, 1))
            node_next = node + 12.7
        if kind in ("sC", "sLC", "pLC"):
            node = node_next + 10.16
            s.wire((node_next, y), (node, y))
            continue
        if kind == "C":
            P = place(e[1], (node + 7.62, y), 90)
            s.wire((node, y), P.pin("1"))
            nxt = node + 15.24
            s.wire(P.pin("2"), (nxt, y))
        elif kind == "LpC":
            P = place(e[1], (node + 7.62, y), 90)
            Q = place(e[3], (node + 7.62, y - 10.16), 90)
            s.wire((node, y), P.pin("1"))
            nxt = node + 15.24
            s.wire(P.pin("2"), (nxt, y))
            s.wire(Q.pin("1"), (Q.pin("1")[0], y))
            s.wire(Q.pin("2"), (Q.pin("2")[0], y))
        elif kind == "LsC":
            P = place(e[1], (node + 7.62, y), 90)
            Q = place(e[3], (node + 20.32, y), 90)
            s.wire((node, y), P.pin("1"))
            s.wire(P.pin("2"), Q.pin("1"))
            nxt = node + 27.94
            s.wire(Q.pin("2"), (nxt, y))
        node = nxt + 5.08
        s.wire((nxt, y), (node, y))
    s.label(fout, (node, y))
    return node


