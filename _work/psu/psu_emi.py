#!/usr/bin/env python3
"""
PSU board: conducted emissions and the noise it puts on the two boards' supply.

1. Input (CISPR 25 voltage method): the LM5177's pulsed input current in buck mode (the worst case for input
   noise: the input sees the inductor current chopped at the duty cycle) as a trapezoid train, its harmonics through
   the input network (every capacitor with its ESR and ESL, L2 and L3 with their winding capacitance, U1's FETs, the 0.2 uF
   at J1, the harness) into the CISPR 25 artificial network (5 uH, 50 ohm). Common mode from SW1's dv/dt through
   C_PAR (0.5 pF [E], 2 pF shown as the sensitivity) to the reference plane. DRSS (+-7.8 %) spreads each harmonic over 2 x 7.8 % x k fsw; against the 9 kHz
   (below 30 MHz) or 120 kHz resolution bandwidth that lowers a peak reading by 10 log(spread / RBW) [E].
   Limits: CISPR 25 Class 5 peak, voltage method, as TI SLLA569B (April 2025) Table 3 gives them; average about
   20 dB lower (TI SSZT673). Check against the edition the vehicle maker specifies.
2. Output: the ripple on the +12V bus and at each output connector (after U3 / U4), the spectrum that reaches
   the adapter's and the KV260's input, in dBuV, 150 kHz to 108 MHz, the HF band (3 to 30 MHz) marked.

Writes docs/sim/psu_emi.json and docs/sim/psu_emi.png.

Usage:  py _work/psu/psu_emi.py
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
OUT_JSON = os.path.join(ROOT, "docs", "sim", "psu_emi.json")
OUT_PNG = os.path.join(ROOT, "docs", "sim", "psu_emi.png")

# SW1's and SW2's copper (about 1 cm2 on L1, the inductor's 17.8 x 16.9 mm terminals and core) 50 mm above the
# plane, the board's own ground planes under the switching copper: 0.5 pF [E]; the sensitivity is shown at 2 pF
C_PAR = 0.5e-12
LIMITS = [(0.15e6, 0.30e6, 70), (0.53e6, 1.8e6, 54), (5.9e6, 6.2e6, 53), (26e6, 28e6, 44), (30e6, 54e6, 44),
          (68e6, 87e6, 38), (76e6, 108e6, 38)]


def cap(f, c, esr, esl):
    w = 2 * math.pi * f
    return esr + 1j * w * esl + 1 / (1j * w * c)


def par(*z):
    return 1 / sum(1 / x for x in z)


def input_transfer(f):
    """Transfer impedance: a noise current injected at node C -> voltage across the 50 ohm LISN receiver."""
    w = 2 * math.pi * f
    zc = par(*([cap(f, 4.7e-6 * 0.7, 0.004, 0.8e-9)] * 4), cap(f, 200e-6, 0.15, 5e-9), cap(f, 0.1e-6, 0.02, 0.4e-9))
    zl2 = par(P.R_FILTER + 1j * w * 1.0e-6, 1 / (1j * w * 15e-12))
    zb = par(*([cap(f, 4.7e-6 * 0.7, 0.004, 0.8e-9)] * 2), cap(f, 47e-6, 0.6, 5e-9))
    # second stage after U1: L3 0.47 uH (winding 10 pF) and B0: 2 x 4.7 uF 100 V 1210 + 2 x 100 nF 0603
    zl3 = par(0.001 + 1j * w * 0.47e-6, 1 / (1j * w * 10e-12))
    zb0 = par(*([cap(f, 4.7e-6 * 0.7, 0.004, 0.8e-9)] * 2), *([cap(f, 0.1e-6, 0.02, 0.4e-9)] * 2))
    zb = par(*([cap(f, 4.7e-6 * 0.7, 0.004, 0.8e-9)] * 2), cap(f, 47e-6, 0.6, 5e-9))
    zm = 0.016 + 1j * w * 3e-9
    za = par(cap(f, 0.1e-6, 0.03, 0.6e-9), cap(f, 0.1e-6, 0.03, 0.6e-9))
    zh = 0.03 + 1j * w * 2e-6                          # harness to the LISN, both wires
    zlisn = par(1j * w * 5e-6, 50.0 + 1 / (1j * w * 0.1e-6))
    # ladder from the LISN back to node C
    z1 = zh + zlisn
    z2 = par(za, z1)
    z3 = zm + z2
    z3b = par(zb0, z3)                                 # node B0 (after U1)
    z3c = zl3 + z3b
    z4 = par(zb, z3c)                                  # node B (47 uF, LTC4364 OUT bypass)
    z5 = zl2 + z4
    z6 = par(zc, z5)
    v_c = z6                                          # per ampere injected
    i5 = v_c / z5
    v_b = i5 * z4
    i3c = v_b / z3c
    v_b0 = i3c * z3b
    i3 = v_b0 / z3
    v_a = i3 * z2
    i1 = v_a / z1
    i_rx = i1 * (1j * w * 5e-6) / (1j * w * 5e-6 + 50.0 + 1 / (1j * w * 0.1e-6))
    return np.abs(i_rx * 50.0)


def trapezoid(k, i_pk, duty, tr, fsw):
    """Fourier amplitude of harmonic k of a trapezoidal pulse train (amplitude i_pk, duty, equal edges tr)."""
    x1 = math.pi * k * duty
    x2 = math.pi * k * tr * fsw
    s1 = math.sin(x1) / x1 if x1 else 1.0
    s2 = math.sin(x2) / x2 if x2 else 1.0
    return 2 * i_pk * duty * abs(s1 * s2)


def spectrum(vin, pout, v, c_par=None):
    global C_PAR
    if c_par is not None:
        C_PAR = c_par
    op = D.operating_point(vin, pout, v=v)
    fsw = v["fsw"]
    f = fsw * np.arange(1, 271)                        # to 108 MHz
    if op["mode"] == "buck":
        i_pk, duty = op["il_avg"], op["duty"]
    else:                                              # boost / transition: the input current is the inductor's
        i_pk, duty = op["il_ripple"] / 2, 0.5          # ripple only (a triangle, less than this) [E]
    tr = 8e-9
    idm = np.array([trapezoid(k, i_pk, duty, tr, fsw) for k in range(1, 271)])
    vdm = idm * np.array([input_transfer(x) for x in f])
    # common mode: SW1 swings VIN with tr; C_PAR to the CISPR 25 ground plane; the current returns through both
    # artificial networks in parallel, so each receiver sees half of it across 50 ohm
    dvdt_amp = np.array([trapezoid(k, vin, duty, tr, fsw) for k in range(1, 271)])
    icm = dvdt_amp * 2 * math.pi * f * C_PAR
    vcm = icm / 2 * 50.0
    vtot = np.sqrt(vdm ** 2 + vcm ** 2)
    rbw = np.where(f < 30e6, 9e3, 120e3)
    spread = 2 * 0.078 * f
    drss = np.where(spread > rbw, 10 * np.log10(spread / rbw), 0.0)
    dbuv = 20 * np.log10(np.maximum(vtot, 1e-12) / 1e-6)
    return f, dbuv, dbuv - drss, op


def output_ripple(vin, pout, v):
    """Ripple at the output connectors: the inductor ripple current into the output network (6 x 22 uF, 2 x 100 uF
    polymer), then each eFuse (31 mOhm) and its 1 m cable into the board's own input capacitance."""
    op = D.operating_point(vin, pout, v=v)
    fsw = v["fsw"]
    k = np.arange(1, 271)
    f = fsw * k
    if op["mode"] == "buck":
        ia = np.array([8 * op["il_ripple"] / (math.pi ** 2 * n ** 2) if n % 2 else 0.0 for n in k])  # triangle
    else:                                              # boost: the output sees the pulsed diode current
        ia = np.array([trapezoid(n, op["il_avg"], 1 - op["duty"], 8e-9, fsw) for n in k])
    out = []
    for fr, i in zip(f, ia):
        zo = par(*([cap(fr, 22e-6 * 0.45, 0.003, 0.8e-9)] * 6), *([cap(fr, 100e-6, 0.025, 3e-9)] * 2))
        out.append(i * abs(zo))
    vbus = np.array(out)
    # to a board: 31 mOhm + 1 m cable (0.7 uH, 42 mOhm) into its 60 uF electrolytic + 10 uF ceramic [E]
    w = 2 * math.pi * f
    zline = 0.031 + 0.042 + 1j * w * 0.7e-6
    zload = np.array([abs(par(cap(x, 60e-6, 0.1, 5e-9), cap(x, 10e-6, 0.005, 1e-9))) for x in f])
    vboard = vbus * zload / np.abs(zline + zload)
    return f, 20 * np.log10(np.maximum(vbus, 1e-12) / 1e-6), 20 * np.log10(np.maximum(vboard, 1e-12) / 1e-6), op


