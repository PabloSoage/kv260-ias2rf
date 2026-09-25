#!/usr/bin/env python3
"""
Check the wired root: every net that crosses between sheets joins exactly the
pins the sheets' own connection lists say it should.

Each sheet's specification (_work/sheets/<name>_spec.py) lists, for every
hierarchical label, the pins of that sheet on the net. Across the root a net
is the union of those lists over every sheet that carries the label. KiCad's
netlist of the whole design must hold that union - nothing missing, nothing
extra - which catches a label misspelt at the root, two interface nets
shorted together, and a sheet pin left unwired.

Also re-runs every sheet's own check (_work/check_sheet.py).

Usage:  py _work/check_root.py
"""

import importlib
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "sheets"))
sys.path.insert(0, HERE)
import check_sheet                                   # noqa: E402

SHEETS = ["ias_link", "control", "clock", "adc_radar", "adc_sdr", "dac_radar", "dac_sdr",
          "routing", "power"]


def main():
    nets, _ = check_sheet.netlist()
    by_pin = {p: (n, pins) for n, pins in nets for p in pins}
    want = {}                                        # label -> {pins}
    carriers = {}
    for sh in SHEETS:
        spec = importlib.import_module(f"{sh}_spec")
        for label in getattr(spec, "HIER", {}):
            want.setdefault(label, set()).update(spec.NETS[label])
            carriers.setdefault(label, []).append(sh)
    errors = 0
    for label in sorted(want):
        exp = want[label]
        first = sorted(exp)[0]
        if first not in by_pin:
            print(f"  FAIL  {label}: {first} is on no net")
            errors += 1
            continue
        name, got = by_pin[first]
        if len(carriers[label]) < 2:
            print(f"  FAIL  {label}: only on {carriers[label]}")
            errors += 1
        if got != exp:
            print(f"  FAIL  {label} ({name}): missing {sorted(exp - got)}, extra {sorted(got - exp)}")
            errors += 1
    print(f"  {len(want)} interface nets checked across {len(SHEETS)} sheets: "
          f"{'all exact' if not errors else f'{errors} failure(s)'}")
    for sh in SHEETS:
        r = subprocess.run([sys.executable, os.path.join(HERE, "check_sheet.py"), sh],
                           capture_output=True, text=True)
        last = r.stdout.strip().splitlines()[-1]
        print(f"  check_sheet {sh:10s} {last}")
        errors += last != "PASS"
    print()
    print("PASS" if not errors else f"{errors} FAILURE(S)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
