"""
CLOCK sheet - the connection specification.

Written BEFORE the drawing, from the datasheets, and kept separate from it:
_work/sheets/clock.py draws the sheet from coordinates, and
_work/check_sheet.py checks that what was drawn connects exactly as listed
here. If this table is right and the check passes, the drawing is right.

This is the file to review against the datasheets. docs/CLOCK_SPEC.md
explains each choice; every value below names its source.

Frequency plan (docs/CLOCK_SPEC.md §1): one master clock, 400 or 500 MHz,
fanned out by the ADCLK948 to the two ADCs and the FPGA. The AD9253 divides
it internally (1..8); the DACs get CMOS clocks from the FPGA, which also
sends them their data.
"""

# ref -> (lib_id, value, footprint, source of the value)
PARTS = {
    "U401": ("kv260-ias2rf:ADCLK948BCPZ", "ADCLK948BCPZ",
             "kv260-ias2rf:LFCSP-32-1EP_5x5mm_P0.5mm_EP2.7x2.7mm",
             "2 selectable inputs, 8 LVPECL outputs. Footprint: CP-32-21 has a 2.70 mm "
             "exposed pad; KiCad's stock LFCSP-32 5x5 all have >= 3.1 mm. Custom footprint "
             "needed at layout"),
    "Y401": ("kv260-ias2rf:Si549_PinoutC", "Si549 LVPECL 3V3 pinout C",
             "Oscillator:Oscillator_SMD_SI570_SI571_Standard",
             "5x7 mm package, pin-compatible with Si570 (datasheet: 'if replacing Si570A-K, "
             "use Code C')"),
    "J401": ("Connector:Conn_Coaxial", "CLK_REF_IN",
             "Connector_Coaxial:SMA_Samtec_SMA-J-P-H-ST-EM1_EdgeMount",
             "Reference from AERIS-10. Edge mount: the board grows outward (INTERFACE_SPEC §5.3)"),
    "J402": ("Connector:Conn_Coaxial", "CLK_OUT",
             "Connector_Coaxial:SMA_Samtec_SMA-J-P-H-ST-EM1_EdgeMount",
             "Master clock out, for measurement or for synchronising another board"),
    "FB401": ("Device:FerriteBead", "220R@100MHz", "Inductor_SMD:L_0603_1608Metric",
              "Judgement: isolates the clock supply from +3V3_D. Rail draws up to 483 mA "
              "(330 + 153): a 2 A, 0.1 ohm bead (14 Nov, _work/power/fb401_filter.py) keeps its inductance "
              "under that bias and drops 48 mV, where a 1 A, 0.2 ohm 600R bead dropped 97 mV and could leave "
              "the Si549 under 3.135 V"),
    "C401": ("Device:C", "10u", "Capacitor_SMD:C_0805_2012Metric",
             "ADCLK948 p.10: bulk bypass 'within several inches'. Ceramic instead of the "
             "1 uF electrolytic it mentions"),
    "C402": ("Device:C", "1u", "Capacitor_SMD:C_0402_1005Metric", "ADCLK948 p.10: 1 uF bypass"),
    "R401": ("Device:R", "10k", "Resistor_SMD:R_0402_1005Metric",
             "IN_SEL pull-up. Table 3: logic 1 >= VCC-0.4 V; with the FPGA driving open-drain "
             "the high level is exactly VCC. Logic 0 sink: 0.6 mA (pin) + 0.33 mA (resistor)"),
    "R402": ("Device:R", "130", "Resistor_SMD:R_0402_1005Metric",
             "Si549 Figure 4.1, AC-coupled LVPECL at VDD 3.3 V: Rp = 130 ohm"),
    "R403": ("Device:R", "130", "Resistor_SMD:R_0402_1005Metric", "Same as R402"),
    "C409": ("Device:C", "100n", "Capacitor_SMD:C_0402_1005Metric",
             "ADCLK948 Figure 21: AC coupling into CLK1 (value not given; 100 nF is the usual "
             "choice and passes 0.2 MHz..1.5 GHz)"),
    "C410": ("Device:C", "100n", "Capacitor_SMD:C_0402_1005Metric", "Same as C409"),
    "C411": ("Device:C", "100n", "Capacitor_SMD:C_0402_1005Metric",
             "ADCLK948 Figure 21: VT1 tied to VREF1, bypassed to ground"),
    "C412": ("Device:C", "100n", "Capacitor_SMD:C_0402_1005Metric",
             "ADCLK948 Figure 22: AC coupling of the single-ended reference into CLK0"),
    "C413": ("Device:C", "100n", "Capacitor_SMD:C_0402_1005Metric",
             "ADCLK948 Figure 22: VT0, VREF0 and CLK0-bar tied, bypassed to ground"),
    "R412": ("Device:R", "49.9", "Resistor_SMD:R_0402_1005Metric",
             "Judgement: dummy 50 ohm load on Q3-bar, so both legs of Q3 see the same load "
             "as the SMA side"),
    "R413": ("Device:R", "4.7k", "Resistor_SMD:R_0402_1005Metric",
             "Si549 I2C: 'SDA and SCL must be connected to VDD via an external pull-up'"),
    "R414": ("Device:R", "4.7k", "Resistor_SMD:R_0402_1005Metric", "Same as R413"),
    "C422": ("Device:C", "100n", "Capacitor_SMD:C_0402_1005Metric",
             "Judgement: the Si549 datasheet gives no decoupling recommendation; one 100 nF "
             "at the VDD pin"),
}
# Six 1 nF, one per ADCLK948 VCC pin - p.10: 'multiple high quality 0.001 uF
# bypass capacitors as close as possible to each of the VCC supply pins'.
for i in range(6):
    PARTS[f"C{403 + i}"] = ("Device:C", "1n", "Capacitor_SMD:C_0402_1005Metric",
                            "ADCLK948 p.10: 0.001 uF at each VCC pin")
