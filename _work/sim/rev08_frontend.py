#!/usr/bin/env python3
"""
Rev08 study: an on-board VHF/UHF receive front end ahead of the AD9484 (docs/REV08_PLAN.md, section 5).

Three things, all from datasheet numbers:

  filters   the three LC filters the plan depends on, as 7th-order elliptic ladders with lossy inductors
            (the method of aaf_lpf.py): can each mask be met with 0402 wirewound parts?
  cascade   gain, noise figure, full scale at the antenna and sensitivity of each receive mode
  plan      where the image, the LO and the aliases fall for each mode at 400 MSPS

    python _work/sim/rev08_frontend.py            # cascade and plan (seconds)
    python _work/sim/rev08_frontend.py --filters  # also re-optimise the three filters (about two minutes)

Assumptions that are not datasheet figures are marked [E] in the output.
"""
import math
import sys

import numpy as np

R0 = 50.0
FS_ADC = 400e6                    # the AD9484 in radar mode; the gateware closes timing at this rate only


# ---------------------------------------------------------------- filters
def _mul(M, N):
    a, b, c, d = M; e, g, h, k = N
    return [a * e + b * h, a * g + b * k, c * e + d * h, c * g + d * k]


def abcd_lpf(v, f, q, cpar):
    """shunt C1, series L2||C2, shunt C3, series L4||C4, shunt C5, series L6||C6, shunt C7"""
    w = 2 * np.pi * f; one = np.ones_like(w, dtype=complex)
    sh = lambda C: [one, 0 * one, 1j * w * C, one]
    def se(L, C):
        ZL = 1j * w * L + w * L / q
        return [one, 1 / (1 / ZL + 1j * w * (C + cpar)), 0 * one, one]
    C1, L2, C2, C3, L4, C4, C5, L6, C6, C7 = v
    M = sh(C1)
    for b in (se(L2, C2), sh(C3), se(L4, C4), sh(C5), se(L6, C6), sh(C7)):
        M = _mul(M, b)
    return M


def abcd_hpf(v, f, q, cpar):
    """series C1, shunt L2+C2, series C3, shunt L4+C4, series C5, shunt L6+C6, series C7"""
    w = 2 * np.pi * f; one = np.ones_like(w, dtype=complex)
    se = lambda C: [one, 1 / (1j * w * C), 0 * one, one]
    def sh(L, C):
        ZL = 1 / (1 / (1j * w * L + w * L / q) + 1j * w * cpar)
        return [one, 0 * one, 1 / (ZL + 1 / (1j * w * C)), one]
    C1, L2, C2, C3, L4, C4, C5, L6, C6, C7 = v
    M = se(C1)
    for b in (sh(L2, C2), se(C3), sh(L4, C4), se(C5), sh(L6, C6), se(C7)):
        M = _mul(M, b)
    return M


def s21(M):
    A, B, C, D = M; den = A + B / R0 + C * R0 + D
    return 2 / den, (A + B / R0 - C * R0 - D) / den


G7 = [0.445, 1.247, 1.802, 2.0, 1.802, 1.247, 0.445]      # Butterworth start


def start_lpf(fc, zeros):
    wc = 2 * np.pi * fc
    C = lambda g: g / (wc * R0); L = lambda g: g * R0 / wc
    zc = lambda Lv, fz: 1 / ((2 * np.pi * fz) ** 2 * Lv)
    L2, L4, L6 = L(G7[1]), L(G7[3]), L(G7[5])
    return [C(G7[0]), L2, zc(L2, zeros[0]), C(G7[2]), L4, zc(L4, zeros[1]), C(G7[4]), L6, zc(L6, zeros[2]), C(G7[6])]


def start_hpf(fc, zeros):
    wc = 2 * np.pi * fc
    Cs = lambda g: 1 / (g * wc * R0); Ls = lambda g: R0 / (g * wc)
    zc = lambda Lv, fz: 1 / ((2 * np.pi * fz) ** 2 * Lv)
    L2, L4, L6 = Ls(G7[1]), Ls(G7[3]), Ls(G7[5])
    return [Cs(G7[0]), L2, zc(L2, zeros[0]), Cs(G7[2]), L4, zc(L4, zeros[1]), Cs(G7[4]), L6, zc(L6, zeros[2]), Cs(G7[6])]


