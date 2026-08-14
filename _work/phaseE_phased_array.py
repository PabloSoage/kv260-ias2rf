#!/usr/bin/env python3
"""Genera PHASED_ARRAY.kicad_sch: placa externa con 8x ADAR1000 + SPI daisy-chain."""
import pathlib, re, uuid

ROOT = pathlib.Path(r"E:\PCB\adapter_AMD_Xilinx_KRIA-KV260")
EASY = pathlib.Path(r"C:\Users\pablo\KiCad\EasyEDA.kicad_sym")
OUT = ROOT / "PHASED_ARRAY.kicad_sch"

def find_symbol_block(name):
    text = EASY.read_text(encoding="utf-8")
    lines = text.splitlines()
    pat = re.compile(r'^\s*\(symbol\s+"' + re.escape(name) + r'"')
    for i, ln in enumerate(lines):
        if pat.match(ln):
            depth = 0
            for j in range(i, len(lines)):
                s = re.sub(r'"[^"]*"', '""', lines[j])
                depth += s.count("(") - s.count(")")
                if depth == 0 and j > i:
                    return "\n".join(lines[i:j+1])
    return None

def transform_block(block):
    """Anade prefijo EasyEDA: y elimina properties no estandar con balanceo."""
    lines = block.splitlines()
    out = []
    skip_depth = 0
    for ln in lines:
        # Si estamos saltando un bloque, contar parentesis
        if skip_depth > 0:
            s = re.sub(r'"[^"]*"', '""', ln)
            skip_depth += s.count("(") - s.count(")")
            continue
        # Detectar propiedad no deseada
        mp = re.match(r'(\s*)\(property\s+"(ki_keywords|Manufacturer|MPN|LCSC Part|JLCPCB Part|Factory Stock)' , ln)
        if mp:
            skip_depth = 1
            continue
        # Quitar (id N)
        if re.match(r'^\s*\(id\s+\d+\)\s*$', ln):
            continue
        # Renombrar symbol top-level
        m = re.match(r'^(\s*)\(symbol\s+"([^"]+)"', ln)
        if m and not re.search(r'_\d+_\d+$', m.group(2)):
            ln = f'{m.group(1)}(symbol "EasyEDA:{m.group(2)}"'
        out.append(ln)
    return "\n".join(out)

# 1. Obtener lib symbol del ADAR1000
adar_block = find_symbol_block("ADAR1000ACCZN")
if not adar_block:
    print("[!] ADAR1000 no encontrado")
    exit(1)
adar_def = transform_block(adar_block)

# 2. Cabecera del archivo
header = f"""(kicad_sch
	(version 20260306)
	(generator "eeschema")
	(generator_version "10.0")
	(uuid "{uuid.uuid4()}")
	(paper "A3")
	(title_block
		(title "Active Antenna Unit - Phased Array 10.5 GHz")
		(rev "01")
		(company "KV260-IAS2RF")
	)
	(lib_symbols
{adar_def}
\t)
"""

