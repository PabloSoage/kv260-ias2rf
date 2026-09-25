#!/usr/bin/env python3
"""
Build a project symbol library with CORRECT pin electrical types.

The point of this exercise is ERC. A symbol whose pins are all `unspecified`
makes ERC blind - that is what produced the 48 uninterpretable `pin_to_pin`
conflicts in the Rev01 work (docs/AUDIT_Rev01.md §2.2). So every pin here
carries a real type.

WHERE THE DATA COMES FROM, AND HOW FAR TO TRUST IT
--------------------------------------------------
Fifteen of the seventeen symbols are transcribed from the MANUFACTURER DATASHEET
(DATASHEET_PINS below). analog.com will not serve its PDFs to this machine, so
they came from two other places:

  * the AERIS-10 repository, which ships several datasheets locally
    (<PLFM_RADAR>/7_Components Datasheets and Application notes/);
  * the Internet Archive's copies of analog.com's own URLs, fetched by
    _work/fetch_datasheets.py - byte-identical to what analog.com served on the
    snapshot date, and the script records which snapshot.

Pin tables were read from the RENDERED page, not from extracted text: text
extraction drops overbars (so REFA and REFA-bar become the same name) and
shuffles table columns.

The remaining two (ADAR1000ACCZN, ADF4382A) come from the **Eagle library of
the AERIS-10 project**, whose boards were fabricated and measured. Good
evidence, but second-hand, and each such symbol says so in its properties.

Eagle records a direction per pin, which is exactly the information KiCad needs:

    in  -> input        out -> output       io  -> bidirectional
    pwr -> power_in     sup -> power_out    pas -> passive
    oc  -> open_collector                   hiz -> tri_state
    nc  -> no_connect

Parts already covered by KiCad's own official libraries are NOT rebuilt here.
Those are maintained and verified, and duplicating them would only create a
second version to drift:

    XC7A50T-FTG256   FPGA_Xilinx_Artix7    front-end FPGA, 256 pins, 4 units
    ADF4351          RF                    SDR synthesiser (board B)

Usage:  py _work/make_symbols.py [--dry-run]
"""

import os
import re
import sys
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_LIB = os.path.join(ROOT, "symbols", "kv260-ias2rf.kicad_sym")

EAGLE_SOURCES = [
    r"E:\Repos\PLFM_RADAR\4_Schematics and Boards Layout\4_6_Schematics\MainBoard\RADAR_Main_Board.sch",
    r"E:\Repos\PLFM_RADAR\4_Schematics and Boards Layout\4_6_Schematics\FrequencySynthesizerBoard\Clocks_Freq_Synth_board.sch",
]

# deviceset name in Eagle -> (symbol name in our library, one-line description)
WANTED = {
    "AD9484BCPZ-500":  ("AD9484BCPZ-500", "8-bit 500 MSPS ADC, parallel LVDS - radar receive"),
    "AD8352ACPZ-R7":   ("AD8352ACPZ",     "Differential amplifier - ADC driver"),
    "M3SWA2-34DR+":    ("M3SWA2-34DR",    "SPDT absorptive RF switch, DC-30 GHz, internal driver"),
    "ADAR1000ACCZN":   ("ADAR1000ACCZN",  "4-channel X-band beamformer (AERIS-10, reference only)"),
    "LTC5552IUDBTRMPBF": ("LTC5552",      "3-20 GHz mixer (AERIS-10, reference only)"),
    "AD9523BCPZ":      ("AD9523BCPZ",     "Low jitter clock generator (AERIS-10, reference only)"),
    "ADF4382ABCCZ":    ("ADF4382A",       "11-21 GHz synthesiser (AERIS-10, reference only)"),
}

# ---------------------------------------------------------------------------
# Pin tables taken from the MANUFACTURER DATASHEET.
# These override anything derived from the Eagle library.
#
# Sources: the AERIS-10 datasheet folder (AD8352, AD9484, M3SWA2, LTC5552) and
# _work/fetch_datasheets.py (AD9523, AD9253, AD9767, ADCLK944, ADCLK948, Si549).
#
# EXPOSED PADS are numbered N+1 throughout, to match KiCad's stock footprints,
# whatever the datasheet calls them - see the AD9484 entry.
#
# (pad, name, kicad_type)
# ---------------------------------------------------------------------------

