#!/usr/bin/env python3
"""Phase D - Tareas finales: SMA, ADL5801 wiring, bypass caps, netclass 50Ω."""
import pathlib, re, uuid

ROOT = pathlib.Path(r"E:\PCB\adapter_AMD_Xilinx_KRIA-KV260")
DST = ROOT / "FRONTEND.kicad_sch"
PRO = ROOT / "CSI2-KRIA-KV260_Rev01.kicad_pro"

text = DST.read_text(encoding="utf-8")
lines = text.splitlines(keepends=False)

# ============================================================
# 1. AÑADIR SÍMBOLO SMA genérico a lib_symbols
# ============================================================
sma_lib_def = """	(symbol "Connector_Coaxial:SMA_EdgeMount"
		(in_bom yes)
		(on_board yes)
		(property "Reference" "J" (at 0 5.08 0) (effects (font (size 1.27 1.27))))
		(property "Value" "SMA" (at 0 -5.08 0) (effects (font (size 1.27 1.27))))
		(property "Footprint" "Connector_Coaxial:SMA_Amphenol_132255-11" (at 0 -7.62 0) (hide yes) (effects (font (size 1.27 1.27))))
		(property "Datasheet" "~" (at 0 0 0) (hide yes) (effects (font (size 1.27 1.27))))
		(symbol "SMA_EdgeMount_0_1"
			(pin passive line (at -7.62 0 0) (length 2.54) (name "~" (effects (font (size 1.27 1.27)))) (number "1" (effects (font (size 1.27 1.27)))))
			(pin passive line (at -7.62 -5.08 0) (length 2.54) (name "~" (effects (font (size 1.27 1.27)))) (number "2" (effects (font (size 1.27 1.27)))))
		)
	)"""

# símbolo genérico de capacitor SMD 0603
cap_lib_def = """	(symbol "Device:C_Small"
		(in_bom yes)
		(on_board yes)
		(property "Reference" "C" (at 0 2.54 0) (effects (font (size 1.27 1.27))))
		(property "Value" "100n" (at 0 -2.54 0) (effects (font (size 1.27 1.27))))
		(property "Footprint" "Capacitor_SMD:C_0603_1608Metric" (at 0 -5.08 0) (hide yes) (effects (font (size 1.27 1.27))))
		(property "Datasheet" "~" (at 0 0 0) (hide yes) (effects (font (size 1.27 1.27))))
		(symbol "C_Small_0_1"
			(rectangle (start -2.54 1.27) (end 2.54 -1.27) (stroke (width 0) (type default)) (fill (type background)))
			(pin passive line (at -5.08 0 0) (length 2.54) (name "~" (effects (font (size 1.27 1.27)))) (number "1" (effects (font (size 1.27 1.27)))))
			(pin passive line (at 5.08 0 0) (length 2.54) (name "~" (effects (font (size 1.27 1.27)))) (number "2" (effects (font (size 1.27 1.27)))))
		)
	)"""

# Encontrar donde termina lib_symbols para insertar
lib_close = None
for i, ln in enumerate(lines):
    if ln.strip() == ")" and i > 0 and "lib_symbols" in lines[i-5] if i > 5 else False:
        pass
# Encontrar: el ); cierra lib_symbols 
for i in range(len(lines)-1,0,-1):
    if lines[i].strip() == ")":
        # ver si la línea anterior comienza una seccion de instancias
        if i+1 < len(lines) and " symbol " in lines[i+1] and lines[i+1].strip().startswith("(symbol"):
            pass
# Mejor: buscar (lib_symbols explicitamente y encontrar su cierre
lib_open = None
for i, ln in enumerate(lines):
    if ln.strip() == "(lib_symbols":
        lib_open = i
        depth = 1
        for j in range(i+1, len(lines)):
            s = re.sub(r'"[^"]*"', '""', lines[j])
            depth += s.count("(") - s.count(")")
            if depth == 0:
                lib_close = j
                break
        break

if lib_close is None:
    print("[!] No encontre lib_symbols close")
    exit(1)

# Insert lib defs antes del cierre
lib_insert = [sma_lib_def, cap_lib_def]
lines[lib_close:lib_close] = lib_insert
print(f"[i] Lib defs SMA + C_Small insertadas en L{lib_close+1}")

