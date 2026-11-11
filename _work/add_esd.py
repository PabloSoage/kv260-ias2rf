#!/usr/bin/env python3
"""
ESD protection added on 11 Nov 2026 (docs/SIGNAL_INTEGRITY.md §7):

  * CONTROL: three TPD4E05U06DQAR (4 lines each, 0.5 pF, no VCC pin) on the Pmod's eight
    signals and the JTAG's four, connected by the sheet's own local labels;
  * ROUTING and CLOCK: a PESD5V0F1BL (bidirectional, 0.4 pF, 5.5 V working) from each SMA's
    centre pin to ground, its pin 1 on the connector's In pin, so the net keeps its name.

Text edit of the sheets: the symbols are copied from KiCad's own libraries into each sheet's
lib_symbols (TPD4E05U06DQA flattened, as KiCad does, from TPD4EUSB30, which it extends). Run once; it refuses to
run twice. Then check with the ERC and the netlist.

Usage:  py _work/add_esd.py
"""
import os, re, sys, uuid, subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "_work"))
from toolpaths import kicad_cli          # noqa: E402

SHARE = os.path.join(os.path.dirname(os.path.dirname(kicad_cli())), "share", "kicad", "symbols")
U = lambda: str(uuid.uuid4())
PWR = 1203                                       # the highest #PWR in the project on 11 Nov


def lib_symbol(lib, name):
    """The library symbol as a schematic embeds it: lib-prefixed, and a derived symbol flattened
    (its parent's pins and graphics, its own properties), as KiCad does."""
    t = open(os.path.join(SHARE, lib + ".kicad_sym"), encoding="utf-8").read()
    NL, TB = "\n", "\t"

    def block(n):
        i = t.find(NL + TB + '(symbol "' + n + '"'); j = t.find(NL + TB + '(symbol "', i + 10)
        return t[i + 1:(j if j > 0 else t.rfind(NL + ")"))].rstrip()
    b = block(name)
    parent = re.search(r'\(extends "([^"]+)"\)', b)
    if parent:
        par = parent.group(1)
        own = b[b.index(TB * 2 + "(property"):b.index(TB * 2 + "(embedded_fonts")]
        p = block(par)
        i = p.index(TB * 2 + "(property"); j = p.index(TB * 2 + '(symbol "' + par + "_")
        b = p[:i] + own + p[j:]
        b = b.replace('(symbol "' + par, '(symbol "' + name)
    b = b.replace('(symbol "' + name + '"', '(symbol "' + lib + ":" + name + '"', 1)
    return NL.join(TB + l for l in b.split(NL))


def prop(name, val, x, y, hide=False, ang=0):
    h = "\n\t\t\t(hide yes)" if hide else ""
    return (f'\t\t(property "{name}" "{val}"\n\t\t\t(at {x:.2f} {y:.2f} {ang})' + h +
            '\n\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t)\n\t\t\t)\n\t\t)')


def instance(lib_id, ref, value, fp, x, y, rot, pins, path, project, in_bom=True):
    pp = "\n".join(f'\t\t(pin "{p}"\n\t\t\t(uuid "{U()}")\n\t\t)' for p in pins)
    b = "yes" if in_bom else "no"
    return (f'\t(symbol\n\t\t(lib_id "{lib_id}")\n\t\t(at {x:.2f} {y:.2f} {rot})\n\t\t(unit 1)\n\t\t(body_style 1)\n'
            f'\t\t(exclude_from_sim no)\n\t\t(in_bom {b})\n\t\t(on_board {b})\n\t\t(in_pos_files {b})\n\t\t(dnp no)\n'
            f'\t\t(uuid "{U()}")\n'
            + prop("Reference", ref, x + 2.54, y - 3.81, hide=ref.startswith("#")) + "\n"
            + prop("Value", value, x + 2.54, y + 3.81) + "\n"
            + prop("Footprint", fp, x, y, hide=True) + "\n"
            + prop("Datasheet", "", x, y, hide=True) + "\n"
            + prop("Description", "", x, y, hide=True) + "\n"
            + pp + f'\n\t\t(instances\n\t\t\t(project "{project}"\n\t\t\t\t(path "{path}"\n'
            f'\t\t\t\t\t(reference "{ref}")\n\t\t\t\t\t(unit 1)\n\t\t\t\t)\n\t\t\t)\n\t\t)\n\t)')


def label(name, x, y, ang):
    j = "right" if ang == 180 else "left"
    return (f'\t(label "{name}"\n\t\t(at {x:.2f} {y:.2f} {ang})\n\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1.27 1.27)\n'
            f'\t\t\t)\n\t\t\t(justify {j} bottom)\n\t\t)\n\t\t(uuid "{U()}")\n\t)')