DATASHEET_PINS = {

    # ad8352.pdf Rev. C, Table 4 "Pin Function Descriptions".
    # 16-lead LFCSP; the exposed pad must be connected to ground.
    # Supply 3 to 5.5 V; quiescent current 39 mA max.
    "AD8352ACPZ": [
        ("1",  "RDP", "passive"),      ("2",  "RGP", "passive"),
        ("3",  "RGN", "passive"),      ("4",  "RDN", "passive"),
        ("5",  "VIN", "input"),
        ("6",  "GND", "power_in"),     ("7",  "GND", "power_in"),
        ("8",  "VCC", "power_in"),     ("9",  "GND", "power_in"),
        ("10", "VON", "output"),       ("11", "VOP", "output"),
        ("12", "GND", "power_in"),     ("13", "VCC", "power_in"),
        ("14", "VCM", "bidirectional"),("15", "ENB", "input"),
        ("16", "VIP", "input"),
        ("17", "GND_EP", "power_in"),
    ],

    # AD9484.pdf Rev. A, Table 7 "Pin Function Descriptions".
    # 56-lead LFCSP; pin 0 is the exposed paddle and is AGND.
    #   AVDD 1.8 V, IAVDD 283 mA typ / 300 mA max
    #   DRVDD 1.8 V, IDRVDD 89 mA typ / 100 mA max
    #   SDR-mode dissipation 670 mW typ / 720 mW max
    #
    # EXPOSED PAD NUMBERING. The datasheet calls the paddle "pin 0"; KiCad's
    # stock LFCSP/QFN footprints number it N+1 (QFN-56-1EP_8x8mm... has pads
    # 1..57). A symbol pin must match a footprint pad, or Update PCB leaves the
    # paddle - here the ADC's only analogue ground - unconnected. So the symbol
    # follows the footprint: pad 57. The first build of this symbol used "0".
    "AD9484BCPZ-500": (
        [("57", "AGND_EP", "power_in")]
        + [(str(n), "AVDD", "power_in")
           for n in (30, 32, 33, 34, 37, 38, 39, 41, 42, 43, 46)]
        + [(str(n), "DRVDD", "power_in") for n in (7, 24, 47)]
        + [(str(n), "DRGND", "power_in") for n in (8, 23, 48)]
        + [("35", "VIN+", "input"), ("36", "VIN-", "input"),
           ("40", "CML", "output"),
           ("44", "CLK+", "input"), ("45", "CLK-", "input"),
           ("31", "VREF", "bidirectional")]
        + [(str(n), "DNC", "no_connect")
           for n in (1, 2, 28, 51, 52, 53, 54, 55, 56)]
        + [("25", "SDIO", "bidirectional"), ("26", "SCLK/DFS", "input"),
           ("27", "CSB", "input"), ("29", "PWDN", "input"),
           ("49", "DCO-", "output"), ("50", "DCO+", "output")]
        + [(str(3 + 2 * i + off), f"D{i}{sign}", "output")
           for i in range(2) for off, sign in ((0, "-"), (1, "+"))]
        + [(str(9 + 2 * (i - 2) + off), f"D{i}{sign}", "output")
           for i in range(2, 8) for off, sign in ((0, "-"), (1, "+"))]
        + [("21", "OR-", "output"), ("22", "OR+", "output")]
    ),
    # M3SWA2-34DR+.pdf, "FUNCTIONAL DIAGRAM" and "DC ELECTRICAL SPECIFICATIONS".
    # 16-lead QFN, 3x3 mm.
    #
    # NOTE THE SUPPLIES. This part needs BOTH VDD = +3.3 V and VEE = -3.3 V.
    # Its control logic is positive (VCTRL low 0..+0.8 V, high +2..+3.6 V),
    # which is what made an earlier reading of a search snippet conclude that
    # no negative rail was needed. The datasheet is explicit: "VDD = +3.3 V,
    # VEE = -3.3 V". Positive control, bipolar supply.
    #   IDD 1.6 mA typ, 2.9 mA max;  IEE 0 mA typ, 1.8 mA max.
    #
    # PADDLE. "GND 2, 4, 7, 9, 11, 14, 16 & Paddle - connects to ground";
    # case style DQ3005, "exposed paddle". The first build of this symbol had
    # 16 pins and no paddle, so on the PCB a 30 GHz switch would have had its
    # main ground floating. Caught by _work/crosscheck_pinouts.py: the AERIS
    # Eagle part has pad 17, ours did not. Eagle was right.
    # Port names follow the PAD DESCRIPTION table ("RF OUT 1", "RF OUT 2").
    # NC pins: "Not used internally. Connected to ground on test board." -
    # passive, so grounding them as the test board does is not an ERC error.
    "M3SWA2-34DR": [
        ("1",  "NC",     "passive"),
        ("2",  "GND",    "power_in"),
        ("3",  "RFOUT1", "passive"),
        ("4",  "GND",    "power_in"),
        ("5",  "VEE",    "power_in"),
        ("6",  "VCTRL",  "input"),
        ("7",  "GND",    "power_in"),
        ("8",  "VDD",    "power_in"),
        ("9",  "GND",    "power_in"),
        ("10", "RFOUT2", "passive"),
        ("11", "GND",    "power_in"),
        ("12", "NC",     "passive"),
        ("13", "NC",     "passive"),
        ("14", "GND",    "power_in"),
        ("15", "RFC",    "passive"),
        ("16", "GND",    "power_in"),
        ("17", "GND_EP", "power_in"),
    ],

    # LTC5552f.pdf, "PIN CONFIGURATION" and "PIN FUNCTIONS".
    # 12-lead 3x2 mm QFN (UDB), exposed pad is pin 13 and is GND.
    # VCC is a regulated 3.3 V, 132 mA typical when enabled.
    #
    # DATASHEET ERRATUM. PIN FUNCTIONS says "GND (Pins 1, 3, 4, 6, 8, 10, 12,
    # Exposed Pad Pin 13)" AND "IF+, IF- (Pins 2, 3)" - pin 3 claimed twice.
    # The PIN CONFIGURATION drawing shows pin 3 as IF-, and a differential IF
    # needs it. Two statements of three say IF-; the GND list is the error.
    # Grounding pin 3 would short one side of the IF port.
    "LTC5552": [
        ("1",  "GND", "power_in"),
        ("2",  "IF+", "passive"),
        ("3",  "IF-", "passive"),
        ("4",  "GND", "power_in"),
        ("5",  "RF",  "passive"),
        ("6",  "GND", "power_in"),
        ("7",  "EN",  "input"),
        ("8",  "GND", "power_in"),
        ("9",  "VCC", "power_in"),
        ("10", "GND", "power_in"),
        ("11", "LO",  "input"),
        ("12", "GND", "power_in"),
        ("13", "GND_EP", "power_in"),
    ],

    # AD9523.pdf Rev. D, Figure 2 and Table 19 "Pin Function Descriptions".
    # 72-lead LFCSP, 10x10 mm; exposed paddle is GND (pad 73, see AD9484 note).
    #
    # Complements carry an overbar in the datasheet, which text extraction
    # loses; they were read from the rendered page. Every OUTn pair has the
    # complement on the LOWER pin number (Table 19: "25 OUT13-bar
    # Complementary..., 26 OUT13 Square Wave..."). In Figure 2 the overbar of
    # the lower row sits right under the row above and reads like an underline
    # of the wrong pin - the table is the authority, not the drawing.
    #
    # Type column: P -> power_in, P/O -> power_out (internal LDO decoupling
    # pins), I -> input, O -> output, I/O -> bidirectional, GND -> power_in.
    # Pin 69 is NC, typed "P" by the datasheet, "not connected internally";
    # Note 1 prefers it grounded, so it is passive rather than no_connect -
    # a no_connect pin wired to GND would be an ERC error for doing the
    # recommended thing.
    "AD9523BCPZ": (
        [("1",  "LDO_PLL1",    "power_out"),
         ("2",  "VDD3_PLL1",   "power_in"),
         ("3",  "REFA",        "input"),  ("4",  "~{REFA}",   "input"),
         ("5",  "REFB",        "input"),  ("6",  "~{REFB}",   "input"),
         ("7",  "LF1_EXT_CAP", "output"),
         ("8",  "OSC_CTRL",    "output"),
         ("9",  "OSC_IN",      "input"),  ("10", "~{OSC_IN}", "input"),
         ("11", "LF2_EXT_CAP", "output"),
         ("12", "LDO_PLL2",    "power_out"),
         ("13", "VDD3_PLL2",   "power_in"),
         ("14", "LDO_VCO",     "power_out"),
         ("15", "~{PD}",       "input"),
         ("16", "REF_SEL",     "input"),
         ("17", "~{SYNC}",     "input"),
         ("18", "VDD3_REF",    "power_in"),
         ("19", "~{RESET}",    "input"),
         ("20", "~{CS}",       "input"),
         ("21", "SCLK/SCL",    "input"),
         ("22", "SDIO/SDA",    "bidirectional"),
         ("23", "SDO",         "output"),
         ("24", "REF_TEST",    "input"),
         ("55", "STATUS1/SP1", "bidirectional"),
         ("56", "STATUS0/SP0", "bidirectional"),
         ("57", "EEPROM_SEL",  "input"),
         ("69", "NC",          "passive"),
         ("70", "ZD_IN",       "input"),  ("71", "~{ZD_IN}", "input"),
         ("72", "PLL1_OUT",    "output"),
         ("73", "GND_EP",      "power_in")]
        # (complement pin, true pin) for OUT0..OUT13
        + [(str(pc), f"~{{OUT{n}}}", "output") for n, (pc, pt) in enumerate(
              [(67, 68), (64, 65), (61, 62), (58, 59), (52, 53), (49, 50),
               (46, 47), (43, 44), (40, 41), (37, 38), (34, 35), (31, 32),
               (28, 29), (25, 26)])]
        + [(str(pt), f"OUT{n}", "output") for n, (pc, pt) in enumerate(
              [(67, 68), (64, 65), (61, 62), (58, 59), (52, 53), (49, 50),
               (46, 47), (43, 44), (40, 41), (37, 38), (34, 35), (31, 32),
               (28, 29), (25, 26)])]
        + [(str(p), n, "power_in") for p, n in (
              (27, "VDD3_OUT[12:13]"), (33, "VDD3_OUT[10:11]"),
              (39, "VDD3_OUT[8:9]"),   (45, "VDD3_OUT[6:7]"),
              (51, "VDD3_OUT[4:5]"),   (60, "VDD3_OUT[2:3]"),
              (66, "VDD3_OUT[0:1]"),
              (30, "VDD1.8_OUT[12:13]"), (36, "VDD1.8_OUT[10:11]"),
              (42, "VDD1.8_OUT[8:9]"),   (48, "VDD1.8_OUT[6:7]"),
              (54, "VDD1.8_OUT[4:5]"),   (63, "VDD1.8_OUT[0:3]"))]
    ),

    # AD9253.pdf Rev. D, Figure 9 and Table 8 "Pin Function Descriptions".
    # 48-lead LFCSP 7x7 mm (CP-48-13); pin 0 = AGND exposed pad -> pad 49.
    # This datasheet has no Type column; types follow the descriptions.
    #
    # NOTE THE SUPPLY. DRVDD is 1.8 V (Table 1: 1.7 / 1.8 / 1.9 V), absolute
    # maximum 2.0 V. The first power budget put it on +3V3_D, which would have
    # destroyed the part at power-up. It is on +1V8_D now.
    #   -125 grade: IAVDD 183 typ / 200 max, IDRVDD 71 typ / 100 max (ANSI-644)
    "AD9253BCPZ-125": (
        [("49", "AGND_EP", "power_in")]
        + [(str(n), "AVDD", "power_in") for n in (3, 4, 7, 34, 39, 45, 46)]
        + [(str(n), "DRVDD", "power_in") for n in (8, 29)]
        + [("1",  "VIN+D", "input"), ("2",  "VIN-D", "input"),
           ("36", "VIN+A", "input"), ("35", "VIN-A", "input"),
           ("37", "VIN+B", "input"), ("38", "VIN-B", "input"),
           ("48", "VIN+C", "input"), ("47", "VIN-C", "input"),
           ("5",  "CLK-",  "input"), ("6",  "CLK+",  "input")]
        + [(p, n, "output") for p, n in (
              ("9", "D1-D"), ("10", "D1+D"), ("11", "D0-D"), ("12", "D0+D"),
              ("13", "D1-C"), ("14", "D1+C"), ("15", "D0-C"), ("16", "D0+C"),
              ("17", "DCO-"), ("18", "DCO+"), ("19", "FCO-"), ("20", "FCO+"),
              ("21", "D1-B"), ("22", "D1+B"), ("23", "D0-B"), ("24", "D0+B"),
              ("25", "D1-A"), ("26", "D1+A"), ("27", "D0-A"), ("28", "D0+A"))]
        + [("30", "SCLK/DTP", "input"),
           ("31", "SDIO/OLM", "bidirectional"),
           ("32", "CSB",      "input"),
           ("33", "PDWN",     "input"),
           ("40", "RBIAS",    "passive"),      # 10 k 1 % to ground
           ("41", "SENSE",    "input"),
           ("42", "VREF",     "bidirectional"),  # "Voltage Reference Input and Output"
           ("43", "VCM",      "output"),
           ("44", "SYNC",     "input")]
    ),

    # AD9763_9765_9767.pdf Rev. G, Figure 5 and Table 6 (AD9767 column).
    # 48-lead LQFP, no exposed pad. Pin 1 is DB13P1, the MSB of port 1.
    #   AVDD 3-5.5 V: IAVDD 71 typ / 75 max.  DVDD 2.7-5.5 V: IDVDD 15 mA
    #   at 100 MSPS (Table 1, footnote 5; no maximum given).
    "AD9767ASTZ": (
        [(str(1 + i),  f"DB{13 - i}P1", "input") for i in range(14)]
        + [(str(23 + i), f"DB{13 - i}P2", "input") for i in range(14)]
        + [("15", "DCOM1", "power_in"), ("16", "DVDD1", "power_in"),
           ("17", "WRT1/IQWRT",   "input"),
           ("18", "CLK1/IQCLK",   "input"),
           ("19", "CLK2/IQRESET", "input"),
           ("20", "WRT2/IQSEL",   "input"),
           ("21", "DCOM2", "power_in"), ("22", "DVDD2", "power_in"),
           ("37", "SLEEP",    "input"),
           ("38", "ACOM",     "power_in"),
           ("39", "IOUTA2",   "output"), ("40", "IOUTB2", "output"),
           ("41", "FSADJ2",   "passive"),      # full-scale set resistor
           ("42", "GAINCTRL", "input"),
           ("43", "REFIO",    "bidirectional"),
           ("44", "FSADJ1",   "passive"),
           ("45", "IOUTB1",   "output"), ("46", "IOUTA1", "output"),
           ("47", "AVDD",     "power_in"),
           ("48", "MODE",     "input")]
    ),

    # ADCLK944.pdf Rev. 0, Figure 2 and Table 6 "Pin Function Descriptions".
    # 16-lead LFCSP 3x3 mm; EPAD must be connected to VEE -> pad 17.
    # Single supply here, so VEE is ground.
    #   Table 3: IVCC 138 typ / 165 max at 3.3 V, with outputs loaded 50 ohm to
    #   VCC-2 V - so the figure INCLUDES the current delivered to the loads.
    "ADCLK944BCPZ": [
        ("1",  "CLK",    "input"),
        ("2",  "VT",     "passive"),     # centre tap of the 100 ohm input termination
        ("3",  "VREF",   "output"),      # bias for AC-coupled inputs
        ("4",  "~{CLK}", "input"),
        ("5",  "VEE",    "power_in"),
        ("6",  "~{Q3}",  "output"), ("7",  "Q3", "output"),
        ("8",  "VCC",    "power_in"),
        ("9",  "~{Q2}",  "output"), ("10", "Q2", "output"),
        ("11", "~{Q1}",  "output"), ("12", "Q1", "output"),
        ("13", "VCC",    "power_in"),
        ("14", "~{Q0}",  "output"), ("15", "Q0", "output"),
        ("16", "VEE",    "power_in"),
        ("17", "VEE_EP", "power_in"),
    ],
}

