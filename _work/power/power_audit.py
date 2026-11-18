#!/usr/bin/env python3
"""
Rev08 power audit (18 November 2026): can anything on the board be damaged, or run outside its rating, by its own
supplies, by the vehicle's supply, or by the boards it is wired to?

    python _work/power/power_audit.py          # about 20 s; writes docs/sim/power_*.png and docs/sim/power_audit.json

Eight checks, all from datasheet figures (marked [V]) or stated engineering estimates ([E]):

  1  budget      every rail's load, typical and worst case, against its regulator's rating; regulator dissipation.
                 The loads are _work/power_budget.py's, which now carries Vivado's report_power for the FPGA.
  2  windows     each rail's set point with its regulator's reference tolerance, the divider's 1 % resistors, ripple,
                 load step and copper drop, against the recommended range and the absolute maximum of every part on it
  3  headroom    each LDO's worst-case input minus its worst-case output, against its maximum dropout
  4  input       input current against the battery voltage (9-16 V), and the input PTC's hold current against temperature
  5  start-up    a behavioural transient of every rail from the moment 12 V is applied: soft-starts, UVLOs, LDOs
                 tracking their inputs; checked against the 7-series power-up rule and the converters' input limits
  6  transients  ISO 7637-2 pulses 1, 2a, 3a, 3b, ISO 16750-2 load dump (suppressed and not), jump start and reverse
                 battery through the input stage as drawn (PTC, SMCJ33CA, LM74502-Q1 with back-to-back FETs, SMBJ18CA,
                 the +12V capacitors and the board as a constant-power load)
  7  faults      the board's outward supplies shorted: bias tee, GPS, fan; and what each limiter lets through
  8  backpower   the lines that cross to the KV260 or the USB host, when one side is powered and the other is not

Python only (numpy, matplotlib), no circuit simulator: the transients are explicit time-stepped node equations with
piecewise device models, small steps (1-10 ns) inside the fast pulses.
"""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "_work"))
import power_budget as pb  # noqa: E402

OUT = os.path.join(ROOT, "docs", "sim")
sys.stdout.reconfigure(encoding="utf-8")
RESULT = {}


def hdr(t):
    print("\n" + t + "\n" + "-" * len(t))


# ------------------------------------------------------------------------------------------------ 1. budget
# Typical case: 25 C, typical process (Vivado), CAN recessive, bias tee off, fan on, GPS on.
TYPICAL_OVERRIDE = {
    "XC7A50T VCCINT + VCCBRAM": 420, "XC7A50T VCCAUX": 313, "XC7A50T VCCADC (XADC, filtered from VCCAUX by FB1101)": 21,
    "TCAN330 CAN transceiver, transmitting dominant into the car's 60 ohm": 5,
    "Bias tee on J961 at its current limit (JP1301 at 5 V, antenna shorted or a hungry LNA)": 0,
}
# rated output current of each rail's regulator [V, data sheets]
RATING = {"+5V0": ("LMR33630ADDA", 3.0), "+3V3_D": ("TPS562201", 2.0), "+2V5": ("TPS562201", 2.0),
          "+1V0": ("TPS562201", 2.0), "+1V8_A": ("TPS7A8300", 2.0), "+1V8_D": ("TPS7A8300", 2.0),
          "+3V3_A": ("TPS7A8300", 2.0), "+3V0_FE": ("LP5907MFX-3.0", 0.25), "-3V3": ("LM2663M", 0.2),
          "+1V2": ("divider", 0.001)}
# thermal resistance junction to board used by the board model (SIGNAL_INTEGRITY 9.6) [V/E as there]
THETA_JB = {"+1V8_D": 12.3, "+1V8_A": 12.3, "+3V3_A": 12.3, "+3V0_FE": 51.0}


def chain(override=None, extra=None, tree=None):
    """Re-run power_budget's propagation with some loads replaced; returns (direct, load, dissipation, i12)."""
    tree = dict(pb.TREE if tree is None else tree)
    direct = {}
    for rail, name, v, ma, conf, src in pb.LOADS:
        if override and name in override:
            ma = override[name]
        direct[rail] = direct.get(rail, 0) + ma
    for rail, ma in (extra or {}).items():
        direct[rail] = direct.get(rail, 0) + ma
    load = {r: direct.get(r, 0) for r in pb.VOLTS}
    diss = {}
    order = ["-3V3", "+3V0_FE", "+1V2", "+1V8_D", "+1V8_A", "+2V5", "+1V0", "+3V3_A", "+3V3_D", "+5V0", "+12V"]
    for rail in order:
        if rail not in tree:
            continue
        src, kind, eff = tree[rail]
        i_out = load[rail]
        v_out, v_in = pb.VOLTS[rail], pb.VOLTS[src]
        if kind == "ldo":
            i_in, diss[rail] = i_out, (v_in - v_out) * i_out / 1000
        else:
            p_out = abs(v_out) * i_out / 1000
            p_in = p_out / eff
            i_in, diss[rail] = p_in / v_in * 1000, p_in - p_out
        load[src] = load.get(src, 0) + i_in
    return direct, load, diss, load["+12V"]


