#!/usr/bin/env python3
"""
Per-rail current budget for the Rev03 adapter board.

Every load carries its source and a confidence mark, because the difference
between a measured figure and a guess is the whole point of a budget:

  V  verified — measured, or taken from a file in a repository we have
  E  estimate — engineering judgement from the device class. NEEDS CHECKING
  ?  unknown  — placeholder, must be replaced before anything is ordered

analog.com would not serve its datasheets while this was written (repeated
timeouts, and the mirrors return 403/410), so the converter figures are marked
E and the exact table and page to check is named for each. Swapping in a real
number is a one-line edit here; the totals, the regulator choices and the
dissipation all follow automatically.

Usage:  py _work/power_budget.py
"""

# (rail, load, volts, milliamps, confidence, source / what to check)
LOADS = [
    # ---- FPGA ---------------------------------------------------------
    ("+1V0", "XC7A50T VCCINT", 1.0, 700, "E",
     "AERIS-10's design on the same part reports 0.730 W total in Vivado "
     "[V]. VCCINT dominates; 700 mA at 1.0 V leaves room for our link SerDes"),
    ("+1V8_D", "XC7A50T VCCAUX", 1.8, 100, "E", "DS181, typical for this device size"),
    ("+1V2", "XC7A50T VCCO, IAS-facing bank", 1.2, 100, "E",
     "5 LVDS_12 pairs plus bank overhead"),
    ("+3V3_D", "XC7A50T VCCO, converter and Pmod banks", 3.3, 200, "E", "DS181"),
    ("+3V3_D", "QSPI config flash", 3.3, 20, "E", "read current during boot only"),

    # ---- converters ---------------------------------------------------
    ("+1V8_A", "AD9484 AVDD, 400 MSPS", 1.8, 400, "E",
     "AD9484 datasheet Rev. A, Table 2 SUPPLY CURRENTS. CHECK IAVDD at 400 MSPS"),
    ("+1V8_D", "AD9484 DRVDD, LVDS drivers", 1.8, 130, "E",
     "AD9484 Table 2. Digital power is set by the LVDS driver bias, so it is "
     "nearly independent of sample rate"),
    ("+1V8_A", "AD9253 AVDD, 2 of 4 channels at 62.5 MSPS", 1.8, 200, "E",
     "AD9253 datasheet Table 2. Quad at 125 MSPS is about 1.1 W total; two "
     "channels at half rate is well under a quarter of that"),
    ("+3V3_D", "AD9253 DRVDD", 3.3, 60, "E", "AD9253 Table 2"),
    ("+3V3_A", "AD9708 AVDD, radar DAC", 3.3, 40, "E", "AD9708 Table 1"),
    ("+3V3_A", "AD9767 AVDD, dual SDR DAC", 3.3, 100, "E", "AD9767 Table 1"),
    ("+3V3_D", "AD9708 + AD9767 DVDD", 3.3, 60, "E", "datasheet Table 1, both parts"),
    ("+3V3_A", "AD8352 differential drivers, x2", 3.3, 100, "E",
     "AD8352 Table 1. About 50 mA each with the recommended bias"),

    # ---- clock ---------------------------------------------------------
    ("+3V3_D", "ADCLK944 LVPECL fanout", 3.3, 150, "E",
     "ADCLK944 datasheet Table 1. LVPECL draws constant current; CHECK whether "
     "the quoted ICC already includes output termination"),
    ("+3V3_D", "LVPECL output termination, 4 outputs", 3.3, 60, "E",
     "about 15 mA per terminated output pair into the bias network"),
    ("+3V3_D", "TCXO", 3.3, 20, "E", "typical for a 100 MHz TCXO"),

    # ---- RF routing and glue -------------------------------------------
    ("+3V3_D", "M3SWA2-34DR+ SPDT, x4", 3.3, 40, "E",
     "Mini-Circuits datasheet: 3.3-3.6 V supply, internal driver [V for the "
     "voltage]. CHECK the supply current per part"),
    ("+3V3_D", "Level translators to 1.8 V", 3.3, 50, "E", "SN74AVC-class, switching"),
    ("+3V3_D", "Housekeeping: temp sensor, EEPROM, LEDs", 3.3, 30, "E", ""),
]

