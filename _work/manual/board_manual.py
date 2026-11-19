"""
The board manual (REV08_PLAN section 11.3): a motherboard-style reference drawn from the final board file.

    python _work/manual/board_manual.py

Reads CSI2-KRIA-KV260_Rev01.kicad_pcb as text (board_parts.py), and writes
  docs/img/manual/board_top.svg|.png, board_bottom.svg|.png   line art with numbered callouts
  docs/BOARD_MANUAL.md                                        the tables, numbered as the drawings
Checks, and exits 1 on any failure: every designator in CATALOG exists on the board with the value written
here; every connector, LED, IC, oscillator, filter, transformer, jumper, switch and test point of the
board is in CATALOG.
"""
import os
import re
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                       # noqa: E402
from matplotlib.patches import Polygon, Rectangle     # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import board_parts                                    # noqa: E402

PCB = os.path.join(ROOT, "CSI2-KRIA-KV260_Rev01.kicad_pcb")
IMG = os.path.join(ROOT, "docs", "img", "manual")
MD = os.path.join(ROOT, "docs", "BOARD_MANUAL.md")

# The parts a reader needs, by group. Each: designator(s), the value on the board, and what it is for.
# A group of several designators gets one callout number (the LED columns, the ESD arrays).
CONNECTORS = [
    ("J101", "BM20B(0.8)-34DP", "IAS1 to the KV260 (its `J8`), underneath: five LVDS pairs at up to 1 Gb/s each (three data lanes, two clocks), the housekeeping I2C (temperature sensor, ID EEPROM) and the FPGA's interrupt. The board's only data link to the Kria"),
    ("J102", "BM20B(0.8)-34DP", "IAS0 to the KV260 (its `J7`), underneath. Every pin is passed through to `J103`; the board uses none"),
    ("J103", "BM20B(0.8)-34DS-0.4V(51)", "IAS0 pass-through receptacle on the tongue's top face, pin for pin with `J102`: an IAS camera module plugs in here as it would on the carrier"),
    ("J401", "CLK_REF_IN", "Reference clock input (SMA) to the ADCLK948, 0.4-3.4 V p-p differential range, 50 ohm on chip. Leave open to run from the on-board Si549"),
    ("J402", "CLK_OUT", "Clock output (SMA), ADCLK948 Q3, LVPECL: to share the master clock with an instrument"),
    ("J911", "SDR_RX_A", "SDR receive A (SMA): through SW1's default throw to the AD9253 channel A. Full scale about -2.4 dBm; DC-blocked"),
    ("J912", "AERIS_IF_A", "Radar IF into the 14-bit AD9253 (SMA), through SW1's second throw"),
    ("J921", "AERIS_IF", "Radar IF from AERIS-10 (SMA): through SW2's default throw to the 500 MSPS AD9484. Full scale about -17.6 dBm"),
    ("J922", "SDR_RX_WB", "Wideband SDR receive (SMA), SW2's second throw. Not connected as built: `C926` is not fitted and the VHF/UHF front end takes the throw (`C927`); swap the two 0402s to use this port"),
    ("J931", "SDR_TX_A", "SDR transmit A (SMA): AD9767 DAC1 through SW3's default throw, 10 mA full scale"),
    ("J932", "AERIS_TX_A", "Radar chirp from the 14-bit AD9767 DAC1 (SMA), SW3's second throw"),
    ("J941", "AERIS_TX", "Radar chirp to AERIS-10 (SMA): the AD9708 through SW4's default throw, 20 mA full scale into a 2:1 balun"),
    ("J942", "SDR_TX_WB", "Wideband SDR transmit from the AD9708 (SMA), SW4's second throw"),
    ("J951", "SDR_RX_C", "HF receive (SMA), no switch: a 30 MHz 7th-order elliptic low-pass, then the AD9253 channel B. Full scale about -3.0 dBm. The default HF input"),
    ("J952", "SDR_TX_C", "HF transmit (SMA), no switch: AD9767 DAC2. The default HF output"),
    ("J961", "VU_ANT", "VHF/UHF antenna (SMA, back wall): the Rev08 front end, direct 30-170 MHz and converted from 300 MHz to 3 GHz (170-300 MHz not covered: the converter's 300 MHz high-pass, AUDIT_Rev08 R1), into the AD9484 through SW2. Bias tee for an active antenna (off at power-up, 5 V or 3.3 V by `JP1301`, 125 mA limit; prefer 3.3 V where the antenna accepts it). Full scale -52 dBm at maximum gain, up to about +2 dBm with the attenuator and the LNA bypassed. No limiter: keep it away from a transmitter on the same vehicle (+25 dBm destroys the LNA)"),
    ("J1001", "12V IN", "12 V input, barrel jack (CUI PJ-102AH, 5 A). Single power entry for both boards (`L1004` on both lines): feeds the adapter (11.7 W typical, 13.4 W / 1.12 A worst; `F1001` 2 A PTC, 18.3 V OVP) and the KV260 via `U1010`/`J1004` (3.0 A / 3.19 A max limit; 1.89 A typical, 4.12 A rated, 4.31 A worst combined). See POWER_SPEC section 1.4 and section 6"),
    ("J1002", "FAN 5V", "Enclosure fan, JST PH 2-pin: pin 1 +5 V (0.5 A PTC `F1002`), pin 2 GND"),
    ("J1004", "B2PS-VH", "12 V output to the KV260's `J12` (JST VH 2-pin right-angle, 10 A: pin 1 `+12V_KV`, pin 2 `GND`): protected by `U1010` (8.0 V UVLO, 14.4 V OVP, 3.0 A limit via `R1043` 6.04 kohm, -60 V reverse); see section 6"),
    ("J1101", "JTAG 2x7 2mm", "Xilinx JTAG for the XC7A50T and its flash (Platform Cable or any 2 mm 14-pin JTAG adapter)"),
    ("J1102", "Pmod", "Pmod from the KV260's `J2` (cable): SPI to the FPGA's register file, beam strobe, PPS and the debug UART. Pin by pin below"),
    ("J1103", "AERIS ADAR", "AERIS-10 beam-steering ribbon (2x20 IDC): the ADAR1000 SPI and its control lines"),
    ("J1201", "HR911130C", "Gigabit Ethernet (RJ45, magnetics and LEDs inside), from the RTL8211FS over SGMII to the FPGA: the board standalone"),
    ("J1501", "TYPE-C-31-E-17", "Debug USB-C (vertical, on the tongue): the FPGA's console through a CH340X, 115,200 baud 8N1, powered from the cable. Lid off"),
    ("J1502", "FPC-1.0FX-15PWCR-H20", "GPS PPS and the vehicle CAN to the KV260's `J9` (Raspberry Pi camera connector) by a 100 mm 15-way 1 mm FFC, either cable type: the pulse reaches `J9` pin 12, a PL pin (`kria_pps`); CAN TX leaves on `J9` pin 6 and RX comes back on pin 8 (PS `CAN1`, R5F core 1)"),
    ("J1503", "BM06B-SRSS-TB", "GPS receiver and vehicle CAN, JST-SH 6-pin, vertical, the plug from above: 1 GND, 2 CANL, 3 CANH, 4 GND, 5 PPS in (3.3 V), 6 +3.3 V out (0.2 A PTC) (no termination: it taps the car's bus)"),
]
SWITCHES = [
    ("SW1101", "PROG", "Pulls the FPGA's PROG_B: reloads the bitstream from the flash"),
    ("JP1101", "WC", "Solder jumper, open as built: close it to allow writing the board-ID EEPROM `U1105`"),
    ("JP1301", "BIAS 5V0 | 3V3", "Solder jumper, bias-tee voltage for `J961`: 1-2 (as built) +5 V, 2-3 +3.3 V. The bias itself is off until the gateware turns it on"),
]
LEDS = [
    ("D1501", "CFG green", "FPGA configured and the clock sequencer finished"),
    ("D1502", "CLK yellow", "Master clock mode: on 500 MHz, off 400 MHz"),
    ("D1503", "LINK green", "IAS1 link to the Kria trained"),
    ("D1504", "ADCR red", "The radar ADC (AD9484) clipped since the last read (sticky)"),
    ("D1505", "ADCS red", "The SDR ADC (AD9253) clipped since the last read (sticky)"),
    ("D1506", "LO green", "The RFFC5072 synthesiser is locked"),
    ("D1507", "TX red", "A DAC is driving an SMA"),
    ("D1508", "ERR red", "Any sticky error: CRC, FIFO overflow, I2C no-acknowledge, over-temperature"),
    ("D1509", "HB blue", "Heartbeat: flickers with every line the FPGA prints on the debug UART, once a second"),
    ("D1520", "+12V green", "+12V present (after the input protection)"),
    ("D1521", "+5V0 green", "+5V0 present"),
    ("D1522", "+3V3_D green", "+3V3_D present"),
    ("D1523", "+1V8_D green", "+1V8_D present (switched from +3V3_D by `Q1520`)"),
    ("D1524", "+1V0 green", "+1V0 (FPGA core) present (switched from +3V3_D by `Q1521`)"),
    ("D1101", "green", "DONE: the FPGA has loaded a bitstream"),
]
LED_GROUPS = {"Status LEDs": ["D1501", "D1502", "D1503", "D1504", "D1505", "D1506", "D1507", "D1508", "D1509"],
              "Rail LEDs": ["D1520", "D1521", "D1522", "D1523", "D1524"], "DONE": ["D1101"]}
