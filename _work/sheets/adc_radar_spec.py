"""
ADC_RADAR sheet - the connection specification.

Written BEFORE the drawing, from the datasheets, and kept separate from it:
_work/sheets/adc_radar.py draws the sheet from coordinates, and
_work/check_sheet.py checks that what was drawn connects exactly as listed
here. docs/ADC_RADAR_SPEC.md explains each choice.

The chain is AERIS-10's receive path, rebuilt from the datasheets:

  IF_RX_B (single-ended, 50 ohm, from ROUTING)
    -> U502 AD8352, single-ended in, 15 dB   (AD8352 Figure 26, Table 7)
    -> U503 AD8352, differential, 10 dB      (AD8352 Table 5)
    -> U501 AD9484, 8 bits, 400/500 MSPS     (AD9484 Figure 30)

25 dB in total, the same as AERIS-10's two cascaded AD8352s
(_work/aeris_reference_circuit.py U8 U4: RG 56 and 115 ohm). AERIS feeds its
first stage differentially from the mixer; here it is single-ended, because
the routing switch in front is single-ended, so the first stage takes the
single-ended values of Table 7 instead of Table 5.
"""

R0402, C0402 = "Resistor_SMD:R_0402_1005Metric", "Capacitor_SMD:C_0402_1005Metric"
C0805, L0603 = "Capacitor_SMD:C_0805_2012Metric", "Inductor_SMD:L_0603_1608Metric"
AD8352_FP = "Package_CSP:LFCSP-16-1EP_3x3mm_P0.5mm_EP1.6x1.6mm"


def R(value, why):
    return ("Device:R", value, R0402, why)


def C(value, why, fp=C0402):
    return ("Device:C", value, fp, why)


