#!/usr/bin/env python3
"""Phase C2 - Wiring: add labels to the symbol pins in FRONTEND.kicad_sch.

Connects by net name (label matching) instead of explicit wires.
Generates (label "NET_X" (at X Y) ...) blocks at absolute pin positions.
"""
from __future__ import annotations
import pathlib, re, uuid, json, math

ROOT = pathlib.Path(r"E:\PCB\adapter_AMD_Xilinx_KRIA-KV260")
FRONT = ROOT / "FRONTEND.kicad_sch"
PINOUTS = ROOT / "_work" / "pinouts.txt"

# Chip layout (the same as phaseC)
LAYOUT = {
    "J_PWR": (40, 40),   "D_TVS": (60, 40),
    "U_PWR1": (90, 40),  "U_PWR2": (130, 40), "U_PWR3": (170, 40),
    "Y_CLK": (40, 110),  "U_CLK": (90, 110),
    "U_ADC": (160, 110),  "U_DAC": (240, 110),
    "U_MIX": (240, 180),
    "U_ADR1": (40, 180), "U_ADR2": (60, 180), "U_ADR3": (80, 180),
    "U_ADR4": (100, 180), "U_ADR5": (40, 220), "U_ADR6": (60, 220),
    "U_ADR7": (80, 220), "U_ADR8": (100, 220),
    "U_SW1": (160, 180), "U_SW2": (180, 180), "U_SW3": (200, 180),
}

CHIP_NAMES = {
    "U_ADC":"AD9253BCPZ-125","U_DAC":"AD9767ASTZ","U_CLK":"ADCLK944BCPZ-R2",
    "Y_CLK":"8132H-T125.000LJ33DT","U_MIX":"ADL5801ACPZ",
    "U_SW1":"HMC547ALC3TR","U_SW2":"HMC547ALC3TR","U_SW3":"HMC547ALC3TR",
    "J_PWR":"PJ-102AH_C3096093","D_TVS":"SMBJ15A_C83846",
    "U_PWR1":"TPS54202DDCR","U_PWR2":"TPS82140SILR","U_PWR3":"ADP151AUJZ-1.8-R7_C462184",
}

# Cargar pinos relativos (nombre pin -> (x_rel, y_rel))
def load_pin_offsets():
    t = PINOUTS.read_text(encoding="utf-8")
    sections = {}
    current_chip = None
    current_pins = {}
    for line in t.splitlines():
        if line.startswith("==="):
            current_chip = line.strip("= ").strip()
            current_pins = {}
            sections[current_chip] = current_pins
        elif line.strip().startswith(("1","2","3","4","5","6","7","8","9",
            "A","B","C","D","E","F","G","H","J","K","L","M","N")):
            # Ej: "  1        CLK+       ?    (-20.32,38.10)"
            parts = line.split()
            if len(parts) >= 5:
                pin_num = parts[0]
                pin_name = parts[1]
                coord = parts[-1].strip("(),")
                xs, ys = coord.split(",")
                current_pins[(pin_num, pin_name)] = (float(xs), float(ys))
    return sections

pin_offsets = load_pin_offsets()
print(f"[i] Chips with offsets: {list(pin_offsets.keys())}")

# For a given chip, the absolute position of a pin by its number
def pin_abs(key, pin_number):
    if key not in LAYOUT:
        return None
    chip = CHIP_NAMES.get(key, "")
    if chip not in pin_offsets:
        return None
    sx, sy = LAYOUT[key]
    # Find the pin by number (string key)
    for (num, name), (dx, dy) in pin_offsets[chip].items():
        if num == str(pin_number):
            return (round(sx + dx, 4), round(sy + dy, 4))
    return None

def pin_abs_by_name(key, pin_name_str):
    """Find by partial name (case insensitive)"""
    if key not in LAYOUT:
        return None
    chip = CHIP_NAMES.get(key, "")
    if chip not in pin_offsets:
        return None
    sx, sy = LAYOUT[key]
    for (num, name), (dx, dy) in pin_offsets[chip].items():
        if pin_name_str.upper() in name.upper():
            return (round(sx + dx, 4), round(sy + dy, 4)), num
    return None, None

def gen_label(net_name, x, y, rot=0):
    u = uuid.uuid4()
    return f"""	(label "{net_name}"
		(at {x} {y} {rot})
		(effects
			(font
				(size 1.27 1.27)
			)
			(justify left bottom)
		)
		(uuid "{u}")
	)"""

