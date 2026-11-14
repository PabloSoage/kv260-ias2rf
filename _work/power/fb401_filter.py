"""+3V3_CLK filter (FB401 + C401/C402/C403..C408/C422) against the +3V3_D buck's ripple, and FB401's DC drop.

The question (REV06_REVIEW §3, RF_REVIEW_GEMINI H3): FB401 carries 483 mA DC, a ferrite bead loses most of its
low-frequency inductance under DC bias, and neither candidate bead's maker publishes a bias curve. So each bead's
effective inductance is swept from a typical zero-bias value down to 5 % of it, and the ripple and the clock spurs it
would leave are computed for each, alongside the bead's worst-case DC drop.

    micromamba run -n fea python _work/power/fb401_filter.py     # writes docs/sim/fb401_filter.{png,json}
"""
import json, os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FSW = 580e3                      # TPS562201 (SLVSD91D)
VIN, VOUT, LBUCK = 5.0, 3.3, 3.3e-6
DI = VOUT * (VIN - VOUT) / (VIN * LBUCK * FSW)          # inductor ripple, A peak-to-peak
I_CLK = 0.483                    # CLOCK_SPEC: ADCLK948 330 mA + Si549 153 mA
# +3V3_D at its lowest: 0.768 V reference x (1 + 33.2k/10k) = 3.318 V, -2.5 % for the reference and the 1 % divider,
# then 10 mV of copper to FB401 (REV06_REVIEW §3)
V3V3D_MIN = 3.318 * 0.975 - 0.010
SI549_VDD_MIN = 3.135            # 3.3 V option, -5 %

# name: (part, DCR max ohm, rated A, zero-bias L typical for its impedance class)
BEADS = {
    "600R, 1 A (as drawn)": ("Chilisin PBY160808T-601Y-N, C108301", 0.200, 1.0, 2.0e-6),
    "220R, 2 A (proposed)": ("TAI-TECH HCB1608KF-221T20, C304314, already on the BOM (FB502/503/602/603)",
                             0.100, 2.0, 0.6e-6),
}
FRACS = [1.0, 0.3, 0.1, 0.05]


def cap(f, c, esr, esl):
    w = 2j * np.pi * f
    return esr + w * esl + 1 / (w * c)


def par(*z):
    return 1 / sum(1 / x for x in z)


def zout_buck(f):
    # 2 x 22 uF X5R at 3.3 V keeps ~60 % (typical 0805/1206 bias curve); the rest of +3V3_D's decoupling is left out,
    # which overstates the ripple.
    return par(cap(f, 2 * 22e-6 * 0.6, 0.0015, 0.2e-9))


def z_clk(f):
    # +3V3_CLK's own capacitors, DC-bias derated: C401 10 uF 0805 -> ~45 %, C402 1 uF 0402 -> ~50 %
    return par(cap(f, 10e-6 * 0.45, 0.005, 0.5e-9), cap(f, 1e-6 * 0.5, 0.01, 0.4e-9),
               cap(f, 100e-9, 0.02, 0.4e-9), *(cap(f, 1e-9, 0.1, 0.4e-9) for _ in range(6)))


def h(f, rdc, l_eff):
    # bead: DCR in series with its bias-dependent inductance, which the ferrite's loss shunts at high frequency.
    # The clock chips draw a constant current: no resistive load, so no damping from them (the worst case).
    w = 2j * np.pi * f
    zb = rdc + par(w * l_eff, np.full_like(f, 400.0, dtype=complex))
    zc = z_clk(f)
    return zc / (zc + zb)


# Ripple on +3V3_D: the inductor's triangle current into the output capacitors, odd harmonics 4*DI/(pi^2 n^2).
harm = np.arange(1, 16, 2)
fh = harm * FSW
v_d = np.abs(4 * DI / (np.pi ** 2 * harm ** 2) * zout_buck(fh))     # peak volts on +3V3_D

# Spur budget. Si549: datasheet table, 50 mVpp supply ripple at 500 kHz -> -82 dBc on its output, scaled linearly.
SI549_REF_DBC, SI549_REF_VPP = -82.0, 0.050
# ADC side: a clock edge moved by dt (peak) puts a spur at 20 log10(pi fin dt) dBc on a tone at fin.
FIN, SPUR_GOAL = 250e6, -90.0

res = {"buck": {"fsw_Hz": FSW, "ripple_App": DI, "v3v3d_580k_mVpp": 2e3 * v_d[0]},
       "v3v3d_min_V": V3V3D_MIN, "si549_vdd_min_V": SI549_VDD_MIN, "beads": {}}
