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
    ("33p", "C_0402_1005Metric"): ("C", "33p", "0402", 25, C0G),
    ("27p", "C_0402_1005Metric"): ("C", "27p", "0402", 25, C0G),       # Y1201 load
    ("106p", "C_0402_1005Metric"): ("C", "110p", "0402", 25, C0G),       # see NOTES
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
    ("green", "LED_0603_1608Metric"): ("P", "KT-0603G", r"^KT-0603G$"),
    ("PTC 1.5A hold", "Fuse_1812_4532Metric"): ("P", "1812 PTC 1.5A", r"(150|1\.5)"),
    ("600R@100MHz >=1A", "L_0603_1608Metric"): ("FB", 600, "0603", 1.0),
    ("600R@100MHz", "L_0603_1608Metric"): ("FB", 600, "0603", 1.0),
    ("220R@100MHz", "L_0603_1608Metric"): ("FB", 220, "0603", 1.0),
    ("107.3n", "L_0603_1608Metric"): ("P", "LQW18ANR11G", r"^LQW18ANR11G"),  # see NOTES
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
    ("74LVC1G07", "SOT-23-5"): ("P", "SN74LVC1G07DBVR", r"^SN74LVC1G07DBV"),
    ("TMP1075DR", "SOIC-8_3.9x4.9mm_P1.27mm"): ("P", "TMP1075DR", r"^TMP1075DR"),
    ("M24C02-FMN6TP", "SOIC-8_3.9x4.9mm_P1.27mm"): ("P", "M24C02-FMN6TP", r"^M24C02-FMN6TP"),
    # the Ethernet PHY (13 Nov 2026, CONTROL_SPEC section 7)
    ("RTL8211FSI-CG", "QFN-48-1EP_6x6mm_P0.4mm_EP4.4x4.4mm"): ("P", "RTL8211FSI-CG", r"^RTL8211FSI-CG"),
    ("HR911130C", "RJ45_Hanrun_HR911130C"): ("P", "HR911130C", r"^HR911130C"),
    ("25MHz", "Crystal_SMD_3225-4Pin_3.2x2.5mm"): ("P", "X322525MOB4SI", r"^X322525MOB4SI"),
    # the PHY's 1.0 V buck (< 0.3 A): a power inductor by name; the L rule picked a 50 mA signal part
    ("2.2u", "L_0805_2012Metric"): ("P", "DFE201210U-2R2M", r"^DFE201210U-2R2M"),
    ("4.7u", "C_0402_1005Metric"): ("C", "4.7u", "0402", 6.3, XR),    # PHYRSTB delay, +3V3_D
    ("Si549 LVPECL 3V3 pinout C", "Oscillator_SMD_SI570_SI571_Standard"): (
        "X", "Si549 ordering codes are built per configuration at Skyworks; not a catalogue part"),
}
# Where the part is not the drawn value, and why. Copied into the CSV's Note.
NOTES = {
    ("106p", "C_0402_1005Metric"): "106 pF (AERIS C141) is not made; nearest E24 value 110 pF (+3.8 %). "
                                   "Or fit 100 pF and add 5.6 pF by hand",
    ("107.3n", "L_0603_1608Metric"): "107.3 nH (AERIS L22) is not made; nearest 110 nH +-2 % (+2.5 %), "
                                     "Murata LQW18 wire-wound",
    ("330u", "CP_EIA-7343-20_Kemet-V"): "UG483 names T520V337M2R5ATE025 (2.5 V); the 6.3 V of the same "
                                        "series and case is what JLCPCB stocks",
}
SMA_NAMES = ("CLK_REF_IN", "CLK_OUT", "SDR_", "AERIS_")


def rule_for(comment, fp):
    if fp.startswith("SMA_") and comment.startswith(SMA_NAMES):
        return RULES[("SMA", fp)]
    if fp.startswith("R_0402") and comment != "4x22":
        return ("R", comment.split()[0], "0402")
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
