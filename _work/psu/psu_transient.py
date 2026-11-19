#!/usr/bin/env python3
"""
PSU board: time-domain simulation of every vehicle event of ISO 7637-2 and ISO 16750-2, and of the faults, with
both boards as the load. Averaged model (the switching ripple is in psu_design.py and psu_emi.py):

  source (the standard's waveform and its internal resistance; ride_through.py's definitions) -> harness
  (R_HARNESS, 2 uH) -> node A: input clamp D1 + D2, 0.2 uF -> U1 LTC4364: M1 (on, or regulating node B at
  V_CLAMP, with the fault timer), M2 (ideal diode: no reverse current); VCC = max(A, +12V bus) - 0.3 V, needs 4 V
  -> nodes B0 + B: 4 x 4.7 uF + 47 uF electrolytic (0.6 ohm) -> L3 + L2 1.47 uH -> node C: 4 x 4.7 uF + 2 x 100 uF electrolytic (0.15 ohm,
  the filter's damping) -> LM5177 (constant
  input power P_out / efficiency(VIN, P_out) from psu_design.py, input current limit, UVLO 3.0 / 6.0 V, 4.7 ms soft
  start, an 8.5 kHz voltage loop) -> +12V bus, 259 uF -> U3 / U4 TPS26631 (UVLO 8.00 / 7.48 V, OVP 14.44 / 13.50
  V, current limit) -> the adapter (60 uF [E], constant power, stops below 5.59 V) and the KV260 (100 uF [E],
  constant power, resets below 5.48 V).

A board "runs" (ISO 16750-1 functional status A) through an event if its own input never fell below its cut-off;
otherwise it reset and restarted (status C), unless something was damaged (FAIL: a rating exceeded).

Writes docs/sim/psu_transient.json and docs/sim/psu_transient.png.

Usage:  py _work/psu/psu_transient.py
"""
import json
import math
import os
import sys

import numpy as np
from scipy.integrate import solve_ivp
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "power"))
import psu_params as P                                    # noqa: E402
import psu_design as D                                    # noqa: E402
import ride_through as RT                                 # noqa: E402  (the standards' waveforms)

ROOT = os.path.dirname(os.path.dirname(HERE))
OUT_JSON = os.path.join(ROOT, "docs", "sim", "psu_transient.json")
OUT_PNG = os.path.join(ROOT, "docs", "sim", "psu_transient.png")

L_H = 2e-6
C_A = 0.2e-6
C_BC, C_E, ESR_E = 4 * 4.7e-6 * 0.7, 47e-6, 0.6      # nodes B0 + B (merged): 4 x 4.7 uF, LTC4364 OUT bypass EEE-FK1J470P (0.65 ohm at 100 kHz)
L2, R_L2 = 0.47e-6 + 1.0e-6, 0.88e-3 + 1.5e-3       # L3 + L2 in series (B0 and B merged)
C_C = 4 * 4.7e-6 * 0.7
C_EC, ESR_EC = 200e-6, 0.15                            # node C: the damping electrolytics, 2 x EEE-FK1J101P (0.35 ohm each at 100 kHz)
C_OUT = D.COUT_EFF
C_KV, C_AD = 100e-6, 60e-6          # [E] the KV260's and the adapter's own input capacitance
V_KV_OFF, V_AD_OFF = 5.48, 5.59    # [V] ride_through.py: MP8772 and LMR33630 drop-out
R_M = P.IPB048N15N5["rds_10"] * P.IPB048N15N5["tc"] + P.BSC040N10NS5["rds_10"] * P.BSC040N10NS5["tc"]
R_EF = D.R_EFUSE
V = D.values()
I_LIM_IN = V["iin_limit"][0]
KP = 2 * math.pi * 8.5e3 * C_OUT * P.VOUT          # W/V, the voltage loop as a power loop (plant 1/(s C V))
KI = KP * 2 * math.pi * 1.7e3

# efficiency table from the steady-state model
_VG = np.array([2.9, 3.5, 4.3, 5.0, 6.0, 8.0, 10.0, 12.0, 13.5, 16.0, 20.0, 24.0, 30.0, 36.0, 42.0, 48.0, 60.0])
_PG = np.array([2.0, 10.0, 20.0, 30.0, 40.0, 52.0, 60.0])
_EFF = np.array([[D.operating_point(v, p, v=V)["eff"] for p in _PG] for v in _VG])


