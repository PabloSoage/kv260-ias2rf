"""docs/sim/eth_branches.png: eye openings of the two link pairs the Ethernet option shares, as simulated
(SIGNAL_INTEGRITY 9.7, stubsim.py / lvds_eye.py at 1.25 Gb/s). Numbers typed from that section."""
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
rows = [  # label, low, high, kept
    ("LINK_TX_D0, no branch", 518, 518, False),
    ("LINK_TX_D0, C1218 beside R101 (6.6 mm branch)", 461, 461, False),
    ("LINK_TX_D0, C1218 on the bottom face", 489, 499, False),
    ("LINK_TX_D0, C1218 on top below the notch (built)", 477, 484, True),
    ("LINK_RX_D0, no branch", 609, 609, False),
    ("LINK_RX_D0, C1220/C1221 branches (built)", 601, 607, True),
    ("Ethernet mode: FPGA to PHY", 350, 350, True),
    ("Ethernet mode: PHY to FPGA", 637, 637, True),
]
INK, MUTED, ACC, NEU, GRID = "#1f2328", "#59636e", "#2f6fb3", "#b8c0c8", "#e6e9ec"
fig, ax = plt.subplots(figsize=(9.5, 4.6), dpi=150)
for i, (lab, lo, hi, kept) in enumerate(rows):
    y = len(rows) - 1 - i - (0.5 if i >= 4 else 0) - (0.5 if i >= 6 else 0)
    mid = (lo + hi) / 2
    ax.barh(y, mid, height=0.62, color=ACC if kept else NEU, edgecolor="white", linewidth=2)
    if hi > lo:
        ax.errorbar(mid, y, xerr=[[mid - lo], [hi - mid]], fmt="none", ecolor=INK, elinewidth=1.2, capsize=3)
    ax.text(hi + 8, y, f"{lo}" if hi == lo else f"{lo}-{hi}", va="center", fontsize=9, color=INK)
    ax.text(-8, y, lab, va="center", ha="right", fontsize=9, color=INK if kept else MUTED)
ax.axvline(200, color=MUTED, lw=1, ls=(0, (4, 3)))
ax.text(206, 7.62, "receiver needs 200 mV (±100 mV threshold)", fontsize=8, color=MUTED, va="center")
ax.set_xlim(0, 700); ax.set_ylim(-1.5, 7.95); ax.set_yticks([]); ax.set_xlabel("Eye opening at 1.25 Gb/s, mV", color=INK, fontsize=9)
for s in ("top", "right", "left"): ax.spines[s].set_visible(False)
ax.spines["bottom"].set_color(MUTED); ax.tick_params(colors=MUTED, labelsize=8)
ax.xaxis.grid(True, color=GRID, lw=0.8); ax.set_axisbelow(True)
ax.set_title("The Ethernet option's cost to the IAS1 link, and its own paths (blue: as built)", fontsize=10, color=INK, loc="left", x=-0.62)
fig.subplots_adjust(left=0.40, right=0.97, top=0.9, bottom=0.13)
fig.savefig("/mnt/d/Repos/kv260-ias2rf/docs/sim/eth_branches.png")
