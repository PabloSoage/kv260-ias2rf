#!/usr/bin/env python3
"""
Vehicle ride-through analysis for the single-entry adapter + KV260 power input stage.

Computes from cited standards (ISO 16750-2, ISO 7637-2) and component datasheets:
  1. Cut-off voltages Vmin of the KV260 branch (U1010 TPS26631 + XTP682 MP5016H/MP8772)
     and the adapter branch (LM74502-Q1 + LMR33630).
  2. Closed-form hold-up energy E = P*t and capacitance C = 2*P*t / (V0^2 - Vmin^2)
     for every transient and cranking profile (both [E] typical and [V] bound loads),
     checked against the 4-node backward-Euler transient solver from power_audit.py.
  3. U1010 dVdT (C1093 = 22 nF) start-up charge time and SLVSE94G thermal SOA limits.
  4. Physical capacitor banks (Nichicon UHE 25 V / 35 V) vs PCB and enclosure volume.
  5. Upstream automotive buck-boost converter specification, comparison of real COTS
     modules (Bicker DC160WS, Mini-Box DCDC-USB-200), Load Dump A active 36 V limiter
     analysis, and converter-fed transient solver re-runs across all events.

Outputs docs/sim/ride_through.json and docs/sim/ride_through.png.

    python _work/power/ride_through.py
"""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
import power_audit as pa  # noqa: E402

OUT = os.path.join(ROOT, "docs", "sim")
sys.stdout.reconfigure(encoding="utf-8")


# ---------------------------------------------------------------------------- 1. Standards [V]
# ISO 16750-2:2012 (4th ed.), Clause 4.6.3 Figure 7 / Table 5 (reproduced in TI TIDUC53 Table 8)
# Waveform: UB=12.0 V -> drop over tf to US for t6 -> rise over t7 to UA -> 2 Hz 2 Vpp sine above UA
# trough (UA .. UA+2V) for t8 -> rise over tr to UB (12.0 V).
CRANK_LEVELS = {
    "Level I (warm crank)": dict(
        us=8.0, ua=9.5, tf=5e-3, t6=15e-3, t7=50e-3, t8=1.0, tr=40e-3,
        std="ISO 16750-2:2012 Clause 4.6.3 Table 5 (Level I)"
    ),
    "Level II (cold crank, good battery)": dict(
        us=4.5, ua=6.5, tf=5e-3, t6=15e-3, t7=50e-3, t8=10.0, tr=100e-3,
        std="ISO 16750-2:2012 Clause 4.6.3 Table 5 (Level II)"
    ),
    "Level III (cold crank, aged battery)": dict(
        us=3.0, ua=5.0, tf=5e-3, t6=15e-3, t7=50e-3, t8=1.0, tr=100e-3,
        std="ISO 16750-2:2012 Clause 4.6.3 Table 5 (Level III)"
    ),
    "Level IV (cold crank, room temp)": dict(
        us=6.0, ua=6.5, tf=5e-3, t6=15e-3, t7=50e-3, t8=10.0, tr=100e-3,
        std="ISO 16750-2:2012 Clause 4.6.3 Table 5 (Level IV)"
    ),
}


def crank_wave(level_key, ub=12.0, min_tol=False):
    """Exact ISO 16750-2 Clause 4.6.3 Fig 7 / Table 5 piecewise waveform for 12 V systems."""
    p = CRANK_LEVELS[level_key]
    us = p["us"] - (0.2 if min_tol else 0.0)
    ua = p["ua"] - (0.2 if min_tol else 0.0)
    tf, t6, t7, t8, tr = p["tf"], p["t6"], p["t7"], p["t8"], p["tr"]
    t1 = tf
    t2 = t1 + t6
    t3 = t2 + t7
    t4 = t3 + t8
    t5 = t4 + tr

    def f(t):
        if t < 0.0:
            return ub
        if t < t1:
            return ub + (us - ub) * (t / tf)
        if t < t2:
            return us
        if t < t3:
            return us + (ua + 1.0 - us) * ((t - t2) / t7)
        if t < t4:
            # 2 Hz 2 Vpp sine between UA trough and UA+2 V peak per Fig 7
            return ua + 1.0 + 1.0 * math.sin(2.0 * math.pi * 2.0 * (t - t3))
        if t < t5:
            v4 = ua + 1.0 + 1.0 * math.sin(2.0 * math.pi * 2.0 * t8)
            return v4 + (ub - v4) * ((t - t4) / tr)
        return ub

    return f, t5 + 0.05