def eff(vin, pout):
    vin = min(max(vin, _VG[0]), _VG[-1])
    pout = min(max(pout, _PG[0]), _PG[-1])
    i = np.searchsorted(_VG, vin) - 1
    j = np.searchsorted(_PG, pout) - 1
    i, j = max(min(i, len(_VG) - 2), 0), max(min(j, len(_PG) - 2), 0)
    a = (vin - _VG[i]) / (_VG[i + 1] - _VG[i])
    b = (pout - _PG[j]) / (_PG[j + 1] - _PG[j])
    return ((1 - a) * (1 - b) * _EFF[i, j] + a * (1 - b) * _EFF[i + 1, j] + (1 - a) * b * _EFF[i, j + 1]
            + a * b * _EFF[i + 1, j + 1])


def smooth(x, w=0.15):
    """0 below, 1 above, over about w volts: a board's own undervoltage stop, without a discontinuity."""
    return 1.0 / (1.0 + math.exp(-max(min(x / w, 40.0), -40.0)))


def tvs_pair(v):
    """D1 (SMCJ100A) + D2 (SMCJ24A) in series, opposed; worst-case (lowest) breakdown for the stress on them."""
    p, n = P.SMCJ100A, P.SMCJ24A
    rp = (p["vc"] - p["vbr_max"]) / p["ipp"]
    rn = (n["vc"] - n["vbr_max"]) / n["ipp"]
    if v > p["vbr_min"] + 0.8:
        return (v - p["vbr_min"] - 0.8) / (rp + 0.02)
    if v < -(n["vbr_min"] + 0.8):
        return (v + n["vbr_min"] + 0.8) / (rn + 0.02)
    return 0.0


