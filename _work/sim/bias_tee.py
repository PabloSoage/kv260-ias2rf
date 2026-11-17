#!/usr/bin/env python3
"""
Rev08 phase 6: J961's bias tee, the shunt branch across the antenna line (SIGNAL_INTEGRITY 9.10).

The branch runs from VU_ANT through L1302 and L1301 to VU_BIAS_OUT, which C1361 (100 nF) holds at RF ground.
Whatever it does not block is lost from the antenna signal: a shunt Z across 50 ohm costs |2Z / (2Z + 50)|.
Target (owner, 17 November): under 0.5 dB extra loss from 25 MHz to 1.1 GHz, with the bias on (up to the
AP22652's 155 mA limit).

Parts, each from its data sheet:
- LQW15AN56NG80 (the drawn 56 nH, 0402 wirewound): 56 nH +-2 %, Q >= 25 at 200 MHz, SRF >= 2.8 GHz
  (Murata LQW15AN table, 56N row: 2.8 GHz minimum), 340 mA.
- LQW2BAS1R0J00 (1 uH, 0805 wirewound): 1 uH +-5 %, Q >= 23 at 25 MHz, SRF >= 200 MHz, 170 mA, 2.4 ohm.
- BLM15HD102SN1 (1 kohm at 100 MHz, 0402 ferrite bead for GHz noise): 250 mA, 1.25 ohm. Its impedance curve
  (R and X, 1 MHz to 3 GHz, Murata data sheet 2012.9.6, page 3) is read by eye at the points in BEAD_PTS and
  fitted with two parallel L-R-C sections in series (least squares, scipy). The fit is below the curve by up to
  27 % at 50-100 MHz, which is on the safe side. A bead loses impedance with DC through it; at 155 mA of 250 mA
  it is taken anywhere from 40 % to 100 % of its curve, on top of its +-25 % tolerance.

Why the drawn pair fails: an inductor past its self-resonance is a capacitor. The 1 uH's own capacitance
(1 / (L (2 pi SRF)^2) = 0.16-0.63 pF for SRF 200-400 MHz) in series with the 56 nH resonates at
0.85-1.7 GHz: a series resonance is a short across the antenna line, and for any 1 uH with SRF below about
330 MHz it lands inside the band. The 56 nH's own SRF (2.8 GHz) is not the problem.

The fix: the 56 nH's place (L1302, 0402) takes the bead. Above 150 MHz the bead is a resistor of 1-2 kohm, so
nothing in the branch can resonate (the 1 uH's capacitance now sits in series with a resistor), and below
150 MHz the 1 uH carries the impedance (157 ohm at 25 MHz). Same footprints, same copper.

Monte Carlo, 3,000 draws per design, worst extra loss anywhere from 25 MHz to 1.1 GHz:
  the drawn 56 nH + 1 uH, and the bead + 1 uH chosen; plus two rejected: the bead + a 1 uH power inductor
  (DFE201210U-1R0M, SRF 80-250 MHz assumed, Q 4-15) and the bead alone (L1301 a 0 ohm link).

The same pattern elsewhere on RX_VU (the sweep of every choke on an RF line, phase 6):
- the SPF5043Z LNA's drain feed: L1304 (56 nH) from VU_LNA_OUT to VU_LNA_BIAS, where C1305 (100 pF) went to
  ground and L1303 (1 uH, 0603) to +3V0_RF. 56 nH in series with 100 pF to ground is a short at 67 MHz, right
  on the LNA's output: 21 dB at 67 MHz, 4.7 dB at 100 MHz. Fixed the same way: L1304 becomes FB1304,
  BLM15HD102SN1, and C1305 is not fitted (25 mA through the bead; derated as above all the same);
- the IF amplifier's drain choke L1305 (1 uH, 0603) straight to +3V0_RF: no series C, the rail's 100 nF puts
  the series resonance near 0.5 MHz; checked over the IF band, 25-170 MHz (the anti-alias low-pass ahead of
  it stops everything above);
- the filters' inductors are the filters (rev08_filters_mc.py), not chokes.
The 0603 1 uH (L1303, L1305) is AHW1608F-1R0KTF: 1 uH +-10 %, SRF 400 MHz, Q 12, 330 mA; taken as SRF
250-500 MHz, Q 8-20 at 25 MHz. Its rail end (+3V0_RF) is a 100 nF with 0.5 nH, as C1361.

Usage:  py _work/sim/bias_tee.py     prints the tables, writes docs/sim/bias_tee.png
"""
import os
import numpy as np
from scipy.optimize import least_squares
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(ROOT, "docs", "sim", "bias_tee.png")
F0, F1 = 25e6, 1.1e9
# BLM15HD102SN1: f (MHz), |Z| (ohm), R (ohm), read from the data sheet's curve
BEAD_PTS = [(1, 5, 0.5), (10, 75, 6), (30, 260, 35), (50, 460, 110), (100, 1000, 450), (150, 1170, 780),
            (300, 1500, 1300), (500, 1800, 1750), (800, 2150, 2150), (1000, 2100, 1950), (2000, 1300, 700),
            (3000, 800, 250)]
