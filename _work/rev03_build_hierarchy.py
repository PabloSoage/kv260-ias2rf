#!/usr/bin/env python3
"""
DO NOT RE-RUN. This script built the Rev03 hierarchy once (commit eae6713).
Running it again would add a second set of sheet blocks to the root and
overwrite the drawn sheets (rev03/CLOCK.kicad_sch since 23 September).
Its tables are kept in step with the design as the record of intent;
interface changes are applied by small scripts such as
_work/rev03_clock_interface.py, followed by _work/sync_sheet_pins.py.

Build the Rev03 sheet hierarchy: sheets and their interfaces, nothing else.

WHY THIS IS NOT THE THING THE AUDIT WARNED ABOUT
------------------------------------------------
docs/AUDIT_Rev01.md §8 says not to generate schematics by script, and that
still holds. The reason it holds is specific: script-generated *circuits* made
of untyped EasyEDA symbols wired with auto-generated labels cannot be reviewed
by eye, and ERC cannot check them because the pins carry no electrical type.

This script generates **no symbols and no wires**. It produces the sheet
structure and the hierarchical labels that define what crosses between sheets.
There is nothing here that can be mis-typed, and the result is exactly what ERC
*can* verify: that every sheet pin in the root matches a hierarchical label in
its child, by name and by direction. The circuit itself gets drawn in the GUI.

Power is deliberately absent from the interfaces. Rails travel as global power
symbols, the way the inherited design already does it, not as hierarchical
labels — that keeps the sheet interfaces to signals and stops the label list
from drowning in copies of GND.

The interface below is the one frozen in docs/INTERFACE_SPEC.md.

Usage:  py _work/rev03_build_hierarchy.py [--dry-run]
"""

import json
import os
import sys
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRO = os.path.join(ROOT, "CSI2-KRIA-KV260_Rev01.kicad_pro")
ROOT_SCH = os.path.join(ROOT, "CSI2-KRIA-KV260_Rev01.kicad_sch")
DRY = "--dry-run" in sys.argv

NS = uuid.UUID("6b1f0c2e-5a4d-4e8b-9c3a-7d2e1f0a4b56")     # stable UUIDs


def uid(*parts):
    return str(uuid.uuid5(NS, "|".join(parts)))


# --------------------------------------------------------------------------
# The interface. (name, direction) where direction is from the sheet's view.
# --------------------------------------------------------------------------

LINK_TO_KRIA = [                       # FPGA -> Kria
    "LINK_RX_D0_P", "LINK_RX_D0_N",
    "LINK_RX_D1_P", "LINK_RX_D1_N",
    "LINK_RX_CLK_P", "LINK_RX_CLK_N",
]
LINK_FROM_KRIA = [                     # Kria -> FPGA
    "LINK_TX_D0_P", "LINK_TX_D0_N",
    "LINK_TX_CLK_P", "LINK_TX_CLK_N",
]

# 24 Sep: the ADCR data bus became one label per line (ADCR_D0_P ...), like
# ADCS_*: a drawn sheet then carries no bus, and every pair is checked by name.
ADCR_BITS = [(f"ADCR_D{i}_{pn}", "input") for i in range(8) for pn in "PN"]

CONV_DIGITAL = [                       # front-end FPGA <-> converters
    *ADCR_BITS,
    ("ADCR_DCO_P", "input"), ("ADCR_DCO_N", "input"),
    ("ADCR_OR_P", "input"), ("ADCR_OR_N", "input"),
    ("ADCS_D0_P", "input"), ("ADCS_D0_N", "input"),
    ("ADCS_D1_P", "input"), ("ADCS_D1_N", "input"),
    ("ADCS_DCO_P", "input"), ("ADCS_DCO_N", "input"),
    ("ADCS_FCO_P", "input"), ("ADCS_FCO_N", "input"),
    # DAC buses split into one label per line on 24 Sep, as ADCR's were.
    *[(f"DACR_D{i}", "output") for i in range(8)], ("DACR_CLK", "output"),
    *[(f"DACS_D{i}", "output") for i in range(14)],
    ("DACS_IQWRT", "output"), ("DACS_IQSEL", "output"),
    ("DACS_IQCLK", "output"), ("DACS_IQRESET", "output"),      # added 23 Sep
    ("CONV_SPI_SCLK", "output"), ("CONV_SPI_SDIO", "bidirectional"),
    ("CONV_SPI_CSB_R", "output"), ("CONV_SPI_CSB_S", "output"),
]

