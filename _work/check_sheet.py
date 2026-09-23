#!/usr/bin/env python3
"""
Check a drawn sheet against its connection specification.

The drawing (_work/sheets/<name>.py) is made from coordinates; the
specification (_work/sheets/<name>_spec.py) is a list of which pins must meet.
They are written separately, so agreement between them means something:
KiCad exports the netlist of what was actually drawn, and every net is
compared, pin for pin, with the specification.

Checks:
  1. every specified net exists and contains EXACTLY the specified pins of
     this sheet - nothing missing, nothing extra (a stray wire touching a
     pin shows up here);
  2. interface nets carry their hierarchical label, power nets their name;
  3. pins specified as no-connect are alone on their net;
  4. every pin of every part on the sheet is accounted for, either in a net
     or as a no-connect - so the specification cannot silently forget one;
  5. no part is on the sheet that the specification does not list.

Usage:  py _work/check_sheet.py clock
"""

import importlib
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(HERE, "sheets"))
sys.path.insert(0, HERE)
import schgen                                        # noqa: E402

KICAD_CLI = "E:/Program Files/KiCad/10.0/bin/kicad-cli.exe"
ROOT_SCH = os.path.join(ROOT, "CSI2-KRIA-KV260_Rev01.kicad_sch")
POWER_NETS = {"GND", "+3V3_D", "+3V3_CLK", "+3V3_A", "+1V8_D", "+1V8_A", "+1V2", "+1V0",
              "+5V0", "+12V", "-3V3", "+2V5", "+3V6"}


def netlist():
    out = os.path.join(tempfile.gettempdir(), "check_sheet.net")
    subprocess.run([KICAD_CLI, "sch", "export", "netlist", ROOT_SCH, "-o", out],
                   check=True, capture_output=True)
    text = open(out, encoding="utf-8").read()
    # KiCad 10 writes the netlist one token per line; match across whitespace.
    nets = []
    heads = list(re.finditer(r'\(net\s*\(code "?\d+"?\)\s*\(name "([^"]*)"\)', text))
    for k, m in enumerate(heads):
        body = text[m.end(): heads[k + 1].start() if k + 1 < len(heads) else len(text)]
        nodes = re.findall(r'\(node\s*\(ref "([^"]+)"\)\s*\(pin "([^"]+)"\)', body)
        nets.append((m.group(1), {f"{r}.{p}" for r, p in nodes}))
    comps = re.findall(r'\(comp\s*\(ref "([^"]+)"\).*?\(sheetpath\s*\(names "([^"]*)"\)',
                       text, re.S)
    return nets, comps


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "clock"
    spec = importlib.import_module(f"{name}_spec")
    refs = set(spec.PARTS)
    nets, comps = netlist()
    by_pin = {}
    for nname, pins in nets:
        for p in pins:
            by_pin[p] = (nname, pins)
    errors = 0

    def err(msg):
        nonlocal errors
        errors += 1
        print("  FAIL  " + msg)

    print(f"sheet '{name}': {len(refs)} parts, {len(spec.NETS)} nets, "
          f"{len(spec.NO_CONNECT)} no-connects in the specification")
    print()

    # 1 and 2 - every specified net
    for nname, want in spec.NETS.items():
        want = set(want)
        first = sorted(want)[0]
        if first not in by_pin:
            err(f"{nname}: pin {first} is on no net at all")
            continue
        got_name, got = by_pin[first]
        mine = {p for p in got if p.split(".")[0] in refs}
        missing, extra = want - mine, mine - want
        if missing:
            err(f"{nname}: not connected: {sorted(missing)}")
        if extra:
            err(f"{nname}: connected but not specified: {sorted(extra)}")
        if nname in spec.HIER and not got_name.endswith("/" + nname):
            err(f"{nname}: carries the name '{got_name}', not the hierarchical label")
        if nname in POWER_NETS and got_name != nname:
            err(f"{nname}: power net is named '{got_name}'")
        if not (missing or extra):
            print(f"  ok    {nname:12s} {len(want):2d} pins   ({got_name})")

    # 3 - no-connects
    for p in spec.NO_CONNECT:
        if p in by_pin:
            others = {q for q in by_pin[p][1] if q != p}
            if others:
                err(f"{p} is specified no-connect but meets {sorted(others)}")
    print(f"  ok    {len(spec.NO_CONNECT)} no-connect pins are alone")

    # 4 - completeness against the symbols' own pin lists
    s = schgen.Sheet("", "", "", "", "")
    s.lib("kv260-ias2rf", os.path.join(ROOT, "symbols", "kv260-ias2rf.kicad_sym"))
    covered = {p for pins in spec.NETS.values() for p in pins} | set(spec.NO_CONNECT)
    total = 0
    for ref, (lib_id, *_rest) in spec.PARTS.items():
        for pad in s._sym(lib_id).pins:
            total += 1
            if f"{ref}.{pad}" not in covered:
                err(f"{ref}.{pad} is in neither a net nor the no-connect list")
    print(f"  ok    all {total} pins of the {len(refs)} parts are accounted for"
          if not errors else f"        {total} pins checked for coverage")

    # 5 - parts on the sheet but not in the specification
    on_sheet = {r for r, path in comps if path.strip("/").lower() == name.lower()}
    for r in sorted(on_sheet - refs):
        err(f"{r} is on the sheet but not in the specification")
    for r in sorted(refs - on_sheet):
        err(f"{r} is in the specification but not on the sheet")

    print()
    print("PASS" if not errors else f"{errors} FAILURE(S)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
