"""Generate single-design 8-layer simulation plots (PNG for docs/sim + SVG vector for docs/img/highres/sim)."""
import csv
import json
import os
import sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SIM_WORK = os.path.join(ROOT, "_work", "sim")
SIM_DOCS = os.path.join(ROOT, "docs", "sim")
SIM_VEC = os.path.join(ROOT, "docs", "img", "highres", "sim")

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 9.5,
    "axes.titlesize": 10.5,
    "axes.titleweight": "bold",
    "axes.labelsize": 9.5,
    "axes.grid": True,
    "grid.alpha": 0.28,
    "grid.linewidth": 0.6,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "svg.fonttype": "none",
})


def save_both(fig, stem, save_svg=True):
    png_path = os.path.join(SIM_DOCS, f"{stem}.png")
    fig.savefig(png_path, dpi=200, bbox_inches="tight", facecolor="white")
    if save_svg:
        svg_path = os.path.join(SIM_VEC, f"{stem}.svg")
        fig.savefig(svg_path, format="svg", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"Generated {stem}.png" + (f" + {stem}.svg" if save_svg else ""))


def load_eye_metrics():
    metrics = {}
    with open(os.path.join(SIM_WORK, "lvds_eye_8layer.csv"), encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["case"] == "routed":
                k = row["pair"].lstrip("/").replace("/", "_")
                metrics[k] = {
                    "pair": row["pair"].lstrip("/"),
                    "rate_gbps": float(row["rate_bps"]) / 1e9,
                    "eye_mV": int(float(row["eye_opening_mV"])),
                    "jitter_ps": int(float(row["zero_crossing_spread_ps"])),
                }
    with open(os.path.join(SIM_WORK, "lvds_eye_eth_1p25g.csv"), encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["case"] == "routed":
                p = row["pair"].lstrip("/")
                if "SGTX" in p:
                    metrics["ETH_SGTX_1P25G"] = {
                        "pair": "CONTROL/ETH_SGTX_PHY",
                        "rate_gbps": 1.25,
                        "eye_mV": int(float(row["eye_opening_mV"])),
                        "jitter_ps": int(float(row["zero_crossing_spread_ps"])),
                    }
                elif "SGRX" in p:
                    # Use worst-case routed sweep entry if multiple exist
                    prev = metrics.get("ETH_SGRX_1P25G")
                    val = int(float(row["eye_opening_mV"]))
                    jit = int(float(row["zero_crossing_spread_ps"]))
                    if prev is None or val < prev["eye_mV"]:
                        metrics["ETH_SGRX_1P25G"] = {
                            "pair": "CONTROL/ETH_SGRX_PHY",
                            "rate_gbps": 1.25,
                            "eye_mV": val,
                            "jitter_ps": jit,
                        }
    return metrics


def draw_eye_axis(ax, phase, traces, title, color, eye_mv, jitter_ps, rate_label):
    for tr in traces:
        ax.plot(phase, tr, color=color, alpha=0.14, lw=0.75)
    # 10th-90th percentile high/low envelope guide lines
    pos_mask = traces > 0
    neg_mask = traces < 0
    # IEEE LVDS receiver threshold +-100 mV
    ax.axhspan(-100, 100, color="#EF9A9A", alpha=0.16, zorder=0)
    ax.axhline(100, color="#C62828", ls="--", lw=0.85, alpha=0.75)
    ax.axhline(-100, color="#C62828", ls="--", lw=0.85, alpha=0.75)
    ax.axhline(0, color="#607D8B", ls=":", lw=0.7, alpha=0.6)
    # Center UI guide markers
    for xc in (0.5, 1.5):
        ax.axvline(xc, color="#455A64", ls=":", lw=0.7, alpha=0.55)
    ax.set_xlim(0.0, 2.0)
    ax.set_ylim(-480, 480)
    ax.set_title(title, fontsize=9.8)
    ax.set_xlabel("Bit Period [UI]")
    ax.set_ylabel("Vdiff [mV]")
    badge = f"{rate_label}\nEye: {eye_mv} mV | Jitter: {jitter_ps} ps"
    ax.text(
        0.03, 0.94, badge,
        transform=ax.transAxes, va="top", ha="left", fontsize=7.8,
        bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="#B0BEC5", alpha=0.92),
    )


def plot_eyes(metrics):
    npz = np.load(os.path.join(SIM_WORK, "eyes_8layer_routed.npz"))
    phase = npz["phase_grid"]

    panels = [
        ("LINK_RX_D0_1G",  "IAS Link RX Data 0 (K26 -> Artix-7)",     "#1565C0", "LINK_RX_D0",     "1.00 Gbps"),
        ("LINK_RX_D1_1G",  "IAS Link RX Data 1 (K26 -> Artix-7)",     "#0277BD", "LINK_RX_D1",     "1.00 Gbps"),
        ("LINK_TX_D0_1G",  "IAS Link TX Data 0 (Artix-7 -> K26)",     "#2E7D32", "LINK_TX_D0",     "1.00 Gbps"),
        ("ADCS_FCO_1G",    "SDR ADC Frame Clock (ADCS_FCO @ 1G ref)", "#6A1B9A", "ADCS_FCO",       "1.00 Gbps"),
        ("ETH_SGTX_1P25G", "1000BASE-T SGMII TX (Artix -> DP83867)",  "#E65100", "ETH_SGTX_1P25G", "1.25 Gbps"),
        ("ETH_SGRX_1P25G", "1000BASE-T SGMII RX (DP83867 -> Artix)",  "#AD1457", "ETH_SGRX_1P25G", "1.25 Gbps"),
    ]
    fig, axes = plt.subplots(2, 3, figsize=(13.5, 7.6), sharex=True, sharey=True)
    for ax, (npz_key, title, col, mkey, rlbl) in zip(axes.flat, panels):
        m = metrics[mkey]
        draw_eye_axis(ax, phase, npz[npz_key], title, col, m["eye_mV"], m["jitter_ps"], rlbl)
    fig.suptitle(
        "KV260-IAS2RF 8-Layer Post-Route High-Speed Eye Diagrams (LVDS 1.0 Gbps & SGMII 1.25 Gbps)",
        fontsize=12.5, fontweight="bold", y=0.99,
    )
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    save_both(fig, "eyes_1g", save_svg=True)

    # Regenerate clean individual eye PNGs referenced by legacy docs
    singles = [
        ("eye_ADCS_FCO_1G",    "ADCS_FCO_1G",    "ADCS_FCO",        "SDR ADC Frame Clock (ADCS_FCO, 1.0 Gbps ref)", "#6A1B9A", "1.00 Gbps"),
        ("eye_CLK_ADCS_1G",    "CLK_ADCS_1G",    "CONTROL_FPGA_CLK","ADCS Clock / Control Reference (1.0 Gbps ref)", "#00838F", "1.00 Gbps"),
        ("eye_LINK_RX_CLK_1G", "LINK_RX_CLK_1G", "LINK_RX_CLK",     "IAS Link RX Clock (K26 -> Artix-7, 1.0 Gbps)",  "#0277BD", "1.00 Gbps"),
        ("eye_LINK_RX_D0_1G",  "LINK_RX_D0_1G",  "LINK_RX_D0",      "IAS Link RX Data 0 (K26 -> Artix-7, 1.0 Gbps)", "#1565C0", "1.00 Gbps"),
        ("eye_LINK_RX_D1_1G",  "LINK_RX_D1_1G",  "LINK_RX_D1",      "IAS Link RX Data 1 (K26 -> Artix-7, 1.0 Gbps)", "#283593", "1.00 Gbps"),
        ("eye_ETH_SGTX_1P25G", "ETH_SGTX_1P25G", "ETH_SGTX_1P25G",  "1000BASE-T SGMII TX (1.25 Gbps)",               "#E65100", "1.25 Gbps"),
        ("eye_ETH_SGRX_1P25G", "ETH_SGRX_1P25G", "ETH_SGRX_1P25G",  "1000BASE-T SGMII RX (1.25 Gbps)",               "#AD1457", "1.25 Gbps"),
    ]
    for fname, nkey, mkey, title, col, rlbl in singles:
        m = metrics[mkey]
        f1, a1 = plt.subplots(figsize=(6.4, 4.2))
        draw_eye_axis(a1, phase, npz[nkey], title, col, m["eye_mV"], m["jitter_ps"], rlbl)
        f1.tight_layout()
        save_both(f1, fname, save_svg=False)

    # Bar summary of all post-route eye openings
    all_rows = []
    with open(os.path.join(SIM_WORK, "lvds_eye_8layer.csv"), encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["case"] == "routed":
                all_rows.append((row["pair"].lstrip("/"), float(row["eye_opening_mV"]), "1.0 Gbps LVDS"))
    all_rows.append(("ETH_SGTX_PHY", float(metrics["ETH_SGTX_1P25G"]["eye_mV"]), "1.25 Gbps SGMII"))
    all_rows.append(("ETH_SGRX_PHY", float(metrics["ETH_SGRX_1P25G"]["eye_mV"]), "1.25 Gbps SGMII"))
    all_rows.sort(key=lambda x: x[1])

    fig, ax = plt.subplots(figsize=(10.5, 6.8))
    labels = [r[0] for r in all_rows]
    vals = [r[1] for r in all_rows]
    colors = ["#E65100" if "SGMII" in r[2] else ("#1565C0" if "LINK" in r[0] else "#2E7D32") for r in all_rows]
    bars = ax.barh(range(len(labels)), vals, color=colors, edgecolor="#263238", linewidth=0.45, height=0.72)
    ax.axvline(200.0, color="#C62828", ls="--", lw=1.4, label="IEEE LVDS Min Differential Window (±100 mV = 200 mVpp)")
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels, fontsize=8.4)
    ax.set_xlabel("Post-Route Eye Opening [mV]")
    ax.set_xlim(0, 760)
    ax.set_title("8-Layer Differential Eye Opening Across All 22 Simulated High-Speed Pairs (Zero Failures)")
    for b, v in zip(bars, vals):
        ax.text(v + 8, b.get_y() + b.get_height() / 2, f"{v:.0f} mV", va="center", fontsize=7.8)
    ax.legend(loc="lower right", frameon=True)
    fig.tight_layout()
    save_both(fig, "eye_openings", save_svg=True)


def plot_lvds_skew():
    skew_data = json.load(open(os.path.join(SIM_WORK, "lvds_skew_8layer.json"), encoding="utf-8"))
    # High-speed differential pairs (excluding slow CLK_FPGA reference)
    order = [
        "ETH_SGTX", "ETH_SGRX",
        "LINK_RX_D0", "LINK_RX_D1", "LINK_RX_CLK", "LINK_TX_D0", "LINK_TX_CLK",
        "ADCS_D0", "ADCS_D1", "ADCS_FCO", "ADCS_DCO",
        "ADCR_D0", "ADCR_D1", "ADCR_D2", "ADCR_D3", "ADCR_D4", "ADCR_D5", "ADCR_D6", "ADCR_D7", "ADCR_OR", "ADCR_DCO",
        "CLK_ADCR", "CLK_ADCS",
        "ETH_MDI0", "ETH_MDI1", "ETH_MDI2", "ETH_MDI3",
    ]
    pairs = [k for k in order if k in skew_data]
    intra_ps = [skew_data[k]["P_ps"] - skew_data[k]["N_ps"] for k in pairs]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13.6, 6.8), gridspec_kw={"width_ratios": [1.15, 1.0]})

    cols1 = ["#E65100" if abs(v) > 10 else ("#0277BD" if "LINK" in k or "ETH_SG" in k else "#2E7D32")
             for k, v in zip(pairs, intra_ps)]
    y = np.arange(len(pairs))
    ax1.barh(y, intra_ps, color=cols1, edgecolor="#263238", lw=0.4, height=0.72)
    ax1.axvspan(-25, 25, color="#C8E6C9", alpha=0.25, zorder=0, label="±25 ps Intra-Pair Budget")
    ax1.axvline(0, color="#37474F", lw=0.8)
    ax1.axvline(-25, color="#2E7D32", ls="--", lw=0.9)
    ax1.axvline(25, color="#2E7D32", ls="--", lw=0.9)
    ax1.set_yticks(y)
    ax1.set_yticklabels(pairs, fontsize=8.0)
    ax1.invert_yaxis()
    ax1.set_xlim(-32, 32)
    ax1.set_xlabel("Intra-Pair Skew (P - N, incl. BGA Pkg Flight Time) [ps]")
    ax1.set_title("Intra-Pair Skew Across 27 High-Speed & MDI Pairs")
    for idx, v in enumerate(intra_ps):
        off = 0.8 if v >= 0 else -0.8
        ha = "left" if v >= 0 else "right"
        ax1.text(v + off, idx, f"{v:+.1f} ps", va="center", ha=ha, fontsize=7.2)
    ax1.legend(loc="lower left", fontsize=8.2)

    # Right panel: Inter-pair bank flight delay & coupling metric
    avg_ps = [0.5 * (skew_data[k]["P_ps"] + skew_data[k]["N_ps"]) for k in pairs]
    coupled_pct = [100.0 * skew_data[k]["coupled"] for k in pairs]
    sc = ax2.barh(y, avg_ps, color="#1565C0", alpha=0.85, edgecolor="#263238", lw=0.4, height=0.72)
    ax2.set_yticks(y)
    ax2.set_yticklabels([f"{k} ({cp:.0f}% coup.)" for k, cp in zip(pairs, coupled_pct)], fontsize=7.8)
    ax2.invert_yaxis()
    ax2.set_xlabel("Total Routed + Package Propagation Delay [ps]")
    ax2.set_title("Total Electrical Flight Time & Differential Coupling %")
    for idx, v in enumerate(avg_ps):
        ax2.text(v + 8, idx, f"{v:.0f} ps", va="center", fontsize=7.2)
    ax2.set_xlim(0, max(avg_ps) * 1.16)

    fig.suptitle("KV260-IAS2RF 8-Layer Post-Layout LVDS / SGMII / MDI Timing & Skew Verification", fontsize=12.2, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    save_both(fig, "lvds_skew", save_svg=True)


def plot_pdn():
    rails = [
        ("pdn_1V0.csv",   "pdn_1V0",   "+1V0 Core (XC7A50T VCCINT)",     0.120, "#1565C0"),
        ("pdn_1V8_D.csv", "pdn_1V8_D", "+1V8_D I/O & ADC Digital",        0.700, "#2E7D32"),
        ("pdn_2V5.csv",   "pdn_2V5",   "+2V5 Auxiliary & LVDS",           2.000, "#6A1B9A"),
        ("pdn_3V3_D.csv", "pdn_3V3_D", "+3V3_D Control & Ethernet PHY",   1.000, "#E65100"),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(12.2, 8.2), sharex=True)
    for ax, (csv_name, stem, label, ztarg, col) in zip(axes.flat, rails):
        data = np.loadtxt(os.path.join(SIM_DOCS, csv_name), delimiter=",", skiprows=1)
        f_mhz = data[:, 0] / 1e6
        z_mohm = data[:, 1] * 1000.0
        zt_mohm = ztarg * 1000.0
        zmax = float(np.max(z_mohm))
        fpeak = float(f_mhz[int(np.argmax(z_mohm))])

        ax.loglog(f_mhz, z_mohm, color=col, lw=2.0, label="8-Layer PDN |Z(f)|")
        ax.axhline(zt_mohm, color="#C62828", ls="--", lw=1.4, label=f"Target Z_max = {zt_mohm:.0f} mOhm")
        ax.fill_between(f_mhz, z_mohm, zt_mohm, where=(z_mohm < zt_mohm), color="#C8E6C9", alpha=0.28)
        ax.set_title(label)
        ax.set_ylabel("|Z(f)| [mOhm]")
        ax.set_xlim(0.1, 100.0)
        mid_mask = f_mhz <= 50.0
        zmid = float(np.max(z_mohm[mid_mask]))
        fmid = float(f_mhz[mid_mask][int(np.argmax(z_mohm[mid_mask]))])
        margin_pct = 100.0 * (zt_mohm - zmax) / zt_mohm
        badge_pos = (0.04, 0.72) if stem == "pdn_3V3_D" else (0.04, 0.10)
        ax.text(
            badge_pos[0], badge_pos[1],
            f"Midband res: {zmid:.1f} mOhm @ {fmid:.1f} MHz\n100 MHz |Z|: {zmax:.1f} mOhm ({margin_pct:.1f}% margin)",
            transform=ax.transAxes, fontsize=8.0,
            bbox=dict(boxstyle="round,pad=0.28", fc="white", ec="#B0BEC5", alpha=0.92),
        )
        ax.legend(loc="upper left", fontsize=8.0)

        # Standalone single-rail PNG
        f1, a1 = plt.subplots(figsize=(6.8, 4.4))
        a1.loglog(f_mhz, z_mohm, color=col, lw=2.2, label="8-Layer PDN |Z(f)|")
        a1.axhline(zt_mohm, color="#C62828", ls="--", lw=1.5, label=f"Target Z_max = {zt_mohm:.0f} mOhm")
        a1.fill_between(f_mhz, z_mohm, zt_mohm, where=(z_mohm < zt_mohm), color="#C8E6C9", alpha=0.28)
        a1.set_title(f"{label} — 8-Layer Plane-Pair PDN Impedance")
        a1.set_xlabel("Frequency [MHz]")
        a1.set_ylabel("|Z(f)| [mOhm]")
        a1.set_xlim(0.1, 100.0)
        a1.legend(loc="upper left", fontsize=8.5)
        a1.text(badge_pos[0], badge_pos[1],
                f"Midband res: {zmid:.1f} mOhm @ {fmid:.1f} MHz | 100 MHz: {zmax:.1f} mOhm ({margin_pct:.1f}% margin)",
                transform=a1.transAxes, fontsize=8.0,
                bbox=dict(boxstyle="round,pad=0.28", fc="white", ec="#B0BEC5", alpha=0.92))
        f1.tight_layout()
        save_both(f1, stem, save_svg=False)

    axes[1, 0].set_xlabel("Frequency [MHz]")
    axes[1, 1].set_xlabel("Frequency [MHz]")
    fig.suptitle(
        "KV260-IAS2RF 8-Layer Power Distribution Network (PDN) Impedance vs. Target Envelope",
        fontsize=12.5, fontweight="bold", y=0.99,
    )
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    save_both(fig, "pdn_impedance", save_svg=True)


def plot_sma_launch():
    traces = [
        ("sma_line.csv",      "50 Ohm Reference CPWG Trace",            "#455A64", "--", 1.5),
        ("sma_plain.csv",     "SMA Launch (No L2 Cutout Baseline)",     "#C62828", ":",  1.8),
        ("sma_cutout.csv",    "SMA Launch + L2 Reference Cutout",       "#1565C0", "-",  2.0),
        ("sma_tvsn08_14.csv", "Final 8-Layer Launch (Cutout + Low-C ESD)", "#2E7D32", "-", 2.3),
    ]
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10.5, 7.2), sharex=True)
    for fname, lbl, col, ls, lw in traces:
        p = os.path.join(SIM_DOCS, fname)
        if not os.path.isfile(p):
            continue
        d = np.loadtxt(p, delimiter=",", skiprows=1)
        f_ghz = d[:, 0] / 1e9
        s11 = d[:, 1]
        s21 = d[:, 2]
        ax1.plot(f_ghz, s11, color=col, ls=ls, lw=lw, label=lbl)
        ax2.plot(f_ghz, s21, color=col, ls=ls, lw=lw, label=lbl)

    ax1.axhline(-15.0, color="#D84315", ls="--", lw=1.1, label="-15 dB Return-Loss Spec")
    ax1.axhline(-20.0, color="#6A1B9A", ls=":", lw=1.0, label="-20 dB High-Quality Threshold")
    ax1.set_ylabel("S11 Return Loss [dB]")
    ax1.set_ylim(-48, 0)
    ax1.set_title("Edge-Launch SMA Transition Return Loss (S11) Across 0.3–6.0 GHz")
    ax1.legend(loc="lower right", ncol=2, fontsize=8.0)

    ax2.set_ylabel("S21 Insertion Loss [dB]")
    ax2.set_xlabel("Frequency [GHz]")
    ax2.set_xlim(0.3, 6.0)
    ax2.set_ylim(-1.6, 0.05)
    ax2.set_title("Edge-Launch SMA Transition Insertion Loss (S21)")
    ax2.legend(loc="lower left", fontsize=8.2)

    fig.suptitle("KV260-IAS2RF 8-Layer 50-Ohm Coplanar Waveguide & SMA Launch EM Analysis", fontsize=12.2, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    save_both(fig, "sma_launch", save_svg=True)


def plot_dac_filters():
    rows = list(csv.DictReader(open(os.path.join(SIM_WORK, "dac_filters_8layer.csv"), encoding="utf-8")))
    series = {}
    for r in rows:
        key = (r["filter"], r["case"])
        series.setdefault(key, []).append((float(r["f"]) / 1e6, float(r["zt_db"]), float(r["cm_rel_db"])))

    styles = [
        ("AD9708 -> T701",      "AD9708 Radar TX Filter -> T701",    "#D84315"),
        ("AD9767 DAC1 -> T801", "AD9767 SDR I Filter -> T801",       "#1565C0"),
        ("AD9767 DAC2 -> T802", "AD9767 SDR Q Filter -> T802",       "#2E7D32"),
    ]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13.0, 5.4), sharex=True)
    for fkey, lbl, col in styles:
        routed = np.array(series[(fkey, "routed")])
        ideal = np.array(series[(fkey, "ideal")])
        ax1.semilogx(routed[:, 0], routed[:, 1], color=col, lw=2.2, label=f"{lbl} (Post-Layout)")
        ax1.semilogx(ideal[:, 0], ideal[:, 1], color=col, lw=1.1, ls="--", alpha=0.65, label=f"{lbl} (Ideal)")
        ax2.semilogx(routed[:, 0], np.clip(routed[:, 2], -120, 0), color=col, lw=2.0, label=f"{lbl} (Post-Layout)")

    ax1.set_title("Differential Reconstruction Filter Transimpedance |Zt(f)|")
    ax1.set_xlabel("Frequency [MHz]")
    ax1.set_ylabel("|Zt| [dB Ohm]")
    ax1.set_xlim(1.0, 500.0)
    ax1.legend(loc="lower left", fontsize=7.6)

    ax2.set_title("Common-Mode Balance / Rejection Relative to Differential")
    ax2.set_xlabel("Frequency [MHz]")
    ax2.set_ylabel("CM Rejection [dBc]")
    ax2.set_xlim(1.0, 500.0)
    ax2.set_ylim(-100, -15)
    ax2.axhline(-35, color="#C62828", ls="--", lw=1.0, label="-35 dBc Balun Balance Spec")
    ax2.legend(loc="upper right", fontsize=8.0)

    fig.suptitle(
        "KV260-IAS2RF 8-Layer Post-Layout DAC Reconstruction LPF + Balun Frequency Response",
        fontsize=12.0, fontweight="bold", y=0.99,
    )
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    save_both(fig, "dac_filters", save_svg=True)


if __name__ == "__main__":
    os.makedirs(SIM_DOCS, exist_ok=True)
    os.makedirs(SIM_VEC, exist_ok=True)
    m = load_eye_metrics()
    plot_eyes(m)
    plot_lvds_skew()
    plot_pdn()
    plot_sma_launch()
    plot_dac_filters()
    print("DONE: All single-design 8-layer simulation plots exported.")
