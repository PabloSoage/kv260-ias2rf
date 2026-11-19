#!/usr/bin/env python3
"""Home common-mode noise loop with and without input choke L1004.

Models the common-mode (CM) loop closed when the module runs at home from an
earthed 12 V SMPS while another earthed cable is connected (an earthed DP
monitor, a PC over USB/Ethernet, and/or a coax shield running to an earthed
antenna mast). Sweeps 10 kHz to 100 MHz and evaluates mains 50 Hz Y-capacitor
leakage separately.

[V] verified against a datasheet or standard; [E] stated engineering estimate.

Usage:
    python _work/power/cm_noise.py
Writes docs/sim/cm_noise.png and docs/sim/cm_noise.json.
"""
import json
import math
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT_PNG = os.path.join(ROOT, "docs", "sim", "cm_noise.png")
OUT_JSON = os.path.join(ROOT, "docs", "sim", "cm_noise.json")


def z_choke(f, l_cm=2.0e-6, r_p=600.0, c_p=1.266515e-12, r_dc=0.004):
    """Parallel R-L-C CM impedance of L1004 (two 8 mOhm windings in parallel).

    Default element values match Coilmaster SMM9070-501 / ZE ZEGMCM9070-501T
    typical rating: |Z_cm(100 MHz)| = 600 Ohm [V], R_dc_cm = 4 mOhm [V].
    """
    w = 2.0 * np.pi * f
    y_l = 1.0 / (r_dc + 1j * w * l_cm)
    y_c = 1j * w * c_p
    y_r = 1.0 / r_p
    return 1.0 / (y_l + y_c + y_r)


def z_cable(f, length_m, l_per_m, r_dc, z_asym=200.0, f_skin=50e3):
    """Cable common-mode impedance: DC+skin resistance in series with L || Z_asym [E].

    Smoothly transitions from lumped inductance j*w*L at low/mid frequencies to
    an asymptotic distributed antenna-mode impedance Z_asym (~200 Ohm) near VHF.
    """
    w = 2.0 * np.pi * f
    r_ac = r_dc * np.sqrt(1.0 + np.maximum(0.0, f / f_skin))
    z_l = 1j * w * (length_m * l_per_m)
    return r_ac + (z_l * z_asym) / (z_l + z_asym)


def z_board_gnd(f, r_gnd=0.5e-3, l_gnd=5.0e-9):
    """Board ground plane impedance between power/KV260 entry and SMA row [E]."""
    w = 2.0 * np.pi * f
    return r_gnd + 1j * w * l_gnd


def v_smps_cm(f):
    """Class-I 12 V desktop SMPS common-mode source envelope V rms [E].

    65 kHz fundamental (50-150 kHz band): 100 mV rms across the fundamental band,
    steep roll-off below 50 kHz (2 mV sub-fundamental baseline at 10 kHz),
    -20 dB/dec switching-harmonic roll-off above 150 kHz, and a 5 mV VHF floor.
    """
    hp = (f / 55e3) ** 2 / (1.0 + (f / 55e3) ** 2)
    lp = 1.0 / np.sqrt(1.0 + (f / 150e3) ** 2)
    fund = 0.12 * hp * lp
    hf_floor = 0.005 / np.sqrt(1.0 + (1e6 / np.maximum(f, 1.0)) ** 2)
    return np.sqrt(fund ** 2 + hf_floor ** 2 + 0.001 ** 2)