# ============================================================
# 2. INSTANCIAR 4× SMA
# ============================================================
sma_instances = ""
smas = [
    ("J_SMA1", 40, 250, "ANT_SDR_RX"),
    ("J_SMA2", 70, 250, "ANT_SDR_TX"),
    ("J_SMA3", 100, 250, "ANT_LO_IN"),
    ("J_SMA4", 240, 250, "ANT_RADAR_RF"),
]
for ref, x, y, val in smas:
    u = uuid.uuid4()
    sma_instances += f"""	(symbol
		(lib_id "Connector_Coaxial:SMA_EdgeMount")
		(at {x} {y} 0)
		(unit 1)
		(body_style 1)
		(exclude_from_sim no)
		(in_bom yes)
		(on_board yes)
		(dnp no)
		(uuid "{u}")
		(property "Reference" "{ref}" (at {x} {y+2.54} 0) (effects (font (size 1.27 1.27))))
		(property "Value" "{val}" (at {x} {y+5.08} 0) (effects (font (size 1.27 1.27))))
		(property "Footprint" "Connector_Coaxial:SMA_Amphenol_132255-11" (at {x} {y} 0) (hide yes) (effects (font (size 1.27 1.27))))
		(property "Datasheet" "~" (at {x} {y} 0) (hide yes) (effects (font (size 1.27 1.27))))
		(instances
			(project "CSI2-KRIA-KV260_Rev01"
				(path "/56c49378-41a8-4cbc-b1f4-3d0ea65d2366"
					(reference "{ref}")
					(unit 1)
				)
			)
		)
	)
"""

# Labels en pines SMA (pin 1 = señal, pin 2 = GND)
sma_labels = ""
for ref, x, y, val in smas:
    u = uuid.uuid4()
    # Pin 1 at (-7.62, 0) rel → abs (x-7.62, y)
    sma_labels += f"""	(label "{val}"
		(at {x-7.62} {y} 0)
		(effects (font (size 1.27 1.27)) (justify left bottom))
		(uuid "{uuid.uuid4()}")
	)
"""
    # Pin 2 (GND) at (-7.62, -5.08) rel → abs (x-7.62, y-5.08)
    sma_labels += f"""	(label "GND"
		(at {x-7.62} {y-5.08} 0)
		(effects (font (size 1.27 1.27)) (justify left bottom))
		(uuid "{uuid.uuid4()}")
	)
"""

# ============================================================
# 3. INSTANCIAR BYPASS CAPACITORS (~16 caps)
# ============================================================
cap_instances = ""
cap_labels = ""
# Lista de (ref, x, y, value, net1, net2)
caps = [
    ("C_BP1", 155, 95, "100n", "VCC1V8_RAW", "GND"),
    ("C_BP2", 155, 100, "100n", "VCC3V3_RAW", "GND"),
    ("C_BP3", 155, 105, "10u", "VCC1V8_RAW", "GND"),
    ("C_BP4", 155, 110, "10u", "VCC3V3_RAW", "GND"),
    ("C_BP5", 165, 95, "100n", "VCC1V8_RAW", "GND"),
    ("C_BP6", 165, 100, "100n", "VCC3V3_RAW", "GND"),
    ("C_BP7", 235, 95, "100n", "VCC1V8_RAW", "GND"),
    ("C_BP8", 235, 100, "100n", "VCC3V3_RAW", "GND"),
    ("C_BP9", 245, 95, "10u", "VCC1V8_RAW", "GND"),
    ("C_BP10", 85, 105, "100n", "VCC3V3_RAW", "GND"),
    ("C_BP11", 85, 110, "100n", "VCC3V3_RAW", "GND"),
    ("C_BP12", 35, 105, "4.7u", "VCC3V3_RAW", "GND"),
    ("C_BP13", 55, 45, "47u", "VCC12V_RAW", "GND"),
    ("C_BP14", 95, 45, "10u", "VCC5V_RAW", "GND"),
    ("C_BP15", 135, 45, "10u", "VCC3V3_RAW", "GND"),
    ("C_BP16", 175, 45, "10u", "VCC1V8_RAW", "GND"),
]
for ref, x, y, val, net1, net2 in caps:
    u = uuid.uuid4()
    cap_instances += f"""	(symbol
		(lib_id "Device:C_Small")
		(at {x} {y} 0)
		(unit 1)
		(body_style 1)
		(exclude_from_sim no)
		(in_bom yes)
		(on_board yes)
		(dnp no)
		(uuid "{u}")
		(property "Reference" "{ref}" (at {x} {y+2.54} 0) (effects (font (size 1.27 1.27))))
		(property "Value" "{val}" (at {x} {y+5.08} 0) (effects (font (size 1.27 1.27))))
		(property "Footprint" "Capacitor_SMD:C_0603_1608Metric" (at {x} {y} 0) (hide yes) (effects (font (size 1.27 1.27))))
		(property "Datasheet" "~" (at {x} {y} 0) (hide yes) (effects (font (size 1.27 1.27))))
		(instances
			(project "CSI2-KRIA-KV260_Rev01"
				(path "/56c49378-41a8-4cbc-b1f4-3d0ea65d2366"
					(reference "{ref}")
					(unit 1)
				)
			)
		)
	)
"""
    # Pin 1 (-5.08, 0) → net1, Pin 2 (+5.08, 0) → net2
    cap_labels += f"""	(label "{net1}"
		(at {x-5.08} {y} 0)
		(effects (font (size 1.27 1.27)) (justify left bottom))
		(uuid "{uuid.uuid4()}")
	)
	(label "{net2}"
		(at {x+5.08} {y} 0)
		(effects (font (size 1.27 1.27)) (justify left bottom))
		(uuid "{uuid.uuid4()}")
	)
"""