def main():
    v = D.values()
    p_max = P.VOUT * (P.I_ADAPTER_MAX + P.I_KV_LIMIT)
    res = {"limits_class5_peak_dBuV": LIMITS, "cases": {}}
    fig, ax = plt.subplots(1, 2, figsize=(16, 5.2))
    for vin, col in ((13.5, "#b2182b"), (24.0, "#ef8a62")):
        f2, _, s2, _ = spectrum(vin, p_max, v, c_par=2e-12)
        ax[0].semilogx(f2 / 1e6, s2, "_", ms=4, color=col, alpha=0.5)
        f, raw, with_drss, op = spectrum(vin, p_max, v, c_par=0.5e-12)
        margins = []
        for lo, hi, lim in LIMITS:
            m = (f >= lo) & (f <= hi)
            if m.any():
                margins.append({"band_MHz": [lo / 1e6, hi / 1e6], "limit_pk": lim, "max_dBuV": float(with_drss[m].max()),
                                "margin_pk_dB": float(lim - with_drss[m].max()),
                                "margin_avg_dB": float(lim - 20 - with_drss[m].max())})
        m30 = f > 30e6
        res["cases"][f"input {vin} V {p_max:.0f} W"] = {"mode": op["mode"], "bands": margins,
                                                       "above_30MHz_max_with_2pF_dBuV": float(s2[m30].max())}
        ax[0].semilogx(f / 1e6, with_drss, ".", ms=3, color=col, label=f"{vin} V in, {p_max:.0f} W, DRSS on")
        ax[0].semilogx(f / 1e6, raw, ".", ms=1.5, color=col, alpha=0.35)
    for lo, hi, lim in LIMITS:
        ax[0].plot([lo / 1e6, hi / 1e6], [lim, lim], color="k", lw=2)
        ax[0].plot([lo / 1e6, hi / 1e6], [lim - 20, lim - 20], color="k", lw=1, ls="--")
    ax[0].set_xlabel("MHz")
    ax[0].set_ylabel("dBuV at the LISN")
    ax[0].set_title("Input: CISPR 25 voltage method (black: Class 5 peak, dashed: average; dashes: 2 pF)")
    ax[0].set_ylim(-20, 100)
    ax[0].grid(alpha=0.3, which="both")
    ax[0].legend(fontsize=8)
    for vin, col in ((13.5, "#2166ac"), (6.0, "#67a9cf")):
        f, vbus, vboard, op = output_ripple(vin, p_max, v)
        hf = (f >= 3e6) & (f <= 30e6)
        res["cases"][f"output {vin} V"] = {"mode": op["mode"], "bus_fund_dBuV": float(vbus[0]),
                                           "board_fund_dBuV": float(vboard[0]),
                                           "board_hf_max_dBuV": float(vboard[hf].max()),
                                           "bus_ripple_mV_pp_model": op["vout_ripple_mV"]}
        ax[1].semilogx(f / 1e6, vbus, ".", ms=3, color=col, label=f"+12V bus, {vin} V in ({op['mode']})")
        ax[1].semilogx(f / 1e6, vboard, "x", ms=3, color=col, alpha=0.6, label=f"at the board's input, {vin} V in")
    ax[1].axvspan(3, 30, color="#eeeeee", zorder=0)
    ax[1].text(4, 95, "HF band (J951)", fontsize=8)
    ax[1].set_xlabel("MHz")
    ax[1].set_ylabel("dBuV")
    ax[1].set_ylim(-20, 110)
    ax[1].set_title("Output: ripple harmonics on the supply to each board")
    ax[1].grid(alpha=0.3, which="both")
    ax[1].legend(fontsize=8)
    fig.suptitle("PSU board: conducted noise (psu_emi.py)")
    fig.tight_layout()
    fig.savefig(OUT_PNG, dpi=140)
    with open(OUT_JSON, "w") as fh:
        json.dump(res, fh, indent=1, default=float)
    for k, c in res["cases"].items():
        print(k, json.dumps(c)[:600])


if __name__ == "__main__":
    main()
