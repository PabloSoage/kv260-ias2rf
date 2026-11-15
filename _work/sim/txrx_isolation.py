#!/usr/bin/env python3
"""
Transmit-to-receive and clock-to-receive coupling between the board's RF lines (SIGNAL_INTEGRITY section 9.8).

Every RF line runs on a signal layer with a ground plane 0.12-0.13 mm away, so lines on different layers are
screened from each other by a plane; what couples is two lines side by side on the same layer. For each victim
(receive) line, the script walks its copper in 0.1 mm steps and finds the nearest aggressor copper on the same
layer. Where the edge gap is under 1.5 mm, the backward (near-end) coupling coefficient Kb(gap) is taken from the
board's field-solver results (SIGNAL_INTEGRITY section 3.5: 0.183 mm lines, L1/L6 microstrip and L3 stripline),
extrapolated exponentially beyond 0.55 mm, and integrated as an electrically short coupled line:

    |NEXT| ~ sum over the run of Kb(gap) * 2 * beta * dl        (beta l << 1; summed in phase: a worst case)

The result is an estimate to rank the risks and size the first measurement, good to a few dB, not a substitute for
the network-analyser sweep (TX SMA to RX SMA, converters off) listed in section 9.8. It does not include coupling
through the supplies, the converters' own feedthrough, or radiation between the SMAs.

Usage:  py _work/sim/txrx_isolation.py
"""
import math, os, re, sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PCB = os.path.join(ROOT, "CSI2-KRIA-KV260_Rev01.kicad_pcb")
C0 = 299792458.0
EEFF = {"F.Cu": 3.3, "B.Cu": 3.3, "In2.Cu": 4.1, "In5.Cu": 4.1}       # microstrip / stripline, 2116 at ~4.1
# Kb at edge gaps 0.15, 0.25, 0.35, 0.55 mm (SIGNAL_INTEGRITY 3.5)
KB = {"micro": [(0.15, 0.145), (0.25, 0.077), (0.35, 0.046), (0.55, 0.020)],
      "strip": [(0.15, 0.167), (0.25, 0.097), (0.35, 0.061), (0.55, 0.028)]}

RX = {"IF_RX_A (SDR ch A / radar IF -> AD9253)": [r"^/IF_RX_A$", r"^Net-\(U901-RFOUT", r"^Net-\(D96[12]-A1\)$"],
      "IF_RX_B (radar IF / wideband -> AD9484)": [r"^/IF_RX_B$", r"^Net-\(U902-RFOUT", r"^Net-\(D96[34]-A1\)$"],
      "IF_RX_C (HF -> filter -> AD9253 ch B)": [r"^/IF_RX_C$", r"^/ROUTING/(IF_RX_C_AAF|AAF_C_N\d)$", r"^Net-\(D969-A1\)$"]}
AGG = {"IF_TX_A (AD9767 DAC1)": [r"^/IF_TX_A$", r"^Net-\(U903-RFOUT", r"^Net-\(D96[56]-A1\)$"],
       "IF_TX_B (AD9708 radar chirp)": [r"^/IF_TX_B$", r"^Net-\(U904-RFOUT", r"^Net-\(D96[78]-A1\)$"],
       "IF_TX_C (AD9767 DAC2)": [r"^/IF_TX_C$", r"^Net-\(D970-A1\)$"],
       "CLK_REF_IN (J401 -> U401 CLK0)": [r"^Net-\(U401-CLK0\)$"],
       "CLK_OUT (U401 Q3 -> J402, 400/500 MHz)": [r"^Net-\(U401-Q3\)$"]}


def kb(gap, layer):
    tab = KB["micro" if layer in ("F.Cu", "B.Cu") else "strip"]
    if gap <= tab[0][0]:
        return tab[0][1]
    for (g0, k0), (g1, k1) in zip(tab, tab[1:]):
        if gap <= g1:
            return math.exp(math.log(k0) + (math.log(k1) - math.log(k0)) * (gap - g0) / (g1 - g0))
    (g0, k0), (g1, k1) = tab[-2], tab[-1]
    return k1 * math.exp(-(math.log(k0 / k1) / (g1 - g0)) * (gap - g1))


def segments():
    t = open(PCB, encoding="utf-8").read()
    out = []
    for m in re.finditer(r'\(segment\s*\(start ([-\d.]+) ([-\d.]+)\)\s*\(end ([-\d.]+) ([-\d.]+)\)\s*\(width ([\d.]+)\)'
                         r'\s*\(layer "([^"]+)"\)\s*\(net "([^"]*)"\)', t):
        x1, y1, x2, y2, w = map(float, m.groups()[:5])
        out.append((x1, y1, x2, y2, w, m.group(6), m.group(7)))
    return out


def pick(segs, pats):
    return [s for s in segs if any(re.search(p, s[6]) for p in pats)]


def dist(px, py, s):
    x1, y1, x2, y2 = s[:4]
    dx, dy = x2 - x1, y2 - y1; L2 = dx * dx + dy * dy
    u = 0 if L2 == 0 else max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / L2))
    return math.hypot(px - x1 - u * dx, py - y1 - u * dy)


def couple(vs, ags, f):
    """|NEXT| (linear) and the parallel length with a gap under 1.5 mm."""
    tot, plen, worst = 0.0, 0.0, None
    by_layer = defaultdict(list)
    for a in ags: by_layer[a[5]].append(a)
    for v in vs:
        cand = by_layer.get(v[5])
        if not cand: continue
        x1, y1, x2, y2, w = v[:5]
        L = math.hypot(x2 - x1, y2 - y1); n = max(1, int(L / 0.1))
        beta = 2 * math.pi * f * math.sqrt(EEFF.get(v[5], 4.1)) / C0 * 1e-3   # rad per mm
        for i in range(n):
            px, py = x1 + (x2 - x1) * (i + 0.5) / n, y1 + (y2 - y1) * (i + 0.5) / n
            a = min(cand, key=lambda s: dist(px, py, s))
            gap = dist(px, py, a) - (w + a[4]) / 2
            if gap < 1.5:
                tot += kb(gap, v[5]) * 2 * beta * (L / n); plen += L / n
                if worst is None or gap < worst[0]: worst = (gap, v[5], round(px, 1), round(py, 1), a[6])
    return tot, plen, worst


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    segs = segments()
    print("Victim <- aggressor: same-layer run with gap < 1.5 mm, closest gap, estimated |NEXT| at 30 / 120 / 500 MHz")
    for rn, rp in RX.items():
        vs = pick(segs, rp)
        for an, ap in AGG.items():
            ags = pick(segs, ap)
            res = [couple(vs, ags, f) for f in (30e6, 120e6, 500e6)]
            plen, worst = res[0][1], res[0][2]
            if plen == 0:
                continue
            db = ["%.0f" % (20 * math.log10(r[0])) if r[0] > 0 else "-" for r in res]
            print(f"  {rn:40s} <- {an:38s} {plen:5.1f} mm, gap {worst[0]:.2f} mm on {worst[1]} at "
                  f"({worst[2]}, {worst[3]})  NEXT {db[0]} / {db[1]} / {db[2]} dB")
    print("Pairs not listed have no same-layer copper within 1.5 mm.")


if __name__ == "__main__":
    main()
