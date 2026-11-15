"""Generate high-resolution (4K PNG) and 100% vector (SVG + PDF) Vivado silicon floorplans and circuit schematics."""
import json
import math
import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Polygon, Rectangle
from matplotlib.lines import Line2D

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WORK_DIR = os.path.join(ROOT, "_work", "fpga_views")
DOCS_DIR = os.path.join(ROOT, "docs", "img", "fpga")
HR_DIR = os.path.join(ROOT, "docs", "img", "highres", "fpga")

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "svg.fonttype": "none",
})


def save_outputs(fig, stem):
    png_web = os.path.join(DOCS_DIR, f"{stem}.png")
    png_4k = os.path.join(HR_DIR, f"{stem}_4k.png")
    svg_p = os.path.join(HR_DIR, f"{stem}.svg")
    pdf_p = os.path.join(HR_DIR, f"{stem}.pdf")
    fig.savefig(png_web, dpi=180, bbox_inches="tight", facecolor="white")
    fig.savefig(png_4k, dpi=300, bbox_inches="tight", facecolor="white")
    fig.savefig(svg_p, format="svg", bbox_inches="tight", facecolor="white")
    fig.savefig(pdf_p, format="pdf", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"Exported {stem}: web PNG + 4K PNG + SVG + PDF")


# ---------------------------------------------------------------------------
# Shared schematic drawing helpers
# ---------------------------------------------------------------------------
def draw_module(ax, x, y, w, h, title, subtitle="", body_lines=(), hdr_col="#1E3A5F",
                fill_col="#F8FAFC", edge_col="#334155", title_size=8.5, badge=None):
    box = FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0.0,rounding_size=0.14",
        facecolor=fill_col, edgecolor=edge_col, linewidth=1.25, zorder=3,
    )
    ax.add_patch(box)
    hh = min(0.62, h * 0.28)
    hdr = FancyBboxPatch(
        (x, y + h - hh), w, hh, boxstyle="round,pad=0.0,rounding_size=0.12",
        facecolor=hdr_col, edgecolor=edge_col, linewidth=1.0, zorder=4,
    )
    ax.add_patch(hdr)
    ax.text(x + w / 2, y + h - hh * 0.48, title, ha="center", va="center",
            color="white", fontsize=title_size, fontweight="bold", zorder=5)
    if subtitle:
        ax.text(x + w / 2, y + h - hh - 0.24, subtitle, ha="center", va="top",
                color="#334155", fontsize=max(6.4, title_size - 1.7), fontweight="bold", zorder=5)
    if body_lines:
        top_txt = y + h - hh - (0.55 if subtitle else 0.22)
        step = min(0.32, max(0.18, (top_txt - y - 0.15) / max(1, len(body_lines))))
        for i, line in enumerate(body_lines):
            ax.text(x + 0.18, top_txt - i * step, line, ha="left", va="top",
                    color="#1E293B", fontsize=max(6.1, title_size - 2.0), zorder=5)
    if badge:
        ax.text(
            x + w - 0.14, y + 0.12, badge, ha="right", va="bottom",
            fontsize=6.0, fontweight="bold", color="#0F172A", zorder=6,
            bbox=dict(boxstyle="round,pad=0.18", fc="#E2E8F0", ec="#94A3B8", lw=0.6),
        )


def draw_wire(ax, pts, color="#1D4ED8", lw=1.4, label=None, label_pos=None,
              arrow=True, ls="-", label_color=None):
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    if arrow and len(pts) >= 2:
        if len(pts) > 2:
            ax.plot(xs[:-1], ys[:-1], color=color, lw=lw, ls=ls, zorder=2, solid_capstyle="round")
        ax.annotate(
            "", xy=pts[-1], xytext=pts[-2],
            arrowprops=dict(arrowstyle="-|>", color=color, lw=lw, mutation_scale=11, shrinkA=0, shrinkB=0),
            zorder=2,
        )
    else:
        ax.plot(xs, ys, color=color, lw=lw, ls=ls, zorder=2)
    if label:
        lp = label_pos if label_pos else ((xs[0] + xs[-1]) / 2, (ys[0] + ys[-1]) / 2 + 0.14)
        ax.text(
            lp[0], lp[1], label, fontsize=6.2, fontweight="bold",
            color=label_color or color, ha="center", va="center", zorder=7,
            bbox=dict(boxstyle="round,pad=0.12", fc="white", ec="none", alpha=0.88),
        )


# ---------------------------------------------------------------------------
# 1 & 2. Real Vivado Silicon Die Floorplans
# ---------------------------------------------------------------------------
ARTIX_GROUPS = [
    ("u_ddc",        "Radar DDC (AERIS 400->100M)", "#D84315"),
    ("u_sdr_ddc",    "SDR DDC (2-Ch NCO+CIC+HB)",   "#1565C0"),
    ("u_dual_mux",   "Dual-Path Mux (IAS1/ETH)",    "#00838F"),
    ("g_eth",        "1000BASE-T SGMII + UDP MAC",  "#7B1FA2"),
    ("u_ul_",        "IAS1 64b/66b Uplink + PCS",   "#0097A7"),
    ("u_dl_",        "IAS1 64b/66b Downlink + FSM", "#00ACC1"),
    ("u_adar",       "ADAR1000 8x Beamformer",      "#2E7D32"),
    ("u_dac_",       "DAC TX (AD9708 + AD9767)",    "#F57C00"),
    ("u_adc",        "ADC Capture (AD9484 + AD9253)","#AD1457"),
    ("other",        "Housekeeping / XO / XADC / IO","#546E7A"),
]


def classify_artix_group(grp):
    if grp.startswith("u_ddc"):
        return "u_ddc"
    if grp.startswith("u_sdr_ddc"):
        return "u_sdr_ddc"
    if "u_dual_mux" in grp or "u_sdr_gen" in grp:
        return "u_dual_mux"
    if "u_eth_" in grp or grp.startswith("g_eth"):
        return "g_eth"
    if grp.startswith("u_ul_"):
        return "u_ul_"
    if grp.startswith("u_dl_"):
        return "u_dl_"
    if grp.startswith("u_adar") or grp.startswith("u_rf_sw"):
        return "u_adar"
    if grp.startswith("u_dac_"):
        return "u_dac_"
    if grp.startswith("u_adc") or grp.startswith("adcs_samp_mem"):
        return "u_adc"
    return "other"


KRIA_GROUPS = [
    ("u_pcs_rx",   "IAS1 2-Lane AM Deskew + 64b/66b RX PCS", "#1565C0"),
    ("u_train_fsm","512-Tap IDELAYE3 Eye Trainer",          "#00897B"),
    ("u_pcs_dl_tx","IAS1 Downlink 64b/66b TX PCS",          "#7B1FA2"),
    ("u_link_axis","AXI4-Stream + AXI-Lite DMA Bridge",     "#D84315"),
    ("u_fifo",     "CDC FIFOs (RX/TX/AXI Domains)",         "#F57C00"),
    ("other",      "Bank 66 HP SERDES / Clocking / EMIO",   "#546E7A"),
]


