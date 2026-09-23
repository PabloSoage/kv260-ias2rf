#!/usr/bin/env python3
"""
Interface changes that came out of drawing the CLOCK sheet (docs/CLOCK_SPEC.md).

  * CLK_DAC_P/N removed. Both DACs take single-ended CMOS clocks (AD9767
    Table 6: CLK1/IQCLK; AD9708: CLOCK), not a differential LVPECL pair. Their
    clocks come from the FPGA, which also sends them their data.
  * DACS_IQCLK and DACS_IQRESET added, FPGA -> AD9767. The AD9767 in
    interleaved mode needs IQCLK, IQWRT, IQSEL and IQRESET (Table 6); the
    first hierarchy only carried IQWRT and IQSEL.
  * CLK_SEL, XO_SCL, XO_SDA added, FPGA -> CLOCK: reference select (driven
    open-drain) and the I2C bus that programs the Si549 to 400 or 500 MHz.
    3.3 V levels: the Si549 needs VIH >= 0.7 x VDD.

_work/rev03_build_hierarchy.py created these sheets once and must not be
re-run (it would add a second set of sheet blocks to the root). Its tables
are updated to match, as the record of intent; this script is what changes
the files. Then run _work/sync_sheet_pins.py to bring the root's sheet pins
in line.

Usage:  py _work/rev03_clock_interface.py
"""

import os
import re
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NS = uuid.UUID("0f4e5d6c-7b8a-4912-a3b4-c5d6e7f80912")

CHANGES = {
    "rev03/CONVERTERS.kicad_sch": {
        "remove": ["CLK_DAC_P", "CLK_DAC_N"],
        "add": [("DACS_IQCLK", "input"), ("DACS_IQRESET", "input")],
    },
    "rev03/CONTROL.kicad_sch": {
        "remove": [],
        "add": [("DACS_IQCLK", "output"), ("DACS_IQRESET", "output"),
                ("CLK_SEL", "output"), ("XO_SCL", "output"), ("XO_SDA", "bidirectional")],
    },
}

LABEL = '''\t(hierarchical_label "{name}"
\t\t(shape {shape})
\t\t(at 25.4 {y:.4f} 0)
\t\t(effects
\t\t\t(font
\t\t\t\t(size 1.27 1.27)
\t\t\t)
\t\t\t(justify left)
\t\t)
\t\t(uuid "{uid}")
\t)
'''


def main():
    for rel, ch in CHANGES.items():
        path = os.path.join(ROOT, rel)
        text = open(path, encoding="utf-8").read()
        for name in ch["remove"]:
            pat = re.compile(r'\t\(hierarchical_label "' + re.escape(name) + r'"\n(?:.*\n)*?\t\)\n')
            text, n = pat.subn("", text, count=1)
            print(f"  {rel}: removed {name}" if n else f"  {rel}: {name} already absent")
        ys = [float(y) for y in re.findall(r'\(hierarchical_label "[^"]+"\s*\(shape \w+\)\s*\(at [\d.]+ ([\d.]+)', text)]
        y = max(ys) + 5.08
        existing = set(re.findall(r'\(hierarchical_label "([^"]+)"', text))
        add = ""
        for name, shape in ch["add"]:
            if name in existing:
                print(f"  {rel}: {name} already present")
                continue
            add += LABEL.format(name=name, shape=shape, y=y, uid=uuid.uuid5(NS, rel + name))
            print(f"  {rel}: added {name} ({shape})")
            y += 5.08
        text = text.rstrip()
        assert text.endswith(")")
        text = text[:-1] + add + ")\n"
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    print("Now run: py _work/sync_sheet_pins.py")


if __name__ == "__main__":
    main()
