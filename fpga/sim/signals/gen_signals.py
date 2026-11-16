# SPDX-License-Identifier: Apache-2.0
"""
Rev08 G-8 Realistic Synthetic Signal & Cascade Model Generators.

Synthesizes modulated RF/IF/baseband sample vectors calibrated to docs/REV08_PLAN.md
sections 5.5 (gain, noise figure, full scale) and 5.6 (LO / IF / image plan), including:
  - Thermal noise (-174 dBm/Hz + NF), clock phase jitter, 8-bit/14-bit quantization & clipping
  - Frequency-selective / Rayleigh fading, QRN atmospheric impulses, Doppler shift
  - Adjacent-channel (+40 dB / +60 dB) & converter-image blockers behind Rev08 filter skirts
"""

import numpy as np


K_BOLTZMANN_DBM_HZ = -174.0  # k*T at 290 K in dBm/Hz


def dbm_to_vpeak(dbm, r=50.0):
    p_w = 10.0 ** ((dbm - 30.0) / 10.0)
    return np.sqrt(2.0 * r * p_w)


def thermal_noise_complex(n, fs, nf_db, rng):
    """Complex thermal noise scaled in antenna-referred dBm (rms = sqrt(P_n))."""
    p_n_dbm = K_BOLTZMANN_DBM_HZ + 10.0 * np.log10(fs) + nf_db
    v_rms = np.sqrt(50.0 * (10.0 ** ((p_n_dbm - 30.0) / 10.0)))
    return (rng.standard_normal(n) + 1j * rng.standard_normal(n)) * (v_rms / np.sqrt(2.0))


def thermal_noise_real(n, fs, nf_db, rng):
    """Real thermal noise scaled in antenna-referred Vrms over bandwidth fs/2."""
    p_n_dbm = K_BOLTZMANN_DBM_HZ + 10.0 * np.log10(fs / 2.0) + nf_db
    v_rms = np.sqrt(50.0 * (10.0 ** ((p_n_dbm - 30.0) / 10.0)))
    return rng.standard_normal(n) * v_rms


def quantize_ad9253_14b(v_ant_real, fs, ant_fs_dbm=-5.0, nf_db=12.0, jitter_fs=120e-15, rng=None):
    """Apply cascade thermal floor + clock jitter + 14-bit signed ADC quantization [-8192..8191]."""
    if rng is None:
        rng = np.random.default_rng(1)
    n = len(v_ant_real)
    v_noise = thermal_noise_real(n, fs, nf_db, rng)
    # Jitter noise approximation: additive dV/dt * dt_rms
    dv = np.gradient(v_ant_real) * fs
    v_tot = v_ant_real + v_noise + dv * rng.standard_normal(n) * jitter_fs
    v_fs = dbm_to_vpeak(ant_fs_dbm)
    codes = np.round((v_tot / v_fs) * 8191.0)
    return np.clip(codes, -8192, 8191).astype(np.int32)


def quantize_ad9484_8b(v_ant_real, fs=400e6, ant_fs_dbm=-49.9, nf_db=2.3, jitter_fs=100e-15, rng=None):
    """Apply Rev08 cascade noise floor + jitter + 8-bit AD9484 offset-binary [0..255]."""
    if rng is None:
        rng = np.random.default_rng(2)
    n = len(v_ant_real)
    v_noise = thermal_noise_real(n, fs, nf_db, rng)
    dv = np.gradient(v_ant_real) * fs
    v_tot = v_ant_real + v_noise + dv * rng.standard_normal(n) * jitter_fs
    v_fs = dbm_to_vpeak(ant_fs_dbm)
    codes = np.round(128.0 + (v_tot / v_fs) * 127.0)
    return np.clip(codes, 0, 255).astype(np.uint8)


