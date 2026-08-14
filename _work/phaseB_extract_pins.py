#!/usr/bin/env python3
"""Phase B v5 - parser tops basado por bloque de pin."""
from __future__ import annotations
import pathlib, re, sys, io

# Redirigir stdout to UTF-8 (windows console cp1252)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)

LIB = pathlib.Path(r"C:\Users\pablo\KiCad\EasyEDA.kicad_sym")
OUT = pathlib.Path(r"E:\PCB\adapter_AMD_Xilinx_KRIA-KV260\_work\pinouts.txt")

CHIPS = [
    "AD9268BCPZ-125","AD9779BSVZ","8132H-T125.000LJ33DT","HMC547ALC3TR",
    "ADL5801ACPZ","ADAR1000ACCZN","ADCLK944BCPZ-R2","AD9253BCPZ-125",
    "DAC3174IRGCR","TPS54202DDCR","TPS82140SILR","ADP151AUJZ-1.8-R7_C462184",
    "SMBJ15A_C83846","PJ-102AH_C3096093","AD9767ASTZ",
]

text = LIB.read_text(encoding="utf-8")
lines = text.splitlines()

def find_block(name: str):
    pat = re.compile(r'^\s*\(symbol\s+"' + re.escape(name) + r'"')
    for i, ln in enumerate(lines):
        if pat.match(ln):
            depth = 0
            for j in range(i, len(lines)):
                s = re.sub(r'"[^"]*"', '""', lines[j])
                depth += s.count("(") - s.count(")")
                if depth == 0 and j > i:
                    return (i, j)
    return None

PIN_OPEN = re.compile(r'\(pin\s+(input|output|bidirectional|passive|power_in|power_out|unspecified|open_collector|open_emitter|emitter)\s+(\S+)')
AT_RE   = re.compile(r'\(at\s+([-0-9.]+)\s+([-0-9.]+)(?:\s+([-0-9.]+))?\)')
NAME_RE = re.compile(r'\(name\s+"([^"]*)"')
NUM_RE  = re.compile(r'\(number\s+"([^"]*)"')

def compute_depth(line):
    s = re.sub(r'"[^"]*"', '""', line)
    return s.count("(") - s.count(")")

def parse_pins(blk_start, blk_end):
    """Para cada apertura de (pin en el bloque, captura las lineas hasta
    que el bloque cierra (parentesis balanceado). Extraer campos dentro."""
    pins = []
    i = blk_start
    while i <= blk_end:
        ln = lines[i]
        m = PIN_OPEN.search(ln)
        if not m:
            i += 1
            continue
        # inicio encontrado en linea i. Acumular bloques linea a linea
        block_lines = []
        # Determinar column del '(' del pin
        col = ln.find("(pin", 0, m.start())
        # Cantidad de '(' antes del col dentro de esta linea
        prefix = ln[:col]
        # Hacer un pseudo-balanceo: depth inicial = (#occurrencias '(' en ln[0:col]) - parentesis de ')'
        # pero partiendo de 0; el '(' del pin abre depth=1.
        depth = 1
        block_lines.append(ln[col:])
        # seguimos en lineas siguientes hasta depth=0
        j = i
        while depth > 0 and j+1 <= blk_end:
            j += 1
            block_lines.append(lines[j])
            depth += compute_depth(lines[j])
        block_str = "\n".join(block_lines)
        at_m  = AT_RE.search(block_str)
        nm_m  = PIN_OPEN.search(block_str)
        pname = NAME_RE.search(block_str)
        pnum  = NUM_RE.search(block_str)
        pins.append({
            "dir": nm_m.group(1) if nm_m else "?",
            "shape": nm_m.group(2) if nm_m else "?",
            "x": at_m.group(1) if at_m else "?",
            "y": at_m.group(2) if at_m else "?",
            "rot": at_m.group(3) if at_m and at_m.group(3) else "",
            "name": pname.group(1) if pname else "?",
            "num":  pnum.group(1) if pnum else "?",
        })
        i = j + 1
    return pins

with OUT.open("w", encoding="utf-8") as f:
    f.write("===== PINOUTS EasyEDA =====\n")
    for name in CHIPS:
        rng = find_block(name)
        f.write(f"\n\n\n=== {name} ===\n")
        if not rng:
            f.write("  [NO ENCONTRADO]\n"); continue
        f.write(f"  lineas {rng[0]+1}..{rng[1]+1}\n")
        pins = parse_pins(rng[0], rng[1])
        def num_key(p):
            x = p.get("num") or ""
            try: return int(x)
            except Exception:
                try: return float(x)
                except Exception: return 9999
        pins_sorted = sorted(pins, key=num_key)
        f.write(f"  Total pins: {len(pins_sorted)}\n")
        f.write(f"  {'Pin':<8} {'Nombre':<32} {'Dir':<14} (x,y)\n")
        for p in pins_sorted:
            f.write(f"  {(p.get('num') or '?'):<8} {(p.get('name') or '?'):<32} {p.get('dir','?'):<14} ({p.get('x','?')},{p.get('y','?')})\n")

print("Pinouts por chip:")
for name in CHIPS:
    rng = find_block(name)
    if rng:
        pins = parse_pins(rng[0], rng[1])
        print(f"  {name}: {len(pins)} pins")
print(f"Archivo: {OUT}")