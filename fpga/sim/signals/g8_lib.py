# SPDX-License-Identifier: Apache-2.0
"""
Rev08 G-8 measurement framework: shared by every signal case in g8_suite.py.

Each receive case is measured in three steps, all on the real RTL:
  1. Calibration (full chain). A CW at a known antenna level, with the cascade's thermal noise, goes through the
     ADC model, the Artix DDC, the board's LVDS channel, the link and into the Kria (tb_system_signals). The
     stream the Kria receives gives the chain's gain (output code amplitude per antenna volt), the noise density
     at the Kria's input and the tuning error.
  2. Scene (full chain). The case's realistic scene (modulation, fading, adjacent carriers, blockers) goes the
     same way; its spectra, waterfall and decoded output make the figures and check that the chain demodulates
     what was sent.
  3. Sweep (Kria RTL with the case's own configuration). A full-chain run of a few milliseconds gives only a few
     audio samples, so the level sweeps feed kria_channel_rx / kria_adsb_rx / kria_radar_proc directly
     (tb_dsp_sweeps) at the stream's real sample rate, with the CSR values the scene used. The input is the
     baseband the Artix would deliver: the signal scaled by the measured gain plus complex noise at the measured
     density. A floating-point reference demodulator gets the same input; the RTL must stay within a stated
     margin of it.
No result has a fallback value: an empty or missing output raises.
"""

import os
import subprocess

import numpy as np

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
SIM_DIR = os.path.abspath(os.path.join(THIS_DIR, ".."))
REPO_ROOT = os.path.abspath(os.path.join(SIM_DIR, "..", ".."))
RUN_PS1 = os.path.join(SIM_DIR, "run.ps1")
OUT_DIR = os.path.join(SIM_DIR, "out")
WORK = os.path.join(OUT_DIR, "g8" + os.environ.get("G8_SUFFIX", ""))   # parallel suites keep their own files
IMG_DIR = os.path.join(REPO_ROOT, "docs", "img", "sim")
VIVADO_BIN = os.environ.get("VIVADO_BIN", r"D:\AMDDesignTools\2026.1\Vivado\bin")
PL_CLK = 100e6

os.makedirs(WORK, exist_ok=True)


def wpath(name):
    return os.path.join(WORK, name).replace("\\", "/")


# ------------------------------------------------------------------ running the benches
_compiled = set()


def _ps_list(xs):
    return "@(" + ",".join(f"'{x}'" for x in xs) + ")"


def run_bench(bench, tag, plusargs, defines=(), mutate=""):
    """First call per (bench, tag, defines, mutate) compiles through run.ps1; later calls rerun the snapshot."""
    tag = tag + os.environ.get("G8_SUFFIX", "")     # parallel suite processes keep their own snapshots
    key = (bench, tag, tuple(defines), mutate)
    run_name = (bench + (("-def-" + "_".join(defines)) if defines else "") + (f"-mutate-{mutate}" if mutate else "")
                + (f"-{tag}" if tag else ""))
    work = os.path.join(OUT_DIR, f"work_{run_name}")
    if key not in _compiled or not os.path.isdir(work):
        cmd = f"& '{RUN_PS1}' -Bench '{bench}' -PlusArg {_ps_list(plusargs)}"
        if tag:
            cmd += f" -RunTag '{tag}'"
        if defines:
            cmd += f" -Define {_ps_list(defines)}"
        if mutate:
            cmd += f" -Mutate '{mutate}'"
        res = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd],
                             capture_output=True, text=True)
        out = res.stdout + res.stderr
        log = os.path.join(OUT_DIR, f"{run_name}.log")
        if os.path.exists(log):
            out += open(log, errors="replace").read()[-4000:]
        _compiled.add(key)
    else:
        args = " ".join(f'--testplusarg "{p}"' for p in plusargs)
        res = subprocess.run(f'"{os.path.join(VIVADO_BIN, "xsim.bat")}" -R {args} sim', cwd=work, shell=True,
                             capture_output=True, text=True)
        out = res.stdout + res.stderr
    if "PASS:" not in out:
        raise RuntimeError(f"{bench} ({tag}) did not pass:\n{out[-3000:]}")
    return out


