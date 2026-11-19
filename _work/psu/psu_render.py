#!/usr/bin/env python3
"""
PSU board renders (KiCad 10 raytracer): iso, top and bottom at the adapter's framing, from a copy of psu/ with
its zones refilled (the board in the repo stays unfilled). The copy sits beside psu/ so ${KIPRJMOD}/.. model
paths resolve. Writes docs/img/psu/psu_{iso,top,bottom}.png and the 4k masters in docs/img/highres/renders/.

Usage:  python _work/psu/psu_render.py [--fast]
"""
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CLI = os.path.expandvars(r"%LOCALAPPDATA%\Programs\KiCad\10.0\bin\kicad-cli.exe")
WORK = os.path.join(ROOT, "_render_psu")
OUT = os.path.join(ROOT, "docs", "img", "psu")
HR = os.path.join(ROOT, "docs", "img", "highres", "renders")

VIEWS = {
    "iso": ["--side", "top", "--rotate", "-40,0,30", "--perspective", "--zoom", "0.92", "--pan", "0,1.0,0"],
    "top": ["--side", "top", "--zoom", "0.95"],
    "bottom": ["--side", "bottom", "--zoom", "0.95"],
}


def refilled_copy():
    shutil.rmtree(WORK, ignore_errors=True)
    os.makedirs(WORK)
    for f in ("psu.kicad_pcb", "psu.kicad_pro", "psu.kicad_sch", "fp-lib-table", "sym-lib-table", "psu.kicad_sym"):
        src = os.path.join(ROOT, "psu", f)
        if os.path.exists(src):
            shutil.copy(src, WORK)
    shutil.copytree(os.path.join(ROOT, "psu", "psu.pretty"), os.path.join(WORK, "psu.pretty"))
    pcb = os.path.join(WORK, "psu.kicad_pcb")
    subprocess.run([CLI, "pcb", "drc", "--refill-zones", "--save-board", "-o", os.path.join(WORK, "drc.rpt"), pcb],
                   check=False, capture_output=True)
    return pcb


def render(pcb, name, args, w, h, out):
    subprocess.run([CLI, "pcb", "render", *args, "--quality", "high", "--use-board-stackup-colors", "-w", str(w), "--height", str(h),
                    "--background", "opaque", "-o", out, pcb], check=True, capture_output=True)


def main():
    fast = "--fast" in sys.argv
    pcb = refilled_copy()
    os.makedirs(OUT, exist_ok=True)
    for name, args in VIEWS.items():
        render(pcb, name, args, 1512, 1008, os.path.join(OUT, f"psu_{name}.png"))
        if not fast:
            render(pcb, name, args, 3808, 2128, os.path.join(HR, f"psu_{name}_4k.png"))
        print("rendered", name)
    return pcb


if __name__ == "__main__":
    main()
