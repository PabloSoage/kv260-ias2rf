#!/usr/bin/env python3
"""Figures of the KrakenSDR and HackRF Pro end-to-end runs (docs/INTEGRATIONS.md sections 9 and 10).

Reads only what the chain wrote: the simulators' truth (kraken_sim.py, hackrf_sim.py), the A53's calibration
(kria-sdrd kraken-pre), the RTL's output (tb_kria_doa, tb_kria_sweep) and the A53's results from it
(kria-sdrd kraken-post / hackrf-post).

    python sw/integrations/usb_sdr_figures.py

- kraken_doa_e2e.png: calibration against the truth; the Bartlett spectrum from kria_doa and the MUSIC spectrum
  from its R, with the emitters' true bearings; the eigenvalues of R.
- hackrf_sweep_e2e.png: the 0 to 7.2 GHz panorama from kria_sweep's bins with the scene marked; the 2.4 GHz
  band in full resolution.
"""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "fpga" / "sim" / "out"
IMG = ROOT / "docs" / "img" / "integrations"

C1, C2, C3, C4 = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"
plt.rcParams.update({
    "font.size": 10, "axes.edgecolor": INK2, "axes.labelcolor": INK, "xtick.color": INK2,
    "ytick.color": INK2, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
    "axes.spines.top": False, "axes.spines.right": False, "legend.frameon": False,
    "lines.linewidth": 1.8,
})


def kraken():
    d = OUT / "kraken"
    truth = json.loads((d / "truth.json").read_text())
    res = json.loads((d / "kraken_doa.json").read_text())
    cal = res["cal"]
    g = np.array(truth["gain_re"]) + 1j * np.array(truth["gain_im"])
    w_true = g[0] / g
    fig, ax = plt.subplots(1, 3, figsize=(15, 4.3), gridspec_kw={"width_ratios": [1, 2.2, 0.9]})

    a = ax[0]
    k = np.arange(5)
    a.bar(k - 0.18, np.degrees(np.angle(w_true)), 0.36, color=C1, label="true (1/gain)")
    a.bar(k + 0.18, cal["weight_deg"], 0.36, color=C2, label="estimated, noise source")
    for i in k:
        a.annotate(f"lag {cal['lag'][i]}\n(true {truth['delays'][i]})", (i, -165), ha="center", fontsize=8,
                   color=INK2)
    a.set_xticks(k, [f"ch {i}" for i in k])
    a.set_ylabel("calibration phase, degrees")
    a.set_title("Calibration from the noise source", loc="left", fontsize=10)
    a.legend(fontsize=8, loc="upper left")
    a.set_ylim(-180, 180)

    a = ax[1]
    b = np.arange(360)
    a.plot(b, res["bartlett_db"], color=C1, label="Bartlett, kria_doa (PL)")
    a.plot(b, res["music_db"], color=C2, label="MUSIC on kria_doa's R (A53)")
    for e in truth["emitters"]:
        a.axvline(e["bearing"], color=INK2, lw=1, ls="--")
        a.annotate(f"true {e['bearing']:.0f}°", (e["bearing"], 1.5), ha="center", fontsize=8, color=INK2)
    for m in res["music_bearings"]:
        a.annotate(f"{m:.1f}°", (m, -2), xytext=(8, -4), textcoords="offset points", fontsize=9, color=C2)
    a.set_xlim(0, 359)
    a.set_ylim(-45, 4)
    a.set_xlabel("bearing, degrees counter-clockwise from the array's x axis")
    a.set_ylabel("dB")
    a.set_title("Direction finding: two emitters at 446 MHz, the second 6 dB weaker", loc="left", fontsize=10)
    a.legend(fontsize=8, loc="lower right")

    a = ax[2]
    ev = res["eig_db"]
    a.bar(np.arange(1, 6), ev, color=[C2 if i < res["sources"] else GRID for i in range(5)])
    for i, v in enumerate(ev):
        a.annotate(f"{v:.1f}", (i + 1, v), xytext=(0, 3), textcoords="offset points", ha="center", fontsize=8)
    a.set_xlabel("eigenvalue of R")
    a.set_ylabel("dB above the smallest")
    a.set_title(f"{res['sources']} sources found", loc="left", fontsize=10)
    fig.tight_layout()
    fig.savefig(IMG / "kraken_doa_e2e.png", dpi=130)
    plt.close(fig)
    print("kraken_doa_e2e.png", res["music_bearings"])


