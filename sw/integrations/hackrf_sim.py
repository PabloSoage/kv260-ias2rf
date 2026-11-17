#!/usr/bin/env python3
"""Synthetic HackRF Pro sweep capture for the end-to-end test (docs/INTEGRATIONS.md section 10).

Writes what libhackrf hands the KV260 in sweep mode, as hackrf_sweep sets it up (20 MS/s, 16,384-byte blocks, one
block per tuning, INTERLEAVED steps of +5 and +15 MHz, the LO 7.5 MHz above the block's frequency): each block is
0x7F 0x7F, the frequency as a little-endian u64, then signed 8-bit I/Q. The Pro discards one block after each
retune in its firmware, so every block that arrives is settled.

The scene is a car's radio environment from 0 to 7.2 GHz: FM broadcast, DAB, DVB-T, PMR446, the mobile bands
(LTE 800/900/1800/2100/2600, 5G NR at 3.5 GHz), ADS-B, Wi-Fi at 2.4 and 5 GHz, Bluetooth hops, an analogue FPV
video link at 5.8 GHz and ITS-G5 at 5.9 GHz. Levels are at the ADC, in dB below full scale per signal. The
baseband filter is 15 MHz wide (the hackrf_sweep default). Block 300's header is corrupted on purpose: the PL must
drop it and count it.

    python sw/integrations/hackrf_sim.py [OUT_DIR]       # default fpga/sim/out/hackrf
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "fpga" / "sim" / "out" / "hackrf"

FS = 20e6
OFFSET = 7.5e6
BLOCK = 16384
NS = BLOCK // 2
F_MIN, F_MAX = 0, 7200          # MHz
NOISE_RMS = 1.6                 # codes per I or Q
BAD_BLOCK = 300

# (name, centre MHz, width MHz, level dBFS); width 0 is a carrier (with FM)
SCENE = [
    ("FM 89.7", 89.7, 0.18, -12), ("FM 93.5", 93.5, 0.18, -18), ("FM 97.2", 97.2, 0.18, -9),
    ("FM 101.8", 101.8, 0.18, -21), ("FM 105.4", 105.4, 0.18, -15),
    ("DAB 12C", 227.36, 1.536, -30), ("DVB-T 35", 586.0, 7.6, -28), ("DVB-T 41", 634.0, 7.6, -32),
    ("PMR446", 446.05625, 0.0, -24),
    ("LTE 800", 806.0, 10.0, -26), ("GSM/LTE 900", 947.5, 5.0, -24), ("ADS-B", 1090.0, 2.0, -38),
    ("LTE 1800", 1842.5, 20.0, -27), ("UMTS 2100", 2140.0, 15.0, -31),
    ("Wi-Fi ch 1", 2412.0, 20.0, -22), ("Wi-Fi ch 6", 2437.0, 20.0, -30),
    ("BT 2426", 2426.0, 1.0, -26), ("BT 2458", 2458.0, 1.0, -29), ("BT 2474", 2474.0, 1.0, -33),
    ("LTE 2600", 2655.0, 20.0, -29), ("5G NR n78", 3550.0, 40.0, -30),
    ("Wi-Fi ch 36", 5180.0, 20.0, -31), ("Wi-Fi ch 100", 5500.0, 40.0, -35),
    ("FPV 5.8", 5800.0, 8.0, -20), ("ITS-G5", 5900.0, 10.0, -33),
]


def sweep_plan():
    v, f, odd = [], F_MIN * 1_000_000, True
    while True:
        v.append(f)
        if not odd and f + 20_000_000 >= F_MAX * 1_000_000:
            break
        f += 5_000_000 if odd else 15_000_000
        odd = not odd
    return v


def baseband_filter(freqs):
    """15 MHz baseband filter: flat to +-7 MHz, then 12 dB/MHz."""
    a = np.abs(freqs) / 1e6
    return 10 ** (-np.maximum(0, a - 7.0) * 12 / 20)


def block_samples(lo, rng):
    t = np.arange(NS) / FS
    fr = np.fft.fftfreq(NS, 1 / FS)
    x = np.zeros(NS, complex)
    for name, fc, bw, lvl in SCENE:
        off = fc * 1e6 - lo
        if abs(off) > 12e6 + bw * 0.5e6:
            continue
        amp = 127 * 10 ** (lvl / 20)
        if bw <= 0.2:
            dev = 75e3 if bw > 0 else 2.5e3
            ph = 2 * np.pi * off * t + dev / 1e3 * np.sin(2 * np.pi * 1e3 * t) + rng.uniform(0, 2 * np.pi)
            x += amp * np.exp(1j * ph)
        else:
            spec = (rng.standard_normal(NS) + 1j * rng.standard_normal(NS))
            spec *= (np.abs(fr - off) <= bw * 0.5e6)
            s = np.fft.ifft(spec)
            s *= amp / np.sqrt(np.mean(np.abs(s) ** 2) + 1e-30)
            x += s
    xf = np.fft.fft(x) * baseband_filter(fr)
    x = np.fft.ifft(xf)
    x += (rng.standard_normal(NS) + 1j * rng.standard_normal(NS)) * NOISE_RMS
    iq = np.empty(2 * NS)
    iq[0::2], iq[1::2] = x.real, x.imag
    return np.clip(np.round(iq), -128, 127).astype(np.int8)


def main():
    rng = np.random.default_rng(20261118)
    OUT.mkdir(parents=True, exist_ok=True)
    plan = sweep_plan()
    out = bytearray()
    for i, f in enumerate(plan):
        b = block_samples(f + OFFSET, rng).tobytes()
        hdr = bytes([0x7F, 0x7F]) + int(f).to_bytes(8, "little")
        if i == BAD_BLOCK:
            hdr = bytes([0x7F, 0x3F]) + hdr[2:]
        out += hdr + b[10:]
    (OUT / "sweep.bin").write_bytes(bytes(out))
    (OUT / "setup.txt").write_text("pshift = 3\nnseg_log2 = 3\ndetect_db = 5\n")
    truth = {"scene": [{"name": n, "f_mhz": f, "bw_mhz": b, "dbfs": l} for n, f, b, l in SCENE],
             "blocks": len(plan), "bad_block": BAD_BLOCK, "bad_block_f": plan[BAD_BLOCK]}
    (OUT / "truth.json").write_text(json.dumps(truth, indent=1))
    print(f"wrote {len(plan)} blocks ({len(out) / 1e6:.1f} MB) for {F_MIN}-{F_MAX} MHz to {OUT}")


if __name__ == "__main__":
    main()