DATASHEET_PINS.update({

    # ADCLK948.pdf Rev. B, Figure 2 and Table 7 "Pin Function Descriptions".
    # 32-lead LFCSP 5x5 mm (CP-32-21), exposed pad 2.70 mm square -> pad 33.
    # EPAD "must be soldered to the VEE power plane"; single 3.3 V supply
    # here, so VEE is ground.
    #   Table 4: IVCC 288 typ / 330 max mA, IVEE 96 / 120 mA, VCC-VEE 3.3 V.
    # Complements on the LOWER pin of each output pair (Table 7: "11, 12
    # Q7-bar, Q7"). IN_SEL (Table 3): logic 1 >= VCC-0.4 V, logic 0 <= 1 V,
    # 0.6 mA flows out of the pin at logic 0 - there is an internal pull-up.
    # VREFx is a bias output ((VCC+1)/2, 235 ohm) for AC-coupled inputs.
    "ADCLK948BCPZ": (
        [("1", "CLK0", "input"), ("2", "~{CLK0}", "input"),
         ("3", "VREF0", "output"), ("4", "VT0", "passive"),
         ("5", "CLK1", "input"), ("6", "~{CLK1}", "input"),
         ("7", "VT1", "passive"), ("8", "VREF1", "output"),
         ("9", "NC", "no_connect"),
         ("32", "IN_SEL", "input"),
         ("33", "VEE_EP", "power_in")]
        + [(str(p), "VCC", "power_in") for p in (10, 15, 16, 25, 26, 31)]
        # (complement pad, true pad) for Q0..Q7
        + [(str(c), f"~{{Q{n}}}", "output") for n, (c, t) in enumerate(
              [(29, 30), (27, 28), (23, 24), (21, 22), (19, 20), (17, 18), (13, 14), (11, 12)])]
        + [(str(t), f"Q{n}", "output") for n, (c, t) in enumerate(
              [(29, 30), (27, 28), (23, 24), (21, 22), (19, 20), (17, 18), (13, 14), (11, 12)])]
    ),

    # Si549 datasheet Revision H (Skyworks), "Pin Assignments" and Ordering
    # Guide. 8-pin, 5x7 mm package option A. Pins 1 and 2 depend on the
    # ordering "pinout option"; this symbol is PINOUT CODE C - the one the
    # datasheet names for replacing an Si570 ("If replacing Si570A-K, use
    # Code C"): pin 1 NC, pin 2 OE active high. That makes it pin- and
    # footprint-compatible with the Si570, whose KiCad stock symbol serves as
    # the second source in crosscheck_pinouts.py.
    #   IDD LVPECL 107 typ / 153 max mA. I2C pull-ups to VDD (datasheet §I2C).
    # AD9708 datasheet Rev. B, Pin Configuration and Pin Function
    # Descriptions (AERIS-10 component folder). Rebuilt here although KiCad's
    # Video library has it: the stock symbol omits the NC pins and its layout
    # forces crossings around the reference pins (docs/DAC_RADAR_SPEC.md).
    "AD9708AR": [
        ("1", "DB7", "input"), ("2", "DB6", "input"), ("3", "DB5", "input"),
        ("4", "DB4", "input"), ("5", "DB3", "input"), ("6", "DB2", "input"),
        ("7", "DB1", "input"), ("8", "DB0", "input"),
        ("9", "NC", "no_connect"), ("10", "NC", "no_connect"), ("11", "NC", "no_connect"),
        ("12", "NC", "no_connect"), ("13", "NC", "no_connect"), ("14", "NC", "no_connect"),
        ("15", "SLEEP", "input"), ("16", "REFLO", "passive"), ("17", "REFIO", "bidirectional"),
        ("18", "FS_ADJ", "passive"), ("19", "COMP1", "passive"), ("20", "ACOM", "power_in"),
        ("21", "IOUTB", "output"), ("22", "IOUTA", "output"), ("23", "COMP2", "passive"),
        ("24", "AVDD", "power_in"), ("25", "NC", "no_connect"), ("26", "DCOM", "power_in"),
        ("27", "DVDD", "power_in"), ("28", "CLOCK", "input"),
    ],
    # Power (25 Sep). TI datasheets: LMR33630 SNVSAN3F (ti.com, fetched by
    # _work/fetch_datasheets.py), TPS562201 SLVSD91D, TPS7A8300 SBVS197F,
    # LM2663 SNVS002E (AERIS-10 component folder). KiCad's own LMR33630
    # symbol extends another and is not used.
    "LMR33630ADDA": [
        ("1", "PGND", "power_in"), ("2", "VIN", "power_in"), ("3", "EN", "input"),
        ("4", "PG", "open_collector"), ("5", "FB", "input"), ("6", "VCC", "power_out"),
        ("7", "BOOT", "passive"), ("8", "SW", "output"), ("9", "AGND_EP", "power_in"),
    ],
    "TPS562201": [
        ("1", "GND", "power_in"), ("2", "SW", "output"), ("3", "VIN", "power_in"),
        ("4", "VFB", "input"), ("5", "EN", "input"), ("6", "VBST", "passive"),
    ],
    "TPS7A8300RGR": [
        ("1", "OUT", "power_out"), ("2", "SNS", "input"), ("3", "FB", "input"),
        ("4", "PG", "open_collector"), ("5", "50mV", "passive"), ("6", "100mV", "passive"),
        ("7", "200mV", "passive"), ("8", "GND", "power_in"), ("9", "400mV", "passive"),
        ("10", "800mV", "passive"), ("11", "1.6V", "passive"), ("12", "BIAS", "power_in"),
        ("13", "NR/SS", "passive"), ("14", "EN", "input"), ("15", "IN", "power_in"),
        ("16", "IN", "power_in"), ("17", "IN", "power_in"), ("18", "GND", "power_in"),
        # one OUT drives the rail; the other two are the same node, typed
        # passive so ERC does not see three drivers in conflict
        ("19", "OUT", "passive"), ("20", "OUT", "passive"), ("21", "GND_EP", "power_in"),
    ],
    "LM2663M": [
        ("1", "SD", "input"), ("2", "CAP+", "passive"), ("3", "GND", "power_in"),
        ("4", "CAP-", "passive"), ("5", "OUT", "power_out"), ("6", "LV", "input"),
        ("7", "OSC", "passive"), ("8", "V+", "power_in"),
    ],
    # CONTROL (25 Sep): the FPGA's configuration flash. Micron datasheet
    # mt25q_qlhs_L_128_ABA Rev. K, Figure 6 (8-pin SOP2, package code SE),
    # HOLD# option (part number digit 1). Fetched by _work/fetch_datasheets.py.
    # Layout (25 Sep): the DAC output balun. Mini-Circuits ADT2-1T+ datasheet
    # (Rev. F), Pin Connections: primary dot 3, primary 1, secondary dot 6,
    # secondary 4, secondary centre tap 5, not used 2. Case CD542.
    "ADT2-1T": [
        ("1", "PRI", "passive"), ("2", "NC", "no_connect"), ("3", "PRI_DOT", "passive"),
        ("4", "SEC", "passive"), ("5", "SEC_CT", "passive"), ("6", "SEC_DOT", "passive"),
    ],
    "MT25QL128ABA1ESE": [
        ("1", "~{S}", "input"), ("2", "DQ1", "bidirectional"), ("3", "~{W}/DQ2", "bidirectional"),
        ("4", "VSS", "power_in"), ("5", "DQ0", "bidirectional"), ("6", "C", "input"),
        ("7", "~{HOLD}/DQ3", "bidirectional"), ("8", "VCC", "power_in"),
    ],
    "Si549_PinoutC": [
        ("1", "NC",   "no_connect"),
        ("2", "OE",   "input"),
        ("3", "GND",  "power_in"),
        ("4", "CLK+", "output"),
        ("5", "CLK-", "output"),
        ("6", "VDD",  "power_in"),
        ("7", "SDA",  "bidirectional"),
        ("8", "SCL",  "input"),
    ],
})