# 3. Generar 8 instancias ADAR1000 en columna
instances = ""
spacing_y = 90  # mm entre cada ADAR1000
base_x, base_y = 60, 300
adar_refs = []
for i in range(8):
    ref = f"U_ADR{i+1}"
    adar_refs.append(ref)
    addr = f"{i:03b}"  # ADDR = binary 000..111
    x, y = base_x, base_y - i * spacing_y
    u = uuid.uuid4()
    instances += f"""	(symbol
		(lib_id "EasyEDA:ADAR1000ACCZN")
		(at {x} {y} 0)
		(unit 1)
		(body_style 1)
		(exclude_from_sim no)
		(in_bom yes)
		(on_board yes)
		(dnp no)
		(uuid "{u}")
		(property "Reference" "{ref}" (at {x} {y+5.08} 0) (effects (font (size 1.27 1.27))))
		(property "Value" "ADAR1000ACCZN" (at {x} {y+7.62} 0) (effects (font (size 1.27 1.27))))
		(property "Footprint" "EasyEDA:CC-88-1_ADI" (at {x} {y} 0) (hide yes) (effects (font (size 1.27 1.27))))
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

# 4. Labels para SPI daisy-chain en cada ADAR1000
# Pines relevantes del ADAR1000:
# SCLK (M6), SDIO (M5), SDO (M4), CSB (M3), ADDR0 (N4), ADDR1 (N5)
# TR (N6), TX_LOAD (N3), RX_LOAD (N2)
# RF_IO (A7) - salida a antena

# Coordenadas relativas de los pines en el simbolo ADAR1000 (de pinouts.txt):
# Los pines en el ADAR1000 tienen coordenadas:
#   SDIO -> pin M5, pero no tenemos coordenadas exactas. Veamos el pinout.
#
# ADAR1000 tiene los pines:
#   SPI: CSB(M3), SCLK(M6), SDIO(M5), SDO(M4) - todos en columna izquierda central
#   ADDR: ADDR0(N4), ADDR1(N5) 
#   RF: RF_IO(A7) - unico pin RF combinado
#   TX_LOAD(N3), RX_LOAD(N2), TR(N6)
#   PA_BIAS1(A10), PA_BIAS2(A9), PA_BIAS3(A5), PA_BIAS4(A4)
#   TR_SW_POS(B5), TR_SW_NEG(A3), PA_ON(B3), TR_POL(B4)
#   LNA_BIAS(A11), DET1(N13), DET2(G13), DET3(A1), DET4(G1)
#   Power: AVDD(B11), AVDD3(M10,M11,N11), VDD_5V
#   GND: 40+ pines

# Pin coordinates from pinouts.txt - the ADAR1000 pins have no (x,y) because the format
# was different (LGA grid positions). The AT positions weren't parsed.
# Let me use approximate positions based on the footprint layout.

# For SPI labels, I'll place them on the LEFT side of each chip at fixed offsets.
# The ADAR1000 symbol has pins on left (input) and right (output) sides.
# Left side pins (input): SCLK, SDIO, CSB, ADDR0, ADDR1, TR, TX_LOAD, RX_LOAD etc.
# Right side pins (output): SDO, PA_BIAS, RF_IO, DET, etc.
# Center pins: power/gnd

# SPI daisy-chain: 
#   FPGA → SCLK(in), SDIO(in), CSB(in) [common to all]
#   ADR1 SDO → ADR2 SDIO, ADR2 SDO → ADR3 SDIO, etc.
#   ADR8 SDO → FPGA (optional readback)

spi_labels = ""
for i, ref in enumerate(adar_refs):
    x, y = base_x, base_y - i * spacing_y
    # SPI common (all in parallel except SDIO/SDO which form daisy-chain)
    for name, dx, dy in [
        ("SPI_SCLK", -5, 20),   # SCLK - shared
        ("SPI_CSB", -5, 15),    # CSB - shared
        ("TR_CTRL", -5, 5),     # TR - shared
        ("TX_LOAD", -5, 0),     # TX_LOAD - shared
    ]:
        u = uuid.uuid4()
        spi_labels += f"""	(label "{name}"
		(at {x+dx} {y+dy} 0)
		(effects (font (size 1.27 1.27)) (justify left bottom))
		(uuid "{u}")
	)
"""
    # SDIO input / SDO output for daisy-chain
    if i == 0:
        # First chip: SDIO comes from FPGA
        sdio_net = "SPI_SDIO_IN"
    else:
        sdio_net = f"SPI_SDO_{i}"  # comes from previous chip's SDO
    u = uuid.uuid4()
    spi_labels += f"""	(label "{sdio_net}"
		(at {x-5} {y+12} 0)
		(effects (font (size 1.27 1.27)) (justify left bottom))
		(uuid "{u}")
	)
"""
    # SDO output (named SPI_SDO_i)
    u = uuid.uuid4()
    spi_labels += f"""	(label "SPI_SDO_{i+1}"
		(at {x+5} {y+12} 0)
		(effects (font (size 1.27 1.27)) (justify left bottom))
		(uuid "{u}")
	)
"""
    # ADDR0, ADDR1 (hardwired)
    addr_bits = f"{i:03b}"
    u = uuid.uuid4()
    spi_labels += f"""	(label "{'VCC3V3' if addr_bits[1]=='1' else 'GND'}"
		(at {x-5} {y+8} 0)
		(effects (font (size 1.27 1.27)) (justify left bottom))
		(uuid "{uuid.uuid4()}")
	)
	(label "{'VCC3V3' if addr_bits[0]=='1' else 'GND'}"
		(at {x-5} {y+6} 0)
		(effects (font (size 1.27 1.27)) (justify left bottom))
		(uuid "{uuid.uuid4()}")
	)
