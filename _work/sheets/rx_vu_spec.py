"""
RX_VU sheet (Rev08) - the connection specification. See docs/REV08_PLAN.md section 5 and docs/RX_VU_SPEC.md.

The VHF/UHF receive front end: J961 (the thirteenth SMA) -> ESD -> bias tee -> LNA with bypass -> preselector A
(straight, FM band-pass, FM-reject high-pass, or preselector B) -> converter (RFFC5072) or its bypass ->
170 MHz anti-alias low-pass -> IF amplifier -> step attenuator -> IF_VU, the 50 ohm line on L6 to SW2 (ROUTING).
One TCA6416A at 0x20 on the FPGA's XO_SCL/XO_SDA bus carries every control line (section 5.8); one LP5907-3.0
makes +3V0_RF from +3V3_D.

Unlike the Rev03 sheets, the drawing (rx_vu.py) is generated from this table: PINS below is both what is drawn
and what _work/check_sheet.py rx_vu checks against KiCad's own netlist of the drawing. What the check proves is
that the drawing makes exactly these connections and no others (no stray wire, no label typo, no pin left out);
the design itself is reviewed here, in this table, against the data sheets named in _work/rev08_symbols.py.

Values: filters from _work/sim/rev08_filters_mc.py (catalogue values, Monte Carlo, plan section 5.4); the
RFFC5072's loop filter, reference and supply network from its data sheet's wideband application schematic
(DS140110 p.13); the SPF5043Z bias from its evaluation board, with the chokes and blocks scaled down to 30 MHz.
"""

from kit import R, C, C0402, L0603

L0402, L0805, C0805 = "Inductor_SMD:L_0402_1005Metric", "Inductor_SMD:L_0805_2012Metric", "Capacitor_SMD:C_0805_2012Metric"
FP = "kv260-ias2rf:"


def L(value, why, fp=L0402):
    return ("Device:L", value, fp, why)


def U(lib, value, why, fp=None):
    return (lib, value, fp or "", why)


