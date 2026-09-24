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
    ("+1V8_A", "AD9484 AVDD", 1.8, 300, "V",
     "AD9484 datasheet, POWER SUPPLY table: IAVDD 283 mA typ, 300 mA max. "
     "Quoted at the rated 500 MSPS, so 400 MSPS is a little lower - using the "
     "500 MSPS figure is the conservative choice. Cross-check: "
     "(283+89) mA x 1.8 V = 670 mW, which is the stated SDR-mode dissipation"),
    ("+1V8_D", "AD9484 DRVDD, LVDS drivers", 1.8, 100, "V",
     "AD9484 datasheet, POWER SUPPLY table: IDRVDD 89 mA typ, 100 mA max in "
     "SDR mode. Set by the LVDS driver bias, so nearly independent of rate"),
    ("+1V8_A", "AD9253 AVDD", 1.8, 200, "V",
     "AD9253 datasheet Rev. D, Table 1, -125 grade: IAVDD 183 mA typ, 200 mA "
     "max - all FOUR channels at 125 MSPS. We use two channels at 62.5 MSPS "
     "and can power the other two down over SPI, so this is an upper bound. "
     "Cross-check: (183+71) mA x 1.8 V = 457 mW, the stated four-channel "
     "sine-wave figure"),
    # DRVDD IS 1.8 V. The first version of this budget had it on +3V3_D;
    # absolute maximum is 2.0 V, so that would have destroyed the ADC.
    ("+1V8_D", "AD9253 DRVDD, LVDS drivers", 1.8, 100, "V",
     "AD9253 datasheet Rev. D, Table 1: DRVDD 1.7-1.9 V; IDRVDD 71 mA typ, "
     "100 mA max, ANSI-644 mode. Abs. max DRVDD 2.0 V"),
    ("+3V3_A", "AD9708 AVDD, radar DAC", 3.3, 25, "V",
     "AD9708 datasheet: Analog Supply Current IAVDD 25 mA"),
    ("+3V3_A", "AD9767 AVDD, dual SDR DAC", 3.3, 75, "V",
     "AD9763/65/67 datasheet Rev. G, Table 1: IAVDD 71 mA typ, 75 mA max, "
     "whole chip at IOUTFS = 20 mA per DAC. Cross-check: (75+15) mA x 5 V = "
     "450 mW, the stated dissipation"),
    ("+3V3_D", "AD9708 DVDD", 3.3, 3, "V",
     "AD9708 datasheet: Digital Supply Current IDVDD 3 mA"),
    ("+3V3_D", "AD9767 DVDD", 3.3, 19, "V",
     "Same table: IDVDD 15 mA at 100 MSPS (no maximum given). Digital "
     "current scales with clock, so 15 x 125/100 = 19 mA at the part's full "
     "125 MSPS. Measured at DVDD = 5 V, so at 3.3 V this over-estimates"),
    # The AD8352s moved from +3V3_A to +5V0 when ADC_RADAR was drawn (24 Sep):
    # the datasheet characterises the part at 5 V only (Table 1), AERIS-10
    # runs its two at 5 V, and 3 V is merely inside the allowed range.
    ("+5V0", "AD8352 radar drivers, x2 (via +5V_IFR)", 5.0, 78, "V",
     "AD8352 datasheet Rev. C, Table 1, POWER INTERFACE: quiescent current "
     "37 typ / 39 max mA per device at ENB 3 V. 2 x 39 = 78 mA. Drawn on "
     "rev03/ADC_RADAR"),
    ("+5V0", "AD8352 SDR drivers, x2", 5.0, 78, "E",
     "Assumes the SDR ADC takes one AD8352 per channel like the radar chain; "
     "confirm when ADC_SDR is drawn"),

    # ---- clock ---------------------------------------------------------
    # Clock, as drawn on rev03/CLOCK.kicad_sch (docs/CLOCK_SPEC.md). The
    # ADCLK944 of the first plan became an ADCLK948 (2 selectable inputs),
    # and the TCXO a Si549 programmable XO: a TCXO cannot give 400-500 MHz.
    # Both sit on +3V3_CLK, a ferrite-filtered branch of +3V3_D.
    ("+3V3_D", "ADCLK948 LVPECL fan-out (via +3V3_CLK)", 3.3, 330, "V",
     "ADCLK948 datasheet Rev. B, Table 4: IVCC 288 typ / 330 max mA at 3.3 V "
     "+/-10 %, outputs loaded - so it covers the current into the 200 ohm "
     "pull-downs. Only 4 of 8 outputs are used; the open ones draw nothing, "
     "so this is an upper bound"),
    ("+3V3_D", "Si549 programmable XO, LVPECL (via +3V3_CLK)", 3.3, 153, "V",
     "Si549 datasheet Revision H: IDD LVPECL 107 typ / 153 max mA"),
    ("+3V3_D", "Si549 LVPECL pull-downs, 2 x 130 ohm", 3.3, 30, "E",
     "About 15 mA per leg into Rp at a ~2 V output level. Whether the "
     "datasheet's IDD already includes it is not stated, so counted apart"),

    # ---- RF routing and glue -------------------------------------------
    ("+3V3_D", "M3SWA2-34DR+ SPDT, x4, VDD", 3.3, 12, "V",
     "Mini-Circuits M3SWA2-34DR+ datasheet, DC ELECTRICAL SPECIFICATIONS: "
     "IDD 1.6 mA typ, 2.9 mA max per part. 4 x 2.9 = 11.6 mA"),
    ("-3V3", "M3SWA2-34DR+ SPDT, x4, VEE", -3.3, 8, "V",
     "Same table: VEE -3.3 V required, IEE 1.8 mA max per part. 4 x 1.8 = 7.2 mA. "
     "This rail was wrongly deleted when B-03 was first closed; see "
     "docs/BLOCKERS_AND_RISKS.md B-03"),
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
    # Charge-pump inverter. Reinstated after B-03 was reopened: the RF switches
    # need VEE = -3.3 V. A few milliamps, so a small pump is plenty.
    "-3V3":   ("+3V3_D", "pump", 0.80),
}

VOLTS = {"+12V": 12.0, "+5V0": 5.0, "+3V6": 3.6, "+3V3_D": 3.3, "+3V3_A": 3.3,
         "+2V5": 2.5, "+1V8_A": 1.8, "+1V8_D": 1.8, "+1V2": 1.2, "+1V0": 1.0,
         "-3V3": -3.3}

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
    order = ["-3V3", "+1V2", "+1V8_D", "+1V8_A", "+2V5", "+1V0", "+3V3_A", "+3V6",
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
        elif kind == "pump":
            p_out = abs(v_out) * i_out / 1000.0
            p_in = p_out / eff
            i_in = p_in / v_in * 1000.0
            diss[rail] = p_in - p_out
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
