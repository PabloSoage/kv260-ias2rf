"""
CONTROL sheet - the connection specification. See docs/CONTROL_SPEC.md.

U1101, the XC7A50T-2FTG256I front-end FPGA (AERIS-10's own part), with
everything it needs to boot and everything it talks to that is not on
another sheet: the configuration flash, JTAG, the Pmod from the KV260, and
the ribbon to AERIS-10's ADAR1000 beamformers.

Bank voltages. The FTG256 has four user banks, and bank 34 has only 20 I/O
and no clock-capable pin (see the symbol, or UG475). So:

  bank 14  3.3 V   AD9484 at AERIS's own pins; AD9253; the two link pairs the
                   FPGA receives; CLK_FPGA; the configuration flash (bank 14
                   holds the flash pins). LVDS_25 INPUTS may sit in a 3.3 V
                   bank with DIFF_TERM off (UG471 Table 1-44 note 1), so each
                   pair gets an external 100 ohm - as AERIS does.
  bank 15  3.3 V   AD9708 at AERIS's own pins; AD9767; Pmod; RF switches;
                   clock select and the XO's I2C. 22 ohm series on DAC lines.
  bank 34  2.5 V   the three link pairs the FPGA DRIVES: LVDS_25 outputs need
                   VCCO = 2.5 V (UG471). Nothing else fits there.
  bank 35  1.8 V   8 x ADAR1000 control + SPI (AERIS drives them at 1.8 V),
                   the converters' SPI (1.8 V parts), HK I2C and FPGA_IRQ
                   (the carrier's 1.8 V).

Configuration: master SPI x4, UG470 Figure 2-14, values from it.
Decoupling: UG483 Table 2-2, row FTG256 / XC7A50T.
XADC: on-chip reference, UG480 Figure 1-2 (right).
"""

import re

from kit import R, C, C0805

FPGA_LIB = "FPGA_Xilinx_Artix7:XC7A50T-FTG256"
C0603, C1210 = "Capacitor_SMD:C_0603_1608Metric", "Capacitor_SMD:C_1210_3225Metric"
R0603 = "Resistor_SMD:R_0603_1608Metric"

PARTS = {
    "U1101": (FPGA_LIB, "XC7A50T-2FTG256I", "Package_BGA:Xilinx_FTG256",
              "Front-end FPGA, AERIS-10's part (ARCHITECTURE §2.2)"),
    "U1102": ("kv260-ias2rf:MT25QL128ABA1ESE", "MT25QL128ABA1ESE",
              "Package_SO:SOIC-8_5.3x5.3mm_P1.27mm",
              "Configuration flash, 128 Mb: in Vivado's list (UG908) as mt25ql128"),
    "U1103": ("74xGxx:74LVC1G07", "74LVC1G07", "Package_TO_SOT_SMD:SOT-23-5",
              "FPGA_PROG_B (1.8 V, from the Kria) to PROGRAM_B (3.3 V): open-drain buffer"),
    "Q1101": ("Transistor_FET:Q_NMOS_GSD", "2N7002", "Package_TO_SOT_SMD:SOT-23",
              "DONE LED driver"),
    "D1101": ("Device:LED", "green", "LED_SMD:LED_0603_1608Metric", "DONE: configured"),
    "SW1101": ("Switch:SW_Push", "PROG", "Button_Switch_SMD:SW_SPST_TL3342",
               "UG470 Table 2-4: 'recommend push-button to GND' on PROGRAM_B"),
    "J1101": ("Connector_Generic:Conn_02x07_Odd_Even", "JTAG 2x7 2mm",
              "Connector_PinHeader_2.00mm:PinHeader_2x07_P2.00mm_Vertical",
              "Xilinx cable header, DS593 Figure 14 (shrouded Molex 87832-1420 to fit)"),
    "J1102": ("Connector_Generic:Conn_02x06_Odd_Even", "Pmod",
              "Connector_PinHeader_2.54mm:PinHeader_2x06_P2.54mm_Vertical",
              "Cable to the KV260's Pmod J2 (INTERFACE_SPEC §4.2)"),
    "J1103": ("Connector_Generic:Conn_02x20_Odd_Even", "AERIS ADAR",
              "Connector_IDC:IDC-Header_2x20_P2.54mm_Vertical",
              "Ribbon to AERIS-10: 8 x ADAR1000 control (ARCHITECTURE §7.2)"),
}

