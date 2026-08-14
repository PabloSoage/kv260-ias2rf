#!/usr/bin/env python3
"""Convierte (label ...) a (hierarchical_label ...) en-2.kicad_sch."""
import pathlib, re, sys

SCH = pathlib.Path(r"E:\PCB\adapter_AMD_Xilinx_KRIA-KV260\CSI2-KRIA-KV260_Rev01-2.kicad_sch")
lines = SCH.read_text(encoding="utf-8").splitlines(keepends=False)

NETS_MATCH = re.compile(r"^(B7-CSI2-|I2C_SCL$|I2C_SDA$|I2C_SCL_3V3$|I2C_SDA_3V3$|PWDN|EXT-GPIO|GPIO\d|INA260-)")

def balance_end(start):
    depth = 0
    for j in range(start, len(lines)):
        s = re.sub(r'"[^"]*"', '""', lines[j])
        depth += s.count("(") - s.count(")")
        if depth == 0:
            return j
    return None

i = 0
n = len(lines)
converted = 0
while i < n:
    m = re.match(r'^\s*\(label\s+"([^"]+)"\s*$', lines[i])
    if not m:
        i += 1; continue
    name = m.group(1)
    if not NETS_MATCH.match(name):
        i += 1; continue
    end = balance_end(i)
    if end is None:
        i += 1; continue
    # reemplazar (label "X" -> (hierarchical_label "X" (shape bidirectional)
    old_first = lines[i]
    indent = old_first[:len(old_first) - len(old_first.lstrip())]
    new_first = f'{indent}(hierarchical_label "{name}" (shape bidirectional)'
    lines[i] = new_first
    converted += 1
    i = end + 1

SCH.write_text("\n".join(lines)+"\n", encoding="utf-8")
print(f"[ok] Convertidos {converted} labels a hierarchical_label")
print("[ok] Verificando con ERC...")
import subprocess
r = subprocess.run([r"E:\Program Files\KiCad\10.0\bin\kicad-cli.exe","sch","erc",
    str(SCH.parent/"CSI2-KRIA-KV260_Rev01.kicad_sch")], capture_output=True, text=True)
print(r.stdout.strip().splitlines()[-1] if r.stdout else r.stderr.strip()[:200])