#!/usr/bin/env python3
"""Tareas finales: no-connect en pines no usados + conectores SMA + documentar interfaz externa."""
import pathlib, re, uuid

ROOT = pathlib.Path(r"E:\PCB\adapter_AMD_Xilinx_KRIA-KV260")
DST = ROOT / "FRONTEND.kicad_sch"

text = DST.read_text(encoding="utf-8")
lines = text.splitlines(keepends=False)

# ---- 1. NO-CONNECT en pines no usados del ADC AD9253 ----
# Pinout AD9253:
# Channel A (SDR): D0±A (pins 28,27) + D1±A (pins 26,25) — D1±A UNUSED
# Channel B (Radar): D0±B (pins 24,23) + D1±B (pins 22,21) — D1±B UNUSED
# Channel C (unused): D0±C(pins 16,15) + D1±C(pins 14,13) — ALL UNUSED
# Channel D (unused): D0±D(pins 12,11) + D1±D(pins 10,9) — ALL UNUSED
# VIN±C (pins 48,47), VIN±D (pins 2,1) — UNUSED
# VNI±B, VNI±C (analog unused)

adc_unused_pins = [
    # D0+C/D, D1+C/D, D0-D/D, D1-D/C
    ("U_ADC", 12), ("U_ADC", 11),  # D0±D
    ("U_ADC", 14), ("U_ADC", 13),  # D1±C
    ("U_ADC", 16), ("U_ADC", 15),  # D0±C
    ("U_ADC", 22), ("U_ADC", 21),  # D1±B
    ("U_ADC", 26), ("U_ADC", 25),  # D1±A
    ("U_ADC", 2),  ("U_ADC", 1),   # VIN±D
    ("U_ADC", 48), ("U_ADC", 47),  # VIN±C
    ("U_ADC", 38), ("U_ADC", 37),  # VNI±B
]

# ---- Posiciones absolutas de los pines (usando offsets de pinouts.txt) ----
# AD9253 at (160, 110)
# Pin rel positions from pinouts.txt:
adc_rel = {
    1: (-16.51,30.48), 2: (-16.51,27.94), 3:(-16.51,25.40), 4:(-16.51,22.86),
    5:(-16.51,20.32), 6:(-16.51,17.78), 7:(-16.51,15.24), 8:(-16.51,12.70),
    9:(-16.51,10.16), 10:(-16.51,7.62), 11:(-16.51,5.08), 12:(-16.51,2.54),
    13:(-16.51,-0.00), 14:(-16.51,-2.54), 15:(-16.51,-5.08), 16:(-16.51,-7.62),
    17:(-16.51,-10.16), 18:(-16.51,-12.70), 19:(-16.51,-15.24), 20:(-16.51,-17.78),
    21:(-16.51,-20.32), 22:(-16.51,-22.86), 23:(-16.51,-25.40), 24:(-16.51,-27.94),
    25:(16.51,-27.94), 26:(16.51,-25.40), 27:(16.51,-22.86), 28:(16.51,-20.32),
    29:(16.51,-17.78), 30:(16.51,-15.24), 31:(16.51,-12.70), 32:(16.51,-10.16),
    33:(16.51,-7.62), 34:(16.51,-5.08), 35:(16.51,-2.54), 36:(16.51,-0.00),
    37:(16.51,2.54), 38:(16.51,5.08), 39:(16.51,7.62), 40:(16.51,10.16),
    41:(16.51,12.70), 42:(16.51,15.24), 43:(16.51,17.78), 44:(16.51,20.32),
    45:(16.51,22.86), 46:(16.51,25.40), 47:(16.51,27.94), 48:(16.51,30.48),
    49:(0.00,-33.02),  # EP
}

adc_x, adc_y = 160, 110
no_connects = []
for key, pin_num in adc_unused_pins:
    if key != "U_ADC": continue
    dx, dy = adc_rel.get(pin_num, (0,0))
    abs_x = round(adc_x + dx, 4)
    abs_y = round(adc_y + dy, 4)
    no_connects.append((abs_x, abs_y))

