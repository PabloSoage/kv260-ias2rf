"""Generate annotated 4K heatsink callout render and 2D mechanical clearance blueprint (PNG + SVG)."""
import json
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
from matplotlib.patches import FancyBboxPatch, Rectangle

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WORK_MECH = os.path.join(ROOT, "_work", "mech")
IMG_DIR = os.path.join(ROOT, "docs", "img")
HR_REN = os.path.join(ROOT, "docs", "img", "highres", "renders")
CACHE_4K = os.path.join(ROOT, "_work", "mech", "cache", "renders4k")


def annotate_render():
    clean_p = os.path.join(CACHE_4K, "board_heatsinks_clean_4k.png")
    pts_p = os.path.join(WORK_MECH, "hs_screen_pts.json")
    if not os.path.isfile(clean_p) or not os.path.isfile(pts_p):
        print("Skipping callout annotation (clean render not present yet).")
        return
    img = mpimg.imread(clean_p)
    h, w = img.shape[0], img.shape[1]
    pts = json.load(open(pts_p, encoding="utf-8"))

    fig = plt.figure(figsize=(19.2, 10.8), dpi=200)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.imshow(img)
    ax.set_xlim(0, w)
    ax.set_ylim(h, 0)
    ax.axis("off")

    callouts = [
        ("HS1_U501",  (0.03, 0.22), "HS1: U501 (AD9484 ADC, 1.05 W)\n14 × 14 × 8.5 mm Black Anodized Al\nClearance to Fan: 1.9 mm", "#94A3B8"),
        ("HS2_U401",  (0.03, 0.84), "HS2: U401 (ADCLK948 Fanout, 0.95 W)\n9 × 7 × 8 mm (-1 mm Y Shift)", "#60A5FA"),
        ("GAP_4MM",   (0.27, 0.90), "4.0 mm Thermal Isolation Air Gap\n(Prevents U401 Heat Transfer to Y401)", "#38BDF8"),
        ("HS3_Y401",  (0.55, 0.87), "HS3: Y401 (Si549 VCXO, 0.50 W)\n9 × 7 × 8 mm (+1 mm Y Shift, Tj ≤ 125 °C)", "#60A5FA"),
        ("HS4_U1101", (0.27, 0.11), "HS4: U1101 (XC7A50T FPGA, 0.73 W typ)\n14 × 14 × 5 mm Optional Low-Profile Cu/Al", "#F59E0B"),
        ("FAN_50MM",  (0.51, 0.11), "Enclosure v2 Fan Envelope (Wireframe)\n50 × 50 × 15 mm OD5015 @ (-40, +14) mm, z=13.75 mm", "#22D3EE"),
        ("HS5_K26",   (0.74, 0.12), "HS5: K26 SOM OEM Heatsink + Fan\n68 × 58 × 18 mm (9.0 W PS+PL Budget)", "#CBD5E1"),
    ]

    for key, (tx, ty), text, ec in callouts:
        u, v = pts[key]
        u = max(0.02, min(0.98, u))
        v = max(0.02, min(0.98, v))
        px, py = u * w, v * h
        ax.annotate(
            text, xy=(px, py), xytext=(tx * w, ty * h),
            fontsize=10.2, fontweight="bold", color="#E6EDF3",
            bbox=dict(boxstyle="round,pad=0.38", fc="#161B22", ec=ec, lw=1.6, alpha=0.92),
            arrowprops=dict(arrowstyle="-|>,head_width=0.5,head_length=0.8", color=ec, lw=2.2, shrinkA=4, shrinkB=4),
            ha="left", va="center", clip_on=True,
        )

    out_4k = os.path.join(CACHE_4K, "board_heatsinks_4k.png")
    out_web = os.path.join(IMG_DIR, "board_heatsinks.jpg")
    fig.savefig(out_4k, dpi=200, facecolor="#161B22")
    fig.savefig(out_web, dpi=115, facecolor="#161B22", pil_kwargs={"quality": 88})
    plt.close(fig)
    print(f"Saved annotated {out_4k} + {out_web}")