# ============================================================
# 4. ADL5801 MIXER WIRING (IF → ADC, RF → switches, LO → SMA)
# ============================================================
mixer_labels = ""
# U_MIX at (240, 180). Pines ADL5801:
# IFOP/IFON (pins 20/21) at (11.43,2.54)/(11.43,5.08) → abs (251.43,182.54)/(251.43,185.08)
# VIN+A/VIN-A of ADC at (16.51,-0.00)/(16.51,-2.54) abs (176.51,110)/(176.51,107.46)
# Conectar IFOP→VIN+A, IFON→VIN-A via labels

# IFOP → ADC VIN+A (176.51, 110.0)
mixer_labels += f"""	(label "MIX_IF_P"
		(at 251.43 182.54 0)
		(effects (font (size 1.27 1.27)) (justify left bottom))
		(uuid "{uuid.uuid4()}")
	)
	(label "MIX_IF_N"
		(at 251.43 185.08 0)
		(effects (font (size 1.27 1.27)) (justify left bottom))
		(uuid "{uuid.uuid4()}")
	)
"""
# Tie MIX_IF_P/N to ADC VIN+A/VIN-A
mixer_labels += f"""	(label "MIX_IF_P"
		(at 176.51 110.0 0)
		(effects (font (size 1.27 1.27)) (justify left bottom))
		(uuid "{uuid.uuid4()}")
	)
	(label "MIX_IF_N"
		(at 176.51 107.46 0)
		(effects (font (size 1.27 1.27)) (justify left bottom))
		(uuid "{uuid.uuid4()}")
	)
"""
# LOIP/LOIN (pins 3/4) at (-11.43,7.62)/(-11.43,5.08) → abs (228.57,187.62)/(228.57,185.08)
# → label MIX_LO_P/N → via global label ANT_LO_IN to SMA
mixer_labels += f"""	(label "MIX_LO_P"
		(at 228.57 187.62 0)
		(effects (font (size 1.27 1.27)) (justify left bottom))
		(uuid "{uuid.uuid4()}")
	)
	(label "MIX_LO_N"
		(at 228.57 185.08 0)
		(effects (font (size 1.27 1.27)) (justify left bottom))
		(uuid "{uuid.uuid4()}")
	)
"""
# RFIP/RFIN (pins 16/15) at (11.43,-7.62)/(11.43,-10.16) → abs (251.43,172.38)/(251.43,169.84)
# Connect to RF switch common port via RF_SW_RADAR label
mixer_labels += f"""	(label "RF_SW_RADAR_P"
		(at 251.43 172.38 0)
		(effects (font (size 1.27 1.27)) (justify left bottom))
		(uuid "{uuid.uuid4()}")
	)
	(label "RF_SW_RADAR_N"
		(at 251.43 169.84 0)
		(effects (font (size 1.27 1.27)) (justify left bottom))
		(uuid "{uuid.uuid4()}")
	)
"""

# ============================================================
# 5. INSERTAR TODO en el archivo
# ============================================================
all_blocks = sma_instances + sma_labels + cap_instances + cap_labels + mixer_labels
text2 = "\n".join(lines) + "\n"

# Hay lineas adicionales; añadir tambien las 5 labels SPI existentes (ya estan del script C5)
insert_pos = text2.rfind("(sheet_instances")
if insert_pos == -1:
    print("[!] No sheet_instances, buscando (embedded_fonts")
    insert_pos = text2.rfind("(embedded_fonts")

text3 = text2[:insert_pos] + all_blocks + text2[insert_pos:]

cleaned = re.sub(r'"[^"]*"', '""', text3)
delta = cleaned.count("(") - cleaned.count(")")
print(f"[i] Parentesis delta: {delta}")

if delta == 0:
    DST.write_text(text3, encoding="utf-8")
    print(f"[ok] SMA={len(smas)} caps={len(caps)} ADL5801 labels={3} añadidos a FRONTEND")
else:
    print(f"[!!] Error parentesis, delta={delta}")