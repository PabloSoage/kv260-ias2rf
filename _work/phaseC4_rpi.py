#!/usr/bin/env python3
"""Add the J_RPI 2x20 connector (RPi 40-pin header) to FRONTEND.kicad_sch.
Creates the lib definition + instance + labels on the DAC and GND pins."""
import pathlib, re, uuid

ROOT = pathlib.Path(r"E:\PCB\adapter_AMD_Xilinx_KRIA-KV260")
DST = ROOT / "FRONTEND.kicad_sch"

text = DST.read_text(encoding="utf-8")

# ---- 1. Definition of the RPi 40-pin symbol in lib_symbols ----
rpi_sym = """	(symbol "Connector:Conn_02x20_RPi"
		(in_bom yes)
		(on_board yes)
		(property "Reference" "J" (at 0 60.96 0) (effects (font (size 1.27 1.27))))
		(property "Value" "RPI_40PIN" (at 0 -60.96 0) (effects (font (size 1.27 1.27))))
		(property "Footprint" "Connector_PinHeader_2.54mm:PinHeader_2x20_P2.54mm_Vertical" (at 0 -63.5 0) (hide yes) (effects (font (size 1.27 1.27))))
		(property "Datasheet" "~" (at 0 0 0) (hide yes) (effects (font (size 1.27 1.27))))
		(symbol "Conn_02x20_RPi_0_1"
			(rectangle (start -10.16 55.88) (end 10.16 -55.88) (stroke (width 0) (type default)) (fill (type background)))
)"""
# generate 40 pins
for row in range(20):
    pin_n = 2*row + 1
    x_left, x_right = -12.70, 12.70
    y = 53.34 - row * 5.08
    rpi_sym += f"""
			(pin bidirectional line (at {x_left} {y} 0) (length 2.54) (name "GPIO{pin_n}" (effects (font (size 1.27 1.27)))) (number "{pin_n}" (effects (font (size 1.27 1.27)))))
			(pin bidirectional line (at {x_right} {y} 0) (length 2.54) (name "GPIO{pin_n+1}" (effects (font (size 1.27 1.27)))) (number "{pin_n+1}" (effects (font (size 1.27 1.27)))))"""
rpi_sym += "\n\t)"

# Insert in lib_symbols (before the first (symbol "EasyEDA" ...)
insert_lib = None
lines = text.splitlines()
for i, ln in enumerate(lines):
    if re.search(r'\(symbol\s+"EasyEDA:', ln):
        insert_lib = i
        break
if insert_lib is None:
    # find the end of lib_symbols
    for i, ln in enumerate(lines):
        if ln.strip() == ")" and i > 0:
            insert_lib = i
            break

if insert_lib:
    lines[insert_lib:insert_lib] = [rpi_sym]
else:
    print("[!] No encontre donde insertar lib_symbol")

# ---- 2. Instantiate the J_RPI connector on the right ----
u_jrpi = uuid.uuid4()
jrpi_x, jrpi_y = 330, 110
jrpi_instance = f"""	(symbol
		(lib_id "Connector:Conn_02x20_RPi")
		(at {jrpi_x} {jrpi_y} 0)
		(unit 1)
		(body_style 1)
		(exclude_from_sim no)
		(in_bom yes)
		(on_board yes)
		(dnp no)
		(uuid "{u_jrpi}")
		(property "Reference" "J_RPI" (at {jrpi_x} {jrpi_y-2.54} 0) (effects (font (size 1.27 1.27))))
		(property "Value" "RPI_40PIN" (at {jrpi_x} {jrpi_y-5.08} 0) (effects (font (size 1.27 1.27))))
		(property "Footprint" "Connector_PinHeader_2.54mm:PinHeader_2x20_P2.54mm_Vertical" (at {jrpi_x} {jrpi_y} 0) (hide yes) (effects (font (size 1.27 1.27))))
		(property "Datasheet" "~" (at {jrpi_x} {jrpi_y} 0) (hide yes) (effects (font (size 1.27 1.27))))
		(instances
			(project "CSI2-KRIA-KV260_Rev01"
				(path "/56c49378-41a8-4cbc-b1f4-3d0ea65d2366"
					(reference "J_RPI")
					(unit 1)
				)
			)
		)
	)"""

# Insert before sheet_instances
text2 = "\n".join(lines) + "\n"
insert2 = text2.rfind("(sheet_instances")
text3 = text2[:insert2] + jrpi_instance + "\n\n" + text2[insert2:]

# ---- 3. Labels on the J_RPI pins ----
# GND pins: 6,9,14,20,25,30,34,39
gnd_pins = [6,9,14,20,25,30,34,39]
labels = []
for gpio in range(1,41):
    row = (gpio-1)//2
    x = 317.30 if gpio % 2 == 1 else 342.70
    y = 163.34 - row * 5.08
    if gpio in gnd_pins:
        labels.append(f"""	(label "GND"
		(at {x} {y} 0)
		(effects (font (size 1.27 1.27)) (justify left bottom))
		(uuid "{uuid.uuid4()}")
	)""")
    elif 1 <= gpio <= 14:
        labels.append(f"""	(label "DAC_D{gpio-1:02d}"
		(at {x} {y} 0)
		(effects (font (size 1.27 1.27)) (justify left bottom))
		(uuid "{uuid.uuid4()}")
	)""")
    elif gpio == 15:
        labels.append(f"""	(label "DAC_WRT"
		(at {x} {y} 0)
		(effects (font (size 1.27 1.27)) (justify left bottom))
		(uuid "{uuid.uuid4()}")
	)""")
    elif 16 <= gpio <= 20:
        # The rest for the ADAR SPI + RF control
        label_map = {16:"EXT-GPIO0-I2C-SCL", 17:"EXT-GPIO1-I2C-SDA", 18:"EXT-GPIO2", 19:"EXT-GPIO3", 20:"GPIO2"}
        net = label_map[gpio]
        labels.append(f"""	(label "{net}"
		(at {x} {y} 0)
		(effects (font (size 1.27 1.27)) (justify left bottom))
		(uuid "{uuid.uuid4()}")
	)""")

# insertar labels
insert_labels = text3.rfind("(sheet_instances")
text4 = text3[:insert_labels] + "\n".join(labels) + "\n\n" + text3[insert_labels:]

# Verificar parentesis
cleaned = re.sub(r'"[^"]*"', '""', text4)
delta = cleaned.count("(") - cleaned.count(")")
if delta != 0:
    print(f"[!!] Delta parentesis = {delta}")
else:
    DST.write_text(text4, encoding="utf-8")
    print(f"[ok] J_RPI connector added + {len(labels)} labels in FRONTEND")