def solve_frequency(f, l_cm=2.0e-6, r_p=600.0, c_p=1.266515e-12):
    z_l1004 = z_choke(f, l_cm=l_cm, r_p=r_p, c_p=c_p, r_dc=0.004)
    z_dc = z_cable(f, length_m=1.8, l_per_m=1.0e-6, r_dc=0.0334, z_asym=200.0)
    z_dev = z_cable(f, length_m=1.5, l_per_m=0.8e-6, r_dc=0.15, z_asym=200.0)
    z_ant = z_cable(f, length_m=5.0, l_per_m=0.7e-6, r_dc=0.10, z_asym=200.0)
    z_gnd = z_board_gnd(f, r_gnd=0.5e-3, l_gnd=5.0e-9)

    # Combined setup: DP monitor / USB / ETH earth + antenna coax earth in parallel
    # Brick internal PE/filter bond impedance ~ 1.0 Ohm [E] in series with 1.8 m DC cord
    z_src = 1.0
    z_ret_comb = (z_dev * z_ant) / (z_dev + z_ant)
    z_loop_wo = z_src + z_dc + z_gnd + z_ret_comb
    z_loop_wi = z_loop_wo + z_l1004

    v_src = v_smps_cm(f)
    i_tot_wo = v_src / z_loop_wo
    i_tot_wi = v_src / z_loop_wi
    ant_share = z_ret_comb / z_ant
    i_ant_wo = i_tot_wo * ant_share
    i_ant_wi = i_tot_wi * ant_share

    v_gnd_comb_wo = np.abs(i_tot_wo * z_gnd)
    v_gnd_comb_wi = np.abs(i_tot_wi * z_gnd)
    v_gnd_ant_share_wo = np.abs(i_ant_wo * z_gnd)
    v_gnd_ant_share_wi = np.abs(i_ant_wi * z_gnd)
    il_comb_db = 20.0 * np.log10(np.abs(z_loop_wi) / np.abs(z_loop_wo))

    # Antenna-only setup (no monitor/PC earthed): 100 % returns on antenna coax shield
    z_only_wo = 1.0 + z_dc + z_gnd + z_ant
    z_only_wi = z_only_wo + z_l1004
    i_only_wo = v_src / z_only_wo
    i_only_wi = v_src / z_only_wi
    v_gnd_only_wo = np.abs(i_only_wo * z_gnd)
    v_gnd_only_wi = np.abs(i_only_wi * z_gnd)
    il_only_db = 20.0 * np.log10(np.abs(z_only_wi) / np.abs(z_only_wo))

    return dict(
        z_l1004=z_l1004,
        z_loop_wo=z_loop_wo,
        z_loop_wi=z_loop_wi,
        v_src=v_src,
        i_tot_wo=i_tot_wo,
        i_tot_wi=i_tot_wi,
        ant_share=ant_share,
        i_ant_wo=i_ant_wo,
        i_ant_wi=i_ant_wi,
        v_gnd_comb_wo=v_gnd_comb_wo,
        v_gnd_comb_wi=v_gnd_comb_wi,
        v_gnd_ant_share_wo=v_gnd_ant_share_wo,
        v_gnd_ant_share_wi=v_gnd_ant_share_wi,
        il_comb_db=il_comb_db,
        i_only_wo=i_only_wo,
        i_only_wi=i_only_wi,
        v_gnd_only_wo=v_gnd_only_wo,
        v_gnd_only_wi=v_gnd_only_wi,
        il_only_db=il_only_db,
    )


