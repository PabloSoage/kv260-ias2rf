#!/usr/bin/env python3
"""
Split the CONVERTERS sheet in four, and apply the interface changes that came
out of starting to draw it (24 September 2026, docs/ADC_RADAR_SPEC.md §1).

  * CONVERTERS -> ADC_RADAR, ADC_SDR, DAC_RADAR, DAC_SDR. One sheet would
    have held about 200 parts; each of the four is the size of CLOCK, which
    is what one review sitting can check properly.
  * ADCR_D_P[7..0] / ADCR_D_N[7..0] -> ADCR_D0_P ... ADCR_D7_N, one label per
    line, the way ADCS_* already were. A drawn sheet then carries no bus and
    _work/check_sheet.py checks every pair by name.
  * IF_RX_A_P/N ... IF_TX_B_P/N -> IF_RX_A, IF_RX_B, IF_TX_A, IF_TX_B,
    single-ended 50 ohm. The routing switches (M3SWA2, SPDT) and the SMAs
    are single-ended; the AD8352 takes a single-ended input (its datasheet,
    Figure 26) and the DACs will drive a balun.

The label lists come from _work/rev03_build_hierarchy.py (updated first, as
the record of intent). That script is NOT re-run; this one makes the change:

  1. rewrites the labels of CONTROL and ROUTING (not yet drawn: labels only);
  2. writes the four new child sheets, labels only;
  3. replaces the CONVERTERS block in the root with four blocks, on an A2
     root page (A3 had no room left), and registers them in the .kicad_pro;
  4. deletes rev03/CONVERTERS.kicad_sch (it held labels only).

Then run _work/sync_sheet_pins.py for the CONTROL and ROUTING blocks.

Usage:  py _work/rev03_split_converters.py [--dry-run]
"""

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rev03_build_hierarchy as H                     # noqa: E402  (tables only)
from sync_sheet_pins import scan                      # noqa: E402

ROOT = H.ROOT
DRY = "--dry-run" in sys.argv
NEW = ["ADC_RADAR", "ADC_SDR", "DAC_RADAR", "DAC_SDR"]
RELABEL = ["CONTROL", "ROUTING", "ADC_SDR", "DAC_RADAR", "DAC_SDR"]   # while labels-only


def relabel(name):
    """Make a labels-only child sheet carry exactly the labels in H.SHEETS."""
    spec = H.SHEETS[name]
    path = os.path.join(ROOT, spec["file"])
    text = open(path, encoding="utf-8").read()
    want = dict(spec["labels"])
    have = dict(re.findall(r'\(hierarchical_label "([^"]+)"\s*\(shape (\w+)\)', text))
    if re.search(r'\n\t\((symbol|wire)\b', text):
        if want == have:
            print(f"  {name:10s} drawn; labels current ({len(want)})")
            return
        raise SystemExit(f"ABORTED: {spec['file']} has been drawn; edit it in KiCad")
    if want == have:
        print(f"  {name:10s} labels already current ({len(want)})")
        return
    print(f"  {name:10s} {len(have)} -> {len(want)} labels   "
          f"-{len(set(have) - set(want))} +{len(set(want) - set(have))}")
    if not DRY:
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(H.child_sheet(name, spec))


def main():
    print("1. labels of the sheets not yet drawn")
    for name in RELABEL:
        relabel(name)

    print("2. new child sheets")
    for name in NEW:
        spec = H.SHEETS[name]
        path = os.path.join(ROOT, spec["file"])
        if os.path.exists(path):
            print(f"  {spec['file']} exists, left alone")
            continue
        print(f"  {spec['file']}: {len(spec['labels'])} labels")
        if not DRY:
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(H.child_sheet(name, spec))

    print("3. root schematic")
    text = open(H.ROOT_SCH, encoding="utf-8").read()
    names = re.findall(r'\(property "Sheetname" "([^"]+)"', text)
    k = text.find('(property "Sheetname" "CONVERTERS"')
    if k >= 0:
        s = text.rfind("\n\t(sheet\n", 0, k) + 1
        e = scan(text, s)
        text = text[:s].rstrip("\n") + text[e:]
        print("  removed the CONVERTERS block")
    add = [n for n in NEW if n not in names]
    if add:
        marker = "\n)\n"
        assert text.endswith(marker)
        text = text[:-len(marker)] + "\n" + "\n".join(H.root_block(n, H.SHEETS[n]) for n in add) + marker
        print(f"  added blocks: {', '.join(add)}")
    text = text.replace('(paper "A3")', '(paper "A2")', 1)
    if not DRY:
        with open(H.ROOT_SCH, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)

    pro = json.load(open(H.PRO, encoding="utf-8"))
    before = len(pro["sheets"])
    pro["sheets"] = [s for s in pro["sheets"] if s[1] != "CONVERTERS"]
    for n in NEW:
        u = H.uid("sheet", n)
        if not any(s[0] == u for s in pro["sheets"]):
            pro["sheets"].append([u, n])
    print(f"  .kicad_pro sheets[]: {before} -> {len(pro['sheets'])}")
    if not DRY:
        with open(H.PRO, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(pro, fh, indent=2)
            fh.write("\n")

    print("4. rev03/CONVERTERS.kicad_sch")
    old = os.path.join(ROOT, "rev03", "CONVERTERS.kicad_sch")
    if os.path.exists(old):
        if re.search(r'\n\t\((symbol|wire)\b', open(old, encoding="utf-8").read()):
            raise SystemExit("ABORTED: CONVERTERS has drawn content")
        if not DRY:
            os.remove(old)
        print("  deleted (labels only)")

    print()
    print("--dry-run: nothing written." if DRY else "Now run: py _work/sync_sheet_pins.py")


if __name__ == "__main__":
    main()
