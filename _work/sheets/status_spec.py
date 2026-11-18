"""
STATUS sheet (Rev08) - the connection specification. See docs/REV08_PLAN.md sections 3.1 and 3.2.

* Eight status LEDs behind a second TCA6416A at 0x21 (ADDR high) on the FPGA's XO_SCL/XO_SDA bus, written on
  change only (never blinked over I2C, plan section 2), plus a heartbeat LED on PMOD_SPARE2, the debug UART's
  transmit line: it flickers with every status line the FPGA prints.
* Five rail LEDs: +12V, +5V0, +3V3_D straight from the rail; +1V8_D and +1V0 switched from +3V3_D by an NPN each,
  since an LED does not light (or barely) at those voltages. About 1 mA each.
* The debug USB bridge: a vertical USB-C (J1501, on the IAS0 tongue), ESD array, CH340X at 3.3 V from the cable
  through its own LP5907-3.3, so it enumerates with the board off. Its TXD reaches PMOD_SPARE1 (an FPGA input)
  through 1 k, so a Kria driving the same line through the Pmod cable wins; PMOD_SPARE2 reaches its RXD through 1 k,
  which also limits what an unpowered bridge can draw from the FPGA. The receptacle is the HRO TYPE-C-31-E-17
  (18 November): surface-mount contacts and shell tabs, plastic pegs 0.7 mm long, so nothing reaches through the
  tongue towards the carrier 0.8 mm below. The first choice, HX-TYPE-C 16P 180 LT H10.0, has four through-hole
  shell legs 2.1 mm long (the maker's drawing), which the tongue cannot take.
* The GPS PPS path to the K26 (INTEGRATIONS 2.1): a JST-SH header for the GPS receiver (3.3 V through a PTC, PPS,
  ground), ESD, a Schmitt buffer, and a 15-way 1 mm FPC receptacle that a short FFC joins to the KV260's J9
  (the Raspberry Pi camera connector), whose pin 12 is HDA10, a PL pin. An FFC's two cable types reverse the pin
  order (n to 16 - n), so the buffer drives both pin 12 and pin 4 through 220 ohm each, and only pins 6, 7, 9 and
  10 are grounded: whichever way the cable maps, pin 12 of J9 gets the pulse, and the other copy lands on a ground
  pin of J9 through 220 ohm (15 mA while the pulse is high). Ground lands on J9's 7 and 10 or 9 and 6; 6 and 9 are
  MIPI receiver pins that the design leaves unused. Pins 11, 13, 14 and 15 of J9 (a reset supervisor, the I2C
  pair, 3.3 V) meet nothing either way.
* The vehicle's CAN bus (18 November, INTEGRATIONS 2.2): the PS's CAN1 controller through EMIO, for R5F core 1.
  Two more J9 lines that the design leaves unused carry it, both in the K26's bank 66 at 1.2 V: pin 6 (DATA1_P) and
  pin 8 (CLK_N). Pin 8 maps to itself with either cable type, so it brings RX in: the TCAN330's RXD through a
  1.8 k / 1 k divider (3.3 V to 1.18 V). TX goes out on J9 pin 6, inverted by the PL; it reaches adapter pin 6 or
  pin 10 depending on the cable, and the other of the two lands on a ground pin of J9 (10 or 6). Each drives one
  NPN (MMBT3904, Q1530 and Q1531) through 2.2 k, with 4.7 k from base to emitter, collectors joined with a 2.2 k pull-up into
  TXD: TXD = NOR(pin 6, pin 10) = TX. An NPN stays off while the K26 is unconfigured, even against a weak
  pull-up, so the bus stays recessive; the TCAN330 also times out a stuck dominant TXD. Pins 6 and 10 are therefore
  no longer grounds; 7 and 9 still are. The bus leaves on J1503, now a 6-way JST-SH shared with the GPS receiver
  (4 CANH, 5 CANL, 6 ground), behind a PESD1CAN. No termination: a tap on a car's bus must not terminate it.

These parts were first planned on the CONTROL sheet; that A1 sheet has no free area large enough to draw them
legibly, so they have their own sheet, joined to CONTROL by PMOD_SPARE1/2 and to CLOCK by XO_SCL/XO_SDA.
Drawn by status.py through labdraw.py from PINS below; checked by _work/check_sheet.py status.
"""

from kit import R, C, C0402

R0402 = "Resistor_SMD:R_0402_1005Metric"
LED0402 = "LED_SMD:LED_0402_1005Metric"
FP = "kv260-ias2rf:"
GND, V3D = "GND", "+3V3_D"


