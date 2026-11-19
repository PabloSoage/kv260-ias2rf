"""
PSU board: the connection specification (every part, every pin's net). Drawn by psu_sheet.py, placed and routed
by psu_pcb.py. The design and its numbers: psu_design.py and docs/PSU_SPEC.md.

Signal path
  J1 (XT30) VBAT -> D1 SMCJ100A + D2 SMCJ24A, in series and opposed, to ground (+111 V / -27 V clamp)
     -> U1 LTC4364-2: Q1 IPB048N15N5 (HGATE, 150 V pass FET) and Q2 BSC040N10NS5 (DGATE, ideal diode), common
        source VS; output B0 clamped at 48 V by R7/R8; VCC OR-ed from VBAT (D3) and +12V (D4) through R4, clamped
        by D5 SMAJ51A; UV 3.0 V (R5/R6); TMR 4.7 uF; HGATE 10 nF; 15 V zeners HGATE-VS and DGATE-VS (D6, D7)
     -> B0 (47 uF + 2 x 4.7 uF + 2 x 100 nF) -> L3 0.47 uH -> B (2 x 4.7 uF) -> L2 1.0 uH -> B2 -> R2 3 mOhm
        (LM5177 input current limit, 16.3 A) -> VIN (4 x 4.7 uF + 2 x 100 uF, the filter's damping)
     -> U2 LM5177: Q3/Q4 BSC0805LS (input half bridge, SW1), R1 2 mOhm (peak current sense, SW1 to LX), L1 2.2 uH,
        Q5/Q6 BSC026N04LS (output half bridge, SW2) -> +12V (6 x 22 uF + 2 x 100 uF polymer)
     -> U3 TPS26631 (2.0 A) -> OUT_A -> J2 (the adapter's J1001); U4 TPS26631 (3.0 A) -> OUT_K -> J3 (the KV260's J12)
"""

R0603, R1206, R2512 = "Resistor_SMD:R_0603_1608Metric", "Resistor_SMD:R_1206_3216Metric", "Resistor_SMD:R_2512_6332Metric"
C0603, C0805, C1206, C1210 = ("Capacitor_SMD:C_0603_1608Metric", "Capacitor_SMD:C_0805_2012Metric",
                              "Capacitor_SMD:C_1206_3216Metric", "Capacitor_SMD:C_1210_3225Metric")
GND = "GND"
FPL = "psu:"

