"""
KVPWR sheet (Rev08, 19 November): the single power entry. The connection specification; drawn by kvpwr.py through
labdraw.py, checked by _work/check_sheet.py kvpwr. See docs/POWER_SPEC.md section 1.4.

Why: the two boards share their ground through the BM20 contacts of J101/J102, the FFC and the Pmod. With each
board on its own supply, any voltage between the two return points drives a current through those contacts: at the
ISO 16750-2 section 4.8 ground offset of 1 V, 411 mA a contact against a 0.3 A rating
(_work/power/ground_offset.py). Here the adapter feeds the KV260 too, so the module has one supply and one ground.

* L1004, a power common-mode choke (6 A, 600 ohm at 100 MHz, 2 x 8 mOhm), between the 12 V jack J1001 and
  everything else, on both lines: J1001's sleeve reaches the board's ground only through it (net GND_IN).
  The two windings are identical; pads 1-2 carry the ground and 3-4 the supply, so that on the bottom face each
  line faces its own pad of J1001 (pads 1 and 3, the dotted ends, on the jack side).
  Both boards' supply currents pass it, so it sees their difference as differential current only.
* From VIN_J (after the choke, before F1001, so F1001 keeps carrying only the adapter) the KV260 branch:
  Q1010 (the TPS26631's reverse-polarity blocking FET, source on VIN_J), U1010 TPS26631 eFuse, J1004.
  - Current limit 3.0 A (R1043 6.04 k; I = 18 kOhm.A / R, +-7 %, so 2.77 to 3.19 A): the KV260's own 3 A brick
    rating. Nearly all of the KV260's return crosses to the adapter through the inter-board ground (1.3 mOhm against
    the jumper's 33 mOhm), so this limit also caps the BM20 contacts: 132 mA a contact at 3.19 A, 254 mA if one
    contact has half the others' resistance, under the 0.3 A rating (_work/power/ground_offset.py). And
    1.12 + 3.19 A within J1001's 5 A.
  - OVP 14.4 V rising, 13.5 V falling (+-2 %), UVLO 8.0 V: R1040 316 k (at least 300 k between UVLO and IN_SYS with
    reverse polarity, data sheet 8.3.3), R1041 24.9 k, R1042 30.9 k. The KV260 has a 16 V TVS (SMAJ16A) at its
    input and its own eFuse cuts off at 13.2 V (MP5016, XTP682 page 3); the adapter's own input runs to 18.3 V.
  - dVdT 22 nF: 5.5 ms ramp at 12 V. MODE to ground: auto-retry. SHDN open (internally 2.7 V: enabled).
    PGTH to ground (PGOOD unused), IMON and FLT open.
  - D1004 Schottky on the output for the cable's negative kick when the eFuse opens (data sheet 10.2.4).
* J1004, JST VH right angle at the back edge: pin 1 +12V_KV, pin 2 ground. A jumper (VHR-2N, 18 AWG, 5.5 x 2.5 mm
  barrel plug, centre positive) to the KV260's J12, which then has no other supply.
"""

from kit import R, C

FP = "kv260-ias2rf:"
R0603 = "Resistor_SMD:R_0603_1608Metric"
C0603, C1206 = "Capacitor_SMD:C_0603_1608Metric", "Capacitor_SMD:C_1206_3216Metric"
GND = "GND"