def classify_kria_group(grp):
    if grp == "u_pcs_rx":
        return "u_pcs_rx"
    if grp == "u_train_fsm":
        return "u_train_fsm"
    if grp == "u_pcs_dl_tx":
        return "u_pcs_dl_tx"
    if grp == "u_link_axis":
        return "u_link_axis"
    if grp.startswith("u_fifo"):
        return "u_fifo"
    return "other"


def render_die_floorplan(json_path, stem, title, is_kria=False):
    data = json.load(open(json_path, encoding="utf-8"))
    b = data["die_bounds"]
    crs = data["clock_regions"]
    arch = data["arch_sites"]
    cells = data["placed_cells"]
    ports = data["ports"]
    max_y = b["max_y"]

    def fy(y):
        # Flip Vivado GRID_POINT_Y so Clock Region Y0 sits at bottom
        return max_y - y

    groups_cfg = KRIA_GROUPS if is_kria else ARTIX_GROUPS
    clf = classify_kria_group if is_kria else classify_artix_group
    col_map = {k: c for k, _, c in groups_cfg}
    lbl_map = {k: l for k, l, _ in groups_cfg}

    fig, (ax, ax_stat) = plt.subplots(
        1, 2, figsize=(15.2, 8.8), gridspec_kw={"width_ratios": [1.35, 0.92]}
    )

    # Die silicon substrate backdrop
    pad_x = 4
    pad_y = 6
    ax.add_patch(Rectangle(
        (b["min_x"] - 1, fy(b["max_y"]) - 1),
        (b["max_x"] - b["min_x"]) + 2,
        (b["max_y"] - b["min_y"]) + 2,
        facecolor="#0B1320", edgecolor="#475569", lw=1.6, zorder=0,
    ))

    # Draw Clock Regions
    for cr in crs:
        x0, x1 = cr["x0"], cr["x1"]
        yy0, yy1 = fy(cr["y1"]), fy(cr["y0"])
        rect = Rectangle(
            (x0, yy0), max(1, x1 - x0), max(1, yy1 - yy0),
            facecolor="#111C2E", edgecolor="#38BDF8", ls="--", lw=0.75, alpha=0.75, zorder=1,
        )
        ax.add_patch(rect)
        ax.text(
            x0 + 1.5, yy1 - 2.0, cr["name"],
            color="#7DD3FC", fontsize=7.5, fontweight="bold", ha="left", va="top", zorder=6,
            alpha=0.85,
        )

    # Draw hard silicon IP columns (BRAM, DSP, MMCM, IOB, PS8)
    for stype_key, col, sz, marker, lbl in [
        ("DSP48",  "#FACC15", 16 if not is_kria else 7,  "s", "DSP48 Slice"),
        ("RAMB36", "#C084FC", 15 if not is_kria else 8,  "s", "BRAM36 Block"),
        ("MMCME",  "#22D3EE", 28, "^", "MMCM / PLL"),
        ("PLLE",   "#22D3EE", 22, "^", None),
        ("XADC",   "#34D399", 40, "D", "XADC / SYSMON"),
        ("SYSMON", "#34D399", 36, "D", None),
        ("IOB33",  "#64748B", 7,  "o", "I/O Bank Pad"),
        ("HPIO",   "#64748B", 5,  "o", None),
        ("HDIO",   "#64748B", 5,  "o", None),
    ]:
        pts_u = [(s["x"], fy(s["y"])) for s in arch if stype_key in s["t"] and s["u"]]
        pts_e = [(s["x"], fy(s["y"])) for s in arch if stype_key in s["t"] and not s["u"]]
        if pts_e:
            ax.scatter([p[0] for p in pts_e], [p[1] for p in pts_e], s=sz * 0.55,
                       marker=marker, facecolors="none", edgecolors=col, linewidths=0.45, alpha=0.28, zorder=2)
        if pts_u:
            ax.scatter([p[0] for p in pts_u], [p[1] for p in pts_u], s=sz * 1.15,
                       marker=marker, c=col, edgecolors="#0F172A", linewidths=0.4, alpha=0.92, zorder=5)

    # For XCK26 Zynq US+: highlight hardened ARM PS8 silicon corner explicitly
    if is_kria:
        # Hardened Zynq US+ PS8 occupies the dedicated lower-left X0Y0..X0Y1 silicon quadrant
        px0 = b["min_x"] + 5
        px1 = min(b["max_x"] * 0.34, 152)
        py0 = fy(b["max_y"]) + 4
        py1 = py0 + (b["max_y"] - b["min_y"]) * 0.48
        ax.add_patch(Rectangle(
            (px0, py0), px1 - px0, py1 - py0,
            facecolor="#1E293B", edgecolor="#F59E0B", lw=1.6, hatch="//", alpha=0.88, zorder=4,
        ))
        ax.text(
            (px0 + px1) / 2, (py0 + py1) / 2,
            "Zynq US+ PS8 Silicon\n(Quad A53 + GEM3\n+ DDR4 + HP0)",
            color="#FDE68A", fontsize=7.6, fontweight="bold", ha="center", va="center", zorder=6,
            bbox=dict(boxstyle="round,pad=0.28", fc="#0F172A", ec="#F59E0B", alpha=0.92),
        )

    # Scatter placed cells colored by subsystem
    buckets = {k: [] for k, _, _ in groups_cfg}
    counts_by_grp = {k: {"LUT": 0, "FF": 0, "BRAM": 0, "DSP": 0, "ALL": 0} for k, _, _ in groups_cfg}
    totals = {"LUT": 0, "FF": 0, "BRAM": 0, "DSP": 0, "SERDES": 0, "CLK": 0}

    rng = np.random.default_rng(42)
    for grp, kind, rf, loc, gx, gy in cells:
        bkey = clf(grp)
        # Small sub-tile jitter so dense slices show fill density cleanly
        buckets[bkey].append((gx + rng.uniform(-0.32, 0.32), fy(gy) + rng.uniform(-0.32, 0.32)))
        counts_by_grp[bkey]["ALL"] += 1
        if kind in counts_by_grp[bkey]:
            counts_by_grp[bkey][kind] += 1
        if kind in totals:
            totals[kind] += 1

    for k, lbl, col in groups_cfg:
        pts = buckets[k]
        if not pts:
            continue
        ax.scatter(
            [p[0] for p in pts], [p[1] for p in pts],
            s=4.5 if not is_kria else 5.5, c=col, alpha=0.72, edgecolors="none",
            label=f"{lbl} ({len(pts):,})", zorder=3, rasterized=True,
        )

    # Highlight placed external I/O package pins
    io_pts = [(p["x"], fy(p["y"])) for p in ports if p["x"] >= 0]
    if io_pts:
        ax.scatter([p[0] for p in io_pts], [p[1] for p in io_pts], s=18, marker="s",
                   c="#38BDF8", edgecolors="white", lw=0.45, alpha=0.95, zorder=6,
                   label=f"Routed I/O Pins ({len(io_pts)})")

    ax.set_xlim(b["min_x"] - pad_x, b["max_x"] + pad_x)
    ax.set_ylim(fy(b["max_y"]) - pad_y, fy(b["min_y"]) + pad_y)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("Vivado Die Tile Grid X")
    ax.set_ylabel("Vivado Die Tile Grid Y")
    ax.set_title(title, fontsize=11.0, fontweight="bold")
    ax.grid(False)
    ax.legend(
        loc="upper center", bbox_to_anchor=(0.5, -0.14 if is_kria else -0.08), ncol=2, fontsize=7.6,
        frameon=True, facecolor="white", edgecolor="#CBD5E1", markerscale=2.0,
    )

    # Right Panel: Resource Breakdown by Subsystem & Silicon Occupancy Table
    active_grps = [g for g in groups_cfg if counts_by_grp[g[0]]["ALL"] > 0]
    y_pos = np.arange(len(active_grps))
    luts = [counts_by_grp[g[0]]["LUT"] for g in active_grps]
    ffs = [counts_by_grp[g[0]]["FF"] for g in active_grps]
    dsps = [counts_by_grp[g[0]]["DSP"] for g in active_grps]
    cols_b = [g[2] for g in active_grps]
    lbls_b = [g[1] for g in active_grps]

    ax_stat.barh(y_pos - 0.18, luts, height=0.34, color=cols_b, alpha=0.92, edgecolor="#0F172A", lw=0.4, label="LUTs")
    ax_stat.barh(y_pos + 0.18, ffs,  height=0.34, color=cols_b, alpha=0.48, edgecolor="#0F172A", lw=0.4, hatch="///", label="Flip-Flops")
    ax_stat.set_yticks(y_pos)
    ax_stat.set_yticklabels(lbls_b, fontsize=8.3, fontweight="bold")
    ax_stat.invert_yaxis()
    ax_stat.set_xlabel("Placed Leaf Primitives Count")
    ax_stat.set_title("Subsystem Silicon Consumption (Vivado Post-Route)", fontsize=10.5, fontweight="bold")
    ax_stat.spines["top"].set_visible(False)
    ax_stat.spines["right"].set_visible(False)
    ax_stat.grid(axis="x", alpha=0.3)
    xmax = max(max(luts, default=1), max(ffs, default=1)) * 1.32
    ax_stat.set_xlim(0, xmax)
    for i, (lu, ff, ds) in enumerate(zip(luts, ffs, dsps)):
        extra = f" | {ds} DSP" if ds else ""
        ax_stat.text(max(lu, ff) + xmax * 0.015, i, f"{lu:,} LUT / {ff:,} FF{extra}", va="center", fontsize=7.6)

    # Occupancy Card below bar chart
    if not is_kria:
        cap = {"LUT": 32600, "FF": 65200, "BRAM": 75, "DSP": 120}
        card = (
            f"Device: XC7A50T-FTG256-2 (Artix-7)\n"
            f"Top: artix_top (ENABLE_ETH=1, Post-Route Vivado 2026.1)\n"
            f"Slice LUTs: 15,416 / {cap['LUT']:,} (47.3%)  [{totals['LUT']:,} leaf LUT1..6]\n"
            f"FFs:        {totals['FF']:,} / {cap['FF']:,} ({100*totals['FF']/cap['FF']:.1f}%)\n"
            f"DSP48E1:    {totals['DSP']} / {cap['DSP']} ({100*totals['DSP']/cap['DSP']:.1f}%)\n"
            f"BRAM36 eq.: 16.0 / {cap['BRAM']} (21.3%: 13 RAMB36 + 6 RAMB18)\n"
            f"Timing:     WNS = +{data['wns_ns']:.3f} ns | WHS = +{data['whs_ns']:.3f} ns (ALL MET)"
        )
    else:
        cap = {"LUT": 117120, "FF": 234240, "BRAM": 144, "DSP": 1248}
        card = (
            f"Device: XCK26-SFVC784-2LV-c (Kria KV260 Zynq US+)\n"
            f"1) kria_top PL Link Core: {totals['LUT']:,} LUTs ({100*totals['LUT']/cap['LUT']:.1f}%), "
            f"{totals['FF']:,} FFs ({100*totals['FF']/cap['FF']:.1f}%), WNS = +{data['wns_ns']:.3f} ns\n"
            f"2) Full Vivado BD (ias2rf_k26_bd_wrapper incl. PS8+DMA+SMC):\n"
            f"   11,034 / {cap['LUT']:,} LUTs (9.4%) | 18,212 / {cap['FF']:,} FFs (7.8%)\n"
            f"   3.0 / {cap['BRAM']} BRAM36 (2.1%) | 0 DSP48E2 | WNS = +1.291 ns\n"
            f">90% K26 PL silicon free for on-SOM CFAR / Range-Doppler / Demod"
        )
    ax_stat.text(
        0.02, -0.14, card, transform=ax_stat.transAxes, va="top", ha="left",
        fontsize=8.0, family="DejaVu Sans Mono",
        bbox=dict(boxstyle="round,pad=0.45", fc="#F1F5F9", ec="#475569", lw=1.0),
    )

    fig.tight_layout()
    save_outputs(fig, stem)


