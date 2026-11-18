#!/usr/bin/env python3
"""
Choose an LCSC part for every BOM line, from JLCPCB's own parts search.

The symbols carry no part numbers (FABRICATION.md §3): chips carry their part
number as the value, passives only a value. This script turns each BOM line
(value + footprint) into a JLCPCB/LCSC part by explicit rules, and writes the
choice to _work/fab/lcsc_parts.csv, which make_fab.py reads to fill the BOM's
"LCSC Part #" column.

The rules, in order of importance:
  * the part must BE the part: value, package, and for a chip the exact model;
  * capacitors: C0G below 1 nF, X7R or X5R above, never Y5V; a voltage rating
    of at least RULES' min_v (from the highest rail the line's nets touch);
  * resistors: 1 %;
  * among parts that qualify: JLCPCB "basic" before "extended" (no loading
    fee), then their "preferred" flag, then stock.

Stock and price change daily. The CSV records the date of the search; run it
again before ordering and read the diff. A line with no qualifying part is
written with an empty code and the reason, never with a near miss.

Data source: jlcpcb.com's parts search (the API behind jlcpcb.com/parts).

Usage:  py _work/fab/lcsc_select.py [--only "Comment|Footprint"]
"""

import csv
import datetime
import glob
import json
import os
import re
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "_work", "fab", "lcsc_parts.csv")
API = ("https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/"
       "selectSmtComponentList")