PARTS = {
    "J1": ("Connector_Generic:Conn_01x02", "XT30PW-M", "Connector_AMASS:AMASS_XT30PW-M_1x02_P2.50mm_Horizontal",
           "Battery or bench supply in: 1 = +, 2 = ground. 16 AWG, 20 A fuse at the battery"),
    "J2": ("Connector_Generic:Conn_01x02", "B2PS-VH", "Connector_JST:JST_VH_B2PS-VH_1x02_P3.96mm_Horizontal",
           "12 V to the adapter's J1001: 1 = OUT_A, 2 = ground"),
    "J3": ("Connector_Generic:Conn_01x02", "B2PS-VH", "Connector_JST:JST_VH_B2PS-VH_1x02_P3.96mm_Horizontal",
           "12 V to the KV260's J12: 1 = OUT_K, 2 = ground"),
    "D1": ("Device:D_Zener", "SMCJ100A", "Diode_SMD:D_SMC", "Input clamp, positive: breaks down at 111 V (with D2 forward)"),
    "D2": ("Device:D_Zener", "SMCJ24A", "Diode_SMD:D_SMC", "Input clamp, negative: breaks down at 26.7 V (with D1 forward)"),
    "U1": (FPL + "LTC4364MS", "LTC4364HMS-2", "Package_SO:MSOP-16_3x4.039mm_P0.5mm",
           "Surge stopper with ideal diode: output clamped at 48 V, reverse input to -40 V, auto-retry"),
    "Q1": (FPL + "NMOS_D2PAK", "IPB048N15N5", "Package_TO_SOT_SMD:TO-263-2",
           "Surge stopper pass FET (HGATE): 150 V, 4.8 mOhm; regulates during a load dump"),
    "Q2": (FPL + "NMOS_SON8", "BSC040N10NS5", "Package_SON:Infineon_PG-TDSON-8_6.15x5.15mm",
           "Ideal diode FET (DGATE): reverse input, no back-feed; 100 V, 4 mOhm"),
    "D3": ("Device:D", "LBAS21HT1G", "Diode_SMD:D_SOD-323", "U1 VCC from VBAT (BAS21, 250 V)"),
    "D4": ("Device:D", "LBAS21HT1G", "Diode_SMD:D_SOD-323", "U1 VCC from +12V: keeps U1 alive while cranking"),
    "D5": ("Device:D_Zener", "SMAJ51A", "Diode_SMD:D_SMA", "U1 VCC clamp (57 to 63 V) during a load dump"),
    "D6": ("Device:D_Zener", "BZT52C15", "Diode_SMD:D_SOD-123", "HGATE to VS, 15 V (data sheet: supplies of 24 V or more)"),
    "D7": ("Device:D_Zener", "BZT52C15", "Diode_SMD:D_SOD-123", "DGATE to VS, 15 V"),
    "L3": ("Device:L", "MDA1365-R47M", FPL + "L_KOHER_MDA1365", "Input filter, first stage: 0.47 uH, 42 A, 0.88 mOhm"),
    "L2": ("Device:L", "MDA1365-1R0M", FPL + "L_KOHER_MDA1365", "Input filter, second stage: 1.0 uH, 33 A, 1.5 mOhm"),
    "U2": (FPL + "LM5177", "LM5177DCPR", FPL + "TI_DCP0038A_HTSSOP-38",
           "Four-switch buck-boost 12.0 V, 400 kHz, DRSS on, hiccup off, input current limit 16.3 A"),
    "Q3": (FPL + "NMOS_SON8", "BSC0805LS", "Package_SON:Infineon_PG-TDSON-8_6.15x5.15mm",
           "Input half bridge, high side (HO1): 100 V, 8.5 mOhm at 4.5 V"),
    "Q4": (FPL + "NMOS_SON8", "BSC0805LS", "Package_SON:Infineon_PG-TDSON-8_6.15x5.15mm",
           "Input half bridge, low side (LO1)"),
    "Q5": (FPL + "NMOS_SON8", "BSC026N04LS", "Package_SON:Infineon_PG-TDSON-8_6.15x5.15mm",
           "Output half bridge, low side (LO2): 40 V, 3.6 mOhm at 4.5 V"),
    "Q6": (FPL + "NMOS_SON8", "BSC026N04LS", "Package_SON:Infineon_PG-TDSON-8_6.15x5.15mm",
           "Output half bridge, high side (HO2)"),
    "L1": ("Device:L", "MDA1870-2R2M", FPL + "L_KOHER_MDA1870", "Buck-boost inductor: 2.2 uH, Isat 35 A, 1.8 mOhm"),
    "U3": (FPL + "TPS26631RGE", "TPS26631RGER", "Package_DFN_QFN:Texas_RGE0024H_VQFN-24-1EP_4x4mm_P0.5mm_EP2.7x2.7mm_ThermalVias",
           "Adapter output eFuse: 2.0 A, OVP 14.4 V, UVLO 8.0 V, auto-retry"),
    "U4": (FPL + "TPS26631RGE", "TPS26631RGER", "Package_DFN_QFN:Texas_RGE0024H_VQFN-24-1EP_4x4mm_P0.5mm_EP2.7x2.7mm_ThermalVias",
           "KV260 output eFuse: 3.0 A, OVP 14.4 V, UVLO 8.0 V, auto-retry"),
    "D8": ("Device:D_Schottky", "SS34", "Diode_SMD:D_SMA", "OUT_A to ground: the cable's negative kick"),
    "D9": ("Device:D_Schottky", "SS34", "Diode_SMD:D_SMA", "OUT_K to ground"),
    "D10": ("Device:LED", "green", "LED_SMD:LED_0603_1608Metric", "+12V present"),
    "D11": ("Device:LED", "red", "LED_SMD:LED_0603_1608Metric", "U1 fault (FLT low: surge clamp timed out)"),
}

