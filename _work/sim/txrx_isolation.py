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

Rev08 (REV08_PLAN section 11, phase 6, gate G3) adds the VHF/UHF front end's copper as aggressors: the
RFFC5072's mixer ports (which carry its LO leakage), its reference, the IF chain from the mixer to the L6
stripline IF_VU, the preselector link VU_PSB_OUT and the USB pair; and as victims both converters' inputs
(the IF_RX lines, the AD8352 driver nets and the ADC VIN nets), IF_VU itself (it feeds the AD9484 through SW2)
and the clock tree (Si549, ADCLK948 inputs and outputs, the ADC and FPGA clock pairs). Two additions for it:
- 1.1 GHz is added to the frequencies (the front end's top), and the in-phase sum is capped at the largest
  Kb along the run: a backward-coupled line never exceeds its own Kb, whatever its length, and the sum is no
  longer electrically short at 1.1 GHz on the longer runs;
- vias pass through every layer, so aggressor vias closer than 1.0 mm to a victim track on any layer are
  listed too (closest centre-to-edge distance; no dB figure, a via is a short vertical, not a parallel run).
The G3 figure of merit is the worst Rev07 track coupling into an ADC input, CLK_REF_IN into IF_RX_B, about
-100 dB at 120 MHz (section 9.9).

Usage:  py _work/sim/txrx_isolation.py [--json out.json]
"""
import json, math, os, re, sys
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

# Rev08 (phase 6): victims and aggressors added by the VHF/UHF front end
RX8 = dict(RX)
RX8.update({"AD9484 drivers and VIN (U502/U503 -> U501)": [r"^Net-\(U50[123]-", r"^/ADC_RADAR/"],
            "AD9253 drivers and VIN (U602/U603 -> U601)": [r"^Net-\(U60[123]-", r"^/ADC_SDR/"],
            "IF_VU (front end IF -> SW2 -> AD9484)": [r"^/IF_VU$"]})
CLK8 = {"Si549 output (Y401 -> U401)": [r"^Net-\(Y401-CLK[+-]\)$"],
        "ADCLK948 inputs and outputs (U401)": [r"^Net-\(U401-(~\{)?(CLK|Q)\d\}?\)$"],
        "CLK_ADCR / CLK_ADCS (ADC clocks)": [r"^/CLK_ADC[RS]_[PN]$"],
        "CLK_FPGA": [r"^/CLK_FPGA_[PN]$"]}
AGG8 = {"LO: RFFC5072 mixer ports (LO leakage)": [r"^/RX_VU/VU_MIX_"],
        "RFFC5072 reference (TCXO)": [r"^/RX_VU/VU_(TCXO_OUT|REF)$"],
        "IF chain (anti-alias, IF amp, PE4312)": [r"^/RX_VU/VU_(AA|IFA)_(IN|OUT)$", r"^/RX_VU/VU_ATT_IN$"],
        "IF line IF_VU (L6 stripline)": [r"^/IF_VU$"],
        "VU_PSB_OUT (preselector B -> A, to 1.1 GHz)": [r"^/RX_VU/VU_PSB_OUT$"],
        "USB (J104 -> CH340X)": [r"^/STATUS/USB_D[PN](_C)?$"]}
# what else shares L3/L6 with IF_VU: the DAC outputs before their filters, and the clock and LVDS pairs
AGG_IFVU = {"DAC outputs before the filters (U701, U801 IOUT)": [r"^Net-\(U[78]01-IOUT"],
            "ADC, FPGA and DAC clocks": [r"^/CLK_(ADC[RS]|FPGA)_[PN]$", r"^/DAC(R_CLK|S_IQCLK)$",
                                         r"^/CONTROL/F_DAC(R_CLK|S_IQCLK)$"],
            "LVDS: ADC data, DCO/FCO, IAS link": [r"^/ADC[RS]_(D\d|DCO|FCO|OR)_[PN]$", r"^/LINK_(RX|TX)_"]}
# a front-end net is not an aggressor of the line it feeds: IF_VU and its chain into the AD9484's own path
SAME_PATH = {("IF_VU (front end IF -> SW2 -> AD9484)", "IF line IF_VU (L6 stripline)"),
             ("IF_VU (front end IF -> SW2 -> AD9484)", "IF chain (anti-alias, IF amp, PE4312)")}
# SW2's RF2 throw, Net-(U902-RFOUT2), is IF_VU's own path (C927 joins them, REV08_PLAN 5.7): for the front end's
# IF aggressors the IF_RX_B victim is IF_RX_B and SW2's other throw only; what crosses from RF2 to the common
# port is SW2's isolation, not track coupling
EXCL_VICTIM = {"IF line IF_VU (L6 stripline)": r"^Net-\(U902-RFOUT2\)$",
               "IF chain (anti-alias, IF amp, PE4312)": r"^Net-\(U902-RFOUT2\)$"}
FREQS8 = (30e6, 120e6, 500e6, 1.1e9)


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


def vias():
    t = open(PCB, encoding="utf-8").read()
    return [(float(m.group(1)), float(m.group(2)), float(m.group(3)), m.group(4)) for m in
            re.finditer(r'\(via\s*\(at ([-\d.]+) ([-\d.]+)\)\s*\(size ([\d.]+)\).*?\(net "([^"]*)"\)', t, re.S)]


def via_near(vs, avias, lim=1.0):
    """Closest aggressor via (centre to the victim track's edge, minus the via's radius) within lim mm."""
    best = None
    for (x, y, d, net) in avias:
        for v in vs:
            g = dist(x, y, v) - v[4] / 2 - d / 2
            if g < lim and (best is None or g < best[0]):
                best = (g, v[5], round(x, 2), round(y, 2), net)
    return best


def couple(vs, ags, f, cap=False):
    """|NEXT| (linear) and the parallel length with a gap under 1.5 mm. cap: limit the sum to the run's
    largest Kb (Rev08 section of the docstring)."""
    tot, plen, worst, kmax = 0.0, 0.0, None, 0.0
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
                tot += kb(gap, v[5]) * 2 * beta * (L / n); plen += L / n; kmax = max(kmax, kb(gap, v[5]))
                if worst is None or gap < worst[0]: worst = (gap, v[5], round(px, 1), round(py, 1), a[6])
    if cap:
        tot = min(tot, kmax)
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
    rev08(segs)


def rev08(segs):
    """Phase 6 (gate G3): the front end's aggressors into both converters' inputs, IF_VU and the clock tree;
    the old transmit and clock aggressors into IF_VU."""
    avias = vias()
    victims = [("adc", k, v) for k, v in RX8.items()] + [("clk", k, v) for k, v in CLK8.items()]
    aggs = dict(AGG8)
    out = []
    print()
    print("Rev08 front end: victim <- aggressor, same-layer run with gap < 1.5 mm, closest gap, |NEXT| at "
          "30 / 120 / 500 / 1100 MHz (capped at the run's Kb); aggressor vias within 1.0 mm of the victim")
    for kind, vn, vp in victims:
        vs = pick(segs, vp)
        if not vs:
            print(f"  (no copper matched for {vn})")
            continue
        pool = dict(aggs)
        if vn.startswith("IF_VU"):          # the transmit lines and clocks into the new receive line too
            pool.update(AGG); pool.update(AGG_IFVU)
        for an, ap in pool.items():
            if (vn, an) in SAME_PATH:
                continue
            vsx = [v for v in vs if not (an in EXCL_VICTIM and re.search(EXCL_VICTIM[an], v[6]))]
            ags = pick(segs, ap)
            res = [couple(vsx, ags, f, cap=True) for f in FREQS8]
            plen, worst = res[0][1], res[0][2]
            vn_ = via_near(vsx, [a for a in avias if any(re.search(p, a[3]) for p in ap)])
            if plen == 0 and vn_ is None:
                continue
            rec = dict(victim=vn, kind=kind, aggressor=an, run_mm=round(plen, 2),
                       next_db=[round(20 * math.log10(r[0]), 1) if r[0] > 0 else None for r in res],
                       gap_mm=round(worst[0], 3) if worst else None, layer=worst[1] if worst else None,
                       at=[worst[2], worst[3]] if worst else None,
                       via_mm=round(vn_[0], 3) if vn_ else None, via_layer=vn_[1] if vn_ else None,
                       via_at=[vn_[2], vn_[3]] if vn_ else None)
            out.append(rec)
            db = " / ".join("-" if d is None else "%.0f" % d for d in rec["next_db"])
            s = f"  {vn:44s} <- {an:44s}"
            if plen:
                s += f" {plen:5.1f} mm, gap {worst[0]:.2f} mm on {worst[1]} at ({worst[2]}, {worst[3]})  NEXT {db} dB"
            if vn_:
                s += f"  via {vn_[0]:.2f} mm from its {vn_[1]} track at ({vn_[2]}, {vn_[3]})"
            print(s)
    print("Pairs not listed: no same-layer copper within 1.5 mm and no aggressor via within 1.0 mm.")
    # how far the front end's copper stays from the converters and the clock tree, on any layer
    print()
    print("Closest approach, any layer (edge to edge, mm): front-end aggressor -> victim")
    near = []
    for an, ap in AGG8.items():
        ags = pick(segs, ap)
        for kind, vn, vp in victims:
            vs = [v for v in pick(segs, vp) if not (an in EXCL_VICTIM and re.search(EXCL_VICTIM[an], v[6]))]
            if (vn, an) in SAME_PATH or not vs:
                continue
            best = closest(vs, ags)
            if best:
                near.append(dict(aggressor=an, victim=vn, mm=round(best[0], 2), layers=[best[1], best[2]]))
    near.sort(key=lambda r: r["mm"])
    for r in near[:12]:
        print(f"  {r['aggressor']:44s} -> {r['victim']:44s} {r['mm']:6.2f} mm ({r['layers'][0]} / {r['layers'][1]})")
    if "--json" in sys.argv:
        p = sys.argv[sys.argv.index("--json") + 1]
        json.dump(dict(coupling=out, closest=near), open(p, "w"), indent=1)
    return out


def closest(vs, ags):
    """Smallest edge-to-edge distance between two sets of segments on any layer, sampled every 0.25 mm."""
    best = None
    for v in vs:
        x1, y1, x2, y2, w = v[:5]
        n = max(1, int(math.hypot(x2 - x1, y2 - y1) / 0.25))
        for i in range(n + 1):
            px, py = x1 + (x2 - x1) * i / n, y1 + (y2 - y1) * i / n
            for a in ags:
                if best and (min(a[0], a[2]) - px > best[0] + 1 or px - max(a[0], a[2]) > best[0] + 1 or
                             min(a[1], a[3]) - py > best[0] + 1 or py - max(a[1], a[3]) > best[0] + 1):
                    continue
                g = dist(px, py, a) - (w + a[4]) / 2
                if best is None or g < best[0]:
                    best = (g, v[5], a[5])
    return best


if __name__ == "__main__":
    main()
