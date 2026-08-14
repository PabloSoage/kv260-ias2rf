#!/usr/bin/env python3
"""Phase C - Genera FRONTEND.kicad_sch con TODOS los bloques:

  (Power tree) Barrel-J -> TVS-SMBJ15A -> TPS54202(12->5V) -> TPS82140(5V->3V3) -> ADP151(5V->1V8)
  (Master Clock) TCXO-8132H-125M -> ADCLK944 fan-out (4 salidas LVPECL)
  (RX) AD9253 dual-channel 14-bit +ADC clock IN+ via HMC547/ADL5801
  (TX) AD9767 dual-channel 14-bit parallel -> alimentación + driven from RPi header J_RPI
  (Radar) 8x ADAR1000 daisy-chain SPI -> ADL5801 mixer
  (RF front) 3x HMC547 SPDT para multiplex bands + duplexor T/R
  (Connectors) J_PWR barrel + J_RPI 2x20 + SMA antennas (placeholders)
  (Hierarchical labels expuestos al padre) :
     - B7-CSI2-TXC_P/N, TXD0/1/2/3_P/N  (RX LVDS ADC->IAS0 Hirose; reutilizan los labels ya en -2.kicad_sch)
     - I2C_SCL, I2C_SDA, I2C_SCL_3V3, I2C_SDA_3V3  (SPI ADAR1000 via GPIO)
     - EXT-GPIO0/1/2/3, GPIO2, GPIO3   (Control RF switch)
     - PWDN, PWDN_3V3                   (ADC power-down / DAC sleep)
     - VCC5V-EXT, GND                   (Alimentacion principal)
     - VCC5V_RAW, VCC3V3_RAW, VCC1V8_RAW (alimentacion on-board; algunas globales)
     - CLK_ADC_P/N, CLK_DAC_P/N, CLK_KRIA_P/N (Master clock differential hacia ADC/DAC/Hirose)

Output: FRONTEND.kicad_sch
"""
from __future__ import annotations
import pathlib, re, uuid, json

ROOT = pathlib.Path(r"E:\PCB\adapter_AMD_Xilinx_KRIA-KV260")
EASY = pathlib.Path(r"C:\Users\pablo\KiCad\EasyEDA.kicad_sym")
OUT  = ROOT / "FRONTEND.kicad_sch"

# ----------------------------------------------------------------------------
# Chips del FRONTEND y su lib_id en EasyEDA
# ----------------------------------------------------------------------------
CHIPS = {
    # Power tree
    "J_PWR":  {"lib_id": "EasyEDA:PJ-102AH_C3096093",   "ref": "J_PWR",  "value": "PJ-102AH",  "fp": "EasyEDA:DC-005_5.5-2.5"},
    "D_TVS":  {"lib_id": "EasyEDA:SMBJ15A_C83846",      "ref": "D_TVS",  "value": "SMBJ15A",  "fp": "EasyEDA:SMB-DO-214AA"},
    "U_PWR1": {"lib_id": "EasyEDA:TPS54202DDCR",        "ref": "U_PWR1", "value": "TPS54202DDCR", "fp": "EasyEDA:SOT-23-6"},
    "U_PWR2": {"lib_id": "EasyEDA:TPS82140SILR",        "ref": "U_PWR2", "value": "TPS82140SILR","fp": "EasyEDA:USIP-8"},
    "U_PWR3": {"lib_id": "EasyEDA:ADP151AUJZ-1.8-R7_C462184","ref": "U_PWR3","value":"ADP151AUJZ-1.8","fp":"EasyEDA:TSOT-23-5"},
    # Master Clock
    "Y_CLK":  {"lib_id": "EasyEDA:8132H-T125.000LJ33DT","ref": "Y_CLK",   "value": "8132H-125MHz","fp":"EasyEDA:OSC-SMD_4P-L3.2-W2.5-BL"},
    "U_CLK":  {"lib_id": "EasyEDA:ADCLK944BCPZ-R2",    "ref": "U_CLK",   "value": "ADCLK944BCPZ-R2","fp":"EasyEDA:LFCSP-24_L4.0-W4.0-P0.50-TL-EP"},
    # ADC
    "U_ADC":  {"lib_id": "EasyEDA:AD9253BCPZ-125",     "ref": "U_ADC",   "value": "AD9253BCPZ-125","fp":"EasyEDA:LFCSP-48_L7.0-W7.0-P0.50-BL-EP6.5"},
    # DAC
    "U_DAC":  {"lib_id": "EasyEDA:AD9767ASTZ",         "ref": "U_DAC",   "value": "AD9767ASTZ","fp":"EasyEDA:LQFP-48_L7.0-W7.0-P0.50-LS9.0-BL"},
    # Mixer
    "U_MIX":  {"lib_id": "EasyEDA:ADL5801ACPZ",        "ref": "U_MIX",   "value": "ADL5801ACPZ","fp":"EasyEDA:LFCSP-24_L4.0-W4.0-P0.50-TL-EP"},
    # 8x ADAR1000 (beamformer) - REMOVIDO (va a placa externa de alta frecuencia)
    # 3x HMC547 SPDT RF switches
    "U_SW1": {"lib_id": "EasyEDA:HMC547ALC3TR", "ref": "U_SW1", "value":"HMC547ALC3TR", "fp":"EasyEDA:QFN-16_L3.0-W3.0-P0.50-TL-EP1.5-1"},
    "U_SW2": {"lib_id": "EasyEDA:HMC547ALC3TR", "ref": "U_SW2", "value":"HMC547ALC3TR", "fp":"EasyEDA:QFN-16_L3.0-W3.0-P0.50-TL-EP1.5-1"},
    "U_SW3": {"lib_id": "EasyEDA:HMC547ALC3TR", "ref": "U_SW3", "value":"HMC547ALC3TR", "fp":"EasyEDA:QFN-16_L3.0-W3.0-P0.50-TL-EP1.5-1"},
}