PINS = {
    "J1": {"1": "VBAT", "2": GND},
    "J2": {"1": "OUT_A", "2": GND},
    "J3": {"1": "OUT_K", "2": GND},
    "D1": {"1": "VBAT", "2": "TVS_MID"},          # Zener symbol: 1 = K, 2 = A
    "D2": {"1": GND, "2": "TVS_MID"},
    "U1": {"8": "VCC_LTC", "10": "UV", "11": GND, "9": "NC", "6": "HG", "5": "VS", "4": "DG", "2": "B0", "1": "B0",
           "16": "FB_LTC", "15": "TMR", "13": "FLT_LTC", "14": "NC", "12": GND, "3": "NC", "7": "NC"},
    "Q1": {"1": "HG", "2": "VBAT", "3": "VS"},
    "Q2": {"4": "DG", "5": "B0", "1": "VS", "2": "VS", "3": "VS"},
    "D3": {"1": "VCC_OR", "2": "VBAT"},            # Device:D: 1 = K, 2 = A
    "D4": {"1": "VCC_OR", "2": "+12V"},
    "D5": {"1": "VCC_LTC", "2": GND},
    "D6": {"1": "HG", "2": "VS"},
    "D7": {"1": "DG", "2": "VS"},
    "L3": {"1": "B0", "2": "B"},
    "L2": {"1": "B", "2": "B2"},
    "U2": {"3": "VIN", "4": "EN_UVLO", "1": "BIAS", "23": "B2", "22": "VIN", "37": "CSA", "38": "CSB", "36": "SW1",
           "35": "HB1", "34": "HO1", "32": "LO1", "8": "NC", "9": "NC", "20": "+12V", "19": "FB", "18": "COMP",
           "16": "SS", "15": "RT", "14": "SLOPE", "13": "CFG", "12": "VCC", "11": "VCC", "10": GND, "7": "NFLT",
           "6": "IMON", "25": "SW2", "26": "HB2", "27": "HO2", "29": "LO2", "31": "VCC", "17": GND, "30": GND,
           "39": GND, "2": "NC", "5": "NC", "21": "NC", "24": "NC", "28": "NC", "33": "NC"},
    "Q3": {"4": "G_HO1", "5": "VIN", "1": "SW1", "2": "SW1", "3": "SW1"},
    "Q4": {"4": "G_LO1", "5": "SW1", "1": GND, "2": GND, "3": GND},
    "Q5": {"4": "G_LO2", "5": "SW2", "1": GND, "2": GND, "3": GND},
    "Q6": {"4": "G_HO2", "5": "+12V", "1": "SW2", "2": "SW2", "3": "SW2"},
    "L1": {"1": "LX", "2": "SW2"},
    "U3": {"1": "+12V", "2": "+12V", "5": "+12V", "3": "NC", "4": "NC", "6": "A_UVLO", "7": "A_OVP", "12": "NC",
           "11": GND, "17": "OUT_A", "18": "OUT_A", "16": "NC", "15": GND, "14": "NC", "13": "NC", "10": "A_ILIM",
           "9": "A_DVDT", "8": GND, "25": GND, "19": "NC", "20": "NC", "21": "NC", "22": "NC", "23": "NC", "24": "NC"},
    "U4": {"1": "+12V", "2": "+12V", "5": "+12V", "3": "NC", "4": "NC", "6": "K_UVLO", "7": "K_OVP", "12": "NC",
           "11": GND, "17": "OUT_K", "18": "OUT_K", "16": "NC", "15": GND, "14": "NC", "13": "NC", "10": "K_ILIM",
           "9": "K_DVDT", "8": GND, "25": GND, "19": "NC", "20": "NC", "21": "NC", "22": "NC", "23": "NC", "24": "NC"},
    "D8": {"1": "OUT_A", "2": GND},
    "D9": {"1": "OUT_K", "2": GND},
    "D10": {"1": "LED_PWR", "2": GND},              # Device:LED: 1 = K, 2 = A -> anode LED_PWR? fixed below
    "D11": {"1": "FLT_LTC", "2": "LED_FLT"},
}
PINS["D10"] = {"1": GND, "2": "LED_PWR"}           # cathode to ground, anode from R through +12V
HIER = {}
FILTERS = {}


