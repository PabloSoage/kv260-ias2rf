"""
ADC_SDR sheet - the connection specification. See docs/ADC_SDR_SPEC.md.

  IF_RX_A -> U602 AD8352, single-ended in, 12 dB -> AD9253 channel A
  IF_RX_C -> U603 AD8352, single-ended in, 12 dB -> AD9253 channel B
  AD9253 channels C and D unused: inputs tied to VCM, outputs open.

The AD9253 runs one-lane (register 0x21, set over SPI) at 62.5 MSPS - the
AD9253 divides the 500 MHz master clock by 8 (docs/CLOCK_SPEC.md §1.1).
In one-lane mode channel A comes out on D0+-B and channel B on D1+-B
(datasheet Rev. D, Table 8 and its footnote 1).

Input network: the AD9484's Figure 30 arrangement (load legs, centre tap) as
on ADC_RADAR, but the AD9253's inputs are NOT internally biased (datasheet
p.22, "Input Common Mode"), so the centre tap is tied to its VCM output
through 200 ohm, as in AD9253 Figure 58.
"""

from kit import R, C, FB, C0805

AD8352_FP = "Package_CSP:LFCSP-16-1EP_3x3mm_P0.5mm_EP1.6x1.6mm"
AD9253_FP = "Package_DFN_QFN:QFN-48-1EP_7x7mm_P0.5mm_EP5.6x5.6mm"

PARTS = {
    "U601": ("kv260-ias2rf:AD9253BCPZ-125", "AD9253BCPZ-125", AD9253_FP,
             "SDR ADC, 14 bits. CP-48-13: 7x7 mm, exposed pad 5.60 mm (Figure 77), matching the stock footprint"),
    "U602": ("kv260-ias2rf:AD8352ACPZ", "AD8352ACPZ", AD8352_FP, "Channel A driver"),
    "U603": ("kv260-ias2rf:AD8352ACPZ", "AD8352ACPZ", AD8352_FP, "Channel B driver"),

    "FB601": FB("600R@100MHz", "As FB501 on ADC_RADAR: isolates the drivers' 5 V, >= 0.5 A"),
    "C660": C("10u", "AD8352 eval board C1: 10 uF bulk", C0805),
    "FB602": FB("220R@100MHz", "As FB502: >= 1 A, DCR <= 0.1 ohm. AD9253 p.38: separate "
                              "AVDD and DRVDD supplies"),
    "C665": C("10u", "AD9253 p.38: 'several different decoupling capacitors ... to cover both "
                     "high and low frequencies'. 10 uF bulk", C0805),
    "FB603": FB("220R@100MHz", "As FB503"),
    "C673": C("10u", "10 uF bulk on DRVDD", C0805),

    # ---- the ADC's own pins
    "R641": R("10k 1%", "AD9253 Table 8: RBIAS to a 10 kohm (1% tolerance) resistor to ground"),
    "C641": C("1u", "AD9253 p.38: VREF decoupled with a low-ESR 1.0 uF ..."),
    "C642": C("100n", "... in parallel with a low-ESR 0.1 uF ceramic"),
    "C643": C("100n", "AD9253 p.38: 'The VCM pin must be decoupled to ground with a 0.1 uF "
                      "capacitor'"),
    "R642": R("100", "ADCLK948 Figure 17 and AD9253 Figure 65: 100 ohm across the clock pair "
                     "at the receiver"),
}
# Per channel: the same network twice. k = 0 (channel A, U602), 1 (channel B, U603).
CH = []
for k, (u, lbl, vp, vn) in enumerate((("U602", "IF_RX_A", 36, 35), ("U603", "IF_RX_C", 37, 38))):
    b = 20 * k
    refs = {
        "term": f"R{601 + b}", "cin": f"C{601 + b}", "rn": f"R{602 + b}", "cvin": f"C{602 + b}",
        "rvin": f"R{603 + b}", "rg": f"R{604 + b}", "rd": f"R{605 + b}", "cd": f"C{603 + b}",
        "vcm": f"C{604 + b}", "cp": f"C{605 + b}", "cn": f"C{606 + b}", "rp": f"R{606 + b}",
        "rl": f"R{607 + b}", "ccm": f"C{607 + b}", "rcm": f"R{608 + b}", "sp": f"R{609 + b}",
        "sn": f"R{610 + b}", "csh": f"C{608 + b}", "vcc": (f"C{661 + 2 * k}", f"C{662 + 2 * k}"),
    }
    CH.append((u, lbl, vp, vn, refs))
    PARTS.update({
        refs["term"]: R("64.9", "AD8352 Figure 26: 65 ohm input termination"),
        refs["cin"]: C("100n", "AD8352 Figure 26: AC coupling into VIP. 0.1 uF into ~3 kohm: "
                               "corner well below the 100 kHz bottom of HF"),
        refs["rn"]: R("200", "AD8352 Figure 26: RN = 200 ohm, VIP to RGN"),
        refs["cvin"]: C("100n", "AD8352 Figure 26: AC coupling of VIN"),
        refs["rvin"]: R("24.9", "AD8352 Figure 26: 25 ohm from VIN to ground"),
        refs["rg"]: R("120", "AD8352 Table 7, 12 dB single-ended: RG = 120 ohm"),
        refs["rd"]: R("4.3k", "AD8352 Table 7, 12 dB: RD = 4.3 kohm"),
        refs["cd"]: C("0.3p", "AD8352 Table 7, 12 dB: CD = 0.3 pF. C0G"),
        refs["vcm"]: C("100n", "AD8352 Table 4: VCM decoupled with 0.1 uF"),
        refs["cp"]: C("100n", "AD9253 Figure 58: 0.1 uF coupling"),
        refs["cn"]: C("100n", "AD9253 Figure 58: 0.1 uF coupling"),
        refs["rp"]: R("200", "AD9484 Figure 30 load leg (the AD8352 tables assume ~200 ohm)"),
        refs["rl"]: R("200", "Same"),
        refs["ccm"]: C("100n", "AD9253 Figure 58: 0.1 uF on the centre tap"),
        refs["rcm"]: R("200", "AD9253 Figure 58: 200 ohm from the centre tap to VCM - the "
                              "inputs are not internally biased (p.22)"),
        refs["sp"]: R("33", "AD9253 Figure 58: 33 ohm series"),
        refs["sn"]: R("33", "AD9253 Figure 58: 33 ohm series"),
        refs["csh"]: C("5p", "AD9253 Figure 58: 5 pF across the inputs. C0G"),
        refs["vcc"][0]: C("100n", f"AD8352 eval board C6: 0.1 uF at {u} VCC pin 8"),
        refs["vcc"][1]: C("100n", f"AD8352 eval board C7: 0.1 uF at {u} VCC pin 13"),
    })

