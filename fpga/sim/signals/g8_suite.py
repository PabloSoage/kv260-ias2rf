# SPDX-License-Identifier: Apache-2.0
"""
Rev08 G-8 signal-level verification (docs/REV08_PLAN.md, G-8). Method in g8_lib.py.

    python g8_suite.py [case ...]        cases: hf_am hf_ssb fm air nbfm adsb tx radar (default: all)

Results go to results.json next to this file and figures to docs/img/sim/g8_*.png.
"""

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import g8_lib as L          # noqa: E402
import gen_signals as gs    # noqa: E402

import matplotlib           # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt   # noqa: E402

RESULTS = os.path.join(L.THIS_DIR, "results" + os.environ.get("G8_SUFFIX", "") + ".json")


def ftw(f, fs):
    return int(round((2 ** 32) * (f / fs))) & 0xFFFFFFFF


def psd_db(x, fs, nfft=4096):
    from scipy.signal import welch
    # no detrending: Welch's default removes each segment's mean, which is the carrier of anything at 0 Hz
    f, p = welch(x, fs, nperseg=min(nfft, len(x)), return_onesided=not np.iscomplexobj(x), scaling="density",
                 detrend=False)
    if np.iscomplexobj(x):
        f, p = np.fft.fftshift(f), np.fft.fftshift(p)
    return f, 10 * np.log10(p + 1e-30)


# ====================================================================== HF (AD9253 channel B, sdr_ddc)
HF = dict(fs_adc=62.5e6, fs_k=62.5e6 / 4, ant_fs_dbm=-32.0, nf_db=12.0, artix_decim="00400004")


def hf_quant(v, rng):
    return gs.quantize_ad9253_14b(v, HF["fs_adc"], ant_fs_dbm=HF["ant_fs_dbm"], nf_db=HF["nf_db"], rng=rng)


def hf_e2e(tag, v_rf, f_tune, kria, run_us, rng, demod=True):
    """Antenna waveform -> AD9253 codes -> full chain. Returns the Kria input stream and the demodulated output."""
    cb = hf_quant(v_rf, rng)
    hexf = L.wpath(f"{tag}_adcs.hex")
    gs.write_adcs_hex(hexf, np.zeros_like(cb), cb)
    ddc, dem = L.wpath(f"{tag}_ddc.txt"), L.wpath(f"{tag}_dem.txt")
    pa = ["CASE=HF", f"RUN_US={run_us}", "SIG_WAIT_ARM", f"ADCS_SIG_FILE={hexf}", f"OUT_DDC={ddc}",
          f"ARTIX_NCO_B={ftw(f_tune, HF['fs_adc']):08x}", f"ARTIX_DECIM={HF['artix_decim']}"] + kria
    if demod:
        pa.append(f"OUT_DEMOD={dem}")
    L.run_bench("tb_system_signals", "g8hf", pa)
    return L.read_iq(ddc), dem


def hf_calibrate(f_tune, kria, p_cal=-70.0, df=50e3, seed=11):
    """CW at f_tune + df: gain (Kria-input code amplitude per antenna peak volt), noise density, tuning error."""
    fs = HF["fs_adc"]
    n = int(400e-6 * fs)
    t = np.arange(n) / fs
    v = L.dbm_to_vpeak(p_cal) * np.cos(2 * np.pi * (f_tune + df) * t)
    x, _ = hf_e2e("hfcal", v, f_tune, kria, 320, np.random.default_rng(seed), demod=False)
    x = L.settled(x)[300:]
    f0, a = L.tone_fit(x, HF["fs_k"], df, 20e3)
    n0 = L.noise_density(L.tone_remove(x, HF["fs_k"], f0), HF["fs_k"], [(f0, 30e3)], 2e6)
    g = a / L.dbm_to_vpeak(p_cal)
    # what the cascade predicts: thermal noise -174 dBm/Hz + NF at the antenna, times the same gain
    n0_pred = (g ** 2) * 2 * 50 * 10 ** ((-174 + HF["nf_db"] - 30) / 10)   # (V peak)^2 per Hz = 2 R P
    cal = dict(p_cal_dbm=p_cal, gain_codes_per_v=g, n0=n0, n0_pred=n0_pred, tune_err_hz=f0 - df,
               cn_db_hz=10 * np.log10((a ** 2) / n0))
    print(f"  calibration: gain {g:.4g} codes/V, tuning error {f0 - df:+.1f} Hz, "
          f"N0 {10*np.log10(n0):.1f} dB(codes^2/Hz) vs cascade {10*np.log10(n0_pred):.1f}, "
          f"C/N0 at {p_cal} dBm {cal['cn_db_hz']:.1f} dB-Hz")
    return cal


# ====================================================================== VHF/UHF (AD9484, AERIS DDC with the G-4 NCO)
# Direct sampling at 400 MSPS; the AERIS DDC's NCO is tuned through RADAR_CTRL[31:8] (24 bits, 23.8 Hz steps),
# 400 -> 100 MSPS, POST_DECIM 4 -> 25 MSPS to the Kria. Full scale and NF per REV08_PLAN section 5.5.
VU = dict(fs_adc=400e6, fs_k=25e6, define=("FPGA_CLK_400M",))
VU_MODES = {"fm": (-49.9, 2.3), "air": (-48.9, 2.5), "vhf": (-51.9, 2.0), "uhf": (-46.3, 3.7), "adsb": (-40.4, 7.1)}


def vu_nco(f_tune):
    hi = int(round((2 ** 24) * f_tune / VU["fs_adc"])) & 0xFFFFFF
    return hi, hi * VU["fs_adc"] / 2 ** 24


def vu_e2e(tag, v_ant, f_tune, kria, run_us, rng, mode, outs=("ddc", "dem"), ant_fs=None, nf=None, mutate=""):
    a_fs, a_nf = VU_MODES[mode]
    codes = gs.quantize_ad9484_8b(v_ant, fs=VU["fs_adc"], ant_fs_dbm=ant_fs if ant_fs is not None else a_fs,
                                  nf_db=nf if nf is not None else a_nf, rng=rng)
    hexf = L.wpath(f"{tag}_adcr.hex")
    gs.write_adcr_hex(hexf, codes)
    hi, _ = vu_nco(f_tune)
    files = {o: L.wpath(f"{tag}_{o}.txt") for o in outs}
    opt = {"ddc": "OUT_DDC", "dem": "OUT_DEMOD", "adsb": "OUT_ADSB", "radar": "OUT_RADAR"}
    pa = ["CASE=VU", f"RUN_US={run_us}", "SIG_WAIT_ARM", f"ADCR_SIG_FILE={hexf}",
          f"ARTIX_RAD_CTRL={(hi << 8) | 0x05:08x}"] + kria + [f"{opt[o]}={f}" for o, f in files.items()]
    L.run_bench("tb_system_signals", "g8vu", pa, defines=VU["define"], mutate=mutate)
    return L.read_iq(files["ddc"]), files


def vu_calibrate(f_tune, kria, mode, p_cal=None, df=10e3, seed=21):
    """CW df above the tuned frequency, 30 dB below full scale."""
    a_fs, a_nf = VU_MODES[mode]
    p_cal = a_fs - 30.0 if p_cal is None else p_cal
    fs = VU["fs_adc"]
    n = int(300e-6 * fs)
    t = np.arange(n) / fs
    _, f_nco = vu_nco(f_tune)
    v = L.dbm_to_vpeak(p_cal) * np.cos(2 * np.pi * (f_tune + df) * t)
    x, _ = vu_e2e("vucal", v, f_tune, kria, 260, np.random.default_rng(seed), mode, outs=("ddc",))
    x = L.settled(x)[300:]
    fs_k = VU["fs_k"]
    f_exp = f_tune + df - f_nco
    # the strongest tone near +/-f_exp, then it and its mirror fitted together (the DDC's own image rejection)
    f0, _ = L.tone_fit(x, fs_k, f_exp, 0.4 * abs(f_exp))
    f0m, _ = L.tone_fit(x, fs_k, -f_exp, 0.4 * abs(f_exp))
    a, am = L.pair_fit(x, fs_k, f0)
    a_m, am_m = L.pair_fit(x, fs_k, f0m)
    inverted = a_m > a                                 # the DDC delivers the conjugate spectrum
    if inverted:
        f0, a, am = -f0m, a_m, am_m
    f_obs = -f0 if inverted else f0
    n0 = L.noise_density(L.tone_remove(L.tone_remove(x, fs_k, f_obs), fs_k, -f_obs), fs_k,
                         [(f_obs, 100e3), (-f_obs, 100e3)], 4e6)
    g = a / L.dbm_to_vpeak(p_cal)
    n0_pred = (g ** 2) * 2 * 50 * 10 ** ((-174 + a_nf - 30) / 10)
    cal = dict(mode=mode, p_cal_dbm=p_cal, gain_codes_per_v=g, n0=n0, n0_pred=n0_pred, f_nco=f_nco, inverted=inverted,
               tune_err_hz=f0 - f_exp, ddc_image_db=20 * np.log10(a / max(am, 1e-12)),
               cn_db_hz=10 * np.log10((a ** 2) / n0))
    print(f"  calibration ({mode}): gain {g:.4g} codes/V, tuning error {f0 - f_exp:+.1f} Hz, DDC image "
          f"{cal['ddc_image_db']:.1f} dB down, N0 {10*np.log10(n0):.1f} dB vs cascade {10*np.log10(n0_pred):.1f}")
    return cal


def sweep_ch(tag, x, ch, mutate=""):
    """Run baseband x (codes at the Kria input) through kria_channel_rx with channel CSRs ch."""
    inf, outf = L.wpath(f"{tag}_in.txt"), L.wpath(f"{tag}_out.txt")
    L.write_iq(inf, x)
    L.run_bench("tb_dsp_sweeps", "g8", ["SWEEP_MODE=CH", f"IN_FILE={inf}", f"OUT_FILE={outf}"] + ch, mutate=mutate)
    return L.read_audio(outf)


def kria_to_ch(kria, fs_k):
    """The scene's KRIA_* CSR plusargs as tb_dsp_sweeps' CH_* plusargs (same registers, kria_dsp_suite.v)."""
    m = {}
    for p in kria:
        k, v = p.split("=")
        m[k] = v
    ch = [f"CH_MODE={(int(m['KRIA_CTRL'], 16) >> 4) & 7}", f"IN_RATE_HZ={int(round(fs_k))}"]
    for src, dst in (("KRIA_NCO", "CH_NCO"), ("KRIA_DECIM", "CH_DECIM"), ("KRIA_DEMOD", "CH_DEMOD"),
                     ("KRIA_PILOT", "CH_PILOT"), ("KRIA_CTCSS", "CH_CTCSS")):
        if src in m:
            ch.append(f"{dst}={m[src]}")
    if "KRIA_THR" in m:
        ch.append(f"CH_THR={int(m['KRIA_THR'], 16)}")
    return ch


def decim_word(cic, fir, cal, fs_k, noise_codes=4.0, n5=False):
    """KRIA_DECIM {fir, shift, cic}. The CIC's gain is R^3; a full shift leaves the channel's noise below one code
    in the 16-bit path after the CIC, and weak signals vanish in its rounding. The shift is chosen so the noise
    in the channel filter's band (0.32 of the CIC output rate) is about noise_codes rms; an in-channel signal then
    clips at 20 log10(32767 / noise_codes) dB above that noise, 78 dB for 4 codes."""
    fs_c = fs_k / cic
    sigma = np.sqrt(cal["n0"] * 0.32 * fs_c)
    gain = max(1.0, noise_codes / sigma)
    stages = 5 if n5 else 3                       # CH_DECIM[22]: five CIC stages
    shift = int(round(stages * np.log2(cic) - np.log2(gain)))
    shift = max(0, min(shift, int(round(stages * np.log2(cic))), 63))
    return f"{fir:02x}{shift | (0x40 if n5 else 0):02x}{cic:04x}"