def gen_global_label(net_name, x, y):
    u = uuid.uuid4()
    return f"""	(global_label "{net_name}" (shape input)
		(at {x} {y} 0)
		(effects
			(font
				(size 1.27 1.27)
			)
		)
		(uuid "{u}")
	)"""

# ---- CONEXIONES ----
labels_blocks = []

# ====== POWER TREE ======
# Barrel Jack J_PWR pin 1 (DC+), pin 2 (GND), pin 3 (SW)
# J_PWR pins: 1-> "1" at(6.35,1.27)  2-> "2" at(6.35,-3.81)  3-> "3" at(6.35,-1.27)
labels_blocks.append(gen_label("VCC12V_RAW", 46.35, 41.27))
labels_blocks.append(gen_label("GND", 46.35, 36.19))  # pin 2

# D_TVS (SMBJ15A): pin 1(1) at(-5.08,0) (6->gnd), pin2(2) at(5.08,0)
# We want pin1 to VCC12V_RAW (through a wire to barrel), pin2 to GND
labels_blocks.append(gen_label("VCC12V_RAW", 54.92, 40.0))
labels_blocks.append(gen_label("GND", 65.08, 40.0))

# TPS54202 pin 3=VIN (at(-12.70,-2.54) rel); absolute
labels_blocks.append(gen_label("VCC12V_RAW", 77.30, 37.46))
# TPS54202 pin 1=GND, pin 2=SW, pin 6=BOOT, pin 4=FB, pin 5=EN
# SW -> VCC5V_RAW (through inductor)
labels_blocks.append(gen_label("VCC5V_RAW", 77.30, 40.0))
labels_blocks.append(gen_label("GND", 77.30, 42.54))

# TPS54202 BOOT -> cap to SW (label both accordingly)
# Actually for minimal, just put VCC5V_RAW at SW pin
labels_blocks.append(gen_global_label("VCC5V_RAW", 90.0, 50.0))  # visual label

# TPS82140: pin 2=VIN (5V), pin 4/5=VOUT(3V3), pin 3/7=GND, pin 6=FB
# VIN at (-11.43, -0.00), so VIN_abs = 130-11.43=118.57, 40+0=40
labels_blocks.append(gen_label("VCC5V_RAW", 118.57, 40.0))
# VOUT at (-11.43,-5.08): absolute (118.57, 34.92)
labels_blocks.append(gen_label("VCC3V3_RAW", 118.57, 34.92))
# GND at (-11.43,-2.54): abs (118.57, 37.46)
labels_blocks.append(gen_label("GND", 118.57, 37.46))
labels_blocks.append(gen_global_label("VCC3V3_RAW", 130.0, 50.0))

# ADP151: pin 1=VIN (5V), pin 2=GND, pin 5=VOUT (1V8), pin 3=EN
# VIN at (-10.16, 2.54): abs (170-10.16=159.84, 40+2.54=42.54)
labels_blocks.append(gen_label("VCC5V_RAW", 159.84, 42.54))
# VOUT at (10.16, 2.54): abs (180.16, 42.54)
labels_blocks.append(gen_label("VCC1V8_RAW", 180.16, 42.54))
# GND at (-10.16, 0): abs (159.84, 40.0)
labels_blocks.append(gen_label("GND", 159.84, 40.0))
labels_blocks.append(gen_global_label("VCC1V8_RAW", 170.0, 50.0))

# ====== MASTER CLOCK ======
# TCXO 8132H: pin 1 E/D/NC, pin 2 GND, pin 3 OUTPUT_RF, pin 4 VCC
# pin at (17.78, -1.27) relative
labels_blocks.append(gen_label("GND", 40.0-17.78, 110.0-1.27))  # GND
# OUTPUT_RF at (17.78, -1.27): abs (57.78, 108.73)
labels_blocks.append(gen_label("CLK_125M", 57.78, 108.73))
# VCC at (17.78, 1.27): abs (57.78, 111.27)
labels_blocks.append(gen_label("VCC3V3_RAW", 57.78, 111.27))