class Sim:
    def __init__(self, src, ri, disconnect=None, p_kv=11.0, p_ad=11.7, short_kv_at=None, v0=13.5, ri_window=None):
        self.src, self.ri, self.disc = src, ri, disconnect
        self.ri_window = ri_window      # ISO 7637-2: the generator's Ri only while its pulse lasts
        self.p_kv, self.p_ad = p_kv, p_ad
        self.short_kv_at = short_kv_at
        # discrete state
        self.conv_on, self.ss_t0 = True, -1.0
        self.u3_on = self.u4_on = True
        self.kv_ok = self.ad_ok = True
        self.m1_on, self.tmr = True, 0.0
        self.y0 = np.array([0.0, v0, v0, v0, 0.0, v0, P.VOUT, (p_kv + p_ad) * 1.05, P.VOUT, P.VOUT, v0])
        self.rec = {k: [] for k in ("t", "va", "vb", "vc", "vout", "vkv", "vad", "iin", "pm1", "itvs", "tmr")}
        self.flags = {"kv_reset": False, "ad_reset": False, "conv_restart": 0, "m1_fault": False}
        self.e = {"m1": 0.0, "tvs": 0.0}
        self.pk = {"m1": 0.0, "tvs": 0.0, "iin": 0.0}

    def rhs(self, t, y):
        ih, va, vb, ve, il2, vc, vo, x, vkv, vad, vec = y
        # source; during a disconnection the supply is open (only the pulse generator behind Ri is there)
        ri = self.ri
        if self.ri_window is not None and not (self.ri_window[0] <= t <= self.ri_window[1]):
            ri = 0.01                       # the supply's own resistance outside the pulse
        vs = self.src(t)
        if self.disc and self.disc[0] < t < self.disc[1]:
            ri = 1e6
        dih = (vs - (ri + P.R_HARNESS) * ih - va) / L_H
        # LTC4364
        vcc = max(va, vo) - 0.3
        im = 0.0
        if self.m1_on and vcc >= P.LTC4364["vcc_min"] and va > vb:
            im = (va - vb) / R_M
            im = min(im, max(0.0, 200.0 * (P.V_CLAMP + 0.2 - vb)))      # the surge stopper regulates node B
        itvs = tvs_pair(va)
        dva = (ih - itvs - im) / C_A
        ie = (vb - ve) / ESR_E
        dvb = (im - ie - il2) / C_BC
        dve = ie / C_E
        dil2 = (vb - vc - R_L2 * il2) / L2
        # LM5177, averaged
        pcmd = KP * (P.VOUT - vo) + x
        p_av = eff(vc, max(pcmd, 1)) * vc * I_LIM_IN
        ss = 1.0
        if self.ss_t0 >= 0:
            ss = min(1.0, (t - self.ss_t0) / V["t_ss"])
        on = self.conv_on and vc > V["vin_off"][1]
        pout = min(max(pcmd, 0.0), p_av) if on else 0.0
        vref = P.VOUT * ss
        pcmd = KP * (vref - vo) + x
        pout = min(max(pcmd, 0.0), p_av) if on else 0.0
        dx = KI * (vref - vo) if on and 0.0 < pcmd < p_av else 0.0
        iconv = (pout / eff(vc, max(pout, 1))) / max(vc, 0.5) if on else 0.0
        iec = (vc - vec) / ESR_EC
        dvc = (il2 - iconv - iec) / C_C
        # outputs
        iu3 = (vo - vad) / R_EF if (self.u3_on and vo > vad) else 0.0
        iu3 = min(iu3, P.TPS26631["ilim_k"] / D.e96(P.TPS26631["ilim_k"] / 2.0))
        iu4 = (vo - vkv) / R_EF if (self.u4_on and vo > vkv) else 0.0
        iu4 = min(iu4, P.I_KV_LIMIT)
        dvo = (pout / max(vo, 0.5) - iu3 - iu4) / C_OUT
        ikv = self.p_kv / max(vkv, V_KV_OFF) * smooth(vkv - V_KV_OFF)
        if self.short_kv_at is not None and t >= self.short_kv_at:
            ikv = vkv / 0.05
        iad = self.p_ad / max(vad, V_AD_OFF) * smooth(vad - V_AD_OFF)
        dvkv = (iu4 - ikv) / C_KV
        dvad = (iu3 - iad) / C_AD
        drop = max(va - vb, 0.0)
        pm1 = im * drop if drop > 1.0 else im * im * R_M        # linear (regulating) or fully on
        self._aux = (va, vb, vc, vo, vkv, vad, ih, pm1, itvs, vcc)
        return [dih, dva, dvb, dve, dil2, dvc, dvo, dx, dvkv, dvad, iec / C_EC]

    def step_discrete(self, t, y, dt):
        ih, va, vb, ve, il2, vc, vo, x, vkv, vad, vec = y
        # LTC4364 fault timer: runs while regulating (node B held at the clamp with M1 dropping volts)
        vcc = min(max(va, vo) - 0.3, 62.0)
        if self.m1_on and vb > P.V_CLAMP - 0.5 and va > vb + 0.5:
            self.tmr += (P.LTC4364["i_tmr0"] + P.LTC4364["k_tmr"] * max(vcc - vb - 0.5, 0)) * dt / P.C_TMR
            if self.tmr > P.LTC4364["vtmr_g"]:
                self.m1_on = False
                self.flags["m1_fault"] = True
        else:
            self.tmr = max(0.0, self.tmr - 2e-6 * dt / P.C_TMR)
        # LM5177 UVLO with hysteresis and soft start
        if self.conv_on and vc < V["vin_off"][1]:
            self.conv_on = False
        elif not self.conv_on and vc > V["vin_on"][1]:
            self.conv_on = True
            self.ss_t0 = t
            self.flags["conv_restart"] += 1
        # eFuses
        for name in ("u3_on", "u4_on"):
            on = getattr(self, name)
            if on and (vo < 7.48 or vo > 14.44):
                setattr(self, name, False)
            elif not on and 8.0 < vo < 13.5:
                setattr(self, name, True)
        if vkv < V_KV_OFF:
            self.flags["kv_reset"] = True
        if vad < V_AD_OFF:
            self.flags["ad_reset"] = True

    def be_step(self, t, y, h, depth=0):
        """One backward-Euler step, y' = y + h f(t+h, y'), by Newton with a finite-difference Jacobian (the
        network is stiff and piecewise; backward Euler is stable at any step). A step whose Newton iteration does
        not converge is split in two, down to h / 256."""
        x, ok = self._newton(t, y, h)
        if ok or depth >= 8:
            return x
        y1 = self.be_step(t, y, h / 2, depth + 1)
        return self.be_step(t + h / 2, y1, h / 2, depth + 1)

    def _newton(self, t, y, h):
        n = len(y)
        x = y + h * np.asarray(self.rhs(t + h, y))
        eye = np.eye(n)
        for it in range(8):
            fx = np.asarray(self.rhs(t + h, x))
            g = x - y - h * fx
            if it and np.max(np.abs(g)) < 1e-7:
                break
            jac = np.empty((n, n))
            for k in range(n):
                d = 1e-6 * max(1.0, abs(x[k]))
                xk = x.copy()
                xk[k] += d
                jac[:, k] = (np.asarray(self.rhs(t + h, xk)) - fx) / d
            x = x - np.linalg.solve(eye - h * jac, g)
        g = x - y - h * np.asarray(self.rhs(t + h, x))
        return x, bool(np.max(np.abs(g)) < 1e-5)

    def run(self, segments):
        y = self.y0.copy()
        for (t0, t1, dt) in segments:
            t = t0
            while t < t1 - 1e-12:
                tn = min(t + dt, t1)
                y = self.be_step(t, y, tn - t)
                self.rhs(tn, y)
                va, vb, vc, vo, vkv, vad, ih, pm1, itvs, vcc = self._aux
                self.e["m1"] += pm1 * (tn - t)
                self.e["tvs"] += abs(itvs) * abs(va) * (tn - t)
                if tn > 0:
                    self.pk["m1"] = max(self.pk["m1"], pm1)
                self.pk["tvs"] = max(self.pk["tvs"], abs(itvs * va))
                self.pk["iin"] = max(self.pk["iin"], abs(ih))
                self.step_discrete(tn, y, tn - t)
                r = self.rec
                for k, val in (("t", tn), ("va", va), ("vb", vb), ("vc", vc), ("vout", vo), ("vkv", vkv),
                               ("vad", vad), ("iin", ih), ("pm1", pm1), ("itvs", itvs), ("tmr", self.tmr)):
                    r[k].append(val)
                t = tn
        return self