CLOCKS = [                             # CLOCK -> consumers
    "CLK_ADCR_P", "CLK_ADCR_N",
    "CLK_ADCS_P", "CLK_ADCS_N",
    # CLK_DAC_P/N removed 23 Sep: the DACs take CMOS clocks from the FPGA
    "CLK_FPGA_P", "CLK_FPGA_N",
]

# 24 Sep: single-ended 50 ohm, not differential pairs. The routing switches
# (M3SWA2, SPDT) and the SMAs are single-ended; the AD8352 drivers take a
# single-ended input (AD8352 datasheet Figure 26), and the DACs get a balun.
# IF_RX_C / IF_TX_C added the same day: the SDR converters are dual (AD9253
# channels A and B, AD9767 DACs 1 and 2), and the second channel needs a way out.
IF_RX = ["IF_RX_A",                    # SDR receive, AD9253 channel A
         "IF_RX_B",                    # radar IF into the 8-bit ADC
         "IF_RX_C"]                    # SDR receive, AD9253 channel B
IF_TX = ["IF_TX_A",                    # SDR transmit, AD9767 DAC 1
         "IF_TX_B",                    # radar chirp out of the DAC
         "IF_TX_C"]                    # SDR transmit, AD9767 DAC 2
IF_ANALOG = IF_RX + IF_TX


def flip(d):
    return {"input": "output", "output": "input"}.get(d, d)


SHEETS = {
    "IAS_LINK": {
        "file": "rev03/IAS_LINK.kicad_sch",
        "desc": "Hirose IAS1, AC coupling, link terminations",
        "at": (30.0, 40.0),
        "labels":
            [(n, "input") for n in LINK_TO_KRIA] +
            [(n, "output") for n in LINK_FROM_KRIA] +
            [("HK_SCL", "bidirectional"), ("HK_SDA", "bidirectional"),
             ("FPGA_PROG_B", "output"), ("FPGA_IRQ", "input")],
    },
    "CONTROL": {
        "file": "rev03/CONTROL.kicad_sch",
        "desc": "Front-end FPGA, Pmod, AERIS-10 control IDC",
        "at": (110.0, 40.0),
        "labels":
            [(n, "output") for n in LINK_TO_KRIA] +
            [(n, "input") for n in LINK_FROM_KRIA] +
            [("HK_SCL", "bidirectional"), ("HK_SDA", "bidirectional"),
             ("FPGA_PROG_B", "input"), ("FPGA_IRQ", "output")] +
            [(n, flip(d)) for n, d in CONV_DIGITAL] +
            [("CLK_FPGA_P", "input"), ("CLK_FPGA_N", "input")] +
            [(f"SW_CTRL{i}", "output") for i in range(4)] +
            [("CLK_SEL", "output"), ("XO_SCL", "output"), ("XO_SDA", "bidirectional")],
    },
    # CONVERTERS was split in four on 24 Sep (_work/rev03_split_converters.py):
    # one sheet held ~200 parts, too many to review in one sitting.
    "ADC_RADAR": {
        "file": "rev03/ADC_RADAR.kicad_sch",
        "desc": "AD9484 radar ADC, two AD8352 drivers",
        "at": (440.0, 40.0),
        "labels":
            [(n, "output") for n, _ in ADCR_BITS] +
            [(f"ADCR_{s}_{pn}", "output") for s in ("DCO", "OR") for pn in "PN"] +
            [("CLK_ADCR_P", "input"), ("CLK_ADCR_N", "input"),
             ("CONV_SPI_SCLK", "input"), ("CONV_SPI_SDIO", "bidirectional"),
             ("CONV_SPI_CSB_R", "input"), ("IF_RX_B", "input")],
    },
    "ADC_SDR": {
        "file": "rev03/ADC_SDR.kicad_sch",
        "desc": "AD9253 SDR ADC and its drivers",
        "at": (440.0, 130.0),
        "labels":
            [(n, "output") for n, _ in CONV_DIGITAL if n.startswith("ADCS_")] +
            [("CLK_ADCS_P", "input"), ("CLK_ADCS_N", "input"),
             ("CONV_SPI_SCLK", "input"), ("CONV_SPI_SDIO", "bidirectional"),
             ("CONV_SPI_CSB_S", "input"), ("IF_RX_A", "input"), ("IF_RX_C", "input")],
    },
    "DAC_RADAR": {
        "file": "rev03/DAC_RADAR.kicad_sch",
        "desc": "AD9708 radar chirp DAC, output balun",
        "at": (520.0, 40.0),
        "labels":
            [(n, "input") for n, _ in CONV_DIGITAL if n.startswith("DACR_")] +
            [("IF_TX_B", "output")],
    },
    "DAC_SDR": {
        "file": "rev03/DAC_SDR.kicad_sch",
        "desc": "AD9767 dual SDR DAC, output balun",
        "at": (520.0, 80.0),
        "labels":
            [(n, "input") for n, _ in CONV_DIGITAL if n.startswith("DACS_")] +
            [("IF_TX_A", "output"), ("IF_TX_C", "output")],
    },
    "CLOCK": {
        "file": "rev03/CLOCK.kicad_sch",
        "desc": "Si549 master XO, ADCLK948 reference select and fan-out",
        "at": (30.0, 140.0),
        "labels": [(n, "output") for n in CLOCKS] +
            [("CLK_SEL", "input"), ("XO_SCL", "input"), ("XO_SDA", "bidirectional")],
    },
    "ROUTING": {
        "file": "rev03/ROUTING.kicad_sch",
        "desc": "4x SPDT channel routing, IF and clock SMAs",
        "at": (190.0, 140.0),
        "labels":
            [(n, "output") for n in IF_RX] + [(n, "input") for n in IF_TX] +
            [(f"SW_CTRL{i}", "input") for i in range(4)],
    },
    "POWER": {
        "file": "rev03/POWER.kicad_sch",
        "desc": "12 V input, protection, buck/LDO tree (rails are global)",
        "at": (190.0, 40.0),
        "labels": [],
    },
}