# --------------------------------------------------------------- pin table
# FPGA ball -> net. Every ball of the four user banks appears here or in
# BANK_NC; check_pins() below proves each assignment against the symbol's own
# pin names (bank, pair polarity, clock capability).
#
# Bank 14. AD9484 (ADCR_*) and CLK_FPGA on AERIS-10's balls (its U42).
BANK14 = {
    "J13": "FLASH_DQ0", "J14": "FLASH_DQ1", "K15": "FLASH_DQ2", "K16": "FLASH_DQ3",
    "L12": "FLASH_CS",                                   # FCS_B
    "L15": "PUDC_B",                                     # high: pull-ups off during config
    "M16": "LINK_TX_D0_P", "N16": "LINK_TX_D0_N",
    "P15": "ADCR_D0_P", "P16": "ADCR_D0_N", "R15": "ADCR_D1_P", "R16": "ADCR_D1_N",
    "T14": "ADCR_D2_P", "T15": "ADCR_D2_N",
    "N13": "LINK_TX_CLK_P", "P13": "LINK_TX_CLK_N",      # L11 SRCC
    "N14": "ADCR_DCO_P", "P14": "ADCR_DCO_N",            # L12 MRCC, as AERIS
    "N11": "FPGA_CLK_P", "N12": "FPGA_CLK_N",            # L13 MRCC, AERIS's FPGA_ADC_CLOCK
    "P10": "ADCS_DCO_P", "P11": "ADCS_DCO_N",            # L14 SRCC
    "R13": "ADCR_D3_P", "T13": "ADCR_D3_N", "R10": "ADCR_D4_P", "R11": "ADCR_D4_N",
    "N9": "ADCS_FCO_P", "P9": "ADCS_FCO_N",
    "M6": "ADCR_OR_P", "N6": "ADCR_OR_N",
    "P8": "ADCS_D0_P", "R8": "ADCS_D0_N",
    "T7": "ADCR_D6_P", "T8": "ADCR_D6_N", "T9": "ADCR_D5_P", "T10": "ADCR_D5_N",
    "R5": "ADCS_D1_P", "T5": "ADCS_D1_N",
    "R6": "ADCR_D7_P", "R7": "ADCR_D7_N",
}
# Bank 15. AD9708 data on AERIS's balls; DACR_CLK on AERIS's FPGA_DAC_CLOCK.
# F_ = the FPGA side of a 22 ohm series resistor.
BANK15 = {
    "C8": "SW_CTRL0", "C9": "SW_CTRL1", "B9": "SW_CTRL2", "B12": "SW_CTRL3",
    "A8": "F_DACR_D7", "A9": "F_DACR_D6", "A10": "F_DACR_D5", "B10": "F_DACR_D4",
    "B11": "F_DACR_D3", "A12": "F_DACR_D2", "A13": "F_DACR_D1", "A14": "F_DACR_D0",
    "D8": "CLK_SEL", "D9": "XO_SCL", "C14": "XO_SDA",
    "C13": "F_DACR_CLK",
    "E12": "F_DACS_D0", "E13": "F_DACS_D1", "E11": "F_DACS_D2", "D11": "F_DACS_D3",
    "D14": "F_DACS_D4", "D15": "F_DACS_D5", "F12": "F_DACS_D6", "F13": "F_DACS_D7",
    "E16": "F_DACS_D8", "D16": "F_DACS_D9", "F15": "F_DACS_D10", "E15": "F_DACS_D11",
    "H11": "F_DACS_D12", "G12": "F_DACS_D13",
    "H12": "F_DACS_IQWRT", "H13": "F_DACS_IQSEL", "G14": "F_DACS_IQCLK",
    "F14": "F_DACS_IQRESET",
    "D13": "PMOD_SCLK",                                  # L12 MRCC: the Kria's SPI clock
    "H16": "PMOD_CS", "G16": "PMOD_MOSI", "J15": "PMOD_MISO",
    "J16": "BEAM_STROBE", "H14": "PPS_SYNC", "G15": "PMOD_SPARE1", "G11": "PMOD_SPARE2",
}
# Bank 34, 2.5 V: the three pairs to the Kria.
BANK34 = {
    "L4": "LINK_RX_D0_P", "M4": "LINK_RX_D0_N",
    "M2": "LINK_RX_D1_P", "M1": "LINK_RX_D1_N",
    "N3": "LINK_RX_CLK_P", "N2": "LINK_RX_CLK_N",
}
# Bank 35, 1.8 V: the ADAR1000 ribbon first, in connector order, then the rest.
ADAR = [f"ADAR{n}_{s}" for n in range(1, 9) for s in ("CS", "TX_LOAD", "RX_LOAD", "TR")] + [
    "ADAR_SCLK", "ADAR_SDIO", "ADAR_SDO"]