_CLOCK_NOTES = {
    "ADCLK948BCPZ": "Pin table from the ADCLK948 datasheet Rev. B, Table 7. "
                    "IVCC 330 mA max. EPAD to VEE (ground here), pad 33.",
    "LMR33630ADDA": "Pin table from the LMR33630 datasheet SNVSAN3F, Pin Functions (HSOIC). "
                    "Thermal pad is AGND, pad 9.",
    "TPS562201": "Pin table from the TPS562201 datasheet SLVSD91D, Table 4-1 (SOT-23-6 DDC).",
    "TPS7A8300RGR": "Pin table from the TPS7A8300 datasheet SBVS197F, Pin Functions (RGR). "
                    "Program pins typed passive: each is tied to GND or left open. Pad 21 = GND.",
    "LM2663M": "Pin table from the LM2662/LM2663 datasheet SNVS002E, Pin Functions (LM2663: pin 1 SD).",
    "ADT2-1T": "Pin Connections from the Mini-Circuits ADT2-1T+ datasheet Rev. F. 50 ohm, impedance "
               "ratio 2 (secondary/primary), 0.4-450 MHz, case CD542, land pattern PL-052.",
    "MT25QL128ABA1ESE": "Pin table from the Micron MT25QL128ABA datasheet Rev. K, Figure 6 "
                        "(SO8W, 208 mil; HOLD# variant). 2.7-3.6 V. In Vivado's configuration "
                        "memory list (UG908) as mt25ql128.",
    "AD9708AR": "Pin table from the AD9708 datasheet Rev. B, Pin Function Descriptions. "
                "AVDD/DVDD 2.7-5.5 V; IAVDD 30 mA max, IDVDD 6 mA max.",
    "Si549_PinoutC": "Pin table from the Si549 datasheet Revision H, pinout code C "
                     "(Si570-compatible: pin 1 NC, pin 2 OE active high). IDD 153 mA max LVPECL.",
}

