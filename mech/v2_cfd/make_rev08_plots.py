#!/usr/bin/env python3
"""Rev08 enclosure CFD figure (docs/ENCLOSURE_V2_THERMAL.md section 8): the adapter PCB at 70 C ambient with the
Rev08 front end and camera, and its change against the adopted Rev06/07 run (same enclosure, same mesh).

    python mech/v2_cfd/make_rev08_plots.py        # after run_built_v2_cfd.py --only rev08_clean_fine_70C ...
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.interpolate import griddata

HERE = Path(__file__).resolve().parent
SL = HERE / "slices"
OUT = HERE.parent.parent / "docs" / "sim" / "rev08_thermal_70c.png"

PARTS = {  # label: (x, y) in the enclosure frame, mm
    "RFFC5072": (-7.35, 61.6), "LNA": (-15.35, 87.36), "IF amp": (-13.76, 56.65), "LP5907": (-11.8, 100.14),
    "LEDs, I/O exp.": (-16.35, 93.8), "camera": (18.0, 62.0), "LMR33630": (-30.25, 94.0), "ADCLK948": (-34.9, -0.2),
    "XC7A50T": (-42.75, 40.0),
}
INK, MUTED = "#1f2328", "#59636e"


def load(name):
    d = np.load(SL / f"{name}.npz")
    return d["ad_x"], d["ad_y"], d["ad_T"]


def main():
    xr, yr, tr = load("rev08_clean_fine_70C")
    xa, ya, ta = load("v2_adopted_clean_fine_70C")
    gx, gy = np.meshgrid(np.arange(-108, 25.5, 0.5), np.arange(-10, 109.5, 0.5))
    tr_g = griddata((xr, yr), tr, (gx, gy), method="nearest")
    ta_g = griddata((xa, ya), ta, (gx, gy), method="nearest")
    # mask the grid to the cells each run actually has (nearest-cell distance under one cell)
    def mask(x, y):
        from scipy.spatial import cKDTree
        d, _ = cKDTree(np.c_[x, y]).query(np.c_[gx.ravel(), gy.ravel()])
        return (d < 1.4).reshape(gx.shape)
    m_r, m_a = mask(xr, yr), mask(xa, ya)
    tr_g = np.where(m_r, tr_g, np.nan)
    diff = np.where(m_r & m_a, tr_g - ta_g, np.nan)

    fig, axs = plt.subplots(1, 2, figsize=(13.5, 6.4), constrained_layout=True)
    for ax in axs:
        ax.set_aspect("equal")
        ax.set_xlim(-110, 27)
        ax.set_ylim(-12, 111)
        ax.set_xlabel("enclosure X (mm)", color=MUTED)
        ax.tick_params(colors=MUTED, labelsize=8)
        for s in ax.spines.values():
            s.set_color("#d0d7de")
    axs[0].set_ylabel("enclosure Y (mm)", color=MUTED)

    im0 = axs[0].pcolormesh(gx, gy, tr_g, cmap="Oranges", vmin=70, vmax=100, shading="auto", rasterized=True)
    axs[0].set_title("Adapter board temperature, Rev08 at 70 °C ambient (°C)", color=INK, fontsize=11, loc="left")
    fig.colorbar(im0, ax=axs[0], shrink=0.8)

    lim = 6.0
    im1 = axs[1].pcolormesh(gx, gy, diff, cmap="RdBu_r", vmin=-lim, vmax=lim, shading="auto", rasterized=True)
    axs[1].set_title("Change against the adopted Rev06/07 board (K)", color=INK, fontsize=11, loc="left")
    fig.colorbar(im1, ax=axs[1], shrink=0.8)

    for ax in axs:
        for lab, (x, y) in PARTS.items():
            ax.plot(x, y, "o", ms=8, mfc="none", mec=INK, mew=1.4)
            off = {"LMR33630": (-58, 6), "LEDs, I/O exp.": (8, -2), "LNA": (8, -6), "IF amp": (8, -12)}.get(lab, (6, 4))
            ax.annotate(lab, (x, y), xytext=off, textcoords="offset points", fontsize=8, color=INK)
    fig.savefig(OUT, dpi=150)
    print("wrote", OUT, "max rise", np.nanmax(diff).round(2), "K, max fall", np.nanmin(diff).round(2), "K")


if __name__ == "__main__":
    main()
