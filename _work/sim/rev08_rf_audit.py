#!/usr/bin/env python3
"""
Rev08 RF audit (18 November 2026): the VHF/UHF converter's preselection, checked for what it lets reach the
mixer besides the wanted band, and the high-pass that fixes it (docs/AUDIT_Rev08.md, R1). Uses the drawn values and
the filter models of rev08_filters_mc.py (lossy inductors, pad capacitance) and the RFFC5072 data sheet's leakage
plots (DS140110 p.22).

    python _work/sim/rev08_rf_audit.py         # seconds; docs/sim/rf_audit_uhf_path.png and docs/sim/rf_audit.json
    python _work/sim/rev08_rf_audit.py --hpf   # also re-optimise the high-pass from scratch (about a minute)

What it computes:
  1  the UHF low-pass (preselector B, RF1) and the anti-alias low-pass with the parts as drawn
  2  the 300 MHz high-pass ahead of preselector B (C1441-C1445, L1441-L1442): a 5th-order elliptic ladder, series C,
     shunt L + C, series C, shunt L + C, series C; its catalogue values and a 3,000-run tolerance Monte Carlo
     (L +-2 %, C +-0.1 pF below 10 pF else +-2 %, pads 0.05-0.15 pF, inductor Q 35-55, capacitor ESL 0.30-0.45 nH,
     0.25 nH to ground in each shunt branch)
  3  every mixer response m x LO - n x RF = IF (IF 135 MHz, m <= 4, n <= 4) for 446 MHz, with and without the high-pass
  4  IF rejection: a signal already at the IF (100-170 MHz: FM broadcast's top, airband, 2 m, marine, PMR) leaks to
     the mixer's output at its RF-to-IF isolation; the high-pass now takes it off before the mixer
  5  the LO: where it falls at the ADC, and an estimate of what leaves the antenna
"""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rev08_frontend as fe  # noqa: E402
import rev08_filters_mc as mc  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(ROOT, "docs", "sim")
sys.stdout.reconfigure(encoding="utf-8")
p, n = 1e-12, 1e-9
UHF = [6.2 * p, 22 * n, 1.8 * p, 6.8 * p, 27 * n, 2 * p, 6.8 * p, 22 * n, 0.4 * p, 1.3 * p]       # RX_VU_SPEC 1.3
AA = [11 * p, 56 * n, 5.6 * p, 22 * p, 62 * n, 7.5 * p, 24 * p, 75 * n, 1.2 * p, 20 * p]
HP300 = [11 * p, 24 * n, 36 * p, 5.6 * p, 22 * n, 91 * p, 8.2 * p]   # C1441, L1441 + C1442, C1443, L1442 + C1444, C1445
NAMES = {k.split(":")[0]: k for k in fe.FILTERS}
IF = 135.0
LNA_DB, SW_DB, CONV_DB = 22.0, 2.0, -4.0      # SPF5043Z at 100-500 MHz; switches to the mixer; RFFC5072 + baluns
ISO_RF_IF = (35.0, 50.0)                      # mixer RF-to-IF isolation at the IF [E]: the data sheet plots 45-60 dB
                                              # from 500 MHz up (0 dBm in, MIX2_IDD 4); none below 500 MHz
LO_LEAK_IF = -38.0                            # LO at the mixer output, dBm (DS140110 p.22, 400-1600 MHz) [V plot]
LO_LEAK_RF = -45.0                            # LO at the mixer input port [E: not in the data sheet]
LNA_S12 = 25.0                                # SPF5043Z reverse isolation, dB [E]
FLOOR_12K5 = -129.0                           # converted UHF noise floor in 12.5 kHz (REV08_PLAN 5.5)
R0, QL, CP, CPAD = 50.0, 45.0, 0.12e-12, 0.10e-12


def rej(name, v, f_mhz):
    f = np.atleast_1d(np.asarray(f_mhz, float)) * 1e6
    return -20 * np.log10(np.abs(mc.response(NAMES[name], v, f)[0]))


