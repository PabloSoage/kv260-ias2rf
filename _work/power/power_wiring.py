#!/usr/bin/env python3
"""Generate docs/img/power_wiring.png for BOARD_MANUAL.md section 6.

Two-panel wiring and grounding diagram for single-entry power:
  Left  - Vehicle installation (single chassis ground, 5 A fuse, regulated DC-DC, J1503 CAN ground)
  Right - Home / bench installation (one 12 V 5 A brick, Class II preferred, ferrite clamps on earthed leads)
"""

import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "docs", "img", "power_wiring.png")

BG_CANVAS = "#E9ECEF"
BG_PANEL = "#DFE3E8"
BORDER_PANEL = "#AAB2BD"

INK = "#1B2028"
MUTED = "#47515E"

KV_FILL = "#A6CFA9"     # KV260 PCB green
KV_EDGE = "#1F5B2C"
AD_FILL = "#C5D4E2"     # Adapter slate blue
AD_EDGE = "#264B6B"
PSU_FILL = "#D6D9DF"
PSU_EDGE = "#505A66"
NOTE_FILL = "#D8DEE6"
NOTE_EDGE = "#7B8794"
WARN_FILL = "#EAD5D3"
WARN_EDGE = "#A62626"

RED = "#B52B27"
CHARCOAL = "#22272E"
EARTH = "#3E6B2C"
FER_FILL = "#3A3F47"
FER_EDGE = "#181B20"


def rbox(ax, x, y, w, h, fc, ec, lw=1.4, r=0.14, ls="-", zorder=2):
    p = FancyBboxPatch(
        (x, y), w, h,
        boxstyle=f"round,pad=0.0,rounding_size={r}",
        facecolor=fc, edgecolor=ec, linewidth=lw, linestyle=ls, zorder=zorder,
    )
    ax.add_patch(p)
    return p


def arrow(ax, p1, p2, color=CHARCOAL, lw=1.8, ls="-", rad=0.0, zorder=4):
    a = FancyArrowPatch(
        p1, p2,
        arrowstyle="-|>,head_length=0.52,head_width=0.33",
        mutation_scale=13,
        color=color, linewidth=lw, linestyle=ls,
        connectionstyle=f"arc3,rad={rad}", zorder=zorder,
    )
    ax.add_patch(a)


def wire(ax, pts, color=CHARCOAL, lw=1.8, ls="-", zorder=3):
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    ax.plot(xs, ys, color=color, linewidth=lw, linestyle=ls, solid_capstyle="round", zorder=zorder)


def gnd_symbol(ax, x, y, color=CHARCOAL, scale=1.0, zorder=5):
    ax.plot([x, x], [y, y - 0.18 * scale], color=color, lw=1.7, zorder=zorder)
    for dy, hw in ((0.18, 0.24), (0.28, 0.16), (0.38, 0.08)):
        ax.plot([x - hw * scale, x + hw * scale], [y - dy * scale, y - dy * scale],
                color=color, lw=1.7, solid_capstyle="round", zorder=zorder)


def ferrite_clamp(ax, x, y, label="Ferrite clamp"):
    w, h = 0.44, 0.30
    rbox(ax, x - w / 2, y - h / 2, w, h, FER_FILL, FER_EDGE, lw=1.2, r=0.05, zorder=6)
    ax.plot([x - w / 2, x + w / 2], [y, y], color="#8E96A0", lw=0.8, zorder=7)
    if label:
        ax.text(x, y + 0.22, label, ha="center", va="bottom", fontsize=7.5,
                fontweight="bold", color=INK, zorder=7)