ICS = [
    ("U1101", "XC7A50T-2FTG256I", "CONTROL", "The front-end FPGA: converters, RF switches, link to the Kria, Ethernet, housekeeping"),
    ("U1102", "MT25QL128ABA1ESE", "CONTROL", "128 Mbit SPI flash: the FPGA's bitstream"),
    ("U1103", "74LVC1G07", "CONTROL", "Open-drain buffer on the FPGA's PROG_B"),
    ("U1104", "TMP1075DR", "CONTROL", "Board temperature sensor, I2C 0x48"),
    ("U1105", "M24C02-FMN6TP", "CONTROL", "Board-ID EEPROM (revision, serial), I2C 0x50, write-protected unless `JP1101` is closed"),
    ("U1108", "TPD4E05U06DQAR", "CONTROL", "ESD array on the Pmod lines"),
    ("U1109", "TPD4E05U06DQAR", "CONTROL", "ESD array on the Pmod lines"),
    ("U1110", "TPD4E05U06DQAR", "CONTROL", "ESD array on the JTAG lines"),
    ("U1201", "RTL8211FSI-CG", "CONTROL", "Gigabit Ethernet PHY, SGMII to the FPGA"),
    ("U401", "ADCLK948BCPZ", "CLOCK", "Clock fan-out: the converters' and the FPGA's clocks from the Si549 or `J401`"),
    ("U501", "AD9484BCPZ-500", "ADC_RADAR", "8-bit 500 MSPS ADC: the radar IF, the wideband SDR and the VHF/UHF front end"),
    ("U502", "AD8352ACPZ", "ADC_RADAR", "Differential driver for the AD9484, first stage"),
    ("U503", "AD8352ACPZ", "ADC_RADAR", "Differential driver for the AD9484, second stage"),
    ("U601", "AD9253BCPZ-125", "ADC_SDR", "14-bit quad ADC, two channels used: SDR receive A and HF (C)"),
    ("U602", "AD8352ACPZ", "ADC_SDR", "Driver for the AD9253 channel A"),
    ("U603", "AD8352ACPZ", "ADC_SDR", "Driver for the AD9253 channel B (HF)"),
    ("U701", "AD9708AR", "DAC_RADAR", "8-bit 125 MSPS DAC: the radar chirp"),
    ("U801", "AD9767ASTZ", "DAC_SDR", "Dual 14-bit 125 MSPS DAC: SDR transmit A and HF"),
    ("U901", "M3SWA2-34DR+", "ROUTING", "SW1: SDR_RX_A or AERIS_IF_A to the AD9253 channel A"),
    ("U902", "M3SWA2-34DR+", "ROUTING", "SW2: AERIS_IF or the VHF/UHF front end to the AD9484"),
    ("U903", "M3SWA2-34DR+", "ROUTING", "SW3: the AD9767 DAC1 to SDR_TX_A or AERIS_TX_A"),
    ("U904", "M3SWA2-34DR+", "ROUTING", "SW4: the AD9708 to AERIS_TX or SDR_TX_WB"),
    ("U1001", "LMR33630ADDA", "POWER", "+12V to +5V0 buck, 3 A"),
    ("U1002", "TPS563201", "POWER", "+5V0 to +3V3_D buck, 3 A (Rev08 audit, P5)"),
    ("U1003", "TPS562201", "POWER", "+5V0 to +2V5 buck (FPGA LVDS banks, feeds +1V8_A)"),
    ("U1004", "TPS562201", "POWER", "+5V0 to +1V0 buck (FPGA core)"),
    ("U1005", "TPS7A8300RGR", "POWER", "+2V5 to +1V8_A LDO (the ADCs' analogue supply)"),
    ("U1006", "TPS7A8300RGR", "POWER", "+3V3_D to +1V8_D LDO (FPGA VCCAUX, the ADCs' outputs)"),
    ("U1007", "TPS7A8300RGR", "POWER", "+5V0 to +3V3_A LDO (the DACs' analogue supply)"),
    ("U1008", "LM2663M", "POWER", "-3V3 charge pump (the RF switches' negative supply)"),
    ("U1009", "LM74502-Q1", "POWER", "Input protection controller: reverse battery and over-voltage cut-off, with `Q1001`/`Q1003`"),
    ("U1010", "TPS26631PWPR", "KVPWR", "KV260 12 V output eFuse: 8.0 V UVLO, 14.4 V OVP, 3.0 A limit (`R1043` 6.04 kohm, 2.77 to 3.19 A), auto-retry, with `Q1010`/`Q1011` reverse protection"),
    ("U1301", "SPF5043Z", "RX_VU", "VHF/UHF low-noise amplifier"),
    ("U1302", "PE4259", "RX_VU", "LNA bypass switch, input side"),
    ("U1303", "PE4259", "RX_VU", "LNA bypass switch, output side"),
    ("U1304", "PE42442", "RX_VU", "Preselector A: band selection, input side"),
    ("U1305", "PE42442", "RX_VU", "Preselector A: band selection, output side"),
    ("U1306", "SKY13418-485LF", "RX_VU", "Preselector B, input side (straight, UHF low-pass, ADS-B)"),
    ("U1307", "SKY13418-485LF", "RX_VU", "Preselector B, output side"),
    ("U1308", "PE4259", "RX_VU", "Direct or converted path"),
    ("U1309", "PE4259", "RX_VU", "Direct or converted path, after the converter"),
    ("U1310", "SPF5043Z", "RX_VU", "IF amplifier"),
    ("U1311", "PE4312", "RX_VU", "Digital attenuator, 0-31.5 dB"),
    ("U1312", "RFFC5072", "RX_VU", "Synthesiser and mixer: converts 300 MHz-3 GHz down to the IF (170-300 MHz not covered)"),
    ("U1313", "TCA6416ARTWR", "RX_VU", "I/O expander 0x20: the front end's switches, bias tee and converter control"),
    ("U1314", "AP22652W6-7", "RX_VU", "Bias-tee current limiter for `J961` (125 mA)"),
    ("U1315", "LP5907MFX-2.8", "RX_VU", "+2V8_RF LDO for the front end (Rev08 audit, P8)"),
    ("U1501", "TCA6416ARTWR", "STATUS", "I/O expander 0x21: the status LEDs"),
    ("U1502", "CH340X", "STATUS", "USB to UART bridge for the debug console"),
    ("U1503", "USBLC6-2SC6", "STATUS", "ESD on the USB data lines"),
    ("U1504", "LP5907MFX-3.3", "STATUS", "3.3 V LDO for the USB bridge, from the cable"),
    ("U1505", "SN74LVC1G17DCKR", "STATUS", "GPS PPS Schmitt buffer, drives `J1502` pins 12 and 4"),
    ("U1506", "TCAN3403DDFRQ1", "STATUS", "Vehicle CAN transceiver on `J1503` pins 3 and 2, listen-only by default; TXD from the NOR pair `Q1530`/`Q1531`, RXD divided to 1.2 V for `J9` pin 8"),
]
OTHER = [   # oscillators, filters, transformers: in the chip table, one line each
    ("Y401", "Si549 LVPECL 3V3 pinout C", "CLOCK", "Programmable master oscillator, 400 or 500 MHz"),
    ("Y1201", "25MHz", "CONTROL", "Crystal for the Ethernet PHY"),
    ("Y1301", "26MHz 1XXD26000MAA", "RX_VU", "TCXO, the RFFC5072's reference"),
    ("FL1301", "TA1090EC", "RX_VU", "1090 MHz SAW filter (ADS-B path)"),
    ("FL1302", "HFCN-1000+", "RX_VU", "High-pass after the mixer"),
    ("FL1303", "LFCN-1000+", "RX_VU", "Low-pass, UHF preselector"),
    ("T701", "ADT2-1T+", "DAC_RADAR", "AD9708 output balun"),
    ("T801", "ADT2-1T+", "DAC_SDR", "AD9767 DAC1 output balun"),
    ("T802", "ADT2-1T+", "DAC_SDR", "AD9767 DAC2 output balun"),
    ("T1301", "TC1-1-13M+", "RX_VU", "Mixer input balun"),
    ("T1302", "TC4-1W+", "RX_VU", "Mixer output balun"),
]
PMOD = [  # J1102 pin, net, direction (seen from the board), use
    (1, "PMOD_CS", "in", "SPI chip select of the FPGA's register file"),
    (2, "BEAM_STROBE", "in", "Applies the loaded beam on every ADAR1000 at once (R5F core 1 drives it in scan mode)"),
    (3, "PMOD_MOSI", "in", "SPI data to the FPGA"),
    (4, "PPS_SYNC", "in", "GPS PPS, to time-stamp detections"),
    (5, "PMOD_MISO", "out", "SPI data from the FPGA"),
    (6, "PMOD_SPARE1", "in", "Debug UART, Kria to FPGA (PS UART1 TX); the USB bridge also drives it through 1 kohm"),
    (7, "PMOD_SCLK", "in", "SPI clock"),
    (8, "PMOD_SPARE2", "out", "Debug UART, FPGA to Kria (PS UART1 RX); also lights the heartbeat LED"),
    ("9, 10", "GND", "", ""),
    ("11, 12", "not connected", "", "The board takes no power from the Pmod"),
]
TESTPOINTS = ["TP1", "TP2", "TP3", "TP4", "TP5", "TP6", "TP7", "TP8", "TP9", "TP10", "TP11", "TP12", "TP13", "TP14", "TP15"]
CHECKED = ("J", "U", "Y", "FL", "T", "JP", "SW", "TP")   # every such part must be catalogued; D: only LEDs

