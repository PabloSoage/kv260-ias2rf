#!/usr/bin/env python3
"""
Rev08 phase 5: the schematic's new parts onto the board (text edit; pcbnew is not used, see the repository notes).

What it does to a copy of the Rev07 board (the input is never written over):
  1. exports the schematic's netlist with kicad-cli and takes every pad's net from it, for the new parts and for
     the old ones whose nets changed in phase 4 (J102's IAS0 contacts; PMOD_SPARE1/2, which are now root nets
     and lose their /CONTROL/ prefix, renamed on every track, via and zone that carries them too);
  2. marks C926 DNP (the board is built for the front end, REV08_PLAN 5.7);
  3. moves J1002 (the fan header, through-hole) and two fiducials out of the way, as the placement trial found;
  4. places the new footprints from their libraries at the positions of rev08_place.py, top or bottom, with the
     schematic's path, sheet name and file, so that KiCad's schematic parity holds;
  5. adds the shield-can frames (board-only footprints, ground ring) and the ground and supply vias that the
     placement table asks for.
Routing is a separate step.

Usage:  py _work/rev08_pcb.py <in.kicad_pcb> <out.kicad_pcb>
"""
import math
import os
import re
import subprocess
import sys
import tempfile
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from toolpaths import KICAD_CLI, stock_footprints          # noqa: E402
import rev08_place as SPEC                                  # noqa: E402

OURS = os.path.join(ROOT, "footprints", "kv260-ias2rf.pretty")
Y_J961 = 121.3
U = lambda: str(uuid.uuid4())
STR = r'"((?:[^"\\]|\\.)*)"'


# ---------------------------------------------------------------- s-expression helpers
def block_end(t, s):
    d, i, n = 0, s, len(t)
    while i < n:
        c = t[i]
        if c == '"':
            i += 1
            while t[i] != '"':
                i += 2 if t[i] == '\\' else 1
        elif c == '(':
            d += 1
        elif c == ')':
            d -= 1
            if d == 0:
                return i + 1
        i += 1
    raise ValueError("unbalanced")


def map_blocks(t, opener, fn):
    """Replace every block that starts with `opener` (a regex) by fn(block)."""
    out, pos = [], 0
    for m in re.finditer(opener, t):
        if m.start() < pos:
            continue
        e = block_end(t, m.start())
        out += [t[pos:m.start()], fn(t[m.start():e])]
        pos = e
    out.append(t[pos:])
    return "".join(out)


def footprints(t):
    out = []
    for m in re.finditer(r'\n\t\(footprint "', t):
        s = m.start() + 1
        e = block_end(t, s)
        out.append((s, e, re.search(r'\(property "Reference" "([^"]+)"', t[s:e]).group(1)))
    return out


# ---------------------------------------------------------------- netlist
def netlist():
    sch = os.path.join(ROOT, "CSI2-KRIA-KV260_Rev01.kicad_sch")
    out = os.path.join(tempfile.mkdtemp(), "rev08.net")
    subprocess.run([KICAD_CLI, "sch", "export", "netlist", "--format", "kicadsexpr", "-o", out, sch],
                   check=True, capture_output=True)
    t = open(out, encoding="utf-8").read()
    comps = {}
    cs, ce = t.find("(components"), t.find("\n\t(libparts")
    for blk in re.split(r"\n\t\t\(comp\b", t[cs:ce])[1:]:
        ref = re.search(r'\(ref "([^"]+)"\)', blk).group(1)
        val = re.search(r'\(value ' + STR + r'\)', blk).group(1)
        fp = re.search(r'\n\t\t\t\(footprint "([^"]*)"\)', blk)
        sp = re.search(r'\(sheetpath\s*\(names "([^"]*)"\)\s*\(tstamps "([^"]*)"\)\s*\)\s*\(tstamps "([^"]*)"\)', blk)
        sf = re.search(r'\(name "Sheetfile"\)\s*\(value "([^"]*)"\)', blk)
        comps[ref] = dict(value=val, footprint=fp.group(1) if fp else "", sheet=sp.group(1) if sp else "",
                          path=(sp.group(2) + sp.group(3)) if sp else "", sheetfile=sf.group(1) if sf else "",
                          dnp='(name "dnp")' in blk)
    pins = {}
    for m in re.finditer(r'\(net\s*\(code "?\d+"?\)\s*\(name ' + STR + r'\)(.*?)\n\t\t\)', t[t.find("\n\t(nets"):], re.S):
        for n in re.finditer(r'\(ref "([^"]+)"\)\s*\(pin "([^"]+)"\)', m.group(2)):
            pins.setdefault(n.group(1), {})[n.group(2)] = m.group(1)
    return comps, pins


