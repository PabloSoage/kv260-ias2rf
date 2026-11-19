#!/usr/bin/env python3
"""
PSU board: the LM5177 design, done with the data sheet's own equations (SNVSBU4F section 8.2.2 and 7.3), and the
steady state at every input voltage and load: mode, duty, inductor current, every device's loss and junction
temperature, efficiency, input current, the limits each one is checked against.

Writes docs/sim/psu_design.json and docs/sim/psu_design.png. Values: psu_params.py.

Usage:  py _work/psu/psu_design.py
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

ROOT = os.path.dirname(os.path.dirname(HERE))
OUT_JSON = os.path.join(ROOT, "docs", "sim", "psu_design.json")
OUT_PNG = os.path.join(ROOT, "docs", "sim", "psu_design.png")

E96 = [1.00, 1.02, 1.05, 1.07, 1.10, 1.13, 1.15, 1.18, 1.21, 1.24, 1.27, 1.30, 1.33, 1.37, 1.40, 1.43, 1.47, 1.50,
       1.54, 1.58, 1.62, 1.65, 1.69, 1.74, 1.78, 1.82, 1.87, 1.91, 1.96, 2.00, 2.05, 2.10, 2.15, 2.21, 2.26, 2.32,
       2.37, 2.43, 2.49, 2.55, 2.61, 2.67, 2.74, 2.80, 2.87, 2.94, 3.01, 3.09, 3.16, 3.24, 3.32, 3.40, 3.48, 3.57,
       3.65, 3.74, 3.83, 3.92, 4.02, 4.12, 4.22, 4.32, 4.42, 4.53, 4.64, 4.75, 4.87, 4.99, 5.11, 5.23, 5.36, 5.49,
       5.62, 5.76, 5.90, 6.04, 6.19, 6.34, 6.49, 6.65, 6.81, 6.98, 7.15, 7.32, 7.50, 7.68, 7.87, 8.06, 8.25, 8.45,
       8.66, 8.87, 9.09, 9.31, 9.53, 9.76]
E12C = [1.0, 1.2, 1.5, 1.8, 2.2, 2.7, 3.3, 3.9, 4.7, 5.6, 6.8, 8.2]


def e96(x):
    d = 10 ** math.floor(math.log10(x))
    return min((v * d for v in E96 + [10.0]), key=lambda v: abs(v - x))


def e12(x):
    d = 10 ** math.floor(math.log10(x))
    return min((v * d for v in E12C + [10.0]), key=lambda v: abs(v - x))


# ---------------------------------------------------------------- 1. component values (data-sheet equations)
def values():
    c = P.LM5177
    v = {}
    # eq. 17: RT
    v["R_RT"] = e96((1 / P.FSW - 20e-9) * 30.3e9)
    v["fsw"] = 1 / (v["R_RT"] / 30.3e9 + 20e-9)
    # eq. 18: FB divider, top 71.5 k as table 8-2
    v["R_FBT"] = 71.5e3
    v["R_FBB"] = e96(c["vref"] * v["R_FBT"] / (P.VOUT - c["vref"]))
    v["vout"] = c["vref"] * (1 + v["R_FBT"] / v["R_FBB"])
    # output tolerance: reference 1 %, two 1 % resistors (worst case)
    hi = (c["vref"] * 1.01) * (1 + v["R_FBT"] * 1.01 / (v["R_FBB"] * 0.99))
    lo = (c["vref"] * 0.99) * (1 + v["R_FBT"] * 0.99 / (v["R_FBB"] * 1.01))
    v["vout_range"] = (lo, hi)
    # EN/UVLO: off at VIN_STOP (falling, no hysteresis current), on at about VIN_START (rising + the sink)
    # V_off = Vf (1 + Rt/Rb); V_on = Vr (1 + Rt/Rb) + I_hyst Rt
    k = P.VIN_STOP / c["uvlo_f"]                     # 1 + Rt/Rb
    rt = (P.VIN_START - c["uvlo_r"] * k) / c["i_hyst"]
    v["R_UVT"] = e96(rt)
    v["R_UVB"] = e96(v["R_UVT"] / (k - 1))
    kk = 1 + v["R_UVT"] / v["R_UVB"]
    v["vin_on"] = (c["uvlo_r_min"] * kk + c["i_hyst_min"] * v["R_UVT"], c["uvlo_r"] * kk + c["i_hyst"] * v["R_UVT"],
                   c["uvlo_r_max"] * kk + c["i_hyst_max"] * v["R_UVT"])
    v["vin_off"] = (c["uvlo_f_min"] * kk, c["uvlo_f"] * kk, c["uvlo_f_max"] * kk)
    # peak current sense and slope (eq. 11-13, 19-24)
    v["L"] = P.L1["l"]
    v["R_CS"] = P.R_CS
    v["R_SLOPE"] = e96(v["L"] / v["R_CS"] * 50e6)
    v["rcs_over_l"] = v["R_CS"] / v["L"]
    v["eq12_limit"] = 1.0 * v["fsw"] / (P.VOUT * 10)
    v["ipk_limit"] = tuple(x / v["R_CS"] for x in (c["vcs_min"], c["vcs_typ"], c["vcs_max"]))
    v["R_ISNS"] = P.R_ISNS
    v["iin_limit"] = tuple(x / P.R_ISNS for x in (c["visns_min"], c["visns"], c["visns_max"]))
    # CSA/CSB filter (eq. 15) at the buck minimum on-time
    v["C_DIFF"] = c["ton_min_buck"] / (2 * math.pi * 2 * P.R_DIFF * 10)
    # soft start (eq. 14): 5 ms
    v["C_SS"] = e12(c["i_ss"] * 5e-3 / c["vref"])
    v["t_ss"] = v["C_SS"] * c["vref"] / c["i_ss"]
    # CFG: DRSS on, hiccup off, PSM 10 %, current limit on -> table 7-1 row 6
    v["R_CFG"] = 3.8e3
    return v


# ---------------------------------------------------------------- 2. steady state
COUT_EFF = 6 * 22e-6 * 0.45 + 2 * 100e-6      # 6 x 22 uF 25 V X7R 1210 at 12 V (45 % left [E]) + 2 x 100 uF polymer
COUT_ESR = 1 / (6 / 0.003 + 2 / 0.025)          # ohm, ceramics 3 mOhm, polymer 25 mOhm each [E]
CIN_ESR = 1 / (4 / 0.004 + 1 / 0.080)           # 4 x 4.7 uF 100 V 1210 + 100 uF 80 V electrolytic [E]
R_EFUSE = P.TPS26631["r_on"] * 1.5             # at about 100 C [E]
R_PATH = (P.R_HARNESS + P.IPB048N15N5["rds_10"] * P.IPB048N15N5["tc"] + P.BSC040N10NS5["rds_10"] * P.BSC040N10NS5["tc"]
          + P.R_FILTER + P.R_ISNS)                # battery terminals to the LM5177's VIN, hot


def fet_sw(f, vds, i, rdrv_up, rdrv_dn):
    """Switching energy per cycle (turn-on + turn-off) from the gate charge: E = 1/2 V I (tr + tf)."""
    qsw = f["qgd"] + f["qgs2"]
    tr = qsw * (rdrv_up + f["rg"]) / max(P.LM5177["vcc"] - f["vplat"], 0.3)
    tf = qsw * (rdrv_dn + f["rg"]) / f["vplat"]
    return 0.5 * vds * i * (tr + tf), tr, tf


def mode_of(vin, vout):
    """LM5177 runs buck, boost, or (near VIN = VOUT) buck-boost; the boundaries come from the minimum on- and
    off-times (7.3.2): buck while its duty can stay below 1 - toff_min fsw, boost while above ton_min fsw."""
    c = P.LM5177
    d_buck_max = 1 - c["toff_min_boost"] * P.FSW
    d_boost_min = c["ton_min_buck"] * P.FSW
    if vout / vin <= d_buck_max:
        return "buck"
    if 1 - vin / vout >= d_boost_min:
        return "boost"
    return "buck-boost"


def operating_point(vin, pout, ta=70.0, v=None):
    """One operating point. Losses are iterated with the junction temperatures (RDS rises with Tj)."""
    v = v or values()
    vout = P.VOUT
    iout = pout / vout
    q_in, q_out = P.BSC0805LS, P.BSC026N04LS
    c = P.LM5177
    m = mode_of(vin, vout)
    eff = 0.93
    tj = {"Q2": ta + 20, "Q3": ta + 20, "Q4": ta + 20, "Q5": ta + 20}
    for _ in range(30):
        def rds(f, t):
            return f["rds_45"] * (1 + (f["tc"] - 1) * (t - 25) / 125)
        loss = {}
        if m == "buck":
            d = vout / vin
            il = iout
            dil = (vin - vout) * d / (v["L"] * P.FSW)
        elif m == "boost":
            d = 1 - vin / vout
            il = pout / (eff * vin)
            dil = vin * d / (v["L"] * P.FSW)
        else:                                      # buck-boost: both legs switch around D = 0.5 each [E]
            d = 0.5
            il = pout / (eff * vin)
            dil = vin * 0.5 / (v["L"] * P.FSW)
        il_rms = math.sqrt(il ** 2 + dil ** 2 / 12)
        ipk = il + dil / 2
        if m in ("buck", "buck-boost"):
            dd = d if m == "buck" else 0.6
            e, tr, tf = fet_sw(q_in, vin, il, c["r_drv_hi_up"], c["r_drv_hi_dn"])
            loss["Q2"] = dd * il_rms ** 2 * rds(q_in, tj["Q2"]) + e * P.FSW + q_in["qoss"] * vin * P.FSW / 2
            loss["Q3"] = (1 - dd) * il_rms ** 2 * rds(q_in, tj["Q3"]) + 2 * 0.8 * il * c["t_dead"] * P.FSW \
                + q_in["qrr"] * vin * P.FSW
        else:
            loss["Q2"] = il_rms ** 2 * rds(q_in, tj["Q2"])
            loss["Q3"] = 0.0
        if m in ("boost", "buck-boost"):
            db = d if m == "boost" else 0.4
            e, tr, tf = fet_sw(q_out, vout, il, c["r_drv_up"], c["r_drv_dn"])
            loss["Q4"] = db * il_rms ** 2 * rds(q_out, tj["Q4"]) + e * P.FSW + q_out["qoss"] * vout * P.FSW / 2
            loss["Q5"] = (1 - db) * il_rms ** 2 * rds(q_out, tj["Q5"]) + 2 * 0.8 * il * c["t_dead"] * P.FSW \
                + q_out["qrr"] * vout * P.FSW
        else:
            loss["Q4"] = 0.0
            loss["Q5"] = il_rms ** 2 * rds(q_out, tj["Q5"])
        loss["L1 copper"] = il_rms ** 2 * P.L1["dcr_max"] * 1.3      # DCR at about 100 C [E]
        loss["L1 core"] = 0.02 * pout / 50 + 0.05 * (dil / 5) ** 2    # [E] no core-loss data published
        loss["R_CS"] = il_rms ** 2 * v["R_CS"]
        iin = (pout + sum(loss.values()) + 0.3) / vin
        loss["R_ISNS"] = iin ** 2 * v["R_ISNS"]
        loss["M1 + M2 (U1)"] = iin ** 2 * (P.IPB048N15N5["rds_10"] * P.IPB048N15N5["tc"]
                                           + P.BSC040N10NS5["rds_10"] * P.BSC040N10NS5["tc"])
        loss["L2 filter"] = iin ** 2 * P.R_FILTER
        qg = 2 * q_in["qg_45"] + 2 * q_out["qg_45"]
        loss["U2 drivers + LDO"] = qg * P.FSW * vout + 2e-3 * vout   # from BIAS = VOUT
        if m == "buck":
            icin = iout * math.sqrt(d * (1 - d))
            icout = dil / math.sqrt(12)
        elif m == "boost":
            icin = dil / math.sqrt(12)
            icout = iout * math.sqrt(vout / vin - 1)
        else:
            icin = il * 0.5
            icout = iout * 0.7
        loss["C_IN ESR"] = icin ** 2 * CIN_ESR
        loss["C_OUT ESR"] = icout ** 2 * COUT_ESR
        p_loss = sum(loss.values())
        new_eff = max(pout / (pout + p_loss), 0.5)
        new_tj = {k: min(ta + loss[k] * (q_in if k in ("Q2", "Q3") else q_out)["rth_ja"] * 0.6, 200.0) for k in tj}   # 0.6: the board's copper beats the data sheet's 6 cm2 [E], refined by psu_thermal.py
        if abs(new_eff - eff) < 1e-5 and all(abs(new_tj[k] - tj[k]) < 0.05 for k in tj):
            break
        eff, tj = new_eff, new_tj
    iin = (pout + p_loss) / vin
    limited = iin > values()["iin_limit"][0]
    return {"vin": vin, "pout": pout, "mode": m, "input_current_limited": bool(limited), "duty": d, "il_avg": il, "il_ripple": dil, "il_rms": il_rms,
            "il_peak": ipk, "iin": iin, "loss_W": loss, "p_loss": p_loss, "eff": eff, "tj_fet": tj,
            "icin_rms": icin, "icout_rms": icout,
            "vout_ripple_mV": 1e3 * (dil / (8 * COUT_EFF * P.FSW) + dil * COUT_ESR if m == "buck"
                                     else iout * d / (COUT_EFF * P.FSW) + ipk * COUT_ESR)}


# ---------------------------------------------------------------- 3. compensation (eq. 3-10)
def compensation(v):
    c = P.LM5177
    io_max = P.I_ADAPTER_MAX + P.I_KV_LIMIT
    vin_min = P.VIN_MIN_FULL
    dmax = 1 - vin_min / P.VOUT
    f_rhpz = P.VOUT * (1 - dmax) ** 2 / (2 * math.pi * io_max * v["L"])
    f_bw = min(f_rhpz / 3, (1 - dmax) * v["fsw"] / 10)
    f_pole = 2 * io_max / (2 * math.pi * P.VOUT * COUT_EFF)
    f_cz = 1.5 * f_pole
    r_comp = 2 * math.pi * f_bw / c["gm_ea"] * (v["R_FBB"] + v["R_FBT"]) / v["R_FBB"] * \
        c["a_cs"] * v["R_CS"] * COUT_EFF / (1 - dmax)
    r_comp_e = e96(r_comp)
    c_comp = 1 / (2 * math.pi * f_cz * r_comp_e)
    c_pcomp = 1 / (2 * math.pi * 10 * f_bw * r_comp_e)
    return {"io_max": io_max, "dmax": dmax, "f_rhpz": f_rhpz, "f_bw": f_bw, "f_pole_boost": f_pole, "f_cz": f_cz,
            "R_COMP": r_comp_e, "C_COMP": e12(c_comp), "C_PCOMP": e12(c_pcomp), "C_OUT_eff": COUT_EFF,
            "C_OUT_esr": COUT_ESR}


# ---------------------------------------------------------------- 4. output eFuses (TPS26631, SLVSE94G)
def efuses():
    t = P.TPS26631
    out = {}
    for name, ilim in (("U3 adapter", 2.0), ("U4 KV260", 3.0)):
        r = e96(t["ilim_k"] / ilim)
        i = t["ilim_k"] / r
        out[name] = {"R_ILIM": r, "ilim": i, "ilim_range": (i * (1 - t["ilim_tol"]), i * (1 + t["ilim_tol"]))}
    # OVP / UVLO divider as on the adapter's KVPWR (316 k / 24.9 k / 30.9 k): OVP 14.4 V, UVLO 8.0 V
    out["divider"] = {"R1": 316e3, "R2": 24.9e3, "R3": 30.9e3, "ovp_rise": 14.44, "uvlo_rise": 8.00}
    p_k = P.I_KV_LIMIT ** 2 * R_EFUSE
    p_a = P.I_ADAPTER_MAX ** 2 * R_EFUSE
    out["loss_W"] = {"U4 at 3.19 A": p_k, "U3 at 1.12 A": p_a}
    out["tj_C_at_70C"] = {"U4": 70 + p_k * t["rth_ja"], "U3": 70 + p_a * t["rth_ja"]}
    return out


# ---------------------------------------------------------------- 5. cranking: the board voltage with the harness
def board_vin(v_batt, pout, eff=0.88):
    """VIN at the converter with the harness, M1 + M2, L2 and R_ISNS in series, constant input power:
    V = Vb - R P / (eff V)  ->  V^2 - Vb V + R P / eff = 0 (the higher root), None if no solution."""
    r = R_PATH
    disc = v_batt ** 2 - 4 * r * pout / eff
    if disc < 0:
        return None, None
    vin = (v_batt + math.sqrt(disc)) / 2
    return vin, pout / eff / vin


def main():
    v = values()
    res = {"values": v, "compensation": compensation(v), "efuses": efuses()}
    p_typ = P.P_ADAPTER["typ"] + P.P_KV260["typ"]
    p_max = P.VOUT * (P.I_ADAPTER_MAX + P.I_KV_LIMIT)
    res["loads_W"] = {"typ": p_typ, "max": p_max}
    vins = [3.0, 4.3, 6.0, 9.0, 12.0, 13.5, 14.4, 16.0, 24.0, 36.0, 50.0]
    grid = {}
    for vin in vins:
        for name, p in (("typ", p_typ), ("max", p_max)):
            op = operating_point(vin, p, v=v)
            grid[f"{vin} V {name}"] = op
    res["operating_points"] = grid
    # checks against the limits
    checks = []
    for k, op in grid.items():
        checks.append({"case": k, "il_peak": op["il_peak"], "ipk_limit_min": v["ipk_limit"][0],
                       "peak_ok": op["il_peak"] * 1.2 < v["ipk_limit"][0] or op["vin"] < P.VIN_MIN_FULL,
                       "isat_margin": P.L1["isat"] / v["ipk_limit"][2],
                       "iin": op["iin"], "iin_limit_min": v["iin_limit"][0],
                       "iin_ok": op["iin"] < v["iin_limit"][0],
                       "tj_max": max(op["tj_fet"].values())})
    res["checks"] = checks
    # cranking (ISO 16750-2:2012 Table 5 via TIDUC53 Table 8): the minimum battery voltage of each level
    crank = {}
    for level, us in (("I", 8.0), ("II", 4.5), ("III", 3.0), ("IV", 6.0)):
        for name, p in (("typ", p_typ), ("max", p_max)):
            vin, iin = board_vin(us, p)
            vcc = max(vin or 0, P.VOUT - 0.3)       # LTC4364's VCC is OR-ed from the +12V bus
            ok = vin is not None and vin >= P.LM5177["vin_min"] and iin <= v["iin_limit"][0] and vcc >= 4.0
            crank[f"Level {level} ({us} V) {name}"] = {"vin_board": vin, "iin": iin, "runs": bool(ok)}
    res["cranking"] = crank
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w") as f:
        json.dump(res, f, indent=1, default=float)

    # figure: efficiency and loss split, junction temperature
    vv = np.linspace(4.3, 50, 60)
    fig, ax = plt.subplots(1, 3, figsize=(15, 4.6))
    for name, p, col in (("typical, %.1f W" % p_typ, p_typ, "#2166ac"), ("worst, %.1f W" % p_max, p_max, "#b2182b")):
        ops = [operating_point(x, p, v=v) for x in vv]
        ax[0].plot(vv, [o["eff"] * 100 for o in ops], color=col, lw=2, label=name)
        ax[1].plot(vv, [o["p_loss"] for o in ops], color=col, lw=2, label=name)
        ax[2].plot(vv, [max(o["tj_fet"].values()) for o in ops], color=col, lw=2, label=name)
    for a in ax:
        a.axvspan(10.2, 13.8, color="#dddddd", zorder=0)
        a.grid(alpha=0.3)
        a.set_xlabel("Input voltage at the board (V)")
        a.legend(fontsize=8)
    ax[0].set_ylabel("Efficiency (%)")
    ax[0].set_ylim(75, 100)
    ax[0].set_title("Efficiency (grey: buck-boost region)")
    ax[1].set_ylabel("Total loss (W)")
    ax[1].set_title("Loss")
    ax[2].set_ylabel("Hottest MOSFET junction (C)")
    ax[2].set_title("MOSFET junction at 70 C ambient")
    ax[2].axhline(150, color="k", ls="--", lw=1, label="MOSFET rating, 150 C")
    ax[2].legend(fontsize=8)
    fig.suptitle("PSU board, LM5177 12 V buck-boost: steady state (psu_design.py)")
    fig.tight_layout()
    fig.savefig(OUT_PNG, dpi=150)

    print("values:", {k: (round(x, 4) if isinstance(x, float) else x) for k, x in v.items()})
    print("compensation:", {k: round(x, 6) for k, x in res["compensation"].items()})
    print("efuses:", res["efuses"])
    for k, op in grid.items():
        print(f"{k:14s} {op['mode']:10s} D {op['duty']:.2f} IL {op['il_avg']:5.2f} pk {op['il_peak']:5.2f} "
              f"Iin {op['iin']:5.2f} eff {op['eff']*100:5.1f} % loss {op['p_loss']:5.2f} W "
              f"Tj {max(op['tj_fet'].values()):5.1f} C ripple {op['vout_ripple_mV']:5.1f} mV"
              f"{'  INPUT CURRENT LIMITED' if op['input_current_limited'] else ''}")
    for k, c in crank.items():
        print(k, c)
    print("wrote", OUT_JSON)


if __name__ == "__main__":
    main()