TROUBLE = [
    ("No LED at all", "No 12 V, or the input protection is off: input below about 6 V, above 18.3 V, or reversed. Check `J1001`, `F1001`"),
    ("`+12V` on, `+5V0` off", "`U1001` or its load: measure `TP1`; a short on +5V0 holds the buck in hiccup"),
    ("`+5V0` on, `+3V3_D` off", "`U1002`; every other rail after it stays off too"),
    ("`+1V8_D` or `+1V0` off, `+3V3_D` on", "`U1006` (+1V8_D) or `U1004` (+1V0); `TP5`, `TP8`"),
    ("Rails on, DONE off", "No bitstream: the flash is empty or the load failed. Program it through `J1101`, or press `SW1101`"),
    ("DONE on, CFG off", "The clock sequencer did not finish: the Si549 did not answer on I2C, or `J401`'s reference is out of range"),
    ("CFG on, LINK off", "The Kria has not trained IAS1: its bitstream or `kria_pl_link` is not running, or `J101` is not seated"),
    ("HB not flickering", "The FPGA's status task has stopped, or the debug UART is held by the Kria (`PMOD_SPARE2`)"),
    ("LO off", "The RFFC5072 is unlocked: only the converted VHF/UHF modes are affected"),
    ("ADCR or ADCS on", "A converter clipped: lower the input (or the front end's gain); the LED clears when read"),
    ("ERR on", "Read the error register over the console (`r` command) to see which: CRC, FIFO, I2C or temperature"),
]
USES = [
    ("Radar with AERIS-10", "Ribbon on `J1103`; chirp `J941` to AERIS's transmit input, AERIS's IF to `J921`; IAS1 on the KV260; 12 V on `J1001`", "Default switch positions. The Kria runs the radar pipeline; R5F core 1 scans the beams"),
    ("HF SDR", "Antenna or HF front end on `J951`; transmit from `J952`", "No switch in either path; 0-30 MHz, the 30 MHz low-pass on receive"),
    ("VHF/UHF reception", "Antenna on `J961` (active antenna: set `JP1301`, then the bias on in software)", "SW2 to its second throw (the front end); band and gain from the Kria"),
    ("SDR on the 14-bit converters", "`J911` receive, `J931` transmit", "Default positions of SW1 and SW3"),
    ("Wideband SDR", "`J942` transmit; `J922` receive only after swapping `C926`/`C927`", "SW4 to its second throw"),
    ("Camera on the KV260", "IAS camera module on `J103`, as on the carrier's `J7`", "Nothing on this board; the camera talks to the SOM as before"),
    ("Standalone over Ethernet", "RJ45 `J1201` to a PC; 12 V on `J1001`", "The FPGA streams over UDP without the Kria"),
    ("Debug", "USB-C `J1501` (lid off), 115,200 8N1; JTAG `J1101`", "Boot banner, one status line a second, `r`/`w` register commands"),
    ("GPS time", "GPS receiver on `J1503`; FFC from `J1502` to the KV260's `J9`", "`kria_pps` timestamps the pulse; R5F core 0 disciplines the converters' clock to it"),
]


