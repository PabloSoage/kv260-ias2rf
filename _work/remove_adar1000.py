#!/usr/bin/env python3
"""Remove the 8 ADAR1000s from FRONTEND.kicad_sch.

1. Deletes the 8 symbol instances (U_ADR1..U_ADR8) - (symbol ...) blocks
2. Deletes the ADAR1000ACCZN lib_symbol definition
3. Keeps: the J_RPI SPI GPIOs, the RF SMA connectors, and the ADL5801 mixer
"""
import pathlib, re, uuid

DST = pathlib.Path(r"E:\PCB\adapter_AMD_Xilinx_KRIA-KV260\FRONTEND.kicad_sch")
text = DST.read_text(encoding="utf-8")
lines = text.splitlines(keepends=False)
n_orig = len(lines)

# ---- 1. Find and remove the U_ADR1..U_ADR8 instances ----
to_delete = set()
i = 0
while i < len(lines):
    m = re.match(r'^\s*\(symbol\s*$', lines[i])
    if not m:
        i += 1; continue
    # buscar (property "Reference" "U_ADR..."
    j_start = i
    depth = 0
    for j in range(i, len(lines)):
        s = re.sub(r'"[^"]*"', '""', lines[j])
        depth += s.count("(") - s.count(")")
        if depth == 0:
            block = "\n".join(lines[j_start:j+1])
            ref_m = re.search(r'\(property\s+"Reference"\s+"(U_ADR\d)"', block)
            if ref_m:
                # remove the whole block
                for k in range(j_start, j+1):
                    to_delete.add(k)
            i = j + 1
            break
    else:
        i += 1

# ---- 2. Find and remove the ADAR1000's lib_symbol definition ----
i = 0
while i < len(lines):
    if "(symbol" in lines[i] and "ADAR1000ACCZN" in lines[i] and "EasyEDA" in lines[i]:
        # buscar balanceo
        depth = 0
        j_start = i
        for j in range(i, len(lines)):
            s = re.sub(r'"[^"]*"', '""', lines[j])
            depth += s.count("(") - s.count(")")
            if depth == 0:
                for k in range(j_start, j+1):
                    to_delete.add(k)
                break
        i = j + 1
    else:
        i += 1

# Aplicar borrado
nuevas = [ln for idx, ln in enumerate(lines) if idx not in to_delete]
new_text = "\n".join(nuevas) + "\n"

cleaned = re.sub(r'"[^"]*"', '""', new_text)
delta = cleaned.count("(") - cleaned.count(")")
print(f"[i] Lines deleted: {len(to_delete)}. Parentheses delta: {delta}")

if delta == 0:
    DST.write_text(new_text, encoding="utf-8")
    print(f"[ok] ADAR1000s removed. Before {n_orig}, now {len(nuevas)} lines")
else:
    print(f"[!!] Error parentesis")