PARTS = {
    "J961": ("Connector:Conn_Coaxial", "VU_ANT", "Connector_Coaxial:SMA_Samtec_SMA-J-P-H-ST-EM1_EdgeMount",
             "The thirteenth SMA: VHF/UHF antenna, 30 MHz - 3 GHz; bias tee up to 125 mA at 5 V (JP1301)"),
    "D1301": ("Device:D_TVS", "PESD5V0F1BL", "Diode_SMD:D_SOD-882",
              "ESD on the antenna, as the other twelve SMAs (5 V stand-off: the bias tee's 5 V sits at it)"),
    "U1301": U("kv260-ias2rf:SPF5043Z", "SPF5043Z", "LNA, 22.6 dB / NF 0.6 dB at 100 MHz, 25 mA at 3.0 V"),
    "U1302": U("kv260-ias2rf:PE4259", "PE4259", "LNA bypass, input side; CTRL high = LNA in"),
    "U1303": U("kv260-ias2rf:PE4259", "PE4259", "LNA bypass, output side"),
    "U1304": U("kv260-ias2rf:PE42442", "PE42442", "Preselector A in: RF1 straight, RF2 FM band-pass, RF3 FM reject, RF4 preselector B"),
    "U1305": U("kv260-ias2rf:PE42442", "PE42442", "Preselector A out"),
    "U1306": U("kv260-ias2rf:SKY13418-485LF", "SKY13418-485LF", "Preselector B in: RF1 UHF low-pass, RF2 SAW 1090, RF3 HPF 1 GHz, RF4 LPF 1 GHz, RF5-8 spare"),
    "U1307": U("kv260-ias2rf:SKY13418-485LF", "SKY13418-485LF", "Preselector B out"),
    "U1308": U("kv260-ias2rf:PE4259", "PE4259", "Converter bypass, input side; CTRL high = through the RFFC5072"),
    "U1309": U("kv260-ias2rf:PE4259", "PE4259", "Converter bypass, output side"),
    "U1310": U("kv260-ias2rf:SPF5043Z", "SPF5043Z", "IF amplifier, 30-170 MHz"),
    "U1311": U("kv260-ias2rf:PE4312", "PE4312", "Step attenuator 0-31.5 dB, serial; powers up at 31.5 dB (C bits high)"),
    "U1312": U("kv260-ias2rf:RFFC5072", "RFFC5072", "Synthesiser and mixer, LO 85-4200 MHz; down-converts to the 135 MHz IF"),
    "U1313": U("kv260-ias2rf:TCA6416ARTW", "TCA6416ARTWR", "I2C expander 0x20 (ADDR low) on XO_SCL/XO_SDA; ports at 3.0 V"),
    "U1314": U("kv260-ias2rf:AP22652W6", "AP22652W6-7", "Bias-tee switch, 125 mA limit (RLIM 210 k), active-low enable, fault flag"),
    "U1315": U("Regulator_Linear:LP5907MFX-3.0", "LP5907MFX-3.0", "+3V0_RF for the whole block, 250 mA, low noise",
               "Package_TO_SOT_SMD:SOT-23-5"),
    "Y1301": U("kv260-ias2rf:TCXO_2016_4P", "26MHz 1XXD26000MAA", "RFFC5072 reference, 26 MHz +-1.5 ppm, clipped sine"),
    "T1301": U("kv260-ias2rf:TC1-1-13M+", "TC1-1-13M+", "Mixer input balun 1:1, 4.5-3000 MHz"),
    "T1302": U("kv260-ias2rf:TC4-1W+", "TC4-1W+", "Mixer output balun 4:1 with centre tap: the data sheet's -2 dB arrangement; "
               "the mixer's bias current flows through it: MIX2_IDD <= 3 (TC4-1W+ is rated 30 mA)"),
    "FL1301": U("kv260-ias2rf:TA1090EC", "TA1090EC", "SAW band-pass 1090 MHz (ADS-B)"),
    "FL1302": ("RF_Filter:HFCN-1000", "HFCN-1000+", FP + "FILTER-SMD_1206-4P-L3.2-W1.6-L", "LTCC high-pass 1 GHz"),
    "FL1303": ("RF_Filter:LFCN-1000", "LFCN-1000+", FP + "FILTER-SMD_1206-4P-L3.2-W1.6-L", "LTCC low-pass 1 GHz"),
    "JP1301": ("Jumper:SolderJumper_3_Bridged12", "BIAS 5V0 | 3V3", "Jumper:SolderJumper-3_P1.3mm_Bridged12_RoundedPad1.0x1.5mm",
               "Bias-tee supply: 1-2 (as built) +5V0, cut and bridge 2-3 for +3V3_D"),
    "FB1301": ("Device:FerriteBead", "600R@100MHz", L0603, "+3V3_D into the front end's LDO"),
}