def callouts():
    """[(number, label, [refs], side-of-first-ref)] in table order."""
    out, n = [], 0
    for ref, _, _ in CONNECTORS + SWITCHES:
        n += 1
        out.append((n, ref, [ref]))
    for name, refs in LED_GROUPS.items():
        n += 1
        out.append((n, name, refs))
    for ref, _, _, _ in ICS + OTHER:
        n += 1
        out.append((n, ref, [ref]))
    return out


def check(parts):
    by = {p.ref: p for p in parts}
    bad = []
    for ref, val, *_ in CONNECTORS + SWITCHES + LEDS + [(r, v) for r, v, _, _ in ICS + OTHER]:
        if ref not in by:
            bad.append(f"{ref}: not on the board")
        elif by[ref].value != val:
            bad.append(f"{ref}: value on the board {by[ref].value!r}, here {val!r}")
    listed = {r for r, *_ in CONNECTORS + SWITCHES + LEDS} | {r for r, *_ in ICS + OTHER} | set(TESTPOINTS)
    for p in parts:
        pre = re.match(r"[A-Z]+", p.ref).group(0)
        is_led = pre == "D" and p.footprint.startswith("LED")
        if (pre in CHECKED or is_led) and p.ref not in listed:
            bad.append(f"{p.ref} ({p.value}): on the board, not in the manual")
    for ref in TESTPOINTS:
        if ref not in by:
            bad.append(f"{ref}: not on the board")
    return bad