FILTERS = {
    # name: kind, passband, stopbands, max loss, min rejection, inductor Q, inductor parasitic C, start
    "AA200: anti-alias for 400 MSPS, pass 30-170 MHz, stop from 230 MHz":
        ("lpf", (30e6, 170e6), [(230e6, 260e6), (260e6, 1500e6)], 1.5, 55, 50, 0.15e-12,
         start_lpf(185e6, (265e6, 235e6, 480e6))),
    "UHF: image filter, pass 400-480 MHz, stop from 660 MHz":
        ("lpf", (400e6, 480e6), [(660e6, 800e6), (800e6, 2500e6)], 2.0, 50, 60, 0.12e-12,
         start_lpf(520e6, (800e6, 680e6, 1400e6))),
    "FMREJ: airband and VHF, pass 118-170 MHz, stop 87-108 MHz":
        ("hpf", (118e6, 170e6), [(87e6, 108e6), (40e6, 87e6)], 2.5, 45, 55, 0.15e-12,
         start_hpf(112e6, (98e6, 107e6, 90e6))),
}

# Results of --filters on 16 November 2026 (ideal values, before snapping to catalogue parts):
#   AA200   loss 0.1-1.5 dB, return loss >= 12.1 dB, rejection >= 55.0 dB
#           12.7 pF, 48.6 nH || 7.88 pF, 22.2 pF, 61.6 nH || 6.96 pF, 24.3 pF, 78.4 nH || 0.7 pF, 18 pF
#   UHF     loss 0.5-1.4 dB, return loss >= 14.5 dB, rejection >= 50.4 dB
#           3.72 pF, 22.2 nH || 1.74 pF, 6.77 pF, 29 nH || 1.66 pF, 7.22 pF, 25.7 nH || 0.552 pF, 3.49 pF
#   FMREJ   loss 0.5-3.2 dB, return loss >= 11.8 dB, rejection >= 44.9 dB
#           20.2 pF, 171 nH + 15 pF, 8.18 pF, 116 nH + 46.4 pF, 9.32 pF, 258 nH + 8.32 pF, 26.4 pF
# Not done yet: snapping to E24 / LQW values and the tolerance Monte Carlo, as aaf_lpf.py does for the HF filter.


def design(name, trials=5):
    from scipy.optimize import minimize
    kind, fp, fs, ilmax, rej, q, cpar, x0 = FILTERS[name]
    fn = abcd_lpf if kind == "lpf" else abcd_hpf
    FP = np.linspace(*fp, 80); FS = np.concatenate([np.linspace(a, b, 60) for a, b in fs])

    def cost(x):
        v = np.exp(x); a, r = s21(fn(v, FP, q, cpar))
        il = -20 * np.log10(np.abs(a)); rl = -20 * np.log10(np.abs(r) + 1e-12)
        s = -20 * np.log10(np.abs(s21(fn(v, FS, q, cpar))[0]))
        return (np.sum(np.maximum(il - ilmax, 0) ** 2) + 0.2 * np.sum(np.maximum(12 - rl, 0) ** 2)
                + np.sum(np.maximum(rej - s, 0) ** 2))

    best = None
    for t in range(trials):
        rng = np.random.default_rng(t)
        x = np.log(np.array(x0)) + (rng.normal(0, 0.3, 10) if t else 0)
        r = minimize(cost, x, method="Nelder-Mead", options={"maxiter": 30000, "maxfev": 30000, "xatol": 1e-5, "fatol": 1e-9})
        r = minimize(cost, r.x, method="Powell", options={"maxiter": 20000})
        if best is None or r.fun < best.fun:
            best = r
    v = np.exp(best.x)
    a, r = s21(fn(v, FP, q, cpar)); il = -20 * np.log10(np.abs(a))
    s = -20 * np.log10(np.abs(s21(fn(v, FS, q, cpar))[0]))
    vals = ", ".join("%.3g pF" % (x * 1e12) if x < 1e-9 else "%.3g nH" % (x * 1e9) for x in v)
    print("%s\n    Q %d, loss %.1f-%.1f dB in band, return loss >= %.1f dB, rejection >= %.1f dB\n    %s"
          % (name, q, il.min(), il.max(), (-20 * np.log10(np.abs(r))).min(), s.min(), vals))


