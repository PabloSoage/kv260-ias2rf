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
  which also limits what an unpowered bridge can draw from the FPGA.

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
    "J1501": ("Connector:USB_C_Receptacle_USB2.0_16P", "HX-TYPE-C 16P 180 LT H10.0", FP + "USB_C_HX_16P_180_LT_H10",
              "Debug USB, vertical, on the IAS0 tongue (inside the box)"),
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
              "B7": "USB_DN", "A8": "NC", "B8": "NC", "SH": "NC"},
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