_B35_BALLS = ["E6", "B7", "A7", "B6", "B5", "A5", "A4", "B4", "A3", "C7", "C6", "D6", "D5",
              "C3", "C2", "B2", "A2", "C1", "B1", "E2", "D1", "E3", "D3", "D4", "C4", "F5",
              "E5", "F4", "F3", "F2", "E1", "G5", "G4", "G2", "G1", "H5", "H4", "J5", "J4",
              "H2", "H1", "J3"]
BANK35 = dict(zip(_B35_BALLS, ADAR + [
    "CONV_SPI_SCLK", "CONV_SPI_SDIO", "CONV_SPI_CSB_R", "CONV_SPI_CSB_S",
    "HK_SCL", "HK_SDA", "FPGA_IRQ"]))
BANK_NC = {
    14: ["K12", "M15", "L14", "M14", "K13", "L13", "M12", "R12", "T12", "P6"],
    15: ["D10", "B14", "B15", "A15", "C16", "B16", "C11", "C12"],
    34: ["L5", "N1", "P1", "P4", "P3", "M5", "N4", "R2", "R1", "R3", "T2", "T4", "T3", "P5"],
    35: ["H3", "K1", "J1", "L3", "L2", "K3", "K2", "K5"],
}
BANKS = {14: BANK14, 15: BANK15, 34: BANK34, 35: BANK35}
# FPGA balls that must be clock capable (MRCC/SRCC), and the reason
CLOCK_BALLS = {"N14": "AD9484 DCO", "N11": "CLK_FPGA", "P10": "AD9253 DCO",
               "N13": "link receive clock", "D13": "Pmod SPI clock"}

# Configuration and JTAG, bank 0 (unit 3): ball -> net
CONFIG = {
    "N7": "JTAG_TDI", "N8": "JTAG_TDO", "M7": "JTAG_TMS", "L7": "JTAG_TCK",
    "E8": "F_CCLK", "M9": "MODE_M0", "M10": "MODE_M1", "M11": "MODE_M2",
    "H10": "DONE", "K10": "INIT_B", "L9": "PROGRAM_B", "E7": "+3V3_D",   # CFGBVS high
    "H8": "XADC_GND", "J7": "XADC_GND", "J8": "XADC_GND", "H7": "XADC_GND",  # VP VN VREFP VREFN
    "K8": "GND", "K7": "GND",                           # DXP, DXN: temperature diode unused
    "L6": "+3V3_D",                                     # VCCO_0
}