# Parts that exist ONLY as datasheet tables - there is no Eagle deviceset to
# start from. name -> one-line description.
DATASHEET_ONLY = {
    "ADCLK948BCPZ":   "2-input, 8-output LVPECL clock fan-out, 4.8 GHz - reference selector and distribution",
    "Si549_PinoutC":  "I2C programmable ultra-low-jitter XO, 0.2-1500 MHz, LVPECL - local master clock",
    "ADT2-1T":          "RF transformer 1:2 impedance, 0.4-450 MHz - DAC output balun (100 ohm side to the DAC)",
    "MT25QL128ABA1ESE": "128 Mb 3 V quad SPI NOR flash, SO8W - FPGA configuration",
    "AD9708AR":       "8-bit 125 MSPS current-output DAC, parallel CMOS - radar chirp",
    "LMR33630ADDA":   "3.8-36 V in, 3 A synchronous buck, 400 kHz - 12 V to +5V0",
    "TPS562201":      "4.5-17 V in, 2 A synchronous buck, SOT-23-6 - +3V3_D, +2V5, +1V0",
    "TPS7A8300RGR":   "2 A low-noise LDO, ANY-OUT - +1V8_A, +1V8_D, +3V3_A",
    "LM2663M":        "Switched-capacitor voltage inverter, 200 mA - -3V3",
    "AD9253BCPZ-125": "Quad 14-bit 125 MSPS ADC, serial LVDS - SDR receive (2 of 4 channels used)",
    "AD9767ASTZ":     "Dual 14-bit 125 MSPS current-output DAC, parallel CMOS - SDR transmit",
    "ADCLK944BCPZ":   "1:4 LVPECL clock fan-out, 7 GHz - first clock plan, superseded by the ADCLK948",
}