AVDD = [3, 4, 7, 34, 39, 45, 46]
DRVDD = [8, 29]
for i, p in enumerate(AVDD):
    PARTS[f"C{666 + i}"] = C("100n", f"0.1 uF at AVDD pin {p} (as the AD9484 eval board: one per pin)")
for i, p in enumerate(DRVDD):
    PARTS[f"C{674 + i}"] = C("100n", f"0.1 uF at DRVDD pin {p}")

DATA = {"ADCS_D0_P": 24, "ADCS_D0_N": 23,     # one-lane: channel A on D0+-B
        "ADCS_D1_P": 22, "ADCS_D1_N": 21,     # one-lane: channel B on D1+-B
        "ADCS_DCO_P": 18, "ADCS_DCO_N": 17, "ADCS_FCO_P": 20, "ADCS_FCO_N": 19}
HIER = {**{k: "output" for k in DATA},
        "CLK_ADCS_P": "input", "CLK_ADCS_N": "input",
        "CONV_SPI_SCLK": "input", "CONV_SPI_SDIO": "bidirectional",
        "CONV_SPI_CSB_S": "input", "IF_RX_A": "input", "IF_RX_C": "input"}
POWER = ["+5V0", "+5V_IFS", "+1V8_A", "+1V8_ADCS_A", "+1V8_D", "+1V8_ADCS_D", "GND"]