# ---------------------------------------------------------------- pins of the ICs and other multi-pin parts
GND, V3, V3D, V5 = "GND", "+3V0_RF", "+3V3_D", "+5V0"
PINS = {
    "J961": {"1": "VU_ANT", "2": GND},
    "D1301": {"1": "VU_ANT", "2": GND},
    "U1301": {"3": "VU_LNA_IN", "1": "VU_LNA_OUT", "2": GND, "4": GND},
    "U1302": {"5": "VU_LNA_SW_IN", "1": "VU_LNA_IN_SW", "3": "VU_LNA_BYPASS", "4": "VU_LNA_ON", "6": V3, "2": GND},
    "U1303": {"5": "VU_PSA_IN", "1": "VU_LNA_OUT_SW", "3": "VU_LNA_BYPASS", "4": "VU_LNA_ON", "6": V3, "2": GND},
    "U1308": {"5": "VU_PSA_OUT", "1": "VU_MIX_IN_SW", "3": "VU_CONV_BYPASS", "4": "VU_CONV_ON", "6": V3, "2": GND},
    "U1309": {"5": "VU_AA_IN", "1": "VU_MIX_OUT_SW", "3": "VU_CONV_BYPASS", "4": "VU_CONV_ON", "6": V3, "2": GND},
    "U1304": {"22": "VU_PSA_IN", "14": "VU_PSA_THRU", "11": "VU_FMBP_IN", "8": "VU_FMREJ_IN", "5": "VU_PSB_IN",
              "17": "VU_PSA_V1", "18": "VU_PSA_V2", "19": GND, "20": GND, "16": V3},
    "U1305": {"22": "VU_PSA_OUT", "14": "VU_PSA_THRU", "11": "VU_FMBP_OUT", "8": "VU_FMREJ_OUT", "5": "VU_PSB_OUT",
              "17": "VU_PSA_V1", "18": "VU_PSA_V2", "19": GND, "20": GND, "16": V3},
    "U1306": {"13": "VU_PSB_IN", "3": "VU_UHF_IN", "9": "VU_SAW_IN", "2": "VU_HP1G_IN", "10": "VU_LP1G_IN",
              "1": "NC", "11": "NC", "14": "NC", "12": "NC", "8": "NC",
              "7": "VU_PSB_V1", "6": "VU_PSB_V2", "5": "VU_PSB_V3", "4": V3, "15": GND},
    "U1307": {"13": "VU_PSB_OUT", "3": "VU_UHF_OUT", "9": "VU_SAW_OUT", "2": "VU_HP1G_OUT", "10": "VU_LP1G_OUT",
              "1": "NC", "11": "NC", "14": "NC", "12": "NC", "8": "NC",
              "7": "VU_PSB_V1", "6": "VU_PSB_V2", "5": "VU_PSB_V3", "4": V3, "15": GND},
    "FL1301": {"2": "VU_SAW_IN", "5": "VU_SAW_OUT", "1": GND, "3": GND, "4": GND, "6": GND},
    "FL1302": {"1": "VU_HP1G_IN", "3": "VU_HP1G_OUT", "2": GND, "4": GND},
    "FL1303": {"1": "VU_LP1G_IN", "3": "VU_LP1G_OUT", "2": GND, "4": GND},
    "T1301": {"6": "VU_MIX_IN", "4": "VU_MIX_INR", "1": "VU_MIX_IPP", "3": "VU_MIX_IPN", "2": "NC"},
    "T1302": {"6": "VU_MIX_OUT", "4": "VU_MIX_OUTR", "1": "VU_MIX_OPP", "3": "VU_MIX_OPN", "2": V3},
    "U1312": {"23": "VU_MIX_IPP", "24": "VU_MIX_IPN", "28": "VU_MIX_OPP", "27": "VU_MIX_OPN",
              "10": "VU_REF", "30": "VU_ENX", "31": "VU_SCLK", "32": "VU_SDATA", "1": "VU_ENBL", "9": "VU_MODE",
              "29": "VU_RESETX", "4": "VU_REXT", "2": "NC", "3": "NC", "12": GND,
              "6": "VU_LF1", "7": "VU_LF2", "8": "VU_LF3", "26": "VU_LD", "25": "NC", "15": "NC", "16": "NC",
              "11": "NC", "13": "NC", "14": "NC", "17": "NC", "18": "NC", "20": "NC", "21": "NC",
              "5": V3, "22": V3, "19": V3, "33": GND},
    "Y1301": {"1": "VU_TCXO_VC", "2": GND, "3": "VU_TCXO_OUT", "4": "VU_TCXO_VCC"},
    "U1311": {"2": "VU_ATT_IN", "14": "IF_VU", "3": "VU_ATT_DATA", "4": "VU_SCLK", "5": "VU_ATT_LE", "13": V3,
              "7": GND, "8": GND, "12": GND, "20": V3, "19": V3, "17": V3, "16": V3, "15": V3, "1": V3,
              "6": V3, "9": V3, "10": GND, "11": GND, "18": GND, "21": GND},
    "U1310": {"3": "VU_IFA_IN", "1": "VU_IFA_OUT", "2": GND, "4": GND},
    "U1314": {"1": "VU_BIAS_IN", "3": "VU_BIAS_EN_N", "5": "VU_ILIM", "6": "VU_BIAS_OUT", "4": "VU_BIAS_FLT_N", "2": GND},
    "JP1301": {"1": V5, "2": "VU_BIAS_IN", "3": V3D},
    "U1313": {"19": "XO_SCL", "20": "XO_SDA", "22": "NC", "24": "VU_EXP_RST", "18": GND,
              "1": "VU_PSA_V1", "2": "VU_PSA_V2", "3": "VU_PSB_V1", "4": "VU_PSB_V2", "5": "VU_PSB_V3",
              "6": "VU_LNA_ON", "7": "VU_CONV_ON", "8": "VU_BIAS_EN_N",
              "10": "VU_BIAS_FLT_N", "11": "VU_ENX", "12": "VU_SCLK", "13": "VU_SDATA", "14": "VU_LD",
              "15": "VU_RESETX", "16": "VU_ATT_LE", "17": "VU_ENBL",
              "23": V3D, "21": V3, "9": GND, "25": GND},
    "U1315": {"1": "VU_LDO_IN", "3": "VU_LDO_IN", "4": "NC", "5": V3, "2": GND},
    "FB1301": {"1": V3D, "2": "VU_LDO_IN"},
}

