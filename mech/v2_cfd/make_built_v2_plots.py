#!/usr/bin/env python3
"""
Generate 2D engineering comparison plots for the built Enclosure v2 CFD suite
from `mech/v2_cfd/results_built_v2.json` and `mech/v2_cfd/slices/*.npz`
into `docs/sim/`.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.tri as mtri
import numpy as np


ROOT = Path(__file__).resolve().parents[2]
CFD_DIR = Path(__file__).resolve().parent
SLICES_DIR = CFD_DIR / "slices"
OUT_DIR = ROOT / "docs" / "sim"
RESULTS_PATH = CFD_DIR / "results_built_v2.json"

# Component Tj_max limits (C) and coordinates for annotation
COMP_META = [
    ("U401_ADCLK948",   "U401 ADCLK948",   -34.9,  -0.2, 150.0),
    ("Y401_Si549",      "Y401 Si549*",     -35.0,   8.8, 105.0),
    ("U501_AD9484",     "U501 AD9484",     -51.8,  10.6, 125.0),
    ("U502_AD8352",     "U502 AD8352",     -48.9,  -1.2, 125.0),
    ("U503_AD8352",     "U503 AD8352",     -57.2,  -2.4, 125.0),
    ("U601_AD9253",     "U601 AD9253",     -70.25, 10.35, 125.0),
    ("U1101_XC7A50T",   "U1101 XC7A50T*",  -42.75, 40.0, 100.0),
    ("U1001_LMR33630",  "U1001 LMR33630",  -30.25, 94.0, 150.0),
    ("U1002_TPS562201", "U1002 TPS562201", -54.75, 104.5, 125.0),
    ("U1003_TPS562201", "U1003 TPS562201", -54.75, 95.5, 125.0),
    ("U1004_TPS562201", "U1004 TPS562201", -54.75, 86.5, 125.0),
    ("U1005_TPS7A8300", "U1005 TPS7A8300", -43.25, 81.0, 125.0),
    ("U1006_TPS7A8300", "U1006 TPS7A8300", -35.25, 81.0, 125.0),
    ("U1007_TPS7A8300", "U1007 TPS7A8300", -27.25, 81.0, 125.0),
    ("U1201_RTL8211FSI","U1201 RTL8211FSI",-18.2,  -1.0, 125.0),
    ("AD9708_AD9767",   "AD9708 / AD9767", -45.5,  71.0, 125.0),
]

FAN_50_PQ = [
    (0.0,     22.0),
    (2.82,    15.2),
    (5.66,     8.0),
    (8.48,     0.0),
]


def plot_margins_70c(by_name: dict[str, dict]) -> None:
    keys = [c[0] for c in COMP_META] + ["K26_SOM"]
    labels = [c[1] for c in COMP_META] + ["K26 SOM*"]

    def extract_tj(case_key: str) -> list[float]:
        row = by_name[case_key]
        vals = [row["components"][k]["T_j_C"] for k, *_ in COMP_META]
        vals.append(row["K26_Tj_C"])
        return vals

    def extract_margin(case_key: str) -> list[float]:
        row = by_name[case_key]
        vals = [row["components"][k]["margin_C"] for k, *_ in COMP_META]
        vals.append(row["K26_margin_C"])
        return vals

    tj_nohs = extract_tj("v2_built_nohs_clean_70C")
    tj_built = extract_tj("v2_built_hs_clean_70C")
    tj_fine = extract_tj("v2_built_hs_clean_fine_70C")
    tj_prop = extract_tj("v2_built_proposed_70C")

    m_nohs = extract_margin("v2_built_nohs_clean_70C")
    m_built = extract_margin("v2_built_hs_clean_70C")
    m_fine = extract_margin("v2_built_hs_clean_fine_70C")
    m_prop = extract_margin("v2_built_proposed_70C")

    y = np.arange(len(keys))
    h = 0.21

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15.5, 8.2), dpi=170, sharey=True)

    ax1.barh(y - 1.5 * h, tj_nohs, height=h, color="#d62728", label="Built v2, NO heatsinks")
    ax1.barh(y - 0.5 * h, tj_built, height=h, color="#ff7f0e", label="Built v2 + 3 heatsinks (med)")
    ax1.barh(y + 0.5 * h, tj_fine, height=h, color="#1f77b4", label="Built v2 + 3 heatsinks (fine 432k)")
    ax1.barh(y + 1.5 * h, tj_prop, height=h, color="#2ca02c", label="Proposed: open grille + gap + exhaust")

    limits = [c[4] for c in COMP_META] + [100.0]
    for yi, lim in zip(y, limits):
        ax1.plot([lim, lim], [yi - 0.43, yi + 0.43], color="#111111", linewidth=2.0)
    ax1.plot([], [], color="#111111", linewidth=2.0, label="IC Tj_max limit")

    for yi, vn, vb, vp in zip(y, tj_nohs, tj_built, tj_prop):
        if keys[yi] in ("U401_ADCLK948", "Y401_Si549", "U501_AD9484", "U1001_LMR33630", "U1201_RTL8211FSI", "U1101_XC7A50T", "K26_SOM"):
            ax1.text(max(vn, vb, vp) + 0.7, yi, f"{vn:.1f} / {vb:.1f} / {vp:.1f}", va="center", fontsize=7.6, color="#222222")

    ax1.set_yticks(y)
    ax1.set_yticklabels(labels, fontsize=9)
    ax1.invert_yaxis()
    ax1.set_xlim(80, 158)
    ax1.set_xlabel("Junction Temperature Tj (C) at Ta = 70 C")
    ax1.set_title("Peak Junction Temperature vs. Silicon Limit (* tight <=105 C limit)")
    ax1.grid(axis="x", linestyle="--", alpha=0.35)
    ax1.legend(loc="lower right", fontsize=8.2, framealpha=0.94)

    ax2.axvline(0.0, color="#111111", linewidth=1.6, linestyle="-")
    ax2.barh(y - 1.5 * h, m_nohs, height=h, color="#d62728", label="NO heatsinks")
    ax2.barh(y - 0.5 * h, m_built, height=h, color="#ff7f0e", label="Built + 3 heatsinks (med)")
    ax2.barh(y + 0.5 * h, m_fine, height=h, color="#1f77b4", label="Built + 3 heatsinks (fine)")
    ax2.barh(y + 1.5 * h, m_prop, height=h, color="#2ca02c", label="Proposed fix")
    for yi, mn, mb, mp in zip(y, m_nohs, m_built, m_prop):
        if keys[yi] in ("Y401_Si549", "U1101_XC7A50T", "K26_SOM", "U501_AD9484", "U401_ADCLK948"):
            ax2.text(max(mn, mb, mp) + 0.8, yi, f"{mn:+.1f} / {mb:+.1f} / {mp:+.1f}", va="center", fontsize=7.6, color="#222222")

    ax2.set_xlim(-13, 54)
    ax2.set_xlabel("Thermal Margin (Tj_max - Tj, C) at Ta = 70 C")
    ax2.set_title("Heatsink Benefit & Design Optimization Margin Gain")
    ax2.grid(axis="x", linestyle="--", alpha=0.35)

    fig.suptitle("Built Enclosure v2 Full-Board Thermal Verification at Ta = 70 C (All 16 Adapter ICs + K26 SOM)", fontsize=13)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(OUT_DIR / "v2_built_margins_70c.png")
    plt.close(fig)


def plot_fan_and_ambient(by_name: dict[str, dict]) -> None:
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13.8, 5.6), dpi=170)

    q_curve = np.array([p[0] for p in FAN_50_PQ])
    p_curve = np.array([p[1] for p in FAN_50_PQ])
    ax1.plot(q_curve, p_curve, "k-", linewidth=2.2, label="Sunon MF50100V1-1000U P-Q Curve (5 V)")

    pts = [
        ("v2_built_hs_clogged_70C",   "Built v2 (2x clogged filter)", "#d62728", "s", (-1.85, -3.2)),
        ("v2_built_hs_clean_70C",     "Built v2 (clean filter)",      "#ff7f0e", "o", (-1.95, -0.5)),
        ("v2_built_hs_clean_fine_70C","Built v2 (clean, fine mesh)",  "#1f77b4", "^", (0.55,  2.6)),
        ("v2_built_widegrille_hs_70C","Fix #1: Open 48 mm grille",    "#9467bd", "D", (0.95,  0.6)),
        ("v2_built_proposed_70C",     "Proposed: Grille + 17 slots",  "#2ca02c", "*", (0.45,  1.2)),
    ]
    for k, lbl, col, mk, offs in pts:
        r = by_name[k]
        q = r["fan50_flow_cfm"]
        dp = r["fan50_curve_dp_Pa"]
        ax1.scatter([q], [dp], color=col, marker=mk, s=95 if mk != "*" else 170, zorder=5, label=f"{lbl}: {q:.2f} CFM @ {dp:.1f} Pa")
        ax1.annotate(
            f"{q:.2f} CFM @ {dp:.1f} Pa",
            (q, dp),
            xytext=(q + offs[0], dp + offs[1]),
            fontsize=8.0,
            color=col,
            fontweight="bold",
            arrowprops=dict(arrowstyle="-", color=col, lw=1.0, shrinkA=2, shrinkB=4),
        )

    ax1.set_xlim(0.0, 9.0)
    ax1.set_ylim(0.0, 24.5)
    ax1.set_xlabel("Adapter 50 mm Fan Airflow (CFM)")
    ax1.set_ylabel("Static Pressure Rise (Pa)")
    ax1.set_title("50x50x10 mm Intake Fan Operating Point (Ta = 70 C)")
    ax1.grid(True, linestyle="--", alpha=0.35)
    ax1.legend(loc="lower left", fontsize=8.0, framealpha=0.93)

    amb = [25.0, 45.0, 70.0]
    clean_keys = ["v2_built_hs_clean_25C", "v2_built_hs_clean_45C", "v2_built_hs_clean_70C"]
    clog_keys = ["v2_built_hs_clogged_45C", "v2_built_hs_clogged_70C"]

    series = [
        ("Y401_Si549", "Y401 Si549 (limit 105 C)", "#d62728", "-o"),
        ("U401_ADCLK948", "U401 ADCLK948 (limit 150 C)", "#ff7f0e", "-s"),
        ("K26_SOM", "K26 SOM (est. 100 C)", "#2ca02c", "-^"),
        ("U1001_LMR33630", "U1001 LMR33630 (limit 150 C)", "#8c564b", "-D"),
        ("U1201_RTL8211FSI", "U1201 RTL8211FSI (10 vias)", "#1f77b4", "-P"),
        ("U1101_XC7A50T", "U1101 XC7A50T (limit 100 C)", "#9467bd", "-v"),
    ]
    for key, lbl, col, fmt in series:
        vals = [by_name[k]["K26_Tj_C"] if key == "K26_SOM" else by_name[k]["components"][key]["T_j_C"] for k in clean_keys]
        ax2.plot(amb, vals, fmt, color=col, linewidth=2.0, markersize=6, label=lbl)
        if key == "Y401_Si549":
            cvals = [by_name[k]["components"][key]["T_j_C"] for k in clog_keys]
            ax2.plot([45.0, 70.0], cvals, "--x", color="#8c1515", linewidth=1.4, markersize=6, label="Y401 Si549 (2x clogged)")

    ax2.axhline(105.0, color="#d62728", linestyle=":", linewidth=1.3, label="Si549 Tj_max (105 C)")
    ax2.axhline(100.0, color="#2ca02c", linestyle="--", linewidth=1.2, label="XC7A50T / K26 Tj_max (100 C)")
    ax2.axvspan(20, 48, color="#2ca02c", alpha=0.07)
    ax2.text(33, 47, "25-45 C Continuous:\nAll ICs >= +21 C margin", ha="center", fontsize=8.5, color="#1b5e20", fontweight="bold")

    ax2.set_xlim(22, 73)
    ax2.set_ylim(43, 122)
    ax2.set_xlabel("Ambient Temperature Ta (C)")
    ax2.set_ylabel("Junction Temperature Tj (C)")
    ax2.set_title("Built Enclosure v2 Ambient Sweep (Clean vs. 2x Clogged Filter)")
    ax2.grid(True, linestyle="--", alpha=0.35)
    ax2.legend(loc="upper left", fontsize=7.6, framealpha=0.93)

    fig.tight_layout()
    fig.savefig(OUT_DIR / "v2_built_fan_pq_and_ambient.png")
    plt.close(fig)


def _tricontour_masked(ax, x, y, z, vmin, vmax, levels, cmap="turbo", max_edge=10.0):
    tri = mtri.Triangulation(x, y)
    t = tri.triangles
    dx = np.ptp(x[t], axis=1)
    dy = np.ptp(y[t], axis=1)
    tri.set_mask((dx > max_edge) | (dy > max_edge))
    return ax.tricontourf(tri, z, levels=levels, cmap=cmap, vmin=vmin, vmax=vmax, extend="both")


def plot_flow_and_pcb(by_name: dict[str, dict]) -> None:
    fig = plt.figure(figsize=(15.0, 8.6), dpi=170)
    gs = fig.add_gridspec(2, 2, hspace=0.32, wspace=0.18, right=0.91)

    cases = [
        ("v2_built_hs_clean_70C", "Built v2 w/ Touching 9x9 Sinks (2.57 CFM @ 15.8 Pa)"),
        ("v2_built_proposed_70C", "Proposed: Open Grille + Gap + 17 Slots (3.62 CFM @ 13.2 Pa)"),
    ]
    levels_air = np.linspace(70.0, 108.0, 25)
    levels_pcb = np.linspace(80.0, 110.0, 25)

    cf_air = None
    cf_pcb = None
    for col_idx, (cname, title) in enumerate(cases):
        npz = np.load(SLICES_DIR / f"{cname}.npz")
        row = by_name[cname]

        # Top row: X-Z slice through Y = +14 mm fan axis
        ax_xz = fig.add_subplot(gs[0, col_idx])
        x, zz, T, U = npz["xz_x"], npz["xz_z"], npz["xz_T"], npz["xz_U"]
        cf_air = _tricontour_masked(ax_xz, x, zz, T, 70.0, 108.0, levels_air, cmap="turbo", max_edge=8.0)

        bx = np.linspace(x.min() + 4.0, x.max() - 4.0, 20)
        bz = np.linspace(zz.min() + 2.0, zz.max() - 2.0, 9)
        qx, qz, qu, qw = [], [], [], []
        for cx in bx:
            for cz in bz:
                d2 = (x - cx) ** 2 + (zz - cz) ** 2
                idx = int(np.argmin(d2))
                if d2[idx] < 20.0:
                    qx.append(x[idx])
                    qz.append(zz[idx])
                    qu.append(U[idx, 0])
                    qw.append(U[idx, 2])
        ax_xz.quiver(qx, qz, qu, qw, color="white", alpha=0.85, scale=44, width=0.0028, headwidth=3.5)
        ax_xz.axvline(-40.0, color="white", linestyle="--", linewidth=0.9, alpha=0.6)
        ax_xz.text(-40.0, 29.0, "Fan (-40, 14)", color="white", fontsize=7.5, ha="center", fontweight="bold")
        ax_xz.set_title(
            f"{title}\nX-Z Slice at Y = +14 mm | pcav={row['p_cav_mean_Pa']} Pa | K26 Tj={row['K26_Tj_C']} C",
            fontsize=9.2,
        )
        ax_xz.set_xlabel("X (mm)")
        ax_xz.set_ylabel("Z (mm)")

        # Bottom row: Adapter PCB top surface temperature T_ad(X, Y)
        ax_pcb = fig.add_subplot(gs[1, col_idx])
        ad_x, ad_y, ad_T = npz["ad_x"], npz["ad_y"], npz["ad_T"]
        cf_pcb = _tricontour_masked(ax_pcb, ad_x, ad_y, ad_T, 80.0, 110.0, levels_pcb, cmap="inferno", max_edge=6.0)
        for ic_id, label, cx, cy, _ in [c for c in COMP_META if c[0] in ("U401_ADCLK948", "Y401_Si549", "U501_AD9484", "U1101_XC7A50T", "U1001_LMR33630", "U1201_RTL8211FSI")]:
            tj = row["components"][ic_id]["T_j_C"]
            short = ic_id.split("_")[0]
            dy_off = -5.0 if short == "U401" else (4.2 if short in ("Y401", "U1001", "U1201") else 3.6)
            ax_pcb.plot(cx, cy, "wo", markersize=4, markeredgecolor="black", markeredgewidth=0.7)
            ax_pcb.text(cx, cy + dy_off, f"{short}\n{tj:.1f}C", color="white", fontsize=7.2, ha="center", va="center",
                        bbox=dict(boxstyle="round,pad=0.14", fc="black", alpha=0.58, lw=0))

        # Overlay fan bore footprint (-40, 14, R=24 mm)
        th = np.linspace(0, 2 * np.pi, 100)
        ax_pcb.plot(-40.0 + 24.0 * np.cos(th), 14.0 + 24.0 * np.sin(th), "c--", linewidth=1.2, label="50 mm fan bore")
        ax_pcb.set_title(
            f"Adapter PCB Surface (Y401={row['components']['Y401_Si549']['T_j_C']} C, U501={row['components']['U501_AD9484']['T_j_C']} C)",
            fontsize=9.2,
        )
        ax_pcb.set_xlabel("X (mm)")
        ax_pcb.set_ylabel("Y (mm)")
        ax_pcb.set_xlim(-108, -9)
        ax_pcb.set_ylim(-14, 111)

    cax1 = fig.add_axes([0.925, 0.54, 0.016, 0.34])
    fig.colorbar(cf_air, cax=cax1).set_label("Cavity Air T (C)")
    cax2 = fig.add_axes([0.925, 0.11, 0.016, 0.34])
    fig.colorbar(cf_pcb, cax=cax2).set_label("Adapter PCB T (C)")

    fig.suptitle("Built Enclosure v2 vs. Proposed Cooling Upgrades (Ta = 70 C)", fontsize=13)
    fig.savefig(OUT_DIR / "v2_built_flow_and_pcb.png", bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = json.loads(RESULTS_PATH.read_text())
    by_name = {r["name"]: r for r in rows}
    plot_margins_70c(by_name)
    plot_fan_and_ambient(by_name)
    plot_flow_and_pcb(by_name)
    print("Generated built v2 plots in", OUT_DIR)


if __name__ == "__main__":
    main()