# ------------------------------------------------------------ passives
PARTS.update({
    # CLK_FPGA: the ADCLK948 swings 610-960 mV (its Table 1, VO); LVDS_25 in
    # accepts at most 600 mV (DS181 Table 11). A matched pad per leg - 24.9
    # series, 24.9 to the bias - is 50 ohm to the line and halves the swing.
    "R1115": R("24.9", "CLK_FPGA_P attenuator, series: 305-480 mV at the pins, 50 ohm match"),
    "R1116": R("24.9", "Same, N leg"),
    "R1117": R("24.9", "Attenuator shunt to the bias; +1V2 sets VICM (0.3-1.5 V, DS181 Table 11)"),
    "R1118": R("24.9", "Same, N leg"),
    "C1101": C("100n", "Decouples the bias node at the resistors"),
    # configuration, UG470 Table 2-4 and Figure 2-14
    "R1119": R("1k", "PUDC_B high: 'tied directly, or via <= 1 kohm' (UG470 Table 2-4). "
                     "AERIS uses 4.7k, outside that limit"),
    "R1120": R("1k", "M0 high: master SPI = 001 (UG470 Table 2-2); <= 1k per Table 2-4"),
    "R1121": R("1k", "M1 low"),
    "R1122": R("1k", "M2 low"),
    "R1123": R("4.7k", "INIT_B pull-up, <= 4.7k (Table 2-4)"),
    "R1124": R("4.7k", "PROGRAM_B pull-up, <= 4.7k (Table 2-4)"),
    "R1125": R("22", "CCLK series, as AERIS (UG470 Figure 2-14 note 4: termination may be needed)"),
    "R1126": R("2.4k", "FCS_B pull-up, Figure 2-14"),
    "R1127": R("4.7k", "W#/DQ2 pull-up, Figure 2-14"),
    "R1128": R("4.7k", "HOLD#/DQ3 pull-up, Figure 2-14 (and MT25QL datasheet Figure 6 note 1)"),
    "R1129": R("10k", "Holds FPGA_PROG_B high while the Kria is not driving it"),
    "R1130": R("330", "DONE LED, about 4 mA"),
    "R1131": R("4.7k", "HK_SCL pull-up at 1.8 V (DNP if the carrier has its own)"),
    "R1132": R("4.7k", "HK_SDA pull-up at 1.8 V (DNP if the carrier has its own)"),
    "C1180": C("100n", "U1102 flash decoupling"),
    "C1181": C("100n", "U1103 decoupling"),
    # XADC, UG480 Figure 1-2 (right): on-chip reference
    "FB1101": ("Device:FerriteBead", "600R@100MHz", "Inductor_SMD:L_0603_1608Metric",
               "UG480 Figure 1-2: VCCADC filtered from VCCAUX"),
    "FB1102": ("Device:FerriteBead", "600R@100MHz", "Inductor_SMD:L_0603_1608Metric",
               "UG480 Figure 1-2: GNDADC to ground through a ferrite"),
    "C1175": C("100n", "VCCADC to GNDADC, UG480 Figure 1-2"),
    "C1176": C("470n", "VCCADC to GNDADC, UG480 Figure 1-2", C0603),
})
# 100 ohm LVDS terminations at the FPGA (AERIS R2-R12 for the AD9484)
TERM = ["ADCR_D0", "ADCR_D1", "ADCR_D2", "ADCR_D3", "ADCR_D4", "ADCR_D5", "ADCR_D6",
        "ADCR_D7", "ADCR_DCO", "ADCR_OR", "ADCS_D0", "ADCS_D1", "ADCS_DCO", "ADCS_FCO"]
for i, n in enumerate(TERM):
    PARTS[f"R{1101 + i}"] = R("100", f"{n} termination across the pair at the FPGA: DIFF_TERM "
                                     "is not allowed in a 3.3 V bank (UG471)")
TERM_REF = {n: f"R{1101 + i}" for i, n in enumerate(TERM)}

# 22 ohm series on every DAC line (AERIS R23-R30), in 4-resistor arrays
DAC_LINES = ([f"DACR_D{i}" for i in range(8)] + ["DACR_CLK"]
             + [f"DACS_D{i}" for i in range(14)]
             + ["DACS_IQWRT", "DACS_IQSEL", "DACS_IQCLK", "DACS_IQRESET"])
RPACK = {}                                               # line -> (ref, pin in, pin out)
for i, n in enumerate(DAC_LINES):
    ref, k = f"RN{1101 + i // 4}", i % 4 + 1             # R(k) is pins k and 9-k
    RPACK[n] = (ref, k, 9 - k)
for ref in sorted({r for r, _, _ in RPACK.values()}):
    PARTS[ref] = ("Device:R_Pack04", "4x22", "Resistor_SMD:R_Array_Convex_4x0402",
                  "22 ohm series on the DAC lines, as AERIS-10 (R23-R30)")
RPACK_SPARE = [(ref, k) for ref in sorted({r for r, _, _ in RPACK.values()})
               for k in range(1, 5) if (ref, k) not in {(r, a) for r, a, _ in RPACK.values()}]

