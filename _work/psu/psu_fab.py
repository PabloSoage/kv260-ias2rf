#!/usr/bin/env python3
"""
PSU board: fabrication outputs for JLCPCB (Gerbers, drill, CPL, BOM, order notes) into fab/ (git-ignored), the
same way _work/fab/make_fab.py does it for the adapter: the board is checked first (DRC with the zones refilled
and schematic parity, on a copy); any error or unrouted connection names the folder DRAFT-.

LCSC: every line's code below was looked up in JLCPCB's parts search on 19 November 2026 (stock and price at that
date in docs/PSU_SPEC.md). Prefer the basic-library part where one exists.

Usage:  py _work/psu/psu_fab.py
"""
import csv
import datetime
import os
import re
import shutil
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
from toolpaths import KICAD_CLI                            # noqa: E402
import psu_pcb as PCB                                     # noqa: E402

ROOT = os.path.dirname(os.path.dirname(HERE))
NAME = "psu"
OUT = os.path.join(ROOT, "fab")
LAYERS = ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu", "F.Paste", "B.Paste", "F.SilkS", "B.SilkS", "F.Mask", "B.Mask",
          "Edge.Cuts"]
ORDER = [
    ("Layers", "4"),
    ("Dimensions", "110 x 70 mm"),
    ("PCB thickness", "1.6 mm"),
    ("Outer / inner copper", "2 oz / 0.5 oz (psu_thermal.py assumes this)"),
    ("Surface finish", "ENIG"),
    ("Via covering", "Tented; U2's 8 thermal vias sit in its exposed pad: epoxy filled & capped if offered"),
    ("Min track / space", "0.15 / 0.15 mm"),
    ("Min via", "0.5 mm pad, 0.25 mm drill"),
    ("Assembly", "Top side only, standard PCBA (BOM and CPL here)"),
]
LCSC = {
    "J1": "C431092", "J2": "C158007", "J3": "C158007",
    "D1": "C42371542", "D2": "C310039", "D5": "C366557", "D6": "C19077412", "D7": "C19077412",
    "D3": "C559090", "D4": "C559090", "D8": "C8678", "D9": "C8678", "D10": "C12624", "D11": "C2286",
    "U1": "C580875", "U2": "C7425536", "U3": "C1850273", "U4": "C1850273",
    "Q1": "C536509", "Q2": "C534334", "Q3": "C534374", "Q4": "C534374", "Q5": "C3039672", "Q6": "C3039672",
    "L1": "C3015590", "L2": "C2847577", "L3": "C5359713",
    "C17": "C128460", "C18": "C128460", "C6": "C278401", "C38": "C19270705", "C39": "C19270705",
    "C4": "C282822", "C5": "C282822", "C41": "C70462", "C51": "C70462",
    "C1": "C106243", "C2": "C354262", "C21": "C5189822", "C22": "C5189822",
    "C3": "C107059", "C9": "C88219", "C10": "C88219", "C19": "C88219", "C20": "C106858", "C23": "C92490",
    "C24": "C92490", "C25": "C1645", "C26": "C107076", "C27": "C1643", "C28": "C1622", "C29": "C327204",
    "C40": "C696861", "C50": "C696861",
    "R1": "C108929", "R2": "C154686", "R4": "C4410",
    "R5": "C185372", "R6": "C25803", "R26": "C25803", "R7": "C844161", "R8": "C25804", "R9": "C4190",
    "R10": "C5204004", "R11": "C2933214", "R12": "C22859", "R17": "C22859", "R18": "C22859",
    "R13": "C21189", "R14": "C21189", "R15": "C21189", "R16": "C21189", "R19": "C103800", "R20": "C2933249",
    "R21": "C2960716", "R22": "C23242", "R23": "C2999457", "R24": "C2933213", "R25": "C4184", "R29": "C23162",
    "R40": "C25814", "R50": "C25814", "R41": "C137761", "R51": "C137761", "R42": "C2930090", "R52": "C2930090",
    "R43": "C2930134", "R53": "C25977",
}
for ref in ("C7", "C8", "C11", "C12", "C13", "C14", "C15", "C16"):
    LCSC[ref] = "C342614"
for ref in ("C32", "C33", "C34", "C35", "C36", "C37"):
    LCSC[ref] = "C21397"


