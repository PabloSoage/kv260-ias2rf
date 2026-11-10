#!/usr/bin/env python3
"""Phase A2 v2 - Clean up the (wire)/(label)/(junction)/(no_connect) blocks left dangling after A1.

The real format in the .kicad_sch:
  (wire
      (pts
          (xy X1 Y1) (xy X2 Y2)
      )
      (stroke ...)
      (uuid "...")
  )

So it parses by balanced parentheses, not by a one-line regex.
The orphan coordinates come from the ERC: @(X mm, Y mm) under the headers
[unconnected_wire_endpoint] or [wire_dangling].

Also deletes (unprotected) labels whose (at X Y) matches, and junctions.
"""
from __future__ import annotations
import pathlib, re, sys, datetime

ROOT = pathlib.Path(r"E:\PCB\adapter_AMD_Xilinx_KRIA-KV260")
SCH  = ROOT / "CSI2-KRIA-KV260_Rev01-2.kicad_sch"
ERC  = ROOT / "CSI2-KRIA-KV260_Rev01-erc.rpt"
LOG  = ROOT / "_work" / "purgeA2_log.txt"

KEEP_LABEL_PATTERNS = [
    r"^B7-CSI2-",
    r"^I2C_",
    r"^PWDN",
    r"^EXT-GPIO",
    r"^GPIO\d",
]
def is_protected_label(name: str) -> bool:
    return any(re.match(p, name) for p in KEEP_LABEL_PATTERNS)

# -------- 1) Orphan coordinates from the ERC --------
erctxt = ERC.read_text(encoding="utf-8")
coord_set = set()
headers = ("[unconnected_wire_endpoint]", "[wire_dangling]")
els = erctxt.splitlines()
i = 0
while i < len(els):
    if any(h in els[i] for h in headers):
        j = i + 1
        while j < len(els) and (els[j].strip()=="" or els[j].strip().startswith(";")):
            j += 1
        while j < len(els) and not els[j].lstrip().startswith("["):
            m = re.match(r"\s*@\(([-0-9.]+)\s*mm,\s*([-0-9.]+)\s*mm\)", els[j])
            if m:
                coord_set.add((round(float(m.group(1)),3), round(float(m.group(2)),3)))
            j += 1
        i = j
    else:
        i += 1
print(f"[i] Orphan coordinates in the ERC (3dp): {len(coord_set)}")

# -------- 2) Localizar (lib_symbols ...) --------
sch_text = SCH.read_text(encoding="utf-8")
sch_lines = sch_text.splitlines(keepends=False)

def find_top_block_start(start_idx: int, keyword: str):
    """Find ` (keyword` opening at or after start_idx and return
    (start,end) 0-based cerrado. keyword no incluira parentesis."""
    pat = re.compile(r"^\s*\(" + re.escape(keyword) + r"\b")
    for i in range(start_idx, len(sch_lines)):
        if pat.match(sch_lines[i]):
            depth = 0
            for j in range(i, len(sch_lines)):
                s = re.sub(r'"[^"]*"', '""', sch_lines[j])
                depth += s.count("(") - s.count(")")
                if depth == 0 and j > i:
                    return (i, j)
    return None

libsyms = find_top_block_start(0, "lib_symbols")
print(f"[i] (lib_symbols) L{libsyms[0]+1}..{libsyms[1]+1}" if libsyms else "[!] lib_symbols not found")

def block_balance(start_idx):
    """Given the index of an opening parenthesis (on the same line), return end_idx."""
    depth = 0
    for j in range(start_idx, len(sch_lines)):
        s = re.sub(r'"[^"]*"', '""', sch_lines[j])
        depth += s.count("(") - s.count(")")
        if depth == 0:
            return j
    return None

# -------- 3) Find every relevant top-level block --------
# Walk the file at "top level" (keywords directly at the
# indent level " \t" for wires/labels/junctions).
# Opening patterns per keyword:
OPEN_PATS = {
    "wire":      re.compile(r'^\s*\(wire\b'),
    "label":     re.compile(r'^\s*\(label\s+"([^"]+)"'),
    "global_label": re.compile(r'^\s*\(global_label\s+"([^"]+)"'),
    "hierarchical_label": re.compile(r'^\s*\(hierarchical_label\s+"([^"]+)"'),
    "junction":  re.compile(r'^\s*\(junction\b'),
    "no_connect": re.compile(r'^\s*\(no_connect\b'),
}

def extract_xy_inside_block(start, end):
    block = "\n".join(sch_lines[start:end+1])
    coords = []
    for m in re.finditer(r'\(at\s+([-0-9.]+)\s+([-0-9.]+)', block):
        coords.append((round(float(m.group(1)),3), round(float(m.group(2)),3)))
    for m in re.finditer(r'\(xy\s+([-0-9.]+)\s+([-0-9.]+)\)\s+\(xy\s+[-0-9.]+\s+[-0-9.]+\)', block):
        coords.append((round(float(m.group(1)),3), round(float(m.group(2)),3)))
    for m in re.finditer(r'\(xy\s+[-0-9.]+\s+[-0-9.]+\)\s+\(xy\s+([-0-9.]+)\s+([-0-9.]+)\)', block):
        coords.append((round(float(m.group(1)),3), round(float(m.group(2)),3)))
    return coords

n = len(sch_lines)
to_delete = set()
i = 0
stats = {k:0 for k in ["wire","label","global_label","hierarchical_label","junction","no_connect"]}
kept   = {k:0 for k in ["wire","label","global_label","hierarchical_label","junction","no_connect"]}
while i < n:
    if libsyms and libsyms[0] <= i <= libsyms[1]:
        i += 1; continue
    m = None; kw = None; name = None
    for k, pat in OPEN_PATS.items():
        m = pat.match(sch_lines[i])
        if m:
            kw = k
            if k in ("label","global_label","hierarchical_label"):
                name = m.group(1)
            break
    if not m:
        i += 1; continue
    end = block_balance(i)
    if end is None:
        print(f"[!!] Block opened and never closed at L{i+1}. Aborting.")
        sys.exit(7)
    coords = extract_xy_inside_block(i, end)
    orphan = any(c in coord_set for c in coords)
    protected = (kw in ("label","global_label","hierarchical_label")) and name and is_protected_label(name)
    if orphan and not protected:
        for k in range(i, end+1):
            to_delete.add(k)
        stats[kw] += 1
    else:
        kept[kw] += 1
    i = end + 1

print(f"[i] Borrado: {stats}")
print(f"[i] Conservado: {kept}")

nuevas = [ln for i,ln in enumerate(sch_lines) if i not in to_delete]
new_text = "\n".join(nuevas) + "\n"
cleaned = re.sub(r'"[^"]*"', '""', new_text)
delta = cleaned.count("(") - cleaned.count(")")
if delta != 0:
    print(f"[!!] Parentesis desbalanceado: delta={delta}. No guardo.")
    sys.exit(8)
SCH.write_text(new_text, encoding="utf-8")
LOG.write_text(
    f"# Purge A2 - {datetime.datetime.now().isoformat()}\n"
    f"# Orphan coordinates in the ERC: {len(coord_set)}\n"
    f"# Borrado: {stats}\n"
    f"# Conservado: {kept}\n"
    f"# Lines before: {len(sch_lines)}, after: {len(nuevas)}\n",
    encoding="utf-8")
print(f"[ok] Before {len(sch_lines)} -> after {len(nuevas)}.")