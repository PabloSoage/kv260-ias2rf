#!/usr/bin/env python3
"""
Draw psu/psu.kicad_sch (the PSU board's one sheet) from psu_spec.py with labdraw.py's drawer, and write the
project files around it (psu.kicad_pro, sym-lib-table, fp-lib-table).

Usage:  py _work/psu/psu_sheet.py
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "sheets"))
sys.path.insert(0, os.path.dirname(HERE))
import labdraw as D                                               # noqa: E402
import schgen                                                     # noqa: E402
import psu_spec as S                                              # noqa: E402

ROOT = os.path.dirname(os.path.dirname(HERE))
PSU = os.path.join(ROOT, "psu")
PATH = os.path.join(PSU, "psu.kicad_sch")
FILE_UUID = schgen.uid("psu", "root", "file")

GROUPS = [
    (["J1"], ["D1", "D2", "C4", "C5"]),
    (["U1"], ["R4", "C1", "D3", "D4", "D5", "R5", "R6", "R7", "R8", "C2", "C3", "D6", "D7", "R9", "D11"]),
    (["Q1", "Q2"], []),
    (["L3", "L2"], ["C6", "C7", "C8", "C9", "C10", "C11", "C12", "R2", "C13", "C14", "C15", "C16", "C17", "C18", "C19"]),
    (["U2"], ["R10", "R11", "R12", "C20", "C21", "C22", "C23", "C24", "R13", "R14", "R15", "R16", "R17", "R18", "C25",
              "R19", "R20", "R21", "C26", "C27", "C28", "R22", "R23", "R24", "R25", "C29", "R26"]),
    (["Q3", "Q4", "Q5", "Q6", "L1"], ["R1", "C32", "C33", "C34", "C35", "C36", "C37", "C38", "C39", "R29", "D10"]),
    (["U3"], ["R40", "R41", "R42", "R43", "C40", "C41", "D8", "J2"]),
    (["U4"], ["R50", "R51", "R52", "R53", "C50", "C51", "D9", "J3"]),
]
NOTES = [
    "PSU board - how this sheet works (docs/PSU_SPEC.md)",
    "1. J1 takes the vehicle battery (16 AWG, 20 A fuse at the battery) or a bench supply, 6 to 36 V; it feeds both boards by their own cables from one ground.",
    "2. D1 + D2 clamp the input at +111 V / -27 V. U1 LTC4364: Q1 clamps B0 at 48 V through a load dump (fault timer C2), Q2 blocks reverse current and back-feed.",
    "3. B0 -> L3 -> L2 -> R2 -> VIN: a two-stage filter, damped by C17/C18 (Middlebrook); R2 is U2's input current limit (16.3 A).",
    "4. U2 LM5177 four-switch buck-boost: 12.0 V from 2.9 to 60 V (BIAS from +12V once running), 400 kHz with spread spectrum.",
    "5. U3 (2.0 A) feeds the adapter's J1001 through J2; U4 (3.0 A) feeds the KV260's J12 through J3. Both: OVP 14.4 V, UVLO 8.0 V.",
    "6. R13-R16 (gate resistors) are 0 ohm: raise them to slow the switching edges if the EMI measurement asks for it.",
]


def setup():
    s = schgen.Sheet(PATH, FILE_UUID, "PSU - vehicle and bench power for the adapter and the KV260", "psu",
                     f"/{FILE_UUID}", paper="A1", generator="_work/psu/psu_sheet.py", ref_base=900)
    s.lib("psu", os.path.join(PSU, "psu.kicad_sym"))
    D.s, D.S = s, S
    D.FLAGGED, D.flagged = {"+12V", "VCC_LTC"}, set()
    return s


def project_files():
    pro = {"meta": {"filename": "psu.kicad_pro", "version": 3},
           "board": {"design_settings": {"defaults": {}, "rules": {"min_clearance": 0.15, "min_track_width": 0.15,
                                                                   "min_via_diameter": 0.45, "min_through_hole_diameter": 0.2}}},
           "net_settings": {"classes": [{"name": "Default", "clearance": 0.15, "track_width": 0.2,
                                         "via_diameter": 0.5, "via_drill": 0.25, "microvia_diameter": 0.3,
                                         "microvia_drill": 0.1, "diff_pair_width": 0.2, "diff_pair_gap": 0.25,
                                         "diff_pair_via_gap": 0.25, "wire_width": 6, "bus_width": 12,
                                         "line_style": 0, "schematic_color": "rgba(0, 0, 0, 0.000)",
                                         "pcb_color": "rgba(0, 0, 0, 0.000)", "priority": 2147483647}],
                            "meta": {"version": 4}, "net_colors": None, "netclass_assignments": None,
                            "netclass_patterns": []},
           "schematic": {"legacy_lib_dir": "", "legacy_lib_list": []},
           "sheets": [[FILE_UUID, "Root"]], "text_variables": {}}
    with open(os.path.join(PSU, "psu.kicad_pro"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(pro, f, indent=2)
    open(os.path.join(PSU, "sym-lib-table"), "w", encoding="utf-8", newline="\n").write(
        '(sym_lib_table\n\t(version 7)\n\t(lib (name "psu")(type "KiCad")(uri "${KIPRJMOD}/psu.kicad_sym")(options "")'
        '(descr "PSU board parts"))\n)\n')
    open(os.path.join(PSU, "fp-lib-table"), "w", encoding="utf-8", newline="\n").write(
        '(fp_lib_table\n\t(version 7)\n\t(lib (name "psu")(type "KiCad")(uri "${KIPRJMOD}/psu.pretty")(options "")'
        '(descr "PSU board footprints"))\n)\n')


def main():
    s = setup()
    D.X0 = 20.32
    y = D.layout(GROUPS, x1=820.0)
    for i, t in enumerate(NOTES):
        s.text(t, (20.32, y + 6.35 + 4.5 * i), size=1.524 if i == 0 else 1.27)
    # the ground's power flag on its own, clear of any connector's adjacent pins
    g = (20.32, y + 6.35 + 4.5 * len(NOTES) + 10.16)
    s.wire(g, (g[0] + 7.62, g[1]))
    s.power("power:GND", "GND", (g[0] + 7.62, g[1]))
    s.power("power:PWR_FLAG", "PWR_FLAG", g)
    n, w, j = s.write()
    t = open(PATH, encoding="utf-8").read()
    # not fitted parts
    for ref in S.DNP:
        i = t.find(f'(property "Reference" "{ref}"')
        k = t.rfind("\n\t(symbol\n", 0, i)
        blk_end = t.find("(dnp no)", k)
        assert 0 <= blk_end < i, ref
        t = t[:blk_end] + "(dnp yes)" + t[blk_end + len("(dnp no)"):]
    open(PATH, "w", encoding="utf-8", newline="\n").write(t)
    project_files()
    print(f"wrote {os.path.relpath(PATH, ROOT)}: {n} symbols, {w} wire segments, {j} junctions; notes end at y "
          f"{y + 40:.0f} of 594")


if __name__ == "__main__":
    main()