for _u in ("U1304", "U1305"):
    PINS[_u].update({str(n): GND for n in (1, 2, 3, 4, 6, 7, 9, 10, 12, 13, 15, 21, 23, 24, 25)})

# ---------------------------------------------------------------- two-pin parts: ref -> (part, net 1, net 2)
TWO = {}


def two(ref, part, n1, n2):
    assert ref not in PARTS and ref not in TWO, ref
    PARTS[ref] = part
    TWO[ref] = (n1, n2)


# bias tee and LNA
two("C1301", C("1n", "DC block, antenna side (C0G)"), "VU_ANT", "VU_LNA_SW_IN")
two("L1302", L("56n", "bias-tee choke near the line, LQW15AN56NG (SRF above 1 GHz)"), "VU_ANT", "VU_BIAS_MID")
two("L1301", L("1u", "bias-tee choke, low end, 0805 (> 180 ohm at 30 MHz)", L0805), "VU_BIAS_MID", "VU_BIAS_OUT")
two("C1302", C("1n", "LNA input DC block (also the switch's RF1)"), "VU_LNA_IN_SW", "VU_LNA_IN")
two("C1303", C("1n", "LNA output DC block"), "VU_LNA_OUT", "VU_LNA_OUT_SW")
two("L1303", L("1u", "LNA drain choke, low end (SPF5043Z eval board: 100 nH, here 30 MHz up)", L0603), V3, "VU_LNA_BIAS")
two("L1304", L("56n", "LNA drain choke near the pin"), "VU_LNA_BIAS", "VU_LNA_OUT")
two("C1304", C("100n", "LNA supply"), V3, GND)
two("C1305", C("100p", "LNA supply, RF"), "VU_LNA_BIAS", GND)
for k, u in enumerate(("U1302", "U1303", "U1308", "U1309")):
    two(f"C13{6 + k:02d}", C("100p", f"VDD of {u}"), V3, GND)
two("C1310", C("100p", "VDD of U1304"), V3, GND)
two("C1311", C("100p", "VDD of U1305"), V3, GND)
two("C1312", C("100p", "VDD of U1306"), V3, GND)
two("C1313", C("100p", "VDD of U1307"), V3, GND)

# converter: baluns' AC returns and blocks (data sheet p.13: C23/C24, C20/C21, C6)
two("C1320", C("100p", "mixer input coupling (data sheet C24)"), "VU_MIX_IN_SW", "VU_MIX_IN")
two("C1321", C("100p", "input balun return (C23)"), "VU_MIX_INR", GND)
two("C1322", C("100p", "output balun centre tap decoupling (C6)"), V3, GND)
two("C1323", C("100p", "mixer output coupling (C21)"), "VU_MIX_OUT", "VU_MIX_OUT_SW")
two("C1324", C("100p", "output balun return (C20)"), "VU_MIX_OUTR", GND)
# RFFC5072: reference, control lines, loop filter, supplies
two("C1340", C("1n", "reference AC coupling (C16)"), "VU_TCXO_OUT", "VU_REF")
two("R1340", R("120", "TCXO supply filter (R31)"), V3, "VU_TCXO_VCC")
two("C1341", C("10n", "TCXO supply (C44)"), "VU_TCXO_VCC", GND)
two("R1341", R("10k", "TCXO pin 1: Vcont at mid-scale-high on a VC-TCXO, enable on a standby part, 0.3 mA into a "
                      "plain TCXO's ground pin; safe for every 1XXD variant"), "VU_TCXO_VCC", "VU_TCXO_VC")