# Each used LVPECL output: 200 ohm pull-down at the driver and 100 pF in
# series - ADCLK948 Figure 17, AC-coupled LVPECL. The 100 ohm differential
# termination sits at the RECEIVER, on the consuming sheet.
for k in range(4):
    for leg in range(2):
        PARTS[f"R{404 + 2 * k + leg}"] = ("Device:R", "200", "Resistor_SMD:R_0402_1005Metric",
                                           "ADCLK948 Figure 17: 200 ohm pull-down at the driver")
        PARTS[f"C{414 + 2 * k + leg}"] = ("Device:C", "100p", "Capacitor_SMD:C_0402_1005Metric",
                                           "ADCLK948 Figure 17: 0.1 nF series coupling")

# Interface to the rest of the design: hierarchical labels.
HIER = {
    "CLK_ADCR_P": "output", "CLK_ADCR_N": "output",   # -> AD9484, ADC_RADAR
    "CLK_ADCS_P": "output", "CLK_ADCS_N": "output",   # -> AD9253, ADC_SDR
    "CLK_FPGA_P": "output", "CLK_FPGA_N": "output",   # -> XC7A50T, CONTROL
    "CLK_SEL": "input",                               # FPGA, open-drain
    "XO_SCL": "input", "XO_SDA": "bidirectional",     # FPGA I2C master, 3.3 V
}

VCC = [f"U401.{p}" for p in (10, 15, 16, 25, 26, 31)]

# net -> pins. Nets named in HIER must carry that label; power nets carry a
# power symbol; the rest are internal and may be unnamed.
NETS = {
    "+3V3_D":   ["FB401.1"],
    "+3V3_CLK": ["FB401.2", "C401.1", "C402.1"] + VCC
                + [f"C{403 + i}.1" for i in range(6)]
                + ["R401.1", "Y401.2", "Y401.6", "C422.1", "R413.1", "R414.1"],
    "GND":      ["C401.2", "C402.2"] + [f"C{403 + i}.2" for i in range(6)]
                + ["U401.33", "R402.2", "R403.2", "C411.2", "C413.2", "R412.2", "C422.2",
                   "J401.2", "J402.2", "Y401.3"]
                + [f"R{404 + i}.2" for i in range(8)],

    # Local reference: Si549 -> CLK1 (the default: IN_SEL floats high).
    "XO_P":     ["Y401.4", "R402.1", "C409.1"],
    "XO_N":     ["Y401.5", "R403.1", "C410.1"],
    "CLK1_P":   ["C409.2", "U401.5"],
    "CLK1_N":   ["C410.2", "U401.6"],
    "VT1":      ["U401.7", "U401.8", "C411.1"],

    # External reference from AERIS-10 -> CLK0, single-ended (Figure 22).
    "REF_IN":   ["J401.1", "C412.1"],
    "CLK0_P":   ["C412.2", "U401.1"],
    "VT0":      ["U401.2", "U401.3", "U401.4", "C413.1"],

    "CLK_SEL":  ["U401.32", "R401.2"],

    # Outputs. Q0 -> AD9484, Q1 -> AD9253, Q2 -> FPGA, Q3 -> SMA.
    "Q0_P": ["U401.30", "R404.1", "C414.1"], "Q0_N": ["U401.29", "R405.1", "C415.1"],
    "Q1_P": ["U401.28", "R406.1", "C416.1"], "Q1_N": ["U401.27", "R407.1", "C417.1"],
    "Q2_P": ["U401.24", "R408.1", "C418.1"], "Q2_N": ["U401.23", "R409.1", "C419.1"],
    "Q3_P": ["U401.22", "R410.1", "C420.1"], "Q3_N": ["U401.21", "R411.1", "C421.1"],
    "CLK_ADCR_P": ["C414.2"], "CLK_ADCR_N": ["C415.2"],
    "CLK_ADCS_P": ["C416.2"], "CLK_ADCS_N": ["C417.2"],
    "CLK_FPGA_P": ["C418.2"], "CLK_FPGA_N": ["C419.2"],
    "CLK_OUT":    ["C420.2", "J402.1"],
    "Q3_N_LOAD":  ["C421.2", "R412.1"],

    "XO_SDA": ["Y401.7", "R413.2"],
    "XO_SCL": ["Y401.8", "R414.2"],
}

# Deliberately unconnected. Q4..Q7: LVPECL outputs are open emitters (Figure
# 13); with no pull-down they draw no current, which is also why IVCC comes
# in under the Table 4 figure (measured with all outputs loaded).
NO_CONNECT = ["U401.9", "Y401.1"] + [f"U401.{p}" for p in (20, 19, 18, 17, 14, 13, 12, 11)]
