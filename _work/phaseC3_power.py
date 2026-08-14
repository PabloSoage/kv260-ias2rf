#!/usr/bin/env python3
"""Anade power symbols (GND_BAR, VCC_CIRCLE variants) a FRONTEND.kicad_sch.
Copia definiciones lib de -2.kicad_sch y las instancia con labels."""
import pathlib, re, uuid

ROOT = pathlib.Path(r"E:\PCB\adapter_AMD_Xilinx_KRIA-KV260")
SRC = ROOT / "CSI2-KRIA-KV260_Rev01-2.kicad_sch"
DST = ROOT / "FRONTEND.kicad_sch"

# 1. Extraer defs de GND_BAR, VCC3V3_CIRCLE, etc. del -2.kicad_sch
src_text = SRC.read_text(encoding="utf-8")
src_lines = src_text.splitlines()

def find_all_blocks(lines, keyword_part):
    """Devuelve [(start,end,block_text)] de bloques top-level con keyword en el nombre."""
    res = []
    i = 0
    n = len(lines)
    while i < n:
        if re.match(r'^\s*\(symbol\s+"[^"]*' + re.escape(keyword_part), lines[i]):
            depth = 0
            for j in range(i, len(lines)):
                s = re.sub(r'"[^"]*"', '""', lines[j])
                depth += s.count("(") - s.count(")")
                if depth == 0 and j > i:
                    block = "\n".join(lines[i:j+1])
                    res.append(block)
                    i = j + 1
                    break
            else:
                i += 1
        else:
            i += 1
    return res

power_defs = find_all_blocks(src_lines, "GND_BAR")
power_defs += find_all_blocks(src_lines, "VCC3V3_CIRCLE")
power_defs += find_all_blocks(src_lines, "VCC5V-EXT_CIRCLE")
power_defs += find_all_blocks(src_lines, "VCC1V8_CIRCLE")
power_defs += find_all_blocks(src_lines, "VCC1V2_CIRCLE")
power_defs += find_all_blocks(src_lines, "C-GND_POWER_GROUND")
print(f"[i] Power symbol defs: {len(power_defs)}")

# 2. Insertarlas en el lib_symbols de FRONTEND (despues de los EasyEDA syms, antes del cierre)
dst_text = DST.read_text(encoding="utf-8")
dst_lines = dst_text.splitlines()

# encontrar el cierre de lib_symbols: buscar (lib_symbols primero, luego balancear
lib_open = None
lib_close = None
in_lib = False
depth = 0
for i, ln in enumerate(dst_lines):
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

if lib_open is None:
    print("[!] No se encontro lib_symbols")
    exit(1)
print(f"[i] Insertando power defs antes de L{lib_close+1} (cierre lib_symbols)")

# Insertar defs antes del cierre
power_lines = []
for blk in power_defs:
    for ln in blk.splitlines():
        power_lines.append("\t\t"+ln.strip())
    power_lines.append("")

dst_lines[lib_close:lib_close] = power_lines

# 3. Anadir instancias de power symbols al final del archivo y labels en posiciones
power_instances = []
# GND_BAR en varias posiciones
for name, x, y, value in [
    ("GND_BAR", 40, 30, "GND"),
    ("GND_BAR", 90, 30, "GND"),
    ("GND_BAR", 130, 30, "GND"),
    ("GND_BAR", 170, 30, "GND"),
    ("GND_BAR", 90, 100, "GND"),
    ("GND_BAR", 160, 100, "GND"),
    ("GND_BAR", 240, 100, "GND"),
    ("GND_BAR", 240, 170, "GND"),
]:
    u = uuid.uuid4()
    instance = f"""	(symbol
		(lib_id "CSI2-KRIA-KV260_Rev01-altium-import:{name}")
		(at {x} {y} 0)
		(unit 1)
		(body_style 1)
		(exclude_from_sim no)
		(in_bom yes)
		(on_board yes)
		(dnp no)
		(uuid "{u}")
		(property "Reference" "#PWR?" (at {x} {y} 0) (hide yes) (effects (font (size 1.27 1.27))))
		(property "Value" "{value}" (at {x} {y} 0) (effects (font (size 1.27 1.27))))
		(property "Footprint" "" (at {x} {y} 0) (hide yes) (effects (font (size 1.27 1.27))))
		(property "Datasheet" "" (at {x} {y} 0) (hide yes) (effects (font (size 1.27 1.27))))
		(pin "{value}" (uuid "{uuid.uuid4()}"))
		(instances
			(project "CSI2-KRIA-KV260_Rev01"
				(path "/56c49378-41a8-4cbc-b1f4-3d0ea65d2366"
					(reference "#PWR?")
					(unit 1)
				)
			)
		)
	)"""
    power_instances.append(instance)

# VCC symbols
vcc_syms = [
    ("VCC3V3_CIRCLE", 130, 35, "VCC3V3_RAW"),
    ("VCC3V3_CIRCLE", 100, 60, "VCC3V3_RAW"),
    ("VCC3V3_CIRCLE", 80, 160, "VCC3V3_RAW"),
    ("VCC5V-EXT_CIRCLE", 60, 50, "VCC5V_RAW"),
    ("VCC5V-EXT_CIRCLE", 230, 175, "VCC5V_RAW"),
    ("VCC1V8_CIRCLE", 165, 35, "VCC1V8_RAW"),
    ("VCC1V8_CIRCLE", 150, 100, "VCC1V8_RAW"),
]
for sym_name, x, y, value in vcc_syms:
    u = uuid.uuid4()
    lib_id = f"CSI2-KRIA-KV260_Rev01-altium-import:{sym_name}"
    instance = f"""	(symbol
		(lib_id "{lib_id}")
		(at {x} {y} 0)
		(unit 1)
		(body_style 1)
		(exclude_from_sim no)
		(in_bom yes)
		(on_board yes)
		(dnp no)
		(uuid "{u}")
		(property "Reference" "#PWR?" (at {x} {y} 0) (hide yes) (effects (font (size 1.27 1.27))))
		(property "Value" "{value}" (at {x} {y} 0) (effects (font (size 1.27 1.27))))
		(property "Footprint" "" (at {x} {y} 0) (hide yes) (effects (font (size 1.27 1.27))))
		(property "Datasheet" "" (at {x} {y} 0) (hide yes) (effects (font (size 1.27 1.27))))
		(pin "{value}" (uuid "{uuid.uuid4()}"))
		(instances
			(project "CSI2-KRIA-KV260_Rev01"
				(path "/56c49378-41a8-4cbc-b1f4-3d0ea65d2366"
					(reference "#PWR?")
					(unit 1)
				)
			)
		)
	)"""
    power_instances.append(instance)

# Insertar antes de sheet_instances
final_text = "\n".join(dst_lines) + "\n"
insert2 = final_text.rfind("(sheet_instances")
final_text = final_text[:insert2] + "\n".join(power_instances) + "\n\n" + final_text[insert2:]

# Verificar parentesis
cleaned = re.sub(r'"[^"]*"', '""', final_text)
delta = cleaned.count("(") - cleaned.count(")")
if delta != 0:
    print(f"[!!] Delta parentesis = {delta}")
else:
    DST.write_text(final_text, encoding="utf-8")
    print(f"[ok] {len(power_instances)} symbolos de poder anadidos a FRONTEND")