def pulse_wave(kind):
    """Unified source waveform with explicit step schedule [(t_start, t_end, dt)].
    Note: ISO 7637-2:2011 Table 2 Pulse 1 includes supply disconnect t2 = 200 ms.
    """
    ua = 13.5
    if kind == "pulse1_200ms":
        # ISO 7637-2:2011 Table 2 / Fig 5: Us=-150 V, Ri=10 Ohm, td=2 ms, tr=1 us, supply disconnected t2=200 ms
        td, us, ri, t2 = 2e-3, -150.0, 10.0, 0.200
        tau = td / math.log(10.0)
        def f(t):
            if t < 0.0:
                return ua
            if t < td * 5.0:
                return us * min(1.0, t / 1e-6) * math.exp(-max(t - 1e-6, 0.0) / tau)
            if t < t2:
                return 0.0
            return ua
        sched = [(0.0, 10e-6, 0.1e-6), (10e-6, 6e-3, 5e-6), (6e-3, 0.200, 100e-6),
                 (0.200, 0.205, 5e-6), (0.205, 0.215, 50e-6)]
        return f, ri, sched, True, 1e-3, ua
    if kind == "pulse2a":
        td, us, ri = 50e-6, 112.0, 2.0
        tau = td / math.log(10.0)
        f = lambda t: ua + (us * min(1.0, t / 1e-6) * math.exp(-max(t - 1e-6, 0.0) / tau) if t >= 0.0 else 0.0)
        sched = [(0.0, 300e-6, 0.05e-6), (300e-6, 3.0e-3, 2e-6)]
        return f, ri, sched, False, 1e-3, ua
    if kind == "pulse3a":
        td, us, ri = 0.1e-6, -220.0, 50.0
        tau = td / math.log(10.0)
        f = lambda t: ua + (us * min(1.0, t / 5e-9) * math.exp(-max(t - 5e-9, 0.0) / tau) if t >= 0.0 else 0.0)
        sched = [(0.0, 2e-6, 1e-9)]
        return f, ri, sched, False, 0.1e-6, ua
    if kind == "pulse3b":
        td, us, ri = 0.1e-6, 150.0, 50.0
        tau = td / math.log(10.0)
        f = lambda t: ua + (us * min(1.0, t / 5e-9) * math.exp(-max(t - 5e-9, 0.0) / tau) if t >= 0.0 else 0.0)
        sched = [(0.0, 2e-6, 1e-9)]
        return f, ri, sched, False, 0.1e-6, ua
    if kind == "load_dump_b":
        f = lambda t: (ua + (35.0 - ua) * min(1.0, t / 5e-3)) if (0.0 <= t <= 0.400) else ua
        sched = [(0.0, 10e-3, 2e-6), (10e-3, 0.398, 200e-6), (0.398, 0.415, 20e-6)]
        return f, 0.5, sched, False, 0.4, ua
    if kind == "load_dump_a":
        tau = 0.4 / math.log(10.0)
        f = lambda t: (ua + (87.0 - ua) * min(1.0, t / 5e-3) * math.exp(-max(t - 5e-3, 0.0) / tau)) if t >= 0.0 else ua
        sched = [(0.0, 10e-3, 5e-6), (10e-3, 0.85, 200e-6)]
        return f, 1.0, sched, False, 0.4, ua
    if kind == "jump_start":
        f = lambda t: (ua + (24.0 - ua) * min(1.0, t / 1e-3)) if t >= 0.0 else ua
        sched = [(0.0, 2e-3, 1e-6), (2e-3, 0.050, 50e-6)]
        return f, 0.05, sched, False, 60.0, ua
    if kind == "reverse":
        f = lambda t: (-14.0 * min(1.0, t / 1e-3)) if t >= 0.0 else ua
        sched = [(0.0, 2e-3, 1e-6), (2e-3, 0.050, 50e-6)]
        return f, 0.05, sched, True, 60.0, ua
    cmap = {
        "crank_I": "Level I (warm crank)",
        "crank_II": "Level II (cold crank, good battery)",
        "crank_III": "Level III (cold crank, aged battery)",
        "crank_IV": "Level IV (cold crank, room temp)",
    }
    if kind in cmap:
        f, t_end = crank_wave(cmap[kind], ub=12.0, min_tol=False)
        p = CRANK_LEVELS[cmap[kind]]
        t_flat = p["tf"] + p["t6"] + p["t7"]
        sched = [(0.0, min(0.15, t_flat + 0.08), 20e-6), (min(0.15, t_flat + 0.08), t_end, 100e-6)]
        return f, 0.05, sched, False, p["t8"], 12.0
    raise KeyError(kind)


# ---------------------------------------------------------------------------- 2. Device limits [V]
def device_thresholds():
    """Exact cut-off and thermal thresholds from datasheets and XTP682."""
    r1, r2, r3 = 316e3, 24.9e3, 30.9e3
    rsum = r1 + r2 + r3
    uv_r = 1.200 * rsum / (r2 + r3)   # 7.9957 V
    uv_f = 1.122 * rsum / (r2 + r3)   # 7.4760 V
    ov_r = 1.200 * rsum / r3          # 14.4388 V
    ov_f = 1.122 * rsum / r3          # 13.5003 V
    iol_nom = 18e3 / 6.04e3           # 2.9801 A
    iol_max = iol_nom * 1.07          # 3.1887 A

    # KV260 XTP682 p.3 + BOM (XTP713): U41 MP5016H + U6 MP8772GQ-Z (L1 1.2 uH, 9.7 mOhm)
    mp5016h_uvlo_r, mp5016h_uvlo_f = 2.53, 2.33
    v5_kv = 0.6 * (1.0 + 20.0 / 2.7)              # 5.0444 V
    dmax_mp8772 = 1.0 - 100e-9 / (1.0 / 700e3)    # 0.930
    rpath_mp8772 = 0.016 + 0.0097                 # R_HS + L1 DCR
    mp8772_min_11w = (v5_kv + (11.0 / v5_kv) * rpath_mp8772) / dmax_mp8772
    mp8772_min_36w = (v5_kv + (36.0 / v5_kv) * rpath_mp8772) / dmax_mp8772
    mp8772_som475_36w = (4.75 + (36.0 / 4.75) * rpath_mp8772) / dmax_mp8772

    # Adapter: LM74502-Q1 POR 3.9/3.2 V, LMR33630ADDA +5V0=5.016 V, R_HS_max=160 mOhm, L_DCR~30 mOhm, Dmax=0.98
    v5_adp = 5.016
    lmr_rpath_wst = 0.160 + 0.030
    lmr_rpath_typ = 0.095 + 0.030
    lmr_min_wst = (v5_adp + 2.409 * lmr_rpath_wst) / 0.98   # 5.586 V
    lmr_min_typ = (v5_adp + 2.099 * lmr_rpath_typ) / 0.98   # 5.386 V
    lmr_450_wst = (4.50 + 2.409 * lmr_rpath_wst) / 0.98     # 5.059 V

    vmin_kv = uv_f                                # 7.476 V (higher of 7.476 V and 5.62 V)
    vmin_adp = lmr_min_wst                        # 5.586 V
    p_kv_typ = 11.0                               # [E]
    p_kv_bnd = iol_max * vmin_kv                  # 23.84 W [V] bound at Vmin
    p_adp_typ, p_adp_wst = 11.7, 13.4             # [V]

    return dict(
        u1010=dict(
            uvlo_rising_v=round(uv_r, 3), uvlo_falling_v=round(uv_f, 3),
            ovp_rising_v=round(ov_r, 3), ovp_falling_v=round(ov_f, 3),
            iol_nom_a=round(iol_nom, 3), iol_max_a=round(iol_max, 3),
            uvlo_ton_ms=round((742 + 49.5 * 22) * 1e-3, 2),   # 1.83 ms
            ovp_ton_ms=round((150 + 49.5 * 22) * 1e-3, 2),    # 1.24 ms
            tdvdt_12v_ms=round(20.8e3 * 12.0 * 22e-9 * 1e3, 2),
        ),
        kv260=dict(
            mp5016h_uvlo_r=mp5016h_uvlo_r, mp5016h_uvlo_f=mp5016h_uvlo_f,
            mp5016h_ovp_v=13.2,
            mp8772_5v_min_11w=round(mp8772_min_11w, 2),
            mp8772_5v_min_36w=round(mp8772_min_36w, 2),
            mp8772_som475_36w=round(mp8772_som475_36w, 2),
            vmin_v=round(vmin_kv, 3),
            p_typ_w=p_kv_typ,
            p_bound_w=round(p_kv_bnd, 2),
        ),
        adapter=dict(
            lm74502_vs_min=3.2, lm74502_reverse_blocking=False,
            lmr33630_min_typ_v=round(lmr_min_typ, 2),
            lmr33630_min_worst_v=round(lmr_min_wst, 2),
            lmr33630_tps56x_floor_v=round(lmr_450_wst, 2),
            vmin_v=round(vmin_adp, 2),
            p_typ_w=p_adp_typ, p_worst_w=p_adp_wst,
        ),
    )