# Decoupling, UG483 Table 2-2, FTG256 / XC7A50T:
#   VCCINT 1 x 330 uF, 3 x 4.7 uF, 5 x 0.47 uF; VCCBRAM 1 x 100 uF, 1 x 0.47 uF;
#   VCCAUX 1 x 47 uF, 2 x 4.7 uF, 3 x 0.47 uF; VCCO_0 1 x 47 uF;
#   other banks: 1 x 47 uF per group of up to 4 at one voltage, 2 x 4.7 uF and
#   4 x 0.47 uF per bank. Capacitor types from Table 2-5.
BULK = {"330u": ("Device:C_Polarized", "330u", "Capacitor_Tantalum_SMD:CP_EIA-7343-20_Kemet-V",
                 "UG483 Table 2-5: T520V337M2R5ATE025, 2.5 V tantalum")}
DECOUPLING = [   # (rail, group, [values])
    ("+1V0", "VCCINT", ["330u"] + ["4.7u"] * 3 + ["0.47u"] * 5),
    ("+1V0", "VCCBRAM", ["100u", "0.47u"]),
    ("+1V8_D", "VCCAUX", ["47u"] + ["4.7u"] * 2 + ["0.47u"] * 3),
    ("+3V3_D", "VCCO_0", ["47u"]),
    ("+3V3_D", "VCCO_14/15", ["47u"] + ["4.7u"] * 4 + ["0.47u"] * 8),
    ("+2V5", "VCCO_34", ["47u"] + ["4.7u"] * 2 + ["0.47u"] * 4),
    ("+1V8_D", "VCCO_35", ["47u"] + ["4.7u"] * 2 + ["0.47u"] * 4),
]
DEC_REFS = []                                            # (rail, group, [refs])
_c = 1110
for rail, group, vals in DECOUPLING:
    refs = []
    for v in vals:
        ref = f"C{_c}"
        _c += 1
        if v == "330u":
            PARTS[ref] = BULK[v]
        elif v in ("100u", "47u"):
            PARTS[ref] = ("Device:C", v, C1210, f"UG483 Table 2-5: {v} X5R/X7R 1210, {group}")
        elif v == "4.7u":
            PARTS[ref] = ("Device:C", v, C0805, f"UG483 Table 2-5: 4.7 uF 0805, {group}")
        else:
            PARTS[ref] = ("Device:C", v, C0603, f"UG483 Table 2-5: 0.47 uF 0603, {group}")
        refs.append(ref)
    DEC_REFS.append((rail, group, refs))
    _c = (_c // 5 + 1) * 5                               # each group starts on a round number

# ------------------------------------------------------------ connectors
# JTAG, DS593 Figure 14: 2 VREF, 4 TMS, 6 TCK, 8 TDO, 10 TDI, 12 NC, 14 HALT;
# 3-11 GND, 13 PGND; 1 shown as not used.
JTAG = {2: "+3V3_D", 4: "JTAG_TMS", 6: "JTAG_TCK", 8: "JTAG_TDO", 10: "JTAG_TDI",
        3: "GND", 5: "GND", 7: "GND", 9: "GND", 11: "GND", 13: "GND"}
JTAG_NC = [1, 12, 14]
# Pmod, 2x6: Pmod pins 1-6 on one row, 7-12 on the other; 5/11 GND, 6/12 VCC.
# On an odd/even header Pmod pin k is pad 2k-1 and pin k+6 is pad 2k.
PMOD_PINS = {1: "PMOD_CS", 2: "PMOD_MOSI", 3: "PMOD_MISO", 4: "PMOD_SCLK",
             7: "BEAM_STROBE", 8: "PPS_SYNC", 9: "PMOD_SPARE1", 10: "PMOD_SPARE2",
             5: "GND", 11: "GND"}
PMOD_NC = [6, 12]           # the KV260's 3.3 V: the adapter takes no power from the Pmod


def pmod_pad(k):
    return 2 * k - 1 if k <= 6 else 2 * (k - 6)


# AERIS ribbon: 4 pins per ADAR1000 (CS, TX_LOAD, RX_LOAD, TR), then the SPI
# between grounds.
IDC = {i + 1: n for i, n in enumerate(ADAR[:32])}
IDC.update({33: "ADAR_SCLK", 35: "ADAR_SDIO", 37: "ADAR_SDO",
            34: "GND", 36: "GND", 38: "GND", 39: "GND", 40: "GND"})

# ------------------------------------------------------------ interface
HIER = {
    **{f"LINK_RX_{s}_{pn}": "output" for s in ("D0", "D1", "CLK") for pn in "PN"},
    **{f"LINK_TX_{s}_{pn}": "input" for s in ("D0", "CLK") for pn in "PN"},
    "HK_SCL": "bidirectional", "HK_SDA": "bidirectional",
    "FPGA_PROG_B": "input", "FPGA_IRQ": "output",
    **{f"ADCR_{s}_{pn}": "input" for s in [f"D{i}" for i in range(8)] + ["DCO", "OR"]
       for pn in "PN"},
    **{f"ADCS_{s}_{pn}": "input" for s in ("D0", "D1", "DCO", "FCO") for pn in "PN"},
    **{n: "output" for n in DAC_LINES},
    "CONV_SPI_SCLK": "output", "CONV_SPI_SDIO": "bidirectional",
    "CONV_SPI_CSB_R": "output", "CONV_SPI_CSB_S": "output",
    "CLK_FPGA_P": "input", "CLK_FPGA_N": "input",
    **{f"SW_CTRL{i}": "output" for i in range(4)},
    "CLK_SEL": "output", "XO_SCL": "output", "XO_SDA": "bidirectional",
}
POWER = ["GND", "+1V0", "+1V8_D", "+2V5", "+3V3_D", "+1V2"]

# ------------------------------------------------------------ nets
NETS = {}


def add(net, *pins):
    NETS.setdefault(net, []).extend(pins)


for bank in BANKS.values():
    for ball, net in bank.items():
        add(net, f"U1101.{ball}")
for ball, net in CONFIG.items():
    add(net, f"U1101.{ball}")

# terminations across each pair
for n, ref in TERM_REF.items():
    add(f"{n}_P", f"{ref}.1")
    add(f"{n}_N", f"{ref}.2")
# CLK_FPGA attenuator
add("CLK_FPGA_P", "R1115.1")
add("FPGA_CLK_P", "R1115.2", "R1117.1")
add("CLK_FPGA_N", "R1116.1")
add("FPGA_CLK_N", "R1116.2", "R1118.2")
add("+1V2", "R1117.2", "R1118.1", "C1101.1")      # the two shunts meet at the bias
add("GND", "C1101.2")
# DAC series resistors
for n, (ref, a, b) in RPACK.items():
    add(f"F_{n}", f"{ref}.{a}")
    add(n, f"{ref}.{b}")
# flash, UG470 Figure 2-14
# Pull-ups are drawn standing, rail at the top: pin 1 is the rail, pin 2 the
# signal. Pull-downs the other way round: pin 1 the signal, pin 2 ground.
add("FLASH_CS", "U1102.1", "R1126.2")
add("FLASH_DQ1", "U1102.2")
add("FLASH_DQ2", "U1102.3", "R1127.2")
add("FLASH_DQ0", "U1102.5")
add("FLASH_DQ3", "U1102.7", "R1128.2")
add("F_CCLK", "R1125.1")
add("FLASH_CLK", "R1125.2", "U1102.6")
add("+3V3_D", "U1102.8", "R1126.1", "R1127.1", "R1128.1", "C1180.1")
add("GND", "U1102.4", "C1180.2")
# mode pins, INIT_B, PROGRAM_B
add("PUDC_B", "R1119.2")
add("MODE_M0", "R1120.2")
add("+3V3_D", "R1119.1", "R1120.1")
add("MODE_M1", "R1121.1")
add("MODE_M2", "R1122.1")
add("GND", "R1121.2", "R1122.2")
add("INIT_B", "R1123.2")
add("+3V3_D", "R1123.1", "R1124.1")
add("PROGRAM_B", "R1124.2", "SW1101.1", "U1103.4")
add("GND", "SW1101.2")
# FPGA_PROG_B through the open-drain buffer
add("FPGA_PROG_B", "U1103.2", "R1129.2")
add("+1V8_D", "R1129.1", "U1103.5", "C1181.1")
add("GND", "U1103.3", "C1181.2")
# DONE LED
add("DONE", "Q1101.1")
add("GND", "Q1101.2")
add("DONE_LED", "Q1101.3", "D1101.1")
add("DONE_LED_A", "D1101.2", "R1130.2")
add("+3V3_D", "R1130.1")
# HK pull-ups
add("HK_SCL", "R1131.2")
add("HK_SDA", "R1132.2")
add("+1V8_D", "R1131.1", "R1132.1")
# XADC
add("+1V8_D", "FB1101.1")
add("XADC_VCC", "FB1101.2", "C1175.1", "C1176.1")
add("XADC_GND", "FB1102.1", "C1175.2", "C1176.2")
add("GND", "FB1102.2")
# power pins (unit 4 and the VCCO pins of units 1-3)
_FPGA_POWER = {"VCCINT": "+1V0", "VCCBRAM": "+1V0", "VCCAUX": "+1V8_D", "GND": "GND",
               "VCCO_14": "+3V3_D", "VCCO_15": "+3V3_D", "VCCO_34": "+2V5",
               "VCCO_35": "+1V8_D", "VCCADC_0": "XADC_VCC", "GNDADC_0": "XADC_GND",
               "VCCBATT_0": "GND"}                      # UG470 Figure 2-14: VCCBATT to GND
FPGA_POWER_PINS = {}                                    # name -> [balls], from the symbol
# decoupling
for rail, group, refs in DEC_REFS:
    for ref in refs:
        add(rail, f"{ref}.1")
        add("GND", f"{ref}.2")
# connectors
for pin, net in JTAG.items():
    add(net, f"J1101.{pin}")
for k, net in PMOD_PINS.items():
    add(net, f"J1102.{pmod_pad(k)}")
for pin, net in IDC.items():
    add(net, f"J1103.{pin}")

NO_CONNECT = ([f"U1101.{b}" for balls in BANK_NC.values() for b in balls]
              + [f"J1101.{p}" for p in JTAG_NC]
              + [f"J1102.{pmod_pad(k)}" for k in PMOD_NC]
              + [f"{ref}.{k}" for ref, k in RPACK_SPARE]
              + [f"{ref}.{9 - k}" for ref, k in RPACK_SPARE]
              + ["U1103.1"])


# ------------------------------------------------------------ self-check
def _fpga_symbol():
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import schgen
    return schgen.LibSymbol(FPGA_LIB, schgen.KICAD_SYM + "FPGA_Xilinx_Artix7.kicad_sym")


def check_pins():
    """Prove the pin table against the symbol's pin names: each ball is in the
    bank it is listed under, P nets sit on P pins and N nets on the N pin of
    the SAME pair, and clocks are on clock-capable balls. Then fill in the
    power pins from the symbol. Raises on the first violation."""
    sym = _fpga_symbol()
    name = {b: v[3] for b, v in sym.pins.items()}
    seen = set()
    for bank, table in BANKS.items():
        for ball in list(table) + BANK_NC[bank]:
            assert ball not in seen, f"{ball} assigned twice"
            seen.add(ball)
            assert name[ball].endswith(f"_{bank}"), f"{ball} {name[ball]} is not in bank {bank}"
        pairs = {}
        for ball, net in table.items():
            m = re.search(r"_(P|N)$", net)
            if not m or net.startswith("+"):
                continue
            pm = re.match(r"IO_L(\d+)([PN])_", name[ball])
            assert pm and pm.group(2) == m.group(1), f"{net} on {ball} {name[ball]}"
            pairs.setdefault(net[:-2], {})[m.group(1)] = pm.group(1)
        for base, pn in pairs.items():
            assert pn.get("P") == pn.get("N"), f"{base}: P and N on different pairs {pn}"
    # every user I/O of the four banks accounted for
    io = {b for b, n in name.items() if re.match(r"IO_.*_(14|15|34|35)$", n)}
    assert io == seen, f"unassigned I/O: {sorted(io - seen)}"
    for ball, why in CLOCK_BALLS.items():
        assert re.search(r"_(MRCC|SRCC)_", name[ball]), f"{why}: {ball} {name[ball]} not clock capable"
    for ball in CONFIG:
        assert name[ball].endswith("_0"), f"{ball} {name[ball]} not a bank-0 pin"
    for b, n in name.items():
        if n in _FPGA_POWER:
            FPGA_POWER_PINS.setdefault(n, []).append(b)
            add(_FPGA_POWER[n], f"U1101.{b}")
    covered = set(seen) | set(CONFIG) | {b for bs in FPGA_POWER_PINS.values() for b in bs}
    assert covered == set(name), f"FPGA balls not covered: {sorted(set(name) - covered)}"
    return sym


check_pins()
