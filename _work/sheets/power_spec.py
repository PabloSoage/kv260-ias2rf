"""
POWER sheet - the connection specification. See docs/POWER_SPEC.md.

  12 V jack -> polyfuse -> P-MOSFET (reverse polarity) -> TVS -> +12V
  +12V  -> U1001 LMR33630 buck   -> +5V0     (3 A)
  +5V0  -> U1002 TPS562201 buck  -> +3V3_D
        -> U1003 TPS562201 buck  -> +2V5     (FPGA LVDS banks; feeds +1V8_A)
        -> U1004 TPS562201 buck  -> +1V0     (FPGA VCCINT)
        -> U1007 TPS7A8300 LDO   -> +3V3_A
  +2V5  -> U1005 TPS7A8300 LDO   -> +1V8_A
        -> divider               -> +1V2     (link terminations only)
  +3V3_D-> U1006 TPS7A8300 LDO   -> +1V8_D
        -> U1008 LM2663 inverter -> -3V3     (RF switch VEE)

Every IC circuit is its datasheet's typical application:
  LMR33630   SNVSAN3F Figure 9-1, Table 9-2 (400 kHz, 5 V row)
  TPS562201  SLVSD91D Figure 7-1, Table 7-2 (R2 = 10 k)
  TPS7A8300  SBVS197F Figure 51 (ANY-OUT), Table 2 (pin settings)
  LM2663     SNVS002E Pin Functions (LV, SD) and the 47 uF test capacitors
"""

from kit import R, C, C0805

C1206 = "Capacitor_SMD:C_1206_3216Metric"
C1210 = "Capacitor_SMD:C_1210_3225Metric"

PARTS = {
    # ---- input
    "J1001": ("Connector:Barrel_Jack", "12V IN", "Connector_BarrelJack:BarrelJack_CUI_PJ-102AH_Horizontal",
              "PJ-102AH (ARCHITECTURE BOM, C). Pin 1 centre = +12 V, pin 2 sleeve = GND"),
    "F1001": ("Device:Polyfuse", "PTC 1.5A hold", "Fuse:Fuse_1812_4532Metric",
              "Judgement: input 0.96 A with margin (POWER_AND_STACKUP §1.3); 1.5 A hold. Part to choose"),
    "Q1001": ("Transistor_FET:DMP3013SFV", "DMP3013SFV", "Package_SON:Diodes_PowerDI3333-8",
              "Reverse-polarity protection. Needed Vds >= 30 V, Id >= 3 A, Rds(on) <= 50 mohm. "
              "DMP3013SFV datasheet DS40141 Rev. 5: -30 V, -12 A, 9.5 mohm at -10 V, VGSS +-25 V. "
              "Pins 1-3 S, 4 G, 5 D (pad)"),
    "R1001": R("100k", "Gate pull-down: turns Q1001 on when the input is the right way round"),
    "D1002": ("Device:D_Zener", "15V", "Diode_SMD:D_SOD-123",
              "Gate-source clamp: keeps Vgs inside +-20 V when the TVS clamps near 24 V"),
    "D1001": ("Device:D_TVS", "SMBJ15CA", "Diode_SMD:D_SMB",
              "TVS on +12V (ARCHITECTURE BOM: SMBJ15A). Bidirectional here: KiCad's TVS symbol is. "
              "Standoff 15 V, clamps about 24 V, under the LMR33630's 38 V absolute maximum"),
    "C1001": C("47u 25V", "Judgement: bulk at the input, for the cable's inductance", C1210),

    # ---- +5V0: LMR33630, Table 9-2, 400 kHz, VOUT 5 V
    "U1001": ("kv260-ias2rf:LMR33630ADDA", "LMR33630ADDA",
              "Package_SO:Texas_HSOP-8-1EP_3.9x4.9mm_P1.27mm", "12 V -> 5 V, 3 A, 400 kHz (A version)"),
    "C1002": C("10u 25V", "Table 9-2: CIN 10 uF", C1206),
    "C1003": C("220n 25V", "Table 9-2: CHF 220 nF", "Capacitor_SMD:C_0603_1608Metric"),
    "C1004": C("1u", "Table 9-2 / Pin Functions: CVCC 1 uF"),
    "C1005": C("100n", "Table 9-2 / Pin Functions: CBOOT 100 nF, BOOT to SW"),
    "L1001": ("Device:L", "SRP7028A-8R2M", "Inductor_SMD:L_Bourns_SRP7028A_7.3x6.6mm",
              "Table 9-2: L 8 uH (8.2 uH nearest standard). Isat >= the high-side limit ISC, "
              "5.05 A max. Bourns SRP7028A-8R2M: Isat 7.5 A, Irms 4 A, DCR 68 mohm max"),
    "R1002": R("100k", "Table 9-2: RFBT 100 kohm"),
    "R1003": R("24.9k", "Table 9-2: RFBB 24.9 kohm (VOUT = 1 V x (1 + 100/24.9) = 5.02 V)"),
}
for i in range(4):
    PARTS[f"C{1006 + i}"] = C("22u 10V", "Table 9-2: COUT 4 x 22 uF", C0805)

