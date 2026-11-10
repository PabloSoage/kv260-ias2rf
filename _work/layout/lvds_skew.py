"""LVDS pair lengths, P/N skew and data-to-clock skew of the routed board (text parse, no pcbnew).

Usage:  py _work/layout/lvds_skew.py board.kicad_pcb [--json out.json]

A pair is two nets ending _P/_N. A link pair broken by AC caps (LINK_RX_D0_P and
IAS_LINK/J_LINK_RX_D0_P) counts as one: the nets are grouped by their name without the sheet path
and a leading J_. Tracks and arcs on each layer are summed and turned into delay with the layer's
ps/mm (L1/L6 microstrip, Er 4.16, Er_eff about 3.2 with the mask: 6.0 ps/mm; L3 stripline between
Er 4.16/4.53: 6.9 ps/mm; POWER_AND_STACKUP §2.5). Vias are counted, not timed (about 10 ps each
through 1.6 mm, the same order on both legs when the counts match). "Coupled" is the share of the
P leg that runs within 0.35 mm (centre to centre) of the N leg on the same layer.
Groups: each source-synchronous bus, data against its clock, by mean pair delay."""
import re, sys, math, json, argparse
from shapely.geometry import LineString
from shapely.ops import unary_union

PS_MM = {"F.Cu": 6.0, "B.Cu": 6.0, "In2.Cu": 6.9, "In1.Cu": 6.9, "In3.Cu": 6.9, "In4.Cu": 6.9}
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


def base(net):
    n = net.rsplit("/", 1)[-1]
    return n[2:] if n.startswith("J_") else n


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


legs = {}   # (pair base, "P"/"N") -> {"mm": {layer: mm}, "vias": n, "lines": {layer: [LineString]}, "nets": set}
for m in re.finditer(r"\n\t\((segment|arc|via)\n(.*?)\n\t\)", t, re.S):
    k, b = m.groups()
    net = re.search(r'\(net "([^"]*)"\)', b)
    if not net: continue
    net = net.group(1)
    mm = re.fullmatch(r"(.*)_([PN])", base(net))
    if not mm: continue
    leg = legs.setdefault((mm.group(1), mm.group(2)), {"mm": {}, "vias": 0, "lines": {}, "nets": set()})
    leg["nets"].add(net)
    if k == "via":
        leg["vias"] += 1; continue
    L = re.search(r'\(layer "([^"]+)"\)', b).group(1)
    s = tuple(map(float, re.search(r"\(start ([-\d.]+) ([-\d.]+)\)", b).groups()))
    e = tuple(map(float, re.search(r"\(end ([-\d.]+) ([-\d.]+)\)", b).groups()))
    if k == "arc":
        mid = tuple(map(float, re.search(r"\(mid ([-\d.]+) ([-\d.]+)\)", b).groups()))
        ln, geo = arc_len(s, mid, e), LineString([s, mid, e])
    else:
        ln, geo = math.dist(s, e), LineString([s, e])
    leg["mm"][L] = leg["mm"].get(L, 0) + ln
    leg["lines"].setdefault(L, []).append(geo)

pairs = {}
for (p, side), leg in legs.items():
    if side != "P" or (p, "N") not in legs: continue
    P, N = leg, legs[(p, "N")]
    ps = lambda g: sum(PS_MM[l] * v for l, v in g["mm"].items())
    cov = tot = 0.0
    for l, lines in P["lines"].items():
        other = unary_union(N["lines"].get(l, [])) if N["lines"].get(l) else None
        for ln in lines:
            n = max(1, int(ln.length / 0.1))
            for i in range(n):
                pt = ln.interpolate((i + 0.5) / n, normalized=True)
                tot += ln.length / n
                if other is not None and other.distance(pt) <= 0.35: cov += ln.length / n
    pairs[p] = {"P_mm": sum(P["mm"].values()), "N_mm": sum(N["mm"].values()), "P_ps": ps(P), "N_ps": ps(N),
                "P_vias": P["vias"], "N_vias": N["vias"], "coupled": cov / tot if tot else 0.0,
                "layers": sorted(set(P["mm"]) | set(N["mm"]))}

print(f"{'pair':16s} {'P mm':>7s} {'N mm':>7s} {'P-N mm':>7s} {'P-N ps':>7s} {'vias P/N':>8s} {'coupled':>7s}  layers")
for p in sorted(pairs):
    q = pairs[p]
    print(f"{p:16s} {q['P_mm']:7.1f} {q['N_mm']:7.1f} {q['P_mm'] - q['N_mm']:+7.1f} {q['P_ps'] - q['N_ps']:+7.0f} "
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