PARTS = {
    "L1004": ("Filter:Choke_CommonMode_FerriteCore_1234", "ZEGMCM9070-501T", FP + "CMC_9070_SMD-4P_9.0x7.0mm",
              "Input common-mode choke, both lines: 6 A, 600 ohm at 100 MHz, 2 x 8 mOhm (Coilmaster SMM9070-501 equivalent)"),
    "U1010": ("kv260-ias2rf:TPS26631PWP", "TPS26631PWPR",
              "Package_SO:HTSSOP-20-1EP_4.4x6.5mm_P0.65mm_EP3.4x6.5mm_Mask2.96x2.96mm_ThermalVias",
              "KV260 supply eFuse: OVP 14.4 V, UVLO 8.0 V, current limit 3.0 A, auto-retry, reverse polarity with Q1010"),
    "Q1010": ("kv260-ias2rf:DMT10H015LFG", "DMT10H015LFG", "Package_SON:Diodes_PowerDI3333-8",
              "Reverse-polarity blocking FET for U1010: source on VIN_J, drain on U1010's IN, gate on B_GATE"),
    "Q1011": ("Transistor_FET:Q_NMOS_GSD", "2N7002", "Package_TO_SOT_SMD:SOT-23",
              "Q1010's fast gate pull-down (TI: >= 15 V VDS, VGS 20 V, Ciss <= 50 pF, VGS(th) min <= 3 V)"),
    "D1004": ("Device:D_Schottky", "SS34", "Diode_SMD:D_SMA", "Output Schottky to ground: the cable's negative kick"),
    "J1004": ("Connector_Generic:Conn_01x02", "B2PS-VH", "Connector_JST:JST_VH_B2PS-VH_1x02_P3.96mm_Horizontal",
              "12 V to the KV260's J12 by a jumper: 1 = +12V_KV, 2 = ground. JST VH, right angle, 10 A"),
}

PINS = {
    "L1004": {"1": "GND_IN", "2": GND, "3": "VIN_JACK", "4": "VIN_J"},
    "U1010": {"1": "KV_IN", "2": "KV_IN", "3": "KV_IN", "6": "VIN_J", "4": "KV_BGATE", "5": "KV_DRV",
              "7": "KV_UVLO", "8": "KV_OVP", "13": "NC", "12": GND, "18": "+12V_KV", "19": "+12V_KV", "20": "+12V_KV",
              "17": "NC", "16": GND, "15": "NC", "14": "NC", "11": "KV_ILIM", "10": "KV_DVDT", "9": GND, "21": GND},
    "Q1010": {"1": "VIN_J", "2": "VIN_J", "3": "VIN_J", "4": "KV_BGATE", "5": "KV_IN"},
    "Q1011": {"1": "KV_DRV", "2": "VIN_J", "3": "KV_BGATE"},
    "D1004": {"1": "+12V_KV", "2": GND},
    "J1004": {"1": "+12V_KV", "2": GND},
}
TWO = {}


def two(ref, part, n1, n2):
    assert ref not in PARTS, ref
    PARTS[ref] = part
    PINS[ref] = {"1": n1, "2": n2}


two("R1040", R("316k", "UVLO/OVP divider, top: 8.0 V UVLO, 14.4 V OVP; >= 300 k for reverse polarity", R0603),
    "VIN_J", "KV_UVLO")
two("R1041", R("24.9k", "UVLO/OVP divider, middle", R0603), "KV_UVLO", "KV_OVP")
two("R1042", R("30.9k", "UVLO/OVP divider, bottom", R0603), "KV_OVP", GND)
two("R1043", R("6.04k", "current limit 3.0 A (18 kOhm.A / R)", R0603), "KV_ILIM", GND)
two("C1093", C("22n", "dVdT: 5.5 ms output ramp at 12 V", C0603), "KV_DVDT", GND)
two("C1094", C("1u 100V", "U1010 input, at IN_SYS", C1206), "VIN_J", GND)
two("C1095", C("10u 25V", "+12V_KV at J1004", C1206), "+12V_KV", GND)

FILTERS = {}
HIER = {"VIN_JACK": "input", "GND_IN": "passive", "VIN_J": "output"}
POWER = ["GND"]

NETS, NO_CONNECT = {}, []
for ref, pins in PINS.items():
    for p, net in pins.items():
        if net == "NC":
            NO_CONNECT.append(f"{ref}.{p}")
        else:
            NETS.setdefault(net, []).append(f"{ref}.{p}")
