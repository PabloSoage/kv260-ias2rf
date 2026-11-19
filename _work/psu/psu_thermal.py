#!/usr/bin/env python3
"""
PSU board: thermal model of the board as placed (psu_pcb.PLACE), steady state and the 10 s cranking transient.

The board is a 2-D plate (finite differences, 0.5 mm cells) with the in-plane conductance of its copper (2 oz
outer, 0.5 oz inner [C], 70 % coverage [E]) and its FR4, losing heat by convection and radiation from both faces
(h = 10 W/m2K natural convection inside the closed case + 5 W/m2K radiation [E]) to the case air at 70 C (the hot
car, as the enclosure model takes it). Every component's loss (psu_design.operating_point, the eFuses' I^2 R)
enters over its pads' area; its junction (or body) temperature is the board under it plus its loss times its
junction-to-board resistance from its data sheet.

Cases: 13.5 V (the car running) and 24 V (jump start) at the worst load, continuous; 6.0 V at the worst load
continuous (a weak battery: the most current); the Level IV cranking (6.5 V for 10 s) as a transient from the
13.5 V steady state.

Writes docs/sim/psu_thermal.json and docs/sim/psu_thermal.png.

Usage:  py _work/psu/psu_thermal.py
"""
import json
import math
import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.sparse import diags, identity
from scipy.sparse.linalg import spsolve

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import psu_params as P                                    # noqa: E402
import psu_design as D                                    # noqa: E402
import psu_pcb as PCB                                     # noqa: E402

ROOT = os.path.dirname(os.path.dirname(HERE))
OUT_JSON = os.path.join(ROOT, "docs", "sim", "psu_thermal.json")
OUT_PNG = os.path.join(ROOT, "docs", "sim", "psu_thermal.png")

DX = 0.5e-3
NX, NY = int(PCB.W / 0.5), int(PCB.H / 0.5)
T_AIR = 70.0
H_FACE = 10.0 + 5.0                    # W/m2K each face [E]
CU_T = 2 * 70e-6 + 2 * 17.5e-6         # copper thickness through the board
K_SHEET = 385.0 * CU_T * 0.70 + 0.3 * 1.6e-3      # W/K, in-plane sheet conductance
C_AREA = 1.6e-3 * 1.9e6 + CU_T * 0.7 * 3.45e6     # J/(m2 K): FR4 1.9 MJ/m3K + copper 3.45 MJ/m3K

# component -> (footprint size x, y in mm for the heat spread, junction-to-board K/W [V], limit C, what limits it)
PARTS = {
    "Q1": ((9.4, 10.8), 0.5 + 1.0, 150, "IPB048N15N5 RthJC 0.5 + solder/tab 1.0 [E]"),
    "Q2": ((4.5, 4.7), 2.0 + 1.0, 150, "BSC040N10NS5 RthJC [V] + 1.0 [E]"),
    "Q3": ((4.5, 4.7), 1.5 + 1.0, 150, "BSC0805LS RthJC 1.5 [V] + 1.0 [E]"),
    "Q4": ((4.5, 4.7), 1.5 + 1.0, 150, "BSC0805LS"),
    "Q5": ((4.5, 4.7), 2.0 + 1.0, 150, "BSC026N04LS RthJC 2 [V] + 1.0 [E]"),
    "Q6": ((4.5, 4.7), 2.0 + 1.0, 150, "BSC026N04LS"),
    "U2": ((2.9, 4.7), 15.2, 125, "LM5177 RthJB 15.2 [V]"),
    "U3": ((2.7, 2.7), 10.2, 125, "TPS26631 RGE RthJB 10.2 [V]"),
    "U4": ((2.7, 2.7), 10.2, 125, "TPS26631 RGE RthJB 10.2 [V]"),
    "L1": ((15.0, 12.5), 2.0, 155, "MDA1870 (with self-heating) [E] winding to pads"),
    "L2": ((10.0, 5.0), 3.0, 155, "MDA1365 [E]"),
    "L3": ((10.0, 5.0), 3.0, 155, "MDA1365 [E]"),
    "R1": ((6.3, 3.2), 10.0, 155, "2512 sense resistor [E]"),
    "R2": ((6.3, 3.2), 10.0, 155, "2512 sense resistor [E]"),
    "C17": ((10.0, 10.0), 5.0, 105, "EEE-FK1J101P, 105 C rated (life halves each 10 C above)"),
    "C18": ((10.0, 10.0), 5.0, 105, "EEE-FK1J101P"),
}


