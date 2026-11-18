"""One figure for every G-8 receive case: the antenna level at which each mode meets its criterion, the RTL
against the floating-point reference on the same input (FPGA_GATEWARE.md §6.1). Reads results.json next to this
script, writes docs/img/sim/g8_overview.png. Run: python fpga/sim/signals/g8_overview.py"""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.transforms

here = Path(__file__).resolve().parent
root = here.parents[2]
r = json.loads((here / "results.json").read_text())

# case, label (band, frequency, mode), RTL key, reference key, criterion
rows = [
    ("hf_am", "HF AM, 7.2 MHz", "sens10_rtl_dbm", "sens10_ref_dbm", "10 dB SINAD"),
    ("hf_ssb", "HF SSB (USB), 14.2 MHz", "sens10_rtl_dbm", "sens10_ref_dbm", "10 dB SINAD"),
    ("fm", "VHF FM broadcast, 98.1 MHz", "sens30_rtl_dbm", "sens30_ref_dbm", "30 dB SINAD"),
    ("air", "VHF airband AM, 121.5 MHz", "sens10_rtl_dbm", "sens10_ref_dbm", "10 dB SINAD"),
    ("nbfm", "UHF PMR446 NBFM, 446 MHz", "sens12_rtl_dbm", "sens12_ref_dbm", "12 dB SINAD"),
    ("adsb", "ADS-B, 1090 MHz", "l90_dbm", "l90_ref_dbm", "90 % decoded"),
]
for case, *_ in rows:
    if not r.get(case, {}).get("passed"):
        raise SystemExit(f"{case}: no passing result in results.json")

INK, MUTED, GRID, SURF = "#1f2328", "#59636e", "#e6e8eb", "#ffffff"
RTL, REF = "#2a6fdb", "#e8772e"  # categorical slots 1 and 2, fixed order

fig, ax = plt.subplots(figsize=(11, 4.6), dpi=160)
fig.patch.set_facecolor(SURF)
ax.set_facecolor(SURF)
ys = list(range(len(rows)))[::-1]
for y, (case, label, kr, kf, crit) in zip(ys, rows):
    a, b = r[case][kr], r[case][kf]
    ax.plot([a, b], [y, y], color=GRID, lw=6, solid_capstyle="round", zorder=1)
    ax.scatter([b], [y], s=90, color=REF, edgecolor=SURF, linewidth=2, zorder=3)
    ax.scatter([a], [y], s=90, color=RTL, edgecolor=SURF, linewidth=2, zorder=4)
    tr = matplotlib.transforms.blended_transform_factory(ax.transAxes, ax.transData)
    ax.text(1.02, y, f"{a:.1f} dBm   (ref {b:.1f}),  {crit}", transform=tr, ha="left", va="center", fontsize=9.5, color=INK)
ax.set_yticks(ys)
ax.set_yticklabels([x[1] for x in rows], fontsize=10, color=INK)
ax.set_xlim(-127, -83)
ax.set_xlabel("Antenna level at the criterion (dBm); further left is more sensitive", fontsize=10, color=MUTED)
ax.grid(axis="x", color=GRID, lw=0.8)
ax.set_axisbelow(True)
for s in ("top", "right", "left"):
    ax.spines[s].set_visible(False)
ax.spines["bottom"].set_color(GRID)
ax.tick_params(axis="x", colors=MUTED, labelsize=9)
ax.tick_params(axis="y", length=0)
ax.scatter([], [], s=70, color=RTL, label="Kria RTL, full chain gain and noise")
ax.scatter([], [], s=70, color=REF, label="floating-point reference, same input")
ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=2, frameon=False, fontsize=9.5)
fig.suptitle("G-8: sensitivity of every receive mode, RTL against reference", fontsize=12, color=INK, y=1.0)
fig.tight_layout()
out = root / "docs" / "img" / "sim" / "g8_overview.png"
fig.savefig(out, facecolor=SURF, bbox_inches="tight")
print("wrote", out)
