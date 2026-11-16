#!/usr/bin/env python3
"""
Rev08 phase 3 (docs/REV08_PLAN.md, section 11, gate G2): the three front-end filters of rev08_frontend.py snapped
to parts that exist, then a tolerance Monte Carlo, the method of aaf_lpf.py.

    python _work/sim/rev08_filters_mc.py          # about five minutes; writes docs/img/rev08_filters_mc.png

Parts and tolerances [E: catalogue series, checked against LCSC stock when the schematic is drawn]:
  inductors  Murata LQW15AN (0402 wirewound, +-2 %, G) up to 120 nH, LQW18AN (0603, +-2 %) above
  capacitors C0G 0402, E24; below 10 pF +-0.1 pF (B) or +-0.25 pF (C), from 10 pF +-2 % (G) or +-5 % (J)
  board      each shunt node gets 0.10 +- 0.05 pF of pad and via capacitance; inductor self-capacitance as in
             rev08_frontend.py
Two tolerance sets are run: "tight" (B / G, the parts the plan specifies) and "loose" (C / J, what a generic
basic-part substitution would give). The gate is judged on the tight set at the 1st percentile of rejection and
the 99th percentile of loss.
"""
import math
import sys

import numpy as np
from scipy.optimize import minimize

sys.path.insert(0, __file__.rsplit("\\", 1)[0] if "\\" in __file__ else __file__.rsplit("/", 1)[0])
import rev08_frontend as fe  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
E24 = [1.0, 1.1, 1.2, 1.3, 1.5, 1.6, 1.8, 2.0, 2.2, 2.4, 2.7, 3.0, 3.3, 3.6, 3.9, 4.3, 4.7, 5.1, 5.6, 6.2, 6.8,
       7.5, 8.2, 9.1]
LQW15 = [1.5, 1.8, 2.2, 2.7, 3.3, 3.6, 3.9, 4.3, 4.7, 5.1, 5.6, 6.2, 6.8, 7.5, 8.2, 8.7, 9.1, 10, 11, 12, 13, 15,
         16, 18, 20, 22, 24, 27, 30, 33, 36, 39, 43, 47, 51, 56, 62, 68, 72, 75, 82, 91, 100, 110, 120]
LQW18 = [150, 180, 220, 270, 330, 390, 470]
LIND = LQW15 + LQW18
IND_IDX = (1, 4, 7)          # positions of the inductors in the 10-element vector (7th order)
IND_IDX9 = (1, 4, 7, 10)     # and in the 13-element vector of the 9th-order FM-reject filter
# The 7th-order FM-reject filter fails gate G2 with real tolerances (rejection 34 dB at p1, see the module
# docstring of the run log); a 9th-order version with 8 dB of design margin is what the plan adopts.
FM9 = "FMREJ9: airband and VHF, 9th order, pass 118-170 MHz, stop 87-108 MHz"
FM9_SPEC = ("hpf9", (118e6, 170e6), [(87e6, 108e6), (40e6, 87e6)], 2.5, 45, 55, 0.15e-12, None)


def abcd_hpf9(v, f, q, cpar):
    """series C1, then (shunt L+C, series C) four times: 13 elements"""
    w = 2 * np.pi * f; one = np.ones_like(w, dtype=complex)
    se = lambda C: [one, 1 / (1j * w * C), 0 * one, one]
    def sh(L, C):
        ZL = 1 / (1 / (1j * w * L + w * L / q) + 1j * w * cpar)
        return [one, 0 * one, 1 / (ZL + 1 / (1j * w * C)), one]
    M = se(v[0]); k = 1
    while k < len(v):
        M = fe._mul(fe._mul(M, sh(v[k], v[k + 1])), se(v[k + 2])); k += 3
    return M


def start_hpf9(fc=112e6, zeros=(98e6, 107e6, 90e6, 104e6)):
    wc = 2 * np.pi * fc; g = [0.347, 1.0, 1.532, 1.879, 2.0, 1.879, 1.532, 1.0, 0.347]
    x = [1 / (g[0] * wc * fe.R0)]
    for i, z in enumerate(zeros):
        L = fe.R0 / (g[2 * i + 1] * wc)
        x += [L, 1 / ((2 * np.pi * z) ** 2 * L), 1 / (g[2 * i + 2] * wc * fe.R0)]
    return x


fe.FILTERS[FM9] = FM9_SPEC[:7] + (start_hpf9(),)
MARGIN_DB = {FM9: 8}


def inds(name):
    return IND_IDX9 if name == FM9 else IND_IDX
CPAD = 0.10e-12


