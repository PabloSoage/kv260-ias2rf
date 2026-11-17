"""Figures for the Kria software and the vehicle integrations (docs/INTEGRATIONS.md).

    python sw/integrations/kria_sw_figures.py [--telemetry-csv FILE]

- pps_discipline.png: R5F core 0's PPS loop (sw/kria/core, pps::Discipline)
  against a model of kria_pps, from `cargo run --example pps_sim` (run here).
- radar_bus_load.png: bus load of a 77 GHz radar's output on classic CAN,
  CAN FD and 100BASE-T1, objects and detections.
- telemetry_e2e.png: the ECU stream through kria-vehicled, from the CSV it
  writes with --csv --interlock (the end-to-end run in INTEGRATIONS.md 4.3).
  Only rates and interlock states are plotted, never the engine values.
"""
import argparse
import csv
import io
import os
import subprocess
from collections import Counter

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
IMG = os.path.join(ROOT, "docs", "img", "integrations")

# Reference categorical order (dataviz palette, light mode) and status colours.
C1, C2, C3, C4 = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
GOOD, WARN, CRIT = "#1baf7a", "#eda100", "#d6455d"
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"

plt.rcParams.update({
    "font.size": 10, "axes.edgecolor": INK2, "axes.labelcolor": INK, "xtick.color": INK2,
    "ytick.color": INK2, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
    "axes.spines.top": False, "axes.spines.right": False, "legend.frameon": False,
    "lines.linewidth": 2.0,
})


def pps_figure():
    out = subprocess.run(
        ["cargo", "run", "-q", "--release", "-p", "kria-core", "--example", "pps_sim"],
        cwd=os.path.join(ROOT, "sw", "kria"), check=True, capture_output=True, text=True).stdout
    rows = list(csv.DictReader(io.StringIO(out)))
    t = [int(r["second"]) for r in rows]
    err = [float(r["gen_error_ns"]) for r in rows]
    state = [r["state"] for r in rows]
    cap = [int(r["captured"]) for r in rows]

    fig, (ax, ax2) = plt.subplots(2, 1, figsize=(9, 5.2), sharex=True,
                                  gridspec_kw={"height_ratios": [4, 1]})
    ax.plot(t, [abs(e) for e in err], color=C1, label="generated second vs true GPS second")
    ax.set_yscale("log")
    ax.set_ylim(1, 2e5)
    ax.axvspan(420, 540, color=WARN, alpha=0.15, lw=0)
    ax.text(480, 6e4, "GPS lost 120 s\n(holdover)", ha="center", color=INK2, fontsize=9)
    fp = t[cap.index(2)]
    ax.axvline(fp, color=CRIT, lw=1, ls="--")
    ax.text(fp + 6, 3e3, "false pulse 250 us early:\nrejected", color=INK2, fontsize=9)
    ax.axhline(200, color=INK2, lw=0.8, ls=":")
    ax.text(895, 230, "lock threshold 200 ns", ha="right", color=INK2, fontsize=8)
    ax.set_ylabel("|phase error| (ns)")
    locked = [abs(e) for e, s, x in zip(err, state, t) if s == "locked" and 60 < x < 420]
    ax.set_title("PPS discipline on R5F core 0: oscillator 37 ppm fast, warming +0.6 ppm, "
                 f"receiver jitter +-20 ns\nlocked: worst {max(locked):.0f} ns", fontsize=10, loc="left")
    ax.legend(loc="upper right")

    colours = {"acquiring": WARN, "locked": GOOD, "holdover": CRIT}
    start = 0
    for i in range(1, len(t) + 1):
        if i == len(t) or state[i] != state[start]:
            ax2.axvspan(t[start] - 0.5, t[i - 1] + 0.5, color=colours[state[start]], lw=0)
            if t[i - 1] - t[start] > 40:
                ax2.text((t[start] + t[i - 1]) / 2, 0.5, state[start], ha="center", va="center",
                         color="white", fontsize=9, fontweight="bold")
            start = i
    ax2.set_yticks([])
    ax2.grid(False)
    ax2.set_xlabel("time (s)")
    ax2.set_xlim(0, 900)
    fig.tight_layout()
    fig.savefig(os.path.join(IMG, "pps_discipline.png"), dpi=150)
    plt.close(fig)
    return {"locked_worst_ns": max(locked),
            "holdover_end_ns": abs(err[t.index(539)]),
            "relock_s": next(x for x, s in zip(t, state) if x > 540 and s == "locked") - 540}


# ---------------------------------------------------------------- radar bus

CYCLE_HZ = 20.0            # one object list every 50 ms
BYTES_PER_OBJECT = 24      # three 8-byte frames per object on classic CAN (ARS408-style)
BYTES_PER_DETECTION = 8