def summarize(s):
    r = {k: np.array(v) for k, v in s.rec.items()}
    out = {"va_max": float(r["va"].max()), "va_min": float(r["va"].min()), "vb_max": float(r["vb"].max()),
           "vc_min": float(r["vc"].min()), "vout_min": float(r["vout"].min()), "vout_max": float(r["vout"].max()),
           "vkv_min": float(r["vkv"].min()), "vad_min": float(r["vad"].min()), "iin_peak": s.pk["iin"],
           "m1_peak_W": s.pk["m1"], "m1_energy_J": s.e["m1"], "tvs_peak_W": s.pk["tvs"],
           "tvs_energy_J": s.e["tvs"], "tmr_max_V": float(r["tmr"].max()), **s.flags}
    # ratings
    stress = []
    if out["va_max"] > P.IPB048N15N5["vds"]:
        stress.append("M1 VDS")
    if out["va_min"] < P.LTC4364["v_rev"] + 0.7:
        stress.append("LTC4364 reverse")
    if out["vb_max"] > P.LM5177["vin_max"]:
        stress.append("LM5177 VIN")
    if out["tvs_peak_W"] > P.SMCJ24A["p_1ms"]:
        stress.append("TVS peak power")
    t, pm = r["t"], r["pm1"]
    lin = 0.0
    if len(t) > 2:
        grid = np.arange(t[0], t[-1], 1e-3)
        if len(grid) > 2:
            cum = np.concatenate([[0], np.cumsum(pm[1:] * np.diff(t))])
            e = np.interp(grid, t, cum)
            lin = float(np.max(np.diff(e)) / 1e-3)
    out["m1_1ms_avg_peak_W"] = lin
    if lin > P.IPB048N15N5["soa_dc_40v"] * 40 * 0.6:      # DC SOA line at 40 V, derated to TC 85 C [E]
        stress.append("M1 SOA")
    out["damage"] = stress
    out["kv260"] = "FAIL" if stress else ("C (reset)" if out["kv_reset"] else "A (runs)")
    out["adapter"] = "FAIL" if stress else ("C (reset)" if out["ad_reset"] else "A (runs)")
    return out, r


def cases():
    c = {}
    for kind in ("pulse1_200ms", "pulse2a", "pulse3a", "pulse3b", "load_dump_a", "load_dump_b", "jump_start",
                 "reverse", "crank_I", "crank_II", "crank_III", "crank_IV"):
        f, ri, sched, disc, _, ua = RT.pulse_wave(kind)
        dwin = None
        rw = None
        if kind == "pulse1_200ms":
            dwin = (5 * 2e-3, 0.200)
            rw = (0.0, 5 * 2e-3)
        elif kind == "pulse2a":
            rw = (0.0, 5 * 50e-6)
        elif kind in ("pulse3a", "pulse3b"):
            rw = (0.0, 5 * 0.1e-6)
        elif kind == "load_dump_a":
            # the alternator's Ri while the dump is above 20 V (the stress); below that its regulator has the bus
            # again. A 55 W load cannot be fed through 1 ohm from 13.5 V at all (13.5^2 / 4 = 45 W at best)
            rw = (0.0, 0.4 / math.log(10.0) * math.log((87.0 - 13.5) / (20.0 - 13.5)))
        elif kind == "load_dump_b":
            rw = (0.0, 0.400)
        segs = [(-0.030, 0.0, 20e-6)] + sched            # settle at the steady state first
        c[kind] = (f, ri, dwin, segs, ua, rw)
    return c


