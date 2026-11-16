"""
Draw rev03/STATUS.kicad_sch (Rev08: status and rail LEDs, LED expander, debug USB bridge) from status_spec.py with
labdraw.py, and check it with _work/check_sheet.py status. Root block: _work/rev08_schematic.py.

Usage:  py _work/sheets/status.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import labdraw as D                                               # noqa: E402
import status_spec as S                                           # noqa: E402

s, PATH, BLOCK_UUID = D.setup(S, "STATUS", "STATUS - LEDs and the debug USB bridge", "A2", 2400, {"VBUS_USB"})
ROOT_UUID = D.ROOT_UUID
LEDS = [r for d, *_ in S.STATUS for r in (f"R15{11 + int(d[-1]) - 1}", d)] + ["R1519", "D1509"]
GROUPS = [
    (["U1501"], ["R1501", "C1501", "C1502"] + LEDS),
    (["Q1520", "Q1521"], ["R1520", "D1520", "R1521", "D1521", "R1522", "D1522", "R1523", "D1523", "R1525",
                          "R1524", "D1524", "R1526"]),
    (["J1501", "U1503"], ["R1531", "R1532"]),
    (["U1502", "U1504"], ["R1533", "R1534", "R1535", "C1531", "C1532", "C1533"]),
]
D.X0 = 20.32
y = D.layout(GROUPS, x1=570.0)
notes = [
    "STATUS - how this sheet works (REV08_PLAN 3.1, 3.2)",
    "1. U1501 TCA6416A at 0x21 on the Si549's bus: P00-P07 sink CFG, CLK, LINK, ADC-R, ADC-S, LO, TX, ERR. Written on change only.",
    "2. D1509 on PMOD_SPARE2 (the debug UART's TX): lit while the line is low, so it flickers once a second (heartbeat).",
    "3. Rail LEDs: dark = dead rail. +1V8_D and +1V0 drive an NPN that switches their LED from +3V3_D.",
    "4. J1501 USB-C -> U1503 ESD -> U1502 CH340X at 3.3 V from the cable (U1504): /dev/ttyUSBx at 115200 8N1.",
]
for i, t in enumerate(notes):
    s.text(t, (20.32, y + 6.35 + 4.5 * i), size=1.524 if i == 0 else 1.27)


def write():
    n, w, j = s.write()
    print(f"wrote {os.path.relpath(PATH, D.ROOT)}: {n} symbols, {w} wire segments, {j} junctions; notes end at "
          f"y {y + 30:.0f} of 420")


if __name__ == "__main__":
    write()
