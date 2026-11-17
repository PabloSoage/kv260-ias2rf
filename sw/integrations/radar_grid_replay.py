"""R5F core 1's radar scan and grid commands, replayed through the grid model; figure.

    cargo run --release --example radar_grid      (in sw/kria/core; writes fpga/sim/out/radar_grid)
    python sw/integrations/radar_grid_replay.py   (expected grid for the RTL bench, and the figure)
    fpga/sim/run.ps1 tb_kria_bev_axi -PlusArg BEV_DIR=../radar_grid

The Rust example runs kria-core's scheduler, coordinate transform and command encoding against models of the
Artix's beam scan, kria_radar_proc and a scene, plus Linux's 77 GHz object list through the ring. This script
feeds its command stream to the bit-exact grid model (bev_fusion_sim.BevGrid, the one tb_kria_bev_grid checks the
RTL against), writes bev_expect.hex next to the stimulus, and draws docs/img/integrations/radar_grid_e2e.png:
the beam the Artix holds over time (longer dwells where there is a target) and the grid at the end.
"""
import csv
import os
import sys

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bev_fusion_sim as bev  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
IMG = os.path.join(ROOT, "docs", "img", "integrations")
C1, C2, C3, C4 = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"
plt.rcParams.update({
    "font.size": 10, "axes.edgecolor": INK2, "axes.labelcolor": INK, "xtick.color": INK2,
    "ytick.color": INK2, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
    "axes.spines.top": False, "axes.spines.right": False, "legend.frameon": False,
})

# The scene in the Rust example, at t = 2 s (x forward, y left, metres)
TARGETS = [("car ahead", 34.0 - 2.0 * 2, 0.5), ("pedestrian", 14.0, 5.0), ("cyclist", 22.0, -9.0 + 4.0 * 2),
           ("parked van", 9.0, -4.5)]


def main():
    d = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "fpga", "sim", "out", "radar_grid")
    rows = [list(map(int, l.split())) for l in open(os.path.join(d, "bev_cfg.txt"))]
    cfg = dict(origin_x=rows[0], origin_y=rows[1], hit=rows[2], miss=rows[3], ray=rows[4])
    words, n = [], {"det": [0, 0, 0, 0], "decay": 0, "dump": 0}
    for line in open(os.path.join(d, "bev_stim.hex")):
        v = int(line, 16)
        op, s = (v >> 34) & 3, (v >> 32) & 3
        if op == 1:
            words.append(("decay",))
            n["decay"] += 1
        elif op == 2:
            n["dump"] += 1
        else:
            words.append((v & 0xFFFF, (v >> 16) & 0xFFFF, s))
            n["det"][s] += 1
    assert n["dump"] == 1, "the bench takes exactly one dump, the last command"
    g = bev.run(words, cfg)
    bev.write_bench_files([], g, d)          # writes bev_expect.hex (and a stimulus we put back below)
    # write_bench_files rewrote bev_stim.hex from an empty list: restore the Rust stimulus
    with open(os.path.join(d, "bev_stim.hex"), "w") as f:
        for w in words:
            if w[0] == "decay":
                f.write("%09X\n" % (1 << 34))
            else:
                f.write("%09X\n" % ((w[2] << 32) | (w[1] << 16) | w[0]))
        f.write("%09X\n" % (2 << 34))
    print("replay: %d radar-10.5 and %d radar-77 detections, %d decay passes; occupied cells %d, max %d"
          % (n["det"][2], n["det"][1], n["decay"], int((g > 20).sum()), int(g.max())))

    tr = list(csv.DictReader(open(os.path.join(d, "trace.csv"))))
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(11, 4.8), gridspec_kw={"width_ratios": [1.25, 1]})
    # beam held over the first 120 ms: a step line, and the CPIs that detected something
    t_s, b_s = [], []
    for r in tr:
        if r["strobe"] == "1":
            t_s.append(float(r["t_ms"]))
            b_s.append(int(r["beam"]))
    t_s.append(120.0)
    b_s.append(b_s[-1])
    az = [-45 + 7.5 * b for b in b_s]
    ax.step(t_s, az, where="post", color=C1, lw=1.6, label="beam the Artix holds")
    hits = [(float(r["t_ms"]), int(r["az_cdeg"]) / 100) for r in tr if r["range_cm"] and float(r["t_ms"]) <= 120]
    ax.scatter([h[0] for h in hits], [h[1] for h in hits], s=10, color=C2, zorder=3,
               label="CPI with a detection (dwell extended)")
    ax.set_xlim(0, 120)
    ax.set_ylim(-50, 68)
    ax.set_yticks(range(-45, 50, 15))
    ax.set_xlabel("time (ms)")
    ax.set_ylabel("beam azimuth (degrees, + left)")
    ax.set_title("R5F core 1: scan, 13 beams, dwell 2 to 8 CPIs", loc="left", fontsize=10, color=INK)
    ax.legend(loc="upper left", fontsize=9, ncol=1)

    sub = g[128:256, 64:192].astype(float)  # x 0..64 m forward, y -32..32 m
    im = ax2.imshow(sub, cmap="RdBu_r", vmin=-127, vmax=127, origin="lower", extent=[-32, 32, 0, 64],
                    aspect="auto")
    for name, x, y in TARGETS:
        ax2.scatter([y], [x], s=60, facecolors="none", edgecolors=INK, lw=1.0)
        ax2.annotate(name, (y, x), xytext=(6, 4), textcoords="offset points", fontsize=8, color=INK)
    ax2.set_xlim(20, -20)
    ax2.set_ylim(0, 45)
    ax2.set_xlabel("y, left (m)")
    ax2.set_ylabel("x, forward (m)")
    ax2.grid(False)
    ax2.set_title("PL grid after 2 s (10.5 GHz scan + 77 GHz objects)", loc="left", fontsize=10, color=INK)
    fig.colorbar(im, ax=ax2, shrink=0.85, label="log-odds")
    fig.tight_layout()
    os.makedirs(IMG, exist_ok=True)
    out = os.path.join(IMG, "radar_grid_e2e.png")
    fig.savefig(out, dpi=150)
    print("figure:", out)


if __name__ == "__main__":
    main()
