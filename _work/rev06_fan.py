#!/usr/bin/env python3
"""
Rev06: a fan header for enclosure v2 (13 Nov 2026; docs/ENCLOSURE_V2_THERMAL.md decides the fan).

  J1002  JST PH 2-pin vertical (the usual plug of 40/50 mm 5 V fans): 1 = FAN_5V, 2 = GND
  F1002  PTC, 0.5 A hold, 1206: a shorted fan lead must not pull +5V0 (and the whole board) down
  C1092  10 uF at the header: the fan motor's commutation current stays local

Always on from +5V0 (LMR33630, 3 A; the board draws about 1.6 A from it). The FPGA has no free ball left
that can be escaped for a PWM or tach line, and HK_ALERT (TMP1075) would leave the fan off at power-up,
which is the wrong failure. Placed near the input power section, at the board's IAS0 (J102) end.

Text edit of rev03/POWER.kicad_sch with add_ethernet.py's helpers. Refuses to run twice.

Usage:  py _work/rev06_fan.py
"""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "_work"))
import add_ethernet as AE                                          # noqa: E402
from rev06_eth import highest                                      # noqa: E402

AE.SHEET = os.path.join(ROOT, "rev03", "POWER.kicad_sch")
AE.POWER["+5V0"] = ("power:+5V", "+5V0")


def main():
    s = AE.Sheet()
    if '"J1002"' in s.t: sys.exit("already applied")
    AE.PWR[0] = highest("#PWR")
    X, Y = 60.96, 330.2
    p = s.inst("Device:Polyfuse", "F1002", "PTC 0.5A hold", "Fuse:Fuse_1206_3216Metric", X, Y, "fan supply protection")
    s.connect(p["1"], "+5V0"); s.connect(p["2"], "FAN_5V")
    p = s.inst("Device:C", "C1092", "10u", AE.C0805, X + 15.24, Y, "fan header bulk")
    s.connect(p["1"], "FAN_5V"); s.connect(p["2"], "GND")
    p = s.inst("Connector_Generic:Conn_01x02", "J1002", "FAN 5V",
               "Connector_JST:JST_PH_B2B-PH-K_1x02_P2.00mm_Vertical", X + 30.48, Y, "enclosure v2 fan, 5 V")
    s.connect(p["1"], "FAN_5V"); s.connect(p["2"], "GND")
    s.save()
    print("fan header added; #PWR up to", AE.PWR[0])


if __name__ == "__main__":
    main()