def speech_like_audio(t, f_probe=1000.0, probe_weight=0.70, seed=10):
    """Realistic speech-like waveform: formant tones + band-limited syllabic voice envelope + clean 1 kHz SINAD probe."""
    rng = np.random.default_rng(seed)
    syllabic = 0.55 + 0.45 * np.sin(2.0 * np.pi * 3.2 * t + 0.4)
    formants = (0.50 * np.sin(2.0 * np.pi * 420.0 * t)
              + 0.30 * np.sin(2.0 * np.pi * 780.0 * t + 0.7)
              + 0.20 * np.sin(2.0 * np.pi * 1650.0 * t + 1.3))
    # Add light band-limited consonant breath noise (0.3..3.4 kHz approximation)
    raw_n = rng.standard_normal(len(t))
    b_n = np.convolve(raw_n, np.ones(8) / 8.0, mode="same")
    b_n = b_n / (np.max(np.abs(b_n)) + 1e-12) * 0.15
    speech = syllabic * (formants + b_n)
    sig = probe_weight * np.sin(2.0 * np.pi * f_probe * t) + (1.0 - probe_weight) * speech
    return sig / (np.max(np.abs(sig)) + 1e-12)


def hilbert_fft(x):
    """Exact analytic Hilbert transform H{x} via FFT for clean SSB modulator / signal synthesis."""
    n = len(x)
    X = np.fft.fft(x)
    h = np.zeros(n)
    if n % 2 == 0:
        h[0] = 1.0
        h[n // 2] = 1.0
        h[1:n // 2] = 2.0
    else:
        h[0] = 1.0
        h[1:(n + 1) // 2] = 2.0
    return np.imag(np.fft.ifft(X * h))


def design_fir_lpf(numtaps, cutoff_norm):
    n = np.arange(numtaps) - (numtaps - 1) / 2.0
    h = np.sinc(2.0 * cutoff_norm * n) * np.hamming(numtaps)
    return h / np.sum(h)


def compute_sinad_db(sig, fs, f_sig, f_bw_lo=250.0, f_bw_hi=3600.0):
    """
    Exact IEEE/TIA SINAD measurement on real demodulated audio:
      SINAD = 10*log10(P_total_inband / P_noise_and_distortion),
    excluding DC and notch-isolating f_sig bin +/- 1 Hann sidelobes.
    """
    s = np.asarray(sig, dtype=float)
    s = s - np.mean(s)
    n = len(s)
    if n < 32:
        return 0.0
    win = np.hanning(n)
    spec = np.abs(np.fft.rfft(s * win)) ** 2
    freqs = np.fft.rfftfreq(n, 1.0 / fs)
    in_band = (freqs >= f_bw_lo) & (freqs <= f_bw_hi)
    if not np.any(in_band):
        in_band = freqs > 0
    df = freqs[1] - freqs[0]
    sig_mask = np.abs(freqs - f_sig) <= max(2.2 * df, 0.06 * f_sig)
    p_tot = float(np.sum(spec[in_band]))
    p_sig = float(np.sum(spec[in_band & sig_mask]))
    p_nd = max(p_tot - p_sig, 1e-15)
    return float(10.0 * np.log10(max(p_tot, 1e-15) / p_nd))


def _apply_fading_real(sig, fs, delay_s, atten, doppler_hz=0.0):
    """2-ray multipath fading channel on real/complex array."""
    n = len(sig)
    d_samp = max(1, int(round(delay_s * fs)))
    delayed = np.zeros_like(sig)
    if d_samp < n:
        delayed[d_samp:] = sig[:-d_samp]
    if doppler_hz != 0.0:
        t = np.arange(n) / fs
        delayed = delayed * np.cos(2.0 * np.pi * doppler_hz * t)
    return 0.85 * sig + atten * delayed


def _encode_rds_group(pi_code=0xC201, text4="KV26"):
    """Build valid 104-bit RDS group (4x26-bit blocks with ISO 62106 10-bit CRC + offset words)."""
    # G(x) = x^10 + x^8 + x^7 + x^5 + x^4 + x^3 + 1 = 0x5B9
    POLY = 0x5B9
    OFFSETS = [0x0FC, 0x198, 0x168, 0x1B4]
    w0 = pi_code & 0xFFFF
    w1 = 0x2000 | (ord(text4[0]) & 0x1F)
    w2 = (ord(text4[0]) << 8) | ord(text4[1])
    w3 = (ord(text4[2]) << 8) | ord(text4[3])
    bits = []
    for idx, w in enumerate((w0, w1, w2, w3)):
        reg = 0
        for b in range(15, -1, -1):
            bit = (w >> b) & 1
            fb = ((reg >> 9) & 1) ^ bit
            reg = ((reg << 1) & 0x3FF) ^ (0x1B9 if fb else 0)
            bits.append(bit)
        cw = (reg ^ OFFSETS[idx]) & 0x3FF
        for b in range(9, -1, -1):
            bits.append((cw >> b) & 1)
    return np.array(bits, dtype=np.int32)


def _modulate_rds_57k(t, carrier_57k_cos, bits, baud=1187.5):
    """Differential-encoded bi-phase (Manchester) 57 kHz RDS BPSK subcarrier."""
    # Differential encoding: b_diff[k] = b_diff[k-1] ^ bits[k]
    n = len(t)
    diff = np.zeros(len(bits), dtype=int)
    prev = 0
    for k, b in enumerate(bits):
        prev ^= int(b)
        diff[k] = prev
    chip_idx = np.floor(t * (2.0 * baud)).astype(int) % (2 * len(bits))
    bit_idx = chip_idx // 2
    half_idx = chip_idx % 2
    # Bi-phase: '1' -> (+1, -1), '0' -> (-1, +1)
    pol = np.where(diff[bit_idx] == 1, 1.0, -1.0) * np.where(half_idx == 0, 1.0, -1.0)
    # Pulse shape lightly
    h = design_fir_lpf(17, 0.20)
    bb = np.convolve(pol, h, mode="same")
    return 0.04 * bb * carrier_57k_cos


# -----------------------------------------------------------------------------
# Realistic Case Generators -> return (iq_baseband_or_rf_info, samples, meta)
# -----------------------------------------------------------------------------
def gen_hf_am(n_samp, fs=62.5e6, f_rf=7.20e6, lvl_dbm=-100.0, adj_plus_db=40.0, seed=101):
    """HF AM Broadcast (J951 -> AD9253 ChB) + +40 dB +9 kHz neighbor + Rayleigh fading."""
    rng = np.random.default_rng(seed)
    t = np.arange(n_samp) / fs
    aud = speech_like_audio(t, f_probe=1000.0, probe_weight=0.80, seed=seed)
    v_des = dbm_to_vpeak(lvl_dbm)
    rf_des = v_des * (1.0 + 0.75 * aud) * np.cos(2.0 * np.pi * f_rf * t)
    # Selective 2-ray fading
    rf_des = _apply_fading_real(rf_des, fs, 4.5e-6, 0.30, doppler_hz=1.5)
    # Strong +40 dB adjacent station at +9 kHz (and -9 kHz weaker +20 dB)
    v_adj = dbm_to_vpeak(lvl_dbm + adj_plus_db)
    aud_adj = np.sin(2.0 * np.pi * 1700.0 * t)
    rf_adj = v_adj * (1.0 + 0.7 * aud_adj) * np.cos(2.0 * np.pi * (f_rf + 9000.0) * t)
    v_tot = rf_des + rf_adj
    codes_b = quantize_ad9253_14b(v_tot, fs, ant_fs_dbm=-32.0, nf_db=12.0, rng=rng)
    codes_a = np.zeros_like(codes_b)
    return v_tot, codes_a, codes_b, {"f_rf": f_rf, "fs": fs, "lvl_dbm": lvl_dbm, "aud_ref": aud}


def gen_hf_ssb(n_samp, fs=62.5e6, f_rf=14.20e6, mode="USB", lvl_dbm=-102.0, seed=202):
    """HF SSB/CB (3.6/7.1/14.2/27 MHz) + selective fading + QRN atmospheric impulse bursts."""
    rng = np.random.default_rng(seed)
    t = np.arange(n_samp) / fs
    aud = speech_like_audio(t, f_probe=1200.0, probe_weight=0.80, seed=seed)
    # Analytic audio -> RF SSB around f_rf
    hilb_a = hilbert_fft(aud)
    v_des = dbm_to_vpeak(lvl_dbm)
    sgn = -1.0 if mode.upper() == "USB" else +1.0
    # cos(wc*t)*aud -/+ sin(wc*t)*H{aud} places USB at +w_m or LSB at -w_m
    rf_des = v_des * (aud * np.cos(2.0 * np.pi * f_rf * t) + sgn * hilb_a * np.sin(2.0 * np.pi * f_rf * t))
    rf_des = _apply_fading_real(rf_des, fs, 3.2e-6, 0.32)
    # QRN atmospheric impulse bursts (broadband spikes spaced randomly)
    qrn = np.zeros(n_samp)
    imp_locs = rng.integers(500, n_samp - 100, size=max(4, n_samp // 12000))
    for p in imp_locs:
        qrn[p:p+4] = dbm_to_vpeak(lvl_dbm + 22.0) * np.array([1.0, -0.7, 0.4, -0.2])
    v_tot = rf_des + qrn
    codes_b = quantize_ad9253_14b(v_tot, fs, ant_fs_dbm=-32.0, nf_db=12.0, rng=rng)
    return v_tot, np.zeros_like(codes_b), codes_b, {"f_rf": f_rf, "fs": fs, "lvl_dbm": lvl_dbm, "aud_ref": aud}


def gen_fm_bcast(n_samp, fs=400e6, f_des=98.1e6, lvl_dbm=-62.0, blocker_plus_db=60.0, seed=303):
    """
    FM Broadcast (88-108 MHz -> AD9484 @ 400 MSPS direct sampling per §5.5/5.6):
    75 kHz dev, L+R + 19 kHz pilot + 38 kHz L-R + 57 kHz RDS BPSK, multipath, +60 dB strong station @ 100.3 MHz.
    Cascade AGC uses PE4312 + LNA bypass when strong station > -30 dBm (FS moves up to +2.1 dBm).
    """
    rng = np.random.default_rng(seed)
    t = np.arange(n_samp) / fs
    L = 0.85 * np.sin(2.0 * np.pi * 1000.0 * t) + 0.15 * np.sin(2.0 * np.pi * 2400.0 * t)
    R = 0.25 * np.sin(2.0 * np.pi * 1000.0 * t) - 0.15 * np.sin(2.0 * np.pi * 2400.0 * t)
    rds_bits = np.tile(_encode_rds_group(), 4)
    c19 = np.cos(2.0 * np.pi * 19e3 * t)
    c38 = np.cos(2.0 * np.pi * 38e3 * t)
    c57 = np.cos(2.0 * np.pi * 57e3 * t)
    mpx = 0.45 * (L + R) + 0.10 * c19 + 0.45 * (L - R) * c38 + _modulate_rds_57k(t, c57, rds_bits)
    # Integrate instantaneous frequency deviation 75 kHz
    phi = 2.0 * np.pi * 75e3 * np.cumsum(mpx) / fs
    v_des = dbm_to_vpeak(lvl_dbm) * np.cos(2.0 * np.pi * f_des * t + phi)
    v_des = _apply_fading_real(v_des, fs, 1.8e-6, 0.22)

    # Strong blocker station at 100.3 MHz (+60 dB stronger!) and second station at 94.5 MHz
    phi_b = 2.0 * np.pi * 75e3 * np.cumsum(0.8 * np.sin(2.0 * np.pi * 2200.0 * t)) / fs
    v_blk = dbm_to_vpeak(lvl_dbm + blocker_plus_db) * np.cos(2.0 * np.pi * 100.3e6 * t + phi_b)
    v_st2 = dbm_to_vpeak(lvl_dbm + 20.0) * np.cos(2.0 * np.pi * 94.5e6 * t)

    v_tot = v_des + v_blk + v_st2
    # AGC backoff (PE4312 + LNA bypass) keeps peak just below ADC FS (-49.9 + 50 = 0 dBm max)
    peak_dbm = lvl_dbm + blocker_plus_db
    ant_fs_eff = max(-49.9, min(2.0, peak_dbm + 2.0))
    atten = ant_fs_eff - (-49.9)
    nf_eff = 2.3 + 0.35 * atten  # Realistic cascade NF scaling under AGC backoff
    codes = quantize_ad9484_8b(v_tot, fs=fs, ant_fs_dbm=ant_fs_eff, nf_db=nf_eff, rng=rng)
    return v_tot, codes, {"f_des": f_des, "fs": fs, "lvl_dbm": lvl_dbm, "rds_bits": rds_bits, "ant_fs": ant_fs_eff, "nf": nf_eff}


def gen_airband(n_samp, fs=400e6, f_des=121.5e6, lvl_dbm=-110.0, fm_blocker_dbm=-15.0, doppler_hz=850.0, seed=404):
    """Airband AM (118-137 MHz, 8.33/25 kHz spacing) + moving aircraft Doppler + FM blocker behind >=44.9 dB filter."""
    rng = np.random.default_rng(seed)
    t = np.arange(n_samp) / fs
    aud = speech_like_audio(t, f_probe=1000.0, probe_weight=0.80, seed=seed)
    v_des = dbm_to_vpeak(lvl_dbm)
    rf_des = v_des * (1.0 + 0.80 * aud) * np.cos(2.0 * np.pi * (f_des + doppler_hz) * t)
    # 8.33 kHz & 25 kHz neighbors
    rf_n1 = dbm_to_vpeak(lvl_dbm + 25.0) * (1.0 + 0.5 * np.sin(2.0 * np.pi * 1900.0 * t)) * np.cos(2.0 * np.pi * (f_des + 8333.0) * t)
    rf_n2 = dbm_to_vpeak(lvl_dbm + 35.0) * (1.0 + 0.5 * np.sin(2.0 * np.pi * 2500.0 * t)) * np.cos(2.0 * np.pi * (f_des + 25000.0) * t)
    # 98.1 MHz FM broadcast blocker attenuated by 44.9 dB FM-reject filter (§5.4)
    rf_fm = dbm_to_vpeak(fm_blocker_dbm - 44.9) * np.cos(2.0 * np.pi * 98.1e6 * t)
    v_tot = rf_des + rf_n1 + rf_n2 + rf_fm
    codes = quantize_ad9484_8b(v_tot, fs=fs, ant_fs_dbm=-48.9, nf_db=2.5, rng=rng)
    return v_tot, codes, {"f_des": f_des, "fs": fs, "lvl_dbm": lvl_dbm}


def gen_vhf_uhf(n_samp, fs=400e6, f_if=135.0e6, lvl_dbm=-110.0, ctcss_hz=100.0, adj_plus_db=40.0, img_rej_db=50.4, seed=505):
    """
    VHF/UHF Handheld NBFM (PMR446 / 70cm / Marine / 2m -> IF=135 MHz @ LO=581 MHz per §5.6):
    12.5 kHz NBFM + CTCSS subtone + +40 dB adjacent channel + converter image at 716 MHz attenuated >=50.4 dB.
    """
    rng = np.random.default_rng(seed)
    t = np.arange(n_samp) / fs
    aud = speech_like_audio(t, f_probe=1000.0, probe_weight=0.80, seed=seed)
    inst_f = 2500.0 * aud + 600.0 * np.sin(2.0 * np.pi * ctcss_hz * t)
    phi = 2.0 * np.pi * np.cumsum(inst_f) / fs
    rf_des = dbm_to_vpeak(lvl_dbm) * np.cos(2.0 * np.pi * f_if * t + phi)
    # +40 dB adjacent channel (+12.5 kHz)
    phi_adj = 2.0 * np.pi * np.cumsum(2500.0 * np.sin(2.0 * np.pi * 2100.0 * t)) / fs
    rf_adj = dbm_to_vpeak(lvl_dbm + adj_plus_db) * np.cos(2.0 * np.pi * (f_if + 12500.0) * t + phi_adj)
    # Converter image signal (716 MHz folding onto f_if + 250 kHz offset) attenuated by UHF filter (>=50.4 dB)
    rf_img = dbm_to_vpeak(lvl_dbm + 20.0 - img_rej_db) * np.cos(2.0 * np.pi * (f_if + 250e3) * t)
    v_tot = rf_des + rf_adj + rf_img
    codes = quantize_ad9484_8b(v_tot, fs=fs, ant_fs_dbm=-46.3, nf_db=3.7, rng=rng)
    return v_tot, codes, {"f_if": f_if, "fs": fs, "lvl_dbm": lvl_dbm, "ctcss_hz": ctcss_hz}


def encode_mode_s_crc24(payload_88):
    """Compute exact 112-bit ICAO Mode-S frame hex word with CRC-24 appended."""
    POLY = 0x1FFF409
    val = payload_88 << 24
    msg_int = val
    for b in range(111, 23, -1):
        if (val >> b) & 1:
            val ^= (POLY << (b - 24))
    return msg_int | (val & 0xFFFFFF)


def gen_adsb(n_samp, fs=400e6, f_if=135.0e6, lvl_dbm=-82.0, seed=606):
    """
    1090 MHz ADS-B Mode-S Extended Squitter (LO=955 MHz -> IF=135/155 MHz per §5.6):
    Valid DF17 frames + overlapping weaker collision reply + Rev08 cascade noise floor (NF=7.1 dB).
    """
    rng = np.random.default_rng(seed)
    frames = [
        0x8D4840D6202CC371C32CE0576098,
        encode_mode_s_crc24(0x8D4CA251204994B1C36E60),
        encode_mode_s_crc24(0x8D3C674B58B9828D58A322),
    ]
    chip_samps = int(round(0.5e-6 * fs))  # 200 samples @ 400 MSPS = 0.5 us
    env = np.zeros(n_samp, dtype=float)
    v_sig = dbm_to_vpeak(lvl_dbm)
    cursor = int(round(10e-6 * fs))
    pre_chips = [1, 0, 1, 0, 0, 0, 0, 1, 0, 1, 0, 0, 0, 0, 0, 0]

    for idx, frm in enumerate(frames):
        if cursor + 245 * chip_samps >= n_samp:
            break
        chips = list(pre_chips)
        for b in range(111, -1, -1):
            bit = (frm >> b) & 1
            chips.extend([1, 0] if bit else [0, 1])
        for ci, val in enumerate(chips):
            if val:
                s0 = cursor + ci * chip_samps
                env[s0:s0 + chip_samps] += v_sig
        # Add an overlapping colliding reply -12 dB halfway through frame 1
        if idx == 1:
            col_start = cursor + 80 * chip_samps
            v_col = v_sig * 0.25
            for ci, val in enumerate(pre_chips):
                if val:
                    s0 = col_start + ci * chip_samps
                    env[s0:s0 + chip_samps] += v_col
        cursor += int(round(150e-6 * fs))

    t = np.arange(n_samp) / fs
    v_tot = env * np.cos(2.0 * np.pi * f_if * t)
    codes = quantize_ad9484_8b(v_tot, fs=fs, ant_fs_dbm=-40.4, nf_db=7.1, rng=rng)
    return v_tot, codes, {"f_if": f_if, "fs": fs, "lvl_dbm": lvl_dbm, "frames": frames}


def gen_radar_cpi(fs=400e6, f_if=120.0e6, n_range=64, n_doppler=16, post_decim=4, snr_db=22.0, seed=707):
    """
    Generate realistic 400 MSPS AD9484 radar IF signal matching 64x16 CPI after 16x decimation:
    Target 1 (strong): R_bin=12, D_bin=3, 0 dB rel (amp=0.65 FS)
    Target 2 (weak -30 dB!): R_bin=40, D_bin=12, -30 dB rel (tests near-far dynamic range & CA-CFAR)
    Clutter: R_bin=6, D_bin=0, -10 dB rel
    """
    rng = np.random.default_rng(seed)
    decim_tot = 4 * post_decim  # 16 @ post_decim=4 -> 25 MSPS -> 16 ADC samples per baseband cell
    n_samp = n_range * n_doppler * decim_tot + 2048  # pad tail flush
    t_adc = np.arange(n_samp) / fs

    # Map each ADC sample to discrete baseband index k = t // decim_tot -> (m, r)
    k_bb = np.arange(n_samp) // decim_tot
    m = (k_bb // n_range).astype(float)
    r = (k_bb % n_range).astype(float)

    a1 = 0.65
    a2 = a1 * (10.0 ** (-30.0 / 20.0))  # -30 dB weaker target!
    ac = a1 * (10.0 ** (-10.0 / 20.0))  # -10 dB zero-Doppler clutter

    # Complex baseband sum modulated onto 120.0 MHz IF
    phi1 = 2.0 * np.pi * (12.0 * r / n_range + 3.0 * m / n_doppler)
    phi2 = 2.0 * np.pi * (40.0 * r / n_range + 12.0 * m / n_doppler)
    phic = 2.0 * np.pi * (6.0  * r / n_range + 0.0 * m / n_doppler)
    bb = a1 * np.exp(1j * phi1) + a2 * np.exp(1j * phi2) + ac * np.exp(1j * phic)

    # Zero outside active CPI
    bb[k_bb >= n_range * n_doppler] = 0.0
    rf = np.real(bb * np.exp(1j * 2.0 * np.pi * f_if * t_adc))

    # Add noise calibrated so Target 1 input SNR matches snr_db before 64*16 (+30.1 dB) FFT processing gain
    sig_rms = a1 / np.sqrt(2.0)
    noise_rms = sig_rms / (10.0 ** (snr_db / 20.0))
    rf_noisy = rf + rng.standard_normal(n_samp) * noise_rms
    codes = np.clip(np.round(128.0 + 110.0 * rf_noisy), 0, 255).astype(np.uint8)
    return rf_noisy, codes, {"f_if": f_if, "fs": fs, "snr_db": snr_db, "targets": [(12, 3, 0.0), (40, 12, -30.0)], "clutter": (6, 0)}


def write_adcs_hex(path, codes_a, codes_b):
    with open(path, "w", encoding="ascii") as f:
        for a, b in zip(codes_a, codes_b):
            f.write(f"{int(a) & 0x3FFF:04x} {int(b) & 0x3FFF:04x}\n")


def write_adcr_hex(path, codes):
    with open(path, "w", encoding="ascii") as f:
        for v in codes:
            f.write(f"{int(v) & 0xFF:02x}\n")


def write_iq_txt(path, iq_arr):
    ii = np.clip(np.round(np.real(iq_arr)), -32768, 32767).astype(np.int32)
    qq = np.clip(np.round(np.imag(iq_arr)), -32768, 32767).astype(np.int32)
    with open(path, "w", encoding="ascii") as f:
        for i_v, q_v in zip(ii, qq):
            f.write(f"{i_v} {q_v}\n")