def check_budget():
    hdr("1. BUDGET: every regulator against its rating (typical / worst case)")
    _, lt, dt, i12t = chain(TYPICAL_OVERRIDE)
    _, lw, dw, i12w = chain()
    rows = []
    print("  %-8s %-14s %7s | %8s %8s %6s | %7s %7s" % ("rail", "regulator", "rating", "typ mA", "worst mA", "use", "typ W", "worst W"))
    for rail in ("+5V0", "+3V3_D", "+2V5", "+1V0", "+1V8_A", "+1V8_D", "+3V3_A", "+3V0_FE", "-3V3"):
        part, amps = RATING[rail]
        use = lw[rail] / 1000 / amps
        flag = "  <-- over 80 % of rating" if use > 0.8 else ""
        if rail in dw and dw[rail] > 0.8 and pb.TREE[rail][1] == "ldo":
            flag += "  <-- LDO above 0.8 W"
        print("  %-8s %-14s %5.2f A | %8.0f %8.0f %5.0f%% | %7.2f %7.2f%s"
              % (rail, part, amps, lt[rail], lw[rail], 100 * use, dt.get(rail, 0), dw.get(rail, 0), flag))
        rows.append(dict(rail=rail, part=part, rating_a=amps, typ_ma=round(lt[rail]), worst_ma=round(lw[rail]),
                         use=round(use, 3), typ_w=round(dt.get(rail, 0), 3), worst_w=round(dw.get(rail, 0), 3)))
    print("  input at 12 V: %.0f mA typical (%.1f W), %.0f mA worst case (%.1f W)" % (i12t, 12 * i12t / 1000, i12w, 12 * i12w / 1000))
    # The fix examined: +1V8_D's LDO fed from +2V5 instead of +3V3_D.
    tree2 = dict(pb.TREE); tree2["+1V8_D"] = ("+2V5", "ldo", None)
    pb.VOLTS_SAVE = dict(pb.VOLTS)
    _, l2, d2, i12f = chain(tree=tree2)
    print("  with U1006 fed from +2V5: +1V8_D LDO %.2f W (was %.2f), +2V5 %.0f mA (%.0f %%), +3V3_D %.0f mA (%.0f %%), input %.0f mA"
          % (d2["+1V8_D"], dw["+1V8_D"], l2["+2V5"], l2["+2V5"] / 20, l2["+3V3_D"], l2["+3V3_D"] / 20, i12f))
    RESULT["budget"] = dict(rows=rows, input_typ_ma=round(i12t), input_worst_ma=round(i12w),
                            fix_1v8d_from_2v5=dict(ldo_w=round(d2["+1V8_D"], 3), v2v5_ma=round(l2["+2V5"]),
                                                   v3v3_ma=round(l2["+3V3_D"]), input_ma=round(i12f)))
    return lt, lw, i12t, i12w, l2


# ------------------------------------------------------------------------------------------------ 2. windows
def divider(vref_min, vref_typ, vref_max, rt, rb, tol=0.01):
    lo = vref_min * (1 + rt * (1 - tol) / (rb * (1 + tol)))
    hi = vref_max * (1 + rt * (1 + tol) / (rb * (1 - tol)))
    return lo, vref_typ * (1 + rt / rb), hi


RAILS = {
    # rail: (min, typ, max) of the regulator output at its pins, ripple+load step (V, each way), copper drop at the loads (V)
    "+5V0": divider(0.985, 1.0, 1.015, 100e3, 24.9e3) + (0.010, 0.0),       # LMR33630 VFB [V]; ripple 6 mV calc
    "+3V3_D": divider(0.749, 0.768, 0.787, 33.2e3, 10e3) + (0.040, 0.020),  # TPS562201 VFB [V]; D-CAP2 step [E]
    "+2V5": divider(0.749, 0.768, 0.787, 22.6e3, 10e3) + (0.030, 0.031),
    "+1V0": divider(0.749, 0.768, 0.787, 3.09e3, 10e3) + (0.020, 0.034),    # drop: SI 4.4 scaled to 735 mA
    "+1V8_A": (1.85 * 0.99, 1.85, 1.85 * 1.01, 0.005, 0.100),               # TPS7A8300 1 % [V]; drop SI 9.1
    # +1V8_D: SI 4.4's path to the FPGA balls is 184-263 mohm (single path, an upper bound); it now carries the
    # FPGA's 426 mA (VCCAUX 365 + VCCADC 31 + VCCO_35 30) instead of the 150 mA it was sized for
    "+1V8_D": (1.8 * 0.99, 1.8, 1.8 * 1.01, 0.005, 0.263 * 0.426),
    "+1V8_D (ADC DRVDD branch)": (1.8 * 0.99, 1.8, 1.8 * 1.01, 0.005, 0.030),
    "+1V8_D at 1.85 V (50 mV pin grounded)": (1.85 * 0.99, 1.85, 1.85 * 1.01, 0.005, 0.263 * 0.426),
    "+1V8_D at 1.85 V, ADC branch": (1.85 * 0.99, 1.85, 1.85 * 1.01, 0.005, 0.030),
    "+3V3_A": (3.3 * 0.99, 3.3, 3.3 * 1.01, 0.005, 0.010),
    "+3V0_FE": (3.0 * 0.97, 3.0, 3.0 * 1.03, 0.005, 0.010),                 # LP5907 3 % over temperature [V]
    "-3V3": (-3.400 + 0.008 * 3.5, -3.318 + 0.008 * 3.5, -3.235 + 0.008 * 3.5, 0.010, 0.0),  # LM2663 follows +3V3_D
}
# part, rail, recommended min, max, absolute max (None where the data sheet gives none) [V unless marked]
WINDOWS = [
    ("XC7A50T VCCINT (DS181)", "+1V0", 0.95, 1.05, 1.10),
    ("XC7A50T VCCAUX, VCCO_35, VCCADC (DS181)", "+1V8_D", 1.71, 1.89, 2.00),
    ("XC7A50T VCCO_34 at 2.5 V (DS181)", "+2V5", 2.375, 2.625, 3.60),
    ("XC7A50T VCCO_14/15 at 3.3 V (DS181)", "+3V3_D", 3.135, 3.465, 3.60),
    ("AD9484 AVDD", "+1V8_A", 1.70, 1.90, 2.00),
    ("AD9253 AVDD", "+1V8_A", 1.70, 1.90, 2.00),
    ("AD9484 / AD9253 DRVDD", "+1V8_D (ADC DRVDD branch)", 1.70, 1.90, 2.00),
    ("XC7A50T VCCAUX with U1006 set to 1.85 V", "+1V8_D at 1.85 V (50 mV pin grounded)", 1.71, 1.89, 2.00),
    ("AD9484 / AD9253 DRVDD with U1006 set to 1.85 V", "+1V8_D at 1.85 V, ADC branch", 1.70, 1.90, 2.00),
    ("AD9767 / AD9708 AVDD", "+3V3_A", 2.70, 5.50, 6.50),
    ("AD8352 x4 (via ferrites)", "+5V0", 3.00, 5.25, 5.50),
    ("Si549 (via FB401)", "+3V3_D", 3.135, 3.465, 3.80),
    ("ADCLK948 (via FB401), 3.3 V +-10 %", "+3V3_D", 2.97, 3.63, 3.90),
    ("RTL8211FSI, 3.3 V +-5 % [E]", "+3V3_D", 3.135, 3.465, 3.63),
    ("TCAN330", "+3V3_D", 3.00, 3.60, 5.00),
    ("M3SWA2-34DR+ VDD", "+3V3_D", 3.00, 3.60, None),
    ("RFFC5072", "+3V0_FE", 2.70, 3.30, 3.60),
    ("SPF5043Z x2 (drain through 1 uH)", "+3V0_FE", 2.70, 5.25, 5.50),
    ("PE4312, PE4259, PE42442, SKY13418 (2.3-3.6 V) [E]", "+3V0_FE", 2.30, 3.60, 4.00),
]