def case_hf_am():
    print("\n=== HF AM broadcast, 7.200 MHz (J951 -> AD9253 B -> sdr_ddc -> kria_channel_rx AM) ===")
    f_rf, fs, fs_k = 7.200e6, HF["fs_adc"], HF["fs_k"]
    cic, fir = 651, 2
    fs_a = fs_k / cic / fir
    cal = hf_calibrate(f_rf, ["KRIA_CTRL=00000005"])
    kria = ["KRIA_CTRL=00000005", "KRIA_NCO=00000000", f"KRIA_DECIM={decim_word(cic, fir, cal, fs_k)}",
            "KRIA_DEMOD=00003000"]

    # scene: the wanted station at -80 dBm with speech and a 1 kHz probe, 2-ray fading, and a station 40 dB
    # stronger 9 kHz up; full chain for 1.2 ms
    n = int(1.2e-3 * fs)
    v_rf, _, _, _ = gs.gen_hf_am(n, fs=fs, f_rf=f_rf, lvl_dbm=-80.0, adj_plus_db=40.0, seed=101)
    iq, _ = hf_e2e("hfam", v_rf, f_rf, kria, 1200, np.random.default_rng(101))
    f_s, p_s = psd_db(L.settled(iq), fs_k, 8192)

    # sweeps on the Kria RTL with the scene's CSRs: 30 % AM at 1 kHz, 96 ms per level
    ch = kria_to_ch(kria, fs_k)
    n_sw = int(0.096 * fs_k)
    t = np.arange(n_sw) / fs_k
    m = 0.3
    levels = np.arange(-125.0, -49.0, 5.0)
    rtl, ref = [], []
    settle = 200
    for lv in levels:
        rng = np.random.default_rng(int(-lv) + 7)
        x = cal["gain_codes_per_v"] * L.dbm_to_vpeak(lv) * (1 + m * np.sin(2 * np.pi * 1000 * t)) \
            + L.complex_noise(n_sw, cal["n0"], fs_k, rng)
        a = sweep_ch("hfam_sw", x, ch)["l"][settle:]
        rtl.append(L.sinad_db(a, fs_a, 1000.0))
        r = L.ref_am(x, fs_k, cic * fir)[settle:]
        ref.append(L.sinad_db(r, fs_a, 1000.0))
        print(f"    {lv:6.1f} dBm  SINAD RTL {rtl[-1]:5.1f} dB  reference {ref[-1]:5.1f} dB")
    # adjacent channel: wanted 20 dB above the RTL's 10 dB point, a station 40 dB stronger at +9 kHz
    s10 = L.level_at(levels, rtl, 10.0)
    s10_ref = L.level_at(levels, ref, 10.0)
    lv_adj = s10 + 20.0
    rng = np.random.default_rng(99)
    base = cal["gain_codes_per_v"] * L.dbm_to_vpeak(lv_adj) * (1 + m * np.sin(2 * np.pi * 1000 * t))
    adj = cal["gain_codes_per_v"] * L.dbm_to_vpeak(lv_adj + 40) * (1 + 0.7 * np.sin(2 * np.pi * 1700 * t)) \
        * np.exp(2j * np.pi * 9000 * t)
    noise = L.complex_noise(n_sw, cal["n0"], fs_k, rng)
    a0 = sweep_ch("hfam_adj0", base + noise, ch)["l"][settle:]
    a1 = sweep_ch("hfam_adj1", base + adj + noise, ch)["l"][settle:]
    sin0, sin1 = L.sinad_db(a0, fs_a, 1000.0), L.sinad_db(a1, fs_a, 1000.0)
    print(f"    10 dB SINAD: RTL {s10:.1f} dBm, reference {s10_ref:.1f} dBm; +40 dB at +9 kHz: "
          f"{sin0:.1f} -> {sin1:.1f} dB")
    # mutation: the CORDIC without its fractional guard bits, at the RTL's 10 dB point
    xm = cal["gain_codes_per_v"] * L.dbm_to_vpeak(s10) * (1 + m * np.sin(2 * np.pi * 1000 * t)) \
        + L.complex_noise(n_sw, cal["n0"], fs_k, np.random.default_rng(77))
    mut = (L.sinad_db(sweep_ch("hfam_m0", xm, ch)["l"][settle:], fs_a, 1000.0),
           L.sinad_db(sweep_ch("hfam_m1", xm, ch, mutate="cordic_no_frac")["l"][settle:], fs_a, 1000.0))
    print(f"    mutation cordic_no_frac at {s10:.1f} dBm: SINAD {mut[0]:.1f} -> {mut[1]:.1f} dB")

    checks = {
        "tuning error < 10 Hz": abs(cal["tune_err_hz"]) < 10.0,
        "noise density within 2 dB of the cascade": abs(10 * np.log10(cal["n0"] / cal["n0_pred"])) < 2.0,
        "10 dB SINAD within 2 dB of the reference": abs(s10 - s10_ref) <= 2.0,
        "SINAD >= 30 dB at high level": max(rtl) >= 30.0,
        "mutation cordic_no_frac costs >= 2 dB at the 10 dB point": mut[0] - mut[1] >= 2.0,
        "+40 dB at +9 kHz costs <= 3 dB": sin0 - sin1 <= 3.0,
    }

    fig, ax = plt.subplots(2, 2, figsize=(12, 8.2))
    ax[0, 0].plot(f_s / 1e3, p_s - p_s.max(), lw=0.8)
    ax[0, 0].set_xlim(-30, 30); ax[0, 0].set_ylim(-100, 5)
    ax[0, 0].set_title("Kria input (full chain): wanted -80 dBm, +40 dB at +9 kHz")
    ax[0, 0].set_xlabel("Offset from 7.200 MHz (kHz)"); ax[0, 0].set_ylabel("dB")
    ax[0, 1].plot(np.arange(len(a1[:240])) / fs_a * 1e3, a1[:240], lw=0.9)
    ax[0, 1].set_title(f"Demodulated audio, +40 dB neighbour (Kria RTL), wanted {lv_adj:.0f} dBm", fontsize=10)
    ax[0, 1].set_xlabel("ms"); ax[0, 1].set_ylabel("LSB")
    fa, pa = psd_db(a1, fs_a, 1024)
    ax[1, 0].plot(fa / 1e3, pa - pa.max(), lw=0.9)
    ax[1, 0].set_ylim(-90, 5); ax[1, 0].set_title("Audio spectrum (1 kHz probe)")
    ax[1, 0].set_xlabel("kHz"); ax[1, 0].set_ylabel("dB")
    ax[1, 1].plot(levels, rtl, "o-", label="Kria RTL")
    ax[1, 1].plot(levels, ref, "s--", label="floating-point reference")
    ax[1, 1].axhline(10, color="grey", ls=":")
    ax[1, 1].set_title("SINAD vs antenna level (30 % AM, 1 kHz)")
    ax[1, 1].set_xlabel("dBm"); ax[1, 1].set_ylabel("SINAD (dB)"); ax[1, 1].legend(); ax[1, 1].grid(alpha=0.3)
    for a in ax.flat:
        a.grid(alpha=0.3)
    fig.suptitle("HF AM, 7.200 MHz: AD9253 -> sdr_ddc -> link -> kria_channel_rx")
    fig.tight_layout()
    png = os.path.join(L.IMG_DIR, "g8_hf_am.png")
    fig.savefig(png, dpi=150); plt.close(fig)

    return dict(case="hf_am", cal=cal, levels=levels.tolist(), sinad_rtl=rtl, sinad_ref=ref,
                sens10_rtl_dbm=s10, sens10_ref_dbm=s10_ref, adj40_sinad=[sin0, sin1], checks=checks,
                passed=all(checks.values()), figure="docs/img/sim/g8_hf_am.png")


def level_sweep(tag, levels, make_x, ch, ref_fn, fs_a, f_tone, settle=200, lo=250.0, hi=3000.0):
    """SINAD of the Kria RTL and of the reference demodulator on the same input, per antenna level."""
    rtl, ref = [], []
    for lv in levels:
        x = make_x(lv, np.random.default_rng(int(-lv * 10) + 7))
        a = sweep_ch(tag, x, ch)["l"][settle:]
        rtl.append(L.sinad_db(a, fs_a, f_tone, lo, hi))
        ref.append(L.sinad_db(ref_fn(x)[settle:], fs_a, f_tone, lo, hi))
        print(f"    {lv:6.1f} dBm  SINAD RTL {rtl[-1]:5.1f} dB  reference {ref[-1]:5.1f} dB")
    return rtl, ref


def case_hf_ssb():
    print("\n=== HF SSB, 14.200 MHz USB (J951 -> AD9253 B -> sdr_ddc -> kria_channel_rx USB) ===")
    f_rf, fs, fs_k = 14.200e6, HF["fs_adc"], HF["fs_k"]
    cic, fir = 651, 2
    fs_a = fs_k / cic / fir
    cal = hf_calibrate(f_rf, ["KRIA_CTRL=00000015"])
    kria = ["KRIA_CTRL=00000015", "KRIA_NCO=00000000", f"KRIA_DECIM={decim_word(cic, fir, cal, fs_k)}",
            "KRIA_DEMOD=00004000"]

    # scene: USB speech at -85 dBm with selective fading and atmospheric impulses (QRN), full chain 1.2 ms
    n = int(1.2e-3 * fs)
    v_rf, _, _, _ = gs.gen_hf_ssb(n, fs=fs, f_rf=f_rf, mode="USB", lvl_dbm=-85.0, seed=202)
    iq, _ = hf_e2e("hfssb", v_rf, f_rf, kria, 1200, np.random.default_rng(202))
    f_s, p_s = psd_db(L.settled(iq), fs_k, 8192)

    ch = kria_to_ch(kria, fs_k)
    n_sw = int(0.096 * fs_k)
    t = np.arange(n_sw) / fs_k
    g = cal["gain_codes_per_v"]
    f_m = 1200.0

    def mk(lv, rng, sb=+1):
        return g * L.dbm_to_vpeak(lv) * np.exp(2j * np.pi * sb * f_m * t) + L.complex_noise(n_sw, cal["n0"], fs_k, rng)

    levels = np.arange(-135.0, -59.0, 5.0)
    rtl, ref = level_sweep("hfssb_sw", levels, mk, ch, lambda x: L.ref_ssb(x, fs_k, cic * fir, True), fs_a, f_m)
    s10, s10_ref = L.level_at(levels, rtl, 10.0), L.level_at(levels, ref, 10.0)

    # opposite sideband: the same tone 1.2 kHz below the carrier, 40 dB above the 10 dB point
    lv = s10 + 40.0
    a_u = sweep_ch("hfssb_u", mk(lv, np.random.default_rng(5), +1), ch)["l"][200:]
    a_l = sweep_ch("hfssb_l", mk(lv, np.random.default_rng(5), -1), ch)["l"][200:]

    def tone_pow(a):
        _, amp = L.tone_fit(a - a.mean() + 0j, fs_a, f_m, 100.0)
        return amp ** 2
    osr = 10 * np.log10(tone_pow(a_u) / tone_pow(a_l))
    print(f"    10 dB SINAD: RTL {s10:.1f} dBm, reference {s10_ref:.1f} dBm; opposite sideband {osr:.1f} dB down")
    # mutation: USB and LSB swapped, the upper-sideband tone must disappear
    a_m = sweep_ch("hfssb_m", mk(lv, np.random.default_rng(5), +1), ch, mutate="swap_usb_lsb")["l"][200:]
    osr_m = 10 * np.log10(tone_pow(a_u) / tone_pow(a_m))
    print(f"    mutation swap_usb_lsb: the USB tone {osr_m:.1f} dB down")

    checks = {
        "tuning error < 10 Hz": abs(cal["tune_err_hz"]) < 10.0,
        "noise density within 2 dB of the cascade": abs(10 * np.log10(cal["n0"] / cal["n0_pred"])) < 2.0,
        "10 dB SINAD within 2 dB of the reference": abs(s10 - s10_ref) <= 2.0,
        "SINAD >= 30 dB at high level": max(rtl) >= 30.0,
        "opposite sideband >= 25 dB down": osr >= 25.0,
        "mutation swap_usb_lsb puts the USB tone >= 25 dB down": osr_m >= 25.0,
    }

    fig, ax = plt.subplots(2, 2, figsize=(12, 8.2))
    ax[0, 0].plot(f_s / 1e3, p_s - p_s.max(), lw=0.8)
    ax[0, 0].set_xlim(-15, 15); ax[0, 0].set_ylim(-100, 5)
    ax[0, 0].set_title("Kria input (full chain): USB speech -85 dBm, fading, QRN")
    ax[0, 0].set_xlabel("Offset from 14.200 MHz (kHz)"); ax[0, 0].set_ylabel("dB")
    ax[0, 1].plot(np.arange(240) / fs_a * 1e3, a_u[:240], lw=0.9, label="USB tone")
    ax[0, 1].plot(np.arange(240) / fs_a * 1e3, a_l[:240], lw=0.9, label="same tone in LSB")
    ax[0, 1].set_title(f"Kria RTL audio at {lv:.0f} dBm: opposite sideband {osr:.0f} dB down")
    ax[0, 1].set_xlabel("ms"); ax[0, 1].set_ylabel("LSB"); ax[0, 1].legend()
    fa, pa = psd_db(a_u, fs_a, 1024)
    ax[1, 0].plot(fa / 1e3, pa - pa.max(), lw=0.9)
    ax[1, 0].set_ylim(-90, 5); ax[1, 0].set_title("Audio spectrum (1.2 kHz tone)")
    ax[1, 0].set_xlabel("kHz"); ax[1, 0].set_ylabel("dB")
    ax[1, 1].plot(levels, rtl, "o-", label="Kria RTL")
    ax[1, 1].plot(levels, ref, "s--", label="floating-point reference")
    ax[1, 1].axhline(10, color="grey", ls=":")
    ax[1, 1].set_title("SINAD vs antenna level (USB, 1.2 kHz)")
    ax[1, 1].set_xlabel("dBm (PEP)"); ax[1, 1].set_ylabel("SINAD (dB)"); ax[1, 1].legend()
    for a in ax.flat:
        a.grid(alpha=0.3)
    fig.suptitle("HF SSB, 14.200 MHz USB: AD9253 -> sdr_ddc -> link -> kria_channel_rx")
    fig.tight_layout()
    fig.savefig(os.path.join(L.IMG_DIR, "g8_hf_ssb.png"), dpi=150); plt.close(fig)

    return dict(case="hf_ssb", cal=cal, levels=levels.tolist(), sinad_rtl=rtl, sinad_ref=ref,
                sens10_rtl_dbm=s10, sens10_ref_dbm=s10_ref, opposite_sideband_db=osr, checks=checks,
                passed=all(checks.values()), figure="docs/img/sim/g8_hf_ssb.png")