def plot_mechanical_blueprint():
    fig, (ax_top, ax_side) = plt.subplots(
        1, 2, figsize=(15.5, 6.8), gridspec_kw={"width_ratios": [1.15, 1.0]}
    )

    # ---- Left: Top-Down Mechanical Plan View (x in [-117, +125] mm, y in [-31, +109] mm) ----
    # Carrier Outline (approximate KV260 carrier 140x119 mm zone in assembly frame)
    ax_top.add_patch(Rectangle((-95, -20), 220, 115, facecolor="#F1F5F9", edgecolor="#94A3B8", lw=1.2, ls="--", label="KV260 Carrier Assembly Zone"))
    # ADAPTER Board outline (verified wbb [-117.0, +24.5] x [-31.0, +109.0] mm -> show RF/Converter section)
    ax_top.add_patch(Rectangle((-90, -16), 114, 96, facecolor="#E2E8F0", edgecolor="#1E293B", lw=1.6, label="KV260-IAS2RF 8-Layer Adapter"))

    # 50x50 mm Overhead Fan Duct Footprint
    ax_top.add_patch(Rectangle((-65, -11), 50, 50, facecolor="#E0F2FE", edgecolor="#0284C7", lw=2.0, ls="-.", alpha=0.55, zorder=2))
    fan_circ = plt.Circle((-40, 14), 23.5, facecolor="none", edgecolor="#0284C7", lw=1.5, ls=":", zorder=2)
    ax_top.add_patch(fan_circ)
    ax_top.text(-40, -14.8, "50×50 mm Impinging Fan Duct (Ø47 mm Bore)\nCenter (-40.0, +14.0) mm", ha="center", va="bottom",
                fontsize=7.3, fontweight="bold", color="#0369A1",
                bbox=dict(boxstyle="round,pad=0.18", fc="white", ec="#0284C7", lw=0.7, alpha=0.9))

    # Package footprints & Heatsinks
    packages = [
        ("U501 AD9484",   -51.8, 10.55,  8.0,  8.0, "#CBD5E1"),
        ("U401 ADCLK948", -34.9, -0.20,  5.0,  5.0, "#CBD5E1"),
        ("Y401 Si549",    -35.0,  8.80,  5.0,  7.0, "#CBD5E1"),
        ("U1101 XC7A50T", -42.75, 40.0, 17.0, 17.0, "#CBD5E1"),
    ]
    for lbl, cx, cy, pw, ph, col in packages:
        ax_top.add_patch(Rectangle((cx - pw / 2, cy - ph / 2), pw, ph, facecolor=col, edgecolor="#475569", lw=0.8, zorder=3))

    heatsinks = [
        ("HS1\n14×14",     -51.8,  10.55, 14.0, 14.0, "#1E293B", "white"),
        ("HS2\n9×7",       -34.9,  -1.20,  9.0,  7.0, "#1D4ED8", "white"),
        ("HS3\n9×7",       -35.0,   9.80,  9.0,  7.0, "#1D4ED8", "white"),
        ("HS4\n14×14",     -42.75, 40.0,  14.0, 14.0, "#D97706", "white"),
        ("HS5: K26 OEM Finned Heatsink\n68 × 58 × 18 mm (+54 mm Fan)\n9.0 W PS+PL Budget", 86.1, 47.0, 68.0, 58.0, "#334155", "white"),
    ]
    for lbl, cx, cy, w, h, fc, tc in heatsinks:
        ax_top.add_patch(Rectangle((cx - w / 2, cy - h / 2), w, h, facecolor=fc, edgecolor="#0F172A", lw=1.2, alpha=0.88, zorder=4))
        ax_top.text(cx, cy, lbl, ha="center", va="center", color=tc, fontsize=6.6 if w < 30 else 8.8, fontweight="bold", zorder=5)

    # 4.0 mm air gap callout between HS2 (y_max=+2.3) and HS3 (y_min=+6.3)
    ax_top.annotate("", xy=(-28.5, 6.3), xytext=(-28.5, 2.3),
                    arrowprops=dict(arrowstyle="<->", color="#DC2626", lw=1.8), zorder=6)
    ax_top.annotate("4.0 mm Air Gap\n(No Bridge U401->Y401)", xy=(-28.5, 4.3), xytext=(-14.0, 14.5),
                    color="#B91C1C", fontsize=7.6, fontweight="bold", va="center",
                    bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="#DC2626", lw=0.8, alpha=0.92),
                    arrowprops=dict(arrowstyle="-|>", color="#DC2626", lw=1.2), zorder=7)

    ax_top.set_xlim(-96, 126)
    ax_top.set_ylim(-22, 86)
    ax_top.set_aspect("equal", adjustable="box")
    ax_top.set_xlabel("Assembly X Coordinate [mm]")
    ax_top.set_ylabel("Assembly Y Coordinate [mm]")
    ax_top.set_title("Top-Down Plan View: Heatsink Footprints & 4.0 mm Isolation Gap")
    ax_top.grid(True, alpha=0.28)

    # ---- Right: Side Profile Z-Stackup & Airflow Clearances ----
    ax_side.add_patch(Rectangle((-80, 0.0), 185, 2.34, facecolor="#059669", edgecolor="#064E3B", lw=1.0, alpha=0.85, label="ADAPTER 8-Layer PCB (2.34 mm top)"))
    # Enclosures ceiling & fan
    ax_side.add_patch(Rectangle((-80, 32.75), 185, 3.0, facecolor="#475569", edgecolor="#0F172A", lw=1.0))
    ax_side.text(12, 34.25, "Enclosure v2 Lid Inner Roof (z = 32.75..35.75 mm)", ha="center", va="center", color="white", fontsize=8.0, fontweight="bold")
    ax_side.add_patch(Rectangle((-65, 13.75), 50, 15.0, facecolor="#BAE6FD", edgecolor="#0284C7", lw=1.5, ls="--"))
    ax_side.text(-40, 21.3, "50×50×15 mm Fan (OD5015)\nz ∈ [13.75, 28.75] mm", ha="center", va="center", color="#0369A1", fontsize=8.0, fontweight="bold")

    # Heatsink side elevation profiles at clean schematic X positions and exact Z heights [mm]
    ax_side.add_patch(Rectangle((-58.8, 3.34), 14.0, 8.5, facecolor="#1E293B", edgecolor="black"))
    ax_side.text(-51.8, 7.6, "HS1\nU501\nz=11.8", ha="center", va="center", fontsize=7.0, fontweight="bold", color="white")
    ax_side.add_patch(Rectangle((-39.4, 3.15), 9.0, 8.0, facecolor="#1D4ED8", edgecolor="black"))
    ax_side.add_patch(Rectangle((-39.5, 3.99), 9.0, 8.0, facecolor="#3B82F6", edgecolor="black", alpha=0.82))
    ax_side.text(-34.9, 7.6, "HS2/3\nU401\nY401\nz=12.0", ha="center", va="center", fontsize=6.6, fontweight="bold", color="white")
    ax_side.add_patch(Rectangle((-19.0, 3.84), 14.0, 5.0, facecolor="#D97706", edgecolor="black"))
    ax_side.text(-11.5, 9.8, "HS4 (Opt.)\nXC7A50T\nz=8.9 mm", ha="center", va="bottom", fontsize=7.2, fontweight="bold", color="#B45309")
    ax_side.add_patch(Rectangle((28.0, 5.80), 68.0, 18.0, facecolor="#334155", edgecolor="black"))
    ax_side.text(62.0, 14.8, "HS5: K26 SOM OEM Heatsink\n68 × 58 × 18 mm (z_top ≈ 25.1 mm)", ha="center", va="center", color="white", fontsize=8.0, fontweight="bold")

    # Vertical Clearance Arrows
    ax_side.annotate("", xy=(-24.0, 13.75), xytext=(-24.0, 11.99), arrowprops=dict(arrowstyle="<->", color="#0284C7", lw=1.6))
    ax_side.text(-63.0, 15.0, "1.8 mm over HS3, the tallest sink", color="#0369A1", fontsize=7.4, fontweight="bold")
    ax_side.annotate("", xy=(62.0, 32.75), xytext=(62.0, 23.8), arrowprops=dict(arrowstyle="<->", color="#0F766E", lw=1.6))
    ax_side.text(60.0, 28.5, "7.6 mm Roof Clearance", color="#0F766E", fontsize=7.8, fontweight="bold", ha="right")

    ax_side.set_xlim(-72, 102)
    ax_side.set_ylim(-1.0, 38.0)
    ax_side.set_xlabel("Section Coordinate (Adapter Zone Left | K26 SOM Zone Right) [mm]")
    ax_side.set_ylabel("Vertical Height Z Above Bottom Datum [mm]")
    ax_side.set_title("Vertical Z-Stackup & Impinging Fan Plenum Clearances")
    ax_side.grid(True, alpha=0.28)

    fig.suptitle(
        "KV260-IAS2RF Mechanical Heatsink Sizing, Coordinates & Enclosure v2 Clearances",
        fontsize=12.5, fontweight="bold", y=0.99,
    )
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    fig.savefig(os.path.join(IMG_DIR, "heatsink_mechanical_map.png"), dpi=200, bbox_inches="tight", facecolor="white")
    fig.savefig(os.path.join(HR_REN, "heatsink_mechanical_map.svg"), format="svg", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("Saved heatsink_mechanical_map.png + heatsink_mechanical_map.svg")


if __name__ == "__main__":
    os.makedirs(IMG_DIR, exist_ok=True)
    os.makedirs(HR_REN, exist_ok=True)
    annotate_render()
    plot_mechanical_blueprint()
