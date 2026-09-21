#!/usr/bin/env python3
"""
Fix the multi-channel annotation of the shared IAS sheet.

CSI2-KRIA-KV260_Rev01-2.kicad_sch is instantiated twice by the root schematic,
once as IAS0 and once as IAS1. Every symbol therefore carries two
(path ... (reference ...)) entries inside its (instances ...) block — and both
currently hold the SAME reference. That is an annotation error, and it makes
`kicad-cli sch export netlist` refuse to produce a netlist. With no netlist,
"Update PCB from Schematic" cannot run, so no schematic change can ever reach
the layout.

The suffix convention is not invented here: the PCB already uses it. Its 145
references are 68 ending in _IAS0, 68 ending in _IAS1 and 9 with no suffix
(LA1, MRK1-6, T1, T2, which live in the root sheet). All 19 references of the
shared sheet exist in the PCB in both suffixed forms, so writing
<ref>_IAS0 / <ref>_IAS1 into the instances makes the schematic agree with the
layout that is already there.

What this does:
  1. For every symbol in the shared sheet, rewrites the reference of each
     instance path according to which sheet UUID it points at.
  2. Leaves the root schematic alone: its references are already unique.
  3. Checks parenthesis balance before writing.
  4. Reports which references ended up not matching the PCB.

Verify afterwards with:
    kicad-cli sch export netlist -o out.net CSI2-KRIA-KV260_Rev01.kicad_sch

Usage:  py _work/fix_multichannel_annotation.py [--dry-run]
"""

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED = os.path.join(ROOT, "CSI2-KRIA-KV260_Rev01-2.kicad_sch")
PRO = os.path.join(ROOT, "CSI2-KRIA-KV260_Rev01.kicad_pro")
PCB = os.path.join(ROOT, "CSI2-KRIA-KV260_Rev01.kicad_pcb")

DRY = "--dry-run" in sys.argv
QUOTE = chr(34)
BACKSLASH = chr(92)


def sheet_uuids():
    """Map sheet UUID -> sheet name, from the project file."""
    pro = json.load(open(PRO, encoding="utf-8"))
    return {uid: name for uid, name in pro.get("sheets", [])}


def balanced(text):
    depth = 0
    in_str = False
    i = 0
    while i < len(text):
        c = text[i]
        if in_str:
            if c == BACKSLASH:
                i += 2
                continue
            if c == QUOTE:
                in_str = False
        elif c == QUOTE:
            in_str = True
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        i += 1
    return depth == 0


def fix_root_uuid(dry):
    """Make the root schematic's own UUID agree with every instance path.

    Second, independent cause of the annotation failure: the root schematic
    declared (uuid "e5fa38a9-...") while every instance path in the project
    pointed at /56c49378-.... The instance tree therefore referenced a root
    that does not exist, so KiCad could not resolve a single annotation and
    reported the whole schematic as unannotated.

    The count decides which one is wrong: the declared UUID appeared exactly
    once, the one used by the paths appeared 188 times across the root
    schematic, the shared sheet and the project file. So the declaration is
    the outlier and gets rewritten.
    """
    root_sch = os.path.join(ROOT, "CSI2-KRIA-KV260_Rev01.kicad_sch")
    text = open(root_sch, encoding="utf-8").read()

    m = re.search(r'\(uuid "([0-9a-f-]{36})"\)', text)
    declared = m.group(1) if m else None

    paths = re.findall(r'\(path "/([0-9a-f-]{36})', text)
    if not paths:
        print("  no instance paths in the root schematic; nothing to check")
        return True
    used = max(set(paths), key=paths.count)

    print()
    print("Root schematic UUID:")
    print(f"    declared by (uuid ...) : {declared}")
    print(f"    used by instance paths : {used}  ({paths.count(used)} times here)")

    if declared == used:
        print("    they already agree")
        return True

    print(f"    MISMATCH -> rewriting the declaration to {used}")
    if dry:
        return True
    text = text.replace(f'(uuid "{declared}")', f'(uuid "{used}")', 1)
    with open(root_sch, "w", encoding="utf-8", newline=chr(10)) as fh:
        fh.write(text)
    print("    root schematic updated")
    return True


def main():
    sheets = sheet_uuids()
    targets = {uid: name for uid, name in sheets.items() if name in ("IAS0", "IAS1")}
    if len(targets) != 2:
        print(f"Expected IAS0 and IAS1 in the project sheets, found: {sheets}")
        return 1
    print("Sheet instances of the shared sheet:")
    for uid, name in targets.items():
        print(f"    {name}  {uid}")

    text = open(SHARED, encoding="utf-8").read()

    # Each instance entry looks like:
    #   (path "/<root-uuid>/<sheet-uuid>"
    #     (reference "C3")
    #     (unit 1)
    #   )
    pattern = re.compile(
        r'\(path "(/[^"]*/([0-9a-f-]{36}))"\s*\n(\s*)\(reference "([^"]+)"\)',
        re.MULTILINE,
    )

    stats = {"IAS0": 0, "IAS1": 0, "skipped": 0, "already": 0}
    changed = []

    def repl(m):
        full_path, sheet_uid, indent, ref = m.group(1), m.group(2), m.group(3), m.group(4)
        name = targets.get(sheet_uid)
        if name is None:
            stats["skipped"] += 1
            return m.group(0)
        if ref.endswith("_IAS0") or ref.endswith("_IAS1"):
            stats["already"] += 1
            return m.group(0)
        new_ref = f"{ref}_{name}"
        stats[name] += 1
        if not ref.startswith("#"):
            changed.append((ref, new_ref))
        return f'(path "{full_path}"\n{indent}(reference "{new_ref}")'

    out = pattern.sub(repl, text)

    print()
    print(f"Instance references rewritten: IAS0 {stats['IAS0']}, IAS1 {stats['IAS1']}")
    print(f"  already suffixed: {stats['already']}   other sheets: {stats['skipped']}")

    named = sorted({c for c in changed if not c[0].startswith("#")})
    print(f"  named components touched: {len(named) // 2 if named else 0} distinct")

    if not balanced(out):
        print()
        print("ABORTED: the result does not have balanced parentheses.")
        return 1

    # --- cross-check against the PCB -------------------------------------
    pcb = open(PCB, encoding="utf-8").read()
    pcb_refs = {r for r in re.findall(r'\(property "Reference" "([^"]+)"', pcb)
                if r and not r.startswith("#")}
    new_refs = {new for _, new in changed}
    missing = sorted(new_refs - pcb_refs)
    print()
    if missing:
        print(f"  NOTE: {len(missing)} new references are not in the PCB: {missing[:8]}")
    else:
        print(f"  All {len(new_refs)} new references exist in the PCB. Schematic and layout agree.")

    if DRY:
        fix_root_uuid(True)
        print()
        print("--dry-run: nothing written.")
        return 0

    with open(SHARED, "w", encoding="utf-8", newline=chr(10)) as fh:
        fh.write(out)
    print()
    print(f"Written: {SHARED}")
    fix_root_uuid(False)
    print("Now run:  kicad-cli sch export netlist -o out.net CSI2-KRIA-KV260_Rev01.kicad_sch")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