# ---------------------------------------------------------------------------- 3. 4-node transient solver
def run_transient(src_fn, ri, sched, disconnect=False, v0=13.5,
                  c12=47e-6*0.5+10e-6*0.5+0.22e-6*0.5, esr12=0.0,
                  ckv=47e-6, esrkv=0.0,
                  p_adp=13.4, p_kv=11.0,
                  adp_reverse_block=False,
                  upstream=None):
    """Backward-Euler 4-node solver reusing pa._solve4 and pa.TVS."""
    d1003 = pa.TVS(38.65, 53.3, 28.2, 1500.0)
    d1001 = pa.TVS(21.05, 29.2, 20.5, 600.0)
    d_smaj16 = pa.TVS(18.75, 26.0, 15.4, 400.0)
    L, r_l1004, rptc = 1.05e-6, 0.016, 0.040
    cvinj, cin = 10e-9, 100e-9
    ron_adp, ron_kv = 2 * 0.0135, 0.0135 + 0.031
    ov_on, ov_off = 18.33, 18.0
    kv_ov_on, kv_ov_off = 14.439, 13.500
    kv_uv_off, kv_uv_on = 7.476, 7.996
    kv_ilim = 3.0

    vinit = 12.0 if upstream is not None else v0
    il = (p_adp + p_kv) / vinit
    vinj = vinit - il * r_l1004
    vin = vinj - (p_adp / vinit) * rptc
    v12_c = vin - (p_adp / vinit) * ron_adp
    vkv_c = vinj - (p_kv / vinit) * ron_kv
    v12, vkv = v12_c, vkv_c

    fet_on, ov_t, on_t = True, 0.0, 0.0
    kv_on, kv_ov_t, kv_uv_t, kv_rcb_t, kv_rec_t = True, 0.0, 0.0, 0.0, 0.0
    ovp_tripped, uv_tripped = False, False

    v_conv = 12.0
    conv_on = True
    conv_v_prev = v0

    t_list, vs_list, vj_list, vf_list, v12_list, vkv_list = [-10e-6], [v0], [vinj], [vin], [v12], [vkv]
    vj_min, vj_max = vinj, vinj
    v12_min, v12_max = v12, v12
    vkv_min, vkv_max = vkv, vkv
    e1003, qds_max, vds_max = 0.0, 0.0, 0.0

    g_ptc = 1.0 / rptc
    g_kv_nom = 1.0 / ron_kv
    next_sample = 0.0

    for t_a, t_b, dt in sched:
        n_steps = max(1, int(round((t_b - t_a) / dt)))
        dt = (t_b - t_a) / n_steps
        for m in range(n_steps):
            t = t_a + (m + 1) * dt
            vs_raw = src_fn(t)

            if upstream is None:
                vs = vs_raw
                rs = ri
            else:
                v_in_conv = vs_raw
                if upstream.get("clamp_36v") and v_in_conv > 35.5:
                    v_in_conv = 35.5
                if v_in_conv < 0.0:
                    conv_on = False
                elif upstream.get("ov_cutoff") and v_in_conv > upstream["ov_cutoff"]:
                    conv_on = False
                elif v_in_conv < upstream["vin_min"] or v_in_conv > upstream["vin_max"]:
                    conv_on = False
                else:
                    if conv_on or (upstream["vin_min"] + 0.3 <= v_in_conv <= upstream["vin_max"] - 0.5):
                        conv_on = True

                dv = v_in_conv - conv_v_prev
                conv_v_prev = v_in_conv
                v_reg_tgt = upstream["vout"] + max(-0.25, min(0.25, 0.002 * dv))

                if conv_on:
                    v_conv = min(v_reg_tgt, v_conv + (12.0 / 3e-3) * dt) if v_conv < v_reg_tgt - 0.1 else v_reg_tgt
                    vs = v_conv
                    rs = upstream.get("rout", 0.02)
                else:
                    c_conv = upstream.get("cout", 470e-6)
                    v_conv = max(0.0, v_conv - (max(0.0, il) / c_conv) * dt)
                    vs = v_conv
                    rs = upstream.get("rout", 0.02)

            if adp_reverse_block:
                want_off = (vin > ov_on) or (vin < 0.5) or (vin < v12 - 0.05)
                ok_rec = (not (vin > ov_off or vin < 3.2)) and (vin >= v12)
            else:
                want_off = (vin > ov_on) or (vin < 0.5)
                ok_rec = not (vin > ov_off or vin < 3.2)

            if fet_on and want_off:
                ov_t += dt
                if ov_t >= 1e-6:
                    fet_on, on_t = False, 0.0
            elif fet_on:
                ov_t = 0.0
            elif ok_rec:
                on_t += dt
                if on_t >= 10e-6:
                    fet_on, ov_t = True, 0.0
            else:
                on_t = 0.0

            kv_want_ov = vinj > kv_ov_on
            kv_want_uv = vinj < kv_uv_off
            kv_want_rcb = (vinj < vkv - 0.05) or (vinj < 0.5)
            if kv_on:
                kv_ov_t = (kv_ov_t + dt) if kv_want_ov else 0.0
                kv_uv_t = (kv_uv_t + dt) if kv_want_uv else 0.0
                kv_rcb_t = (kv_rcb_t + dt) if kv_want_rcb else 0.0
                if kv_ov_t >= 11e-6:
                    kv_on, kv_rec_t, ovp_tripped = False, 0.0, True
                elif kv_rcb_t >= 0.17e-6:
                    kv_on, kv_rec_t = False, 0.0
                elif kv_uv_t >= 11e-6:
                    kv_on, kv_rec_t, uv_tripped = False, 0.0, True
            else:
                ok_kv = (kv_uv_on <= vinj <= kv_ov_off) and (vinj >= vkv)
                kv_rec_t = (kv_rec_t + dt) if ok_kv else 0.0
                if kv_rec_t >= 1.24e-3:
                    kv_on = True
                    kv_ov_t = kv_uv_t = kv_rcb_t = 0.0

            gf = 1.0 / ron_adp if fet_on else 0.0
            a_l = dt / L
            den = 1.0 + a_l * (rs + r_l1004)
            g_l = a_l / den
            g_c12 = 1.0 / (dt / c12 + esr12)
            g_ckv = 1.0 / (dt / ckv + esrkv)

            # Evaluate load outside Newton iteration, matching power_audit.py, bounded cleanly at the 4.0 V UVLO floor on coarse steps
            iload_const = min(p_adp / v12, max(0.0, (v12 - 3.98) * c12 / dt + gf * max(0.0, vin - 3.98))) if v12 > 4.0 else 0.0
            if vkv > 4.0:
                ikv_max_sup = kv_ilim if kv_on else 0.0
                ikv_const = min(p_kv / vkv, max(0.0, (vkv - 3.98) * ckv / dt + ikv_max_sup))
            else:
                ikv_const = 0.0

            x0, x1, x2, x3 = vinj, vin, v12, vkv
            for _ in range(8):
                il_n = (il + a_l * (vs - x0)) / den
                if kv_on and (x0 - x3) * g_kv_nom > kv_ilim:
                    ikv, gkv = kv_ilim + 1e-3 * (x0 - x3), 1e-3
                elif kv_on:
                    ikv, gkv = (x0 - x3) * g_kv_nom, g_kv_nom
                else:
                    ikv, gkv = 0.0, 0.0

                ic12_eq = (x2 - v12_c) * g_c12
                ickv_eq = (x3 - vkv_c) * g_ckv

                f0 = cvinj * (x0 - vinj) / dt - il_n + g_ptc * (x0 - x1) + ikv
                f1 = cin * (x1 - vin) / dt - g_ptc * (x0 - x1) + d1003.i(x1) + gf * (x1 - x2)
                f2 = ic12_eq - gf * (x1 - x2) + d1001.i(x2) + iload_const
                f3 = ickv_eq - ikv + d_smaj16.i(x3) + ikv_const

                A = [
                    [cvinj / dt + g_l + g_ptc + gkv, -g_ptc, 0.0, -gkv],
                    [-g_ptc, cin / dt + g_ptc + d1003.g(x1) + gf, -gf, 0.0],
                    [0.0, -gf, g_c12 + gf + d1001.g(x2), 0.0],
                    [-gkv, 0.0, 0.0, g_ckv + gkv + d_smaj16.g(x3)],
                ]
                dx0, dx1, dx2, dx3 = pa._solve4(A, [-f0, -f1, -f2, -f3])
                x0 += dx0; x1 += dx1; x2 += dx2; x3 += dx3
                if abs(dx0) < 1e-6 and abs(dx1) < 1e-6 and abs(dx2) < 1e-6 and abs(dx3) < 1e-6:
                    break

            il = (il + a_l * (vs - x0)) / den
            v12_c += ((x2 - v12_c) * g_c12) * dt / c12
            vkv_c += ((x3 - vkv_c) * g_ckv) * dt / ckv
            vinj, vin, v12, vkv = x0, x1, x2, x3

            i3 = d1003.i(vin)
            e1003 += abs(vin * i3) * dt
            if not fet_on:
                vds_max = max(vds_max, abs(vin - v12))
            if not kv_on:
                qds_max = max(qds_max, abs(vinj - vkv))

            vj_min = min(vj_min, vinj); vj_max = max(vj_max, vinj)
            v12_min = min(v12_min, v12); v12_max = max(v12_max, v12)
            vkv_min = min(vkv_min, vkv); vkv_max = max(vkv_max, vkv)

            if t >= next_sample or m == n_steps - 1:
                t_list.append(t)
                vs_list.append(vs_raw)
                vj_list.append(vinj)
                vf_list.append(vin)
                v12_list.append(v12)
                vkv_list.append(vkv)
                next_sample = t + max(dt, sched[-1][1] / 1200.0)

    return (
        dict(t=np.array(t_list), vsrc=np.array(vs_list), vinj=np.array(vj_list),
             vin=np.array(vf_list), v12=np.array(v12_list), vkv=np.array(vkv_list)),
        dict(vinj_min=round(vj_min, 2), vinj_max=round(vj_max, 2),
             v12_min=round(v12_min, 2), v12_max=round(v12_max, 2),
             vkv_min=round(vkv_min, 2), vkv_max=round(vkv_max, 2),
             q1010_vds_max=round(qds_max, 2), vds_max=round(vds_max, 2),
             e1003=round(e1003, 3), ovp_tripped=ovp_tripped, uv_tripped=uv_tripped,
             kv_uv_ok=(vkv_min >= 7.476),
             adp_uv_ok=(v12_min >= 5.59),
             kv_running=(vkv_min >= 7.476 and vkv_max < 13.2),
             adp_running=(v12_min >= 5.59 and v12_max < 25.0))
    )


