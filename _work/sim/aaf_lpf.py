#!/usr/bin/env python3
"""
The anti-alias low-pass on IF_RX_C (J951 -> AD9253 channel B), SIGNAL_INTEGRITY section 9.8.

The AD9253 runs at 62.5 MSPS (50 MSPS with the 400 MHz master): everything above 31.25 MHz that reaches it folds
into the HF band. This is a 7th-order elliptic (Cauer) ladder between 50 ohm at both ends (the SMA side, and the
64.9 ohm termination in parallel with the AD8352's input on the ADC side):

    in -- C1 --+-- L2 || C2 --+-- C3 --+-- L4 || C4 --+-- C5 --+-- L6 || C6 --+-- C7 -- out
         (shunt)                (shunt)                 (shunt)                  (shunt)

The element values are optimised for the mask below with the inductors' loss (Q) included, then snapped to
E24 values and checked by Monte Carlo over the fitted parts' tolerances (L951 +-5 %, L952/L953 +-2 %, the C0G
capacitors +-5 % or 0.1 pF, inductor Q 30-45).

Mask: loss <= 0.8 dB to 27 MHz and <= 1.5 dB at 30 MHz, return loss >= 15 dB; >= 42 dB from 42 MHz, >= 62 dB from
50 MHz to 600 MHz (targets of the optimiser; the snapped, toleranced result is what is printed).

Usage:  py _work/sim/aaf_lpf.py [--design]   checks the fitted values; writes docs/sim/aaf_lpf.png and .csv
"""
import os, sys, math
import numpy as np
from scipy.optimize import minimize

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
R0 = 50.0
Q_L = 35.0          # 0805 wirewound (LQW2BAS, SDWL2012C): DCR 0.7-1.4 ohm, so Q about 35-45 at 30 MHz
SRF = {}            # filled after snapping: self-resonance of each inductor (parallel C)

E24 = [1.0, 1.1, 1.2, 1.3, 1.5, 1.6, 1.8, 2.0, 2.2, 2.4, 2.7, 3.0, 3.3, 3.6, 3.9, 4.3, 4.7, 5.1, 5.6, 6.2, 6.8,
       7.5, 8.2, 9.1]
# LQW18AN values Murata makes in 0603 (nH)
LQW = [100, 110, 120, 150, 180, 220, 270, 330, 390, 470]


def snap(v, series):
    d = 10 ** math.floor(math.log10(v))
    cands = [s * d for s in series] + [s * d * 10 for s in series]
    return min(cands, key=lambda c: abs(math.log(c / v)))


def s21(vals, f, q=Q_L, cpar=0.0):
    """vals = C1, L2, C2, C3, L4, C4, C5, L6, C6, C7 (F, H). ABCD cascade; returns S21, S11."""
    C1, L2, C2, C3, L4, C4, C5, L6, C6, C7 = vals
    w = 2 * np.pi * f
    one = np.ones_like(w, dtype=complex)

    def shunt(C):
        Y = 1j * w * C
        return [one, 0 * one, Y, one]

    def series(L, C):
        ZL = 1j * w * L + w * L / q
        YC = 1j * w * (C + cpar)
        Z = 1 / (1 / ZL + YC)
        return [one, Z, 0 * one, one]

    def mul(M, N):
        a, b, c, d = M; e, f_, g, h = N
        return [a * e + b * g, a * f_ + b * h, c * e + d * g, c * f_ + d * h]

    M = shunt(C1)
    for blk in (series(L2, C2), shunt(C3), series(L4, C4), shunt(C5), series(L6, C6), shunt(C7)):
        M = mul(M, blk)
    A, B, C, D = M
    den = A + B / R0 + C * R0 + D
    return 2 / den, (A + B / R0 - C * R0 - D) / den


FP = np.linspace(0.1e6, 30e6, 120)
FS1 = np.linspace(42e6, 50e6, 30)
FS2 = np.geomspace(50e6, 600e6, 160)