def draw_car_panel(ax):
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    ax.axis("off")

    rbox(ax, 0.12, 0.12, 9.76, 9.76, BG_PANEL, BORDER_PANEL, lw=1.5, r=0.22, zorder=1)
    ax.text(0.42, 9.54, "A. Vehicle installation: single chassis ground point",
            fontsize=11.5, fontweight="bold", color=INK, va="top")
    ax.text(0.42, 9.12, "Only one 12 V supply and one return path; zero chassis ground loop through BM20 contacts",
            fontsize=8.3, color=MUTED, va="top")

    # 12 V Battery
    rbox(ax, 0.38, 6.45, 1.48, 1.85, PSU_FILL, PSU_EDGE, lw=1.5, r=0.12)
    ax.text(1.12, 7.82, "12 V Battery", ha="center", va="center", fontsize=8.9, fontweight="bold", color=INK)
    ax.text(1.12, 7.28, "Alternator +\nLiFePO4 bus", ha="center", va="center", fontsize=7.4, color=MUTED)
    ax.text(1.12, 6.68, "+12 V     GND", ha="center", va="center", fontsize=7.4, fontweight="bold", color=INK)

    # 5 A fuse
    rbox(ax, 2.22, 7.36, 1.06, 0.90, PSU_FILL, RED, lw=1.5, r=0.10)
    ax.text(2.75, 7.96, "5 A Fuse", ha="center", va="center", fontsize=8.5, fontweight="bold", color=RED)
    ax.text(2.75, 7.60, "Inline harness\n(was 3 A)", ha="center", va="center", fontsize=7.0, color=MUTED)

    # Regulated 12 V DC-DC converter
    rbox(ax, 3.64, 6.82, 2.08, 1.44, PSU_FILL, PSU_EDGE, lw=1.5, r=0.12)
    ax.text(4.68, 7.96, "Regulated DC-DC", ha="center", va="center", fontsize=8.8, fontweight="bold", color=INK)
    ax.text(4.68, 7.34, "12.0 V out (< 13.2 V)\n>= 5 A continuous\nBlocks Load Dump A",
            ha="center", va="center", fontsize=7.3, color=MUTED, linespacing=1.18)

    # +12 V path Battery -> Fuse -> DC-DC -> J1001
    arrow(ax, (1.86, 7.82), (2.22, 7.82), color=RED, lw=2.1)
    arrow(ax, (3.28, 7.82), (3.64, 7.82), color=RED, lw=2.1)
    arrow(ax, (5.72, 7.82), (6.42, 7.82), color=RED, lw=2.1)
    ax.text(6.07, 8.00, "+12 V", fontsize=7.7, fontweight="bold", color=RED, ha="center")

    # Single chassis ground bus bar (y = 1.85)
    ax.plot([0.80, 9.00], [1.85, 1.85], color=CHARCOAL, lw=2.6, solid_capstyle="round", zorder=3)
    ax.scatter([1.12, 3.05, 5.15, 6.02], [1.85, 1.85, 1.85, 1.85], s=32, color=CHARCOAL, zorder=5)
    gnd_symbol(ax, 1.12, 1.85, color=CHARCOAL, scale=1.05)
    ax.text(1.12, 1.28, "Single vehicle chassis\nground point", ha="center", va="top",
            fontsize=8.1, fontweight="bold", color=INK)
    ax.text(3.16, 2.02, "Single return bus",
            fontsize=7.6, fontweight="bold", color=CHARCOAL, ha="left")

    # Clean vertical GND wires to bus (zero overlap with J1503)
    wire(ax, [(1.12, 6.45), (1.12, 1.85)], color=CHARCOAL, lw=1.9)
    wire(ax, [(5.15, 6.82), (5.15, 1.85)], color=CHARCOAL, lw=1.8)

    # J1503 CAN harness ground (strictly x = 1.65..4.45, clear of x = 1.12 and x = 5.15)
    rbox(ax, 1.65, 3.65, 2.80, 1.32, "#DCE5EE", AD_EDGE, lw=1.3, r=0.12)
    ax.text(3.05, 4.74, "J1503 (GPS PPS + CAN)", ha="center", va="top", fontsize=8.2, fontweight="bold", color=INK)
    ax.text(3.05, 4.18, "CANH / CANL to vehicle bus\nPins 1 & 4 GND from same point",
            ha="center", va="center", fontsize=7.0, color=MUTED, linespacing=1.16)
    wire(ax, [(3.05, 3.65), (3.05, 1.85)], color=CHARCOAL, lw=1.6, ls="--")
    ax.text(2.94, 2.88, "CAN GND\n(same point)", ha="right", va="center", fontsize=7.2, color=INK)
    wire(ax, [(4.45, 4.70), (6.42, 5.55)], color=AD_EDGE, lw=1.4, ls=":")

    # Adapter board container (right column x = 6.42..9.62)
    rbox(ax, 6.42, 5.25, 3.20, 3.30, AD_FILL, AD_EDGE, lw=1.7, r=0.16)
    ax.text(8.02, 8.34, "IAS2RF Adapter Board", ha="center", va="top", fontsize=9.4, fontweight="bold", color=INK)

    # J1001 & L1004 inside adapter
    rbox(ax, 6.56, 6.80, 1.00, 1.15, "#DCE5EE", AD_EDGE, lw=1.2, r=0.08, zorder=3)
    ax.text(7.06, 7.66, "J1001", ha="center", va="center", fontsize=8.2, fontweight="bold", color=INK, zorder=4)
    ax.text(7.06, 7.14, "5 A jack\nGND_IN", ha="center", va="center", fontsize=7.0, color=MUTED, zorder=4)

    rbox(ax, 7.98, 6.80, 1.50, 1.15, "#DCE5EE", AD_EDGE, lw=1.2, r=0.08, zorder=3)
    ax.text(8.73, 7.66, "L1004 (CM)", ha="center", va="center", fontsize=8.2, fontweight="bold", color=INK, zorder=4)
    ax.text(8.73, 7.14, "Both +12V & GND\n6 A, 600R@100M", ha="center", va="center", fontsize=6.9, color=MUTED, zorder=4)

    # Adapter rail + Q1010/U1010 inside adapter
    rbox(ax, 6.56, 5.40, 1.32, 1.10, "#DCE5EE", AD_EDGE, lw=1.1, r=0.08, zorder=3)
    ax.text(7.22, 6.22, "Adapter rail", ha="center", va="center", fontsize=7.7, fontweight="bold", color=INK, zorder=4)
    ax.text(7.22, 5.74, "F1001 2 A PTC\nU1009 (1.12 A)", ha="center", va="center", fontsize=6.8, color=MUTED, zorder=4)

    rbox(ax, 8.05, 5.40, 1.43, 1.10, "#DCE5EE", AD_EDGE, lw=1.1, r=0.08, zorder=3)
    ax.text(8.765, 6.22, "Q1010 + U1010", ha="center", va="center", fontsize=7.6, fontweight="bold", color=INK, zorder=4)
    ax.text(8.765, 5.74, "OVP 14.4 V, 3.6 A\n-> J1004 out", ha="center", va="center", fontsize=6.8, color=MUTED, zorder=4)

    # Adapter internal and external GND connections
    wire(ax, [(6.02, 1.85), (6.02, 7.05), (6.56, 7.05)], color=CHARCOAL, lw=1.9)
    arrow(ax, (7.56, 7.38), (7.98, 7.38), color=CHARCOAL, lw=1.5)
    arrow(ax, (8.30, 6.80), (7.50, 6.50), color=RED, lw=1.4)
    arrow(ax, (8.765, 6.80), (8.765, 6.50), color=RED, lw=1.4)

    # KV260 box (KV260 GREEN!)
    rbox(ax, 6.42, 2.55, 3.20, 1.50, KV_FILL, KV_EDGE, lw=1.8, r=0.16)
    ax.text(8.02, 3.84, "AMD Kria KV260", ha="center", va="top", fontsize=9.6, fontweight="bold", color=INK)
    ax.text(8.02, 3.36, "J12 input (+12V_KV)\nMP5016 OVP 13.2 V, 3 A typ / 3.6 A lim",
            ha="center", va="center", fontsize=7.1, color="#16381D", linespacing=1.16)
    ax.text(8.02, 2.76, "Do NOT plug any other supply into J12",
            ha="center", va="center", fontsize=7.3, fontweight="bold", color="#5F1212")

    # Between Adapter (y=5.25) and KV260 (y=4.05): both labels right of their wires, clear of x=6.02
    wire(ax, [(6.65, 5.25), (6.65, 4.05)], color=CHARCOAL, lw=2.3)
    ax.text(6.74, 4.66, "BM20 + FFC/Pmod\n125 mA/contact\n(limit 300 mA)",
            ha="left", va="center", fontsize=6.85, color=INK, linespacing=1.12)

    arrow(ax, (8.28, 5.25), (8.28, 4.05), color=RED, lw=2.2)
    ax.text(8.38, 4.66, "J1004 -> J12\nVHR-2N jumper\n18 AWG (~15 cm)",
            ha="left", va="center", fontsize=6.85, fontweight="bold", color=RED, linespacing=1.12)

    # CROSSED-OUT second chassis ground wire from KV260
    wire(ax, [(8.02, 2.55), (8.02, 1.85)], color="#C92A2A", lw=2.2, ls="--", zorder=5)
    cx, cy = 8.02, 2.20
    ax.plot([cx - 0.18, cx + 0.18], [cy - 0.18, cy + 0.18], color="#C92A2A", lw=3.2, solid_capstyle="round", zorder=8)
    ax.plot([cx - 0.18, cx + 0.18], [cy + 0.18, cy - 0.18], color="#C92A2A", lw=3.2, solid_capstyle="round", zorder=8)

    rbox(ax, 4.85, 0.36, 4.77, 1.06, WARN_FILL, WARN_EDGE, lw=1.3, r=0.10)
    ax.text(7.235, 0.89,
            "FORBIDDEN: second KV260 wire to chassis\n"
            "1.0 V chassis offset drives 411 mA/contact in BM20\n"
            "(exceeds 300 mA rating from 0.75 V on 1 m leads)",
            ha="center", va="center", fontsize=7.3, fontweight="bold", color="#6E1414", linespacing=1.18)


