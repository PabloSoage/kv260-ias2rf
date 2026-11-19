#!/usr/bin/env python3
"""
Rev08, 19 November 2026: the RJ45's shield to ground through an RC (sheet CONTROL), as a text edit of the sheet.

J1201 (HanRun HR911130C) bonds the cable's shield to the board's ground at its SH tabs. Ethernet is isolated by
the jack's transformers and its pin 10 (chassis) reaches ground only through the jack's internal 1000 pF / 75 ohm
termination, so the shield is the only DC path between this board's ground and an earthed switch or PC at the
far end of the cable: with the single power entry (docs/POWER_SPEC.md section 1.4) that path would close a 50 Hz
earth loop through the module. The shield now goes to ground through R1218 (1 Mohm, bleeds static) in parallel
with C1223 (1 nF, 2 kV: keeps the RF and ESD bond), the usual termination of an isolated port.

  1. The GND symbol on J1201's SH pin goes; a label ETH_SHIELD takes its place.
  2. R1218 and C1223 stand to the left of J1201, each between ETH_SHIELD and GND; their pin 1s are joined by a
     wire with one label, and the SH pin reaches its label through a short wire (clear of pin 10's ground).

Usage:  py _work/ethshield_schematic.py      (edits sheets/CONTROL.kicad_sch in place; refuses to run twice)
"""
import os
import re
import sys
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import rev08_pcb as P                                    # noqa: E402

SHEET = os.path.join(ROOT, "sheets", "CONTROL.kicad_sch")
NS = uuid.UUID("2b0f6a52-6f0e-4c3e-9d8c-1a7c5e3e1201")
U = lambda name: str(uuid.uuid5(NS, name))
SH_PIN = (718.82, 497.84)
PARTS = {   # ref: (lib_id, value, footprint, x, y, note); the note stays here, the sheet's Description empty as the
            # other parts' are
    "R1218": ("Device:R", "1M", "Resistor_SMD:R_0603_1608Metric", 695.96, 515.62,
              "J1201 shield bleed to ground (with C1223): no DC path to an earthed far end"),
    "C1223": ("Device:C", "1n 2kV", "Capacitor_SMD:C_1206_3216Metric", 706.12, 515.62,
              "J1201 shield RF and ESD bond to ground, 2 kV X7R"),
}


def block_at(t, opener):
    s = t.find(opener)
    assert s >= 0, opener
    s += 1
    return s, P.block_end(t, s)


def label(name, x, y, ang, just):
    return (f'\t(label "{name}"\n\t\t(at {x:.2f} {y:.2f} {ang})\n\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1.27 1.27)\n'
            f'\t\t\t)\n\t\t\t(justify {just} bottom)\n\t\t)\n\t\t(uuid "{U("label" + name + str(x))}")\n\t)\n')


def wire(a, b):
    return (f'\t(wire\n\t\t(pts\n\t\t\t(xy {a[0]:.2f} {a[1]:.2f}) (xy {b[0]:.2f} {b[1]:.2f})\n\t\t)\n\t\t(stroke\n'
            f'\t\t\t(width 0)\n\t\t\t(type default)\n\t\t)\n\t\t(uuid "{U("wire" + str(a) + str(b))}")\n\t)\n')


def main():
    t = open(SHEET, encoding="utf-8").read()
    assert '"ETH_SHIELD"' not in t, "already applied"
    path = re.search(r'\(reference "J1201"\)', t)
    inst = re.search(r'\(path "([^"]+)"\s*\(reference "J1201"\)', t).group(1)
    assert path
    # 1. the GND symbol on SH
    s, e = block_at(t, f'\n\t(symbol\n\t\t(lib_id "power:GND")\n\t\t(at {SH_PIN[0]:.2f} {SH_PIN[1]:.2f} 0)')
    gnd_tpl = t[s:e]
    # a short wire out to the left first, so the label clears pin 10's ground symbol
    lab = (SH_PIN[0] - 7.62, SH_PIN[1])
    t = t[:s] + (wire(SH_PIN, lab) + label("ETH_SHIELD", lab[0], lab[1], 180, "right")).lstrip("\t").rstrip("\n") + t[e:]
    # 2. R1218, C1223 from templates of the same kind already on the sheet
    pwr = max(int(x) for x in re.findall(r'"#PWR(\d+)"', t)) + 1
    add = []
    for ref, (lib, val, fp, x, y, desc) in PARTS.items():
        s0, e0 = block_at(t, f'\n\t(symbol\n\t\t(lib_id "{lib}")')
        b = t[s0:e0]
        ox, oy = [float(v) for v in re.search(r'\n\t\t\(at ([-\d.]+) ([-\d.]+) 0\)', b).groups()]

        def mv(m):
            return f"(at {float(m.group(1)) - ox + x:.2f} {float(m.group(2)) - oy + y:.2f}{m.group(3)}"
        b = re.sub(r'\(at ([-\d.]+) ([-\d.]+)((?: [-\d.]+)?\))', mv, b)
        old_ref = re.search(r'\(property "Reference" "([^"]+)"', b).group(1)
        b = b.replace(f'"{old_ref}"', f'"{ref}"')
        b = re.sub(r'\(property "Value" "[^"]*"', f'(property "Value" "{val}"', b, count=1)
        b = re.sub(r'\(property "Footprint" "[^"]*"', f'(property "Footprint" "{fp}"', b, count=1)
        k = [0]

        def nu(m):
            k[0] += 1
            return f'(uuid "{U(ref + str(k[0]))}")'
        b = re.sub(r'\(uuid "[^"]+"\)', nu, b)
        b = re.sub(r'\(path "[^"]+"', f'(path "{inst}"', b)
        add.append("\t" + b + "\n")
        # pin 1 at the top (y - 3.81): the shield; pin 2 at the bottom: ground
        g = gnd_tpl
        g = re.sub(r'\(at ([-\d.]+) ([-\d.]+)((?: [-\d.]+)?\))',
                   lambda m: f"(at {float(m.group(1)) - SH_PIN[0] + x:.2f} {float(m.group(2)) - SH_PIN[1] + y + 3.81:.2f}"
                             f"{m.group(3)}", g)
        old = re.search(r'\(property "Reference" "([^"]+)"', g).group(1)
        g = g.replace(f'"{old}"', f'"#PWR{pwr}"')
        k2 = [0]

        def nu2(m, ref=ref):
            k2[0] += 1
            return f'(uuid "{U(ref + "gnd" + str(k2[0]))}")'
        g = re.sub(r'\(uuid "[^"]+"\)', nu2, g)
        add.append("\t" + g + "\n")
        pwr += 1
    # the two pin 1s joined by a wire, one label at R1218's end
    (r_x, r_y), (c_x, _) = [(v[3], v[4]) for v in PARTS.values()]
    add.append(wire((r_x, r_y - 3.81), (c_x, r_y - 3.81)))
    add.append(label("ETH_SHIELD", r_x, r_y - 3.81, 180, "right"))
    s = t.rfind("\n\t(sheet_instances")
    s = s if s > 0 else t.rfind("\n)")
    t = t[:s] + "\n" + "".join(add).rstrip("\n") + t[s:]
    open(SHEET, "w", encoding="utf-8", newline="\n").write(t)
    print(f"ETH_SHIELD: GND symbol removed, R1218 + C1223 added -> {SHEET}")


if __name__ == "__main__":
    main()
