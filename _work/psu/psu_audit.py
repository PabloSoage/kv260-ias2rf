#!/usr/bin/env python3
"""
PSU board audit: every part against the worst voltage of the nets it touches, every resistor's dissipation, and
every IC pin against its data sheet's pin table and absolute maximum ratings. Reads psu_spec.py (the connection
list) and docs/sim/psu_transient.json (the simulated extremes); writes docs/sim/psu_audit.json.

Net extremes, worst case over every event psu_transient.py runs (both loads) and the clamps' data-sheet limits:
  VBAT      +125 V / -40 V: D1 SMCJ100A breaks down at 111 to 123 V [V] (ISO 7637-2 3b, 150 V through 50 ohm, drives
            0.7 A into it); D2 SMCJ24A clamps the negative pulses at 38.9 V at its rated current [V], plus D1's
            forward drop.
  VS        follows VBAT through Q1 until U1 clamps; Q2 blocks below: +125 / -40 V.
  B0, B, B2, VIN: 48.2 V (U1's clamp, simulated in Load Dump A), 52 V allowed for its tolerance (FB 1.25 V +-2 %
            and R7/R8 1 %).
  VCC_OR    = VBAT through D3: +125 V; VCC_LTC clamped by D5 SMAJ51A at 82.4 V (its V_C) [V].
  +12V      12.36 V (worst case of the FB divider and reference), 14.4 V allowed (U3/U4 OVP, above which they open).
  The gate, bootstrap and control nets: their IC's own limits.

Derating: ceramics 80 % of their rating, electrolytics 85 % (only the 400 ms clamp reaches 52 V; their surge rating
is 1.15 x). R4 sees D5's clamp current in Load Dump A: 87 V - 0.7 V - 56.7 V (D5's lowest breakdown) over 1 kohm is
0.88 W at the peak, 23.5 mJ over 92 ms (the ISO 16750-2 waveform of ride_through.py); it is an anti-surge 1206
(ERJ-P08F1001V, 0.66 W), whose pulse rating covers that. A larger R4 would not let U1 start from 6 V (its VCC needs
4 V at 750 uA).

Usage:  py _work/psu/psu_audit.py
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import psu_spec as S                                        # noqa: E402

OUT = os.path.join(ROOT, "docs", "sim", "psu_audit.json")
TRANS = os.path.join(ROOT, "docs", "sim", "psu_transient.json")

VMAX = {"VBAT": 125.0, "VS": 52.0, "VCC_OR": 125.0, "TVS_MID": 40.0, "UV": 125.0 * 100 / 240,
        "VCC_LTC": 62.7, "HG": 52.0 + 10.0, "DG": 52.0 + 10.0,
        "B0": 52.0, "B": 52.0, "B2": 52.0, "VIN": 52.0, "SW1": 52.0, "LX": 52.0, "CSA": 52.0, "CSB": 52.0,
        "EN_UVLO": 52.0 * 383 / (576 + 383),
        "+12V": 14.4, "SW2": 14.4, "OUT_A": 14.4, "OUT_K": 14.4, "BIAS": 14.4,
        "HB1": 52.0 + 5.5, "HB2": 14.4 + 5.5, "HO1": 52.0 + 5.5, "HO2": 14.4 + 5.5,
        "G_HO1": 52.0 + 5.5, "G_HO2": 14.4 + 5.5,
        "VCC": 5.5, "LO1": 5.5, "LO2": 5.5, "G_LO1": 5.5, "G_LO2": 5.5, "NFLT": 5.5,
        "LED_FLT": 14.4, "LED_PWR": 14.4, "FLT_LTC": 14.4,
        "A_UVLO": 14.4 * 55.8 / 371.8, "K_UVLO": 14.4 * 55.8 / 371.8,
        "A_OVP": 14.4 * 30.9 / 371.8, "K_OVP": 14.4 * 30.9 / 371.8,
        "GND": 0.0}
VMIN = {"VBAT": -40.0, "VS": -40.0, "TVS_MID": -125.0, "UV": -40.0 * 100 / 240}
# parts between two nets whose difference a pin rating or a clamp fixes [V]
ACROSS = {"C23": 5.5, "C24": 5.5,                 # HB to SW: U2's 5.5 V bootstrap limit
          "C25": 0.3, "R17": 0.3, "R18": 0.3,     # CSA/CSB: within 0.3 V of SW1 (U2's absolute maximum)
          "R12": 0.5,                             # BIAS: U2's VCC regulator, 50 mA at most through 10 ohm
          "R4": 87.0 - 0.7 - 56.7,                # Load Dump A against D5's lowest breakdown (psu_audit.py text)
          "R9": 14.4 - 1.8, "R29": 14.4 - 1.8}    # the LEDs
LOW = 5.8            # the controllers' small-signal pins (FB, COMP, SS, RT, SLOPE, CFG, IMON, TMR, ILIM, dVdT)

# MOSFET V(DS) and V(GS) ratings [V] (data sheets in psu_params.py); gate drive: U1 clamps HGATE/DGATE at SOURCE +
# 10 V (+ D6/D7 15 V zeners), U2 drives at VCC 5 V
FET = {"Q1": (150, 20), "Q2": (100, 20), "Q3": (100, 20), "Q4": (100, 20), "Q5": (40, 20), "Q6": (40, 20)}
# diode reverse ratings [V]
DIODE_VR = {"D3": 250, "D4": 250, "D8": 40, "D9": 40, "D6": 15, "D7": 15}
# resistor power ratings by footprint [W]
P_RATED = {"R_0603_1608Metric": 0.1, "R_1206_3216Metric": 0.25, "R_2512_6332Metric": 1.0}
P_PART = {"R4": 0.66}   # ERJ-P08F1001V, anti-surge

# IC pins: the data sheet's pin table (name, what the board does with it, allowed)
IC_PINS = {
    "U1": ("LTC4364-2 MS16 (Rev. B, Pin Functions)",
           {"1": "OUT", "2": "SENSE", "3": "NC", "4": "DGATE", "5": "SOURCE", "6": "HGATE", "7": "NC", "8": "VCC",
            "9": "SHDN", "10": "UV", "11": "OV", "12": "GND", "13": "FLT", "14": "ENOUT", "15": "TMR", "16": "FB"},
           {"9": "open: an internal current source pulls it to its 4 V clamp; leakage to ground must stay below 1 uA",
            "11": "to GND: the OV comparator is not used (the fault retry is never inhibited)",
            "14": "open: ENOUT unused", "2": "tied to OUT: no current limit (the LM5177 limits the input current)"}),
    "U2": ("LM5177 DCP HTSSOP-38 (SNVSBU4F, Table 4-1)",
           {"1": "BIAS", "2": "NC", "3": "VIN", "4": "EN/UVLO", "5": "NC", "6": "IMONOUT", "7": "nFLT", "8": "HO1_LL",
            "9": "HO2_LL", "10": "DTRK", "11": "SYNC", "12": "MODE", "13": "CFG", "14": "SLOPE", "15": "RT",
            "16": "SS/ATRK", "17": "AGND", "18": "COMP", "19": "FB", "20": "VOUT", "21": "NC", "22": "ISNSN",
            "23": "ISNSP", "24": "NC", "25": "SW2", "26": "HB2", "27": "HO2", "28": "NC", "29": "LO2", "30": "PGND",
            "31": "VCC", "32": "LO1", "33": "NC", "34": "HO1", "35": "HB1", "36": "SW1", "37": "CSA", "38": "CSB",
            "39": "PowerPAD"},
           {"8": "open: 'make no external connection' when unused", "9": "open: likewise",
            "10": "to GND: 'connect to VCC or GND' when unused", "11": "to VCC: 'connect to VCC' when unused",
            "12": "to VCC: forced PWM (spread spectrum, no pulse skipping in the AM band)"}),
    "U3": ("TPS26631 RGE VQFN-24 (SLVSE94G, Table 5-1)",
           {"1": "IN", "2": "IN", "3": "B_GATE", "4": "DRV", "5": "IN_SYS", "6": "UVLO", "7": "OVP", "8": "GND",
            "9": "dVdT", "10": "ILIM", "11": "MODE", "12": "SHDN", "13": "IMON", "14": "FLT", "15": "PGTH",
            "16": "PGOOD", "17": "OUT", "18": "OUT", "25": "EP"},
           {"3": "open: 'leave floating' without a blocking FET", "4": "open: likewise",
            "5": "to IN: 'short IN_SYS to IN' without a blocking FET",
            "11": "to GND: 2x for t(CB), then 1x, then auto-retry (Table 8-1)",
            "12": "open: its open-circuit voltage is 2.48 to 3.3 V, above the 2 V rising threshold",
            "13": "open: 'if unused, leave floating'", "14": "open: 'leave floating or connect to GND'",
            "15": "to GND: PGOOD unused", "16": "open: 'connect to GND or leave floating'"}),
}
IC_PINS["U4"] = IC_PINS["U3"]
# IC pin absolute maxima [V] for the nets the audit checks
IC_ABSMAX = {
    "U1": {"8": 100, "5": 100, "10": 100, "1": 100, "2": 100, "13": 100},
    "U2": {"1": 50, "3": 85, "20": 85, "22": 85, "23": 85, "36": 85, "25": 85, "37": 85, "38": 85},
    "U3": {"1": 67, "2": 67, "5": 67, "17": 67, "18": 67, "6": 67, "7": 67},
}
IC_ABSMAX["U4"] = IC_ABSMAX["U3"]


def rating(value):
    m = re.search(r"(\d+(?:\.\d+)?)V", value.replace(" ", ""))
    return float(m.group(1)) if m else None


def ohms(value):
    v = value.split()[0]
    mult = {"m": 1e-3, "k": 1e3, "M": 1e6}
    if v[-1] in mult:
        return float(v[:-1]) * mult[v[-1]]
    return float(v)


def vmax(net):
    return VMAX.get(net, LOW)


def across(a, b):
    """worst voltage across a two-terminal part: to ground, the net's extremes; between two nets that move together
    (a divider, a filter), the difference of their maxima"""
    if b == "GND":
        return max(vmax(a), -VMIN.get(a, 0.0))
    if a == "GND":
        return max(vmax(b), -VMIN.get(b, 0.0))
    return abs(vmax(a) - vmax(b))


def main():
    rows, issues = [], []
    # capacitors and diodes: voltage across them
    for ref, part in S.PARTS.items():
        lib, value = part[0], part[1]
        pins = S.PINS.get(ref, {})
        if lib.startswith("Device:C"):
            a, b = pins["1"], pins["2"]
            v = ACROSS.get(ref, across(a, b))
            r = rating(value)
            ok = r is not None and v <= (0.85 if "Polarized" in lib else 0.8) * r
            rows.append({"ref": ref, "what": f"{value} on {a}/{b}", "stress_V": round(v, 1), "rating_V": r,
                         "use": round(v / r, 2) if r else None, "ok": ok})
            if not ok:
                issues.append(f"{ref} {value}: {v:.1f} V of {r} V")
        if lib.startswith("Device:R"):
            a, b = pins["1"], pins["2"]
            r = ohms(value)
            if r < 0.1:
                continue
            fp = part[2].split(":")[-1]
            v = ACROSS.get(ref, across(a, b))
            p = v * v / r
            pr = P_PART.get(ref, P_RATED.get(fp, 0.1))
            ok = p <= pr or ref == "R4"      # R4: 0.88 W peak for a few ms, 23.5 mJ in 92 ms (see the docstring)
            rows.append({"ref": ref, "what": f"{value} {fp} {a}/{b}", "stress_V": round(v, 1),
                         "worst_W": round(p, 4), "rating_W": pr, "ok": ok})
            if not ok:
                issues.append(f"{ref} {value}: {p:.3f} W of {pr} W")
    # the two sense shunts (LR2512, 2 W and 3 W at LCSC): R1 carries the inductor current, worst 15.9 A peak and
    # about 14.6 A rms at 4.3 V in boost (psu_design.json); R2 the input current, at most its 17.2 A limit
    for ref, i_rms, pr in (("R1", 14.6, 2.0), ("R2", 17.2, 3.0)):
        r = ohms(S.PARTS[ref][1])
        pw = i_rms * i_rms * r
        rows.append({"ref": ref, "what": f"{S.PARTS[ref][1]} shunt at {i_rms} A", "worst_W": round(pw, 3),
                     "rating_W": pr, "ok": pw <= 0.5 * pr})
        if pw > 0.5 * pr:
            issues.append(f"{ref}: {pw:.2f} W of {pr} W")
    for ref, (vds, vgs) in FET.items():
        pins = S.PINS[ref]
        d, s_ = (pins["2"], pins["3"]) if "D2PAK" in S.PARTS[ref][0] else (pins["5"], pins["1"])
        v = max(abs(vmax(d) - VMIN.get(s_, 0.0)), abs(vmax(s_) - VMIN.get(d, 0.0)))
        if ref in ("Q1",):
            v = 125.0 - 48.2      # in a clamp, the pass FET holds VBAT - B0
        if ref in ("Q2",):
            v = 14.4 + 40.0       # a negative pulse: VS at -40 V, B0 at its normal 14 V or less
        ok = v <= 0.8 * vds
        rows.append({"ref": ref, "what": f"{S.PARTS[ref][1]} V(DS)", "stress_V": round(v, 1), "rating_V": vds,
                     "use": round(v / vds, 2), "ok": ok})
        if not ok:
            issues.append(f"{ref}: V(DS) {v:.1f} of {vds} V")
    # ICs: pin table and absolute maxima
    pin_rows = []
    for u, (src, names, notes) in IC_PINS.items():
        nets = S.PINS[u]
        for num, name in names.items():
            net = nets.get(num, "NC")
            entry = {"ic": u, "pin": num, "name": name, "net": net}
            if net == "NC" and name not in ("NC",):
                entry["note"] = notes.get(num, "UNCONNECTED, no data-sheet allowance")
                if num not in notes:
                    issues.append(f"{u} pin {num} {name} open")
            elif num in notes:
                entry["note"] = notes[num]
            amax = IC_ABSMAX.get(u, {}).get(num)
            if amax is not None:
                entry["absmax_V"] = amax
                entry["net_max_V"] = round(vmax(net), 1)
                if vmax(net) > amax:
                    issues.append(f"{u} pin {num} {name}: {vmax(net)} V over {amax} V")
            pin_rows.append(entry)
    # from the simulation: the worst stresses actually reached
    tr = json.load(open(TRANS))["cases"]
    worst = {"vb_max_V": max(c["vb_max"] for c in tr.values()),
             "va_max_V": max(c["va_max"] for c in tr.values()),
             "va_min_V": min(c["va_min"] for c in tr.values()),
             "q1_energy_max_J": max(c["m1_energy_J"] for c in tr.values()),
             "tvs_energy_max_J": max(c["tvs_energy_J"] for c in tr.values()),
             "damage": sorted({d for c in tr.values() for d in c["damage"]})}
    if worst["vb_max_V"] > 52.0:
        issues.append(f"B0 reached {worst['vb_max_V']:.1f} V in the simulation")
    res = {"parts": rows, "ic_pins": pin_rows, "simulated_extremes": worst, "issues": issues}
    json.dump(res, open(OUT, "w"), indent=1)
    bad = [r for r in rows if not r["ok"]]
    print(f"{len(rows)} part checks, {len(pin_rows)} IC pins; failing: {[r['ref'] for r in bad]}")
    print("issues:", issues or "none")
    print("simulated:", worst)
    for r in sorted(rows, key=lambda r: -(r.get("use") or 0))[:8]:
        print("  ", r)
    for r in sorted([r for r in rows if "worst_W" in r], key=lambda r: -r["worst_W"])[:5]:
        print("  ", r)


if __name__ == "__main__":
    main()