def check_windows():
    hdr("2. VOLTAGE WINDOWS: worst-case rail at the part against its range and absolute maximum")
    out = []
    for part, rail, rmin, rmax, amax in WINDOWS:
        lo, typ, hi, ripple, drop = RAILS[rail]
        if rail == "-3V3":
            continue
        # the clock and PHY rails sit behind a ferrite: 0.05-0.10 V of extra drop at their currents [E]
        extra = 0.05 if "FB401" in part else 0.0
        vmin, vmax = lo - ripple - drop - extra, hi + ripple
        ok = vmin >= rmin and vmax <= rmax
        abs_ok = amax is None or vmax < amax
        flag = "" if ok else ("  <-- outside the recommended range" if abs_ok else "  <-- ABOVE ABSOLUTE MAXIMUM")
        print("  %-48s %-8s %.3f-%.3f V   range %.3f-%.3f%s" % (part, rail, vmin, vmax, rmin, rmax, flag))
        out.append(dict(part=part, rail=rail, vmin=round(vmin, 3), vmax=round(vmax, 3), rmin=rmin, rmax=rmax,
                        absmax=amax, ok=ok, abs_ok=abs_ok))
    lo, typ, hi, rip, _ = RAILS["-3V3"]
    print("  %-48s %-8s %.3f to %.3f V   M3SWA2 VEE: -3.3 typ, -3.6 most negative" % ("M3SWA2-34DR+ VEE (LM2663 from +3V3_D)", "-3V3", lo - rip, hi + rip))
    RESULT["windows"] = out


# ------------------------------------------------------------------------------------------------ 3. headroom
def check_headroom():
    hdr("3. LDO HEADROOM: worst-case input minus worst-case output against maximum dropout")
    rows = []
    # (LDO, input rail, output rail, load mA, series R on the input (ohm), dropout max at its rated current, rated mA)
    cases = [
        ("U1005 +1V8_A", "+2V5", "+1V8_A", 500, 0.02, 0.200, 2000),
        ("U1006 +1V8_D (as drawn, from +3V3_D)", "+3V3_D", "+1V8_D", 629, 0.02, 0.200, 2000),
        ("U1006 +1V8_D (fed from +2V5)", "+2V5", "+1V8_D", 629, 0.02, 0.200, 2000),
        ("U1007 +3V3_A", "+5V0", "+3V3_A", 100, 0.02, 0.200, 2000),
        ("U1315 +3V0_FE (through FB1301)", "+3V3_D", "+3V0_FE", 180, 0.15 + 0.02, 0.250, 250),
    ]
    for name, rin, rout, ma, rser, vdo, irated in cases:
        lo_in = RAILS[rin][0] - RAILS[rin][3] - ma / 1000 * rser
        hi_out = RAILS[rout][2]
        typ_head = RAILS[rin][1] - ma / 1000 * rser - RAILS[rout][1]
        need = vdo * ma / irated           # dropout scales with current (a resistive pass device) [E]
        head = lo_in - hi_out
        flag = "" if head > need else "  <-- can enter dropout at the worst corner"
        print("  %-40s worst %.3f V (typical %.3f V), dropout at %d mA up to %.3f V%s"
              % (name, head, typ_head, ma, need, flag))
        rows.append(dict(ldo=name, worst_headroom=round(head, 3), typ_headroom=round(typ_head, 3), dropout=round(need, 3),
                         ok=head > need))
    RESULT["headroom"] = rows