# ---- TPS562201 bucks from +5V0 (Figure 7-1, Table 7-2)
BUCKS = [  # ref, rail, R1, L, first passive number
    ("U1002", "+3V3_D", "33.2k", "3.3u", 1010),
    ("U1003", "+2V5", "22.6k", "3.3u", 1020),
    ("U1004", "+1V0", "3.09k", "2.2u", 1030),
]
for u, rail, r1, l, b in BUCKS:
    PARTS.update({
        u: ("kv260-ias2rf:TPS562201", "TPS562201", "Package_TO_SOT_SMD:SOT-23-6",
            f"+5V0 -> {rail}, 2 A, 580 kHz"),
        f"C{b}": C("10u 10V", "Figure 7-1 / p.14: input ceramic over 10 uF", C0805),
        f"C{b + 1}": C("100n", "p.14: optional 0.1 uF at pin 3 for high frequency"),
        f"R{b}": R("10k", "Figure 7-1: R3 10 kohm pulls EN up to VIN"),
        f"C{b + 2}": C("100n", "p.14: 0.1 uF from VBST to SW"),
        f"L{b}": ("Device:L", f"SRP7028A-{l[0]}R{l[2]}M", "Inductor_SMD:L_Bourns_SRP7028A_7.3x6.6mm",
                  f"Table 7-2: L1 {l}. Peak current >= 3.5 A (the datasheet's worked example). "
                  "Bourns SRP7028A: 3R3M Isat 12 A / Irms 6 A; 2R2M Isat 14 A / Irms 8 A"),
        f"R{b + 1}": R(r1, f"Table 7-2: R1 for {rail[1:].replace('V', '.').rstrip('_AD.')} V"),
        f"R{b + 2}": R("10k", "Table 7-2: R2 10 kohm"),
        f"C{b + 3}": C("22u 10V", "Figure 7-1: C8 22 uF (20-68 uF, Table 7-2)", C0805),
        f"C{b + 4}": C("22u 10V", "Figure 7-1: C9 22 uF", C0805),
    })

# ---- TPS7A8300 LDOs (Figure 51, ANY-OUT). ref, in, out, grounded program pins, base
LDOS = [
    ("U1005", "+2V5", "+1V8_A", (5, 7, 10), 1040),  # 0.8 + 0.05 + 0.2 + 0.8 = 1.85 V (Table 2): +50 mV for the ~70 mV drop on the way to the ADCs (SIGNAL_INTEGRITY 9.1)
    ("U1006", "+3V3_D", "+1V8_D", (7, 10), 1050),
    ("U1007", "+5V0", "+3V3_A", (6, 10, 11), 1060),  # 0.8 + 0.1 + 0.8 + 1.6 = 3.3 V
]
PROG = (5, 6, 7, 9, 10, 11)
for u, vin, vout, gnd_pins, b in LDOS:
    PARTS.update({
        u: ("kv260-ias2rf:TPS7A8300RGR", "TPS7A8300RGR",
            "Package_DFN_QFN:QFN-20-1EP_3.5x3.5mm_P0.5mm_EP2x2mm", f"{vin} -> {vout}. "
            "RGR 3.5x3.5 mm; check the stock footprint's 2x2 mm pad against the drawing at layout"),
        f"C{b}": C("10u", "Pin Functions: IN 'A 10-uF input ceramic capacitor is required'", C0805),
        f"C{b + 1}": C("10n", "Pin Functions: NR/SS 10 nF recommended for low noise"),
        f"C{b + 2}": C("10n", "Pin Functions: FB 10 nF feed-forward to OUT recommended"),
        f"C{b + 3}": C("22u 10V", "Pin Functions: OUT 'A 22-uF or larger ceramic capacitor is "
                                  "required for stability'", C0805),
    })