# ---------------------------------------------------------------- footprints from libraries
def lib_text(lib_id):
    lib, name = lib_id.split(":", 1)
    d = OURS if lib == "kv260-ias2rf" else os.path.join(stock_footprints(), lib + ".pretty")
    return open(os.path.join(d, name + ".kicad_mod"), encoding="utf-8").read()


def from_board(t, ref):
    """A footprint copied from the board (the SMA: the Rev07 launch, already simulated), back to local frame."""
    for s, e, r in footprints(t):
        if r == ref:
            f = t[s:e]
            break
    at = re.search(r'\n\t\t\(at ([-\d.]+) ([-\d.]+)(?: ([-\d.]+))?\)', f)
    r0 = float(at.group(3) or 0)
    f = f[:at.start()] + f[at.end():]

    def unrot(m):
        ang = (float(m.group(4)) if m.group(4) else 0.0) - r0
        return f'{m.group(1)}(at {m.group(2)} {m.group(3)} {ang:g})'
    f = re.sub(r'(\(pad "[^"]*" \w+ \w+\s*\n\s*)\(at ([-\d.]+) ([-\d.]+)(?: ([-\d.]+))?\)', unrot, f)
    f = re.sub(r'(\((?:property "[^"]+" "[^"]*"|fp_text \w+ "[^"]*")\s*\n\s*)\(at ([-\d.]+) ([-\d.]+)(?: ([-\d.]+))?\)',
               unrot, f)
    f = re.sub(r'\n\t\t\t\(net "[^"]*"\)', "", f)
    f = re.sub(r'\n\t\t\(path "[^"]*"\)\n\t\t\(sheetname "[^"]*"\)\n\t\t\(sheetfile "[^"]*"\)', "", f)
    return "\n".join(line[1:] if line.startswith("\t") else line for line in f.split("\n"))