def losses(vin, pout):
    op = D.operating_point(vin, pout, ta=T_AIR)
    l = op["loss_W"]
    r1 = P.IPB048N15N5["rds_10"] * P.IPB048N15N5["tc"]
    r2 = P.BSC040N10NS5["rds_10"] * P.BSC040N10NS5["tc"]
    m = l["M1 + M2 (U1)"]
    ef = D.efuses()
    out = {"Q1": m * r1 / (r1 + r2), "Q2": m * r2 / (r1 + r2), "Q3": l["Q2"], "Q4": l["Q3"], "Q5": l["Q4"],
           "Q6": l["Q5"], "U2": l["U2 drivers + LDO"], "L1": l["L1 copper"] + l["L1 core"],
           "L2": l["L2 filter"] * 1.5 / 2.38, "L3": l["L2 filter"] * 0.88 / 2.38, "R1": l["R_CS"], "R2": l["R_ISNS"],
           "C17": l["C_IN ESR"] / 2, "C18": l["C_IN ESR"] / 2,
           "U3": ef["loss_W"]["U3 at 1.12 A"], "U4": ef["loss_W"]["U4 at 3.19 A"]}
    return out, op


def grid_sources(loss):
    q = np.zeros((NX, NY))
    for ref, p in loss.items():
        x, y = PCB.PLACE[ref][0], PCB.PLACE[ref][1]
        (sx, sy), _, _, _ = PARTS[ref]
        if PCB.PLACE[ref][2] in (90, 270):
            sx, sy = sy, sx
        i0, i1 = int((x - sx / 2 - PCB.X0) / 0.5), int((x + sx / 2 - PCB.X0) / 0.5)
        j0, j1 = int((y - sy / 2 - PCB.Y0) / 0.5), int((y + sy / 2 - PCB.Y0) / 0.5)
        i0, j0 = max(i0, 0), max(j0, 0)
        i1, j1 = max(min(i1, NX - 1), i0), max(min(j1, NY - 1), j0)
        n = (i1 - i0 + 1) * (j1 - j0 + 1)
        q[i0:i1 + 1, j0:j1 + 1] += p / n
    return q


def operator():
    """conduction Laplacian (W/K per cell) and the convective loss per cell."""
    n = NX * NY
    g = K_SHEET                           # W/K between neighbouring square cells
    main = np.zeros(n)
    off_x = np.zeros(n - 1)
    off_y = np.zeros(n - NY)
    for i in range(NX):
        for j in range(NY):
            k = i * NY + j
            if j < NY - 1:
                off_x[k] = -g
                main[k] += g
                main[k + 1] += g
            if i < NX - 1:
                off_y[k] = -g
                main[k] += g
                main[k + NY] += g
    hconv = 2 * H_FACE * DX * DX
    A = diags([main + hconv, off_x, off_x, off_y, off_y], [0, 1, -1, NY, -NY], format="csr")
    return A, hconv


def solve_steady(q, A, hconv):
    T = spsolve(A, q.ravel() + hconv * T_AIR)
    return T.reshape(NX, NY)


def transient(q, T0, A, hconv, t_end=10.0, dt=0.1):
    cap = C_AREA * DX * DX
    M = identity(NX * NY, format="csr") * (cap / dt)
    K = M + A
    T = T0.ravel().copy()
    peak = T0.copy()
    for _ in range(int(t_end / dt)):
        T = spsolve(K, M @ T + q.ravel() + hconv * T_AIR)
        peak = np.maximum(peak, T.reshape(NX, NY))
    return T.reshape(NX, NY)


