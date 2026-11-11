#!/usr/bin/env python3
"""
Fabrication outputs for JLCPCB: Gerbers, drill, pick-and-place, BOM and the
order notes, into fab/ (git-ignored: regenerate them, never edit them).

Settings follow JLCPCB's own KiCad guide ("How to generate Gerber and drill
files in KiCad 8"): Protel extensions, soldermask subtracted from silkscreen,
zones refilled before plotting; drill in Excellon, mm, decimal, absolute
origin, alternate mode for oval holes. Inner layers In1..In4 are included.

What this script refuses to hide: the board is checked first (DRC with the
zones refilled, on a copy). If there is any error, or any unrouted
connection, the output folder is named DRAFT-... and the notes say why. A
draft is for checking the files, not for ordering.

The zones are filled on a copy (fab/_work/): the board file itself stays
unfilled, as it is kept in git.

BOM: the symbols carry no LCSC or MPN field. Chips carry their part number
as the value; passives carry value only. The LCSC column comes from
_work/fab/lcsc_parts.csv, written by lcsc_select.py from JLCPCB's parts
search (docs/FABRICATION.md). A line missing there is left empty.

CPL: KiCad's position file with JLCPCB's column names. JLCPCB's rotation
convention differs from KiCad's for some packages (SOT-23, some QFNs): check
every part in JLCPCB's placement preview before paying.

Usage:  py _work/fab/make_fab.py
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
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "layout"))
import pcbdata as P                                  # noqa: E402

ROOT = P.ROOT
CLI = P.KICAD_CLI
NAME = "CSI2-KRIA-KV260_Rev01"
BOARD = os.path.join(ROOT, NAME + ".kicad_pcb")
OUT = os.path.join(ROOT, "fab")
LAYERS = ["F.Cu", "In1.Cu", "In2.Cu", "In3.Cu", "In4.Cu", "B.Cu", "F.Paste", "B.Paste",
          "F.SilkS", "B.SilkS", "F.Mask", "B.Mask", "Edge.Cuts"]

# The order, as it must be entered on jlcpcb.com (docs/FABRICATION.md explains each)
ORDER = [
    ("Layers", "6"),
    ("Dimensions", "119 x 120 mm (outline in the Gerbers)"),
    ("PCB thickness", "1.6 mm"),
    ("Impedance control", "Yes, stackup JLC06161H-2116A"),
    ("Outer / inner copper", "1 oz / 0.5 oz"),
    ("Material", "FR-4 (the stackup's laminate: NP-155F)"),
    ("Via covering", "Epoxy filled & capped (POFV): free on 6 layers; ~400 vias are in pads"),
    ("Min via hole / diameter", "0.20 / 0.45 mm"),
    ("Min track / spacing", "0.10 / 0.10 mm"),
    ("Surface finish", "ENIG (flat pads for the 1.0 mm BGA and the LFCSPs)"),
    ("Solder mask / silkscreen", "any / any"),
    ("Remove order number", "Specify a location, or pay to remove"),
]


def run(args):
    r = subprocess.run([CLI] + args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode not in (0, 5):           # 5: DRC found violations, reported below
        sys.exit(f"kicad-cli failed: {' '.join(args)}\n{r.stdout}\n{r.stderr}")
    return r


def check(work_pcb):
    """DRC with zones refilled (saved into the copy). Returns (errors, unconnected, report)."""
    rpt = os.path.join(os.path.dirname(work_pcb), "drc.rpt")
    run(["pcb", "drc", "--refill-zones", "--save-board", "--schematic-parity",
         "--severity-error", "-o", rpt, work_pcb])
    text = open(rpt, encoding="utf-8").read()
    kinds = re.findall(r"^\[(\w+)\]", text, re.M)
    unconnected = kinds.count("unconnected_items")
    errors = [k for k in kinds if k != "unconnected_items"]
    return errors, unconnected, text


def lcsc_codes():
    """(Comment, footprint name) -> LCSC code, from lcsc_select.py's table."""
    path = os.path.join(HERE, "lcsc_parts.csv")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        return {(r["Comment"], r["Footprint"]): r["LCSC"] for r in csv.DictReader(fh)}


def bom(comps):
    """JLCPCB BOM: Comment, Designator, Footprint, LCSC Part #; one row per value+footprint."""
    codes = lcsc_codes()
    groups = {}
    for c in comps.values():
        groups.setdefault((c.value, c.fpid), []).append(c.ref)

    def natural(r):
        m = re.match(r"([A-Z]+)(\d+)", r)
        return (m.group(1), int(m.group(2))) if m else (r, 0)
    rows = []
    for (value, fp), refs in sorted(groups.items(), key=lambda kv: natural(sorted(kv[1], key=natural)[0])):
        refs = sorted(refs, key=natural)
        name = fp.split(":", 1)[1]
        rows.append([value, ",".join(refs), name, codes.get((value, name), ""), len(refs)])
    return rows