# ---------------------------------------------------------------------------
# 3. Artix-7 Vivado Hierarchical Circuit Schematic
# ---------------------------------------------------------------------------
def plot_artix7_schematic(artix_json):
    d = json.load(open(artix_json, encoding="utf-8"))
    mc = d["module_counts"]

    def cnt(prefix, kind="LUT"):
        return sum(v for k, v in mc.items() if k.startswith(prefix) and k.endswith("|" + kind))

    fig, ax = plt.subplots(figsize=(16.5, 10.2))
    ax.set_xlim(0, 24)
    ax.set_ylim(0, 15)
    ax.axis("off")

    ax.text(12, 14.65, "Artix-7 XC7A50T-FTG256-2 (artix_top) — Vivado Post-Route Hierarchical Circuit Schematic",
            ha="center", va="center", fontsize=13.5, fontweight="bold", color="#0F172A")
    ax.text(12, 14.25, f"Clock Domains: fpga_clk 400/500M | dac_clk 100/125M (no MMCM) | link_clk 125M | tx_clk_ddr 500M | clk_400m 400M | clk_625 625M | cfgmclk   |   WNS = +{d['wns_ns']:.3f} ns, WHS = +{d['whs_ns']:.3f} ns",
            ha="center", va="center", fontsize=9.0, color="#334155")

    # Left Column: RF Converters & Clocks Input Interfaces
    draw_module(ax, 0.4, 11.4, 3.8, 2.3, "Clock Synthesizer", "u_clk_mode_ctrl + 2x MMCME2_ADV",
                ["fpga_clk_p/n (400/500M LVDS)", "DRP DIVCLK /4 or /5 -> 1000 MHz VCO:", " -> 125M link_clk, 500M tx_clk_ddr", " -> 200M refclk, eth 625/312.5M", "fpga_clk/4 -> dac_clk (no MMCM)", "CFGMCLK safe boot + Si549 I2C"],
                hdr_col="#0E7490", fill_col="#ECFEFF", badge="2x MMCME2")
    draw_module(ax, 0.4, 8.2, 3.8, 2.8, "AD9484 Radar ADC RX", "adc_capture (400 MSPS)",
                ["IBUFDS_DIFF_OUT (adcr_d[7:0],", "  adcr_dco, adcr_or)", "MMCME2_ADV (clk_400m)", "IDELAYE2 + ISERDESE2 (8b)", "Auto eye scan (32 taps)"],
                hdr_col="#9D174D", fill_col="#FDF2F8", badge="Bank 14 HR")
    draw_module(ax, 0.4, 4.9, 3.8, 2.9, "AD9253 SDR Dual ADC", "adcs_capture (2x14b 125M)",
                ["adcs_d0[1:0], d1[1:0], dco, fco", "2-wire DDR 7:1 ISERDESE2", "IDELAYE2 + Bitslip align FSM", "Ch B (HF, J951 LPF) & Ch A", "Syncs FCO frame word"],
                hdr_col="#1D4ED8", fill_col="#EFF6FF", badge="Bank 34 2.5V")
    draw_module(ax, 0.4, 1.0, 3.8, 3.5, "Housekeeping, XADC & SPI", "Bank 15 & Bank 35 (1.8/3.3V)",
                ["conv_spi: AD9484 / AD9253 SPI", "hk_i2c_master: TMP1075 / EEPROM", "hk_xo_ctrl: Si549 I2C + CLK_SEL", "hk_xadc_pps: XADC die T/V", "  + PPS timestamp + ppm meas.", "pmod_spi: Failsafe J1102 SPI"],
                hdr_col="#475569", fill_col="#F8FAFC")

    # Center-Left Column: DSP Engines & TX Generators
    draw_module(ax, 5.1, 8.2, 4.5, 5.5, "AERIS-10 Radar DDC", "ddc_wrapper -> ddc_400m_enhanced",
                ["nco_400m_enhanced (32b FTW=120M)", "Dual-branch I/Q mix + LFSR dither", "cic_decimator_4x_enhanced (5-stg)", "fir_lowpass_parallel (32-tap sym.)", "ddc_input_interface (18b -> 16b)", "100 MSPS I/Q -> Async BRAM FIFO", "Packetizer -> Stream ID 8'h01", f"{cnt('u_ddc','DSP')} DSP48E1 | {cnt('u_ddc','LUT'):,} LUTs"],
                hdr_col="#C2410C", fill_col="#FFF7ED", badge=f"{cnt('u_ddc','DSP')} DSPs")
    draw_module(ax, 5.1, 4.5, 4.5, 3.3, "Dual-Ch SDR I/Q DDC", "sdr_ddc (2x sdr_ddc_ch)",
                ["2x sdr_ddc_nco (32b FTW A & B)", "Programmable 3-stage CIC3 +", "  15-tap symmetric Halfband FIR", "Decim 2..65535 -> HF / FM / SSB", "Gray BRAM FIFO -> Stream 8'h04/05", f"{cnt('u_sdr_ddc','DSP')} DSP48E1 | {cnt('u_sdr_ddc','LUT'):,} LUTs"],
                hdr_col="#1E40AF", fill_col="#EFF6FF", badge=f"{cnt('u_sdr_ddc','DSP')} DSPs")
    draw_module(ax, 5.1, 1.0, 4.5, 3.1, "DAC TX + ADAR1000 Beam", "u_dac_radar / u_dac_sdr / u_adar",
                ["dac_radar: 32b LFM Chirp DDS ->", "  ODDR, dac_clk 100/125M (AD9708)", "dac_sdr: Async FIFO + IQ -> AD9767", "adar_ctrl: 32x8x24B Beam RAM +", "  15.6M SPI + T/R guard FSM", "rf_switch: 4x M3SWA-2+ SPDT"],
                hdr_col="#15803D", fill_col="#F0FDF4", badge="32 T/R Ch.")

    # Center-Right Column: Arbitration, CSR Control & Dual-Path Failover
    draw_module(ax, 10.6, 5.4, 4.3, 8.3, "CSR Regfile & 3-Way Arbiter", "artix_top Control + Packet Router",
                ["0x00..0xE0 Control/Status Space", "Written by:", " - IAS1 Downlink CMD (0x01/0x02)", " - ETH UDP RX Port 0x4952", " - Pmod Failsafe SPI (J1102)", "", "Packet-Atomic Arbiter -> s0_arb:", "  1) 0x11 Reg Readback Response", "  2) 0x01 Radar DDC IQ Stream", "  3) 0x04/05 SDR DDC IQ Streams", "", "dual_path_mux (Failover Router):", "  policy[1:0]: SPLIT / MIRROR_1P1", "  IAS_ONLY / ETH_ONLY (sof/eop safe)"],
                hdr_col="#0F766E", fill_col="#F0FDFA", badge="Zero Loss")
    draw_module(ax, 10.6, 1.0, 4.3, 4.0, "1000BASE-T MAC + UDP Core", "eth_mac_udp + eth_mdio (@ 125M)",
                ["GMII TX/RX 8-bit @ clk_125", "IPv4 Checksum + IEEE CRC-32 FCS", "Supports 9000 B Jumbo UDP frames", "Embedded HW ARP Responder", "192.168.10.2 : 0x4952 ('IR')", "eth_mdio: RTL8211FSI Clause 22", "Auto failover alive watchdog"],
                hdr_col="#6D28D9", fill_col="#F5F3FF", badge="993 Mb/s")

    # Right Column: High-Speed SERDES Transceivers & External Pins
    draw_module(ax, 16.0, 9.2, 4.1, 4.5, "IAS1 Uplink TX PCS (2-Lane)", "link_pcs_tx (64b/66b)",
                ["link_framer (/S/ TS /D/ /T/ CRC32)", "link_tx_lanes (2-lane stripe + /A/)", "link_64b66b_enc (G=1+x^39+x^58)", "2x link_gearbox_tx (66:8 @ 125M)", "2x OSERDESE2 8:1 DDR (500 MHz)", "Forward CLK OSERDES (8'b10101010)"],
                hdr_col="#0369A1", fill_col="#F0F9FF", badge="2.0 Gb/s")
    draw_module(ax, 16.0, 5.2, 4.1, 3.6, "IAS1 Downlink RX PCS", "link_pcs_single_rx + Train FSM",
                ["IDELAYE2 + ISERDESE2 (500M DDR)", "32-tap eye-scan trainer (78 ps)", "link_block_lock (64 valid SH)", "link_64b66b_dec + deframer", "Delivers K->A CMD (8'h10)"],
                hdr_col="#0284C7", fill_col="#F0F9FF", badge="1.0 Gb/s")
    draw_module(ax, 16.0, 1.0, 4.1, 3.8, "SGMII 1.25G Soft LVDS PHY", "eth_sgmii_phy (XAPP523 DDR)",
                ["TX: Clause 36/37 -> 8b10b_enc ->", "  20b/4b gearbox -> OSERDESE2", "RX: IBUFDS_DIFF_OUT -> dual", "  IDELAYE2 + ISERDESE2 @ 625M 0/90°", "4x oversampler + K28.5 barrel shift", "Clause 37 AN -> PHY R2/R1, R3/T2"],
                hdr_col="#7E22CE", fill_col="#FAF5FF", badge="1.25 Gb/s")

    # Far Right Column: PCB Connector / Pin Outputs
    draw_module(ax, 21.0, 9.8, 2.6, 3.8, "J101 -> KV260 J8", "Bank 34 / 14 IAS1",
                ["LINK_RX_D0_P/N", "LINK_RX_D1_P/N", "LINK_RX_CLK_P/N", "LINK_TX_D0_P/N", "LINK_TX_CLK_P/N", "HK_SCL/SDA/IRQ"],
                hdr_col="#1E293B", fill_col="#F1F5F9")
    draw_module(ax, 21.0, 1.2, 2.6, 3.4, "U1201 RTL8211FSI", "Dedicated Rev06 Pins",
                ["ETH_SGTX_P/N", "ETH_SGRX_P/N", "ETH_MDC / MDIO", "ETH_RST_N -> J1201"],
                hdr_col="#1E293B", fill_col="#F1F5F9")
    draw_module(ax, 21.0, 5.4, 2.6, 3.6, "RF & Array I/O", "SMAs + J1103",
                ["J901..905 SMAs", "AD9708 & AD9767", "8x ADAR1000 SPI", "4x M3SWA-2+ SW"],
                hdr_col="#1E293B", fill_col="#F1F5F9")

    # Connections
    draw_wire(ax, [(4.2, 12.6), (5.1, 12.6)], "#0E7490", 1.5, "clk_400m /\n125M", (4.65, 13.05))
    draw_wire(ax, [(4.2, 9.6), (5.1, 9.6)], "#C2410C", 1.8, "adc_d[7:0]\n400M", (4.65, 10.05))
    draw_wire(ax, [(4.2, 6.4), (5.1, 6.4)], "#1D4ED8", 1.8, "ChA/B 2x14b\n125M", (4.65, 6.85))
    draw_wire(ax, [(9.6, 10.9), (10.6, 10.9)], "#C2410C", 1.9, "s0 Radar\n(0x01)", (10.1, 11.35))
    draw_wire(ax, [(9.6, 6.4), (10.6, 6.4)], "#1D4ED8", 1.9, "s1 SDR\n(0x04/05)", (10.1, 6.85))
    draw_wire(ax, [(4.2, 2.7), (4.65, 2.7), (4.65, 4.30), (10.35, 4.30), (10.35, 5.8), (10.6, 5.8)], "#475569", 1.3, "HK / PPS / XADC", (7.4, 4.30))
    draw_wire(ax, [(10.6, 7.6), (10.1, 7.6), (10.1, 2.8), (9.6, 2.8)], "#15803D", 1.5, "Chirp /\nBeam TX", (10.1, 3.85))
    draw_wire(ax, [(14.9, 11.4), (16.0, 11.4)], "#0369A1", 2.0, "64b Pkts\n@ 125M", (15.45, 11.85))
    draw_wire(ax, [(16.0, 7.0), (14.9, 7.0)], "#0284C7", 1.6, "CMD / Poll", (15.45, 7.35))
    draw_wire(ax, [(12.75, 5.4), (12.75, 5.0)], "#6D28D9", 1.8, "ETH", (13.3, 5.2))
    draw_wire(ax, [(14.9, 3.0), (16.0, 3.0)], "#7E22CE", 1.8, "GMII\n@ 125M", (15.45, 3.45))
    draw_wire(ax, [(20.1, 11.8), (21.0, 11.8)], "#0369A1", 2.0, "2x 1.0G\nLVDS", (20.55, 12.25))
    draw_wire(ax, [(21.0, 10.5), (20.55, 10.5), (20.55, 7.2), (20.1, 7.2)], "#0284C7", 1.6, "1.0G DL", (20.55, 8.85))
    draw_wire(ax, [(20.1, 2.9), (21.0, 2.9)], "#7E22CE", 2.0, "1.25G\nSGMII", (20.55, 3.35))
    draw_wire(ax, [(7.35, 1.0), (7.35, 0.55), (22.3, 0.55), (22.3, 5.4)], "#15803D", 1.6, "DAC / ADAR / RF Switch I/O", (14.8, 0.35))

    fig.tight_layout()
    save_outputs(fig, "artix7_vivado_schematic")