# ---- -3V3: LM2663 from +3V3_D
PARTS.update({
    "U1008": ("kv260-ias2rf:LM2663M", "LM2663M", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
              "Inverter, +3V3_D -> about -3.25 V at 8 mA (ROUT 3.5 ohm typ)"),
    "C1070": C("10u", "Judgement: input bypass at V+", C0805),
    "C1071": C("47u", "Electrical Characteristics: C1 = 47 uF, 0.2 ohm max ESR (flying)", C1206),
    "C1072": C("47u", "Electrical Characteristics: C2 = 47 uF, 0.2 ohm max ESR (output)", C1206),
    # ---- +1V2 from +2V5: a divider, the load is only two AC-coupled terminations
    "R1080": R("1.10k 1%", "Divider top: 2.5 V x 1.02 / (1.10 + 1.02) = 1.203 V"),
    "R1081": R("1.02k 1%", "Divider bottom"),
    "C1080": C("1u", "Holds +1V2 at AC; the terminations draw no DC (their pairs are AC-coupled)"),
})

HIER = {}
RAILS = ["+12V", "+5V0", "+3V3_D", "+2V5", "+1V0", "+1V8_A", "+1V8_D", "+3V3_A", "-3V3", "+1V2"]
POWER = RAILS + ["GND"]

NETS = {r: [] for r in POWER}
NETS["GND"] += ["J1001.2", "R1001.2", "D1001.1", "C1001.2",
                "U1001.1", "U1001.9", "C1002.2", "C1003.2", "C1004.2", "R1003.2"] + \
               [f"C{1006 + i}.2" for i in range(4)]
NETS.update({
    "VIN_RAW": ["J1001.1", "F1001.1"],
    "VIN_FUSED": ["F1001.2", "Q1001.5"],
    "GATE": ["Q1001.4", "R1001.1", "D1002.2"],
    "LMR_VCC": ["U1001.6", "C1004.1"],
    "LMR_BOOT": ["U1001.7", "C1005.1"],
    "LMR_SW": ["U1001.8", "C1005.2", "L1001.1"],
    "LMR_FB": ["U1001.5", "R1002.2", "R1003.1"],
})
NETS["+12V"] += ["Q1001.1", "Q1001.2", "Q1001.3", "D1002.1", "D1001.2", "C1001.1", "U1001.2", "U1001.3",
                 "C1002.1", "C1003.1"]
NETS["+5V0"] += ["L1001.2", "R1002.1"] + [f"C{1006 + i}.1" for i in range(4)]
for u, rail, r1, l, b in BUCKS:
    NETS["+5V0"] += [f"{u}.3", f"C{b}.1", f"C{b + 1}.1", f"R{b}.1"]
    NETS["GND"] += [f"{u}.1", f"C{b}.2", f"C{b + 1}.2", f"R{b + 2}.2", f"C{b + 3}.2", f"C{b + 4}.2"]
    NETS[rail] += [f"L{b}.2", f"R{b + 1}.1", f"C{b + 3}.1", f"C{b + 4}.1"]
    NETS.update({
        f"{u}_EN": [f"{u}.5", f"R{b}.2"],
        f"{u}_BST": [f"{u}.6", f"C{b + 2}.1"],
        f"{u}_SW": [f"{u}.2", f"C{b + 2}.2", f"L{b}.1"],
        f"{u}_FB": [f"{u}.4", f"R{b + 1}.2", f"R{b + 2}.1"],
    })
for u, vin, vout, gnd_pins, b in LDOS:
    NETS[vin] += [f"{u}.15", f"{u}.16", f"{u}.17", f"{u}.14", f"C{b}.1"]
    NETS[vout] += [f"{u}.1", f"{u}.19", f"{u}.20", f"{u}.2", f"C{b + 2}.1", f"C{b + 3}.1"]
    NETS["GND"] += [f"{u}.8", f"{u}.18", f"{u}.21", f"C{b}.2", f"C{b + 1}.2", f"C{b + 3}.2"] + \
                   [f"{u}.{p}" for p in gnd_pins]
    NETS[f"{u}_NR"] = [f"{u}.13", f"C{b + 1}.1"]
    NETS[f"{u}_FB"] = [f"{u}.3", f"C{b + 2}.2"]
NETS["+3V3_D"] += ["U1008.8", "C1070.1"]
NETS["GND"] += ["U1008.3", "U1008.1", "U1008.6", "C1070.2", "C1072.2"]
NETS["-3V3"] += ["U1008.5", "C1072.1"]
NETS["LM_CAPP"] = ["U1008.2", "C1071.1"]
NETS["LM_CAPN"] = ["U1008.4", "C1071.2"]
NETS["+2V5"] += ["R1080.1"]
NETS["+1V2"] += ["R1080.2", "R1081.1", "C1080.1"]
NETS["GND"] += ["R1081.2", "C1080.2"]

NO_CONNECT = ["U1001.4", "U1008.7"] + \
    [f"{u}.{p}" for u, _, _, g, _ in LDOS for p in PROG if p not in g] + \
    [f"{u}.{p}" for u, *_ in LDOS for p in (12, 4)]      # BIAS open (VIN >= 1.4 V), PG unused