def cpl(pos_csv):
    """KiCad's CSV position file, renamed to JLCPCB's columns."""
    rows = []
    with open(pos_csv, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            rows.append([r["Ref"], f'{float(r["PosX"]):.4f}mm', f'{float(r["PosY"]):.4f}mm',
                         "Top" if r["Side"].lower() == "top" else "Bottom", f'{float(r["Rot"]):.1f}'])
    return rows


def main():
    stamp = datetime.date.today().isoformat()
    work = os.path.join(OUT, "_work")
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)
    work_pcb = os.path.join(work, NAME + ".kicad_pcb")
    shutil.copy2(BOARD, work_pcb)
    shutil.copy2(os.path.join(ROOT, NAME + ".kicad_pro"), work)
    for f in ("fp-lib-table", "sym-lib-table", NAME + ".kicad_dru"):    # .kicad_dru: the custom rules
        if os.path.exists(os.path.join(ROOT, f)):
            shutil.copy2(os.path.join(ROOT, f), work)
    # the schematic, for the parity check, and the project's own libraries
    shutil.copy2(os.path.join(ROOT, NAME + ".kicad_sch"), work)
    for d in ("rev03", "footprints", "symbols"):
        if os.path.isdir(os.path.join(ROOT, d)):
            shutil.copytree(os.path.join(ROOT, d), os.path.join(work, d))

    errors, unconnected, report = check(work_pcb)
    draft = bool(errors or unconnected)
    dest = os.path.join(OUT, ("DRAFT-" if draft else "") + f"{NAME}-{stamp}")
    shutil.rmtree(dest, ignore_errors=True)
    gdir = os.path.join(dest, "gerber")
    os.makedirs(gdir)

    run(["pcb", "export", "gerbers", "-o", gdir, "-l", ",".join(LAYERS), "--subtract-soldermask",
         "--check-zones", work_pcb])
    run(["pcb", "export", "drill", "-o", gdir + os.sep, "--format", "excellon", "--drill-origin",
         "absolute", "--excellon-units", "mm", "--excellon-zeros-format", "decimal",
         "--excellon-oval-format", "alternate", "--generate-map", "--map-format", "pdf", work_pcb])
    zpath = os.path.join(dest, f"{NAME}-gerber.zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(os.listdir(gdir)):
            if not f.endswith(".pdf"):                  # the drill map is for people
                z.write(os.path.join(gdir, f), f.replace(" ", "_"))

    pos = os.path.join(work, "pos.csv")
    run(["pcb", "export", "pos", "-o", pos, "--format", "csv", "--units", "mm", "--side", "both",
         work_pcb])
    comps = P.netlist()
    # parts only: the fiducials and holes are board-only, nothing to place
    rows = [r for r in cpl(pos) if r[0] in comps]
    with open(os.path.join(dest, f"{NAME}-CPL.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        w.writerows(rows)

    placed = {r[0] for r in rows}
    brows = bom({k: v for k, v in comps.items() if k in placed})
    with open(os.path.join(dest, f"{NAME}-BOM.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #", "Quantity"])
        w.writerows(brows)

    with open(os.path.join(dest, "ORDER.txt"), "w", encoding="utf-8") as fh:
        fh.write(f"{NAME} - fabrication outputs, {stamp}\n\n")
        if draft:
            fh.write("*** DRAFT - DO NOT ORDER ***\n")
            fh.write(f"DRC: {len(errors)} error(s), {unconnected} unrouted connection(s).\n")
            for k in sorted(set(errors)):
                fh.write(f"  {errors.count(k):4d} x {k}\n")
            fh.write("\n")
        fh.write("Enter on jlcpcb.com:\n")
        for k, v in ORDER:
            fh.write(f"  {k:26s} {v}\n")
        fh.write(f"\nFiles:\n  {NAME}-gerber.zip  Gerbers + Excellon drill\n"
                 f"  {NAME}-BOM.csv     {len(brows)} lines, {sum(r[4] for r in brows)} parts; "
                 f"{sum(1 for r in brows if r[3])} with an LCSC code (lcsc_parts.csv)\n"
                 f"  {NAME}-CPL.csv     {len(rows)} placements; check rotations in the preview\n")
    shutil.copy2(os.path.join(work, "drc.rpt"), os.path.join(dest, "drc.rpt"))

    print(f"{'DRAFT: ' if draft else ''}{os.path.relpath(dest, ROOT)}")
    print(f"  DRC {len(errors)} errors, {unconnected} unrouted")
    print(f"  gerber zip: {len(zipfile.ZipFile(zpath).namelist())} files")
    print(f"  BOM {len(brows)} lines / {sum(r[4] for r in brows)} parts, CPL {len(rows)} placements")
    return 0


if __name__ == "__main__":
    sys.exit(main())