def LED(value, why):
    return ("Device:LED", value, LED0402, why)


PARTS = {
    "U1501": ("kv260-ias2rf:TCA6416ARTW", "TCA6416ARTWR", FP + "WQFN-24_L4.0-W4.0-P0.50-TL-EP2.5",
              "LED expander at 0x21 on XO_SCL/XO_SDA; P00-P07 sink the status LEDs"),
    "J1501": ("Connector:USB_C_Receptacle_USB2.0_16P", "TYPE-C-31-E-17", FP + "USB_C_HRO_TYPE-C-31-E-17",
              "Debug USB, vertical, surface mount only, on the IAS0 tongue (inside the box)"),
    "J1502": ("Connector_Generic_MountingPin:Conn_01x15_MountingPin", "FPC-1.0FX-15PWCR-H20",
              FP + "FPC_1.0_15P_XUNPU_FPC-1.0FX-15PWCR-H20",
              "To KV260 J9 (Raspberry Pi camera connector) by a 15-way 1 mm FFC, 100 mm; J9 pin 12 = HDA10 (PL)"),
    "J1503": ("Connector_Generic_MountingPin:Conn_01x06_MountingPin", "SM06B-SRSS-TB",
              "Connector_JST:JST_SH_SM06B-SRSS-TB_1x06-1MP_P1.00mm_Horizontal",
              "GPS receiver and vehicle CAN: 1 = 3.3 V out, 2 = PPS in, 3 = ground, 4 = CANH, 5 = CANL, 6 = ground"),
    "U1506": ("Interface_CAN_LIN:TCAN330", "TCAN330DCNT", "Package_TO_SOT_SMD:SOT-23-8",
              "Vehicle CAN transceiver, 3.3 V, TXD and RXD dominant time-out; S and SHDN low: normal mode"),
    "Q1530": ("Transistor_BJT:Q_NPN_BEC", "MMBT3904", "Package_TO_SOT_SMD:SOT-23",
              "CAN TX from FPC pin 6; with Q1531 a NOR into TXD (one of pins 6, 10 is a J9 ground)"),
    "Q1531": ("Transistor_BJT:Q_NPN_BEC", "MMBT3904", "Package_TO_SOT_SMD:SOT-23", "CAN TX from FPC pin 10"),
    "D1531": ("Power_Protection:NUP2105L", "PESD1CAN", "Package_TO_SOT_SMD:SOT-23",
              "ESD on CANH and CANL"),
    "U1505": ("74xGxx:74LVC1G17", "SN74LVC1G17DCKR", "Package_TO_SOT_SMD:SOT-353_SC-70-5",
              "PPS Schmitt buffer: drives J9 pin 12 through either cable type"),
    "D1530": ("Device:D_TVS", "PESD5V0F1BL", "Diode_SMD:D_SOD-882", "ESD on the GPS PPS input"),
    "F1501": ("Device:Polyfuse", "PTC 0.2A hold", "Fuse:Fuse_0805_2012Metric",
              "GPS receiver supply from +3V3_D; a shorted cable cannot pull the rail down"),
    "U1503": ("Power_Protection:USBLC6-2SC6", "USBLC6-2SC6", "Package_TO_SOT_SMD:SOT-23-6", "USB ESD"),
    "U1502": ("Interface_USB:CH340X", "CH340X", FP + "MSOP-10_L3.0-W3.0-P0.50-LS5.0-BL", "USB-UART bridge at 3.3 V"),
    "U1504": ("Regulator_Linear:LP5907MFX-3.3", "LP5907MFX-3.3", "Package_TO_SOT_SMD:SOT-23-5",
              "3.3 V for the bridge from the USB cable"),
    "Q1520": ("Transistor_BJT:Q_NPN_BEC", "MMBT3904", "Package_TO_SOT_SMD:SOT-23", "+1V8_D LED switch"),
    "Q1521": ("Transistor_BJT:Q_NPN_BEC", "MMBT3904", "Package_TO_SOT_SMD:SOT-23", "+1V0 LED switch"),
}
STATUS = [("D1501", "CFG", "green", "FPGA configured and the clock sequencer done (xo_boot_done)"),
          ("D1502", "CLK", "yellow", "master clock: on = 500 MHz, off = 400 MHz"),
          ("D1503", "LINK", "green", "IAS1 link trained"),
          ("D1504", "ADCR", "red", "AD9484 clipped since the last read (sticky)"),
          ("D1505", "ADCS", "red", "AD9253 clipped since the last read (sticky)"),
          ("D1506", "LO", "green", "RFFC5072 locked"),
          ("D1507", "TX", "red", "a DAC drives an SMA"),
          ("D1508", "ERR", "red", "sticky error: CRC, FIFO overflow, I2C no-acknowledge, over-temperature")]