# ------------------------------------------------------------------------------------------------ 4. input and PTC
# Polymer PTC hold-current derating for an 1812 part [E: Littelfuse 1812L series table; the fitted C142805 is
# generic and gives no table]. Ambient of the part itself: inside the enclosure, beside the jack.
PTC_T = np.array([-40, -20, 0, 23, 40, 50, 60, 70, 85])
PTC_K = np.array([1.47, 1.30, 1.15, 1.00, 0.88, 0.81, 0.74, 0.66, 0.55])


def check_input(i12t, i12w, i12fix):
    hdr("4. INPUT CURRENT against the battery voltage, and F1001 (PTC 1.5 A hold) against its temperature")
    vin = np.linspace(9, 16, 71)
    # the input stage is a constant-power load above the LMR33630's dropout; the buck's efficiency improves a
    # little at low input [E], ignored (pessimistic at 16 V, slightly optimistic at 9 V)
    p_t, p_w = 12 * i12t / 1000, 12 * i12w / 1000
    it, iw = p_t / vin, p_w / vin
    hold = 1.5 * np.interp([25, 40, 50, 56, 60, 70, 85], PTC_T, PTC_K)
    for T, h in zip([25, 40, 50, 56, 60, 70, 85], hold):
        print("  PTC at %2d C holds %.2f A   (board at 12 V: %.2f A typical, %.2f A worst; at 10.5 V: %.2f / %.2f A)"
              % (T, h, p_t / 12, p_w / 12, p_t / 10.5, p_w / 10.5))
    # temperature at which the PTC would trip, worst case at 12 V and at 10.5 V
    tt = np.linspace(-40, 85, 1251)
    k = np.interp(tt, PTC_T, PTC_K) * 1.5
    trip12 = tt[np.argmax(k < p_w / 12)] if (k < p_w / 12).any() else None
    trip105 = tt[np.argmax(k < p_w / 10.5)] if (k < p_w / 10.5).any() else None
    tripT = tt[np.argmax(k < p_t / 12)] if (k < p_t / 12).any() else None
    print("  worst-case load trips the PTC above %.0f C at 12 V and above %.0f C at 10.5 V; typical load above %.0f C"
          % (trip12, trip105, tripT))
    RESULT["input"] = dict(p_typ_w=round(p_t, 2), p_worst_w=round(p_w, 2), ptc_trip_c_worst_12v=float(trip12),
                           ptc_trip_c_worst_10v5=float(trip105), ptc_trip_c_typ_12v=float(tripT))
    return vin, it, iw


# ------------------------------------------------------------------------------------------------ 5. start-up
def startup(t_end=0.02, dt=1e-6, tss_lmr=4e-3, tss_tps=1.0e-3, i_nrss=6.2e-6):
    t = np.arange(0, t_end, dt)
    v = {k: np.zeros_like(t) for k in ("+12V", "+5V0", "+3V3_D", "+2V5", "+1V0", "+1V8_A", "+1V8_D", "+3V3_A", "+3V0_FE", "-3V3", "+1V2")}
    st = {"lmr": None, "3v3": None, "2v5": None, "1v0": None}
    ss = {"1V8_A": 0.0, "1V8_D": 0.0, "3V3_A": 0.0}
    c_ss = 10e-9
    for k in range(1, len(t)):
        tk = t[k]
        v12 = min(12.0, 12.0 * tk / 0.5e-3)       # LM74502 turns its FETs on, +12V rises in about 0.5 ms [E]
        v["+12V"][k] = v12
        if st["lmr"] is None and v12 > 3.9:      # LMR33630 VIN UVLO rising [V]
            st["lmr"] = tk + 0.4e-3              # internal start-up delay before the soft-start [E]
        v5 = 0.0 if st["lmr"] is None or tk < st["lmr"] else min(5.016, 5.016 * (tk - st["lmr"]) / tss_lmr)
        v5 = min(v5, max(v12 - 0.3, 0))
        v["+5V0"][k] = v5
        for key, rail, vset in (("3v3", "+3V3_D", 3.318), ("2v5", "+2V5", 2.503), ("1v0", "+1V0", 1.005)):
            if st[key] is None and v5 > 4.1:     # TPS562201 VIN UVLO wake-up 3.8-4.3 V [V]
                st[key] = tk + 0.2e-3            # EN through 10 k, internal delay [E]
            vv = 0.0 if st[key] is None or tk < st[key] else min(vset, vset * (tk - st[key]) / tss_tps)
            v[rail][k] = vv
        for key, rin, rout, vset in (("1V8_A", "+2V5", "+1V8_A", 1.85), ("1V8_D", "+3V3_D", "+1V8_D", 1.8),
                                     ("3V3_A", "+5V0", "+3V3_A", 3.3)):
            vin = v[rin][k]
            if vin > 1.4:                         # TPS7A8300 EN tied to IN, UVLO about 1.4 V [V]
                ss[key] = min(0.8, ss[key] + i_nrss * dt / c_ss)   # NR/SS: 6.2 uA into 10 nF [V]
            vout = vset * ss[key] / 0.8
            v[rout][k] = max(0.0, min(vout, vin - 0.05))
        vin = v["+3V3_D"][k]
        v["+3V0_FE"][k] = max(0.0, min(3.0, vin - 0.1)) if vin > 2.2 else 0.0   # LP5907, fast start [V]
        v["-3V3"][k] = -0.98 * v["+3V3_D"][k]
        v["+1V2"][k] = v["+2V5"][k] * 1.02 / 2.12
    return t, v