def draw_home_panel(ax):
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    ax.axis("off")

    rbox(ax, 0.12, 0.12, 9.76, 9.76, BG_PANEL, BORDER_PANEL, lw=1.5, r=0.22, zorder=1)
    ax.text(0.42, 9.54, "B. Home / bench installation: one brick and ferrite clamps",
            fontsize=11.5, fontweight="bold", color=INK, va="top")
    ax.text(0.42, 9.12, "L1004 attenuates PSU CM current 3 to 10 dB; external earthed cables still need ferrite clamps",
            fontsize=8.3, color=MUTED, va="top")

    # Wall Adapter
    rbox(ax, 0.38, 5.75, 2.25, 2.45, PSU_FILL, PSU_EDGE, lw=1.5, r=0.14)
    ax.text(1.505, 7.92, "Wall Adapter", ha="center", va="top", fontsize=9.4, fontweight="bold", color=INK)
    ax.text(1.505, 7.22, "ONE 12 V, >= 5 A supply\n11.7 W + KV260 (~23-55 W)\n1.8 m DC output lead",
            ha="center", va="center", fontsize=7.4, color=MUTED, linespacing=1.18)
    rbox(ax, 0.54, 5.92, 1.93, 0.62, "#C9D8C7", EARTH, lw=1.1, r=0.08, zorder=3)
    ax.text(1.505, 6.23, "Prefer 2-prong (Class II)\nno mains earth loop",
            ha="center", va="center", fontsize=7.2, fontweight="bold", color="#1A421D", linespacing=1.12, zorder=4)

    wire(ax, [(1.505, 5.75), (1.505, 5.05)], color=EARTH, lw=1.5, ls="--")
    gnd_symbol(ax, 1.505, 5.05, color=EARTH, scale=0.85)
    ax.text(1.505, 4.60, "If 3-prong brick:\nPE earth + Y-cap", ha="center", va="top", fontsize=7.1, color=EARTH)

    # Module block (Adapter top + KV260 bottom green)
    rbox(ax, 3.55, 5.65, 2.75, 2.55, AD_FILL, AD_EDGE, lw=1.6, r=0.15)
    ax.text(4.925, 7.98, "IAS2RF Adapter", ha="center", va="top", fontsize=9.3, fontweight="bold", color=INK)
    rbox(ax, 3.74, 6.55, 2.37, 0.98, "#DCE5EE", AD_EDGE, lw=1.2, r=0.08, zorder=3)
    ax.text(4.925, 7.04, "J1001 -> L1004 (600R@100M)\nQ1010/U1010 -> J1004",
            ha="center", va="center", fontsize=7.3, fontweight="bold", color=INK, linespacing=1.20, zorder=4)
    ax.text(4.925, 6.10, "Board GND plane\n(0.5 mOhm + 5 nH [E] to SMAs)",
            ha="center", va="center", fontsize=7.0, color=MUTED, linespacing=1.15)

    rbox(ax, 3.55, 2.95, 2.75, 1.85, KV_FILL, KV_EDGE, lw=1.8, r=0.15)
    ax.text(4.925, 4.58, "AMD Kria KV260", ha="center", va="top", fontsize=9.6, fontweight="bold", color=INK)
    ax.text(4.925, 3.86, "J12 (+12V_KV)\nsole power entry\nNothing else on J12",
            ha="center", va="center", fontsize=7.5, color="#16381D", linespacing=1.18)

    arrow(ax, (2.63, 7.12), (3.55, 7.12), color=RED, lw=2.2)
    ax.text(3.09, 7.30, "+12V / GND", ha="center", va="bottom", fontsize=7.3, fontweight="bold", color=INK)

    arrow(ax, (5.40, 5.65), (5.40, 4.80), color=RED, lw=2.1)
    ax.text(5.50, 5.23, "J1004 -> J12", ha="left", va="center", fontsize=7.3, fontweight="bold", color=RED)
    wire(ax, [(4.40, 5.65), (4.40, 4.80)], color=CHARCOAL, lw=2.2)
    ax.text(4.30, 5.23, "BM20\nGND", ha="right", va="center", fontsize=7.1, fontweight="bold", color=CHARCOAL)

    # Earthed external peripherals on right
    periphs = [
        (7.55, "PC / Laptop", "USB (KV260) or\nEthernet (J1201)", 7.95),
        (5.25, "Antenna Mast", "RF coax to J961\n(49.7% VHF CM share)", 5.95),
        (2.95, "DisplayPort Monitor", "DP cable to KV260", 3.60),
    ]
    for y0, title, sub, wire_y in periphs:
        rbox(ax, 7.72, y0, 1.92, 1.25, PSU_FILL, PSU_EDGE, lw=1.4, r=0.12)
        ax.text(8.68, y0 + 0.92, title, ha="center", va="center", fontsize=8.7, fontweight="bold", color=INK)
        ax.text(8.68, y0 + 0.42, sub, ha="center", va="center", fontsize=6.95, color=MUTED, linespacing=1.12)
        gnd_symbol(ax, 9.25, y0, color=EARTH, scale=0.75)
        ax.text(8.98, y0 - 0.16, "PE earth", ha="right", va="top", fontsize=6.8, fontweight="bold", color=EARTH)
        wire(ax, [(6.30, wire_y), (7.72, wire_y)], color=CHARCOAL, lw=1.8)
        ferrite_clamp(ax, 7.01, wire_y, label="Ferrite clamp")

    # Honest limit & numbers box (padded text stays strictly inside borders)
    rbox(ax, 0.38, 0.36, 9.26, 1.95, NOTE_FILL, NOTE_EDGE, lw=1.3, r=0.12)
    ax.text(0.58, 2.12, "Honest performance and earth-loop limits (docs/sim/cm_noise.json & ground_offset.json):",
            fontsize=8.2, fontweight="bold", color=INK, va="top")
    ax.text(0.58, 1.78,
            "- L1004 insertion loss on the combined CM loop: 2.9 dB at 65 kHz, 3.7 dB at 100 kHz, 4.8 dB at 1 MHz, 9.5 dB at 100 MHz.\n"
            "- 50 Hz Y-cap leakage (230 V / 2.2 nF [E], 159 uA rms): |Z_L1004| = 4.05 mOhm -> 0.08 uV across the board ground plane.\n"
            "- L1004 does NOT interrupt earth loops between a 3-prong brick and earthed PC, monitor or coax shields;\n"
            "  fit clip-on ferrites on those cables or use a 2-prong (Class II) wall adapter.",
            fontsize=7.25, color=MUTED, va="top", linespacing=1.26)


def main():
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16.5, 7.8), dpi=180, facecolor=BG_CANVAS)
    fig.subplots_adjust(left=0.012, right=0.988, top=0.905, bottom=0.02, wspace=0.025)
    fig.suptitle(
        "Single Power Entry and Grounding: Vehicle vs. Home Installation",
        fontsize=14.0, fontweight="bold", color=INK, y=0.968,
    )
    fig.text(
        0.5, 0.928,
        "KV260 fed strictly from adapter J1004 -> J12; both boards share one return path through L1004 to J1001",
        ha="center", fontsize=9.5, color=MUTED,
    )

    draw_car_panel(ax1)
    draw_home_panel(ax2)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    fig.savefig(OUT, facecolor=BG_CANVAS, dpi=180)
    plt.close(fig)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