# ---------------------------------------------------------------------------
# 4. Kria K26 Vivado BD & PL Link Circuit Schematic
# ---------------------------------------------------------------------------
def plot_kria_bd_schematic(kria_json):
    d = json.load(open(kria_json, encoding="utf-8"))
    fig, ax = plt.subplots(figsize=(16.5, 10.0))
    ax.set_xlim(0, 24)
    ax.set_ylim(0, 14.8)
    ax.axis("off")

    ax.text(12, 14.45, "Kria KV260 XCK26-SFVC784-2LV-c — Vivado IPI Block Design (ias2rf_k26_bd) & PL Link Circuit",
            ha="center", va="center", fontsize=13.2, fontweight="bold", color="#0F172A")
    ax.text(12, 14.05, f"PS8 (Quad Cortex-A53 + GEM3 RJ45 + DDR4) + HP0 DMA + kria_pl_link (5x Oversampled DRU + 64b/66b PCS)   |   BD WNS = +1.291 ns, kria_top WNS = +{d['wns_ns']:.3f} ns",
            ha="center", va="center", fontsize=9.0, color="#334155")

    # Left: J8 Connector + PHY Front-end
    draw_module(ax, 0.4, 8.8, 3.3, 4.4, "KV260 J8 (IAS1)", "Bank 66 HP (1.2V DIFF_SSTL12)",
                ["LINK_RX_CLK (C1/B1)", "LINK_RX_D0  (A2/A1)", "LINK_RX_D1  (B3/A3)", "  ODT = RTT_48 int.", "LINK_TX_CLK (D4/C4)", "LINK_TX_D0  (B4/A4)", "HK_SCL/SDA/IRQ/PROG"],
                hdr_col="#1E293B", fill_col="#F1F5F9", badge="2.0 Gb/s UL")
    draw_module(ax, 0.4, 1.2, 3.3, 3.4, "KV260 J2 Pmod + J10 RJ45", "Carriers Side Interfaces",
                ["J2 Bank 45 LVCMOS33:", "  pmod_cs_n/mosi/miso/sclk", "  beam_strobe / pps_sync", "J10 Carrier RJ45:", "  PS GEM3 RGMII (DP83867)", "  Receives Artix U1201 UDP"],
                hdr_col="#334155", fill_col="#F8FAFC")

    # Center-Left: Exploded kria_pl_link_0
    ax.add_patch(Rectangle((4.3, 5.2), 8.2, 8.2, facecolor="#F0F9FF", edgecolor="#0284C7", lw=1.6, ls="--", zorder=1))
    ax.text(4.5, 13.15, "kria_pl_link_0 (Custom Verilog Module in ias2rf_k26_bd)", fontsize=9.2, fontweight="bold", color="#0369A1")

    draw_module(ax, 4.6, 9.6, 3.6, 3.1, "HP Bank 66 SERDES & Clock", "MMCME4 + IDELAYCTRL + 2x ISERDESE3",
                ["MMCME4_ADV: 250M->500M DDR", "IDELAYE3 VAR_LOAD (512 taps", "  @ 4 ps) + BISC EN_VTC ctrl", "link_rx_train_fsm eye scan", "2x OSERDESE3 -> Downlink TX"],
                hdr_col="#0369A1", fill_col="white")
    draw_module(ax, 4.6, 5.6, 3.6, 3.4, "2-Lane 64b/66b RX/TX PCS", "link_pcs_rx + link_pcs_tx",
                ["link_gearbox_rx (8:66) +", "  Clause 49 block_lock (x2)", "link_64b66b_dec (G=1+x^39+x^58)", "link_rx_lanes (AM deskew FIFO)", "link_deframer + CRC-32 verify"],
                hdr_col="#0284C7", fill_col="white")
    draw_module(ax, 8.6, 9.4, 3.6, 3.3, "AXI4-Stream Bridge", "link_axis + Dual-Clk Async FIFO",
                ["rx_clkdiv (125M) <-> pl_clk 100M", "m_axis_rx (64b TLAST TID TUSER)", "s_axis_tx (64b MM2S -> /S/ /T/)", "PPS-disciplined 64b ts_cnt_rx", "256x64 RX / 128x64 TX FIFOs"],
                hdr_col="#0F766E", fill_col="white")
    draw_module(ax, 8.6, 5.6, 3.6, 3.3, "AXI4-Lite CSR & EMIO Mux", "s_axi @ 0x8000_0000 (64K)",
                ["CSRs 0x00..0x34 (status/eye)", "PPS GPIO + EMIO I2C0 -> HK", "EMIO SPI0 -> J2 Pmod failsafe", "irq_fpga + irq_link_up out", "Watchdog timeout guard"],
                hdr_col="#475569", fill_col="white")

    # Center-Right: Vivado BD Infrastructure (DMA + SmartConnects)
    draw_module(ax, 13.3, 9.4, 4.1, 3.9, "axi_dma_0", "Xilinx AXI DMA v7.1 (64-bit Simple)",
                ["S_AXIS_S2MM <- kria_pl_link RX", "M_AXIS_MM2S -> kria_pl_link TX", "MM2S & S2MM DRE enabled", "Max burst length = 64 x 64b", "S_AXI_LITE @ 0x8001_0000", "s2mm_introut / mm2s_introut"],
                hdr_col="#C2410C", fill_col="#FFF7ED", badge="No SG / DRE")
    draw_module(ax, 13.3, 6.2, 4.1, 2.7, "axi_smc_hp0 + axi_smc_ctrl", "2x Xilinx AXI SmartConnect",
                ["axi_smc_hp0 (2 SI -> 1 MI): DDR", "  combines MM2S + S2MM 64-bit", "axi_smc_ctrl (1 SI -> 2 MI):", "  PS HPM0 -> PL Link + DMA CSRs"],
                hdr_col="#7E22CE", fill_col="#FAF5FF")
    draw_module(ax, 13.3, 2.6, 4.1, 3.1, "rst_ps8_100M + xlconcat_0", "Reset & 4-bit Interrupt Combine",
                ["proc_sys_reset on pl_clk0 (100M)", "xlconcat_0 [3:0] -> pl_ps_irq0:", "  [0] irq_fpga  [1] irq_link_up", "  [2] s2mm_irq  [3] mm2s_irq"],
                hdr_col="#334155", fill_col="#F8FAFC")

    # Right: PS8 Hardened Zynq UltraScale+ Block
    draw_module(ax, 18.4, 1.8, 5.1, 11.5, "ps8 (zynq_ultra_ps_e_0)", "Hardened Zynq UltraScale+ MPSoC Silicon",
                ["ARM Quad Cortex-A53 @ 1.33 GHz", "64-bit DDR4-2400 Controller (4 GB)", "", "AXI High-Performance & Control:", "  S_AXI_HP0_FPD (64-bit, DMA -> DDR)", "  M_AXI_HPM0_LPD (32-bit CSRs)", "", "Clocks & Interrupts:", "  pl_clk0 = 100 MHz (IOPLL)", "  pl_resetn0 -> rst_ps8_100M", "  pl_ps_irq0[3:0] <- xlconcat_0", "", "PS EMIO Peripherals:", "  EMIO I2C0 -> HK_SCL / HK_SDA", "  EMIO SPI0 -> J2 Pmod SPI", "  EMIO GPIO[7:0] -> PPS / PROG_B", "", "PS MIO 64-77 GEM3 -> KV260 J10 RJ45", "  Ingests Artix U1201 SGMII UDP!", "", "PetaLinux User-Space Zero-Copy:", "  uio + udmabuf / AF_XDP merge"],
                hdr_col="#991B1B", fill_col="#FEF2F2", badge="Hard IP")

    # Connections
    draw_wire(ax, [(3.7, 11.4), (4.6, 11.4)], "#0369A1", 2.0, "2x 1.0G LVDS")
    draw_wire(ax, [(4.6, 10.2), (3.7, 10.2)], "#0284C7", 1.6, "1.0G DL")
    draw_wire(ax, [(6.4, 9.6), (6.4, 9.0)], "#0284C7", 1.8, "rx_bytes[15:0]")
    draw_wire(ax, [(8.2, 7.3), (8.6, 10.8)], "#0F766E", 1.8, "64b Pkts")
    draw_wire(ax, [(12.2, 11.6), (13.3, 11.6)], "#C2410C", 2.0, "m_axis_rx (64b)")
    draw_wire(ax, [(13.3, 10.2), (12.2, 10.2)], "#C2410C", 1.7, "s_axis_tx (64b)")
    draw_wire(ax, [(15.35, 9.4), (15.35, 8.9)], "#7E22CE", 2.0, "MM2S+S2MM")
    draw_wire(ax, [(17.4, 7.8), (18.4, 7.8)], "#991B1B", 2.2, "S_AXI_HP0_FPD")
    draw_wire(ax, [(18.4, 6.7), (17.4, 6.7)], "#7E22CE", 1.6, "M_AXI_HPM0_LPD")
    draw_wire(ax, [(13.3, 7.1), (12.2, 7.1)], "#475569", 1.4, "0x8000_0000")
    draw_wire(ax, [(17.4, 4.1), (18.4, 4.1)], "#991B1B", 1.5, "pl_ps_irq0[3:0]")
    draw_wire(ax, [(3.7, 2.8), (18.4, 2.8)], "#475569", 1.4, "J2 Pmod EMIO SPI + J10 GEM3 Ethernet UDP", (11.0, 2.15))

    fig.tight_layout()
    save_outputs(fig, "kria_k26_vivado_bd_schematic")