# ---------------------------------------------------------------- drawing
INSET = (88.0, 88.0, 152.0, 130.0)     # the dense corner (front end, status, tongue), drawn again at a larger scale


def draw(parts, edge, side, nums):
    on = [p for p in parts if p.side == side]
    mirror = side == "bottom"
    fx = (lambda x: -x) if mirror else (lambda x: x)
    fig = plt.figure(figsize=(16, 10.5))
    ax = fig.add_axes([0.01, 0.02, 0.56, 0.93])
    ai = fig.add_axes([0.58, 0.30, 0.41, 0.65])
    for a, fs in ((ax, 6.0), (ai, 7.5)):
        for seg in edge:
            a.plot([fx(x) for x, _ in seg], [y for _, y in seg], color="#1f3b57", lw=1.2)
        for p in on:
            key = p.ref in nums
            a.add_patch(Polygon([(fx(x), y) for x, y in p.poly], closed=True,
                                fc="#d6e6f2" if key else "none", ec="#33658a" if key else "#b8c4cc",
                                lw=0.6 if key else 0.3))
        by = {p.ref: p for p in on}
        for n, label, refs in callouts():
            ps = [by[r] for r in refs if r in by]
            if not ps:
                continue
            x = sum(p.x for p in ps) / len(ps)
            y = sum(p.y for p in ps) / len(ps)
            if len(ps) > 1:                    # a group: one frame round all of it, one number beside it
                xs = [q[0] for p in ps for q in p.poly]
                ys = [q[1] for p in ps for q in p.poly]
                a.add_patch(Rectangle((min(fx(min(xs)), fx(max(xs))) - 0.4, min(ys) - 0.4), max(xs) - min(xs) + 0.8,
                                      max(ys) - min(ys) + 0.8, fill=False, ec="#33658a", lw=0.8))
                if max(ys) - min(ys) > max(xs) - min(xs):      # a column: the number to its right
                    x = (max(xs) + 1.6) if not mirror else (min(xs) - 1.6)
                else:                                          # a row: the number above it
                    y = min(ys) - 1.6
            inside = INSET[0] <= x <= INSET[2] and INSET[1] <= y <= INSET[3]
            if a is ax and inside:
                continue                       # numbered in the inset instead
            if a is ai and not inside:
                continue
            a.text(fx(x), y, str(n), ha="center", va="center", fontsize=fs, color="#102a43",
                   fontweight="bold", bbox=dict(boxstyle="round,pad=0.12", fc="white", ec="#33658a", lw=0.4))
        a.set_aspect("equal")
        a.invert_yaxis()
        a.axis("off")
    xs = [fx(x) for seg in edge for x, _ in seg]
    ys = [y for seg in edge for _, y in seg]
    ax.set_xlim(min(xs) - 2, max(xs) + 2)
    ax.set_ylim(max(ys) + 2, min(ys) - 2)
    x0, y0, x1, y1 = INSET
    ai.set_xlim(min(fx(x0), fx(x1)), max(fx(x0), fx(x1)))
    ai.set_ylim(y1, y0)
    ax.add_patch(Rectangle((min(fx(x0), fx(x1)), y0), x1 - x0, y1 - y0, fill=False, ec="#c0392b", lw=1.0, ls="--"))
    for s in ai.spines.values():
        s.set_visible(True)
        s.set_edgecolor("#c0392b")
    ai.axis("on")
    ai.set_xticks([])
    ai.set_yticks([])
    title = ("Top side" if side == "top" else "Bottom side, seen from below (mirrored)")
    fig.text(0.01, 0.975, f"KV260-IAS2RF Rev08, {title}", fontsize=14, fontweight="bold", color="#102a43")
    fig.text(0.58, 0.27, "Inset (red frame): the VHF/UHF front end, the status LEDs and the tongue", fontsize=9,
             color="#c0392b")
    fig.text(0.58, 0.24, "Numbers: the tables of docs/BOARD_MANUAL.md. Shaded: the parts the tables describe.",
             fontsize=9, color="#334e68")
    fig.text(0.58, 0.21, "Drawn by _work/manual/board_manual.py from CSI2-KRIA-KV260_Rev01.kicad_pcb.",
             fontsize=9, color="#334e68")
    os.makedirs(IMG, exist_ok=True)
    for ext in ("svg", "png"):
        fig.savefig(os.path.join(IMG, f"board_{side}.{ext}"), dpi=200 if ext == "png" else None, facecolor="white")
    plt.close(fig)