DATASHEET_NOTE = {
    "AD8352ACPZ": "Pin table from the AD8352 datasheet Rev. C, Table 4. "
                  "Supply 3-5.5 V, quiescent current 39 mA max. EP is GND.",
    "AD9484BCPZ-500": "Pin table from the AD9484 datasheet Rev. A, Table 7. "
                      "AVDD/DRVDD 1.8 V; IAVDD 300 mA max, IDRVDD 100 mA max. "
                      "Exposed pad (datasheet pin 0) is pad 57 to match KiCad footprints.",
    "AD9523BCPZ": "Pin table from the AD9523 datasheet Rev. D, Table 19. "
                  "Complements read from the rendered page. Exposed pad is GND, pad 73.",
    "AD9253BCPZ-125": "Pin table from the AD9253 datasheet Rev. D, Table 8. "
                      "AVDD AND DRVDD are both 1.8 V (DRVDD abs max 2.0 V). "
                      "Exposed pad (datasheet pin 0) is AGND, pad 49.",
    "AD9767ASTZ": "Pin table from the AD9763/AD9765/AD9767 datasheet Rev. G, Table 6. "
                  "AVDD 3-5.5 V, 75 mA max; DVDD 2.7-5.5 V. No exposed pad.",
    "ADCLK944BCPZ": "Pin table from the ADCLK944 datasheet Rev. 0, Table 6. "
                    "IVCC 165 mA max at 3.3 V, outputs loaded. EPAD to VEE, pad 17.",
    "M3SWA2-34DR": "Pin table from the Mini-Circuits M3SWA2-34DR+ datasheet, PAD DESCRIPTION. "
                   "Needs BOTH VDD +3.3 V and VEE -3.3 V; control logic is positive. "
                   "Exposed paddle is GND, pad 17.",
    "LTC5552": "Pin table from the Analog Devices LTC5552 datasheet (LTC5552f). "
               "VCC 3.3 V, 132 mA typical enabled. Exposed pad (pin 13) is GND.",
}
DATASHEET_NOTE.update(_CLOCK_NOTES)


DIR_MAP = {
    "in": "input", "out": "output", "io": "bidirectional",
    "oc": "open_collector", "pwr": "power_in", "sup": "power_out",
    "pas": "passive", "hiz": "tri_state", "nc": "no_connect",
}

DRY = "--dry-run" in sys.argv
NL, TAB = chr(10), chr(9)


def load_libraries(path):
    """Return {deviceset: [(pad, pinname, kicad_type)]} from an Eagle schematic."""
    tree = ET.parse(path)
    root = tree.getroot()
    found = {}
    for lib in root.iter("library"):
        # symbol -> {pinname: direction}
        symdirs = {}
        for sym in lib.iter("symbol"):
            d = {}
            for pin in sym.iter("pin"):
                d[pin.get("name")] = pin.get("direction", "pas")
            symdirs[sym.get("name")] = d

        for ds in lib.iter("deviceset"):
            name = ds.get("name")
            if name not in WANTED:
                continue
            gate_sym = {g.get("name"): g.get("symbol") for g in ds.iter("gate")}
            pins = []
            for dev in ds.iter("device"):
                for con in dev.iter("connect"):
                    gate, pin, pad = con.get("gate"), con.get("pin"), con.get("pad")
                    if not pad:
                        continue
                    direction = symdirs.get(gate_sym.get(gate, ""), {}).get(pin, "pas")
                    for p in pad.split():
                        pins.append((p, pin, DIR_MAP.get(direction, "passive")))
                if pins:
                    break            # first packaged variant is enough
            if pins:
                found[name] = pins
    return found


def sort_key(pad):
    m = re.match(r"^(\d+)$", pad)
    return (0, int(m.group(1)), "") if m else (1, 0, pad)