# ------------------------------------------------------------------ files
def write_iq(path, x):
    x = np.asarray(x)
    i = np.clip(np.round(x.real), -32768, 32767).astype(np.int64)
    q = np.clip(np.round(x.imag), -32768, 32767).astype(np.int64)
    np.savetxt(path, np.c_[i, q], fmt="%d")


def read_iq(path, min_len=64):
    a = np.loadtxt(path, dtype=float, ndmin=2)
    if a.shape[0] < min_len:
        raise RuntimeError(f"{path}: {a.shape[0]} samples, expected at least {min_len}")
    return a[:, 0] + 1j * a[:, 1]


def settled(x, flush=1024):
    """A full-chain record starts with zeros (before the stimulus is armed) and then what was still in the
    Artix FIFO and the link from before the arm (the ADC model's built-in test tone). Drop both."""
    nz = np.flatnonzero(np.abs(x) > 0)
    if len(nz) == 0:
        raise RuntimeError("record is all zeros")
    start = nz[0] + flush
    if len(x) - start < 1024:
        raise RuntimeError(f"record too short after the arm transient ({len(x) - start} samples)")
    return x[start:]


def read_audio(path, min_len=32):
    """tb_dsp_sweeps / tb_system_signals channel output: audio_l audio_r mono pilot_locked ctcss, and RDS lines."""
    l, r, m, plk, ct, pw, rds = [], [], [], [], [], [], []
    with open(path) as f:
        for ln in f:
            p = ln.split()
            if not p:
                continue
            if p[0] == "RDS":
                rds.append(int(p[1]))
            else:
                l.append(int(p[0])); r.append(int(p[1])); m.append(int(p[2])); plk.append(int(p[3]))
                ct.append(int(p[4]))
                pw.append(int(p[5]) if len(p) > 5 else 0)
    if len(l) < min_len:
        raise RuntimeError(f"{path}: {len(l)} audio samples, expected at least {min_len}")
    return dict(l=np.array(l, float), r=np.array(r, float), mono=np.array(m, float), pilot=np.array(plk),
                ctcss=np.array(ct), ctcss_pw=np.array(pw, float), rds=np.array(rds, int))


# ------------------------------------------------------------------ measurements
def dbm_to_vpeak(dbm):
    return np.sqrt(2.0 * 50.0 * 10.0 ** ((dbm - 30.0) / 10.0))


def tone_fit(x, fs, f_guess, search_hz):
    """Strongest complex tone within f_guess +/- search_hz: coarse peak of a zero-padded FFT, then the frequency
    that maximises |sum x exp(-j w n)| (golden section within one bin), and the least-squares amplitude there."""
    n = len(x)
    nfft = 1 << int(np.ceil(np.log2(n * 8)))
    X = np.fft.fft(x * np.hanning(n), nfft)
    f = np.fft.fftfreq(nfft, 1.0 / fs)
    m = np.abs(f - f_guess) <= search_hz
    fc = f[np.flatnonzero(m)[np.argmax(np.abs(X[m]))]]
    k = np.arange(n)

    def amp(fr):
        return np.abs(np.mean(x * np.exp(-2j * np.pi * fr * k / fs)))
    lo, hi = fc - fs / n, fc + fs / n
    g = (np.sqrt(5) - 1) / 2
    c, d = hi - g * (hi - lo), lo + g * (hi - lo)
    for _ in range(60):
        if amp(c) > amp(d):
            hi, d = d, c
            c = hi - g * (hi - lo)
        else:
            lo, c = c, d
            d = lo + g * (hi - lo)
    f0 = (lo + hi) / 2
    return f0, amp(f0)


def pair_fit(x, fs, f0):
    """Least-squares amplitudes of the tones at +f0 and -f0 fitted together, so that neither leaks into the other
    (a digital DDC's mirror sits exactly at -f0, often only a few resolution bins away)."""
    k = np.arange(len(x))
    e = np.exp(2j * np.pi * f0 * k / fs)
    c, *_ = np.linalg.lstsq(np.c_[e, np.conj(e)], x, rcond=None)
    return abs(c[0]), abs(c[1])


def tone_remove(x, fs, f0):
    """x less its least-squares tone at f0."""
    e = np.exp(2j * np.pi * f0 * np.arange(len(x)) / fs)
    return x - np.mean(x * np.conj(e)) * e