def e24(v_pf):
    if v_pf < 1.0:           # sub-picofarad parts come in 0.1 pF steps
        return max(0.1, round(v_pf, 1))
    dec = 10 ** math.floor(math.log10(v_pf))
    return min((m * dec for m in E24 + [10.0]), key=lambda c: abs(math.log(c / v_pf)))


def response(name, v, f, cpad=None, q=None):
    kind, fp, fs, ilmax, rej, q0, cpar, x0 = fe.FILTERS[name]
    fn = {"lpf": fe.abcd_lpf, "hpf": fe.abcd_hpf, "hpf9": abcd_hpf9}[kind]
    v = np.array(v, float)
    if kind == "lpf":                      # pad capacitance adds to the shunt capacitors C1, C3, C5, C7
        pads = cpad if cpad is not None else np.full(4, CPAD)
        for k, idx in enumerate((0, 3, 6, 9)):
            v[idx] = v[idx] + pads[k]
    return fe.s21(fn(v, f, q if q else q0, cpar))


def metrics(name, v, cpad=None):
    kind, fp, fs, ilmax, rej, q, cpar, _ = fe.FILTERS[name]
    FP = np.linspace(*fp, 80); FS = np.concatenate([np.linspace(a, b, 60) for a, b in fs])
    a, r = response(name, v, FP, cpad)
    s = -20 * np.log10(np.abs(response(name, v, FS, cpad)[0]))
    return (-20 * np.log10(np.abs(a))).max(), (-20 * np.log10(np.abs(r) + 1e-12)).min(), s.min()


def cost_vec(name, v):
    kind, fp, fs, ilmax, rej, q, cpar, _ = fe.FILTERS[name]
    FP = np.linspace(*fp, 80); FS = np.concatenate([np.linspace(a, b, 60) for a, b in fs])
    a, r = response(name, v, FP)
    il = -20 * np.log10(np.abs(a)); rl = -20 * np.log10(np.abs(r) + 1e-12)
    s = -20 * np.log10(np.abs(response(name, v, FS)[0]))
    return (np.sum(np.maximum(il - ilmax, 0) ** 2) + 0.2 * np.sum(np.maximum(12 - rl, 0) ** 2)
            + np.sum(np.maximum(rej + MARGIN_DB.get(name, 3) - s, 0) ** 2))   # margin for the tolerances


def ideal(name, trials=4):
    x0 = np.log(np.array(fe.FILTERS[name][7]))
    best = None
    for t in range(trials):
        rng = np.random.default_rng(t)
        x = x0 + (rng.normal(0, 0.3, len(x0)) if t else 0)
        r = minimize(lambda x: cost_vec(name, np.exp(x)), x, method="Nelder-Mead",
                     options={"maxiter": 30000, "maxfev": 30000, "xatol": 1e-5, "fatol": 1e-9})
        r = minimize(lambda x: cost_vec(name, np.exp(x)), r.x, method="Powell", options={"maxiter": 20000})
        if best is None or r.fun < best.fun:
            best = r
    return np.exp(best.x)


def snapped(name, v):
    """Inductors to the nearest catalogue value, the capacitors re-optimised around them, then to E24."""
    v = np.array(v, float)
    for k in inds(name):
        v[k] = min(LIND, key=lambda c: abs(math.log(c / (v[k] * 1e9)))) * 1e-9
    caps = [k for k in range(len(v)) if k not in inds(name)]

    def cc(x):
        w = v.copy(); w[caps] = np.exp(x)
        return cost_vec(name, w)
    r = minimize(cc, np.log(v[caps]), method="Nelder-Mead", options={"maxiter": 20000, "xatol": 1e-6, "fatol": 1e-10})
    for k, xi in zip(caps, r.x):
        v[k] = e24(math.exp(xi) * 1e12) * 1e-12
    # a final pass: try one E24 step either way on each capacitor
    for _ in range(2):
        for k in caps:
            best = (cost_vec(name, v), v[k])
            for step in (-1, 1):
                pf = v[k] * 1e12
                if pf < 1:
                    cand = max(0.1, round(pf + 0.1 * step, 1))
                else:
                    dec = 10 ** math.floor(math.log10(pf))
                    ser = sorted(set([m * dec for m in E24] + [m * dec * 10 for m in E24] + [m * dec / 10 for m in E24]))
                    i = min(range(len(ser)), key=lambda j: abs(ser[j] - pf))
                    cand = ser[max(0, min(len(ser) - 1, i + step))]
                w = v.copy(); w[k] = cand * 1e-12
                c = cost_vec(name, w)
                if c < best[0]:
                    best = (c, w[k])
            v[k] = best[1]
    return v