def check_startup():
    hdr("5. START-UP: every rail from the moment 12 V is applied (behavioural, nominal soft-start times)")
    worst = {}
    runs = {}
    for label, kw in (("nominal", {}), ("fast LDO, slow buck", dict(tss_tps=1.2e-3, i_nrss=9.0e-6)),
                      ("slow LDO", dict(i_nrss=4.0e-6))):
        t, v = startup(**kw)
        runs[label] = (t, v)
        d = v["+3V3_D"] - v["+1V8_D"]
        over = (d > 2.625).sum() * (t[1] - t[0])
        # time each rail reaches 90 %
        t90 = {r: float(t[np.argmax(v[r] >= 0.9 * v[r].max())]) for r in ("+1V0", "+1V8_D", "+2V5", "+3V3_D", "+1V8_A")}
        order = sorted(t90, key=t90.get)
        worst[label] = dict(vcco_minus_vccaux_over_2v625_ms=round(over * 1e3, 3), t90_ms={k: round(x * 1e3, 2) for k, x in t90.items()},
                            order=order)
        print("  %-22s order to 90 %%: %s;  VCCO(3.3) - VCCAUX > 2.625 V for %.2f ms (DS181 allows 300 ms per power cycle)"
              % (label, " -> ".join("%s %.1f ms" % (r, t90[r] * 1e3) for r in order), over * 1e3))
    RESULT["startup"] = worst
    return runs


# ------------------------------------------------------------------------------------------------ 6. transients
class TVS:
    """Bidirectional TVS: off below breakdown, a resistance above it."""
    def __init__(self, vbr, vc, ipp, ppk):
        self.vbr, self.rd, self.ppk = vbr, (vc - vbr) / ipp, ppk

    def i(self, v):
        a = abs(v) - self.vbr
        return 0.0 if a <= 0 else math.copysign(a / self.rd, v)

    def g(self, v):
        return 0.0 if abs(v) <= self.vbr else 1.0 / self.rd


def pulse(kind):
    """ISO 7637-2:2011 / ISO 16750-2 test pulses for 12 V systems: source voltage vs time, source resistance, end."""
    UA = 13.5
    if kind == "ISO 7637-2 pulse 1 (-150 V, 10 ohm, 2 ms; supply disconnected)":
        td, us, ri = 2e-3, -150.0, 10.0
        f = lambda t: (us * min(1, t / 1e-6) * math.exp(-max(t - 1e-6, 0) / (td / math.log(10))) if t >= 0 else UA)
        return f, ri, 6e-3, 20e-9, True
    if kind == "ISO 7637-2 pulse 2a (+112 V, 2 ohm, 50 us)":
        td, us, ri = 50e-6, 112.0, 2.0
        f = lambda t: UA + (us * min(1, t / 1e-6) * math.exp(-max(t - 1e-6, 0) / (td / math.log(10))) if t >= 0 else 0)
        return f, ri, 300e-6, 2e-9, False
    if kind == "ISO 7637-2 pulse 3a (-220 V, 50 ohm, 0.1 us)":
        td, us, ri = 0.1e-6, -220.0, 50.0
        f = lambda t: UA + (us * min(1, t / 5e-9) * math.exp(-max(t - 5e-9, 0) / (td / math.log(10))) if t >= 0 else 0)
        return f, ri, 2e-6, 0.2e-9, False
    if kind == "ISO 7637-2 pulse 3b (+150 V, 50 ohm, 0.1 us)":
        td, us, ri = 0.1e-6, 150.0, 50.0
        f = lambda t: UA + (us * min(1, t / 5e-9) * math.exp(-max(t - 5e-9, 0) / (td / math.log(10))) if t >= 0 else 0)
        return f, ri, 2e-6, 0.2e-9, False
    if kind == "ISO 16750-2 load dump, test B (suppressed to 35 V, 0.5 ohm, 400 ms)":
        f = lambda t: UA + (35.0 - UA) * min(1, t / 5e-3) if 0 <= t <= 0.4 else UA
        return f, 0.5, 0.45, 5e-6, False
    if kind == "ISO 16750-2 load dump, test A (87 V unsuppressed, 1 ohm, 400 ms)":
        f = lambda t: UA + (87.0 - UA) * min(1, t / 5e-3) * math.exp(-max(t - 5e-3, 0) / (0.4 / math.log(10))) if t >= 0 else UA
        return f, 1.0, 0.45, 5e-6, False
    if kind == "Jump start, 24 V for 60 s (ISO 16750-2 4.3.1.2), first 50 ms":
        f = lambda t: UA + (24.0 - UA) * min(1, t / 1e-3) if t >= 0 else UA
        return f, 0.05, 0.05, 1e-6, False
    if kind == "Reverse battery, -14 V (ISO 16750-2 4.7), first 50 ms":
        f = lambda t: -14.0 * min(1, t / 1e-3) if t >= 0 else UA
        return f, 0.05, 0.05, 1e-6, True
    raise KeyError(kind)


PULSES = ["ISO 7637-2 pulse 1 (-150 V, 10 ohm, 2 ms; supply disconnected)",
          "ISO 7637-2 pulse 2a (+112 V, 2 ohm, 50 us)",
          "ISO 7637-2 pulse 3a (-220 V, 50 ohm, 0.1 us)",
          "ISO 7637-2 pulse 3b (+150 V, 50 ohm, 0.1 us)",
          "ISO 16750-2 load dump, test B (suppressed to 35 V, 0.5 ohm, 400 ms)",
          "ISO 16750-2 load dump, test A (87 V unsuppressed, 1 ohm, 400 ms)",
          "Jump start, 24 V for 60 s (ISO 16750-2 4.3.1.2), first 50 ms",
          "Reverse battery, -14 V (ISO 16750-2 4.7), first 50 ms"]