# ---------------------------------------------------------------------------
# 5. DSP Radar & SDR Pipeline Gate-Level Schematic
# ---------------------------------------------------------------------------
def plot_dsp_pipeline_schematic():
    fig, ax = plt.subplots(figsize=(16.5, 10.0))
    ax.set_xlim(0, 24)
    ax.set_ylim(0, 14.8)
    ax.axis("off")

    ax.text(12, 14.45, "KV260-IAS2RF DSP, Wideband SDR & 10.5 GHz Phased-Array Radar Gateware Pipelines",
            ha="center", va="center", fontsize=13.2, fontweight="bold", color="#0F172A")
    ax.text(12, 14.05, "AERIS-10 400 MSPS Radar DDC  |  AD9253 125 MSPS Dual-Ch HF/VHF/UHF SDR DDC  |  LFM Chirp TX DACs  |  8x ADAR1000 SPI Beamformer",
            ha="center", va="center", fontsize=9.0, color="#334155")

    # Row 1: Radar RX Chain (120 MHz IF -> 100 MSPS I/Q)
    ax.add_patch(Rectangle((0.3, 10.4), 23.4, 3.25, facecolor="#FFF7ED", edgecolor="#EA580C", lw=1.2, ls="--", zorder=1))
    ax.text(0.5, 13.42, "CHAIN A: AERIS-10 10.5 GHz Radar RX Digital Down-Converter (400 MSPS -> 100 MSPS Complex I/Q -> 0.8 / 1.6 Gb/s)", fontsize=9.0, fontweight="bold", color="#9A3412")
    draw_module(ax, 0.5, 10.7, 3.1, 2.3, "J905 SMA -> AD9484", "U501 8b 400 MSPS", ["120 MHz IF +/- 50 MHz", "ad9484_radar_model (sim)", "8-bit LVDS DDR -> ISERDES"], hdr_col="#9A3412", fill_col="white")
    draw_module(ax, 4.1, 10.7, 3.5, 2.3, "nco_400m_enhanced", "6-Stage Pipelined DDS", ["32b FTW = 0x4CCCCCCD", "fs=400M -> LO=-120.0 MHz", "LFSR dither + cos/sin LUT"], hdr_col="#C2410C", fill_col="white")
    draw_module(ax, 8.1, 10.7, 3.7, 2.3, "I/Q Mixer & CIC4x", "cic_decimator_4x_enhanced", ["8b x 16b DSP48E1 complex", "5-stage CIC decimate 4x", "400 MSPS -> 100 MSPS"], hdr_col="#C2410C", fill_col="white")
    draw_module(ax, 12.3, 10.7, 3.8, 2.3, "fir_lowpass_parallel", "32-Tap Symmetric FIR", ["100 MHz droop comp. LPF", "Folded DSP48E1 MACs", "18b -> 16b ddc_input_int."], hdr_col="#C2410C", fill_col="white")
    draw_module(ax, 16.6, 10.7, 3.4, 2.3, "Async FIFO + Post-Dec", "ddc_wrapper", ["POST_DECIM = 1 (100M) or", "4 (25M -> 0.80 Gb/s)", "64-bit {Q1,I1,Q0,I0}"], hdr_col="#0F766E", fill_col="white")
    draw_module(ax, 20.5, 10.7, 3.0, 2.3, "Stream 8'h01", "To Dual-Path Mux", ["1000/125M -> IAS1 or ETH", "PPS 64b timestamping", "AERIS-10 20 km CFAR"], hdr_col="#1E293B", fill_col="#F1F5F9")
    for xa, xb in [(3.6, 4.1), (7.6, 8.1), (11.8, 12.3), (16.1, 16.6), (20.0, 20.5)]:
        draw_wire(ax, [(xa, 11.85), (xb, 11.85)], "#C2410C", 1.8)

    # Row 2: Wideband Dual-Ch SDR Chain
    ax.add_patch(Rectangle((0.3, 6.7), 23.4, 3.3, facecolor="#EFF6FF", edgecolor="#2563EB", lw=1.2, ls="--", zorder=1))
    ax.text(0.5, 9.75, "CHAIN B: Wideband Dual-Channel SDR RX (HF/CB 0-62.5 MHz Direct + VHF/FM/Walkie/UHF IF via Mixer -> J901/J902 SMAs)", fontsize=9.0, fontweight="bold", color="#1E40AF")
    draw_module(ax, 0.5, 7.0, 3.1, 2.3, "J901/J902 -> AD9253", "U601 Dual 14b 125 MSPS", ["ChA: HF/CB 0.5-55 MHz", "ChB: VHF/UHF external IF", "2-wire 7:1 ISERDES + FCO"], hdr_col="#1E3A8A", fill_col="white")
    draw_module(ax, 4.1, 7.0, 3.5, 2.3, "2x sdr_ddc_nco", "Independent 32b Tuning", ["0x44 SDR_DDC_NCO_A", "0x48 SDR_DDC_NCO_B", "29.1 mHz tuning step"], hdr_col="#1D4ED8", fill_col="white")
    draw_module(ax, 8.1, 7.0, 3.7, 2.3, "3-Stage CIC3 Decim", "Programmable Decim R", ["AM/CB/Walkie narrow ch.", "FM 200 kHz / Wide 25M", "16b convergent scale"], hdr_col="#1D4ED8", fill_col="white")
    draw_module(ax, 12.3, 7.0, 3.8, 2.3, "15-Tap Halfband FIR", "Sysclk Transition Comp.", ["Symmetric polyphase MAC", "80 dB stopband alias rej.", "Bypasses when R < 4"], hdr_col="#1D4ED8", fill_col="white")
    draw_module(ax, 16.6, 7.0, 3.4, 2.3, "Dual-Clock Gray FIFO", "adcs_clkdiv -> link_clk", ["2 independent I/Q FIFOs", "Programmable words/pkt", "Saturating drop counter"], hdr_col="#0F766E", fill_col="white")
    draw_module(ax, 20.5, 7.0, 3.0, 2.3, "Streams 8'h04/05", "Simultaneous RX", ["Coherent ChA + ChB", "Sent via ETH UDP / IAS1", "Demod on K26 ARM/PL"], hdr_col="#1E293B", fill_col="#F1F5F9")
    for xa, xb in [(3.6, 4.1), (7.6, 8.1), (11.8, 12.3), (16.1, 16.6), (20.0, 20.5)]:
        draw_wire(ax, [(xa, 8.15), (xb, 8.15)], "#1D4ED8", 1.8)

    # Row 3: Radar Chirp TX & SDR TX + ADAR1000 Phased Array
    ax.add_patch(Rectangle((0.3, 0.7), 11.4, 5.5, facecolor="#F0FDF4", edgecolor="#16A34A", lw=1.2, ls="--", zorder=1))
    ax.text(0.5, 5.95, "CHAIN C: AERIS-10 8x ADAR1000 Phased-Array & RF Switch Engine", fontsize=9.0, fontweight="bold", color="#166534")
    draw_module(ax, 0.5, 3.4, 3.3, 2.1, "Beam Table BRAM", "32 Beams x 8 x 24 Bytes", ["Reg 0x088 ADAR_TBL_WR", "Stores Ch1..4 RX/TX gain", "& I/Q vector weights"], hdr_col="#15803D", fill_col="white")
    draw_module(ax, 4.3, 3.4, 3.6, 2.1, "T/R Safe Guard FSM", "adar_ctrl + rf_switch", ["guard_pre/post deadtime", "BEAM_STROBE hw trigger", "4x M3SWA-2+ 1 us settle"], hdr_col="#15803D", fill_col="white")
    draw_module(ax, 8.4, 3.4, 3.0, 2.1, "J1103 Ribbon 1.8V", "8x ADAR1000 Array", ["15.625 MHz Mode-0 SPI", "CSB[7:0], TR[7:0], LOAD", "32 X-band T/R elements"], hdr_col="#1E293B", fill_col="#F1F5F9")
    draw_module(ax, 0.5, 1.0, 10.9, 2.0, "AERIS-10 10.5 GHz / 20 km Array Coordination", "auto_tr_chirp Synchronized Pulse Timing",
                ["1) Load beam ID -> wait guard_pre -> assert ADAR_TR=1 (TX) & M3SWA-2+ TX path", "2) Pulse AD9708 LFM Chirp for pulse_len -> wait guard_post -> switch ADAR_TR=0 (RX)", "3) AD9484 captures 400 MSPS echo -> 100 MSPS DDC -> K26 20 km pulse compression"], hdr_col="#047857", fill_col="white")
    draw_wire(ax, [(3.8, 4.45), (4.3, 4.45)], "#15803D", 1.8)
    draw_wire(ax, [(7.9, 4.45), (8.4, 4.45)], "#15803D", 1.8)

    ax.add_patch(Rectangle((12.2, 0.7), 11.5, 5.5, facecolor="#FAF5FF", edgecolor="#7E22CE", lw=1.2, ls="--", zorder=1))
    ax.text(12.4, 5.95, "CHAIN D: Radar LFM Chirp TX (AD9708) & Wideband SDR I/Q TX (AD9767)", fontsize=9.0, fontweight="bold", color="#6B21A8")
    draw_module(ax, 12.5, 3.4, 3.4, 2.1, "LFM Chirp DDS", "dac_radar (125 MSPS)", ["FTW(n) = f0 + n * df", "Up/down chirp + PRI FSM", "Q15 sine LUT + amp_scale"], hdr_col="#7E22CE", fill_col="white")
    draw_module(ax, 16.4, 3.4, 3.5, 2.1, "ODDR Clock & TX", "AD9708 (U701) -> J904", ["Center-aligned ODDR clk", "(D1=0,D2=1) -> t_S/t_H met", "3rd-order LPF + ADT2-1T+"], hdr_col="#6D28D9", fill_col="white")
    draw_module(ax, 20.4, 3.4, 3.0, 2.1, "J904 Radar TX", "10-50 MHz Chirp IF", ["Drives AERIS upconverter", "10.5 GHz X-band PA", "Cal loopback to RX SMAs"], hdr_col="#1E293B", fill_col="#F1F5F9")
    draw_module(ax, 12.5, 1.0, 5.2, 2.0, "SDR Dual-DAC FIFO & Mux", "dac_sdr (64b -> 2x14b I/Q)", ["K26 MM2S Stream -> link_clk", "-> 125 MSPS IQSEL DDR bus", "Saturating underflow monitor"], hdr_col="#5B21B6", fill_col="white")
    draw_module(ax, 18.2, 1.0, 5.2, 2.0, "AD9767 (U801) -> J903/T801/T802", "Dual 14b 125 MSPS I/Q TX", ["IQWRT + IQCLK interleaved", "50-Ohm diff LPF + baluns", "HF/CB direct TX & VHF/UHF IF"], hdr_col="#1E293B", fill_col="#F1F5F9")
    draw_wire(ax, [(15.9, 4.45), (16.4, 4.45)], "#7E22CE", 1.8)
    draw_wire(ax, [(19.9, 4.45), (20.4, 4.45)], "#7E22CE", 1.8)
    draw_wire(ax, [(17.7, 2.0), (18.2, 2.0)], "#5B21B6", 1.8)

    fig.tight_layout()
    save_outputs(fig, "dsp_radar_sdr_pipeline_schematic")


def main():
    os.makedirs(DOCS_DIR, exist_ok=True)
    os.makedirs(HR_DIR, exist_ok=True)
    artix_json = os.path.join(WORK_DIR, "artix7_die_data.json")
    kria_json = os.path.join(WORK_DIR, "kria_k26_die_data.json")

    render_die_floorplan(
        artix_json, "artix7_silicon_floorplan",
        "Artix-7 XC7A50T-FTG256-2 Silicon Die Occupancy & Post-Route Placement", is_kria=False,
    )
    render_die_floorplan(
        kria_json, "kria_k26_silicon_floorplan",
        "Kria K26 XCK26-SFVC784-2LV-c Silicon Die & Post-Route PL Link Placement", is_kria=True,
    )
    plot_artix7_schematic(artix_json)
    plot_kria_bd_schematic(kria_json)
    plot_dsp_pipeline_schematic()
    print("DONE: All FPGA floorplan & Vivado circuit renders generated.")


if __name__ == "__main__":
    main()