# ---------------------------------------------------------------- values
SI = {"p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "m": 1e-3, "k": 1e3, "M": 1e6, "": 1.0}


def num(text, unit):
    """'4.7u' / '4.7uF' / '10kΩ' / '1.91k' -> float; None if no match."""
    m = re.match(r"^\s*([\d.]+)\s*([pnuµmkM]?)\s*" + unit + r"?", text)
    if not m:
        return None
    return float(m.group(1)) * SI[m.group(2)]


def close(a, b, rel=0.005):
    return a is not None and b is not None and abs(a - b) <= rel * max(abs(a), abs(b))


# ---------------------------------------------------------------- rules
# Key: (BOM Comment, footprint name). Kinds:
#   C   value, package code, min volts, dielectrics
#   R   value, package code (1 %)
#   L   value, package code, min current (A)
#   FB  impedance at 100 MHz, package code, min current (A)
#   P   keyword, regex the manufacturer part number must match
#   X   no part: the reason
C0G, XR = ("C0G", "NP0", "C0G(NP0)"), ("X7R", "X5R", "X7S", "X6S")
RULES = {
    ("100n", "C_0402_1005Metric"): ("C", "100n", "0402", 16, XR),
    ("10u", "C_0805_2012Metric"): ("C", "10u", "0805", 16, XR),      # up to +5V0
    ("1u", "C_0402_1005Metric"): ("C", "1u", "0402", 10, XR),
    ("1n", "C_0402_1005Metric"): ("C", "1n", "0402", 25, XR),
    ("100p", "C_0402_1005Metric"): ("C", "100p", "0402", 25, C0G),
    ("0.6p", "C_0402_1005Metric"): ("C", "0.6p", "0402", 25, C0G),
    ("0.2p", "C_0402_1005Metric"): ("C", "0.2p", "0402", 25, C0G),
    ("2.7p", "C_0402_1005Metric"): ("C", "2.7p", "0402", 25, C0G),
    ("0.3p", "C_0402_1005Metric"): ("C", "0.3p", "0402", 25, C0G),
    ("5p", "C_0402_1005Metric"): ("C", "5p", "0402", 25, C0G),
    ("22p", "C_0402_1005Metric"): ("C", "22p", "0402", 25, C0G),
    ("8.2p", "C_0402_1005Metric"): ("C", "8.2p", "0402", 25, C0G),
    ("20p", "C_0402_1005Metric"): ("C", "20p", "0402", 25, C0G),
    ("62p", "C_0402_1005Metric"): ("C", "62p", "0402", 25, C0G),
    ("27p", "C_0402_1005Metric"): ("C", "27p", "0402", 25, C0G),       # Y1201 load
    ("82p", "C_0402_1005Metric"): ("C", "82p", "0402", 25, C0G),       # IF_RX_C anti-alias LPF (Rev07)
    ("47p", "C_0402_1005Metric"): ("C", "47p", "0402", 25, C0G),
    ("150p", "C_0402_1005Metric"): ("C", "150p", "0402", 25, C0G),
    ("39p", "C_0402_1005Metric"): ("C", "39p", "0402", 25, C0G),
    ("160p", "C_0402_1005Metric"): ("C", "160p", "0402", 25, C0G),
    ("10p", "C_0402_1005Metric"): ("C", "10p", "0402", 25, C0G),
    ("220n", "L_0805_2012Metric"): ("P", "LQW2BASR22J", r"^LQW2BASR22J"),   # anti-alias LPF: 0805 wirewound, Q ~40 at 30 MHz (the 2 % part is not stocked)
    ("270n", "L_0805_2012Metric"): ("P", "SDWL2012CR27G", r"^SDWL2012CR27G"),
    ("330n", "L_0805_2012Metric"): ("P", "LQW2BASR33G", r"^LQW2BASR33G"),
    # J961's bias tee (SIGNAL_INTEGRITY 9.10, _work/sim/bias_tee.py): the bead's curve and the 1 uH's SRF are what
    # the simulation used, so these two are the parts, not a value match (C21516, C333860 on 17 Nov 2026)
    ("BLM15HD102SN1", "L_0402_1005Metric"): ("P", "BLM15HD102SN1", r"^BLM15HD102SN1"),
    ("1u", "L_0805_2012Metric"): ("P", "LQW2BAS1R0J", r"^LQW2BAS1R0J"),
    ("1u", "L_0603_1608Metric"): ("P", "AHW1608F-1R0KTF", r"^AHW1608F-1R0KTF"),   # L1303, L1305: SRF 400 MHz, 330 mA (C6364703)
    ("22n", "C_0402_1005Metric"): ("C", "22n", "0402", 16, XR),
    ("47u 25V", "C_1210_3225Metric"): ("C", "47u", "1210", 25, XR),
    ("10u 25V", "C_1206_3216Metric"): ("C", "10u", "1206", 25, XR),
    ("220n 25V", "C_0603_1608Metric"): ("C", "220n", "0603", 25, XR),
    ("22u 10V", "C_0805_2012Metric"): ("C", "22u", "0805", 10, XR),
    ("10u 10V", "C_0805_2012Metric"): ("C", "10u", "0805", 10, XR),
    ("10n", "C_0402_1005Metric"): ("C", "10n", "0402", 16, XR),
    ("47u", "C_1206_3216Metric"): ("C", "47u", "1206", 6.3, XR),     # -3V3 pump
    ("4.7u", "C_0805_2012Metric"): ("C", "4.7u", "0805", 10, XR),
    ("0.47u", "C_0603_1608Metric"): ("C", "470n", "0603", 10, XR),
    ("100u", "C_1210_3225Metric"): ("C", "100u", "1210", 6.3, XR),   # +1V0
    ("47u", "C_1210_3225Metric"): ("C", "47u", "1210", 6.3, XR),     # up to +3V3_D
    ("470n", "C_0603_1608Metric"): ("C", "470n", "0603", 10, XR),
    ("330u", "CP_EIA-7343-20_Kemet-V"): ("P", "T520V337M006ATE", r"^T520V337M\d+ATE"),
    ("4x22", "R_Array_Convex_4x0402"): ("P", "22Ω 0402x4 resistor array", r"4D02|0402.?4|CRA04|YC124|EXB28V220|CAY16"),
    ("5.6V", "D_SOD-123"): ("P", "MMSZ5232B", r"^MMSZ5232B"),
    ("15V", "D_SOD-123"): ("P", "MMSZ5245B", r"^MMSZ5245B"),
    ("SMBJ15CA", "D_SMB"): ("P", "SMBJ15CA", r"^SMBJ15CA"),
    ("SMBJ18CA", "D_SMB"): ("P", "SMBJ18CA", r"^SMBJ18CA"),
    ("SMCJ33CA", "D_SMC"): ("P", "SMCJ33CA", r"^SMCJ33CA"),
    ("DMT10H015LFG", "Diodes_PowerDI3333-8"): ("P", "DMT10H015LFG", r"^DMT10H015LFG-7"),
    ("LM74502-Q1", "SOT-23-8"): ("P", "LM74502QDDFRQ1", r"^LM74502QDDFRQ1"),
    ("100n 100V", "C_0603_1608Metric"): ("C", "100n", "0603", 100, XR),
    ("green", "LED_0603_1608Metric"): ("P", "KT-0603G", r"^KT-0603G$"),
    ("PTC 1.5A hold", "Fuse_1812_4532Metric"): ("P", "1812 PTC 1.5A", r"(150|1\.5)"),
    ("PTC 0.5A hold", "Fuse_1206_3216Metric"): ("P", "SMD1206P050TF", r"^(SMD1206P050|1206L050|BSMD1206-050)"),
    ("FAN 5V", "JST_PH_B2B-PH-K_1x02_P2.00mm_Vertical"): ("P", "B2B-PH-K-S", r"^B2B-PH-K-S"),
    # FB401 was "600R@100MHz >=1A" until 14 Nov; it now shares the 220R@100MHz line (2 A, 0.1 ohm)
    ("600R@100MHz", "L_0603_1608Metric"): ("FB", 600, "0603", 1.0),
    ("220R@100MHz", "L_0603_1608Metric"): ("FB", 220, "0603", 1.0),
    ("270n", "L_0603_1608Metric"): ("P", "LQW18ANR27G", r"^LQW18ANR27G"),  # DAC filters, 100 ohm Butterworth
    ("SRP7028A-8R2M", "L_Bourns_SRP7028A_7.3x6.6mm"): ("P", "SRP7028A-8R2M", r"^SRP7028A-8R2M"),
    ("SRP7028A-3R3M", "L_Bourns_SRP7028A_7.3x6.6mm"): ("P", "SRP7028A-3R3M", r"^SRP7028A-3R3M"),
    ("SRP7028A-2R2M", "L_Bourns_SRP7028A_7.3x6.6mm"): ("P", "SRP7028A-2R2M", r"^SRP7028A-2R2M"),
    ("DMP3013SFV", "Diodes_PowerDI3333-8"): ("P", "DMP3013SFV", r"^DMP3013SFV-7$"),
    ("2N7002", "SOT-23"): ("P", "2N7002", r"^2N7002(LT1G|-7-F|,215|K|$)"),
    ("BM20B(0.8)-34DP", "J-BM20B(0.8)-34DP"): ("P", "BM20B(0.8)-34DP", r"^BM20B\(0\.8\)-34DP"),
    ("SMA", "SMA_Samtec_SMA-J-P-H-ST-EM1_EdgeMount"): ("P", "SMA-J-P-H-ST-EM1", r"^SMA-J-P-H-ST-EM1"),
    ("12V IN", "BarrelJack_CUI_PJ-102AH_Horizontal"): ("P", "PJ-102AH", r"^PJ-102AH"),
    ("JTAG 2x7 2mm", "PinHeader_2x07_P2.00mm_Vertical"): ("P", "87832-1420", r"^0?87832-?1420"),
    ("Pmod", "PinHeader_2x06_P2.54mm_Vertical"): ("P", "HX PZ2.54-2x6P ZZ", r"^HX PZ2\.54-2x6P ZZ$"),
    ("AERIS ADAR", "IDC-Header_2x20_P2.54mm_Vertical"): ("P", "IDC 40P 2.54mm", r".", r"2x20P.*IDC Header Through Hole"),
    ("PROG", "SW_SPST_TL3342"): ("P", "TL3342", r"^TL3342"),
    ("ADT2-1T+", "Mini-Circuits_CD542_H2.84mm"): ("P", "ADT2-1T+", r"^ADT2-1T"),
    ("ADCLK948BCPZ", "LFCSP-32-1EP_5x5mm_P0.5mm_EP2.7x2.7mm"): ("P", "ADCLK948", r"^ADCLK948BCPZ"),
    ("AD9484BCPZ-500", "LFCSP-56-1EP_8x8mm_P0.5mm_EP5.1x5.1mm"): ("P", "AD9484", r"^AD9484BCPZ-500"),
    ("AD8352ACPZ", "LFCSP-16-1EP_3x3mm_P0.5mm_EP1.6x1.6mm"): ("P", "AD8352", r"^AD8352ACPZ"),
    ("AD9253BCPZ-125", "QFN-48-1EP_7x7mm_P0.5mm_EP5.6x5.6mm"): ("P", "AD9253", r"^AD9253BCPZ-125"),
    ("AD9708AR", "SOIC-28W_7.5x17.9mm_P1.27mm"): ("P", "AD9708", r"^AD9708ARZ"),
    ("AD9767ASTZ", "LQFP-48_7x7mm_P0.5mm"): ("P", "AD9767", r"^AD9767ASTZ"),
    ("M3SWA2-34DR+", "MiniCircuits_DQ3005"): ("P", "M3SWA2-34DR+", r"^M3SWA2-34DR"),
    ("LMR33630ADDA", "Texas_HSOP-8-1EP_3.9x4.9mm_P1.27mm"): ("P", "LMR33630ADDA", r"^LMR33630ADDA"),
    ("TPS562201", "SOT-23-6"): ("P", "TPS562201", r"^TPS562201DDC"),
    ("TPS7A8300RGR", "QFN-20-1EP_3.5x3.5mm_P0.5mm_EP2x2mm"): ("P", "TPS7A8300RGR", r"^TPS7A8300RGR"),
    ("LM2663M", "SOIC-8_3.9x4.9mm_P1.27mm"): ("P", "LM2663M", r"^LM2663MX?/NOPB"),
    ("XC7A50T-2FTG256I", "Xilinx_FTG256"): ("P", "XC7A50T-2FTG256I", r"^XC7A50T-2FTG256I"),
    ("MT25QL128ABA1ESE", "SOIC-8_5.3x5.3mm_P1.27mm"): ("P", "MT25QL128ABA1ESE", r"^MT25QL128ABA1ESE"),
    ("74LVC1G07", "SOT-23-5"): ("P", "SN74LVC1G07DBVR", r"^SN74LVC1G07DBVR$"),   # TI's, not a "-JSM" second source
    ("TMP1075DR", "SOIC-8_3.9x4.9mm_P1.27mm"): ("P", "TMP1075DR", r"^TMP1075DR"),
    ("M24C02-FMN6TP", "SOIC-8_3.9x4.9mm_P1.27mm"): ("P", "M24C02-FMN6TP", r"^M24C02-FMN6TP"),
    # the Ethernet PHY (13 Nov 2026, CONTROL_SPEC section 7)
    ("RTL8211FSI-CG", "QFN-48-1EP_6x6mm_P0.4mm_EP4.4x4.4mm"): ("P", "RTL8211FSI-CG", r"^RTL8211FSI-CG"),
    ("HR911130C", "RJ45_Hanrun_HR911130C"): ("P", "HR911130C", r"^HR911130C"),
    ("25MHz", "Crystal_SMD_3225-4Pin_3.2x2.5mm"): ("P", "X322525MOB4SI", r"^X322525MOB4SI"),
    # the PHY's 1.0 V buck (< 0.3 A): a power inductor by name; the L rule picked a 50 mA signal part
    ("2.2u", "L_0805_2012Metric"): ("P", "DFE201210U-2R2M", r"^DFE201210U-2R2M"),
    ("4.7u", "C_0402_1005Metric"): ("C", "4.7u", "0402", 6.3, XR),    # PHYRSTB delay, +3V3_D
    # Rev08 (17 Nov 2026): the VHF/UHF receiver (RX_VU_SPEC) and the STATUS sheet.
    # The filters' inductors are Murata LQW wirewounds, 2 % (Q 40-45, what rev08_filters_mc.py assumed).
    ("16n", "L_0402_1005Metric"): ("P", "LQW15AN16NG", r"^LQW15AN16NG"),
    ("22n", "L_0402_1005Metric"): ("P", "LQW15AN22NG", r"^LQW15AN22NG"),
    ("27n", "L_0402_1005Metric"): ("P", "LQW15AN27NG", r"^LQW15AN27NG"),
    ("56n", "L_0402_1005Metric"): ("P", "LQW15AN56NG", r"^LQW15AN56NG"),
    ("62n", "L_0402_1005Metric"): ("P", "LQW15AN62NG", r"^LQW15AN62NG"),
    ("68n", "L_0402_1005Metric"): ("P", "LQW15AN68NG", r"^LQW15AN68NG"),
    ("75n", "L_0402_1005Metric"): ("P", "LQW15AN75NG", r"^LQW15AN75NG"),
    ("82n", "L_0402_1005Metric"): ("P", "LQW15AN82NG", r"^LQW15AN82NG"),
    ("100n", "L_0402_1005Metric"): ("P", "LQW15ANR10J", r"^LQW15ANR10J00D"),   # the 2 % part is not stocked
    ("0.47u", "C_0402_1005Metric"): ("C", "470n", "0402", 10, XR),
    ("PESD5V0F1BL", "D_SOD-882"): ("P", "PESD5V0F1BL", r"^PESD5V0F1BL"),
    ("TPD4E05U06DQAR", "USON-10_2.5x1.0mm_P0.5mm"): ("P", "TPD4E05U06DQAR", r"^TPD4E05U06DQAR"),
    ("220n", "L_0603_1608Metric"): ("P", "LQW18ANR22G", r"^LQW18ANR22G"),
    ("390n", "L_0603_1608Metric"): ("P", "LQW18ANR39G", r"^LQW18ANR39G"),
    ("TA1090EC", "FILTER-SMD_6P-L3.8-W3.8-P1.27-TL-3"): ("P", "TA1090EC", r"^TA1090EC"),
    ("HFCN-1000+", "FILTER-SMD_1206-4P-L3.2-W1.6-L"): ("P", "HFCN-1000+", r"^HFCN-1000"),
    ("LFCN-1000+", "FILTER-SMD_1206-4P-L3.2-W1.6-L"): ("P", "LFCN-1000+", r"^LFCN-1000"),
    ("TC1-1-13M+", "XFMR-SMD_TC1-1TX"): (
        "X", "Mini-Circuits TC1-1-13M+ only: LCSC's H3-TC1-1-13M+ clone has another pin-out (RX_VU_SPEC); consign it"),
    ("TC4-1W+", "XFMR-SMD_TC1-1TX"): ("P", "TC4-1W+", r"^TC4-1W"),
    ("SPF5043Z", "SOT343_L2.0-W1.3-P1.30-LS2.1-BL"): ("P", "SPF5043Z", r"^SPF5043Z"),
    ("PE4259", "SC-70-6_L2.2-W1.3-P0.65-LS2.1-BL"): ("P", "PE4259", r"^PE4259"),
    ("PE42442", "QFN-24_L4.0-W4.0-P0.50-BL-EP2.8"): ("P", "PE42442", r"^PE42442"),
    ("SKY13418-485LF", "QFN-14_L2.0-W2.0-P0.45-BL-EP"): ("P", "SKY13418-485LF", r"^SKY13418-485LF"),
    ("PE4312", "QFN-20_L4.0-W4.0-P0.50-BL-EP2.2"): ("P", "PE4312", r"^PE4312"),
    ("RFFC5072", "QFN-32-1EP_5x5mm_P0.5mm_EP3.45x3.45mm"): ("P", "RFFC5072", r"^RFFC5072"),
    ("26MHz 1XXD26000MAA", "OSC-SMD_4P-L2.0-W1.6-BL"): ("P", "1XXD26000MAA", r"^1XXD26000MAA"),
    ("TCA6416ARTWR", "WQFN-24_L4.0-W4.0-P0.50-TL-EP2.5"): ("P", "TCA6416ARTWR", r"^TCA6416ARTWR"),
    ("AP22652W6-7", "SOT-23-6_L2.9-W1.6-P0.95-LS2.8-BL"): ("P", "AP22652W6-7", r"^AP22652W6-7"),
    ("LP5907MFX-3.0", "SOT-23-5"): ("P", "LP5907MFX-3.0", r"^LP5907MFX-3\.0"),
    ("LP5907MFX-3.3", "SOT-23-5"): ("P", "LP5907MFX-3.3", r"^LP5907MFX-3\.3"),
    ("BM20B(0.8)-34DS-0.4V(51)", "CONN-SMD_34P-P0.40_BM20B-0.8-34DS-0.4V-51"): (
        "P", "BM20B(0.8)-34DS-0.4V", r"^BM20B\(0\.8\)-34DS-0\.4V"),
    ("HX-TYPE-C 16P 180 LT H10.0", "USB_C_HX_16P_180_LT_H10"): (
        "P", "HX-TYPE-C 16P 180 LT H10.0", r"^HX-TYPE-C 16P 180 LT H10"),
    ("TYPE-C-31-E-17", "USB_C_HRO_TYPE-C-31-E-17"): ("P", "TYPE-C-31-E-17", r"^TYPE-C-31-E-17$"),
    ("FPC-1.0FX-15PWCR-H20", "FPC_1.0_15P_XUNPU_FPC-1.0FX-15PWCR-H20"): (
        "P", "FPC-1.0FX-15PWCR-H20", r"^FPC-1\.0FX-15PWCR-H20$"),
    ("SM04B-SRSS-TB", "JST_SH_SM04B-SRSS-TB_1x04-1MP_P1.00mm_Horizontal"): (
        "P", "SM04B-SRSS-TB", r"^SM04B-SRSS-TB\(LF\)\(SN\)$"),
    ("SN74LVC1G17DCKR", "SOT-353_SC-70-5"): ("P", "SN74LVC1G17DCKR", r"^SN74LVC1G17DCKR$"),
    ("SM06B-SRSS-TB", "JST_SH_SM06B-SRSS-TB_1x06-1MP_P1.00mm_Horizontal"): (
        "P", "SM06B-SRSS-TB", r"^SM06B-SRSS-TB\(LF\)\(SN\)$"),
    ("BM06B-SRSS-TB", "JST_SH_BM06B-SRSS-TB_1x06-1MP_P1.00mm_Vertical"): (
        "P", "BM06B-SRSS-TB", r"^BM06B-SRSS-TB\(LF\)\(SN\)$"),
    ("TCAN330DCNT", "SOT-23-8"): ("P", "TCAN330DCNT", r"^TCAN330DCN[TR]$"),
    ("PESD1CAN", "SOT-23"): ("P", "PESD1CAN", r"^PESD1CAN(,215|-U)?$"),
    ("PTC 0.2A hold", "Fuse_0805_2012Metric"): ("P", "JK-SMD0805-020", r"^JK-SMD0805-020"),
    ("CH340X", "MSOP-10_L3.0-W3.0-P0.50-LS5.0-BL"): ("P", "CH340X", r"^CH340X$"),
    ("USBLC6-2SC6", "SOT-23-6"): ("P", "USBLC6-2SC6", r"^USBLC6-2SC6"),
    ("MMBT3904", "SOT-23"): ("P", "MMBT3904", r"^MMBT3904(LT1G|-7-F|,215|$)"),
    ("Si549 LVPECL 3V3 pinout C", "Oscillator_SMD_SI570_SI571_Standard"): (
        "X", "Si549 ordering codes are built per configuration at Skyworks; not a catalogue part"),
}
# Where the part is not the drawn value, and why. Copied into the CSV's Note.
NOTES = {
    ("100n", "L_0402_1005Metric"): "LQW15ANR10G (2 %) is not stocked; the 5 % part, as rev08_filters_mc.py allowed for the 390 nH",
    ("330u", "CP_EIA-7343-20_Kemet-V"): "UG483 names T520V337M2R5ATE025 (2.5 V); the 6.3 V of the same "
                                        "series and case is what JLCPCB stocks",
}
SMA_NAMES = ("CLK_REF_IN", "CLK_OUT", "SDR_", "AERIS_", "VU_")
LED_COLOURS = ("green", "yellow", "red", "blue")


def rule_for(comment, fp):
    if fp.startswith("SMA_") and comment.startswith(SMA_NAMES):
        return RULES[("SMA", fp)]
    if fp == "LED_0402_1005Metric" and comment.split()[-1] in LED_COLOURS:
        return ("LED", comment.split()[-1], "0402")      # STATUS sheet: "<name> <colour>"
    if fp == "C_0402_1005Metric" and re.match(r"^[\d.]+p$", comment) and (comment, fp) not in RULES:
        return ("C", comment, "0402", 25, C0G)            # any small capacitor: C0G
    if comment == "0" and fp.startswith("R_0402"):
        return ("J", "0402")
    if fp.startswith("R_0402") and comment != "4x22":
        return ("R", comment.split()[0], "0402")
    if fp.startswith("R_0603"):
        return ("R", comment.split()[0], "0603")
    return RULES.get((comment, fp))


# ---------------------------------------------------------------- search
def search(keyword, pages=3, size=100):
    out = []
    for page in range(1, pages + 1):
        body = json.dumps({"keyword": keyword, "currentPage": page, "pageSize": size}).encode()
        req = urllib.request.Request(API, data=body, headers={
            "Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
        for attempt in range(4):
            try:
                d = json.load(urllib.request.urlopen(req, timeout=60))
                break
            except Exception:                       # noqa: BLE001
                if attempt == 3:
                    raise
                time.sleep(5 * (attempt + 1))
        info = (d.get("data") or {}).get("componentPageInfo") or {}
        lst = info.get("list") or []
        out += lst
        if len(out) >= (info.get("total") or 0) or not lst:
            break
        time.sleep(0.5)
    return out


def attrs(c):
    return {a.get("attribute_name_en"): a.get("attribute_value_name") for a in c.get("attributes") or []}


def package_of(c):
    return (c.get("componentSpecificationEn") or "").upper()


def rank(c):
    return (c.get("componentLibraryType") != "base", not c.get("preferredComponentFlag"),
            -(c.get("stockCount") or 0))


def pick(rule):
    kind = rule[0]
    if kind == "X":
        return None, rule[1]
    if kind == "C":
        _, val, pkg, min_v, diel = rule
        want = num(val, "F")
        kw = f"{val}F {pkg} " + ("C0G" if diel == C0G else "")
        ok = []
        for c in search(kw.strip()):
            a = attrs(c)
            v = num(a.get("Voltage Rating", ""), "V")
            tc = (a.get("Temperature Coefficient") or "").upper()
            if (package_of(c) == pkg and close(num(a.get("Capacitance", ""), "F"), want)
                    and v is not None and v >= min_v and any(d in tc for d in diel)):
                ok.append(c)
        why = f"no {val} {pkg} {'/'.join(diel[:2])} >= {min_v} V"
    elif kind == "R":
        _, val, pkg = rule
        want = num(val, "Ω")
        ok = []
        for c in search(f"{val}Ω {pkg} 1%"):
            a = attrs(c)
            if (package_of(c) == pkg and close(num(a.get("Resistance", ""), "Ω"), want)
                    and (a.get("Tolerance") or "").strip() in ("±1%", "±0.5%", "±0.1%")):
                ok.append(c)
        why = f"no {val} {pkg} 1 %"
    elif kind == "L":
        _, val, pkg, min_i = rule
        want = num(val, "H")
        ok = [c for c in search(f"{val}H {pkg} inductor")
              if package_of(c) == pkg and close(num(attrs(c).get("Inductance", ""), "H"), want)]
        why = f"no {val}H {pkg}"
    elif kind == "FB":
        _, z, pkg, min_i = rule
        ok = []
        for c in search(f"{z}Ω@100MHz {pkg} ferrite bead"):
            a = attrs(c)
            zz = num(a.get("Impedance @ Frequency", "") or "", "Ω")
            i = num(a.get("Current Rating", "") or "", "A")
            if package_of(c) == pkg and close(zz, z, 0.01) and i is not None and i >= min_i:
                ok.append(c)
        why = f"no {z} ohm {pkg} bead >= {min_i} A"
    elif kind == "LED":
        _, colour, pkg = rule
        ok = [c for c in search(f"{pkg} LED", pages=4)          # the colour in the keyword returns other parts
              if package_of(c) == pkg and (attrs(c).get("Illumination Color") or "").lower() == colour]
        if colour == "green":   # AlGaInP yellow-green (about 2 V), not InGaN (about 3 V): the rail LEDs and the
            # status LEDs run from 3.3 V through a resistor, and +1V8_D's from 1.8 V (REV08_PLAN section 3.1)
            ok = [c for c in ok if (num(attrs(c).get("Wavelength - Dominant") or "", "nm") or 0) >= 560e0]
        why = f"no {pkg} {colour} LED"
    elif kind == "J":
        _, pkg = rule
        ok = [c for c in search(f"0Ω {pkg} resistor")
              if package_of(c) == pkg and num(attrs(c).get("Resistance", "") or "x", "Ω") == 0]
        why = f"no {pkg} 0 ohm jumper"
    else:                                           # P
        kw, pat, desc = rule[1], rule[2], (rule[3] if len(rule) > 3 else ".")
        ok = [c for c in search(kw, pages=1, size=50)
              if re.search(pat, c.get("componentModelEn") or "", re.I)
              and re.search(desc, c.get("describe") or "", re.I)]
        why = f"no part matching {pat} for '{kw}'"
    ok = [c for c in ok if (c.get("stockCount") or 0) > 0] or ok
    if not ok:
        return None, why
    return sorted(ok, key=rank)[0], ""


def main():
    only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else None
    # the newest BOM by time: by name, DRAFT-... folders would sort after the real ones
    bom = max(glob.glob(os.path.join(ROOT, "fab", "*", "*-BOM.csv")), key=os.path.getmtime)
    rows = list(csv.reader(open(bom, encoding="utf-8")))[1:]
    keep = {}
    if os.path.exists(OUT) and only:
        for r in csv.DictReader(open(OUT, encoding="utf-8")):
            keep[(r["Comment"], r["Footprint"])] = r
    today = datetime.date.today().isoformat()
    out = []
    for comment, refs, fp, _, qty in rows:
        key = (comment, fp)
        if only and f"{comment}|{fp}" != only and key in keep:
            out.append({**keep[key], "Qty": qty})        # the part kept, the count from this BOM
            continue
        rule = rule_for(comment, fp)
        if rule is None:
            c, why = None, "no rule in lcsc_select.py"
        else:
            c, why = pick(rule)
        row = {"Comment": comment, "Footprint": fp, "Qty": qty, "LCSC": "", "MPN": "",
               "Manufacturer": "", "Description": "", "Library": "", "Stock": "",
               "Searched": today, "Note": NOTES.get(key, why)}
        if c:
            row.update(LCSC=c["componentCode"], MPN=c.get("componentModelEn") or "",
                       Manufacturer=c.get("componentBrandEn") or "",
                       Description=c.get("describe") or "",
                       Library={"base": "basic", "expand": "extended"}.get(
                           c.get("componentLibraryType"), c.get("componentLibraryType") or ""),
                       Stock=c.get("stockCount") or 0)
        out.append(row)
        print(f"  {row['LCSC'] or '-':10s} {row['Library']:9s} {str(row['Stock']):>9s}  "
              f"{comment[:22]:22s} {row['MPN'][:28]:28s} {row['Note']}")
        time.sleep(0.3)
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    n = sum(1 for r in out if r["LCSC"])
    print(f"\n{n} of {len(out)} lines have a part; wrote {os.path.relpath(OUT, ROOT)}")


if __name__ == "__main__":
    main()