def place(text, lib_id, ref, comp, nets, x, y, a, bottom):
    """Library text -> a board footprint block (one tab deeper), placed, with nets and the schematic path."""
    t = text
    for k in ("version", "generator", "generator_version"):
        t = re.sub(r'\n\t\(' + k + r' [^\n]*\)', '', t)
    t = re.sub(r'^\(footprint "[^"]*"', f'(footprint "{lib_id}"', t)
    head = f'\n\t(layer "F.Cu")\n\t(uuid "{U()}")\n\t(at {x:g} {y:g}{" " + format(a, "g") if a else ""})'
    t = re.sub(r'\n\t\(layer "F\.Cu"\)', head, t, count=1)
    t = re.sub(r'\(property "Reference" "[^"]*"', f'(property "Reference" "{ref}"', t, count=1)
    # the new blocks are dense: their references go on the assembly (Fab) drawing only, as most passives do
    t = re.sub(r'(\(property "Reference" "[^"]*"\s*\(at [^)]*\)\s*\(layer "[^"]+"\))(?!\s*\(hide yes\))',
               r'
		(hide yes)', t, count=1)
    t = re.sub(r'\(property "Value" "[^"]*"', f'(property "Value" "{comp["value"]}"', t, count=1)
    t = re.sub(r'\(uuid "[^"]+"\)', lambda m: f'(uuid "{U()}")', t)
    if "\n\t(path " not in t:
        t = re.sub(r'\n\t\(attr ', f'\n\t(path "{comp["path"]}")\n\t(sheetname "{comp["sheet"]}")\n'
                   f'\t(sheetfile "{comp["sheetfile"]}")\n\t(attr ', t, count=1)
    if comp.get("dnp"):
        t = re.sub(r'\n\t\(attr (\w+)\)', r'\n\t(attr \1 dnp)', t, count=1)
    sgn = -1 if bottom else 1

    def pad(blk):
        m = re.match(r'\(pad "([^"]*)" (\w+) (\w+)', blk)
        num, kind, shape, body = m.group(1), m.group(2), m.group(3), blk[m.end():-1]

        def at(q):
            px, py, pa = float(q.group(1)), float(q.group(2)), float(q.group(3) or 0)
            return f"(at {px:g} {sgn * py:g} {(sgn * pa + a) % 360:g})"
        body = re.sub(r'\(at ([-\d.]+) ([-\d.]+)(?: ([-\d.]+))?\)', at, body, count=1)
        body = re.sub(r'\n\t\t\(net [^\n]*\)', '', body)
        if kind != "np_thru_hole" and num:
            net = nets.get(num)
            if net is None:
                raise SystemExit(f"{ref}: pad {num} has no pin in the schematic")
            if "\n\t\t(uuid " in body:
                body = re.sub(r'(\n\t\t\(uuid )', f'\n\t\t(net "{net}")\\1', body, count=1)
            else:
                body = body.rstrip() + f'\n\t\t(net "{net}")\n\t\t(uuid "{U()}")\n\t'
        elif "\n\t\t(uuid " not in body:
            body = body.rstrip() + f'\n\t\t(uuid "{U()}")\n\t'
        return f'(pad "{num}" {kind} {shape}{body})'
    t = map_blocks(t, r'\(pad "', pad)

    def txt(m):
        px, py, pa = float(m.group(2)), float(m.group(3)), float(m.group(4) or 0)
        return f'{m.group(1)}(at {px:g} {sgn * py:g} {(pa + a) % 360:g})'
    t = re.sub(r'(\((?:property "[^"]+" "[^"]*"|fp_text \w+ "[^"]*")\s*\n\s*)\(at ([-\d.]+) ([-\d.]+)(?: ([-\d.]+))?\)',
               txt, t)
    if bottom:
        for k in ("start", "end", "mid", "center", "xy"):
            t = re.sub(r'\(' + k + r' ([-\d.]+) ([-\d.]+)\)', lambda m: f'({k} {m.group(1)} {-float(m.group(2)):g})', t)
        t = re.sub(r'"F\.(Cu|SilkS|Fab|CrtYd|Mask|Paste|Adhes)"', r'"B.\1"', t)
        t = re.sub(r'(\(effects\s*\(font(?:[^()]|\([^()]*\))*\))', r'\1\n\t\t\t(justify mirror)', t)
    lines = t.rstrip().split("\n")
    return "\t" + "\n\t".join(lines) + "\n"


# ---------------------------------------------------------------- the board
def main(src, dst):
    t = open(src, encoding="utf-8").read()
    comps, pins = netlist()
    have = {r for _, _, r in footprints(t)}
    # 1. renamed nets, everywhere
    for old, new in SPEC.RENAME.items():
        t = t.replace(f'"{old}"', f'"{new}"')
    # 1b. pad nets of the old parts from the netlist
    changed = 0
    for s, e, ref in reversed(footprints(t)):
        if ref not in comps:
            continue
        f = t[s:e]
        want = pins.get(ref, {})

        def fix(blk):
            nonlocal changed
            m = re.match(r'\(pad "([^"]*)"', blk)
            num, body = m.group(1), blk[m.end():]
            if not num or num not in want:
                return blk
            cur = re.search(r'\n\t\t\t\(net "((?:[^"\\]|\\.)*)"\)', body)
            if cur and cur.group(1) == want[num]:
                return blk
            changed += 1
            if cur:
                body = body[:cur.start()] + f'\n\t\t\t(net "{want[num]}")' + body[cur.end():]
            else:
                body = body.replace("\n\t\t\t(uuid", f'\n\t\t\t(net "{want[num]}")\n\t\t\t(uuid', 1)
            return f'(pad "{num}"{body}'
        f = map_blocks(f, r'\(pad "', fix)
        if comps[ref]["dnp"] and " dnp)" not in f:
            f = re.sub(r'\n\t\t\(attr (\w+)\)', r'\n\t\t(attr \1 dnp)', f, count=1)
        t = t[:s] + f + t[e:]
    # 3. moved parts
    for ref, (x, y, a) in SPEC.MOVE.items():
        for s, e, r in footprints(t):
            if r == ref:
                f = re.sub(r'\n\t\t\(at [-\d. ]+\)', f'\n\t\t(at {x:g} {y:g}{" " + format(a, "g") if a else ""})', t[s:e],
                           count=1)
                t = t[:s] + f + t[e:]
                break
    for r in SPEC.RIP:
        t = rip(t, *r)
    # 4. new parts
    new = [r for r in comps if r not in have]
    missing = [r for r in new if r not in SPEC.PLACE and r not in {n[0] for n in SPEC.NEAR}]
    if missing:
        print("not placed yet:", " ".join(sorted(missing)))
    blocks = []
    for ref in new:
        if ref not in SPEC.PLACE:
            continue
        x, y, a, side = SPEC.PLACE[ref]
        lib_id = comps[ref]["footprint"]
        text = from_board(t, SPEC.TEMPLATE[ref]) if ref in SPEC.TEMPLATE else lib_text(lib_id)
        blocks.append(place(text, lib_id, ref, comps[ref], pins.get(ref, {}), x, y, a, side == "B"))
    blocks += SPEC.extra_items()
    # J961's launch keeps J922's: L2-L6 clear under the signal pad (the same footprint, turned)
    zones = []
    for m in re.finditer(r'\n\t\(zone\n', t):
        z = t[m.start() + 1:block_end(t, m.start() + 1)]
        if '(name "J922 launch' not in z:
            continue
        z = z.replace("J922 launch", "J961 launch")
        z = re.sub(r'\(uuid "[^"]+"\)', lambda q: f'(uuid "{U()}")', z)

        def mv(q):
            px, py = float(q.group(2)) - 212.65, 177.5 - float(q.group(1))   # J922 at (177.5, 212.65), -90
            return f"(xy {91.1 - px:g} {Y_J961 - py:g})"                      # J961 at (91.1, 121.3), 180
        zones.append("\t" + re.sub(r'\(xy ([-\d.]+) ([-\d.]+)\)', mv, z) + "\n")
    s = t.rfind("\n\t(embedded_fonts")
    s = s if s > 0 else t.rfind("\n)")
    t = t[:s] + "\n" + "".join(zones).rstrip("\n") + t[s:]
    s = max(e for _, e, _ in footprints(t))
    t = t[:s] + "\n" + "".join(blocks).rstrip("\n") + t[s:]
    # 4a. escapes: a stub and a via on pins the router would wall in
    esc = []
    for (ref, n), dx, dy in getattr(SPEC, "ESCAPES", []):
        net = pins[ref][n]
        x, y = SPEC.pin(ref, n)
        x2, y2 = round(x + dx, 4), round(y + dy, 4)
        cu = "B.Cu" if SPEC.PLACE[ref][3] == "B" else "F.Cu"
        esc.append(f'\t(segment\n\t\t(start {x:g} {y:g})\n\t\t(end {x2:g} {y2:g})\n\t\t(width 0.12)\n'
                   f'\t\t(layer "{cu}")\n\t\t(net "{net}")\n\t\t(uuid "{U()}")\n\t)\n')
        esc.append(f'\t(via\n\t\t(at {x2:g} {y2:g})\n\t\t(size 0.45)\n\t\t(drill 0.2)\n'
                   f'\t\t(layers "F.Cu" "B.Cu")\n\t\t(net "{net}")\n\t\t(uuid "{U()}")\n\t)\n')
    # 4a'. J103 over J102: a via per contact, J103's pad to it on the top, J102's on the bottom
    def seg(a, b, w, layer, net):
        return (f'\t(segment\n\t\t(start {a[0]:g} {a[1]:g})\n\t\t(end {b[0]:g} {b[1]:g})\n\t\t(width {w:g})\n'
                f'\t\t(layer "{layer}")\n\t\t(net "{net}")\n\t\t(uuid "{U()}")\n\t)\n')

    def via(p, net):
        return (f'\t(via\n\t\t(at {p[0]:g} {p[1]:g})\n\t\t(size 0.45)\n\t\t(drill 0.2)\n'
                f'\t\t(layers "F.Cu" "B.Cu")\n\t\t(net "{net}")\n\t\t(uuid "{U()}")\n\t)\n')
    if getattr(SPEC, "PASS", None):
        j102 = [f for s0, e0, r in footprints(t) if r == "J102" for f in [t[s0:e0]]][0]
        at = re.search(r'\n\t\t\(at ([-\d.]+) ([-\d.]+)(?: ([-\d.]+))?\)', j102)
        X, Y, A = float(at.group(1)), float(at.group(2)), float(at.group(3) or 0)
        ppos = {}
        for m in re.finditer(r'\(pad "(\d+)" \w+ \w+\s*\(at ([-\d.]+) ([-\d.]+)', j102):
            dx, dy = _rot(float(m.group(2)), float(m.group(3)), A)
            ppos[m.group(1)] = (round(X + dx, 4), round(Y + dy, 4))
        cy = SPEC.PLACE["J103"][1]
        for n, r in SPEC.PASS:
            net = pins["J103"][str(n)]
            top = SPEC.pin("J103", str(n))
            bot = ppos[str(n)]
            assert abs(top[0] - bot[0]) < 0.01 and (top[1] - cy) * (bot[1] - cy) > 0, (n, top, bot)
            v = (top[0], round(cy + (r if top[1] > cy else -r), 4))
            esc += [seg(top, v, 0.1, "F.Cu", net), seg(bot, v, 0.1, "B.Cu", net), via(v, net)]
    if esc:
        s = t.rfind("\n\t(embedded_fonts")
        t = t[:s] + "\n" + "".join(esc).rstrip("\n") + t[s:]
    # 4b. the small parts, next to the pin they serve
    anchors = []
    for ref, kind, anc, side in SPEC.NEAR:
        aref, apin = anc[0], (anc[1:] if anc[0] == "@" else anc[1])
        if ref in have:
            continue
        anchors.append((ref, comps[ref]["footprint"], (apin if aref == "@" else SPEC.pin(aref, apin)), side,
                        lambda b, side=side: SPEC.allowed(side, b)))
    packed = pack(t, comps, pins, anchors)
    s = max(e for _, e, _ in footprints(t))
    t = t[:s] + "\n" + "".join(packed).rstrip("\n") + t[s:]
    blocks += packed
    open(dst, "w", encoding="utf-8", newline="\n").write(t)
    print(f"{len(blocks)} items added, {changed} pad nets changed on old parts -> {dst}")


# ---------------------------------------------------------------- packing the small parts near their pin
def _rot(px, py, a):
    r = math.radians(a)
    return px * math.cos(r) + py * math.sin(r), -px * math.sin(r) + py * math.cos(r)


def fp_boxes(f):
    """(side, [boxes]) of a placed footprint block: its pads grown by the clearance, and its courtyard."""
    lay = re.search(r'\n\t\t\(layer "([FB])\.Cu"\)', f).group(1)
    at = re.search(r'\n\t\t\(at ([-\d.]+) ([-\d.]+)(?: ([-\d.]+))?\)', f)
    X, Y, A = float(at.group(1)), float(at.group(2)), float(at.group(3) or 0)
    out = {"F": [], "B": []}
    for m in re.finditer(r'\(pad "[^"]*" (\w+) \w+\s*\(at ([-\d.]+) ([-\d.]+)(?: ([-\d.]+))?\)\s*\(size ([\d.]+) ([\d.]+)\)'
                         r'(?:\s*\(drill[^)]*\))?\s*\(layers ([^)]*)\)', f):
        kind, px, py, pa, w, h, layers = m.groups()
        dx, dy = _rot(float(px), float(py), A)
        ang = float(pa or 0) % 180
        w, h = float(w), float(h)
        if abs(ang - 90) < 1:
            w, h = h, w
        elif ang > 1:
            w = h = max(w, h)
        c = 0.15
        bx = (X + dx - w / 2 - c, Y + dy - h / 2 - c, X + dx + w / 2 + c, Y + dy + h / 2 + c)
        for s in "FB":
            if f'"{s}.Cu"' in layers or '"*.Cu"' in layers or kind in ("thru_hole", "np_thru_hole"):
                out[s].append(bx)
    pts = []
    for m in re.finditer(r'\((?:fp_line|fp_rect|fp_poly|fp_circle)\b(.*?)\(layer "[FB]\.CrtYd"\)', f, re.S):
        for q in re.finditer(r'\((?:start|end|xy|center) ([-\d.]+) ([-\d.]+)\)', m.group(1)):
            pts.append(_rot(float(q.group(1)), float(q.group(2)), A))
    if pts:
        xs, ys = [X + p[0] for p in pts], [Y + p[1] for p in pts]
        out[lay].append((min(xs), min(ys), max(xs), max(ys)))
    return out


def board_obstacles(t):
    obs = {"F": [], "B": []}
    for s, e, ref in footprints(t):
        for k, v in fp_boxes(t[s:e]).items():
            obs[k] += v
    for m in re.finditer(r'\n\t\((segment|via)\n(.*?)\n\t\)', t, re.S):
        b = m.group(2)
        if m.group(1) == "via":
            x, y = map(float, re.search(r'\(at ([-\d.]+) ([-\d.]+)\)', b).groups())
            r = float(re.search(r'\(size ([\d.]+)', b).group(1)) / 2 + 0.15
            obs["F"].append((x - r, y - r, x + r, y + r))
            obs["B"].append((x - r, y - r, x + r, y + r))
        else:
            lay = re.search(r'\(layer "([^"]+)"\)', b).group(1)
            if lay not in ("F.Cu", "B.Cu"):
                continue
            (x1, y1), (x2, y2) = [tuple(map(float, re.search(r'\(' + k + r' ([-\d.]+) ([-\d.]+)\)', b).groups()))
                                  for k in ("start", "end")]
            w = float(re.search(r'\(width ([\d.]+)\)', b).group(1)) / 2 + 0.15
            obs[lay[0]].append((min(x1, x2) - w, min(y1, y2) - w, max(x1, x2) + w, max(y1, y2) + w))
    return obs


def hit(b, boxes):
    return any(b[0] < o[2] and o[0] < b[2] and b[1] < o[3] and o[1] < b[3] for o in boxes)


def pack(t, comps, pins, anchors):
    """anchors: [(ref, lib_id, (x, y), side, allowed(box))]. Tries 0 and 90 degrees on a 0.05 mm spiral."""
    obs = board_obstacles(t)
    blocks = []
    for ref, lib_id, (ax, ay), side, allowed in anchors:
        text = lib_text(lib_id)
        local = {a: fp_boxes(place(text, lib_id, ref, comps[ref], pins.get(ref, {}), 0, 0, a, side == "B"))[side]
                 for a in (0, 90)}
        R = 8.0
        near_obs = [o for o in obs[side] if o[2] > ax - R and o[0] < ax + R and o[3] > ay - R and o[1] < ay + R]
        best = None
        for r in range(0, 140):
            rr = r * 0.05
            n = max(1, int(2 * math.pi * rr / 0.05))
            for k in range(n):
                x = round(ax + rr * math.cos(2 * math.pi * k / n), 2)
                y = round(ay + rr * math.sin(2 * math.pi * k / n), 2)
                for a in (0, 90):
                    mine = [(b[0] + x, b[1] + y, b[2] + x, b[3] + y) for b in local[a]]
                    if not all(allowed(b) for b in mine) or any(hit(b, near_obs) for b in mine):
                        continue
                    best = (x, y, a, mine)
                    break
                if best:
                    break
            if best:
                break
        if not best:
            print("NO ROOM:", ref)
            continue
        x, y, a, mine = best
        blocks.append(place(text, lib_id, ref, comps[ref], pins.get(ref, {}), x, y, a, side == "B"))
        obs[side] += mine
    return blocks


def rip(t, net, box, mode="all"):
    """Remove the tracks and vias of `net` inside box (x0, y0, x1, y1): copper the new parts displace. mode "any":
    also the tracks that only touch the box."""
    x0, y0, x1, y1 = box
    out, n = [], 0
    pos = 0
    for m in re.finditer(r'\n\t\((segment|via|arc)\n(.*?)\n\t\)', t, re.S):
        b = m.group(2)
        if f'(net "{net}")' not in b:
            continue
        pts = [tuple(map(float, q)) for q in re.findall(r'\((?:start|end|at|mid) ([-\d.]+) ([-\d.]+)\)', b)]
        inside = [x0 <= x <= x1 and y0 <= y <= y1 for x, y in pts]
        if pts and (all(inside) if mode == "all" else any(inside)):
            out.append(t[pos:m.start()])
            pos = m.end()
            n += 1
    out.append(t[pos:])
    print(f"ripped {n} items of {net} in {box}")
    return "".join(out)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