def esc(s):
    return s.replace(chr(92), chr(92) * 2).replace('"', chr(92) + '"')


def child_sheet(name, spec):
    """A .kicad_sch holding only hierarchical labels."""
    out = ['(kicad_sch', '\t(version 20260306)', '\t(generator "eeschema")',
           '\t(generator_version "10.0")', f'\t(uuid "{uid("sheetfile", name)}")',
           '\t(paper "A3")', '\t(title_block',
           f'\t\t(title "{esc(name)} - {esc(spec["desc"])}")',
           '\t\t(rev "03")', '\t\t(company "KV260-IAS2RF")', '\t)',
           '\t(lib_symbols', '\t)']
    x, y, col = 25.4, 25.4, 0
    for lbl, direction in spec["labels"]:
        if y > 260.0:
            y = 25.4
            col += 1
            x = 25.4 + col * 80.0
        out += [f'\t(hierarchical_label "{esc(lbl)}"',
                f'\t\t(shape {direction})',
                f'\t\t(at {x} {y:.4f} 0)',
                '\t\t(effects', '\t\t\t(font', '\t\t\t\t(size 1.27 1.27)', '\t\t\t)',
                '\t\t\t(justify left)', '\t\t)',
                f'\t\t(uuid "{uid("hlabel", name, lbl)}")', '\t)']
        y += 5.08
    out.append(')')
    return chr(10).join(out) + chr(10)


