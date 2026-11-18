#!/usr/bin/env python3
"""
Rev08 RF audit (18 November 2026): the VHF/UHF converter's preselection, checked for what it lets reach the
mixer besides the wanted band. Uses the drawn values and the filter models of rev08_filters_mc.py (lossy inductors,
pad capacitance) and the RFFC5072 data sheet's leakage plots (DS140110 p.22).

    python _work/sim/rev08_rf_audit.py      # seconds; writes docs/sim/rf_audit_uhf_path.png and docs/sim/rf_audit.json

What it computes:
  1  the UHF low-pass (FL path RF1 of preselector B) and the anti-alias low-pass with the parts as drawn
  2  every mixer response m x LO - n x RF = IF (IF 135 MHz, m <= 4, n <= 4) for the UHF channels, and how much the
     preselector takes off each
  3  IF rejection: a signal already at the IF (100-170 MHz: FM broadcast's top, airband, 2 m, marine, PMR) reaches the
     mixer through the UHF low-pass unattenuated and leaks to the mixer output at the mixer's RF-to-IF isolation
  4  the LO: where it falls at the ADC, and an estimate of what leaves the antenna
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
NAMES = {k.split(":")[0]: k for k in fe.FILTERS}
IF = 135.0
LNA_DB, SW_DB, CONV_DB = 22.0, 2.0, -4.0      # SPF5043Z at 100-500 MHz; switches to the mixer; RFFC5072 + baluns
ISO_RF_IF = (35.0, 50.0)                      # mixer RF-to-IF isolation at the IF [E]: the data sheet plots 45-60 dB
                                              # from 500 MHz up (0 dBm in, MIX2_IDD 4); none below 500 MHz
LO_LEAK_IF = -38.0                            # LO at the mixer output, dBm (DS140110 p.22, 400-1600 MHz) [V plot]
LO_LEAK_RF = -45.0                            # LO at the mixer input port [E: not in the data sheet]
LNA_S12 = 25.0                                # SPF5043Z reverse isolation, dB [E]
FLOOR_12K5 = -129.0                           # converted UHF noise floor in 12.5 kHz (REV08_PLAN 5.5)


def rej(name, v, f_mhz):
    f = np.atleast_1d(np.asarray(f_mhz, float)) * 1e6
    return -20 * np.log10(np.abs(mc.response(NAMES[name], v, f)[0]))


def spurs(rf):
    lo = rf + IF
    out = []
    for m in range(0, 5):
        for k in range(1, 5):
            for s in (+1, -1):
                f = (m * lo + s * IF) / k
                if f <= 20 or (m == 1 and k == 1) or abs(f - rf) < 1:
                    continue
                out.append((m, k, round(f, 1), float(rej("UHF", UHF, f)[0])))
    return sorted(set(out), key=lambda r: r[3])


def main():
    res = {}
    f = np.linspace(20, 2500, 2000)
    r_uhf, r_aa = rej("UHF", UHF, f), rej("AA200", AA, f)
    print("UHF low-pass as drawn (preselector B, RF1): rejection")
    pts = [88, 100, 108, 118, 137, 145, 156, 170, 446, 480, 500, 513.5, 530, 581, 616, 660, 716, 1000]
    for x in pts:
        print("  %7.1f MHz  %5.1f dB" % (x, rej("UHF", UHF, x)[0]))
    res["uhf_lpf_db"] = {str(x): round(float(rej("UHF", UHF, x)[0]), 1) for x in pts}

    print("\nIF REJECTION in converted UHF mode (signals at 100-170 MHz reach the mixer through the UHF low-pass)")
    ifr = []
    for iso in ISO_RF_IF:
        r = iso + CONV_DB      # wanted: conversion gain; at the IF: minus the isolation; filter loss the same (< 0.4 dB)
        ifr.append(r)
        print("  mixer RF-to-IF isolation %2.0f dB -> IF rejection %2.0f dB; an FM or airband carrier of -30 dBm at the "
              "antenna looks like a %4.0f dBm UHF signal, %2.0f dB above the 12.5 kHz floor" % (iso, r, -30 - r, -30 - r - FLOOR_12K5))
    res["if_rejection_db"] = ifr
    print("  where VHF lands with LO = RF + 135 MHz: a carrier at f_IF appears at RF = LO - f_IF")
    for rf in (390, 435, 446):
        lo = rf + IF
        print("    tuned %d MHz (LO %d): FM 100-108 -> %d-%d, airband 118-137 -> %d-%d, 2 m/marine/PMR 144-174 -> %d-%d MHz"
              % (rf, lo, lo - 108, lo - 100, lo - 137, lo - 118, lo - 174, lo - 144))

    print("\nMIXER RESPONSES that the UHF low-pass takes off less than 30 dB (m x LO, n x RF), tuned 446 MHz")
    sp = spurs(446)
    for m, k, fr, a in sp:
        if a < 30:
            print("  %dx%d  %7.1f MHz  %5.1f dB" % (m, k, fr, a))
    res["spurs_446"] = [dict(m=m, n=k, f_mhz=fr, presel_db=round(a, 1)) for m, k, fr, a in sp if a < 30]
    h = rej("UHF", UHF, 446 + IF / 2)[0]
    print("  half-IF (2x2) at %.1f MHz: the UHF low-pass takes off %.1f dB; DVB-T channel 26 (506-514 MHz) sits on it" % (446 + IF / 2, h))

    print("\nLO")
    for rf in (390, 446, 1090):
        lo = rf + IF if rf < 1000 else rf - IF
        a = rej("AA200", AA, lo)[0]
        al = fe.alias(lo * 1e6) / 1e6
        lvl = LO_LEAK_IF - a + 21.0              # through the anti-alias filter and the IF amplifier, at IF_VU
        print("  tuned %4d MHz, LO %4d MHz: at the mixer output %.0f dBm, anti-alias %.0f dB, at IF_VU %.0f dBm "
              "(%.0f dBFS against -17.6 dBm full scale), aliased to %.0f MHz %s"
              % (rf, lo, LO_LEAK_IF, a, lvl, lvl + 17.6, al, "(inside 100-170 MHz)" if 100 <= al <= 170 else ""))
    # out of the antenna, LO 525-1000 MHz: through preselector B (UHF low-pass or the 1 GHz low-pass), the switches,
    # then the LNA's reverse isolation, or the bypass
    for path, att in (("UHF low-pass, LO 581 MHz", float(rej("UHF", UHF, 581)[0])), ("LFCN-1000+ path, LO 735 MHz", 1.0)):
        print("  LO out of J961 (%s): LNA in %.0f dBm, LNA bypassed %.0f dBm [E]; receiver spurious limit -57 dBm below 1 GHz"
              % (path, LO_LEAK_RF - att - SW_DB - LNA_S12, LO_LEAK_RF - att - SW_DB - 1.0))
    with open(os.path.join(OUT, "rf_audit.json"), "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(10, 4.4))
    ax.plot(f, -r_uhf, c="#2a78b5", lw=1.4, label="UHF low-pass as drawn (preselector B, RF1)")
    ax.plot(f, -r_aa, c="#7f8c8d", lw=1.0, ls="--", label="anti-alias low-pass (after the mixer)")
    ax.axvspan(100, 170, color="#c0392b", alpha=0.12)
    ax.text(112, -22, "IF window\n100-170 MHz\npasses at\n< 0.4 dB", fontsize=7, color="#c0392b")
    ax.axvspan(400, 480, color="#27ae60", alpha=0.15); ax.text(405, -75, "wanted\n400-480", fontsize=7, color="#1e8449")
    ax.axvline(446 + IF / 2, c="#8e44ad", lw=0.8, ls=":"); ax.text(518, -30, "half-IF of 446\n(2x2), 513.5 MHz", fontsize=7, color="#8e44ad")
    ax.axvspan(87.5, 108, color="#f39c12", alpha=0.12); ax.text(64, -22, "FM\nbroadcast", fontsize=7, color="#b9770e")
    ax.set_xscale("log"); ax.set_xlim(30, 2500); ax.set_ylim(-90, 3)
    ax.set_xlabel("MHz"); ax.set_ylabel("|S21| (dB)"); ax.grid(alpha=0.3, which="both")
    ax.set_title("Converted UHF mode: what the preselector lets reach the mixer")
    ax.legend(fontsize=8, loc="lower left")
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "rf_audit_uhf_path.png"), dpi=130); plt.close(fig)
    print("\nwrote docs/sim/rf_audit_uhf_path.png and docs/sim/rf_audit.json")


if __name__ == "__main__":
    main()
