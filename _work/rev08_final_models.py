#!/usr/bin/env python3
"""
3-D models for the parts added on 18 November 2026 (LAYOUT 6.8), toned for the render rules (nothing pure white).

* J1502, the XUNPU 15-way FPC receptacle: its EasyEDA model (LCSC C19269358) into _work/mech/cache/models3d (outside
  git), with the white lid and the light grey latch turned to the ceramic tone, and the beige body darkened a little.
* J1503, the JST-SH header (6-way SM06B-SRSS-TB since the vehicle CAN): KiCad's own model is a STEP with a pure
  white housing, so the board points J1503 at EasyEDA's model of the same part (LCSC C160405, fetched with
  `easyeda2kicad --3d --lcsc_id C160405`), toned like the others.
* J1501's model is ours, made by _work/mech/usbc_hro_model.py.

Usage:  py _work/rev08_final_models.py --models <dir with the EasyEDA .wrl files>
"""
import argparse
import os
import re
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PCB = os.path.join(ROOT, "CSI2-KRIA-KV260_Rev01.kicad_pcb")
CACHE = os.path.join(ROOT, "_work", "mech", "cache", "models3d")
FPC = "FPC-SMD_15P-P1.00_XUNPU_FPC-1.0FX-15PWCR-H20.wrl"
JST_SRC, JST = "CONN-SMD_SR1.00-WS-6P.wrl", "JST_SH_SM06B-SRSS-TB_toned.wrl"
TONES = [  # (colour in the EasyEDA file, colour written)
    (r"diffuseColor 1\.0 1\.0 1\.0\b", "diffuseColor 0.62 0.60 0.55"),
    (r"diffuseColor 0\.75294\d* 0\.75294\d* 0\.75294\d*", "diffuseColor 0.55 0.55 0.55"),
    (r"diffuseColor 0\.99607\d* 0\.87058\d* 0\.76078\d*", "diffuseColor 0.76 0.66 0.55"),
    (r"diffuseColor 0\.84313\d* 0\.81568\d* 0\.75294\d*", "diffuseColor 0.68 0.64 0.56"),
    (r"diffuseColor 0\.85098\d* 0\.85098\d* 0\.85098\d*", "diffuseColor 0.62 0.62 0.62"),
]


def tone(src, dst):
    t = open(src, encoding="utf-8", errors="replace").read()
    for a, b in TONES:
        t = re.sub(a, b, t)
    open(dst, "w", encoding="utf-8").write(t)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", required=True)
    a = ap.parse_args()
    os.makedirs(CACHE, exist_ok=True)
    tone(os.path.join(a.models, FPC), os.path.join(CACHE, FPC))
    tone(os.path.join(a.models, JST_SRC), os.path.join(CACHE, JST))
    t = open(PCB, encoding="utf-8").read()
    i = t.find('(property "Reference" "J1503"')
    s, e = t.rfind("\n\t(footprint", 0, i), t.find("\n\t(footprint", i)
    f = t[s:e]
    f2 = re.sub(r'\(model "[^"]*"', f'(model "${{KIPRJMOD}}/_work/mech/cache/models3d/{JST}"', f, count=1)
    if f2 != f:
        open(PCB, "w", encoding="utf-8", newline="\n").write(t[:s] + f2 + t[e:])
    print("toned", FPC, "and", JST, "; J1503 points at the toned model" if f2 != f else "")


if __name__ == "__main__":
    main()