# ---------------------------------------------------------------------------- 4. Main study
def main():
    dev = device_thresholds()
    vmin_kv = dev["kv260"]["vmin_v"]         # 7.476 V
    vmin_adp = dev["adapter"]["vmin_v"]      # 5.59 V
    p_kv_t, p_kv_b = dev["kv260"]["p_typ_w"], dev["kv260"]["p_bound_w"]
    p_adp_t, p_adp_w = dev["adapter"]["p_typ_w"], dev["adapter"]["p_worst_w"]

    print("=== 1. CUT-OFF THRESHOLDS & LOADS ===")
    print(json.dumps(dev, indent=2))

    events = [
        dict(id="pulse2a", label="ISO 7637-2 Pulse 2a (+112 V, 2 Ohm, 50 us)", v0=13.5, t_kv=1.35e-3, t_adp=0.10e-3,
             note="50 us spike + U1010 1.24 ms OVP_ton(dly) (PGTH=GND)"),
        dict(id="pulse1_td", label="ISO 7637-2 Pulse 1 spike alone (t_d = 2 ms)", v0=13.5, t_kv=2.0e-3, t_adp=2.0e-3,
             note="Negative pulse only; unrealistic unless supply reconnects immediately"),
        dict(id="pulse1_t2", label="ISO 7637-2 Pulse 1 full disconnect (t_2 = 200 ms)", v0=13.5, t_kv=0.202, t_adp=0.200,
             note="Table 2 / Fig 5 supply off t2=200 ms + U1010 1.83 ms UVLO_ton"),
        dict(id="load_dump_b", label="ISO 16750-2 Load Dump B (35 V, 0.5 Ohm, 400 ms)", v0=13.5, t_kv=0.401, t_adp=0.400,
             note="Table 7 max td=400 ms > OVP"),
        dict(id="load_dump_a", label="ISO 16750-2 Load Dump A (87 V, 1 Ohm, 400 ms)", v0=13.5, t_kv=0.757, t_adp=0.485,
             note="Table 6 tail > OVP; D1003 fails on bare board (116.5 J > 29.7 J)"),
        dict(id="jump_start", label="ISO 16750-2 Jump Start (24 V, 60 s)", v0=13.5, t_kv=60.0, t_adp=60.0,
             note="Clause 4.3.1.2 duration 60 s above OVP"),
        dict(id="reverse", label="ISO 16750-2 Reverse Battery (-14 V, 60 s)", v0=13.5, t_kv=60.0, t_adp=60.0,
             note="Clause 4.7 service fault 60 s (module off, protected)"),
        dict(id="crank_I", label="ISO 16750-2 Cranking Level I (8.0 V / 9.5..11.5 V)", v0=12.0, t_kv=0.0, t_adp=0.0,
             note="Always >= 8.0 V > Vmin_KV 7.48 V and Vmin_adp 5.59 V: no hold-up needed"),
        dict(id="crank_IV", label="ISO 16750-2 Cranking Level IV (6.0 V, 6.5..8.5 V, 10 s)", v0=12.0, t_kv=10.12, t_adp=0.0,
             note="6.0 V > 5.59 V adapter stays on; KV260 bank discharged across 10 s"),
        dict(id="crank_II", label="ISO 16750-2 Cranking Level II (4.5 V, 6.5..8.5 V, 10 s)", v0=12.0, t_kv=10.12, t_adp=0.038,
             note="KV260 Q1010 blocks 10 s; adapter < 5.59 V 38 ms (if reverse-blocked)"),
        dict(id="crank_III", label="ISO 16750-2 Cranking Level III (3.0 V, 5.0..7.0 V, 1 s)", v0=12.0, t_kv=1.13, t_adp=1.13,
             note="5..7 V ripple < UVLO rising (8.00 V) for full 1.13 s"),
    ]

    UHE_4700_25 = dict(part="UHE1E472MHD", mouser="647-UHE1E472MHD", uF=4700, v=25, dia=16.0, h=40.0,
                       esr_mohm=13.0, irip_a=4.08, life_105c_h=10000, life_85c_h=40000)
    UHE_1000_25 = dict(part="UHE1E102MHD6", mouser="647-UHE1E102MHD6", uF=1000, v=25, dia=12.5, h=20.0,
                       esr_mohm=35.0, irip_a=1.90, life_105c_h=10000, life_85c_h=40000)

    slew_dvdt = 12.0 / (20.8e3 * 12.0 * 22e-9)   # 2185 V/s
    c_knee_f = dev["u1010"]["iol_nom_a"] / slew_dvdt
    r_th_ja = 32.2
    p_reg_70 = (145.0 - 70.0) / r_th_ja
    c_treg_max_70_f = 2.0 * (p_reg_70 * 2.30) / (12.0 ** 2)

    print("\n=== 2. HOLD-UP ENERGY, CAPACITANCE & U1010 THERMAL / BANK CHECK ===")
    holdup_rows = []
    for ev in events:
        v0 = ev["v0"]
        dv2_kv = v0**2 - vmin_kv**2
        dv2_kv562 = v0**2 - 5.62**2
        dv2_adp = v0**2 - vmin_adp**2
        ek_t, ek_b = p_kv_t * ev["t_kv"], p_kv_b * ev["t_kv"]
        ck_t, ck_b = 2.0 * ek_t / dv2_kv, 2.0 * ek_b / dv2_kv
        ck_562_b = 2.0 * (3.19 * 5.62 * ev["t_kv"]) / dv2_kv562
        ea_t, ea_w = p_adp_t * ev["t_adp"], p_adp_w * ev["t_adp"]
        ca_t, ca_w = 2.0 * ea_t / dv2_adp, 2.0 * ea_w / dv2_adp

        if ck_t == 0.0:
            i_chg, t_chg_ms, e_fet_j, u1010_ok = 0.0, 0.0, 0.0, True
        else:
            i_dvdt = ck_t * slew_dvdt
            if i_dvdt <= dev["u1010"]["iol_nom_a"]:
                i_chg = i_dvdt
                t_chg_ms = 5.49
            else:
                i_chg = dev["u1010"]["iol_nom_a"]
                t_chg_ms = ck_t * 12.0 / i_chg * 1e3
            e_fet_j = 0.5 * ck_t * (12.0 ** 2)
            u1010_ok = (ck_t <= c_treg_max_70_f and t_chg_ms <= 65.0)

        c_tot_mf = (ck_t + ca_w) * 1e3
        c_tot_bnd_mf = (ck_b + ca_w) * 1e3
        if c_tot_mf == 0.0:
            n_cans, n_cans_bnd, can = 0, 0, None
        elif c_tot_bnd_mf <= 1.0:
            can = UHE_1000_25
            n_cans = max(1, math.ceil(c_tot_mf / 1.0))
            n_cans_bnd = max(1, math.ceil(c_tot_bnd_mf / 1.0))
        else:
            can = UHE_4700_25
            n_cans = math.ceil(c_tot_mf / 4.7)
            n_cans_bnd = math.ceil(c_tot_bnd_mf / 4.7)
        vol_cm3 = 0.0 if n_cans == 0 else n_cans * (can["dia"] ** 2) * can["h"] * 1e-3

        row = dict(
            id=ev["id"], label=ev["label"], v0=v0, t_kv_ms=round(ev["t_kv"]*1e3, 2), t_adp_ms=round(ev["t_adp"]*1e3, 2),
            e_kv_typ_j=round(ek_t, 3), e_kv_bnd_j=round(ek_b, 3),
            c_kv_typ_mf=round(ck_t*1e3, 2), c_kv_bnd_mf=round(ck_b*1e3, 2),
            c_kv_5v62_mf=round(ck_562_b*1e3, 2),
            c_adp_typ_mf=round(ca_t*1e3, 2), c_adp_wst_mf=round(ca_w*1e3, 2),
            u1010_ichg_a=round(i_chg, 2), u1010_tchg_ms=round(t_chg_ms, 1), u1010_efet_j=round(e_fet_j, 2),
            u1010_startup_ok=u1010_ok,
            bank_part=(can["part"] if can else "none"),
            bank_cans_typ=n_cans,
            bank_cans_bnd=n_cans_bnd,
            bank_packed_cm3=round(vol_cm3, 1),
            fits_enclosure=(n_cans <= 1 and (can is None or can["h"] <= 20.0)),
            note=ev["note"],
        )
        holdup_rows.append(row)
        print(f"  {ev['id']:12s}: E_KV={ek_t:6.2f}/{ek_b:6.2f} J | C_KV={ck_t*1e3:7.2f}/{ck_b*1e3:8.2f} mF | "
              f"C_ADP={ca_t*1e3:6.2f}/{ca_w*1e3:7.2f} mF | t_chg={t_chg_ms:7.1f} ms ({'OK' if u1010_ok else 'FAIL'}) | "
              f"cans={n_cans}..{n_cans_bnd} x {row['bank_part']} ({row['bank_packed_cm3']} cm3)")

    print("\n=== 3. TRANSIENT SOLVER VERIFICATION OF HOLD-UP BANKS ===")
    solver_holdup = []
    # Check both exact closed-form banks and practical discrete Nichicon UHE banks (adding ~15% for IR drop + U1010 UVLO recovery)
    checks = [
        ("pulse2a",      "Pulse 2a with 1 x 1 mF KV260 + 0.1 mF adp",                      1.0e-3,  0.035,  0.10e-3, 0.0,    True),
        ("pulse1_200ms", "Pulse 1 (t2=200 ms) exact 8x4.7mF (37.6 mF) both rails",         37.6e-3, 0.0016, 37.6e-3, 0.0016, True),
        ("pulse1_200ms", "Pulse 1 (t2=200 ms) practical 9x4.7mF (42.3 mF) both rails",     42.3e-3, 0.0014, 42.3e-3, 0.0014, True),
        ("load_dump_b",  "Load Dump B (400 ms) 16x4.7mF (75.2 mF) KV + 16x4.7mF adp",      75.2e-3, 0.0008, 75.2e-3, 0.0008, True),
        ("crank_I",      "Cranking Level I (8.0 V, stock C = 47 uF / 28.6 uF)",             47e-6,   0.0,    28.6e-6, 0.0,    False),
        ("crank_II",     "Cranking Level II (10.1 s) unblocked LM74502 (back-feed demo)",  2.70,    0.0001, 12.0e-3, 0.006,  False),
        ("crank_II",     "Cranking Level II (10.1 s) 2.70 F KV + 12 mF adp (rev-blocked)", 2.70,    0.0001, 12.0e-3, 0.006,  True),
        ("crank_III",    "Cranking Level III (1.13 s) 300 mF KV + 282 mF adp (rev-blocked)",0.30,   0.0002, 0.282,   0.0002, True),
    ]
    for cid, label, ckv_b, esrk, c12_b, esr12, rb in checks:
        fn, ri, sched, disc, _, v0 = pulse_wave(cid)
        _, r = run_transient(fn, ri, sched, disc, v0=v0, c12=c12_b, esr12=esr12,
                             ckv=ckv_b, esrkv=esrk, p_adp=13.4, p_kv=11.0, adp_reverse_block=rb)
        solver_holdup.append(dict(label=label, ckv_mf=round(ckv_b*1e3, 2), c12_mf=round(c12_b*1e3, 2),
                                  rev_block=rb, **r))
        print(f"  {label:64s} -> +12V={r['v12_min']:5.2f}..{r['v12_max']:5.2f} V ({'OK' if r['adp_uv_ok'] else 'DROP'}), "
              f"+12V_KV={r['vkv_min']:5.2f}..{r['vkv_max']:5.2f} V ({'OK' if r['kv_uv_ok'] else 'DROP'})")

    # Upstream SM8S33A check vs Load Dump A (87 V, 1 Ohm, 400 ms)
    tau_ld = 0.4 / math.log(10.0)
    rd_sm8 = (53.3 - 38.65) / 124.0
    dt_ld = 1e-4
    e_sm8, v_sm8_pk = 0.0, 0.0
    for i in range(6000):
        t = i * dt_ld
        vs = 13.5 + 73.5 * min(1.0, t / 5e-3) * math.exp(-max(t - 5e-3, 0.0) / tau_ld)
        if vs > 38.65:
            itvs = (vs - 38.65) / (1.0 + rd_sm8)
            vc = 38.65 + itvs * rd_sm8
            e_sm8 += vc * itvs * dt_ld
            v_sm8_pk = max(v_sm8_pk, vc)
    lim_sm8 = pa.tvs_energy_limit(6600.0, 0.4 * 0.7)

    # ---------------------------------------------------------------------------- 5. Converter-fed transients
    conv_spec = dict(name="Specified 4.3-36 V buck-boost + 36 V Load Dump A limiter",
                     vin_min=4.3, vin_max=36.0, vout=12.0, rout=0.02, cout=470e-6, clamp_36v=True)
    conv_bicker = dict(name="Bicker DC160WS (6-36 V -> 12 V 8.3/13.3 A) + 36 V Load Dump A limiter",
                       vin_min=6.0, vin_max=36.0, vout=12.0, rout=0.02, cout=470e-6, clamp_36v=True)
    conv_minibox = dict(name="Mini-Box DCDC-USB-200 (6-34 V -> 12 V 6-12 A) + 36 V limiter + rev block",
                        vin_min=6.0, vin_max=34.0, vout=12.0, rout=0.02, cout=470e-6, clamp_36v=True)

    run_events = [
        ("pulse1_200ms", "ISO 7637-2 Pulse 1 (-150 V, t2 = 200 ms disconnect)"),
        ("pulse2a",      "ISO 7637-2 Pulse 2a (+112 V, 2 Ohm, 50 us)"),
        ("pulse3a",      "ISO 7637-2 Pulse 3a (-220 V, 50 Ohm, 0.1 us)"),
        ("pulse3b",      "ISO 7637-2 Pulse 3b (+150 V, 50 Ohm, 0.1 us)"),
        ("load_dump_b",  "ISO 16750-2 Load Dump B (35 V, 0.5 Ohm, 400 ms)"),
        ("load_dump_a",  "ISO 16750-2 Load Dump A (87 V, 1 Ohm, 400 ms)"),
        ("jump_start",   "ISO 16750-2 Jump Start (24 V, 60 s)"),
        ("reverse",      "ISO 16750-2 Reverse Battery (-14 V, 60 s)"),
        ("crank_I",      "ISO 16750-2 Cranking Level I (8.0 V / 9.5..11.5 V, 1 s)"),
        ("crank_IV",     "ISO 16750-2 Cranking Level IV (6.0 V / 6.5..8.5 V, 10 s)"),
        ("crank_II",     "ISO 16750-2 Cranking Level II (4.5 V / 6.5..8.5 V, 10 s)"),
        ("crank_III",    "ISO 16750-2 Cranking Level III (3.0 V / 5.0..7.0 V, 1 s)"),
    ]

    print("\n=== 4. CONVERTER-FED TRANSIENT RE-RUNS ===")
    conv_rows = []
    traces_bare, traces_spec, traces_bicker = {}, {}, {}
    for cid, elabel in run_events:
        fn, ri, sched, disc, _, v0 = pulse_wave(cid)
        ab, rb = run_transient(fn, ri, sched, disc, v0=v0, upstream=None)
        as_, rs = run_transient(fn, ri, sched, disc, v0=v0, upstream=conv_spec)
        ak, rk = run_transient(fn, ri, sched, disc, v0=v0, upstream=conv_bicker)
        am, rm = run_transient(fn, ri, sched, disc, v0=v0, upstream=conv_minibox)
        traces_bare[cid], traces_spec[cid], traces_bicker[cid] = ab, as_, ak

        def conv_status(r):
            return "Class A (runs)" if (r["kv_running"] and r["adp_running"]) else "Class C (reset)"

        if cid == "load_dump_a" and rb["e1003"] > 29.7:
            bare_status = "FAIL (D1003 burns)"
        elif (not rb["ovp_tripped"]) and (not rb["uv_tripped"]) and rb["kv_uv_ok"] and rb["adp_uv_ok"]:
            bare_status = "Class A at 12 V (UA 13.5 V > 13.2 V OVP)" if rb["vkv_max"] >= 13.2 else "Class A (runs)"
        else:
            bare_status = "Class C (reset)"

        row = dict(
            id=cid, label=elabel,
            bare=dict(vkv_min=rb["vkv_min"], vkv_max=rb["vkv_max"], e1003=rb["e1003"],
                      status=bare_status),
            spec_4v3_36v=dict(vkv_min=rs["vkv_min"], vkv_max=rs["vkv_max"],
                              v12_min=rs["v12_min"], v12_max=rs["v12_max"], status=conv_status(rs)),
            bicker_dc160ws=dict(vkv_min=rk["vkv_min"], vkv_max=rk["vkv_max"], status=conv_status(rk)),
            minibox_usb200=dict(vkv_min=rm["vkv_min"], vkv_max=rm["vkv_max"], status=conv_status(rm)),
        )
        conv_rows.append(row)
        print(f"  {elabel:55s} | bare={row['bare']['status']:18s} | 4.3-36V={row['spec_4v3_36v']['status']:15s} | "
              f"DC160WS={row['bicker_dc160ws']['status']:15s} | USB200={row['minibox_usb200']['status']:15s}")

    # Also compute a zoomed 0..150 ms view of Cranking Level II so the 4.5 V / 15 ms notch is legible
    fn_c2, ri_c2, _, disc_c2, _, v0_c2 = pulse_wave("crank_II")
    sched_zoom = [(0.0, 0.150, 10e-6)]
    ab_c2z, _ = run_transient(fn_c2, ri_c2, sched_zoom, disc_c2, v0=v0_c2, upstream=None)
    as_c2z, _ = run_transient(fn_c2, ri_c2, sched_zoom, disc_c2, v0=v0_c2, upstream=conv_spec)
    ak_c2z, _ = run_transient(fn_c2, ri_c2, sched_zoom, disc_c2, v0=v0_c2, upstream=conv_bicker)

    # ---------------------------------------------------------------------------- 6. Plot docs/sim/ride_through.png
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.size": 8.5})

    panels = [
        ("pulse1_200ms",  "ISO 7637-2 Pulse 1 (t2 = 200 ms disconnect)", None),
        ("pulse2a",       "ISO 7637-2 Pulse 2a (+112 V, 50 us)", None),
        ("load_dump_b",   "ISO 16750-2 Load Dump B (35 V, 400 ms)", None),
        ("load_dump_a",   "ISO 16750-2 Load Dump A (87 V + 36 V limiter)", None),
        ("crank_II_zoom", "ISO 16750-2 Cranking Level II (first 150 ms of 10 s)", (ab_c2z, as_c2z, ak_c2z)),
        ("crank_IV",      "ISO 16750-2 Cranking Level IV (6.0 V / 10 s)", None),
        ("crank_III",     "ISO 16750-2 Cranking Level III (3.0 V / 1 s)", None),
        ("jump_start",    "ISO 16750-2 Jump Start (24 V, 60 s)", None),
    ]
    fig, axs = plt.subplots(2, 4, figsize=(15.5, 7.6))
    for ax, (cid, title, custom) in zip(axs.flat, panels):
        if custom is None:
            ab, as_, ak = traces_bare[cid], traces_spec[cid], traces_bicker[cid]
        else:
            ab, as_, ak = custom
        sc = 1e6 if ab["t"][-1] < 5e-3 else (1.0 if ab["t"][-1] > 1.5 else 1e3)
        un = "us" if sc == 1e6 else ("s" if sc == 1.0 else "ms")
        ax.plot(ab["t"] * sc, np.clip(ab["vsrc"], -25, 45), c="#95a5a6", lw=0.95, label="Vehicle bus (clipped)")
        ax.plot(ab["t"] * sc, ab["vkv"], c="#c0392b", lw=1.1, ls="--", label="Bare board +12V_KV")
        ax.plot(ak["t"] * sc, ak["vkv"], c="#d35400", lw=1.3, ls=":", label="Bicker DC160WS (6-36 V)")
        ax.plot(as_["t"] * sc, as_["vkv"], c="#1e8449", lw=1.5, label="Spec buck-boost (4.3-36 V)")
        ax.axhline(vmin_kv, c="#2c3e50", ls=":", lw=0.75)
        ax.axhline(13.2, c="#7f8c8d", ls="-.", lw=0.7)
        ax.set_title(title, fontsize=8.5, pad=4)
        ax.set_xlabel(un, fontsize=7.5)
        ax.set_ylim(-5, 28)
        ax.grid(alpha=0.25)
    axs[0, 0].set_ylabel("Voltage (V)", fontsize=8)
    axs[1, 0].set_ylabel("Voltage (V)", fontsize=8)
    handles, labels = axs[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", bbox_to_anchor=(0.5, 0.945), ncol=4, fontsize=8, frameon=True)
    fig.suptitle(
        "Single-entry +12V_KV response: bare board vs upstream automotive buck-boost (dotted: 7.48 V UVLO, dash-dot: 13.2 V KV260 OVP)",
        fontsize=10.5, y=0.985,
    )
    fig.tight_layout(rect=[0, 0, 1, 0.905])
    png_path = os.path.join(OUT, "ride_through.png")
    fig.savefig(png_path, dpi=150)
    plt.close(fig)

    out = dict(
        standards=dict(
            iso16750_2_cranking=CRANK_LEVELS,
            iso7637_2_pulse1="ISO 7637-2:2011 Table 2 / Fig 5: -150 V, 10 Ohm, td=2 ms, t2=200 ms disconnect",
            iso16750_2_load_dump="ISO 16750-2:2012 Tables 6-7: Test A 87 V (79-101 V), 1 Ohm, 400 ms; Test B 35 V, 0.5 Ohm, 400 ms",
        ),
        thresholds=dev,
        u1010_thermal=dict(
            tdvdt_12v_ms=dev["u1010"]["tdvdt_12v_ms"],
            slew_v_per_s=round(slew_dvdt, 1),
            iol_knee_mf=round(c_knee_f * 1e3, 2),
            r_theta_ja_c_per_w=r_th_ja,
            p_reg_70c_w=round(p_reg_70, 2),
            c_treg_noload_70c_mf=round(c_treg_max_70_f * 1e3, 1),
        ),
        sm8s33a_load_dump_a=dict(
            v_clamp_peak_v=round(v_sm8_pk, 2),
            energy_j=round(e_sm8, 1),
            wunsch_bell_limit_j=round(lim_sm8, 1),
            ok=bool(e_sm8 < lim_sm8 and v_sm8_pk <= 36.0),
        ),
        holdup_events=holdup_rows,
        holdup_solver_verification=solver_holdup,
        converter_spec=dict(
            topology="4-switch synchronous buck-boost (plus an upstream 36 V Load Dump A surge stopper that clamps, such as LT4363)",
            output_v="12.0 V +-2 % (11.76-12.24 V < 13.2 V KV260 MP5016H OVP)",
            current_min_a=5.0,
            power_min_w=60.0,
            input_range_v="4.3 to 36.0 V continuous (ISO 16750-2 Level II cranking min 4.5-0.2 V, Load Dump B 35 V, Jump Start 24 V 60 s)",
            reverse_v="-14 V for 60 s (ISO 16750-2 4.7)",
            load_dump_a_87v="Requires upstream 36 V active surge stopper (SM8S33A alone reaches 43.8 V / 141.7 J > 130.7 J limit)",
            startup_rise="Monotonic 2-20 ms into U1010 dVdT (5.49 ms), no dwell in 7.48-8.00 V hysteresis",
        ),
        cots_modules=[
            dict(
                part="Bicker Elektronik DC160WS",
                url="https://www.bicker.de/en/dc160ws",
                vin_v="6.0-36.0 V",
                vout_v="12.0 V +-3 % (11.64-12.36 V, jumper-selected), 120 mVpp ripple",
                iout_a="8.3 A (100 W) free air, 13.3 A (160 W) chassis-cooled",
                temp_c="-20 to +70 C",
                protections="Reverse polarity, SCP, OTP, OVP (+28 V)",
                missed=["6.0 V min misses Level II cranking (4.5 V) and Level III (3.0 V); passes Level I and IV",
                        "36 V max needs upstream 36 V limiter for unsuppressed 87 V Load Dump A",
                        "-20 C lower rating vs -40 C; start-up rise time unstated in datasheet"],
            ),
            dict(
                part="Mini-Box DCDC-USB-200 (Dumb Mode)",
                url="https://resources.mini-box.com/online/PWR-DCDC-USB-200/PWR-DCDC-USB-200-manual.pdf",
                vin_v="6.0-34.0 V (electronic shutdown at 34 V, clamps 34-36 V)",
                vout_v="12.0 V +-2.5 % (11.70-12.30 V)",
                iout_a="6 A at 6 V in, 9-12 A at 9-18 V (forced air > 60 W or > 65 C)",
                temp_c="-40 to +85 C (-20 to +65 C chassis)",
                protections="15 A input limit, 20 A fuse, TVS; must set J7 Dumb Mode",
                missed=["6.0 V min misses Level II (4.5 V) and Level III (3.0 V)",
                        "34 V max trips 1 V short of 35 V Load Dump B and fails 87 V Load Dump A without upstream limiter",
                        "No active reverse-polarity blocking listed (fuse-only without external ideal diode)"],
            ),
        ],
        converter_transients=conv_rows,
    )
    json_path = os.path.join(OUT, "ride_through.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    print(f"\nwrote {json_path} and {png_path}")


if __name__ == "__main__":
    main()