def R(value, why, fp=R0603):
    return ("Device:R", value, fp, why)


def C(value, why, fp=C0603):
    return ("Device:C", value, fp, why)


def CP(value, why, fp):
    return ("Device:C_Polarized", value, fp, why)


def two(ref, part, n1, n2):
    assert ref not in PARTS, ref
    PARTS[ref] = part
    PINS[ref] = {"1": n1, "2": n2}


# ---- U1 LTC4364
two("R4", R("1k 0.66W", "U1 VCC: limits D5's current in a load dump; anti-surge (ERJ-P08F1001V): 0.88 W peak, "
                   "23.5 mJ over 92 ms in Load Dump A (psu_audit.py)", R1206), "VCC_OR", "VCC_LTC")
two("C1", C("100n 100V", "U1 VCC", C0805), "VCC_LTC", GND)
two("R5", R("140k", "U1 UV divider, top: 3.0 V", R0603), "VBAT", "UV")
two("R6", R("100k", "U1 UV divider, bottom", R0603), "UV", GND)
two("R7", R("374k", "U1 FB divider, top: output clamp 48.0 V (1.25 V x (1 + 374k / 10k))", R0603), "B0", "FB_LTC")
two("R8", R("10k", "U1 FB divider, bottom", R0603), "FB_LTC", GND)
two("C2", C("4.7u 25V", "U1 TMR: the fault timer (a whole Load Dump A passes)", C0805), "TMR", GND)
two("C3", C("10n 100V", "U1 HGATE to ground (6.8 nF or more)", C0603), "HG", GND)
two("R9", R("2.2k", "D11 (U1 fault LED)", R0603), "+12V", "LED_FLT")
two("C4", C("100n 250V", "Input, fast pulses (ISO 7637-2 3a/3b)", C1206), "VBAT", GND)
two("C5", C("100n 250V", "Input, fast pulses", C1206), "VBAT", GND)
# ---- input filter
two("C6", CP("47u 63V", "B0: U1 OUT bypass (22 uF or more, low ESR electrolytic); EEE-FK1J470P",
             "Capacitor_SMD:CP_Elec_8x10"), "B0", GND)
for i, ref in enumerate(("C7", "C8")):
    two(ref, C("4.7u 100V", "B0", C1210), "B0", GND)
for ref in ("C9", "C10"):
    two(ref, C("100n 100V", "B0, high frequency", C0603), "B0", GND)
for ref in ("C11", "C12"):
    two(ref, C("4.7u 100V", "B, between L3 and L2", C1210), "B", GND)
two("R2", R("3m", "U2 input current sense: 50 mV / 3 mOhm = 16.7 A (16.3 A min)", R2512), "B2", "VIN")
for ref in ("C13", "C14", "C15", "C16"):
    two(ref, C("4.7u 100V", "VIN, the power stage's input", C1210), "VIN", GND)
for ref in ("C17", "C18"):
    two(ref, CP("100u 63V", "VIN: the input filter's damping (Middlebrook); EEE-FK1J101P",
                "Capacitor_SMD:CP_Elec_10x10"), "VIN", GND)
