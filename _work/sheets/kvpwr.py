"""
Draw sheets/KVPWR.kicad_sch (Rev08, 19 November: the single power entry, the KV260 fed through J1004) from
kvpwr_spec.py with labdraw.py, and check it with _work/check_sheet.py kvpwr. Root block and the POWER sheet's
hierarchical labels: _work/kvpwr_schematic.py.

Usage:  py _work/sheets/kvpwr.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import labdraw as D                                               # noqa: E402
import kvpwr_spec as S                                            # noqa: E402

s, PATH, BLOCK_UUID = D.setup(S, "KVPWR", "KVPWR - single power entry: input choke, KV260 supply eFuse", "A3", 2600,
                              set())
ROOT_UUID = D.ROOT_UUID
GROUPS = [
    (["L1004"], []),
    (["U1010", "Q1010", "Q1011"], ["R1040", "R1041", "R1042", "R1043", "C1093", "C1094", "C1095", "D1004", "J1004"]),
]
D.X0 = 20.32
y = D.layout(GROUPS, x1=400.0)
notes = [
    "KVPWR - how this sheet works (POWER_SPEC 1.4, BOARD_MANUAL 6)",
    "1. One supply and one ground for both boards: J1001 -> L1004 (both lines) -> VIN_J. J1001's sleeve is GND_IN; it reaches GND only through L1004.",
    "2. VIN_J -> F1001 -> the adapter (POWER sheet). VIN_J -> Q1010 -> U1010 -> +12V_KV -> J1004 -> jumper -> KV260 J12.",
    "3. U1010: OVP 14.4 V (KV260: SMAJ16A, its own cutoff 13.2 V), UVLO 8.0 V, current limit 3.0 A, auto-retry; -60 V reverse with Q1010/Q1011.",
    "4. In a car the module needs a regulated 12 V supply upstream: the KV260 does not run above 13.2 V.",
]
for i, t in enumerate(notes):
    s.text(t, (20.32, y + 6.35 + 4.5 * i), size=1.524 if i == 0 else 1.27)


def write():
    n, w, j = s.write()
    print(f"wrote {os.path.relpath(PATH, D.ROOT)}: {n} symbols, {w} wire segments, {j} junctions; notes end at "
          f"y {y + 30:.0f} of 297")


if __name__ == "__main__":
    write()