# ---------------------------------------------------------------- cascade
def cascade(stages):
    """stages: (name, gain dB, NF dB). Returns total gain and noise figure (Friis)."""
    g_tot = 1.0; f_tot = 1.0
    for _, g, nf in stages:
        f_tot += (10 ** (nf / 10) - 1) / g_tot
        g_tot *= 10 ** (g / 10)
    return 10 * math.log10(g_tot), 10 * math.log10(f_tot)


def loss(name, db):
    return (name, -db, db)


# The receiver the front end feeds, at IF_RX_B (docs/ADC_RADAR_SPEC.md section 3):
#   full scale 1.5 V p-p at the AD9484 behind 25 dB  -> about -17 dBm
#   noise: AD9484 47 dBFS over 200 MHz = 168 nV/rtHz at its pins, 9.4 nV/rtHz referred to the first AD8352,
#   whose own noise is 2.7 nV/rtHz; against the 0.45 nV/rtHz of a terminated 50 ohm source -> NF about 27 dB
ADC_NF = 27.0
ADC_FS = -17.0
IF_LINE = [loss("stripline to SW2, 150 mm on L6", 0.5), loss("M3SWA2 (SW2)", 1.0)]

LNA = ("SPF5043Z at 3 V, 100-500 MHz", 21.0, 0.8)           # 22.6 dB / 0.60 dB at 0.1 GHz, 18 dB at 0.9 GHz
LNA_1G = ("SPF5043Z at 3 V, 1.1 GHz", 16.0, 0.9)
IFAMP = ("second SPF5043Z as IF amplifier", 21.0, 0.8)
MIXER = ("RFFC5072 with its two baluns", -4.0, 12.0)        # -2 dB and 10-13 dB in the data sheet, 1 dB per balun


def mode(name, pre, mixer, filt_loss, lna=LNA, hpf_loss=1.1):
    st = [loss("ESD, bias tee, DC block", 0.4), loss("LNA bypass switch", 0.3), lna, loss("LNA bypass switch", 0.3)]
    if mixer and hpf_loss:
        st.append(loss("300 MHz IF-reject high-pass (HP300)", hpf_loss))
    st += [loss("SP8T", 0.6), loss(pre, filt_loss), loss("SP8T", 0.6)]
    st += [loss("mixer bypass switch", 0.3)] + ([MIXER] if mixer else []) + [loss("mixer bypass switch", 0.3)]
    st += [loss("anti-alias low-pass", 1.3), IFAMP, loss("PE4312 at 0 dB", 1.5)] + IF_LINE
    g, nf_front = cascade(st)
    g_tot, nf = cascade(st + [("AD8352 x2 + AD9484", 0.0, ADC_NF)])
    return name, g, nf, ADC_FS - g