f = np.logspace(3, 8, 2000)
fig, (a1, a2) = plt.subplots(1, 2, figsize=(15, 5.6))
STY = {"600R, 1 A (as drawn)": "#c0392b", "220R, 2 A (proposed)": "#1f6fb2"}
LS = {1.0: "-", 0.3: "--", 0.1: "-.", 0.05: ":"}
for name, (part, rdc, irated, l0) in BEADS.items():
    drop = I_CLK * rdc
    b = {"part": part, "dcr_max_ohm": rdc, "rated_A": irated, "bias_fraction_of_rating": I_CLK / irated,
         "L0_uH": l0 * 1e6, "dc_drop_max_mV": 1e3 * drop, "v3v3clk_min_V": V3V3D_MIN - drop,
         "si549_margin_mV": 1e3 * (V3V3D_MIN - drop - SI549_VDD_MIN), "cases": {}}
    rip = []
    for k in FRACS:
        le = l0 * k
        g = np.abs(h(f, rdc, le))
        a1.semilogx(f, 20 * np.log10(g), color=STY[name], ls=LS[k], lw=1.8,
                    label=f"{name.split(' (')[0]}, L = {le * 1e6:.2g} µH ({k:.0%} left)")
        v_c = v_d * np.abs(h(fh, rdc, le))
        vpp = 2 * v_c[0]
        rip.append(2e6 * v_c[0])
        b["cases"][f"{k:.0%} of L left"] = {
            "L_uH": le * 1e6, "atten_580k_dB": float(20 * np.log10(np.abs(h(fh[:1], rdc, le))[0])),
            "peak_gain_dB": float(20 * np.log10(g.max())), "peak_Hz": float(f[np.argmax(g)]),
            "clk_ripple_580k_uVpp": float(vpp * 1e6),
            "si549_spur_dBc": float(SI549_REF_DBC + 20 * np.log10(vpp / SI549_REF_VPP)),
            "adclk948_ps_per_V_for_-90dBc_at_250MHz": float(10 ** (SPUR_GOAL / 20) / (np.pi * FIN) / v_c[0] * 1e12)}
    a2.plot([f"{k:.0%}" for k in FRACS], rip, "o-", color=STY[name], lw=2, ms=7, label=name)
    res["beads"][name] = b
a1.axvline(FSW, color="#555", ls=":", lw=1)
a1.text(FSW * 1.08, 12, "580 kHz", color="#555")
a1.set_xlabel("frequency (Hz)")
a1.set_ylabel("+3V3_CLK / +3V3_D (dB)")
a1.set_title("FB401 filter transfer (constant-current load, no damping)")
a1.set_ylim(-80, 20)
a1.grid(True, which="both", alpha=0.3)
a1.legend(fontsize=7.5, loc="lower left", ncol=1)
a2.set_yscale("log")
a2.axhline(2e6 * v_d[0], color="#888", ls="--", lw=1)
a2.text(0.02, 2e6 * v_d[0] * 0.75, f"+3V3_D before FB401: {2e3 * v_d[0]:.1f} mVpp", color="#555", fontsize=9)
a2.set_xlabel("bead inductance left under 483 mA DC\n(the 2 A bead, at 24 % of its rating, keeps more than the 1 A one)")
a2.set_ylabel("580 kHz ripple on +3V3_CLK (µV peak-to-peak)")
a2.set_title("Ripple reaching the Si549 and the ADCLK948")
a2.grid(True, which="both", alpha=0.3)
a2.legend(fontsize=9)
fig.tight_layout()
os.makedirs(os.path.join(ROOT, "docs", "sim"), exist_ok=True)
fig.savefig(os.path.join(ROOT, "docs", "sim", "fb401_filter.png"), dpi=110)
json.dump(res, open(os.path.join(ROOT, "docs", "sim", "fb401_filter.json"), "w"), indent=1)
for n, b in res["beads"].items():
    print(n, f"drop {b['dc_drop_max_mV']:.0f} mV, +3V3_CLK min {b['v3v3clk_min_V']:.3f} V "
             f"(Si549 margin {b['si549_margin_mV']:+.0f} mV)")
    for c, v in b["cases"].items():
        print(f"   {c:>14}: {v['atten_580k_dB']:6.1f} dB, {v['clk_ripple_580k_uVpp']:7.0f} uVpp, "
              f"Si549 {v['si549_spur_dBc']:.0f} dBc, ADCLK948 needs {v['adclk948_ps_per_V_for_-90dBc_at_250MHz']:.0f} ps/V, "
              f"peak {v['peak_gain_dB']:+.1f} dB @ {v['peak_Hz'] / 1e3:.0f} kHz")