def root_block(name, spec):
    """The (sheet ...) block that goes in the root schematic."""
    x, y = spec["at"]
    n = max(len(spec["labels"]), 1)
    h = max(20.0, n * 2.54 + 10.0)
    w = 62.0
    o = [f'\t(sheet', f'\t\t(at {x} {y})', f'\t\t(size {w} {h:.2f})',
         '\t\t(exclude_from_sim no)', '\t\t(in_bom yes)', '\t\t(on_board yes)',
         '\t\t(dnp no)', '\t\t(fields_autoplaced yes)',
         '\t\t(stroke', '\t\t\t(width 0)', '\t\t\t(type solid)', '\t\t)',
         '\t\t(fill', '\t\t\t(color 255 255 255 0.0000)', '\t\t)',
         f'\t\t(uuid "{uid("sheet", name)}")',
         f'\t\t(property "Sheetname" "{esc(name)}"',
         f'\t\t\t(at {x} {y - 2.54} 0)', '\t\t\t(show_name no)',
         '\t\t\t(do_not_autoplace no)',
         '\t\t\t(effects', '\t\t\t\t(font', '\t\t\t\t\t(size 1.27 1.27)', '\t\t\t\t)',
         '\t\t\t\t(justify left bottom)', '\t\t\t)', '\t\t)',
         f'\t\t(property "Sheetfile" "{esc(spec["file"])}"',
         f'\t\t\t(at {x} {y + h + 1.27:.2f} 0)', '\t\t\t(show_name no)',
         '\t\t\t(do_not_autoplace no)',
         '\t\t\t(effects', '\t\t\t\t(font', '\t\t\t\t\t(size 1.27 1.27)', '\t\t\t\t)',
         '\t\t\t\t(justify left top)', '\t\t\t)', '\t\t)']
    py = y + 5.08
    for lbl, direction in spec["labels"]:
        o += [f'\t\t(pin "{esc(lbl)}" {direction}',
              f'\t\t\t(at {x} {py:.4f} 180)',
              f'\t\t\t(uuid "{uid("pin", name, lbl)}")',
              '\t\t\t(effects', '\t\t\t\t(font', '\t\t\t\t\t(size 1.27 1.27)', '\t\t\t)',
              '\t\t\t\t(justify right)', '\t\t)', '\t\t)']
        py += 2.54
    o.append('\t)')
    return chr(10).join(o)


def main():
    print("Rev03 sheet hierarchy")
    print()
    total = 0
    for name, spec in SHEETS.items():
        print(f"  {name:12s} {len(spec['labels']):3d} interface signals   {spec['desc']}")
        total += len(spec["labels"])
    print(f"  {'':12s} {total:3d} total")

    dups = []
    for name, spec in SHEETS.items():
        seen = set()
        for lbl, _ in spec["labels"]:
            if lbl in seen:
                dups.append((name, lbl))
            seen.add(lbl)
    if dups:
        print()
        print(f"ABORTED: duplicate labels within a sheet: {dups}")
        return 1

    if DRY:
        print()
        print("--dry-run: nothing written.")
        return 0

    os.makedirs(os.path.join(ROOT, "rev03"), exist_ok=True)
    for name, spec in SHEETS.items():
        p = os.path.join(ROOT, spec["file"])
        with open(p, "w", encoding="utf-8", newline=chr(10)) as fh:
            fh.write(child_sheet(name, spec))
        print(f"    wrote {spec['file']}")

    # Insert the sheet blocks into the root, just before its final paren.
    text = open(ROOT_SCH, encoding="utf-8").read()
    marker = chr(10) + ")" + chr(10)
    assert text.endswith(marker), "unexpected root schematic ending"
    body = text[:-len(marker)]
    blocks = chr(10).join(root_block(n, s) for n, s in SHEETS.items())
    out = body + chr(10) + blocks + marker
    with open(ROOT_SCH, "w", encoding="utf-8", newline=chr(10)) as fh:
        fh.write(out)
    print(f"    root schematic: {len(text)} -> {len(out)} bytes")

    # Register the new sheets in the project file.
    pro = json.load(open(PRO, encoding="utf-8"))
    for name in SHEETS:
        u = uid("sheet", name)
        if not any(s[0] == u for s in pro["sheets"]):
            pro["sheets"].append([u, name])
    with open(PRO, "w", encoding="utf-8", newline=chr(10)) as fh:
        json.dump(pro, fh, indent=2)
        fh.write(chr(10))
    print(f"    .kicad_pro sheets[]: {len(pro['sheets'])} entries")

    print()
    print("Now run ERC. hier_label_mismatch must not increase.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