def input_stage(kind, p_load=13.4):
    """Source -> Ri -> harness 1 uH -> PTC 0.06 ohm -> VIN_F (C1090 100 nF, D1003) -> FETs -> +12V (C1001 47 uF +
    C1002 10 uF + C1003 0.22 uF, derated 50 % for DC bias, D1001) -> constant-power load (LMR33630, off below 4 V)."""
    src, ri, t_end, dt, disconnect = pulse(kind)
    d1003 = TVS(38.65, 53.3, 28.2, 1500.0)    # SMCJ33CA: VBR 36.7-40.6, VC 53.3 V at 28.2 A, 1500 W 10/1000 us [V]
    d1001 = TVS(21.05, 29.2, 20.5, 600.0)     # SMBJ18CA: VBR 20.0-22.1, VC 29.2 V at 20.5 A, 600 W [V]
    L, rptc, cin, c12 = 1e-6, 0.06, 100e-9, 0.5 * (47e-6 + 10e-6 + 0.22e-6)
    ron = 2 * 0.0135
    ov_on, ov_off = 18.33, 18.0                # R1004/R1005 with the 1.25 V typical threshold [V]
    vin, v12 = 13.5, 13.5 - p_load / 13.5 * ron
    il = p_load / v12
    fet_on, ov_timer, on_timer = True, 0.0, 0.0
    n = int(t_end / dt)
    rec = dict(t=[], vsrc=[], vin=[], v12=[], fet=[])
    e1003 = e1001 = p1003 = p1001 = vds_max = 0.0
    pk = dict(vin_max=-1e9, vin_min=1e9, v12_max=-1e9, v12_min=1e9)
    keep = max(1, n // 4000)
    t0 = -20e-6                      # settle before the pulse
    k0 = int(-t0 / dt)
    for k in range(-k0, n):
        t = k * dt
        vs = src(t) if (t >= 0 or not disconnect) else 13.5
        rs = ri if t >= 0 else 0.05
        if t < 0:
            vs = 13.5
        # LM74502: OV comparator, 0.6-1 us to turn the gate off, 5-10 us to turn it back on [V];
        # reverse polarity (VS below about 0.5 V) also pulls the gate to the source
        want_off = vin > ov_on or vin < 0.5
        if fet_on and want_off:
            ov_timer += dt
            if ov_timer >= 1e-6:
                fet_on, on_timer = False, 0.0
        elif fet_on:
            ov_timer = 0.0
        elif not (vin > ov_off or vin < 3.2):
            on_timer += dt
            if on_timer >= 10e-6:
                fet_on, ov_timer = True, 0.0
        else:
            on_timer = 0.0
        gf = 1.0 / ron if fet_on else 0.0
        iload = p_load / v12 if v12 > 4.0 else 0.0
        # backward Euler: harness current eliminated, Newton on (vin, v12) with the TVSs piecewise linear
        a_l = dt / L; den = 1 + a_l * (rs + rptc)
        x1, x2 = vin, v12
        for _ in range(8):
            il_n = (il + a_l * (vs - x1)) / den
            f1 = cin * (x1 - vin) / dt - il_n + d1003.i(x1) + gf * (x1 - x2)
            f2 = c12 * (x2 - v12) / dt - gf * (x1 - x2) + d1001.i(x2) + iload
            j11 = cin / dt + a_l / den + d1003.g(x1) + gf
            j12 = -gf
            j21 = -gf
            j22 = c12 / dt + gf + d1001.g(x2)
            det = j11 * j22 - j12 * j21
            d1 = (f1 * j22 - f2 * j12) / det
            d2 = (j11 * f2 - j21 * f1) / det
            x1 -= d1; x2 -= d2
            if abs(d1) < 1e-6 and abs(d2) < 1e-6:
                break
        il = (il + a_l * (vs - x1)) / den
        vin, v12 = x1, x2
        if t < 0:
            continue
        i3, i1 = d1003.i(vin), d1001.i(v12)
        e1003 += abs(vin * i3) * dt; e1001 += abs(v12 * i1) * dt
        p1003 = max(p1003, abs(vin * i3)); p1001 = max(p1001, abs(v12 * i1))
        if not fet_on:
            vds_max = max(vds_max, abs(vin - v12))
        pk["vin_max"] = max(pk["vin_max"], vin); pk["vin_min"] = min(pk["vin_min"], vin)
        pk["v12_max"] = max(pk["v12_max"], v12); pk["v12_min"] = min(pk["v12_min"], v12)
        if k % keep == 0:
            rec["t"].append(t); rec["vsrc"].append(vs); rec["vin"].append(vin); rec["v12"].append(v12); rec["fet"].append(fet_on)
    arr = {k: np.array(x) for k, x in rec.items()}
    return arr, dict(vds_max=vds_max, e1003=e1003, e1001=e1001, p1003=p1003, p1001=p1001, **pk)


def tvs_energy_limit(ppk, t_eff):
    """Energy a TVS rated ppk for a 10/1000 us pulse takes over an effective duration t_eff (Wunsch-Bell, P ~ t^-1/2)
    [E]: E = ppk * 1.4 ms * sqrt(t_eff / 1.4 ms)."""
    return ppk * 1.4e-3 * math.sqrt(max(t_eff, 1e-7) / 1.4e-3)


def check_transients():
    hdr("6. VEHICLE TRANSIENTS through the input stage as drawn")
    rows, traces = [], {}
    durations = {PULSES[0]: 2e-3, PULSES[1]: 50e-6, PULSES[2]: 0.1e-6, PULSES[3]: 0.1e-6, PULSES[4]: 0.4, PULSES[5]: 0.4,
                 PULSES[6]: 60, PULSES[7]: 60}
    for kind in PULSES:
        arr, r = input_stage(kind)
        traces[kind] = arr
        lim3 = tvs_energy_limit(1500, durations[kind] * 0.7)
        lim1 = tvs_energy_limit(600, durations[kind] * 0.7)
        ok = (r["v12_max"] < 36 and r["vds_max"] < 100 and r["vin_max"] < 65 and r["vin_min"] > -65
              and r["e1003"] < lim3 and r["e1001"] < lim1)
        print("  %-70s\n      VIN_F %+7.1f/%+7.1f V, +12V %5.1f..%5.1f V, FET VDS %5.1f V, D1003 %.3g J (limit %.3g), D1001 %.3g J (limit %.3g)  %s"
              % (kind, r["vin_max"], r["vin_min"], r["v12_min"], r["v12_max"], r["vds_max"], r["e1003"], lim3, r["e1001"], lim1,
                 "PASS" if ok else "FAIL"))
        r.update(kind=kind, ok=bool(ok), d1003_limit_j=lim3, d1001_limit_j=lim1)
        rows.append({k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()})
    print("  limits: LMR33630 VIN 36 V abs (+12V), LM74502 VS +-65 V (VIN_F), DMT10H015LFG 100 V; TVS energy by Wunsch-Bell scaling [E]")
    RESULT["transients"] = rows
    return traces


# ------------------------------------------------------------------------------------------------ 7. faults
def check_faults():
    hdr("7. OUTWARD SUPPLIES SHORTED: what the limiter lets through")
    rows = [
        ("Bias tee J961 shorted (5 V)", "AP22652, RLIM 210 k", "95-155 mA, then thermal cycling; fault flag to U1313 P10",
         "FB1302 rated 250 mA, L1301 170 mA [V]: both above 155 mA", True),
        ("GPS supply J1503 pin 6 shorted", "F1501 JK-SMD0805-020 (0.2 A hold, 0.4 A trip)", "trips in under a second at 1 A; +3V3_D sags briefly",
         "+3V3_D buck current limit carries the trip current; C1540 1 uF", True),
        ("Fan J1002 shorted", "F1002 SMD1206P050TF (0.5 A hold, 1 A trip)", "trips; +5V0 holds (3 A buck)", "", True),
        ("CAN bus shorted to +12-14.8 V (battery)", "none: PESD1CAN stands off 24 V", "TCAN330 CANH/CANL absolute maximum is +-14 V [V]",
         "a charging alternator (14.4-14.8 V) or a 24 V jump start destroys U1506", False),
        ("CAN bus shorted to ground", "TCAN330 driver current limit", "survives (rated)", "", True),
        ("USB-C host on J1501 with the board off", "LP5907 from VBUS powers only the CH340X", "1 k (R1533) into the FPGA's PMOD_SPARE1: under 3 mA", "", True),
    ]
    for a, b, c, d, ok in rows:
        print("  %-42s %-44s %s %s%s" % (a, b, c, d, "" if ok else "  <-- DAMAGE"))
    RESULT["faults"] = [dict(fault=a, limiter=b, result=c, note=d, ok=ok) for a, b, c, d, ok in rows]


# ------------------------------------------------------------------------------------------------ 8. back-powering
def check_backpower():
    hdr("8. BACK-POWERING: lines to the KV260 and the USB host when one side is unpowered")
    # LVCMOS33, 12 mA drive: about 25 ohm output resistance [E from IBIS-class data]; clamp diode 0.6 V; the
    # unpowered bank's VCCO held near 0 V by its own decoupling and loads (the worst case for current).
    r_out, vclamp = 25.0, 0.6
    rows = []
    for line, path, r_series, v in (
            ("Pmod (8 lines, 3.3 V, no series resistor on either board: KV260 R276-R283 are 0 ohm)",
             "Artix bank 15 <-> K26 HDA bank", 0.0, 3.3),
            ("PMOD_SPARE1 from the CH340X", "USB bridge -> Artix", 1000.0, 3.3),
            ("PMOD_SPARE2 to the CH340X", "Artix -> USB bridge", 1000.0, 3.3),
            ("GPS PPS to J9 pin 12 (and its copy)", "U1505 -> K26 HDA10", 220.0, 3.3),
            ("CAN RX to J9 pin 8, through 1.8 k / 1 k", "TCAN330 RXD -> K26 bank 66 (1.2 V)", 1800.0 * 1000 / 2800, 1.18),
            ("IAS1 LVDS pairs", "AC-coupled (C101-C110)", None, 0.0),
            ("IAS1 HK_SCL/HK_SDA (open drain) and PROG_B (74LVC1G07, Ioff)", "carrier 1.8 V <-> bank 35", None, 0.0),
            ("IAS1 FPGA_IRQ, push-pull 1.8 V", "Artix bank 35 -> K26 HPA", 0.0, 1.8)):
        if r_series is None:
            i = 0.0
        else:
            i = max(0.0, v - vclamp) / (r_out + r_series)
        flag = "  <-- upper bound above 10 mA" if i > 0.010 else ""
        print("  %-78s %-38s %6.1f mA%s" % (line, path, i * 1e3, flag))
        rows.append(dict(line=line, path=path, i_ma=round(i * 1e3, 1)))
    RESULT["backpower"] = rows


# ------------------------------------------------------------------------------------------------ figures
def figures(lt, lw, vin, it, iw, runs, traces):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.size": 9})

    # budget bars
    fig, ax = plt.subplots(1, 2, figsize=(11, 4.2))
    rails = ["+5V0", "+3V3_D", "+2V5", "+1V0", "+1V8_A", "+1V8_D", "+3V3_A", "+3V0_FE"]
    x = np.arange(len(rails))
    ax[0].bar(x - 0.2, [lt[r] / 1000 / RATING[r][1] * 100 for r in rails], 0.4, label="typical (25 C)", color="#2a78b5")
    ax[0].bar(x + 0.2, [lw[r] / 1000 / RATING[r][1] * 100 for r in rails], 0.4, label="worst case (70 C, max process, bias tee, CAN)", color="#c0392b")
    ax[0].axhline(80, ls="--", c="k", lw=0.8); ax[0].text(-0.4, 82, "80 %", fontsize=8)
    ax[0].set_xticks(x, [f"{r}\n{RATING[r][0]}" for r in rails], fontsize=7, rotation=35, ha="right")
    ax[0].set_ylabel("load / regulator rating (%)"); ax[0].set_title("Regulator use"); ax[0].legend(fontsize=7)
    ax[1].plot(vin, it, label="typical", c="#2a78b5"); ax[1].plot(vin, iw, label="worst case", c="#c0392b")
    for T, ls in ((25, "-"), (56, "--"), (70, ":")):
        ax[1].axhline(1.5 * np.interp(T, PTC_T, PTC_K), c="k", ls=ls, lw=0.8)
        ax[1].text(15.0, 1.5 * np.interp(T, PTC_T, PTC_K) + 0.02, f"PTC hold at {T} C", fontsize=7)
    ax[1].set_xlabel("input voltage (V)"); ax[1].set_ylabel("input current (A)"); ax[1].set_title("Input current against F1001's hold current")
    ax[1].legend(fontsize=7); ax[1].grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "power_budget_ptc.png"), dpi=130); plt.close(fig)

    # start-up
    t, v = runs["nominal"]
    fig, ax = plt.subplots(figsize=(9, 4.2))
    for r, c in (("+12V", "#7f8c8d"), ("+5V0", "#8e44ad"), ("+3V3_D", "#c0392b"), ("+2V5", "#d35400"), ("+1V0", "#27ae60"),
                 ("+1V8_A", "#16a085"), ("+1V8_D", "#2980b9"), ("+3V3_A", "#e67e22"), ("+3V0_FE", "#f1c40f"), ("-3V3", "#34495e")):
        ax.plot(t * 1e3, v[r], label=r, c=c, lw=1.2)
    ax.plot(t * 1e3, v["+3V3_D"] - v["+1V8_D"], c="k", ls="--", lw=0.9, label="VCCO(3.3) - VCCAUX")
    ax.axhline(2.625, c="k", ls=":", lw=0.8); ax.text(0.2, 2.7, "2.625 V (DS181: at most 300 ms)", fontsize=7)
    ax.set_xlabel("time from 12 V applied (ms)"); ax.set_ylabel("V"); ax.set_xlim(0, 12); ax.grid(alpha=0.3)
    ax.set_title("Power-up, behavioural model (nominal soft-starts)"); ax.legend(ncol=4, fontsize=7, loc="center right", bbox_to_anchor=(1.0, 0.68))
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "power_startup.png"), dpi=130); plt.close(fig)

    # transients
    fig, axs = plt.subplots(2, 4, figsize=(13, 6))
    for ax, kind in zip(axs.flat, PULSES):
        a = traces[kind]
        sc = 1e3 if a["t"][-1] > 1e-3 else 1e6
        un = "ms" if sc == 1e3 else "us"
        ax.plot(a["t"] * sc, a["vsrc"], c="#bdc3c7", lw=0.9, label="source (open circuit)")
        ax.plot(a["t"] * sc, a["vin"], c="#c0392b", lw=1.1, label="VIN_F (D1003)")
        ax.plot(a["t"] * sc, a["v12"], c="#2980b9", lw=1.3, label="+12V (to LMR33630)")
        ax.axhline(36, c="k", ls=":", lw=0.7)
        ax.set_title(kind.split("(")[0].replace("ISO ", ""), fontsize=8); ax.set_xlabel(un, fontsize=7); ax.grid(alpha=0.3)
        lo = min(-20, a["vin"].min() * 1.1); hi = max(40, min(a["vsrc"].max(), 120) * 1.05)
        ax.set_ylim(lo, hi)
    axs[0, 0].legend(fontsize=6)
    fig.suptitle("Input stage under vehicle transients (dotted: LMR33630's 36 V)", fontsize=10)
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "power_transients.png"), dpi=130); plt.close(fig)


def main():
    lt, lw, i12t, i12w, l2 = check_budget()
    check_windows()
    check_headroom()
    vin, it, iw = check_input(i12t, i12w, l2["+12V"])
    runs = check_startup()
    traces = check_transients()
    check_faults()
    check_backpower()
    if "--no-plots" not in sys.argv:
        figures(lt, lw, vin, it, iw, runs, traces)
    with open(os.path.join(OUT, "power_audit.json"), "w", encoding="utf-8") as f:
        json.dump(RESULT, f, indent=1, default=float)
    print("\nwrote docs/sim/power_audit.json and power_budget_ptc.png, power_startup.png, power_transients.png")


if __name__ == "__main__":
    main()