def hp_s(v, f_hz, cpad=CPAD, q=QL, esl=0.35e-9):
    """S21, S11 of the 5th-order elliptic high-pass: series C (with ESL), shunt (L || self-C) + C + 0.25 nH via."""
    w = 2 * np.pi * np.atleast_1d(f_hz); one = np.ones_like(w, dtype=complex)
    se = lambda C: [one, 1 / (1j * w * C) + 1j * w * esl, 0 * one, one]

    def sh(L, C):
        zl = 1 / (1 / (1j * w * L + w * L / q) + 1j * w * CP)
        return [one, 0 * one, 1 / (zl + 1 / (1j * w * C) + 1j * w * 0.25e-9) + 1j * w * cpad, one]
    C1, L2, C2, C3, L4, C4, C5 = v
    M = se(C1)
    for b in (sh(L2, C2), se(C3), sh(L4, C4), se(C5)):
        M = fe._mul(M, b)
    A, B, C, D = M; den = A + B / R0 + C * R0 + D
    return 2 / den, (A + B / R0 - C * R0 - D) / den


def hp_rej(f_mhz, v=HP300, **k):
    return -20 * np.log10(np.abs(hp_s(v, np.atleast_1d(np.asarray(f_mhz, float)) * 1e6, **k)[0]))


def hp_metrics(v, **k):
    FP, FS = np.linspace(300e6, 3000e6, 120), np.linspace(30e6, 175e6, 80)
    a, r = hp_s(v, FP, **k)
    return ((-20 * np.log10(np.abs(a))).max(), (-20 * np.log10(np.abs(r) + 1e-12)).min(),
            (-20 * np.log10(np.abs(hp_s(v, FS, **k)[0]))).min())


def hp_monte_carlo(v=HP300, runs=3000, seed=7):
    rng = np.random.default_rng(seed); out = []
    for _ in range(runs):
        x = list(v)
        for i in (1, 4):
            x[i] *= 1 + rng.uniform(-0.02, 0.02)
        for i in (0, 2, 3, 5, 6):
            x[i] = x[i] + rng.uniform(-0.1e-12, 0.1e-12) if x[i] < 10e-12 else x[i] * (1 + rng.uniform(-0.02, 0.02))
        out.append(hp_metrics(x, cpad=rng.uniform(0.05e-12, 0.15e-12), q=rng.uniform(35, 55),
                              esl=rng.uniform(0.30e-9, 0.45e-9)))
    a = np.array(out)
    return np.percentile(a[:, 0], 99), np.percentile(a[:, 1], 1), np.percentile(a[:, 2], 1)


def hp_design():
    """Optimise the ladder from scratch (the values were snapped to E24 / LQW15AN and the capacitors re-fitted)."""
    from scipy.optimize import minimize
    FP, FS = np.linspace(300e6, 3000e6, 120), np.linspace(30e6, 175e6, 80)

    def cost(lx):
        v = np.exp(lx); a, r = hp_s(v, FP)
        il = -20 * np.log10(np.abs(a)); rl = -20 * np.log10(np.abs(r) + 1e-12)
        s = -20 * np.log10(np.abs(hp_s(v, FS)[0]))
        return np.sum(np.maximum(il - 1.2, 0) ** 2) + 0.3 * np.sum(np.maximum(13 - rl, 0) ** 2) + np.sum(np.maximum(52 - s, 0) ** 2)
    best = None
    for t in range(20):
        rng = np.random.default_rng(t)
        x0 = np.log([10e-12, 30e-9, 30e-12, 5e-12, 25e-9, 50e-12, 10e-12]) + rng.normal(0, 0.5, 7)
        r = minimize(cost, x0, method="Nelder-Mead", options={"maxiter": 20000, "maxfev": 20000})
        r = minimize(cost, r.x, method="Powell")
        if best is None or r.fun < best.fun:
            best = r
    return np.exp(best.x)


