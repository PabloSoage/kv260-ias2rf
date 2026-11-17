#!/usr/bin/env python3
"""
Rev08 phase 6: J961's return loss, figure and numbers (SIGNAL_INTEGRITY 9.10).

Two parts, plotted together:
- the launch, from openEMS (j961_launch.py: j961_p5.csv, j961_fixed.csv, j961_j921.csv, j961_line.csv,
  0.1-3 GHz): the phase 5 copper, the phase 6 copper, the other SMAs' pattern (J921's) and the bare line;
- the bias tee's shunt branch (bias_tee.py): the drawn 56 nH + 1 uH and the chosen BLM15HD102SN1 + 1 uH, at
  their nominal values. The branch sits 4.65 mm from the SMA pad, about 1/30 of a wavelength at 1.1 GHz; it is
  taken at the same plane as the launch, and the two reflections are added in magnitude (the worst case of
  their phases).

Usage:  py _work/sim/j961_plot.py     writes docs/sim/j961_launch.png and prints the table
"""
import os
import sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bias_tee as bt                                    # noqa: E402

ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(ROOT, "docs", "sim", "j961_launch.png")
BAND = (25e6, 1.1e9)


def launch(case):
    d = np.loadtxt(os.path.join(ROOT, "docs", "sim", f"j961_{case}.csv"), delimiter=",", skiprows=1)
    return d[:, 0], d[:, 1], d[:, 2]


def db(x):
    return 20 * np.log10(np.maximum(x, 1e-9))


def main():
    bead = bt.fit_bead()
    des = bt.designs(bead)
    f = np.logspace(np.log10(25e6), np.log10(3e9), 600)
    tee = {k: 10 ** (bt.rl_db(fn(f, None) + bt.c1361(f)) / 20) for k, fn in
           (("drawn", des["drawn: LQW15AN56NG80 + LQW2BAS1R0J"]), ("chosen", des["chosen: BLM15HD102SN1 + LQW2BAS1R0J"]))}
    cases = {}
    for c in ("p5", "fixed", "j921", "line"):
        try:
            cases[c] = launch(c)
        except OSError:
            pass
    fig, ax = plt.subplots(figsize=(8.8, 5.0))
    ax.axvspan(BAND[0] / 1e9, BAND[1] / 1e9, color="#e8eef6", zorder=0, label="RX_VU band (25 MHz to 1.1 GHz)")
    style = {"p5": ("#b03030", "-", "launch, phase 5 copper"),
             "fixed": ("#2f6db3", "-", "launch, phase 6 copper (leg vias, fence, L1 pour)"),
             "j921": ("#2e8b57", "-", "the other SMAs' pattern (J921), bare line"),
             "line": ("#777777", ":", "bare 0.2 mm line (the set-up's floor)")}
    for c, (fl, s11, _) in cases.items():
        col, ls, lab = style[c]
        ax.plot(fl / 1e9, s11, color=col, ls=ls, lw=1.6, label=lab)
    for c, k, lab in (("p5", "drawn", "phase 5 launch + drawn bias tee (56 nH + 1 uH)"),
                      ("fixed", "chosen", "phase 6 launch + chosen bias tee (BLM15HD102SN1 + 1 uH)")):
        if c in cases:
            fl, s11, _ = cases[c]
            fm = fl[fl >= f[0]]
            tot = 10 ** (np.interp(fm, fl, s11) / 20) + np.interp(fm, f, tee[k])
            ax.plot(fm / 1e9, db(tot), color=style[c][0], ls="--", lw=1.2, label=lab)
    ax.axhline(-20, color="k", lw=0.6, ls=":")
    ax.set_xscale("log")
    ax.set_xlim(0.025, 3)
    ax.set_ylim(-60, 0)
    ax.set_xticks([0.025, 0.1, 0.3, 1, 3])
    ax.set_xticklabels(["0.025", "0.1", "0.3", "1", "3"])
    ax.set_xlabel("Frequency (GHz)")
    ax.set_ylabel("|S11| (dB)")
    ax.set_title("J961 (VHF/UHF antenna SMA): return loss, openEMS launch and bias tee")
    ax.grid(True, which="both", lw=0.3, alpha=0.6)
    ax.legend(fontsize=7.2, loc="lower right")
    fig.tight_layout()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    fig.savefig(OUT, dpi=150)
    pts = (100e6, 170e6, 300e6, 500e6, 1.0e9, 1.1e9, 2.0e9)
    print("|S11| dB              " + "  ".join(f"{x:>7s}" for x in ("100M", "170M", "300M", "500M", "1.0G", "1.1G", "2.0G")))
    for c, (fl, s11, s21) in cases.items():
        print(f"launch {c:14s} " + "  ".join(f"{np.interp(p, fl, s11):7.1f}" for p in pts))
    for k in tee:
        print(f"bias tee {k:12s} " + "  ".join(f"{db(np.interp(p, f, tee[k])):7.1f}" for p in pts))
    for c, (fl, s11, s21) in cases.items():
        b = (fl >= 0.1e9) & (fl <= BAND[1])
        print(f"launch {c:14s} worst |S11| in 0.1-1.1 GHz {s11[b].max():6.1f} dB at {fl[b][s11[b].argmax()] / 1e6:4.0f} MHz;"
              f" |S21| at 1.1 GHz {np.interp(1.1e9, fl, s21):5.2f} dB")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
