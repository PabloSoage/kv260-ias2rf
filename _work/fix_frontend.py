#!/usr/bin/env python3
"""Fix FRONTEND.kicad_sch: move the power symbols from title_block to lib_symbols."""
import pathlib, re

DST = pathlib.Path(r"E:\PCB\adapter_AMD_Xilinx_KRIA-KV260\FRONTEND.kicad_sch")
lines = DST.read_text(encoding="utf-8").splitlines(keepends=False)

# 1. Find (lib_symbols and its closing )
lib_open = None
lib_close = None
depth = 0
in_lib = False
for i, ln in enumerate(lines):
    s = re.sub(r'"[^"]*"', '""', ln)
    if ln.strip() == "(lib_symbols":
        lib_open = i
        in_lib = True
        depth = 1
        continue
    if in_lib:
        depth += s.count("(") - s.count(")")
        if depth == 0:
            lib_close = i
            break

if lib_open is None or lib_close is None:
    print(f"[!] lib_symbols not found: open={lib_open} close={lib_close}")
    exit(1)
print(f"[i] lib_symbols: L{lib_open+1} .. L{lib_close+1}")

# 2. Find the lines holding the power symbols ("GND_BAR", "VCC3V3_CIRCLE" etc.)
power_keywords = ["GND_BAR", "VCC3V3_CIRCLE", "VCC5V-EXT_CIRCLE", "VCC1V8_CIRCLE",
                  "VCC1V2_CIRCLE", "C-GND_POWER_GROUND"]
power_start = None
power_end = None
for kw in power_keywords:
    for i, ln in enumerate(lines):
        if kw in ln and "(" in ln and "symbol" in ln:
            if power_start is None or i < power_start:
                power_start = i
            # find end of its block
            d = 0
            for j in range(i, len(lines)):
                s = re.sub(r'"[^"]*"', '""', lines[j])
                d += s.count("(") - s.count(")")
                if d == 0:
                    if power_end is None or j > power_end:
                        power_end = j
                    break
            break

if power_start is None:
    print("[!] No power sym defs found")
    exit(1)

print(f"[i] Power defs: L{power_start+1} .. L{power_end+1}")

# 3. Take them out of where they are now
power_block = lines[power_start:power_end+1]
del lines[power_start:power_end+1]

# Adjust lib_close (it moved)
new_lib_close = power_start if power_start < lib_close else lib_close - (power_end - power_start + 1)
if power_start < lib_close:
    new_lib_close = lib_close - (power_end - power_start + 1)
else:
    new_lib_close = lib_close

# 4. Insert before the end of lib_symbols (with the right tabs)
# Adjust lines, since the indices changed
# re-indent: drop 1 tab from each line (they were at 2 tabs = children of title_block, 
# necesitan 2 tabs = children of lib_symbols)
for i in range(len(power_block)):
    if power_block[i].strip():
        power_block[i] = "\t" + power_block[i].lstrip()  # re-normalize a 1 tab

lines[new_lib_close:new_lib_close] = power_block

# 5. Guardar
new_text = "\n".join(lines) + "\n"
cleaned = re.sub(r'"[^"]*"', '""', new_text)
delta = cleaned.count("(") - cleaned.count(")")
print(f"[i] Parentesis delta: {delta}")
if delta == 0:
    DST.write_text(new_text, encoding="utf-8")
    print("[ok] FRONTEND.kicad_sch reparado")
else:
    print(f"[!!] Error de parentesis")