# ADCLK944: pin 1 CLK (input) at (-10.16,7.62) abs
# CLK rel: (-10.16,7.62) -> abs (90-10.16=79.84, 110+7.62=117.62)
labels_blocks.append(gen_label("CLK_125M", 79.84, 117.62))
# Output pairs: Q0+/- (pins 15/14), Q1+/- (pins 13/12), Q2+/- (pins 11/10), Q3+/- (pins 9/～)
# Q0 at (10.16,5.08) -> abs (100.16, 115.08)
labels_blocks.append(gen_label("CLK_ADC_P", 100.16, 115.08))
# ~Q0 at (10.16,2.54) -> abs (100.16, 112.54)
labels_blocks.append(gen_label("CLK_ADC_N", 100.16, 112.54))
# Q1 at (10.16,-5.08) -> abs (100.16, 104.92)
labels_blocks.append(gen_label("CLK_DAC_P", 100.16, 104.92))
# ~Q1 at (10.16,-7.62) -> abs (100.16, 102.38)
labels_blocks.append(gen_label("CLK_DAC_N", 100.16, 102.38))
# Q2 at (-10.16,-7.62) -> abs (79.84, 102.38)
labels_blocks.append(gen_label("CLK_KRIA_P", 79.84, 102.38))
# ~Q2 at (-10.16,-5.08) -> abs (79.84, 104.92)
labels_blocks.append(gen_label("CLK_KRIA_N", 79.84, 104.92))
# Power: VCC (pins 8,13) at (-10.16,-10.16) and (10.16,-0.00)
labels_blocks.append(gen_label("VCC3V3_RAW", 79.84, 99.84))
labels_blocks.append(gen_label("GND", 79.84, 107.46))  # VEE pin 5

# ====== ADC AD9253 (LVDS outputs + clock input) ======
# CLK+/CLK- at (-16.51, 17.78), (-16.51, 20.32) -> abs (143.49, 130.32)
labels_blocks.append(gen_label("CLK_ADC_P", 143.49, 130.32))
labels_blocks.append(gen_label("CLK_ADC_N", 143.49, 127.78))
# D0+/D0- A (channel A data lane): pins 28/27 at (16.51,-20.32),(16.51,-22.86)
labels_blocks.append(gen_label("B7-CSI2-TXD0_P", 176.51, 89.68))
labels_blocks.append(gen_label("B7-CSI2-TXD0_N", 176.51, 87.14))
# D0+/D0- B (channel B data lane): pins 24/23 at (-16.51,-27.94),(-16.51,-25.40)
labels_blocks.append(gen_label("B7-CSI2-TXD1_P", 143.49, 82.06))
labels_blocks.append(gen_label("B7-CSI2-TXD1_N", 143.49, 84.60))
# DCO+/DCO- (shared): pins 18/17 at (-16.51,-12.70),(-16.51,-10.16)
labels_blocks.append(gen_label("B7-CSI2-TXC_P", 143.49, 97.30))
labels_blocks.append(gen_label("B7-CSI2-TXC_N", 143.49, 99.84))
# FCO+/FCO- (shared): pins 20/19 at (-16.51,-17.78),(-16.51,-15.24)
labels_blocks.append(gen_label("B7-CSI2-TXD2_P", 143.49, 92.22))
labels_blocks.append(gen_label("B7-CSI2-TXD2_N", 143.49, 94.76))
# SPI control: SDIO(pin31), SCLK(pin30), CSB(pin32)
labels_blocks.append(gen_label("I2C_SDA_3V3", 176.51, 97.30))
labels_blocks.append(gen_label("I2C_SCL_3V3", 176.51, 94.76))
labels_blocks.append(gen_label("EXT-GPIO2", 176.51, 99.84))
# PDWN (pin33), SYNC (pin44)
labels_blocks.append(gen_label("PWDN_3V3", 176.51, 102.38))
# Power: AVDD pins (3,4,7,34,39,45,46), DRVDD (8,29)
for p_nums in [3,4,7,34,39,45,46]:
    a = pin_abs("U_ADC", p_nums)
    if a: labels_blocks.append(gen_label("VCC1V8_RAW", a[0], a[1]))
for p_nums in [8,29]:
    a = pin_abs("U_ADC", p_nums)
    if a: labels_blocks.append(gen_label("VCC3V3_RAW", a[0], a[1]))
# GND via AD9253 EP = pad 49 at (0,-33.02) rel -> abs (160, 76.98)
labels_blocks.append(gen_label("GND", 160.0, 76.98))

# ====== DAC AD9767 (parallel CMOS) ======
# Power rails
labels_blocks.append(gen_label("VCC3V3_RAW", 222.22, 137.46))# AVDD pin47
labels_blocks.append(gen_label("VCC1V8_RAW", 222.22, 123.38))# DVDD1 pin16
labels_blocks.append(gen_label("VCC1V8_RAW", 222.22, 118.46))# DVDD2 pin22
labels_blocks.append(gen_label("GND", 222.22, 126.68))# DCOM1 pin15
labels_blocks.append(gen_label("GND", 222.22, 114.68))# DCOM2 pin21
labels_blocks.append(gen_label("GND", 222.22, 128.18))# ACOM pin38
# CLK from ADCLK944: CLK1 at (-17.78,-13.97) abs (222.22,96.03)
labels_blocks.append(gen_label("CLK_DAC_P", 222.22, 96.03))
# WRT1 (write) at (-17.78,-11.43) abs (222.22,98.57)
labels_blocks.append(gen_label("DAC_WRT", 222.22, 98.57))
# SLEEP pin37 at (17.78,1.27) abs (257.78,111.27)
labels_blocks.append(gen_label("PWDN", 257.78, 111.27))

