#!/usr/bin/env python3
"""PCB placement - extract the edges and positions, add the new footprints."""
import pathlib, re, uuid

ROOT = pathlib.Path(r"E:\PCB\adapter_AMD_Xilinx_KRIA-KV260")
PCB = ROOT / "CSI2-KRIA-KV260_Rev01.kicad_pcb"

text = PCB.read_text(encoding="utf-8")

# 1. Extraer board outline (gr_line Edge.Cuts)
edge_coords = []
for m in re.finditer(
    r'\(gr_line\s+\(start\s+([-0-9.]+)\s+([-0-9.]+)\)\s+\(end\s+([-0-9.]+)\s+([-0-9.]+)\)\s+\(stroke[^)]+\)\s+\(layer\s+"Edge\.Cuts"',
    text, re.S
):
    edge_coords.append((float(m.group(1)), float(m.group(2))))
    edge_coords.append((float(m.group(3)), float(m.group(4))))

if edge_coords:
    xs = [c[0] for c in edge_coords]
    ys = [c[1] for c in edge_coords]
    print(f"Board bounds: X=[{min(xs):.1f}..{max(xs):.1f}] Y=[{min(ys):.1f}..{max(ys):.1f}]")
else:
    print("No Edge.Cuts found")

# 2. Extract the existing footprints with their positions
fps = re.findall(
    r'\(footprint\s+"([^"]+)"(?:\s+\(layer[^)]+\))?\s*\n\s*(?:.*\n)*?\s*\(at\s+([-0-9.]+)\s+([-0-9.]+)\s+([-0-9.]+)\)',
    text
)
print(f"\nFootprints: {len(fps)}")
# Find the Hirose connectors
for i, (fp, x, y, r) in enumerate(fps):
    if "BM20B" in fp or "Hirose" in fp:
        print(f"  {fp} @ ({float(x):.1f},{float(y):.1f}) rot={r}")

# Min/max positions of all footprints
all_x = [float(x) for _,x,_,_ in fps]
all_y = [float(y) for _,_,y,_ in fps]
print(f"\nComponentes: X=[{min(all_x):.1f}..{max(all_x):.1f}] Y=[{min(all_y):.1f}..{max(all_y):.1f}]")

# Find the free area (above the existing parts)
top_y = max(all_y) if all_y else 0
print(f"Top Y of the parts: {top_y:.1f}")

# 3. Generate footprint blocks to place above
# Free area: Y > top_y (10 mm margin)
place_y_start = top_y + 15

FOOTPRINTS = {
    "J_PWR":  ("EasyEDA:DC-005_5.5-2.5", 40, place_y_start, 0),
    "D_TVS":  ("EasyEDA:SMB-DO-214AA", 55, place_y_start + 5, 0),
    "U_PWR1": ("EasyEDA:SOT-23-6", 75, place_y_start, 0),
    "U_PWR2": ("EasyEDA:USIP-8", 95, place_y_start, 0),
    "U_PWR3": ("EasyEDA:TSOT-23-5", 115, place_y_start, 0),
    "Y_CLK":  ("EasyEDA:OSC-SMD_4P-L3.2-W2.5-BL", 40, place_y_start + 30, 0),
    "U_CLK":  ("EasyEDA:LFCSP-24_L4.0-W4.0-P0.50-TL-EP", 70, place_y_start + 30, 0),
    "U_ADC":  ("EasyEDA:LFCSP-48_L7.0-W7.0-P0.50-BL-EP6.5", 110, place_y_start + 30, 0),
    "U_DAC":  ("EasyEDA:LQFP-48_L7.0-W7.0-P0.50-LS9.0-BL", 155, place_y_start + 30, 0),
    "U_MIX":  ("EasyEDA:LFCSP-24_L4.0-W4.0-P0.50-TL-EP", 155, place_y_start + 55, 0),
    "U_SW1":  ("EasyEDA:QFN-16_L3.0-W3.0-P0.50-TL-EP1.5-1", 35, place_y_start + 55, 0),
    "U_SW2":  ("EasyEDA:QFN-16_L3.0-W3.0-P0.50-TL-EP1.5-1", 55, place_y_start + 55, 0),
    "U_SW3":  ("EasyEDA:QFN-16_L3.0-W3.0-P0.50-TL-EP1.5-1", 75, place_y_start + 55, 0),
    "J_RPI":  ("Connector_PinHeader_2.54mm:PinHeader_2x20_P2.54mm_Vertical", 200, place_y_start + 30, 0),
    "J_SMA1": ("Connector_Coaxial:SMA_Amphenol_132255-11", 35, place_y_start + 80, 90),
    "J_SMA2": ("Connector_Coaxial:SMA_Amphenol_132255-11", 55, place_y_start + 80, 90),
    "J_SMA3": ("Connector_Coaxial:SMA_Amphenol_132255-11", 75, place_y_start + 80, 90),
    "J_SMA4": ("Connector_Coaxial:SMA_Amphenol_132255-11", 155, place_y_start + 80, 90),
}

caps = []
cap_x, cap_y = 40, place_y_start + 100
for i in range(16):
    caps.append((f"C_BP{i+1}", "100n", "Capacitor_SMD:C_0603_1608Metric", cap_x + i*7, cap_y, 0))

fp_blocks = []
for ref, (fp_name, x, y, rot) in FOOTPRINTS.items():
    u = uuid.uuid4()
    fp_blocks.append(f"""	(footprint "{fp_name}"
		(layer "F.Cu")
		(at {x} {y} {rot})
		(property "Reference" "{ref}" (at 0 2 0) (layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15)) (justify left bottom)))
		(property "Value" "{ref}" (at 0 -2 0) (layer "F.Fab") (hide yes) (effects (font (size 1 1) (thickness 0.15)) (justify left bottom)))
		(uuid "{u}")
	)
""")

for ref, val, fp_name, x, y, rot in caps:
    u = uuid.uuid4()
    fp_blocks.append(f"""	(footprint "{fp_name}"
		(layer "F.Cu")
		(at {x} {y} {rot})
		(property "Reference" "{ref}" (at 0 2 0) (layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15)) (justify left bottom)))
		(property "Value" "{val}" (at 0 -2 0) (layer "F.Fab") (hide yes) (effects (font (size 1 1) (thickness 0.15)) (justify left bottom)))
		(uuid "{u}")
	)
""")

# Insert at the end, before the file closes
# Find the last \n)\n that closes the (kicad_pcb ...)
last_close = text.rfind("\n)\n")
if last_close == -1:
    last_close = len(text) - 2

insert_text = "\n".join(fp_blocks) + "\n"
new_text = text[:last_close] + "\n" + insert_text + text[last_close:]
print(new_text[last_close-50:last_close+50])

# Verificar parentesis
cleaned = re.sub(r'"[^"]*"', '""', new_text)
delta = cleaned.count("(") - cleaned.count(")")
print(f"\nNuevos footprints: {len(FOOTPRINTS) + len(caps)}")
print(f"Parentesis delta: {delta}")

if delta == 0:
    PCB.write_text(new_text, encoding="utf-8")
    print(f"[ok] PCB updated. Before {len(text.splitlines())}, now {len(new_text.splitlines())} lines")
else:
    print(f"[!!] Delta={delta}, NO guardado")