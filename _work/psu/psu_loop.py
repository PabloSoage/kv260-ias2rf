#!/usr/bin/env python3
"""
PSU board: small-signal stability of the LM5177 voltage loop and of the input filter.

1. Voltage loop, peak current mode (Ridley's model, as TI's own design equations assume: SNVSBU4F eq. 3-10):
     buck:  Gvc = (Ro / Ri) (1 + s/wz) / (1 + s/wp) Fh(s),                       wp = 1/(Ro C)
     boost: Gvc = (Ro (1-D) / (2 Ri)) (1 + s/wz)(1 - s/wrhp) / (1 + s/wp) Fh(s),  wp = 2/(Ro C),
            wrhp = Ro (1-D)^2 / L
     Fh = 1 / (1 + s/(wn Qp) + s^2/wn^2), wn = pi fsw, Qp = 1 / (pi (mc (1 - D') - 0.5)); Ri = A_CS R_CS
     compensator: gm (R_FBB / (R_FBB + R_FBT)) [(R_COMP + 1/(s C_COMP)) || 1/(s C_PCOMP)]
   at every input voltage (4.3 to 48 V) and load (1 W to the maximum): crossover, phase and gain margin.
2. Input filter (Middlebrook): the filter's output impedance seen by the converter (L2 with the bulk on node B,
   its 0.1 ohm ESR the damping, and the harness) against the converter's negative input impedance V^2 / P.

Writes docs/sim/psu_loop.json and docs/sim/psu_loop.png.

Usage:  py _work/psu/psu_loop.py
"""
import json
import math
import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import psu_params as P                                    # noqa: E402
import psu_design as D                                    # noqa: E402

ROOT = os.path.dirname(os.path.dirname(HERE))
OUT_JSON = os.path.join(ROOT, "docs", "sim", "psu_loop.json")
OUT_PNG = os.path.join(ROOT, "docs", "sim", "psu_loop.png")
F = np.logspace(1, np.log10(2e5), 1500)


def loop(vin, pout, v, comp):
    s = 2j * math.pi * F
    vout = P.VOUT
    ro = vout ** 2 / pout
    c, esr = D.COUT_EFF, D.COUT_ESR
    ri = P.LM5177["a_cs"] * v["R_CS"]
    fsw = v["fsw"]
    wn = math.pi * fsw
    mode = D.mode_of(vin, vout)
    wz = 1 / (esr * c)
    # slope compensation: the eq. 11 resistor gives half the dead-beat ramp; dead-beat is Se = Sf (falling slope)
    if mode == "boost" or mode == "buck-boost":
        d = max(1 - vin / vout, 0.05)
        sf = (vout - vin) / v["L"]                 # falling slope (boost)
        sn = vin / v["L"]
    else:
        d = vout / vin
        sf = vout / v["L"]
        sn = (vin - vout) / v["L"]
    se = 0.5 * vout / v["L"]                      # [E] a fixed ramp: half the buck dead-beat slope at 12 V
    mc = 1 + se / sn
    dp = (1 - d)
    qp = 1 / (math.pi * (mc * dp - 0.5)) if mc * dp > 0.5 else 10.0
    fh = 1 / (1 + s / (wn * qp) + (s / wn) ** 2)
    if mode == "buck":
        gvc = (ro / ri) * (1 + s / wz) / (1 + s * ro * c) * fh
    else:
        wrhp = ro * (1 - d) ** 2 / v["L"]
        gvc = (ro * (1 - d) / (2 * ri)) * (1 + s / wz) * (1 - s / wrhp) / (1 + s * ro * c / 2) * fh
    k = v["R_FBB"] / (v["R_FBB"] + v["R_FBT"])
    zc1 = comp["R_COMP"] + 1 / (s * comp["C_COMP"])
    zc = 1 / (1 / zc1 + s * comp["C_PCOMP"])
    t = P.LM5177["gm_ea"] * k * zc * gvc
    mag = 20 * np.log10(np.abs(t))
    ph = np.unwrap(np.angle(t)) * 180 / math.pi
    i = np.where(np.diff(np.sign(mag)) < 0)[0]
    fc = float(F[i[0]]) if len(i) else None
    pm = float(180 + ph[i[0]]) if len(i) else None
    j = np.where(np.diff(np.sign(ph + 180)) < 0)[0]
    gm_db = float(-mag[j[0]]) if len(j) else None
    return {"mode": mode, "fc_Hz": fc, "phase_margin_deg": pm, "gain_margin_dB": gm_db, "Qp": qp}, mag, ph


