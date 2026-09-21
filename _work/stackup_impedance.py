#!/usr/bin/env python3
"""
Trace widths for the proposed 6-layer stackup.

Solves for the geometry that hits the two impedances this board needs:
  100 ohm differential  — the five IAS pairs and the converter LVDS
   50 ohm single-ended  — the IF lines to the SMAs

Method: IPC-2141 / Hammerstad-Jensen closed forms for microstrip and stripline,
with the usual coupled-line correction for the differential case. These are
approximations, good to roughly +/-10 %. They are enough to choose a stackup and
to sanity-check a quote; they are NOT the final word. The fabricator's own
calculator, run on their actual laminate, is the authority, and the numbers here
should be handed to them for confirmation before any board is ordered.

No dependencies: bisection, not a solver library.

Usage:  py _work/stackup_impedance.py
"""

import math

# ---------------------------------------------------------------------------
# Candidate stackup: 6 layers, 1.6 mm finished, a common fabricator offering.
# Dielectric constants are for FR-4 grade laminate at ~1 GHz. Er falls with
# frequency, so a fabricator quoting Er at 1 MHz will give optimistic widths.
# ---------------------------------------------------------------------------

STACKUP = [
    ("L1", "SIG  high-speed: IAS pairs, converter LVDS", 0.035),
    ("--", "prepreg 0.100 mm, Er 4.05", None),
    ("L2", "GND  solid reference for L1", 0.0175),
    ("--", "core    0.200 mm, Er 4.30", None),
    ("L3", "SIG  general routing", 0.0175),
    ("--", "prepreg 0.800 mm, Er 4.30", None),
    ("L4", "PWR  split planes", 0.0175),
    ("--", "core    0.200 mm, Er 4.30", None),
    ("L5", "GND  solid reference for L6", 0.0175),
    ("--", "prepreg 0.100 mm, Er 4.05", None),
    ("L6", "SIG  slow signals, fan-out", 0.035),
]

H_MICROSTRIP = 0.100      # mm, L1 to L2
ER_MICROSTRIP = 4.05
T_OUTER = 0.035           # mm, 1 oz finished

H_STRIPLINE_A = 0.200     # mm, L3 to L2
H_STRIPLINE_B = 0.800     # mm, L3 to L4
ER_CORE = 4.30
T_INNER = 0.0175          # mm, 0.5 oz


def microstrip_z0(w, h, er, t):
    """Hammerstad-Jensen microstrip, with thickness correction."""
    # Thickness correction: widen the effective trace.
    if t > 0:
        w_eff = w + (t / math.pi) * (1.0 + math.log(2.0 * h / t))
    else:
        w_eff = w
    u = w_eff / h
    er_eff = (er + 1) / 2 + (er - 1) / 2 * (1 + 12 / u) ** -0.5
    if u <= 1:
        return (60 / math.sqrt(er_eff)) * math.log(8 / u + u / 4)
    return (120 * math.pi / math.sqrt(er_eff)) / (u + 1.393 + 0.667 * math.log(u + 1.444))


def stripline_z0(w, h1, h2, er, t):
    """Offset stripline between two planes h1 and h2 away."""
    b = h1 + h2 + t
    # Symmetric form, then the offset correction of IPC-2141.
    w_eff = w + (t / math.pi) * (1.0 + math.log(2.0 * b / t)) if t > 0 else w
    z_sym = (60 / math.sqrt(er)) * math.log(4 * b / (0.67 * math.pi * (0.8 * w_eff + t)))
    if abs(h1 - h2) < 1e-9:
        return z_sym
    # Offset: the closer plane dominates. IPC-2141 offset stripline.
    c = min(h1, h2)
    return z_sym * (1 + 0.0004 * (b / max(c, 1e-6)))


def diff_from_se(z0, s, h):
    """Differential impedance of a coupled pair, from the single-ended value.

    IPC-2141: Zdiff = 2*Z0*(1 - 0.48*exp(-0.96*s/h)).  The coupling term falls
    off fast: at s = 2h the pair is almost uncoupled and Zdiff -> 2*Z0.
    """
    return 2 * z0 * (1 - 0.48 * math.exp(-0.96 * s / h))