# ---- DAC AD9767 canal B no usado ----
# DB0P2..DB13P2 (pins 36..23 reversed), WRT2(pin20), CLK2(pin19)
# DAC at (240, 110)
dac_rel = {
    36:(17.78,-1.27), 35:(17.78,-3.81), 34:(17.78,-6.35), 33:(17.78,-8.89),
    32:(17.78,-11.43), 31:(17.78,-13.97), 30:(17.78,-16.51), 29:(17.78,-19.05),
    28:(17.78,-21.59), 27:(17.78,-24.13), 26:(17.78,-26.67), 25:(17.78,-29.21),
    24:(-17.78,-29.21), 23:(-17.78,-26.67),
    20:(-17.78,-19.05), 19:(-17.78,-16.51),
    48:(17.78,29.21),  # MODE
    42:(17.78,13.97),  # GAINCTRL
    41:(17.78,11.43),  # FSADJ2
    40:(17.78,8.89),   # IOUTB2
    39:(17.78,6.35),   # IOUTA2
    45:(17.78,21.59),  # IOUTB1 (solo IOUTA1 usado)
}
dac_x, dac_y = 240, 110
for pin_num in [23,24,25,26,27,28,29,30,31,32,33,34,35,36,19,20,39,40,41,42,45,48]:
    dx, dy = dac_rel.get(pin_num, (0,0))
    abs_x = round(dac_x + dx, 4)
    abs_y = round(dac_y + dy, 4)
    no_connects.append((abs_x, abs_y))

# ---- Generar bloques (no_connect ...) ----
nc_blocks = []
for x, y in no_connects:
    u = uuid.uuid4()
    nc_blocks.append(f"""	(no_connect
		(at {x} {y})
		(uuid "{u}")
	)""")

# Insertar antes de sheet_instances
text2 = "\n".join(lines) + "\n"
insert_pos = text2.rfind("(sheet_instances")
if insert_pos == -1:
    insert_pos = text2.rfind("(embedded_fonts")
text3 = text2[:insert_pos] + "\n".join(nc_blocks) + "\n\n" + text2[insert_pos:]

# ---- 2. Labels de conexión RF hacia conectores SMA (a colocar en GUI) ----
sma_labels = [
    (45, 245, "ANT_SDR_RX", "input"),
    (75, 245, "ANT_SDR_TX", "output"),
    (105, 245, "ANT_LO_IN", "input"),
    (245, 245, "ANT_RADAR_RF", "bidirectional"),
]
sma_blocks = []
for x, y, name, shape in sma_labels:
    u = uuid.uuid4()
    sma_blocks.append(f"""	(global_label "{name}" (shape {shape})
		(at {x} {y} 0)
		(effects (font (size 1.27 1.27)))
		(uuid "{u}")
	)""")

insert2 = text3.rfind("(sheet_instances")
text4 = text3[:insert2] + "\n".join(sma_blocks) + "\n\n" + text3[insert2:]

# ---- 3. Labels de interfaz para placa externa Phased Array ----
# GPIOs 16-20 del J_RPI (SPI bus daisy-chain hacia placa externa de ADAR1000)
interface_labels = [
    (317.30, 163.34 - 15.24, "SPI_SCLK_EXT"),   # GPIO16
    (342.70, 163.34 - 15.24, "SPI_SDIO_EXT"),   # GPIO17
    (317.30, 163.34 - 17.78, "SPI_CSB_EXT"),    # GPIO18
    (342.70, 163.34 - 17.78, "TR_CTRL_EXT"),    # GPIO19
    (317.30, 163.34 - 20.32, "TX_LOAD_EXT"),    # GPIO20
]
ext_labels = []
for x, y, name in interface_labels:
    u = uuid.uuid4()
    ext_labels.append(f"""	(label "{name}"
		(at {x} {y} 0)
		(effects (font (size 1.27 1.27)) (justify left bottom))
		(uuid "{u}")
	)""")

insert3 = text4.rfind("(sheet_instances")
text5 = text4[:insert3] + "\n".join(ext_labels) + "\n\n" + text4[insert3:]

# Verificar parentesis
cleaned = re.sub(r'"[^"]*"', '""', text5)
delta = cleaned.count("(") - cleaned.count(")")
print(f"[i] No-connects: {len(no_connects)}, SMA labels: {len(sma_blocks)}, ext labels: {len(ext_labels)}")
print(f"[i] Parentesis delta: {delta}")

if delta == 0:
    DST.write_text(text5, encoding="utf-8")
    print("[ok] FRONTEND.kicad_sch actualizado")
else:
    print(f"[!!] Error parentesis, delta={delta}")