def spurs(rf, with_hp):
    lo = rf + IF
    out = []
    for m in range(0, 5):
        for k in range(1, 5):
            for s in (+1, -1):
                f = (m * lo + s * IF) / k
                if f <= 20 or (m == 1 and k == 1) or abs(f - rf) < 1:
                    continue
                a = float(rej("UHF", UHF, f)[0]) + (float(hp_rej(f)[0]) if with_hp else 0.0)
                out.append((m, k, round(f, 1), a))
    return sorted(set(out), key=lambda r: r[3])


def main():
    res = {}
    if "--hpf" in sys.argv:
        v = hp_design()
        print("high-pass re-optimised (ideal): " + ", ".join("%.3g pF" % (x / p) if x < 1e-9 else "%.3g nH" % (x / n) for x in v)
              + "; loss %.2f dB, return loss %.1f dB, stop %.1f dB" % hp_metrics(v))
    f = np.linspace(20, 2500, 2000)
    r_uhf, r_aa, r_hp = rej("UHF", UHF, f), rej("AA200", AA, f), hp_rej(f)
    il, rl, st = hp_metrics(HP300)
    il99, rl1, st1 = hp_monte_carlo()
    print("300 MHz high-pass as drawn (C1441 11p, L1441 24n + C1442 36p, C1443 5.6p, L1442 22n + C1444 91p, C1445 8.2p)")
    print("  nominal: loss <= %.2f dB from 300 MHz to 3 GHz, return loss >= %.1f dB, rejection >= %.1f dB below 175 MHz" % (il, rl, st))
    print("  Monte Carlo, 3,000 boards: loss p99 %.2f dB, return loss p1 %.1f dB, rejection p1 %.1f dB" % (il99, rl1, st1))
    res["hp300"] = dict(loss_db=round(il, 2), rl_db=round(rl, 1), stop_db=round(st, 1), loss_p99=round(il99, 2),
                        rl_p1=round(rl1, 1), stop_p1=round(st1, 1))
    print("\nPreselector B's UHF path: rejection, before (low-pass alone) and now (high-pass + low-pass)")
    pts = [88, 100, 108, 118, 137, 145, 156, 170, 200, 250, 300, 390, 446, 480, 500, 513.5, 530, 581, 616, 660, 716, 1000]
    tab = {}
    for x in pts:
        a, b = float(rej("UHF", UHF, x)[0]), float(rej("UHF", UHF, x)[0] + hp_rej(x)[0])
        tab[str(x)] = (round(a, 1), round(b, 1))
        print("  %7.1f MHz  %5.1f dB  ->  %5.1f dB" % (x, a, b))
    res["uhf_path_db"] = tab

    print("\nIF REJECTION in converted mode (signals at 100-170 MHz)")
    hp_if = float(hp_rej(np.linspace(100, 170, 71)).min())
    ifr = []
    for iso in ISO_RF_IF:
        before = iso + CONV_DB
        now = before + hp_if
        ifr.append((before, now))
        print("  mixer isolation %2.0f dB: IF rejection %2.0f dB before, %3.0f dB with the high-pass (>= %.1f dB at 100-170 MHz);"
              " a -30 dBm FM or airband carrier at the antenna was %2.0f dB above the 12.5 kHz floor, now %3.0f dB above it"
              % (iso, before, now, hp_if, -30 - before - FLOOR_12K5, -30 - now - FLOOR_12K5))
    res["if_rejection_db"] = ifr
    print("  converted coverage now starts at 300 MHz; 170-300 MHz is not covered (direct sampling ends at 170 MHz)")

    print("\nMIXER RESPONSES, tuned 446 MHz: preselection before -> now, those under 40 dB before")
    sb, sn = spurs(446, False), {(m, k, fr): a for m, k, fr, a in spurs(446, True)}
    for m, k, fr, a in sb:
        if a < 40:
            print("  %dx%d  %7.1f MHz  %5.1f dB -> %5.1f dB" % (m, k, fr, a, sn[(m, k, fr)]))
    res["spurs_446"] = [dict(m=m, n=k, f_mhz=fr, before_db=round(a, 1), now_db=round(sn[(m, k, fr)], 1))
                        for m, k, fr, a in sb if a < 40]
    h = 446 + IF / 2
    print("  half-IF (2x2) at %.1f MHz: %.1f dB (the high-pass adds %.1f dB there); DVB-T channel 26 sits on it"
          % (h, rej("UHF", UHF, h)[0], hp_rej(h)[0]))

    print("\nLO")
    for rf in (390, 446, 1090):
        lo = rf + IF if rf < 1000 else rf - IF
        a = rej("AA200", AA, lo)[0]
        al = fe.alias(lo * 1e6) / 1e6
        lvl = LO_LEAK_IF - a + 21.0              # through the anti-alias filter and the IF amplifier, at IF_VU
        print("  tuned %4d MHz, LO %4d MHz: at the mixer output %.0f dBm, anti-alias %.0f dB, at IF_VU %.0f dBm "
              "(%.0f dBFS against -17.6 dBm full scale), aliased to %.0f MHz %s"
              % (rf, lo, LO_LEAK_IF, a, lvl, lvl + 17.6, al, "(inside 100-170 MHz)" if 100 <= al <= 170 else ""))
    for path, att in (("UHF low-pass, LO 581 MHz", float(rej("UHF", UHF, 581)[0])), ("LFCN-1000+ path, LO 735 MHz", 1.0)):
        print("  LO out of J961 (%s): LNA in %.0f dBm, LNA bypassed %.0f dBm [E]; receiver spurious limit -57 dBm below 1 GHz"
              % (path, LO_LEAK_RF - att - SW_DB - LNA_S12, LO_LEAK_RF - att - SW_DB - 1.0))
    with open(os.path.join(OUT, "rf_audit.json"), "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(10, 4.6))
    ax.plot(f, -r_uhf, c="#c0392b", lw=1.0, ls="--", label="UHF path before the audit: low-pass alone")
    ax.plot(f, -(r_uhf + r_hp), c="#2a78b5", lw=1.6, label="UHF path now: 300 MHz high-pass + low-pass")
    ax.plot(f, -r_hp, c="#16a085", lw=0.9, ls=":", label="the high-pass alone (also ahead of the SAW and LTCC paths)")
    ax.plot(f, -r_aa, c="#7f8c8d", lw=0.9, ls="-.", label="anti-alias low-pass (after the mixer)")
    ax.axvspan(100, 170, color="#c0392b", alpha=0.10)
    ax.text(112, -22, "IF window\n100-170 MHz", fontsize=7, color="#c0392b")
    ax.axvspan(400, 480, color="#27ae60", alpha=0.15); ax.text(405, -75, "wanted\n400-480", fontsize=7, color="#1e8449")
    ax.axvline(446 + IF / 2, c="#8e44ad", lw=0.8, ls=":"); ax.text(518, -30, "half-IF of 446\n(2x2), 513.5 MHz", fontsize=7, color="#8e44ad")
    ax.axvspan(87.5, 108, color="#f39c12", alpha=0.12); ax.text(64, -22, "FM\nbroadcast", fontsize=7, color="#b9770e")
    ax.set_xscale("log"); ax.set_xlim(30, 2500); ax.set_ylim(-110, 3)
    ax.set_xlabel("MHz"); ax.set_ylabel("|S21| (dB)"); ax.grid(alpha=0.3, which="both")
    ax.set_title("Converted UHF mode: what the preselector lets reach the mixer, before and after the audit")
    ax.legend(fontsize=7, loc="lower left")
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "rf_audit_uhf_path.png"), dpi=130); plt.close(fig)
    print("\nwrote docs/sim/rf_audit_uhf_path.png and docs/sim/rf_audit.json")


if __name__ == "__main__":
    main()