def junctions(T, loss):
    out = {}
    for ref, p in loss.items():
        x, y = PCB.PLACE[ref][0], PCB.PLACE[ref][1]
        i, j = int((x - PCB.X0) / 0.5), int((y - PCB.Y0) / 0.5)
        tb = float(T[min(i, NX - 1), min(j, NY - 1)])
        _, rjb, lim, why = PARTS[ref]
        out[ref] = {"loss_W": p, "board_C": tb, "junction_C": tb + p * rjb, "limit_C": lim,
                    "margin_C": lim - (tb + p * rjb), "basis": why}
    return out


def main():
    A, hconv = operator()
    p_max = P.VOUT * (P.I_ADAPTER_MAX + P.I_KV_LIMIT)
    res = {"model": {"cell_mm": 0.5, "T_air_C": T_AIR, "h_face_W_m2K": H_FACE, "K_sheet_W_K": K_SHEET},
           "cases": {}}
    maps = {}
    for name, vin in (("13.5 V, worst load", 13.5), ("24 V jump start, worst load", 24.0),
                      ("6.0 V weak battery, worst load", 6.0)):
        loss, op = losses(vin, p_max)
        T = solve_steady(grid_sources(loss), A, hconv)
        res["cases"][name] = {"total_loss_W": sum(loss.values()), "board_max_C": float(T.max()),
                              "parts": junctions(T, loss)}
        maps[name] = T
    # Level IV cranking: 6.5 V for 10 s from the 13.5 V steady state
    l13, _ = losses(13.5, p_max)
    T0 = solve_steady(grid_sources(l13), A, hconv)
    l65, _ = losses(6.5, p_max)
    Tc = transient(grid_sources(l65), T0, A, hconv)
    res["cases"]["cranking Level IV, 10 s at 6.5 V"] = {"total_loss_W": sum(l65.values()),
                                                       "board_max_C": float(Tc.max()), "parts": junctions(Tc, l65)}
    maps["cranking Level IV, 10 s at 6.5 V"] = Tc
    with open(OUT_JSON, "w") as fh:
        json.dump(res, fh, indent=1)

    fig, axs = plt.subplots(2, 2, figsize=(14, 9.5))
    vmax = max(m.max() for m in maps.values())
    for ax, (name, T) in zip(axs.flat, maps.items()):
        im = ax.imshow(T.T, origin="upper", extent=(PCB.X0, PCB.X0 + PCB.W, PCB.Y0 + PCB.H, PCB.Y0),
                       cmap="inferno", vmin=T_AIR, vmax=vmax)
        for ref in PARTS:
            x, y = PCB.PLACE[ref][0], PCB.PLACE[ref][1]
            ax.text(x, y, ref, color="#9ecae1", fontsize=7, ha="center", va="center")
        c = res["cases"][name]
        hot = max(c["parts"].items(), key=lambda kv: kv[1]["junction_C"])
        ax.set_title(f"{name}: {c['total_loss_W']:.1f} W, hottest {hot[0]} {hot[1]['junction_C']:.0f} C", fontsize=9)
        ax.set_xlabel("mm")
        fig.colorbar(im, ax=ax, label="board C")
    fig.suptitle(f"PSU board: temperature at {T_AIR:.0f} C case air (psu_thermal.py)")
    fig.tight_layout()
    fig.savefig(OUT_PNG, dpi=130)
    for name, c in res["cases"].items():
        print(name, f"loss {c['total_loss_W']:.2f} W board max {c['board_max_C']:.1f} C")
        for ref, v in sorted(c["parts"].items(), key=lambda kv: -kv[1]["junction_C"])[:6]:
            print(f"   {ref:4s} {v['loss_W']:5.2f} W  board {v['board_C']:5.1f}  junction {v['junction_C']:5.1f} "
                  f"(limit {v['limit_C']}, margin {v['margin_C']:5.1f})")


if __name__ == "__main__":
    main()