# WIRE the DAC parallel data bus to labels named DAC_D0..D13
# Channel A: pins 1-14 (DB13P1..DB0P1) at (-17.78, 29.21..-3.81) step -2.54
base_x, base_y = 240-17.78, 110+29.21  # absolute of DB13P1(MSB)
for i in range(14):
    y = base_y - i*2.54
    labels_blocks.append(gen_label(f"DAC_D{13-i:02d}", base_x, y))

# ====== MIXER ADL5801 ======
# Power: VPLO(5V), VPRF(5V), VPDT(5V)
labels_blocks.append(gen_label("VCC5V_RAW", 228.57, 177.46))
labels_blocks.append(gen_label("VCC5V_RAW", 251.43, 177.46))
labels_blocks.append(gen_label("VCC5V_RAW", 251.43, 164.76))
# LO/IF/RF signals
labels_blocks.append(gen_label("MIX_LO_P", 228.57, 187.62))
labels_blocks.append(gen_label("MIX_LO_N", 228.57, 185.08))
labels_blocks.append(gen_label("MIX_RF_P", 251.43, 169.84))
labels_blocks.append(gen_label("MIX_RF_N", 251.43, 172.38))
labels_blocks.append(gen_label("MIX_IF_P", 251.43, 182.54))
labels_blocks.append(gen_label("MIX_IF_N", 251.43, 185.08))
# ENBL pin 9
labels_blocks.append(gen_label("EXT-GPIO3", 228.57, 172.38))
# GNDs varios
labels_blocks.append(gen_label("GND", 228.57, 190.0))

# ====== RF SWITCH HMC547 (×3) ======
switch_labels = ["RF_BAND_SDR", "RF_BAND_RADAR", "RF_DUPLEX"]
switch_positions = [(40,180), (70,180), (100,180)]
for idx, (sx, sy) in enumerate(switch_positions):
    # RFC (pin 3) at (-11.43,-1.27)
    labels_blocks.append(gen_label(f"RF_SW{idx+1}_COM", sx-11.43, sy-1.27))
    # RF1 (pin 7) at (3.81,-12.70)
    labels_blocks.append(gen_label(f"RF_SW{idx+1}_A", sx+3.81, sy-12.70))
    # RF2 (pin 14) at (3.81,12.70)
    labels_blocks.append(gen_label(f"RF_SW{idx+1}_B", sx+3.81, sy+12.70))
    # Control A (pin 11): at (11.43,1.27)
    labels_blocks.append(gen_label(f"SW{idx+1}_CTRL_A", sx+11.43, sy+1.27))
    # Control B (pin 10): at (11.43,-1.27)
    labels_blocks.append(gen_label(f"SW{idx+1}_CTRL_B", sx+11.43, sy-1.27))
    # GNDs
    labels_blocks.append(gen_label("GND", sx-11.43, sy+1.27))
    labels_blocks.append(gen_label("GND", sx+6.35, sy+12.70))
    labels_blocks.append(gen_label("GND", sx-11.43, sy-3.81))
    labels_blocks.append(gen_label("GND", sx+6.35, sy-12.70))
    labels_blocks.append(gen_label("GND", sx+1.27, sy+12.70))
    labels_blocks.append(gen_label("GND", sx+1.27, sy-12.70))

# ====== Insert the labels at the end of FRONTEND.kicad_sch ======
front_text = FRONT.read_text(encoding="utf-8")
# insert before (sheet_instances
insert_pos = front_text.rfind("(sheet_instances")
if insert_pos == -1:
    print("[!] sheet_instances not found")
    exit(1)

labels_text = "\n".join(labels_blocks) + "\n\n"
new_text = front_text[:insert_pos] + labels_text + front_text[insert_pos:]
FRONT.write_text(new_text, encoding="utf-8")
print(f"[ok] Insertadas {len(labels_blocks)} labels en FRONTEND.kicad_sch")
# Verificar parentesis
import re
cleaned = re.sub(r'"[^"]*"', '""', new_text)
delta = cleaned.count("(") - cleaned.count(")")
print(f"[ok] Parentesis delta: {delta}")