# Hand-arranged pin layouts, for symbols that have to read well on a sheet.
# Pads listed per side, top to bottom (left/right) or left to right
# (pwr/gnd); None leaves a gap between groups. Every pad must appear once.
SYMBOL_LAYOUT = {
    # Each input grouped with its own termination pins, so the AC-coupling
    # network draws as a straight line; outputs in order Q0..Q7, true pin
    # above its complement.
    "ADCLK948BCPZ": {
        "half_w": 12.7,
        "left": ["1", "2", "4", "3", None, None, None, None,
                 "5", "6", "7", "8", None, None, None, None, "32"],
        "right": ["30", "29", "28", "27", "24", "23", "22", "21",
                  "20", "19", "18", "17", "14", "13", "12", "11"],
        "pwr": ["10", "15", "16", "25", "26", "31"],
        "gnd": ["33", "9"],
    },
    "Si549_PinoutC": {
        "half_w": 7.62,
        "left": ["2", None, "7", "8"],
        "right": ["4", "5"],
        "pwr": ["6"],
        "gnd": ["3", "1"],
    },
    # Ordered so the external network draws without a single crossing:
    # VIP, RGN, RGP, RDP, RDN, VIN, each pair that takes a part exactly one
    # resistor length (7.62 mm) apart. RN (single-ended input, AD8352
    # Figure 26) runs VIP -> RGN, RG runs RGN -> RGP, RD and CD run
    # RDP -> RDN. VOP is level with VIP and VON with VIN. ENB sits on top
    # beside VCC, which is what it is tied to.
    "AD8352ACPZ": {
        "half_w": 10.16,
        "left": ["16", None, None, "3", None, None, "2", "1", None, None, "4",
                 None, None, "5", None, "14", None, None],
        "right": ["11"] + [None] * 12 + ["10"] + [None] * 4,
        "pwr": ["8", "13", "15"],
        "gnd": ["6", "7", "9", "12", "17"],
    },
    # Channel A's input at the top of the left side and channel B's at the
    # bottom, so each driver chain comes straight in; between them the
    # reference, bias, clock and SPI pins, spaced for the parts hanging off
    # them. Unused channels C and D on the bottom edge (tied to VCM).
    # Right: the one-lane outputs used (A on D0+-B, B on D1+-B, Table 8),
    # DCO, FCO, then the unused lanes.
    "AD9253BCPZ-125": {
        "half_w": 20.32,
        "left": ["36", "35", None, None, "43", None, None, None, None,
                 "42", None, None, None, None, "41", None, None, "40", None, None, None, None,
                 "6", "5", None, None, None, "31", "30", "32", "33", None, "44",
                 None, None, "37", "38"],
        "right": ["24", "23", "22", "21", None, "18", "17", "20", "19", None,
                  "28", "27", "26", "25", "16", "15", "14", "13", "12", "11", "10", "9"],
        "pwr": ["3", "4", "7", "34", "39", "45", "46", None, "8", "29"],
        "gnd": ["49", None, "48", "47", "1", "2"],
    },
    # Regulators: input and enable on the left, switch node with its boot
    # capacitor pin one part-length above it, feedback below, on the right.
    "LMR33630ADDA": {"half_w": 10.16, "left": ["2", None, "3", None, "6", None, "4"],
                     "right": ["7", None, None, "8", None, None, "5"], "gnd": ["1", "9"]},
    "TPS562201": {"half_w": 7.62, "left": ["3", None, None, "5"],
                  "right": ["6", None, None, "2", None, None, "4"], "gnd": ["1"]},
    "TPS7A8300RGR": {"half_w": 12.7,
                     "left": ["15", "16", "17", None, "14", None, "13", None, "12"],
                     "right": ["1", "19", "20", None, "2", None, "3", None, "4"],
                     "gnd": ["5", "6", "7", "9", "10", "11", None, "8", "18", "21"]},
    # secondary (100 ohm, to the DAC) on the left, dot at the top and the
    # other end 15.24 mm below, the spacing of the DAC output legs
    "ADT2-1T": {"half_w": 10.16, "left": ["6", None, None, "5", None, None, "4"],
                "right": ["3", None, None, None, None, None, "1"], "gnd": ["2"]},
    "MT25QL128ABA1ESE": {"half_w": 10.16, "left": ["1", "6", "5", "2", "3", "7", None],
                         "pwr": ["8"], "gnd": ["4"]},
    "LM2663M": {"half_w": 7.62, "left": ["8", None, "1", "6", "7"],
                "right": ["2", None, None, "4", None, "5"], "gnd": ["3"]},
    # RFC and the control in on the left, the two throws out on the right
    # 15.24 mm apart; VDD alone on top and VEE apart at the bottom-left, so
    # each supply's filter network (datasheet Figure 2) stacks clear of the
    # ground bus that takes the GND and NC pads.
    "M3SWA2-34DR": {
        "half_w": 19.05,
        "left": [None, "15", None, None, None, "6"],
        "right": ["3", None, None, None, None, None, "10"],
        "pwr": ["8"],
        "gnd": ["5", None, None, "2", "4", "7", "9", "11", "14", "16", "17", "1", "12", "13"],
    },
    # Interleaved mode: port 1 data and the four IQ controls on the left, then
    # every pin tied low (MODE, GAINCTRL, SLEEP and the unused port 2) in one
    # contiguous block that a single bus grounds. Each DAC's outputs 15.24 mm
    # apart on the right; reference and full-scale networks along the bottom.
    "AD9767ASTZ": {
        "half_w": 30.48,
        "left": [str(p) for p in range(1, 15)] + [None, "17", "18", "19", "20", None, None,
                                                   "48", "42", "37"]
                + [str(p) for p in range(23, 37)] + [None, None],
        "right": ["46"] + [None] * 5 + ["45"] + [None] * 6 + ["39"] + [None] * 5 + ["40"],
        "pwr": ["16", "22", None, None, None, "47"],
        "gnd": ["43", None, None, None, "44"] + [None] * 7 + ["41"] + [None] * 7
               + ["38", "15", "21"],
    },
    # Data and clock in on the left; outputs on the right, 15.24 mm apart so
    # the filter's shunt parts hang between the legs; COMP1 on top beside
    # AVDD (its capacitor goes to AVDD); the reference, full-scale and
    # grounds along the bottom, spaced for the parts hanging off them.
    "AD9708AR": {
        "half_w": 22.86,
        "left": ["1", "2", "3", "4", "5", "6", "7", "8", None, "28", None, "15", None,
                 "9", "10", "11", "12", "13", "14", "25", None, None, None],
        "right": [None, None, None, None, None, "22", None, None, None, None, None, "21"],
        "pwr": ["27", None, None, None, "24", None, None, "19"],
        "gnd": ["17", None, None, None, "18", None, None, None, None, None, "23", None,
                None, None, "16", "20", "26"],
    },
    # Analogue, clock and control in on the left; data out on the right in
    # bit order, true pin above complement; supplies on top, AVDD then DRVDD.
    # The gaps on the left leave room for the parts hanging off CML, VREF
    # and the clock termination, so nothing crosses the wires below them.
    "AD9484BCPZ-500": {
        "half_w": 25.4,
        "left": ["35", "36", None, None, "40", "31", None, None, None, None, "44", "45",
                 None, None, "25", "26", "27", "29"],
        "right": ["4", "3", "6", "5", "10", "9", "12", "11", "14", "13", "16", "15",
                  "18", "17", "20", "19", None, "22", "21", None, "50", "49"],
        "pwr": ["30", "32", "33", "34", "37", "38", "39", "41", "42", "43", "46",
                None, "7", "24", "47"],
        "gnd": ["57", "8", "23", "48", None,
                "1", "2", "28", "51", "52", "53", "54", "55", "56"],
    },
}


