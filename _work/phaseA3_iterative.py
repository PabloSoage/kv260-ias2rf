#!/usr/bin/env python3
"""Phase A3 - Hunt down orphan references. Iterative:
1. Read the current .kicad_sch (phase A2 already applied).
2. Quick in-memory inventory: ref -> (line_start,line_end).
3. Read the ERC (CSI2-KRIA-KV260_Rev01-erc.rpt) and extract the refs cited in
   pin_not_connected / label_dangling / wire_dangling / no_connect_dangling
   / unconnected_wire_endpoint.
4. Leave out the untouchable refs: J8 (Hirose), #PWR? (power symbols), TP* if
   marked to keep, X1 (mount hole), MRK*, PCB1, T*, LA1.
5. If a ref has AT LEAST one pin flagged pin_not_connected ON THE
   PART (not on the wire), and is NOT J8 or a power symbol -> delete it.
6. Dangling labels and wires that are not protected are deleted too.
7. Repeat until it converges (at most 4 iterations), with kicad-cli
   regenerating the ERC on each pass.

Defensive: checks the parentheses balance after each pass; aborts on any doubt.
"""
from __future__ import annotations
import pathlib, re, sys, subprocess, datetime, shutil, os

ROOT = pathlib.Path(r"E:\PCB\adapter_AMD_Xilinx_KRIA-KV260")
SCH  = ROOT / "CSI2-KRIA-KV260_Rev01-2.kicad_sch"
ERC  = ROOT / "CSI2-KRIA-KV260_Rev01-erc.rpt"
LOG  = ROOT / "_work" / "purgeA3_iter.log"
KICAD_CLI = r"E:\Program Files\KiCad\10.0\bin\kicad-cli.exe"

KEEP_REFS = {"J8","X1","PCB1","LA1"}  # mantener siempre
KEEP_REF_PREFIXES = ("MRK","T","TP")    # kept; the user decides at the end
PROTECTED_LABEL_PATTERNS = [r"^B7-CSI2-", r"^I2C_", r"^PWDN", r"^EXT-GPIO", r"^GPIO\d"]

def is_protected_label(name: str) -> bool:
    return any(re.match(p, name) for p in PROTECTED_LABEL_PATTERNS)

def run_erc():
    res = subprocess.run([KICAD_CLI, "sch", "erc", str(ROOT/"CSI2-KRIA-KV260_Rev01.kicad_sch")],
                         cwd=str(ROOT), capture_output=True, text=True, timeout=180)
    return res.stdout + res.stderr

def parse_erc_refs(erc_path: pathlib.Path):
    """Return a dict {ref: [ (pin_no, pin_type, sheet) ]}. For #PWR? no pin
    number is attached, but it is included. Limited to pin_not_connected."""
    text = erc_path.read_text(encoding='utf-8')
    els = text.splitlines()
    i = 0
    refs_map = {}
    while i < len(els):
        if '[pin_not_connected]' in els[i]:
            j = i + 1
            while j < len(els) and (els[j].strip()=='' or els[j].strip().startswith(';')): j += 1
            while j < len(els) and not els[j].lstrip().startswith('['):
                line = els[j].strip()
                # format: @(X,Y): Symbol REF Pin N [N, type, ...]
                m = re.match(r"@\(.*?\):\s*Symbol\s+(\S+)\s+Pin\s+(\d+)\s+\[", line)
                if m:
                    refs_map.setdefault(m.group(1), set()).add(m.group(2))
                else:
                    # hidden pin power: 'Symbol #PWR? Hidden pin  [NET, Power input, Line]'
                    m2 = re.match(r"@\(.*?\):\s*Symbol\s+(#\S+)\s+Hidden pin", line)
                    if m2:
                        refs_map.setdefault(m2.group(1), set()).add('hid')
                j += 1
            i = j
        else:
            i += 1
    return refs_map

def find_libsyms_range(lines):
    for i, ln in enumerate(lines):
        if re.match(r"^\s*\(lib_symbols\s*$", ln):
            depth = 0
            for j in range(i, len(lines)):
                s = re.sub(r'"[^"]*"', '""', lines[j])
                depth += s.count("(") - s.count(")")
                if depth == 0 and j > i:
                    return (i, j)
    return None

