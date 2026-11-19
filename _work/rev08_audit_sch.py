#!/usr/bin/env python3
"""
Rev08 RF and power audit (docs/AUDIT_Rev08.md, 18 November 2026): the schematic edits on the two hand-drawn sheets,
as text edits. RX_VU and STATUS are regenerated from their specifications instead (rx_vu.py, status.py).

POWER (the only sheet this script edits)
  - U1002 (+3V3_D buck) becomes the TPS563201: 3 A, pin for pin the TPS562201 (P5: +3V3_D carries up to 1.89 A).
  - R1031 3.09 k -> 3.24 k: +1V0 at 1.017 V, centred in VCCINT's window at the balls (P7).
  - U1006 pin 5 (the 50 mV ANY-OUT pin) to ground: +1V8_D at 1.85 V, so VCCAUX stays above 1.71 V at the balls (P4).
  - F1001 holds 2.0 A at 25 C (1812, 24 V, mSMD200-24V): 1.32 A at 70 C against the 1.27 A worst case at 10.5 V (P3).
    A 2920 part would hold more but does not fit between J1001, Q1001, R1004 and TP4.
The Pmod's back-powering (P2) is fixed in the gateware of both FPGAs, not with series resistors: the eight lines run
as a 0.2-0.3 mm bus from J1102 to the BGA, with no room for a resistor in line (docs/AUDIT_Rev08.md, P2).

Usage:  py _work/rev08_audit_sch.py          (idempotent: refuses to run twice)
"""
import os
import re
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
U = lambda: str(uuid.uuid4())



def block_of(t, ref):
    i = t.find(f'(property "Reference" "{ref}"')
    assert i > 0, ref
    st = t.rfind("\n\t(symbol\n", 0, i)
    en = t.find("\n\t)\n", i) + 4
    return st, en


def set_prop(blk, name, value):
    new, n = re.subn(r'\(property "' + name + r'" "[^"]*"', f'(property "{name}" "{value}"', blk, count=1)
    assert n == 1, name
    return new


def power():
    p = os.path.join(ROOT, "sheets", "POWER.kicad_sch")
    t = open(p, encoding="utf-8").read()
    assert "TPS563201" not in t, "already applied"
    for ref, props in (("U1002", {"Value": "TPS563201"}), ("R1031", {"Value": "3.24k"}),
                       ("F1001", {"Value": "PTC 2A hold"})):
        st, en = block_of(t, ref)
        blk = t[st:en]
        for k, v in props.items():
            blk = set_prop(blk, k, v)
        t = t[:st] + blk + t[en:]
    # U1006 pin 5 at (238.76, 280.67): its no-connect flag becomes a ground symbol
    m = re.search(r'\n\t\(no_connect\n\t\t\(at 238\.76 280\.67\)\n\t\t\(uuid "[^"]+"\)\n\t\)', t)
    assert m, "U1006 pin 5 no-connect"
    t = t[:m.start()] + t[m.end():]
    # clone a ground symbol of this sheet
    gm = re.search(r'\n\t\(symbol\n\t\t\(lib_id "power:GND"\)\n\t\t\(at [-\d.]+ [-\d.]+ \d+\)[\s\S]*?\n\t\)\n', t)
    g = gm.group(0)
    refs = [int(x) for x in re.findall(r'"#PWR(\d+)"', t)]
    nref = f"#PWR{max(refs) + 1}"
    g = re.sub(r'\(at [-\d.]+ [-\d.]+ \d+\)', "(at 238.76 280.67 0)", g, count=1)
    old = re.search(r'\(property "Reference" "(#PWR\d+)"', g).group(1)
    g = g.replace(f'"{old}"', f'"{nref}"')
    g = re.sub(r'\(uuid "[^"]+"\)', lambda _: f'(uuid "{U()}")', g)
    # property positions follow the symbol
    g = re.sub(r'(\(property "Reference" "[^"]*"\n\t\t\t)\(at [-\d.]+ [-\d.]+ \d+\)', r'\1(at 238.76 286.02 0)', g)
    g = re.sub(r'(\(property "Value" "[^"]*"\n\t\t\t)\(at [-\d.]+ [-\d.]+ \d+\)', r'\1(at 238.76 284.48 0)', g)
    g = re.sub(r'(\(property "(?:Footprint|Datasheet|Description)" "[^"]*"\n\t\t\t)\(at [-\d.]+ [-\d.]+ \d+\)',
               r'\1(at 238.76 280.67 0)', g)
    k = t.rfind("\n\t(sheet_instances")
    k = k if k > 0 else t.rfind("\n)")
    t = t[:k] + g.rstrip("\n") + t[k:]
    open(p, "w", encoding="utf-8").write(t)
    print("POWER: U1002 TPS563201, R1031 3.24k, F1001 2 A, U1006 pin 5 to ground (" + nref + ")")


if __name__ == "__main__":
    power()
