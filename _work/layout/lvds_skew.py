"""LVDS pair delays, P/N skew and data-to-clock skew of the routed board (text parse, no pcbnew).

Usage:  py _work/layout/lvds_skew.py board.kicad_pcb [--json out.json]

A pair is two legs, P and N. A leg is every net on the way from the driver's pin to the
receiver's: nets ending _P/_N grouped by their name without the sheet path and a leading J_
(LINK_RX_D0_P and IAS_LINK/J_LINK_RX_D0_P, either side of an AC cap), plus the names in ALIAS
(FPGA_CLK, after the series resistors, is CLK_FPGA), plus an unnamed net with two pads that
reaches a leg through a series part (U401's outputs before their AC caps).

The delay of a leg is that of the shortest copper path between its two chip pins (U*, J*):
tracks per layer at the layer's ps/mm (L1/L6 microstrip, Er 4.16, Er_eff about 3.2 with the
mask: 6.0 ps/mm; L3/L4 stripline: 6.9 ps/mm; POWER_AND_STACKUP §2.5), vias joining the layers,
a series part (two pads on the same leg) joining its pads. Copper off that path is a stub,
reported on its own: the branch to a termination resistor that is not passed through, say.
Vias are counted, not timed (about 10 ps each through 1.6 mm). "Coupled" is the share of the
P leg within 0.35 mm (centre to centre) of the N leg on the same layer.
Groups: each source-synchronous bus, data against its clock, by mean leg delay."""
import re, sys, math, json, heapq, argparse
from shapely.geometry import LineString, Point, box
from shapely import affinity
from shapely.ops import unary_union

PS_MM = {"F.Cu": 6.0, "B.Cu": 6.0, "In2.Cu": 6.9, "In1.Cu": 6.9, "In3.Cu": 6.9, "In4.Cu": 6.9}
CU = ["F.Cu", "In1.Cu", "In2.Cu", "In3.Cu", "In4.Cu", "B.Cu"]
ALIAS = {"FPGA_CLK": "CLK_FPGA"}
GROUPS = {   # bus: (clock pair, data pairs), names as grouped (no sheet path, no J_)
    "LINK_RX (FPGA -> Kria, <=1 Gb/s)": ("LINK_RX_CLK", ["LINK_RX_D0", "LINK_RX_D1"]),
    "LINK_TX (Kria -> FPGA, <=1 Gb/s)": ("LINK_TX_CLK", ["LINK_TX_D0"]),
    "ADCS AD9253 (1 Gb/s per lane)": ("ADCS_DCO", ["ADCS_D0", "ADCS_D1", "ADCS_FCO"]),
    "ADCR AD9484 (400 MSPS)": ("ADCR_DCO", [f"ADCR_D{i}" for i in range(8)] + ["ADCR_OR"]),
}

ap = argparse.ArgumentParser()
ap.add_argument("board"); ap.add_argument("--json")
a = ap.parse_args()
t = open(a.board, encoding="utf-8").read()


def leg_of(net):
    """(pair, 'P'/'N') for a pair net, else None."""
    n = net.rsplit("/", 1)[-1]
    n = n[2:] if n.startswith("J_") else n
    m = re.fullmatch(r"(.*)_([PN])", n)
    if not m: return None
    return ALIAS.get(m.group(1), m.group(1)), m.group(2)


def arc_len(s, m, e):
    # circle through three points
    ax, ay = s; bx, by = m; cx, cy = e
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-12: return math.dist(s, e)
    ux = ((ax**2 + ay**2) * (by - cy) + (bx**2 + by**2) * (cy - ay) + (cx**2 + cy**2) * (ay - by)) / d
    uy = ((ax**2 + ay**2) * (cx - bx) + (bx**2 + by**2) * (ax - cx) + (cx**2 + cy**2) * (bx - ax)) / d
    r = math.dist((ux, uy), s)
    chord = math.dist(s, e)
    ang = 2 * math.asin(min(1, chord / (2 * r)))
    # the mid point on the far side means the long way round
    if math.dist(m, ((s[0] + e[0]) / 2, (s[1] + e[1]) / 2)) > r: ang = 2 * math.pi - ang
    return r * ang


