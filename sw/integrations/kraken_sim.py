#!/usr/bin/env python3
"""Synthetic KrakenSDR capture for the end-to-end direction-finding test (docs/INTEGRATIONS.md section 9).

Writes what the KV260 would read from the KrakenSDR's five RTL2832U devices over USB: one file per channel of
unsigned 8-bit interleaved I/Q (the RTL-SDR's format, zero at 127.5), cut into the 256 KiB bulk transfers that
librtlsdr hands its callback. The channels share one clock, so they never drift apart, but:

  - each RTL device starts streaming at its own moment, so the five files are offset by a whole number of
    samples (0 to 37 here, of the order a USB hub gives);
  - each R820T2's synthesiser locks with its own phase, and each channel has its own gain: a random complex
    gain per channel;
  - for the first NOISE_N samples the KrakenSDR's noise source is on (the control channel's bias-tee GPIO):
    one strong noise signal reaches all five inputs through the calibration switches, with each channel's
    delay and gain but no array geometry;
  - then the noise source is off and the antennas see two emitters: a narrowband FM signal at bearing 117
    degrees and a weaker one (-6 dB) at 250 degrees, on a five-element circular array (UCA) of 0.5 lambda
    spacing at 446 MHz, plus each channel's own thermal noise.

    python sw/integrations/kraken_sim.py [OUT_DIR]       # default fpga/sim/out/kraken

The truth (delays, gains, bearings, array) goes to truth.json for the checks downstream.
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "fpga" / "sim" / "out" / "kraken"

FS = 2.4e6            # RTL sample rate, the KrakenSDR default (heimdall daq_chain_config.ini)
F_RF = 446.0e6        # PMR446
M = 5
NOISE_N = 1 << 16     # samples with the noise source on
CPI_N = 1 << 16       # samples for one direction-finding CPI
SPARE = 512           # extra samples so every channel still has NOISE_N + CPI_N after its start offset
XFER = 262144         # bytes per USB bulk transfer (librtlsdr's default buffer)
LAM = 299792458.0 / F_RF
SPACING = 0.5 * LAM
RADIUS = SPACING / (2.0 * np.sin(np.pi / M))
EMITTERS = [  # bearing (deg), amplitude (RMS at the ADC, codes), baseband offset (Hz), FM deviation (Hz)
    (117.0, 22.0, 180e3, 5e3),
    (250.0, 11.0, -420e3, 3e3),
]
NOISE_SRC_RMS = 38.0  # noise source at the ADC, codes RMS (per I or Q)
THERMAL_RMS = 2.2     # each channel's own noise, codes RMS (per I or Q)


def element_xy():
    k = np.arange(M)
    return RADIUS * np.cos(2 * np.pi * k / M), RADIUS * np.sin(2 * np.pi * k / M)


def steering(theta_deg):
    x, y = element_xy()
    th = np.deg2rad(theta_deg)
    return np.exp(1j * 2 * np.pi / LAM * (x * np.cos(th) + y * np.sin(th)))


def main():
    rng = np.random.default_rng(20261118)
    OUT.mkdir(parents=True, exist_ok=True)
    n = NOISE_N + CPI_N + SPARE
    t = np.arange(n) / FS

    # what each antenna input sees, aligned in time
    clean = np.zeros((M, n), complex)
    noise = (rng.standard_normal(n) + 1j * rng.standard_normal(n)) * NOISE_SRC_RMS
    clean[:, :NOISE_N] += noise[None, :NOISE_N]
    for bearing, amp, f_off, dev in EMITTERS:
        fm = np.cumsum(np.sin(2 * np.pi * 1.0e3 * t) * dev) / FS
        s = amp * np.sqrt(2) * np.exp(1j * (2 * np.pi * (f_off * t + fm) + rng.uniform(0, 2 * np.pi)))
        s[:NOISE_N] *= 0.03    # the calibration switches isolate the antennas while the noise source is on
        clean += steering(bearing)[:, None] * s[None, :]

    gains = rng.uniform(0.7, 1.3, M) * np.exp(1j * rng.uniform(-np.pi, np.pi, M))
    gains[0] = abs(gains[0])
    delays = np.array([0, 13, 37, 5, 22])      # samples each stream starts late
    files = []
    for k in range(M):
        x = clean[k] * gains[k]
        x += (rng.standard_normal(n) + 1j * rng.standard_normal(n)) * THERMAL_RMS
        # a stream that starts d samples late begins at sample d of the common time line
        x = x[delays[k]:delays[k] + NOISE_N + CPI_N]
        iq = np.empty(2 * x.size)
        iq[0::2], iq[1::2] = x.real, x.imag
        u8 = np.clip(np.round(iq + 127.5), 0, 255).astype(np.uint8)
        f = OUT / f"ch{k}.u8"
        f.write_bytes(u8.tobytes())
        files.append(f.name)

    truth = {
        "fs": FS, "f_rf": F_RF, "m": M, "noise_n": NOISE_N, "cpi_n": CPI_N, "xfer": XFER,
        "array": "UCA", "radius_m": RADIUS, "spacing_m": SPACING, "lambda_m": LAM,
        "delays": delays.tolist(),
        "gain_re": gains.real.tolist(), "gain_im": gains.imag.tolist(),
        "emitters": [{"bearing": b, "amp": a, "f_off": f, "dev": d} for b, a, f, d in EMITTERS],
        "files": files,
    }
    (OUT / "truth.json").write_text(json.dumps(truth, indent=1))
    # what the operator sets on the KV260 (the daemon does not see the truth)
    (OUT / "setup.txt").write_text(
        f"fs = {FS}\nf_rf = {F_RF}\nradius_m = {RADIUS:.6f}\nnoise_n = {NOISE_N}\nxfer = {XFER}\nn_log2 = 15\n")
    print(f"wrote {M} channels of {NOISE_N + CPI_N} samples to {OUT}; delays {delays.tolist()}; "
          f"UCA radius {RADIUS * 100:.1f} cm")


if __name__ == "__main__":
    main()
