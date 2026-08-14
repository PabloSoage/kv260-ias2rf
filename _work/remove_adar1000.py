#!/usr/bin/env python3
"""Elimina los 8 ADAR1000 de FRONTEND.kicad_sch.

1. Borra las 8 instancias de simbolo (U_ADR1..U_ADR8) - bloques (symbol ...)
2. Borra la definicion lib_symbol del ADAR1000ACCZN
3. Conserva: J_RPI GPIOs SPI, conectores SMA para RF, y el mezclador ADL5801
"""
import pathlib, re, uuid

DST = pathlib.Path(r"E:\PCB\adapter_AMD_Xilinx_KRIA-KV260\FRONTEND.kicad_sch")
text = DST.read_text(encoding="utf-8")
lines = text.splitlines(keepends=False)
n_orig = len(lines)

# ---- 1. Encontrar y eliminar instancias U_ADR1..U_ADR8 ----
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
                # eliminar todo el bloque
                for k in range(j_start, j+1):
                    to_delete.add(k)
            i = j + 1
            break
    else:
        i += 1

# ---- 2. Encontrar y eliminar la def lib_symbol del ADAR1000 ----
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
print(f"[i] Lineas borradas: {len(to_delete)}. Delta parentesis: {delta}")

if delta == 0:
    DST.write_text(new_text, encoding="utf-8")
    print(f"[ok] ADAR1000 purgados. Antes {n_orig}, ahora {len(nuevas)} lineas")
else:
    print(f"[!!] Error parentesis")