def cost(x):
    vals = np.exp(x)
    a, r = s21(vals, FP)
    il = -20 * np.log10(np.abs(a)); rl = -20 * np.log10(np.abs(r) + 1e-12)
    s1 = -20 * np.log10(np.abs(s21(vals, FS1)[0])); s2 = -20 * np.log10(np.abs(s21(vals, FS2)[0]))
    lim = np.where(FP <= 27e6, 0.8, 1.5)
    c = np.sum(np.maximum(il - lim, 0) ** 2) + np.sum(np.maximum(15 - rl, 0) ** 2) * 0.3
    c += np.sum(np.maximum(42 - s1, 0) ** 2) + np.sum(np.maximum(62 - s2, 0) ** 2)
    return c


def design():
    # start: Butterworth 7th order at 33 MHz, zeros near 41, 52 and 90 MHz
    fc = 33e6; wc = 2 * np.pi * fc
    g = [0.445, 1.247, 1.802, 2.0, 1.802, 1.247, 0.445]
    C = lambda gi: gi / (wc * R0); L = lambda gi: gi * R0 / wc
    zc = lambda Lv, fz: 1 / ((2 * np.pi * fz) ** 2 * Lv)
    L2, L4, L6 = L(g[1]), L(g[3]), L(g[5])
    x0 = [C(g[0]), L2, zc(L2, 52e6), C(g[2]), L4, zc(L4, 41e6), C(g[4]), L6, zc(L6, 90e6), C(g[6])]
    best = None
    for trial in range(12):
        rng = np.random.default_rng(trial)
        x = np.log(np.array(x0)) + (rng.normal(0, 0.25, 10) if trial else 0)
        r = minimize(cost, x, method="Nelder-Mead", options={"maxiter": 40000, "maxfev": 40000, "xatol": 1e-5, "fatol": 1e-9})
        r = minimize(cost, r.x, method="Powell", options={"maxiter": 40000})
        if best is None or r.fun < best.fun: best = r
    return np.exp(best.x), best.fun


def snapped(vals):
    """Inductors to the nearest LQW18AN value, then the capacitors re-optimised around them, then to E24."""
    v = list(vals)
    for k in (1, 4, 7):
        v[k] = min(LQW, key=lambda c: abs(math.log(c / (vals[k] * 1e9)))) * 1e-9
    caps = [0, 2, 3, 5, 6, 8, 9]

    def cc(x):
        w = list(v)
        for k, xi in zip(caps, x): w[k] = math.exp(xi)
        return cost(np.log(w))
    r = minimize(cc, [math.log(v[k]) for k in caps], method="Nelder-Mead", options={"maxiter": 20000, "maxfev": 20000})
    r = minimize(cc, r.x, method="Powell")
    for k, xi in zip(caps, r.x): v[k] = snap(math.exp(xi) * 1e12, E24) * 1e-12
    return v


def report(vals, label):
    f = np.array([1e6, 10e6, 20e6, 25e6, 30e6, 35e6, 40e6, 45e6, 50e6, 54e6, 62.5e6, 88e6, 100e6, 108e6, 146e6, 200e6, 433e6])
    a, r = s21(vals, f)
    print(label)
    for fi, ai, ri in zip(f, a, r):
        print(f"  {fi/1e6:7.1f} MHz  S21 {20*np.log10(abs(ai)):7.1f} dB  RL {-20*np.log10(abs(ri)):5.1f} dB")