# ---------------------------------------------------------------- the document
def md(parts, nums):
    by = {p.ref: p for p in parts}
    side = lambda r: by[r].side                                       # noqa: E731
    L = []
    w = L.append
    w("# Board manual")
    w("")
    w("What every connector, LED, switch and chip on the KV260-IAS2RF Rev08 board is for, so that the board can be "
      "used without the schematic. The drawings and the tables are generated together from the board file by "
      "`_work/manual/board_manual.py`, which also checks that every connector, LED and IC on the board is listed "
      "and that every listed part is on the board.")
    w("")
    w("![Top side](img/manual/board_top.png)")
    w("")
    w("![Bottom side](img/manual/board_bottom.png)")
    w("")
    w("For orientation, the rendered board: [top](img/board_top.png), [bottom](img/board_bottom.png), "
      "[iso](img/board_iso.png). Vector drawings: [top](img/manual/board_top.svg), "
      "[bottom](img/manual/board_bottom.svg).")
    w("")
    w("## 1. Connectors")
    w("")
    w("The thirteen SMAs are on the front edge (`J401`-`J952`) and the back wall (`J961`). Every RF port is "
      "DC-blocked except `J961` when its bias tee is on.")
    w("")
    w("| No. | Ref | Side | Name | What it is for |")
    w("|---|---|---|---|---|")
    for ref, val, what in CONNECTORS:
        w(f"| {nums[ref]} | `{ref}` | {side(ref)} | {val} | {what} |")
    w("")
    w("### 1.1 Pmod `J1102`")
    w("")
    w("A Pmod cable from the KV260's `J2`. 3.3 V signals into the FPGA's bank 15, ESD-protected by `U1108`/`U1109`.")
    w("")
    w("| Pin | Net | Direction | Use |")
    w("|---|---|---|---|")
    for pin, net, d, use in PMOD:
        w(f"| {pin} | `{net}` | {d} | {use} |")
    w("")
    w("### 1.2 Test points")
    w("")
    w("| Ref | Net | Ref | Net | Ref | Net |")
    w("|---|---|---|---|---|---|")
    tps = [(r, by[r].value) for r in TESTPOINTS]
    for k in range(0, len(tps), 3):
        row = tps[k:k + 3] + [("", "")] * (3 - len(tps[k:k + 3]))
        w("| " + " | ".join(f"`{r}` | `{v}`" if r else " | " for r, v in row) + " |")
    w("")
    w("## 2. Switches and jumpers")
    w("")
    w("| No. | Ref | Side | Name | What it does |")
    w("|---|---|---|---|---|")
    for ref, val, what in SWITCHES:
        w(f"| {nums[ref]} | `{ref}` | {side(ref)} | {val} | {what} |")
    w("")
    w("**Assembly options.** `C926`/`C927` choose what SW2's second throw reaches: as built `C927` is fitted (the "
      "VHF/UHF front end) and `C926` is not (`J922`). The Ethernet parts (`U1201`, `J1201`, `Y1201`) can be left "
      "off the BOM for a board that only runs with the Kria. The master clock mode (400 or 500 MHz) has no jumper: "
      "the FPGA programs the Si549 over I2C.")
    w("")
    w("**The RF switches**, set by the FPGA's register file (`SW_CTRL0-3`); pulled to the default while the FPGA "
      "is unconfigured:")
    w("")
    w("| Switch | Default (RF1) | Second throw (RF2) |")
    w("|---|---|---|")
    w("| SW1 `U901`, AD9253 channel A | `J911` SDR_RX_A | `J912` AERIS_IF_A |")
    w("| SW2 `U902`, AD9484 | `J921` AERIS_IF | The VHF/UHF front end (`J922` with `C926` fitted) |")
    w("| SW3 `U903`, AD9767 DAC1 | `J931` SDR_TX_A | `J932` AERIS_TX_A |")
    w("| SW4 `U904`, AD9708 | `J941` AERIS_TX | `J942` SDR_TX_WB |")
    w("")
    w("## 3. LEDs")
    w("")
    w("The nine status LEDs stand in a column beside `J961`, seen through a window in the lid. The rail LEDs are on "
      "the tongue: each one is lit by its rail, so a dead rail shows without a meter.")
    w("")
    w("| No. | Ref | Side | Colour | Meaning when lit |")
    w("|---|---|---|---|---|")
    for name, refs in LED_GROUPS.items():
        for ref in refs:
            val, what = next((v, t) for r, v, t in LEDS if r == ref)
            w(f"| {nums[name]} | `{ref}` | {side(ref)} | {val} | {what} |")
    w("")
    w("**At power-up**, in order: the five rail LEDs; DONE when the FPGA has loaded its bitstream; CFG when the "
      "clocks are running; HB flickering once a second; LINK when the Kria has trained IAS1. The RJ45's own two "
      "LEDs show the Ethernet link and activity.")
    w("")
    w("| What you see | What it means, what to check |")
    w("|---|---|")
    for a, b in TROUBLE:
        w(f"| {a} | {b} |")
    w("")
    w("## 4. Chips")
    w("")
    w("| No. | Ref | Side | Part | Sheet | Function |")
    w("|---|---|---|---|---|---|")
    for ref, val, sheet, what in ICS + OTHER:
        w(f"| {nums[ref]} | `{ref}` | {side(ref)} | {val} | {sheet} | {what} |")
    w("")
    w("## 5. Typical uses")
    w("")
    w("| Use | Connect | Set |")
    w("|---|---|---|")
    for a, b, c in USES:
        w(f"| {a} | {b} | {c} |")
    w("")
    w("## 6. Powering the KV260 together with the board")
    w("")
    w("![Power and grounding wiring](img/power_wiring.png)")
    w("")
    w("![Ground offset and earth loops](sim/ground_offset.png)")
    w("")
    w("Feed the entire two-board module through `J1001` alone. Connect `J1004` (right-angle JST VH at the back edge; "
      "pin 1 `+12V_KV`, pin 2 `GND`) to the KV260's barrel jack `J12` with the short 18 AWG jumper (VHR-2N, 15 cm to a "
      "5.5 x 2.5 mm centre-positive plug) and **plug nothing else into `J12`**. Combined draw at `J1001` (5 A rating) and "
      "`L1004` (6 A rating) is 1.89 A typical, 4.12 A at the KV260's 3.0 A brick rating (1.12 A adapter plus 3.0 A KV260), "
      "and 4.31 A worst case at `U1010`'s +7 % limit (3.19 A from `R1043` 6.04 kohm).")
    w("")
    w("With this single entry, **the KV260's own DC return runs through the BM20 ground contacts (`J101`/`J102`) by design**: "
      "the 22 parallel BM20 ground contacts plus the FFC and Pmod conductors present 1.3 mOhm (1.29 mOhm) against the jumper's "
      "33 mOhm (33.1 mOhm), so 96 % of the KV260's return crosses the BM20 link. That is why `U1010` limits the KV260 to its "
      "brick's 3 A rating (2.98 A nominal, 2.77 to 3.19 A).")
    w("")
    w("- In a vehicle:")
    w("  - **Feed `J1001` from a 4.3 to 36 V automotive buck-boost converter (12.0 V +-2 % strictly below 13.2 V, >= 5 A / 60 W) "
      "with an upstream 36 V Load Dump A (87 V) surge limiter and a 5 A inline fuse to `J1001`** (plus a 15 to 20 A fuse on the "
      "battery feed; never fit a 13.6 V stabiliser, which trips the KV260's `MP5016H` OVP). With that converter in place, only "
      "disconnecting the battery (`ISO 7637-2` pulse 1, 200 ms off), prolonged -14 V reverse battery, or extreme 3.0 V cranking "
      "still resets the module (`POWER_SPEC` §1.4).")
    w("  - **Never run a second chassis ground wire to the KV260** (by wire, mounting strap or shield); both boards return "
      "through `J1001` alone. Return the CAN/GPS cable ground (`J1503` pins 1 and 4) from the same chassis ground point as the "
      "DC-DC converter's negative lead.")
    w("- At home / on a bench:")
    w("  - Use one 12 V / 5 A wall adapter on `J1001`, preferably a two-prong (Class II, double-insulated) brick with no mains "
      "earth pin.")
    w("  - Ethernet on `J1201` to an earthed PC or switch no longer closes a DC or 50 Hz earth loop (`J1201`'s shield goes to "
      "ground through `R1218` 1 Mohm in parallel with `C1223` 1 nF 2 kV).")
    w("  - **USB does close a ground loop** (its ground is a cable conductor): when connecting the debug USB-C `J1501` or the "
      "KV260's USB to an earthed PC while running an earthed supply, use a USB isolator or a laptop on battery.")
    w("  - DisplayPort to an earthed monitor stays a loop (189 mA per BM20 contact with 1 V rms 50 Hz between earths, inside "
      "the 300 mA rating); fit clip-on ferrites on earthed cables.")
    w("")
    w("Inter-board BM20 ground currents (`_work/power/ground_offset.py`, `docs/sim/ground_offset.json`, 0.30 A per-contact rating):")
    w("")
    w("| Installation / Fault case | Inter-board link current | Per BM20 contact | Against 0.30 A rating |")
    w("|---|---|---|---|")
    w("| Separate grounds, same point (1.0 m / 1.0 m) | -0.93 A | 40 mA | Pass |")
    w("| Separate grounds, same point (0.3 m / 2.0 m) | -1.96 A | 84 mA | Pass |")
    w("| Separate grounds, 1.0 V chassis offset (1 m typ) | 10.2 A | 411 mA | Fail (exceeds 0.30 A from 0.75 V) |")
    w("| Separate grounds, 1.0 V offset (1 m, max contact R) | 9.9 A | 355 mA | Fail (exceeds 0.30 A from 0.85 V) |")
    w("| Separate grounds, 1.0 V offset (0.3 m leads, typ) | 17.7 A | 714 mA | Fail (exceeds 0.30 A from 0.40 V) |")
    w("| Separate grounds, 1.0 V offset (3.0 m leads, typ) | 5.0 A | 203 mA | Pass (0.30 A at 1.60 V) |")
    w("| Separate grounds, KV260 ground wire lost | 3.00 A | 129 mA | Pass (surviving jack 4.12 A) |")
    w("| Single entry, typical KV260 load (0.92 A) | -0.89 A | 38 mA | Pass |")
    w("| Single entry, at `U1010` limit (3.19 A) | -3.09 A | 132 mA | Pass (independent of chassis offset) |")
    w("| Single entry, contacts at 100 mOhm max | -2.88 A | 109 mA | Pass |")
    w("| Single entry, one contact at half resistance (3.19 A / 0.92 A) | -3.09 A / -0.89 A | 254 mA / 73 mA | Pass |")
    w("| Single entry, one contact at a third of the others' resistance (2 A) | | 219 mA | Pass |")
    w("| Single entry, one contact at a third (3.19 A; the other 21 typical / at 100 mOhm max) | -3.09 A | 352 mA / 306 mA | Over 0.30 A, pass on heat: 1.86 mW / 3.13 mW in that contact |")
    w("| Single entry, jumper ground contact open (typ / max R) | -3.21 A | 138 mA / 122 mA | Pass |")
    w("| Home, single entry, earthed monitor 50 Hz (1.0 V / 0.1 V) | 3.27 A / 0.33 A loop | 189 mA / 133 mA | Pass (4.05 mV / 405 uV adapter drop) |")
    w("")
    w("The 0.30 A rating is a heating limit (Hirose derives it from the temperature rise under current). When one "
      "contact takes more than its share it is because its resistance is low, so its heat stays small: 3.13 mW at "
      "worst, against 9.0 mW for a contact at its 100 mOhm maximum at 0.30 A, and 25 mW in all 22 against 59 mW "
      "(docs/AUDIT_Rev08.md section 6.3).")
    w("")
    w("Levels, bands and the register map: [ROUTING_SPEC](ROUTING_SPEC.md), [RX_VU_SPEC](RX_VU_SPEC.md), "
      "[SIGNAL_INTEGRITY](SIGNAL_INTEGRITY.md), [FPGA_GATEWARE](FPGA_GATEWARE.md), "
      "[LINK_PROTOCOL](../fpga/link/LINK_PROTOCOL.md).")
    w("")
    open(MD, "w", encoding="utf-8", newline="\n").write("\n".join(L))