def solve(fn, target, lo, hi, tol=1e-4):
    """Bisection on a monotonically decreasing function of width."""
    for _ in range(200):
        mid = (lo + hi) / 2
        v = fn(mid)
        if abs(v - target) < tol:
            return mid
        if v > target:
            lo = mid           # too high -> widen
        else:
            hi = mid
    return (lo + hi) / 2


def main():
    print("Proposed stackup: 6 layers, 1.6 mm finished")
    print()
    total = 0.0
    for name, desc, t in STACKUP:
        if name == "--":
            print(f"        {desc}")
            d = float(desc.split()[1])
            total += d
        else:
            print(f"   {name}  {desc}   {t*1000:.0f} um")
            total += t
    print(f"        total {total:.3f} mm before soldermask")
    print()

    # ---- 50 ohm single-ended microstrip on L1 --------------------------
    f_ms = lambda w: microstrip_z0(w, H_MICROSTRIP, ER_MICROSTRIP, T_OUTER)
    w50 = solve(f_ms, 50.0, 0.02, 2.0)
    print("L1 microstrip over L2, h = 0.100 mm, Er = 4.05, t = 35 um")
    print(f"   50 ohm single-ended  ->  W = {w50*1000:.0f} um   "
          f"(check: {f_ms(w50):.2f} ohm)")

    # ---- 100 ohm differential on L1 -------------------------------------
    print()
    print("   100 ohm differential, for a few trace/gap combinations:")
    print("      W (um)   S (um)   Z0 (ohm)   Zdiff (ohm)")
    best = None
    for s_um in (100, 125, 150, 175, 200):
        s = s_um / 1000.0
        f_diff = lambda w: diff_from_se(f_ms(w), s, H_MICROSTRIP)
        w = solve(f_diff, 100.0, 0.02, 2.0)
        z0 = f_ms(w)
        zd = diff_from_se(z0, s, H_MICROSTRIP)
        flag = ""
        if 0.090 <= w <= 0.200:          # comfortably manufacturable
            flag = "  <- good candidate"
            if best is None:
                best = (w, s)
        print(f"      {w*1000:6.0f}   {s_um:6d}   {z0:8.2f}   {zd:9.2f}{flag}")

    if best:
        w, s = best
        print()
        print(f"   RECOMMENDED: W = {w*1000:.0f} um, S = {s*1000:.0f} um")
        print(f"   Pitch = {(w+s)*1000:.0f} um, so a pair occupies "
              f"{(2*w+s)*1000:.0f} um of routing channel.")

    # ---- stripline on L3 -------------------------------------------------
    print()
    print(f"L3 stripline between L2 and L4, {H_STRIPLINE_A:.3f} / "
          f"{H_STRIPLINE_B:.3f} mm, Er = {ER_CORE}, t = 17.5 um")
    f_sl = lambda w: stripline_z0(w, H_STRIPLINE_A, H_STRIPLINE_B, ER_CORE, T_INNER)
    w50s = solve(f_sl, 50.0, 0.02, 2.0)
    print(f"   50 ohm single-ended  ->  W = {w50s*1000:.0f} um   "
          f"(check: {f_sl(w50s):.2f} ohm)")
    for s_um in (150, 200, 250):
        s = s_um / 1000.0
        f_d = lambda w: diff_from_se(f_sl(w), s, H_STRIPLINE_A)
        w = solve(f_d, 100.0, 0.02, 2.0)
        print(f"   100 ohm differential, S = {s_um} um  ->  W = {w*1000:.0f} um")

    # ---- sanity notes -----------------------------------------------------
    print()
    print("Notes that matter more than the third decimal place:")
    print("  · These are IPC-2141 closed forms, good to about +/-10 %. Hand them")
    print("    to the fabricator and use THEIR field-solver numbers on the board.")
    print("  · Er drops with frequency. A fabricator quoting Er at 1 MHz will")
    print("    give widths that run high in impedance at 1 Gbps.")
    print("  · The L1 pairs need L2 as a solid, unbroken reference. A split under")
    print("    a differential pair costs more than any width error here.")
    print("  · Keep the IAS pairs on L1 end to end. Every via pair is a stub and")
    print("    a reference change.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