two("R1342", R("100k", "ENX high (deselected) until the expander drives it"), V3, "VU_ENX")
two("R1343", R("100k", "ENBL low (converter off) until the expander drives it"), "VU_ENBL", GND)
two("R1344", R("100k", "RESETX high until the expander drives it"), V3, "VU_RESETX")
two("R1345", R("10k", "MODE high: mixer 2 and PLL2 bank under hardware control (software control sets SIPIN)"),
    V3, "VU_MODE")
two("R1346", R("51k", "REXT, 1 % (data sheet note 3)"), "VU_REXT", GND)
for k, (net, why) in enumerate((("VU_RESETX", "C1"), ("VU_ENX", "C13"), ("VU_SCLK", "C14"), ("VU_SDATA", "C15"),
                                ("VU_ENBL", "C35"))):
    two(f"C13{42 + k}", C("33p", f"RC filter on the serial line (data sheet {why}, note 1)"), net, GND)
two("C1347", C("8.2p", "loop filter C8"), "VU_LF1", "VU_LF2")
two("R1347", R("22k", "loop filter R3"), "VU_LF1", "VU_LF_RC")
two("C1348", C("180p", "loop filter C9"), "VU_LF_RC", "VU_LF2")
two("R1348", R("470", "loop filter R2"), "VU_LF2", "VU_LF_M")
two("C1349", C("330p", "loop filter C10"), "VU_LF_M", GND)
two("R1349", R("470", "loop filter R6"), "VU_LF_M", "VU_LF3")
two("C1350", C("330p", "loop filter C17"), "VU_LF3", GND)
for k, (why) in enumerate(("ANA_VDD1", "ANA_VDD1", "ANA_VDD2", "ANA_VDD2", "DIG_VDD", "DIG_VDD")):
    two(f"C13{51 + k}", C("33p" if k % 2 == 0 else "10n", f"{why} decoupling"), V3, GND)
# IF chain
two("C1330", C("1n", "IF amplifier input DC block"), "VU_AA_OUT", "VU_IFA_IN")
two("L1305", L("1u", "IF amplifier drain choke (30-170 MHz only)", L0603), V3, "VU_IFA_OUT")
two("C1331", C("100n", "IF amplifier supply"), V3, GND)
two("C1332", C("1n", "IF amplifier output DC block"), "VU_IFA_OUT", "VU_ATT_IN")
two("R1330", R("10k", "PE4312 DATA: series 10 k at the pin (data sheet Table 2 note 3)"), "VU_SDATA", "VU_ATT_DATA")
two("C1333", C("100n", "PE4312 VDD"), V3, GND)
two("C1334", C("100p", "PE4312 VDD, RF"), V3, GND)
# bias-tee switch
two("C1360", C("1u", "AP22652 input", C0402), "VU_BIAS_IN", GND)
two("C1361", C("100n", "AP22652 output"), "VU_BIAS_OUT", GND)
two("R1360", R("100k", "~EN high: bias off until the expander drives it low"), V3, "VU_BIAS_EN_N")
two("R1361", R("100k", "~FAULT pull-up"), V3, "VU_BIAS_FLT_N")
two("R1362", R("210k", "RLIM: 125 mA typical (95-155), data sheet table, 1 %"), "VU_ILIM", GND)
# expander and LDO
two("R1370", R("10k", "~RESET pull-up to VCCI"), V3D, "VU_EXP_RST")
two("C1370", C("100n", "TCA6416A VCCI"), V3D, GND)
two("C1371", C("100n", "TCA6416A VCCP"), V3, GND)
two("C1380", C("1u", "LP5907 input"), "VU_LDO_IN", GND)
two("C1381", C("1u", "LP5907 output"), V3, GND)
two("C1382", C("100n", "+3V0_RF"), V3, GND)