README = os.path.join(ROOT, "README.md")


def readme(parts, nums):
    """The README's board manual section: the top drawing, the connectors and the LEDs."""
    by = {p.ref: p for p in parts}
    L = ["<!-- board-manual:start -->", "## Board manual", "",
         "Every connector, LED, switch and chip, numbered as in the drawing; the bottom side, the switches, "
         "the chips, troubleshooting and typical uses are in [docs/BOARD_MANUAL.md](docs/BOARD_MANUAL.md). "
         "Generated with the tables from the board file by `_work/manual/board_manual.py`.", "",
         "![Board manual, top side](docs/img/manual/board_top.png)", "",
         "| No. | Ref | Side | Name | What it is for |", "|---|---|---|---|---|"]
    for ref, val, what in CONNECTORS:
        L.append(f"| {nums[ref]} | `{ref}` | {by[ref].side} | {val} | {what} |")
    L += ["", "| No. | LED | Meaning when lit |", "|---|---|---|"]
    for name, refs in LED_GROUPS.items():
        for ref in refs:
            val, what = next((v, t) for r, v, t in LEDS if r == ref)
            L.append(f"| {nums[name]} | `{ref}` {val} | {what} |")
    L.append("<!-- board-manual:end -->")
    text = open(README, encoding="utf-8").read()
    a, b = text.index("<!-- board-manual:start -->"), text.index("<!-- board-manual:end -->")
    b += len("<!-- board-manual:end -->")
    nl = chr(10)
    open(README, "w", encoding="utf-8", newline=nl).write(text[:a] + nl.join(L) + text[b:])


def main():
    parts = board_parts.parts(PCB)
    edge = board_parts.outline(PCB)
    bad = check(parts)
    for b in bad:
        print("FAIL", b)
    nums = {}
    for n, label, refs in callouts():
        nums[label] = n
        for r in refs:
            nums[r] = n
    for side in ("top", "bottom"):
        draw(parts, edge, side, nums)
    md(parts, nums)
    readme(parts, nums)
    n_items = sum(len(r) for _, _, r in callouts())
    print(f"{len(callouts())} callouts, {n_items} parts; {len(TESTPOINTS)} test points; "
          f"{'FAIL' if bad else 'PASS'}: every connector, LED and IC of the board is listed and every listed part is on it")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