PINS = {
    "U1501": {"19": "XO_SCL", "20": "XO_SDA", "22": "NC", "24": "LED_EXP_RST", "18": V3D, "23": V3D, "21": V3D,
              "9": GND, "25": GND, **{str(1 + k): f"LED_{n}_K" for k, (_, n, _, _) in enumerate(STATUS)},
              **{str(10 + k): "NC" for k in range(8)}},
    "J1501": {"A1": GND, "A12": GND, "B1": GND, "B12": GND, "A4": "VBUS_USB", "A9": "VBUS_USB", "B4": "VBUS_USB",
              "B9": "VBUS_USB", "A5": "USB_CC1", "B5": "USB_CC2", "A6": "USB_DP", "B6": "USB_DP", "A7": "USB_DN",
              "B7": "USB_DN", "A8": "NC", "B8": "NC", "SH": GND},
    "J1502": {"12": "J9_PPS12", "4": "J9_PPS4", "6": "J9_CAN_TX6", "10": "J9_CAN_TX10", "8": "J9_CAN_RX",
              "7": GND, "9": GND, "MP": GND, **{str(n): "NC" for n in (1, 2, 3, 5, 11, 13, 14, 15)}},
    "J1503": {"1": "GPS_3V3", "2": "GPS_PPS_IN", "3": GND, "4": "CAN_H", "5": "CAN_L", "6": GND, "MP": GND},
    "U1506": {"1": "CAN_TXD", "2": GND, "3": V3D, "4": "CAN_RXD", "5": GND, "6": "CAN_L", "7": "CAN_H", "8": GND},
    "Q1530": {"1": "CAN_TXB6", "2": GND, "3": "CAN_TXD"},
    "Q1531": {"1": "CAN_TXB10", "2": GND, "3": "CAN_TXD"},
    "D1531": {"1": "CAN_H", "2": "CAN_L", "3": GND},
    "U1505": {"1": "NC", "2": "GPS_PPS_R", "3": GND, "4": "GPS_PPS_Y", "5": V3D},
    "D1530": {"1": "GPS_PPS_IN", "2": GND},
    "F1501": {"1": V3D, "2": "GPS_3V3"},
    "U1503": {"1": "USB_DP", "6": "USB_DP_C", "3": "USB_DN", "4": "USB_DN_C", "5": "VBUS_USB", "2": GND},
    "U1502": {"1": "USB_DP_C", "2": "USB_DN_C", "3": GND, "4": "NC", "5": "NC", "6": "NC", "7": "+3V3_USB",
              "8": "USB_TXD", "9": "USB_RXD", "10": "USB_V3"},
    "U1504": {"1": "VBUS_USB", "3": "VBUS_USB", "4": "NC", "5": "+3V3_USB", "2": GND},
    "Q1520": {"1": "LED_1V8_B", "2": GND, "3": "LED_1V8_K"},
    "Q1521": {"1": "LED_1V0_B", "2": GND, "3": "LED_1V0_K"},
}
TWO = {}


def two(ref, part, n1, n2):
    assert ref not in PARTS, ref
    PARTS[ref] = part
    PINS[ref] = {"1": n1, "2": n2}


two("R1501", R("10k", "~RESET pull-up"), V3D, "LED_EXP_RST")
two("C1501", C("100n", "TCA6416A VCCI"), V3D, GND)
two("C1502", C("100n", "TCA6416A VCCP"), V3D, GND)
for k, (d, n, colour, why) in enumerate(STATUS):
    two(f"R15{11 + k}", R("1k", f"{n} LED, about 1.3 mA"), V3D, f"LED_{n}_A")
    two(d, LED(f"{n} {colour}", why), f"LED_{n}_K", f"LED_{n}_A")          # Device:LED: pin 1 K, pin 2 A
two("R1519", R("1k", "heartbeat LED"), V3D, "LED_HB_A")
two("D1509", LED("HB blue", "heartbeat: on while the debug UART's transmit line is low"), "PMOD_SPARE2", "LED_HB_A")
# rail LEDs
for d, r, rail, rv, n in (("D1520", "R1520", "+12V", "10k", "12V"), ("D1521", "R1521", "+5V0", "3.3k", "5V0"),
                          ("D1522", "R1522", V3D, "1.5k", "3V3")):
    two(r, R(rv, f"{rail} rail LED, about 1 mA"), rail, f"LED_{n}_A")
    two(d, LED(f"{rail} green", f"{rail} present"), GND, f"LED_{n}_A")