"""
    # RF_IO label (pin A7, right side)
    u = uuid.uuid4()
    spi_labels += f"""	(label "RF_ANT_{i+1}"
		(at {x+5} {y+8} 0)
		(effects (font (size 1.27 1.27)) (justify left bottom))
		(uuid "{u}")
	)
"""

# 5. SMA connector for combined RF input
# Use a generic SMA symbol with label RF_COMBINED
sma_x, sma_y = base_x + 40, base_y
sma_inst = ""
for name, sy in [("SMA_RF_IN", base_y - 60),]:
    u = uuid.uuid4()
    sma_inst += f"""	(symbol
		(lib_id "Connector_Coaxial:SMA_EdgeMount")
		(at {sma_x} {sy} 0)
		(unit 1)
		(body_style 1)
		(exclude_from_sim no)
		(in_bom yes)
		(on_board yes)
		(dnp no)
		(uuid "{u}")
		(property "Reference" "J_SMA_RF" (at {sma_x} {sy+3.81} 0) (effects (font (size 1.27 1.27))))
		(property "Value" "RF_COMBINED_IN" (at {sma_x} {sy+6.35} 0) (effects (font (size 1.27 1.27))))
		(property "Footprint" "Connector_Coaxial:SMA_Amphenol_132255-11" (at {sma_x} {sy} 0) (hide yes) (effects (font (size 1.27 1.27))))
		(property "Datasheet" "~" (at {sma_x} {sy} 0) (hide yes) (effects (font (size 1.27 1.27))))
		(instances
			(project "CSI2-KRIA-KV260_Rev01"
				(path "/56c49378-41a8-4cbc-b1f4-3d0ea65d2366"
					(reference "J_SMA_RF")
					(unit 1)
				)
			)
		)
	)
"""
# Label on SMA pin 1
sma_inst += f"""	(label "RF_COMBINED_IN"
		(at {sma_x-7.62} {sy} 0)
		(effects (font (size 1.27 1.27)) (justify left bottom))
		(uuid "{uuid.uuid4()}")
	)
	(label "GND"
		(at {sma_x-7.62} {sy-5.08} 0)
		(effects (font (size 1.27 1.27)) (justify left bottom))
		(uuid "{uuid.uuid4()}")
	)
"""

# 6. Interface header (10-pin IDC) for connection to Carrier board
# Pins: VCC5V, GND, SCLK, SDIO_IN, SDO_8(readback), CSB, TR, TX_LOAD, RX_LOAD
iface_x, iface_y = base_x - 30, base_y - 420
iface_labels = ""
for net, dx, dy in [
    ("VCC5V", 0, 0), ("GND", 0, -2.54), ("SPI_SCLK", 0, -5.08),
    ("SPI_CSB", 0, -7.62), ("SPI_SDIO_IN", 0, -10.16), ("SPI_SDO_8", 0, -12.70),
    ("TR_CTRL", 0, -15.24), ("TX_LOAD", 0, -17.78),
]:
    u = uuid.uuid4()
    iface_labels += f"""	(label "{net}"
		(at {iface_x} {iface_y+dy} 0)
		(effects (font (size 1.27 1.27)) (justify left bottom))
		(uuid "{u}")
	)
"""

# 7. Global labels (power + interfaz)
global_labels = ""
for net, x, y in [
    ("VCC5V", base_x-30, base_y+20),
    ("VCC3V3", base_x-25, base_y+15),
    ("GND", base_x-20, base_y+10),
    ("SPI_SCLK", base_x-15, base_y+5),
    ("SPI_CSB", base_x-10, base_y),
    ("SPI_SDIO_IN", base_x-5, base_y-5),
]:
    u = uuid.uuid4()
    global_labels += f"""	(global_label "{net}" (shape input)
		(at {x} {y} 0)
		(effects (font (size 1.27 1.27)))
		(uuid "{u}")
	)
"""


# 8. Componer archivo
file_text = header + instances + spi_labels + sma_inst + iface_labels + global_labels
file_text += f"""	(sheet_instances
		(path "/"
			(page "1")
		)
	)
)
"""

cleaned = re.sub(r'"[^"]*"', '""', file_text)
delta = cleaned.count("(") - cleaned.count(")")
print(f"[i] Parentesis delta: {delta}")
print(f"[i] Generando {OUT} ({len(file_text)} bytes, delta={delta})")
OUT.write_text(file_text, encoding="utf-8")