# ---------------------------------------------------------------- the filters, drawn as ladders
# element: ("sC", ref) shunt C | ("sLC", L, C) shunt series resonator | ("pLC", L, C) shunt parallel resonator
#          ("C", ref) series C | ("LpC", L, C) series L parallel C | ("LsC", L, C) series L then C
LQW = lambda v, n: L(v, n)
FILTERS = {
    "UHF": ("VU_UHF_IN", "VU_UHF_OUT", "UHF image low-pass, 7th-order elliptic, 480 MHz (C0G +-0.1 pF, LQW15AN 2 %)", [
        ("sC", "C1401", "6.2p"), ("LpC", "L1401", "22n", "C1402", "1.8p"), ("sC", "C1403", "6.8p"),
        ("LpC", "L1402", "27n", "C1404", "2p"), ("sC", "C1405", "6.8p"), ("LpC", "L1403", "22n", "C1406", "0.4p"),
        ("sC", "C1407", "1.3p")]),
    "AA": ("VU_AA_IN", "VU_AA_OUT", "Anti-alias low-pass, 7th-order elliptic, 30-170 MHz, >= 55 dB from 230 MHz", [
        ("sC", "C1411", "11p"), ("LpC", "L1411", "56n", "C1412", "5.6p"), ("sC", "C1413", "22p"),
        ("LpC", "L1412", "62n", "C1414", "7.5p"), ("sC", "C1415", "24p"), ("LpC", "L1413", "75n", "C1416", "1.2p"),
        ("sC", "C1417", "20p")]),
    "FMREJ": ("VU_FMREJ_IN", "VU_FMREJ_OUT", "FM-reject high-pass, 9th order, 118-170 MHz pass, >= 40 dB at 87-108 MHz", [
        ("C", "C1421", "18p"), ("sLC", "L1421", "68n", "C1422", "110p"), ("C", "C1423", "13p"),
        ("sLC", "L1422", "82n", "C1424", "36p"), ("C", "C1425", "18p"), ("sLC", "L1423", "100n", "C1426", "24p"),
        ("C", "C1427", "24p"), ("sLC", "L1424", "220n", "C1428", "10p"), ("C", "C1429", "91p")]),
    "FMBP": ("VU_FMBP_IN", "VU_FMBP_OUT", "FM band-pass, 3-pole Butterworth, 84-113 MHz", [
        ("pLC", "L1431", "24n", "C1431", "110p"), ("LsC", "L1432", "560n", "C1432", "4.7p"),
        ("pLC", "L1433", "24n", "C1433", "110p")]),
}


def ind_fp(v):
    n = float(v.rstrip("nu")) * (1000 if v.endswith("u") else 1)
    return L0402 if n <= 100 else (L0603 if n <= 470 else L0805)


for fname, (fin, fout, title, elems) in FILTERS.items():
    node, k = fin, 0
    for e in elems:
        kind = e[0]
        if kind == "sC":
            two(e[1], C(e[2], f"{fname}: shunt"), node, GND)
        elif kind == "sLC":
            mid = f"VU_{fname}_R{k}"
            two(e[1], L(e[2], f"{fname}: shunt resonator", ind_fp(e[2])), node, mid)
            two(e[3], C(e[4], f"{fname}: shunt resonator"), mid, GND)
        elif kind == "pLC":
            two(e[1], L(e[2], f"{fname}: shunt resonator", ind_fp(e[2])), node, GND)
            two(e[3], C(e[4], f"{fname}: shunt resonator"), node, GND)
        else:
            last = e is elems[-1] or all(x[0] in ("sC", "sLC", "pLC") for x in elems[elems.index(e) + 1:])
            nxt = fout if last else f"VU_{fname}_N{k + 1}"
            if kind == "C":
                two(e[1], C(e[2], f"{fname}: series"), node, nxt)
            elif kind == "LpC":
                two(e[1], L(e[2], f"{fname}: series", ind_fp(e[2])), node, nxt)
                two(e[3], C(e[4], f"{fname}: across the series inductor"), node, nxt)
            elif kind == "LsC":
                mid = f"VU_{fname}_S{k}"
                two(e[1], L(e[2], f"{fname}: series resonator", ind_fp(e[2])), node, mid)
                two(e[3], C(e[4], f"{fname}: series resonator"), mid, nxt)
            node, k = nxt, k + 1
    assert node == fout, (fname, node)

for ref, (n1, n2) in TWO.items():
    PINS[ref] = {"1": n1, "2": n2}

HIER = {"XO_SCL": "input", "XO_SDA": "bidirectional", "IF_VU": "output"}
POWER = ["GND", V3, V3D, V5]

NETS, NO_CONNECT = {}, []
for ref, pins in PINS.items():
    for p, net in pins.items():
        if net == "NC":
            NO_CONNECT.append(f"{ref}.{p}")
        else:
            NETS.setdefault(net, []).append(f"{ref}.{p}")