def emit_symbol(libname, desc, pins, source_note):
    """A KiCad symbol: power on top/bottom, inputs left, outputs right."""
    def bucket(t, name):
        if t in ("power_in", "power_out"):
            return "gnd" if re.search(
                r"(?i)^(a|d|dr)?gnd(_ep)?$|^(vee|vss|epad|ep|vee_ep|[ad]com\d?)$", name) else "pwr"
        if t in ("input",):
            return "left"
        if t in ("output",):
            return "right"
        if t == "no_connect":
            return "nc"
        return "left" if len(name) <= 6 else "right"

    groups = {"pwr": [], "gnd": [], "left": [], "right": [], "nc": []}
    for pad, name, t in sorted(pins, key=lambda p: sort_key(p[0])):
        groups[bucket(t, name)].append((pad, name, t))

    lay = SYMBOL_LAYOUT.get(libname)
    if lay:
        bypad = {p[0]: p for p in pins}
        listed = [x for k in ("left", "right", "pwr", "gnd") for x in lay.get(k, []) if x]
        assert sorted(listed) == sorted(bypad),             f"{libname}: layout and pin table disagree: {set(bypad) ^ set(listed)}"
        groups = {k: [bypad[x] if x else None for x in lay.get(k, [])]
                  for k in ("left", "right", "pwr", "gnd")}
        groups["nc"] = []

    n_side = max(len(groups["left"]), len(groups["right"]), 1)
    n_tb = max(len(groups["pwr"]), len(groups["gnd"]) + len(groups["nc"]), 1)
    half_h = max(n_side, 4) * 2.54 / 2 + 2.54
    half_w = max(n_tb, 4) * 2.54 / 2 + 2.54
    half_w = lay["half_w"] if lay else max(half_w, 25.4)

    L = []
    L.append(f'{TAB}(symbol "{libname}"')
    L.append(f'{TAB}{TAB}(pin_names (offset 0.508))')
    L.append(f'{TAB}{TAB}(exclude_from_sim no)')
    L.append(f'{TAB}{TAB}(in_bom yes)')
    L.append(f'{TAB}{TAB}(on_board yes)')
    for pname, pval, vis in (("Reference", "U", "no"), ("Value", libname, "no"),
                             ("Footprint", "", "yes"), ("Datasheet", "", "yes"),
                             ("Description", desc, "yes"),
                             ("ki_keywords", "kv260-ias2rf", "yes"),
                             ("SymbolSource", source_note, "yes")):
        L.append(f'{TAB}{TAB}(property "{pname}" "{pval}"')
        L.append(f'{TAB}{TAB}{TAB}(at 0 0 0)')
        L.append(f'{TAB}{TAB}{TAB}(effects (font (size 1.27 1.27)) (hide {vis}))')
        L.append(f'{TAB}{TAB})')

    L.append(f'{TAB}{TAB}(symbol "{libname}_0_1"')
    L.append(f'{TAB}{TAB}{TAB}(rectangle')
    L.append(f'{TAB}{TAB}{TAB}{TAB}(start {-half_w:.2f} {half_h:.2f})')
    L.append(f'{TAB}{TAB}{TAB}{TAB}(end {half_w:.2f} {-half_h:.2f})')
    L.append(f'{TAB}{TAB}{TAB}{TAB}(stroke (width 0.254) (type default))')
    L.append(f'{TAB}{TAB}{TAB}{TAB}(fill (type background))')
    L.append(f'{TAB}{TAB}{TAB})')
    L.append(f'{TAB}{TAB})')

    L.append(f'{TAB}{TAB}(symbol "{libname}_1_1"')

    def add(pad, name, t, x, y, rot):
        L.append(f'{TAB}{TAB}{TAB}(pin {t} line')
        L.append(f'{TAB}{TAB}{TAB}{TAB}(at {x:.2f} {y:.2f} {rot})')
        L.append(f'{TAB}{TAB}{TAB}{TAB}(length 2.54)')
        L.append(f'{TAB}{TAB}{TAB}{TAB}(name "{name}" (effects (font (size 1.27 1.27))))')
        L.append(f'{TAB}{TAB}{TAB}{TAB}(number "{pad}" (effects (font (size 1.27 1.27))))')
        L.append(f'{TAB}{TAB}{TAB})')

    # None entries are gaps: they take a position but place no pin.
    y = (len(groups["left"]) - 1) * 2.54 / 2
    for e in groups["left"]:
        if e:
            add(*e, -half_w - 2.54, y, 0)
        y -= 2.54
    y = (len(groups["right"]) - 1) * 2.54 / 2
    for e in groups["right"]:
        if e:
            add(*e, half_w + 2.54, y, 180)
        y -= 2.54
    x = -(len(groups["pwr"]) - 1) * 2.54 / 2
    for e in groups["pwr"]:
        if e:
            add(*e, x, half_h + 2.54, 270)
        x += 2.54
    bottom = groups["gnd"] + groups["nc"]
    x = -(len(bottom) - 1) * 2.54 / 2
    for e in bottom:
        if e:
            add(*e, x, -half_h - 2.54, 90)
        x += 2.54

    L.append(f'{TAB}{TAB})')
    L.append(f'{TAB})')
    return NL.join(L)


def main():
    print("Building the project symbol library")
    print()
    print("Already covered by KiCad's official libraries, not rebuilt:")
    print("    XC7A50T-FTG256   FPGA_Xilinx_Artix7")
    print("    ADF4351          RF")
    print()

    all_pins = {}
    for src in EAGLE_SOURCES:
        if not os.path.exists(src):
            print(f"  source missing: {src}")
            continue
        got = load_libraries(src)
        for k, v in got.items():
            all_pins.setdefault(k, v)
        print(f"  {os.path.basename(src)}: {len(got)} devicesets")

    print()
    missing = [k for k in WANTED if k not in all_pins]

    # (symbol name, description, pins, provenance note) for every symbol.
    symbols = []
    for ds, pins in sorted(all_pins.items()):
        name, desc = WANTED[ds]
        if name in DATASHEET_PINS:
            symbols.append((name, desc, DATASHEET_PINS[name], DATASHEET_NOTE[name]))
        else:
            symbols.append((name, desc, pins, None))
    for name, desc in sorted(DATASHEET_ONLY.items()):
        symbols.append((name, desc, DATASHEET_PINS[name], DATASHEET_NOTE[name]))

    import collections
    bad = 0
    for name, desc, pins, src in symbols:
        tag = "datasheet" if src else "eagle    "
        types = collections.Counter(t for _, _, t in pins)
        print(f"  [{tag}] {name:18s} {len(pins):3d} pins   "
              + "  ".join(f"{t}:{c}" for t, c in types.most_common()))
        # A pad listed twice is a transcription error, never a feature.
        pads = collections.Counter(p for p, _, _ in pins)
        dup = sorted((p for p, c in pads.items() if c > 1), key=sort_key)
        if dup:
            print(f"        DUPLICATE PADS: {dup}")
            bad += 1
        # Numeric pads must run 1..N with no gap (the exposed pad is N).
        # Datasheet symbols only: Eagle's LGA/BGA parts use letter-number pads.
        nums = sorted(int(p) for p in pads if p.isdigit())
        if src and nums and nums != list(range(1, len(nums) + 1)):
            gaps = sorted(set(range(1, max(nums) + 1)) - set(nums))
            print(f"        PAD SEQUENCE BROKEN: first={nums[0]} gaps={gaps}")
            bad += 1
    if missing:
        print(f"\n  NOT FOUND in the Eagle sources: {missing}")
    if bad:
        print(f"\nABORTED: {bad} symbol(s) failed the pad checks")
        return 1

    if DRY:
        print("\n--dry-run: nothing written.")
        return 0

    os.makedirs(os.path.dirname(OUT_LIB), exist_ok=True)
    note = ("Pin table derived from the AERIS-10 Eagle library "
            "(fabricated and measured hardware), NOT from the manufacturer "
            "datasheet - analog.com was unreachable. Verify before fabrication.")
    body = [
        '(kicad_symbol_lib',
        f'{TAB}(version 20241209)',
        f'{TAB}(generator "kv260-ias2rf/_work/make_symbols.py")',
    ]
    for name, desc, pins, src in symbols:
        body.append(emit_symbol(name, desc, pins, src or note))
    body.append(')')

    with open(OUT_LIB, "w", encoding="utf-8", newline=NL) as fh:
        fh.write(NL.join(body) + NL)
    print(f"\nwrote {os.path.relpath(OUT_LIB, ROOT)}  ({len(symbols)} symbols)")
    print("Verify with:  kicad-cli sym upgrade / sym export svg")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