def block_balance(lines, start):
    depth = 0
    for j in range(start, len(lines)):
        s = re.sub(r'"[^"]*"', '""', lines[j])
        depth += s.count("(") - s.count(")")
        if depth == 0:
            return j
    return None

def find_top_symbol_block_by_ref(lines, target_ref, libsyms):
    """Find the top-level (symbol ...) whose Reference is target_ref. Return (s,e)."""
    i = 0
    n = len(lines)
    while i < n:
        if libsyms and libsyms[0] <= i <= libsyms[1]:
            i += 1; continue
        if not re.match(r"^\s*\(symbol\s*$", lines[i]):
            i += 1; continue
        end = block_balance(lines, i)
        if end is None: return None
        block = "\n".join(lines[i:end+1])
        m = re.search(r'\(property\s+"Reference"\s+"([^"]+)"', block)
        if m and m.group(1) == target_ref:
            return (i, end)
        i = end + 1
    return None

def find_label_block_by_coord(lines, coord_set, libsyms):
    """Return a list of (start,end) of the label/global_label/hierarchical_label blocks
    whose (at X Y) falls in coord_set and is not protected."""
    res = []
    i = 0
    n = len(lines)
    pats = [
        (re.compile(r'^\s*\(label\s+"([^"]+)"'), 'label'),
        (re.compile(r'^\s*\(global_label\s+"([^"]+)"'), 'global'),
        (re.compile(r'^\s*\(hierarchical_label\s+"([^"]+)"'), 'hier'),
    ]
    while i < n:
        if libsyms and libsyms[0] <= i <= libsyms[1]:
            i += 1; continue
        matched = False
        name = None
        kind = None
        for pat, k in pats:
            m = pat.match(lines[i])
            if m:
                matched = True
                name = m.group(1); kind = k
                break
        if not matched:
            i += 1; continue
        end = block_balance(lines, i)
        if end is None: return res
        block = "\n".join(lines[i:end+1])
        m = re.search(r'\(at\s+([-0-9.]+)\s+([-0-9.]+)', block)
        if m:
            c = (round(float(m.group(1)),3), round(float(m.group(2)),3))
            if c in coord_set and not is_protected_label(name or ''):
                res.append((i, end))
        i = end + 1
    return res

def find_wire_block_by_coord(lines, coord_set, libsyms):
    res = []
    i = 0
    n = len(lines)
    pat = re.compile(r"^\s*\(wire\b")
    while i < n:
        if libsyms and libsyms[0] <= i <= libsyms[1]:
            i += 1; continue
        if not pat.match(lines[i]):
            i += 1; continue
        end = block_balance(lines, i)
        if end is None: return res
        block = "\n".join(lines[i:end+1])
        coords = []
        for m in re.finditer(r'\(xy\s+([-0-9.]+)\s+([-0-9.]+)', block):
            coords.append((round(float(m.group(1)),3), round(float(m.group(2)),3)))
        if any(c in coord_set for c in coords):
            res.append((i, end))
        i = end + 1
    return res

def find_junction_block_by_coord(lines, coord_set, libsyms):
    res = []
    i = 0; n = len(lines)
    pat = re.compile(r"^\s*\(junction\b")
    while i < n:
        if libsyms and libsyms[0] <= i <= libsyms[1]:
            i += 1; continue
        if not pat.match(lines[i]):
            i += 1; continue
        end = block_balance(lines, i)
        if end is None: return res
        block = "\n".join(lines[i:end+1])
        m = re.search(r'\(at\s+([-0-9.]+)\s+([-0-9.]+)', block)
        if m:
            c = (round(float(m.group(1)),3), round(float(m.group(2)),3))
            if c in coord_set: res.append((i, end))
        i = end + 1
    return res

def is_deletable_ref(ref: str, refs_map: dict) -> bool:
    if ref in KEEP_REFS: return False
    for pref in KEEP_REF_PREFIXES:
        if ref.startswith(pref) and ref[len(pref):].isdigit():
            return False
    if ref.startswith('#'): return False  # power symbol; lo tratamos aparte
    if ref not in refs_map: return False
    return True