# pads: (ref, number, net, layers, geometry)
pads = []
for fp in re.finditer(r"\n\t\(footprint .*?\n\t\)", t, re.S):
    f = fp.group(0)
    ref = re.search(r'\(property "Reference" "([^"]+)"', f).group(1)
    at = re.search(r"\n\t\t\(at ([-\d.]+) ([-\d.]+)(?: ([-\d.]+))?\)", f)
    X, Y, A = float(at.group(1)), float(at.group(2)), math.radians(float(at.group(3) or 0))
    for pm in re.finditer(r"\n\t\t\(pad \"([^\"]*)\" \w+ (\w+)(.*?)\n\t\t\)", f, re.S):
        num, shape, b = pm.groups()
        net = re.search(r'\(net "([^"]*)"\)', b)
        if not net: continue
        pa = re.search(r"\(at ([-\d.]+) ([-\d.]+)(?: ([-\d.]+))?\)", b)
        px, py, pang = float(pa.group(1)), float(pa.group(2)), float(pa.group(3) or 0)
        gx, gy = X + px * math.cos(A) + py * math.sin(A), Y - px * math.sin(A) + py * math.cos(A)
        sw, sh = map(float, re.search(r"\(size ([\d.]+) ([\d.]+)\)", b).groups())
        g = Point(gx, gy).buffer(sw / 2) if shape == "circle" else \
            affinity.rotate(box(gx - sw / 2, gy - sh / 2, gx + sw / 2, gy + sh / 2), -pang, origin=(gx, gy))
        ls = re.search(r"\(layers ([^)]*)\)", b).group(1)
        lay = CU if '"*.Cu"' in ls else [l for l in CU if f'"{l}"' in ls]
        pads.append((ref, num, net.group(1), lay, g, (gx, gy)))

# nets of each leg: pair nets, then unnamed two-pad nets reaching a leg through a series part
leg_nets = {}
for net in {p[2] for p in pads} | set(re.findall(r'\n\t\t\(net "([^"]*)"\)', t)):
    k = leg_of(net)
    if k: leg_nets.setdefault(k, set()).add(net)
net_leg = {n: k for k, ns in leg_nets.items() for n in ns}
by_ref = {}
for p in pads: by_ref.setdefault(p[0], []).append(p)
by_net = {}
for p in pads: by_net.setdefault(p[2], []).append(p)
for net, ps in by_net.items():   # one chip pin, a series part on to the leg, maybe bias resistors
    if net in net_leg or not net.startswith("Net-(") or sum(p[0][0] in "UJ" for p in ps) != 1: continue
    for p in ps:
        parts = by_ref[p[0]]
        if len(parts) == 2 and p[0][0] in "CR":
            other = [q for q in parts if q is not p][0][2]
            if other in net_leg:
                k = net_leg[other]; leg_nets[k].add(net); net_leg[net] = k

# copper per leg
legs = {k: {"edges": [], "vias": [], "mm": {}, "ps": 0.0, "lines": {}} for k in leg_nets}
for m in re.finditer(r"\n\t\((segment|arc|via)\n(.*?)\n\t\)", t, re.S):
    kind, b = m.groups()
    net = re.search(r'\(net "([^"]*)"\)', b)
    if not net or net.group(1) not in net_leg: continue
    leg = legs[net_leg[net.group(1)]]
    if kind == "via":
        x, y = map(float, re.search(r"\(at ([-\d.]+) ([-\d.]+)\)", b).groups())
        leg["vias"].append((x, y, float(re.search(r"\(size ([\d.]+)", b).group(1)) / 2)); continue
    L = re.search(r'\(layer "([^"]+)"\)', b).group(1)
    s = tuple(map(float, re.search(r"\(start ([-\d.]+) ([-\d.]+)\)", b).groups()))
    e = tuple(map(float, re.search(r"\(end ([-\d.]+) ([-\d.]+)\)", b).groups()))
    if kind == "arc":
        mid = tuple(map(float, re.search(r"\(mid ([-\d.]+) ([-\d.]+)\)", b).groups()))
        ln, geo = arc_len(s, mid, e), LineString([s, mid, e])
    else:
        ln, geo = math.dist(s, e), LineString([s, e])
    leg["edges"].append((s, e, L, ln * PS_MM[L]))
    leg["mm"][L] = leg["mm"].get(L, 0) + ln
    leg["ps"] += ln * PS_MM[L]
    leg["lines"].setdefault(L, []).append(geo)