def rds_ber(rx, sent):
    """Bit error rate of the decoded RDS bits against the sent ones, over the last 3/4 of the record (the bit
    clock and the pilot PLL settle in the first quarter), best alignment and polarity."""
    rx = np.asarray(rx, int)
    if len(rx) < 60:
        raise RuntimeError(f"only {len(rx)} RDS bits decoded")
    tail = rx[len(rx) // 4:]
    best = 1.0
    for off in range(0, len(sent) - len(tail)):
        e = np.mean(tail != sent[off:off + len(tail)])
        best = min(best, e, 1 - e)
    return float(best)


def case_fm():
    print("\n=== FM broadcast, 98.1 MHz: stereo, RDS (AD9484 -> AERIS DDC -> kria_channel_rx WBFM) ===")
    f_rf, fs_k = 98.1e6, VU["fs_k"]
    cic, fir = 25, 4
    fs_a = fs_k / cic / fir                                    # 250 kS/s
    alpha = int(round((1 - np.exp(-1 / (fs_a * 50e-6))) * 32768))   # 50 us de-emphasis
    c19 = int(round(2 * np.cos(2 * np.pi * 19e3 / fs_a) * 16384)) & 0xFFFF
    spb = int(round(fs_a / 1187.5 * 256))
    cal = vu_calibrate(f_rf, ["KRIA_CTRL=00000041"], "fm", df=300e3)
    kria = ["KRIA_CTRL=00000041", "KRIA_NCO=00000000", f"KRIA_DECIM={decim_word(cic, fir, cal, fs_k)}",
            f"KRIA_DEMOD={c19:04x}{alpha:04x}", f"KRIA_PILOT={ftw(19e3, fs_a):08x}", f"KRIA_CTCSS={spb:04x}0000"]
    g, n0 = cal["gain_codes_per_v"], cal["n0"]

    def conj(z):
        return np.conj(z) if cal["inverted"] else z

    # scene: the wanted station at -62 dBm (stereo, pilot, RDS, multipath), one 60 dB stronger 2.2 MHz up and
    # one 20 dB stronger 3.6 MHz down; the AGC has backed the front end off so the strong one sits under full scale
    fs = VU["fs_adc"]
    n = int(1.5e-3 * fs)
    v_rf, _, meta = gs.gen_fm_bcast(n, fs=fs, f_des=f_rf, lvl_dbm=-62.0, blocker_plus_db=60.0, seed=303)
    iq, files = vu_e2e("fmscene", v_rf, f_rf, kria, 1500, np.random.default_rng(303), "fm",
                       ant_fs=meta["ant_fs"], nf=meta["nf"])
    sc = L.settled(iq)
    f_s, p_s = psd_db(conj(sc), fs_k, 8192)          # the DDC's conjugate turned back: offsets read as at RF
    dem = L.read_audio(files["dem"], min_len=64)
    scene_pilot = bool(dem["pilot"][len(dem["pilot"]) // 2:].mean() > 0.9)
    print(f"    scene: pilot locked in the second half of the record: {scene_pilot}")

    ch = kria_to_ch(kria, fs_k)

    def fm_bb(mpx, lv, rng):
        phi = 2 * np.pi * 75e3 * np.cumsum(mpx) / fs_k
        return conj(g * L.dbm_to_vpeak(lv) * np.exp(1j * phi)) + L.complex_noise(len(mpx), n0, fs_k, rng)

    # mono sensitivity: 1 kHz at 75 kHz deviation, 50 ms
    n_sw = int(0.05 * fs_k)
    t = np.arange(n_sw) / fs_k
    mono = np.sin(2 * np.pi * 1000 * t)
    levels = np.arange(-120.0, -54.0, 5.0)
    rtl, ref = [], []
    for lv in levels:
        x = fm_bb(mono, lv, np.random.default_rng(int(-lv) + 3))
        a = sweep_ch("fm_sw", x, ch)["mono"][2000:]
        rtl.append(L.sinad_db(a, fs_a, 1000.0, 200.0, 15000.0))
        r = L.ref_fm(conj(x), fs_k, cic * fir, 110e3, deemph_us=50)[2000:]
        ref.append(L.sinad_db(r, fs_a, 1000.0, 200.0, 15000.0))
        print(f"    {lv:6.1f} dBm  mono SINAD RTL {rtl[-1]:5.1f} dB  reference {ref[-1]:5.1f} dB")
    s30, s30_ref = L.level_at(levels, rtl, 30.0), L.level_at(levels, ref, 30.0)

    # stereo: left only, pilot at 10 %, -60 dBm, 80 ms
    n_st = int(0.08 * fs_k)
    t = np.arange(n_st) / fs_k
    lc = np.sin(2 * np.pi * 1000 * t)
    mpx = 0.45 * lc + 0.10 * np.cos(2 * np.pi * 19e3 * t) + 0.45 * lc * np.cos(2 * np.pi * 38e3 * t)
    st = sweep_ch("fm_st", fm_bb(mpx, -60.0, np.random.default_rng(1)), ch)
    half = len(st["l"]) // 2
    _, al = L.tone_fit(st["l"][half:] - st["l"][half:].mean() + 0j, fs_a, 1000.0, 200.0)
    _, ar = L.tone_fit(st["r"][half:] - st["r"][half:].mean() + 0j, fs_a, 1000.0, 200.0)
    sep = 20 * np.log10(al / max(ar, 1e-9))
    st_pilot = bool(st["pilot"][half:].mean() > 0.9)
    print(f"    stereo: separation {sep:.1f} dB, pilot locked {st_pilot}")

    # RDS: 0.25 s per level (about 300 bits), random bit phase, with and without the bit-clock loop
    n_r = int(0.25 * fs_k)
    t = np.arange(n_r) / fs_k
    grp = gs._encode_rds_group()
    sent = np.concatenate([np.random.default_rng(7).integers(0, 2, 64), np.tile(grp, 4)])
    c57 = np.cos(2 * np.pi * 57e3 * t)
    rds_lv = [-105.0, -100.0, -95.0, -90.0, -80.0]
    ber, ber_mut = [], []
    for lv in rds_lv:
        toff = float(np.random.default_rng(int(-lv)).uniform(0, 1 / 1187.5))
        mpx = 0.45 * np.sin(2 * np.pi * 1000 * t) + 0.10 * np.cos(2 * np.pi * 19e3 * t) \
            + gs._modulate_rds_57k(t + toff, c57, sent)
        x = fm_bb(mpx, lv, np.random.default_rng(int(-lv) + 11))
        inf, outf = L.wpath("fm_rds_in.txt"), L.wpath("fm_rds_out.txt")
        L.write_iq(inf, x)
        for mut, lst in (("", ber), ("rds_no_timing", ber_mut)):
            L.run_bench("tb_dsp_sweeps", "g8", ["SWEEP_MODE=CH", f"IN_FILE={inf}", f"OUT_FILE={outf}"] + ch,
                        mutate=mut)
            lst.append(rds_ber(L.read_audio(outf)["rds"], np.concatenate([sent, sent])))
        print(f"    {lv:6.1f} dBm  RDS BER {ber[-1]:.4f}   without the bit clock loop {ber_mut[-1]:.4f}")

    checks = {
        "tuning error < 30 Hz (24-bit NCO, 23.8 Hz steps)": abs(cal["tune_err_hz"]) < 30.0,
        "noise density within 2 dB of the cascade": abs(10 * np.log10(cal["n0"] / cal["n0_pred"])) < 2.0,
        "mono 30 dB SINAD within 2 dB of the reference": abs(s30 - s30_ref) <= 2.0,
        "mono SINAD >= 40 dB at high level": max(rtl) >= 40.0,
        "stereo separation >= 20 dB, pilot locked": sep >= 20.0 and st_pilot,
        "scene with a +60 dB blocker: pilot locked": scene_pilot,
        "RDS BER 0 at -90 and -80 dBm": ber[rds_lv.index(-90.0)] == 0 and ber[rds_lv.index(-80.0)] == 0,
        "bit clock loop no worse than without it at every level": all(b <= bm for b, bm in zip(ber, ber_mut)),
        "mutation rds_no_timing is worse somewhere": any(bm > b + 0.02 for b, bm in zip(ber, ber_mut)),
    }

    fig, ax = plt.subplots(2, 2, figsize=(12, 8.2))
    ax[0, 0].plot(f_s / 1e6, p_s - p_s.max(), lw=0.7)
    ax[0, 0].set_ylim(-110, 5)
    ax[0, 0].set_title("Kria input (full chain): -62 dBm wanted,\n+60 dB at +2.2 MHz, +20 dB at -3.6 MHz", fontsize=10)
    ax[0, 0].set_xlabel("Offset from 98.1 MHz (MHz)"); ax[0, 0].set_ylabel("dB")
    fa, pa = psd_db(st["l"][half:], fs_a, 4096)
    ax[0, 1].plot(fa / 1e3, pa - pa.max(), lw=0.8, label="L")
    fa, pa2 = psd_db(st["r"][half:], fs_a, 4096)
    ax[0, 1].plot(fa / 1e3, pa2 - pa.max(), lw=0.8, label="R (left-only test)")
    ax[0, 1].set_xlim(0, 20); ax[0, 1].set_ylim(-90, 5); ax[0, 1].legend()
    ax[0, 1].set_title(f"Stereo decode (Kria RTL, -60 dBm): separation {sep:.0f} dB")
    ax[0, 1].set_xlabel("kHz"); ax[0, 1].set_ylabel("dB")
    ax[1, 0].semilogy(rds_lv, np.maximum(ber, 1e-4), "o-", label="bit clock loop")
    ax[1, 0].semilogy(rds_lv, np.maximum(ber_mut, 1e-4), "s--", label="mutation: no loop")
    ax[1, 0].set_title("RDS bit error rate (floor shown at 1e-4)"); ax[1, 0].set_xlabel("dBm"); ax[1, 0].legend()
    ax[1, 1].plot(levels, rtl, "o-", label="Kria RTL")
    ax[1, 1].plot(levels, ref, "s--", label="floating-point reference")
    ax[1, 1].axhline(30, color="grey", ls=":")
    ax[1, 1].set_title("Mono SINAD vs antenna level (1 kHz, 75 kHz deviation)")
    ax[1, 1].set_xlabel("dBm"); ax[1, 1].set_ylabel("SINAD (dB)"); ax[1, 1].legend()
    for a in ax.flat:
        a.grid(alpha=0.3)
    fig.suptitle("FM broadcast, 98.1 MHz: AD9484 -> AERIS DDC -> link -> kria_channel_rx (WBFM, stereo, RDS)")
    fig.tight_layout()
    fig.savefig(os.path.join(L.IMG_DIR, "g8_fm_broadcast.png"), dpi=150); plt.close(fig)

    return dict(case="fm", cal=cal, levels=levels.tolist(), sinad_rtl=rtl, sinad_ref=ref, sens30_rtl_dbm=s30,
                sens30_ref_dbm=s30_ref, stereo_sep_db=sep, rds_levels=rds_lv, rds_ber=ber, rds_ber_no_loop=ber_mut,
                scene_pilot=scene_pilot, checks=checks, passed=all(checks.values()),
                figure="docs/img/sim/g8_fm_broadcast.png")



def case_air():
    print("\n=== Airband AM, 121.500 MHz: 8.33 kHz neighbours (AD9484 -> AERIS DDC -> kria_channel_rx AM) ===")
    f_rf, fs_k = 121.5e6, VU["fs_k"]
    # the channel filter cuts at 0.16 of the CIC output rate: 25 MSPS / 1040 = 24.0 kS/s gives +/-3.8 kHz, the
    # 8.33 kHz neighbour at 0.35 of the rate (-74 dB)
    cic, fir = 1040, 2
    fs_a = fs_k / cic / fir
    cal = vu_calibrate(f_rf, ["KRIA_CTRL=00000001"], "air", df=100e3)
    # five CIC stages: the 25 kHz neighbour's sidebands sit within 3 kHz of the CIC's first null (24.0 kHz)
    kria = ["KRIA_CTRL=00000001", "KRIA_NCO=00000000", f"KRIA_DECIM={decim_word(cic, fir, cal, fs_k, n5=True)}",
            "KRIA_DEMOD=00003000"]
    g, n0 = cal["gain_codes_per_v"], cal["n0"]
    off = f_rf - cal["f_nco"]            # where the carrier lands in the Kria stream (24-bit NCO step)
    kria_c = [k if not k.startswith("KRIA_NCO") else f"KRIA_NCO={ftw(off if not cal['inverted'] else -off, fs_k):08x}"
              for k in kria]

    def cj(z):
        return np.conj(z) if cal["inverted"] else z

    # scene: -90 dBm with speech and a 1 kHz probe, an aircraft's Doppler, neighbours 25 dB up at +8.33 kHz and
    # 35 dB up at +25 kHz, FM broadcast behind the FM-reject filter
    fs = VU["fs_adc"]
    n = int(1.2e-3 * fs)
    v_rf, _, _ = gs.gen_airband(n, fs=fs, f_des=f_rf, lvl_dbm=-90.0, seed=404)
    iq, _ = vu_e2e("airscene", v_rf, f_rf, kria_c, 1200, np.random.default_rng(404), "air", outs=("ddc",))
    f_s, p_s = psd_db(cj(L.settled(iq)), fs_k, 16384)     # the DDC's conjugate turned back: offsets read as at RF

    ch = kria_to_ch(kria_c, fs_k)
    n_sw = int(0.096 * fs_k)
    t = np.arange(n_sw) / fs_k
    m = 0.3
    rot = np.exp(2j * np.pi * off * t)

    def mk(lv, rng, extra=0):
        return cj(g * L.dbm_to_vpeak(lv) * (1 + m * np.sin(2 * np.pi * 1000 * t)) * rot + extra) \
            + L.complex_noise(n_sw, n0, fs_k, rng)

    def ref_fn(x):
        return L.ref_am(cj(x) * np.conj(rot), fs_k, cic * fir)

    levels = np.arange(-130.0, -59.0, 5.0)
    rtl, ref = level_sweep("air_sw", levels, mk, ch, ref_fn, fs_a, 1000.0)
    s10, s10_ref = L.level_at(levels, rtl, 10.0), L.level_at(levels, ref, 10.0)
    lv = s10 + 20.0
    res = {}
    for name, df, up in (("8.33 kHz +25 dB", 8333.0, 25.0), ("25 kHz +35 dB", 25e3, 35.0)):
        nb = g * L.dbm_to_vpeak(lv + up) * (1 + 0.5 * np.sin(2 * np.pi * 1900 * t)) * rot * np.exp(2j * np.pi * df * t)
        a0 = sweep_ch("air_nb0", mk(lv, np.random.default_rng(3)), ch)["l"][200:]
        a1 = sweep_ch("air_nb1", mk(lv, np.random.default_rng(3), nb), ch)["l"][200:]
        res[name] = (L.sinad_db(a0, fs_a, 1000.0), L.sinad_db(a1, fs_a, 1000.0))
        print(f"    neighbour {name}: SINAD {res[name][0]:.1f} -> {res[name][1]:.1f} dB")
    print(f"    10 dB SINAD: RTL {s10:.1f} dBm, reference {s10_ref:.1f} dBm")
    # mutation: the mixer's bare 9-bit sine table (its phase steps modulate the strong neighbour into the channel)
    nb = g * L.dbm_to_vpeak(lv + 25.0) * (1 + 0.5 * np.sin(2 * np.pi * 1900 * t)) * rot * np.exp(2j * np.pi * 8333.0 * t)
    a1m = sweep_ch("air_nbm", mk(lv, np.random.default_rng(3), nb), ch, mutate="mix_nco_9bit")["l"][200:]
    mut_nb = L.sinad_db(a1m, fs_a, 1000.0)
    print(f"    mutation mix_nco_9bit: 8.33 kHz neighbour +25 dB: SINAD {res['8.33 kHz +25 dB'][0]:.1f} -> {mut_nb:.1f} dB")

    checks = {
        "tuning error < 30 Hz (24-bit NCO, 23.8 Hz steps)": abs(cal["tune_err_hz"]) < 30.0,
        "noise density within 2 dB of the cascade": abs(10 * np.log10(cal["n0"] / cal["n0_pred"])) < 2.0,
        "10 dB SINAD within 2 dB of the reference": abs(s10 - s10_ref) <= 2.0,
        "SINAD >= 30 dB at high level": max(rtl) >= 30.0,
        "8.33 kHz neighbour +25 dB costs <= 3 dB": res["8.33 kHz +25 dB"][0] - res["8.33 kHz +25 dB"][1] <= 3.0,
        "25 kHz neighbour +35 dB costs <= 3 dB": res["25 kHz +35 dB"][0] - res["25 kHz +35 dB"][1] <= 3.0,
        "mutation mix_nco_9bit: the 8.33 kHz neighbour costs > 3 dB": res["8.33 kHz +25 dB"][0] - mut_nb > 3.0,
    }

    fig, ax = plt.subplots(1, 2, figsize=(12, 4.4))
    ax[0].plot(f_s / 1e3, p_s - p_s.max(), lw=0.8)
    ax[0].set_xlim(-15, 40); ax[0].set_ylim(-100, 5)
    ax[0].set_title("Kria input (full chain): -90 dBm, +25 dB at 8.33 kHz, +35 dB at 25 kHz")
    ax[0].set_xlabel("Offset from 121.500 MHz (kHz)"); ax[0].set_ylabel("dB")
    ax[1].plot(levels, rtl, "o-", label="Kria RTL"); ax[1].plot(levels, ref, "s--", label="floating-point reference")
    ax[1].axhline(10, color="grey", ls=":")
    ax[1].set_title("SINAD vs antenna level (30 % AM, 1 kHz)"); ax[1].set_xlabel("dBm"); ax[1].set_ylabel("dB")
    ax[1].legend()
    for a in ax:
        a.grid(alpha=0.3)
    fig.suptitle("Airband AM, 121.500 MHz: AD9484 -> AERIS DDC -> link -> kria_channel_rx")
    fig.tight_layout()
    fig.savefig(os.path.join(L.IMG_DIR, "g8_airband_am.png"), dpi=150); plt.close(fig)
    return dict(case="air", cal=cal, levels=levels.tolist(), sinad_rtl=rtl, sinad_ref=ref, sens10_rtl_dbm=s10,
                sens10_ref_dbm=s10_ref, neighbours=res, checks=checks, passed=all(checks.values()),
                figure="docs/img/sim/g8_airband_am.png")


def case_nbfm():
    print("\n=== PMR446 NBFM, 446.00625 MHz through the converter (IF 135 MHz): CTCSS 100 Hz ===")
    f_if, fs_k = 135.0e6, VU["fs_k"]
    # 25 MSPS / 640 = 39.1 kS/s: the channel filter passes +/-6.25 kHz and puts the 12.5 kHz neighbour at 0.32
    cic, fir = 640, 2
    fs_a = fs_k / cic / fir                               # 19.5 kS/s audio
    alpha = int(round((1 - np.exp(-1 / (fs_a * 750e-6))) * 32768))  # 750 us de-emphasis, the PMR446 audio slope
    c100 = int(round(2 * np.cos(2 * np.pi * 100.0 / fs_a) * 16384)) & 0xFFFF
    n_g = int(round(fs_a * 0.1))                          # 100 ms Goertzel block
    cal = vu_calibrate(f_if, ["KRIA_CTRL=00000031"], "uhf", df=100e3)
    base = ["KRIA_CTRL=00000031", f"KRIA_DECIM={decim_word(cic, fir, cal, fs_k)}",
            f"KRIA_DEMOD={c100:04x}{alpha:04x}", f"KRIA_CTCSS=0000{n_g:04x}"]
    g, n0 = cal["gain_codes_per_v"], cal["n0"]
    off = f_if - cal["f_nco"]
    nco = f"KRIA_NCO={ftw(off if not cal['inverted'] else -off, fs_k):08x}"

    def cj(z):
        return np.conj(z) if cal["inverted"] else z

    n_sw = int(0.4 * fs_k)
    t = np.arange(n_sw) / fs_k
    rot = np.exp(2j * np.pi * off * t)

    def nbfm(lv, rng, tone=True, extra=0):
        inst = 1500.0 * np.sin(2 * np.pi * 1000 * t) + (300.0 * np.sin(2 * np.pi * 100.0 * t) if tone else 0)
        phi = 2 * np.pi * np.cumsum(inst) / fs_k
        return cj(g * L.dbm_to_vpeak(lv) * np.exp(1j * phi) * rot + extra) + L.complex_noise(n_sw, n0, fs_k, rng)

    # CTCSS threshold: software's setting, from the Goertzel power with and without the tone at a strong level
    ch0 = kria_to_ch(base + [nco, "KRIA_THR=00000001"], fs_k)
    p_tone = sweep_ch("nb_thr1", nbfm(-80.0, np.random.default_rng(1)), ch0)
    p_none = sweep_ch("nb_thr0", nbfm(-80.0, np.random.default_rng(2), tone=False), ch0)
    pw1 = float(np.median(p_tone["ctcss_pw"][len(p_tone["ctcss_pw"]) // 2:]))
    pw0 = float(np.median(p_none["ctcss_pw"][len(p_none["ctcss_pw"]) // 2:]))
    thr = int(np.sqrt(max(pw1, 1.0) * max(pw0, 1.0)))
    print(f"    CTCSS Goertzel power: tone {pw1:.0f}, none {pw0:.0f}: threshold {thr}")
    kria = base + [nco, f"KRIA_THR={thr:08x}"]
    ch = kria_to_ch(kria, fs_k)

    # scene through the full chain: speech, CTCSS, a neighbour 40 dB up at +12.5 kHz
    fs = VU["fs_adc"]
    n = int(1.2e-3 * fs)
    v_rf, _, _ = gs.gen_vhf_uhf(n, fs=fs, f_if=f_if, lvl_dbm=-95.0, seed=505)
    iq, _ = vu_e2e("nbscene", v_rf, f_if, kria, 1200, np.random.default_rng(505), "uhf", outs=("ddc",))
    f_s, p_s = psd_db(cj(L.settled(iq)), fs_k, 16384)     # the DDC's conjugate turned back: offsets read as at RF

    def ref_fn(x):
        return L.ref_fm(cj(x) * np.conj(rot), fs_k, cic * fir, 5.5e3, deemph_us=750)

    levels = np.arange(-140.0, -94.0, 3.0)
    rtl, ref = level_sweep("nb_sw", levels, lambda lv, rng: nbfm(lv, rng), ch, ref_fn, fs_a, 1000.0,
                           settle=600, lo=300.0, hi=3000.0)
    s12, s12_ref = L.level_at(levels, rtl, 12.0), L.level_at(levels, ref, 12.0)
    # CTCSS at the 12 dB SINAD level, and no false detection without the tone
    det = sweep_ch("nb_ct1", nbfm(s12, np.random.default_rng(5)), ch)["ctcss"]
    fa = sweep_ch("nb_ct0", nbfm(s12 + 20, np.random.default_rng(6), tone=False), ch)["ctcss"]
    det_ok = bool(det[len(det) // 2:].mean() > 0.9)
    fa_ok = bool(fa[len(fa) // 2:].mean() < 0.05)
    # neighbour 40 dB up at +12.5 kHz with the wanted 3 dB above its 12 dB point. The unwanted signal is the
    # EN 300 296 one: 400 Hz at 12 % of the channel spacing (1.5 kHz). A wider modulation puts the neighbour's own
    # sidebands inside the wanted channel, where no channel filter can remove them, so the RTL's cost is also
    # compared with the reference demodulator's on the same input.
    lv = s12 + 3.0
    phn = 2 * np.pi * np.cumsum(1500.0 * np.sin(2 * np.pi * 400.0 * t)) / fs_k
    nb = g * L.dbm_to_vpeak(lv + 40) * np.exp(1j * phn) * rot * np.exp(2j * np.pi * 12.5e3 * t)
    x0, x1 = nbfm(lv, np.random.default_rng(8)), nbfm(lv, np.random.default_rng(8), extra=nb)
    a0 = sweep_ch("nb_a0", x0, ch)["l"][600:]
    a1 = sweep_ch("nb_a1", x1, ch)["l"][600:]
    acs = (L.sinad_db(a0, fs_a, 1000.0, 300.0, 3000.0), L.sinad_db(a1, fs_a, 1000.0, 300.0, 3000.0))
    acs_ref = (L.sinad_db(ref_fn(x0)[600:], fs_a, 1000.0, 300.0, 3000.0),
               L.sinad_db(ref_fn(x1)[600:], fs_a, 1000.0, 300.0, 3000.0))
    # mutation: the mixer's products truncated instead of rounded (the DC offset that cost 6.5 dB), at 12 dB SINAD
    xt = nbfm(s12, np.random.default_rng(10))
    trunc = (L.sinad_db(sweep_ch("nb_t0", xt, ch)["l"][600:], fs_a, 1000.0, 300.0, 3000.0),
             L.sinad_db(sweep_ch("nb_t1", xt, ch, mutate="mix_truncate")["l"][600:], fs_a, 1000.0, 300.0, 3000.0))
    print(f"    mutation mix_truncate at {s12:.1f} dBm: SINAD {trunc[0]:.1f} -> {trunc[1]:.1f} dB")
    # mutation: a corrupted CORDIC arctangent stage, 30 dB above the 12 dB point
    xm = nbfm(s12 + 30.0, np.random.default_rng(9))
    mut = (L.sinad_db(sweep_ch("nb_m0", xm, ch)["l"][600:], fs_a, 1000.0, 300.0, 3000.0),
           L.sinad_db(sweep_ch("nb_m1", xm, ch, mutate="wrong_atan_lut")["l"][600:], fs_a, 1000.0, 300.0, 3000.0))
    print(f"    mutation wrong_atan_lut at {s12 + 30:.1f} dBm: SINAD {mut[0]:.1f} -> {mut[1]:.1f} dB")
    print(f"    12 dB SINAD: RTL {s12:.1f} dBm, reference {s12_ref:.1f} dBm; CTCSS at it {det_ok}, no false "
          f"detection {fa_ok}; +40 dB at 12.5 kHz: {acs[0]:.1f} -> {acs[1]:.1f} dB (reference {acs_ref[0]:.1f} -> "
          f"{acs_ref[1]:.1f}); DDC mirror "
          f"{cal['ddc_image_db']:.1f} dB down")

    checks = {
        "tuning error < 30 Hz (24-bit NCO, 23.8 Hz steps)": abs(cal["tune_err_hz"]) < 30.0,
        "noise density within 2 dB of the cascade": abs(10 * np.log10(cal["n0"] / cal["n0_pred"])) < 2.0,
        "12 dB SINAD within 2 dB of the reference": abs(s12 - s12_ref) <= 2.0,
        "CTCSS detected at the 12 dB SINAD level": det_ok,
        "no CTCSS false detection without the tone": fa_ok,
        "+40 dB at 12.5 kHz costs <= 3 dB, and <= the reference's cost + 1 dB":
            acs[0] - acs[1] <= 3.0 and (acs[0] - acs[1]) - (acs_ref[0] - acs_ref[1]) <= 1.0,
        "mutation mix_truncate costs >= 3 dB at the 12 dB SINAD level": trunc[0] - trunc[1] >= 3.0,
        "DDC mirror >= 50 dB down": cal["ddc_image_db"] >= 50.0,
        "mutation wrong_atan_lut costs >= 6 dB at high level": mut[0] - mut[1] >= 6.0,
    }

    fig, ax = plt.subplots(1, 2, figsize=(12, 4.4))
    ax[0].plot(f_s / 1e3, p_s - p_s.max(), lw=0.8)
    ax[0].set_xlim(-30, 40); ax[0].set_ylim(-100, 5)
    ax[0].set_title("Kria input (full chain scene): -95 dBm NBFM + CTCSS and a neighbour")
    ax[0].set_xlabel("Offset from the IF (kHz)"); ax[0].set_ylabel("dB")
    ax[1].plot(levels, rtl, "o-", label="Kria RTL"); ax[1].plot(levels, ref, "s--", label="floating-point reference")
    ax[1].axhline(12, color="grey", ls=":")
    ax[1].set_title("SINAD vs antenna level (1 kHz at 1.5 kHz deviation)"); ax[1].set_xlabel("dBm")
    ax[1].set_ylabel("dB"); ax[1].legend()
    for a in ax:
        a.grid(alpha=0.3)
    fig.suptitle("PMR446 NBFM via the converter: AD9484 -> AERIS DDC -> link -> kria_channel_rx (NBFM, CTCSS)")
    fig.tight_layout()
    fig.savefig(os.path.join(L.IMG_DIR, "g8_vhf_uhf_nbfm.png"), dpi=150); plt.close(fig)
    return dict(case="nbfm", cal=cal, levels=levels.tolist(), sinad_rtl=rtl, sinad_ref=ref, sens12_rtl_dbm=s12,
                sens12_ref_dbm=s12_ref, ctcss_threshold=thr, ctcss_det=det_ok, ctcss_no_false=fa_ok,
                adjacent_40db=acs, adjacent_40db_ref=acs_ref, mix_truncate=trunc, checks=checks, passed=all(checks.values()),
                figure="docs/img/sim/g8_vhf_uhf_nbfm.png")


ADSB_PRE = [1, 0, 1, 0, 0, 0, 0, 1, 0, 1, 0, 0, 0, 0, 0, 0]


def adsb_chips(frame):
    ch = list(ADSB_PRE)
    for b in range(111, -1, -1):
        ch += [1, 0] if (frame >> b) & 1 else [0, 1]
    return np.array(ch, float)


def adsb_crc_ok(bits):
    poly = 0x1FFF409
    v = 0
    for b in bits:
        v = (v << 1) | int(b)
    for k in range(111, 23, -1):
        if (v >> k) & 1:
            v ^= poly << (k - 24)
    return (v & 0xFFFFFF) == 0


def adsb_burst(frames, fs, start_s, spacing_s, n_tot, rng, amp):
    """Complex envelope of a train of frames at fs (chip edges at their true, fractional sample times), each with
    a random carrier phase; returns the waveform and each frame's start time in samples."""
    x = np.zeros(n_tot, complex)
    starts = []
    t = np.arange(n_tot) / fs
    for k, fr in enumerate(frames):
        t0 = start_s + k * spacing_s + rng.uniform(0, 0.5e-6)    # sub-chip offset
        ch = adsb_chips(fr)
        idx = np.floor((t - t0) / 0.5e-6).astype(int)
        m = (idx >= 0) & (idx < len(ch))
        env = np.zeros(n_tot)
        env[m] = ch[idx[m]]
        x += amp * env * np.exp(1j * rng.uniform(0, 2 * np.pi))
        starts.append(t0 * fs)
    return x, starts


def adsb_ref_decode(x, fs, starts, frames):
    """Reference: the frame's timing known exactly, |x| averaged over each chip, PPM decisions, CRC."""
    ok = 0
    for s0, fr in zip(starts, frames):
        a = np.abs(x)
        cs = 0.5e-6 * fs
        bits = []
        for b in range(112):
            c1 = s0 + (16 + 2 * b) * cs
            v1 = a[int(np.ceil(c1)):int(np.floor(c1 + cs))].mean()
            v2 = a[int(np.ceil(c1 + cs)):int(np.floor(c1 + 2 * cs))].mean()
            bits.append(1 if v1 >= v2 else 0)
        val = 0
        for bt in bits:
            val = (val << 1) | bt
        ok += int(adsb_crc_ok(bits) and val == fr)
    return ok


def case_adsb():
    print("\n=== ADS-B 1090 MHz through the converter (IF 135 MHz): Mode-S DF17, kria_adsb_rx ===")
    f_if, fs_k = 135.0e6, VU["fs_k"]
    cal = vu_calibrate(f_if, ["KRIA_CTRL=00000081", "KRIA_ADSB=0001008C"], "adsb", df=100e3)
    g, n0 = cal["gain_codes_per_v"], cal["n0"]
    sigma = np.sqrt(n0 * fs_k)                      # complex noise rms per sample at the Kria input
    # software's floor on the preamble: four pulses, each twice the noise envelope's mean (0.886 sigma). The
    # decoder's own test (pulses at least 2/3 of the twelve gaps, about 7 sigma on noise) sets the sensitivity;
    # the floor only has to stay under a weak frame's pulses (four times the mean, 14 sigma, missed every frame
    # at -82 dBm, where the four pulses sum to about 13 sigma)
    thr = int(min(0xFFFF, 4 * 2 * 0.886 * sigma))
    kria = ["KRIA_CTRL=00000081", f"KRIA_ADSB={thr:04x}8C"]
    frames = [0x8D4840D6202CC371C32CE0576098, gs.encode_mode_s_crc24(0x8D4CA251204994B1C36E60),
              gs.encode_mode_s_crc24(0x8D3C674B58B9828D58A322)]

    # scene through the full chain: three frames at -82 dBm 150 us apart, a weaker colliding preamble
    fs = VU["fs_adc"]
    n = int(0.52e-3 * fs)
    v_rf, _, meta = gs.gen_adsb(n, fs=fs, f_if=f_if, lvl_dbm=-82.0, seed=606)
    iq, files = vu_e2e("adsbscene", v_rf, f_if, kria, 540, np.random.default_rng(606), "adsb",
                       outs=("ddc", "adsb"))
    got = []
    for ln in open(files["adsb"]):
        p = ln.split()
        if p and p[0] == "1":
            got.append(int(p[1], 16))
    scene_ok = sum(1 for fr in meta["frames"] if fr in got)
    print(f"    scene: {scene_ok} of {len(meta['frames'])} frames decoded CRC-good through the full chain")
    # mutation: the DSP suite's input without its beat queue (beats arriving back to back were lost)
    _, files_m = vu_e2e("adsbscene_m", v_rf, f_if, kria, 540, np.random.default_rng(606), "adsb",
                        outs=("ddc", "adsb"), mutate="unpack_no_queue")
    got_m = [int(ln.split()[1], 16) for ln in open(files_m["adsb"]) if ln.split() and ln.split()[0] == "1"]
    scene_m = sum(1 for fr in meta["frames"] if fr in got_m)
    print(f"    mutation unpack_no_queue: {scene_m} of {len(meta['frames'])} frames")
    sc = L.settled(iq)

    # Pd vs level on kria_adsb_rx: 40 frames per level, random sub-chip timing and carrier phase
    adsb_args = ["SWEEP_MODE=ADSB", f"ADSB_OSR={0x8C}", f"ADSB_THR={thr}", f"IN_RATE_HZ={int(fs_k)}"]
    levels = np.arange(-100.0, -77.0, 2.0)
    nfr = 40
    pd, pd_ref, pd_mut, pd_strict = [], [], [], []
    for lv in levels:
        rng = np.random.default_rng(int(-lv * 7))
        fr_list = [frames[k % 3] for k in range(nfr)]
        n_tot = int((nfr * 150e-6 + 50e-6) * fs_k)
        amp = g * L.dbm_to_vpeak(lv)
        x, starts = adsb_burst(fr_list, fs_k, 20e-6, 150e-6, n_tot, rng, amp)
        x = (np.conj(x) if cal["inverted"] else x) + L.complex_noise(n_tot, n0, fs_k, rng)
        inf, outf = L.wpath("adsb_in.txt"), L.wpath("adsb_out.txt")
        L.write_iq(inf, x)
        res = []
        for mut in ("", "one_phase", "strict_preamble"):
            L.run_bench("tb_dsp_sweeps", "g8", [f"IN_FILE={inf}", f"OUT_FILE={outf}"] + adsb_args, mutate=mut)
            okc = 0
            for ln in open(outf):
                p = ln.split()
                if p and p[0] == "1" and int(p[1], 16) in frames:
                    okc += 1
            res.append(min(okc, nfr) / nfr)
        pd.append(res[0]); pd_mut.append(res[1]); pd_strict.append(res[2])
        pd_ref.append(adsb_ref_decode(x, fs_k, starts, fr_list) / nfr)
        print(f"    {lv:6.1f} dBm  Pd RTL {pd[-1]:.2f}  reference {pd_ref[-1]:.2f}  one grid {pd_mut[-1]:.2f}  "
              f"strict preamble {pd_strict[-1]:.2f}")
    l90, l90_ref = L.level_at(levels, pd, 0.9), L.level_at(levels, pd_ref, 0.9)
    print(f"    90 % decode: RTL {l90} dBm, reference {l90_ref} dBm")

    checks = {
        "tuning error < 30 Hz (24-bit NCO, 23.8 Hz steps)": abs(cal["tune_err_hz"]) < 30.0,
        "noise density within 2 dB of the cascade": abs(10 * np.log10(cal["n0"] / cal["n0_pred"])) < 2.0,
        "scene: all three frames decoded through the full chain": scene_ok == len(meta["frames"]),
        "mutation unpack_no_queue decodes fewer frames in the scene": scene_m < scene_ok,
        "90 % decode within 3 dB of the timing-aware reference": l90 is not None and l90_ref is not None
        and l90 - l90_ref <= 3.0,
        "90 % decode at or below -84 dBm": l90 is not None and l90 <= -84.0,
        "mutation one_phase decodes less somewhere": any(m < p - 0.1 for p, m in zip(pd, pd_mut)),
        "mutation strict_preamble decodes less somewhere": any(m < p - 0.1 for p, m in zip(pd, pd_strict)),
    }

    fig, ax = plt.subplots(1, 2, figsize=(12, 4.4))
    a = np.abs(sc)
    tt = np.arange(len(a)) / fs_k * 1e6
    ax[0].plot(tt, a, lw=0.6)
    ax[0].set_title(f"Kria input envelope (full chain): three frames at -82 dBm, {scene_ok}/3 decoded")
    ax[0].set_xlabel("us"); ax[0].set_ylabel("|I + jQ| (codes)")
    ax[1].plot(levels, pd, "o-", label="kria_adsb_rx (four grids)")
    ax[1].plot(levels, pd_ref, "s--", label="reference, timing known")
    ax[1].plot(levels, pd_mut, "^:", label="mutation: one grid")
    ax[1].plot(levels, pd_strict, "v:", label="mutation: strict preamble")
    ax[1].axhline(0.9, color="grey", ls=":")
    ax[1].set_title("Frames decoded CRC-good vs antenna level"); ax[1].set_xlabel("dBm"); ax[1].set_ylabel("Pd")
    ax[1].legend()
    for a_ in ax:
        a_.grid(alpha=0.3)
    fig.suptitle("ADS-B 1090 MHz via the converter: AD9484 -> AERIS DDC -> link -> kria_adsb_rx")
    fig.tight_layout()
    fig.savefig(os.path.join(L.IMG_DIR, "g8_adsb_1090.png"), dpi=150); plt.close(fig)
    return dict(case="adsb", cal=cal, threshold=thr, scene_decoded=scene_ok, levels=levels.tolist(), pd=pd,
                pd_ref=pd_ref, pd_one_grid=pd_mut, pd_strict_preamble=pd_strict, l90_dbm=l90, l90_ref_dbm=l90_ref, checks=checks,
                passed=all(checks.values()), figure="docs/img/sim/g8_adsb_1090.png")


# ====================================================================== radar (AD9484 at 120 MHz IF, AERIS DDC)
RAD_N, RAD_M = 64, 16                     # range samples per chirp, chirps per CPI (kria_radar_proc)
RAD_FS = 25e6                             # stream rate; one chirp = 64 samples = 2.56 us


def rad_scene_adc(targets, n_cpi, snr_db, seed, f_if=120e6, fs=400e6):
    """De-chirped FMCW echoes at the ADC: each target a beat tone at range bin r (r/64 of the stream rate) whose
    phase steps by 2 pi d/16 per chirp (Doppler bin d), on the 120 MHz IF; noise for snr_db per stream sample
    against the first target. Sample 0 is the start of a chirp."""
    rng = np.random.default_rng(seed)
    n = int(n_cpi * RAD_M * RAD_N * fs / RAD_FS)
    t = np.arange(n) / fs
    chirp = np.floor(t / (RAD_N / RAD_FS))
    bb = np.zeros(n, complex)
    for (rb, db, rel_db) in targets:
        a = 10 ** (rel_db / 20)
        # bins N/2..N-1 are the negative beat frequencies: a 25 MSPS complex stream holds only +/-12.5 MHz, and the
        # radar DDC's anti-alias filter (ddc_hb4) removes anything placed above that
        rs = (rb + RAD_N // 2) % RAD_N - RAD_N // 2
        bb += a * np.exp(2j * np.pi * (rs / RAD_N * RAD_FS * t + db / RAD_M * chirp))
    a0 = 0.30                                              # first target at 0.30 of full scale
    v = a0 * np.real(bb * np.exp(2j * np.pi * f_if * t))
    # noise: snr_db in the 25 MSPS stream against the first target's power a0^2 / 2 per real sample... the
    # stream keeps 25/400 of the real noise's bandwidth (one side, complex), so scale by 400/25
    p_sig = a0 ** 2 / 2
    p_n = p_sig / 10 ** (snr_db / 10) * (fs / RAD_FS) / 2
    v = v + rng.standard_normal(n) * np.sqrt(p_n)
    return np.clip(np.round(128 + 127 * v), 0, 255).astype(np.uint8)


def rad_ref(cpi, alpha_q8, min_pwr, win=True):
    """kria_radar_proc in floating point: Hann (Q15 tables) on both FFTs, /2 per butterfly stage, |Z|^2, range
    CA-CFAR (guard 1, train 4 each side, circular), threshold alpha/256 x mean."""
    x = cpi.reshape(RAD_M, RAD_N)
    w64 = np.floor(0.5 * (1 - np.cos(2 * np.pi * np.arange(RAD_N) / RAD_N)) * 32767) / 32768
    w16 = np.floor(0.5 * (1 - np.cos(2 * np.pi * np.arange(RAD_M) / RAD_M)) * 32767) / 32768
    if win:
        x = x * w64[None, :]
    R = np.fft.fft(x, axis=1) / RAD_N
    if win:
        R = R * w16[:, None]
    D = np.fft.fft(R, axis=0) / RAD_M
    P = np.abs(D.T) ** 2                                   # [range, doppler]
    det = np.zeros_like(P, bool)
    for r in range(RAD_N):
        tr = sum(P[(r + k) % RAD_N] for k in (-5, -4, -3, -2, 2, 3, 4, 5)) / 8
        det[r] = (P[r] > tr * alpha_q8 / 256) & (P[r] >= min_pwr)
    return P, det


def rad_sweep(tag, cpis, alpha_q8, min_pwr, mutate=""):
    """CPIs (each 1024 complex samples, chirp-major) through kria_radar_proc; returns [(P, det)] per CPI."""
    inf, outf = L.wpath(f"{tag}_in.txt"), L.wpath(f"{tag}_out.txt")
    L.write_iq(inf, np.concatenate(cpis))
    L.run_bench("tb_dsp_sweeps", "g8", ["SWEEP_MODE=RADAR", f"IN_FILE={inf}", f"OUT_FILE={outf}",
                                         f"RAD_ALPHA={alpha_q8}", f"RAD_MIN={min_pwr}"], mutate=mutate)
    rows = [ln.split() for ln in open(outf) if len(ln.split()) == 4]
    out = []
    for k in range(len(rows) // (RAD_N * RAD_M)):
        P = np.zeros((RAD_N, RAD_M)); det = np.zeros((RAD_N, RAD_M), bool)
        for r_, d_, p_, t_ in rows[k * RAD_N * RAD_M:(k + 1) * RAD_N * RAD_M]:
            P[int(r_), int(d_)] = float(p_); det[int(r_), int(d_)] = t_ == "1"
        out.append((P, det))
    if len(out) != len(cpis):
        raise RuntimeError(f"radar sweep returned {len(out)} CPIs for {len(cpis)}")
    return out


def case_radar():
    print("\n=== Radar: FMCW scene through AD9484 -> AERIS DDC (120 MHz IF) -> link -> kria_radar_proc ===")
    alpha, min_pwr = 1536, 2000              # threshold 6x the training mean (7.8 dB)
    truth = [(12, 3, 0.0), (40, 12, -30.0), (6, 0, -10.0)]
    # 20 dB per stream sample on the strongest target: after the 2-D FFT (+30 dB, -3.5 dB for the two Hann
    # windows) the -30 dB target stands 16.6 dB over the noise. The scene's CFAR is set for Pfa 1e-4 over eight
    # training cells (alpha = 8 (Pfa^-1/8 - 1) = 17.3, 12.4 dB), so about 0.1 false detection per 1024-cell map,
    # and its absolute floor is lowered to 16 (RADAR_ALPHA[31:16] = 1): the fixed 20000 sat above the -30 dB
    # target's cell power (about 15300 at 0.30 of full scale for the first target)
    alpha_scene = 4427
    codes = rad_scene_adc(truth, n_cpi=8, snr_db=20.0, seed=707)
    hexf = L.wpath("radscene_adcr.hex")
    gs.write_adcr_hex(hexf, codes)
    rd = L.wpath("radscene_rd.txt")
    ddc = L.wpath("radscene_ddc.txt")
    dly = int(os.environ.get("G8_RAD_DLY", "3"))
    L.run_bench("tb_system_signals", "g8rad", [
        "CASE=RADAR", "RUN_US=600", "SIG_WAIT_ARM", f"ADCR_SIG_FILE={hexf}", f"OUT_RADAR={rd}", f"OUT_DDC={ddc}",
        "ARTIX_RAD_CTRL=00000001", f"RADAR_SYNC_DLY={dly}", "KRIA_CTRL=00002301",
        f"RAD_ALPHA={(1 << 16) | alpha_scene:08x}"],
        defines=VU["define"])
    rows = [ln.split() for ln in open(rd) if len(ln.split()) == 4]
    # the first CPI after the stimulus starts holds the DDC filters' start-up transient (Doppler sidelobes near
    # -30 dBc even in floating point); kria_radar_proc takes about five CPIs per map, so the run is long enough
    # for its second map, from a CPI in steady state, and that one is judged
    if len(rows) < 2 * RAD_N * RAD_M:
        raise RuntimeError(f"radar scene: {len(rows)} cells, expected two CPIs")
    rows = rows[RAD_N * RAD_M:2 * RAD_N * RAD_M]         # the second map (a third, if any, is after the stimulus)
    P = np.zeros((RAD_N, RAD_M)); det = np.zeros((RAD_N, RAD_M), bool)
    for r_, d_, p_, t_ in rows:
        P[int(r_), int(d_)] = float(p_); det[int(r_), int(d_)] = t_ == "1"
    pk = np.unravel_index(np.argmax(P), P.shape)
    # the AERIS DDC delivers the conjugate spectrum (tb_e2e checks it: +1.5625 MHz lands at bin -4), so a beat
    # tone above the IF at range bin r, Doppler bin d appears at (-r mod 64, -d mod 16)
    seen = [((-rb) % RAD_N, (-db) % RAD_M, lv_) for rb, db, lv_ in truth]

    def near(rb, db):
        return any(det[(rb + i) % RAD_N, (db + j) % RAD_M] for i in (-1, 0, 1) for j in (-1, 0, 1))
    found = [near(rb, db) for rb, db, _ in seen]
    false = int(det.sum()) - sum(int(det[(rb + i) % RAD_N, (db + j) % RAD_M]) for rb, db, _ in seen
                                 for i in (-1, 0, 1) for j in (-1, 0, 1))
    print(f"    scene: peak at {pk}, targets found {found}, detections elsewhere {false}")

    # Pd vs SNR on kria_radar_proc, against the floating-point model with the same window and CFAR
    snrs = np.arange(-30.0, -9.0, 2.0)                    # per stream sample; the 2-D FFT adds 30 dB less windowing
    trials = 96                                         # 24 left about 1 dB of scatter on the Pd 0.5 difference
    pd, pd_ref, pd_mut = [], [], []
    rng = np.random.default_rng(31)
    rr, dd = 21, 5
    n_i = np.arange(RAD_N)[None, :]; m_i = np.arange(RAD_M)[:, None]
    tone = np.exp(2j * np.pi * (rr * n_i / RAD_N + dd * m_i / RAD_M)).reshape(-1)
    amp = 4000.0
    for snr in snrs:
        sig = amp / 10 ** (snr / 20) / np.sqrt(2)
        cpis = [amp * tone * np.exp(2j * np.pi * rng.uniform()) + sig * (rng.standard_normal(RAD_N * RAD_M)
                + 1j * rng.standard_normal(RAD_N * RAD_M)) for _ in range(trials)]
        cpis = [np.round(c) for c in cpis]
        res = rad_sweep("radpd", cpis, alpha, 0)
        resm = rad_sweep("radpd", cpis, alpha, 0, mutate="wrong_twiddle_sign")
        pd.append(np.mean([d[rr, dd] for _, d in res]))
        pd_mut.append(np.mean([d[rr, dd] for _, d in resm]))
        pd_ref.append(np.mean([rad_ref(c, alpha, 0)[1][rr, dd] for c in cpis]))
        print(f"    SNR {snr:6.1f} dB  Pd RTL {pd[-1]:.2f}  model {pd_ref[-1]:.2f}  wrong twiddle sign {pd_mut[-1]:.2f}")
    # false alarms on noise only
    noise = [np.round(1000 * (rng.standard_normal(RAD_N * RAD_M) + 1j * rng.standard_normal(RAD_N * RAD_M)))
             for _ in range(16)]
    resn = rad_sweep("radpfa", noise, alpha, 0)
    pfa = float(np.mean([d.mean() for _, d in resn]))
    pfa_ref = float(np.mean([rad_ref(c, alpha, 0)[1].mean() for c in noise]))
    s50, s50_ref = L.level_at(snrs, pd, 0.5), L.level_at(snrs, pd_ref, 0.5)
    print(f"    Pd 0.5 at {s50} dB (model {s50_ref} dB); Pfa {pfa:.2e} (model {pfa_ref:.2e})")

    # beam: eight elements at half a wavelength, ADAR1000 phase steps of 360/128 deg; a target at -15 deg; one
    # CPI per beam through kria_radar_proc, the beam with the strongest detection gives the angle
    th_t = -15.0
    beams = np.arange(-60.0, 61.0, 7.5)
    step = 360.0 / 128
    pk_b = []
    cpis = []
    for b in beams:
        ph = np.round(np.arange(8) * 180 * np.sin(np.radians(b)) / step) * step
        af = np.abs(np.sum(np.exp(1j * np.radians(np.arange(8) * 180 * np.sin(np.radians(th_t)) - ph)))) / 8
        cpis.append(np.round(amp * af * tone + 200 * (rng.standard_normal(RAD_N * RAD_M)
                                                       + 1j * rng.standard_normal(RAD_N * RAD_M))))
    resb = rad_sweep("radbeam", cpis, alpha, 0)
    pk_b = [P_[rr, dd] for P_, _ in resb]
    th_est = float(beams[int(np.argmax(pk_b))])
    print(f"    beam scan: strongest at {th_est:+.1f} deg (target at {th_t:+.1f} deg)")

    checks = {
        "scene: the strongest cell is the 0 dB target (12, 3), seen at (52, 13)": tuple(int(v) for v in pk) == seen[0][:2],
        "scene: all three targets detected, the -30 dB one too": all(found),
        "scene: no more than 3 detections away from the targets": false <= 3,
        "Pd 0.5 within 1 dB of the floating-point model": s50 is not None and s50_ref is not None
        and abs(s50 - s50_ref) <= 1.0,
        "Pfa within a factor of 3 of the model": pfa <= 3 * max(pfa_ref, 1.0 / (16 * RAD_N * RAD_M)),
        "beam within one step (7.5 deg) of the target": abs(th_est - th_t) <= 7.5,
        "mutation wrong_twiddle_sign loses the target": max(pd_mut) < 0.5,
    }

    fig, ax = plt.subplots(2, 2, figsize=(12, 8.2))
    Pd_ = 10 * np.log10(np.maximum(P, 1)); Pd_ -= Pd_.max()
    im = ax[0, 0].imshow(np.roll(Pd_, 8, axis=1).T, aspect="auto", origin="lower", vmin=-60, vmax=0,
                         extent=(-0.5, 63.5, -8.5, 7.5), cmap="viridis")
    dr, dd_ = np.nonzero(det)
    ax[0, 0].scatter(dr, ((dd_ + 8) % 16) - 8, s=18, facecolors="none", edgecolors="w", label="CFAR detections")
    ax[0, 0].scatter([t[0] for t in seen], [((t[1] + 8) % 16) - 8 for t in seen], marker="x", c="r",
                     label="truth (conjugate stream)")
    ax[0, 0].set_title("Range-Doppler map (full chain, kria_radar_proc)"); ax[0, 0].set_xlabel("range bin")
    ax[0, 0].set_ylabel("Doppler bin"); ax[0, 0].legend(loc="upper right", fontsize=8)
    fig.colorbar(im, ax=ax[0, 0], label="dB")
    d_cut = seen[0][1]                                   # the strongest target's Doppler bin, as the map shows it
    ax[0, 1].plot(np.arange(RAD_N), Pd_[:, d_cut], lw=1.2)
    ax[0, 1].set_title(f"Range cut at Doppler bin {((d_cut + 8) % 16) - 8} (the 0 dB target)"); ax[0, 1].set_xlabel("range bin"); ax[0, 1].set_ylabel("dB")
    ax[1, 0].plot(snrs, pd, "o-", label="kria_radar_proc")
    ax[1, 0].plot(snrs, pd_ref, "s--", label="floating-point model")
    ax[1, 0].plot(snrs, pd_mut, "^:", label="mutation: twiddle sign")
    ax[1, 0].set_title(f"Pd vs SNR per sample, CA-CFAR 6x (Pfa {pfa:.1e})"); ax[1, 0].set_xlabel("dB")
    ax[1, 0].legend()
    ax[1, 1].plot(beams, 10 * np.log10(np.maximum(pk_b, 1)) - 10 * np.log10(max(pk_b)), "o-")
    ax[1, 1].axvline(th_t, color="r", ls=":")
    ax[1, 1].set_title(f"Beam scan (8 elements, 2.8 deg phase steps): peak {th_est:+.1f} deg")
    ax[1, 1].set_xlabel("beam (deg)"); ax[1, 1].set_ylabel("target cell power (dB)")
    for a in ax.flat[1:]:
        a.grid(alpha=0.3)
    fig.suptitle("Radar: AD9484 -> AERIS DDC -> link (CPI mark) -> kria_radar_proc (2-D FFT, CA-CFAR)")
    fig.tight_layout()
    fig.savefig(os.path.join(L.IMG_DIR, "g8_radar_rd_cfar.png"), dpi=150); plt.close(fig)
    return dict(case="radar", peak=[int(v) for v in pk], found=found, false_det=false, snrs=snrs.tolist(), pd=pd,
                pd_ref=pd_ref, pd_mut=pd_mut, pfa=pfa, pfa_ref=pfa_ref, beam_est_deg=th_est, checks=checks,
                passed=all(checks.values()), figure="docs/img/sim/g8_radar_rd_cfar.png")


# ====================================================================== transmit (kria_tx_mod -> link -> dac_sdr, dac_radar)
TX_FS = 25e6


def tx_run(tag, mode, car_hz, tone_hz, mod_param, amp, n, mutate=""):
    """kria_tx_mod at 25 MSPS (tb_dsp_sweeps TX): n complex samples."""
    outf = L.wpath(f"{tag}.txt")
    L.run_bench("tb_dsp_sweeps", "g8", ["SWEEP_MODE=TX", f"OUT_FILE={outf}", f"TX_MODE={mode}",
                                         f"TX_CAR={ftw(car_hz, TX_FS):08x}", f"TX_TONE={ftw(tone_hz, TX_FS):08x}",
                                         f"TX_CFG={(amp << 16) | mod_param:08x}", f"TX_SAMPLES={n}"], mutate=mutate)
    d = np.loadtxt(outf, ndmin=2)
    if len(d) < n:
        raise RuntimeError(f"{tag}: {len(d)} samples of {n}")
    return d[:, 0] + 1j * d[:, 1]


def band_power(x, fs, lo, hi):
    from scipy.signal import welch
    f, p = welch(x, fs, nperseg=1 << 16, return_onesided=False, detrend=False)
    m = (f >= lo) & (f <= hi)
    return float(np.sum(p[m]) * (f[1] - f[0]))


def case_tx():
    print("\n=== Transmit: kria_tx_mod (AM, NBFM, USB, CW) and the full chain to the AD9767 / AD9708 pins ===")
    n = int(0.06 * TX_FS)                       # 60 ms: 60 periods of the 1 kHz test tone
    skip = int(0.005 * TX_FS)
    from scipy.signal import resample_poly
    res = {}

    # AM, 80 % at 1 kHz (mod_param = m * 32768); demodulate the envelope at 48 kS/s
    x = tx_run("tx_am", 1, 0.0, 1000.0, int(0.8 * 32768), 0x4000, n)[skip:]
    env = np.abs(resample_poly(x, 48, 25000))
    m_meas = (env.max() - env.min()) / (env.max() + env.min())
    res["am"] = dict(sinad=L.sinad_db(env, 48e3, 1000.0, 100.0, 5000.0), depth=float(m_meas),
                     acp=10 * np.log10(band_power(x, TX_FS, 9e3 - 4e3, 9e3 + 4e3) / band_power(x, TX_FS, -4e3, 4e3)))
    # NBFM, 2.5 kHz deviation (mod_param * 8192 is the peak FTW step: 47.7 Hz per unit)
    dev_p = int(round(2500.0 / (8192 * TX_FS / 2 ** 32)))
    x = tx_run("tx_fm", 2, 0.0, 1000.0, dev_p, 0x4000, n)[skip:]
    y = resample_poly(x, 48, 25000)
    inst = np.angle(y[1:] * np.conj(y[:-1])) * 48e3 / (2 * np.pi)
    res["nbfm"] = dict(sinad=L.sinad_db(inst, 48e3, 1000.0, 100.0, 5000.0),
                       dev_hz=float((np.percentile(inst, 99.9) - np.percentile(inst, 0.1)) / 2),
                       dev_set_hz=dev_p * 8192 * TX_FS / 2 ** 32,
                       acp=10 * np.log10(band_power(x, TX_FS, 12.5e3 - 5.5e3, 12.5e3 + 5.5e3)
                                         / band_power(x, TX_FS, -5.5e3, 5.5e3)))
    # USB at 1 kHz: wanted at +1 kHz, opposite sideband and carrier
    def usb(mut=""):
        x = tx_run("tx_usb" + mut, 3, 0.0, 1000.0, 0, 0x4000, n, mutate=mut)[skip:]
        _, aw = L.tone_fit(x, TX_FS, 1000.0, 200.0)
        _, ao = L.tone_fit(x, TX_FS, -1000.0, 200.0)
        c = abs(np.mean(x))
        return 20 * np.log10(aw / max(ao, 1e-9)), 20 * np.log10(aw / max(c, 1e-9)), x
    osb, carr, xu = usb()
    osb_m, _, _ = usb("flip_usb_q")
    res["usb"] = dict(opposite_db=osb, carrier_db=carr, opposite_db_mutation=osb_m)
    # CW at 1 MHz offset: spurs within +/-5 MHz
    x = tx_run("tx_cw", 0, 1.0e6, 1000.0, 0, 0x4000, n)[skip:]
    from scipy.signal import welch
    f, p = welch(x, TX_FS, nperseg=1 << 14, return_onesided=False, window="blackmanharris")
    pk = p.max()
    k0 = int(np.argmax(p))
    mask = (np.abs(f - f[k0]) > 20e3) & (np.abs(f) < 5e6)
    sfdr = 10 * np.log10(pk / p[mask].max())
    res["cw"] = dict(sfdr_dbc=float(sfdr))
    for k, v in res.items():
        print(f"    {k}: " + ", ".join(f"{a} {b:.2f}" if isinstance(b, float) else f"{a} {b}" for a, b in v.items()))

    # full chain: AM on a 3.125 MHz carrier and the radar chirp, 250 us, at the DAC pins
    outf = L.wpath("txe2e.txt")
    L.run_bench("tb_system_signals", "g8tx", [
        "CASE=TX", "RUN_US=250", f"OUT_TX={outf}", f"KRIA_CTRL={(1 << 10) | 0x2:08x}",
        f"TX_CAR={ftw(3.125e6, TX_FS):08x}", f"TX_TONE={ftw(10e3, TX_FS):08x}",
        f"TX_CFG={(0x4000 << 16) | int(0.8 * 32768):08x}"], defines=VU["define"])
    s_iq, rad = [], []
    for ln in open(outf):
        p_ = ln.split()
        if p_ and p_[0] == "S":
            s_iq.append(int(p_[1]) + 1j * int(p_[2]))
        elif p_ and p_[0] == "R":
            rad.append((int(p_[1]), int(p_[2])))
    s_iq = np.array(s_iq)
    if len(s_iq) < 2000:
        raise RuntimeError(f"full-chain TX: {len(s_iq)} DAC samples")
    s_iq = s_iq[len(s_iq) // 5:]
    fs_dac = len(s_iq) / (0.8 * 250e-6)          # samples per second at the AD9767, from the record
    f_c, a_c = L.tone_fit(s_iq, fs_dac, 3.125e6, 200e3)
    gaps = int(np.sum(np.abs(s_iq) == 0))
    env = np.abs(s_iq)
    e2e_depth = (np.percentile(env, 99.5) - np.percentile(env, 0.5)) / (np.percentile(env, 99.5) + np.percentile(env, 0.5))
    print(f"    full chain: AD9767 {fs_dac/1e6:.2f} MSPS, carrier at {f_c/1e6:.4f} MHz, AM depth {e2e_depth:.2f}, "
          f"{gaps} zero samples; AD9708 {sum(a for _, a in rad)} chirp samples")
    # each chirp on its own (the active flag marks it): instantaneous frequency against the programmed
    # start (CSR 0x58, 1/64 of dac_clk) and slope (CSR 0x5C, 0x20000 per sample)
    chirp_ok, n_chirps, slope_err, f0_err, resid = False, 0, 1.0, 1.0, 1.0
    if rad:
        from scipy.signal import hilbert
        v = np.array([a for a, _ in rad], float)
        act = np.array([b for _, b in rad], int)
        edges = np.flatnonzero(np.diff(np.r_[0, act, 0]))
        runs = [(a, b) for a, b in zip(edges[::2], edges[1::2]) if b - a >= 256]
        slope_set = 2 * np.pi * 0x20000 / 2 ** 32
        f0_set = 2 * np.pi * 0x0400_0000 / 2 ** 32
        errs = []
        for a, b in runs:
            seg_v = v[a:b]
            ph = np.unwrap(np.angle(hilbert(seg_v - seg_v.mean())))
            fi = np.diff(ph)
            k = np.arange(len(fi))
            m = slice(len(fi) // 10, len(fi) * 9 // 10)
            pf = np.polyfit(k[m], fi[m], 1)
            errs.append((pf[0] / slope_set - 1, pf[1] / f0_set - 1,
                         np.std(fi[m] - np.polyval(pf, k[m])) / (slope_set * len(fi))))
        if errs:
            e = np.array(errs)
            n_chirps = len(runs)
            slope_err, f0_err, resid = (float(np.max(np.abs(e[:, 0]))), float(np.max(np.abs(e[:, 1]))),
                                        float(np.max(e[:, 2])))
            chirp_ok = slope_err < 0.05 and f0_err < 0.05 and resid < 0.05
        print(f"    chirp: {n_chirps} chirps, worst slope error {100*slope_err:.2f} %, start frequency "
              f"{100*f0_err:.2f} %, residual {100*resid:.2f} % of the sweep")

    checks = {
        "AM: SINAD >= 40 dB, depth within 0.03 of 0.80": res["am"]["sinad"] >= 40 and abs(res["am"]["depth"] - 0.8) <= 0.03,
        "NBFM: SINAD >= 40 dB, deviation within 5 % of the setting": res["nbfm"]["sinad"] >= 40
        and abs(res["nbfm"]["dev_hz"] / res["nbfm"]["dev_set_hz"] - 1) <= 0.05,
        "NBFM: adjacent channel (12.5 kHz) <= -60 dBc": res["nbfm"]["acp"] <= -60,
        "AM: adjacent channel (9 kHz) <= -60 dBc": res["am"]["acp"] <= -60,
        "USB: opposite sideband and carrier >= 40 dB down": osb >= 40 and carr >= 40,
        "mutation flip_usb_q puts the tone in the wrong sideband": osb_m < 0,
        "CW: SFDR within +/-5 MHz >= 60 dBc": sfdr >= 60,
        "full chain: carrier within 1 kHz of 3.125 MHz, no gaps": abs(f_c - 3.125e6) < 1e3 and gaps == 0,
        "full chain: AM depth at the pins within 0.05 of 0.80": abs(e2e_depth - 0.8) <= 0.05,
        "full chain: every radar chirp at the programmed start and slope within 5 %, linear": chirp_ok,
    }

    fig, ax = plt.subplots(2, 2, figsize=(12, 8.2))
    for a, (nm, md, ft, mp) in zip(ax.flat, [("AM 80 %", 1, 1000.0, int(0.8 * 32768)),
                                            ("NBFM 2.5 kHz", 2, 1000.0, dev_p), ("USB", 3, 1000.0, 0),
                                            ("CW +1 MHz", 0, 1000.0, 0)]):
        car = 1e6 if md == 0 else 0.0
        xx = tx_run("tx_plot", md, car, ft, mp, 0x4000, 1 << 18)
        f_, p_ = psd_db(xx, TX_FS, 1 << 16)
        a.plot((f_ - car) / 1e3, p_ - p_.max(), lw=0.7)
        a.set_xlim(-30, 30); a.set_ylim(-110, 5); a.grid(alpha=0.3)
        a.set_title(f"kria_tx_mod {nm} (1 kHz tone)"); a.set_xlabel("offset (kHz)"); a.set_ylabel("dBc")
        if md == 2:
            for e in (-12.5, 12.5):
                a.axvspan(e - 5.5, e + 5.5, color="r", alpha=0.08)
    fig.suptitle("Transmit: kria_tx_mod at 25 MSPS (adjacent channels shaded for NBFM)")
    fig.tight_layout()
    fig.savefig(os.path.join(L.IMG_DIR, "g8_tx_masks.png"), dpi=150); plt.close(fig)
    return dict(case="tx", modes=res, e2e=dict(fs_dac=fs_dac, carrier_hz=f_c, am_depth=float(e2e_depth), gaps=gaps,
                                               chirp_samples=int(sum(b for _, b in rad)), chirps=n_chirps,
                                               slope_err=slope_err, f0_err=f0_err, chirp_ok=bool(chirp_ok)),
                checks=checks, passed=all(checks.values()), figure="docs/img/sim/g8_tx_masks.png")


CASES = dict(hf_am=case_hf_am, hf_ssb=case_hf_ssb, fm=case_fm, air=case_air, nbfm=case_nbfm,
             adsb=case_adsb, radar=case_radar, tx=case_tx)


def main(argv):
    names = argv or list(CASES)
    res = {}
    if os.path.exists(RESULTS):
        res = json.load(open(RESULTS))
        if isinstance(res, list):
            res = {}
    for nme in names:
        r = CASES[nme]()
        res[nme] = r
        for k, ok in r["checks"].items():
            print(f"  [{'ok' if ok else 'FAIL'}] {k}")
        json.dump(res, open(RESULTS, "w"), indent=1, default=float)
    bad = [k for k, r in res.items() if not r["passed"]]
    print("\nG-8:", "all pass" if not bad else f"failing: {', '.join(bad)}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