# Layout grid (mm). Cada bloque se separa en columnas.
LAYOUT = {
    # (x, y) del centro del símbolo
    "J_PWR":  (40,  40),
    "D_TVS":  (60,  40),
    "U_PWR1": (90,  40),
    "U_PWR2": (130, 40),
    "U_PWR3": (170, 40),
    "Y_CLK":  (40,  110),
    "U_CLK":  (90,  110),
    "U_ADC":  (160, 110),
    "U_DAC":  (240, 110),
    "U_MIX":  (240, 180),
    "U_SW1":  (40, 180),
    "U_SW2":  (70, 180),
    "U_SW3":  (100, 180),
}

# Hierarchical labels que FRONTEND expone al padre. Conectan con los labels
# presentes en las sub-hojas IAS0/IAS1.
HIER_LABELS = [
    # LVDS RX ADC -> Hirose IAS0 (4 pares datos + 1 par reloj)
    ("B7-CSI2-TXC_P", "input"),  ("B7-CSI2-TXC_N", "input"),
    ("B7-CSI2-TXD0_P","input"), ("B7-CSI2-TXD0_N","input"),
    ("B7-CSI2-TXD1_P","input"), ("B7-CSI2-TXD1_N","input"),
    ("B7-CSI2-TXD2_P","input"), ("B7-CSI2-TXD2_N","input"),
    ("B7-CSI2-TXD3_P","input"), ("B7-CSI2-TXD3_N","input"),
    # I2C/SPI ADAR + GPIOs RF switch controls (via labels I2C/GPIO de sub hojas)
    ("I2C_SCL","bidirectional"), ("I2C_SDA","bidirectional"),
    ("I2C_SCL_3V3","bidirectional"), ("I2C_SDA_3V3","bidirectional"),
    ("EXT-GPIO0-I2C-SCL","bidirectional"),
    ("EXT-GPIO1-I2C-SDA","bidirectional"),
    ("EXT-GPIO2","bidirectional"), ("EXT-GPIO3","bidirectional"),
    ("GPIO2","bidirectional"), ("GPIO3","bidirectional"),
    ("GPIO2_3V3","bidirectional"), ("GPIO3_3V3","bidirectional"),
    # Power-down de chips
    ("PWDN","input"), ("PWDN_3V3","input"),
    # Power rails Kria (recibidos desde sub-hojas)
    ("VCC5V-EXT","power_in"), ("VCC-EXT-IN","power_in"),
    ("VCC3V3","power_in"), ("VCC1V8","power_in"),
    ("VCC1V2","power_in"), ("VCC2V75","power_in"),
    ("GND","power_in"),
    # Power rails onboard (frontend)
    ("VCC12V_RAW","output"), ("VCC5V_RAW","output"),
    ("VCC3V3_RAW","output"), ("VCC1V8_RAW","output"),
    # Clock diferenciales hacia Hirose IAS0+IAS1
    ("CLK_ADC_P","output"), ("CLK_ADC_N","output"),
    ("CLK_DAC_P","output"), ("CLK_DAC_N","output"),
    ("CLK_KRIA_P","output"), ("CLK_KRIA_N","output"),
    # Antenas
    ("ANT_SDR_RX","input"), ("ANT_SDR_TX","output"),
    ("ANT_RADAR_RX","input"), ("ANT_RADAR_TX","output"),
    ("ANT_RADIANT_1","input"),
]