# The values fitted on the board (C953, L951, C954, C955, L952, C956, C957, L953, C958, C959): the design run of
# 15 Nov (--design re-runs it) snapped to E24 and to the inductors that are stocked.
FITTED = [82e-12, 220e-9, 47e-12, 150e-12, 270e-9, 39e-12, 160e-12, 330e-9, 10e-12, 100e-12]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    names = ["C1", "L2", "C2", "C3", "L4", "C4", "C5", "L6", "C6", "C7"]
    if "--design" in sys.argv:
        vals, c = design()
        print("optimised (cost %.3g):" % c, ", ".join(f"{n} {v*1e9:.1f} nH" if n[0] == "L" else f"{n} {v*1e12:.2f} pF"
                                                      for n, v in zip(names, vals)))
        report(vals, "optimised")
        sv0 = snapped(vals)
        print("snapped:", ", ".join(f"{n} {v*1e9:.0f} nH" if n[0] == "L" else f"{n} {v*1e12:.3g} pF" for n, v in zip(names, sv0)))
    sv = FITTED
    report(sv, "fitted values")
    # Monte Carlo
    rng = np.random.default_rng(1)
    f = np.concatenate([np.linspace(0.1e6, 30e6, 60), np.linspace(42e6, 50e6, 9), np.geomspace(50e6, 600e6, 60)])
    worst_il = []; worst_s1 = []; worst_s2 = []; worst_rl = []
    for _ in range(2000):
        v = []
        for k, x in enumerate(sv):
            if k in (1, 4, 7): v.append(x * (1 + rng.uniform(-1, 1) * (0.05 if k == 1 else 0.02)))
            else: v.append(x + max(x * 0.05, 0.1e-12) * rng.uniform(-1, 1))
        a, r = s21(v, f, q=rng.uniform(30, 45))
        db = -20 * np.log10(np.abs(a))
        worst_il.append(db[:60].max()); worst_rl.append((-20 * np.log10(np.abs(r[:60]))).min())
        worst_s1.append(db[60:69].min()); worst_s2.append(db[69:].min())
    print(f"Monte Carlo 2000: passband loss max {max(worst_il):.2f} dB (p99 {np.percentile(worst_il,99):.2f}); "
          f"RL min {min(worst_rl):.1f} dB; 42-50 MHz min {min(worst_s1):.1f} dB; 50-600 MHz min {min(worst_s2):.1f} dB")
    import csv
    ff = np.geomspace(0.1e6, 1e9, 600)
    a, r = s21(sv, ff)
    with open(os.path.join(ROOT, "docs", "sim", "aaf_lpf.csv"), "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["f_Hz", "S21_dB", "S11_dB"])
        for fi, ai, ri in zip(ff, a, r): w.writerow([f"{fi:.6g}", f"{20*np.log10(abs(ai)):.3f}", f"{20*np.log10(abs(ri)):.3f}"])
    try:
        import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(8, 4.2), dpi=150)
        ax.semilogx(ff / 1e6, 20 * np.log10(np.abs(a)), color="#1f4e79", lw=2, label="|S21|, fitted values, inductor Q 35")
        ax.semilogx(ff / 1e6, 20 * np.log10(np.abs(r)), color="#9aa5b1", lw=1.2, label="|S11|")
        ax.axvspan(0.1, 30, color="#2e7d32", alpha=0.06); ax.axvspan(88, 108, color="#c62828", alpha=0.07)
        ax.axvline(31.25, color="#555", ls=":", lw=1)
        ax.text(31.8, -95, "Nyquist at 62.5 MSPS", fontsize=7, color="#555", rotation=90, va="bottom")
        ax.text(90, -8, "FM\nbroadcast", fontsize=7, color="#c62828")
        ax.set_xlim(0.1, 1000); ax.set_ylim(-100, 3); ax.grid(True, which="both", alpha=0.25)
        ax.set_xlabel("Frequency (MHz)"); ax.set_ylabel("dB")
        ax.set_title("IF_RX_C anti-alias low-pass (J951 → AD9253 channel B), 7th-order elliptic", fontsize=10)
        ax.legend(loc="lower left", fontsize=8); fig.tight_layout()
        fig.savefig(os.path.join(ROOT, "docs", "sim", "aaf_lpf.png")); print("wrote docs/sim/aaf_lpf.png")
    except ImportError:
        pass


if __name__ == "__main__":
    main()