def main():
    freqs = np.logspace(4, 8, 1000)
    typ = solve_frequency(freqs, l_cm=2.0e-6, r_p=600.0, c_p=1.266515e-12)
    wc = solve_frequency(freqs, l_cm=1.5e-6, r_p=450.0, c_p=1.688686e-12)

    # 50 Hz Y-capacitor mains leakage [E]: 230 V rms through C_Y = 2.2 nF
    f_50 = 50.0
    c_y = 2.2e-9
    x_cy = 1.0 / (2.0 * math.pi * f_50 * c_y)
    i_50_ua = 230.0 / x_cy * 1e6
    z50_choke = abs(z_choke(f_50))
    v_gnd_50_uv = (i_50_ua * 1e-6) * 0.5e-3 * 1e6

    spot_hz = [10e3, 65e3, 100e3, 150e3, 1e6, 3e6, 10e6, 30e6, 100e6]
    spots = []
    print("Home common-mode noise sweep (combined earthed monitor/PC + earthed antenna coax):")
    print("  %-9s | %7s | %6s | %9s -> %-9s | %8s | %9s -> %-9s" % (
        "freq", "|Z_1004|", "IL(dB)", "Icm_wo", "Icm_wi", "coax%", "Vgnd_wo", "Vgnd_wi"))
    for f0 in spot_hz:
        s = solve_frequency(np.array([f0]))
        s_min = solve_frequency(np.array([f0]), l_cm=1.5e-6, r_p=450.0, c_p=1.688686e-12)
        z_m = float(abs(s["z_l1004"][0]))
        il_c = float(s["il_comb_db"][0])
        il_min = float(s_min["il_comb_db"][0])
        i_wo_ma = float(abs(s["i_tot_wo"][0]) * 1e3)
        i_wi_ma = float(abs(s["i_tot_wi"][0]) * 1e3)
        ia_wo_ma = float(abs(s["i_ant_wo"][0]) * 1e3)
        ia_wi_ma = float(abs(s["i_ant_wi"][0]) * 1e3)
        sh_pct = float(abs(s["ant_share"][0]) * 100.0)
        vg_wo_uv = float(s["v_gnd_comb_wo"][0] * 1e6)
        vg_wi_uv = float(s["v_gnd_comb_wi"][0] * 1e6)
        lbl = f"{f0/1e6:g} MHz" if f0 >= 1e6 else f"{f0/1e3:g} kHz"
        print("  %-9s | %6.1fR | %5.1fdB | %6.2f mA -> %6.2f mA | %6.1f%% | %7.2f -> %7.2f uV" % (
            lbl, z_m, il_c, i_wo_ma, i_wi_ma, sh_pct, vg_wo_uv, vg_wi_uv))
        spots.append(dict(
            freq_hz=f0,
            label=lbl,
            v_src_mv=round(float(s["v_src"][0] * 1e3), 2),
            z_l1004_ohm=round(z_m, 3),
            il_combined_db=round(il_c, 2),
            il_combined_min450_db=round(il_min, 2),
            il_ant_only_db=round(float(s["il_only_db"][0]), 2),
            i_total_wo_ma=round(i_wo_ma, 4),
            i_total_wi_ma=round(i_wi_ma, 4),
            coax_share_pct=round(sh_pct, 1),
            i_coax_wo_ma=round(ia_wo_ma, 4),
            i_coax_wi_ma=round(ia_wi_ma, 4),
            v_gnd_comb_wo_uv=round(vg_wo_uv, 3),
            v_gnd_comb_wi_uv=round(vg_wi_uv, 3),
            v_gnd_ant_only_wo_uv=round(float(s["v_gnd_only_wo"][0] * 1e6), 3),
            v_gnd_ant_only_wi_uv=round(float(s["v_gnd_only_wi"][0] * 1e6), 3),
        ))
    print("  50 Hz mains Y-cap leakage (230 V, C_Y = 2.2 nF [E]): %.1f uA rms, |Z_L1004| = %.3f mOhm, V_gnd = %.3f uV" % (
        i_50_ua, z50_choke * 1e3, v_gnd_50_uv))

    out = dict(
        model={
            "source_smps_cm": "120 mV peak factor across 50-150 kHz switching band, -20 dB/dec roll-off, 5 mV HF ringing floor, 1 mV baseline, 1.0 Ohm brick PE bond [E]",
            "source_50hz_ycap": "230 V rms across C_Y = 2.2 nF [E]",
            "l1004_typ": {"L_cm_uH": 2.0, "R_p_ohm": 600.0, "C_p_pF": 1.267, "R_dc_cm_mOhm": 4.0, "mark": "[V/E]"},
            "l1004_min": {"L_cm_uH": 1.5, "R_p_ohm": 450.0, "C_p_pF": 1.689, "R_dc_cm_mOhm": 4.0, "mark": "[V/E]"},
            "dc_cord": {"length_m": 1.8, "R_dc_mOhm": 33.4, "L_uH": 1.8, "Z_asym_ohm": 200.0, "mark": "[E]"},
            "dev_cable": {"length_m": 1.5, "R_dc_mOhm": 150.0, "L_uH": 1.2, "Z_asym_ohm": 200.0, "mark": "[E]"},
            "ant_coax": {"length_m": 5.0, "R_dc_mOhm": 100.0, "L_uH": 3.5, "Z_asym_ohm": 200.0, "mark": "[E]"},
            "board_gnd": {"R_mOhm": 0.5, "L_nH": 5.0, "mark": "[E]"},
        },
        mains_50hz=dict(
            v_mains_v=230.0,
            c_y_nf=2.2,
            i_leak_ua=round(i_50_ua, 1),
            z_l1004_mohm=round(z50_choke * 1e3, 3),
            v_gnd_uv=round(v_gnd_50_uv, 4),
        ),
        spot_frequencies=spots,
        peak_il_db=round(float(np.max(typ["il_comb_db"])), 2),
        peak_il_freq_mhz=round(float(freqs[np.argmax(typ["il_comb_db"])] / 1e6), 2),
    )

    os.makedirs(os.path.dirname(OUT_PNG), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)

    f_mhz = freqs / 1e6
    fig, ax = plt.subplots(2, 2, figsize=(11.5, 8.0))
    plt.rcParams.update({"font.size": 8.5})

    # (0,0) Impedances
    ax[0, 0].loglog(f_mhz, np.abs(typ["z_l1004"]), c="#2980b9", lw=2.0, label="|Z_L1004| typ (600 Ohm @ 100 MHz)")
    ax[0, 0].loglog(f_mhz, np.abs(wc["z_l1004"]), c="#3498db", lw=1.4, ls="--", label="|Z_L1004| min (450 Ohm @ 100 MHz)")
    ax[0, 0].loglog(f_mhz, np.abs(typ["z_loop_wo"]), c="#c0392b", lw=1.8, label="|Z_loop| without L1004")
    ax[0, 0].set_title("Common-mode impedance: L1004 vs return loop")
    ax[0, 0].set_xlabel("Frequency (MHz)"); ax[0, 0].set_ylabel("Impedance magnitude (Ohm)")
    ax[0, 0].grid(True, which="both", alpha=0.28); ax[0, 0].legend(fontsize=7.5)

    # (0,1) Common-mode currents
    ax[0, 1].loglog(f_mhz, np.abs(typ["i_tot_wo"]) * 1e3, c="#c0392b", lw=2.0, label="Total CM current, no L1004")
    ax[0, 1].loglog(f_mhz, np.abs(typ["i_tot_wi"]) * 1e3, c="#27ae60", lw=2.0, label="Total CM current, with L1004")
    ax[0, 1].loglog(f_mhz, np.abs(typ["i_ant_wo"]) * 1e3, c="#e67e22", lw=1.4, ls="--", label="Coax shield share, no L1004")
    ax[0, 1].loglog(f_mhz, np.abs(typ["i_ant_wi"]) * 1e3, c="#16a085", lw=1.4, ls="--", label="Coax shield share, with L1004")
    ax[0, 1].set_title("Module & coax-shield CM current (V_cm [E])")
    ax[0, 1].set_xlabel("Frequency (MHz)"); ax[0, 1].set_ylabel("Current (mA rms)")
    ax[0, 1].grid(True, which="both", alpha=0.28); ax[0, 1].legend(fontsize=7.2)

    # (1,0) Board ground voltage drop (0.5 mOhm + 5 nH)
    ax[1, 0].axvspan(3.0, 30.0, color="#eef5fb", zorder=0, label="HF band (3-30 MHz)")
    ax[1, 0].axvspan(30.0, 100.0, color="#fdf3e7", zorder=0, label="VHF band (30-100 MHz)")
    ax[1, 0].loglog(f_mhz, typ["v_gnd_only_wo"] * 1e6, c="#922b21", lw=1.3, ls=":", label="Ant coax only, no L1004")
    ax[1, 0].loglog(f_mhz, typ["v_gnd_comb_wo"] * 1e6, c="#c0392b", lw=2.0, label="Combined loop, no L1004")
    ax[1, 0].loglog(f_mhz, typ["v_gnd_comb_wi"] * 1e6, c="#27ae60", lw=2.0, label="Combined loop, with L1004")
    ax[1, 0].set_title("Voltage across adapter ground (0.5 mOhm + 5 nH [E])")
    ax[1, 0].set_xlabel("Frequency (MHz)"); ax[1, 0].set_ylabel("Ground drop (uV rms)")
    ax[1, 0].grid(True, which="both", alpha=0.28); ax[1, 0].legend(fontsize=7.0, loc="lower left")

    # (1,1) Common-mode insertion loss
    ax[1, 1].semilogx(f_mhz, typ["il_comb_db"], c="#2980b9", lw=2.0, label="Combined loop, typ 600 Ohm")
    ax[1, 1].semilogx(f_mhz, wc["il_comb_db"], c="#3498db", lw=1.4, ls="--", label="Combined loop, min 450 Ohm")
    ax[1, 1].semilogx(f_mhz, typ["il_only_db"], c="#16a085", lw=1.6, ls=":", label="Antenna coax only, typ 600 Ohm")
    ax[1, 1].set_title("Common-mode insertion loss (source-independent)")
    ax[1, 1].set_xlabel("Frequency (MHz)"); ax[1, 1].set_ylabel("Attenuation (dB)")
    ax[1, 1].set_ylim(0, 16)
    ax[1, 1].grid(True, which="both", alpha=0.28); ax[1, 1].legend(fontsize=7.5)

    fig.suptitle("Single-entry CM choke L1004 at home: SMPS to earthed monitor/PC & antenna coax (10 kHz - 100 MHz)", fontsize=10.5)
    fig.tight_layout()
    fig.savefig(OUT_PNG, dpi=150)
    plt.close(fig)
    print("wrote", OUT_PNG, "and", OUT_JSON)


if __name__ == "__main__":
    main()