# ref -> (lib_id, value, footprint, source of the value)
PARTS = {
    "U501": ("kv260-ias2rf:AD9484BCPZ-500", "AD9484BCPZ-500",
             "kv260-ias2rf:LFCSP-56-1EP_8x8mm_P0.5mm_EP5.1x5.1mm",
             "Radar ADC, AERIS-10's part. Footprint: CP-56-5 has a 5.10 mm exposed pad "
             "(datasheet Figure 40); KiCad's 8x8 mm 56-pin parts have 6.6 or 5.1x4.96 mm. "
             "Custom footprint needed at layout"),
    "U502": ("kv260-ias2rf:AD8352ACPZ", "AD8352ACPZ", AD8352_FP,
             "First stage, single-ended in. CP-16-22: exposed pad 1.60 mm (datasheet outline)"),
    "U503": ("kv260-ias2rf:AD8352ACPZ", "AD8352ACPZ", AD8352_FP, "Second stage, differential"),

    # ---- supplies
    "FB501": ("Device:FerriteBead", "600R@100MHz", L0603,
              "Judgement: isolates the drivers' 5 V from +5V0. Rated >= 0.5 A; draw is "
              "2 x 39 mA max (AD8352 Table 1)"),
    "C520": C("10u", "AD8352 evaluation board: 10 uF bulk (datasheet, C1)", C0805),
    "FB502": ("Device:FerriteBead", "220R@100MHz", L0603,
              "AD9484 evaluation board: a ferrite in each rail (E302). Rated >= 1 A, "
              "DCR <= 0.1 ohm: 300 mA max x 0.1 ohm = 30 mV, AVDD stays inside 1.7-1.9 V"),
    "C521": C("10u", "AD9484 evaluation board: 10 uF per rail (C314)", C0805),
    "FB503": ("Device:FerriteBead", "220R@100MHz", L0603,
              "AD9484 evaluation board: ferrite in the DRVDD rail (E303). Same part as FB502"),
    "C533": C("10u", "AD9484 evaluation board: 10 uF per rail (C315)", C0805),

    # ---- stage 1: single-ended in (AD8352 Figure 26), 15 dB (Table 7)
    "R501": R("64.9", "AD8352 Figure 26: 65 ohm input termination"),
    "C501": C("100n", "AD8352 Figure 26: AC coupling into VIP"),
    "R502": R("200", "AD8352 Figure 26 and text: RN = 200 ohm between VIP and RGN, "
                     "balances the outputs"),
    "C502": C("100n", "AD8352 Figure 26: AC coupling of VIN"),
    "R503": R("24.9", "AD8352 Figure 26: 25 ohm from VIN to ground"),
    "R504": R("68", "AD8352 Table 7, 15 dB single-ended: RG = 68 ohm"),
    "R505": R("4.3k", "AD8352 Table 7, 15 dB: RD = 4.3 kohm"),
    "C503": C("0.6p", "AD8352 Table 7, 15 dB: CD = 0.6 pF. C0G"),
    "C504": C("100n", "AD8352 Table 4: VCM decoupled to ground with 0.1 uF"),

    # ---- between the stages (AD9484 Figure 30's output network; AERIS C48-C53)
    "C507": C("100n", "AD9484 Figure 30: 0.1 uF out of VOP"),
    "C508": C("100n", "AD9484 Figure 30: 0.1 uF out of VON"),
    "R506": R("200", "AD9484 Figure 30: 200 ohm load leg"),
    "R507": R("200", "AD9484 Figure 30: 200 ohm load leg"),
    "C509": C("100n", "AD9484 Figure 30: 0.1 uF from the centre to ground"),
    "C510": C("100n", "AD9484 Figure 30: 0.1 uF into VIP (AERIS C49)"),
    "C511": C("100n", "AD9484 Figure 30: 0.1 uF into VIN (AERIS C48)"),

    # ---- stage 2: differential, 10 dB (AD8352 Table 5)
    "R508": R("115", "AD8352 Table 5, 10 dB: RG = 115 ohm (AERIS R14)"),
    "R509": R("4.3k", "AD8352 Table 5, 10 dB: RD = 4.3 kohm (AERIS R15)"),
    "C512": C("0.2p", "AD8352 Table 5, 10 dB: CD = 0.2 pF (AERIS C43). C0G"),
    "C513": C("100n", "AD8352 Table 4: VCM decoupled with 0.1 uF"),

    # ---- into the ADC (AD9484 Figure 30)
    "C516": C("100n", "AD9484 Figure 30: 0.1 uF out of VOP"),
    "C517": C("100n", "AD9484 Figure 30: 0.1 uF out of VON"),
    "R510": R("200", "AD9484 Figure 30: 200 ohm to the common-mode node"),
    "R511": R("200", "AD9484 Figure 30: 200 ohm to the common-mode node"),
    "C518": C("100n", "AD9484 Figure 30: 0.1 uF on the CML node"),
    "R512": R("24", "AD9484 Figure 30 'R', value from AERIS R13 and AD8352 p.14 "
                    "('the output 24 ohm resistors provide isolation')"),
    "R513": R("24", "Same as R512 (AERIS R1)"),
    "C519": C("2.7p", "AD9484 Figure 30 'C' (depends on input frequency); 2.7 pF as "
                      "AERIS C3, measured at the 120 MHz IF. C0G"),

    # ---- ADC clock, reference
    "R514": R("100", "ADCLK948 Figure 17 and AD9484 Figure 31: 100 ohm across the "
                     "pair at the receiver (AERIS R173)"),
    "R515": R("20k", "AD9484 p.17: internal VREF = 20 kohm to ground (AERIS R38)"),
}
# One 0.1 uF at each supply pin: AD9484 evaluation board (11 on AVDD, 3 on
# DRVDD, one per pin) and AD8352 evaluation board (C6, C7: two per device).
AVDD = [30, 32, 33, 34, 37, 38, 39, 41, 42, 43, 46]
DRVDD = [7, 24, 47]
for i in range(11):
    PARTS[f"C{522 + i}"] = C("100n", f"AD9484 eval board: 0.1 uF at AVDD pin {AVDD[i]}")
for i in range(3):
    PARTS[f"C{534 + i}"] = C("100n", f"AD9484 eval board: 0.1 uF at DRVDD pin {DRVDD[i]}")
for ref, pin in (("C505", "U502.8"), ("C506", "U502.13"), ("C514", "U503.8"), ("C515", "U503.13")):
    PARTS[ref] = C("100n", f"AD8352 eval board C6/C7: 0.1 uF at VCC pin {pin}")

# Interface: hierarchical labels.
DATA = {  # label -> AD9484 pin (Table 7)
    **{f"ADCR_D{i}_P": p for i, p in enumerate((4, 6, 10, 12, 14, 16, 18, 20))},
    **{f"ADCR_D{i}_N": p for i, p in enumerate((3, 5, 9, 11, 13, 15, 17, 19))},
    "ADCR_OR_P": 22, "ADCR_OR_N": 21, "ADCR_DCO_P": 50, "ADCR_DCO_N": 49,
}
HIER = {**{k: "output" for k in DATA},
        "CLK_ADCR_P": "input", "CLK_ADCR_N": "input",
        "CONV_SPI_SCLK": "input", "CONV_SPI_SDIO": "bidirectional",
        "CONV_SPI_CSB_R": "input", "IF_RX_B": "input"}