def parse_orphan_coords(erc_path):
    text = erc_path.read_text(encoding='utf-8')
    els = text.splitlines()
    coord_set = set()
    headers = ("[unconnected_wire_endpoint]", "[wire_dangling]",
              "[label_dangling]", "[no_connect_dangling]")
    i = 0
    while i < len(els):
        if any(h in els[i] for h in headers):
            j = i + 1
            while j < len(els) and (els[j].strip()=='' or els[j].strip().startswith(';')): j += 1
            while j < len(els) and not els[j].lstrip().startswith('['):
                m = re.match(r"\s*@\(([-0-9.]+)\s*mm,\s*([-0-9.]+)\s*mm\)", els[j])
                if m:
                    coord_set.add((round(float(m.group(1)),3), round(float(m.group(2)),3)))
                # for label_dangling/no_connect_dangling '(at X Y)' shows up too
                m2 = re.match(r"\s*\(at\s+([-0-9.]+)\s+([-0-9.]+)\)", els[j])
                if m2:
                    coord_set.add((round(float(m2.group(1)),3), round(float(m2.group(2)),3)))
                j += 1
            i = j
        else:
            i += 1
    return coord_set

# ---- iterative loop ----
total_deleted = 0
all_logs = []
for it in range(1, 5):
    print(f"\n=== Iteracion {it} ===")
    out = run_erc()
    print("ERC out:", out.strip()[:200])
    if not ERC.exists():
        print("[!] No ERC file."); break
    refs_map = parse_erc_refs(ERC)
    print(f"Refs con pin_not_connected: {len(refs_map)}")
    print("Candidate refs to delete:",
          [r for r in refs_map if is_deletable_ref(r, refs_map)][:30], '...')
    coord_set = parse_orphan_coords(ERC)
    print(f"Orphan coords (label/wire): {len(coord_set)}")

    sch_lines = SCH.read_text(encoding='utf-8').splitlines(keepends=False)
    libsyms = find_libsyms_range(sch_lines)
    if not libsyms:
        print("[!] lib_symbols not found"); break

    to_delete = set()
    del_refs = []
    for ref in list(refs_map.keys()):
        if not is_deletable_ref(ref, refs_map): continue
        blk = find_top_symbol_block_by_ref(sch_lines, ref, libsyms)
        if blk:
            for k in range(blk[0], blk[1]+1):
                to_delete.add(k)
            del_refs.append(ref)
    # labels y wires
    label_blocks = find_label_block_by_coord(sch_lines, coord_set, libsyms)
    for s,e in label_blocks:
        for k in range(s,e+1): to_delete.add(k)
    wire_blocks = find_wire_block_by_coord(sch_lines, coord_set, libsyms)
    for s,e in wire_blocks:
        for k in range(s,e+1): to_delete.add(k)
    j_blocks = find_junction_block_by_coord(sch_lines, coord_set, libsyms)
    for s,e in j_blocks:
        for k in range(s,e+1): to_delete.add(k)

    n_del = len(to_delete)
    print(f"Refs to delete: {del_refs}")
    print(f"Delete {len(label_blocks)} labels, {len(wire_blocks)} wires, {len(j_blocks)} junctions")
    print(f"Total lines to delete: {n_del}")
    if n_del == 0:
        print("[ok] Converged."); break

    nuevas = [ln for i,ln in enumerate(sch_lines) if i not in to_delete]
    new_text = "\n".join(nuevas) + "\n"
    cleaned = re.sub(r'"[^"]*"', '""', new_text)
    delta = cleaned.count("(") - cleaned.count(")")
    if delta != 0:
        print(f"[!!] Parentheses unbalanced after deleting: delta={delta}. Aborting.")
        sys.exit(9)
    SCH.write_text(new_text, encoding='utf-8')
    all_logs.append(f"Iter {it}: refs={del_refs}, labels={len(label_blocks)}, "
                    f"wires={len(wire_blocks)}, junctions={len(j_blocks)}, lines={n_del}\n")
    total_deleted += n_del

LOG.write_text(
    f"# Purge A3 - {datetime.datetime.now().isoformat()}\n"
    f"# Total iteracciones: {len(all_logs)}\n"
    f"# Total lines deleted: {total_deleted}\n\n"
    + "".join(all_logs),
    encoding='utf-8')
print(f"\n[ok] Total deleted: {total_deleted} lines. Log: {LOG}")