def path_ps(k):
    """Shortest delay between the leg's two chip pins, and the chip pins found."""
    leg = legs[k]
    G = {}
    def edge(u, v, w):
        G.setdefault(u, []).append((v, w)); G.setdefault(v, []).append((u, w))
    pts = {}   # (layer) -> [(x, y, node)]
    def node(x, y, l):
        for qx, qy, n in pts.setdefault(l, []):
            if math.hypot(qx - x, qy - y) < 0.06: return n   # overlapping track ends
        n = ("p", l, round(x, 3), round(y, 3)); pts[l].append((x, y, n)); return n
    for s, e, L, w in leg["edges"]:
        node(*s, L); node(*e, L)
    for s, e, L, w in leg["edges"]:   # a track end (within half a track) or a via on another's middle splits it
        g = LineString([s, e]); on = []
        for qx, qy, n in pts[L]:
            q = Point(qx, qy)
            if g.distance(q) < 0.06 and math.dist((qx, qy), s) > 0.06 and math.dist((qx, qy), e) > 0.06:
                on.append((g.project(q), n))
        for x, y, r in leg["vias"]:
            d = g.project(Point(x, y))
            if g.distance(Point(x, y)) < r + 0.05 and 0.06 < d < g.length - 0.06:
                on.append((d, ("v", x, y)))
        chain = [(0.0, node(*s, L))] + sorted(on) + [(g.length, node(*e, L))]
        for (d0, u), (d1, v) in zip(chain, chain[1:]):
            edge(u, v, w * (d1 - d0) / g.length if g.length else 0.0)
    for x, y, r in leg["vias"]:
        v = ("v", x, y)
        for l, lst in pts.items():
            for qx, qy, n in lst:
                if math.hypot(qx - x, qy - y) <= r + 0.05: edge(v, n, 0.0)   # the track's copper reaches the via
    ends, mine = [], [p for p in pads if p[2] in leg_nets[k]]
    for p in mine:
        pn = ("pad", p[0], p[1])
        for l in p[3]:   # a track ending on the pad (to its edge, half a track out), or a via in it
            for qx, qy, n in pts.get(l, []):
                if p[4].buffer(0.06).contains(Point(qx, qy)): edge(pn, n, 0.0)
        for x, y, r in leg["vias"]:
            if p[4].distance(Point(x, y)) < r: edge(pn, ("v", x, y), 0.0)
        if p[0][0] in "UJ": ends.append(pn)
        parts = by_ref[p[0]]
        if len(parts) == 2 and p[0][0] in "CR":
            q = [x for x in parts if x is not p][0]
            if q[2] in leg_nets[k]: edge(pn, ("pad", q[0], q[1]), 0.0)
    if len(ends) < 2: return None, ends
    best = None
    for i, src in enumerate(ends):
        dist = {src: 0.0}; h = [(0.0, src)]
        while h:
            d, u = heapq.heappop(h)
            if d > dist[u]: continue
            for v, w in G.get(u, []):
                if d + w < dist.get(v, 1e18): dist[v] = d + w; heapq.heappush(h, (d + w, v))
        for dst in ends[i + 1:]:
            if dst in dist and (best is None or dist[dst] > best): best = dist[dst]
    return best, ends


pairs = {}
for (p, side), leg in legs.items():
    if side != "P" or (p, "N") not in legs: continue
    P, N = leg, legs[(p, "N")]
    pp, pe = path_ps((p, "P")); nn, ne = path_ps((p, "N"))
    if pp is None or nn is None:
        print(f"{p}: no path between two chip pins (P {len(pe)}, N {len(ne)} pins found)", file=sys.stderr); continue
    cov = tot = 0.0
    for l, lines in P["lines"].items():
        other = unary_union(N["lines"].get(l, [])) if N["lines"].get(l) else None
        for ln in lines:
            n = max(1, int(ln.length / 0.1))
            for i in range(n):
                pt = ln.interpolate((i + 0.5) / n, normalized=True)
                tot += ln.length / n
                if other is not None and other.distance(pt) <= 0.35: cov += ln.length / n
    pairs[p] = {"P_ps": pp, "N_ps": nn, "P_mm": sum(P["mm"].values()), "N_mm": sum(N["mm"].values()),
                "P_stub_ps": P["ps"] - pp, "N_stub_ps": N["ps"] - nn,
                "P_vias": len(P["vias"]), "N_vias": len(N["vias"]), "coupled": cov / tot if tot else 0.0,
                "layers": sorted(set(P["mm"]) | set(N["mm"]))}

print(f"{'pair':14s} {'P ps':>6s} {'N ps':>6s} {'P-N ps':>7s} {'stub P/N ps':>12s} {'copper P/N mm':>14s} "
      f"{'vias P/N':>8s} {'coupled':>7s}  layers")
for p in sorted(pairs):
    q = pairs[p]
    print(f"{p:14s} {q['P_ps']:6.0f} {q['N_ps']:6.0f} {q['P_ps'] - q['N_ps']:+7.0f} "
          f"{q['P_stub_ps']:6.0f}/{q['N_stub_ps']:<5.0f} {q['P_mm']:7.1f}/{q['N_mm']:<6.1f} "
          f"{q['P_vias']:>4d}/{q['N_vias']:<3d} {100 * q['coupled']:6.0f}%  {','.join(q['layers'])}")
print()
for g, (clk, data) in GROUPS.items():
    if clk not in pairs:
        print(f"{g}: no {clk} pair on the board"); continue
    c = (pairs[clk]["P_ps"] + pairs[clk]["N_ps"]) / 2
    row = []
    for d in data:
        if d in pairs: row.append(f"{d} {((pairs[d]['P_ps'] + pairs[d]['N_ps']) / 2 - c):+.0f}")
    print(f"{g}: data - clock, ps: " + ", ".join(row))
if a.json:
    json.dump(pairs, open(a.json, "w"), indent=1)