NETS = {
    "+5V0": ["FB601.1"],
    "+5V_IFS": ["FB601.2", "C660.1", "C661.1", "C662.1", "C663.1", "C664.1"]
               + [f"{u}.{p}" for u in ("U602", "U603") for p in (8, 13, 15)],
    "+1V8_A": ["FB602.1"],
    "+1V8_ADCS_A": ["FB602.2", "C665.1"] + [f"C{666 + i}.1" for i in range(7)]
                   + [f"U601.{p}" for p in AVDD],
    "+1V8_D": ["FB603.1"],
    "+1V8_ADCS_D": ["FB603.2", "C673.1", "C674.1", "C675.1"] + [f"U601.{p}" for p in DRVDD],
    "GND": ["C660.2", "C665.2", "C673.2", "C661.2", "C662.2", "C663.2", "C664.2"]
           + [f"C{666 + i}.2" for i in range(7)] + ["C674.2", "C675.2"]
           + [f"{u}.{p}" for u in ("U602", "U603") for p in (6, 7, 9, 12, 17)]
           + ["U601.49", "U601.41", "U601.33", "U601.44", "R641.2", "C641.2", "C642.2",
              "C643.2"],
    "ADCS_VCM": ["U601.43", "C643.1", "U601.48", "U601.47", "U601.1", "U601.2"],
    "VREF": ["U601.42", "C641.1", "C642.1"],
    "RBIAS": ["U601.40", "R641.1"],
    "CLK_ADCS_P": ["U601.6", "R642.1"],
    "CLK_ADCS_N": ["U601.5", "R642.2"],
    "CONV_SPI_SDIO": ["U601.31"],
    "CONV_SPI_SCLK": ["U601.30"],
    "CONV_SPI_CSB_S": ["U601.32"],
    **{k: [f"U601.{p}"] for k, p in DATA.items()},
}
for k, (u, lbl, vp, vn, r) in enumerate(CH):
    t = "AB"[k]
    NETS["ADCS_VCM"] += [f"{r['rcm']}.2"]
    NETS["GND"] += [f"{r['term']}.2", f"{r['rvin']}.2", f"{r['vcm']}.2", f"{r['ccm']}.1"]
    NETS.update({
        lbl: [f"{r['term']}.1", f"{r['cin']}.1"],
        f"{t}_VIP": [f"{r['cin']}.2", f"{u}.16", f"{r['rn']}.1"],
        f"{t}_RGN": [f"{r['rn']}.2", f"{u}.3", f"{r['rg']}.1"],
        f"{t}_RGP": [f"{r['rg']}.2", f"{u}.2"],
        f"{t}_RDP": [f"{u}.1", f"{r['rd']}.1", f"{r['cd']}.1"],
        f"{t}_RDN": [f"{u}.4", f"{r['rd']}.2", f"{r['cd']}.2"],
        f"{t}_VIN": [f"{u}.5", f"{r['cvin']}.2"],
        f"{t}_VIN_T": [f"{r['cvin']}.1", f"{r['rvin']}.1"],
        f"{t}_VCM8352": [f"{u}.14", f"{r['vcm']}.1"],
        f"{t}_OP": [f"{u}.11", f"{r['cp']}.1"],
        f"{t}_ON": [f"{u}.10", f"{r['cn']}.1"],
        f"{t}_P": [f"{r['cp']}.2", f"{r['rp']}.1", f"{r['sp']}.1"],
        f"{t}_N": [f"{r['cn']}.2", f"{r['rl']}.2", f"{r['sn']}.1"],
        f"{t}_CM": [f"{r['rp']}.2", f"{r['rl']}.1", f"{r['ccm']}.2", f"{r['rcm']}.1"],
        f"{t}_INP": [f"{r['sp']}.2", f"U601.{vp}", f"{r['csh']}.1"],
        f"{t}_INN": [f"{r['sn']}.2", f"U601.{vn}", f"{r['csh']}.2"],
    })

# Lanes that one-lane mode disables or that carry the unused channels C, D.
NO_CONNECT = [f"U601.{p}" for p in (28, 27, 26, 25, 16, 15, 14, 13, 12, 11, 10, 9)]