def noconn(x, y):
    return f'\t(no_connect\n\t\t(at {x:.2f} {y:.2f})\n\t\t(uuid "{U()}")\n\t)'


class Sheet:
    def __init__(s, rel):
        s.path = os.path.join(ROOT, rel)
        s.t = open(s.path, encoding="utf-8").read()
        m = re.search(r'\(instances\s*\(project "([^"]+)"\s*\(path "([^"]+)"', s.t)
        s.project, s.ipath = m.group(1), m.group(2)
        s.new = []

    def need(s, lib, name):
        key = f'(symbol "{lib}:{name}"'
        if key in s.t: return
        block = lib_symbol(lib, name)
        i = s.t.find("(lib_symbols"); j = s.t.find("\n\t)", i)
        s.t = s.t[:j] + "\n" + block + s.t[j:]

    def gnd(s, x, y):
        global PWR
        PWR += 1                                  # unique across the sheets: 1204 on
        s.new.append(instance("power:GND", f"#PWR{PWR}", "GND", "", x, y, 0, ["1"], s.ipath, s.project, in_bom=False))

    def coax_in(s, ref):
        i = s.t.find(f'(property "Reference" "{ref}"'); st = s.t.rfind("\n\t(symbol", 0, i)
        b = s.t[st:i]
        x, y = map(float, re.search(r"\n\t\t\(at ([-\d.]+) ([-\d.]+)", b).groups())
        mirror = "(mirror y)" in b
        return (x + 5.08 if mirror else x - 5.08), y        # Conn_Coaxial pin 1 (In) at (-5.08, 0)

    def save(s):
        end = s.t.rstrip().rfind(")")
        s.t = s.t[:end].rstrip("\n") + "\n" + "\n".join(s.new) + "\n)\n"
        open(s.path, "w", encoding="utf-8", newline="\n").write(s.t)


def tvs_on_sma(sheet, pairs):
    sheet.need("Device", "D_TVS")
    for ref, sma in pairs:
        px, py = sheet.coax_in(sma)
        # D_TVS pins at (-3.81, 0) and (3.81, 0); at 270 deg pin 1 sits 3.81 above the origin
        x, y = px, py + 3.81
        sheet.new.append(instance("Device:D_TVS", ref, "PESD5V0F1BL", "Diode_SMD:D_SOD-882", x, y, 270,
                                  ["1", "2"], sheet.ipath, sheet.project))
        sheet.gnd(x, y + 3.81)


def arrays(sheet, items):
    sheet.need("Power_Protection", "TPD4E05U06DQA")
    pins = {"1": (-12.7, 2.54), "2": (-12.7, -2.54), "4": (12.7, 2.54), "5": (12.7, -2.54)}
    for ref, x, y, nets in items:
        sheet.new.append(instance("Power_Protection:TPD4E05U06DQA", ref, "TPD4E05U06DQAR",
                                  "Package_SON:USON-10_2.5x1.0mm_P0.5mm", x, y, 0,
                                  [str(k) for k in range(1, 11)], sheet.ipath, sheet.project))
        for num, net in zip(("1", "2", "4", "5"), nets):
            dx, dy = pins[num]
            sheet.new.append(label(net, x + dx, y - dy, 180 if dx < 0 else 0))
        sheet.gnd(x, y + 12.7)                    # pins 3 and 8, stacked at (0, -12.7)
        for dx, dy in ((12.7, -7.62), (12.7, 7.62), (-12.7, -7.62), (-12.7, 7.62)):   # NC 6, 7, 9, 10
            sheet.new.append(noconn(x + dx, y - dy))


def main():
    c = Sheet("rev03/CONTROL.kicad_sch")
    if "TPD4E05U06DQAR" in c.t: sys.exit("already added")
    arrays(c, [
        ("U1108", 425.45, 152.40, ("PMOD_CS", "PMOD_MOSI", "PMOD_MISO", "PMOD_SCLK")),
        ("U1109", 467.36, 152.40, ("BEAM_STROBE", "PPS_SYNC", "PMOD_SPARE1", "PMOD_SPARE2")),
        ("U1110", 447.04, 180.34, ("JTAG_TCK", "JTAG_TMS", "JTAG_TDI", "JTAG_TDO")),
    ])
    c.save()
    r = Sheet("rev03/ROUTING.kicad_sch")
    tvs_on_sma(r, [(f"D9{k}", j) for k, j in zip(range(61, 71),
               ("J911", "J912", "J921", "J922", "J931", "J932", "J941", "J942", "J951", "J952"))])
    r.save()
    k = Sheet("rev03/CLOCK.kicad_sch")
    tvs_on_sma(k, [("D401", "J401"), ("D402", "J402")])
    k.save()
    print("added: U1108-U1110 (CONTROL), D961-D970 (ROUTING), D401-D402 (CLOCK)")


if __name__ == "__main__":
    main()