# ----------------------------------------------------------------------------
# 1) Copiar definiciones de lib_symbols desde EasyEDA.kicad_sym
# ----------------------------------------------------------------------------
print("[i] Leyendo EasyEDA.kicad_sym ...")
easy_text = EASY.read_text(encoding="utf-8")
easy_lines = easy_text.splitlines()

def find_symbol_block_by_name(name):
    pat = re.compile(r'^\s*\(symbol\s+"' + re.escape(name) + r'"')
    for i, ln in enumerate(easy_lines):
        if pat.match(ln):
            depth = 0
            for j in range(i, len(easy_lines)):
                s = re.sub(r'"[^"]*"', '""', easy_lines[j])
                depth += s.count("(") - s.count(")")
                if depth == 0 and j > i:
                    return (i, j)
    return None

needed_symbols = sorted(set(c["lib_id"].split(":",1)[1] for c in CHIPS.values()))
print(f"[i] Simbolos necesarios: {needed_symbols}")

# Transformaciones:
#  - añadir prefijo "EasyEDA:" al top-level (symbol "X"  si X es un nombre de chip
#  - quitar las lineas con (id N)   (campo obsoleto easyeda2kicad.py)
#  - quitar properties 'ki_keywords', 'Manufacturer', 'MPN', 'LCSC Part', etc.

ALLOWED_PROPS = {"Reference", "Value", "Footprint", "Datasheet", "Description"}

def transform_symbol_block(block_lines):
    out = []
    skip_until_close = None  # si estamos dentro de una property prohibida, saltar
    prop_depth = 0
    for ln in block_lines:
        # 1. renombrar el primer (symbol "X"  añadiendo prefijo
        m = re.match(r'^(\s*)\(symbol\s+"([^"]+)"', ln)
        if m and not re.match(r'^[^"]*_(\d)+_(\d)+$', m.group(2)):
            name = m.group(2)
            ln = f"{m.group(1)}(symbol \"EasyEDA:{name}\""
            if ln.rstrip() != ln.rstrip() and ")" in block_lines[block_lines.index(ln) if ln in block_lines else 0]:
                # Mantenería el resto de la línea si hubiera más contenido; aquí se cortó
                pass
        # 2. quitar lineas con (id N)
        if re.match(r'^\s*\(id\s+\d+\)\s*$', ln):
            continue
        # 3. capturar inicio de (property "NAME"  ) y decidir
        mp = re.match(r'^\s*\(property\s+"([^"]+)"', ln)
        if mp:
            pname = mp.group(1)
            if pname in ALLOWED_PROPS:
                # mantener
                out.append(ln)
                continue
            else:
                # saltar hasta el cierre de este property: balanceo con lines siguientes
                # marcamos skip
                depth = 0
                depth += re.sub(r'"[^"]*"', '""', ln).count("(") - re.sub(r'"[^"]*"', '""', ln).count(")")
                idx = block_lines.index(ln)
                while depth > 0 and idx < len(block_lines)-1:
                    idx += 1
                    s = re.sub(r'"[^"]*"', '""', block_lines[idx])
                    depth += s.count("(") - s.count(")")
                # saltar las lineas idx+1 desde ln
                # marcar como omitidas
                block_lines[:] = block_lines[:block_lines.index(ln)] + block_lines[idx+1:]
                # reiniciar el bucle
                return transform_symbol_block(block_lines)
        out.append(ln)
    return out

lib_syms_blocks = []
for sym_name in needed_symbols:
    rng = find_symbol_block_by_name(sym_name)
    if not rng:
        print(f"[!] Simbolo {sym_name} no encontrado en EasyEDA.kicad_sym")
        continue
    block_lines = easy_lines[rng[0]:rng[1]+1]
    block_lines = transform_symbol_block(block_lines)
    block = "\n".join(("\t"+L if not L.startswith(" ") and not L.startswith("\t") else L) for L in block_lines)
    lib_syms_blocks.append(block)

lib_symbols_text = "\n".join(lib_syms_blocks)