# rail -> (source rail, converter type, efficiency or dropout)
# Two pre-regulator bucks exist purely to keep the analogue LDOs cool. The
# first pass of this budget had +3V3_A as an LDO straight off 5 V (1.43 W) and
# +1V8_A off 3V3 (0.90 W) - the same class of mistake the Rev01 design made
# with its ADP151. Dropping a buck in front of each LDO keeps the LDO's noise
# rejection where it matters while cutting the dissipation to something a
# small package can actually shed.
TREE = {
    "+5V0":   ("+12V",   "buck", 0.90),
    "+3V3_D": ("+5V0",   "buck", 0.90),
    "+3V6":   ("+5V0",   "buck", 0.90),   # pre-regulator for the analogue 3V3
    "+3V3_A": ("+3V6",   "ldo",  None),
    "+2V5":   ("+5V0",   "buck", 0.88),   # pre-regulator for the analogue 1V8
    "+1V8_A": ("+2V5",   "ldo",  None),
    "+1V8_D": ("+3V3_D", "ldo",  None),
    "+1V2":   ("+3V3_D", "ldo",  None),
    "+1V0":   ("+5V0",   "buck", 0.88),
}

VOLTS = {"+12V": 12.0, "+5V0": 5.0, "+3V6": 3.6, "+3V3_D": 3.3, "+3V3_A": 3.3,
         "+2V5": 2.5, "+1V8_A": 1.8, "+1V8_D": 1.8, "+1V2": 1.2, "+1V0": 1.0}

MARGIN = 1.30          # design margin on every rail


def main():
    rails = {}
    for rail, name, v, ma, conf, src in LOADS:
        rails.setdefault(rail, []).append((name, v, ma, conf, src))

    print("PER-RAIL LOADS")
    print()
    direct = {}
    for rail in sorted(rails, key=lambda r: -VOLTS[r]):
        print(f"  {rail}  ({VOLTS[rail]:.1f} V)")
        tot = 0
        for name, v, ma, conf, src in rails[rail]:
            print(f"      [{conf}] {name:52s} {ma:5d} mA")
            tot += ma
        direct[rail] = tot
        print(f"          {'subtotal':52s} {tot:5d} mA")
        print()

    # Propagate loads up the tree, innermost first.
    order = ["+1V2", "+1V8_D", "+1V8_A", "+2V5", "+1V0", "+3V3_A", "+3V6",
             "+3V3_D", "+5V0", "+12V"]
    load = {r: direct.get(r, 0) for r in VOLTS}
    diss = {}

    for rail in order:
        if rail not in TREE:
            continue
        src, kind, eff = TREE[rail]
        i_out = load[rail]
        v_out, v_in = VOLTS[rail], VOLTS[src]
        if kind == "ldo":
            i_in = i_out                       # LDO passes its output current
            diss[rail] = (v_in - v_out) * i_out / 1000.0
        else:
            p_out = v_out * i_out / 1000.0
            p_in = p_out / eff
            i_in = p_in / v_in * 1000.0
            diss[rail] = p_in - p_out
        load[src] = load.get(src, 0) + i_in

    print("REGULATOR CHAIN")
    print()
    print(f"  {'rail':8s} {'Vout':>6s} {'Iout':>8s} {'type':>6s} {'from':>8s} "
          f"{'diss':>8s}   sizing")
    for rail in order:
        if rail not in TREE:
            continue
        src, kind, eff = TREE[rail]
        i = load[rail]
        d = diss[rail]
        need = i * MARGIN / 1000.0
        warn = ""
        if kind == "ldo" and d > 0.8:
            warn = "  <-- too hot for an LDO, use a buck"
        elif kind == "ldo" and d > 0.4:
            warn = "  <-- needs a thermal pad"
        print(f"  {rail:8s} {VOLTS[rail]:5.1f}V {i:7.0f}mA {kind:>6s} {src:>8s} "
              f"{d:7.2f}W   >= {need:.2f} A{warn}")

    print()
    i12 = load["+12V"]
    p12 = 12.0 * i12 / 1000.0
    print(f"INPUT: {i12:.0f} mA at 12 V  =  {p12:.1f} W")
    print(f"  with {int((MARGIN-1)*100)} % margin: {i12*MARGIN/1000:.2f} A, "
          f"{p12*MARGIN:.1f} W")
    print(f"  jack and input protection rated for >= {round(i12*MARGIN/1000*2)/2:.1f} A")

    print()
    n_e = sum(1 for *_, c, _ in LOADS if c == "E")
    n_v = sum(1 for *_, c, _ in LOADS if c == "V")
    print(f"CONFIDENCE: {n_v} verified, {n_e} estimated, of {len(LOADS)} loads.")
    print("  This budget sizes the regulators and the input. It is NOT a")
    print("  thermal sign-off. Before ordering, replace every [E] with the")
    print("  datasheet figure named beside it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