def main():
    res = {"model": {"L_H": L_H, "C_A": C_A, "C_B": C_BC + C_E, "L2": L2, "C_C": C_C, "C_OUT": C_OUT, "C_KV": C_KV,
                     "C_AD": C_AD, "R_M1+M2": R_M, "I_LIM_IN": I_LIM_IN, "KP": KP, "KI": KI}, "cases": {}}
    traces = {}
    loads = {"typ": (P.P_KV260["typ"], P.P_ADAPTER["typ"]), "max": (P.I_KV_LIMIT * P.VOUT * 0.98, P.P_ADAPTER["max"])}
    for name, (f, ri, dwin, segs, ua, rw) in cases().items():
        for lname, (pk, pa) in loads.items():
            if name in ("crank_II", "crank_IV") and lname == "typ":
                pass
            s = Sim(f, ri, dwin, p_kv=pk, p_ad=pa, v0=ua, ri_window=rw).run(segs)
            out, r = summarize(s)
            res["cases"][f"{name} {lname}"] = out
            traces[f"{name} {lname}"] = r
            print(f"{name:14s} {lname}: KV260 {out['kv260']:10s} adapter {out['adapter']:10s} "
                  f"A {out['va_min']:7.1f}..{out['va_max']:6.1f} V  B max {out['vb_max']:5.1f} V  "
                  f"bus {out['vout_min']:5.2f}..{out['vout_max']:5.2f} V  M1 {out['m1_peak_W']:5.1f} W "
                  f"{out['m1_energy_J']:5.2f} J  TVS {out['tvs_peak_W']:6.0f} W {out['tvs_energy_J']:5.2f} J "
                  f"tmr {out['tmr_max_V']:.2f} V {out['damage']}")
    # faults: a short on the KV260 output while running from 13.5 V
    f13 = lambda t: 13.5
    for lname, (pk, pa) in loads.items():
        s = Sim(f13, 0.01, None, p_kv=pk, p_ad=pa, short_kv_at=0.002).run([(0, 0.002, 50e-6), (0.002, 0.004, 2e-6),
                                                                           (0.004, 0.05, 50e-6)])
        out, r = summarize(s)
        res["cases"][f"KV260 output short {lname}"] = out
        traces[f"KV260 output short {lname}"] = r
        print(f"KV260 short {lname}: adapter {out['adapter']}, bus {out['vout_min']:.2f}..{out['vout_max']:.2f} V")
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w") as fh:
        json.dump(res, fh, indent=1, default=float)

    show = ["pulse1_200ms max", "pulse2a max", "load_dump_a max", "load_dump_b max", "jump_start max",
            "reverse max", "crank_II max", "crank_III typ", "crank_IV max", "KV260 output short max"]
    fig, axs = plt.subplots(2, 5, figsize=(20, 7.5))
    for ax, k in zip(axs.flat, show):
        r = traces[k]
        t = r["t"]
        unit, sc = ("ms", 1e3) if t[-1] < 2 else ("s", 1)
        ax.plot(t * sc, np.clip(r["va"], -60, 140), color="#999999", lw=1, label="input (A)")
        ax.plot(t * sc, r["vb"], color="#d6604d", lw=1.2, label="after U1 (B)")
        ax.plot(t * sc, r["vout"], color="#2166ac", lw=1.6, label="+12V bus")
        ax.plot(t * sc, r["vkv"], color="#1b7837", lw=1.2, ls="--", label="KV260 input")
        ax.axhline(7.48, color="k", lw=0.6, ls=":")
        ax.set_title(f"{k}: KV260 {res['cases'][k]['kv260']}", fontsize=9)
        ax.set_xlabel(unit)
        ax.set_ylim(-45, 70)
        ax.grid(alpha=0.3)
    axs.flat[0].legend(fontsize=7, loc="lower right")
    fig.suptitle("PSU board: vehicle events and faults, worst load (dotted: 7.48 V, the eFuses' UVLO)")
    fig.tight_layout()
    fig.savefig(OUT_PNG, dpi=130)
    print("wrote", OUT_JSON)


if __name__ == "__main__":
    main()