for d, r, rb, rail, n in (("D1523", "R1523", "R1525", "+1V8_D", "1V8"), ("D1524", "R1524", "R1526", "+1V0", "1V0")):
    two(r, R("1.5k", f"{rail} rail LED from +3V3_D"), V3D, f"LED_{n}_A")
    two(d, LED(f"{rail} green", f"{rail} present (switched by the NPN)"), f"LED_{n}_K", f"LED_{n}_A")
    two(rb, R("10k", f"base from {rail}: 35-110 uA"), rail, f"LED_{n}_B")
# USB bridge
two("R1531", R("5.1k", "CC1: a sink (UFP)"), "USB_CC1", GND)
two("R1532", R("5.1k", "CC2"), "USB_CC2", GND)
two("R1533", R("1k", "bridge TXD to the FPGA's PMOD_SPARE1; a Kria on the Pmod wins"), "USB_TXD", "PMOD_SPARE1")
two("R1534", R("1k", "FPGA's PMOD_SPARE2 to the bridge's RXD"), "PMOD_SPARE2", "USB_RXD")
two("R1535", R("0", "V3 to VCC: the CH340X at 3.3 V (data sheet); at 5 V this is 100 nF to ground instead"),
    "+3V3_USB", "USB_V3")
two("C1531", C("1u", "LP5907 input"), "VBUS_USB", GND)
two("C1532", C("1u", "LP5907 output"), "+3V3_USB", GND)
two("C1533", C("100n", "CH340X VCC"), "+3V3_USB", GND)
# GPS PPS to KV260 J9
two("R1540", R("100", "PPS input series, with D1530"), "GPS_PPS_IN", "GPS_PPS_R")
two("R1541", R("100k", "holds the buffer low with no receiver"), "GPS_PPS_R", GND)
two("R1542", R("220", "PPS to J1502 pin 12 (J9 pin 12 with a straight cable)"), "GPS_PPS_Y", "J9_PPS12")
two("R1543", R("220", "PPS to J1502 pin 4 (J9 pin 12 with a reversing cable)"), "GPS_PPS_Y", "J9_PPS4")
two("C1540", C("1u", "GPS supply"), "GPS_3V3", GND)
two("C1541", C("100n", "GPS supply"), "GPS_3V3", GND)
two("C1542", C("100n", "U1505 VCC"), V3D, GND)
# vehicle CAN to KV260 J9 (pins 6/10 TX, 8 RX)
two("R1551", R("2.2k", "CAN TX base from FPC pin 6 (J9 pin 6 with a straight cable)"), "J9_CAN_TX6", "CAN_TXB6")
two("R1552", R("2.2k", "CAN TX base from FPC pin 10 (J9 pin 6 with a reversing cable)"), "J9_CAN_TX10", "CAN_TXB10")
two("R1553", R("4.7k", "holds the NPN off while the K26 pin floats or is weakly pulled up"), "CAN_TXB6", GND)
two("R1554", R("4.7k", "holds the NPN off while the K26 pin floats or is weakly pulled up"), "CAN_TXB10", GND)
two("R1555", R("2.2k", "TXD pull-up: recessive unless an NPN conducts"), V3D, "CAN_TXD")
two("R1556", R("1.8k", "RXD divider, top: 3.3 V to 1.18 V for J9's 1.2 V bank"), "CAN_RXD", "J9_CAN_RX")
two("R1557", R("1k", "RXD divider, bottom"), "J9_CAN_RX", GND)
two("C1550", C("100n", "TCAN330 VCC"), V3D, GND)

FILTERS = {}
HIER = {"XO_SCL": "input", "XO_SDA": "bidirectional", "PMOD_SPARE1": "output", "PMOD_SPARE2": "input"}
POWER = ["GND", V3D, "+12V", "+5V0", "+1V8_D", "+1V0", "+3V3_USB", "VBUS_USB"]

NETS, NO_CONNECT = {}, []
for ref, pins in PINS.items():
    for p, net in pins.items():
        if net == "NC":
            NO_CONNECT.append(f"{ref}.{p}")
        else:
            NETS.setdefault(net, []).append(f"{ref}.{p}")