two("C19", C("100n 100V", "VIN, high frequency", C0603), "VIN", GND)
# ---- U2 LM5177
two("R10", R("576k", "U2 EN/UVLO top: on at 6.0 V, off at 3.0 V", R0603), "VIN", "EN_UVLO")
two("R11", R("383k", "U2 EN/UVLO bottom", R0603), "EN_UVLO", GND)
two("R12", R("10", "U2 BIAS from +12V (operation down to 2.8 V VIN)", R0603), "+12V", "BIAS")
two("C20", C("1u 25V", "U2 BIAS", C0603), "BIAS", GND)
two("C21", C("10u 10V", "U2 VCC", C0805), "VCC", GND)
two("C22", C("10u 10V", "U2 VCC", C0805), "VCC", GND)
two("C23", C("100n 25V", "U2 HB1 bootstrap", C0603), "HB1", "SW1")
two("C24", C("100n 25V", "U2 HB2 bootstrap", C0603), "HB2", "SW2")
two("R13", R("0", "Q3 gate (raise for slower SW1 edges)", R0603), "HO1", "G_HO1")
two("R14", R("0", "Q4 gate", R0603), "LO1", "G_LO1")
two("R15", R("0", "Q5 gate", R0603), "LO2", "G_LO2")
two("R16", R("0", "Q6 gate", R0603), "HO2", "G_HO2")
two("R1", R("2m", "Peak current sense, SW1 to L1: limit 19.3 / 25 / 29.3 A", R2512), "SW1", "LX")
two("R17", R("10", "CSA filter", R0603), "SW1", "CSA")
two("R18", R("10", "CSB filter", R0603), "LX", "CSB")
two("C25", C("150p 50V", "CSA-CSB filter: 197 ns / (2 pi x 20 ohm x 10) = 157 pF (eq. 15)", C0603), "CSA", "CSB")
two("R19", R("71.5k", "FB top: 12.02 V", R0603), "+12V", "FB")
two("R20", R("6.49k", "FB bottom", R0603), "FB", GND)
two("R21", R("15.8k", "COMP (eq. 3)", R0603), "COMP", "COMP_RC")
two("C26", C("15n 50V", "COMP zero (eq. 4)", C0603), "COMP_RC", GND)
two("C27", C("120p 50V", "COMP high-frequency pole (eq. 5)", C0603), "COMP", GND)
two("C28", C("47n 25V", "Soft start 4.7 ms (eq. 14)", C0603), "SS", GND)
two("R22", R("75k", "RT: 400 kHz (eq. 17)", R0603), "RT", GND)
two("R23", R("54.9k", "SLOPE (eq. 11)", R0603), "SLOPE", GND)
two("R24", R("3.83k", "CFG: DRSS on, hiccup off, PSM 10 %, current limit on (table 7-1 row 6)", R0603), "CFG", GND)
two("R25", R("20k", "IMONOUT: the input current loop's compensation [E], tune on the bench", R0603), "IMON", "IMON_RC")
two("C29", C("10n 25V", "IMONOUT compensation", C0603), "IMON_RC", GND)
two("R26", R("100k", "nFLT pull-up", R0603), "VCC", "NFLT")
for ref in ("C32", "C33", "C34", "C35", "C36", "C37"):
    two(ref, C("22u 25V", "+12V output", C1210), "+12V", GND)
for ref in ("C38", "C39"):
    two(ref, CP("100u 25V", "+12V output, polymer (50 mOhm, 1.87 A)", "Capacitor_SMD:CP_Elec_6.3x5.8"), "+12V", GND)
two("R29", R("4.7k", "D10 (+12V LED)", R0603), "+12V", "LED_PWR")
# ---- U3 / U4 TPS26631
for p, ilim in (("A", "9.09k"), ("K", "6.04k")):
    base = {"A": 40, "K": 50}[p]
    two(f"R{base}", R("316k", f"U{3 if p == 'A' else 4} UVLO/OVP divider top: UVLO 8.0 V, OVP 14.4 V", R0603),
        "+12V", f"{p}_UVLO")
    two(f"R{base + 1}", R("24.9k", "UVLO/OVP divider middle", R0603), f"{p}_UVLO", f"{p}_OVP")
    two(f"R{base + 2}", R("30.9k", "UVLO/OVP divider bottom", R0603), f"{p}_OVP", GND)
    two(f"R{base + 3}", R(ilim, "current limit (18 kOhm.A / R)", R0603), f"{p}_ILIM", GND)
    two(f"C{base}", C("22n 50V", "dVdT: 5.5 ms output ramp", C0603), f"{p}_DVDT", GND)
    two(f"C{base + 1}", C("10u 25V", f"OUT_{p} at the connector", C1206), f"OUT_{p}", GND)
DNP = set()