def monte_carlo(name, v, tight, n=2000, seed=1):
    rng = np.random.default_rng(seed)
    il, rl, rj = [], [], []
    for _ in range(n):
        w = v.copy()
        for k in range(len(w)):
            if k in inds(name):
                w[k] *= 1 + rng.uniform(-0.02, 0.02)
            else:
                pf = w[k] * 1e12
                if pf < 10:
                    w[k] += rng.uniform(-1, 1) * (0.1e-12 if tight else 0.25e-12)
                else:
                    w[k] *= 1 + rng.uniform(-1, 1) * (0.02 if tight else 0.05)
                w[k] = max(w[k], 0.05e-12)
        pads = CPAD + rng.uniform(-0.05e-12, 0.05e-12, 4)
        a, b, c = metrics(name, w, pads)
        il.append(a); rl.append(b); rj.append(c)
    return np.array(il), np.array(rl), np.array(rj)


def fmt(v, name=None):
    return ", ".join("%.3g nH" % (x * 1e9) if k in inds(name) else "%.3g pF" % (x * 1e12) for k, x in enumerate(v))


def main():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    names = list(fe.FILTERS)
    fig, axs = plt.subplots(1, 4, figsize=(21, 4.8))
    for ax, name in zip(axs, names):
        kind, fp, fs, ilmax, rej, q, cpar, _ = fe.FILTERS[name]
        vi = ideal(name)
        vs = snapped(name, vi)
        print(name)
        print("  ideal   %s\n          loss <= %.2f dB, return loss >= %.1f dB, rejection >= %.1f dB" % ((fmt(vi, name),) + metrics(name, vi)))
        print("  parts   %s\n          loss <= %.2f dB, return loss >= %.1f dB, rejection >= %.1f dB" % ((fmt(vs, name),) + metrics(name, vs)))
        for tight in (True, False):
            il, rl, rj = monte_carlo(name, vs, tight)
            tag = "tight (B/G)" if tight else "loose (C/J)"
            print("  MC %s: loss p99 %.2f dB (mask %.1f), return loss p1 %.1f dB, rejection p1 %.1f dB (mask %d), "
                  "yield %.1f %%" % (tag, np.percentile(il, 99), ilmax, np.percentile(rl, 1), np.percentile(rj, 1), rej,
                                     100 * np.mean((il <= ilmax) & (rj >= rej))))
        f = np.linspace(20e6, (900e6 if fp[1] < 300e6 else 1500e6) if kind == "lpf" else 300e6, 1500)
        rng = np.random.default_rng(7)
        for i in range(60):
            w = vs.copy()
            for k in range(len(w)):
                if k in inds(name):
                    w[k] *= 1 + rng.uniform(-0.02, 0.02)
                elif w[k] < 10e-12:
                    w[k] += rng.uniform(-0.1e-12, 0.1e-12)
                else:
                    w[k] *= 1 + rng.uniform(-0.02, 0.02)
            ax.plot(f / 1e6, 20 * np.log10(np.abs(response(name, w, f)[0])), color="#9fb8d6", lw=0.5, alpha=0.6)
        ax.plot(f / 1e6, 20 * np.log10(np.abs(response(name, vs, f)[0])), color="#1f4e79", lw=1.6, label="catalogue values")
        ax.axvspan(fp[0] / 1e6, fp[1] / 1e6, color="#c6e0b4", alpha=0.4, label="pass band")
        for a_, b_ in fs:
            ax.fill_between([a_ / 1e6, min(b_, f[-1]) / 1e6], -rej, -rej - 40, color="#f4b183", alpha=0.35)
        ax.axhline(-rej, color="#c55a11", lw=0.8, ls="--", label=f"−{rej} dB mask")
        ax.set_ylim(-100, 3); ax.set_xlim(f[0] / 1e6, f[-1] / 1e6)
        ax.set_xlabel("MHz"); ax.set_ylabel("S21 (dB)"); ax.grid(lw=0.3)
        ax.set_title(name.split(":")[0] + ": " + name.split(":")[1].strip(), fontsize=9)
        ax.legend(fontsize=7, loc="lower left")
    fig.suptitle("Rev08 front-end filters with catalogue parts: nominal (dark) and 60 Monte Carlo samples, "
                 "L ±2 %, C ±0.1 pF / ±2 %, pads 0.10 ± 0.05 pF", fontsize=10)
    plt.tight_layout()
    out = __file__.replace("\\", "/").rsplit("/_work/", 1)[0] + "/docs/img/rev08_filters_mc.png"
    plt.savefig(out, dpi=130)
    print("figure:", out)


if __name__ == "__main__":
    main()