def noise_density(x, fs, exclude, band):
    """Complex noise PSD (codes^2/Hz) by Welch averaging over |f| <= band, skipping the (f, half-width) list."""
    nseg = 1024
    w = np.hanning(nseg)
    segs = [x[i:i + nseg] for i in range(0, len(x) - nseg + 1, nseg // 2)]
    if len(segs) < 4:
        raise RuntimeError("noise_density: record too short")
    P = np.mean([np.abs(np.fft.fft((s - s.mean()) * w)) ** 2 for s in segs], axis=0) / (fs * np.sum(w ** 2))
    f = np.fft.fftfreq(nseg, 1.0 / fs)
    m = np.abs(f) <= band
    for fc, hw in exclude:
        m &= np.abs(f - fc) > hw
    return float(np.median(P[m]))   # Welch-averaged, so the median is close to the mean and ignores spurs


def complex_noise(n, n0, fs, rng):
    s = np.sqrt(n0 * fs / 2.0)
    return s * (rng.standard_normal(n) + 1j * rng.standard_normal(n))


def sinad_db(audio, fs, f_tone, lo=250.0, hi=3000.0):
    """SINAD of a single-tone test in the lo..hi audio band: total power over everything but the tone (the tone's
    bin and the Hann window's main lobe), DC excluded."""
    s = np.asarray(audio, float)
    s = s - s.mean()
    n = len(s)
    w = np.hanning(n)
    P = np.abs(np.fft.rfft(s * w)) ** 2
    f = np.fft.rfftfreq(n, 1.0 / fs)
    band = (f >= lo) & (f <= hi)
    tone = np.abs(f - f_tone) <= 2.5 * fs / n
    p_tot = P[band].sum()
    p_nd = P[band & ~tone].sum()
    return float(10.0 * np.log10(p_tot / max(p_nd, 1e-30)))


def level_at(levels, values, target):
    """Lowest level where the (rising) curve reaches target, by linear interpolation; None if it never does."""
    levels, values = np.asarray(levels, float), np.asarray(values, float)
    for k in range(len(values)):
        if values[k] >= target:
            if k == 0:
                return float(levels[0])
            return float(np.interp(target, [values[k - 1], values[k]], [levels[k - 1], levels[k]]))
    return None


# ------------------------------------------------------------------ reference demodulators (floating point)
def fir_lowpass(n_taps, fc, fs):
    from scipy.signal import firwin
    return firwin(n_taps, fc, fs=fs)


def ref_channel(x, fs_in, decim, f_cut):
    """Ideal channel: low-pass at f_cut and decimate (polyphase, float)."""
    from scipy.signal import resample_poly
    y = resample_poly(x, 1, decim, window=("kaiser", 8.0))
    from scipy.signal import lfilter
    h = fir_lowpass(129, f_cut, fs_in / decim)
    return lfilter(h, 1.0, y)


def ref_am(x, fs_in, decim, f_cut=4000.0):
    y = ref_channel(x, fs_in, decim, f_cut)
    return np.abs(y)


def ref_ssb(x, fs_in, decim, usb=True, f_cut=3000.0):
    """Phasing SSB: the channel is centred on the suppressed carrier; shift by +/- f_cut/2 so the sideband sits in
    the low-pass, demodulate, shift back."""
    from scipy.signal import resample_poly, lfilter
    y = resample_poly(x, 1, decim, window=("kaiser", 8.0))
    fs = fs_in / decim
    n = np.arange(len(y))
    sh = 1.0 if usb else -1.0
    fo = sh * f_cut / 2.0
    z = lfilter(fir_lowpass(257, f_cut / 2.0, fs), 1.0, y * np.exp(-2j * np.pi * fo * n / fs))
    return np.real(z * np.exp(2j * np.pi * fo * n / fs))


def ref_fm(x, fs_in, decim, f_cut, deemph_us=None):
    from scipy.signal import lfilter
    y = ref_channel(x, fs_in, decim, f_cut)
    fs = fs_in / decim
    d = np.angle(y[1:] * np.conj(y[:-1])) * fs / (2 * np.pi)
    if deemph_us:
        a = np.exp(-1.0 / (fs * deemph_us * 1e-6))
        d = lfilter([1 - a], [1, -a], d)
    return d