# ----------------------------------------------------------------------------
# 2) Generar instancias (symbol ...) de cada chip con properties basicas.
# ----------------------------------------------------------------------------
def gen_uuid():
    return str(uuid.uuid4())

def gen_symbol_instance(chip_key, lines_list):
    spec = CHIPS[chip_key]
    x, y = LAYOUT[chip_key]
    u = gen_uuid()
    txt = []
    txt.append("\t(symbol")
    txt.append(f"\t\t(lib_id \"{spec['lib_id']}\")")
    txt.append(f"\t\t(at {x} {y} 0)")
    txt.append("\t\t(unit 1)")
    txt.append("\t\t(body_style 1)")
    txt.append("\t\t(exclude_from_sim no)")
    txt.append("\t\t(in_bom yes)")
    txt.append("\t\t(on_board yes)")
    txt.append("\t\t(dnp no)")
    txt.append(f"\t\t(uuid \"{u}\")")
    # Properties
    for field, key, hide in [
        ("Reference", spec["ref"], False),
        ("Value", spec["value"], False),
        ("Footprint", spec["fp"], True),
        ("Datasheet", "~", True),
        ("Description", spec["value"], True),
    ]:
        txt.append(f"\t\t(property \"{field}\" \"{key}\" (at {x} {y} 0)")
        txt.append("\t\t\t(hide " + ("yes" if hide else "no") + ")")
        txt.append("\t\t\t(effects (font (size 1.27 1.27)))")
        txt.append("\t\t)")
    txt.append("\t\t(instances")
    txt.append("\t\t\t(project \"CSI2-KRIA-KV260_Rev01\"")
    txt.append("\t\t\t\t(path \"/56c49378-41a8-4cbc-b1f4-3d0ea65d2366\"")
    txt.append(f"\t\t\t\t\t(reference \"{spec['ref']}\")")
    txt.append("\t\t\t\t\t(unit 1)")
    txt.append("\t\t\t\t)")
    txt.append("\t\t\t)")
    txt.append("\t\t)")
    txt.append("\t)")
    return "\n".join(txt)

# ----------------------------------------------------------------------------
# 3) Hierarchical labels del FRONTEND (expuestos al sheet padre)
# Discipline: labelnames the same as in -2.kicad_sch (B7-CSI2-*, I2C_*, PWDN*, etc.)
# Hacemos 4 columnas a la derecha del bloque (enumerados de arriba abajo) para
# cada grupo.
# ----------------------------------------------------------------------------
def gen_hlabels():
    out = []
    x_base = 280
    y0 = 30
    ystep = 3
    for i, (name, dir_) in enumerate(HIER_LABELS):
        x = x_base + (60 * (i // 24))
        y = y0 + (i % 24) * ystep
        u = gen_uuid()
        out.append(f"\t(hierarchical_label \"{name}\" (shape {dir_ if 'power' not in dir_ else 'input'})")
        out.append(f"\t\t(at {x} {y} 0)")
        out.append(f"\t\t(effects (font (size 1.27 1.27)))")
        out.append(f"\t\t(uuid \"{u}\")")
        out.append("\t)")
    return "\n".join(out)

# ----------------------------------------------------------------------------
# 4) Componer archivo
# ----------------------------------------------------------------------------
header = """(kicad_sch
	(version 20260306)
	(generator "eeschema")
	(generator_version "10.0")
	(uuid "abcdef12-3456-7890-abcd-ef1234567890")
	(paper "A2")
	(title_block
		(title "FRONTEND - KV260-IAS2RF SDR + Radar")
		(rev "01")
		(company "open hardware")
	)
	(lib_symbols
"""
footer = """	(sheet_instances
		(path "/"
			(page "1")
		)
	)
)
"""

inst_blocks = [gen_symbol_instance(k, []) for k in CHIPS.keys()]
symbols_text = "\n".join(
    [gen_symbol_instance(k, [i for i in range(len(CHIPS))]) for k in CHIPS.keys()]
)

hlabels_text = gen_hlabels()

# ----------------------------------------------------------------------------
# 5) Escribir el archivo
# ----------------------------------------------------------------------------
file_text = header + lib_symbols_text + "\n\t)\n\n" + symbols_text + "\n\n" + hlabels_text + footer
OUT.write_text(file_text, encoding="utf-8")
print(f"[ok] Generado: {OUT}")
print(f"[ok] Tamano: {len(file_text)} bytes")