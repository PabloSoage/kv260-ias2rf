#!/usr/bin/env python3
"""
Dump how AERIS-10's main board wires a given IC: for every pin, the net, and
every other part on that net with its value.

AERIS-10 was fabricated and measured, so its converter circuits (AD9484 with
AD8352 drivers, AD9708) are the best reference available for the ones this
board copies. This is the evidence behind the values in docs/ADC_RADAR_SPEC.md
that say "as AERIS-10".

Usage:  py _work/aeris_reference_circuit.py U1 U4 U3
        (no arguments: list the converter-related parts)
"""

import sys
import xml.etree.ElementTree as ET

SCH = (r"E:\Repos\PLFM_RADAR\4_Schematics and Boards Layout\4_6_Schematics"
       r"\MainBoard\RADAR_Main_Board.sch")

root = ET.parse(SCH).getroot()
parts = {p.get("name"): p for p in root.iter("part")}


def desc(name):
    p = parts[name]
    val = p.get("value") or ""
    for a in p.iter("attribute"):
        if a.get("name") in ("VALUE", "MPN", "PART_NUMBER") and a.get("value"):
            val = val or a.get("value")
    return f"{name}({p.get('deviceset')}{' ' + val if val else ''})"


# net -> set of (part, pin). Eagle's auto-named nets (N$12) are local to their sheet and the same name
# recurs on other sheets, so they are keyed by sheet; named nets are global.
nets = {}
for i, sheet in enumerate(root.iter("sheet")):
    for net in sheet.iter("net"):
        key = net.get("name")
        if key.startswith("N$"):
            key = f"{key}@s{i + 1}"
        for pr in net.iter("pinref"):
            nets.setdefault(key, set()).add((pr.get("part"), pr.get("pin")))

by_part = {}
for net, members in nets.items():
    for part, pin in members:
        by_part.setdefault(part, []).append((pin, net))

if len(sys.argv) == 1:
    for n, p in sorted(parts.items()):
        d = p.get("deviceset") or ""
        if any(k in d for k in ("AD9", "AD8", "ADCLK", "LTC", "TRANS", "BALUN", "ETC", "TC")):
            print(desc(n))
    sys.exit()

def members(net, skip):
    others = sorted(f"{desc(p)}.{q}" for p, q in nets[net] if p != skip)
    if net.upper() in ("GND", "AGND", "DGND") or len(others) > 12:
        others = [f"<{len(others)} pins>"]
    return " ".join(others)


def is_passive(ref):
    return ref[:1] in "RCLF" and not ref.startswith("CON")


for ref in sys.argv[1:]:
    print(f"=== {desc(ref)}")
    for pin, net in sorted(by_part.get(ref, []), key=lambda t: (t[1], t[0])):
        print(f"  {pin:>10}  {net:<22} {members(net, ref)}")
        # one step further through two-pin passives: where the far end goes
        for p, q in sorted(nets[net]):
            if p == ref or not is_passive(p) or len(nets[net]) > 12:
                continue
            for q2, n2 in by_part.get(p, []):
                if n2 != net:
                    print(f"  {'':>10}    via {p}.{q2}: {n2:<16} {members(n2, p)}")
