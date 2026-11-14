#!/usr/bin/env python3
"""Generate thermal CFD visualization figures from OpenFOAM results.json and slice NPZs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.tri as mtri
import numpy as np


ROOT = Path(__file__).resolve().parents[2]
CFD_DIR = ROOT / "mech" / "v2_cfd"
SLICES_DIR = CFD_DIR / "slices"
OUT_DIR = ROOT / "docs" / "sim"
RESULTS_PATH = CFD_DIR / "results.json"


def load_results() -> Dict[str, dict]:
    data = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    return {row["name"]: row for row in data}


def plot_options_70c(by_name: Dict[str, dict]) -> None:
    cases = [
        ("v1_open_70C", "v1 Open\n(baseline)"),
        ("sealed_petg_70C", "Opt 1: Sealed\nPETG"),
        ("sealed_paht_70C", "Opt 1: Sealed\nPAHT"),
        ("sealed_alu_70C", "Opt 1b: Sealed\nAl + pads"),
        ("hex2_passive_bare_70C", "Opt 2: Passive\nbare vents"),
        ("hex2_passive_filt_70C", "Opt 2: Passive\nfiltered"),
        ("fan40_imp_filt_70C", "Opt 3: 40mm\nimpinging"),
        ("fan50_imp_filt_70C", "Opt 4: 50mm\nimpinging"),
        ("fan50_exh_filt_70C", "Opt 4b: 50mm\nexhaust"),
        ("fan50_imp_clogged_70C", "Opt 4: 50mm\nclogged 50%"),
        ("fan50_imp_maxpwr_70C", "Opt 4: 50mm\nworst-case"),
    ]
    labels = [lbl for _, lbl in cases]
    x = np.arange(len(cases))

    si549 = [by_name[k]["components"]["U402_Si549"]["T_j_C"] for k, _ in cases]
    xc7a = [by_name[k]["XC7A50T_Tj_C"] for k, _ in cases]
    adclk = [by_name[k]["ADCLK948_Tj_C"] for k, _ in cases]
    k26 = [by_name[k]["K26_Tj_C"] for k, _ in cases]
    tair = [by_name[k]["T_air_max_C"] for k, _ in cases]

    fig, ax = plt.subplots(figsize=(13.5, 6.2), dpi=160)
    w = 0.16
    ax.bar(x - 2 * w, xc7a, width=w, label="XC7A50T (limit 100 C)", color="#1f77b4")
    ax.bar(x - 1 * w, si549, width=w, label="Y401 Si549 (limit 105 C)", color="#d62728")
    ax.bar(x + 0 * w, adclk, width=w, label="U401 ADCLK948 (limit 150 C)", color="#ff7f0e")
    ax.bar(x + 1 * w, k26, width=w, label="K26 SOM (est. 100 C)", color="#2ca02c")
    ax.bar(x + 2 * w, tair, width=w, label="Max cavity air", color="#7f7f7f", alpha=0.8)

    ax.axhline(100.0, color="#1f77b4", linestyle="--", linewidth=1.2, alpha=0.85, label="XC7A50T Tj_max (100 C)")
    ax.axhline(105.0, color="#d62728", linestyle=":", linewidth=1.4, alpha=0.9, label="Si549 Tj_max (105 C)")

    for xi, val in zip(x - 1 * w, si549):
        ax.text(xi, val + 1.2, f"{val:.1f}", ha="center", va="bottom", fontsize=7.5, color="#8c1515", rotation=90)
    for xi, val in zip(x - 2 * w, xc7a):
        ax.text(xi, val + 1.2, f"{val:.1f}", ha="center", va="bottom", fontsize=7.5, color="#124e78", rotation=90)

    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=8.5)
    ax.set_ylabel("Temperature (C)")
    ax.set_ylim(60, 152)
    ax.set_title("Enclosure v2 3D CHT CFD Comparison at Ta = 70 C (Steady-State Peak Temperatures)")
    ax.grid(axis="y", linestyle="--", alpha=0.35)
    ax.legend(loc="upper right", ncol=2, fontsize=8.5, framealpha=0.92)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "v2_cfd_options_70c.png")
    plt.close(fig)


def _tricontour_slice(ax, x, y, z, vmin, vmax, levels, cmap="inferno"):
    tri = mtri.Triangulation(x, y)
    # Mask stretched triangles across solid voids or boundaries
    triangles = tri.triangles
    dx = np.ptp(x[triangles], axis=1)
    dy = np.ptp(y[triangles], axis=1)
    tri.set_mask((dx > 12.0) | (dy > 12.0))
    return ax.tricontourf(tri, z, levels=levels, cmap=cmap, vmin=vmin, vmax=vmax, extend="both")


def plot_flow_slices(by_name: Dict[str, dict]) -> None:
    selected = [
        ("v1_open_70C", "v1 Open (70 C)"),
        ("sealed_alu_70C", "Opt 1b: Sealed Al + Pads (70 C)"),
        ("hex2_passive_filt_70C", "Opt 2: Passive Filtered (70 C)"),
        ("fan50_imp_filt_70C", "Opt 4: 50mm Impinging Fan (70 C)"),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(13.0, 7.6), dpi=160, sharex=True, sharey=True)
    levels = np.linspace(70.0, 118.0, 25)
    cf = None
    for ax, (name, title) in zip(axes.flat, selected):
        z = np.load(SLICES_DIR / f"{name}.npz")
        x = z["xz_x"]
        zz = z["xz_z"]
        T = z["xz_T"]
        U = z["xz_U"]
        cf = _tricontour_slice(ax, x, zz, T, 70.0, 118.0, levels, cmap="turbo")

        # Subsample velocity vectors on coarse 8mm x 4mm spatial grid
        bx = np.linspace(x.min() + 4.0, x.max() - 4.0, 18)
        bz = np.linspace(zz.min() + 2.5, zz.max() - 2.5, 8)
        qx, qz, qu, qw = [], [], [], []
        for cx in bx:
            for cz in bz:
                d2 = (x - cx) ** 2 + (zz - cz) ** 2
                idx = int(np.argmin(d2))
                if d2[idx] < 25.0:
                    qx.append(x[idx])
                    qz.append(zz[idx])
                    qu.append(U[idx, 0])
                    qw.append(U[idx, 2])
        ax.quiver(qx, qz, qu, qw, color="white", alpha=0.8, scale=42, width=0.0028, headwidth=3.5)

        row = by_name[name]
        ax.set_title(
            f"{title}\nTair_max={row['T_air_max_C']} C, Umax={row['U_air_max_mps']} m/s, "
            f"Si549={row['components']['U402_Si549']['T_j_C']} C",
            fontsize=9.5,
        )
        ax.set_xlabel("X (mm)")
        ax.set_ylabel("Z (mm)")

    fig.subplots_adjust(right=0.90, hspace=0.30, wspace=0.14)
    cax = fig.add_axes([0.92, 0.14, 0.02, 0.72])
    cbar = fig.colorbar(cf, cax=cax)
    cbar.set_label("Air Temperature (C)")
    fig.suptitle("X-Z Cavity Airflow (Velocity Vectors) and Air Temperature Contours at Y ~ 42 mm (Ta = 70 C)", fontsize=12)
    fig.savefig(OUT_DIR / "v2_cfd_flow_slices.png", bbox_inches="tight")
    plt.close(fig)


def plot_adapter_maps(by_name: Dict[str, dict]) -> None:
    selected = [
        ("v1_open_70C", "v1 Open (70 C)"),
        ("sealed_petg_70C", "Opt 1: Sealed PETG (70 C)"),
        ("sealed_alu_70C", "Opt 1b: Sealed Al + Pads (70 C)"),
        ("fan50_imp_filt_70C", "Opt 4: 50mm Impinging Fan (70 C)"),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(13.0, 8.2), dpi=160, sharex=True, sharey=True)
    levels = np.linspace(80.0, 130.0, 26)
    cf = None
    for ax, (name, title) in zip(axes.flat, selected):
        z = np.load(SLICES_DIR / f"{name}.npz")
        x = z["ad_x"]
        y = z["ad_y"]
        T = z["ad_T"]
        cf = _tricontour_slice(ax, x, y, T, 80.0, 130.0, levels, cmap="inferno")
        row = by_name[name]
        ax.set_title(
            f"{title}\nXC7A50T Tj={row['XC7A50T_Tj_C']} C, ADCLK948 Tj={row['ADCLK948_Tj_C']} C, "
            f"Si549 Tj={row['components']['U402_Si549']['T_j_C']} C",
            fontsize=9.2,
        )
        ax.set_xlabel("Enclosure X (mm)")
        ax.set_ylabel("Enclosure Y (mm)")

    fig.subplots_adjust(right=0.90, hspace=0.28, wspace=0.14)
    cax = fig.add_axes([0.92, 0.14, 0.02, 0.72])
    cbar = fig.colorbar(cf, cax=cax)
    cbar.set_label("Adapter PCB Temperature (C)")
    fig.suptitle("Adapter PCB Temperature Map (Top View) Across Cooling Options at Ta = 70 C", fontsize=12)
    fig.savefig(OUT_DIR / "v2_cfd_adapter_maps.png", bbox_inches="tight")
    plt.close(fig)


def plot_ambient_and_mesh(by_name: Dict[str, dict]) -> None:
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13.2, 5.2), dpi=160)

    amb = [25, 45, 70]
    families = [
        ("v1_open", "v1 Open (Si549 Tj)", "U402_Si549", "#7f7f7f", "-o"),
        ("sealed_petg", "Opt 1 Sealed PETG (Si549 Tj)", "U402_Si549", "#d62728", "-s"),
        ("sealed_alu", "Opt 1b Sealed Al+Pads (Si549 Tj)", "U402_Si549", "#2ca02c", "-^"),
        ("sealed_alu", "Opt 1b Sealed Al+Pads (K26 Tj)", "K26", "#2ca02c", "--^"),
        ("fan50_imp_filt", "Opt 4 50mm Fan (Si549 Tj)", "U402_Si549", "#1f77b4", "-D"),
        ("fan50_imp_filt", "Opt 4 50mm Fan (XC7A50T Tj)", "XC7A50T", "#1f77b4", "--D"),
    ]
    for prefix, lbl, comp, color, fmt in families:
        vals = []
        for t in amb:
            row = by_name[f"{prefix}_{t}C"]
            if comp == "XC7A50T":
                vals.append(row["XC7A50T_Tj_C"])
            elif comp == "K26":
                vals.append(row["K26_Tj_C"])
            else:
                vals.append(row["components"][comp]["T_j_C"])
        ax1.plot(amb, vals, fmt, color=color, linewidth=1.8, markersize=6, label=lbl)

    ax1.axhline(100.0, color="#1f77b4", linestyle=":", linewidth=1.2, label="XC7A50T Tj_max (100 C)")
    ax1.axhline(105.0, color="#d62728", linestyle=":", linewidth=1.2, label="Si549 Tj_max (105 C)")
    ax1.set_xlabel("Ambient Temperature Ta (C)")
    ax1.set_ylabel("Junction Temperature Tj (C)")
    ax1.set_title("Ambient Temperature Sweep (25 C / 45 C / 70 C)")
    ax1.set_xticks(amb)
    ax1.grid(True, linestyle="--", alpha=0.35)
    ax1.legend(fontsize=7.8, loc="upper left")

    mesh_cases = [
        ("conv_coarse_70C", "Coarse"),
        ("fan50_imp_filt_70C", "Medium"),
        ("conv_fine_70C", "Fine"),
    ]
    cells = [by_name[k]["cells_air"] + by_name[k]["cells_solid"] for k, _ in mesh_cases]
    xc_m = [by_name[k]["XC7A50T_Tj_C"] for k, _ in mesh_cases]
    si_m = [by_name[k]["components"]["U402_Si549"]["T_j_C"] for k, _ in mesh_cases]
    ad_m = [by_name[k]["ADCLK948_Tj_C"] for k, _ in mesh_cases]
    k26_m = [by_name[k]["K26_Tj_C"] for k, _ in mesh_cases]

    ax2.plot(cells, ad_m, "-o", label="ADCLK948 Tj", color="#ff7f0e")
    ax2.plot(cells, si_m, "-s", label="Si549 Tj", color="#d62728")
    ax2.plot(cells, k26_m, "-^", label="K26 SOM Tj", color="#2ca02c")
    ax2.plot(cells, xc_m, "-D", label="XC7A50T Tj", color="#1f77b4")
    for c_val, (_, lbl) in zip(cells, mesh_cases):
        ax2.annotate(f"{lbl}\n({c_val//1000}k)", (c_val, ad_m[cells.index(c_val)] + 1.5), ha="center", fontsize=8)
    ax2.set_xscale("log")
    ax2.set_xlabel("Total Mesh Cells (air + solid)")
    ax2.set_ylabel("Junction Temperature Tj (C)")
    ax2.set_title("Mesh Convergence Study (Opt 4, Ta = 70 C)")
    ax2.set_ylim(88, 128)
    ax2.grid(True, which="both", linestyle="--", alpha=0.35)
    ax2.legend(fontsize=8.5, loc="lower left")

    fig.tight_layout()
    fig.savefig(OUT_DIR / "v2_cfd_ambient_and_mesh.png")
    plt.close(fig)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    by_name = load_results()
    plot_options_70c(by_name)
    plot_flow_slices(by_name)
    plot_adapter_maps(by_name)
    plot_ambient_and_mesh(by_name)
    print("Generated 4 CFD plots in", OUT_DIR)


if __name__ == "__main__":
    main()
