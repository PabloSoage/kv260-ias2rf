#!/usr/bin/env python3
"""Phase A1 - PURGA del CSI2-KRIA-KV260_Rev01-2.kicad_sch

Borra bloques top-level (symbol ...) por rango de lineas confirmado en
el inventario. NO toca wires/labels/junctions (se asume que el usuario
limpiara visualmente en KiCad). Producimos un diff estilo "antes/despues"
y un archivo de log con el borrado.

DEFENSIVO: solo borra si al leer la primera linea del rango se confirma
que empieza con '(symbol ' (con indentacion), para evitar corromper.
"""
from __future__ import annotations
import pathlib, sys, re, datetime

ROOT = pathlib.Path(r"E:\PCB\adapter_AMD_Xilinx_KRIA-KV260")
SCH  = ROOT / "CSI2-KRIA-KV260_Rev01-2.kicad_sch"
LOG  = ROOT / "_work" / "purge_log.txt"

# Refs y rangos (1-based, inclusive) confirmados por inventario
TO_DELETE = [
    # AGroup: FFC camara
    ("J7", 17595, 17806, "FFC22 camara MIPI"),
    # Reguladores / I2C / control optica
    ("U5", 23525, 23687, "NCP114 LDO 3V3 camara"),
    ("U4", 14279, 14453, "NTB0104 level shifter 4-bit"),
    ("U3", 26307, 26469, "PCA9306 I2C level shifter"),
    ("U1", 15920, 16106, "INA260 monitor corriente camara"),
    ("U2", 15738, 15919, "TPS25200 USB power switch"),
    ("D1", 26161, 26306, "ESD9B5.0ST5G (ESD USB)"),
    # LEDs status camara
    ("D2", 13862, 14030, "LED rojo camara"),
    ("D3", 14109, 14278, "LED verde camara"),
    # USB + pin headers expansion
    ("J1", 27626, 27791, "USB 2.0 Type B (camara/alim)"),
    ("J2", 19103, 19247, "CON1x2 2.54"),
    ("J5", 28279, 28418, "Jumper 2.54"),
    ("J6", 14860, 15008, "CON1x3 2.54"),
    ("J9", 16962, 17112, "CON1x4 2.54"),
    ("J10", 22416, 22566, "CON1x4 2.54"),
]

# Verificar rangos no solapan
rngs = sorted([(s,e) for _,s,e,_ in TO_DELETE])
for i in range(len(rngs)-1):
    if rngs[i][1] >= rngs[i+1][0]:
        print(f"[!!] SOLAPAMIENTO entre {rngs[i]} y {rngs[i+1]}")
        sys.exit(2)

text = SCH.read_text(encoding="utf-8")
lines = text.splitlines(keepends=False)
total_before = len(lines)

# Verificar cada rango
print(f"[i] Archivo: {SCH.name}, lineas originales: {total_before}")
print(f"[i] Componentes a borrar: {len(TO_DELETE)}")
log_lines = []
log_lines.append(f"# Purge log - {datetime.datetime.now().isoformat()}\n")
log_lines.append(f"# Archivo: {SCH}\n")
log_lines.append(f"# Lineas antes: {total_before}\n\n")

# vamos a borrar lineas con indices 0-based [s-1, e-1] inclusive.
# Verificamos que la primera linea del rango empieza (ignorando espacios)
# con '(symbol' para confirmar:
confirmados = []
for ref, s, e, descr in TO_DELETE:
    s0 = s - 1
    e0 = e - 1
    head = lines[s0].lstrip()
    if not head.startswith("(symbol"):
        print(f"[!!] Rango para {ref} L{s}-L{e}: la primera linea NO empieza con '(symbol'. Abortando.")
        print(f"     L{s}: {lines[s0][:120]!r}")
        sys.exit(3)
    # tambien verificar paridad de parentesis en el rango
    block = "\n".join(lines[s0:e0+1])
    # limpiar strings para no confundir
    cleaned = re.sub(r'"[^"]*"', '""', block)
    depth = cleaned.count("(") - cleaned.count(")")
    if depth != 0:
        print(f"[!!] Rango {ref} L{s}-L{e}: parentesis NO balanceados (delta={depth}). Abortando rango.")
        continue
    confirmados.append((ref, s0, e0, descr))
    print(f"[ok] {ref:5} L{s}-L{e} confirmado ({e-s+1} lineas): {descr}")

# Ahora borrar de abajo a arriba para preservar indices
confirmados.sort(key=lambda x: x[1], reverse=True)
borradas = 0
nuevas = list(lines)
for ref, s0, e0, descr in confirmados:
    log_lines.append(f"  BORRADO {ref:5} L{s0+1}-L{e0+1} ({e0-s0+1} ln): {descr}\n")
    del nuevas[s0:e0+1]
    borradas += (e0 - s0 + 1)

log_lines.append(f"\n# Total borradas: {borradas} lineas\n")
log_lines.append(f"# Lineas despues: {len(nuevas)}\n")
LOG.write_text("".join(log_lines), encoding="utf-8")

# Guardar archivo
SCH.write_text("\n".join(nuevas) + "\n", encoding="utf-8")
print(f"\n[ok] Borradas {borradas} lineas. Lineas ahora: {len(nuevas)}.")
print(f"[ok] Log: {LOG}")
print(f"[ok] Backup previo en _backup_original/ (ya hecho).")