def run(args):
    r = subprocess.run([KICAD_CLI] + args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode not in (0, 5):
        sys.exit(f"kicad-cli failed: {' '.join(args)}\n{r.stdout}\n{r.stderr}")
    return r


def main():
    stamp = datetime.date.today().isoformat()
    work = os.path.join(OUT, "_work_psu")
    shutil.rmtree(work, ignore_errors=True)
    shutil.copytree(PCB.PSU, work)
    pcb = os.path.join(work, "psu.kicad_pcb")
    rpt = os.path.join(work, "drc.rpt")
    run(["pcb", "drc", "--refill-zones", "--save-board", "--schematic-parity", "--severity-error", "-o", rpt, pcb])
    text = open(rpt, encoding="utf-8").read()
    kinds = re.findall(r"^\[(\w+)\]", text, re.M)
    unconnected = kinds.count("unconnected_items")
    errors = [k for k in kinds if k != "unconnected_items"]
    draft = bool(errors or unconnected)
    dest = os.path.join(OUT, ("DRAFT-" if draft else "") + f"{NAME}-{stamp}")
    shutil.rmtree(dest, ignore_errors=True)
    gdir = os.path.join(dest, "gerber")
    os.makedirs(gdir)
    run(["pcb", "export", "gerbers", "-o", gdir, "-l", ",".join(LAYERS), "--subtract-soldermask", "--check-zones",
         pcb])
    run(["pcb", "export", "drill", "-o", gdir + os.sep, "--format", "excellon", "--drill-origin", "absolute",
         "--excellon-units", "mm", "--excellon-zeros-format", "decimal", "--excellon-oval-format", "alternate",
         "--generate-map", "--map-format", "pdf", pcb])
    zpath = os.path.join(dest, f"{NAME}-gerber.zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(os.listdir(gdir)):
            if not f.endswith(".pdf"):
                z.write(os.path.join(gdir, f), f.replace(" ", "_"))
    pos = os.path.join(work, "pos.csv")
    run(["pcb", "export", "pos", "-o", pos, "--format", "csv", "--units", "mm", "--side", "both", "--exclude-dnp", pcb])
    comps, pins = PCB.netlist()
    rows = []
    with open(pos, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["Ref"] in comps:
                rows.append([r["Ref"], f'{float(r["PosX"]):.4f}mm', f'{float(r["PosY"]):.4f}mm',
                             "Top" if r["Side"].lower() == "top" else "Bottom", f'{float(r["Rot"]):.1f}'])
    with open(os.path.join(dest, f"{NAME}-CPL.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        w.writerows(rows)
    groups = {}
    for ref, c in comps.items():
        groups.setdefault((c["value"], c["footprint"].split(":")[-1], LCSC.get(ref, "")), []).append(ref)
    def nat(r):
        m = re.match(r"([A-Z]+)(\d+)", r)
        return (m.group(1), int(m.group(2)))
    brows = sorted([[v, ",".join(sorted(rs, key=nat)), fp, code, len(rs)] for (v, fp, code), rs in groups.items()],
                   key=lambda r: nat(r[1].split(",")[0]))
    with open(os.path.join(dest, f"{NAME}-BOM.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #", "Quantity"])
        w.writerows(brows)
    missing = [r for r in brows if not r[3]]
    with open(os.path.join(dest, "ORDER.txt"), "w", encoding="utf-8") as fh:
        fh.write(f"PSU board - fabrication outputs, {stamp}\n\n")
        if draft:
            fh.write(f"*** DRAFT - DO NOT ORDER ***\nDRC: {len(errors)} error(s), {unconnected} unrouted.\n\n")
        fh.write("Enter on jlcpcb.com:\n")
        for k, v in ORDER:
            fh.write(f"  {k:22s} {v}\n")
        fh.write(f"\nBOM {len(brows)} lines, {sum(r[4] for r in brows)} parts; without an LCSC code: "
                 f"{', '.join(r[1] for r in missing) or 'none'}\nCPL {len(rows)} placements: check every rotation "
                 f"in JLCPCB's preview\n")
    shutil.copy2(rpt, os.path.join(dest, "drc.rpt"))
    print(f"{'DRAFT: ' if draft else ''}{os.path.relpath(dest, ROOT)}  DRC {len(errors)} errors, {unconnected} "
          f"unrouted; BOM {len(brows)} lines / {sum(r[4] for r in brows)} parts, {len(missing)} without LCSC; "
          f"CPL {len(rows)}")


if __name__ == "__main__":
    main()