def can_classic_bits(nbytes):
    """Worst-case stuffed 11-bit-ID frames, 8 bytes each: 135 bits per frame."""
    frames = -(-nbytes // 8)
    return frames * 135, 0.0


def can_fd_time(nbytes, data_rate):
    """64-byte CAN FD frames: ~30 bits at 500 kbit/s arbitration, ~590 at the data rate."""
    frames = -(-nbytes // 64)
    return frames * (30 / 500e3 + 590 / data_rate)


def eth_time(nbytes, rate=100e6):
    """UDP over 100BASE-T1: 1472-byte payloads, 66 bytes of headers, preamble and gap each."""
    packets = -(-nbytes // 1472)
    return (nbytes + packets * (42 + 24)) * 8 / rate


def bus_loads(nbytes):
    per_cycle = {
        "CAN 500 kbit/s": can_classic_bits(nbytes)[0] / 500e3,
        "CAN FD 2 Mbit/s data": can_fd_time(nbytes, 2e6),
        "CAN FD 5 Mbit/s data": can_fd_time(nbytes, 5e6),
        "100BASE-T1 Ethernet": eth_time(nbytes),
    }
    return {k: 100 * v * CYCLE_HZ for k, v in per_cycle.items()}


def radar_figure():
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 4.2), sharey=True)
    colours = [C2, C1, C3, C4]
    objs = list(range(1, 257))
    dets = list(range(10, 2001, 10))
    for ax, xs, per, title in ((a1, objs, BYTES_PER_OBJECT, "object list (tracked targets)"),
                               (a2, dets, BYTES_PER_DETECTION, "detection list (point cloud)")):
        loads = [bus_loads(x * per + 8) for x in xs]
        for c, k in zip(colours, loads[0]):
            ax.plot(xs, [ld[k] for ld in loads], color=c, label=k)
        ax.axhline(70, color=INK2, lw=0.8, ls=":")
        ax.set_yscale("log")
        ax.set_ylim(0.05, 3000)
        ax.set_title(title, fontsize=10, loc="left")
        ax.set_xlabel("per 50 ms cycle")
    a1.text(250, 80, "70 % usable", ha="right", color=INK2, fontsize=8)
    a1.set_ylabel("bus load (%)")
    a2.legend(loc="lower right")
    fig.suptitle("77 GHz radar output at 20 Hz: which bus carries it", x=0.01, ha="left", fontsize=11)
    fig.tight_layout()
    fig.savefig(os.path.join(IMG, "radar_bus_load.png"), dpi=150)
    plt.close(fig)
    table = {}
    for n in (32, 64, 100, 256):
        table[f"{n} objects"] = {k: round(v, 1) for k, v in bus_loads(n * BYTES_PER_OBJECT + 8).items()}
    for n in (500, 1000, 2000):
        table[f"{n} detections"] = {k: round(v, 1) for k, v in bus_loads(n * BYTES_PER_DETECTION + 8).items()}
    return table


# ------------------------------------------------------------ telemetry e2e

def telemetry_figure(path, switch_s):
    samples, il = [], []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            if r["id"] == "interlock":
                il.append((float(r["recv_ms"]) / 1e3, r["unit"].split("/")[0]))
            else:
                samples.append((float(r["recv_ms"]) / 1e3, r["id"]))
    end = max(s for s, _ in samples)
    bins = Counter(int(s * 4) for s, _ in samples)
    xs = [b / 4 for b in range(int(end * 4) + 1)]
    rate = [bins.get(b, 0) * 4 for b in range(len(xs))]
    first_new = next(s for s, i in samples if s > switch_s + 0.5 and i in ("0x0023", "0x308A")
                     and s > switch_s) if switch_s else None
    gap = max((b - a for (a, _), (b, _) in zip(samples, samples[1:]) if a > switch_s - 1), default=0)

    fig, (ax, ax2) = plt.subplots(2, 1, figsize=(9, 4.8), sharex=True,
                                  gridspec_kw={"height_ratios": [3, 1]})
    ax.step(xs, rate, where="post", color=C1)
    ax.set_ylabel("values/s received")
    if switch_s:
        for a in (ax, ax2):
            a.axvline(switch_s, color=INK2, lw=1, ls="--")
        ax.text(switch_s + 0.2, max(rate) * 0.92, f"selection changed:\n{gap:.1f} s with no values",
                color=INK2, fontsize=9)
    ax.set_title("ECU stream end to end: emulated ECU, SM3 protocol, opendash-telemetry/1, "
                 "kria-vehicled\n12 rows at 100 Hz, then 4 rows", fontsize=10, loc="left")
    colours = {"Keyed": GOOD, "Settling": WARN, "SpeedUnknown": CRIT, "Moving": CRIT}
    labels = {"Keyed": "transmit allowed", "Settling": "parked < 3 s", "SpeedUnknown": "no speed"}
    start = 0
    for i in range(1, len(il) + 1):
        if i == len(il) or il[i][1] != il[start][1]:
            a, b, s = il[start][0], il[i - 1][0] + 0.05, il[start][1]
            ax2.axvspan(a, b, color=colours.get(s, INK2), lw=0)
            if b - a > 1.2:
                ax2.text((a + b) / 2, 0.5, labels.get(s, s), ha="center", va="center", color="white",
                         fontsize=8, fontweight="bold")
            start = i
    ax2.set_yticks([])
    ax2.grid(False)
    ax2.set_ylabel("interlock", rotation=0, ha="right", va="center")
    ax2.set_xlabel("time (s)")
    ax2.set_xlim(0, end)
    fig.tight_layout()
    fig.savefig(os.path.join(IMG, "telemetry_e2e.png"), dpi=150)
    plt.close(fig)
    lost = next((t for t, s in il if t > switch_s and s != "Keyed"), None)
    back = next((t for t, s in il if lost and t > lost and s == "Keyed"), None)
    return {"gap_s": round(gap, 2), "first_new_s": first_new, "values_per_s_before": max(rate[:int(switch_s * 4)]),
            "locked_out_s": round(back - lost, 2) if back else None,
            "locked_out_from_s": round(lost - switch_s, 2) if lost else None}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--telemetry-csv")
    ap.add_argument("--switch-s", type=float, default=14.0)
    a = ap.parse_args()
    os.makedirs(IMG, exist_ok=True)
    print("pps:", pps_figure())
    for k, v in radar_figure().items():
        print("radar", k, v)
    if a.telemetry_csv:
        print("telemetry:", telemetry_figure(a.telemetry_csv, a.switch_s))