BEAD_RDC = 0.9                       # typical, of 1.25 maximum


def bead_model(p, f, k=1.0):
    """Two parallel L-R-C sections in series; k scales the ferrite's L and R (tolerance and DC bias)."""
    L1, R1, C1, L2, R2, C2 = p
    w = 2 * np.pi * f
    s1 = 1 / (1 / (1j * w * L1 * k) + 1 / (R1 * k) + 1j * w * C1)
    s2 = 1 / (1 / (1j * w * L2 * k) + 1 / (R2 * k) + 1j * w * C2)
    return BEAD_RDC + s1 + s2


def fit_bead():
    f = np.array([p[0] for p in BEAD_PTS]) * 1e6
    z = np.array([p[1] for p in BEAD_PTS], float)
    r = np.array([p[2] for p in BEAD_PTS], float)
    x = np.sqrt(np.maximum(z ** 2 - r ** 2, 0)) * np.where(f > 800e6, -1, 1)    # capacitive past the peak

    def res(q):
        m = bead_model(np.exp(q), f)
        return np.r_[(m.real - r) / z, (m.imag - x) / z]
    q = least_squares(res, np.log([0.6e-6, 600, 0.3e-12, 0.5e-6, 1800, 0.1e-12])).x
    return np.exp(q)


def inductor(f, L, srf, q, fq):
    """Inductor with its parallel capacitance (from the SRF) and a series loss giving Q at fq, rising as sqrt(f)."""
    w = 2 * np.pi * f
    c = 1 / (L * (2 * np.pi * srf) ** 2)
    z = 2 * np.pi * fq * L / q * np.sqrt(f / fq) + 1j * w * L
    return z / (1 + 1j * w * c * z)


def c1361(f):
    return 0.02 + 1j * 2 * np.pi * f * 0.5e-9 + 1 / (1j * 2 * np.pi * f * 100e-9)


def loss_db(z):
    """Extra insertion loss of a shunt impedance z across a 50 ohm line."""
    return -20 * np.log10(np.abs(2 * z / (2 * z + 50)))


def rl_db(z):
    return 20 * np.log10(np.abs(-50 / (2 * z + 50)))


def designs(bead):
    """Each design: a function of (f, rng or None) giving the branch impedance; None = nominal values."""
    def u(rng, a, b, nom):
        return nom if rng is None else rng.uniform(a, b)

    def drawn(f, rng):
        return (inductor(f, 56e-9 * u(rng, .98, 1.02, 1), u(rng, 2.8e9, 3.5e9, 3.0e9), 25, 200e6)
                + inductor(f, 1e-6 * u(rng, .95, 1.05, 1), u(rng, 200e6, 400e6, 250e6), u(rng, 23, 40, 28), 25e6))

    def k(rng):
        return u(rng, .75, 1.25, 1) * u(rng, .4, 1.0, .7)

    def chosen(f, rng):
        return (bead_model(bead, f, k(rng))
                + inductor(f, 1e-6 * u(rng, .95, 1.05, 1), u(rng, 200e6, 400e6, 250e6), u(rng, 23, 40, 28), 25e6))

    def power_l(f, rng):
        return bead_model(bead, f, k(rng)) + inductor(f, 1e-6 * u(rng, .8, 1.2, 1), u(rng, 80e6, 250e6, 150e6),
                                                      u(rng, 4, 15, 8), 25e6)

    def bead_only(f, rng):
        return bead_model(bead, f, k(rng)) + 0.05

    return {"drawn: LQW15AN56NG80 + LQW2BAS1R0J": drawn,
            "chosen: BLM15HD102SN1 + LQW2BAS1R0J": chosen,
            "rejected: BLM15HD102SN1 + DFE201210U-1R0M": power_l,
            "rejected: BLM15HD102SN1 alone": bead_only}


def lna_designs(bead):
    """The LNA's drain feed and the IF amplifier's choke, as designs() (f, rng)."""
    def u(rng, a, b, nom):
        return nom if rng is None else rng.uniform(a, b)

    def l0603(f, rng):
        return inductor(f, 1e-6 * u(rng, .9, 1.1, 1), u(rng, 250e6, 500e6, 400e6), u(rng, 8, 20, 12), 25e6)

    def c100p(f):
        return 0.3 + 1j * 2 * np.pi * f * 0.4e-9 + 1 / (1j * 2 * np.pi * f * 100e-12)

    def par(a, b):
        return a * b / (a + b)

    def drawn(f, rng):
        return (inductor(f, 56e-9 * u(rng, .98, 1.02, 1), u(rng, 2.8e9, 3.5e9, 3.0e9), 25, 200e6)
                + par(c100p(f), l0603(f, rng) + c1361(f)))

    def fixed(f, rng):
        return bead_model(bead, f, u(rng, .75, 1.25, 1) * u(rng, .4, 1.0, .7)) + l0603(f, rng) + c1361(f)

    def ifa(f, rng):
        return l0603(f, rng) + c1361(f)
    return {"LNA drawn: 56 nH + 100 pF || 1 uH": (drawn, 1.1e9),
            "LNA fixed: BLM15HD102SN1 + 1 uH, C1305 DNP": (fixed, 1.1e9),
            "IF amp L1305: 1 uH to the rail (25-170 MHz)": (ifa, 170e6)}