def input_filter(vin, pout):
    """Output impedance of the input network seen from the LM5177's VIN (node C), and |Zin| = V^2 / P."""
    s = 2j * math.pi * F
    import psu_transient as T
    z_src = P.R_HARNESS + T.R_M + s * T.L_H
    z_b = 1 / (s * T.C_BC + 1 / (T.ESR_E + 1 / (s * T.C_E)) + 1 / z_src)
    z_l2 = T.R_L2 + s * T.L2
    z_out = 1 / (s * T.C_C + 1 / (T.ESR_EC + 1 / (s * T.C_EC)) + 1 / (z_b + z_l2))
    zin = vin ** 2 / pout
    return np.abs(z_out), zin


def main():
    v = D.values()
    comp = D.compensation(v)
    res = {"compensation": comp, "cases": {}}
    loads = {"1 W": 1.0, "typ": D.P.P_ADAPTER["typ"] + D.P.P_KV260["typ"],
             "max": P.VOUT * (P.I_ADAPTER_MAX + P.I_KV_LIMIT)}
    fig, ax = plt.subplots(1, 3, figsize=(17, 5))
    worst_pm = 999
    for vin in (4.3, 6.0, 9.0, 13.5, 16.0, 24.0, 36.0, 48.0):
        for ln, p in loads.items():
            r, mag, ph = loop(vin, p, v, comp)
            res["cases"][f"{vin} V {ln}"] = r
            if r["phase_margin_deg"] is not None:
                worst_pm = min(worst_pm, r["phase_margin_deg"])
            if ln == "max" and vin in (4.3, 13.5, 48.0):
                ax[0].semilogx(F, mag, lw=1.6, label=f"{vin} V, {p:.0f} W ({r['mode']})")
                ax[1].semilogx(F, ph + 180, lw=1.6, label=f"{vin} V")
    res["worst_phase_margin_deg"] = worst_pm
    ax[0].axhline(0, color="k", lw=0.8)
    ax[0].set_ylim(-60, 80)
    ax[0].set_title("Voltage loop gain")
    ax[0].set_ylabel("dB")
    ax[1].axhline(45, color="k", lw=0.8, ls="--")
    ax[1].set_ylim(-90, 200)
    ax[1].set_title("Phase + 180 (the margin at crossover)")
    ax[1].set_ylabel("degrees")
    for a in ax[:2]:
        a.set_xlabel("Hz")
        a.grid(alpha=0.3, which="both")
        a.legend(fontsize=8)
    # Middlebrook
    filt = {}
    for vin, p in ((4.3, loads["max"]), (6.0, loads["max"]), (13.5, loads["max"]), (13.5, loads["typ"])):
        zo, zin = input_filter(vin, p / 0.9)
        k = f"{vin} V {p:.0f} W"
        filt[k] = {"zin_ohm": zin, "zout_peak_ohm": float(zo.max()), "f_peak_Hz": float(F[zo.argmax()]),
                   "margin_dB": float(20 * math.log10(zin / zo.max()))}
        ax[2].loglog(F, zo, lw=1.6, label=f"|Zout| filter")
        ax[2].axhline(zin, ls="--", lw=1, color=ax[2].lines[-1].get_color(), label=f"|Zin| conv, {k}")
        break
    for vin, p in ((6.0, loads["max"]), (13.5, loads["max"]), (13.5, loads["typ"])):
        zo, zin = input_filter(vin, p / 0.9)
        k = f"{vin} V {p:.0f} W"
        filt[k] = {"zin_ohm": zin, "zout_peak_ohm": float(zo.max()), "f_peak_Hz": float(F[zo.argmax()]),
                   "margin_dB": float(20 * math.log10(zin / zo.max()))}
        ax[2].axhline(zin, ls="--", lw=1, label=f"|Zin| conv, {k}")
    res["input_filter"] = filt
    ax[2].set_title("Input filter: |Zout| against the converter's |Zin| (Middlebrook)")
    ax[2].set_xlabel("Hz")
    ax[2].set_ylabel("ohm")
    ax[2].grid(alpha=0.3, which="both")
    ax[2].legend(fontsize=7)
    fig.suptitle("PSU board, LM5177: loop stability (psu_loop.py)")
    fig.tight_layout()
    fig.savefig(OUT_PNG, dpi=140)
    with open(OUT_JSON, "w") as fh:
        json.dump(res, fh, indent=1, default=float)
    for k, r in res["cases"].items():
        print(f"{k:14s} {r['mode']:10s} fc {r['fc_Hz'] and round(r['fc_Hz'])!s:>6} Hz  PM "
              f"{r['phase_margin_deg'] and round(r['phase_margin_deg'], 1)!s:>6}  GM {r['gain_margin_dB'] and round(r['gain_margin_dB'], 1)!s:>6} dB  Qp {r['Qp']:.2f}")
    print("worst phase margin", worst_pm)
    print("input filter", filt)
    print("compensation", comp)


if __name__ == "__main__":
    main()
