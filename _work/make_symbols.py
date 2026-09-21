#!/usr/bin/env python3
"""
Build a project symbol library with CORRECT pin electrical types.

The point of this exercise is ERC. A symbol whose pins are all `unspecified`
makes ERC blind - that is what produced the 48 uninterpretable `pin_to_pin`
conflicts in the Rev01 work (docs/AUDIT_Rev01.md §2.2). So every pin here
carries a real type.

WHERE THE DATA COMES FROM, AND HOW FAR TO TRUST IT
--------------------------------------------------
analog.com would not serve its datasheets from this machine (repeated 60 s
timeouts; mirrors return 403 and 410), so the pin tables could not be taken
from the primary source. They are taken instead from the **Eagle library of the
AERIS-10 project**, whose boards were fabricated and measured. That is good
evidence - a wrong pinout there would have shown up as a dead board - but it is
**second-hand**, and each symbol says so in its description.

Eagle records a direction per pin, which is exactly the information KiCad needs:

    in  -> input        out -> output       io  -> bidirectional
    pwr -> power_in     sup -> power_out    pas -> passive
    oc  -> open_collector                   hiz -> tri_state
    nc  -> no_connect

Parts already covered by KiCad's own official libraries are NOT rebuilt here.
Those are maintained and verified, and duplicating them would only create a
second version to drift:

    XC7A50T-FTG256   FPGA_Xilinx_Artix7    front-end FPGA, 256 pins, 4 units
    AD9708AR         Video                 radar DAC
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
# Both datasheets were read locally from the AERIS-10 repository at
#   <PLFM_RADAR>/7_Components Datasheets and Application notes/
# because analog.com would not serve its PDFs from this machine.
#
# (pad, name, kicad_type)
# ---------------------------------------------------------------------------

DATASHEET_PINS = {
    # M3SWA2-34DR+.pdf, "FUNCTIONAL DIAGRAM" and "DC ELECTRICAL SPECIFICATIONS".
    # 16-lead QFN, 3x3 mm.
    #
    # NOTE THE SUPPLIES. This part needs BOTH VDD = +3.3 V and VEE = -3.3 V.
    # Its control logic is positive (VCTRL low 0..+0.8 V, high +2..+3.6 V),
    # which is what made an earlier reading of a search snippet conclude that
    # no negative rail was needed. The datasheet is explicit: "VDD = +3.3 V,
    # VEE = -3.3 V". Positive control, bipolar supply.
    #   IDD 1.6 mA typ, 2.9 mA max;  IEE 0 mA typ, 1.8 mA max.
    "M3SWA2-34DR": [
        ("1",  "NC",    "no_connect"),
        ("2",  "GND",   "power_in"),
        ("3",  "RF1",   "passive"),
        ("4",  "GND",   "power_in"),
        ("5",  "VEE",   "power_in"),
        ("6",  "VCTRL", "input"),
        ("7",  "GND",   "power_in"),
        ("8",  "VDD",   "power_in"),
        ("9",  "GND",   "power_in"),
        ("10", "RF2",   "passive"),
        ("11", "GND",   "power_in"),
        ("12", "NC",    "no_connect"),
        ("13", "NC",    "no_connect"),
        ("14", "GND",   "power_in"),
        ("15", "RFC",   "passive"),
        ("16", "GND",   "power_in"),
    ],

    # LTC5552f.pdf, "PIN CONFIGURATION" and "PIN FUNCTIONS".
    # 12-lead 3x2 mm QFN (UDB), exposed pad is pin 13 and is GND.
    # VCC is a regulated 3.3 V, 132 mA typical when enabled.
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
}

DATASHEET_NOTE = {
    "M3SWA2-34DR": "Pin table from the Mini-Circuits M3SWA2-34DR+ datasheet. "
                   "Needs BOTH VDD +3.3 V and VEE -3.3 V; control logic is positive.",
    "LTC5552": "Pin table from the Analog Devices LTC5552 datasheet (LTC5552f). "
               "VCC 3.3 V, 132 mA typical enabled. Exposed pad (pin 13) is GND.",
}


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


def emit_symbol(libname, desc, pins, source_note):
    """A KiCad symbol: power on top/bottom, inputs left, outputs right."""
    def bucket(t, name):
        if t in ("power_in", "power_out"):
            return "gnd" if re.search(r"(?i)^(gnd|vee|vss|agnd|dgnd|epad|ep)$", name) else "pwr"
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

    n_side = max(len(groups["left"]), len(groups["right"]), 1)
    n_tb = max(len(groups["pwr"]), len(groups["gnd"]) + len(groups["nc"]), 1)
    half_h = max(n_side, 4) * 2.54 / 2 + 2.54
    half_w = max(n_tb, 4) * 2.54 / 2 + 2.54
    half_w = max(half_w, 25.4)

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

    y = (len(groups["left"]) - 1) * 2.54 / 2
    for pad, name, t in groups["left"]:
        add(pad, name, t, -half_w - 2.54, y, 0); y -= 2.54
    y = (len(groups["right"]) - 1) * 2.54 / 2
    for pad, name, t in groups["right"]:
        add(pad, name, t, half_w + 2.54, y, 180); y -= 2.54
    x = -(len(groups["pwr"]) - 1) * 2.54 / 2
    for pad, name, t in groups["pwr"]:
        add(pad, name, t, x, half_h + 2.54, 270); x += 2.54
    bottom = groups["gnd"] + groups["nc"]
    x = -(len(bottom) - 1) * 2.54 / 2
    for pad, name, t in bottom:
        add(pad, name, t, x, -half_h - 2.54, 90); x += 2.54

    L.append(f'{TAB}{TAB})')
    L.append(f'{TAB})')
    return NL.join(L)


def main():
    print("Building the project symbol library")
    print()
    print("Already covered by KiCad's official libraries, not rebuilt:")
    print("    XC7A50T-FTG256   FPGA_Xilinx_Artix7")
    print("    AD9708AR         Video")
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
    import collections
    for ds, pins in sorted(all_pins.items()):
        name, desc = WANTED[ds]
        tag = "datasheet" if name in DATASHEET_PINS else "eagle    "
        if name in DATASHEET_PINS:
            pins = DATASHEET_PINS[name]
        types = collections.Counter(t for _, _, t in pins)
        print(f"  [{tag}] {name:18s} {len(pins):3d} pins   "
              + "  ".join(f"{t}:{c}" for t, c in types.most_common()))
    if missing:
        print(f"\n  NOT FOUND in the Eagle sources: {missing}")

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
    for ds, pins in sorted(all_pins.items()):
        name, desc = WANTED[ds]
        if name in DATASHEET_PINS:
            pins = DATASHEET_PINS[name]
            src = DATASHEET_NOTE[name]
        else:
            src = note
        body.append(emit_symbol(name, desc, pins, src))
    body.append(')')

    with open(OUT_LIB, "w", encoding="utf-8", newline=NL) as fh:
        fh.write(NL.join(body) + NL)
    print(f"\nwrote {os.path.relpath(OUT_LIB, ROOT)}  ({len(all_pins)} symbols)")
    print("Verify with:  kicad-cli sym upgrade / sym export svg")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