def main():
    bead = fit_bead()
    f = np.logspace(np.log10(F0), np.log10(F1), 500)
    rng = np.random.default_rng(1)
    d = designs(bead)
    print("bead fit: L1 %.3g H, R1 %.0f ohm, C1 %.3g F; L2 %.3g H, R2 %.0f ohm, C2 %.3g F" % tuple(bead))
    print(f"{'design':44s} {'nominal':>8s} {'p50':>7s} {'p99':>7s} {'max':>7s}  at   (extra loss, dB, 25 MHz-1.1 GHz)")
    mc = {}
    for name, fn in d.items():
        nom = loss_db(fn(f, None) + c1361(f))
        w = []
        for _ in range(3000):
            x = loss_db(fn(f, rng) + c1361(f))
            w.append((x.max(), f[x.argmax()]))
        a = np.array(w)
        mc[name] = a
        i = a[:, 0].argmax()
        print(f"{name:44s} {nom.max():8.2f} {np.median(a[:, 0]):7.2f} {np.percentile(a[:, 0], 99):7.2f} "
              f"{a[i, 0]:7.2f}  {a[i, 1] / 1e6:5.0f} MHz")
    print()
    for name, (fn, ftop) in lna_designs(bead).items():
        fl = np.logspace(np.log10(F0), np.log10(ftop), 500)
        nom = loss_db(fn(fl, None))
        a = []
        for _ in range(3000):
            x = loss_db(fn(fl, rng))
            a.append((x.max(), fl[x.argmax()]))
        a = np.array(a)
        i = a[:, 0].argmax()
        print(f"{name:44s} {nom.max():8.2f} {np.median(a[:, 0]):7.2f} {np.percentile(a[:, 0], 99):7.2f} "
              f"{a[i, 0]:7.2f}  {a[i, 1] / 1e6:5.0f} MHz")
    # figure: nominal and 200 draws of the drawn and the chosen designs
    fig, ax = plt.subplots(1, 2, figsize=(11, 4.4))
    fp = np.logspace(np.log10(10e6), np.log10(3e9), 600)
    for name, col in (("drawn: LQW15AN56NG80 + LQW2BAS1R0J", "#b03030"),
                      ("chosen: BLM15HD102SN1 + LQW2BAS1R0J", "#2f6db3")):
        fn = d[name]
        r2 = np.random.default_rng(7)
        for j in range(200):
            z = fn(fp, r2) + c1361(fp)
            ax[0].plot(fp / 1e9, loss_db(z), color=col, lw=0.4, alpha=0.12)
            ax[1].plot(fp / 1e9, rl_db(z), color=col, lw=0.4, alpha=0.12)
        z = fn(fp, None) + c1361(fp)
        ax[0].plot(fp / 1e9, loss_db(z), color=col, lw=1.8, label=name)
        ax[1].plot(fp / 1e9, rl_db(z), color=col, lw=1.8, label=name)
    zb = bead_model(bead, fp)
    for a in ax:
        a.axvspan(F0 / 1e9, F1 / 1e9, color="#e8eef6", zorder=0)
        a.set_xscale("log")
        a.set_xlim(0.01, 3)
        a.set_xticks([0.01, 0.025, 0.1, 0.3, 1, 3])
        a.set_xticklabels(["0.01", "0.025", "0.1", "0.3", "1", "3"])
        a.set_xlabel("Frequency (GHz)")
        a.grid(True, which="both", lw=0.3, alpha=0.6)
    ax[0].axhline(0.5, color="k", lw=0.8, ls=":")
    ax[0].set_ylim(0, 3)
    ax[0].set_ylabel("Extra loss from the bias tee (dB)")
    ax[0].set_title("Shunt branch loss: nominal (bold) and 200 draws")
    ax[0].legend(fontsize=7.5, loc="upper left")
    ax[1].set_ylim(-60, 0)
    ax[1].set_ylabel("|S11| of the branch alone (dB)")
    ax[1].set_title("Its reflection")
    ax2 = ax[1].twinx()
    ax2.plot(fp / 1e9, np.abs(zb), color="#555555", lw=1.0, ls="--")
    ax2.plot([p[0] / 1e3 for p in BEAD_PTS], [p[1] for p in BEAD_PTS], "o", ms=3, color="#555555")
    ax2.set_ylabel("BLM15HD102SN1 |Z| (ohm): fit (dashed), data sheet (dots)", fontsize=8)
    ax2.set_ylim(0, 2500)
    fig.tight_layout()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    fig.savefig(OUT, dpi=150)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