def report_cascade():
    print("\nCASCADE (maximum gain; the PE4312 takes off up to 31.5 dB, the LNA bypass another 22 dB)\n")
    print("  %-38s %8s %7s %12s %10s %10s %10s" % ("mode", "gain", "NF", "full scale", "8.33 kHz", "12.5 kHz", "200 kHz"))
    modes = [
        ("direct, 30-170 MHz", "no preselector", False, 0.0, LNA),
        ("direct, FM broadcast", "FM band-pass", False, 2.0, LNA),
        ("direct, airband and VHF", "FM-reject high-pass", False, 3.0, LNA),
        ("converted, UHF 300-480 MHz", "UHF low-pass", True, 1.6, LNA),
        ("converted, ADS-B 1090 MHz", "SAW TA1090EC", True, 2.5, LNA_1G),
        ("converted, gen. cov. 300 MHz-3 GHz", "LTCC high-pass", True, 1.0, LNA_1G),
    ]
    for label, pre, mx, fl, lna in modes:
        name, g, nf, fs = mode(label, pre, mx, fl, lna=lna)
        mds = lambda bw: -174 + nf + 10 * math.log10(bw)
        line = "  %-38s %6.1f dB %5.1f dB %8.1f dBm %6.0f dBm %6.0f dBm %6.0f dBm" % (
            name, g, nf, fs, mds(8330), mds(12500), mds(200e3))
        if mx:
            _, g0, nf0, fs0 = mode(label, pre, mx, fl, lna=lna, hpf_loss=0.0)
            line += "  [before HP300: gain %.1f, NF %.1f, FS %.1f]" % (g0, nf0, fs0)
        print(line)
    print("\n  The three right-hand columns are the noise floor in that bandwidth: the weakest carrier that")
    print("  reaches 0 dB signal-to-noise. Add 10 dB for AM voice, 12 dB for narrow FM.")
    print("  Dynamic range in one channel, any gain setting: full scale minus the floor, about %d dB in 12.5 kHz."
          % (47 + 10 * math.log10(FS_ADC / 2 / 12500)))
    print("  Gap: 170-300 MHz is not covered (direct ends at 170 MHz; converted starts at 300 MHz behind HP300).")


# ---------------------------------------------------------------- frequency plan
def alias(f, fs=FS_ADC):
    f = f % fs
    return f if f <= fs / 2 else fs - f


def report_plan():
    print("\nFREQUENCY PLAN at %d MSPS (first Nyquist zone 0-%d MHz, anti-alias pass band to 170 MHz)\n" % (FS_ADC / 1e6, FS_ADC / 2e6))
    print("  direct sampling: what folds onto the wanted band if the anti-alias filter were absent")
    for name, lo, hi in (("FM broadcast", 87.5, 108), ("airband", 118, 137), ("2 m, marine VHF", 144, 162.5)):
        print("    %-18s %5.1f-%5.1f MHz   <- %5.1f-%5.1f MHz (zone 2)  and %5.1f-%5.1f MHz (zone 3)"
              % (name, lo, hi, FS_ADC / 1e6 - hi, FS_ADC / 1e6 - lo, FS_ADC / 1e6 + lo, FS_ADC / 1e6 + hi))
    print("\n  converted, IF centred on 135 MHz (100-170 MHz reaches the ADC), high-side LO below 1 GHz")
    print("    %-22s %9s %9s %14s %22s" % ("band centre", "LO", "image", "LO at the ADC", "image filter"))
    for name, rf, side, filt in (("PMR446, 446 MHz", 446, +1, "UHF low-pass, >= 50 dB"),
                                 ("70 cm, 435 MHz", 435, +1, "UHF low-pass, >= 50 dB"),
                                 ("TETRA, 390 MHz", 390, +1, "UHF low-pass, >= 50 dB"),
                                 ("868 MHz SRD", 868, +1, "none on this board"),
                                 ("ADS-B, 1090 MHz", 1090, -1, "SAW, >= 40 dB"),
                                 ("GNSS L1, 1575 MHz", 1575.42, -1, "none unless a SAW is fitted"),
                                 ("2.4 GHz ISM", 2440, -1, "none on this board")):
        lo = rf + side * 135; im = rf + side * 270
        print("    %-22s %7.1f MHz %7.1f MHz %10.1f MHz   %s" % (name, lo, im, alias(lo * 1e6) / 1e6, filt))
    print("\n  The LO reaches the ADC only through the anti-alias filter's stop band (>= 55 dB from 230 MHz),")
    print("  and it is a single known tone. Below 365 MHz of RF a high-side LO falls inside 230-500 MHz: fine.")
    print("  From 300 to 480 MHz the converter works behind the UHF low-pass (with the 300 MHz high-pass ahead")
    print("  of preselector B; below 170 MHz it is bypassed for direct sampling; 170-300 MHz is not covered).")


if __name__ == "__main__":
    if "--filters" in sys.argv:
        print("FILTERS (7th-order elliptic ladders, lossy inductors)\n")
        for n in FILTERS:
            design(n)
    report_cascade()
    report_plan()