def hackrf():
    d = OUT / "hackrf"
    truth = json.loads((d / "truth.json").read_text())
    res = json.loads((d / "hackrf_sweep.json").read_text())
    beats = [int(x, 16) for x in (d / "sweep_rtl.hex").read_text().split()]
    # raw bins at full resolution from the RTL's output (78.125 kHz), the panorama's own placement
    fr, pw = [], []
    for blk in range(len(beats) // 65):
        f = beats[blk * 65]
        for j in range(64):
            v = beats[blk * 65 + 1 + j]
            for h, p in enumerate((v & 0xFFFFFFFF, v >> 32)):
                idx = 2 * j + h
                b = 161 + idx if idx < 64 else 33 + idx - 64
                rel = b - 256 if b >= 128 else b
                fr.append(f + 7.5e6 + rel * 78125.0)
                pw.append(p)
    fr = np.array(fr)
    full = 127 * 256 * 0.5
    st = {k.strip(): v.strip() for k, v in (l.split("=") for l in (d / "setup.txt").read_text().split("\n") if "=" in l)}
    scale = int(st["pshift"]) - int(st["nseg_log2"])     # output x 2^scale = mean power over the segments
    db = 10 * np.log10(np.maximum(np.array(pw), 1) * 2.0 ** scale / (full * full))
    o = np.argsort(fr)
    fr, db = fr[o], db[o]

    fig, ax = plt.subplots(2, 1, figsize=(15, 7.2), gridspec_kw={"height_ratios": [1.25, 1]})
    a = ax[0]
    tr = np.array(res["trace_db"][:7200])
    a.axvspan(0, 1.1, color=C3, alpha=0.08)
    a.axvspan(1.1, 7.1, color=C1, alpha=0.05)
    a.plot(np.arange(7200) / 1000, tr, color=C1, lw=0.9)
    # one label per group of the scene, above the trace
    groups = [("FM", 0.098), ("DAB", 0.227), ("PMR446", 0.446), ("DVB-T", 0.61), ("LTE 800/900", 0.88),
              ("ADS-B", 1.09), ("LTE 1800", 1.842), ("UMTS", 2.14), ("Wi-Fi, BT", 2.44), ("LTE 2600", 2.655),
              ("5G NR", 3.55), ("Wi-Fi 5", 5.34), ("FPV 5.8", 5.8), ("ITS-G5", 5.9)]
    for i, (n, f) in enumerate(groups):
        a.annotate(n, (f, -20 + 8 * (i % 2)), rotation=0, fontsize=7.5, color=INK2, ha="center")
    a.annotate("this board: HF, VHF/UHF to 1.1 GHz", (0.05, 9), fontsize=8, color=C3)
    a.annotate("HackRF Pro adds 1.1 to 7.1 GHz, receive and transmit", (1.2, 9), fontsize=8, color=C1)
    bf = truth["bad_block_f"] / 1e9
    a.annotate("block with a corrupted header,\ndropped by kria_sweep", (bf + 0.01, -70), fontsize=7, color=C2)
    a.set_xlim(0, 7.2)
    a.set_ylim(-75, 15)
    a.set_xlabel("GHz")
    a.set_ylabel("dBFS, max per MHz")
    a.set_title(f"One sweep, 0 to 7.2 GHz in {truth['blocks']} blocks: kria_sweep's bins on the A53's panorama "
                f"({res['covered'] * 100:.1f} % covered)", loc="left", fontsize=10)

    a = ax[1]
    m = (fr >= 2.380e9) & (fr <= 2.500e9)
    a.plot(fr[m] / 1e6, db[m], color=C1, lw=0.9, label="kria_sweep bins (78.125 kHz)")
    for s in res["signals"]:
        if 2380e6 <= s["f"] <= 2500e6:
            a.axvspan((s["f"] - s["bw"] / 2) / 1e6, (s["f"] + s["bw"] / 2) / 1e6, color=C2, alpha=0.12)
    for s in truth["scene"]:
        if 2380 <= s["f_mhz"] <= 2500:
            a.annotate(s["name"], (s["f_mhz"], -8), ha="center", fontsize=8, color=INK2)
    a.set_xlim(2380, 2500)
    a.set_ylim(-75, 0)
    a.set_xlabel("MHz")
    a.set_ylabel("dBFS")
    a.set_title("2.4 GHz band at full resolution; shaded: what the A53's detector reports", loc="left", fontsize=10)
    a.legend(fontsize=8, loc="lower right")
    fig.tight_layout()
    fig.savefig(IMG / "hackrf_sweep_e2e.png", dpi=130)
    plt.close(fig)
    print("hackrf_sweep_e2e.png", len(res["signals"]), "signals")


if __name__ == "__main__":
    IMG.mkdir(parents=True, exist_ok=True)
    kraken()
    hackrf()