POWER = ["+5V0", "+5V_IFR", "+1V8_A", "+1V8_ADCR_A", "+1V8_D", "+1V8_ADCR_D", "GND"]


def stage(u):
    return [f"{u}.{p}" for p in (6, 7, 9, 12, 17)]


NETS = {
    "+5V0":        ["FB501.1"],
    "+5V_IFR":     ["FB501.2", "C520.1", "C505.1", "C506.1", "C514.1", "C515.1",
                    "U502.8", "U502.13", "U502.15", "U503.8", "U503.13", "U503.15"],
    "+1V8_A":      ["FB502.1"],
    "+1V8_ADCR_A": ["FB502.2", "C521.1"] + [f"C{522 + i}.1" for i in range(11)]
                   + [f"U501.{p}" for p in AVDD],
    "+1V8_D":      ["FB503.1"],
    "+1V8_ADCR_D": ["FB503.2", "C533.1"] + [f"C{534 + i}.1" for i in range(3)]
                   + [f"U501.{p}" for p in DRVDD],
    "GND":         ["C520.2", "C521.2", "C533.2", "C505.2", "C506.2", "C514.2", "C515.2"]
                   + [f"C{522 + i}.2" for i in range(11)] + [f"C{534 + i}.2" for i in range(3)]
                   + stage("U502") + stage("U503")
                   + ["U501.57", "U501.8", "U501.23", "U501.48", "U501.29",
                      "R501.2", "R503.2", "C504.2", "C509.2", "C513.2", "C518.2", "R515.2"],

    # stage 1
    "IF_RX_B":  ["R501.1", "C501.1"],
    "S1_VIP":   ["C501.2", "U502.16", "R502.1"],
    "S1_RGN":   ["R502.2", "U502.3", "R504.1"],
    "S1_RGP":   ["R504.2", "U502.2"],
    "S1_RDP":   ["U502.1", "R505.1", "C503.1"],
    "S1_RDN":   ["U502.4", "R505.2", "C503.2"],
    "S1_VIN":   ["U502.5", "C502.2"],
    "S1_VIN_T": ["C502.1", "R503.1"],
    "S1_VCM":   ["U502.14", "C504.1"],
    "S1_OP":    ["U502.11", "C507.1"],
    "S1_ON":    ["U502.10", "C508.1"],
    # between the stages
    "IS_P":     ["C507.2", "R506.1", "C510.1"],
    "IS_N":     ["C508.2", "R507.2", "C511.1"],
    "IS_CM":    ["R506.2", "R507.1", "C509.1"],
    # stage 2
    "S2_VIP":   ["C510.2", "U503.16"],
    "S2_VIN":   ["C511.2", "U503.5"],
    "S2_RGN":   ["U503.3", "R508.1"],
    "S2_RGP":   ["U503.2", "R508.2"],
    "S2_RDP":   ["U503.1", "R509.1", "C512.1"],
    "S2_RDN":   ["U503.4", "R509.2", "C512.2"],
    "S2_VCM":   ["U503.14", "C513.1"],
    "S2_OP":    ["U503.11", "C516.1"],
    "S2_ON":    ["U503.10", "C517.1"],
    # into the ADC
    "AD_P":     ["C516.2", "R510.1", "R512.1"],
    "AD_N":     ["C517.2", "R511.2", "R513.1"],
    "ADCR_VCM": ["R510.2", "R511.1", "U501.40", "C518.1"],
    "VIN_P":    ["R512.2", "U501.35", "C519.1"],
    "VIN_N":    ["R513.2", "U501.36", "C519.2"],
    "VREF":     ["U501.31", "R515.1"],
    "CLK_ADCR_P": ["U501.44", "R514.1"],
    "CLK_ADCR_N": ["U501.45", "R514.2"],
    "CONV_SPI_SCLK":  ["U501.26"],
    "CONV_SPI_SDIO":  ["U501.25"],
    "CONV_SPI_CSB_R": ["U501.27"],
    **{k: [f"U501.{p}"] for k, p in DATA.items()},
}

# DNC: "Do not connect to this pin. This pin should be left floating."
NO_CONNECT = [f"U501.{p}" for p in (1, 2, 28, 51, 52, 53, 54, 55, 56)]
